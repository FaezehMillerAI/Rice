from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from contracts.response import (
    RESPONSE_JSON_SCHEMA,
    RESPONSE_WIRE_FIELD_ORDER,
)
from field_app.field_cli import format_payload
from field_app.hybrid_engine import HybridFieldEngine
from field_app.telemetry_logger import FieldPilotTelemetryLogger


def compact_response(**updates):
    value = {
        "status": "needs_more_information",
        "observations_needed": ["q:q_lesion_margin"],
        "differential": ["disease:bacterial_leaf_blight"],
        "actions": [],
        "escalation_required": False,
        "grounding": ["FACT_050"],
        "safety_flags": [],
        "user_response": (
            "The cause is uncertain. Please check whether there are wavy "
            "lesions along the leaf margins."
        ),
    }
    value.update(updates)
    return value


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class FakeRetriever:
    version = "test-retrieval"

    def retrieve(self, _case):
        return {
            "normalized_observations": [],
            "candidate_causes": ["disease:bacterial_leaf_blight"],
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "missing_observations": ["obs:lesion_margin_shape"],
            "suggested_questions": [
                {
                    "question_id": "q:q_lesion_margin",
                    "target_observation_id": "obs:lesion_margin_shape",
                    "canonical_text": "Are there wavy lesions along the leaf margins?",
                    "farmer_friendly_phrasing": "Do the leaf edges have wavy lesions?",
                    "rationale": "Lesion margins distinguish the likely causes.",
                }
            ],
            "retrieved_facts": [{
                "claim_id": "FACT_050",
                "subject_uri": "disease:bacterial_leaf_blight",
                "predicate_uri": "rice:presentsAs",
                "object_uri": "symptom:water_soaked_wavy_lesion",
                "source_id": "SOURCE_001",
                "source_section": "Symptoms",
                "source_text_span": "Wavy leaf-margin lesions support BLB.",
            }],
            "evidence_fact_ids": ["FACT_050"],
            "evidence_source_ids": ["SOURCE_001"],
        }


class FakeKG:
    def __init__(self):
        self.calls = 0
        self.diseases = {
            "disease:bacterial_leaf_blight": {
                "canonical_name": "Bacterial leaf blight",
            }
        }
        self.questions = {
            "q:q_lesion_margin": {
                "canonical_text": "Are there wavy lesions along the leaf margins?",
            }
        }

    def get_management_actions(self, _cause, _escalated):
        return []

    def diagnose(self, *_args, **_kwargs):
        self.calls += 1
        return {
            "status": "needs_more_information",
            "observations_needed": [
                {
                    "question_id": "q:q_lesion_margin",
                    "canonical_text": "Are there wavy lesions along the leaf margins?",
                }
            ],
            "differential": [
                {
                    "cause_id": "disease:bacterial_leaf_blight",
                    "display_name": "Bacterial leaf blight",
                }
            ],
            "recommended_actions": [],
            "escalation": {"required": False, "triggers": []},
            "grounding": [{"claim_id": "FACT_050"}],
        }


class RejectingVerifier:
    def verify_all(self, _response):
        return {
            "passed": False,
            "errors": ["test verifier rejection"],
        }


