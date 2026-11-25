"""Functional checks for JSON loading and prompt/target construction."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from sft.data_preparation import build_examples, load_scenarios
from contracts.retrieval import empty_retrieved_context
from engine.retriever import KGRetriever
from engine.prompting import SYSTEM_PROMPT


CONTEXT_SEPARATOR = "\n\nretrieved context:\n"


def scenario():
    return {
        "scenario_id": "SCN-TEST-001",
        "family_id": "FAMILY-TEST-001",
        "language": "en",
        "region_id": "region:global",
        "input": {
            "user_text": "Rice leaves are yellow after rain.",
            "growth_stage_id": None,
            "production_system_id": None,
            "cultivar_id": None,
            "private_note": "NESTED_INPUT_SECRET",
        },
        "annotations": {
            "private_note": "ANNOTATION_SECRET",
            "supporting_fact_ids": ["FACT-PRIVATE"],
            "supporting_source_ids": ["SRC-PRIVATE"],
        },
        "target_response": {
            "status": "needs_more_information",
            "observations_needed": ["question:lesion_presence"],
            "differential": ["disease:TARGET_SECRET"],
            "actions": [],
            "escalation_required": False,
            "grounding": ["FACT-PRIVATE"],
            "safety_flags": [],
            "user_response": "Please check whether the leaves have visible lesions. USER_RESPONSE_SECRET",
        },
        "natural_response": "NATURAL_RESPONSE_SECRET",
    }


def public_case():
    return {
        "input": {
            "user_text": "Rice leaves are yellow after rain.",
            "growth_stage_id": None,
            "production_system_id": None,
            "cultivar_id": None,
        },
        "language": "en",
        "region_id": "region:global",
    }


def retrieved_context():
    return {
        "normalized_observations": [
            {"concept_id": "symptom:leaf_yellowing", "state": "PRESENT"}
        ],
        "candidate_causes": ["disease:rice_blast", "disorder:water_stress"],
        "supporting_evidence": [{
            "cause_id": "disease:rice_blast",
            "observation_id": "symptom:leaf_yellowing",
            "evidence_type": "Supporting",
            "condition_truth_state": "state:TRUE",
            "explanation": "Yellowing supports this candidate.",
        }],
        "contradicting_evidence": [{
            "cause_id": "disorder:water_stress",
            "observation_id": "symptom:leaf_yellowing",
            "evidence_type": "Contradicting",
            "condition_truth_state": "state:TRUE",
            "explanation": "This pattern weighs against water stress.",
        }],
        "missing_observations": ["obs:lesion_presence"],
        "suggested_questions": [{
            "question_id": "question:lesion_presence",
            "target_observation_id": "obs:lesion_presence",
            "canonical_text": "Are lesions present?",
            "farmer_friendly_phrasing": "Can you see any spots or lesions?",
            "rationale": "Lesions distinguish the leading candidates.",
        }],
        "retrieved_facts": [{
            "claim_id": "FACT-PRIVATE",
            "subject_uri": "disease:rice_blast",
            "predicate_uri": "rice:presentsAs",
            "object_uri": "symptom:leaf_yellowing",
            "source_id": "SRC-RETRIEVED",
            "source_section": "Symptoms",
            "source_text_span": "Retrieved fact",
        }],
        "evidence_fact_ids": ["FACT-PRIVATE"],
        "evidence_source_ids": ["SRC-RETRIEVED"],
    }


def prompt_payloads(example):
    query_json, context_json = example["prompt"][1]["content"].removeprefix(
        "User query:\n"
    ).split(CONTEXT_SEPARATOR)
    return json.loads(query_json), json.loads(context_json)


class DataPreparationTests(unittest.TestCase):
    def test_load_json_object_and_array(self):
        case = scenario()
        with tempfile.TemporaryDirectory() as directory:
            for filename, document, expected in (
                ("object.json", case, [case]),
                ("array.json", [case], [case]),
            ):
                with self.subTest(filename=filename):
                    path = Path(directory) / filename
                    path.write_text(json.dumps(document), encoding="utf-8")
                    self.assertEqual(load_scenarios(path), expected)

    def test_empty_retrieval_separates_public_prompt_and_copied_target(self):
        case = scenario()
        original = copy.deepcopy(case)
        received = []

        def retrieve_empty(query):
            received.append(copy.deepcopy(query))
            return empty_retrieved_context()

        empty_retriever = Mock(spec=KGRetriever)
        empty_retriever.retrieve.side_effect = retrieve_empty

        example = build_examples([case], retriever=empty_retriever)[0]
        empty = empty_retrieved_context()
        self.assertEqual(received, [public_case()])
        self.assertEqual(prompt_payloads(example), (public_case(), empty))
        self.assertEqual(example["prompt"][0], {"role": "system", "content": SYSTEM_PROMPT})
        self.assertEqual(
            example["prompt"][1]["content"],
            "User query:\n" + json.dumps(public_case(), ensure_ascii=False, indent=2)
            + CONTEXT_SEPARATOR + json.dumps(empty, ensure_ascii=False, indent=2),
        )
        expected_target = copy.deepcopy(original["target_response"])
        self.assertEqual(example["completion"], [{
            "role": "assistant",
            "content": json.dumps(expected_target, ensure_ascii=False, separators=(",", ":")),
        }])
        self.assertEqual(example["scenario_id"], original["scenario_id"])
        self.assertEqual(example["family_id"], original["family_id"])
        self.assertEqual(example["metadata"], {
            "annotations": original["annotations"],
            "retrieved_context": empty,
        })
        visible = json.dumps({"retriever_input": received, "prompt": example["prompt"]})
        for secret in (
            "NESTED_INPUT_SECRET", "ANNOTATION_SECRET", "NATURAL_RESPONSE_SECRET",
            "TARGET_SECRET", "USER_RESPONSE_SECRET", "FACT-PRIVATE", "SRC-PRIVATE",
        ):
            self.assertNotIn(secret, visible)
        self.assertNotIn("ANNOTATION_SECRET", example["completion"][0]["content"])
        self.assertNotIn("NATURAL_RESPONSE_SECRET", example["completion"][0]["content"])
        example["metadata"]["annotations"]["private_note"] = "changed"
        self.assertEqual(case, original)
        first = empty_retrieved_context()
        for field in empty:
            first[field].append("changed")
        self.assertEqual(empty_retrieved_context(), empty)

    def test_nonempty_retrieval_is_inserted_and_target_is_preserved(self):
        case = scenario()
        original = copy.deepcopy(case)
        context = retrieved_context()
        retriever = Mock(spec=KGRetriever)
        retriever.retrieve.return_value = context
        example = build_examples([case], retriever=retriever)[0]
        retriever.retrieve.assert_called_once_with(public_case())
        self.assertEqual(prompt_payloads(example), (public_case(), context))
        self.assertEqual(json.loads(example["completion"][0]["content"]), original["target_response"])
        self.assertEqual(example["metadata"]["retrieved_context"], context)
        self.assertEqual(case, original)
        example["metadata"]["retrieved_context"]["retrieved_facts"][0]["source_text_span"] = "changed"
        self.assertEqual(context, retrieved_context())
        self.assertEqual(prompt_payloads(example)[1], context)

    def test_retriever_cannot_mutate_public_prompt_or_original_case(self):
        case = scenario()
        original = copy.deepcopy(case)

        def retrieve_and_mutate(query):
            self.assertEqual(query, public_case())
            query["input"]["user_text"] = "changed"
            query["region_id"] = "region:changed"
            return retrieved_context()

        retriever = Mock(spec=KGRetriever)
        retriever.retrieve.side_effect = retrieve_and_mutate
        example = build_examples([case], retriever=retriever)[0]
        self.assertEqual(prompt_payloads(example), (public_case(), retrieved_context()))
        self.assertEqual(json.loads(example["completion"][0]["content"]), original["target_response"])
        self.assertEqual(case, original)

    def test_nonempty_context_without_evidence_preserves_copied_target(self):
        case = scenario()
        original = copy.deepcopy(case)
        context = retrieved_context()
        context["retrieved_facts"] = []
        context["evidence_fact_ids"] = []
        context["evidence_source_ids"] = []
        retriever = Mock(spec=KGRetriever)
        retriever.retrieve.return_value = context
        example = build_examples([case], retriever=retriever)[0]
        self.assertEqual(prompt_payloads(example)[1], context)
        self.assertEqual(json.loads(example["completion"][0]["content"]), original["target_response"])
        self.assertEqual(case, original)

    def test_default_retriever_can_be_replaced_at_runtime(self):
        replacement = Mock(spec=KGRetriever)
        replacement.retrieve.return_value = retrieved_context()
        with patch("sft.data_preparation.KGRetriever", return_value=replacement) as constructor:
            example = build_examples([scenario()])[0]
        constructor.assert_called_once_with()
        replacement.retrieve.assert_called_once_with(public_case())
        self.assertEqual(prompt_payloads(example)[1], retrieved_context())
        self.assertEqual(json.loads(example["completion"][0]["content"]), scenario()["target_response"])

    def test_default_retrieval_uses_real_kg_with_only_public_input(self):
        case = scenario()
        original = copy.deepcopy(case)
        original_retrieve = KGRetriever.retrieve
        with patch.object(KGRetriever, "retrieve", autospec=True,
                          side_effect=original_retrieve) as retrieve:
            example = build_examples([case])[0]

        retrieve.assert_called_once()
        self.assertIsInstance(retrieve.call_args.args[0], KGRetriever)
        self.assertEqual(retrieve.call_args.args[1], public_case())
        query, context = prompt_payloads(example)
        self.assertEqual(query, public_case())
        self.assertEqual(set(context), set(empty_retrieved_context()))
        self.assertTrue(context["normalized_observations"])
        self.assertTrue(context["candidate_causes"])
        self.assertTrue(context["retrieved_facts"])
        self.assertTrue(context["evidence_fact_ids"])
        self.assertEqual(context, example["metadata"]["retrieved_context"])
        visible = json.dumps({"retriever_input": retrieve.call_args.args[1],
                              "prompt": example["prompt"]})
        for secret in (
            "NESTED_INPUT_SECRET", "ANNOTATION_SECRET", "NATURAL_RESPONSE_SECRET",
            "TARGET_SECRET", "USER_RESPONSE_SECRET", "FACT-PRIVATE", "SRC-PRIVATE",
        ):
            self.assertNotIn(secret, visible)
        self.assertEqual(json.loads(example["completion"][0]["content"]), original["target_response"])
        self.assertEqual(case, original)


if __name__ == "__main__":
    unittest.main()
