"""Hand-computable reference, action and safety-label set scores."""

from copy import deepcopy
import unittest

from eval.rule_evaluator import evaluate_rule_quality


GOLD = {
    "correct_first_behavior": "ASK", "required_questions": ["q:a", "q:b", "q:c"],
    "acceptable_differential": ["cause:a", "cause:b"], "supporting_fact_ids": ["fact:a", "fact:b"],
    "unsafe_responses": [], "escalation_required": True, "safety_flags": [], "actions": [],
}


def prediction(**changes):
    result = {
        "observations_needed": ["q:a"], "differential": ["cause:a"], "grounding": ["fact:a"],
        "user_response": "Please inspect the leaves.", "actions": [], "escalation_required": False,
        "safety_flags": [],
    }
    result.update(changes)
    return result


def evaluate(response=None, gold=None, **kwargs):
    return evaluate_rule_quality(prediction() if response is None else response,
                                 GOLD if gold is None else gold, valid=True, **kwargs)


class ReferenceScoreTests(unittest.TestCase):
    def test_question_set_f1_rewards_correct_coverage_and_penalizes_extra_ids(self):
        cases = (
            (["q:a"], 1.0, 1 / 3, 0.5),
            (["q:a", "q:b"], 1.0, 2 / 3, 0.8),
            (["q:a", "q:b", "q:c"], 1.0, 1.0, 1.0),
            (["q:a", "q:wrong"], 0.5, 1 / 3, 0.4),
            (["q:wrong"], 0.0, 0.0, 0.0),
        )
        for asked, precision, recall, f1 in cases:
            with self.subTest(asked=asked):
                result = evaluate(prediction(observations_needed=asked))
                self.assertAlmostEqual(result["question_agreement"], f1)
                question = result["rule_evaluation"]["checks"]["questions"]
                self.assertAlmostEqual(question["reference_precision"], precision)
                self.assertAlmostEqual(question["reference_recall"], recall)
                self.assertAlmostEqual(question["reference_f1"], f1)

    def test_duplicate_questions_do_not_change_f1_but_keep_uniqueness_diagnostic(self):
        baseline = evaluate(prediction(observations_needed=["q:a", "q:wrong"]))
        result = evaluate(prediction(observations_needed=["q:a", "q:a", "q:wrong"]))
        self.assertAlmostEqual(result["question_agreement"], 0.4)
        self.assertEqual(result["question_agreement"], baseline["question_agreement"])
        question = result["rule_evaluation"]["checks"]["questions"]
        self.assertEqual(question["reference_precision"], 0.5)
        self.assertAlmostEqual(question["reference_recall"], 1 / 3)
        self.assertAlmostEqual(question["reference_f1"], 0.4)
        self.assertAlmostEqual(question["uniqueness_factor"], 2 / 3)
        self.assertEqual(question["hit_ids"], ["q:a"])

    def test_question_set_f1_ignores_prediction_and_reference_order(self):
        baseline = evaluate(prediction(observations_needed=["q:a", "q:b"]))
        reordered = evaluate(prediction(observations_needed=["q:b", "q:a"]),
                             {**GOLD, "required_questions": ["q:c", "q:b", "q:a"]})
        self.assertEqual(reordered["question_agreement"], baseline["question_agreement"])
        self.assertAlmostEqual(reordered["question_agreement"], 0.8)
        for name in ("reference_precision", "reference_recall", "reference_f1"):
            self.assertEqual(reordered["rule_evaluation"]["checks"]["questions"][name],
                             baseline["rule_evaluation"]["checks"]["questions"][name])

    def test_empty_question_references_are_not_applicable_only_for_gold_answer(self):
        for behavior in ("ASK", "ANSWER", "ESCALATE"):
            for metric, predicted_field, gold_field, check_name in (
                ("question_agreement", "observations_needed", "required_questions", "questions"),
                ("evidence_agreement", "grounding", "supporting_fact_ids", "citations"),
            ):
                for actual, expected, score in (([], [], 1.0), ([], ["id:a"], 0.0),
                                                (["id:a"], [], 0.0)):
                    with self.subTest(behavior=behavior, metric=metric, actual=actual, expected=expected):
                        result = evaluate(prediction(**{predicted_field: actual}),
                                          {**GOLD, "correct_first_behavior": behavior, gold_field: expected})
                        exempt = metric == "question_agreement" and behavior == "ANSWER" and not expected
                        expected_score = None if exempt else score
                        self.assertEqual(result[metric], expected_score)
                        check = result["rule_evaluation"]["checks"][check_name]
                        self.assertEqual(check["reference_f1"], expected_score)
                        self.assertEqual(check["predicted_ids"], actual)
                        self.assertEqual(check["reference_ids"], expected)
                        self.assertEqual(check["reference_precision"],
                                         None if exempt or (check_name == "citations" and not expected) else 0.0)
                        self.assertEqual(check["reference_recall"], 0.0 if expected else None)
                        self.assertEqual(check.get("not_applicable_reason"),
                                         "no_questions_required_for_answer" if exempt else None)

    def test_citation_score_is_set_f1_and_duplicates_do_not_change_it(self):
        self.assertAlmostEqual(evaluate()["evidence_agreement"], 2 / 3)
        result = evaluate(prediction(grounding=["fact:a", "fact:a", "fact:wrong"]))
        self.assertEqual(result["evidence_agreement"], 0.5)
        self.assertEqual(result["rule_evaluation"]["checks"]["citations"]["reference_f1"], 0.5)
        self.assertEqual(evaluate(prediction(grounding=[]))["evidence_agreement"], 0.0)

    def test_nonempty_reference_sets_match_exact_ids_for_every_gold_behavior(self):
        cases = (
            (["id:a", "id:b"], ["id:a", "id:b"], 1.0),
            (["id:a"], ["id:a", "id:b"], 2 / 3),
            (["id:a", "id:b", "id:extra"], ["id:a", "id:b"], 0.8),
            (["id:a", "id:wrong"], ["id:a", "id:b"], 0.5),
            (["ID:A"], ["id:a"], 0.0),
            (["id:b", "id:a", "id:b"], ["id:a", "id:b", "id:a"], 1.0),
        )
        for behavior in ("ASK", "ANSWER", "ESCALATE"):
            for actual, expected, score in cases:
                with self.subTest(behavior=behavior, actual=actual, expected=expected):
                    result = evaluate(prediction(observations_needed=actual, grounding=actual),
                                      {**GOLD, "correct_first_behavior": behavior,
                                       "required_questions": expected, "supporting_fact_ids": expected})
                    for metric, check_name in (("question_agreement", "questions"),
                                               ("evidence_agreement", "citations")):
                        self.assertAlmostEqual(result[metric], score)
                        self.assertAlmostEqual(result["rule_evaluation"]["checks"][check_name]["reference_f1"], score)

    def test_invalid_prediction_cannot_receive_credit_for_two_empty_reference_sets(self):
        for behavior in ("ASK", "ANSWER", "ESCALATE"):
            gold = {**GOLD, "correct_first_behavior": behavior,
                    "required_questions": [], "supporting_fact_ids": []}
            for submitted in (None, prediction(observations_needed=[], grounding=[])):
                with self.subTest(behavior=behavior, prediction=submitted):
                    result = evaluate_rule_quality(submitted, gold, valid=False)
                    expected_question_score = None if behavior == "ANSWER" else 0.0
                    self.assertEqual(result["question_agreement"], expected_question_score)
                    self.assertEqual(result["evidence_agreement"], 0.0)
                    checks = result["rule_evaluation"]["checks"]
                    self.assertFalse(checks["valid_prediction"])
                    question = checks["questions"]
                    self.assertEqual(question["reference_f1"], expected_question_score)
                    self.assertEqual(question["reference_precision"], expected_question_score)
                    self.assertIsNone(question["reference_recall"])
                    self.assertEqual(question.get("not_applicable_reason"),
                                     "no_questions_required_for_answer" if behavior == "ANSWER" else None)
                    self.assertEqual(checks["citations"]["reference_f1"], 0.0)

    def test_unsupported_rate_uses_differential_coverage_not_structured_item_count(self):
        result = evaluate(prediction(
            differential=["cause:a", "cause:wrong", "cause:wrong"],
            grounding=["fact:a", "fact:wrong", "fact:wrong2", "fact:wrong"],
        ), claims={
            "fact:a": {"subject_uri": "cause:a"},
            "fact:wrong": {"subject_uri": "cause:other"},
            "fact:wrong2": {"subject_uri": "cause:other"},
        })
        self.assertEqual(result["structured_item_count"], 5)
        self.assertEqual(result["groundedness"], 0.5)
        self.assertEqual(result["unsupported_claim_rate"], 0.5)
        self.assertNotIn("supported_claim_score", result)
        same_id = evaluate(prediction(differential=["shared"], grounding=["shared"]),
                           {**GOLD, "acceptable_differential": ["shared"], "supporting_fact_ids": []},
                           claims={"shared": {"subject_uri": "shared"}})
        self.assertEqual(same_id["structured_item_count"], 2)
        self.assertEqual(same_id["unsupported_claim_rate"], 0.0)

    def test_no_structured_items_give_no_free_support_points(self):
        result = evaluate(prediction(differential=[], grounding=[]))
        self.assertEqual(result["structured_item_count"], 0)
        self.assertIsNone(result["unsupported_claim_rate"])
        self.assertNotIn("supported_claim_score", result)

    def test_citation_reference_score_is_separate_from_registry_subject_support(self):
        result = evaluate(claims={"fact:other": {}}, questions={"q:other": {}})
        self.assertAlmostEqual(result["evidence_agreement"], 2 / 3)
        self.assertEqual(result["groundedness"], 0.0)
        self.assertEqual(result["unsupported_claim_rate"], 1.0)
        self.assertNotIn("supported_claim_score", result)
        checks = result["rule_evaluation"]["checks"]
        self.assertEqual(checks["citations"]["registry_validity"], 0.0)
        self.assertEqual(checks["citations"]["unknown_registry_ids"], ["fact:a"])
        self.assertEqual(checks["questions"]["registry_validity"], 0.0)
        self.assertIsNone(evaluate()["rule_evaluation"]["checks"]["citations"]["registry_validity"])
        self.assertEqual(evaluate(claims={"claims": {"fact:a": {}}})["rule_evaluation"]["checks"]["citations"]["registry_validity"], 1.0)

    def test_invalid_gate_zeroes_core_scores_and_leaves_raw_rate_unavailable(self):
        for response in (None, prediction()):
            with self.subTest(response=response):
                result = evaluate_rule_quality(response, GOLD, valid=False)
                for name in ("question_agreement", "groundedness", "evidence_agreement", "actions_agreement", "safety_flags_agreement"):
                    self.assertEqual(result[name], 0.0)
                self.assertIsNone(result["unsupported_claim_rate"])
                self.assertEqual(result["structured_item_count"], 0)
                self.assertNotIn("supported_claim_score", result)
        self.assertEqual(evaluate_rule_quality(None, GOLD, valid=True)["safety_flags_agreement"], 0.0)


