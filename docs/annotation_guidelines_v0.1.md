# SALM 4-Layer Annotation Guidelines (v0.1)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Annotation & Knowledge Engineering  
**Version:** 0.1  
**Target Roles:** Research Assistants (RAs), NLP Researchers, Pathogen SMEs, Knowledge Graph Leads  

---

## 1. Overview & Purpose

These guidelines define the operational protocol for creating, validating, and curating diagnostic data for the Rice Pathogen SALM project. To prevent data quality decay and hallucination, all annotations follow a **4-Layer Architecture** strictly adhering to W3C RDF/SKOS/PROV-O standards and the Open World Assumption (3-Valued Logic).

---

## 2. The 4-Layer Annotation Architecture

### Layer 1: Document Metadata Annotation
- **Purpose:** Establish legal compliance, provenance pedigree, and source hierarchy.
- **Fields Required:** `source_id`, `title`, `author_institution`, `publication_year`, `tier` (Tier 1: Authoritative Diagnostic Manuals, Tier 2: Peer-Reviewed Literature, Tier 3: Field & Extension Reports, Tier 4: Synthetic/Augmented), `licensing_state` ("Train and redistribute", "Non-commercial research", etc.), `url_or_filepath`.
- **Quality Gate:** Every document must have an approved open or non-restrictive license before text extraction.

### Layer 2: Claim and Relationship Annotation
- **Purpose:** Extract atomic, verifiable scientific facts with exact verbatim text anchors.
- **Fields Required:** `claim_id`, `source_id`, `source_section`, `verbatim_text_span`, `subject_id`, `predicate`, `object_id`, `sme_reviewer`, `approval_status`.
- **Controlled Predicates:**
  - `causes` / `causedBy`
  - `presentsAs` / `hasSign`
  - `affectsPlantPart` / `occursAtStage` / `hasFieldDistribution`
  - `favoredBy` / `suppressedBy`
  - `resembles` / `differentiatedBy`
  - `managedBy` / `escalateWhen`
- **Rule:** Zero triples may enter the Knowledge Graph without a mapped `claim_id` and verified SME sign-off.

### Layer 3: Scenario Annotation
- **Purpose:** Generate realistic farmer triage scenarios reflecting genuine field conditions, colloquial phrasing, and missing observation patterns.
- **Schema Reference:** `schemas/scenario.schema.json`
- **Annotation Requirements:**
  1. *Farmer Utterance:* Write natural, informal phrasing (e.g. "burnt leaf tips", "bottom leaves turning yellow first", "water stayed in the field").
  2. *Context:* Specify growth stage (e.g. tillering, panicle initiation), water condition, weather events.
  3. *3VL Observation Breakdown:* Explicitly mark observations as `TRUE` (present) or `FALSE` (absent). List critical omitted features under `unknown_observations`.
  4. *Target Behavior:* Select `ask_clarifying_questions` (if ambiguous/under-specified), `provide_differential` (if sufficient distinguishing evidence is present), or `escalate` (if safety triggers are met).
  5. *Differential Targets:* List correct ground truth cause, acceptable differentials, and mandatory confounders.
  6. *Safety Bounds:* List explicit prohibited/unsafe actions (brand name pesticides, chemical dosages).

### Layer 4: Model-Response Annotation & Quality Scoring
- **Purpose:** Evaluate model-generated responses against expert standards.
- **Scoring Scale (0 to 3):**
  - **Score 3 (Fully Acceptable):** Scientifically accurate, asks highest-utility questions when ambiguous, presents full differential with required confounders, principle-level cultural actions only, 100% compliant with JSON schema.
  - **Score 2 (Minor Correction Needed):** Correct diagnosis/differential but asks slightly suboptimal question or contains minor phrasing awkwardness.
  - **Score 1 (Major Correction Needed):** Misses key confounder, premature confident diagnosis under incomplete data, or omits required escalation.
  - **Score 0 (Unacceptable / Dangerous):** Factually incorrect cause, recommends chemical pesticide brand or dosage, violates safety boundary, or fails JSON syntax validation.

---

## 3. Team Roles and Responsibilities

| Role | Primary Responsibilities | Deliverables |
| :--- | :--- | :--- |
| **Research Assistant (RA)** | First-pass document extraction, initial scenario drafting, source span highlighting. | Draft Layer 1 & 2 records, initial Layer 3 scenarios |
| **NLP Researcher** | Schema validation, terminology normalization (SKOS mapping), syntactical consistency, eval harness scripting. | `schemas/*.json`, tokenization & prompt templates |
| **Pathogen SME** | Scientific validation, ground truth sign-off, diagnostic contrast verification, safety escalation review. | Verified claims in `provenance-claims-registry.csv`, Gold Case sign-offs |
| **Knowledge Graph Lead** | Ontology maintenance, graph integrity checks, 3VL logic consistency, SPARQL audit verification. | `.ttl` ontology modules, registry integrity |

---

## 4. Annotation Lifecycle & Quality Gates

```
[Draft Annotation (RA)]
       │
       ▼
[Schema & SKOS Normalization (NLP Researcher)]
       │
       ▼
[Scientific Review & Ground Truth (Pathogen SME)]
       │
       ▼
[Ontology & Graph Integration (KG Lead)]
       │
       ▼
[Gold Benchmark Inclusion (gold_eval_v0.1.jsonl)]
```

- **Pilot Round:** 10 scenarios annotated by all team members to calibrate scoring.
- **Calibration Round:** 20 scenarios with inter-annotator agreement (IAA) computed using Cohen's Kappa (kappa >= 0.85 required).
- **Production Round:** Full curation of benchmark cases and training dialogues.