class FieldEngineTests(unittest.TestCase):
    def make_engine(self, raw_output=None, *, urlopen=None, verifier=None):
        kg = FakeKG()
        if urlopen is None:
            response = {
                "response": raw_output
                if raw_output is not None
                else json.dumps(compact_response()),
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 100,
                "eval_count": 80,
            }
            calls = []

            def urlopen(request, timeout):
                calls.append((request, timeout))
                return FakeResponse(response)
        else:
            calls = []
        engine = HybridFieldEngine(
            ollama_model="rice-qwen3-4b:q4_k_m",
            kg_engine=kg,
            retriever=FakeRetriever(),
            verifier=verifier,
            urlopen=urlopen,
        )
        return engine, kg, calls

    def test_valid_compact_output_uses_exact_tuned_tag_without_fallback(self):
        engine, kg, calls = self.make_engine()
        result = engine.diagnose("Rice leaves are yellow.")
        self.assertEqual(result["engine_used"], "edge_slm")
        self.assertFalse(result["fallback_triggered"])
        self.assertTrue(result["contract_validation"]["passed"])
        self.assertTrue(result["verification"]["passed"])
        self.assertTrue(result["verification"]["structural_valid"])
        self.assertTrue(result["verification"]["graph_grounded"])
        self.assertEqual(result["diagnostic_payload"], compact_response())
        self.assertEqual(kg.calls, 0)
        request_payload = json.loads(calls[0][0].data)
        self.assertEqual(request_payload["model"], "rice-qwen3-4b:q4_k_m")
        self.assertIsInstance(request_payload["format"], dict)
        self.assertEqual(request_payload["system"].splitlines()[0], "You are a rice crop diagnostic assistant. Use the public case and any supplied evidence to choose a cautious first response. Ask for distinguishing observations when the cause is uncertain.")

    def test_invalid_explicit_observation_state_fails_before_model_or_kg(self):
        engine, kg, calls = self.make_engine()
        with self.assertRaisesRegex(
            ValueError,
            "state must be TRUE, FALSE, or UNKNOWN",
        ):
            engine.diagnose(
                "Rice leaves are yellow.",
                explicit_observations=[{
                    "term_id": "symptom:leaf_yellowing",
                    "state": "PRESENT",
                }],
            )
        self.assertEqual(calls, [])
        self.assertEqual(kg.calls, 0)

    def test_invalid_outputs_each_trigger_one_compact_kg_fallback(self):
        invalid = {
            "malformed": "not json",
            "duplicate": '{"status":"needs_more_information","status":"provisional_assessment"}',
            "extra": json.dumps(compact_response(extra="not allowed")),
            "status_mismatch": json.dumps(
                compact_response(status="escalation_required", escalation_required=False)
            ),
        }
        for name, raw_output in invalid.items():
            with self.subTest(name=name):
                engine, kg, _ = self.make_engine(raw_output)
                result = engine.diagnose("Rice leaves are yellow.")
                self.assertEqual(result["engine_used"], "kg_deterministic_fallback")
                self.assertTrue(result["fallback_triggered"])
                self.assertIn("SLM runtime/delivery-check failure", result["fallback_reason"])
                self.assertEqual(kg.calls, 1)
                self.assertTrue(result["contract_validation"]["passed"])
                self.assertTrue(result["verification"]["passed"])
                self.assertEqual(
                    set(result["diagnostic_payload"]),
                    {
                        "status", "observations_needed", "differential", "actions",
                        "escalation_required", "grounding", "safety_flags", "user_response",
                    },
                )

    def test_maintained_verifier_can_reject_and_trigger_fallback(self):
        engine, kg, _ = self.make_engine(verifier=RejectingVerifier())

        result = engine.diagnose("Rice leaves are yellow.")

        self.assertEqual(result["engine_used"], "kg_deterministic_fallback")
        self.assertTrue(result["fallback_triggered"])
        self.assertIn("test verifier rejection", result["fallback_reason"])
        self.assertEqual(kg.calls, 1)

    def test_transport_error_triggers_one_fallback(self):
        def unavailable(*_args, **_kwargs):
            raise urllib.error.URLError("offline")

        engine, kg, _ = self.make_engine(urlopen=unavailable)
        result = engine.diagnose("Rice leaves are yellow.")
        self.assertTrue(result["fallback_triggered"])
        self.assertIn("request failed", result["fallback_reason"])
        self.assertEqual(kg.calls, 1)

    def test_default_model_uses_environment_and_explicit_argument_wins(self):
        with patch.dict(os.environ, {"RICE_OLLAMA_MODEL": "rice-env:quant"}):
            engine = HybridFieldEngine(
                kg_engine=FakeKG(), retriever=FakeRetriever(), urlopen=lambda *_a, **_k: None
            )
            self.assertEqual(engine.ollama_model, "rice-env:quant")
            explicit = HybridFieldEngine(
                ollama_model="rice-explicit:quant",
                kg_engine=FakeKG(),
                retriever=FakeRetriever(),
                urlopen=lambda *_a, **_k: None,
            )
            self.assertEqual(explicit.ollama_model, "rice-explicit:quant")

    def test_preflight_requires_exact_installed_tag_without_pull(self):
        routes = []

        def urlopen(request, timeout):
            routes.append(request.full_url)
            if request.full_url.endswith("/api/version"):
                return FakeResponse({"version": "test"})
            if request.full_url.endswith("/api/tags"):
                return FakeResponse({"models": [{"name": "qwen2.5:1.5b"}]})
            self.fail("/api/show must not be called for a missing exact tag")

        engine, _kg, _ = self.make_engine(urlopen=urlopen)
        with self.assertRaisesRegex(RuntimeError, "not installed"):
            engine.check_ollama_model()
        self.assertEqual(len(routes), 2)


class FieldOutputAndTelemetryTests(unittest.TestCase):
    def test_runtime_schema_is_generated_by_the_response_contract(self):
        self.assertEqual(
            RESPONSE_JSON_SCHEMA["required"],
            list(RESPONSE_WIRE_FIELD_ORDER),
        )
        self.assertEqual(
            set(RESPONSE_JSON_SCHEMA["properties"]),
            set(RESPONSE_WIRE_FIELD_ORDER),
        )

    def test_compact_string_lists_render_without_dict_access(self):
        rendered = format_payload(compact_response(actions=["action:monitor_field"]))
        self.assertIn("q:q_lesion_margin", rendered)
        self.assertIn("disease:bacterial_leaf_blight", rendered)
        self.assertIn("action:monitor_field", rendered)
        self.assertIn("FACT_050", rendered)

    def test_telemetry_records_compact_top_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "telemetry.db"
            log = root / "telemetry.jsonl"
            logger = FieldPilotTelemetryLogger(
                str(database), str(log), hmac_secret=b"test-only-secret"
            )
            result = {
                "engine_used": "edge_slm",
                "fallback_triggered": False,
                "latency_ms": 12.3,
                "diagnostic_payload": compact_response(),
            }
            logger.log_session("officer", "district", "yellow leaves", result)
            with sqlite3.connect(database) as connection:
                top_one = connection.execute(
                    "SELECT top1_cause FROM field_telemetry"
                ).fetchone()[0]
            self.assertEqual(top_one, "disease:bacterial_leaf_blight")
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
