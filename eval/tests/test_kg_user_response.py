"""KG-only user text uses available labels without changing compact IDs."""

from copy import deepcopy
import unittest

from eval.evaluate_unified import ROOT
from engine.diagnostic_engine import DiagnosticEngine
from engine.retriever import to_compact_target_response


COMPACT_KEYS = {
    "status", "observations_needed", "differential", "actions",
    "escalation_required", "grounding", "safety_flags", "user_response",
}


def verbose_response(**changes):
    response = {
        "status": "needs_more_information",
        "observations_needed": [
            {"question_id": "q:leaf", "farmer_friendly_phrasing": "Are the leaf edges wavy?", "canonical_text": "CANONICAL NOT PREFERRED", "question": "QUESTION NOT PREFERRED"},
            {"question_id": "q:age", "farmer_friendly_phrasing": " ", "canonical_text": "Are older leaves affected first?", "question": "QUESTION NOT PREFERRED"},
            {"question_id": "q:water", "question": "Do leaves recover after watering?"},
        ],
        "differential": [
            {"cause_id": "disease:bacterial_leaf_blight", "display_name": "Bacterial leaf blight"},
            {"cause_id": "disorder:nitrogen_deficiency", "display_name": "Nitrogen deficiency"},
        ],
        "recommended_actions": [
            {"action_id": "action:drain", "action": "Improve field drainage."},
            {"action_id": "action:monitor", "action": "Monitor the affected plants."},
        ],
        "escalation": {"required": False, "triggers": []},
        "grounding": [{"claim_id": "fact:two"}, {"claim_id": "fact:one"}],
        "safety_flags": ["confirm_before_treatment"],
        "annotations": {"user_response": "SECRET GOLD ANSWER"},
        "target_response": {"user_response": "SECRET TRAINING ANSWER"},
    }
    response.update(changes)
    return response


