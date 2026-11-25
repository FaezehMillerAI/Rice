"""Gold v0.3 integration checks with deterministic rule scoring and no HTTP."""

from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
import csv
import io
import json
from math import fsum
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml

import eval.evaluate_unified as unified


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data/eval/gold_eval_v0.3.json"
CONFIG = ROOT / "configs/eval/eval_config.yaml"
METRICS = {
    "behavior_correctness", "differential_top1_precision", "differential_top3_recall", "differential_f1",
    "confounder_recall", "question_agreement",
    "evidence_agreement", "groundedness", "actions_agreement", "safety_flags_agreement", "escalation_correctness",
    "structured_output_vs_user_response_consistency", "response_safety_check",
    "schema_compliance", "resource_efficiency",
}
CATEGORIES = {
    "behavior_correctness", "differential_metrics", "confounder_recall",
    "question_agreement", "evidence_agreement", "groundedness", "actions_agreement",
    "safety_flags_agreement", "structured_output_vs_user_response_consistency", "response_safety_check",
    "escalation_correctness", "schema_compliance", "resource_efficiency",
}
LABELS = {
    "behavior_correctness": "Behavior Correctness",
    "differential_metrics": "Differential Metrics",
    "confounder_recall": "Confounder Recall",
    "groundedness": "Groundedness",
    "question_agreement": "Question Agreement",
    "evidence_agreement": "Evidence Agreement",
    "actions_agreement": "Actions Agreement",
    "safety_flags_agreement": "Safety_flags Agreement",
    "escalation_correctness": "Escalation Correctness",
    "structured_output_vs_user_response_consistency": "Structured_output vs User_response Consistency",
    "response_safety_check": "Response Safety Check",
    "schema_compliance": "Schema Compliance",
    "resource_efficiency": "Resource Efficiency",
}
# Explicit negative assertions keep removed identifiers from returning as aliases.
LEGACY_METRIC_KEYS = {
    "first_behavior_correct", "differential_precision", "differential_recall",
    "question_quality", "evidence_id_agreement", "action_f1", "safety_score",
    "escalation_correct", "response_consistency_score", "response_safety_score", "schema_valid",
}
REMOVED_TOTAL_SCORE_METRICS = {"score_coverage", "partial_score", "complete_score"}


def fake_resource_monitor():
    monitor = Mock()
    monitor.start.return_value = monitor
    monitor.stop.return_value = {
        "process_peak_rss_mib": 128.0,
        "memory_measurement_scope": "evaluator_process_tree",
        "memory_sample_count": 2,
        "memory_measurement_error": None,
    }
    return monitor


def fake_generator(generate):
    return SimpleNamespace(
        device="cpu", context_limit=8192,
        model=SimpleNamespace(config=SimpleNamespace(_commit_hash="unit-test")),
        generate=Mock(side_effect=generate),
    )


def generated(raw_output):
    return {"raw_output": raw_output, "prompt_tokens": 32, "generated_tokens": 20,
            "cuda_peak_allocated_mib": None, "output_budget_exhausted": False}


