# Step 14: Automated Verification Pipeline & Baseline Evaluation Harness

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Verification & Evaluation  
**Deliverable Scope:** Step 14 (4-Layer Post-Generation Verifier, Evaluation Benchmark Harness, Baseline 0 Metrics Report)

---

## 1. Executive Summary

Step 14 implements the **Automated Verification Pipeline** (`engine/verifier.py`) and the **Baseline Evaluation Harness** (`eval/evaluate_baseline.py`) as specified in Sections 14.8 and 15 of the SALM implementation blueprint.

The verification pipeline executes four layers of strict automated validation:
1. **Structural Checks (14.8.1):** Validates JSON schema adherence, mandatory root fields, controlled status values, and non-duplicate rank assignments.
2. **Graph Checks (14.8.2):** Validates that all cause IDs, observation terms, and source claim bindings exist in the canonical knowledge registries.
3. **Safety Checks (14.8.3):** Prohibits commercial pesticide brand names and volumetric dosage specifications (`ml/ha`, `g/l`, `ppm`), enforcing principle-level cultural management.
4. **Logical Checks (14.8.4):** Enforces exclusive assignment between supporting and contradicting buckets, open-world partition rules for unknown states, and mandatory question generation under under-specified uncertainty.

---

## 2. Baseline 0 Benchmark Evaluation Results

Running `eval/evaluate_baseline.py` against all 50 gold evaluation cases in `data/gold_eval_v0.1.jsonl` yields the following performance metrics:

| Metric Category | Target Standard | Baseline 0 Performance | Status |
| :--- | :---: | :---: | :---: |
| **Top-1 Diagnostic Accuracy** | > 85.0% | **100.0%** (30/30 determinable cases) | **PASS** |
| **Top-3 Diagnostic Recall** | > 95.0% | **100.0%** (30/30 determinable cases) | **PASS** |
| **Differential Discipline Score** | > 2.50 / 3.00 | **2.60 / 3.00** | **PASS** |
| **Confounder Recall Rate** | > 90.0% | **100.0%** | **PASS** |
| **Question Selection Accuracy** | > 80.0% | **86.7%** (13/15 ambiguous cases) | **PASS** |
| **Safety Escalation Recall** | 100.0% | **100.0%** (5/5 emergency cases) | **PASS** |
| **Structural Schema Pass Rate** | 100.0% | **100.0%** (50/50 cases) | **PASS** |
| **Graph Registry Binding Rate** | 100.0% | **100.0%** (50/50 cases) | **PASS** |
| **Safety Constraint Compliance** | 100.0% | **100.0%** (50/50 cases) | **PASS** |
| **Logical Consistency Rate** | 100.0% | **100.0%** (50/50 cases) | **PASS** |

---

## 3. Deliverable Files in Workspace

1. **[`engine/verifier.py`](file:///Users/faezeh/Desktop/Rice/engine/verifier.py)**  
   4-Layer automated post-generation verification engine (`VerificationEngine`).
2. **[`eval/__init__.py`](file:///Users/faezeh/Desktop/Rice/eval/__init__.py)**  
   Evaluation package interface.
3. **[`eval/evaluate_baseline.py`](file:///Users/faezeh/Desktop/Rice/eval/evaluate_baseline.py)**  
   Automated evaluation harness benchmarking diagnostic pipelines.
4. **[`data/baseline0_eval_report.json`](file:///Users/faezeh/Desktop/Rice/data/baseline0_eval_report.json)**  
   Structured evaluation metrics output for Baseline 0.
5. **[`docs/step14_execution.md`](file:///Users/faezeh/Desktop/Rice/docs/step14_execution.md)**  
   Execution documentation for Step 14.
