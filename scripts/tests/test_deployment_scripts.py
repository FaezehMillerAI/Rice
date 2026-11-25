from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import export_quantized_gguf
from scripts import merge_lora


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def make_adapter(root: Path, base_model: str = "example/base-model") -> Path:
    adapter = root / "adapter"
    adapter.mkdir()
    write_json(
        adapter / "adapter_config.json",
        {"base_model_name_or_path": base_model, "peft_type": "LORA"},
    )
    (adapter / "adapter_model.safetensors").write_bytes(b"adapter-weights")
    write_json(adapter / "tokenizer_config.json", {"model_max_length": 4096})
    write_json(adapter / "tokenizer.json", {"version": "1.0"})
    return adapter


def make_merged_model(root: Path) -> Path:
    merged = root / "merged"
    merged.mkdir()
    write_json(merged / "config.json", {"architectures": ["FakeForCausalLM"]})
    (merged / "model.safetensors").write_bytes(b"merged-weights")
    write_json(merged / "tokenizer_config.json", {"model_max_length": 4096})
    write_json(merged / "tokenizer.json", {"version": "1.0"})
    return merged


def make_gguf_tools(root: Path) -> tuple[Path, Path]:
    converter = root / "convert_hf_to_gguf.py"
    converter.write_text("# converter fixture\n", encoding="utf-8")
    quantizer = root / "llama-quantize"
    quantizer.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    quantizer.chmod(0o755)
    return converter, quantizer


class FakeTokenizer:
    def save_pretrained(self, directory: Path) -> None:
        write_json(Path(directory) / "tokenizer_config.json", {"fake": True})
        write_json(Path(directory) / "tokenizer.json", {"version": "1.0"})


class FakeBaseModel:
    def __init__(self) -> None:
        self.to_calls: list[dict[str, object]] = []

    def to(self, **kwargs: object) -> "FakeBaseModel":
        self.to_calls.append(kwargs)
        return self


class FakeMergedModel:
    def __init__(self, fail_save: bool = False) -> None:
        self.fail_save = fail_save
        self.to_calls: list[dict[str, object]] = []

    def to(self, **kwargs: object) -> "FakeMergedModel":
        self.to_calls.append(kwargs)
        return self

    def named_parameters(self) -> list[tuple[str, object]]:
        return [("model.weight", object())]

    def save_pretrained(self, directory: Path, *, safe_serialization: bool) -> None:
        if self.fail_save:
            raise OSError("simulated save failure")
        self.assert_safe_serialization = safe_serialization
        write_json(Path(directory) / "config.json", {"architectures": ["FakeForCausalLM"]})
        (Path(directory) / "model.safetensors").write_bytes(b"merged-weights")


def fake_dependencies(*, fail_save: bool = False) -> tuple[SimpleNamespace, dict[str, object]]:
    dtype = object()
    tokenizer = FakeTokenizer()
    base_model = FakeBaseModel()
    merged_model = FakeMergedModel(fail_save=fail_save)
    adapter_model = SimpleNamespace(
        merge_and_unload=Mock(return_value=merged_model),
    )
    tokenizer_loader = Mock(return_value=tokenizer)
    model_loader = Mock(return_value=base_model)
    peft_loader = Mock(return_value=adapter_model)
    dependencies = SimpleNamespace(
        torch=SimpleNamespace(
            float16="fake-float16",
            bfloat16="fake-bfloat16",
            float32=dtype,
            __version__="fake-torch",
        ),
        transformers=SimpleNamespace(
            AutoTokenizer=SimpleNamespace(from_pretrained=tokenizer_loader),
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=model_loader),
            __version__="fake-transformers",
        ),
        peft=SimpleNamespace(
            PeftModel=SimpleNamespace(from_pretrained=peft_loader),
            __version__="fake-peft",
        ),
    )
    fixtures = {
        "dtype": dtype,
        "tokenizer_loader": tokenizer_loader,
        "model_loader": model_loader,
        "peft_loader": peft_loader,
        "base_model": base_model,
        "adapter_model": adapter_model,
        "merged_model": merged_model,
    }
    return dependencies, fixtures