class KGUserResponseTests(unittest.TestCase):
    def assert_compact_fields(self, result, original):
        self.assertEqual(set(result), COMPACT_KEYS)
        for field, source, id_key in (
            ("observations_needed", "observations_needed", "question_id"),
            ("differential", "differential", "cause_id"),
            ("actions", "recommended_actions", "action_id"),
            ("grounding", "grounding", "claim_id"),
        ):
            self.assertEqual(result[field], [item[id_key] if isinstance(item, dict) else str(item) for item in original[source]])
        escalation = original.get("escalation", {})
        self.assertEqual(result["safety_flags"], escalation.get("triggers", []) if isinstance(escalation, dict) else [])
        self.assertIsInstance(result["user_response"], str)
        self.assertTrue(result["user_response"].strip())
        self.assertNotIn("SECRET", result["user_response"])

    def test_ask_uses_friendly_names_and_all_three_actual_questions(self):
        original = verbose_response()
        result = to_compact_target_response(original)
        self.assert_compact_fields(result, original)
        self.assertEqual(result["status"], "needs_more_information")
        self.assertFalse(result["escalation_required"])
        text = result["user_response"]
        self.assertIn("Bacterial leaf blight", text)
        self.assertIn("Nitrogen deficiency", text)
        for index, question in enumerate(("Are the leaf edges wavy?", "Are older leaves affected first?", "Do leaves recover after watering?"), start=1):
            self.assertIn(f"{index}. {question}", text)
        self.assertNotIn("NOT PREFERRED", text)
        self.assertNotIn("disease:bacterial_leaf_blight", text)
        self.assertNotIn("q:leaf", text)

    def test_answer_uses_first_display_name_and_existing_first_action(self):
        original = verbose_response(status="differential_available", observations_needed=[])
        result = to_compact_target_response(original)
        self.assert_compact_fields(result, original)
        self.assertEqual(result["status"], "provisional_assessment")
        self.assertIn("Bacterial leaf blight", result["user_response"])
        self.assertIn("Improve field drainage.", result["user_response"])
        self.assertIn("provisional", result["user_response"])
        self.assertNotIn("disease:bacterial_leaf_blight", result["user_response"])
        self.assertEqual(result["actions"], ["action:drain", "action:monitor"])
        self.assertNotIn("action:", result["user_response"])

    def test_escalation_keeps_fixed_extension_and_plant_clinic_guidance(self):
        original = verbose_response(status="high_risk_escalation", escalation={"required": True}, observations_needed=[])
        result = to_compact_target_response(original)
        self.assert_compact_fields(result, original)
        self.assertEqual(result["status"], "escalation_required")
        self.assertTrue(result["escalation_required"])
        self.assertIn("agricultural extension officer", result["user_response"])
        self.assertIn("plant clinic", result["user_response"])
        self.assertIn("avoid applying unverified chemicals", result["user_response"])

    def test_text_and_id_fallbacks_preserve_string_ids_order_and_duplicates(self):
        original = verbose_response(
            observations_needed=[{"question_id": "q:text", "text": "Is the soil dry?"}, "q:last", "q:last"],
            differential=[{"cause_id": "cause:fallback", "display_name": " "}, "cause:second"],
            recommended_actions=["action:drain", "action:drain"], grounding=["fact:two", "fact:one"],
        )
        result = to_compact_target_response(original)
        self.assert_compact_fields(result, original)
        text = result["user_response"]
        self.assertIn("cause:fallback, cause:second", text)
        self.assertIn("1. Is the soil dry?", text)
        self.assertIn("2. q:last\n3. q:last", text)
        answered = to_compact_target_response({**original, "status": "differential_available"})
        self.assertIn("cause:fallback", answered["user_response"])
        self.assertEqual(answered["actions"], ["action:drain", "action:drain"])
        self.assertIn("Monitor field conditions closely.", answered["user_response"])
        self.assertNotIn("action:", answered["user_response"])

    def test_answer_without_action_text_uses_readable_fallback_instead_of_ids(self):
        for action in (
            {"action_id": "action:drain"},
            {"action_id": "action:drain", "action": ""},
            {"action_id": "action:drain", "action": " "},
            "action:drain",
        ):
            with self.subTest(action=action):
                original = verbose_response(status="differential_available", observations_needed=[],
                                            recommended_actions=[action])
                result = to_compact_target_response(original)
                self.assert_compact_fields(result, original)
                self.assertEqual(result["actions"], ["action:drain"])
                self.assertIn("Monitor field conditions closely.", result["user_response"])
                self.assertNotIn("action:", result["user_response"])

    def test_safety_flags_use_triggers_without_borrowing_top_level_policy_labels(self):
        for escalation, expected in (
            ({"required": True, "triggers": ["trigger:panicle_infection", "trigger:panicle_infection"]},
             ["trigger:panicle_infection", "trigger:panicle_infection"]),
            ({"required": False, "triggers": []}, []),
            ({"required": True}, []),
            (True, []),
            (False, []),
        ):
            with self.subTest(escalation=escalation):
                original = verbose_response(escalation=escalation,
                                            safety_flags=["PRINCIPLE_ACTIONS_ONLY_NO_CHEMICAL_DOSAGES"])
                result = to_compact_target_response(original)
                self.assert_compact_fields(result, original)
                self.assertEqual(result["safety_flags"], expected)
                self.assertNotIn("PRINCIPLE_ACTIONS_ONLY_NO_CHEMICAL_DOSAGES", result["safety_flags"])

    def test_real_engine_trigger_ids_and_action_ids_are_preserved(self):
        engine = DiagnosticEngine(str(ROOT))
        original = engine.diagnose("Panicle neck rot is destroying the crop.")
        before = deepcopy(original)
        result = to_compact_target_response(original)
        self.assert_compact_fields(result, original)
        self.assertEqual(result["status"], "escalation_required")
        self.assertTrue(result["escalation_required"])
        self.assertEqual(result["safety_flags"], [
            "trigger:rapid_uncontrolled_spread", "trigger:panicle_infection",
        ])
        self.assertEqual(result["actions"], ["action:escalate_to_pathologist"])
        self.assertNotIn("PRINCIPLE_ACTIONS_ONLY_NO_CHEMICAL_DOSAGES", result["safety_flags"])
        self.assertNotIn("action:", result["user_response"])
        self.assertNotIn("trigger:", result["user_response"])
        self.assertIsNot(result["safety_flags"], original["escalation"]["triggers"])
        self.assertEqual(original, before)

    def test_real_rank_questions_question_key_is_rendered_without_a_model(self):
        engine = DiagnosticEngine(str(ROOT))
        ranked = engine.rank_questions([{"cause_id": "disease:bacterial_leaf_blight", "score": 2}], {})[:3]
        self.assertEqual(len(ranked), 3)
        original = verbose_response(observations_needed=ranked)
        result = to_compact_target_response(original)
        self.assert_compact_fields(result, original)
        for index, item in enumerate(ranked, start=1):
            self.assertIn(f"{index}. {item['question']}", result["user_response"])

    def test_all_three_statuses_leave_the_verbose_input_unchanged(self):
        for status, escalates in (("needs_more_information", False), ("differential_available", False), ("high_risk_escalation", True)):
            with self.subTest(status=status):
                original = verbose_response(status=status, escalation={
                    "required": escalates,
                    "triggers": ["trigger:panicle_infection"] if escalates else [],
                })
                before = deepcopy(original)
                result = to_compact_target_response(original)
                self.assertIsNot(result["safety_flags"], original["escalation"]["triggers"])
                for compact, verbose in (
                    ("observations_needed", "observations_needed"),
                    ("differential", "differential"),
                    ("actions", "recommended_actions"),
                    ("grounding", "grounding"),
                    ("safety_flags", "safety_flags"),
                ):
                    self.assertIsNot(result[compact], original[verbose])
                    result[compact].append("MUTATED COMPACT LIST")
                self.assertEqual(original, before)

    def test_empty_candidates_and_actions_still_produce_readable_text(self):
        for status in ("needs_more_information", "differential_available"):
            with self.subTest(status=status):
                original = verbose_response(status=status, differential=[], recommended_actions=[], observations_needed=[])
                result = to_compact_target_response(original)
                self.assert_compact_fields(result, original)
                self.assertNotIn("None", result["user_response"])
                self.assertNotIn("[]", result["user_response"])


if __name__ == "__main__":
    unittest.main()
