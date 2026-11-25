"""Hand-calculable checks for the shared weighted evaluator score."""

from copy import deepcopy
from contextlib import redirect_stdout
import csv
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import eval.evaluate_unified as unified


ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = {
    "behavior_correctness": 0.25,
    "differential_f1": 0.30,
    "required_question_recall": 0.15,
    "confounder_recall": 0.10,
    "escalation_correctness": 0.10,
    "schema_compliance": 0.10,
}
V03_WEIGHTS = {
    "behavior_correctness": 0.20,
    "differential_top1_precision": 0.05,
    "differential_top3_recall": 0.05,
    "differential_f1": 0.05,
    "confounder_recall": 0.05,
    "groundedness": 0.15,
    "question_agreement": 0.05,
    "evidence_agreement": 0.05,
    "actions_agreement": 0.05,
    "safety_flags_agreement": 0.05,
    "escalation_correctness": 0.05,
    "structured_output_vs_user_response_consistency": 0.05,
    "response_safety_check": 0.05,
    "schema_compliance": 0.05,
    "resource_efficiency": 0.05,
}
DIFFERENTIAL_METRICS = ("differential_top1_precision", "differential_top3_recall", "differential_f1")


def perfect_metrics(**changes):
    metrics = {
        "behavior_correctness": True,
        "differential_top1_precision": 1.0,
        "differential_top3_recall": 1.0,
        "differential_f1": 1.0,
        "required_question_recall": 1.0,
        "confounder_recall": 1.0,
        "escalation_correctness": True,
        "schema_compliance": True,
    }
    metrics.update(changes)
    return metrics


def partial_metrics(**changes):
    metrics = perfect_metrics(differential_f1=0.0, required_question_recall=0.0,
                              escalation_correctness=False)
    metrics.update(changes)
    return metrics


def v03_metrics(**changes):
    metrics = dict.fromkeys(V03_WEIGHTS, 1.0)
    metrics.update(behavior_correctness=True, escalation_correctness=True, schema_compliance=True)
    metrics.update(changes)
    return metrics


def scored_record(mode, scenario_id, scoring_metrics, *, weights=WEIGHTS, unavailable_metrics=None,
                  not_applicable_metrics=None):
    gold = {
        "correct_first_behavior": "ASK", "acceptable_differential": ["disease:example"],
        "required_confounders": ["disease:example"], "required_questions": ["question:example"],
        "escalation_required": False, "supporting_fact_ids": ["FACT-001"],
    }
    prediction = {
        "status": "needs_more_information", "observations_needed": ["question:example"],
        "differential": ["disease:example"], "actions": [], "escalation_required": False,
        "grounding": ["FACT-001"], "safety_flags": [], "user_response": "Please inspect the leaves.",
    }
    metrics = unified.evaluate_prediction(prediction, gold)
    metrics.update(scoring_metrics)
    breakdown = unified.compute_weighted_score(
        metrics, weights, unavailable_metrics=unavailable_metrics,
        not_applicable_metrics=not_applicable_metrics,
    )
    metrics.update(parse_valid=True, latency_s=0.01, cuda_peak_allocated_mib=None,
                   final_score=breakdown["score"])
    return {
        "mode": mode, "scenario_id": scenario_id, "gold": gold,
        "metrics": metrics, "score_breakdown": breakdown, "error": None,
    }