def reports(directory):
    rows = [json.loads(line) for line in
            (directory / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    return rows, summary


class V03DefaultsTests(unittest.TestCase):
    def test_default_dataset_has_thirteen_scored_categories_and_no_pending_metrics(self):
        args = unified.build_parser().parse_args([])
        self.assertEqual(args.backend, "transformers")
        self.assertEqual(args.dtype, "auto")
        self.assertIsNone(args.dataset)
        self.assertIsNone(args.config)
        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(unified.resolve_benchmark_dataset(args.dataset, config["benchmark"]),
                         ROOT / "data/eval/gold_eval_v0.4.json")
        self.assertEqual(unified.project_path(args.score_config), CONFIG.resolve())
        self.assertNotIn("semantic_judge", config)
        self.assertFalse(hasattr(args, "judge_model"))
        configured = unified.load_score_weights(CONFIG)
        self.assertEqual(set(configured), METRICS)
        self.assertTrue(all(weight > 0 for weight in configured.values()))
        self.assertEqual(len(configured), 15)
        self.assertAlmostEqual(sum(configured.values()), 1.0)
        self.assertNotIn("pending_metrics", config)
        self.assertEqual(set(unified.SCORE_CATEGORIES), CATEGORIES)
        self.assertEqual(list(unified.SCORE_CATEGORIES), list(LABELS))
        self.assertEqual({metric for group in unified.SCORE_CATEGORIES.values() for metric in group}, METRICS)
        self.assertTrue(all(isinstance(group, tuple) for group in unified.SCORE_CATEGORIES.values()))
        self.assertEqual(unified.SCORE_CATEGORIES["differential_metrics"],
                         ("differential_top1_precision", "differential_top3_recall", "differential_f1"))
        self.assertEqual(unified.METRIC_LABELS, LABELS)
        self.assertEqual(list(unified.METRIC_LABELS), list(LABELS))
        self.assertNotIn("supported_claim_score", configured)
        self.assertNotIn("unsupported_claim_rate", configured)

    def test_all_sixty_five_reference_cases_load_with_consistent_status(self):
        cases = unified.load_cases(DATASET)
        self.assertEqual(cases, json.loads(DATASET.read_text(encoding="utf-8")))
        self.assertEqual(len(cases), 65)
        self.assertEqual(len({case["scenario_id"] for case in cases}), 65)
        self.assertEqual(Counter(case["annotations"]["correct_first_behavior"] for case in cases),
                         {"ASK": 16, "ANSWER": 43, "ESCALATE": 6})
        expected = {"ASK": "needs_more_information", "ANSWER": "provisional_assessment",
                    "ESCALATE": "escalation_required"}
        for case in cases:
            with self.subTest(scenario_id=case["scenario_id"]):
                prediction = case["target_response"]
                self.assertEqual(unified.validate_response(prediction), [])
                self.assertEqual(prediction["status"], expected[case["annotations"]["correct_first_behavior"]])
                self.assertEqual(prediction["escalation_required"],
                                 case["annotations"]["correct_first_behavior"] == "ESCALATE")
                self.assertEqual(case["family_id"], case["scenario_id"])
                self.assertEqual(unified.scoring_annotations(case)["safety_flags"], prediction["safety_flags"])
                self.assertEqual(unified.scoring_annotations(case)["actions"], prediction["actions"])

    def test_resource_normalization_uses_both_explicit_budgets(self):
        budgets = {"latency_s": 10.0, "memory_mib": 4096.0}
        result = unified.evaluate_resources(20.0, 8192.0, budgets)
        self.assertEqual(result["latency_efficiency"], 0.0)
        self.assertEqual(result["memory_efficiency"], 0.0)
        self.assertEqual(result["resource_efficiency"], 0.0)
        self.assertIsNone(unified.evaluate_resources(1.0, None, budgets)["resource_efficiency"])


class ScoringAnnotationsTests(unittest.TestCase):
    def setUp(self):
        self.case = deepcopy(unified.load_cases(DATASET)[0])

    def test_reference_actions_and_safety_are_copied_without_mutating_the_case(self):
        self.case["target_response"]["actions"] = ["action:reference"]
        self.case["target_response"]["safety_flags"] = ["flag:reference"]
        original = deepcopy(self.case)
        gold = unified.scoring_annotations(self.case)
        self.assertEqual(gold["safety_flags"], ["flag:reference"])
        self.assertEqual(gold["actions"], ["action:reference"])
        self.assertEqual(set(gold), set(self.case["annotations"]) | {"actions", "safety_flags"})
        self.assertEqual(self.case, original)
        self.assertIsNot(gold["safety_flags"], self.case["target_response"]["safety_flags"])
        self.assertIsNot(gold["actions"], self.case["target_response"]["actions"])
        gold["safety_flags"].append("flag:changed")
        gold["actions"].clear()
        gold["observations"][0]["state"] = "CHANGED"
        gold["acceptable_differential"].clear()
        self.assertEqual(self.case, original)

    def test_target_actions_and_safety_take_precedence_over_annotation_duplicates(self):
        self.case["annotations"]["actions"] = ["action:annotation"]
        self.case["annotations"]["safety_flags"] = ["flag:explicit"]
        self.case["target_response"]["actions"] = ["action:target"]
        self.case["target_response"]["safety_flags"] = ["flag:target"]
        original = deepcopy(self.case)
        gold = unified.scoring_annotations(self.case)
        self.assertEqual(gold["actions"], ["action:target"])
        self.assertEqual(gold["safety_flags"], ["flag:target"])
        self.assertIsNot(gold["actions"], self.case["annotations"]["actions"])
        self.assertIsNot(gold["safety_flags"], self.case["annotations"]["safety_flags"])
        self.assertEqual(self.case, original)

    def test_malformed_annotation_duplicates_do_not_replace_valid_target_references(self):
        for field in ("actions", "safety_flags"):
            expected = deepcopy(self.case["target_response"][field])
            for value in (None, "label:a", [1], [""], [" \t"], {}):
                with self.subTest(field=field, value=value):
                    self.case["annotations"][field] = value
                    self.assertEqual(unified.scoring_annotations(self.case)[field], expected)

    def test_missing_or_malformed_target_response_is_not_assumed_empty(self):
        for target in (None, [], {}):
            with self.subTest(target=target):
                self.case["target_response"] = target
                with self.assertRaisesRegex(ValueError, r"target_response"):
                    unified.scoring_annotations(self.case)

    def test_missing_or_malformed_target_fields_cannot_fall_back_to_annotation_duplicates(self):
        for field in ("actions", "safety_flags"):
            for value in ("MISSING", None, "label:a", [1], [""], [" \t"], {}):
                with self.subTest(field=field, value=value):
                    case = deepcopy(self.case)
                    case["annotations"][field] = ["annotation:valid"]
                    if value == "MISSING":
                        del case["target_response"][field]
                    else:
                        case["target_response"][field] = value
                    with self.assertRaisesRegex(ValueError, rf"target_response\.{field}"):
                        unified.scoring_annotations(case)

    def test_loading_keeps_sample_schema_and_validates_both_target_reference_fields(self):
        original = deepcopy(self.case)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "case.json"
            path.write_text(json.dumps(self.case), encoding="utf-8")
            loaded = unified.load_cases(path)
            self.assertEqual(loaded, [original])
            self.assertNotIn("safety_flags", loaded[0]["annotations"])
            self.assertNotIn("actions", loaded[0]["annotations"])
            self.case["target_response"]["actions"] = None
            path.write_text(json.dumps(self.case), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"target_response\.actions"):
                unified.load_cases(path)
            self.case["target_response"]["actions"] = original["target_response"]["actions"]
            self.case["target_response"]["safety_flags"] = None
            path.write_text(json.dumps(self.case), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"target_response\.safety_flags"):
                unified.load_cases(path)
            self.case["target_response"]["safety_flags"] = []
            self.case["annotations"]["actions"] = None
            self.case["annotations"]["safety_flags"] = None
            path.write_text(json.dumps(self.case), encoding="utf-8")
            self.assertEqual(unified.load_cases(path), [self.case])

    def test_quality_flag_audit_distinguishes_absent_labels_from_empty_labels(self):
        kg = SimpleNamespace(
            catalog={
                "retrieval_version": "test",
                "causes": {},
                "questions": {},
                "claims": {},
                "evidence_sources_by_fact": {},
                "action_catalog": {},
            },
        )
        audit = unified.dataset_audit([self.case], kg)
        self.assertFalse(audit["quality_flags_available"])
        self.assertIsNone(audit["quality_flag_counts"])
        self.assertIsNone(audit["quality_flagged_case_ids"])
        self.case["annotations"]["quality_flags"] = []
        audit = unified.dataset_audit([self.case], kg)
        self.assertTrue(audit["quality_flags_available"])
        self.assertEqual(audit["quality_flag_counts"], {})
        self.assertEqual(audit["quality_flagged_case_ids"], [])
        self.case["annotations"]["quality_flags"] = ["review:source_evidence"]
        audit = unified.dataset_audit([self.case], kg)
        self.assertTrue(audit["quality_flags_available"])
        self.assertEqual(audit["quality_flag_counts"], {"review:source_evidence": 1})
        self.assertEqual(audit["quality_flagged_case_ids"], [self.case["scenario_id"]])


class V03RunTests(unittest.TestCase):
    def test_reference_top_one_confounder_receives_only_tail_credit_and_its_weighted_points(self):
        case = next(case for case in unified.load_cases(DATASET)
                    if case["scenario_id"] == "case-amb-016")
        original = deepcopy(case)
        prediction = deepcopy(case["target_response"])
        confounders = set(case["annotations"]["required_confounders"])
        self.assertIn(prediction["differential"][0], confounders)
        self.assertEqual(len(confounders), 2)
        self.assertNotIn(prediction["differential"][0], prediction["differential"][1:])
        generator = fake_generator(lambda messages, **kwargs: generated(json.dumps(prediction)))
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps([case]), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--model", "qwen2.5-1.5b",
                "--device", "cpu", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, summary = reports(directory)
            metadata = json.loads((directory / "run_config.json").read_text(encoding="utf-8"))

        network.assert_not_called()
        self.assertEqual(case, original)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["prediction"], prediction)
        self.assertEqual(json.loads(row["raw_output"]), prediction)
        self.assertEqual(row["final_user_output"], prediction["user_response"])
        self.assertEqual(row["raw_score_metrics"]["confounder_recall"], 0.5)
        self.assertEqual(row["metrics"]["confounder_recall"], 0.5)
        component = row["score_breakdown"]["components"]["confounder_recall"]
        self.assertAlmostEqual(component["configured_weight"], 0.05)
        self.assertAlmostEqual(component["effective_weight"], 0.05)
        self.assertAlmostEqual(component["contribution"], 2.5)
        self.assertEqual(component["state"], "scored")
        self.assertTrue(component["assessed"])
        self.assertFalse(component["zero_filled"])
        self.assertEqual(row["metrics"]["differential_top1_precision"], 1.0)
        self.assertEqual(row["metrics"]["differential_top3_recall"], 1.0)
        self.assertEqual(row["metrics"]["differential_f1"], 1.0)
        grounding = row["rule_evaluation"]["checks"]["differential_grounding"]
        self.assertEqual(grounding["claim_ids"], sorted(set(prediction["differential"])))
        self.assertEqual(grounding["claim_count"], len(set(prediction["differential"])))
        self.assertIn(prediction["differential"][0], grounding["claim_ids"])
        full_list_metrics = {**row["raw_score_metrics"], "confounder_recall": 1.0}
        full_list_score = unified.compute_weighted_score(full_list_metrics, unified.load_score_weights(CONFIG))
        self.assertAlmostEqual(full_list_score["score"] - row["metrics"]["final_score"], 2.5)
        result = summary["results"]["model-only"]
        self.assertEqual(result["metrics"]["confounder_recall"]["value"], 0.5)
        self.assertAlmostEqual(result["score_breakdown"]["confounder_recall"]["mean_contribution_points"], 2.5)
        formula = "count(set(differential[1:]) intersect set(required_confounders)) / count(set(required_confounders)); null if gold is empty"
        self.assertEqual(metadata["scoring"]["confounder_recall_formula"], formula)
        self.assertEqual(summary["run"]["scoring"]["confounder_recall_formula"], formula)

    def test_question_agreement_exempts_answers_without_reference_questions(self):
        reference_cases = unified.load_cases(DATASET)
        templates = {
            behavior: next(case for case in reference_cases
                           if case["annotations"]["correct_first_behavior"] == behavior)
            for behavior in ("ASK", "ANSWER", "ESCALATE")
        }
        statuses = {behavior: status for status, behavior in unified.BEHAVIORS.items()}
        question = "q:q_lesion_margin"
        fact = "fact:reference"
        specifications = (
            ("answer-empty", "ANSWER", "ANSWER", [], [], [], [], True, None, 1.0),
            ("answer-extra-question", "ANSWER", "ANSWER", [question], [], [], [], True, None, 1.0),
            ("answer-missing-question", "ANSWER", "ANSWER", [], [question], [], [], True, 0.0, 1.0),
            ("ask-extra-question", "ASK", "ASK", [question], [], [], [], True, 0.0, 1.0),
            ("ask-empty-with-valid-answer", "ASK", "ANSWER", [], [], [], [], True, 1.0, 1.0),
            ("escalate-empty", "ESCALATE", "ESCALATE", [], [], [], [], True, 1.0, 1.0),
            ("missing-citation", "ANSWER", "ANSWER", [question], [question], [], [fact], True, 1.0, 0.0),
            ("extra-citation", "ANSWER", "ANSWER", [question], [question], [fact], [], True, 1.0, 0.0),
            ("invalid-ask", "ASK", "ASK", [], [question], [], [], False, 0.0, 0.0),
        )
        cases, predictions = [], []
        for name, gold_behavior, predicted_behavior, asked, required, cited, supporting, valid, _, _ in specifications:
            case = deepcopy(templates[gold_behavior])
            case["scenario_id"] = case["family_id"] = f"EMPTY-AGREEMENT-{name}"
            case["annotations"].update(required_questions=required, supporting_fact_ids=supporting)
            case["target_response"].update(observations_needed=required, grounding=supporting)
            prediction = {
                **deepcopy(case["target_response"]), "status": statuses[predicted_behavior],
                "escalation_required": predicted_behavior == "ESCALATE",
                "observations_needed": asked, "grounding": cited,
            }
            self.assertEqual(not unified.validate_response(prediction), valid)
            cases.append(case)
            predictions.append(prediction)
        completions = iter(predictions)
        generator = fake_generator(lambda messages, **kwargs: generated(json.dumps(next(completions))))
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--model", "qwen2.5-1.5b",
                "--device", "cpu", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, summary = reports(directory)

        network.assert_not_called()
        self.assertEqual(generator.generate.call_count, len(specifications))
        self.assertEqual(len(rows), len(specifications))
        for row, specification in zip(rows, specifications):
            name, gold_behavior, *_, valid, question_score, evidence_score = specification
            with self.subTest(case=name):
                self.assertEqual(row["metrics"]["schema_compliance"], valid)
                breakdown = row["score_breakdown"]
                self.assertEqual(breakdown["schema_gate_passed"], valid)
                applicable_weight = 0.95 if question_score is None or gold_behavior == "ESCALATE" else 1.0
                self.assertAlmostEqual(breakdown["applicable_weight"], applicable_weight)
                behavior = breakdown["components"]["behavior_correctness"]
                self.assertAlmostEqual(behavior["effective_weight"], 0.20)
                for metric, expected, weight, check_name in (
                    ("question_agreement", question_score, 0.05, "questions"),
                    ("evidence_agreement", evidence_score, 0.05, "citations"),
                ):
                    component = breakdown["components"][metric]
                    trace = row["rule_evaluation"]["checks"][check_name]
                    score = 0.0 if expected is None else expected
                    self.assertEqual(row["raw_score_metrics"][metric], expected)
                    self.assertEqual(row["metrics"][metric], score)
                    self.assertEqual(trace["reference_f1"], expected)
                    self.assertEqual(component["applicable"], expected is not None)
                    self.assertEqual(component["assessed"], expected is not None)
                    self.assertEqual(component["zero_filled"], expected is None)
                    self.assertEqual(component["raw_value"], expected)
                    self.assertEqual(component["value"], score)
                    self.assertAlmostEqual(component["configured_weight"], weight)
                    self.assertAlmostEqual(component["effective_weight"], weight)
                    self.assertAlmostEqual(component["contribution"], score * weight * 100)
                    if expected is None:
                        reason = "no_questions_required_for_answer"
                        self.assertEqual(component["state"], "not_applicable")
                        self.assertEqual(component["not_applicable_reason"], reason)
                        self.assertEqual(trace["not_applicable_reason"], reason)
                        self.assertEqual(row["not_applicable_metrics"][metric], reason)
                        self.assertNotIn(metric, row["unavailable_metrics"])
                        self.assertIsNone(component["missing_reason"])
                    else:
                        self.assertEqual(component["state"], "scored")
                if not valid:
                    self.assertTrue(row["metrics"]["parse_valid"])
                    self.assertEqual(row["prediction"]["observations_needed"], [])
                    self.assertEqual(row["prediction"]["grounding"], [])
                    self.assertEqual(row["metrics"]["final_score"], 0.0)
                    self.assertTrue(all(component["contribution"] == 0.0
                                        for component in row["score_breakdown"]["components"].values()))
        result = summary["results"]["model-only"]
        self.assertEqual(result["metrics"]["question_agreement"], {"value": 4 / 9, "applicable_n": 7})
        self.assertEqual(result["metrics"]["evidence_agreement"], {"value": 6 / 9, "applicable_n": 9})
        question_counts = result["score_breakdown"]["question_agreement"]
        self.assertEqual(question_counts["assessed_n"], 7)
        self.assertEqual(question_counts["scored_n"], 7)
        self.assertEqual(question_counts["passed_n"], 4)
        self.assertEqual(question_counts["failed_n"], 0)
        self.assertEqual(question_counts["not_applicable_n"], 2)
        self.assertEqual(question_counts["not_applicable_reasons"], {"no_questions_required_for_answer": 2})

    def test_empty_claims_keep_groundedness_weight_and_leave_unsupported_rate_unassessed(self):
        case = deepcopy(unified.load_cases(DATASET)[0])
        self.assertEqual(case["scenario_id"], "case-amb-001")
        prediction = {
            "status": "needs_more_information",
            "observations_needed": [case["annotations"]["required_questions"][0]],
            "differential": [], "actions": [], "escalation_required": False,
            "grounding": [], "safety_flags": [],
            "user_response": "Are the leaf margins wavy? Please check before making an assessment.",
        }
        original_prediction = deepcopy(prediction)
        self.assertEqual(unified.validate_response(prediction), [])
        raw_prediction = json.dumps(prediction)
        case["target_response"]["user_response"] = "GOLD_RESPONSE_MUST_NOT_REPLACE_MODEL_OUTPUT"
        generator = fake_generator(lambda messages, **kwargs: generated(raw_prediction))
        terminal = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps([case]), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--backend", "transformers", "--model", "qwen2.5-1.5b",
                "--device", "cpu", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(terminal),
            ):
                unified.run(args)
            rows, summary = reports(directory)

        network.assert_not_called()
        generator.generate.assert_called_once()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertTrue(row["metrics"]["schema_compliance"])
        self.assertEqual(row["metrics"]["question_agreement"], 0.5)
        self.assertEqual(row["rule_evaluation"]["checks"]["questions"]["reference_f1"], 0.5)
        self.assertAlmostEqual(row["score_breakdown"]["components"]["question_agreement"]["contribution"],
                               2.5)
        self.assertEqual(row["metrics"]["groundedness"], 0.0)
        self.assertEqual(row["metrics"]["evidence_agreement"], 0.0)
        self.assertEqual(row["metrics"]["actions_agreement"], 0.0)
        self.assertEqual(row["metrics"]["safety_flags_agreement"], 1.0)
        self.assertIsNone(row["raw_score_metrics"]["groundedness"])
        self.assertIsNone(row["metrics"]["unsupported_claim_rate"])
        self.assertNotIn("supported_claim_score", row["metrics"])
        self.assertNotIn("unsupported_claim_rate", row["raw_score_metrics"])
        self.assertNotIn("unsupported_claim_rate", row["category_scores"])
        component = row["score_breakdown"]["components"]["groundedness"]
        self.assertTrue(component["applicable"])
        self.assertAlmostEqual(component["configured_weight"], 0.15)
        self.assertAlmostEqual(component["effective_weight"], 0.15)
        self.assertEqual(component["state"], "failed")
        self.assertFalse(component["assessed"])
        self.assertTrue(component["zero_filled"])
        self.assertIsNone(component["raw_value"])
        self.assertEqual(component["value"], 0.0)
        self.assertEqual(component["contribution"], 0.0)
        self.assertEqual(set(row["score_breakdown"]["components"]), METRICS)
        self.assertTrue(all(item["applicable"] for item in row["score_breakdown"]["components"].values()))
        self.assertAlmostEqual(row["score_breakdown"]["applicable_weight"], 1.0)
        self.assertIsInstance(row["response_consistency"], dict)
        self.assertIsInstance(row["response_safety"], dict)
        self.assertEqual(row["metrics"]["response_safety_check"], 1.0)
        consistency = row["raw_score_metrics"]["structured_output_vs_user_response_consistency"]
        if consistency is not None:
            self.assertGreaterEqual(consistency, 0.0)
            self.assertLessEqual(consistency, 1.0)
        self.assertTrue(REMOVED_TOTAL_SCORE_METRICS.isdisjoint(row["metrics"]))
        self.assertTrue({"coverage", "assessed_weight", "is_complete", "partial_score", "complete_score"}
                        .isdisjoint(row["score_breakdown"]))
        self.assertAlmostEqual(sum(item["effective_weight"] for item in row["score_breakdown"]["components"].values()), 1.0)
        self.assertAlmostEqual(fsum(item["contribution"] for item in row["score_breakdown"]["components"].values()),
                               row["metrics"]["final_score"])
        self.assertEqual(row["prediction"], original_prediction)
        self.assertEqual(prediction, original_prediction)
        self.assertEqual(row["raw_output"], raw_prediction)
        self.assertEqual(row["final_user_output"], original_prediction["user_response"])

        result = summary["results"]["model-only"]
        self.assertEqual(result["metrics"]["groundedness"]["value"], 0.0)
        self.assertEqual(result["metrics"]["groundedness"]["applicable_n"], 1)
        self.assertEqual(result["metrics"]["groundedness"]["assessed_n"], 0)
        self.assertNotIn("supported_claim_score", result["metrics"])
        self.assertNotIn("unsupported_claim_rate", result["score_breakdown"])
        self.assertTrue(REMOVED_TOTAL_SCORE_METRICS.isdisjoint(result["metrics"]))
        self.assertTrue({"weighted_coverage", "partial_score", "incomplete_score_cases", "score_status"}
                        .isdisjoint(result))
        self.assertIn("question_registry_coverage", summary["run"]["dataset_audit"])
        self.assertIsNone(result["metrics"]["unsupported_claim_rate"]["value"])
        self.assertNotIn("pending_metrics", row)
        self.assertNotIn("pending_metrics", result)
        self.assertIn("response_safety_check", row["score_breakdown"]["components"])
        output = terminal.getvalue()
        self.assertNotIn("score_status", output)
        lines = output.split("=== Score summary ===", 1)[1].splitlines()
        header = next(line.split() for line in lines if line.split()[:2] == ["mode", "n"])
        raw = next(line.split() for line in lines if line.split()[:3] == ["model-only", "1", "raw"])
        self.assertNotIn("supported", header)
        self.assertNotIn("unsup", header)
        self.assertIn("consistency", header)
        self.assertEqual(raw[header.index("safety")], "1.00")

    def test_no_required_or_predicted_candidates_marks_groundedness_not_applicable(self):
        first = deepcopy(unified.load_cases(DATASET)[0])
        first["annotations"].update(acceptable_differential=[], required_confounders=[])
        first["target_response"].update(differential=[], grounding=[])
        prediction = deepcopy(first["target_response"])
        prediction["user_response"] = "Please inspect the leaf margins before making an assessment."
        examples = {
            "no-claims": prediction,
            "asserted-claim": {**prediction, "differential": ["cause:unsupported"]},
            "invalid-ask": {**prediction, "observations_needed": []},
        }
        cases = []
        for name in examples:
            case = deepcopy(first)
            case["scenario_id"] = case["family_id"] = name
            cases.append(case)
        completions = iter(examples.values())
        generator = fake_generator(lambda messages, **kwargs: generated(json.dumps(next(completions))))
        terminal = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--model", "qwen2.5-1.5b",
                "--device", "cpu", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")),
                redirect_stdout(terminal),
            ):
                unified.run(args)
            rows, summary = reports(directory)
            with (directory / "case_metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertTrue(REMOVED_TOTAL_SCORE_METRICS.isdisjoint(reader.fieldnames))
                csv_states = {row["scenario_id"]: json.loads(row["assessment_states"])
                              for row in reader}

        no_claims, asserted_claim, invalid = rows
        for row in rows:
            with self.subTest(case=row["scenario_id"]):
                components = row["score_breakdown"]["components"]
                self.assertEqual(set(components), METRICS)
                self.assertEqual(csv_states[row["scenario_id"]],
                                 {"metrics": {name: item["state"] for name, item in components.items()}})
                for metric in ("differential_top1_precision", "differential_top3_recall",
                               "differential_f1", "confounder_recall"):
                    self.assertIsNone(row["raw_score_metrics"][metric])
                    self.assertEqual(row["metrics"][metric], 0.0)
                    self.assertFalse(components[metric]["applicable"])
                    self.assertEqual(components[metric]["state"], "not_applicable")
                    self.assertAlmostEqual(components[metric]["effective_weight"], 0.05)
                    self.assertEqual(components[metric]["contribution"], 0.0)
                category = row["category_scores"]["differential_metrics"]
                self.assertIsNone(category["raw_value"])
                self.assertEqual(category["value"], 0.0)
                self.assertFalse(category["applicable"])
                self.assertAlmostEqual(category["effective_weight"], 0.15)
        no_claims_grounding = no_claims["score_breakdown"]["components"]["groundedness"]
        self.assertIsNone(no_claims["raw_score_metrics"]["groundedness"])
        self.assertEqual(no_claims["metrics"]["groundedness"], 0.0)
        self.assertFalse(no_claims_grounding["applicable"])
        self.assertFalse(no_claims_grounding["assessed"])
        self.assertTrue(no_claims_grounding["zero_filled"])
        self.assertEqual(no_claims_grounding["state"], "not_applicable")
        self.assertAlmostEqual(no_claims_grounding["effective_weight"], 0.15)
        self.assertEqual(no_claims_grounding["contribution"], 0.0)
        self.assertAlmostEqual(no_claims["score_breakdown"]["applicable_weight"], 0.65)
        self.assertEqual(no_claims["metrics"]["question_agreement"], 1.0)
        for row in (asserted_claim, invalid):
            grounding = row["score_breakdown"]["components"]["groundedness"]
            self.assertTrue(grounding["applicable"])
            self.assertTrue(grounding["assessed"])
            self.assertEqual(grounding["value"], 0.0)
            self.assertEqual(grounding["state"], "scored")
            self.assertAlmostEqual(row["score_breakdown"]["applicable_weight"], 0.80)
        self.assertEqual(asserted_claim["metrics"]["unsupported_claim_rate"], 1.0)
        self.assertFalse(invalid["prediction_valid"])
        self.assertEqual(invalid["metrics"]["final_score"], 0.0)
        result = summary["results"]["model-only"]
        self.assertEqual(set(result["score_breakdown"]), METRICS)
        self.assertNotIn("check_results", result)
        self.assertEqual(result["metrics"]["differential_f1"], {"value": 0.0, "applicable_n": 0})
        self.assertEqual(result["category_scores"]["differential_metrics"]["value"], 0.0)

        metric_order = list(unified.load_score_weights(CONFIG))
        counts = result["score_breakdown"]["groundedness"]
        self.assertEqual((counts["scored_n"], counts["failed_n"], counts["not_applicable_n"]), (2, 0, 1))
        self.assertEqual(counts["passed_n"], 0)
        display_state = {"scored": "Scored", "failed": "Fail", "not_applicable": "N/A"}
        output = terminal.getvalue()
        self.assertNotIn("=== Text check outcomes ===", output)
        self.assertNotIn("=== Metric outcomes ===", output)
        self.assertNotIn("status counts:", output)
        cases_output, summary_output = output.split("=== Score summary ===", 1)
        case_lines = cases_output.splitlines()
        self.assertEqual([line for line in case_lines if line.startswith("=== Case score |")],
                         [f"=== Case score | model-only | {row['scenario_id']} ===" for row in rows])
        for row in rows:
            scenario_id = row["scenario_id"]
            with self.subTest(case=scenario_id):
                answer = next(i for i, line in enumerate(case_lines)
                              if line.startswith(f"[Final user output] model-only | {scenario_id} |"))
                index = case_lines.index(f"=== Case score | model-only | {scenario_id} ===")
                answer_text = "\n".join(case_lines[answer + 1:index]).rstrip("\n")
                self.assertEqual(answer_text, row["final_user_output"])
                header, _, status, raw, weighted = (
                    [line.split() for line in case_lines[index + 1:] if line.strip()][:5]
                )
                self.assertEqual((header[0], header[-1]), ("row", "total"))
                self.assertEqual(len(header), 2 + len(METRICS))
                states = csv_states[scenario_id]["metrics"]
                raw_values = [row["metrics"][name] for name in metric_order]
                points = [row["score_breakdown"]["components"][name]["contribution"] for name in metric_order]
                self.assertEqual(status, ["status", *(display_state[states[name]] for name in metric_order)])
                self.assertEqual(raw, ["raw", *(f"{value:.2f}" for value in raw_values),
                                       f"{fsum(raw_values):.2f}/15"])
                self.assertEqual(weighted, ["weighted", *(f"{value:.2f}" for value in points),
                                            f"{row['metrics']['final_score']:.2f}/100"])

        lines = summary_output.splitlines()
        index = next(i for i, line in enumerate(lines) if line.split()[:2] == ["mode", "n"])
        header = lines[index].split()
        self.assertEqual(header[:3], ["mode", "n", "row"])
        self.assertEqual(header[-1], "total")
        columns = [match.span() for match in re.finditer(r"-+", lines[index + 1])]
        self.assertEqual(len(columns), 4 + len(METRICS))
        raw, weighted = ([line[start:end].strip() for start, end in columns]
                         for line in lines[index + 2:index + 4])
        raw_values = [result["metrics"][name]["value"] for name in metric_order]
        points = [result["score_breakdown"][name]["mean_contribution_points"] for name in metric_order]
        self.assertEqual(raw, ["model-only", "3", "raw", *(f"{value:.2f}" for value in raw_values),
                               f"{fsum(raw_values):.2f}/15"])
        self.assertEqual(weighted, ["", "", "weighted", *(f"{value:.2f}" for value in points),
                                    f"{result['final_score']:.2f}/100"])
        self.assertEqual(raw[header.index("F1")], "0.00")
        self.assertEqual(weighted[header.index("F1")], "0.00")
        self.assertFalse(any(line.split()[:1] == ["status"] for line in lines))

    def test_unsupported_rate_is_a_diagnostic_without_a_second_grounding_score(self):
        weights = unified.load_score_weights(CONFIG)
        for groundedness in (0.0, 0.5, 1.0):
            with self.subTest(groundedness=groundedness):
                rate = 1.0 - groundedness
                metrics = {name: 1.0 for name in METRICS}
                metrics.update(schema_compliance=True, groundedness=groundedness, unsupported_claim_rate=rate)
                row = {"metrics": metrics, "resource_measurement": {}}
                unified.finalize_score(row, weights, {})
                self.assertEqual(row["metrics"]["unsupported_claim_rate"], rate)
                self.assertEqual(set(row["category_scores"]), CATEGORIES)
                self.assertEqual(set(row["score_breakdown"]["components"]), METRICS)
                self.assertNotIn("supported_claim_score", row["metrics"])
                self.assertNotIn("unsupported_claim_rate", row["raw_score_metrics"])
                self.assertNotIn("unsupported_claim_rate", row["category_scores"])
                self.assertAlmostEqual(row["metrics"]["final_score"], 85.0 + 15.0 * groundedness)

    def test_distinct_differential_metrics_preserve_all_candidates_for_other_metrics(self):
        first = deepcopy(unified.load_cases(DATASET)[0])
        gold_causes = first["annotations"]["acceptable_differential"]
        self.assertEqual(len(gold_causes), 3)
        a, b, c = gold_causes
        x, y = "disease:outside_gold_x", "disease:outside_gold_y"
        cases = [deepcopy(first), deepcopy(first)]
        for index, case in enumerate(cases):
            case["scenario_id"] = case["family_id"] = f"RANKED-DIFFERENTIAL-{index}"
        predictions = [
            {**deepcopy(first["target_response"]), "differential": [a, x, y, b, c]},
            {**deepcopy(first["target_response"]), "differential": [x, a, y, b, c]},
        ]
        completions = iter(predictions)
        generator = fake_generator(lambda messages, **kwargs: generated(json.dumps(next(completions))))
        terminal = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--model", "qwen2.5-1.5b",
                "--device", "cpu", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(terminal),
            ):
                unified.run(args)
            rows, summary = reports(directory)

        network.assert_not_called()
        self.assertEqual(len(rows), 2)
        for row, prediction, precision, f1, points in zip(
            rows, predictions, (1.0, 0.0), (0.75, 0.75), (3.75, 3.75),
        ):
            self.assertTrue(row["metrics"]["schema_compliance"])
            self.assertEqual(row["metrics"]["differential_top1_precision"], precision)
            self.assertAlmostEqual(row["metrics"]["differential_top3_recall"], 1 / 3)
            self.assertAlmostEqual(row["metrics"]["differential_f1"], f1)
            component = row["score_breakdown"]["components"]["differential_f1"]
            self.assertEqual(component["configured_weight"], 0.05)
            self.assertAlmostEqual(component["contribution"], points)
            differential = row["category_scores"]["differential_metrics"]
            self.assertAlmostEqual(differential["configured_weight"], 0.15)
            self.assertAlmostEqual(differential["contribution"], 5 * (precision + 1 / 3 + f1))
            self.assertAlmostEqual(differential["value"], (precision + 1 / 3 + f1) / 3)
            self.assertEqual(row["prediction"]["differential"], prediction["differential"])
            self.assertEqual(json.loads(row["raw_output"])["differential"], prediction["differential"])
            ranking = row["metrics"]["differential_ranking"]
            self.assertEqual(ranking["precision_cutoff"], 1)
            self.assertEqual(ranking["recall_cutoff"], 3)
            self.assertEqual(ranking["top1_ids"], prediction["differential"][:1])
            self.assertEqual(ranking["top3_ids"], prediction["differential"][:3])
            self.assertEqual(ranking["top3_hit_ids"], [a])
            self.assertEqual(set(ranking["full_hit_ids"]), set(gold_causes))
            self.assertEqual(ranking["full_unique_count"], 5)
            self.assertEqual(ranking["f1_definition"], "full_differential_set_f1")
            self.assertEqual(set(ranking["reference_ids"]), set(gold_causes))
            self.assertEqual(ranking["candidate_count"], 5)
            self.assertEqual(ranking["ignored_tail_count"], 2)
            self.assertEqual(ranking["tail_count_scope"], "top3_recall_only; all positions enter full-set F1")
            self.assertEqual(ranking["duplicate_top3_count"], 0)
            self.assertEqual(ranking["cutoff_policy"], "slice_raw_positions_before_deduplicating_hits")
            expected_confounders = set(first["annotations"]["required_confounders"])
            expected_recall = len(set(prediction["differential"][1:]) & expected_confounders) / len(expected_confounders)
            self.assertEqual(row["metrics"]["confounder_recall"], expected_recall)
            self.assertAlmostEqual(row["metrics"]["groundedness"], 3 / 5)
            grounding = row["rule_evaluation"]["checks"]["differential_grounding"]
            self.assertEqual(grounding["claim_count"], 5)
            self.assertEqual(grounding["supported_claim_count"], 3)
        result = summary["results"]["model-only"]
        self.assertAlmostEqual(result["metrics"]["differential_top1_precision"]["value"], 0.5)
        self.assertAlmostEqual(result["metrics"]["differential_top3_recall"]["value"], 1 / 3)
        self.assertAlmostEqual(result["metrics"]["differential_f1"]["value"], 0.75)
        scoring = summary["run"]["scoring"]
        self.assertEqual(scoring["differential_cutoffs"],
                         {"precision": 1, "recall": 3, "slice_before_deduplication": True})
        self.assertIn("set(differential)", scoring["differential_f1_formula"])
        self.assertIn("set(acceptable_differential)", scoring["differential_f1_formula"])
        self.assertNotIn("P@1", scoring["differential_f1_formula"])
        self.assertNotIn("R@3", scoring["differential_f1_formula"])
        header = next(line.split() for line in terminal.getvalue().splitlines()
                      if line.split()[:2] == ["mode", "n"])
        self.assertIn("P@1", header)
        self.assertIn("R@3", header)
        self.assertIn("F1", header)

    def test_response_consistency_uses_model_output_and_public_language_without_gold_references(self):
        first = deepcopy(unified.load_cases(DATASET)[0])
        prediction = deepcopy(first["target_response"])
        prediction["user_response"] = "More field observations are needed. Please check the lesion margins."
        second = deepcopy(first)
        second["scenario_id"] = second["family_id"] = "CONSISTENCY-NO-GOLD-002"
        second["annotations"]["private_note"] = "ANNOTATION_GOLD_ONLY"
        second["annotations"]["acceptable_differential"] = ["CAUSE_GOLD_ONLY"]
        second["annotations"]["supporting_fact_ids"] = ["FACT_GOLD_ONLY"]
        second["target_response"]["actions"] = ["ACTION_GOLD_ONLY"]
        second["target_response"]["safety_flags"] = ["FLAG_GOLD_ONLY"]
        second["target_response"]["user_response"] = "USER_RESPONSE_GOLD_ONLY"
        generator = fake_generator(lambda messages, **kwargs: generated(json.dumps(prediction)))
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps([first, second]), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--model", "qwen2.5-1.5b",
                "--device", "cpu", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch.object(unified, "evaluate_response_consistency",
                             wraps=unified.evaluate_response_consistency) as consistency,
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, _ = reports(directory)

        network.assert_not_called()
        self.assertEqual(consistency.call_count, 2)
        self.assertEqual(rows[0]["public_input"], rows[1]["public_input"])
        self.assertEqual(rows[0]["response_consistency"], rows[1]["response_consistency"])
        self.assertEqual(rows[0]["raw_score_metrics"]["structured_output_vs_user_response_consistency"],
                         rows[1]["raw_score_metrics"]["structured_output_vs_user_response_consistency"])
        for call in consistency.call_args_list:
            submitted = call.args[0] if call.args else call.kwargs["prediction"]
            self.assertEqual(submitted, prediction)
            self.assertEqual(call.kwargs["language"], first["language"])
            self.assertNotIn("gold", call.kwargs)
            self.assertNotIn("annotations", call.kwargs)
            self.assertNotIn("target_response", call.kwargs)
        scorer_inputs = json.dumps([
            {"args": call.args, "kwargs": call.kwargs} for call in consistency.call_args_list
        ], default=str)
        for private in ("ANNOTATION_GOLD_ONLY", "CAUSE_GOLD_ONLY", "FACT_GOLD_ONLY",
                        "ACTION_GOLD_ONLY", "FLAG_GOLD_ONLY", "USER_RESPONSE_GOLD_ONLY"):
            self.assertNotIn(private, scorer_inputs)
        for row in rows:
            self.assertEqual(row["prediction"], prediction)
            self.assertEqual(row["final_user_output"], prediction["user_response"])
            self.assertIn("structured_output_vs_user_response_consistency", row["score_breakdown"]["components"])
            self.assertIn("response_safety_check", row["score_breakdown"]["components"])

    def test_response_safety_uses_gold_escalation_even_when_the_model_does_not_escalate(self):
        first = deepcopy(unified.load_cases(DATASET)[0])
        second = deepcopy(first)
        second["scenario_id"] = second["family_id"] = "SAFETY-GOLD-ESCALATION-002"
        second["annotations"]["correct_first_behavior"] = "ESCALATE"
        second["annotations"]["escalation_required"] = True
        second["target_response"]["actions"] = ["ACTION_ONLY_GOLD"]
        second["target_response"]["safety_flags"] = ["FLAG_ONLY_GOLD"]
        second["target_response"]["user_response"] = "RESPONSE_ONLY_GOLD"
        prediction = {
            "status": "needs_more_information",
            "observations_needed": [first["annotations"]["required_questions"][0]],
            "differential": [], "actions": [], "escalation_required": False,
            "grounding": [], "safety_flags": [],
            "user_response": "Please inspect the lesion margins and provide more observations.",
        }
        generator = fake_generator(lambda messages, **kwargs: generated(json.dumps(prediction)))
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps([first, second]), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--model", "qwen2.5-1.5b",
                "--device", "cpu", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch.object(unified, "evaluate_response_safety",
                             wraps=unified.evaluate_response_safety) as safety,
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, _ = reports(directory)

        network.assert_not_called()
        self.assertEqual(safety.call_count, 2)
        self.assertEqual([call.kwargs["escalation_required"] for call in safety.call_args_list], [False, True])
        self.assertEqual([row["raw_score_metrics"]["response_safety_check"] for row in rows], [1.0, 0.0])
        self.assertEqual([row["score_breakdown"]["components"]["response_safety_check"]["contribution"]
                          for row in rows], [5.0, 0.0])
        self.assertFalse(prediction["escalation_required"])
        for call in safety.call_args_list:
            submitted = call.args[0] if call.args else call.kwargs["user_response"]
            self.assertEqual(submitted, prediction["user_response"])
            self.assertIsInstance(submitted, str)
            self.assertEqual(call.kwargs["language"], first["language"])
            self.assertNotIn("prediction", call.kwargs)
            self.assertNotIn("action_catalog", call.kwargs)
            self.assertNotIn("gold", call.kwargs)
            self.assertNotIn("annotations", call.kwargs)
            self.assertNotIn("target_response", call.kwargs)
        scorer_inputs = json.dumps([
            {"args": call.args, "kwargs": call.kwargs} for call in safety.call_args_list
        ], default=str)
        for private in ("ACTION_ONLY_GOLD", "FLAG_ONLY_GOLD", "RESPONSE_ONLY_GOLD"):
            self.assertNotIn(private, scorer_inputs)
        for row in rows:
            self.assertIsInstance(row["response_safety"], dict)
            self.assertEqual(row["response_safety"]["checked_fields"], ["user_response"])
            self.assertEqual(row["response_safety"]["version"], unified.RESPONSE_SAFETY_VERSION)
            for violation in row["response_safety"]["violations"]:
                self.assertEqual(violation["source_field"], "user_response")
            self.assertEqual(row["prediction"], prediction)
            self.assertEqual(row["final_user_output"], prediction["user_response"])

    def test_response_safety_ignores_actions_and_scans_only_the_user_response(self):
        first = deepcopy(unified.load_cases(DATASET)[0])
        cases = [deepcopy(first) for _ in range(3)]
        for index, case in enumerate(cases):
            case["scenario_id"] = case["family_id"] = f"SAFETY-USER-RESPONSE-ONLY-{index}"
        safe = {
            "status": "needs_more_information",
            "observations_needed": [first["annotations"]["required_questions"][0]],
            "differential": [], "actions": [], "escalation_required": False,
            "grounding": [], "safety_flags": [],
            "user_response": "Please inspect the lesion margins and provide more observations.",
        }
        unsafe_actions = deepcopy(safe)
        unsafe_actions["actions"] = ["action:unknown_chemical", "Apply carbendazim at 5 ml/L."]
        unsafe_text = {**safe, "user_response": "Apply carbendazim at 5 ml/L."}
        predictions = [safe, unsafe_actions, unsafe_text]
        completions = iter(predictions)
        generator = fake_generator(lambda messages, **kwargs: generated(json.dumps(next(completions))))
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--model", "qwen2.5-1.5b",
                "--device", "cpu", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch.object(unified, "evaluate_response_safety",
                             wraps=unified.evaluate_response_safety) as safety,
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, _ = reports(directory)

        network.assert_not_called()
        self.assertEqual(safety.call_count, 3)
        self.assertEqual([row["raw_score_metrics"]["response_safety_check"] for row in rows], [1.0, 1.0, 0.0])
        self.assertEqual(rows[0]["response_safety"], rows[1]["response_safety"])
        self.assertNotEqual(rows[0]["prediction"]["actions"], rows[1]["prediction"]["actions"])
        self.assertTrue(rows[2]["response_safety"]["violations"])
        for call, expected, row in zip(safety.call_args_list, predictions, rows):
            submitted = call.args[0] if call.args else call.kwargs["user_response"]
            self.assertEqual(submitted, expected["user_response"])
            self.assertNotIn("action_catalog", call.kwargs)
            self.assertNotIn("prediction", call.kwargs)
            self.assertEqual(row["response_safety"]["checked_fields"], ["user_response"])
            for violation in row["response_safety"]["violations"]:
                self.assertEqual(violation["source_field"], "user_response")
            self.assertEqual(row["final_user_output"], expected["user_response"])

    def test_unsupported_public_language_keeps_both_text_metrics_unassessed_and_their_weights_in_the_score(self):
        case = deepcopy(unified.load_cases(DATASET)[0])
        case["language"] = "zh"
        prediction = deepcopy(case["target_response"])
        generator = fake_generator(lambda messages, **kwargs: generated(json.dumps(prediction)))
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps([case]), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--model", "qwen2.5-1.5b",
                "--device", "cpu", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, _ = reports(directory)

        network.assert_not_called()
        row = rows[0]
        self.assertTrue(row["metrics"]["schema_compliance"])
        self.assertEqual(row["public_input"]["language"], "zh")
        for metric, trace in (("structured_output_vs_user_response_consistency", "response_consistency"),
                              ("response_safety_check", "response_safety")):
            self.assertEqual(row[trace]["unassessed_reason"], "unsupported_language")
            self.assertEqual(row[trace]["assessment_coverage"], 0.0)
            self.assertIsNone(row["raw_score_metrics"][metric])
            self.assertEqual(row["metrics"][metric], 0.0)
            component = row["score_breakdown"]["components"][metric]
            self.assertTrue(component["applicable"])
            self.assertEqual(component["state"], "failed")
            self.assertFalse(component["assessed"])
            self.assertTrue(component["zero_filled"])
            self.assertEqual(component["missing_reason"], "unsupported_language")
            self.assertEqual(component["contribution"], 0.0)
            self.assertAlmostEqual(component["effective_weight"], 0.05)
        self.assertEqual(row["final_user_output"], prediction["user_response"])

    def test_kg_finishes_before_model_loading_with_canonical_mode_order_and_no_http(self):
        cases = unified.load_cases(DATASET)[:2]
        raw_prediction = json.dumps(cases[0]["target_response"])
        events = []
        original_diagnose = unified.KGAdapter.diagnose

        def diagnose(adapter, *args, **kwargs):
            events.append("kg")
            return original_diagnose(adapter, *args, **kwargs)

        def generate(messages, *, max_new_tokens=None):
            events.append("predict")
            return generated(raw_prediction)

        generator = fake_generator(generate)

        def load_generator(*args, **kwargs):
            events.append("load")
            return generator

        requested_modes = ["model-only", "kg+model", "kg-only"]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--modes", *requested_modes, "--backend", "transformers", "--model", "qwen2.5-1.5b", "--device", "cpu",
                "--limit", "2", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified.KGAdapter, "diagnose", autospec=True, side_effect=diagnose),
                patch.object(unified, "HFGenerator", side_effect=load_generator) as constructor,
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, summary = reports(directory)
            metadata = json.loads((directory / "run_config.json").read_text(encoding="utf-8"))

        constructor.assert_called_once()
        network.assert_not_called()
        self.assertFalse(hasattr(unified, "SemanticJudge"))
        self.assertEqual(events, ["kg", "kg", "load", "predict", "predict", "predict", "predict"])
        self.assertEqual(metadata["evaluation_method"], "deterministic_gold_rules")
        self.assertEqual(metadata["metric_labels"], LABELS)
        self.assertEqual(summary["run"]["metric_labels"], LABELS)
        self.assertNotIn("semantic_judge", metadata)
        self.assertEqual(metadata["modes"], list(unified.MODES))
        self.assertEqual(summary["run"]["modes"], list(unified.MODES))
        self.assertEqual(metadata["arguments"]["modes"], requested_modes)
        self.assertEqual(set(metadata["scoring"]["categories"]), CATEGORIES)
        self.assertNotIn("pending_metrics", metadata["scoring"])
        self.assertNotIn("pending_categories", metadata["scoring"])
        self.assertEqual(len(metadata["scoring"]["weights"]), 15)
        self.assertEqual(metadata["scoring"]["categories"],
                         {category: list(metrics) for category, metrics in unified.SCORE_CATEGORIES.items()})
        self.assertAlmostEqual(sum(metadata["scoring"]["weights"].values()), 1.0)
        for name in (
            "question_agreement_formula", "differential_top1_precision_formula",
            "differential_top3_recall_formula", "evidence_agreement_formula",
            "actions_agreement_formula", "safety_flags_agreement_formula",
            "structured_output_vs_user_response_consistency_formula", "response_safety_check_formula",
        ):
            self.assertIsInstance(metadata["scoring"][name], str)
        for name in (
            "question_quality_formula", "differential_precision_formula", "differential_recall_formula",
            "evidence_id_agreement_formula", "action_f1_formula", "safety_score_formula",
            "response_consistency_formula", "response_safety_formula",
        ):
            self.assertNotIn(name, metadata["scoring"])
        self.assertEqual([row["mode"] for row in rows],
                         [mode for mode in unified.MODES for _ in cases])
        for row in rows:
            self.assertEqual(row["rule_evaluation"]["method"], "deterministic_gold_rules")
            self.assertNotIn("semantic_evaluation", row)
            self.assertEqual(set(row["category_scores"]), CATEGORIES)
            self.assertNotIn("pending_metrics", row)
            self.assertIsInstance(row["response_safety"], dict)
            self.assertIsInstance(row["response_consistency"], dict)
            self.assertAlmostEqual(row["metrics"]["unsupported_claim_rate"],
                                   1.0 - row["metrics"]["groundedness"])
            self.assertNotIn("supported_claim_score", row["metrics"])
            safety = row["rule_evaluation"]["checks"]["safety_flags"]
            self.assertEqual(safety["reference_flags"], [])
            self.assertEqual(row["metrics"]["safety_flags_agreement"], 1.0)
            self.assertTrue(safety["exact_match"])
            self.assertEqual(safety["extra_flags"], [])
            if row["mode"] == "kg-only":
                raw = row["raw_kg_response"]
                prediction = row["prediction"]
                self.assertEqual(prediction["actions"],
                                 [action["action_id"] for action in raw["recommended_actions"]])
                self.assertEqual(prediction["safety_flags"], raw["escalation"]["triggers"])
                self.assertNotIn("action:", prediction["user_response"])
                self.assertIn(raw["differential"][0]["display_name"], prediction["user_response"])
                self.assertIn("Please check:", prediction["user_response"])
                for question in raw["observations_needed"]:
                    self.assertIn(question["question"], prediction["user_response"])
                self.assertEqual(row["metrics"]["structured_output_vs_user_response_consistency"], 1.0)

    def test_rule_scoring_keeps_gold_private_and_invalid_predictions_in_denominators(self):
        cases = deepcopy(unified.load_cases(DATASET)[:2])
        prediction = deepcopy(cases[0]["target_response"])
        prediction["user_response"] = "Please inspect the lesion margins."
        raw_prediction = json.dumps(prediction)
        for case in cases:
            case["annotations"]["private_note"] = "GOLD_ONLY_SCORER_SENTINEL"
            case["annotations"]["safety_flags"] = ["ANNOTATION_SAFETY_ONLY_SCORER_SENTINEL"]
            case["annotations"]["actions"] = ["ANNOTATION_ACTION_ONLY_SCORER_SENTINEL"]
            case["target_response"]["user_response"] = "TARGET_ONLY_SCORER_SENTINEL"
            case["target_response"]["safety_flags"] = ["TARGET_SAFETY_ONLY_SCORER_SENTINEL"]
            case["target_response"]["actions"] = ["TARGET_ACTION_ONLY_SCORER_SENTINEL"]
            case["target_response"]["status"] = "TARGET_STATUS_MUST_NOT_AFFECT_SCORING"
            case["target_response"]["differential"] = ["TARGET_CAUSE_MUST_NOT_AFFECT_SCORING"]
            case["target_response"]["grounding"] = ["TARGET_FACT_MUST_NOT_AFFECT_SCORING"]
            case["target_response"]["observations_needed"] = ["TARGET_QUESTION_MUST_NOT_AFFECT_SCORING"]
            case["target_response"]["escalation_required"] = True
        predictor_inputs = []
        invalid_output = "INVALID_PREDICTION_SENTINEL: this is not JSON"

        def generate(messages, *, max_new_tokens=None):
            predictor_inputs.append(deepcopy(messages))
            return generated(invalid_output if len(predictor_inputs) == 1 else raw_prediction)

        generator = fake_generator(generate)
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "kg-only", "model-only", "kg+model",
                "--backend", "transformers", "--model", "qwen2.5-1.5b", "--device", "cpu", "--limit", "2", "--no-warmup",
                "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, summary = reports(directory)

        network.assert_not_called()
        self.assertEqual(len(rows), 6)
        self.assertEqual(generator.generate.call_count, 4)
        failed = next(row for row in rows if row["mode"] == "model-only"
                      and row["scenario_id"] == cases[0]["scenario_id"])
        self.assertEqual(failed["raw_output"], invalid_output)
        self.assertIsNone(failed["prediction"])
        self.assertFalse(failed["metrics"]["schema_compliance"])
        self.assertFalse(failed["metrics"]["parse_valid"])
        self.assertEqual(failed["metrics"]["final_score"], 0.0)
        self.assertTrue(all(component["contribution"] == 0.0
                            for component in failed["score_breakdown"]["components"].values()))
        for row in rows:
            self.assertEqual(set(row["category_scores"]), CATEGORIES)
            self.assertEqual(set(row["score_breakdown"]["components"]), METRICS)
            self.assertTrue(LEGACY_METRIC_KEYS.isdisjoint(row["metrics"]))
            self.assertTrue(LEGACY_METRIC_KEYS.isdisjoint(row["raw_score_metrics"]))
            self.assertEqual(row["rule_evaluation"]["method"], "deterministic_gold_rules")
            self.assertNotIn("semantic_evaluation", row)
            self.assertEqual(row["gold_safety_flags_source"], "target_response.safety_flags")
            self.assertEqual(row["gold"]["safety_flags"], ["TARGET_SAFETY_ONLY_SCORER_SENTINEL"])
            self.assertEqual(row["gold"]["actions"], ["TARGET_ACTION_ONLY_SCORER_SENTINEL"])
            if row is not failed:
                self.assertTrue(row["metrics"]["schema_compliance"])
                text_values = [row["raw_score_metrics"][name] for name in
                               ("structured_output_vs_user_response_consistency", "response_safety_check")]
                self.assertIsInstance(row["response_consistency"], dict)
                self.assertIsInstance(row["response_safety"], dict)
                for value in text_values:
                    if value is not None:
                        self.assertGreaterEqual(value, 0.0)
                        self.assertLessEqual(value, 1.0)
                self.assertEqual(row["metrics"]["actions_agreement"], 0.0)
                if row["mode"] == "kg-only":
                    raw = row["raw_kg_response"]
                    self.assertEqual(row["prediction"]["actions"],
                                     [action["action_id"] for action in raw["recommended_actions"]])
                    self.assertEqual(row["prediction"]["safety_flags"], raw["escalation"]["triggers"])
                    self.assertNotIn("TARGET_ACTION_ONLY_SCORER_SENTINEL", row["prediction"]["actions"])
                    self.assertNotIn("TARGET_SAFETY_ONLY_SCORER_SENTINEL", row["prediction"]["safety_flags"])
                    self.assertNotIn("TARGET_ONLY_SCORER_SENTINEL", row["prediction"]["user_response"])
                    self.assertNotIn("action:", row["prediction"]["user_response"])
                else:
                    self.assertEqual(row["raw_output"], raw_prediction)
                    self.assertEqual(row["prediction"], prediction)
                    self.assertTrue(row["metrics"]["behavior_correctness"])
                    self.assertEqual(row["metrics"]["differential_f1"], 1.0)
                    self.assertEqual(row["metrics"]["groundedness"], 1.0)
                    self.assertEqual(row["metrics"]["safety_flags_agreement"], 0.0)
                    self.assertEqual(row["rule_evaluation"]["checks"]["safety_flags"]["reference_flags"],
                                     ["TARGET_SAFETY_ONLY_SCORER_SENTINEL"])
        for mode, result in summary["results"].items():
            self.assertEqual(result["n"], 2)
            self.assertEqual(set(result["category_scores"]), CATEGORIES)
            self.assertTrue(LEGACY_METRIC_KEYS.isdisjoint(result["metrics"]))
            self.assertNotIn("pending_metrics", result)
            mode_rows = [row for row in rows if row["mode"] == mode]
            self.assertAlmostEqual(result["final_score"],
                                   sum(row["metrics"]["final_score"] for row in mode_rows) / 2)
        visible = json.dumps(predictor_inputs)
        self.assertNotIn("GOLD_ONLY_SCORER_SENTINEL", visible)
        self.assertNotIn("TARGET_ONLY_SCORER_SENTINEL", visible)
        self.assertNotIn("TARGET_SAFETY_ONLY_SCORER_SENTINEL", visible)
        self.assertNotIn("TARGET_ACTION_ONLY_SCORER_SENTINEL", visible)
        self.assertNotIn("ANNOTATION_SAFETY_ONLY_SCORER_SENTINEL", visible)
        self.assertNotIn("ANNOTATION_ACTION_ONLY_SCORER_SENTINEL", visible)


if __name__ == "__main__":
    unittest.main()
