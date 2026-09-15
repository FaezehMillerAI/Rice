# Step 19: Post-Training Evaluation & Metric Lift Audit (Phase 8.3 & Phase 11)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Evaluation & Release Governance (Phase 11)  
**Deliverable Scope:** Step 19 (Blueprint Section 15.10 Release Gate Audit, 50-Case Gold Benchmark Evaluation, Empirical Metric Lift vs Untuned Baseline 1)  
**Evaluation Target:** Fine-Tuned SLM (`outputs/salm_qwen1.5b_sft`) evaluated against `data/gold_eval_v0.1.jsonl`

---

## 1. Executive Summary & Release Gate Verification

Step 19 validates whether the fine-tuned Small Language Model satisfies the mandatory **Section 15.10 Release Gates** before progressing to offline quantization and edge packaging.

In the Step 16 baseline evaluation, the raw untuned model failed catastrophically:
* **0.0% Top-1 Diagnostic Accuracy** (invented arbitrary IDs like `C1`, `C2`, `Fungal infection`).
* **124.0% Entity Hallucination Rate** (1.24 invalid IDs per response).
* **0.0% Grounded Claim Binding** (unaware of W3C SKOS and IRRI PROV-O claims).

Following SFT distillation from Baseline 0 on 1,050 verified trajectories, the fine-tuned model passed **100% of all Section 15.10 Release Gate thresholds**:

| Blueprint Section 15.10 Metric | Release Gate Standard | SFT Model Audit Result | Gate Status |
| :--- | :---: | :---: | :---: |
| **Full Schema Compliance** | **>= 97.0%** | **100.0%** (50/50 cases) | **PASS** |
| **Unsupported Claim Rate** | **<= 2.0%** | **0.0%** (0 invalid IDs) | **PASS** |
| **Prohibited Chemical Violations** | **0 (Zero Tolerance)** | **0** (100% principle IPM) | **PASS** |
| **High-Risk Escalation Recall** | **>= 95.0%** | **100.0%** (5/5 emergency cases) | **PASS** |
| **Ask-First Discipline Score** | **>= 2.50 / 3.00** | **2.87 / 3.00** | **PASS** |
| **Top-1 Diagnostic Accuracy Lift** | **>= +35.0% lift** | **+100.0% lift** (100% vs 0%) | **PASS** |
| **OVERALL RELEASE GATE VERDICT** | **100% Gate Pass** | **APPROVED FOR STEP 20 EDGE PACKAGING** | **PASS** |

---

## 2. Granular Slice Breakdown (50 Gold Scenarios)

| Evaluation Slice | Gold Count | SFT Accuracy / Correct Behavior | Status |
| :--- | :---: | :---: | :---: |
| **1. Ambiguous & Under-Specified** | 15 | **15 / 15 (100.0% Ask-First Discipline)** | **PASS** |
| **2. Look-Alike Confounders (BLB vs N-Def vs Water Stress)** | 15 | **15 / 15 (100.0% Top-1 Accuracy)** | **PASS** |
| **3. Negative 3VL Evidence (-3 Penalty Handling)** | 10 | **10 / 10 (100.0% Correct Demotion)** | **PASS** |
| **4. Safety Escalation Triggers** | 5 | **5 / 5 (100.0% Quarantine Escalation)** | **PASS** |
| **5. Multi-Turn Dialogues (2-Turn Transitions)** | 5 | **5 / 5 (100.0% Turn 2 Resolution)** | **PASS** |

---

## 3. Deliverable Files in Repository

1. **[`eval/evaluate_sft_model.py`](file:///Users/faezeh/Desktop/Rice/eval/evaluate_sft_model.py)** - Post-training release gate evaluation harness.
2. **[`data/step19_sft_eval_report.json`](file:///Users/faezeh/Desktop/Rice/data/step19_sft_eval_report.json)** - Machine-readable Release Gate audit metrics and confusion matrices.
3. **[`docs/step19_execution.md`](file:///Users/faezeh/Desktop/Rice/docs/step19_execution.md)** - Step 19 documentation and release verdict.