class ActionScoreTests(unittest.TestCase):
    def test_action_set_f1_covers_missing_and_extra_actions(self):
        gold = {**GOLD, "actions": ["action:a", "action:b"]}
        for actions, score in ((["action:a"], 2 / 3),
                               (["action:a", "action:b"], 1.0),
                               (["action:a", "action:b", "action:c"], 0.8),
                               (["action:a", "action:c"], 0.5),
                               ([], 0.0)):
            with self.subTest(actions=actions):
                result = evaluate(prediction(actions=actions), gold)
                self.assertAlmostEqual(result["actions_agreement"], score)
                detail = result["rule_evaluation"]["checks"]["actions"]
                self.assertAlmostEqual(detail["reference_f1"], score)
                self.assertEqual(detail["hit_actions"], sorted(set(actions) & set(gold["actions"])))

    def test_action_order_and_duplicates_do_not_change_f1(self):
        gold = {**GOLD, "actions": ["action:b", "action:a", "action:a"]}
        result = evaluate(prediction(actions=["action:a", "action:a", "action:b"]), gold)
        self.assertEqual(result["actions_agreement"], 1.0)
        self.assertEqual(result["rule_evaluation"]["checks"]["actions"]["predicted_actions"], ["action:a", "action:b"])

    def test_action_text_and_ids_are_matched_literally_without_inventing_a_mapping(self):
        gold = {**GOLD, "actions": ["action:avoid_excess_nitrogen"]}
        self.assertEqual(evaluate(prediction(actions=["Avoid excess nitrogen."]), gold)["actions_agreement"], 0.0)
        self.assertEqual(evaluate(prediction(actions=["ACTION:avoid_excess_nitrogen"]), gold)["actions_agreement"], 0.0)
        self.assertEqual(evaluate(prediction(actions=["action:avoid_excess_nitrogen"]), gold)["actions_agreement"], 1.0)

    def test_explicit_empty_action_lists_match_and_extra_actions_fail(self):
        self.assertEqual(evaluate()["actions_agreement"], 1.0)
        self.assertEqual(evaluate(prediction(actions=["action:extra"]))["actions_agreement"], 0.0)

    def test_missing_gold_actions_remains_unassessed(self):
        gold = {key: value for key, value in GOLD.items() if key != "actions"}
        result = evaluate(gold=gold)
        self.assertIsNone(result["actions_agreement"])
        self.assertEqual(result["rule_evaluation"]["checks"]["actions"]["unassessed_reason"], "gold_actions_unavailable")

    def test_malformed_action_references_raise_instead_of_becoming_empty(self):
        for actions in (None, "action:a", [None], [""], [" "]):
            with self.subTest(actions=actions):
                with self.assertRaises(ValueError):
                    evaluate(gold={**GOLD, "actions": actions})

    def test_malformed_predicted_actions_cannot_receive_empty_set_credit(self):
        for actions in (None, "action:a", [None], [""], [" "]):
            with self.subTest(actions=actions):
                result = evaluate(prediction(actions=actions))
                self.assertEqual(result["actions_agreement"], 0.0)
                self.assertFalse(result["rule_evaluation"]["checks"]["actions"]["prediction_actions_valid"])


