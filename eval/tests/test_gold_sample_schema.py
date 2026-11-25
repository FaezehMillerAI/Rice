"""Check the current gold dataset contract without historical source files."""

from collections import Counter
import json
from pathlib import Path
import unittest

from eval.evaluate_unified import scoring_annotations, validate_response


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data/eval/gold_eval_v0.3.json"
ROOT_FIELDS = {
    "schema_version", "scenario_id", "family_id", "origin", "language",
    "region_id", "input", "annotations", "target_response",
}
INPUT_FIELDS = {"user_text", "growth_stage_id", "production_system_id", "cultivar_id"}
ANNOTATION_FIELDS = {
    "observations", "acceptable_differential", "required_confounders",
    "correct_first_behavior", "required_questions", "escalation_required",
    "supporting_fact_ids", "supporting_source_ids",
}
OBSERVATION_FIELDS = {"concept_id", "state"}
TARGET_FIELDS = {
    "status", "observations_needed", "differential", "actions",
    "escalation_required", "grounding", "safety_flags", "user_response",
}
STATUS_BEHAVIORS = {
    "needs_more_information": "ASK",
    "provisional_assessment": "ANSWER",
    "escalation_required": "ESCALATE",
}


class GoldSampleSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(DATASET.read_text(encoding="utf-8"))

    def assert_nonempty_string(self, value, path):
        self.assertIsInstance(value, str, path)
        self.assertTrue(value.strip(), path)

    def assert_string_list(self, value, path):
        self.assertIsInstance(value, list, path)
        for item in value:
            self.assert_nonempty_string(item, f"{path}[]")

    def test_release_has_65_unique_scenarios_and_expected_behaviors(self):
        self.assertIsInstance(self.cases, list)
        self.assertEqual(len(self.cases), 65)
        scenario_ids = [case["scenario_id"] for case in self.cases]
        self.assertEqual(len(set(scenario_ids)), 65)
        self.assertEqual(
            Counter(case["annotations"]["correct_first_behavior"] for case in self.cases),
            {"ASK": 16, "ANSWER": 43, "ESCALATE": 6},
        )

    def test_every_case_has_exact_fields_and_valid_types(self):
        for case in self.cases:
            with self.subTest(scenario_id=case.get("scenario_id")):
                self.assertIsInstance(case, dict)
                self.assertEqual(set(case), ROOT_FIELDS)
                self.assertEqual(case["schema_version"], "0.3.0")
                self.assertEqual(case["origin"], "sme_authored")
                for field in ("scenario_id", "family_id", "language", "region_id"):
                    self.assert_nonempty_string(case[field], field)

                public_input = case["input"]
                self.assertIsInstance(public_input, dict)
                self.assertEqual(set(public_input), INPUT_FIELDS)
                self.assert_nonempty_string(public_input["user_text"], "input.user_text")
                for field in ("growth_stage_id", "production_system_id", "cultivar_id"):
                    value = public_input[field]
                    if value is not None:
                        self.assert_nonempty_string(value, f"input.{field}")

                annotations = case["annotations"]
                self.assertIsInstance(annotations, dict)
                self.assertEqual(set(annotations), ANNOTATION_FIELDS)
                self.assertIsInstance(annotations["observations"], list)
                for observation in annotations["observations"]:
                    self.assertIsInstance(observation, dict)
                    self.assertEqual(set(observation), OBSERVATION_FIELDS)
                    self.assert_nonempty_string(observation["concept_id"], "observation.concept_id")
                    self.assertIn(observation["state"], {"PRESENT", "ABSENT", "UNKNOWN"})
                for field in (
                    "acceptable_differential", "required_confounders", "required_questions",
                    "supporting_fact_ids", "supporting_source_ids",
                ):
                    self.assert_string_list(annotations[field], f"annotations.{field}")
                self.assertIn(annotations["correct_first_behavior"], {"ASK", "ANSWER", "ESCALATE"})
                self.assertIs(type(annotations["escalation_required"]), bool)

                target = case["target_response"]
                self.assertIsInstance(target, dict)
                self.assertEqual(set(target), TARGET_FIELDS)
                for field in ("observations_needed", "differential", "actions", "grounding", "safety_flags"):
                    self.assert_string_list(target[field], f"target_response.{field}")
                self.assert_nonempty_string(target["user_response"], "target_response.user_response")
                self.assertIs(type(target["escalation_required"]), bool)
                self.assertEqual(validate_response(target), [])

    def test_reference_behavior_and_escalation_are_consistent(self):
        for case in self.cases:
            with self.subTest(scenario_id=case["scenario_id"]):
                annotations, target = case["annotations"], case["target_response"]
                behavior = annotations["correct_first_behavior"]
                self.assertEqual(STATUS_BEHAVIORS[target["status"]], behavior)
                self.assertEqual(annotations["escalation_required"], behavior == "ESCALATE")
                self.assertEqual(target["escalation_required"], annotations["escalation_required"])

    def test_target_actions_use_action_ids(self):
        for case in self.cases:
            with self.subTest(scenario_id=case["scenario_id"]):
                for action in case["target_response"]["actions"]:
                    self.assertRegex(action, r"^action:[A-Za-z0-9_]+$")

    def test_safety_reference_is_copied_from_target_response(self):
        for case in self.cases:
            with self.subTest(scenario_id=case["scenario_id"]):
                self.assertNotIn("safety_flags", case["annotations"])
                gold = scoring_annotations(case)
                self.assertEqual(gold["safety_flags"], case["target_response"]["safety_flags"])
                self.assertIsNot(gold["safety_flags"], case["target_response"]["safety_flags"])
                self.assertNotIn("safety_flags", case["annotations"])


if __name__ == "__main__":
    unittest.main()
