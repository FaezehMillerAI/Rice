# Step 11: Scenario Schema Definition & 4-Layer Annotation Guidelines

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Knowledge Graph & Data Engineering  
**Deliverable Scope:** Step 11 (Scenario Response Schema, Formal 4-Layer Annotation Guidelines, Inter-Annotator Agreement Protocols)

---

## 1. Executive Summary

Following the completion of the 10-step Knowledge Graph foundation, Step 11 establishes the data engineering contracts and annotation protocols required to build training and evaluation benchmarks.

Without strict schemas and quality gates, training datasets in agricultural AI suffer from:
1. **Linguistic Drift:** Ambiguous farmer phrasing interpreted inconsistently.
2. **Premature Closure:** AI guessing diseases without asking essential clarifying questions.
3. **Safety Violations:** Recommending illegal, unapproved, or hazardous pesticide dosages.

Step 11 formalizes the **Scenario Schema** (`schemas/scenario.schema.json`) and the **4-Layer Annotation Protocol** (`docs/annotation_guidelines_v0.1.md`) ensuring all test and training cases are grounded in W3C RDF/SKOS terminology and verified by Pathogen SMEs.

---

## 2. Deliverables Summary

1. **[`schemas/scenario.schema.json`](file:///Users/faezeh/Desktop/Rice/schemas/scenario.schema.json)**  
   Formal JSON Schema validating test/gold scenarios, including farmer utterances, growth stages, explicit 3VL observations, unknown features, acceptable differentials, required confounders, and safety bounds.
2. **[`docs/annotation_guidelines_v0.1.md`](file:///Users/faezeh/Desktop/Rice/docs/annotation_guidelines_v0.1.md)**  
   Operational standard operating procedure for the multidisciplinary team across all 4 annotation layers (Metadata, Claim/Relationship, Scenario, Model Response).
3. **[`docs/step11_execution.md`](file:///Users/faezeh/Desktop/Rice/docs/step11_execution.md)**  
   Execution documentation for Step 11.
