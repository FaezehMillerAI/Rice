"""Unit tests for strict output parsing and shared task-level scoring."""

from copy import deepcopy
from contextlib import redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import warnings

import eval.evaluate_unified as unified
import engine.retriever as retriever_module

from eval.evaluate_unified import (
    evaluate_prediction,
    parse_response,
    validate_response,
)


ROOT = Path(__file__).resolve().parents[2]
MODEL_CONFIG = None  # Model aliases are built in; no external model YAML is required.


def response():
    return {
        "status": "needs_more_information",
        "observations_needed": ["question:lesion_shape"],
        "differential": ["disease:rice_blast", "disease:brown_spot"],
        "actions": [],
        "escalation_required": False,
        "grounding": ["FACT-001"],
        "safety_flags": [],
        "user_response": "Could you check the shape of the lesions?",
    }


def annotations():
    return {
        "correct_first_behavior": "ASK",
        "acceptable_differential": ["disease:rice_blast", "disease:brown_spot"],
        "required_confounders": ["disease:brown_spot"],
        "required_questions": ["question:lesion_shape"],
        "escalation_required": False,
        "supporting_fact_ids": ["FACT-001"],
        "safety_flags": [],
    }


class StrictJsonTests(unittest.TestCase):
    def test_parsing_is_separate_from_schema_validation(self):
        parsed, errors = parse_response(' \n {"arbitrary": "object"} \t')
        self.assertEqual(parsed, {"arbitrary": "object"})
        self.assertEqual(errors, [])
        self.assertTrue(validate_response(parsed))

    def test_complete_response_round_trips(self):
        expected = response()
        parsed, errors = parse_response(json.dumps(expected))
        self.assertEqual(parsed, expected)
        self.assertEqual(errors, [])

    def test_rejects_non_objects_wrappers_and_trailing_content(self):
        for raw in (
            "null", "[]", "42", '"text"', "", "{",
            "```json\n{}\n```", "Here is JSON: {}", "{} extra", "{} {}",
        ):
            with self.subTest(raw=raw):
                parsed, errors = parse_response(raw)
                self.assertIsNone(parsed)
                self.assertTrue(errors)

    def test_rejects_duplicate_keys_at_any_depth(self):
        for raw in (
            '{"status":"needs_more_information","status":"provisional_assessment"}',
            '{"nested":{"claim":"FACT-001","claim":"FACT-002"}}',
        ):
            with self.subTest(raw=raw):
                parsed, errors = parse_response(raw)
                self.assertIsNone(parsed)
                self.assertTrue(errors)

    def test_rejects_nonfinite_json_constants(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                parsed, errors = parse_response('{"score":' + value + "}")
                self.assertIsNone(parsed)
                self.assertTrue(errors)


class OutputContractTests(unittest.TestCase):
    def test_accepts_all_three_behavior_shapes(self):
        for status, escalates, questions in (
            ("needs_more_information", False, ["question:lesion_shape"]),
            ("provisional_assessment", False, []),
            ("escalation_required", True, []),
        ):
            with self.subTest(status=status):
                value = response()
                value.update(status=status, escalation_required=escalates,
                             observations_needed=questions)
                self.assertEqual(validate_response(value), [])

    def test_rejects_missing_and_extra_fields(self):
        for key in response():
            with self.subTest(missing=key):
                value = response()
                del value[key]
                self.assertTrue(validate_response(value))
        value = response()
        value["hidden_reasoning"] = "extra"
        self.assertTrue(validate_response(value))

    def test_rejects_wrong_root_and_field_types(self):
        for value in (None, [], "json", True, 1):
            with self.subTest(root=value):
                self.assertTrue(validate_response(value))
        for key, bad_value in (
            ("status", "unknown"),
            ("status", None),
            ("escalation_required", 0),
            ("escalation_required", "false"),
            ("user_response", []),
            ("user_response", None),
        ):
            with self.subTest(key=key, bad_value=bad_value):
                value = response()
                value[key] = bad_value
                self.assertTrue(validate_response(value))

    def test_rejects_non_string_array_items(self):
        for key in ("observations_needed", "differential", "actions",
                    "grounding", "safety_flags"):
            for bad_value in ("single-string", None, [1], [None], [{}], [""]):
                with self.subTest(key=key, bad_value=bad_value):
                    value = response()
                    value[key] = bad_value
                    self.assertTrue(validate_response(value))

    def test_rejects_status_and_escalation_disagreement(self):
        for status, escalates in (
            ("needs_more_information", True),
            ("provisional_assessment", True),
            ("escalation_required", False),
        ):
            with self.subTest(status=status, escalates=escalates):
                value = response()
                value.update(status=status, escalation_required=escalates)
                self.assertTrue(validate_response(value))

    def test_ask_requires_a_question(self):
        value = response()
        value["observations_needed"] = []
        self.assertTrue(validate_response(value))


class PredictionScoringTests(unittest.TestCase):
    def test_perfect_prediction(self):
        result = evaluate_prediction(response(), annotations(),
                                     retrieved_fact_ids=["FACT-001"])
        self.assertTrue(result["schema_compliance"])
        self.assertEqual(result["first_behavior"], "ASK")
        self.assertTrue(result["behavior_correctness"])
        self.assertTrue(result["escalation_correctness"])
        for metric in (
            "differential_top1_precision", "differential_top3_recall", "differential_f1",
            "confounder_recall", "required_question_recall",
            "gold_fact_id_precision", "gold_fact_id_recall",
            "retrieved_fact_id_precision",
        ):
            with self.subTest(metric=metric):
                self.assertEqual(result[metric], 1.0)

    def test_partial_overlap_has_hand_calculable_ranked_differential_scores(self):
        value = response()
        value["differential"] = ["disease:rice_blast", "disease:other"]
        value["grounding"] = ["FACT-001", "FACT-OTHER"]
        gold = annotations()
        gold["acceptable_differential"].append("disease:third_gold_cause")
        gold["required_questions"].append("question:leaf_age")
        result = evaluate_prediction(value, gold,
                                     retrieved_fact_ids=["FACT-001"])
        self.assertAlmostEqual(result["differential_top1_precision"], 1.0)
        self.assertAlmostEqual(result["differential_top3_recall"], 1.0 / 3.0)
        self.assertAlmostEqual(result["differential_f1"], 0.4)
        self.assertEqual(result["confounder_recall"], 0.0)
        self.assertEqual(result["required_question_recall"], 0.5)
        self.assertEqual(result["gold_fact_id_precision"], 0.5)
        self.assertEqual(result["gold_fact_id_recall"], 1.0)
        self.assertEqual(result["retrieved_fact_id_precision"], 0.5)

    def test_duplicate_ids_do_not_inflate_scores(self):
        value = response()
        value["differential"] = ["disease:rice_blast"] * 3 + ["disease:other"]
        value["grounding"] = ["FACT-001", "FACT-001", "FACT-OTHER"]
        result = evaluate_prediction(value, annotations(),
                                     retrieved_fact_ids=["FACT-001"])
        self.assertTrue(result["schema_compliance"])
        self.assertEqual(result["differential_top1_precision"], 1.0)
        self.assertEqual(result["differential_top3_recall"], 0.5)
        self.assertAlmostEqual(result["differential_f1"], 0.5)
        self.assertEqual(result["gold_fact_id_precision"], 0.5)
        self.assertEqual(result["retrieved_fact_id_precision"], 0.5)

    def test_empty_gold_sets_are_not_applicable(self):
        gold = annotations()
        for key in ("acceptable_differential", "required_confounders",
                    "required_questions", "supporting_fact_ids"):
            gold[key] = []
        result = evaluate_prediction(response(), gold)
        for metric in (
            "differential_top1_precision", "differential_top3_recall", "differential_f1",
            "confounder_recall", "required_question_recall",
            "gold_fact_id_precision", "gold_fact_id_recall",
            "retrieved_fact_id_precision",
        ):
            with self.subTest(metric=metric):
                self.assertIsNone(result[metric])

    def test_empty_prediction_sets_against_nonempty_gold_score_zero(self):
        value = response()
        value.update(status="provisional_assessment", observations_needed=[],
                     differential=[], grounding=[])
        result = evaluate_prediction(value, annotations(), retrieved_fact_ids=[])
        self.assertTrue(result["schema_compliance"])
        for metric in (
            "differential_top1_precision", "differential_top3_recall", "differential_f1",
            "confounder_recall", "required_question_recall",
            "gold_fact_id_precision", "gold_fact_id_recall",
            "retrieved_fact_id_precision",
        ):
            with self.subTest(metric=metric):
                self.assertEqual(result[metric], 0.0)

    def test_no_retrieval_is_distinct_from_empty_retrieval(self):
        no_retrieval = evaluate_prediction(response(), annotations())
        empty_retrieval = evaluate_prediction(response(), annotations(),
                                              retrieved_fact_ids=[])
        self.assertIsNone(no_retrieval["retrieved_fact_id_precision"])
        self.assertEqual(empty_retrieval["retrieved_fact_id_precision"], 0.0)

    def test_unregistered_gold_ids_can_still_match_exactly(self):
        value = response()
        value["differential"] = ["disease:not_in_local_registry"]
        gold = annotations()
        gold["acceptable_differential"] = value["differential"][:]
        result = evaluate_prediction(value, gold)
        self.assertTrue(result["schema_compliance"])
        self.assertEqual(result["differential_f1"], 1.0)

    def test_similar_question_ids_are_not_implicitly_mapped(self):
        value = response()
        value["observations_needed"] = ["q:lesion_shape"]
        result = evaluate_prediction(value, annotations())
        self.assertTrue(result["schema_compliance"])
        self.assertEqual(result["required_question_recall"], 0.0)

    def test_invalid_outputs_fail_tasks_instead_of_scoring_as_abstention(self):
        invalid_schema = response()
        invalid_schema["escalation_required"] = True
        for value, errors in (
            (None, ["timeout"]),
            (invalid_schema, []),
            (response(), ["backend failure"]),
        ):
            with self.subTest(value=value, errors=errors):
                result = evaluate_prediction(value, annotations(),
                                             schema_errors=errors)
                self.assertFalse(result["schema_compliance"])
                self.assertEqual(result["first_behavior"], "INVALID")
                self.assertFalse(result["behavior_correctness"])
                self.assertFalse(result["escalation_correctness"])
                for metric in (
                    "differential_top1_precision", "differential_top3_recall",
                    "differential_f1", "confounder_recall",
                    "required_question_recall", "gold_fact_id_precision",
                    "gold_fact_id_recall",
                ):
                    with self.subTest(metric=metric):
                        self.assertEqual(result[metric], 0.0)

    def test_evaluation_does_not_mutate_prediction_or_annotations(self):
        value, gold = response(), annotations()
        original_value, original_gold = deepcopy(value), deepcopy(gold)
        evaluate_prediction(value, gold, retrieved_fact_ids=["FACT-001"])
        self.assertEqual(value, original_value)
        self.assertEqual(gold, original_gold)

    def test_all_gold_targets_agree_with_their_available_annotations(self):
        cases = json.loads((ROOT / "data/eval/gold_eval_v0.3.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 65)
        behavior_counts = {"ASK": 0, "ANSWER": 0, "ESCALATE": 0}
        for case in cases:
            with self.subTest(scenario_id=case["scenario_id"]):
                gold = case["annotations"]
                result = evaluate_prediction(case["target_response"], gold)
                self.assertTrue(result["schema_compliance"])
                self.assertTrue(result["behavior_correctness"])
                self.assertTrue(result["escalation_correctness"])
                expected_causes = set(gold["acceptable_differential"])
                predicted_causes = case["target_response"]["differential"]
                if expected_causes:
                    expected_precision = float(bool(predicted_causes) and predicted_causes[0] == gold["acceptable_differential"][0])
                    expected_recall = len(set(predicted_causes[:3]) & expected_causes) / len(expected_causes)
                    expected_f1 = 2 * len(set(predicted_causes) & expected_causes) / (len(set(predicted_causes)) + len(expected_causes))
                else:
                    expected_precision = expected_recall = expected_f1 = None
                self.assertEqual(result["differential_top1_precision"], expected_precision)
                self.assertEqual(result["differential_top3_recall"], expected_recall)
                self.assertEqual(result["differential_f1"], expected_f1)
                expected_confounders = set(gold["required_confounders"])
                expected_confounder_recall = (len(set(predicted_causes[1:]) & expected_confounders)
                                              / len(expected_confounders) if expected_confounders else None)
                self.assertEqual(result["confounder_recall"], expected_confounder_recall)
                self.assertEqual(result["gold_fact_id_recall"], 1.0 if gold["supporting_fact_ids"] else None)
                expected_question_score = 1.0 if gold["required_questions"] else None
                self.assertEqual(result["required_question_recall"], expected_question_score)
                behavior_counts[result["first_behavior"]] += 1
        self.assertEqual(behavior_counts, {"ASK": 16, "ANSWER": 43, "ESCALATE": 6})

    def test_always_ask_baseline_matches_only_the_sixteen_gold_ask_cases(self):
        cases = json.loads((ROOT / "data/eval/gold_eval_v0.3.json").read_text(encoding="utf-8"))
        scored = [evaluate_prediction(response(), case["annotations"]) for case in cases]
        self.assertEqual(len(scored), 65)
        self.assertEqual(sum(item["behavior_correctness"] for item in scored), 16)
        for case, result in zip(cases, scored):
            if case["annotations"]["correct_first_behavior"] != "ASK":
                self.assertFalse(result["behavior_correctness"])


class ModelResolutionTests(unittest.TestCase):
    def test_full_model_id_needs_no_external_configuration(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("Unexpected model-config read")):
            spec = unified.resolve_model_spec("example/independent-model", None)
        self.assertEqual(spec["base_model"], "example/independent-model")
        self.assertEqual(spec["tokenizer"], "example/independent-model")
        self.assertEqual(spec["chat_template_kwargs"], {})

    def test_explicit_configuration_overrides_builtins_and_missing_path_is_an_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "models.yaml"
            config.write_text(json.dumps({"models": {
                "qwen2.5-1.5b": {"id": "example/custom-model",
                                 "chat_template_kwargs": {"enable_thinking": False}},
            }}), encoding="utf-8")
            spec = unified.resolve_model_spec("qwen2.5-1.5b", None, config)
            self.assertEqual(spec["base_model"], "example/custom-model")
            self.assertEqual(spec["chat_template_kwargs"], {"enable_thinking": False})
            with self.assertRaises(FileNotFoundError):
                unified.resolve_model_spec("Qwen/Qwen2.5-1.5B-Instruct", None,
                                           Path(temporary) / "missing.yaml")

    def test_short_names_and_full_model_ids_preserve_chat_options(self):
        expected = (
            ("qwen2.5-1.5b", "Qwen/Qwen2.5-1.5B-Instruct", {}),
            ("qwen3-4b", "Qwen/Qwen3-4B-Instruct-2507", {}),
            ("phi4-mini", "microsoft/Phi-4-mini-instruct", {}),
            ("smollm3-3b", "HuggingFaceTB/SmolLM3-3B", {"enable_thinking": False}),
            ("qwen3.5-4b", "Qwen/Qwen3.5-4B", {"enable_thinking": False}),
            ("llama3.2-3b", "meta-llama/Llama-3.2-3B-Instruct", {}),
        )
        for short_name, model_id, chat_options in expected:
            with self.subTest(model=short_name):
                by_short = unified.resolve_model_spec(short_name, None, MODEL_CONFIG)
                by_full_id = unified.resolve_model_spec(model_id, None, MODEL_CONFIG)
                for spec in (by_short, by_full_id):
                    self.assertEqual(spec["base_model"], model_id)
                    self.assertEqual(spec["tokenizer"], model_id)
                    self.assertEqual(spec["chat_template_kwargs"], chat_options)
                    self.assertEqual(spec["variant"], "base")
                    self.assertIsNone(spec["adapter"])

    def test_checkpoint_infers_base_and_uses_saved_parent_tokenizer(self):
        with tempfile.TemporaryDirectory() as temporary:
            training_run = Path(temporary) / "training-run"
            checkpoint = training_run / "checkpoint-10"
            checkpoint.mkdir(parents=True)
            (checkpoint / "adapter_config.json").write_text(json.dumps({
                "base_model_name_or_path": "Qwen/Qwen3.5-4B",
            }), encoding="utf-8")
            (training_run / "tokenizer_config.json").write_text("{}", encoding="utf-8")
            (training_run / "run_config.json").write_text(json.dumps({
                "model": {"chat_template_kwargs": {"enable_thinking": False}},
                "training": {"max_seq_length": 1024},
            }), encoding="utf-8")

            spec = unified.resolve_model_spec(None, str(checkpoint), MODEL_CONFIG)
            self.assertEqual(spec["base_model"], "Qwen/Qwen3.5-4B")
            self.assertEqual(spec["variant"], "tuned")
            self.assertEqual(spec["adapter"], str(checkpoint.resolve()))
            self.assertEqual(spec["tokenizer"], str(training_run.resolve()))
            self.assertEqual(spec["chat_template_kwargs"], {"enable_thinking": False})
            self.assertEqual(spec["training_max_seq_length"], 1024)
            self.assertEqual(len(spec["adapter_sha256"]), 64)
            with self.assertRaises(ValueError):
                unified.resolve_model_spec("qwen2.5-1.5b", str(checkpoint), MODEL_CONFIG)


class OptionalDependenciesTests(unittest.TestCase):
    def test_plain_hf_does_not_require_adapter_or_quantization_packages(self):
        def installed(name):
            return object() if name in ("torch", "transformers") else None

        with patch.object(unified.importlib.util, "find_spec", side_effect=installed) as probe:
            unified._require_transformers_dependencies(adapter=False, load_in_4bit=False)
        self.assertEqual({call.args[0] for call in probe.call_args_list}, {"torch", "transformers"})

    def test_missing_hf_packages_explain_default_cuda_and_optional_cpu_installation(self):
        for missing in ("torch", "transformers"):
            with self.subTest(missing=missing), patch.object(
                unified.importlib.util, "find_spec",
                side_effect=lambda name: None if name == missing else object(),
            ):
                with self.assertRaises(RuntimeError) as error:
                    unified._require_transformers_dependencies(adapter=False, load_in_4bit=False)
                self.assertIn(missing, str(error.exception))
                self.assertIn("Install default NVIDIA CUDA support", str(error.exception))
                self.assertIn("'uv sync --locked'", str(error.exception))
                self.assertIn("'uv sync --locked --no-default-groups --group hf'", str(error.exception))

    def test_requested_adapter_or_quantization_packages_have_specific_install_hints(self):
        for missing, adapter, quantized, extra in (
            ("peft", True, False, "--extra adapter"),
            ("accelerate", False, True, "--extra quantization"),
            ("bitsandbytes", False, True, "--extra quantization"),
        ):
            with self.subTest(missing=missing), patch.object(
                unified.importlib.util, "find_spec",
                side_effect=lambda name: None if name == missing else object(),
            ):
                with self.assertRaises(RuntimeError) as error:
                    unified._require_transformers_dependencies(adapter=adapter, load_in_4bit=quantized)
                self.assertIn(missing, str(error.exception))
                self.assertIn(extra, str(error.exception))
                if quantized:
                    self.assertIn("'uv sync --locked --extra quantization'", str(error.exception))

    def test_generator_checks_dependencies_before_importing_or_loading_models(self):
        with (
            patch.object(unified, "_require_transformers_dependencies",
                         side_effect=RuntimeError("INSTALL_OPTIONAL_HF")) as require,
            patch("builtins.__import__", side_effect=AssertionError("Unexpected optional-package import")) as imports,
        ):
            try:
                unified.HFGenerator({"adapter": None}, SimpleNamespace(load_in_4bit=False))
            except RuntimeError as error:
                message = str(error)
            else:
                message = None
        self.assertEqual(message, "INSTALL_OPTIONAL_HF")
        require.assert_called_once_with(adapter=False, load_in_4bit=False)
        imports.assert_not_called()


class HFPrecisionTests(unittest.TestCase):
    def fake_modules(self, *, bf16_supported=True, loaded_dtype="bfloat16"):
        torch = SimpleNamespace(
            float32="torch.float32", float16="torch.float16", bfloat16="torch.bfloat16",
            cuda=SimpleNamespace(is_available=Mock(return_value=True),
                                 is_bf16_supported=Mock(return_value=bf16_supported)),
            backends=SimpleNamespace(mps=SimpleNamespace(is_available=Mock(return_value=False))),
        )
        tokenizer = SimpleNamespace(pad_token=None, eos_token="EOS", model_max_length=8192)
        model = Mock()
        model.config = SimpleNamespace(max_position_embeddings=8192, _commit_hash="mock-revision")
        model.dtype = getattr(torch, loaded_dtype)
        model.get_input_embeddings.return_value.weight.device = "mock-device"
        transformers = SimpleNamespace(
            AutoModelForCausalLM=Mock(from_pretrained=Mock(return_value=model)),
            AutoTokenizer=Mock(from_pretrained=Mock(return_value=tokenizer)),
            BitsAndBytesConfig=Mock(), set_seed=Mock(),
        )
        return torch, transformers

    def load_generator(self, *, device="cpu", dtype="auto", bf16_supported=True):
        args = unified.build_parser().parse_args(["--device", device, "--dtype", dtype])
        torch, transformers = self.fake_modules(bf16_supported=bf16_supported)
        spec = {"adapter": None, "adapter_config": {}, "base_model": "mock-base", "tokenizer": "mock-base"}
        with (
            patch.object(unified, "_require_transformers_dependencies"),
            patch.dict("sys.modules", {"torch": torch, "transformers": transformers}),
        ):
            generator = unified.HFGenerator(spec, args)
        return generator, transformers

    def test_auto_dtype_preserves_device_policy(self):
        for device, supported, expected in (
            ("cpu", True, "torch.float32"), ("cuda", True, "torch.bfloat16"),
            ("cuda", False, "torch.float16"), ("mps", True, "torch.float16"),
        ):
            with self.subTest(device=device, bf16_supported=supported):
                _, transformers = self.load_generator(device=device, bf16_supported=supported)
                self.assertEqual(transformers.AutoModelForCausalLM.from_pretrained.call_args.kwargs["dtype"], expected)

    def test_explicit_dtype_is_forwarded_without_quantizing_or_cpu_upcasting(self):
        for dtype in ("bfloat16", "float16", "float32"):
            with self.subTest(dtype=dtype):
                generator, transformers = self.load_generator(dtype=dtype)
                options = transformers.AutoModelForCausalLM.from_pretrained.call_args.kwargs
                self.assertEqual(options["dtype"], "torch." + dtype)
                self.assertNotIn("quantization_config", options)
                transformers.BitsAndBytesConfig.assert_not_called()
                generator.model.to.assert_called_once_with("cpu")

    def test_explicit_cuda_bf16_requires_support_before_loading_files(self):
        args = unified.build_parser().parse_args(["--device", "cuda", "--dtype", "bfloat16"])
        torch, transformers = self.fake_modules(bf16_supported=False)
        with (
            patch.object(unified, "_require_transformers_dependencies"),
            patch.dict("sys.modules", {"torch": torch, "transformers": transformers}),
            self.assertRaisesRegex(ValueError, "BF16 support; no dtype fallback"),
        ):
            unified.HFGenerator({"adapter": None}, args)
        transformers.AutoTokenizer.from_pretrained.assert_not_called()
        transformers.AutoModelForCausalLM.from_pretrained.assert_not_called()

    def test_explicit_full_bf16_rejects_four_bit_weights(self):
        args = unified.build_parser().parse_args(["--device", "cuda", "--dtype", "bfloat16", "--load-in-4bit"])
        torch, transformers = self.fake_modules()
        with (
            patch.object(unified, "_require_transformers_dependencies"),
            patch.dict("sys.modules", {"torch": torch, "transformers": transformers}),
            self.assertRaisesRegex(ValueError, "full BF16 weights"),
        ):
            unified.HFGenerator({"adapter": None}, args)
        transformers.AutoModelForCausalLM.from_pretrained.assert_not_called()

    def test_run_metadata_records_loaded_dtype_instead_of_auto_request(self):
        args = unified.build_parser().parse_args(["--no-warmup"])
        generator = SimpleNamespace(
            device="cuda:0", context_limit=4608,
            model=SimpleNamespace(dtype="torch.bfloat16", config=SimpleNamespace(_commit_hash="mock-revision")),
        )
        with tempfile.TemporaryDirectory() as temporary, patch.object(unified, "HFGenerator", return_value=generator):
            directory = Path(temporary)
            metadata = {}
            unified.prepare_generator({}, args, metadata, directory)
            saved = json.loads((directory / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(args.dtype, "auto")
        self.assertEqual(saved["effective_dtype"], "torch.bfloat16")
        self.assertEqual(saved["effective_device"], "cuda:0")

    def test_adapter_loading_merges_before_plain_model_device_and_eval(self):
        args = unified.build_parser().parse_args(["--device", "cpu", "--dtype", "bfloat16"])
        torch, transformers = self.fake_modules()
        base = transformers.AutoModelForCausalLM.from_pretrained.return_value
        wrapper = Mock(config=base.config)
        merged = Mock(config=base.config)
        merged.named_parameters.return_value = []
        merged.get_input_embeddings.return_value.weight.device = "adapter-device"
        wrapper.merge_and_unload.return_value = merged
        loader = Mock(return_value=wrapper)
        peft = SimpleNamespace(PeftModel=type("FakePeftModel", (), {"from_pretrained": loader}))
        spec = {"adapter": "mock-adapter", "adapter_config": {}, "base_model": "mock-base", "tokenizer": "mock-base"}
        with (
            patch.object(unified, "_require_transformers_dependencies"),
            patch.dict("sys.modules", {"torch": torch, "transformers": transformers, "peft": peft}),
        ):
            generator = unified.HFGenerator(spec, args)
        loader.assert_called_once_with(base, "mock-adapter", is_trainable=False)
        wrapper.merge_and_unload.assert_called_once_with(safe_merge=True)
        self.assertIs(generator.model, merged)
        self.assertEqual(generator.device, "adapter-device")
        merged.to.assert_called_once_with(device="cpu", dtype="torch.bfloat16")
        merged.eval.assert_called_once_with()
        wrapper.to.assert_not_called()
        wrapper.eval.assert_not_called()
        base.to.assert_not_called()
        base.eval.assert_not_called()

    def test_incomplete_adapter_is_rejected_before_device_transfer_or_evaluation(self):
        for prefix in ("", "Adapter name 'lora' should not be contained in the prefix 'lora_'. "):
            with self.subTest(prefix=prefix):
                args = unified.build_parser().parse_args(["--device", "cpu"])
                torch, transformers = self.fake_modules()
                base = transformers.AutoModelForCausalLM.from_pretrained.return_value
                wrapper = Mock(config=base.config)

                def partial_load(*unused_args, **unused_kwargs):
                    warnings.warn(prefix + "Found missing adapter keys while loading the checkpoint: ['layer.lora_B.default.weight'].")
                    return wrapper

                loader = Mock(side_effect=partial_load)
                peft = SimpleNamespace(PeftModel=SimpleNamespace(from_pretrained=loader))
                spec = {"adapter": "incomplete-adapter", "adapter_config": {}, "base_model": "mock-base", "tokenizer": "mock-base"}
                with (
                    patch.object(unified, "_require_transformers_dependencies"),
                    patch.dict("sys.modules", {"torch": torch, "transformers": transformers, "peft": peft}),
                    self.assertRaisesRegex(RuntimeError, "incomplete-adapter.*incomplete or incompatible tuned model") as raised,
                ):
                    unified.HFGenerator(spec, args)
                self.assertIn("layer.lora_B.default.weight", str(raised.exception))
                loader.assert_called_once_with(base, "incomplete-adapter", is_trainable=False)
                wrapper.to.assert_not_called()
                wrapper.eval.assert_not_called()
                base.to.assert_not_called()
                base.eval.assert_not_called()

    def test_unrelated_adapter_warning_remains_a_warning(self):
        args = unified.build_parser().parse_args(["--device", "cpu"])
        torch, transformers = self.fake_modules()
        wrapper = Mock(config=transformers.AutoModelForCausalLM.from_pretrained.return_value.config)
        merged = Mock(config=wrapper.config)
        merged.named_parameters.return_value = []
        wrapper.merge_and_unload.return_value = merged

        def load_with_warning(*unused_args, **unused_kwargs):
            warnings.warn("Unrelated PEFT compatibility warning")
            return wrapper

        peft = SimpleNamespace(PeftModel=type("FakePeftModel", (), {"from_pretrained": Mock(side_effect=load_with_warning)}))
        spec = {"adapter": "mock-adapter", "adapter_config": {}, "base_model": "mock-base", "tokenizer": "mock-base"}
        with (
            patch.object(unified, "_require_transformers_dependencies"),
            patch.dict("sys.modules", {"torch": torch, "transformers": transformers, "peft": peft}),
            warnings.catch_warnings(record=True) as observed,
        ):
            warnings.simplefilter("always")
            generator = unified.HFGenerator(spec, args)
        self.assertIs(generator.model, merged)
        self.assertEqual([str(item.message) for item in observed], ["Unrelated PEFT compatibility warning"])
        merged.eval.assert_called_once_with()


class RepositoryRootTests(unittest.TestCase):
    def test_eval_and_kg_use_the_same_repository_root(self):
        self.assertEqual(unified.ROOT, ROOT)
        self.assertTrue((unified.ROOT / "engine/__init__.py").is_file())
        self.assertTrue((unified.ROOT / "registry/disease-registry.csv").is_file())


class KGContextTests(unittest.TestCase):
    def setUp(self):
        self.retriever = retriever_module.KGRetriever(str(ROOT))
        self.adapter = unified.KGAdapter(self.retriever)
        self.case = json.loads((ROOT / "data/eval/gold_eval_v0.3.json").read_text(encoding="utf-8"))[0]
        self.public = unified.select_public_case(self.case)

    def test_adapter_exposes_a_detached_catalog_instead_of_engine_registries(self):
        self.assertFalse(hasattr(self.adapter, "engine"))
        self.assertFalse(hasattr(self.adapter, "retriever"))
        first = self.adapter.catalog
        original = deepcopy(first)
        cause_id = next(iter(first["causes"]))
        original_name = first["causes"][cause_id]["canonical_name"]
        first["causes"][cause_id]["canonical_name"] = "changed"
        first["causes"][cause_id]["skos_alt_labels"].append("changed")
        action_id = next(iter(first["action_catalog"]))
        first["action_catalog"][action_id].append("changed")
        first["claims"].clear()
        second = self.retriever.catalog_snapshot()
        self.assertEqual(second["causes"][cause_id]["canonical_name"], original_name)
        self.assertEqual(second, original)

    def test_catalog_snapshot_preserves_the_registry_and_action_catalog(self):
        from eval.response_consistency import build_action_catalog

        engine = self.retriever.engine
        catalog = self.retriever.catalog_snapshot()
        self.assertEqual(set(catalog["causes"]), set(engine.diseases))
        self.assertEqual(set(catalog["questions"]), set(engine.questions))
        self.assertEqual(set(catalog["claims"]), set(engine.claims))
        self.assertEqual(catalog["action_catalog"], build_action_catalog(engine))
        for claim_id, row in engine.claims.items():
            with self.subTest(claim_id=claim_id):
                self.assertEqual(
                    catalog["evidence_sources_by_fact"][claim_id],
                    row["source_id"],
                )
        for fact_id, row in self.retriever.richard_facts.items():
            with self.subTest(fact_id=fact_id):
                self.assertEqual(
                    catalog["evidence_sources_by_fact"][fact_id],
                    row.get("source_id") or "source:irri_rice_doctor_2024",
                )

    def test_real_case_has_nine_context_keys_and_observation_targets(self):
        original = deepcopy(self.public)
        context = self.adapter.retrieve(self.public, 3, 2)
        self.assertEqual(set(context), {
            "normalized_observations", "candidate_causes", "supporting_evidence",
            "contradicting_evidence", "missing_observations", "suggested_questions",
            "retrieved_facts", "evidence_fact_ids", "evidence_source_ids",
        })
        self.assertEqual(self.public, original)
        self.assertTrue(context["candidate_causes"])
        self.assertLessEqual(len(context["candidate_causes"]), 3)
        self.assertTrue(context["suggested_questions"])
        self.assertLessEqual(len(context["suggested_questions"]), 2)
        for question in context["suggested_questions"]:
            self.assertIn(question["target_observation_id"], context["missing_observations"])
            self.assertNotIn(question["question_id"], context["missing_observations"])
            self.assertTrue(question["farmer_friendly_phrasing"] or question["canonical_text"])
        self.assertEqual(
            {fact["claim_id"] for fact in context["retrieved_facts"]},
            set(context["evidence_fact_ids"]),
        )
        for fact in context["retrieved_facts"]:
            self.assertEqual(set(fact), {
                "claim_id", "subject_uri", "predicate_uri", "object_uri",
                "source_id", "source_section", "source_text_span",
            })
        self.assertEqual(context, self.retriever.retrieve(self.public, 3, 2))

    def test_direct_retrieve_and_public_helper_share_one_context_contract(self):
        retriever = self.retriever
        self.assertFalse(hasattr(retriever, "retrieve_context"))
        self.assertFalse(hasattr(retriever, "to_slm_context"))
        expected = retriever.retrieve(self.public, 2, 1)
        with patch.object(retriever_module, "_DEFAULT_RETRIEVER", retriever):
            context = retriever_module.retrieve_kg(
                self.public, top_k_candidates=2, top_k_questions=1,
                workspace_root=retriever.workspace_root,
            )
        self.assertEqual(context, expected)
        self.assertIsNot(context, expected)
        self.assertIsNot(context["suggested_questions"], expected["suggested_questions"])
        context["suggested_questions"][0]["canonical_text"] = "Changed helper result"
        self.assertEqual(retriever.retrieve(self.public, 2, 1), expected)

    def test_retrieval_result_is_independent_of_registry_and_later_calls(self):
        retriever = self.retriever
        engine = retriever.engine
        original_registry = deepcopy((engine.questions, engine.claims, engine.evidence_rules))
        public = deepcopy(self.public)
        public["input"]["user_text"] = "Yellow leaves have wavy water-soaked lesions. No bacterial ooze is present."
        original_public = deepcopy(public)
        context = retriever.retrieve(public, 5, 3)
        expected = deepcopy(context)
        self.assertTrue(context["suggested_questions"])
        self.assertTrue(context["retrieved_facts"])
        self.assertTrue(context["supporting_evidence"])
        context["candidate_causes"].append("disease:changed")
        context["evidence_fact_ids"].clear()
        context["normalized_observations"][0]["state"] = "CHANGED"
        context["suggested_questions"][0]["canonical_text"] = "Changed question"
        context["retrieved_facts"][0]["source_text_span"] = "Changed fact"
        context["supporting_evidence"][0]["observation_id"] = "symptom:changed"
        self.assertEqual((engine.questions, engine.claims, engine.evidence_rules), original_registry)
        self.assertEqual(public, original_public)
        self.assertEqual(retriever.retrieve(public, 5, 3), expected)

    def test_retrieve_normalizes_observations_only_once(self):
        engine = self.retriever.engine
        with patch.object(engine, "normalize_observations", wraps=engine.normalize_observations) as normalize:
            context = self.adapter.retrieve(self.public, 3, 2)
        normalize.assert_called_once()
        self.assertTrue(context["normalized_observations"])

    def test_explicit_observations_preserve_three_truth_states(self):
        case = {
            "input": {"user_text": "Please examine the rice crop.",
                      "growth_stage_id": "growth_stage:tillering"},
            "explicit_observations": [
                {"term_id": "symptom:leaf_yellowing", "state": "TRUE"},
                {"term_id": "sign:bacterial_ooze_beads", "state": "FALSE"},
                {"term_id": "sign:water_test_cloudy_streaming", "state": "UNKNOWN"},
            ],
        }
        original = deepcopy(case)
        context = self.retriever.retrieve(case, 5, 3)
        states = {item["concept_id"]: item["state"] for item in context["normalized_observations"]}
        self.assertEqual(states["symptom:leaf_yellowing"], "PRESENT")
        self.assertEqual(states["sign:bacterial_ooze_beads"], "ABSENT")
        self.assertEqual(states["sign:water_test_cloudy_streaming"], "UNKNOWN")
        self.assertEqual(states["stage:tillering"], "PRESENT")
        for field in ("supporting_evidence", "contradicting_evidence"):
            for rule in context[field]:
                expected = {"state:TRUE": "PRESENT", "state:FALSE": "ABSENT",
                            "state:UNKNOWN": "UNKNOWN"}[rule["condition_truth_state"]]
                self.assertEqual(states[rule["observation_id"]], expected)
        self.assertEqual(case, original)

    def test_explicit_observation_output_state_is_rejected_instead_of_silently_scored(self):
        case = {
            "input": {
                "user_text": "Please examine the rice crop.",
                "growth_stage_id": "growth_stage:tillering",
            },
            "explicit_observations": [{
                "term_id": "symptom:water_soaked_wavy_lesion",
                "state": "PRESENT",
            }],
        }
        with self.assertRaisesRegex(
            ValueError,
            "state must be TRUE, FALSE, or UNKNOWN",
        ):
            self.retriever.retrieve(case, 5, 3)

        case["explicit_observations"][0]["state"] = "TRUE"
        context = self.retriever.retrieve(case, 5, 3)
        self.assertTrue(any(
            item["observation_id"] == "symptom:water_soaked_wavy_lesion"
            for item in context["supporting_evidence"]
        ))

    def test_evidence_contains_matching_conditions_instead_of_all_candidate_rules(self):
        public = deepcopy(self.public)
        public["input"]["user_text"] = (
            "Yellow leaves have wavy water-soaked lesions. No bacterial ooze is present."
        )
        context = self.adapter.retrieve(public, 5, 3)
        support_pairs = {
            (rule["cause_id"], rule["observation_id"])
            for rule in context["supporting_evidence"]
        }
        self.assertIn(
            ("disease:bacterial_leaf_blight", "symptom:water_soaked_wavy_lesion"),
            support_pairs,
        )
        self.assertNotIn(
            ("disease:bacterial_leaf_blight", "sign:bacterial_ooze_beads"),
            support_pairs,
        )
        states = {item["concept_id"]: item["state"] for item in context["normalized_observations"]}
        self.assertEqual(states["sign:bacterial_ooze_beads"], "ABSENT")
        for field in ("supporting_evidence", "contradicting_evidence"):
            for rule in context[field]:
                with self.subTest(field=field, rule=rule):
                    self.assertIn(rule["cause_id"], context["candidate_causes"])
                    expected = {"state:TRUE": "PRESENT", "state:FALSE": "ABSENT",
                                "state:UNKNOWN": "UNKNOWN"}[rule["condition_truth_state"]]
                    self.assertEqual(states[rule["observation_id"]], expected)

    def test_kg_diagnosis_respects_candidate_and_question_budgets(self):
        compact, verbose = self.adapter.diagnose(self.public, 1, 1)
        self.assertEqual(validate_response(compact), [])
        self.assertEqual(len(compact["differential"]), 1)
        self.assertEqual(len(compact["observations_needed"]), 1)
        self.assertGreater(len(verbose["differential"]), len(compact["differential"]))
        self.assertGreater(len(verbose["observations_needed"]), len(compact["observations_needed"]))

    def test_family_id_reaches_engine_case_id_without_changing_public_input(self):
        original = deepcopy(self.public)
        family_id = "FAMILY_PRIVATE_ID_SENTINEL"
        with patch.object(self.adapter._engine, "diagnose", wraps=self.adapter._engine.diagnose) as diagnose:
            compact, verbose = self.adapter.diagnose(self.public, family_id=family_id)
        self.assertEqual(diagnose.call_args.kwargs["context"]["case_id"], family_id)
        self.assertEqual(verbose["case_id"], family_id)
        self.assertEqual(validate_response(compact), [])
        self.assertEqual(self.public, original)
        self.assertNotIn(family_id, json.dumps(self.public))


class UnifiedRunTests(unittest.TestCase):
    def test_prompt_omits_only_absent_retrieval_and_preserves_explicit_context(self):
        public = {"input": {"user_text": "Public crop observations."}, "language": "en", "region_id": None}
        marker = "\n\nretrieved context:\n"
        messages = unified.build_prompt(public)
        self.assertNotIn("retrieved context", messages[0]["content"].lower())
        self.assertEqual(json.loads(messages[1]["content"].removeprefix("User query:\n")), public)
        self.assertEqual(unified.build_prompt(public, None), messages)
        empty_context = {key: [] for key in (
            "normalized_observations", "candidate_causes", "supporting_evidence", "contradicting_evidence",
            "missing_observations", "suggested_questions", "retrieved_facts", "evidence_fact_ids", "evidence_source_ids",
        )}
        with_context = unified.build_prompt(public, empty_context)
        query, encoded_context = with_context[1]["content"].split(marker, 1)
        self.assertEqual(json.loads(query.removeprefix("User query:\n")), public)
        self.assertEqual(json.loads(encoded_context), empty_context)
        with self.assertRaisesRegex(ValueError, "Invalid retrieved context"):
            unified.build_prompt(public, {})

    def test_model_only_including_warmup_never_retrieves_or_sends_kg_context(self):
        case = deepcopy(json.loads((ROOT / "data/eval/gold_eval_v0.3.json").read_text(encoding="utf-8"))[0])
        secrets = ("MODEL_ONLY_GOLD_SECRET", "MODEL_ONLY_TARGET_SECRET", "MODEL_ONLY_INPUT_SECRET")
        case["annotations"]["private_note"] = secrets[0]
        case["target_response"]["user_response"] = secrets[1]
        case["input"]["private_note"] = secrets[2]
        generator = SimpleNamespace(
            device="cpu", context_limit=4096,
            model=SimpleNamespace(config=SimpleNamespace(_commit_hash="unit-test-commit")),
            generate=Mock(return_value={
                "raw_output": json.dumps(response()), "prompt_tokens": 20, "generated_tokens": 10,
                "output_budget_exhausted": False, "cuda_peak_allocated_mib": None,
            }),
        )
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "case.json"
            dataset.write_text(json.dumps([case]), encoding="utf-8")
            report_dir = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--output-dir", str(report_dir), "--modes", "model-only",
                "--backend", "transformers", "--model", "qwen2.5-1.5b", "--device", "cpu", "--limit", "1",
            ])
            self.assertTrue(args.warmup)
            terminal = io.StringIO()
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified.KGAdapter, "retrieve", side_effect=AssertionError("Unexpected KG retrieval")) as retrieve,
                patch.object(unified.KGAdapter, "diagnose", side_effect=AssertionError("Unexpected KG diagnosis")) as diagnose,
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected HTTP")) as http,
                redirect_stdout(terminal),
            ):
                unified.run(args)
            records = [json.loads(line) for line in
                       (report_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
            metadata = json.loads((report_dir / "run_config.json").read_text(encoding="utf-8"))
        retrieve.assert_not_called()
        diagnose.assert_not_called()
        http.assert_not_called()
        self.assertEqual(generator.generate.call_count, 2)  # Warm-up plus one real case.
        self.assertEqual(generator.generate.call_args_list[0].kwargs["max_new_tokens"], 16)
        for generation in generator.generate.call_args_list:
            messages = generation.args[0]
            content = messages[1]["content"]
            self.assertTrue(content.startswith("User query:\n"))
            payload = json.loads(content.removeprefix("User query:\n"))
            self.assertNotIn("retrieved context", content.lower())
            for key in ("normalized_observations", "candidate_causes", "supporting_evidence", "contradicting_evidence",
                        "missing_observations", "suggested_questions", "retrieved_facts", "evidence_fact_ids", "evidence_source_ids"):
                self.assertNotIn(key, content)
            for secret in secrets:
                self.assertNotIn(secret, json.dumps(messages))
            self.assertIn("input", payload)
        self.assertEqual(json.loads(generator.generate.call_args_list[1].args[0][1]["content"].removeprefix("User query:\n")),
                         unified.select_public_case(case))
        self.assertEqual(len(records), 1)
        for field in ("retrieved_context", "raw_retrieval", "raw_kg_response"):
            self.assertIsNone(records[0][field])
        self.assertEqual(records[0]["retrieval_s"], 0.0)
        self.assertIsNone(metadata["retrieval_version"])
        self.assertFalse(metadata["kg_enabled_by_mode"]["model-only"])
        self.assertIn("retrieval=disabled", terminal.getvalue())

    def test_kg_only_run_does_not_call_any_http_service(self):
        cases = json.loads((ROOT / "data/eval/gold_eval_v0.3.json").read_text(encoding="utf-8"))[:1]
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "test.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            report_dir = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--output-dir", str(report_dir),
                "--modes", "kg-only", "--no-warmup",
            ])
            with (
                patch("urllib.request.urlopen", side_effect=AssertionError("KG-only must not use HTTP")) as http,
                patch.object(unified, "HFGenerator", side_effect=AssertionError("KG-only must not load a model")),
                patch.object(unified, "OllamaGenerator", side_effect=AssertionError("KG-only must not use Ollama")),
                redirect_stdout(io.StringIO()),
            ):
                returned = unified.run(args)
            http.assert_not_called()
            self.assertEqual(returned, report_dir.resolve())
            records = [json.loads(line) for line in
                       (report_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
            user_outputs = [json.loads(line) for line in
                            (report_dir / "user_outputs.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(len(user_outputs), 1)
            self.assertEqual(records[0]["mode"], "kg-only")
            self.assertTrue(records[0]["metrics"]["schema_compliance"])
            self.assertEqual(user_outputs[0]["scenario_id"], records[0]["scenario_id"])
            self.assertEqual(user_outputs[0]["family_id"], records[0]["family_id"])
            self.assertEqual(user_outputs[0]["mode"], "kg-only")
            self.assertEqual(user_outputs[0]["source"], "kg_template")
            self.assertEqual(user_outputs[0]["status"], "ready")
            self.assertEqual(user_outputs[0]["user_response"], records[0]["prediction"]["user_response"])

    def test_all_modes_keep_failures_and_write_reports_without_gold_in_messages(self):
        cases = json.loads((ROOT / "data/eval/gold_eval_v0.3.json").read_text(encoding="utf-8"))[:2]
        shared_family = "SHARED_FAMILY_PRIVATE_SENTINEL"
        secrets = (
            "ANNOTATION_PRIVATE_SECRET", "TARGET_RESPONSE_SECRET", "INPUT_PRIVATE_SECRET",
            "disease:GOLD_CAUSE_SECRET", "question:GOLD_QUESTION_SECRET",
            "GOLD_FACT_SECRET", "GOLD_SOURCE_SECRET",
        )
        for case in cases:
            case["family_id"] = shared_family
            case["input"]["private_note"] = secrets[2]
            case["annotations"].update({
                "private_note": secrets[0], "acceptable_differential": [secrets[3]],
                "required_questions": [secrets[4]], "supporting_fact_ids": [secrets[5]],
                "supporting_source_ids": [secrets[6]],
            })
            case["target_response"]["user_response"] = secrets[1]

        captured_messages = []
        generated_user_responses = []

        def generate(messages, *, max_new_tokens=None):
            captured_messages.append(deepcopy(messages))
            call_number = len(captured_messages)
            if call_number == 2:
                raise RuntimeError("Simulated model execution failure")
            generated = response()
            generated["user_response"] = f"MODEL_USER_OUTPUT_{call_number}\nDo the leaf margins look wavy?"
            if call_number != 3:
                generated_user_responses.append(generated["user_response"])
            return {
                "raw_output": "not JSON" if call_number == 3 else json.dumps(generated),
                "prompt_tokens": 20, "generated_tokens": 10,
                "output_budget_exhausted": False, "cuda_peak_allocated_mib": None,
            }

        generator = SimpleNamespace(
            device="cpu", context_limit=4096,
            model=SimpleNamespace(config=SimpleNamespace(_commit_hash="unit-test-commit")),
            generate=Mock(side_effect=generate),
        )
        real_kg = unified.KGAdapter()
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "test.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            report_dir = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--output-dir", str(report_dir),
                "--backend", "transformers", "--model", "qwen2.5-1.5b", "--device", "cpu", "--limit", "2",
                "--modes", "kg-only", "model-only", "kg+model", "--no-warmup",
            ])
            terminal = io.StringIO()
            with (
                patch.object(unified, "HFGenerator", return_value=generator) as constructor,
                patch.object(unified, "KGAdapter", return_value=real_kg),
                patch.object(real_kg, "diagnose", wraps=real_kg.diagnose) as diagnose,
                patch.object(real_kg, "retrieve", wraps=real_kg.retrieve) as retrieve,
                patch.object(unified, "finalize_score", wraps=unified.finalize_score) as finalize_score,
                redirect_stdout(terminal),
            ):
                returned = unified.run(args)

            constructor.assert_called_once()
            self.assertEqual(diagnose.call_count, 2)  # Model failures never invoke KG fallback.
            self.assertEqual(retrieve.call_count, 2)  # Only the two KG+model cases retrieve.
            self.assertEqual(generator.generate.call_count, 4)  # No warm-up call.
            for scored in finalize_score.call_args_list:
                row = scored.args[0]
                if row["mode"] == "kg+model":
                    self.assertEqual(row["raw_retrieval"], row["retrieved_context"])
                    self.assertIsNot(row["raw_retrieval"], row["retrieved_context"])
                    self.assertIsNot(row["raw_retrieval"]["suggested_questions"],
                                     row["retrieved_context"]["suggested_questions"])
                    self.assertIsNot(row["raw_retrieval"]["suggested_questions"][0],
                                     row["retrieved_context"]["suggested_questions"][0])
            self.assertEqual(returned, report_dir.resolve())
            self.assertEqual({path.name for path in report_dir.iterdir()}, {
                "run_config.json", "predictions.jsonl", "user_outputs.jsonl", "summary.json", "case_metrics.csv",
                "behavior_per_class.csv",
            })
            records = [json.loads(line) for line in
                       (report_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
            user_outputs = [json.loads(line) for line in
                            (report_dir / "user_outputs.jsonl").read_text(encoding="utf-8").splitlines()]
            summary = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
            config = json.loads((report_dir / "run_config.json").read_text(encoding="utf-8"))
            with (report_dir / "case_metrics.csv").open(encoding="utf-8-sig", newline="") as handle:
                csv_rows = list(csv.DictReader(handle))

            self.assertEqual(len(records), 6)
            self.assertEqual(len(user_outputs), 6)
            self.assertEqual(len(csv_rows), 6)
            for row, user_output, csv_row in zip(records, user_outputs, csv_rows):
                for field in ("scenario_id", "family_id", "mode"):
                    self.assertEqual(user_output[field], row[field])
                    self.assertEqual(csv_row[field], row[field])
                self.assertEqual(user_output["user_response"], row["final_user_output"])
                self.assertEqual(user_output["source"], row["final_output_source"])
                self.assertEqual(user_output["status"], row["final_output_status"])
                self.assertEqual(user_output["schema_compliance"], row["metrics"]["schema_compliance"])
                self.assertEqual(user_output["error"], row["error"])
                for field in ("final_user_output", "final_output_source", "final_output_status"):
                    self.assertEqual(csv_row[field], row[field] if row[field] is not None else "")
            self.assertEqual(config["scenario_ids"], [case["scenario_id"] for case in cases])
            self.assertEqual(config["family_ids"], [shared_family, shared_family])
            self.assertTrue(all(row["family_id"] == shared_family for row in records))
            self.assertTrue(all(row["family_id"] == shared_family for row in csv_rows))
            self.assertIn(shared_family, terminal.getvalue())
            self.assertEqual(config["model_commit"], "unit-test-commit")
            self.assertIsNone(config["warmup_s"])
            self.assertEqual(config["kg_enabled_by_mode"], {"kg-only": True, "model-only": False, "kg+model": True})
            self.assertEqual(config["retrieval_version"], retriever_module.KGRetriever.version)
            kg_root = Path(retriever_module.WORKSPACE_ROOT)
            self.assertEqual(kg_root, ROOT)
            self.assertEqual(config["kg_git_revision"], unified.git_revision(ROOT))
            for mode in ("kg-only", "model-only", "kg+model"):
                result = summary["results"][mode]
                self.assertEqual(result["n"], 2)
                self.assertEqual({row["scenario_id"] for row in records if row["mode"] == mode},
                                 {case["scenario_id"] for case in cases})
                for metric in ("schema_compliance", "behavior_correctness", "differential_f1"):
                    self.assertEqual(result["metrics"][metric]["applicable_n"], 2)
            for row in records:
                if row["mode"] == "kg-only":
                    self.assertEqual(row["raw_kg_response"]["case_id"], shared_family)
                    self.assertEqual(row["final_output_source"], "kg_template")
                else:
                    self.assertEqual(row["final_output_source"], "model_generated")
                    content = row["messages"][1]["content"]
                    if row["mode"] == "model-only":
                        self.assertEqual(json.loads(content.removeprefix("User query:\n")), row["public_input"])
                        self.assertNotIn("retrieved context", content.lower())
                        self.assertEqual(row["retrieval_s"], 0.0)
                        for field in ("retrieved_context", "raw_retrieval", "raw_kg_response"):
                            self.assertIsNone(row[field])
                    else:
                        self.assertIsNotNone(row["retrieved_context"])
                        self.assertIsNotNone(row["raw_retrieval"])
                        self.assertEqual(row["raw_retrieval"], row["retrieved_context"])
                        encoded_context = content.split("\n\nretrieved context:\n", 1)[1]
                        self.assertEqual(json.loads(encoded_context), row["retrieved_context"])

            valid_model_rows = [row for row in records if row["mode"] != "kg-only"
                                and row["metrics"]["schema_compliance"]]
            self.assertEqual([row["final_user_output"] for row in valid_model_rows], generated_user_responses)
            for row in valid_model_rows:
                self.assertEqual(row["final_output_status"], "ready")
                self.assertEqual(row["final_user_output"], row["prediction"]["user_response"])
                self.assertIn(row["final_user_output"], terminal.getvalue())
                self.assertNotEqual(row["final_user_output"], secrets[1])

            runtime_failure = next(row for row in records if row["mode"] == "model-only"
                                   and row["scenario_id"] == cases[1]["scenario_id"])
            malformed_output = next(row for row in records if row["mode"] == "kg+model"
                                    and row["scenario_id"] == cases[0]["scenario_id"])
            self.assertEqual(runtime_failure["error"]["type"], "RuntimeError")
            self.assertEqual(runtime_failure["final_output_status"], "inference_error")
            self.assertEqual(malformed_output["raw_output"], "not JSON")
            self.assertEqual(malformed_output["final_user_output"], "not JSON")
            self.assertEqual(malformed_output["final_output_status"], "raw_output")
            self.assertIn("not JSON", terminal.getvalue())
            for failed_row in (runtime_failure, malformed_output):
                self.assertIsNone(failed_row["prediction"])
                self.assertIsNone(failed_row["raw_kg_response"])
                self.assertEqual(failed_row["metrics"]["first_behavior"], "INVALID")
                self.assertFalse(failed_row["metrics"]["schema_compliance"])
                self.assertEqual(failed_row["metrics"]["differential_f1"], 0.0)
                self.assertEqual(failed_row["metrics"]["final_score"], 0.0)
            self.assertEqual(summary["results"]["model-only"]["inference_errors"], 1)
            self.assertEqual(summary["results"]["kg+model"]["metrics"]["parse_valid"]["value"], 0.5)

        visible_messages = json.dumps(captured_messages)
        self.assertNotIn(shared_family, visible_messages)
        for case in cases:
            self.assertNotIn(case["scenario_id"], visible_messages)
        for secret in secrets:
            with self.subTest(secret=secret):
                self.assertNotIn(secret, visible_messages)
        for index, messages in enumerate(captured_messages):
            self.assertIn(cases[index % 2]["input"]["user_text"], messages[1]["content"])


class CaseTraceTests(unittest.TestCase):
    def test_step_output_is_disabled_by_default_and_enabled_explicitly(self):
        self.assertFalse(unified.build_parser().parse_args([]).show_steps)
        self.assertTrue(unified.build_parser().parse_args(["--show-steps"]).show_steps)

    def test_trace_includes_pipeline_and_errors_without_scoring_details_or_mutation(self):
        context = {
            key: [] for key in (
                "normalized_observations", "candidate_causes", "supporting_evidence",
                "contradicting_evidence", "missing_observations", "suggested_questions",
                "retrieved_facts", "evidence_fact_ids", "evidence_source_ids",
            )
        }
        context["candidate_causes"] = ["disease:CONTEXT_TRACE_SENTINEL"]
        raw_output = 'RAW_TRACE_SENTINEL\n{"unmodified": true}\ntrailing text'
        for mode in ("kg-only", "model-only", "kg+model"):
            with self.subTest(mode=mode):
                row = {
                    "mode": mode, "scenario_id": "TRACE-CASE-001",
                    "family_id": "TRACE_FAMILY_SENTINEL",
                    "public_input": {"input": {"user_text": "PUBLIC_INPUT_TRACE_SENTINEL"}},
                    "retrieved_context": deepcopy(context) if mode == "kg+model" else None,
                    "raw_kg_response": {"diagnosis": "KG_ONLY_TRACE_SENTINEL"} if mode == "kg-only" else None,
                    "messages": [{"role": "user", "content": "REQUEST_TRACE_SENTINEL"}],
                    "ollama_request": {"model": "trace-model:latest", "options": {"temperature": 0.1}},
                    "raw_output": raw_output, "prediction": None,
                    "error": {"type": "TraceError", "message": "BACKEND_TRACE_SENTINEL"},
                    "metrics": {"schema_compliance": False, "first_behavior": "INVALID",
                                "schema_errors": ["SCHEMA_ERROR_TRACE_SENTINEL"]},
                    "gold": {"correct_first_behavior": "ASK", "escalation_required": False},
                    "score_breakdown": {"details": "SCORE_DETAILS_TRACE_SENTINEL"},
                    "category_scores": {"details": "CATEGORY_DETAILS_TRACE_SENTINEL"},
                    "rule_evaluation": {"details": "RULE_DETAILS_TRACE_SENTINEL"},
                    "resource_measurement": {"details": "RESOURCE_DETAILS_TRACE_SENTINEL"},
                }
                original = deepcopy(row)
                terminal = io.StringIO()
                with redirect_stdout(terminal):
                    unified.print_case_steps(row)
                shown = terminal.getvalue()
                self.assertIn("TRACE_FAMILY_SENTINEL", shown)
                self.assertIn("PUBLIC_INPUT_TRACE_SENTINEL", shown)
                self.assertIn(raw_output, shown)  # Preserve line breaks and non-JSON text.
                self.assertIn("SCHEMA_ERROR_TRACE_SENTINEL", shown)
                self.assertIn("BACKEND_TRACE_SENTINEL", shown)
                self.assertIn("[Errors]", shown)
                for detail in ("[6] Evaluator result", "correct_first_behavior", "schema_compliance",
                               "SCORE_DETAILS_TRACE_SENTINEL", "CATEGORY_DETAILS_TRACE_SENTINEL",
                               "RULE_DETAILS_TRACE_SENTINEL", "RESOURCE_DETAILS_TRACE_SENTINEL"):
                    self.assertNotIn(detail, shown)
                if mode == "kg+model":
                    self.assertIn("CONTEXT_TRACE_SENTINEL", shown)
                elif mode == "kg-only":
                    self.assertIn("KG_ONLY_TRACE_SENTINEL", shown)
                else:
                    self.assertIn("disabled for model-only", shown)
                    self.assertIn("null", shown)
                    self.assertNotIn("candidate_causes", shown)
                self.assertEqual(row, original)

    def test_trace_displays_valid_parsed_prediction(self):
        prediction = response()
        prediction["user_response"] = "PARSED_PREDICTION_TRACE_SENTINEL"
        row = {
            "mode": "model-only", "scenario_id": "TRACE-CASE-002",
            "public_input": {"input": {"user_text": "Yellow leaves."}},
            "retrieved_context": None, "raw_kg_response": None,
            "messages": [{"role": "user", "content": "Request"}],
            "ollama_request": None,
            "raw_output": json.dumps(prediction), "prediction": prediction, "error": None,
            "metrics": {"schema_compliance": True, "schema_errors": [],
                        "first_behavior": "ASK", "behavior_correctness": True},
            "gold": {"correct_first_behavior": "ASK"},
        }
        original = deepcopy(row)
        terminal = io.StringIO()
        with redirect_stdout(terminal):
            unified.print_case_steps(row)
        self.assertIn("Parsed prediction", terminal.getvalue())
        self.assertIn("PARSED_PREDICTION_TRACE_SENTINEL", terminal.getvalue())
        self.assertNotIn("[6] Evaluator result", terminal.getvalue())
        self.assertNotIn("[Errors]", terminal.getvalue())
        self.assertEqual(row, original)


if __name__ == "__main__":
    unittest.main()
