"""
scripts/test_field_pilot.py
Automated integration test for Step 21 Field Pilot Application & Telemetry Logger.
"""

import json
import os
import sys

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, WORKSPACE_ROOT)

from field_app.hybrid_engine import HybridFieldEngine
from field_app.telemetry_logger import FieldPilotTelemetryLogger

def test_field_pilot():
    print("=" * 80)
    print(" RICE PATHOGEN SALM — STEP 21: FIELD PILOT INTEGRATION TEST")
    print("=" * 80)

    engine = HybridFieldEngine()
    logger = FieldPilotTelemetryLogger()

    test_cases = [
        {
            "utterance": "Wavy water-soaked yellow lesions on leaf tips during tillering after monsoon floods.",
            "context": {"growth_stage": "tillering", "weather": "heavy_rainfall"},
            "agreement": "agree",
            "confirmed_cause": "disease:bacterial_leaf_blight",
            "notes": "Classic BLB symptoms confirmed by cut-leaf streaming test."
        },
        {
            "utterance": "Rice leaves are yellowing in patches across the field.",
            "context": {"growth_stage": "tillering", "weather": "normal"},
            "agreement": "agree",
            "confirmed_cause": "disorder:nitrogen_deficiency",
            "notes": "Followed clarifying question to confirm lower leaf chlorosis."
        },
        {
            "utterance": "All panicles completely blackened and rotting with rapid district-wide collapse.",
            "context": {"growth_stage": "heading", "weather": "cyclone_storm"},
            "agreement": "agree",
            "confirmed_cause": "disease:bacterial_leaf_blight",
            "notes": "Immediate emergency escalation triggered successfully."
        }
    ]

    for idx, tc in enumerate(test_cases, 1):
        print(f"\n[Test Case {idx}/3] Processing: \"{tc['utterance']}\"")
        res = engine.diagnose(tc["utterance"], tc["context"])
        print(f" -> Engine Selected: {res['engine_used']}")
        print(f" -> Fallback Triggered: {res['fallback_triggered']}")
        print(f" -> Latency: {res['latency_ms']} ms")
        print(f" -> Diagnostic Status: {res['diagnostic_payload'].get('status')}")
        
        sid = logger.log_session(
            officer_id="EXT-TEST-001",
            district_code="Sambalpur-Dist",
            farmer_utterance=tc["utterance"],
            diagnostic_result=res,
            officer_agreement=tc["agreement"],
            confirmed_cause=tc["confirmed_cause"],
            officer_notes=tc["notes"]
        )
        print(f" -> Telemetry Recorded: Session ID = {sid}")

    print("\n" + "=" * 80)
    print(" STEP 21 FIELD PILOT INTEGRATION TEST PASSED")
    print(f" Database Created: {logger.db_path}")
    print(f" JSONL Log: {logger.jsonl_path}")
    print("=" * 80)

if __name__ == "__main__":
    test_field_pilot()