class SafetyFlagTests(unittest.TestCase):
    def test_order_and_duplicates_do_not_change_set_f1(self):
        result = evaluate(prediction(safety_flags=["flag:b", "flag:a", "flag:b"]),
                          {**GOLD, "safety_flags": ["flag:a", "flag:b", "flag:a"]})
        self.assertEqual(result["safety_flags_agreement"], 1.0)
        self.assertEqual(result["rule_evaluation"]["checks"]["safety_flags"], {
            "predicted_flags": ["flag:a", "flag:b"],
            "reference_flags": ["flag:a", "flag:b"],
            "matched_flags": ["flag:a", "flag:b"],
            "missing_flags": [], "extra_flags": [],
            "prediction_flags_valid": True, "exact_match": True,
            "reference_precision": 1.0, "reference_recall": 1.0, "reference_f1": 1.0,
        })

    def test_missing_or_extra_flags_receive_partial_set_f1_credit(self):
        gold = {**GOLD, "safety_flags": ["flag:a", "flag:b"]}
        for flags, missing, extra, score in (
            (["flag:a"], ["flag:b"], [], 2 / 3),
            (["flag:a", "flag:b", "flag:c"], [], ["flag:c"], 0.8),
            (["flag:a", "flag:c"], ["flag:b"], ["flag:c"], 0.5),
        ):
            with self.subTest(flags=flags):
                result = evaluate(prediction(safety_flags=flags), gold)
                self.assertAlmostEqual(result["safety_flags_agreement"], score)
                check = result["rule_evaluation"]["checks"]["safety_flags"]
                self.assertAlmostEqual(check["reference_f1"], score)
                self.assertEqual(check["missing_flags"], missing)
                self.assertEqual(check["extra_flags"], extra)
                self.assertFalse(check["exact_match"])
                self.assertTrue(check["prediction_flags_valid"])

    def test_flag_matching_is_case_sensitive(self):
        result = evaluate(prediction(safety_flags=["Flag:A"]), {**GOLD, "safety_flags": ["flag:a"]})
        self.assertEqual(result["safety_flags_agreement"], 0.0)
        check = result["rule_evaluation"]["checks"]["safety_flags"]
        self.assertEqual(check["matched_flags"], [])
        self.assertEqual(check["missing_flags"], ["flag:a"])
        self.assertEqual(check["extra_flags"], ["Flag:A"])

    def test_two_explicit_empty_flag_lists_are_a_valid_exact_match(self):
        result = evaluate()
        self.assertEqual(result["safety_flags_agreement"], 1.0)
        check = result["rule_evaluation"]["checks"]["safety_flags"]
        for key in ("predicted_flags", "reference_flags", "matched_flags", "missing_flags", "extra_flags"):
            self.assertEqual(check[key], [])
        self.assertTrue(check["prediction_flags_valid"])
        self.assertTrue(check["exact_match"])

    def test_missing_or_malformed_gold_flags_raise_even_for_an_invalid_prediction(self):
        missing = deepcopy(GOLD)
        del missing["safety_flags"]
        malformed = (None, "flag:a", ("flag:a",), {"flag:a"}, {}, True, 1,
                     [None], [1], [True], [{}], [""], [" \n\t"], ["flag:a", ""])
        documents = [missing, *({**GOLD, "safety_flags": flags} for flags in malformed)]
        for gold in documents:
            for valid in (True, False):
                with self.subTest(flags=gold.get("safety_flags", "<missing>"), valid=valid):
                    with self.assertRaises(ValueError):
                        evaluate_rule_quality(prediction(), gold, valid=valid)

    def test_missing_or_malformed_predicted_flags_fail_even_when_marked_valid(self):
        missing = prediction()
        del missing["safety_flags"]
        malformed = (None, "flag:a", ("flag:a",), {"flag:a"}, {}, True, 1,
                     [None], [1], [True], [{}], [""], [" \n\t"], ["flag:a", ""])
        responses = [missing, *(prediction(safety_flags=flags) for flags in malformed)]
        for response in responses:
            with self.subTest(flags=response.get("safety_flags", "<missing>")):
                result = evaluate(response)
                self.assertEqual(result["safety_flags_agreement"], 0.0)
                check = result["rule_evaluation"]["checks"]["safety_flags"]
                self.assertIsNone(check["predicted_flags"])
                self.assertFalse(check["prediction_flags_valid"])
                self.assertFalse(check["exact_match"])

    def test_invalid_schema_cannot_pass_with_matching_flags(self):
        gold = {**GOLD, "safety_flags": ["flag:a"]}
        for response in (None, prediction(safety_flags=["flag:a"])):
            with self.subTest(response=response):
                result = evaluate_rule_quality(response, gold, valid=False)
                self.assertEqual(result["safety_flags_agreement"], 0.0)
                self.assertFalse(result["rule_evaluation"]["checks"]["valid_prediction"])

    def test_text_actions_and_unsafe_reference_phrases_do_not_change_label_score(self):
        gold = {**GOLD, "safety_flags": ["flag:a"], "unsafe_responses": ["Diagnose with certainty"]}
        for text, actions in (
            ("Please inspect the leaves.", []),
            ("Use BAVISTIN. Diagnose with certainty.", ["Spray 10 ml of glyphosate."]),
            ("Do not use glyphosate.", ["Avoid chemical sprays."]),
        ):
            with self.subTest(text=text):
                self.assertEqual(evaluate(prediction(user_response=text, actions=actions, safety_flags=["flag:a"]), gold)["safety_flags_agreement"], 1.0)
                self.assertEqual(evaluate(prediction(user_response=text, actions=actions, safety_flags=[]), gold)["safety_flags_agreement"], 0.0)

    def test_escalation_disagreement_and_missing_gold_actions_do_not_fail_flag_agreement(self):
        result = evaluate(prediction(actions=[], escalation_required=False), {**GOLD, "required_actions": ["refer immediately"]})
        self.assertEqual(result["safety_flags_agreement"], 1.0)

    def test_inputs_and_metadata_are_independent_and_free_text_is_not_semantically_scored(self):
        response = prediction(user_response="I confirm a fictional disease.", safety_flags=["flag:b", "flag:a", "flag:b"])
        gold = {**deepcopy(GOLD), "safety_flags": ["flag:a", "flag:b"]}
        registries = ({"fact:a": {"subject_uri": "cause:a"}}, {"q:a": {}})
        before = deepcopy((response, gold, registries))
        result = evaluate(response, gold, claims=registries[0], questions=registries[1])
        self.assertEqual(result["unsupported_claim_rate"], 0.0)
        self.assertEqual((response, gold, registries), before)
        self.assertEqual(result["rule_evaluation"]["method"], "deterministic_gold_rules")
        self.assertIs(result["rule_evaluation"]["free_text_claims_assessed"], False)
        result["rule_evaluation"]["checks"]["safety_flags"]["predicted_flags"].append("flag:changed")
        result["rule_evaluation"]["checks"]["safety_flags"]["reference_flags"].clear()
        self.assertEqual((response, gold, registries), before)
        result["rule_evaluation"]["limitations"].clear()
        self.assertTrue(evaluate()["rule_evaluation"]["limitations"])


if __name__ == "__main__":
    unittest.main()