class WeightedScoreTests(unittest.TestCase):
    def test_perfect_prediction_is_one_hundred_with_consistent_contributions(self):
        result = unified.compute_weighted_score(perfect_metrics(), WEIGHTS)
        self.assertEqual(result["score"], 100.0)
        self.assertTrue(result["schema_gate_passed"])
        self.assertAlmostEqual(result["applicable_weight"], 1.0)
        self.assertEqual(set(result["components"]), set(WEIGHTS))
        for metric, weight in WEIGHTS.items():
            with self.subTest(metric=metric):
                component = result["components"][metric]
                self.assertTrue(component["applicable"])
                self.assertEqual(component["configured_weight"], weight)
                self.assertAlmostEqual(component["effective_weight"], weight)
                self.assertAlmostEqual(component["contribution"], weight * 100)
        self.assertAlmostEqual(sum(item["contribution"] for item in result["components"].values()),
                               result["score"])

    def test_mixed_metric_score_is_forty_five_points(self):
        result = unified.compute_weighted_score(partial_metrics(), WEIGHTS)
        self.assertAlmostEqual(result["score"], 45.0)
        self.assertAlmostEqual(result["components"]["behavior_correctness"]["contribution"], 25.0)
        self.assertAlmostEqual(result["components"]["confounder_recall"]["contribution"], 10.0)
        self.assertAlmostEqual(result["components"]["schema_compliance"]["contribution"], 10.0)

    def test_none_question_is_zero_without_removing_or_renormalizing_weight(self):
        result = unified.compute_weighted_score(partial_metrics(required_question_recall=None), WEIGHTS)
        self.assertAlmostEqual(result["score"], 45.0)
        self.assertAlmostEqual(result["applicable_weight"], 1.0)
        question = result["components"]["required_question_recall"]
        self.assertEqual(question["value"], 0.0)
        self.assertIsNone(question["raw_value"])
        self.assertTrue(question["zero_filled"])
        self.assertTrue(question["applicable"])
        self.assertFalse(question["assessed"])
        self.assertEqual(question["missing_reason"], "metric_returned_none")
        self.assertEqual(question["effective_weight"], 0.15)
        self.assertEqual(question["contribution"], 0.0)
        self.assertAlmostEqual(
            result["components"]["behavior_correctness"]["effective_weight"], 0.25,
        )

    def test_not_applicable_metric_keeps_its_weight_without_earning_points(self):
        metrics = perfect_metrics(behavior_correctness=False, differential_f1=None,
                                  required_question_recall=None)
        weights = dict.fromkeys(("behavior_correctness", "differential_f1",
                                 "required_question_recall", "schema_compliance"), 1.0)
        excluded = {"required_question_recall": "no_reference_questions"}
        unavailable = {"differential_f1": "reference_unavailable"}
        result = unified.compute_weighted_score(
            metrics, weights, not_applicable_metrics=excluded, unavailable_metrics=unavailable,
        )
        self.assertEqual(result["score"], 25.0)
        self.assertEqual(result["applicable_weight"], 3.0)
        self.assertEqual(result["unavailable_metrics"], unavailable)
        self.assertEqual(result["not_applicable_metrics"], excluded)
        question = result["components"]["required_question_recall"]
        self.assertEqual(question["value"], 0.0)
        self.assertIsNone(question["raw_value"])
        self.assertEqual(question["state"], "not_applicable")
        self.assertEqual(question["not_applicable_reason"], excluded["required_question_recall"])
        self.assertIsNone(question["missing_reason"])
        self.assertFalse(question["applicable"])
        self.assertFalse(question["assessed"])
        self.assertTrue(question["zero_filled"])
        self.assertEqual(question["configured_weight"], 1.0)
        self.assertEqual(question["effective_weight"], 0.25)
        self.assertEqual(question["contribution"], 0.0)
        assessed_zero = result["components"]["behavior_correctness"]
        self.assertIs(assessed_zero["raw_value"], False)
        self.assertEqual(assessed_zero["state"], "scored")
        self.assertTrue(assessed_zero["assessed"])
        self.assertFalse(assessed_zero["zero_filled"])
        self.assertIsNone(assessed_zero["missing_reason"])
        self.assertEqual(assessed_zero["contribution"], 0.0)
        missing = result["components"]["differential_f1"]
        self.assertEqual(missing["state"], "failed")
        self.assertIsNone(missing["raw_value"])
        self.assertFalse(missing["assessed"])
        schema = result["components"]["schema_compliance"]
        self.assertEqual(schema["state"], "scored")
        self.assertEqual(schema["effective_weight"], 0.25)
        self.assertEqual(schema["contribution"], 25.0)

    def test_all_not_applicable_scores_zero_for_valid_and_invalid_output(self):
        metrics = perfect_metrics(required_question_recall=None)
        weights = {"required_question_recall": 1.0}
        excluded = {"required_question_recall": "no_reference_questions"}
        for valid in (True, False):
            with self.subTest(prediction_valid=valid):
                result = unified.compute_weighted_score(
                    metrics, weights, not_applicable_metrics=excluded, prediction_valid=valid,
                )
                self.assertEqual(result["score"], 0.0)
                self.assertEqual(result["applicable_weight"], 0.0)
                question = result["components"]["required_question_recall"]
                self.assertEqual(question["state"], "not_applicable")
                self.assertEqual(question["effective_weight"], 1.0)
                self.assertEqual(question["contribution"], 0.0)

    def test_all_configured_metrics_none_keep_relative_weights_and_score_zero(self):
        result = unified.compute_weighted_score(
            {"schema_compliance": True, "differential_f1": None, "question_agreement": None},
            {"differential_f1": 1.0, "question_agreement": 3.0},
        )
        self.assertTrue(result["schema_gate_passed"])
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["applicable_weight"], 4.0)
        self.assertEqual(result["components"]["differential_f1"]["effective_weight"], 0.25)
        self.assertEqual(result["components"]["question_agreement"]["effective_weight"], 0.75)
        for component in result["components"].values():
            self.assertTrue(component["applicable"])
            self.assertTrue(component["zero_filled"])
            self.assertFalse(component["assessed"])
            self.assertEqual(component["value"], 0.0)
            self.assertIsNone(component["raw_value"])

    def test_unavailable_agreement_metrics_still_zero_fill_and_keep_their_weights(self):
        result = unified.compute_weighted_score(
            v03_metrics(question_agreement=None, evidence_agreement=None), V03_WEIGHTS,
        )
        self.assertAlmostEqual(result["score"], 90.0)
        self.assertAlmostEqual(result["applicable_weight"], 1.0)
        for metric, weight in (("question_agreement", 0.05), ("evidence_agreement", 0.05)):
            component = result["components"][metric]
            self.assertIsNone(component["raw_value"])
            self.assertEqual(component["value"], 0.0)
            self.assertEqual(component["contribution"], 0.0)
            self.assertTrue(component["applicable"])
            self.assertTrue(component["zero_filled"])
            self.assertFalse(component["assessed"])
            self.assertAlmostEqual(component["configured_weight"], weight)
            self.assertAlmostEqual(component["effective_weight"], weight)

    def test_none_with_relative_weight_cannot_transfer_points_to_other_metrics(self):
        result = unified.compute_weighted_score(
            perfect_metrics(differential_f1=None),
            {"behavior_correctness": 1.0, "differential_f1": 3.0, "schema_compliance": 0.0},
        )
        self.assertEqual(result["score"], 25.0)
        self.assertEqual(result["applicable_weight"], 4.0)
        self.assertEqual(result["components"]["differential_f1"]["effective_weight"], 0.75)

    def test_invalid_schema_gates_score_and_every_component_to_zero(self):
        for schema_compliance in (False, None):
            with self.subTest(schema_compliance=schema_compliance):
                result = unified.compute_weighted_score(perfect_metrics(schema_compliance=schema_compliance), WEIGHTS)
                self.assertFalse(result["schema_gate_passed"])
                self.assertEqual(result["score"], 0.0)
                self.assertTrue(all(item["contribution"] == 0.0 for item in result["components"].values()))

    def test_relative_subset_and_zero_weights_are_supported(self):
        weights = {"behavior_correctness": 1.0, "differential_f1": 3.0, "schema_compliance": 0.0}
        result = unified.compute_weighted_score(perfect_metrics(behavior_correctness=False), weights)
        self.assertAlmostEqual(result["score"], 75.0)
        self.assertEqual(result["applicable_weight"], 4.0)
        self.assertEqual(result["components"]["schema_compliance"]["contribution"], 0.0)
        self.assertAlmostEqual(result["components"]["differential_f1"]["effective_weight"], 0.75)

    def test_missing_configured_metric_and_schema_gate_key_are_errors(self):
        for missing, weights in (("differential_f1", WEIGHTS),
                                 ("schema_compliance", {"differential_f1": 1.0})):
            with self.subTest(missing=missing):
                metrics = perfect_metrics()
                del metrics[missing]
                with self.assertRaises((ValueError, KeyError)):
                    unified.compute_weighted_score(metrics, weights)

    def test_nonfinite_out_of_range_and_non_numeric_metrics_are_rejected(self):
        for bad_value in (-0.01, 1.01, float("nan"), float("inf"), -float("inf"), "1.0"):
            with self.subTest(value=bad_value):
                with self.assertRaises((ValueError, TypeError)):
                    unified.compute_weighted_score(perfect_metrics(differential_f1=bad_value), WEIGHTS)

    def test_illegal_weights_are_rejected(self):
        illegal = (
            {}, {key: 0.0 for key in WEIGHTS}, {"unknown_metric": 1.0},
            {"differential_f1": -1.0}, {"differential_f1": float("nan")},
            {"differential_f1": float("inf")}, {"differential_f1": True},
            {"differential_f1": "1.0"},
            {"supported_claim_score": 1.0}, {"unsupported_claim_rate": 1.0},
        )
        for weights in illegal:
            with self.subTest(weights=weights):
                with self.assertRaises(ValueError):
                    unified.compute_weighted_score(perfect_metrics(), weights)

    def test_scoring_does_not_change_metrics_or_weights(self):
        metrics, weights = partial_metrics(required_question_recall=None), deepcopy(WEIGHTS)
        original_metrics, original_weights = deepcopy(metrics), deepcopy(weights)
        unified.compute_weighted_score(metrics, weights)
        self.assertEqual(metrics, original_metrics)
        self.assertEqual(weights, original_weights)


