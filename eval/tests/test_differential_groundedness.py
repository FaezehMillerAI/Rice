"""Grounding IDs support differential claims through exact registry subjects."""

from copy import deepcopy
import csv
import json
from pathlib import Path
import unittest

import eval.evaluate_unified as unified
from eval.rule_evaluator import evaluate_rule_quality


ROOT = Path(__file__).resolve().parents[2]
GOLD = {
    "correct_first_behavior": "ANSWER",
    "required_questions": [],
    "acceptable_differential": ["cause:a", "cause:b"],
    "supporting_fact_ids": ["fact:a", "fact:b"],
    "safety_flags": [],
}
REGISTRY = {
    "fact:a": {
        "subject_uri": "cause:a", "predicate_uri": "rice:presentsAs",
        "object_uri": "symptom:a",
    },
    "fact:b": {
        "subject_uri": "cause:b", "predicate_uri": "rice:hasSign",
        "object_uri": "sign:b",
    },
}


def response(**changes):
    result = {
        "differential": ["cause:a", "cause:b", "cause:c"],
        "observations_needed": [], "grounding": ["fact:a", "fact:b"], "actions": [],
        "safety_flags": [], "user_response": "A provisional assessment.",
    }
    result.update(changes)
    return result


def evaluate(prediction=None, annotations=None, registry=REGISTRY, *, valid=True):
    return evaluate_rule_quality(
        response() if prediction is None else prediction,
        GOLD if annotations is None else annotations,
        valid=valid, claims=registry,
    )


def check(result):
    return result["rule_evaluation"]["checks"]["differential_grounding"]


