"""
field_app/field_cli.py
Rice Pathogen SALM — Extension Officer Interactive Field Diagnostic Console (Step 21.3)
"""

import os
import sys

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, WORKSPACE_ROOT)

from field_app.hybrid_engine import HybridFieldEngine
from field_app.telemetry_logger import FieldPilotTelemetryLogger

def run_cli():
    print("=" * 75)
    print(" RICE PATHOGEN SALM — OFFLINE FIELD DIAGNOSTIC SYSTEM (V1.0)")
    print(" Extension Officer Diagnostic Terminal")
    print("=" * 75)

    officer_id = input("Enter Extension Officer ID [e.g. EXT-ODISHA-042]: ").strip() or "EXT-ODISHA-DEFAULT"
    district_code = input("Enter District / Block Code [e.g. Sambalpur]: ").strip() or "Sambalpur"

    engine = HybridFieldEngine()
    logger = FieldPilotTelemetryLogger()

    while True:
        print("\n" + "-" * 75)
        utterance = input("\nEnter Farmer Utterance (or 'q' to quit): ").strip()
        if utterance.lower() in ['q', 'quit', 'exit']:
            print("Exiting Field Terminal. All records safely logged in telemetry/field_pilot.db.")
            break
        if not utterance:
            continue

        growth_stage = input("Growth Stage [tillering/heading/flowering/ripening] (default: tillering): ").strip() or "tillering"
        context = {"growth_stage": growth_stage, "region": "priority-region-1"}

        print("\nAnalyzing observation through Hybrid Safety Gateway...")
        result = engine.diagnose(utterance, context)

        payload = result["diagnostic_payload"]
        print(f"\n[Engine]: {result['engine_used']} (Latency: {result['latency_ms']} ms)")
        if result["fallback_triggered"]:
            print(f"\033[93m[FALLBACK CIRCUIT BREAKER TRIGGERED]: {result['fallback_reason']}\033[0m")

        print(f"Diagnostic Status: \033[1m{payload.get('status')}\033[0m")

        if payload.get("status") == "needs_more_information":
            print("\nClarifying Questions Needed Before Conclusive Diagnosis:")
            for q in payload.get("observations_needed", []):
                print(f"  ? [{q.get('priority', 1)}] {q.get('question')}")

        print("\nDifferential Diagnostic Hypotheses:")
        for cand in payload.get("differential", []):
            print(f"  #{cand.get('rank')} {cand.get('display_name')} (Score: {cand.get('score')}, Confidence: {cand.get('confidence_band')})")
            if cand.get("supporting_observations"):
                print(f"     + Supporting: {', '.join(cand['supporting_observations'])}")
            if cand.get("missing_distinguishing_observations"):
                print(f"     - Missing: {', '.join(cand['missing_distinguishing_observations'])}")

        if payload.get("recommended_actions"):
            print("\nRecommended IPM Cultural Actions:")
            for act in payload["recommended_actions"]:
                print(f"  * [{act.get('action_type', 'cultural').upper()}] {act.get('action')}")

        if payload.get("escalation", {}).get("required"):
            print("\n\033[91m[CRITICAL ESCALATION REQUIRED]: Epidemic quarantine risk. Contact plant pathologist.\033[0m")

        print("\n" + "." * 75)
        agreement = input("Extension Officer Validation [agree/disagree/partial/skip]: ").strip().lower()
        if agreement in ["agree", "disagree", "partial"]:
            conf_cause = input("Confirmed Ground Truth Cause (if verified): ").strip()
            notes = input("Field Notes / Crop Response Observations: ").strip()
            sid = logger.log_session(officer_id, district_code, utterance, result, agreement, conf_cause, notes)
            print(f"Telemetry successfully written to local database (Session ID: {sid}).")
        else:
            sid = logger.log_session(officer_id, district_code, utterance, result)
            print(f"Session telemetry recorded (Session ID: {sid}).")

if __name__ == "__main__":
    run_cli()
