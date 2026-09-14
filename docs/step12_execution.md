# Step 12: Gold Evaluation Benchmark Dataset (v0.1)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Evaluation & Benchmarking  
**Deliverable Scope:** Step 12 (50 Calibrated Gold Evaluation Scenarios, Multi-Category Distribution, Leakage-Free Stratification)

---

## 1. Executive Summary

As emphasized in Section 6 and Section 21.2 of the SALM implementation blueprint (*"Fine-Tuning Before Evaluation Exists makes objective improvement difficult to measure"*), building a rigorous, leak-free evaluation dataset **before** model training is essential.

Step 12 delivers **`data/gold_eval_v0.1.jsonl`**, containing **50 expert-annotated gold evaluation test cases** formatted according to `schemas/scenario.schema.json`.

---

## 2. Dataset Composition & Category Distribution

The 50 gold evaluation cases are partitioned across 5 critical diagnostic challenges:

| Category | Case Count | Core Diagnostic Challenge | Expected Model Behavior |
| :--- | :---: | :--- | :--- |
| **1. Under-Specified & Ambiguous** | **15** | Broad symptoms (e.g., general yellowing) without distinguishing parameters. | Must **ask high-utility clarifying questions** (`q:q_lesion_margin`, `q:q_older_vs_younger`, `q:q_water_test`); avoid premature diagnosis. |
| **2. Look-Alike Differentials** | **15** | Direct contrast between Bacterial Leaf Blight, Nitrogen Deficiency, and Water Stress with partial or full discriminative features. | Retain correct top-1 cause and include **mandatory abiotic confounders** in differential. |
| **3. Negative Evidence (3VL)** | **10** | Scenarios where key symptoms/signs are confirmed `FALSE` (e.g., no wavy lesions, clear water test). | Apply 3VL penalty (-3) to **demote/exclude ruled-out candidates**. |
| **4. Safety & Escalation Triggers** | **5** | High-risk field conditions (rapid uncontained spread, panicle rot, catastrophic seedling wilt). | Trigger **mandatory emergency escalation** to human plant pathologists; suppress standalone cultural self-treatment. |
| **5. Multi-Turn Dialogues** | **5** | Two-turn interactions where missing data is clarified in Turn 2. | Seamlessly transition from asking clarifying questions to presenting definitive diagnosis. |

---

## 3. Data Leakage Prevention

In accordance with Blueprint Section 6.3, data leakage is strictly prevented:
- Evaluation cases are stratified by **scenario family, disease etiology, and field context**, rather than random syntactic paraphrases.
- Gold evaluation scenarios are isolated in `data/gold_eval_v0.1.jsonl` and permanently quarantined from model pre-training / fine-tuning splits.

---

## 4. Deliverable Files in Workspace

1. **[`data/gold_eval_v0.1.jsonl`](file:///Users/faezeh/Desktop/Rice/data/gold_eval_v0.1.jsonl)**  
   50 gold evaluation cases validated against `schemas/scenario.schema.json`.
2. **[`docs/step12_execution.md`](file:///Users/faezeh/Desktop/Rice/docs/step12_execution.md)**  
   Execution documentation and dataset breakdown for Step 12.
