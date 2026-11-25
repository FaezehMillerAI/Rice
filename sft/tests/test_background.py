"""Check detached launch wiring without starting a process or loading a model."""

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from contracts.response import RESPONSE_CONTRACT_VERSION
from contracts.retrieval import RETRIEVAL_CONTRACT_VERSION
from sft import trainer
from engine.retriever import KGRetriever


class BackgroundTests(unittest.TestCase):
    def test_background_parent_returns_before_data_or_model_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "selected experiment"
            config = {
                "model_name": "qwen3-4b",
                "training": {"learning_rate": 0.0001},
                "output": {
                    "root_dir": temporary,
                    "experiment_name": "{model}_sft",
                    "sample_preview_filename": "sample_preview.json",
                    "run_config_filename": "run_config.json",
                    "log_filename": "train.log",
                    "pid_filename": "train.pid",
                },
            }
            args = SimpleNamespace(
                config="configs/sft/training_config.yaml", model="qwen3-4b",
                output_dir=str(directory), background=True, dry_run=False,
            )
            version = "v0.2-test"
            revision = "1" * 40
            prompt_version = "v4.2-test"
            launched = {
                "pid": 43210, "output_dir": str(directory),
                "retrieval_version": version, "retrieval_revision": revision,
                "system_prompt_version": prompt_version,
            }
            terminal = io.StringIO()
            with (
                patch("sft.trainer.load_config", return_value=config) as load,
                patch.object(KGRetriever, "version", version),
                patch("sft.trainer.get_retrieval_revision", return_value=revision),
                patch("sft.trainer.SYSTEM_PROMPT_VERSION", prompt_version),
                patch("sft.trainer.launch_background", return_value=launched) as launch,
                patch("sft.trainer.prepare_data") as prepare,
                patch("sft.trainer.load_tokenizer") as tokenizer,
                patch("sft.trainer.load_trainable_model") as model,
                redirect_stdout(terminal),
            ):
                result = trainer.run(args)
            self.assertIs(result, launched)
            load.assert_called_once_with(args.config, args.model)
            prepare.assert_not_called()
            tokenizer.assert_not_called()
            model.assert_not_called()
            launch.assert_called_once()
            passed_args, passed_config, paths = launch.call_args.args
            self.assertIs(passed_args, args)
            self.assertIs(passed_config, config)
            self.assertEqual(passed_config["retrieval"], {"version": version, "git_revision": revision})
            self.assertEqual(passed_config["system_prompt"], {"version": prompt_version})
            self.assertEqual(passed_config["contracts"], {
                "retrieval": RETRIEVAL_CONTRACT_VERSION,
                "response": RESPONSE_CONTRACT_VERSION,
            })
            self.assertIn(f"Retrieval version: {version}", terminal.getvalue())
            self.assertIn(f"System prompt version: {prompt_version}", terminal.getvalue())
            self.assertEqual(paths["directory"], directory)
            self.assertEqual(paths["log"], directory / "train.log")
            self.assertEqual(paths["pid"], directory / "train.pid")

    def test_launcher_builds_detached_child_with_log_pid_and_control_commands(self):
        for platform, dry_run in (("posix", True), ("nt", False)):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary) / "experiment with spaces"
                directory.mkdir()
                log_file = directory / "training log.txt"
                log_file.write_text("previous log\n", encoding="utf-8")
                pid_file = directory / "train.pid"
                paths = {"directory": directory, "log": log_file, "pid": pid_file}
                args = SimpleNamespace(
                    config="configs/sft/training_config.yaml", model="qwen3-4b",
                    output_dir=None, background=True, dry_run=dry_run,
                )
                config = {
                    "model_name": "qwen3-4b",
                    "retrieval": {"version": "v9.8-test", "git_revision": "2" * 40},
                    "system_prompt": {"version": "v3.7-test"},
                }
                process = Mock(return_value=SimpleNamespace(pid=43210))
                process_api = SimpleNamespace(
                    Popen=process, DEVNULL=subprocess.DEVNULL, STDOUT=subprocess.STDOUT,
                    DETACHED_PROCESS=0x00000008, CREATE_NEW_PROCESS_GROUP=0x00000200,
                )
                platform_api = SimpleNamespace(name=platform, environ=os.environ)
                terminal = io.StringIO()
                with (
                    patch("sft.trainer.os", platform_api),
                    patch("sft.trainer.subprocess", process_api),
                    redirect_stdout(terminal),
                ):
                    result = trainer.launch_background(args, config, paths)
                process.assert_called_once()
                command = process.call_args.args[0]
                expected = [
                    sys.executable, "-u", "-m", "sft.trainer",
                    "--config", str(trainer.PROJECT_ROOT / args.config),
                    "--model", "qwen3-4b", "--output-dir", str(directory),
                ]
                if dry_run:
                    expected.append("--dry-run")
                self.assertEqual(command, expected)
                self.assertNotIn("--background", command)
                options = process.call_args.kwargs
                self.assertEqual(Path(options["cwd"]), trainer.PROJECT_ROOT)
                self.assertEqual(options["stdin"], subprocess.DEVNULL)
                self.assertEqual(options["stderr"], subprocess.STDOUT)
                self.assertEqual(Path(options["stdout"].name), log_file)
                self.assertIn("a", options["stdout"].mode)
                self.assertTrue(log_file.read_text(encoding="utf-8").startswith("previous log\n"))
                self.assertEqual(options["env"]["SFT_BACKGROUND"], "1")
                self.assertEqual(options["env"]["PYTHONIOENCODING"], "utf-8")
                self.assertEqual(pid_file.read_text(encoding="utf-8").strip(), "43210")
                self.assertEqual(result, {
                    "pid": 43210, "output_dir": str(directory),
                    "log_file": str(log_file), "pid_file": str(pid_file),
                    "retrieval_version": "v9.8-test", "retrieval_revision": "2" * 40,
                    "retrieval_contract_version": RETRIEVAL_CONTRACT_VERSION,
                    "response_contract_version": RESPONSE_CONTRACT_VERSION,
                    "system_prompt_version": "v3.7-test",
                })
                printed = terminal.getvalue()
                self.assertIn('"retrieval_version": "v9.8-test"', printed)
                self.assertIn('"system_prompt_version": "v3.7-test"', printed)
                if platform == "posix":
                    self.assertTrue(options["start_new_session"])
                    self.assertEqual(options.get("creationflags", 0), 0)
                    self.assertIn(f"tail -n 100 -f {shlex.quote(str(log_file))}", printed)
                    self.assertIn("kill 43210", printed)
                else:
                    self.assertEqual(options["creationflags"], 0x00000008 | 0x00000200)
                    self.assertFalse(options.get("start_new_session", False))
                    self.assertIn("Get-Content", printed)
                    self.assertIn(str(log_file), printed)
                    self.assertIn("-Tail 100", printed)
                    self.assertIn("-Wait", printed)
                    self.assertIn("Stop-Process -Id 43210", printed)

    def test_posix_worker_ignores_hangup_without_changing_foreground_signals(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            args = SimpleNamespace(
                config="configs/sft/training_config.yaml", model="qwen3-4b",
                output_dir=None, background=False, dry_run=True,
            )
            for worker in (False, True):
                with self.subTest(background_worker=worker):
                    config = {
                        "model_name": "qwen3-4b",
                        "model": {"base_model_name_or_path": "Qwen/Qwen3-4B-Instruct-2507"},
                        "output": {},
                    }
                    signal_api = SimpleNamespace(signal=Mock(), SIGHUP=1, SIG_IGN=object())
                    platform_api = SimpleNamespace(
                        name="posix", environ={"SFT_BACKGROUND": "1"} if worker else {},
                    )
                    with (
                        patch("sft.trainer.os", platform_api),
                        patch("sft.trainer.signal", signal_api),
                        patch("sft.trainer.load_config", return_value=config),
                        patch("sft.trainer.get_retrieval_revision", return_value=None),
                        patch("sft.trainer.resolve_output_paths", return_value={
                            "directory": directory, "preview": None, "run_config": None,
                        }),
                        patch("sft.trainer.prepare_data", return_value={"train": [], "validation": []}) as prepare,
                        patch("sft.trainer.load_tokenizer") as tokenizer,
                        patch("sft.trainer.load_trainable_model") as model,
                        redirect_stdout(io.StringIO()),
                    ):
                        trainer.run(args)
                    retriever = prepare.call_args.kwargs["retriever"]
                    self.assertIsInstance(retriever, KGRetriever)
                    prepare.assert_called_once_with(config, retriever=retriever)
                    self.assertEqual(config["retrieval"], {"version": retriever.version, "git_revision": None})
                    self.assertEqual(config["system_prompt"], {"version": trainer.SYSTEM_PROMPT_VERSION})
                    tokenizer.assert_not_called()
                    model.assert_not_called()
                    if worker:
                        signal_api.signal.assert_called_once_with(signal_api.SIGHUP, signal_api.SIG_IGN)
                    else:
                        signal_api.signal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
