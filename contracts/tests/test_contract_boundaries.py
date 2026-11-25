"""Compatibility checks for the two shared contracts."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from typing import get_type_hints
import unittest

import engine
import engine.retriever as retriever_module
from contracts.response import (
    MODEL_RESPONSE_INSTRUCTIONS,
    RESPONSE_FIELD_ORDER,
    RESPONSE_JSON_SCHEMA,
    RESPONSE_WIRE_FIELD_ORDER,
    decode_model_response,
    encode_model_response,
    make_model_response,
    parse_response,
    validate_response,
)
from contracts.retrieval import (
    CauseCatalogEntry,
    EvidenceRecord,
    ExplicitObservation,
    ExplicitObservationState,
    KGCatalogSnapshot,
    NormalizedObservation,
    PublicCase,
    QuestionCatalogEntry,
    RETRIEVAL_CONTRACT_VERSION,
    RETRIEVAL_FIELD_ORDER,
    RetrievedFact,
    RetrievedContext,
    SuggestedQuestion,
    decode_retrieved_context,
    empty_retrieved_context,
    encode_retrieved_context,
    ensure_explicit_observations,
    ensure_retrieved_context,
    make_retrieved_context,
    validate_retrieved_context,
)
from engine.prompting import SYSTEM_PROMPT, build_prompt


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def response():
    return make_model_response(
        status="needs_more_information",
        observations_needed=["q:q_lesion_margin"],
        differential=["disease:bacterial_leaf_blight"],
        actions=[],
        escalation_required=False,
        grounding=["FACT_050"],
        safety_flags=[],
        user_response="Please check the leaf margins.",
    )


def retrieved_context():
    return make_retrieved_context(
        normalized_observations=[{
            "concept_id": "symptom:leaf_yellowing",
            "state": "PRESENT",
        }],
        candidate_causes=["disease:bacterial_leaf_blight"],
        supporting_evidence=[{
            "cause_id": "disease:bacterial_leaf_blight",
            "observation_id": "symptom:leaf_yellowing",
            "evidence_type": "Supporting",
            "condition_truth_state": "state:TRUE",
            "explanation": "Yellowing supports the candidate.",
        }],
        contradicting_evidence=[],
        missing_observations=["obs:lesion_margin_shape"],
        suggested_questions=[{
            "question_id": "q:q_lesion_margin",
            "target_observation_id": "obs:lesion_margin_shape",
            "canonical_text": "Are the lesion margins wavy?",
            "farmer_friendly_phrasing": "Do the leaf edges look wavy?",
            "rationale": "The margin shape distinguishes likely causes.",
        }],
        retrieved_facts=[{
            "claim_id": "FACT_050",
            "subject_uri": "disease:bacterial_leaf_blight",
            "predicate_uri": "rice:presentsAs",
            "object_uri": "",
            "source_id": "SOURCE_001",
            "source_section": "Symptoms",
            "source_text_span": "Wavy leaf-margin lesions support BLB.",
        }],
        evidence_fact_ids=["FACT_050"],
        evidence_source_ids=["SOURCE_001"],
    )


class RetrievalContractTests(unittest.TestCase):
    def test_phase10_pipeline_is_absent_from_the_active_tree(self):
        root = REPOSITORY_ROOT
        active_roots = (
            "configs",
            "contracts",
            "engine",
            "eval",
            "field_app",
            "sft",
            "scripts",
        )
        forbidden = (
            "IntegrationPipeline",
            "integration_pipeline",
            "archive.phase10",
        )
        active_suffixes = {".py", ".sh", ".yaml", ".yml"}
        active_paths = [
            path
            for directory in active_roots
            for path in (root / directory).rglob("*")
        ]
        active_paths.extend(root.iterdir())
        references = []
        for path in active_paths:
            relative = path.relative_to(root)
            if (
                not path.is_file()
                or path.suffix not in active_suffixes
                or "tests" in relative.parts
            ):
                continue
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                if marker in text:
                    references.append(f"{relative}: {marker}")
        self.assertEqual(references, [])
        for old_path in (
            "engine/integration_pipeline.py",
            "scripts/run_integration_pipeline.py",
        ):
            self.assertFalse((root / old_path).exists(), old_path)

    def test_v03_nested_types_and_catalog_snapshot_have_explicit_fields(self):
        self.assertEqual(RETRIEVAL_CONTRACT_VERSION, "v0.3")
        for record, fields in (
            (NormalizedObservation, {"concept_id", "state"}),
            (EvidenceRecord, {
                "cause_id", "observation_id", "evidence_type",
                "condition_truth_state", "explanation",
            }),
            (SuggestedQuestion, {
                "question_id", "target_observation_id", "canonical_text",
                "farmer_friendly_phrasing", "rationale",
            }),
            (RetrievedFact, {
                "claim_id", "subject_uri", "predicate_uri", "object_uri",
                "source_id", "source_section", "source_text_span",
            }),
            (CauseCatalogEntry, {
                "id", "canonical_name", "skos_pref_label", "skos_alt_labels",
            }),
            (QuestionCatalogEntry, {
                "question_id", "canonical_text", "farmer_friendly_phrasing",
            }),
            (KGCatalogSnapshot, {
                "retrieval_version", "causes", "questions", "claims",
                "evidence_sources_by_fact", "action_catalog",
            }),
        ):
            with self.subTest(record=record.__name__):
                self.assertEqual(record.__required_keys__, frozenset(fields))

    def test_loading_retriever_does_not_import_deployment_verifier(self):
        root = REPOSITORY_ROOT
        for module in ("engine.retriever", "eval.evaluate_unified", "sft.data_preparation"):
            with self.subTest(module=module):
                check = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            f"import sys; import {module}; "
                            "raise SystemExit('engine.verifier' in sys.modules)"
                        ),
                    ],
                    cwd=root,
                    check=False,
                )
                self.assertEqual(check.returncode, 0)

    def test_explicit_engine_verifier_import_keeps_the_compatibility_exports(self):
        root = REPOSITORY_ROOT
        check = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "from engine import VerificationEngine, verify_slm_output; "
                    "assert VerificationEngine.__module__ == 'engine.verifier'; "
                    "assert verify_slm_output.__module__ == 'engine.verifier'; "
                    "raise SystemExit('engine.verifier' not in sys.modules)"
                ),
            ],
            cwd=root,
            check=False,
        )
        self.assertEqual(check.returncode, 0)
        self.assertIn("VerificationEngine", engine.__all__)
        self.assertIn("verify_slm_output", engine.__all__)

    def test_explicit_observation_matches_the_engine_input_shape(self):
        self.assertEqual(
            ExplicitObservation.__required_keys__,
            frozenset({"term_id", "state"}),
        )
        self.assertEqual(
            get_type_hints(ExplicitObservation)["state"],
            ExplicitObservationState,
        )

    def test_explicit_observation_states_are_validated_and_copied(self):
        value = [
            {"term_id": "symptom:leaf_yellowing", "state": "TRUE"},
            {"term_id": "sign:bacterial_ooze_beads", "state": "FALSE"},
            {"term_id": "sign:water_test_cloudy_streaming", "state": "UNKNOWN"},
        ]
        validated = ensure_explicit_observations(value)
        self.assertEqual(validated, value)
        self.assertIsNot(validated, value)
        self.assertIsNot(validated[0], value[0])
        for invalid_state in ("PRESENT", "ABSENT", "", "true", None):
            with self.subTest(state=invalid_state):
                with self.assertRaisesRegex(
                    ValueError,
                    "state must be TRUE, FALSE, or UNKNOWN",
                ):
                    ensure_explicit_observations([{
                        "term_id": "symptom:leaf_yellowing",
                        "state": invalid_state,
                    }])

    def test_all_public_kg_entry_points_enforce_explicit_observation_states(self):
        root = REPOSITORY_ROOT
        kg = engine.DiagnosticEngine(str(root))
        invalid = [{
            "term_id": "symptom:water_soaked_wavy_lesion",
            "state": "PRESENT",
        }]
        calls = (
            lambda: kg.normalize_observations("", invalid),
            lambda: kg.diagnose("", explicit_obs=invalid),
            lambda: engine.diagnose("", explicit_obs=invalid),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaisesRegex(
                    ValueError,
                    "state must be TRUE, FALSE, or UNKNOWN",
                ):
                    call()

    def test_engine_keeps_compatibility_exports_owned_by_contracts(self):
        self.assertIs(engine.PublicCase, PublicCase)
        self.assertIs(engine.RetrievedContext, RetrievedContext)
        self.assertIs(retriever_module.PublicCase, PublicCase)
        self.assertIs(retriever_module.RetrievedContext, RetrievedContext)

    def test_empty_context_has_exact_fields_and_independent_lists(self):
        first = empty_retrieved_context()
        second = empty_retrieved_context()
        self.assertEqual(tuple(first), RETRIEVAL_FIELD_ORDER)
        first["candidate_causes"].append("changed")
        self.assertEqual(second["candidate_causes"], [])

    def test_factory_and_wire_adapter_do_not_mutate_inputs(self):
        candidates = ["disease:bacterial_leaf_blight"]
        context = make_retrieved_context(
            normalized_observations=[],
            candidate_causes=candidates,
            supporting_evidence=[],
            contradicting_evidence=[],
            missing_observations=[],
            suggested_questions=[],
            retrieved_facts=[],
            evidence_fact_ids=[],
            evidence_source_ids=[],
        )
        candidates.append("changed")
        original = deepcopy(context)
        encoded = encode_retrieved_context(context)
        decoded = decode_retrieved_context(encoded)
        self.assertEqual(decoded, original)
        self.assertEqual(context, original)

    def test_nested_validation_and_cross_references_are_enforced(self):
        valid = retrieved_context()
        self.assertEqual(validate_retrieved_context(valid), [])
        self.assertIs(ensure_retrieved_context(valid), valid)

        mutations = (
            ("invalid observation state", lambda value: value["normalized_observations"][0].update(state="BROKEN"), "normalized_observations[0].state"),
            ("extra nested field", lambda value: value["suggested_questions"][0].update(extra="value"), "extra fields"),
            ("unknown evidence cause", lambda value: value["supporting_evidence"][0].update(cause_id="disease:other"), "absent from candidate_causes"),
            ("unknown evidence observation", lambda value: value["supporting_evidence"][0].update(observation_id="symptom:other"), "absent from normalized_observations"),
            ("evidence state conflict", lambda value: value["supporting_evidence"][0].update(condition_truth_state="state:FALSE"), "conflicts with normalized_observations"),
            ("unknown question target", lambda value: value["suggested_questions"][0].update(target_observation_id="obs:other"), "absent from missing_observations"),
            ("fact ID mismatch", lambda value: value["evidence_fact_ids"].clear(), "claim IDs must equal"),
            ("source ID mismatch", lambda value: value["evidence_source_ids"].clear(), "source IDs must be present"),
        )
        for name, mutate, expected in mutations:
            with self.subTest(name=name):
                invalid = deepcopy(valid)
                mutate(invalid)
                errors = validate_retrieved_context(invalid)
                self.assertTrue(any(expected in error for error in errors), errors)
                with self.assertRaises(ValueError) as error:
                    ensure_retrieved_context(invalid)
                self.assertIn(expected, str(error.exception))

    def test_factory_encode_and_decode_reject_invalid_contexts(self):
        with self.assertRaisesRegex(ValueError, "claim IDs must equal"):
            make_retrieved_context(
                normalized_observations=[],
                candidate_causes=[],
                supporting_evidence=[],
                contradicting_evidence=[],
                missing_observations=[],
                suggested_questions=[],
                retrieved_facts=[],
                evidence_fact_ids=["FACT_050"],
                evidence_source_ids=[],
            )

        invalid = empty_retrieved_context()
        del invalid["candidate_causes"]
        for adapter in (encode_retrieved_context, decode_retrieved_context):
            with self.subTest(adapter=adapter.__name__):
                with self.assertRaisesRegex(ValueError, "Missing fields"):
                    adapter(invalid)

    def test_real_retriever_output_satisfies_the_nested_contract(self):
        retriever = retriever_module.KGRetriever(
            str(REPOSITORY_ROOT)
        )
        context = retriever.retrieve({
            "input": {
                "user_text": "Yellow leaves have wavy water-soaked lesions.",
                "growth_stage_id": "growth_stage:tillering",
            },
        })
        self.assertEqual(validate_retrieved_context(context), [])

    def test_prompt_uses_the_contract_wire_adapter(self):
        public = {
            "input": {
                "user_text": "Yellow leaves",
                "growth_stage_id": None,
                "production_system_id": None,
                "cultivar_id": None,
            },
            "language": "en",
            "region_id": None,
        }
        context = empty_retrieved_context()
        messages = build_prompt(public, context)
        wire_context = json.loads(
            messages[1]["content"].split("\n\nretrieved context:\n", 1)[1]
        )
        self.assertEqual(wire_context, encode_retrieved_context(context))


class ModelResponseContractTests(unittest.TestCase):
    def test_response_round_trips_between_canonical_and_wire_shapes(self):
        canonical = response()
        encoded = encode_model_response(canonical)
        self.assertEqual(tuple(encoded), RESPONSE_WIRE_FIELD_ORDER)
        self.assertEqual(decode_model_response(encoded), canonical)
        parsed, errors = parse_response(json.dumps(encoded))
        self.assertEqual(errors, [])
        self.assertEqual(parsed, canonical)
        self.assertEqual(validate_response(parsed), [])

    def test_schema_and_prompt_share_the_same_contract_fields(self):
        self.assertEqual(
            RESPONSE_JSON_SCHEMA["required"],
            list(RESPONSE_WIRE_FIELD_ORDER),
        )
        self.assertEqual(
            set(RESPONSE_JSON_SCHEMA["properties"]),
            set(RESPONSE_WIRE_FIELD_ORDER),
        )
        self.assertIn(MODEL_RESPONSE_INSTRUCTIONS, SYSTEM_PROMPT)
        field_line = ", ".join(RESPONSE_WIRE_FIELD_ORDER) + "."
        self.assertIn(field_line, MODEL_RESPONSE_INSTRUCTIONS)

    def test_factory_uses_canonical_order_and_copies_lists(self):
        value = response()
        self.assertEqual(tuple(value), RESPONSE_FIELD_ORDER)
        copied = encode_model_response(value)
        copied["grounding"].append("changed")
        self.assertEqual(value["grounding"], ["FACT_050"])

    def test_blank_user_text_and_blank_array_items_are_contract_errors(self):
        for user_text in ("", " \n\t"):
            with self.subTest(user_text=user_text):
                value = response()
                value["user_response"] = user_text
                self.assertTrue(validate_response(value))
        value = response()
        value["grounding"] = ["   "]
        self.assertTrue(validate_response(value))


if __name__ == "__main__":
    unittest.main()
