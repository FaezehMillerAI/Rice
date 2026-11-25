"""Functional checks for model selection, output settings and SFT labels."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from sft.trainer import (
    DEFAULT_CONFIG_PATH, build_sft_config, load_config, parse_args,
    resolve_output_paths, run, tokenize_examples,
)
from engine.retriever import KGRetriever
from engine.prompting import SYSTEM_PROMPT


class CharacterChatTokenizer:
    """Small deterministic template for testing labels without downloads."""

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt, return_dict, **kwargs):
        prefix = "<assistant>" + ("<think></think>" if kwargs.get("enable_thinking") is False else "")
        text = "".join(
            (prefix if item["role"] == "assistant" else f"<{item['role']}>")
            + item["content"] + "<end>" for item in messages
        )
        if add_generation_prompt:
            text += prefix
        return {"input_ids": [ord(character) for character in text]}


def example():
    return {
        "scenario_id": "case-1",
        "prompt": [
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Leaves are yellow; KG unavailable."},
        ],
        "completion": [{"role": "assistant", "content": '{"status":"needs_more_information"}'}],
        "metadata": {},
    }


class TrainerTests(unittest.TestCase):
    def test_short_model_name_selects_id_and_model_specific_settings(self):
        with patch("sys.argv", ["sft.trainer", "--model", "phi4-mini"]):
            args = parse_args()
        self.assertEqual(args.config, DEFAULT_CONFIG_PATH)
        config = load_config(args.config, args.model)
        self.assertEqual(config["model_name"], "phi4-mini")
        self.assertEqual(config["model"]["base_model_name_or_path"], "microsoft/Phi-4-mini-instruct")
        self.assertEqual(config["lora"]["target_modules"], ["qkv_proj"])
        smol = load_config(model_name="smollm3-3b")
        self.assertEqual(smol["model"]["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(load_config()["model_name"], "qwen2.5-1.5b")

    def test_training_parameters_format_experiment_name_and_artifact_filenames(self):
        config = load_config(model_name="qwen3-4b")
        config["training"].update(num_train_epochs=3, learning_rate=0.0001, seed=42)
        config["output"].update(
            root_dir="outputs/sft",
            experiment_name="sft_{model}_ep{num_train_epochs}_lr{learning_rate}_seed{seed}",
            sample_preview_filename="{model}_sample_preview.json", run_config_filename="{name}_settings.json",
        )
        paths = resolve_output_paths(config)
        self.assertEqual(paths["directory"].name, "sft_qwen3-4b_ep3_lr1e-4_seed42")
        self.assertEqual(paths["preview"].name, "qwen3-4b_sample_preview.json")
        self.assertEqual(paths["run_config"].name, "sft_qwen3-4b_ep3_lr1e-4_seed42_settings.json")
        config["training"].update(num_train_epochs=5, learning_rate=0.0002, seed=7)
        self.assertEqual(resolve_output_paths(config)["directory"].name, "sft_qwen3-4b_ep5_lr2e-4_seed7")
        config["training"]["learning_rate"] = 0.00025
        self.assertEqual(resolve_output_paths(config)["directory"].name, "sft_qwen3-4b_ep5_lr2.5e-4_seed7")
        self.assertEqual(config["training"]["learning_rate"], 0.00025)

    def test_shared_yaml_settings_reach_sft_config(self):
        config = load_config(model_name="qwen3-4b")
        config["output"]["experiment_name"] = "{model}_baseline"
        stub = SimpleNamespace(SFTConfig=lambda **kwargs: kwargs)
        with patch.dict("sys.modules", {"trl": stub}):
            settings = build_sft_config(config, use_cuda=False, use_mps=False, bf16=False)
        self.assertEqual(settings["run_name"], "qwen3-4b_baseline")
        self.assertEqual(settings["max_length"], config["training"]["max_seq_length"])
        self.assertEqual(settings["learning_rate"], config["training"]["learning_rate"])
        self.assertEqual(settings["eval_steps"], config["logging"]["eval_steps"])
        self.assertTrue(settings["completion_only_loss"])
        self.assertIn("max_seq_length", config["training"])

    def test_only_assistant_json_and_template_tail_receive_labels(self):
        rows, stats = tokenize_examples([example()], CharacterChatTokenizer(), 1024)
        row = rows[0]
        text = "".join(chr(label) for label in row["labels"] if label != -100)
        self.assertEqual(text, example()["completion"][0]["content"] + "<end>")
        self.assertEqual(row["labels"][:stats["longest_prompt"]], [-100] * stats["longest_prompt"])
        self.assertEqual(len(row["input_ids"]), len(row["labels"]))

    def test_non_thinking_assistant_prefix_belongs_to_masked_prompt(self):
        rows, stats = tokenize_examples(
            [example()], CharacterChatTokenizer(), 1024,
            chat_template_kwargs={"enable_thinking": False},
        )
        row = rows[0]
        prefix = "".join(chr(token) for token in row["input_ids"][:stats["longest_prompt"]])
        self.assertTrue(prefix.endswith("<assistant><think></think>"))
        supervised = "".join(chr(label) for label in row["labels"] if label != -100)
        self.assertEqual(supervised, example()["completion"][0]["content"] + "<end>")

    def test_length_limit_rejects_overlong_sequence_without_truncation(self):
        case = example()
        tokenizer = CharacterChatTokenizer()
        prompt = tokenizer.apply_chat_template(
            case["prompt"], tokenize=True, add_generation_prompt=True, return_dict=True,
        )["input_ids"]
        full = tokenizer.apply_chat_template(
            case["prompt"] + case["completion"], tokenize=True,
            add_generation_prompt=False, return_dict=True,
        )["input_ids"]
        maximum = len(prompt) + 10
        self.assertLess(maximum, len(full))
        with self.assertRaises(ValueError) as raised:
            tokenize_examples([case], tokenizer, maximum)
        error = str(raised.exception)
        self.assertIn(case["scenario_id"], error)
        self.assertIn(str(len(full)), error)
        self.assertIn(f"prompt={len(prompt)}", error)
        self.assertIn(f"max_seq_length={maximum}", error)
        self.assertIn("no tokens were truncated", error)

    def test_exact_sequence_limit_preserves_all_assistant_tokens(self):
        case = example()
        tokenizer = CharacterChatTokenizer()
        full = tokenizer.apply_chat_template(
            case["prompt"] + case["completion"], tokenize=True,
            add_generation_prompt=False, return_dict=True,
        )["input_ids"]
        rows, stats = tokenize_examples([case], tokenizer, len(full))
        self.assertEqual(rows[0]["input_ids"], full)
        self.assertEqual(len(rows[0]["labels"]), len(full))
        supervised = "".join(chr(label) for label in rows[0]["labels"] if label != -100)
        expected = case["completion"][0]["content"] + "<end>"
        self.assertEqual(supervised, expected)
        self.assertEqual(stats["supervised_tokens"], len(expected))

    def test_template_without_supervised_assistant_tokens_is_rejected(self):
        for prompt_length in (3, 5):
            with self.subTest(prompt_length=prompt_length):
                class MissingAssistantTokenizer:
                    def apply_chat_template(self, messages, *, tokenize,
                                            add_generation_prompt, return_dict, **kwargs):
                        return {"input_ids": [7] * (prompt_length if add_generation_prompt else 3)}

                case = example()
                case["scenario_id"] = "malformed-template-case"
                with self.assertRaises(ValueError) as raised:
                    tokenize_examples([case], MissingAssistantTokenizer(), 1024)
                self.assertIn(case["scenario_id"], str(raised.exception))
                self.assertIn("no assistant tokens", str(raised.exception))

    def test_direct_trainer_dry_run_overrides_output_directory_without_loading_weights(self):
        config = load_config(model_name="qwen3-4b")
        with tempfile.TemporaryDirectory() as directory:
            config["output"]["sample_preview_filename"] = "sample.json"
            output_directory = Path(directory) / "custom" / "qwen3-4b_trial1"
            with patch("sys.argv", [
                "sft.trainer", "--model", "qwen3-4b", "--output-dir", str(output_directory),
                "--dry-run",
            ]):
                args = parse_args()
            with (
                patch("sft.trainer.load_config", return_value=config) as load,
                patch("sft.trainer.prepare_data", return_value={"train": [example()], "validation": [example()]}) as prepare,
                patch("sft.trainer.load_tokenizer") as tokenizer,
                patch("sft.trainer.load_trainable_model") as weights,
                redirect_stdout(io.StringIO()),
            ):
                summary = run(args)
            load.assert_called_once_with(DEFAULT_CONFIG_PATH, "qwen3-4b")
            retriever = prepare.call_args.kwargs["retriever"]
            self.assertIsInstance(retriever, KGRetriever)
            prepare.assert_called_once_with(config, retriever=retriever)
            tokenizer.assert_not_called()
            weights.assert_not_called()
            self.assertEqual(Path(summary["output_dir"]), output_directory)
            self.assertEqual(resolve_output_paths(config)["directory"], output_directory)
            report = json.loads((output_directory / "sample.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"], summary)
            self.assertEqual(report["examples"]["train"]["completion"], example()["completion"])

    def test_actual_component_versions_reach_startup_and_dry_run_artifacts(self):
        config = load_config(model_name="qwen3-4b")
        version = "v9.8-test"
        revision = "3" * 40
        prompt_version = "v3.7-test"
        original_retrieve = KGRetriever.retrieve
        context_fields = {
            "normalized_observations", "candidate_causes", "supporting_evidence",
            "contradicting_evidence", "missing_observations", "suggested_questions",
            "retrieved_facts", "evidence_fact_ids", "evidence_source_ids",
        }
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for split, data_key in (("train", "train_data_path"), ("validation", "val_data_path")):
                case = {
                    "scenario_id": split,
                    "input": {"user_text": "Rice leaves are yellow."},
                    "target_response": {"status": "needs_more_information", "grounding": []},
                }
                data_path = directory / f"{split}.json"
                data_path.write_text(json.dumps([case]), encoding="utf-8")
                config["dataset"][data_key] = str(data_path)
            args = SimpleNamespace(
                config=DEFAULT_CONFIG_PATH, model="qwen3-4b",
                output_dir=str(directory / "run"), background=False, dry_run=True,
            )
            terminal = io.StringIO()
            with (
                patch("sft.trainer.load_config", return_value=config),
                patch.object(KGRetriever, "version", version),
                patch("sft.trainer.get_retrieval_revision", return_value=revision),
                patch("sft.trainer.SYSTEM_PROMPT_VERSION", prompt_version),
                patch.object(KGRetriever, "retrieve", autospec=True,
                             side_effect=original_retrieve) as retrieve,
                patch("sft.trainer.load_tokenizer") as tokenizer,
                patch("sft.trainer.load_trainable_model") as weights,
                redirect_stdout(terminal),
            ):
                summary = run(args)
            tokenizer.assert_not_called()
            weights.assert_not_called()
            self.assertIn(f"Retrieval version: {version}", terminal.getvalue())
            self.assertIn(f"System prompt version: {prompt_version}", terminal.getvalue())
            self.assertEqual(summary["retrieval_version"], version)
            self.assertEqual(summary["retrieval_revision"], revision)
            self.assertEqual(summary["retrieval_contract_version"], "v0.3")
            self.assertEqual(summary["response_contract_version"], "v0.2")
            self.assertEqual(summary["system_prompt_version"], prompt_version)
            self.assertEqual(retrieve.call_count, 2)
            self.assertIs(retrieve.call_args_list[0].args[0], retrieve.call_args_list[1].args[0])
            paths = resolve_output_paths(config)
            preview = json.loads(paths["preview"].read_text(encoding="utf-8"))
            saved_config = json.loads(paths["run_config"].read_text(encoding="utf-8"))
            self.assertEqual(preview["summary"]["retrieval_version"], version)
            self.assertEqual(preview["summary"]["retrieval_revision"], revision)
            self.assertEqual(preview["summary"]["system_prompt_version"], prompt_version)
            self.assertEqual(saved_config["retrieval"], {"version": version, "git_revision": revision})
            self.assertEqual(saved_config["system_prompt"], {"version": prompt_version})
            self.assertEqual(saved_config["contracts"], {
                "retrieval": "v0.3",
                "response": "v0.2",
            })
            for prepared in preview["examples"].values():
                self.assertEqual(prepared["prompt"][0]["content"], SYSTEM_PROMPT)
                self.assertNotIn(prompt_version, json.dumps(prepared["prompt"]))
                context = prepared["metadata"]["retrieved_context"]
                self.assertEqual(set(context), context_fields)
                self.assertTrue(context["candidate_causes"])
                self.assertTrue(context["retrieved_facts"])
                self.assertTrue(context["evidence_fact_ids"])
                prompt_context = json.loads(prepared["prompt"][1]["content"].split("\n\nretrieved context:\n", 1)[1])
                self.assertEqual(prompt_context, context)


if __name__ == "__main__":
    unittest.main()
