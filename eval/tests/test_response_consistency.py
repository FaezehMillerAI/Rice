"""Finite English consistency checks, including negation and summary omissions."""

from copy import deepcopy
import csv
import inspect
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from eval.evaluate_unified import ROOT
from engine.diagnostic_engine import DiagnosticEngine
from engine.retriever import to_compact_target_response
from eval.response_consistency import build_action_catalog, evaluate_response_consistency


BLB = "disease:bacterial_leaf_blight"
NDEF = "disorder:nitrogen_deficiency"


def prediction(**changes):
    result = {
        "status": "needs_more_information", "differential": [BLB],
        "observations_needed": ["q:q_lesion_margin"], "actions": [],
        "escalation_required": False, "grounding": [], "safety_flags": [],
        "user_response": "Please check whether the leaf lesions have wavy edges.",
    }
    result.update(changes)
    return result


class ResponseConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = DiagnosticEngine(str(ROOT))
        with (ROOT / "registry/disease-registry.csv").open(encoding="utf-8-sig", newline="") as stream:
            cls.causes = {row["id"]: row for row in csv.DictReader(stream)}
        cls.catalog = build_action_catalog(cls.engine)

    def evaluate(self, response=None, **kwargs):
        return evaluate_response_consistency(
            prediction() if response is None else response, valid=kwargs.pop("valid", True),
            causes=kwargs.pop("causes", self.causes), questions=kwargs.pop("questions", self.engine.questions),
            action_catalog=kwargs.pop("action_catalog", self.catalog), **kwargs,
        )

    def dimension(self, response, name, **kwargs):
        return self.evaluate(response, **kwargs)["response_consistency"]["checks"][name]

    def answer(self, text, **kwargs):
        return prediction(status="provisional_assessment", observations_needed=[], user_response=text, **kwargs)

    def escalate(self, text):
        return prediction(status="escalation_required", escalation_required=True, observations_needed=[], user_response=text)

    def test_real_kg_ask_can_omit_all_management_actions(self):
        raw = self.engine.diagnose("The leaves are yellow.")
        response = to_compact_target_response(raw)
        self.assertEqual(response["status"], "needs_more_information")
        self.assertTrue(response["actions"])
        result = self.evaluate(response)
        self.assertEqual(result["structured_output_vs_user_response_consistency"], 1.0)
        self.assertFalse(result["response_consistency"]["checks"]["actions"]["applicable"])

    def test_answer_requires_first_candidate_and_first_action_not_every_array_item(self):
        first = self.catalog["action:avoid_excess_nitrogen"][0]
        response = self.answer(
            f"Bacterial leaf blight is a possible cause. This is provisional. {first}",
            differential=[BLB, NDEF], actions=["action:avoid_excess_nitrogen", "action:ensure_field_drainage"],
        )
        self.assertEqual(self.evaluate(response)["structured_output_vs_user_response_consistency"], 1.0)

    def test_ask_may_omit_candidates_but_answer_must_mention_the_first_candidate(self):
        for candidates in ([], [BLB]):
            with self.subTest(ask_candidates=candidates):
                check = self.dimension(prediction(differential=candidates), "differential")
                self.assertFalse(check["applicable"])
                self.assertIsNone(check["score"])
                self.assertEqual(check["state"], "not_applicable")

        answer = self.answer("This is a provisional assessment.", differential=[BLB], actions=[])
        result = self.evaluate(answer)
        checks = result["response_consistency"]["checks"]
        diagnosis = checks["differential"]
        self.assertTrue(diagnosis["applicable"])
        self.assertEqual(diagnosis["score"], 0.0)
        self.assertEqual(diagnosis["state"], "failed")
        self.assertEqual(diagnosis["reason"], "missing_first_candidate")
        self.assertEqual(checks["actions"]["state"], "not_applicable")
        self.assertAlmostEqual(result["structured_output_vs_user_response_consistency"], 2 / 3)

    def test_real_kg_escalation_needs_no_candidate_list_in_user_text(self):
        raw = self.engine.diagnose("Panicle neck rot is destroying the crop.")
        response = to_compact_target_response(raw)
        self.assertTrue(response["differential"])
        result = self.evaluate(response)
        self.assertEqual(result["structured_output_vs_user_response_consistency"], 1.0)
        self.assertFalse(result["response_consistency"]["checks"]["differential"]["applicable"])

    def test_generic_request_or_question_mark_does_not_cover_specific_questions(self):
        for text in ("Please provide more details.", "Hello?", "The leaf lesions have wavy edges. Please provide details."):
            with self.subTest(text=text):
                response = prediction(user_response=text)
                check = self.dimension(response, "questions")
                self.assertEqual(check["score"], 0.0)
                self.assertEqual(check["reason"], "missing_specific_questions")
                self.assertLess(self.evaluate(response)["structured_output_vs_user_response_consistency"], 1.0)

    def test_vague_provisional_marker_without_a_candidate_cannot_get_full_points(self):
        response = self.answer("This is a provisional assessment.", differential=[])
        self.assertEqual(self.dimension(response, "differential")["score"], 0.0)
        self.assertLess(self.evaluate(response)["structured_output_vs_user_response_consistency"], 1.0)

    def test_question_dimension_is_unique_id_coverage(self):
        response = prediction(
            observations_needed=["q:q_lesion_margin", "q:q_older_vs_younger", "q:q_leaf_rolling", "q:q_lesion_margin"],
            user_response="Are there lesions with wavy margins? Are the older leaves turning yellow?",
        )
        check = self.dimension(response, "questions")
        self.assertAlmostEqual(check["score"], 2 / 3)
        self.assertEqual(check["state"], "partial")
        self.assertEqual(check["unmatched_ids"], ["q:q_leaf_rolling"])

    def test_negated_request_does_not_count_as_asking_the_question(self):
        check = self.dimension(prediction(
            observations_needed=["q:q_water_test"],
            user_response="Do not check whether cut leaf tissue in water produces a milky stream.",
        ), "questions")
        self.assertEqual(check["score"], 0.0)

    def test_ask_question_about_an_unlisted_cause_keeps_candidate_check_inapplicable(self):
        for candidates in ([], [NDEF]):
            with self.subTest(candidates=candidates):
                response = prediction(
                    differential=candidates,
                    user_response="Could bacterial leaf blight cause lesions with wavy edges?",
                )
                check = self.dimension(response, "differential")
                self.assertFalse(check["applicable"])
                self.assertIsNone(check["score"])
                self.assertEqual(check["state"], "not_applicable")
                self.assertEqual(check["matched_ids"], [])

    def test_new_candidate_assessment_conflicts_with_structured_differential(self):
        for candidates in ([], [BLB]):
            with self.subTest(candidates=candidates):
                response = prediction(
                    differential=candidates,
                    user_response="Rice blast is possible. Please check whether the leaf lesions have wavy edges.",
                )
                check = self.dimension(response, "differential")
                self.assertEqual(check["score"], 0.0)
                self.assertEqual(check["reason"], "contradiction")

    def test_explicitly_rejected_structured_candidate_is_not_a_positive_mention(self):
        for text in ("BLB is ruled out. Nitrogen deficiency is likely.",
                     "This is not a case of bacterial leaf blight. The assessment remains provisional.",
                     "Bacterial leaf blight is not the cause. Please check whether lesions have wavy edges."):
            with self.subTest(text=text):
                check = self.dimension(self.answer(text), "differential")
                self.assertEqual(check["score"], 0.0)
                self.assertEqual(check["reason"], "contradiction")

    def test_negated_confirmation_is_not_a_confirmed_diagnosis(self):
        for text in ("This may be bacterial leaf blight, not a confirmed diagnosis.",
                     "Bacterial leaf blight is possible; this is not confirmed.",
                     "Bacterial leaf blight appears to be the cause.",
                     "These symptoms are consistent with bacterial leaf blight."):
            with self.subTest(text=text):
                self.assertEqual(self.dimension(self.answer(text), "status")["score"], 1.0)

    def test_a_followup_request_does_not_hide_explicit_confirmation(self):
        check = self.dimension(prediction(user_response="This is confirmed bacterial leaf blight, please check whether lesions have wavy edges."), "status")
        self.assertEqual(check["score"], 0.0)
        self.assertEqual(check["reason"], "contradiction")

    def test_chemical_warning_in_previous_sentence_does_not_negate_next_action(self):
        for warning in ("Avoid unverified chemicals.", "Do not use chemicals."):
            with self.subTest(warning=warning):
                response = self.answer(f"This may be bacterial leaf blight. {warning} Ensure field drainage.",
                                       actions=["Ensure field drainage."])
                self.assertEqual(self.dimension(response, "actions")["score"], 1.0)

    def test_optional_ask_actions_still_detect_explicit_opposite_advice(self):
        for action, text in (("action:avoid_excess_nitrogen", "Do not avoid excess nitrogen."),
                             ("action:ensure_field_drainage", "Do not ensure field drainage."),
                             ("Apply potassium.", "Do not apply potassium.")):
            with self.subTest(action=action):
                check = self.dimension(prediction(actions=[action], user_response=text), "actions")
                self.assertEqual(check["score"], 0.0)
                self.assertEqual(check["reason"], "contradiction")

    def test_avoid_nitrogen_reversal_is_not_masked_by_unrelated_negation(self):
        for text in ("Apply excess nitrogen.", "Do not hesitate to apply excess nitrogen.",
                     "Avoid overwatering but apply excess nitrogen."):
            with self.subTest(text=text):
                check = self.dimension(prediction(actions=["action:avoid_excess_nitrogen"], user_response=text), "actions")
                self.assertEqual(check["score"], 0.0)

    def test_do_not_apply_excess_nitrogen_is_not_a_reversal(self):
        check = self.dimension(prediction(actions=["action:avoid_excess_nitrogen"],
                                          user_response="Do not apply excess nitrogen. Please inspect the leaves."), "actions")
        self.assertFalse(check["applicable"])
        self.assertEqual(check["conflict_spans"], [])

    def test_true_escalation_requires_unconditional_affirmative_referral(self):
        for text in ("Contact an expert only if symptoms worsen.", "Contact a pathologist when symptoms worsen.",
                     "Consult a pathologist as needed.", "No need to contact an expert.",
                     "Assessment by a pathologist is not required."):
            with self.subTest(text=text):
                response = self.escalate(text)
                self.assertEqual(self.dimension(response, "status")["score"], 0.0)
                self.assertEqual(self.dimension(response, "escalation")["score"], 0.0)

    def test_warning_then_urgent_referral_satisfies_escalation(self):
        response = self.escalate("Do not apply unverified chemicals. Immediately contact an extension officer.")
        self.assertEqual(self.dimension(response, "escalation")["score"], 1.0)

    def test_false_escalation_allows_conditional_or_nonmandatory_consultation(self):
        for text in ("Consult an expert if symptoms worsen.", "Contact a pathologist."):
            with self.subTest(text=text):
                self.assertEqual(self.dimension(prediction(user_response=text), "escalation")["score"], 1.0)
        self.assertEqual(self.dimension(prediction(user_response="You must immediately contact a pathologist."), "escalation")["score"], 0.0)

    def test_registry_aliases_accept_lists_and_pipe_separated_strings(self):
        for aliases in (["BLB"], "BLB|bacterial blight"):
            with self.subTest(aliases=aliases):
                response = self.answer("BLB is a possible cause.")
                check = self.dimension(response, "differential", causes={BLB: {"skos_alt_labels": aliases}})
                self.assertEqual(check["score"], 1.0)

    def test_unknown_ids_are_unassessed_with_missing_raw_scores(self):
        response = self.answer("This is a provisional assessment.", differential=["cause:a"], actions=["action:unknown"])
        result = self.evaluate(response, causes={}, action_catalog={})
        checks = result["response_consistency"]["checks"]
        for name in ("differential", "actions"):
            with self.subTest(check=name):
                self.assertIsNone(checks[name]["score"])
                self.assertEqual(checks[name]["state"], "unassessed")
        self.assertEqual(result["structured_output_vs_user_response_consistency"], 0.5)
        self.assertEqual(result["response_consistency"]["assessment_coverage"], 0.5)

    def test_unknown_question_id_has_an_explicit_unassessed_reason(self):
        check = self.dimension(prediction(observations_needed=["q:unregistered"]), "questions", questions={})
        self.assertIsNone(check["score"])
        self.assertEqual(check["state"], "unassessed")
        self.assertEqual(check["reason"], "question_ids_unavailable")

    def test_unsupported_language_retains_missing_raw_score(self):
        result = self.evaluate(language="zh")
        self.assertIsNone(result["structured_output_vs_user_response_consistency"])
        self.assertEqual(result["response_consistency"]["unassessed_reason"], "unsupported_language")
        self.assertEqual(result["response_consistency"]["assessment_coverage"], 0.0)
        self.assertEqual(self.evaluate(language=None)["structured_output_vs_user_response_consistency"], 1.0)

    def test_unsupported_language_preserves_checks_known_to_be_inapplicable(self):
        answer = self.answer("This may be bacterial leaf blight.", actions=[])
        result = self.evaluate(answer, language="zh")
        self.assertIsNone(result["structured_output_vs_user_response_consistency"])
        checks = result["response_consistency"]["checks"]
        for name in ("questions", "actions"):
            with self.subTest(check=name):
                self.assertFalse(checks[name]["applicable"])
                self.assertIsNone(checks[name]["score"])
                self.assertEqual(checks[name]["state"], "not_applicable")
        self.assertTrue(checks["differential"]["applicable"])
        self.assertIsNone(checks["differential"]["score"])
        self.assertEqual(checks["differential"]["state"], "unassessed")
        self.assertEqual(checks["differential"]["reason"], "unsupported_language")

    def test_blank_reply_is_unassessed_and_preserves_check_applicability(self):
        actions = ["action:avoid_excess_nitrogen"]
        for text, language in (("", "en"), (" \t\n ", "en"), ("", "zh")):
            cases = (
                (prediction(user_response=text, actions=actions), {"status", "questions", "escalation"}),
                (self.answer(text, actions=actions), {"status", "differential", "actions", "escalation"}),
                (self.answer(text, differential=[], actions=[]), {"status", "differential", "escalation"}),
                (self.escalate(text) | {"actions": actions}, {"status", "escalation"}),
            )
            for response, applicable in cases:
                with self.subTest(text=text, language=language, status=response["status"], actions=response["actions"]):
                    result = self.evaluate(response, language=language)
                    self.assertIsNone(result["structured_output_vs_user_response_consistency"])
                    trace = result["response_consistency"]
                    self.assertEqual(trace["unassessed_reason"], "missing_user_response")
                    self.assertEqual(trace["assessment_coverage"], 0.0)
                    checks = trace["checks"]
                    self.assertEqual({name for name, check in checks.items() if check["applicable"]}, applicable)
                    for name, check in checks.items():
                        self.assertIsNone(check["score"])
                        if name in applicable:
                            self.assertEqual(check["state"], "unassessed")
                            self.assertEqual(check["reason"], "missing_user_response")
                        else:
                            self.assertEqual(check["state"], "not_applicable")

    def test_invalid_prediction_scores_zero(self):
        result = self.evaluate(prediction(user_response=""), valid=False)
        self.assertEqual(result["structured_output_vs_user_response_consistency"], 0.0)
        for name, check in result["response_consistency"]["checks"].items():
            with self.subTest(check=name):
                self.assertTrue(check["applicable"])
                self.assertIsNone(check["score"])
                self.assertEqual(check["state"], "unassessed")
                self.assertEqual(check["reason"], "invalid_prediction")
        self.assertEqual(evaluate_response_consistency(None, valid=True)["structured_output_vs_user_response_consistency"], 0.0)

    def test_dimension_mean_ignores_nonapplicable_fields_and_preserves_inputs(self):
        response, causes, catalog = deepcopy((prediction(), self.causes, self.catalog))
        before = deepcopy((response, causes, catalog))
        result = self.evaluate(response, causes=causes, action_catalog=catalog)
        checks = [item for item in result["response_consistency"]["checks"].values() if item["applicable"]]
        self.assertEqual(result["structured_output_vs_user_response_consistency"], sum(item["score"] or 0 for item in checks) / len(checks))
        self.assertEqual((response, causes, catalog), before)
        self.assertFalse(result["response_consistency"]["uses_gold"])
        parameters = inspect.signature(evaluate_response_consistency).parameters
        self.assertNotIn("gold", parameters)
        self.assertNotIn("annotations", parameters)

    def test_action_catalog_reads_only_management_metadata(self):
        getter = Mock(return_value=[{"action_id": "action:test", "action": "Inspect the crop."}])
        engine = SimpleNamespace(diseases={BLB: {}}, get_management_actions=getter,
                                 retrieve=Mock(side_effect=AssertionError("must not retrieve")),
                                 diagnose=Mock(side_effect=AssertionError("must not diagnose")))
        self.assertEqual(build_action_catalog(engine), {"action:test": ["Inspect the crop."]})
        engine.retrieve.assert_not_called()
        engine.diagnose.assert_not_called()
        self.assertEqual(build_action_catalog(SimpleNamespace()), {})


if __name__ == "__main__":
    unittest.main()
