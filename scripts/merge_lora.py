"""Strictly merge a PEFT adapter into its recorded base model.

The merge is performed on CPU in FP32.  No output is published until the
merged model and tokenizer have been saved and validated in a sibling staging
directory.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Callable
import warnings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from contracts.response import RESPONSE_CONTRACT_VERSION
from contracts.retrieval import RETRIEVAL_CONTRACT_VERSION


ADAPTER_WEIGHT_PATTERNS = ("adapter_model*.safetensors", "adapter_model*.bin")
TOKENIZER_MODEL_FILES = ("tokenizer.json", "tokenizer.model", "spiece.model", "vocab.json")
MERGED_WEIGHT_PATTERNS = ("model*.safetensors", "pytorch_model*.bin")


class DeploymentError(RuntimeError):
    """Raised when deployment inputs or produced artifacts are unsafe."""


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _nonempty_matches(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    matches = sorted({path for pattern in patterns for path in root.glob(pattern)})
    return [path for path in matches if path.is_file() and path.stat().st_size > 0]


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


def _canonical_model_reference(value: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return str(candidate.resolve())
    project_candidate = (PROJECT_ROOT / candidate).resolve()
    return str(project_candidate) if project_candidate.exists() else value.rstrip("/")


def validate_adapter(adapter: Path, explicit_base: str | None) -> dict[str, Any]:
    if not adapter.is_dir():
        raise DeploymentError(f"Adapter directory does not exist: {adapter}")

    config_path = adapter / "adapter_config.json"
    config = _read_json_object(config_path, "adapter_config.json")
    recorded_base = config.get("base_model_name_or_path")
    if not isinstance(recorded_base, str) or not recorded_base.strip():
        raise DeploymentError("adapter_config.json has no nonempty base_model_name_or_path")
    recorded_base = recorded_base.strip()
    if explicit_base and _canonical_model_reference(explicit_base) != _canonical_model_reference(recorded_base):
        raise DeploymentError(
            f"Explicit base model {explicit_base!r} does not match adapter base {recorded_base!r}"
        )

    weights = _nonempty_matches(adapter, ADAPTER_WEIGHT_PATTERNS)
    if not weights:
        raise DeploymentError(
            f"No nonempty adapter weights found in {adapter}; expected adapter_model*.safetensors or .bin"
        )

    tokenizer_dir = next(
        (
            directory
            for directory in (adapter, adapter.parent)
            if (directory / "tokenizer_config.json").is_file()
            and any(
                (directory / name).is_file()
                and (directory / name).stat().st_size > 0
                for name in TOKENIZER_MODEL_FILES
            )
        ),
        None,
    )
    if tokenizer_dir is None:
        raise DeploymentError(
            f"Adapter tokenizer is incomplete in {adapter} and its parent; "
            f"expected tokenizer_config.json plus one of {', '.join(TOKENIZER_MODEL_FILES)}"
        )
    tokenizer_config = tokenizer_dir / "tokenizer_config.json"
    _read_json_object(tokenizer_config, "tokenizer_config.json")
    tokenizer_models = [
        tokenizer_dir / name for name in TOKENIZER_MODEL_FILES
        if (tokenizer_dir / name).is_file() and (tokenizer_dir / name).stat().st_size > 0
    ]

    tokenizer_files = [tokenizer_config, *tokenizer_models]
    chat_template = tokenizer_dir / "chat_template.jinja"
    if chat_template.is_file() and chat_template.stat().st_size > 0:
        tokenizer_files.append(chat_template)

    return {
        "base_model": explicit_base or recorded_base,
        "recorded_base_model": recorded_base,
        "config": config,
        "config_path": config_path,
        "weights": weights,
        "tokenizer_dir": tokenizer_dir,
        "tokenizer_files": sorted(set(tokenizer_files)),
    }


def validate_output_target(output: Path) -> bool:
    """Return whether an existing empty directory must be replaced at publish time."""
    if not output.exists():
        return False
    if not output.is_dir():
        raise DeploymentError(f"Output path already exists and is not a directory: {output}")
    if any(output.iterdir()):
        raise DeploymentError(f"Output directory must be absent or empty: {output}")
    return True


def load_dependencies() -> SimpleNamespace:
    try:
        import peft
        import torch
        import transformers
    except ImportError as exc:
        raise DeploymentError(
            "Merging requires torch, transformers, and peft in the active environment"
        ) from exc
    return SimpleNamespace(torch=torch, transformers=transformers, peft=peft)


def _library_versions(dependencies: SimpleNamespace) -> dict[str, str | None]:
    return {
        name: getattr(getattr(dependencies, name), "__version__", None)
        for name in ("torch", "transformers", "peft")
    }


def _validate_merged_directory(directory: Path) -> list[Path]:
    _read_json_object(directory / "config.json", "merged model config.json")
    weights = _nonempty_matches(directory, MERGED_WEIGHT_PATTERNS)
    if not weights:
        raise DeploymentError(f"Merged model produced no nonempty model weights in {directory}")
    _read_json_object(directory / "tokenizer_config.json", "merged tokenizer_config.json")
    tokenizer_models = [
        directory / name for name in TOKENIZER_MODEL_FILES
        if (directory / name).is_file() and (directory / name).stat().st_size > 0
    ]
    if not tokenizer_models:
        raise DeploymentError(f"Merged model produced no tokenizer model in {directory}")
    return [*weights, directory / "config.json", directory / "tokenizer_config.json", *tokenizer_models]


def merge_adapter(
    *,
    adapter: Path,
    output: Path,
    explicit_base: str | None = None,
    output_dtype: str = "float16",
    local_files_only: bool = False,
    dry_run: bool = False,
    dependency_loader: Callable[[], SimpleNamespace] | None = None,
) -> dict[str, Any]:
    adapter = adapter.resolve()
    output = output.resolve()
    if adapter == output or adapter in output.parents or output in adapter.parents:
        raise DeploymentError("Adapter and output directories must be separate and non-nested")

    manifest = validate_adapter(adapter, explicit_base)
    existing_empty_output = validate_output_target(output)
    dependencies = (dependency_loader or load_dependencies)()
    if output_dtype not in {"float16", "bfloat16", "float32"}:
        raise DeploymentError(f"Unsupported output dtype: {output_dtype}")
    torch_dtype = getattr(dependencies.torch, output_dtype, None)
    if torch_dtype is None:
        raise DeploymentError(f"Active torch has no dtype {output_dtype}")
    run_config_path = next(
        (
            path
            for path in (adapter / "run_config.json", adapter.parent / "run_config.json")
            if path.is_file()
        ),
        None,
    )
    run_config = (
        _read_json_object(run_config_path, "training run_config.json")
        if run_config_path is not None
        else {}
    )
    retrieval_config = run_config.get("retrieval", {})
    retrieval_config = retrieval_config if isinstance(retrieval_config, dict) else {}
    prompt_config = run_config.get("system_prompt", {})
    prompt_config = prompt_config if isinstance(prompt_config, dict) else {}
    training_config = run_config.get("training", {})
    training_config = training_config if isinstance(training_config, dict) else {}
    model_config = run_config.get("model", {})
    model_config = model_config if isinstance(model_config, dict) else {}

    validation = {
        "adapter": str(adapter),
        "output": str(output),
        "base_model": manifest["base_model"],
        "load_device": "cpu",
        "merge_dtype": "float32",
        "output_dtype": output_dtype,
        "safe_merge": True,
        "merge_method": "merge_and_unload",
        "local_files_only": local_files_only,
        "response_contract_version": RESPONSE_CONTRACT_VERSION,
        "retrieval_contract_version": RETRIEVAL_CONTRACT_VERSION,
        "retrieval_version": retrieval_config.get("version"),
        "system_prompt_version": prompt_config.get("version"),
        "dependencies": _library_versions(dependencies),
    }
    if dry_run:
        print(json.dumps({"dry_run": True, **validation}, indent=2))
        return validation

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.merge-", dir=output.parent))
    published = False
    try:
        torch = dependencies.torch
        transformers = dependencies.transformers
        peft = dependencies.peft

        tokenizer = transformers.AutoTokenizer.from_pretrained(
            str(manifest["tokenizer_dir"]),
            local_files_only=True,
            trust_remote_code=False,
        )
        base_model = transformers.AutoModelForCausalLM.from_pretrained(
            manifest["base_model"],
            dtype=torch.float32,
            device_map=None,
            trust_remote_code=False,
            local_files_only=local_files_only,
            **(
                {"revision": manifest["config"]["revision"]}
                if manifest["config"].get("revision")
                else {}
            ),
        )
        base_model.to(device="cpu", dtype=torch.float32)
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "error",
                    message=r".*Found missing adapter keys while loading the checkpoint:",
                    category=UserWarning,
                )
                adapter_model = peft.PeftModel.from_pretrained(
                    base_model, str(adapter), is_trainable=False
                )
        except UserWarning as exc:
            if "Found missing adapter keys while loading the checkpoint:" not in str(exc):
                raise
            raise DeploymentError(
                "PEFT reported missing adapter keys; refusing to publish an "
                f"incomplete or incompatible adapter: {exc}"
            ) from exc
        try:
            merged_model = adapter_model.merge_and_unload(safe_merge=True)
        except Exception as exc:
            raise DeploymentError(f"LoRA safe merge failed: {exc}") from exc
        if merged_model is None:
            raise DeploymentError("merge_and_unload(safe_merge=True) returned no model")
        peft_model_type = getattr(peft, "PeftModel", None)
        if isinstance(peft_model_type, type) and isinstance(merged_model, peft_model_type):
            raise DeploymentError("LoRA merge returned a PEFT wrapper instead of a plain model")
        leftover = [
            name for name, _ in merged_model.named_parameters()
            if "lora_" in name.lower()
        ]
        if leftover:
            raise DeploymentError(f"Merged model still contains LoRA parameters: {leftover[:5]}")
        merged_model.to(device="cpu", dtype=torch_dtype)

        merged_model.save_pretrained(staging, safe_serialization=True)
        tokenizer.save_pretrained(staging)
        artifacts = _validate_merged_directory(staging)

        metadata = {
            "schema_version": "rice.deployment.merge.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            **validation,
            "loaded_base_commit": getattr(
                getattr(base_model, "config", None), "_commit_hash", None
            ),
            "merged_model_class": type(merged_model).__name__,
            "adapter_config_sha256": sha256_file(manifest["config_path"]),
            "adapter_weights": [
                artifact_record(path, adapter) for path in manifest["weights"]
            ],
            "tokenizer_source": str(manifest["tokenizer_dir"]),
            "adapter_tokenizer": [
                artifact_record(path, manifest["tokenizer_dir"])
                for path in manifest["tokenizer_files"]
            ],
            "training_run_config": (
                {
                    "path": str(run_config_path),
                    "size_bytes": run_config_path.stat().st_size,
                    "sha256": sha256_file(run_config_path),
                    "training_max_seq_length": training_config.get("max_seq_length"),
                    "chat_template_kwargs": model_config.get("chat_template_kwargs", {}),
                }
                if run_config_path is not None
                else None
            ),
            "merged_artifacts": [
                artifact_record(path, staging) for path in sorted(set(artifacts))
            ],
        }
        (staging / "merge_metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )

        if existing_empty_output:
            output.rmdir()
        try:
            staging.rename(output)
        except Exception:
            if existing_empty_output and not output.exists():
                output.mkdir()
            raise
        published = True
        print(f"Merged model published atomically to {output}")
        return metadata
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adapter", "--lora-adapter", "--lora_adapter",
        dest="adapter", required=True,
        help="PEFT adapter directory containing adapter_config.json, weights, and tokenizer",
    )
    parser.add_argument(
        "--output-dir", "--output_dir",
        dest="output_dir", required=True,
        help="New merged Hugging Face model directory",
    )
    parser.add_argument(
        "--base-model", "--base_model",
        dest="base_model",
        help="Optional explicit base; must exactly match adapter_config.json",
    )
    parser.add_argument(
        "--output-dtype", "--output_dtype",
        choices=("float16", "bfloat16", "float32"), default="float16",
        help="Saved merged weight dtype after the FP32 safe merge (default: float16)",
    )
    parser.add_argument(
        "--local-files-only", action="store_true",
        help="Do not download the recorded base model if it is absent from the HF cache",
    )
    parser.add_argument(
        "--dry-run", "--dry_run", dest="dry_run", action="store_true",
        help="Validate all local inputs and dependencies without loading a model or writing output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        merge_adapter(
            adapter=resolve_path(args.adapter),
            output=resolve_path(args.output_dir),
            explicit_base=args.base_model,
            output_dtype=args.output_dtype,
            local_files_only=args.local_files_only,
            dry_run=args.dry_run,
        )
    except (DeploymentError, OSError, ValueError) as exc:
        print(f"merge_lora: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
