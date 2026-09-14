# Step 17: Synthetic Teacher Training Trajectory Generation (Phase 8.1 SFT Dataset Curation)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Training Data Engineering & Distillation (Phase 8)  
**Deliverable Scope:** Step 17 (1,050 Verified ChatML Teacher Trajectories, Multi-Slice Combinatorial Generator, Leak-Free Quarantine)  
**Teacher Architecture:** Baseline 0 Deterministic Rules & Knowledge Graph Reasoning Engine (`engine/diagnostic_engine.py`) verified by 4-Layer Post-Generation Verifier (`engine/verifier.py`)

---

## 1. Executive Summary & Problem Context

In Step 16, our empirical multi-model challenger bake-off proved that zero-shot Small Language Models (`Qwen2.5-1.5B`, `Llama-3.2-1B`, `SmolLM2-1.7B`) suffer from a **124.0% entity hallucination rate** and **0.0% ontology grounding** because they have not internalized our canonical W3C SKOS terminology, Three-Valued Logic (3VL) arithmetic, and structured JSON response schemas.

To prepare the models for **Phase 8 Supervised Fine-Tuning (SFT / QLoRA)** without human annotation bottlenecks, Step 17 executes **Distillation from Baseline 0**:
1. Uses the symbolic ceiling of Baseline 0 as an **automated expert teacher** to generate structured, scientifically validated diagnostic trajectories.
2. Formats each trajectory with an explicit `<thought>` reasoning chain (Observation Normalization -> 3VL Candidate Scoring -> Evidence Partitioning -> Question Utility Ranking) followed by the validated JSON response contract.
3. Enforces **100% automated quality verification** through `VerificationEngine` and guarantees **0.0% benchmark leakage** against `data/gold_eval_v0.1.jsonl`.

---

## 2. Dataset Composition & Category Distribution

The generator synthesized **1,050 high-diversity training trajectories**, partitioned across 7 distinct operational slices:

| Diagnostic Slice | Target Count | Verified Samples | Core Diagnostic Focus in Training |
| :--- | :---: | :---: | :--- |
| **1. Ambiguous & Under-Specified** | 220 | **220** | Teaches the model to **ask clarifying questions** (`q:q_lesion_margin`, `q:q_older_vs_younger`) when missing distinguishing features. |
| **2. BLB Positive Diagnoses** | 220 | **220** | Teaches recognition of wavy water-soaked lesions, bacterial ooze streaming, and high moisture drivers. |
| **3. Nitrogen Deficiency Positive** | 200 | **200** | Teaches recognition of uniform oldest/lower leaf chlorosis and whole-field soil depletion patterns. |
| **4. Water Stress Positive** | 180 | **180** | Teaches recognition of longitudinal leaf rolling/folding, drought context, and recovery upon re-watering. |
| **5. Negative Evidence (3VL Penalties)** | 100 | **100** | Teaches the model to apply **-3 penalties** and demote candidates when symptoms/signs are confirmed `state:FALSE`. |
| **6. Multi-Turn Clarification Dialogues** | 80 | **80** | Teaches two-turn conversational flow (Turn 1: Clarifying Question -> Turn 2: Follow-up Observation -> Diagnosis). |
| **7. High-Risk Safety Escalations** | 50 | **50** | Teaches immediate trigger recognition (panicle rot, seedling collapse) and mandatory extension escalation. |
| **TOTAL SYNTHESIZED** | **1,050** | **1,050** | **100.0% Verification Pass Rate across all slices.** |

---

## 3. Data Splits & Leak-Free Quarantine

Following Blueprint Section 6.3 and Section 21.2:
* **Training Split (85%):** `892` samples saved in [`data/sft_train_trajectories.jsonl`](file:///Users/faezeh/Desktop/Rice/data/sft_train_trajectories.jsonl) (8.4 MB).
* **Validation Split (15%):** `158` samples saved in [`data/sft_val_trajectories.jsonl`](file:///Users/faezeh/Desktop/Rice/data/sft_val_trajectories.jsonl) (1.5 MB).
* **Quarantined Evaluation Benchmark:** [`data/gold_eval_v0.1.jsonl`](file:///Users/faezeh/Desktop/Rice/data/gold_eval_v0.1.jsonl) (50 gold cases) is strictly isolated with **0.0% lexical or scenario overlap**.

---

## 4. Quality Verification Summary

* **Structural Schema Compliance:** 1,050 / 1,050 (**100.0% Pass**)
* **Safety Constraint Pass Rate:** 1,050 / 1,050 (**0.0% Chemical Violations**)
* **Graph ID Registry Binding Rate:** 1,050 / 1,050 (**100.0% Bound to Canonical Ontologies**)
* **Logical Consistency Check:** 1,050 / 1,050 (**100.0% Pass**)

---

## 5. Deliverable Files in Workspace

1. **[`engine/trajectory_generator.py`](file:///Users/faezeh/Desktop/Rice/engine/trajectory_generator.py)** - Multi-slice combinatorial scenario synthesizer and reasoning formatter.
2. **[`scripts/generate_sft_dataset.py`](file:///Users/faezeh/Desktop/Rice/scripts/generate_sft_dataset.py)** - Dataset generation and verification CLI pipeline.
3. **[`data/sft_train_trajectories.jsonl`](file:///Users/faezeh/Desktop/Rice/data/sft_train_trajectories.jsonl)** - 892 verified training samples (85% split).
4. **[`data/sft_val_trajectories.jsonl`](file:///Users/faezeh/Desktop/Rice/data/sft_val_trajectories.jsonl)** - 158 verified validation samples (15% split).
5. **[`docs/step17_execution.md`](file:///Users/faezeh/Desktop/Rice/docs/step17_execution.md)** - Step 17 execution and dataset report.