class MergeLoraTests(unittest.TestCase):
    def test_legacy_flag_aliases_are_supported(self) -> None:
        args = merge_lora.build_parser().parse_args(
            [
                "--lora_adapter", "adapter",
                "--output_dir", "merged",
                "--base_model", "example/base-model",
                "--dry_run",
            ]
        )
        self.assertEqual(args.adapter, "adapter")
        self.assertEqual(args.output_dir, "merged")
        self.assertTrue(args.dry_run)

    def test_explicit_base_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = make_adapter(root)
            with self.assertRaisesRegex(merge_lora.DeploymentError, "does not match"):
                merge_lora.validate_adapter(adapter, "different/base-model")

    def test_checkpoint_can_reuse_parent_tokenizer_and_run_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = make_adapter(root)
            write_json(parent / "run_config.json", {"training": {"max_seq_length": 3072}})
            checkpoint = parent / "checkpoint-10"
            checkpoint.mkdir()
            write_json(
                checkpoint / "adapter_config.json",
                {"base_model_name_or_path": "example/base-model", "peft_type": "LORA"},
            )
            (checkpoint / "adapter_model.safetensors").write_bytes(b"checkpoint")
            output = root / "published"
            dependencies, fixtures = fake_dependencies()

            metadata = merge_lora.merge_adapter(
                adapter=checkpoint,
                output=output,
                dependency_loader=lambda: dependencies,
            )

            fixtures["tokenizer_loader"].assert_called_once_with(
                str(parent), local_files_only=True, trust_remote_code=False
            )
            self.assertEqual(metadata["tokenizer_source"], str(parent))
            self.assertTrue(metadata["training_run_config"]["path"].endswith("run_config.json"))

    def test_dry_run_validates_without_creating_output_or_loading_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = make_adapter(root)
            output = root / "published"
            dependencies, fixtures = fake_dependencies()

            result = merge_lora.merge_adapter(
                adapter=adapter,
                output=output,
                dry_run=True,
                dependency_loader=lambda: dependencies,
            )

            self.assertEqual(result["merge_dtype"], "float32")
            self.assertEqual(result["output_dtype"], "float16")
            self.assertFalse(output.exists())
            fixtures["tokenizer_loader"].assert_not_called()
            fixtures["model_loader"].assert_not_called()

    def test_merge_is_cpu_fp32_safe_and_atomically_published(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = make_adapter(root)
            output = root / "published"
            dependencies, fixtures = fake_dependencies()

            metadata = merge_lora.merge_adapter(
                adapter=adapter,
                output=output,
                dependency_loader=lambda: dependencies,
            )

            dtype = fixtures["dtype"]
            fixtures["model_loader"].assert_called_once_with(
                "example/base-model",
                dtype=dtype,
                device_map=None,
                trust_remote_code=False,
                local_files_only=False,
            )
            fixtures["adapter_model"].merge_and_unload.assert_called_once_with(
                safe_merge=True
            )
            self.assertEqual(
                fixtures["base_model"].to_calls,
                [{"device": "cpu", "dtype": dtype}],
            )
            self.assertEqual(
                fixtures["merged_model"].to_calls,
                [{"device": "cpu", "dtype": "fake-float16"}],
            )
            self.assertTrue((output / "model.safetensors").is_file())
            self.assertTrue((output / "merge_metadata.json").is_file())
            self.assertEqual(metadata["safe_merge"], True)
            self.assertFalse(list(root.glob(".published.merge-*")))

    def test_nonempty_output_is_rejected_before_model_loading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = make_adapter(root)
            output = root / "published"
            output.mkdir()
            (output / "keep.txt").write_text("do not overwrite", encoding="utf-8")
            dependencies, fixtures = fake_dependencies()

            with self.assertRaisesRegex(merge_lora.DeploymentError, "absent or empty"):
                merge_lora.merge_adapter(
                    adapter=adapter,
                    output=output,
                    dependency_loader=lambda: dependencies,
                )

            fixtures["model_loader"].assert_not_called()
            self.assertEqual((output / "keep.txt").read_text(encoding="utf-8"), "do not overwrite")

    def test_failure_removes_staging_and_publishes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = make_adapter(root)
            output = root / "published"
            dependencies, _ = fake_dependencies(fail_save=True)

            with self.assertRaisesRegex(OSError, "simulated save failure"):
                merge_lora.merge_adapter(
                    adapter=adapter,
                    output=output,
                    dependency_loader=lambda: dependencies,
                )

            self.assertFalse(output.exists())
            self.assertFalse(list(root.glob(".published.merge-*")))

    def test_missing_dependencies_fail_without_fake_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = make_adapter(root)
            output = root / "published"
            with patch.object(
                merge_lora,
                "load_dependencies",
                side_effect=merge_lora.DeploymentError("missing dependencies"),
            ):
                return_code = merge_lora.main(
                    ["--adapter", str(adapter), "--output-dir", str(output)]
                )
            self.assertEqual(return_code, 1)
            self.assertFalse(output.exists())

    def test_missing_adapter_keys_are_fatal_and_publish_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = make_adapter(root)
            output = root / "published"
            dependencies, fixtures = fake_dependencies()
            fixtures["peft_loader"].side_effect = UserWarning(
                "Found missing adapter keys while loading the checkpoint: ['lora_A']"
            )

            with self.assertRaisesRegex(merge_lora.DeploymentError, "missing adapter keys"):
                merge_lora.merge_adapter(
                    adapter=adapter,
                    output=output,
                    dependency_loader=lambda: dependencies,
                )

            self.assertFalse(output.exists())


class ExportQuantizedGgufTests(unittest.TestCase):
    def test_converter_python_keeps_virtualenv_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base_python = root / "base-python"
            base_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            base_python.chmod(0o755)
            virtualenv = root / ".venv" / "bin"
            virtualenv.mkdir(parents=True)
            venv_python = virtualenv / "python"
            venv_python.symlink_to(base_python)

            resolved = export_quantized_gguf._resolve_executable(
                str(venv_python), "Converter Python"
            )

            self.assertEqual(resolved, str(venv_python))
            self.assertTrue(Path(resolved).is_symlink())

    def test_legacy_aliases_and_multiple_quant_types_are_supported(self) -> None:
        args = export_quantized_gguf.build_parser().parse_args(
            [
                "--merged_dir", "merged",
                "--output_dir", "gguf",
                "--converter", "convert.py",
                "--quantizer", "llama-quantize",
                "--converter_python", "python3",
                "--quant_type", "q4_k_m", "Q5_K_M",
                "--quant-type", "q8_0",
            ]
        )
        self.assertEqual(
            export_quantized_gguf.normalize_quant_types(args.quant_type_groups),
            ["Q4_K_M", "Q5_K_M", "Q8_0"],
        )

    def test_empty_quant_type_list_is_rejected_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            merged = make_merged_model(root)
            converter, quantizer = make_gguf_tools(root)
            with self.assertRaisesRegex(
                export_quantized_gguf.DeploymentError,
                "At least one --quant-type",
            ):
                export_quantized_gguf.export_gguf(
                    merged=merged,
                    output=root / "gguf",
                    converter=converter,
                    quantizer=str(quantizer),
                    converter_python=sys.executable,
                    quant_types=[],
                )

    def test_real_commands_are_checked_and_artifacts_use_actual_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            merged = make_merged_model(root)
            converter, quantizer = make_gguf_tools(root)
            output = root / "gguf"
            calls: list[tuple[list[str], bool]] = []

            def runner(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
                calls.append((command, check))
                if "--outfile" in command:
                    target = Path(command[command.index("--outfile") + 1])
                    target.write_bytes(b"GGUF-reference-data")
                else:
                    Path(command[2]).write_bytes(b"GGUF-quantized-" + command[3].encode())
                return subprocess.CompletedProcess(command, 0)

            metadata = export_quantized_gguf.export_gguf(
                merged=merged,
                output=output,
                converter=converter,
                quantizer=str(quantizer),
                converter_python=sys.executable,
                quant_types=["Q4_K_M", "Q8_0"],
                keep_f16=True,
                runner=runner,
            )

            self.assertEqual(len(calls), 3)
            self.assertTrue(all(check for _, check in calls))
            self.assertEqual(calls[0][0][-2:], ["--outtype", "f16"])
            self.assertEqual(calls[1][0][-1], "Q4_K_M")
            self.assertEqual(calls[2][0][-1], "Q8_0")
            for record in [metadata["reference"], *metadata["quantized"]]:
                artifact = output / record["filename"]
                self.assertEqual(record["size_bytes"], artifact.stat().st_size)
                self.assertEqual(record["sha256"], export_quantized_gguf.sha256_file(artifact))
            self.assertTrue(metadata["reference"]["retained"])
            serialized = json.dumps(metadata).lower()
            self.assertNotIn("throughput", serialized)
            self.assertNotIn("tokens_per_second", serialized)
            modelfile = (output / "Modelfile").read_text(encoding="utf-8")
            self.assertIn("FROM ./", modelfile)
            self.assertNotIn("SYSTEM", modelfile)
            self.assertNotIn("TEMPLATE", modelfile)
            self.assertTrue((output / "deployment_metadata.json").is_file())
            self.assertFalse(list(root.glob(".gguf.gguf-*")))

    def test_intermediate_f16_is_removed_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            merged = make_merged_model(root)
            converter, quantizer = make_gguf_tools(root)
            output = root / "gguf"

            def runner(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
                if "--outfile" in command:
                    Path(command[command.index("--outfile") + 1]).write_bytes(b"GGUF-reference")
                else:
                    Path(command[2]).write_bytes(b"GGUF-quantized")
                return subprocess.CompletedProcess(command, 0)

            metadata = export_quantized_gguf.export_gguf(
                merged=merged,
                output=output,
                converter=converter,
                quantizer=str(quantizer),
                converter_python=sys.executable,
                quant_types=["Q4_K_M"],
                runner=runner,
            )

            self.assertFalse(metadata["reference"]["retained"])
            self.assertFalse((output / metadata["reference"]["filename"]).exists())
            self.assertTrue((output / metadata["quantized"][0]["filename"]).exists())

    def test_existing_output_is_rejected_without_running_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            merged = make_merged_model(root)
            converter, quantizer = make_gguf_tools(root)
            output = root / "gguf"
            output.mkdir()
            runner = Mock()

            with self.assertRaisesRegex(export_quantized_gguf.DeploymentError, "already exists"):
                export_quantized_gguf.export_gguf(
                    merged=merged,
                    output=output,
                    converter=converter,
                    quantizer=str(quantizer),
                    converter_python=sys.executable,
                    quant_types=["Q4_K_M"],
                    runner=runner,
                )

            runner.assert_not_called()

    def test_converter_failure_leaves_no_output_or_success_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            merged = make_merged_model(root)
            converter, quantizer = make_gguf_tools(root)
            output = root / "gguf"

            def runner(command: list[str], *, check: bool) -> None:
                raise subprocess.CalledProcessError(2, command)

            with self.assertRaises(subprocess.CalledProcessError):
                export_quantized_gguf.export_gguf(
                    merged=merged,
                    output=output,
                    converter=converter,
                    quantizer=str(quantizer),
                    converter_python=sys.executable,
                    quant_types=["Q4_K_M"],
                    runner=runner,
                )

            self.assertFalse(output.exists())
            self.assertFalse(list(root.glob(".gguf.gguf-*")))

    def test_invalid_gguf_magic_is_not_published(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            merged = make_merged_model(root)
            converter, quantizer = make_gguf_tools(root)
            output = root / "gguf"

            def runner(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
                target = Path(command[command.index("--outfile") + 1])
                target.write_bytes(b"NOT-GGUF")
                return subprocess.CompletedProcess(command, 0)

            with self.assertRaisesRegex(export_quantized_gguf.DeploymentError, "Invalid GGUF magic"):
                export_quantized_gguf.export_gguf(
                    merged=merged,
                    output=output,
                    converter=converter,
                    quantizer=str(quantizer),
                    converter_python=sys.executable,
                    quant_types=["Q4_K_M"],
                    runner=runner,
                )

            self.assertFalse(output.exists())
            self.assertFalse(list(root.glob(".gguf.gguf-*")))


if __name__ == "__main__":
    unittest.main()
