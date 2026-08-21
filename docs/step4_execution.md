# Step 4: Define Stable IDs and Controlled Vocabulary

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Knowledge Graph Team  
**Deliverable Scope:** Step 4 (Stable ID Specification, Registry Structure, SKOS Terminology & Vernacular Mapping)

---

## 1. Stable ID Specification Rules

To ensure the Knowledge Graph scales without breaking references, all entity IDs follow strict formatting, prefix, and immutability rules.

### A. ID Format & Case Conventions
*   **Format:** `<namespace_prefix>:<concept_name_in_snake_case>`
*   **Characters:** Lowercase alphanumeric characters and underscores (`[a-z0-9_]`). No spaces, hyphens, uppercase letters, or special characters.
*   **Immutability:** IDs are permanent once registered. Synonym additions or label updates do not change the core ID.

### B. Namespace Prefix Scheme
| Entity Type | Prefix | URI Namespace | Example ID |
| :--- | :--- | :--- | :--- |
| Disease | `disease:` | `https://openag.example/rice/disease/` | `disease:bacterial_leaf_blight` |
| Abiotic Disorder | `disorder:` | `https://openag.example/rice/disorder/` | `disorder:nitrogen_deficiency` |
| Pathogen | `pathogen:` | `https://openag.example/rice/pathogen/` | `pathogen:xanthomonas_oryzae_pv_oryzae` |
| Symptom | `symptom:` | `https://openag.example/rice/symptom/` | `symptom:water_soaked_wavy_lesion` |
| Diagnostic Sign | `sign:` | `https://openag.example/rice/sign/` | `sign:water_test_cloudy_streaming` |
| Plant Part | `part:` | `https://openag.example/rice/part/` | `part:leaf_sheath` |
| Growth Stage | `stage:` | `https://openag.example/rice/stage/` | `stage:tillering` |
| Environment | `env:` | `https://openag.example/rice/env/` | `env:standing_water` |
| Field Pattern | `field:` | `https://openag.example/rice/field/` | `field:patchy_distribution` |
| Diagnostic Obs. | `obs:` | `https://openag.example/rice/obs/` | `obs:lesion_margin_shape` |
| Diagnostic Question| `q:` | `https://openag.example/rice/question/` | `q:q_lesion_margin` |
| Management Action | `action:` | `https://openag.example/rice/action/` | `action:use_resistant_varieties` |
| Contrast Pair | `contrast:` | `https://openag.example/rice/contrast/` | `contrast:blb_vs_nitrogen_deficiency` |
| Source Document | `source:` | `https://openag.example/rice/source/` | `source:irri_rice_doctor_2024` |
| Evidence Claim | `claim:` | `https://openag.example/rice/claim/` | `claim:claim_blb_001` |

---

## 2. Controlled Terminology & Vernacular Mapping

A key role of the Knowledge Graph is normalizing informal farmer utterances (e.g. "burnt edges", "water stayed in field") into precise, canonical scientific terms (`symptom:water_soaked_wavy_lesion`, `env:standing_water`).

### Mapping Table: Farmer Phrasing -> SKOS Concept -> Stable ID

| Farmer Utterance / Phrasing | SKOS Preferred Label | Controlled ID | Normalized Class |
| :--- | :--- | :--- | :--- |
| *"leaves turning yellow"*, *"pale plants"* | Leaf yellowing | `symptom:leaf_yellowing` | Symptom |
| *"burnt edges"*, *"stripes on leaf side"*, *"wavy yellow edges"* | Water-soaked wavy lesion | `symptom:water_soaked_wavy_lesion` | Symptom |
| *"burnt leaf tips"*, *"drying from ends"* | Leaf tip and margin necrosis | `symptom:leaf_tip_margin_necrosis` | Symptom |
| *"bottom leaves yellow first"*, *"lower foliage pale"* | Uniform older leaf chlorosis | `symptom:uniform_older_leaf_chlorosis` | Symptom |
| *"short plants"*, *"not growing tall"*, *"few tillers"* | Stunted growth | `symptom:stunted_growth` | Symptom |
| *"leaves curling up"*, *"rolled like needles"* | Leaf rolling and folding | `symptom:leaf_rolling_folding` | Symptom |
| *"milky liquid on leaves"*, *"sticky yellow drops"* | Bacterial ooze beads | `sign:bacterial_ooze_beads` | Sign |
| *"cloudy water from cut leaf"*, *"white thread in glass"* | Water test cloudy streaming | `sign:water_test_cloudy_streaming` | Sign |
| *"plants in groups"*, *"yellow spots across field"* | Patchy field distribution | `field:patchy_distribution` | FieldDistribution |
| *"whole field yellow"*, *"entire field affected"* | Uniform field-wide distribution | `field:uniform_fieldwide_distribution` | FieldDistribution |
| *"water stayed in field"*, *"flooded field"* | Standing water | `env:standing_water` | EnvironmentalCondition |

---

## 3. CSV Registry Files Structure

The following 3 CSV registry files have been populated in the `registry/` directory:

1. **[`registry/disease-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/disease-registry.csv)**: Master registry of all diseases, abiotic disorders, and pathogens in the v1 scope.
2. **[`registry/terminology-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/terminology-registry.csv)**: Master mapping table linking canonical terms, SKOS preferred labels, alt labels, and farmer vernacular phrasings.
3. **[`registry/source-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/source-registry.csv)**: Provenance and license registry tracking authoritative diagnostic sources (IRRI Rice Doctor, IRRI Rice Knowledge Bank).

---

## 4. SKOS Vocabulary File

The Controlled Terminology has also been serialized as W3C SKOS Concepts in **[`kg/ontology/rice-terminology-skos-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-terminology-skos-v0.1.ttl)** using:
*   `skos:prefLabel` for the canonical scientific name.
*   `skos:altLabel` for technical synonyms.
*   `skos:hiddenLabel` for informal farmer phrasings used by the SLM normalization module.
