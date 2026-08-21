# Step 8: Represent TRUE, FALSE, and UNKNOWN (Three-Valued Logic)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Knowledge Graph Team  
**Deliverable Scope:** Step 8 (Three-Valued Logic, Open World Assumption, Candidate Penalty Matrix, State Transition Workflow)

---

## 1. Executive Summary & Problem Definition

In conventional binary logic (Closed World Assumption), any fact not explicitly declared is assumed to be `FALSE`. In agricultural disease triage, this assumption is catastrophic:
* If a farmer states *"Leaves are yellowing during tillering"*, they have said nothing about whether lesions exist or whether bottom leaves yellowed first.
* If a binary AI system defaults `lesion_margin_shape = FALSE`, it will **rule out Bacterial Leaf Blight prematurely** and misdiagnose the crop.

### The Step 8 Solution: Three-Valued Logic (3VL)
Step 8 replaces binary true/false flags with **Three-Valued Logic (3VL)** operating under the **Open World Assumption (OWA)**:
1. **`TRUE` (Confirmed Present):** Explicitly confirmed by user observation or diagnostic test.
2. **`FALSE` (Confirmed Absent):** Explicitly confirmed *absent* by user observation or negative test.
3. **`UNKNOWN` (Unobserved / Unmentioned):** Unspecified parameter. **Must never be treated as negative evidence.**

---

## 2. Three-Valued Logic State Definitions

| Truth State ID | SKOS Preferred Label | Operational Definition | Candidate Ranking Score Impact | Action in SALM Triage Engine |
| :--- | :--- | :--- | :---: | :--- |
| **`state:TRUE`** | `TRUE` | Symptom/sign is explicitly confirmed present. | **+2** (Symptom) / **+3** (Sign) | Positive evidence matching candidate profile. |
| **`state:FALSE`** | `FALSE` | Symptom/sign is explicitly confirmed absent. | **-3** (Penalty) | Negative evidence ruling out candidate profile. |
| **`state:UNKNOWN`** | `UNKNOWN` | Symptom/sign is unmentioned, unobserved, or unasked. | **0** (Neutral) | **Never penalizes candidate.** Adds parameter to `missing_observations` list; triggers Step 7 clarifying question. |

---

## 3. Candidate Scoring & Penalty Matrix

The candidate ranking engine computes scores based on 3VL assertions:

$$\text{Candidate Score} = \sum (\text{Matches in } \mathtt{TRUE}) \times W_{\text{match}} - \sum (\text{Matches in } \mathtt{FALSE}) \times W_{\text{penalty}} - \sum (\text{Contradictions in } \mathtt{TRUE}) \times W_{\text{contra}}$$

Where:
* $W_{\text{match}}$ = +2 for standard symptom match; +3 for distinguishing sign match.
* $W_{\text{penalty}}$ = -3 for required symptom confirmed `FALSE`.
* $W_{\text{contra}}$ = -3 for contradicting symptom confirmed `TRUE`.
* $\mathtt{UNKNOWN}$ states contribute **0 score change**, preserving candidate plausibility while flagging missing data.

### Scoring Example Matrix: "Yellowing Leaves in Tillering"

| Candidate Disease | `obs:leaf_yellowing` (`TRUE`) | `obs:lesion_margin_shape` (`UNKNOWN`) | `obs:leaf_age_progression` (`UNKNOWN`) | Candidate Score | Diagnostic Action |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Bacterial Leaf Blight** | +2 | 0 | 0 | **+2** | Retained; `lesion_margin_shape` missing |
| **Nitrogen Deficiency** | +2 | 0 | 0 | **+2** | Retained; `leaf_age_progression` missing |
| **Water Stress** | +2 | 0 | 0 | **+2** | Retained; `leaf_rolling_folding` missing |

#### State Transition: User answers *"No lesions present at all"* (`obs:lesion_margin_shape` $\rightarrow$ `FALSE`)

| Candidate Disease | `obs:leaf_yellowing` (`TRUE`) | `obs:lesion_margin_shape` (`FALSE`) | `obs:leaf_age_progression` (`UNKNOWN`) | Candidate Score | Diagnostic Action |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Bacterial Leaf Blight** | +2 | **-3** | 0 | **-1** | **Demoted / Excluded** |
| **Nitrogen Deficiency** | +2 | 0 | 0 | **+2** | **Top Candidate** |
| **Water Stress** | +2 | 0 | 0 | **+2** | Retained as secondary |

---

## 4. Deliverable Files Created in Workspace

1. **[`registry/logic-state-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/logic-state-registry.csv)**  
   Master CSV registry detailing 3VL truth states, open-world evaluation rules, scoring weights, and clarifying actions.
2. **[`kg/ontology/rice-logic-3vl-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-logic-3vl-v0.1.ttl)**  
   W3C Turtle ontology defining `rice:TruthState` individuals (`state:TRUE`, `state:FALSE`, `state:UNKNOWN`), `rice:ObservationAssertion` nodes, and candidate evaluation properties.
3. **[`docs/step8_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step8_execution.md)**  
   Detailed execution documentation for Step 8.
