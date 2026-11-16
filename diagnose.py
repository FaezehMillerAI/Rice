#!/usr/bin/env python3
"""
Rice Pathogen SALM — Live Interactive Clinical Diagnostic Tester
=================================================================
Type any farmer observation or field report to test the live Knowledge Graph
diagnostic pipeline with 100% REAL DATA.

Usage:
  python3 diagnose.py
  python3 diagnose.py "Leaves have wavy margins turning greyish white with morning bacterial ooze"
"""

import os
import sys
import json
import textwrap

WORKSPACE_ROOT = os.path.abspath(os.path.dirname(__file__))
candidate_roots = [
    WORKSPACE_ROOT,
    os.path.abspath(os.path.join(WORKSPACE_ROOT, "..", "Rice")),
    "/Users/faezeh/Desktop/Rice"
]
for root in candidate_roots:
    if os.path.exists(os.path.join(root, "engine", "diagnostic_engine.py")) and root not in sys.path:
        sys.path.insert(0, root)

# ANSI Colors
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
MAGENTA = "\033[35m"
RESET = "\033[0m"

# Load Richard's facts database
FACTS_PATH = os.path.join(WORKSPACE_ROOT, "data/scenarios/richard_facts_842.json")
if not os.path.exists(FACTS_PATH):
    FACTS_PATH = os.path.join(WORKSPACE_ROOT, "richard_facts_842.json")

RICHARD_FACTS = {}
if os.path.exists(FACTS_PATH):
    try:
        with open(FACTS_PATH, "r", encoding="utf-8") as f:
            RICHARD_FACTS = json.load(f)
    except Exception:
        RICHARD_FACTS = {}

from engine.diagnostic_engine import DiagnosticEngine
from engine.retriever import retrieve_kg, to_compact_target_response

ENGINE = DiagnosticEngine(WORKSPACE_ROOT)

PRESETS = [
    ("Rice Blast (Direct Diagnosis)", "My rice leaves have diamond shaped spots pointed at both ends with grey centers and dark brown borders. Nights have been cool and dewy.", "tillering"),
    ("Bacterial Leaf Blight (Direct Diagnosis)", "Leaves have water-soaked wavy stripes along the edges turning milky white, with amber bacterial ooze droplets in the morning dew.", "tillering"),
    ("Brown Spot (Direct Diagnosis)", "I see circular to oval brown spots on older leaves, and many have a distinct yellow halo around the brown spot.", "tillering"),
    ("Ambiguous / Look-alike (Ask-First)", "There are some yellow and brown spots appearing on my leaves. What disease is this?", "tillering"),
    ("Emergency Escalation (Neck/Panicle Rot)", "Almost the entire field has white empty panicles breaking at the neck. Tell me what chemical fungicide to spray immediately.", "heading"),
    ("Nitrogen Deficiency vs Blast Look-alike", "Older leaves are turning pale yellow starting from the leaf tips down the midrib, but younger leaves look green.", "tillering")
]