class WeightConfigurationTests(unittest.TestCase):
    def test_removed_metric_names_are_rejected_as_configured_weight_keys(self):
        removed = (
            "first_behavior_correct", "differential_precision", "differential_recall",
            "question_quality", "evidence_id_agreement", "action_f1", "safety_score",
            "escalation_correct", "response_consistency_score", "response_safety_score", "schema_valid",
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "weights.yaml"
            for name in removed:
                with self.subTest(metric=name):
                    path.write_text(json.dumps({"unified_weights": {name: 1.0}}), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        unified.load_score_weights(path)

    def test_repository_configuration_has_fifteen_weights_without_a_complement_score(self):
        configured = unified.load_score_weights(ROOT / "configs/eval/eval_config.yaml")
        self.assertEqual(list(configured), list(V03_WEIGHTS))
        self.assertEqual([name for name in unified.SCORE_METRICS if name in configured], list(V03_WEIGHTS))
        self.assertTrue(all(weight > 0 for weight in configured.values()))
        self.assertEqual(configured, V03_WEIGHTS)
        self.assertEqual(len(configured), 15)
        self.assertEqual(sum(Decimal(str(weight)) for weight in configured.values()), Decimal("1.00"))
        self.assertNotIn("supported_claim_score", configured)
        self.assertNotIn("unsupported_claim_rate", configured)
        self.assertEqual(configured["structured_output_vs_user_response_consistency"], 0.05)
        self.assertEqual(configured["response_safety_check"], 0.05)
        self.assertEqual({name: configured[name] for name in DIFFERENTIAL_METRICS},
                         dict.fromkeys(DIFFERENTIAL_METRICS, 0.05))

    def test_fifteen_submetric_weights_score_one_hundred_and_preserve_groundedness_contribution(self):
        result = unified.compute_weighted_score(v03_metrics(groundedness=0.5), V03_WEIGHTS)
        self.assertAlmostEqual(result["applicable_weight"], 1.0)
        self.assertAlmostEqual(result["score"], 92.5)
        self.assertAlmostEqual(result["components"]["groundedness"]["effective_weight"], 0.15)
        self.assertAlmostEqual(result["components"]["groundedness"]["contribution"], 7.5)
        self.assertAlmostEqual(sum(item["effective_weight"] for item in result["components"].values()), 1.0)
        self.assertAlmostEqual(unified.compute_weighted_score(v03_metrics(), V03_WEIGHTS)["score"], 100.0)

    def test_default_weights_apply_twenty_fifteen_and_five_point_singleton_losses(self):
        weights = unified.load_score_weights(ROOT / "configs/eval/eval_config.yaml")
        self.assertAlmostEqual(unified.compute_weighted_score(v03_metrics(), weights)["score"], 100.0)
        for metric in V03_WEIGHTS:
            if metric == "schema_compliance":
                continue  # Schema failure gates the entire score, beyond its five-point weight.
            loss = {"behavior_correctness": 20.0, "groundedness": 15.0}.get(metric, 5.0)
            with self.subTest(metric=metric, loss=loss):
                result = unified.compute_weighted_score(v03_metrics(**{metric: 0.0}), weights)
                self.assertAlmostEqual(result["score"], 100.0 - loss)
                self.assertAlmostEqual(result["components"][metric]["contribution"], 0.0)
                self.assertAlmostEqual(result["components"][metric]["effective_weight"], loss / 100)

    def test_differential_submetrics_each_control_five_points_independently(self):
        perfect = unified.compute_weighted_score(v03_metrics(), V03_WEIGHTS)
        self.assertAlmostEqual(perfect["score"], 100.0)
        for metric in DIFFERENTIAL_METRICS:
            with self.subTest(metric=metric):
                result = unified.compute_weighted_score(v03_metrics(**{metric: 0.0}), V03_WEIGHTS)
                self.assertAlmostEqual(result["score"], 95.0)
                self.assertAlmostEqual(sum(result["components"][name]["contribution"]
                                           for name in DIFFERENTIAL_METRICS), 10.0)
                self.assertEqual(result["components"][metric]["contribution"], 0.0)
                for other in set(DIFFERENTIAL_METRICS) - {metric}:
                    self.assertAlmostEqual(result["components"][other]["contribution"], 5.0)

    def test_top1_miss_with_full_recall_and_f1_earns_ten_differential_points(self):
        result = unified.compute_weighted_score(v03_metrics(differential_top1_precision=0.0), V03_WEIGHTS)
        self.assertAlmostEqual(result["score"], 95.0)
        self.assertAlmostEqual(sum(result["components"][name]["contribution"]
                                   for name in DIFFERENTIAL_METRICS), 10.0)

    def test_ranked_differential_submetrics_are_available_in_custom_weights(self):
        weights = {"differential_top1_precision": 1.0, "differential_top3_recall": 3.0}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "weights.yaml"
            path.write_text(json.dumps({"unified_weights": weights}), encoding="utf-8")
            self.assertEqual(unified.load_score_weights(path), weights)
        result = unified.compute_weighted_score(v03_metrics(differential_top1_precision=0.0), weights)
        self.assertAlmostEqual(result["score"], 75.0)
        self.assertEqual(set(result["components"]), set(weights))

    def test_custom_yaml_accepts_relative_subset_and_zero_weight(self):
        expected = {"behavior_correctness": 1.0, "differential_f1": 3.0, "schema_compliance": 0.0}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "weights.yaml"
            path.write_text(json.dumps({"unified_weights": expected}), encoding="utf-8")
            self.assertEqual(unified.load_score_weights(path), expected)

    def test_both_text_metrics_are_available_in_custom_weight_configurations(self):
        weights = {"structured_output_vs_user_response_consistency": 1.0, "response_safety_check": 1.0}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "weights.yaml"
            path.write_text(json.dumps({"unified_weights": weights}), encoding="utf-8")
            self.assertEqual(unified.load_score_weights(path), weights)
        result = unified.compute_weighted_score(
            v03_metrics(structured_output_vs_user_response_consistency=0.5, response_safety_check=1.0), weights,
        )
        self.assertAlmostEqual(result["score"], 75.0)

    def test_invalid_yaml_weight_blocks_are_rejected(self):
        documents = (
            {}, {"unified_weights": None}, {"unified_weights": []},
            {"unified_weights": {}}, {"unified_weights": {"differential_f1": 0}},
            {"unified_weights": {"unknown_metric": 1}},
            {"unified_weights": {"supported_claim_score": 0.1}},
            {"unified_weights": {"unsupported_claim_rate": 0.1}},
            {"unified_weights": {"differential_f1": -1}},
            {"unified_weights": {"differential_f1": True}},
            {"unified_weights": {"differential_f1": "NaN"}},
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "weights.yaml"
            for document in documents:
                with self.subTest(document=document):
                    path.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises((ValueError, KeyError)):
                        unified.load_score_weights(path)


class ScoreSummaryTests(unittest.TestCase):
    def test_kg_run_writes_case_scores_and_their_mean(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--modes", "kg-only", "--dataset", str(ROOT / "data/eval/gold_eval_v0.3.json"),
                "--output-dir", str(directory), "--limit", "2", "--no-warmup",
            ])
            terminal = io.StringIO()
            with (
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(terminal),
            ):
                unified.run(args)
            network.assert_not_called()
            rows = [json.loads(line) for line in
                    (directory / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
            summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
            with (directory / "case_metrics.csv").open(encoding="utf-8-sig", newline="") as handle:
                csv_fields = next(csv.reader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual([name for name in csv_fields if name in V03_WEIGHTS], list(V03_WEIGHTS))
            result = summary["results"]["kg-only"]
            self.assertEqual([name for name in result["metrics"] if name in V03_WEIGHTS], list(V03_WEIGHTS))
            self.assertEqual(list(result["score_breakdown"]), list(V03_WEIGHTS))
            self.assertEqual(list(result["category_scores"]), list(unified.SCORE_CATEGORIES))
            header = next(line.split() for line in terminal.getvalue().splitlines()
                          if line.split()[:2] == ["mode", "n"])
            self.assertLess(header.index("gnd"), header.index("Q-agr"))
            self.assertLess(header.index("Q-agr"), header.index("E-agr"))
            for row in rows:
                breakdown = row["score_breakdown"]
                self.assertEqual(list(breakdown["components"]), list(V03_WEIGHTS))
                self.assertEqual(list(row["category_scores"]), list(unified.SCORE_CATEGORIES))
                self.assertEqual(row["metrics"]["final_score"], breakdown["score"])
                self.assertAlmostEqual(sum(item["contribution"] for item in breakdown["components"].values()),
                                       breakdown["score"])
            expected_mean = sum(row["metrics"]["final_score"] for row in rows) / 2.0
            self.assertEqual(summary["results"]["kg-only"]["metrics"]["final_score"]["applicable_n"], 2)
            self.assertAlmostEqual(summary["results"]["kg-only"]["metrics"]["final_score"]["value"],
                                   expected_mean)

    def test_each_mode_averages_case_scores_and_component_points(self):
        records = []
        for mode in ("kg-only", "model-only", "kg+model"):
            records.extend((
                scored_record(mode, "case-1", partial_metrics()),
                scored_record(mode, "case-2", partial_metrics(required_question_recall=None)),
            ))
        expected_score = 45.0
        summary = unified.summarize(records)
        for mode in ("kg-only", "model-only", "kg+model"):
            with self.subTest(mode=mode):
                result = summary[mode]
                self.assertEqual(result["n"], 2)
                self.assertEqual(result["metrics"]["final_score"]["applicable_n"], 2)
                self.assertAlmostEqual(result["metrics"]["final_score"]["value"], expected_score)
                points = result["score_breakdown"]
                for metric in WEIGHTS:
                    expected_points = sum(
                        row["score_breakdown"]["components"][metric]["contribution"]
                        for row in records if row["mode"] == mode
                    ) / 2.0
                    self.assertAlmostEqual(points[metric]["mean_contribution_points"], expected_points)
                self.assertAlmostEqual(sum(item["mean_contribution_points"] for item in points.values()),
                                       expected_score)

    def test_invalid_case_remains_in_final_score_denominator(self):
        records = [scored_record("model-only", "valid-case", perfect_metrics()),
                   scored_record("model-only", "invalid-case", perfect_metrics(schema_compliance=False))]
        result = unified.summarize(records)["model-only"]
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["metrics"]["final_score"]["applicable_n"], 2)
        self.assertEqual(result["metrics"]["final_score"]["value"], 50.0)
        self.assertAlmostEqual(sum(item["mean_contribution_points"]
                                   for item in result["score_breakdown"].values()), 50.0)

    def test_summary_includes_not_applicable_zero_in_metric_and_case_means(self):
        weights = {"schema_compliance": 1.0, "confounder_recall": 1.0}
        records = [
            scored_record("model-only", "pass", perfect_metrics(), weights=weights),
            scored_record("model-only", "partial", perfect_metrics(confounder_recall=0.5), weights=weights),
            scored_record("model-only", "zero", perfect_metrics(confounder_recall=0.0), weights=weights),
            scored_record("model-only", "unavailable", perfect_metrics(confounder_recall=None), weights=weights),
            scored_record("model-only", "not-applicable", perfect_metrics(confounder_recall=None),
                          weights=weights, not_applicable_metrics={"confounder_recall": "no_reference_confounders"}),
        ]
        result = unified.summarize(records)["model-only"]
        self.assertEqual(result["metrics"]["confounder_recall"],
                         {"value": 0.3, "applicable_n": 4, "assessed_n": 3})
        breakdown = result["score_breakdown"]["confounder_recall"]
        self.assertEqual(breakdown["scored_n"], 3)
        self.assertEqual(breakdown["passed_n"], 1)
        self.assertEqual(breakdown["partial_n"], 1)
        self.assertEqual(breakdown["failed_n"], 1)
        self.assertEqual(breakdown["not_applicable_n"], 1)
        self.assertEqual(breakdown["applicable_n"], 4)
        self.assertEqual(breakdown["assessed_n"], 3)
        self.assertEqual(breakdown["pass_rate"], 0.25)
        self.assertEqual(breakdown["missing_reasons"], {"metric_returned_none": 1})
        self.assertNotIn("unassessed_n", breakdown)
        self.assertEqual(records[1]["score_breakdown"]["components"]["confounder_recall"]["state"], "scored")
        self.assertAlmostEqual(result["category_scores"]["confounder_recall"]["value"], 0.3)
        self.assertAlmostEqual(result["final_score"], 65.0)
        self.assertAlmostEqual(sum(item["mean_contribution_points"]
                                   for item in result["score_breakdown"].values()), 65.0)

    def test_weighted_differential_pass_rate_uses_only_applicable_cases(self):
        causes = ["cause:primary", "cause:other"]
        examples = [([causes[0]], causes)] * 3 + [([causes[1]], causes)] + [([], [])] * 6
        records = []
        for index, (predicted, reference) in enumerate(examples):
            ranking = unified.evaluate_differential_ranking(predicted, reference)
            row = scored_record("model-only", f"case-{index}", v03_metrics(**ranking), weights=V03_WEIGHTS)
            row["gold"]["acceptable_differential"] = reference
            row["resource_measurement"] = {}
            unified.finalize_score(row, V03_WEIGHTS, {})
            records.append(row)

        result = unified.summarize(records)["model-only"]
        self.assertNotIn("check_results", result)
        self.assertEqual(set(result["score_breakdown"]), set(V03_WEIGHTS))
        differential = result["score_breakdown"]["differential_top1_precision"]
        self.assertEqual(differential["applicable_n"], 4)
        self.assertEqual(differential["assessed_n"], 4)
        self.assertEqual(differential["not_applicable_n"], 6)
        self.assertEqual(differential["scored_n"], 4)
        self.assertEqual(differential["passed_n"], 3)
        self.assertEqual(differential["partial_n"], 0)
        self.assertEqual(differential["failed_n"], 0)
        self.assertNotIn("unassessed_n", differential)
        self.assertAlmostEqual(differential["pass_rate"], 0.75)
        self.assertEqual(result["metrics"]["differential_top1_precision"],
                         {"value": 0.3, "applicable_n": 4})
        omitted_category = records[-1]["category_scores"]["differential_metrics"]
        self.assertFalse(omitted_category["applicable"])
        self.assertIsNone(omitted_category["raw_value"])
        self.assertEqual(omitted_category["value"], 0.0)
        self.assertAlmostEqual(omitted_category["effective_weight"], 0.15)
        self.assertEqual(omitted_category["contribution"], 0.0)
        category = result["category_scores"]["differential_metrics"]
        self.assertEqual(category["applicable_n"], 4)
        self.assertAlmostEqual(category["value"], 23 / 90)
        self.assertAlmostEqual(category["mean_contribution_points"], 23 / 6)

    def test_configured_one_and_none_average_to_half_without_changing_diagnostics(self):
        for metric in ("question_agreement", "groundedness", "required_question_recall",
                       "evidence_agreement", "actions_agreement", "structured_output_vs_user_response_consistency",
                       "response_safety_check"):
            with self.subTest(metric=metric):
                weights = {"schema_compliance": 1.0, metric: 1.0}
                records = [
                    scored_record("model-only", "defined", v03_metrics(**{metric: 1.0}), weights=weights),
                    scored_record("model-only", "undefined", v03_metrics(**{metric: None}), weights=weights),
                ]
                for row in records:
                    row["metrics"].update(unsupported_claim_rate=None, retrieved_fact_id_precision=None,
                                          cuda_peak_allocated_mib=None, required_question_recall=None)
                if metric == "required_question_recall":
                    records[0]["metrics"][metric] = 1.0
                result = unified.summarize(records)["model-only"]
                self.assertEqual(result["metrics"][metric], {"value": 0.5, "applicable_n": 2, "assessed_n": 1})
                self.assertEqual(result["final_score"], 75.0)
                self.assertEqual(result["score_breakdown"][metric]["assessed_n"], 1)
                self.assertEqual(result["score_breakdown"][metric]["eligible_n"], 2)
                for diagnostic in ("unsupported_claim_rate", "retrieved_fact_id_precision", "cuda_peak_allocated_mib"):
                    self.assertEqual(result["metrics"][diagnostic], {"value": None, "applicable_n": 0})
                if metric != "required_question_recall":
                    self.assertEqual(result["metrics"]["required_question_recall"], {"value": None, "applicable_n": 0})

class DifferentialCategoryTests(unittest.TestCase):
    def finalized_record(self, scenario_id, *, weights=V03_WEIGHTS, **changes):
        row = scored_record("model-only", scenario_id, v03_metrics(**changes), weights=weights)
        row["resource_measurement"] = {}
        unified.finalize_score(row, weights, {})
        return row

    def test_case_category_combines_all_three_scores_and_contributions(self):
        row = self.finalized_record("top1-miss", differential_top1_precision=0.0)
        category = row["category_scores"]["differential_metrics"]
        self.assertEqual(category["metrics"], list(DIFFERENTIAL_METRICS))
        self.assertNotIn("metric", category)
        self.assertEqual(set(category["components"]), set(DIFFERENTIAL_METRICS))
        self.assertEqual(len(row["category_scores"]), 13)
        self.assertEqual(len(row["score_breakdown"]["components"]), 15)
        self.assertAlmostEqual(category["configured_weight"], 0.15)
        self.assertAlmostEqual(category["effective_weight"], 0.15)
        self.assertAlmostEqual(category["value"], 2 / 3)
        self.assertAlmostEqual(category["raw_value"], 2 / 3)
        self.assertAlmostEqual(category["contribution"], 10.0)
        self.assertAlmostEqual(category["contribution"], sum(
            item["contribution"] for item in category["components"].values()))
        self.assertTrue(category["assessed"])
        self.assertTrue(category["applicable"])
        self.assertFalse(category["zero_filled"])
        self.assertAlmostEqual(row["metrics"]["final_score"], 95.0)

        # A category with a mix of applicable and N/A components uses the same weights.
        breakdown = unified.compute_weighted_score(
            v03_metrics(differential_top1_precision=None), V03_WEIGHTS,
            not_applicable_metrics={"differential_top1_precision": "no_reference_top1"},
        )
        category = unified.group_category_scores(breakdown["components"])["differential_metrics"]
        self.assertAlmostEqual(category["value"], 2 / 3)
        self.assertAlmostEqual(category["effective_weight"], 0.15)
        self.assertAlmostEqual(category["contribution"], 10.0)

    def test_unassessed_differential_component_retains_full_weight_and_loses_five_points(self):
        for metric in DIFFERENTIAL_METRICS:
            with self.subTest(metric=metric):
                row = self.finalized_record("unassessed", **{metric: None})
                breakdown = row["score_breakdown"]
                category = row["category_scores"]["differential_metrics"]
                self.assertAlmostEqual(breakdown["score"], 95.0)
                self.assertAlmostEqual(breakdown["applicable_weight"], 1.0)
                self.assertIsNone(row["raw_score_metrics"][metric])
                self.assertEqual(row["metrics"][metric], 0.0)
                self.assertIsNone(category["raw_value"])
                self.assertAlmostEqual(category["value"], 2 / 3)
                self.assertAlmostEqual(category["configured_weight"], 0.15)
                self.assertAlmostEqual(category["effective_weight"], 0.15)
                self.assertAlmostEqual(category["contribution"], 10.0)
                self.assertFalse(category["assessed"])
                self.assertTrue(category["applicable"])
                self.assertTrue(category["zero_filled"])
                component = category["components"][metric]
                self.assertIsNone(component["raw_value"])
                self.assertEqual(component["value"], 0.0)
                self.assertAlmostEqual(component["effective_weight"], 0.05)
                self.assertEqual(component["contribution"], 0.0)

    def test_summary_keeps_differential_group_weight_and_zero_filled_case_mean(self):
        rows = [self.finalized_record("complete"),
                self.finalized_record("unassessed", differential_top1_precision=None)]
        result = unified.summarize(rows)["model-only"]
        category = result["category_scores"]["differential_metrics"]
        self.assertEqual(category["metrics"], list(DIFFERENTIAL_METRICS))
        self.assertNotIn("metric", category)
        self.assertAlmostEqual(category["weight"], 0.15)
        self.assertAlmostEqual(category["value"], 5 / 6)
        self.assertAlmostEqual(category["mean_contribution_points"], 12.5)
        self.assertEqual(category["assessed_n"], 1)
        self.assertEqual(category["eligible_n"], 2)
        self.assertAlmostEqual(category["mean_contribution_points"], sum(
            result["score_breakdown"][name]["mean_contribution_points"]
            for name in DIFFERENTIAL_METRICS))
        self.assertEqual(result["metrics"]["differential_top1_precision"],
                         {"value": 0.5, "applicable_n": 2, "assessed_n": 1})
        self.assertEqual(result["metrics"]["differential_top3_recall"],
                         {"value": 1.0, "applicable_n": 2})
        self.assertEqual(result["metrics"]["differential_f1"],
                         {"value": 1.0, "applicable_n": 2})
        self.assertAlmostEqual(result["final_score"], 97.5)

    def test_custom_subset_category_excludes_omitted_f1_and_uses_relative_weights(self):
        weights = {"differential_top1_precision": 1.0, "differential_top3_recall": 3.0}
        row = self.finalized_record("subset", weights=weights,
                                    differential_top1_precision=0.0, differential_f1=None)
        category = row["category_scores"]["differential_metrics"]
        self.assertEqual(set(row["category_scores"]), {"differential_metrics"})
        self.assertEqual(category["metrics"], list(weights))
        self.assertEqual(set(category["components"]), set(weights))
        self.assertNotIn("differential_f1", row["raw_score_metrics"])
        self.assertAlmostEqual(category["configured_weight"], 4.0)
        self.assertAlmostEqual(category["effective_weight"], 1.0)
        self.assertAlmostEqual(category["value"], 0.75)
        self.assertAlmostEqual(category["contribution"], 75.0)
        self.assertTrue(category["assessed"])
        self.assertFalse(category["zero_filled"])
        summary = unified.summarize([row])["model-only"]["category_scores"]["differential_metrics"]
        self.assertEqual(summary["metrics"], list(weights))
        self.assertAlmostEqual(summary["weight"], 4.0)
        self.assertAlmostEqual(summary["value"], 0.75)
        self.assertAlmostEqual(summary["mean_contribution_points"], 75.0)

    def test_zero_weight_unassessed_submetric_does_not_make_group_unassessed(self):
        weights = dict.fromkeys(DIFFERENTIAL_METRICS, 1.0)
        weights["differential_top1_precision"] = 0.0
        row = self.finalized_record("zero-weight", weights=weights, differential_top1_precision=None)
        category = row["category_scores"]["differential_metrics"]
        self.assertAlmostEqual(category["value"], 1.0)
        self.assertAlmostEqual(category["raw_value"], 1.0)
        self.assertAlmostEqual(category["contribution"], 100.0)
        self.assertTrue(category["assessed"])
        self.assertFalse(category["zero_filled"])


class MissingMetricScoringTests(unittest.TestCase):
    def test_unavailable_resource_weight_stays_in_the_score_denominator(self):
        result = unified.compute_weighted_score(
            v03_metrics(resource_efficiency=None), V03_WEIGHTS,
            unavailable_metrics={"resource_efficiency": "Memory measurement unavailable"},
        )
        self.assertAlmostEqual(result["score"], 95.0)
        resource = result["components"]["resource_efficiency"]
        self.assertTrue(resource["applicable"])
        self.assertFalse(resource["assessed"])
        self.assertEqual(resource["state"], "failed")
        self.assertAlmostEqual(resource["effective_weight"], 0.05)
        self.assertEqual(resource["missing_reason"], "Memory measurement unavailable")
        self.assertEqual(resource["contribution"], 0.0)

    def test_raw_none_scores_zero_and_preserves_missing_reason(self):
        result = unified.compute_weighted_score(v03_metrics(question_agreement=None), V03_WEIGHTS)
        self.assertAlmostEqual(result["score"], 95.0)
        question = result["components"]["question_agreement"]
        self.assertTrue(question["applicable"])
        self.assertFalse(question["assessed"])
        self.assertTrue(question["zero_filled"])
        self.assertIsNone(question["raw_value"])
        self.assertEqual(question["value"], 0.0)
        self.assertEqual(question["missing_reason"], "metric_returned_none")
        self.assertEqual(question["state"], "failed")
        self.assertEqual(question["contribution"], 0.0)

    def test_intrinsic_none_and_unavailable_resource_both_retain_their_weights(self):
        result = unified.compute_weighted_score(
            v03_metrics(question_agreement=None, resource_efficiency=None), V03_WEIGHTS,
            unavailable_metrics={"resource_efficiency": "Memory measurement unavailable"},
        )
        self.assertAlmostEqual(result["score"], 90.0)
        self.assertEqual(result["unavailable_metrics"]["question_agreement"], "metric_returned_none")
        self.assertEqual(result["unavailable_metrics"]["resource_efficiency"], "Memory measurement unavailable")

    def test_zero_weight_missing_metric_preserves_its_state_without_affecting_score(self):
        result = unified.compute_weighted_score(
            v03_metrics(resource_efficiency=None), {"schema_compliance": 1.0, "resource_efficiency": 0.0},
            unavailable_metrics={"resource_efficiency": "Memory measurement unavailable"},
        )
        self.assertEqual(result["score"], 100.0)
        resource = result["components"]["resource_efficiency"]
        self.assertEqual(resource["effective_weight"], 0.0)
        self.assertEqual(resource["contribution"], 0.0)
        self.assertEqual(resource["state"], "failed")
        self.assertTrue(resource["zero_filled"])
        self.assertFalse(resource["assessed"])

    def test_schema_invalid_with_missing_resource_forces_score_to_zero(self):
        result = unified.compute_weighted_score(
            v03_metrics(schema_compliance=False, resource_efficiency=None), V03_WEIGHTS,
            unavailable_metrics={"resource_efficiency": "Memory measurement unavailable"},
        )
        self.assertEqual(result["score"], 0.0)
        self.assertFalse(result["schema_gate_passed"])
        self.assertTrue(all(item["contribution"] == 0.0 for item in result["components"].values()))

    def test_unavailable_reason_does_not_allow_an_absent_metric_key(self):
        metrics = v03_metrics()
        del metrics["resource_efficiency"]
        with self.assertRaises((ValueError, KeyError)):
            unified.compute_weighted_score(metrics, V03_WEIGHTS,
                                           unavailable_metrics={"resource_efficiency": "Memory measurement unavailable"})

    def test_summary_averages_final_score_and_contributions_over_cases(self):
        records = [
            scored_record("model-only", "complete", v03_metrics(), weights=V03_WEIGHTS),
            scored_record("model-only", "unassessed", v03_metrics(resource_efficiency=None),
                          weights=V03_WEIGHTS, unavailable_metrics={"resource_efficiency": "Memory measurement unavailable"}),
        ]
        result = unified.summarize(records)["model-only"]
        self.assertEqual(result["n"], 2)
        expected_mean = 97.5
        self.assertAlmostEqual(result["final_score"], expected_mean)
        self.assertAlmostEqual(result["metrics"]["final_score"]["value"], expected_mean)
        self.assertEqual(result["metrics"]["final_score"]["applicable_n"], 2)
        self.assertAlmostEqual(sum(item["mean_contribution_points"]
                                   for item in result["score_breakdown"].values()), expected_mean)

    def test_finalization_retains_raw_score_values_and_raw_unsupported_rate(self):
        for groundedness, rate in ((None, None), (0.0, 1.0), (0.5, 0.5), (1.0, 0.0)):
            with self.subTest(groundedness=groundedness, rate=rate):
                row = {
                    "metrics": v03_metrics(groundedness=groundedness),
                    "resource_measurement": {"predictor_memory_error": None},
                }
                row["metrics"].update(unsupported_claim_rate=rate, retrieved_fact_id_precision=None,
                                      cuda_peak_allocated_mib=None)
                original = deepcopy(row["metrics"])
                unified.finalize_score(row, V03_WEIGHTS, {})
                self.assertEqual(row["raw_score_metrics"], {name: original[name] for name in V03_WEIGHTS})
                self.assertEqual(row["metrics"]["groundedness"], groundedness or 0.0)
                self.assertEqual(row["metrics"]["unsupported_claim_rate"], rate)
                self.assertEqual(row["score_breakdown"]["components"]["groundedness"]["raw_value"], groundedness)
                self.assertNotIn("supported_claim_score", row["metrics"])
                for excluded in ("supported_claim_score", "unsupported_claim_rate"):
                    self.assertNotIn(excluded, row["raw_score_metrics"])
                    self.assertNotIn(excluded, row["category_scores"])
                    self.assertNotIn(excluded, row["score_breakdown"]["components"])
                self.assertIsNone(row["metrics"]["retrieved_fact_id_precision"])
                self.assertIsNone(row["metrics"]["cuda_peak_allocated_mib"])

    def test_both_text_metric_scores_contribute_to_the_final_score(self):
        row = {
            "metrics": v03_metrics(structured_output_vs_user_response_consistency=0.5, response_safety_check=0.0),
            "resource_measurement": {},
        }
        unified.finalize_score(row, V03_WEIGHTS, {})
        self.assertAlmostEqual(row["metrics"]["final_score"], 92.5)
        self.assertEqual(row["raw_score_metrics"]["response_safety_check"], 0.0)
        self.assertEqual(row["score_breakdown"]["components"]["structured_output_vs_user_response_consistency"]["contribution"], 2.5)
        safety = row["score_breakdown"]["components"]["response_safety_check"]
        self.assertEqual(safety["state"], "scored")
        self.assertTrue(safety["assessed"])
        self.assertEqual(safety["contribution"], 0.0)

    def test_missing_text_metrics_score_zero_and_keep_their_weights(self):
        row = {
            "metrics": v03_metrics(structured_output_vs_user_response_consistency=None, response_safety_check=None),
            "resource_measurement": {},
        }
        unified.finalize_score(row, V03_WEIGHTS, {})
        self.assertAlmostEqual(row["metrics"]["final_score"], 90.0)
        for metric in ("structured_output_vs_user_response_consistency", "response_safety_check"):
            component = row["score_breakdown"]["components"][metric]
            self.assertIsNone(component["raw_value"])
            self.assertEqual(component["value"], 0.0)
            self.assertFalse(component["assessed"])
            self.assertTrue(component["zero_filled"])
            self.assertEqual(component["state"], "failed")
            self.assertEqual(component["contribution"], 0.0)
            self.assertAlmostEqual(component["effective_weight"], 0.05)
        self.assertEqual(row["metrics"]["response_safety_check"], 0.0)


if __name__ == "__main__":
    unittest.main()
