# Step 6: Differential Diagnosis Graph Modeling

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Knowledge Graph Team  
**Deliverable Scope:** Step 6 (First-Class DiagnosticContrast Nodes, Look-Alike Pairing, Discriminative Matrices, Question Selection Logic)

---

## 1. Why Naive Graph Lookups Fail in Agronomic Triage

A traditional disease graph represents knowledge simply as:  
`Disease -> presentsAs -> Symptom`

For example:
*   `Bacterial Leaf Blight` -> `presentsAs` -> `Leaf yellowing`
*   `Nitrogen Deficiency` -> `presentsAs` -> `Leaf yellowing`
*   `Water Stress` -> `presentsAs` -> `Leaf yellowing`

If a farmer inputs *"Leaves are turning yellow"*, a naive lookup returns all three conditions with equal likelihood and cannot determine what to ask next.

### The SALM Approach: First-Class `DiagnosticContrast` Nodes

Step 6 models **look-alike pairs** as first-class entities in the graph (`contrast:<cond1>_vs_<cond2>`).  
Instead of just linking diseases to symptoms, the graph explicitly stores **what distinguishes look-alikes** and **which observation resolves the ambiguity**.

---

## 2. Complete Differential Matrix for Vertical Slice

Below is the discriminative observation matrix for the 3 look-alike pairs in our initial vertical slice (BLB, Nitrogen Deficiency, Water Stress):

| Feature / Observation | Bacterial Leaf Blight (BLB) | Nitrogen Deficiency | Water-Related Stress | Discriminative Power | Target Clarifying Question |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Lesion Margin & Shape** | Water-soaked, yellow/brown stripes with **wavy edges** | **No lesions**; uniform chlorosis across leaf blade | **No lesions**; uniform pale yellow or scorched tips | **Definitive** for BLB vs Abiotic | `q:q_lesion_margin` |
| **Leaf Age Progression** | Affects upper or middle leaves; spreads along veins | Affects **lowest (older) leaves first** in uniform order | Affects all exposed leaves equally | **High** for N-Deficiency vs BLB | `q:q_older_vs_younger` |
| **Field Spatial Pattern** | **Patchy**; occurs in isolated clusters/waterways | **Uniform** across entire field or soil zone | Correlates with **elevation/soil depth** gradient | **High** for Disease vs Nutrient | `q:q_field_pattern` (in registry) |
| **Cut-Leaf Water Test** | **Cloudy bacterial stream** issues into clear water | **Clear water** (no ooze or turbid streaming) | **Clear water** (no ooze or turbid streaming) | **Definitive Diagnostic Test** | `q:q_water_test` |
| **Leaf Blade Folding** | Leaves remain flat or blighted/dead | Leaves remain flat, narrow, and erect | Leaves **roll/fold inward** like needles | **Definitive** for Water Stress | `q:q_leaf_rolling` (in registry) |
| **Response to Rewatering** | No recovery; lesions continue spreading | No recovery; requires nitrogen fertilizer | **Leaves uncurl and recover** within 24h | **Definitive** for Drought | `q:q_rewatering` (in registry) |

---

## 3. Structural Graph Topology for Differential Contrasts

In `kg/ontology/rice-differentials-v0.1.ttl`, each differential pair is explicitly declared:

### A. Resembles Symmetric Triples
```turtle
disease:bacterial_leaf_blight rice:resembles disorder:nitrogen_deficiency , disorder:water_stress .
disorder:nitrogen_deficiency rice:resembles disease:bacterial_leaf_blight , disorder:water_stress .
disorder:water_stress rice:resembles disease:bacterial_leaf_blight , disorder:nitrogen_deficiency .
```

### B. First-Class Contrast Node (BLB vs Nitrogen Deficiency)
```turtle
contrast:blb_vs_nitrogen_deficiency a rice:DiagnosticContrast ;
    skos:prefLabel "BLB vs Nitrogen Deficiency Contrast"@en ;
    rice:compares disease:bacterial_leaf_blight , disorder:nitrogen_deficiency ;
    rice:differentiatedBy obs:lesion_margin_shape , obs:leaf_age_progression , obs:field_spatial_pattern , obs:bacterial_ooze_test ;
    rice:occursAtStage stage:tillering ;
    prov:wasDerivedFrom source:irri_rice_doctor_2024 .
```

### C. First-Class Contrast Node (BLB vs Water Stress)
```turtle
contrast:blb_vs_water_stress a rice:DiagnosticContrast ;
    skos:prefLabel "BLB vs Water Stress Contrast"@en ;
    rice:compares disease:bacterial_leaf_blight , disorder:water_stress ;
    rice:differentiatedBy obs:leaf_rolling_folding , obs:rewatering_recovery , obs:lesion_margin_shape , obs:bacterial_ooze_test ;
    rice:occursAtStage stage:tillering , stage:heading ;
    prov:wasDerivedFrom source:irri_rice_doctor_2024 .
```

---

## 4. Question Utility Selection Algorithm

When two or more candidates remain plausible, the runtime engine computes question utility using the formula defined in PDF Section 14.4:

$$\text{Question Utility} = \frac{\text{Candidates Separated} \times \text{Observation Reliability} \times \text{Field Observability} \times \text{Safety Importance}}{\text{User Effort}}$$

### Example Utility Ranking for "Yellowing Leaves in Tillering":
1. **Top Question 1 (`q:q_lesion_margin`):** High utility. Easy for farmer to inspect leaf edge (Low effort, high separation power).
2. **Top Question 2 (`q:q_older_vs_younger`):** High utility. Simple visual check of lower vs upper leaves.
3. **Top Question 3 (`q:q_water_test`):** Medium utility / High definitive value. Requires cutting leaf and putting in water glass (Slightly higher effort, but 100% definitive for BLB).

---

## 5. Deliverable Files Created in Workspace

1. **[`kg/ontology/rice-differentials-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-differentials-v0.1.ttl)**  
   OWL graph model containing `rice:resembles` symmetric pairs, `rice:DiagnosticContrast` nodes, discriminative observation links, and provenance attribution.
2. **[`docs/step6_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step6_execution.md)**  
   Detailed execution documentation for Step 6.
