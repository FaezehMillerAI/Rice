# Step 5: Relationship Types & Formal Semantics

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Knowledge Graph Team  
**Deliverable Scope:** Step 5 (Relationship Vocabulary, Domain/Range Constraints, Property Axioms, Differential Logic)

---

## 1. Relationship Categories & Formal Semantics

The Knowledge Graph relationships are organized into 5 functional clusters. Every property is formally defined with OWL domain and range constraints to ensure semantic strictness.

### A. Etiological & Phenotypic Relationships
Used to model the biological cause, anatomical site, and observable physical manifestations of crop diseases.

| Relationship Property | Domain | Range | Inverse / Symmetry | Description |
| :--- | :--- | :--- | :--- | :--- |
| `rice:causes` | `rice:Pathogen` | `rice:Disease` | `rice:causedBy` | Links a pathogen to the disease it induces. |
| `rice:causedBy` | `rice:Disease` | `rice:Pathogen` | `rice:causes` | Links a disease to its underlying causal pathogen. |
| `rice:presentsAs` | `rice:Disease` / `Disorder` | `rice:Symptom` | None | Connects a condition to an observable symptom. |
| `rice:hasSign` | `rice:Disease` | `rice:Sign` | None | Links a disease to physical signs or diagnostic test outputs. |
| `rice:affectsPlantPart` | `rice:Disease` / `Disorder` | `rice:PlantPart` | None | Anatomical location (e.g. leaf, sheath, panicle). |
| `rice:occursAtStage` | `rice:Disease` / `Disorder` | `rice:GrowthStage` | None | Crop growth stage constraint (e.g. tillering). |
| `rice:hasFieldDistribution`| `rice:Disease` / `Disorder` | `rice:FieldDistribution`| None | Spatial spread pattern across paddy (e.g. patchy). |

### B. Environmental & Epidemiological Relationships
Used to model weather, soil, and management drivers that increase or decrease disease incidence.

| Relationship Property | Domain | Range | Description |
| :--- | :--- | :--- | :--- |
| `rice:favoredBy` | `rice:Disease` / `Disorder` | `rice:EnvironmentalCondition` | Weather or field conditions promoting the disease (e.g. high humidity, standing water). |
| `rice:suppressedBy` | `rice:Disease` / `Disorder` | `rice:EnvironmentalCondition` | Conditions inhibiting disease development. |
| `rice:applicableInRegion`| `owl:Thing` | `rice:Region` | Geographic applicability scope constraint. |

### C. Diagnostic & Differential Relationships
Used by the Small Language Model to rank candidate diseases, identify look-alikes, and ask high-utility clarifying questions.

| Relationship Property | Domain | Range | Axioms | Description |
| :--- | :--- | :--- | :--- | :--- |
| `rice:resembles` | `rice:Disease` / `Disorder` | `rice:Disease` / `Disorder` | `owl:SymmetricProperty` | Pairs look-alike conditions (e.g. BLB resembles N-deficiency). |
| `rice:compares` | `rice:DiagnosticContrast` | `rice:Disease` / `Disorder` | None | Connects a differential pair node to its candidate conditions. |
| `rice:differentiatedBy` | `rice:DiagnosticContrast` | `rice:DiagnosticObservation`| None | Links a contrast node to the key observation separating them. |
| `rice:requiresObservation` | `rice:Disease` | `rice:DiagnosticObservation`| None | Mandates a required observation before diagnosis confirmation. |
| `rice:observesParameter` | `rice:DiagnosticQuestion` | `rice:DiagnosticObservation`| None | Connects clarifying questions to observation parameters. |
| `rice:supports` | `rice:DiagnosticObservation`| `rice:Disease` / `Disorder` | None | Indicates an observation supports a candidate cause. |
| `rice:contradicts` | `rice:DiagnosticObservation`| `rice:Disease` / `Disorder` | None | Indicates an observation penalizes or excludes a candidate cause. |

### D. Actionable & Safety Control Relationships
Used to enforce principle-level agronomic guidance and safety escalation rules.

| Relationship Property | Domain | Range | Description |
| :--- | :--- | :--- | :--- |
| `rice:managedBy` | `rice:Disease` / `Disorder` | `rice:ManagementAction` | Links condition to safe principle-level cultural practice. |
| `rice:notRecommendedWhen` | `rice:ManagementAction` | `rice:EnvironmentalCondition` | Safety rule blocking an action under specific conditions. |
| `rice:escalateWhen` | `rice:Disease` / `Disorder` | `rice:EscalationTrigger` | Mandatory rule referring case to human extension expert. |

### E. Provenance & Evidence Relationships
Used to trace every graph assertion back to authoritative literature or expert approval.

| Relationship Property | Domain | Range | Description |
| :--- | :--- | :--- | :--- |
| `rice:supportedBy` | `owl:Thing` | `rice:EvidenceClaim` | Connects graph triple to extracted atomic claim. |
| `rice:contradictedBy` | `owl:Thing` | `rice:EvidenceClaim` | Connects graph triple to conflicting evidence. |
| `prov:wasDerivedFrom` | `rice:EvidenceClaim` | `rice:SourceDocument` | PROV-O link to original source document. |

---

## 2. Differential Reasoning Representation Example

The primary value of Step 5 is enabling **DiagnosticContrast** nodes that explicitly teach the language model how to distinguish look-alikes rather than making naive direct disease lookup.

### Graph Triples for BLB vs Nitrogen Deficiency Contrast:

```turtle
contrast:blb_vs_nitrogen_deficiency a rice:DiagnosticContrast ;
    skos:prefLabel "BLB vs Nitrogen Deficiency Contrast"@en ;
    rice:compares disease:bacterial_leaf_blight , disorder:nitrogen_deficiency ;
    rice:differentiatedBy obs:lesion_margin_shape , obs:leaf_age_progression , obs:field_spatial_pattern , obs:bacterial_ooze_test ;
    prov:wasDerivedFrom source:irri_rice_doctor_2024 .
```

When a farmer reports *"yellowing leaves during tillering"*, the model retrieves `contrast:blb_vs_nitrogen_deficiency` and evaluates:
1. `obs:lesion_margin_shape` -> `q:q_lesion_margin` ("Are lesions present with wavy margins?")
2. `obs:leaf_age_progression` -> `q:q_older_vs_younger` ("Do older leaves yellow first?")
3. `obs:bacterial_ooze_test` -> `q:q_water_test` ("Does a cut leaf stream cloudy fluid in water?")

---

## 3. Files Created in Workspace

1. **[`kg/ontology/rice-relationships-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-relationships-v0.1.ttl)**  
   OWL object property definitions with formal domain/range, `owl:inverseOf`, and `owl:SymmetricProperty` declarations.
2. **[`docs/step5_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step5_execution.md)**  
   Detailed execution documentation for Step 5.