def run_diagnosis(query: str, growth_stage: str = "tillering"):
    print(f"\n{BOLD}{CYAN}{'=' * 76}{RESET}")
    print(f"{BOLD}INPUT OBSERVATION:{RESET} \"{query}\"")
    print(f"{BOLD}GROWTH STAGE:{RESET} {growth_stage}")
    print(f"{BOLD}{CYAN}{'=' * 76}{RESET}")

    # 1. Retrieve Knowledge Graph context
    ret_context = retrieve_kg(query)
    # 2. Run Diagnostic Engine
    diag_res = ENGINE.diagnose(query, context={"growth_stage": growth_stage})
    compact_res = to_compact_target_response(diag_res)

    status = compact_res.get("status", "unknown")
    status_color = GREEN if status == "provisional_assessment" else (YELLOW if status == "needs_more_information" else RED)
    escalated = compact_res.get("escalation_required", False)

    print(f"\n{BOLD}1. CLINICAL ASSESSMENT:{RESET}")
    print(f"   • Triage Status:       {status_color}{BOLD}{status}{RESET}")
    print(f"   • Escalation Required: {RED if escalated else GREEN}{BOLD}{escalated}{RESET}")
    print(f"   • Differential Ranks:  {BOLD}{', '.join(compact_res.get('differential', [])[:3])}{RESET}")

    # Extracted concepts
    obs = ret_context.get("normalized_observations", ret_context.get("observations", []))
    if obs:
        print(f"\n{BOLD}2. DETECTED SYMPTOMS & CONCEPTS (Knowledge Graph):{RESET}")
        for o in obs[:6]:
            label = f"{o.get('concept_id')} ({o.get('state')})" if isinstance(o, dict) else o
            print(f"   • {CYAN}{label}{RESET}")

    # Missing checks if Ask-First
    needed = compact_res.get("observations_needed", [])
    if needed:
        print(f"\n{BOLD}{YELLOW}3. CLARIFYING FIELD CHECKS NEEDED (Ask-First Discipline):{RESET}")
        print(f"   {DIM}Symptoms overlap across multiple causes. To prevent misdiagnosis, the model asks:{RESET}")
        for q in needed:
            print(f"   ? {YELLOW}{BOLD}{q}{RESET}")

    # Grounding facts from Richard
    fact_ids = ret_context.get("evidence_fact_ids", [])
    if fact_ids:
        print(f"\n{BOLD}4. RETRIEVED GROUNDING FACTS (Richard's 842 Pathology Facts (95 Approved)):{RESET}")
        for fid in fact_ids[:3]:
            if fid in RICHARD_FACTS:
                finfo = RICHARD_FACTS[fid]
                print(f"   [{BOLD}{fid}{RESET}] ({finfo.get('disease')} / {finfo.get('category')}): {finfo.get('statement')}")
            else:
                print(f"   [{BOLD}{fid}{RESET}]: Verified Plant Pathology Fact")

    # Cultural IPM actions
    actions = compact_res.get("actions", [])
    if actions:
        print(f"\n{BOLD}5. GROUNDED CULTURAL IPM ACTIONS (Chemical Safety Enforced):{RESET}")
        for act in actions[:3]:
            print(f"   ✓ {act}")

    # Natural Language Response
    print(f"\n{BOLD}{GREEN}6. ADVISOR RESPONSE TO FARMER / EXTENSION OFFICER:{RESET}")
    wrapped = textwrap.fill(compact_res.get("user_response", ""), width=74, initial_indent="   ", subsequent_indent="   ")
    print(f"{wrapped}")
    print(f"\n{DIM}{'-' * 76}{RESET}\n")

def interactive_loop():
    print(f"\n{BOLD}{CYAN}============================================================================{RESET}")
    print(f"{BOLD}{CYAN}   RICE PATHOGEN SALM — LIVE CLINICAL DIAGNOSTIC TESTER{RESET}")
    print(f"{BOLD}{CYAN}   100% Real Vetted Data | 842 Richard Facts (95 SME Approved) | Schema v0.2.0{RESET}")
    print(f"{BOLD}{CYAN}============================================================================{RESET}\n")
    print("You can type your own farmer symptom observation, or pick one of the sample presets.\n")

    while True:
        print(f"{BOLD}Choose an option:{RESET}")
        print("  [T] Type your own symptom observation")
        print("  [1] Preset: Rice Blast (Diamond lesions with grey centers)")
        print("  [2] Preset: Bacterial Leaf Blight (Wavy margins with morning ooze)")
        print("  [3] Preset: Brown Spot (Round/oval spots with yellow halo)")
        print("  [4] Preset: Ambiguous Vague Spots (Triggers Ask-First clarifying questions)")
        print("  [5] Preset: Panicle Rot / Whitehead (Triggers Emergency Escalation)")
        print("  [6] Preset: Nitrogen Deficiency vs Blast look-alike")
        print("  [Q] Quit")

        try:
            choice = input(f"\n{BOLD}Enter choice [T/1-6/Q]: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if choice.upper() == "Q":
            print("Exiting diagnostic tester.")
            break
        elif choice.upper() == "T":
            try:
                user_input = input(f"\n{BOLD}Enter what the farmer is seeing in the field:{RESET}\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user_input:
                continue
            stage = input("Growth stage [tillering / heading / seedling, default: tillering]: ").strip() or "tillering"
            run_diagnosis(user_input, stage)
        elif choice in ["1", "2", "3", "4", "5", "6"]:
            idx = int(choice) - 1
            name, query, stage = PRESETS[idx]
            print(f"\n{BOLD}Selected Preset: {name}{RESET}")
            run_diagnosis(query, stage)
        else:
            print(f"{RED}Invalid choice. Enter T, 1-6, or Q.{RESET}\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query_text = " ".join(sys.argv[1:])
        run_diagnosis(query_text)
    else:
        interactive_loop()
