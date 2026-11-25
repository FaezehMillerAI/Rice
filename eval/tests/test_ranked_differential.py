"""Top-1 precision, raw-position top-3 recall, and full-set F1 stay separate."""

from copy import deepcopy
import unittest

from eval.evaluate_unified import evaluate_prediction, set_scores


METRICS = ("differential_top1_precision", "differential_top3_recall", "differential_f1")


def prediction(differential):
    return {
        "status": "provisional_assessment", "observations_needed": [],
        "differential": differential, "actions": [], "escalation_required": False,
        "grounding": [], "safety_flags": [], "user_response": "A provisional assessment.",
    }


def annotations(acceptable=("cause:a", "cause:b", "cause:c")):
    return {
        "correct_first_behavior": "ANSWER", "acceptable_differential": list(acceptable),
        "required_confounders": [], "required_questions": [], "escalation_required": False,
        "supporting_fact_ids": [], "safety_flags": [],
    }


def score(differential, acceptable=("cause:a", "cause:b", "cause:c")):
    return evaluate_prediction(prediction(differential), annotations(acceptable))


class RankedDifferentialTests(unittest.TestCase):
    def assert_metrics(self, result, precision, recall, f1):
        for name, expected in zip(METRICS, (precision, recall, f1)):
            if expected is None:
                self.assertIsNone(result[name])
            else:
                self.assertAlmostEqual(result[name], expected)

    def test_first_position_controls_precision_even_when_top_three_set_is_unchanged(self):
        first_correct = score(["cause:a", "cause:wrong", "cause:other"])
        first_wrong = score(["cause:wrong", "cause:a", "cause:other"])
        self.assert_metrics(first_correct, 1.0, 1 / 3, 1 / 3)
        self.assert_metrics(first_wrong, 0.0, 1 / 3, 1 / 3)

    def test_all_three_gold_causes_do_not_give_precision_credit_to_wrong_primary(self):
        self.assert_metrics(score(["cause:c", "cause:a", "cause:b"]), 0.0, 1.0, 1.0)

    def test_secondary_gold_cause_at_rank_one_is_not_a_correct_primary(self):
        self.assert_metrics(score(["cause:b", "cause:a", "cause:c"]), 0.0, 1.0, 1.0)

    def test_reordering_gold_changes_primary_accuracy_but_not_top_three_recall(self):
        differential = ["cause:a", "cause:b", "cause:c"]
        ordered = score(differential, ["cause:a", "cause:b", "cause:c"])
        reordered = score(differential, ["cause:c", "cause:b", "cause:a"])
        self.assert_metrics(ordered, 1.0, 1.0, 1.0)
        self.assert_metrics(reordered, 0.0, 1.0, 1.0)

    def test_primary_reference_uses_original_order_instead_of_sorted_or_unique_order(self):
        acceptable = ["cause:z", "cause:a", "cause:b", "cause:z"]
        result = score(["cause:z", "cause:a", "cause:b"], acceptable)
        self.assert_metrics(result, 1.0, 1.0, 1.0)
        trace = result["differential_ranking"]
        self.assertEqual(trace["reference_top1_ids"], ["cause:z"])
        self.assertEqual(trace["reference_ranked_ids"], acceptable)
        self.assertEqual(trace["reference_ids"], ["cause:a", "cause:b", "cause:z"])
        self.assert_metrics(score(["cause:a", "cause:z", "cause:b"], acceptable), 0.0, 1.0, 1.0)

    def test_correct_fourth_candidate_improves_full_set_f1_without_top_three_recall(self):
        result = score(["cause:wrong", "cause:other", "cause:unrelated", "cause:a"], ["cause:a"])
        self.assert_metrics(result, 0.0, 0.0, 0.4)

    def test_wrong_tail_candidates_reduce_full_set_f1_only(self):
        baseline = score(["cause:a", "cause:b", "cause:c"])
        longer = score(["cause:a", "cause:b", "cause:c", "cause:wrong", "cause:other"])
        for name in METRICS[:2]:
            self.assertEqual(longer[name], baseline[name])
        self.assert_metrics(baseline, 1.0, 1.0, 1.0)
        self.assert_metrics(longer, 1.0, 1.0, 0.75)

    def test_full_set_f1_deduplicates_prediction_and_gold_across_all_positions(self):
        acceptable = ["cause:a", "cause:a", "cause:b"]
        baseline = score(["cause:a", "cause:b", "cause:wrong"], acceptable)
        duplicated = score(["cause:a", "cause:a", "cause:wrong", "cause:b", "cause:b", "cause:wrong"], acceptable)
        self.assertEqual(baseline["differential_f1"], 0.8)
        self.assertEqual(duplicated["differential_f1"], baseline["differential_f1"])
        self.assertEqual(duplicated["differential_top3_recall"], 0.5)
        self.assertEqual(duplicated["differential_ranking"]["full_unique_count"], 3)

    def test_duplicates_consume_raw_top_three_positions(self):
        result = score(["cause:a", "cause:a", "cause:a", "cause:b"], ["cause:a", "cause:b"])
        self.assert_metrics(result, 1.0, 0.5, 1.0)

    def test_deduplication_does_not_promote_fourth_distinct_cause(self):
        result = score(["cause:a", "cause:b", "cause:b", "cause:c"])
        self.assert_metrics(result, 1.0, 2 / 3, 1.0)

    def test_ranking_trace_keeps_raw_positions_and_explains_the_cutoffs(self):
        result = score(["cause:b", "cause:b", "cause:wrong", "cause:a", "cause:c"])
        trace = result["differential_ranking"]
        self.assertEqual(trace["precision_cutoff"], 1)
        self.assertEqual(trace["recall_cutoff"], 3)
        self.assertEqual(trace["top1_ids"], ["cause:b"])
        self.assertEqual(trace["top3_ids"], ["cause:b", "cause:b", "cause:wrong"])
        self.assertEqual(trace["top3_hit_ids"], ["cause:b"])
        self.assertEqual(trace["full_hit_ids"], ["cause:a", "cause:b", "cause:c"])
        self.assertEqual(trace["full_unique_count"], 4)
        self.assertEqual(trace["reference_ids"], ["cause:a", "cause:b", "cause:c"])
        self.assertEqual(trace["reference_top1_ids"], ["cause:a"])
        self.assertEqual(trace["reference_ranked_ids"], ["cause:a", "cause:b", "cause:c"])
        self.assertEqual(trace["candidate_count"], 5)
        self.assertEqual(trace["ignored_tail_count"], 2)
        self.assertEqual(trace["tail_count_scope"], "top3_recall_only; all positions enter full-set F1")
        self.assertEqual(trace["duplicate_top3_count"], 1)
        self.assertEqual(trace["cutoff_policy"], "slice_raw_positions_before_deduplicating_hits")
        self.assertEqual(trace["f1_definition"], "full_differential_set_f1")

    def test_duplicate_gold_ids_do_not_enlarge_the_reference_denominator(self):
        result = score(["cause:a", "cause:b"], ["cause:a", "cause:a", "cause:b"])
        self.assert_metrics(result, 1.0, 1.0, 1.0)

    def test_short_or_empty_prediction_uses_available_positions_only(self):
        examples = (([], 0.0, 0.0, 0.0), (["cause:a"], 1.0, 1 / 3, 0.5),
                    (["cause:a", "cause:b"], 1.0, 2 / 3, 0.8))
        for differential, precision, recall, f1 in examples:
            with self.subTest(differential=differential):
                self.assert_metrics(score(differential), precision, recall, f1)

    def test_empty_gold_makes_all_three_raw_metrics_unassessed(self):
        for differential in ([], ["cause:a"], ["cause:wrong", "cause:a"]):
            with self.subTest(differential=differential):
                self.assert_metrics(score(differential, []), None, None, None)

    def test_gold_with_more_than_three_causes_can_have_at_most_three_recall_hits(self):
        result = score(["cause:a", "cause:b", "cause:c", "cause:d"],
                       ["cause:a", "cause:b", "cause:c", "cause:d"])
        self.assert_metrics(result, 1.0, 0.75, 1.0)

    def test_top_three_cutoff_does_not_truncate_confounder_or_registry_diagnostics(self):
        differential = ["cause:a", "cause:wrong", "cause:other", "cause:b"]
        submitted = prediction(differential)
        gold = annotations(["cause:a", "cause:b"])
        gold["required_confounders"] = ["cause:b"]
        before = deepcopy((submitted, gold))
        result = evaluate_prediction(submitted, gold, claims={"causes": {"cause:a": {}}})
        self.assert_metrics(result, 1.0, 0.5, 2 / 3)
        self.assertEqual(result["confounder_recall"], 1.0)
        self.assertIn("cause:b", result["cause_ids_absent_from_registry"])
        self.assertEqual((submitted, gold), before)
        self.assertEqual(submitted["differential"], differential)

    def test_matching_is_exact_and_case_sensitive(self):
        result = score(["CAUSE:A", "cause:a"], ["cause:a"])
        self.assert_metrics(result, 0.0, 1.0, 2 / 3)

    def test_schema_or_backend_failure_cannot_receive_ranked_credit(self):
        malformed = prediction(["cause:a", "cause:b", "cause:c"])
        malformed["escalation_required"] = True
        for submitted, errors in ((malformed, []), (None, ["timeout"]),
                                  (prediction(["cause:a", "cause:b", "cause:c"]), ["backend failure"])):
            with self.subTest(submitted=submitted, errors=errors):
                result = evaluate_prediction(submitted, annotations(), schema_errors=errors)
                self.assertFalse(result["schema_compliance"])
                self.assert_metrics(result, 0.0, 0.0, 0.0)

    def test_shared_unranked_set_score_helper_keeps_its_original_contract(self):
        self.assertEqual(set_scores(["cause:a", "cause:wrong"], ["cause:a", "cause:b"]),
                         (0.5, 0.5, 0.5))
        self.assert_metrics(score(["cause:a", "cause:wrong"], ["cause:a", "cause:b"]),
                            1.0, 0.5, 0.5)


if __name__ == "__main__":
    unittest.main()
