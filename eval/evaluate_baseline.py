import json
import os
import sys
from typing import Dict, List, Any

# Ensure project root is in sys.path
sys.path.insert(0, "/Users/faezeh/Desktop/Rice")

from engine.diagnostic_engine import DiagnosticEngine
from engine.verifier import VerificationEngine

def run_evaluation(benchmark_file: str = None):
    if benchmark_file is None:
        if len(sys.argv) > 1:
            benchmark_file = sys.argv[1]
        else:
            v2_path = "/Users/faezeh/Desktop/Rice/data/gold_eval_v0.2.jsonl"
            benchmark_file = v2_path if os.path.exists(v2_path) else "/Users/faezeh/Desktop/Rice/data/gold_eval_v0.1.jsonl"

    print("=" * 70)
    print("Rice Pathogen SALM — Deterministic Benchmark Evaluation")
    print(f"Target Benchmark: {os.path.basename(benchmark_file)}")
    print("=" * 70)

    engine = DiagnosticEngine()
    verifier = VerificationEngine()

    with open(benchmark_file, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    total_cases = len(cases)
    top1_correct = 0
    top3_correct = 0
    determ_cases = 0

    discipline_scores = []
    confounder_recalls = []
    question_matches = 0
    ambig_cases = 0

    escalation_correct = 0
    escalation_total = 0

    verifier_passed = 0
    structural_passed = 0
    graph_passed = 0
    safety_passed = 0
    logical_passed = 0

    results = []

    for i, case in enumerate(cases):
        cid = case["scenario_id"]
        utt = case["farmer_utterance"]
        ctx = case["context"]
        explicit = case.get("explicit_observations", [])
        gt_cause = case.get("ground_truth_cause")
        req_conf = set(case.get("required_confounders", []))
        gold_qs = set(case.get("gold_next_questions", []))
        must_esc = case.get("escalation_required", False)
        target_behavior = case.get("correct_first_behavior")

        # Run diagnosis
        response = engine.diagnose(utt, ctx, explicit)

        # Run verification
        v_res = verifier.verify_all(response)
        if v_res["passed"]:
            verifier_passed += 1
        if v_res["structural_valid"]:
            structural_passed += 1
        if v_res["graph_valid"]:
            graph_passed += 1
        if v_res["safety_valid"]:
            safety_passed += 1
        if v_res["logical_valid"]:
            logical_passed += 1

        # 1. Top-1 & Top-3 Diagnostic Accuracy (for determinable cases)
        if gt_cause is not None:
            determ_cases += 1
            diff = response.get("differential", [])
            if diff and diff[0]["cause_id"] == gt_cause:
                top1_correct += 1
            top3_ids = [d["cause_id"] for d in diff[:3]]
            if gt_cause in top3_ids:
                top3_correct += 1

        # 2. Confounder Recall
        if req_conf:
            diff_ids = set(d["cause_id"] for d in response.get("differential", []))
            found_conf = req_conf.intersection(diff_ids)
            confounder_recalls.append(len(found_conf) / len(req_conf))

        # 3. Differential Discipline (for ambiguous cases)
        if target_behavior == "ask_clarifying_questions":
            ambig_cases += 1
            if response["status"] == "needs_more_information" and response["observations_needed"]:
                # Check if top question is in gold questions
                top_q = response["observations_needed"][0]["question_id"]
                if top_q in gold_qs:
                    discipline_scores.append(3)
                    question_matches += 1
                else:
                    discipline_scores.append(2)
            elif response["status"] == "needs_more_information":
                discipline_scores.append(2)
            else:
                discipline_scores.append(0)

        # 4. Safety Escalation
        if must_esc:
            escalation_total += 1
            if response["escalation"]["required"] and response["status"] == "high_risk_escalation":
                escalation_correct += 1
        else:
            if not response["escalation"]["required"]:
                pass

        results.append({
            "scenario_id": cid,
            "status": response["status"],
            "top_candidate": response["differential"][0]["cause_id"] if response["differential"] else None,
            "verification": v_res["passed"]
        })

    # Summary Metrics
    top1_acc = (top1_correct / determ_cases * 100) if determ_cases > 0 else 0
    top3_acc = (top3_correct / determ_cases * 100) if determ_cases > 0 else 0
    mean_discipline = (sum(discipline_scores) / len(discipline_scores)) if discipline_scores else 0
    mean_conf_recall = (sum(confounder_recalls) / len(confounder_recalls) * 100) if confounder_recalls else 0
    q_acc = (question_matches / ambig_cases * 100) if ambig_cases > 0 else 0
    esc_recall = (escalation_correct / escalation_total * 100) if escalation_total > 0 else 0

    print("\n" + "=" * 70)
    print("BENCHMARK EVALUATION RESULTS SUMMARY")
    print("=" * 70)
    print(f"Total Evaluated Cases:              {total_cases}")
    print(f"Determinable Diagnostic Cases:      {determ_cases}")
    print(f"Ambiguous / Clarification Cases:    {ambig_cases}")
    print(f"Emergency Escalation Cases:         {escalation_total}")
    print("-" * 70)
    print(f"Top-1 Diagnostic Accuracy:          {top1_acc:.1f}% ({top1_correct}/{determ_cases})")
    print(f"Top-3 Diagnostic Recall:            {top3_acc:.1f}% ({top3_correct}/{determ_cases})")
    print(f"Differential Discipline Score:      {mean_discipline:.2f} / 3.00")
    print(f"Confounder Recall Rate:             {mean_conf_recall:.1f}%")
    print(f"Question Selection Accuracy:        {q_acc:.1f}% ({question_matches}/{ambig_cases})")
    print(f"Safety Escalation Recall:           {esc_recall:.1f}% ({escalation_correct}/{escalation_total})")
    print("-" * 70)
    print("POST-GENERATION VERIFICATION METRICS (Section 14.8):")
    print(f"Structural Validation Pass Rate:    {(structural_passed/total_cases)*100:.1f}% ({structural_passed}/{total_cases})")
    print(f"Graph Registry ID Pass Rate:        {(graph_passed/total_cases)*100:.1f}% ({graph_passed}/{total_cases})")
    print(f"Safety Constraint Pass Rate:        {(safety_passed/total_cases)*100:.1f}% ({safety_passed}/{total_cases})")
    print(f"Logical Consistency Pass Rate:      {(logical_passed/total_cases)*100:.1f}% ({logical_passed}/{total_cases})")
    print(f"Overall Full Verification Pass Rate:{(verifier_passed/total_cases)*100:.1f}% ({verifier_passed}/{total_cases})")
    print("=" * 70)

    # Save summary report to data/baseline0_eval_report.json
    report = {
        "benchmark": "data/gold_eval_v0.1.jsonl",
        "total_cases": total_cases,
        "metrics": {
            "top1_accuracy": top1_acc,
            "top3_recall": top3_acc,
            "differential_discipline": mean_discipline,
            "confounder_recall": mean_conf_recall,
            "question_selection_accuracy": q_acc,
            "safety_escalation_recall": esc_recall,
            "verification_pass_rate": (verifier_passed / total_cases) * 100
        }
    }
    with open("/Users/faezeh/Desktop/Rice/data/baseline0_eval_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Report saved to data/baseline0_eval_report.json\n")

if __name__ == "__main__":
    run_evaluation()
