# Rice Pathogen SALM — Knowledge Graph Team: Execution Deliverable (Steps 1–3)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Collaboration:** IAAIR × University of Exeter × OpenAg  
**Workstream:** Knowledge Graph & Scientific Reasoning Engine  
**Deliverable Scope:** Steps 1, 2, and 3 (First 2-Week Sprint Target)

---

## STEP 1: Competency Questions (20–30 Core Diagnostic Queries)

Before formalizing the ontology schema, the Knowledge Graph (KG) must be scoped by the competency questions it must answer. Below is the set of 25 structured competency questions categorized by operational requirement:

### Category A: Symptom & Cause Candidate Retrieval
1. **CQ-01:** Which diseases or abiotic disorders cause leaf yellowing during the tillering stage?
2. **CQ-02:** Which rice pathogens present with water-soaked lesions along leaf margins?
3. **CQ-03:** Which abiotic conditions mimic leaf wilting or drying?
4. **CQ-04:** What diseases are favored by stagnant standing water and high relative humidity?
5. **CQ-05:** Which pathogens affect both the leaf blades and leaf sheaths?

### Category B: Look-Alikes & Differential Diagnosis
6. **CQ-06:** What abiotic disorders or diseases look similar to Bacterial Leaf Blight (BLB)?
7. **CQ-07:** What specific field observation distinguishes BLB chlorosis from Nitrogen (N) deficiency?
8. **CQ-08:** How does the spatial distribution (patchy vs. field-wide) distinguish a bacterial pathogen from a soil nutrient deficiency?
9. **CQ-09:** What physical sign (e.g., cut-leaf streaming test / bacterial ooze) definitively separates BLB from waterlogging or nitrogen deficiency?
10. **CQ-10:** What distinguishes leaf rolling caused by water stress from seedling wilt (Kresek) caused by early BLB infection?

### Category C: Clarifying Questions & Missing Observations
11. **CQ-11:** If a farmer reports "yellow leaves," what critical observations are missing before a differential diagnosis can be generated?
12. **CQ-12:** Which diagnostic question has the highest utility to separate BLB from Nitrogen deficiency?
13. **CQ-13:** What specific question should be asked to determine if leaf rolling is due to lack of irrigation versus vascular pathogen infection?
14. **CQ-14:** Which growth stage context must be confirmed to evaluate the severity of leaf chlorosis?

### Category D: Environmental Drivers & Growth Stage Relevancy
15. **CQ-15:** Which conditions are aggravated by high nitrogen application rates during tillering?
16. **CQ-16:** What recent weather events (e.g., storms, high wind, heavy rain) increase the probability of *Xanthomonas oryzae* infection?
17. **CQ-17:** Which symptoms are specific to the tillering stage versus the panicle initiation or heading stages?

### Category E: Principle-Level Management, Safety & Escalation
18. **CQ-18:** What cultural management actions are safe and effective for Bacterial Leaf Blight without specifying commercial pesticide brands or dosages?
19. **CQ-19:** Under what field conditions (e.g., rapid field spread, panicle involvement, unknown wilting) must the system trigger an automatic expert escalation?
20. **CQ-20:** What agronomic practice is recommended when both nitrogen deficiency and BLB are suspected?

### Category F: Provenance, Evidence & Source Attributability
21. **CQ-21:** What authoritative source (e.g., IRRI Rice Doctor, national extension manual) supports the claim that BLB lesions have wavy margins?
22. **CQ-22:** What is the underlying evidence claim ID for the cut-leaf streaming diagnostic test?
23. **CQ-23:** Which facts in the graph are backed by peer-reviewed literature versus practitioner extension notes?
24. **CQ-24:** Has the relationship between nitrogen over-application and BLB severity been approved by a Pathogen Subject Matter Expert (SME)?
25. **CQ-25:** What license and redistribution state applies to the source document supporting the BLB diagnostic pathway?

---

## STEP 2: First Vertical Slice Scope Boundary

To ensure rapid execution and prevent scope creep, the initial v0.1 release strictly restricts the domain scope to **three target conditions**:

### 1. Primary Pathogen Disease: Bacterial Leaf Blight (BLB)
*   **Scientific Name:** *Xanthomonas oryzae* pv. *oryzae*
*   **Key Features:** Water-soaked lesions starting at leaf tips/edges with distinctive wavy margins, yellow-orange chlorotic halo, bacterial ooze under humid conditions, positive cut-leaf water streaming test.

### 2. Primary Abiotic Confounder 1: Nitrogen (N) Deficiency
*   **Key Features:** Uniform pale-yellow chlorosis affecting older (lower) leaves first, erect/small leaves, reduced tillering, field-wide distribution, absence of leaf lesions or bacterial ooze.

### 3. Primary Abiotic Confounder 2: Water-Related Stress
*   **Key Features:** Inward leaf rolling/folding, wilting, leaf tip scorching, elevation/topography-dependent field pattern, symptom reversal following irrigation re-watering.

