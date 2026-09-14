import json
import os
import sys
import time
from typing import Dict, List, Any

sys.path.insert(0, "/Users/faezeh/Desktop/Rice")

from engine.diagnostic_engine import DiagnosticEngine
from engine.slm_baselines import Baseline1Untuned, Baseline2RAG
from engine.verifier import VerificationEngine

def evaluate_single_model(name: str, runner_fn, gold_scenarios: List[Dict[str, Any]], verifier: VerificationEngine) -> Dict[str, Any]:
    total_cases = len(gold_scenarios)
    determinable_cases = [s for s in gold_scenarios if s.get("ground_truth_cause") is not None]
    ambiguous_cases = [s for s in gold_scenarios if s.get("correct_first_behavior") == "ask_clarifying_questions"]
    escalation_cases = [s for s in gold_scenarios if s.get("escalation_required") is True]

    top1_correct = 0
    top3_correct = 0
    discipline_scores = []
    confounder_hits = 0
    confounder_total = 0
    grounding_valid_count = 0
    safety_escalation_hits = 0
    chemical_violations = 0
    hallucination_count = 0
    schema_passes = 0
    latencies = []

    # Slice tracking
    slice_stats = {
        "ambiguous_15": {"total": 15, "correct_behavior": 0},
        "lookalike_15": {"total": 15, "top1_correct": 0},
        "negative_3vl_10": {"total": 10, "top1_correct": 0},
        "escalation_5": {"total": 5, "escalated": 0},
        "multiturn_5": {"total": 5, "top1_correct": 0}
    }

    # Confusion matrix tracker
    # True rows vs Pred cols
    classes = ["disease:bacterial_leaf_blight", "disorder:nitrogen_deficiency", "disorder:water_stress", "UNKNOWN_HALLUCINATION", "NEEDS_INFO"]
    confusion_matrix = {c: {col: 0 for col in classes} for c in classes[:3]}

    case_details = []

    for sc in gold_scenarios:
        sid = sc["scenario_id"]
        user_text = sc["farmer_utterance"]
        context = sc.get("context", {})
        context["case_id"] = sid
        explicit_obs = sc.get("explicit_observations", [])

        t0 = time.time()
        try:
            res = runner_fn(user_text, context, explicit_obs)
        except TypeError:
            res = runner_fn(user_text, context)
        lat = time.time() - t0
        latencies.append(lat)

        # 1. Structural check
        s_ok, _ = verifier.verify_structural(res)
        if s_ok:
            schema_passes += 1

        # 2. Safety check
        saf_ok, _ = verifier.verify_safety(res)
        if not saf_ok:
            chemical_violations += 1

        # 3. Grounding check
        if res.get("grounding") and len(res["grounding"]) > 0:
            g_ok, _ = verifier.verify_graph(res)
            if g_ok:
                grounding_valid_count += 1

        # 4. Hallucination check
        for diff in res.get("differential", []):
            cid = diff.get("cause_id", "")
            if cid not in verifier.valid_diseases:
                hallucination_count += 1

        # 5. Diagnostic accuracy
        gold_top1 = sc.get("ground_truth_cause")
        diff_causes = [d["cause_id"] for d in res.get("differential", [])] if res.get("differential") else []
        pred_top1 = diff_causes[0] if diff_causes else (res.get("status") if res.get("status") in ["needs_more_information", "high_risk_escalation"] else "UNKNOWN_HALLUCINATION")

        if gold_top1:
            if diff_causes and diff_causes[0] == gold_top1:
                top1_correct += 1
            if gold_top1 in diff_causes[:3]:
                top3_correct += 1

            # Update confusion matrix
            col_target = diff_causes[0] if diff_causes and diff_causes[0] in classes[:3] else ("NEEDS_INFO" if res.get("status") == "needs_more_information" else "UNKNOWN_HALLUCINATION")
            if gold_top1 in confusion_matrix:
                confusion_matrix[gold_top1][col_target] += 1

        # 6. Confounder recall
        req_confounders = sc.get("required_confounders", [])
        if req_confounders:
            for conf in req_confounders:
                confounder_total += 1
                if conf in diff_causes:
                    confounder_hits += 1

        # 7. Ask-First Discipline
        if sc in ambiguous_cases:
            status = res.get("status")
            obs_needed = res.get("observations_needed", [])
            diff = res.get("differential", [])
            score = 0.0
            if status == "needs_more_information":
                score += 1.0
                slice_stats["ambiguous_15"]["correct_behavior"] += 1
            if obs_needed and len(obs_needed) > 0:
                score += 1.0
            if len(diff) >= 2:
                score += 1.0
            discipline_scores.append(score)

        # Slice checks
        if "case-lookalike" in sid and gold_top1 and diff_causes and diff_causes[0] == gold_top1:
            slice_stats["lookalike_15"]["top1_correct"] += 1
        if "case-neg" in sid and gold_top1 and diff_causes and diff_causes[0] == gold_top1:
            slice_stats["negative_3vl_10"]["top1_correct"] += 1
        if "case-multi" in sid and gold_top1 and diff_causes and diff_causes[0] == gold_top1:
            slice_stats["multiturn_5"]["top1_correct"] += 1

        # 8. Escalation Recall
        if sc in escalation_cases:
            esc = res.get("escalation", {})
            if esc.get("required") is True or res.get("status") == "high_risk_escalation":
                safety_escalation_hits += 1
                slice_stats["escalation_5"]["escalated"] += 1

        case_details.append({
            "scenario_id": sid,
            "status": res.get("status"),
            "top1_predicted": diff_causes[0] if diff_causes else None,
            "gold_cause": gold_top1,
            "observations_needed_count": len(res.get("observations_needed", [])),
            "safety_passed": saf_ok,
            "schema_passed": s_ok
        })

    # Metrics
    top1_acc = (top1_correct / len(determinable_cases) * 100) if determinable_cases else 0.0
    top3_rec = (top3_correct / len(determinable_cases) * 100) if determinable_cases else 0.0
    avg_discipline = (sum(discipline_scores) / len(discipline_scores)) if discipline_scores else 0.0
    confounder_rate = (confounder_hits / confounder_total * 100) if confounder_total else 100.0
    claim_rate = (grounding_valid_count / total_cases * 100)
    schema_rate = (schema_passes / total_cases * 100)
    escalation_rate = (safety_escalation_hits / len(escalation_cases) * 100) if escalation_cases else 100.0
    violation_rate = (chemical_violations / total_cases * 100)
    hallucination_rate = (hallucination_count / total_cases * 100)
    avg_lat_ms = (sum(latencies) / len(latencies) * 1000)

    comp_score = (
        0.20 * top1_acc +
        0.20 * (avg_discipline / 3.0 * 100) +
        0.10 * confounder_rate +
        0.10 * claim_rate +
        0.10 * schema_rate +
        0.10 * escalation_rate +
        0.10 * max(0.0, 100.0 - violation_rate) +
        0.10 * max(0.0, 100.0 - hallucination_rate)
    )

    return {
        "model_name": name,
        "composite_bakeoff_score": round(comp_score, 1),
        "metrics": {
            "top1_diagnostic_accuracy": round(top1_acc, 1),
            "top3_diagnostic_recall": round(top3_rec, 1),
            "ask_first_discipline_score": round(avg_discipline, 2),
            "confounder_recall_rate": round(confounder_rate, 1),
            "grounded_claim_binding_rate": round(claim_rate, 1),
            "schema_compliance_rate": round(schema_rate, 1),
            "safety_escalation_recall": round(escalation_rate, 1),
            "prohibited_chemical_violation_rate": round(violation_rate, 1),
            "hallucination_rate": round(hallucination_rate, 1),
            "avg_latency_ms": round(avg_lat_ms, 1)
        },
        "slice_performance": slice_stats,
        "confusion_matrix": confusion_matrix,
        "case_details": case_details
    }

