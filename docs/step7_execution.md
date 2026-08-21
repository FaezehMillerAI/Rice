# Step 7: Treat Diagnostic Questions as First-Class Objects

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Knowledge Graph Team  
**Deliverable Scope:** Step 7 (First-Class Question Nodes, Utility Metrics, Rationale Links, Execution Integration)

---

## 1. Executive Summary & Operational Shift

In traditional LLM implementations, clarifying questions are generated as unstructured free-text strings by the language model. This creates severe risks in agricultural advisory:
*   The model may generate vague or unanswerable questions (*"Is the plant sick?"*).
*   The model may recommend tests impossible in smallholder settings (*"Perform a PCR test"*).
*   The model cannot explain *why* it is asking a specific question.

### The Step 7 Architecture
In Step 7, **every diagnostic question is modeled as a first-class object (`q:<snake_case_id>`) in the Knowledge Graph**.  
Questions are assigned stable URIs, explicit scientific rationales, user effort scores, field observability metrics, target observation bindings (`rice:observesParameter`), and farmer-friendly phrasings (`skos:hiddenLabel`).

---

## 2. Structured Question Schema & Utility Coefficients

Each question instance in `kg/ontology/rice-questions-v0.1.ttl` is modeled with the following properties:

| Property | Property URI / Type | Function |
| :--- | :--- | :--- |
| **Stable ID** | `q:<snake_case_id>` | Permanent graph URI (e.g. `q:q_lesion_margin`). |
| **Canonical Text** | `skos:definition` | Official diagnostic question text for extension officers. |
| **Farmer Phrasing** | `skos:hiddenLabel` | Vernacular, simplified phrasing for direct farmer triage. |
| **Target Parameter** | `rice:observesParameter` | Link to the exact observation node (`obs:<obs_id>`). |
| **Scientific Rationale**| `rice:questionRationale` | Explicit scientific justification for asking the question. |
| **User Effort Score** | `rice:userEffortScore` (1–3) | 1 = Quick visual inspection; 2 = Simple field test (e.g., water glass test); 3 = Complex lab test. |
| **Field Observability** | `rice:observabilityScore` (1–5) | Ease of observing feature in normal daylight field conditions. |
| **Reliability Score** | `rice:reliabilityScore` (1–5) | Diagnostic reliability of farmer reporting for this feature. |
| **Default Priority** | `rice:defaultPriority` (1–3) | Baseline execution ranking. |

---

## 3. Question Catalog for Vertical Slice

| Question ID | Target Parameter | Scientific Rationale | Effort | Observability | Reliability | Canonical Question Text |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **`q:q_lesion_margin`** | `obs:lesion_margin_shape` | Distinguishes BLB (wavy margins) from Nitrogen Deficiency and Water Stress (no lesions). | **1** | **5** | **5** | *"Are there visible yellow or brown lesions starting at the leaf tip or margins, and do they have wavy edges?"* |
| **`q:q_older_vs_younger`** | `obs:leaf_age_progression` | Identifies Nitrogen Deficiency (uniform lower leaf chlorosis) vs BLB or Water Stress. | **1** | **5** | **5** | *"Are the lowest (older) leaves turning yellow first in a uniform pattern while upper leaves stay green?"* |
| **`q:q_water_test`** | `obs:bacterial_ooze_test` | Definitive sign confirming vascular bacterial infection (BLB). | **2** | **4** | **5** | *"When cut leaf tissue with lesions is placed in a glass of clear water, does a cloudy or milky stream issue into the water?"* |
| **`q:q_leaf_rolling`** | `obs:leaf_rolling_folding` | Definitive physical response to moisture deficit and drought stress. | **1** | **5** | **5** | *"Are the leaf blades rolling or curling inward longitudinally into tube-like shapes?"* |
| **`q:q_rewatering_recovery`**| `obs:rewatering_recovery` | Distinguishes reversible drought stress from permanent pathogen damage. | **1** | **4** | **5** | *"Do the leaves unroll and recover normal appearance within 24 hours after rainfall or irrigation?"* |
| **`q:q_field_spatial_pattern`**| `obs:field_spatial_pattern` | Distinguishes infectious pathogen spread (patchy) from soil nutrient depletion (uniform). | **1** | **4** | **4** | *"Is the yellowing occurring in isolated patches or groups of plants, or is it spread uniformly across the field?"* |

---

## 4. Integration with Question Utility Selection Engine

When the system receives an under-specified case (e.g., *"Leaves are yellowing during tillering"*), the runtime diagnostic engine computes question utility using the formula from Section 14.4 of the implementation blueprint:

$$\text{Question Utility} = \frac{\text{Candidates Separated} \times \text{Observation Reliability} \times \text{Field Observability} \times \text{Safety Importance}}{\text{User Effort}}$$

### Execution Walkthrough:
1. **Retrieve Candidate Pair:** `contrast:blb_vs_nitrogen_deficiency` is active.
2. **Fetch Candidate Questions:** Retrieves `q:q_lesion_margin`, `q:q_older_vs_younger`, and `q:q_water_test`.
3. **Calculate Utility:**
   * `q:q_lesion_margin`: Separation = 2, Reliability = 5, Observability = 5, Effort = 1 $\rightarrow$ **Utility = 50.0** (Rank 1)
   * `q:q_older_vs_younger`: Separation = 2, Reliability = 5, Observability = 5, Effort = 1 $\rightarrow$ **Utility = 50.0** (Rank 2)
   * `q:q_water_test`: Separation = 2, Reliability = 5, Observability = 4, Effort = 2 $\rightarrow$ **Utility = 20.0** (Rank 3)
4. **Generate Structured Response:** The SLM selects `q:q_lesion_margin` as the top priority question to present to the user.

---

## 5. Deliverable Files Created in Workspace

1. **[`registry/question-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/question-registry.csv)**  
   Master CSV catalog of diagnostic questions, target parameter URIs, rationales, effort scores, and farmer-friendly phrasings.
2. **[`kg/ontology/rice-questions-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-questions-v0.1.ttl)**  
   W3C Turtle ontology defining `rice:DiagnosticQuestion` instances, datatype properties (`rice:userEffortScore`, `rice:observabilityScore`, `rice:reliabilityScore`, `rice:questionRationale`), and PROV-O source citations.
3. **[`docs/step7_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step7_execution.md)**  
   Detailed execution documentation for Step 7.