### Boundary Principles (v1 Constraints):
*   **Input/Output:** Text-based observation triage (no image processing in v1).
*   **Target User:** Agricultural Extension Officers, Plant Clinic Workers, and Field Advisors.
*   **Advisory Boundary:** Principle-level cultural practices only. Strictly prohibits recommending specific chemical pesticide product names or volumetric dosages.
*   **Safety Trigger:** Mandatory escalation to human experts when symptoms involve rapid uncontrollable spread or panicle blight symptoms.

---

## STEP 3: Minimum Ontology Definition (v0.1 Schema & Taxonomy)

The v0.1 ontology (`rice-pathogen-v0.1.ttl`) defines the minimum set of concepts, relationships, and stable ID conventions needed to construct the reasoning graph.

### 1. Core Classes (Concepts)
*   `rice:Disease`: Pathogenic crop diseases (e.g., `disease:bacterial_leaf_blight`).
*   `rice:Pathogen`: Biological causal agents (e.g., `pathogen:xanthomonas_oryzae_pv_oryzae`).
*   `rice:AbioticDisorder`: Non-pathogenic physiological issues (e.g., `disorder:nitrogen_deficiency`, `disorder:water_stress`).
*   `rice:Symptom`: Observable plant disease manifestations (e.g., `symptom:leaf_yellowing`, `symptom:water_soaked_wavy_lesion`).
*   `rice:Sign`: Direct physical evidence of pathogen presence (e.g., `sign:bacterial_ooze_beads`, `sign:water_test_cloudy_streaming`).
*   `rice:PlantPart`: Affected plant anatomy (e.g., `part:leaf`, `part:leaf_sheath`, `part:older_leaves`).
*   `rice:GrowthStage`: Phenological stage (e.g., `stage:tillering`, `stage:heading`).
*   `rice:EnvironmentalCondition`: Ambient field/weather drivers (e.g., `env:high_humidity`, `env:heavy_rainfall`, `env:standing_water`).
*   `rice:FieldDistribution`: Spatial symptom spread across the field (e.g., `field:patchy_distribution`, `field:uniform_fieldwide_distribution`).
*   `rice:DiagnosticObservation`: Normalized observation parameter.
*   `rice:DiagnosticQuestion`: Clarifying question linked to missing parameters.
*   `rice:DiagnosticContrast`: First-class differential node comparing two look-alike conditions.
*   `rice:ManagementAction`: Safe agronomic principle-level recommendation.
*   `rice:EscalationTrigger`: Hard safety rule triggering referral to human experts.
*   `rice:SourceDocument`: Provenance record of extension/peer-reviewed document.
*   `rice:EvidenceClaim`: Atomic fact snippet extracted from source document.

### 2. Core Relationship Vocabulary (Object Properties)
*   `causes` / `causedBy`: Biological etiology.
*   `presentsAs`: Links disease/disorder to symptoms.
*   `hasSign`: Links disease to physical diagnostic signs.
*   `affectsPlantPart`: Anatomical target.
*   `favoredBy`: Environmental or seasonal drivers.
*   `occursAtStage`: Growth stage constraints.
*   `hasFieldDistribution`: Spatial pattern linkage.
*   `resembles`: Diagnostic look-alike pairing.
*   `compares`: Connects conditions within a `DiagnosticContrast` node.
*   `differentiatedBy`: Links contrast pair to discriminating observations.
*   `observesParameter`: Connects diagnostic questions to observations.
*   `managedBy`: Connects condition to safe management action.
*   `escalateWhen`: Connects condition to emergency escalation criteria.
*   `supportedBy`: Direct provenance link to atomic evidence claim.

### 3. Stable ID Specification
*   Diseases: `disease:<snake_case>` (e.g., `disease:bacterial_leaf_blight`)
*   Disorders: `disorder:<snake_case>` (e.g., `disorder:nitrogen_deficiency`)
*   Pathogens: `pathogen:<snake_case>` (e.g., `pathogen:xanthomonas_oryzae_pv_oryzae`)
*   Symptoms: `symptom:<snake_case>` (e.g., `symptom:water_soaked_wavy_lesion`)
*   Signs: `sign:<snake_case>` (e.g., `sign:water_test_cloudy_streaming`)
*   Questions: `q:<snake_case>` (e.g., `q:q_lesion_margin`)
*   Contrasts: `contrast:<cond1>_vs_<cond2>` (e.g., `contrast:blb_vs_nitrogen_deficiency`)
*   Sources: `source:<source_id>` (e.g., `source:irri_rice_doctor_2024`)
*   Claims: `claim:<claim_id>` (e.g., `claim:claim_blb_001`)

---

## File Deliverables Location in Workspace
1. **W3C Turtle Ontology File:** [`/Users/fs525/Desktop/Rice/kg/ontology/rice-pathogen-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-pathogen-v0.1.ttl)
2. **Execution Documentation:** [`/Users/fs525/Desktop/Rice/docs/step1_to_3_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step1_to_3_execution.md)
