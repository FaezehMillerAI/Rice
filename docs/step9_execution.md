# Step 9: Model Supporting and Contradicting Evidence

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Knowledge Graph Team  
**Deliverable Scope:** Step 9 (Transparent Evidence Modeling, JSON Response Schema Binding, Logical Validation Rules)

---

## 1. Executive Summary & Transparency Mandate

In black-box AI diagnostic systems, the user receives a disease prediction without knowing *why* it was chosen or *what evidence supports or contradicts it*. This undermines trust among extension officers and plant pathologists.

### The Step 9 Transparency Mandate
Step 9 mandates that **every candidate cause evaluated by the SALM engine must break down its evidence into three distinct, mutually exclusive buckets**:
1. **`supporting_observations`:** Confirmed present observations (`state:TRUE`) that match the candidate's diagnostic profile.
2. **`contradicting_observations`:** Confirmed present observations (`state:TRUE`) that contradict the candidate, OR confirmed absent observations (`state:FALSE`) that are required by the candidate.
3. **`missing_distinguishing_observations`:** Unobserved parameters (`state:UNKNOWN`) required to confirm or rule out the candidate.

---

## 2. Evidence Breakdown by Candidate Cause

Below is the evidence classification breakdown across our initial vertical slice:

| Candidate Cause | Confirmed Feature | Observation State | Evidence Bucket Classification | Rationale / Explanation |
| :--- | :--- | :---: | :--- | :--- |
| **Bacterial Leaf Blight** | `leaf_yellowing` | `state:TRUE` | **`supporting_observations`** | Chlorotic halo is a common initial symptom. |
| **Bacterial Leaf Blight** | `water_soaked_wavy_lesion` | `state:TRUE` | **`supporting_observations`** | Pathognomonic lesion border for *Xanthomonas* infection. |
| **Bacterial Leaf Blight** | `water_test_cloudy_streaming`| `state:TRUE` | **`supporting_observations`** | Definitive proof of bacterial vascular ooze. |
| **Bacterial Leaf Blight** | `uniform_older_leaf_chlorosis`| `state:TRUE` | **`contradicting_observations`**| Bottom-leaf uniform yellowing indicates N-deficiency. |
| **Bacterial Leaf Blight** | `water_soaked_wavy_lesion` | `state:FALSE` | **`contradicting_observations`**| Explicit absence of lesions rules out BLB. |
| **Bacterial Leaf Blight** | `lesion_margin_shape` | `state:UNKNOWN`| **`missing_distinguishing`** | Unobserved; requires `q:q_lesion_margin` check. |
| **Nitrogen Deficiency** | `leaf_yellowing` | `state:TRUE` | **`supporting_observations`** | General chlorosis due to lack of nitrogen. |
| **Nitrogen Deficiency** | `uniform_older_leaf_chlorosis`| `state:TRUE` | **`supporting_observations`** | Nitrogen remobilizes strictly from oldest leaves first. |
| **Nitrogen Deficiency** | `uniform_fieldwide_distribution`|`state:TRUE` | **`supporting_observations`** | Soil depletion occurs evenly across field zones. |
| **Nitrogen Deficiency** | `water_soaked_wavy_lesion` | `state:TRUE` | **`contradicting_observations`**| Wavy lesions indicate pathogen, not nutrient deficit. |
| **Water Stress** | `leaf_rolling_folding` | `state:TRUE` | **`supporting_observations`** | Inward leaf curling is a classic drought response. |
| **Water Stress** | `recovers_upon_rewatering` | `state:TRUE` | **`supporting_observations`** | Symptom reversal after rain/watering confirms drought. |
| **Water Stress** | `water_soaked_wavy_lesion` | `state:TRUE` | **`contradicting_observations`**| Lesions indicate bacterial infection, not drought. |

---

## 3. Logical Validation Rules (Section 14.8.4 Rules)

To maintain absolute logical consistency in model responses, the validation engine enforces three automated checks:
1. **Exclusive Assignment Rule:** An observation parameter **cannot appear in both `supporting_observations` and `contradicting_observations`** for the same candidate cause.
2. **Open-World Partition Rule:** An observation parameter in `state:UNKNOWN` **must strictly appear in `missing_distinguishing_observations`** and can never be listed under supporting or contradicting.
3. **Escalation Trigger Rule:** If `contradicting_observations` contains a high-impact contradiction while confidence is `high`, the system triggers an automated logical check warning.

---

## 4. Response Contract Binding (`schemas/response.schema.json`)

The differential array in the JSON response contract enforces this evidence breakdown:

```json
{
  "cause_id": "disease:bacterial_leaf_blight",
  "display_name": "Bacterial leaf blight",
  "cause_type": "pathogen",
  "rank": 1,
  "confidence_band": "medium",
  "supporting_observations": [
    "yellowing",
    "standing_water"
  ],
  "contradicting_observations": [],
  "missing_distinguishing_observations": [
    "lesion_margin_shape",
    "leaf_tip_progression"
  ],
  "distinguishing_checks": [
    "Check whether lesions begin at the leaf tip or margin with wavy edges."
  ]
}
```

---

## 5. Deliverable Files Created in Workspace

1. **[`schemas/response.schema.json`](file:///Users/fs525/Desktop/Rice/schemas/response.schema.json)**  
   Formal JSON Schema validating `differential` items, `supporting_observations`, `contradicting_observations`, and `missing_distinguishing_observations`.
2. **[`registry/evidence-rules.csv`](file:///Users/fs525/Desktop/Rice/registry/evidence-rules.csv)**  
   Master CSV mapping cause IDs, observation IDs, truth states, evidence types, and scientific explanations.
3. **[`kg/ontology/rice-evidence-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-evidence-v0.1.ttl)**  
   W3C Turtle ontology defining `rice:EvidenceBucket` nodes and evidence linking properties.
4. **[`docs/step9_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step9_execution.md)**  
   Detailed execution documentation for Step 9.
