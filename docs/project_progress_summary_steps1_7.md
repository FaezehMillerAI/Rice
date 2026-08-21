# Rice Pathogen SALM — Knowledge Graph Progress Report (Steps 1–7)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Collaboration:** IAAIR × University of Exeter × OpenAg  
**Workstream:** Knowledge Graph & Scientific Reasoning Engine  
**Document Purpose:** Comprehensive Progress Summary (Steps 1 through 7)  
**Target Audience:** Project PIs, Steering Committee, and Multidisciplinary Team Members  

---

## Executive Summary & Background Context

The Rice Pathogen Small Agriculture Language Model (SALM) project is a joint research initiative designed to provide offline-capable, explainable, and scientifically grounded AI diagnostic assistance to agricultural extension officers and field advisors. In smallholder farming systems, misdiagnosing a crop issue—such as confusing an infectious bacterial disease with a simple nutrient deficiency—can lead to inappropriate chemical applications, crop failure, and severe economic loss. 

To prevent the artificial intelligence from "hallucinating" plausible-sounding but incorrect advice, our architecture separates responsibility: the language model handles natural conversation and translation, while a dedicated Knowledge Graph (KG) serves as the authoritative, expert-reviewed scientific brain behind every diagnostic decision. Over the first phase of development, the Knowledge Graph team has successfully completed the first seven foundational engineering steps.

---

## 1. Defining the Scope: The Initial Vertical Slice (Step 2)

A common mistake in agricultural AI is attempting to model every known crop disease from day one. To establish an early working prototype and ensure maximum reliability, we began by restricting the scope to a tight, high-impact "vertical slice" containing three primary conditions:

1. **Bacterial Leaf Blight (BLB):** A destructive bacterial disease caused by *Xanthomonas oryzae* pv. *oryzae*, characterized by water-soaked, wavy-edged yellow/brown lesions starting at leaf tips or edges.
2. **Nitrogen (N) Deficiency:** An abiotic nutrient disorder that causes uniform pale yellowing starting strictly on the lowest, oldest leaves as the plant remobilizes nitrogen to younger growth.
3. **Water-Related Stress:** An abiotic moisture disorder (such as drought or waterlogging) that triggers inward leaf rolling, wilting, and tip browning without true infectious lesions.

### Core Boundary Rules
To ensure safety during field testing, the initial system operates under strict boundaries: it is text-based (no image processing in v1), provides principle-level cultural management advice only, strictly prohibits recommending commercial chemical product brand names or dosages, and enforces mandatory escalation to human plant pathologists whenever rapid, uncontrollable field spread or panicle damage occurs.

---

## 2. Requirements & Competency Questions (Step 1)

Before writing any database code or ontology logic, we established 25 core **Competency Questions** (CQs). These questions define the exact scientific queries the Knowledge Graph must be capable of answering. 

The questions span six essential categories:
* **Candidate Retrieval:** *"Which diseases cause leaf yellowing during the tillering stage?"*
* **Look-Alike Differentiation:** *"What specific field observation separates Bacterial Leaf Blight from Nitrogen deficiency?"*
* **Clarifying Questions:** *"If a farmer reports yellow leaves, what critical information is missing?"*
* **Environmental Drivers:** *"What weather events increase the probability of bacterial infection?"*
* **Safety Management:** *"What cultural practices are safe for BLB without using specific pesticide products?"*
* **Scientific Provenance:** *"Which authoritative source document supports the claim that BLB lesions have wavy margins?"*

---

## 3. Building the Foundation: Minimum Ontology & Stable IDs (Steps 3 & 4)

To store scientific facts systematically, we created a formal W3C RDF/OWL ontology (`rice-pathogen-v0.1.ttl`) containing 19 core concept classes. These classes represent everything from physical plant organs (`rice:PlantPart`) and growth stages (`rice:GrowthStage`) to diagnostic signs (`rice:Sign`), clarifying questions (`rice:DiagnosticQuestion`), and safety triggers (`rice:EscalationTrigger`).

To ensure that the graph can scale seamlessly without breaking references, we enforced a strict, immutable naming convention (`<prefix>:<snake_case_id>`). Every concept possesses a permanent ID, such as `disease:bacterial_leaf_blight`, `disorder:nitrogen_deficiency`, `symptom:water_soaked_wavy_lesion`, or `sign:water_test_cloudy_streaming`.

### Translating Farmer Vernacular to Science
Farmers in the field rarely speak in academic Latin terms; they describe symptoms in local everyday language (e.g., *"burnt edges"*, *"bottom leaves yellowing first"*, *"water stayed in the field"*). Using W3C SKOS standards (`rice-terminology-skos-v0.1.ttl`), we built controlled registries mapping these informal farmer descriptions directly to canonical scientific concepts. When a farmer inputs a phrase, the system normalizes it instantly into a structured graph node.

---

## 4. Modeling Diagnostic Logic & Look-Alikes (Steps 5 & 6)

Traditional AI systems model diseases as simple lists of symptoms (`Disease -> presentsAs -> Symptom`). However, when multiple conditions share the exact same broad symptom—such as leaf yellowing—a simple lookup fails to tell the user what to do next.

