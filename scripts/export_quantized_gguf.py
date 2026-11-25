"""Convert a merged Hugging Face model to verified, quantized GGUF artifacts.

The converter and quantizer are external llama.cpp tools supplied explicitly by
the caller.  All work happens in a sibling staging directory; the requested
output directory appears only after every GGUF and its metadata are validated.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GGUF_MAGIC = b"GGUF"
MODEL_WEIGHT_PATTERNS = ("model*.safetensors", "pytorch_model*.bin")
TOKENIZER_MODEL_FILES = ("tokenizer.json", "tokenizer.model", "spiece.model", "vocab.json")


class DeploymentError(RuntimeError):
    """Raised when conversion inputs, tools, or artifacts fail validation."""


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        raise DeploymentError(f"{label} is missing or empty: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DeploymentError(f"{label} must contain a JSON object: {path}")
    return value


def _nonempty_matches(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    matches = sorted({path for pattern in patterns for path in root.glob(pattern)})
    return [path for path in matches if path.is_file() and path.stat().st_size > 0]


def validate_merged_model(merged: Path) -> dict[str, Any]:
    if not merged.is_dir():
        raise DeploymentError(f"Merged model directory does not exist: {merged}")
    config = _read_json_object(merged / "config.json", "merged model config.json")
    if not _nonempty_matches(merged, MODEL_WEIGHT_PATTERNS):
        raise DeploymentError(f"Merged model has no nonempty model weights: {merged}")
    _read_json_object(merged / "tokenizer_config.json", "merged tokenizer_config.json")
    if not any(
        (merged / name).is_file() and (merged / name).stat().st_size > 0
        for name in TOKENIZER_MODEL_FILES
    ):
        raise DeploymentError(f"Merged model has no tokenizer model: {merged}")
    return config


def _resolve_executable(value: str, label: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or candidate.parent != Path("."):
        # Do not call Path.resolve() here. Python virtual-environment
        # executables are commonly symlinks to the base interpreter; resolving
        # that symlink bypasses the venv and makes its installed packages
        # unavailable to the converter subprocess.
        path = Path(os.path.abspath(
            candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
        ))
        if not path.is_file():
            raise DeploymentError(f"{label} does not exist: {path}")
        if not path.stat().st_mode & 0o111:
            raise DeploymentError(f"{label} is not executable: {path}")
        return str(path)
    located = shutil.which(value)
    if not located:
        raise DeploymentError(f"{label} is not executable or not on PATH: {value}")
    return located


def validate_tools(
    converter: Path, quantizer: str, converter_python: str,
) -> tuple[Path, str, str]:
    if not converter.is_file() or converter.stat().st_size == 0:
        raise DeploymentError(f"Converter script is missing or empty: {converter}")
    python_executable = _resolve_executable(converter_python, "Converter Python")
    quantizer_executable = _resolve_executable(quantizer, "Quantizer")
    return converter, quantizer_executable, python_executable


def normalize_quant_types(groups: Sequence[Sequence[str]]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for raw in group:
            quant_type = raw.strip().upper()
            if not re.fullmatch(r"[A-Z0-9_]+", quant_type):
                raise DeploymentError(f"Invalid quantization type: {raw!r}")
            if quant_type == "F16":
                raise DeploymentError("F16 is the converter reference output, not a quantizer target")
            if quant_type in result:
                raise DeploymentError(f"Duplicate quantization type: {quant_type}")
            result.append(quant_type)
    if not result:
        raise DeploymentError("At least one --quant-type is required")
    return result


def validate_gguf(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= len(GGUF_MAGIC):
        raise DeploymentError(f"GGUF output is missing or empty: {path}")
    with path.open("rb") as stream:
        magic = stream.read(len(GGUF_MAGIC))
    if magic != GGUF_MAGIC:
        raise DeploymentError(f"Invalid GGUF magic in {path}: {magic!r}")


def file_record(path: Path) -> dict[str, Any]:
    return {
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _model_slug(directory: Path) -> str:
    source = directory.parent.name if directory.name in {"merged", "merged-hf"} else directory.name
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", source).strip(".-_")
    if not slug:
        raise DeploymentError(f"Cannot derive an artifact name from {directory}")
    return slug


def export_gguf(
    *,
    merged: Path,
    output: Path,
    converter: Path,
    quantizer: str,
    converter_python: str,
    quant_types: list[str],
    keep_f16: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
) -> dict[str, Any]:
    merged = merged.resolve()
    output = output.resolve()
    quant_types = normalize_quant_types([quant_types])
    if merged == output or merged in output.parents or output in merged.parents:
        raise DeploymentError("Merged model and GGUF output directories must be separate and non-nested")
    run_command = runner or subprocess.run
    model_config = validate_merged_model(merged)
    converter, quantizer, converter_python = validate_tools(
        converter.resolve(), quantizer, converter_python
    )
    if output.exists():
        raise DeploymentError(f"Output path already exists; refusing to overwrite: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.gguf-", dir=output.parent))
    published = False
    try:
        slug = _model_slug(merged)
        reference = staging / f"{slug}-f16.gguf"
        converter_command = [
            converter_python,
            str(converter),
            str(merged),
            "--outfile",
            str(reference),
            "--outtype",
            "f16",
        ]
        run_command(converter_command, check=True)
        validate_gguf(reference)

        quantized: list[tuple[str, Path]] = []
        for quant_type in quant_types:
            target = staging / f"{slug}-{quant_type.lower()}.gguf"
            run_command(
                [quantizer, str(reference), str(target), quant_type],
                check=True,
            )
            validate_gguf(target)
            quantized.append((quant_type, target))

        reference_record = {"format": "F16", **file_record(reference)}
        reference_record["retained"] = keep_f16
        if not keep_f16:
            reference.unlink()

        preferred_quant, preferred_file = quantized[0]
        modelfile = staging / "Modelfile"
        modelfile.write_text(
            "# Tuned GGUF model; the application supplies the canonical prompt.\n"
            f"FROM ./{preferred_file.name}\n"
            "PARAMETER temperature 0.1\n"
            "PARAMETER top_p 0.9\n"
            "PARAMETER seed 42\n"
            "PARAMETER num_ctx 4608\n",
            encoding="utf-8",
        )
        modelfile_text = modelfile.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s*(SYSTEM|TEMPLATE)\b", modelfile_text):
            raise DeploymentError("Generated Modelfile must not embed SYSTEM or TEMPLATE directives")

        source_merge_metadata = None
        merge_metadata_path = merged / "merge_metadata.json"
        if merge_metadata_path.is_file():
            source_merge_metadata = _read_json_object(
                merge_metadata_path, "source merge_metadata.json"
            )

        metadata = {
            "schema_version": "rice.deployment.gguf.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_merged_dir": str(merged),
            "source_model_architectures": model_config.get("architectures", []),
            "converter": str(converter),
            "converter_python": converter_python,
            "quantizer": quantizer,
            "reference": reference_record,
            "quantized": [
                {"quant_type": quant_type, **file_record(path)}
                for quant_type, path in quantized
            ],
            "ollama": {
                "modelfile": modelfile.name,
                "preferred_quant_type": preferred_quant,
                "gguf": preferred_file.name,
            },
            "source_merge_metadata": source_merge_metadata,
        }
        (staging / "deployment_metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )

        staging.rename(output)
        published = True
        print(f"Verified GGUF artifacts published atomically to {output}")
        return metadata
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--merged-dir", "--merged_dir", dest="merged_dir", required=True,
        help="Merged Hugging Face model directory",
    )
    parser.add_argument(
        "--output-dir", "--output_dir", dest="output_dir", required=True,
        help="New directory that will receive verified GGUF artifacts",
    )
    parser.add_argument(
        "--converter", required=True,
        help="Path to llama.cpp convert_hf_to_gguf.py",
    )
    parser.add_argument(
        "--quantizer", required=True,
        help="Path or executable name for llama-quantize",
    )
    parser.add_argument(
        "--converter-python", "--converter_python",
        dest="converter_python", default=sys.executable,
        help="Python executable used to run the converter",
    )
    parser.add_argument(
        "--quant-type", "--quant_type", dest="quant_type_groups",
        action="append", nargs="+", required=True,
        help="One or more llama.cpp quantization types; may be repeated",
    )
    parser.add_argument(
        "--keep-f16", action="store_true",
        help="Retain the intermediate F16 GGUF (default removes it after quantization)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        export_gguf(
            merged=resolve_path(args.merged_dir),
            output=resolve_path(args.output_dir),
            converter=resolve_path(args.converter),
            quantizer=args.quantizer,
            converter_python=args.converter_python,
            quant_types=normalize_quant_types(args.quant_type_groups),
            keep_f16=args.keep_f16,
        )
    except (
        DeploymentError,
        OSError,
        ValueError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"export_quantized_gguf: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
