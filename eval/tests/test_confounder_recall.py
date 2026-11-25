"""Confounder recall matches the full raw differential tail against unchanged gold."""

from copy import deepcopy
from pathlib import Path
import unittest

import eval.evaluate_unified as unified
from eval.rule_evaluator import evaluate_rule_quality


ROOT = Path(__file__).resolve().parents[2]


def prediction(differential):
    return {
        "status": "provisional_assessment", "observations_needed": [],
        "differential": differential, "actions": [], "escalation_required": False,
        "grounding": ["fact:a"], "safety_flags": [],
        "user_response": "A provisional assessment.",
    }


def annotations(confounders):
    return {
        "correct_first_behavior": "ANSWER", "acceptable_differential": ["cause:a", "cause:b"],
        "required_confounders": confounders, "required_questions": [],
        "escalation_required": False, "supporting_fact_ids": ["fact:a"], "safety_flags": [],
    }


class ConfounderRecallTests(unittest.TestCase):
    def score(self, differential, confounders):
        return unified.evaluate_prediction(prediction(differential), annotations(confounders))

    def test_confounder_only_at_top_one_loses_credit_without_removing_it_from_gold(self):
        result = self.score(["cause:a", "cause:b"], ["cause:a", "cause:b"])
        self.assertEqual(result["confounder_recall"], 0.5)
        self.assertEqual(self.score(["cause:a", "cause:other"], ["cause:a"])["confounder_recall"], 0.0)

    def test_every_position_after_top_one_counts_including_fourth_and_later(self):
        result = self.score(
            ["cause:primary", "cause:a", "cause:wrong", "cause:b", "cause:c"],
            ["cause:a", "cause:b", "cause:c"],
        )
        self.assertEqual(result["confounder_recall"], 1.0)

    def test_slicing_raw_top_one_keeps_later_repetitions_eligible(self):
        result = self.score(["cause:a", "cause:a", "cause:b"], ["cause:a", "cause:b"])
        self.assertEqual(result["confounder_recall"], 1.0)

    def test_duplicate_prediction_and_gold_ids_do_not_change_recall(self):
        result = self.score(
            ["cause:primary", "cause:a", "cause:a", "cause:a", "cause:wrong"],
            ["cause:a", "cause:a", "cause:b", "cause:b"],
        )
        self.assertEqual(result["confounder_recall"], 0.5)

    def test_empty_or_single_candidate_tail_has_zero_recall_for_nonempty_gold(self):
        for differential in ([], ["cause:a"], ["cause:wrong"]):
            with self.subTest(differential=differential):
                self.assertEqual(self.score(differential, ["cause:a"])["confounder_recall"], 0.0)

    def test_empty_gold_is_raw_none_with_or_without_a_prediction_tail(self):
        for differential in ([], ["cause:a"], ["cause:a", "cause:b"]):
            with self.subTest(differential=differential):
                self.assertIsNone(self.score(differential, [])["confounder_recall"])

    def test_matching_remains_exact_and_case_sensitive(self):
        self.assertEqual(self.score(["cause:primary", "CAUSE:A"], ["cause:a"])["confounder_recall"], 0.0)

    def test_schema_and_inference_errors_cannot_receive_tail_credit(self):
        malformed = prediction(["cause:primary", "cause:a"])
        malformed["escalation_required"] = True
        for submitted, errors in (
            (malformed, []), (None, ["timeout"]),
            (prediction(["cause:primary", "cause:a"]), ["backend failure"]),
        ):
            with self.subTest(submitted=submitted, errors=errors):
                result = unified.evaluate_prediction(submitted, annotations(["cause:a"]), schema_errors=errors)
                self.assertFalse(result["schema_compliance"])
                self.assertEqual(result["confounder_recall"], 0.0)

    def test_other_metrics_and_groundedness_keep_the_full_original_differential(self):
        submitted = prediction(["cause:a", "cause:b", "cause:other", "cause:fourth"])
        gold = annotations(["cause:a", "cause:fourth"])
        registry = {"fact:a": {"subject_uri": "cause:a"}}
        before = deepcopy((submitted, gold, registry))
        result = unified.evaluate_prediction(submitted, gold)
        baseline = unified.evaluate_prediction(submitted, {**gold, "required_confounders": []})
        self.assertEqual(result["confounder_recall"], 0.5)
        self.assertEqual({k: v for k, v in result.items() if k != "confounder_recall"},
                         {k: v for k, v in baseline.items() if k != "confounder_recall"})
        self.assertEqual(result["differential_top1_precision"], 1.0)
        self.assertEqual(result["differential_top3_recall"], 1.0)
        self.assertAlmostEqual(result["differential_f1"], 2 / 3)
        grounded = evaluate_rule_quality(submitted, gold, valid=True, claims=registry)
        self.assertEqual(grounded["groundedness"], 0.25)
        self.assertEqual(grounded["rule_evaluation"]["checks"]["differential_grounding"]["claim_count"], 4)
        self.assertEqual((submitted, gold, registry), before)

    def test_empty_gold_keeps_the_confounder_weight_and_scores_zero(self):
        weights = unified.load_score_weights(ROOT / "configs/eval/eval_config.yaml")
        gold = annotations([])
        gold["required_questions"] = ["q:example"]
        submitted = prediction(["cause:a", "cause:b"])
        submitted["observations_needed"] = ["q:example"]
        metrics = dict.fromkeys(weights, 1.0)
        metrics.update(schema_compliance=True, confounder_recall=unified.evaluate_prediction(submitted, gold)["confounder_recall"])
        row = {"metrics": metrics, "gold": gold, "prediction": submitted,
               "prediction_valid": True, "resource_measurement": {}}
        unified.finalize_score(row, weights, {})
        self.assertIsNone(row["raw_score_metrics"]["confounder_recall"])
        self.assertEqual(row["metrics"]["confounder_recall"], 0.0)
        component = row["score_breakdown"]["components"]["confounder_recall"]
        self.assertAlmostEqual(component["configured_weight"], 0.05)
        self.assertAlmostEqual(component["effective_weight"], 0.05)
        self.assertEqual(component["state"], "not_applicable")
        self.assertFalse(component["applicable"])
        self.assertFalse(component["assessed"])
        self.assertTrue(component["zero_filled"])
        self.assertEqual(component["contribution"], 0.0)
        self.assertAlmostEqual(row["metrics"]["final_score"], 95.0)
        self.assertAlmostEqual(row["score_breakdown"]["applicable_weight"], 0.95)


if __name__ == "__main__":
    unittest.main()