### Relationship Semantics (Step 5)
We defined five functional clusters of graph relationships with strict mathematical rules (domain and range constraints, symmetry, and inverses). These relationships explicitly connect pathogens to their diseases (`causes` / `causedBy`), diseases to affected organs (`affectsPlantPart`), weather drivers (`favoredBy`), and safe practices (`managedBy`).

### First-Class Differential Contrast Nodes (Step 6)
To handle look-alike conditions properly, we introduced **`rice:DiagnosticContrast`** nodes. Instead of treating diseases in isolation, the graph explicitly pairs look-alike conditions (such as `contrast:blb_vs_nitrogen_deficiency`) and links them directly to the key discriminating observations that separate them:
* **Lesion Margin Shape:** BLB produces distinct wavy, water-soaked margins; Nitrogen Deficiency produces no lesions.
* **Leaf Age Progression:** Nitrogen Deficiency affects the lowest (oldest) leaves first; BLB affects upper/middle leaves along veins.
* **Field Pattern:** BLB spreads in isolated, patchy clusters; Nitrogen Deficiency affects large, uniform field areas.
* **Cut-Leaf Water Test:** Immersing a cut BLB leaf in clear water causes cloudy bacterial ooze to stream out; nutrient and water stress remain completely clear.

---

## 5. Diagnostic Questions as First-Class Objects (Step 7)

In Step 7, we made a crucial design upgrade: rather than allowing the language model to generate unstructured, unpredictable clarifying questions on the fly, we turned every question into a **first-class graph object (`q:<snake_case_id>`)**.

Each question in `kg/ontology/rice-questions-v0.1.ttl` and `registry/question-registry.csv` is equipped with:
1. **Dual Phrasings:** Formal technical phrasing for extension officers (`skos:definition`) and simplified vernacular phrasing for farmers (`skos:hiddenLabel`).
2. **Observation Parameter Bindings:** Direct connection to the exact observation parameter it measures (`rice:observesParameter`).
3. **Scientific Rationale:** An explicit statement explaining *why* the question is necessary (e.g., *"Confirms vascular bacterial infection"*).
4. **Utility Metrics:** Numerical scores for **User Effort** (1 = visual check, 2 = water test), **Field Observability**, and **Diagnostic Reliability**.

### The Dynamic Question Selection Engine
When an under-specified observation is received (e.g., *"Leaves are yellow"*), the diagnostic engine computes a mathematical **Question Utility** score:

$$\text{Question Utility} = \frac{\text{Candidates Separated} \times \text{Observation Reliability} \times \text{Field Observability} \times \text{Safety Importance}}{\text{User Effort}}$$

This formula allows the AI to automatically rank all available questions and select the single most informative, low-effort question to ask the user next.

---

## Summary of Complete Project Artifacts Created

| Artifact Category | File Location | Core Purpose |
| :--- | :--- | :--- |
| **Core Ontology** | [`kg/ontology/rice-pathogen-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-pathogen-v0.1.ttl) | 19 core classes & foundational vertical slice schema |
| **SKOS Vocabulary** | [`kg/ontology/rice-terminology-skos-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-terminology-skos-v0.1.ttl) | Controlled terminology & farmer phrasing mappings |
| **Relationships** | [`kg/ontology/rice-relationships-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-relationships-v0.1.ttl) | Formal object property taxonomy & domain/range rules |
| **Differential Graph**| [`kg/ontology/rice-differentials-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-differentials-v0.1.ttl) | First-class `DiagnosticContrast` nodes & look-alike pairing |
| **Question Ontology** | [`kg/ontology/rice-questions-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-questions-v0.1.ttl) | First-class `DiagnosticQuestion` nodes & utility metrics |
| **Master Registries** | [`registry/disease-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/disease-registry.csv) | Catalog of diseases, disorders, and pathogens |
| | [`registry/terminology-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/terminology-registry.csv) | 26 normalized terms with SKOS labels & farmer phrases |
| | [`registry/source-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/source-registry.csv) | Authoritative IRRI diagnostic source provenance & licenses |
| | [`registry/question-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/question-registry.csv) | Master catalog of diagnostic questions & effort scores |
| **Detailed Guides** | [`docs/step1_to_3_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step1_to_3_execution.md) | Comprehensive report for Steps 1 through 3 |
| | [`docs/step4_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step4_execution.md) | Stable IDs & SKOS documentation |
| | [`docs/step5_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step5_execution.md) | Relationship taxonomy & semantics documentation |
| | [`docs/step6_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step6_execution.md) | Differential diagnosis graph model documentation |
| | [`docs/step7_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step7_execution.md) | First-class diagnostic question model documentation |

---

## Conclusion & Next Steps

With Steps 1 through 7 complete, the Knowledge Graph possesses a fully structured ontology, a controlled SKOS vocabulary, explicit differential look-alike contrast pairs, and a mathematical question utility selection model. 

The system is now ready to move into **Step 8: Representing TRUE, FALSE, and UNKNOWN States**, which will establish three-valued logic to ensure that missing field information is never mistaken for negative evidence.
