# Step 13: Deterministic Diagnostic Reasoning Engine (Baseline 0)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Reasoning Engine & Baselines  
**Deliverable Scope:** Step 13 (Baseline 0 Engine, 3VL Scorer, Question Utility Selector, Response Contract Serialization)

---

## 1. Executive Summary

As defined in Blueprint Section 10.1 and Section 14.10, before evaluating and fine-tuning language models, we must establish **Baseline 0**: a fully deterministic, rules-and-graph-driven diagnostic reasoning engine.

Baseline 0 serves three critical project functions:
1. **Performance Floor:** Provides an objective lower-bound benchmark for Small Language Model evaluation.
2. **Deterministic Fallback:** Serves as a hard safety fallback whenever an SLM produces invalid JSON, ungrounded IDs, or safety violations.
3. **Training Data Teacher:** Generates grounded, structured reasoning traces for future distillation and preference tuning (Phase 8 & 9).

---

## 2. Reasoning Pipeline Components

`engine/diagnostic_engine.py` implements the full multi-stage inference pipeline:

```
[Farmer Input Text] 
         │
         ▼
[1. SKOS Vernacular Normalizer] ──> Mapped to stable term IDs (symptom:, sign:, env:)
         │
         ▼
[2. 3VL Candidate Scorer] ────────> Computes Candidate Score = 3*sign + 2*sym + 2*env - 3*penalty
         │
         ▼
[3. Question Utility Ranker] ─────> Computes Utility = (Separation * Rel * Obs * Safety) / Effort
         │
         ▼
[4. Evidence Partitioner] ────────> Bins into supporting, contradicting, and missing distinguishing
         │
         ▼
[5. Safety & Escalation Guard] ───> Checks emergency triggers & enforces principle-level actions
         │
         ▼
[Response Contract JSON] ─────────> Validated against schemas/response.schema.json
```

---

## 3. Deliverable Files in Workspace

1. **[`engine/__init__.py`](file:///Users/faezeh/Desktop/Rice/engine/__init__.py)**  
   Engine module interface.
2. **[`engine/diagnostic_engine.py`](file:///Users/faezeh/Desktop/Rice/engine/diagnostic_engine.py)**  
   Full deterministic engine implementation (`DiagnosticEngine`, `diagnose()`).
3. **[`docs/step13_execution.md`](file:///Users/faezeh/Desktop/Rice/docs/step13_execution.md)**  
   Execution documentation for Step 13.