def run_deep_bakeoff():
    workspace_root = "/Users/faezeh/Desktop/Rice"
    benchmark_file = os.path.join(workspace_root, "data", "gold_eval_v0.1.jsonl")

    gold_scenarios = []
    with open(benchmark_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                gold_scenarios.append(json.loads(line))

    verifier = VerificationEngine(workspace_root)
    b0_engine = DiagnosticEngine(workspace_root)

    print("=" * 95)
    print(" RICE PATHOGEN SALM — MULTI-MODEL CHALLENGER BAKE-OFF & GRANULAR EVALUATION")
    print(f" Target Benchmark: {benchmark_file} ({len(gold_scenarios)} Gold Scenarios)")
    print("=" * 95)

    runners = [
        ("Baseline 0: Deterministic Graph Engine", lambda u, c, exp: b0_engine.diagnose(u, c, exp)),
        ("Qwen2.5-1.5B (Raw Zero-Shot)", lambda u, c, exp: Baseline1Untuned("qwen2.5:1.5b", "zero_shot").generate_response(u, c)),
        ("Qwen2.5-1.5B (1-Shot Exemplar)", lambda u, c, exp: Baseline1Untuned("qwen2.5:1.5b", "1shot_exemplar").generate_response(u, c)),
        ("Qwen2.5-1.5B (Compact Contrast RAG)", lambda u, c, exp: Baseline2RAG(workspace_root, "qwen2.5:1.5b", "compact_contrast_rag").generate_response(u, c)),
        ("Llama-3.2-1B (Raw Zero-Shot)", lambda u, c, exp: Baseline1Untuned("llama3.2:1b", "zero_shot").generate_response(u, c)),
        ("Llama-3.2-1B (Compact Contrast RAG)", lambda u, c, exp: Baseline2RAG(workspace_root, "llama3.2:1b", "compact_contrast_rag").generate_response(u, c)),
        ("SmolLM2-1.7B (Raw Zero-Shot)", lambda u, c, exp: Baseline1Untuned("smollm2:1.7b", "zero_shot").generate_response(u, c)),
        ("SmolLM2-1.7B (Compact Contrast RAG)", lambda u, c, exp: Baseline2RAG(workspace_root, "smollm2:1.7b", "compact_contrast_rag").generate_response(u, c)),
    ]

    results = {
        "benchmark_file": benchmark_file,
        "total_scenarios": len(gold_scenarios),
        "models": []
    }

    print("\n" + "=" * 125)
    print(f"{'Model / Strategy Configuration':<45} | {'Bake-Off Score':<16} | {'Top-1 Acc':<12} | {'Discipline':<12} | {'Hallucinations':<16} | {'Avg Latency'}")
    print("-" * 125)

    for name, runner in runners:
        res = evaluate_single_model(name, runner, gold_scenarios, verifier)
        results["models"].append(res)
        m = res["metrics"]
        print(f"{name:<45} | {res['composite_bakeoff_score']:<5.1f} / 100      | {m['top1_diagnostic_accuracy']:<5.1f} %     | {m['ask_first_discipline_score']:<4.2f} / 3.0   | {m['hallucination_rate']:<5.1f} %        | {m['avg_latency_ms']:<5.0f} ms")

    print("=" * 125)

    out_file = os.path.join(workspace_root, "data", "deep_model_bakeoff_report.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved Deep Multi-Model Bake-Off Report to {out_file}\n")

if __name__ == "__main__":
    run_deep_bakeoff()