class DifferentialGroundednessTests(unittest.TestCase):
    def test_score_counts_supported_differential_claims_and_explains_each_match(self):
        result = evaluate()
        self.assertAlmostEqual(result["groundedness"], 2 / 3)
        self.assertAlmostEqual(result["unsupported_claim_rate"], 1 / 3)
        self.assertAlmostEqual(result["groundedness"] + result["unsupported_claim_rate"], 1.0)
        self.assertNotIn("supported_claim_score", result)
        detail = check(result)
        self.assertNotIn("structured_gold_support", result["rule_evaluation"]["checks"])
        self.assertEqual(detail["claim_count"], 3)
        self.assertEqual(detail["supported_claim_count"], 2)
        self.assertEqual(detail["claim_ids"], ["cause:a", "cause:b", "cause:c"])
        self.assertEqual(detail["supported_claim_ids"], ["cause:a", "cause:b"])
        self.assertEqual(detail["unsupported_claim_ids"], ["cause:c"])
        self.assertEqual(detail["supporting_fact_ids_by_claim"], {
            "cause:a": ["fact:a"], "cause:b": ["fact:b"], "cause:c": [],
        })
        self.assertEqual(detail["grounding_fact_ids"], ["fact:a", "fact:b"])
        self.assertTrue(detail["uses_predicted_grounding"])
        self.assertEqual(detail["matching_rule"], "subject_uri_equals_differential_id")
        self.assertNotIn("reference_fact_ids", detail)
        self.assertNotIn("support_predicates", detail)
        self.assertTrue(detail["registry_available"])
        self.assertIsNone(detail["unassessed_reason"])

    def test_duplicate_claims_and_facts_do_not_change_coverage(self):
        result = evaluate(
            response(differential=["cause:c", "cause:a", "cause:a", "cause:b"],
                     grounding=["fact:b", "fact:a", "fact:a"]),
        )
        self.assertAlmostEqual(result["groundedness"], 2 / 3)
        self.assertAlmostEqual(result["unsupported_claim_rate"], 1 / 3)
        self.assertEqual(check(result)["claim_count"], 3)
        self.assertEqual(check(result)["supported_claim_count"], 2)

    def test_multiple_facts_for_one_cause_cannot_cover_another_cause(self):
        registry = {
            "fact:a": REGISTRY["fact:a"],
            "fact:a-extra": {
                "subject_uri": "cause:a", "predicate_uri": "rice:favoredBy",
                "object_uri": "env:rain",
            },
        }
        result = evaluate(
            response(differential=["cause:a", "cause:b"], grounding=["fact:a", "fact:a-extra"]),
            registry=registry,
        )
        self.assertEqual(result["groundedness"], 0.5)
        self.assertEqual(result["unsupported_claim_rate"], 0.5)
        self.assertEqual(check(result)["supporting_fact_ids_by_claim"]["cause:a"],
                         ["fact:a", "fact:a-extra"])

    def test_any_matching_citation_supports_a_claim_regardless_of_unrelated_citation_order(self):
        for grounding in (["fact:a", "fact:b"], ["fact:b", "fact:a"]):
            with self.subTest(grounding=grounding):
                result = evaluate(response(differential=["cause:a"], grounding=grounding))
                self.assertEqual(result["groundedness"], 1.0)
                self.assertEqual(result["unsupported_claim_rate"], 0.0)
                self.assertEqual(check(result)["supporting_fact_ids_by_claim"], {"cause:a": ["fact:a"]})

    def test_only_subject_uri_is_required_for_fact_support(self):
        result = evaluate(
            response(differential=["cause:a"], grounding=["fact:a"]),
            registry={"fact:a": {"subject_uri": "cause:a"}},
        )
        self.assertEqual(result["groundedness"], 1.0)
        self.assertEqual(check(result)["supporting_fact_ids_by_claim"], {"cause:a": ["fact:a"]})

    def test_predicate_and_object_fields_do_not_change_a_subject_match(self):
        records = (
            {"subject_uri": "cause:a", "predicate_uri": "rice:presentsAs", "object_uri": "symptom:a"},
            {"subject_uri": "cause:a", "predicate_uri": "rice:contradicts"},
            {"subject_uri": "cause:a", "predicate_uri": "rice:managedBy", "object_uri": "action:a"},
            {"subject_uri": "cause:a", "predicate_uri": "rice:unknown", "object_uri": ""},
            {"subject_uri": "cause:a", "predicate_uri": [], "object_uri": None},
        )
        for record in records:
            with self.subTest(record=record):
                result = evaluate(response(differential=["cause:a"], grounding=["fact:a"]),
                                  registry={"fact:a": record})
                self.assertEqual(result["groundedness"], 1.0)
                self.assertEqual(check(result)["rejected_grounding_facts"], {})

    def test_disease_in_object_position_is_not_a_subject_match(self):
        registry = {"fact:a": {
            "subject_uri": "cause:other", "predicate_uri": "rice:presentsAs",
            "object_uri": "cause:a",
        }}
        result = evaluate(response(differential=["cause:a"]), registry=registry)
        self.assertEqual(result["groundedness"], 0.0)
        self.assertEqual(check(result)["supporting_fact_ids_by_claim"]["cause:a"], [])

    def test_matching_is_exact_and_does_not_guess_from_fact_id_names(self):
        registry = {"fact:looks_like_cause_b": REGISTRY["fact:a"]}
        result = evaluate(
            response(differential=["cause:a", "cause:b", "CAUSE:A"],
                     grounding=["fact:looks_like_cause_b"]),
            registry=registry,
        )
        self.assertAlmostEqual(result["groundedness"], 1 / 3)
        self.assertEqual(check(result)["supported_claim_ids"], ["cause:a"])

    def test_unknown_grounding_fact_is_reported_and_never_infers_a_cause(self):
        result = evaluate(
            response(differential=["cause:a", "cause:b"], grounding=["fact:a", "fact:missing"]),
        )
        self.assertEqual(result["groundedness"], 0.5)
        self.assertEqual(check(result)["unknown_grounding_fact_ids"], ["fact:missing"])

    def test_facts_outside_gold_support_when_model_cites_a_matching_subject(self):
        result = evaluate(
            response(differential=["cause:b"], grounding=["fact:b"]),
            {**GOLD, "supporting_fact_ids": ["fact:a"]},
        )
        self.assertEqual(result["groundedness"], 1.0)
        self.assertEqual(result["unsupported_claim_rate"], 0.0)
        self.assertEqual(check(result)["supported_claim_ids"], ["cause:b"])
        self.assertEqual(result["evidence_agreement"], 0.0)

    def test_gold_support_facts_and_cause_labels_do_not_replace_model_citation_matching(self):
        for gold_facts in ([], ["fact:a"], ["fact:b"], ["fact:fictional"]):
            with self.subTest(gold_facts=gold_facts):
                result = evaluate(
                    response(differential=["cause:a"], grounding=["fact:a"]),
                    {**GOLD, "acceptable_differential": [], "supporting_fact_ids": gold_facts},
                )
                self.assertEqual(result["groundedness"], 1.0)
                self.assertEqual(result["unsupported_claim_rate"], 0.0)
        result = evaluate(
            response(differential=["cause:c"], grounding=["fact:a", "fact:b"]),
            {**GOLD, "acceptable_differential": ["cause:c"]},
        )
        self.assertEqual(result["groundedness"], 0.0)
        self.assertEqual(result["unsupported_claim_rate"], 1.0)
        self.assertEqual(result["evidence_agreement"], 1.0)

    def test_invalid_records_or_missing_subjects_do_not_support_claims(self):
        records = (None, "cause:a", {},
                   {"predicate_uri": "rice:presentsAs", "object_uri": "cause:a"},
                   {"subject_uri": ""}, {"subject_uri": " \t"},
                   {"subject_uri": None}, {"subject_uri": []})
        for record in records:
            with self.subTest(record=record):
                result = evaluate(response(differential=["cause:a"]), registry={"fact:a": record})
                self.assertEqual(result["groundedness"], 0.0)
                self.assertIn("fact:a", check(result)["rejected_grounding_facts"])

    def test_empty_differential_is_unassessed_instead_of_receiving_free_points(self):
        result = evaluate(response(differential=[]))
        self.assertIsNone(result["groundedness"])
        self.assertIsNone(result["unsupported_claim_rate"])
        self.assertEqual(check(result)["claim_count"], 0)
        self.assertEqual(check(result)["supported_claim_count"], 0)
        self.assertIsNotNone(check(result)["unassessed_reason"])

    def test_empty_model_grounding_scores_zero_with_or_without_registry(self):
        for registry in (REGISTRY, {}, None):
            with self.subTest(registry=registry):
                result = evaluate(response(grounding=[]), registry=registry)
                self.assertEqual(result["groundedness"], 0.0)
                self.assertEqual(result["unsupported_claim_rate"], 1.0)

    def test_missing_registry_is_unassessed_when_model_grounding_needs_resolving(self):
        for registry in (None, {}, {"claims": {}}, {"facts": {}}):
            with self.subTest(registry=registry):
                result = evaluate(registry=registry)
                self.assertIsNone(result["groundedness"])
                self.assertIsNone(result["unsupported_claim_rate"])
                self.assertFalse(check(result)["registry_available"])
                self.assertIsNotNone(check(result)["unassessed_reason"])
                self.assertIsNone(check(result)["unsupported_claim_ids"])
                self.assertEqual(check(result)["unassessed_claim_ids"], ["cause:a", "cause:b", "cause:c"])

    def test_flat_and_wrapped_provenance_registries_have_identical_scores(self):
        for registry in (REGISTRY, {"claims": REGISTRY}, {"facts": REGISTRY}):
            with self.subTest(registry=registry):
                result = evaluate(registry=registry)
                self.assertAlmostEqual(result["groundedness"], 2 / 3)
                self.assertEqual(check(result)["supported_claim_ids"], ["cause:a", "cause:b"])

    def test_invalid_prediction_cannot_get_groundedness_points(self):
        for prediction in (response(), {}):
            with self.subTest(prediction=prediction):
                result = evaluate(prediction, valid=False)
                self.assertEqual(result["groundedness"], 0.0)
                self.assertIsNone(result["unsupported_claim_rate"])
                self.assertEqual(check(result)["claim_count"], 0)
                self.assertEqual(check(result)["supported_claim_count"], 0)
        result = evaluate_rule_quality(None, GOLD, valid=True, claims=REGISTRY)
        self.assertEqual(result["groundedness"], 0.0)
        self.assertIsNone(result["unsupported_claim_rate"])

    def test_evaluation_does_not_mutate_inputs_or_reuse_their_lists_in_trace(self):
        prediction, gold, registry = deepcopy((response(), GOLD, REGISTRY))
        before = deepcopy((prediction, gold, registry))
        result = evaluate(prediction, gold, registry)
        self.assertEqual((prediction, gold, registry), before)
        detail = check(result)
        detail["claim_ids"].append("cause:changed")
        detail["grounding_fact_ids"].clear()
        detail["supporting_fact_ids_by_claim"]["cause:a"].clear()
        self.assertEqual((prediction, gold, registry), before)


class RealRegistryGroundednessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (unified.ROOT / "registry/provenance-claims-registry.csv").open(encoding="utf-8-sig", newline="") as stream:
            cls.registry = {row["claim_id"]: row for row in csv.DictReader(stream)}
        cls.cases = json.loads((ROOT / "data/eval/gold_eval_v0.3.json").read_text(encoding="utf-8"))

    def score_case_reference(self, case, *, grounding=None, gold_facts=None):
        annotations = deepcopy(case["annotations"])
        annotations["safety_flags"] = case["target_response"]["safety_flags"]
        if gold_facts is not None:
            annotations["supporting_fact_ids"] = gold_facts
        prediction = deepcopy(case["target_response"])
        if grounding is not None:
            prediction["grounding"] = grounding
        return evaluate(prediction, annotations, self.registry)

    def test_first_real_case_all_three_differential_claims_have_matching_model_citations(self):
        result = self.score_case_reference(self.cases[0])
        self.assertEqual(result["groundedness"], 1.0)
        self.assertEqual(result["unsupported_claim_rate"], 0.0)
        self.assertEqual(check(result)["claim_count"], 3)
        self.assertEqual(check(result)["supported_claim_count"], 3)
        self.assertEqual(result["evidence_agreement"], 1.0)
        self.assertEqual(check(result)["supporting_fact_ids_by_claim"]["disorder:water_stress"],
                         ["claim:claim_wstress_001"])

    def test_real_kg_style_two_citations_support_two_of_three_differential_claims(self):
        result = self.score_case_reference(
            self.cases[0], grounding=["claim:claim_blb_001", "claim:claim_ndef_001"],
        )
        self.assertAlmostEqual(result["groundedness"], 2 / 3)
        self.assertAlmostEqual(result["unsupported_claim_rate"], 1 / 3)
        self.assertEqual(check(result)["unsupported_claim_ids"], ["disorder:water_stress"])

    def test_real_gold_fact_selection_does_not_change_model_groundedness(self):
        for gold_facts in ([], ["claim:claim_bspot_001"], ["claim:unavailable"]):
            with self.subTest(gold_facts=gold_facts):
                result = self.score_case_reference(self.cases[0], gold_facts=gold_facts)
                self.assertEqual(result["groundedness"], 1.0)
                self.assertEqual(result["unsupported_claim_rate"], 0.0)

    def test_real_case_empty_model_citations_cannot_borrow_gold_evidence(self):
        result = self.score_case_reference(self.cases[0], grounding=[])
        self.assertEqual(result["groundedness"], 0.0)
        self.assertEqual(result["unsupported_claim_rate"], 1.0)
        self.assertEqual(check(result)["supported_claim_ids"], [])

    def test_case_rules_resolve_new_fact_ids_from_the_retrieved_context(self):
        kg = unified.KGAdapter()
        case = self.cases[0]
        public = unified.select_public_case(case)
        fact = {
            "claim_id": "test:retrieved_fact_outside_registry",
            "subject_uri": case["target_response"]["differential"][0],
        }
        context = {"retrieved_facts": [fact]}
        prediction = {
            **case["target_response"],
            "differential": [fact["subject_uri"]],
            "grounding": [fact["claim_id"]],
        }
        for retrieved_context, expected in ((context, 1.0), (None, 0.0)):
            with self.subTest(has_context=retrieved_context is not None):
                row = {
                    "gold": unified.scoring_annotations(case),
                    "prediction": prediction,
                    "prediction_valid": True,
                    "public_input": public,
                    "retrieved_context": retrieved_context,
                    "metrics": {},
                }
                unified.evaluate_case_rules(row, kg, kg.catalog["causes"], {})
                self.assertEqual(row["metrics"]["groundedness"], expected)
        self.assertNotIn(fact["claim_id"], kg.catalog["claims"])

    def test_mismatched_model_fact_does_not_silently_use_registrywide_facts(self):
        case = next(case for case in self.cases if case["scenario_id"] == "case-diff-blb-001")
        result = self.score_case_reference(case)
        self.assertEqual(case["annotations"]["supporting_fact_ids"], ["claim:claim_wstress_001"])
        self.assertEqual(result["groundedness"], 0.0)
        self.assertEqual(check(result)["supported_claim_ids"], [])


if __name__ == "__main__":
    unittest.main()
