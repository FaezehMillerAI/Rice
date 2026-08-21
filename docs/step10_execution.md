# Step 10: Build Provenance from Day One (Chain of Custody & PROV-O)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Knowledge Graph Team  
**Deliverable Scope:** Step 10 (End-to-End Chain of Custody, W3C PROV-O Implementation, Licensing Controls, SPARQL Audit Queries)

---

## 1. Executive Summary & Provenance Mandate

In scientific agricultural AI, every assertion in the Knowledge Graph must have a permanent **"evidence receipt"**. If an extension officer or plant pathologist asks:  
*"Why does the graph say Bacterial Leaf Blight produces wavy lesions?"*  
The system must not return a generic AI response. It must provide the complete **Chain of Custody**:

$$\text{Source Document} \longrightarrow \text{Exact Text Span} \longrightarrow \text{Atomic Claim} \longrightarrow \text{SME Reviewer Sign-Off} \longrightarrow \text{Graph Relationship}$$

### Core Rule of Step 10
No triple may exist in the production Knowledge Graph without an associated `claim:<claim_id>` binding linked to an approved `source:<source_id>` record, an exact verbatim text span, and a named Subject Matter Expert (SME) sign-off timestamp.

---

## 2. The 5-Stage Chain of Custody Workflow

As specified in Section 9.9 of the implementation blueprint, candidate facts follow an approved 5-stage pipeline before graph insertion:

```
[1. Source Document] (IRRI Fact Sheet / Manual)
        │
        ▼
[2. Text Span Extraction] (Verbatim snippet extracted)
        │
        ▼
[3. Schema Validation & Term Normalization] (Mapped to SKOS concepts)
        │
        ▼
[4. SME Human Review & Approval] (Pathogen SME sign-off timestamp)
        │
        ▼
[5. Knowledge Graph Insertion] (Triples linked to claim:claim_id)
```

> [!CAUTION]
> **Prohibited Workflow:** Never use `Document -> LLM -> Production Knowledge Graph` without human SME annotation and schema validation!

---

## 3. W3C PROV-O Ontology Integration

In `kg/ontology/rice-provenance-provo-v0.1.ttl`, provenance is formally modeled using W3C `PROV-O` standard terms:

| PROV-O / Custom Property | Domain | Range | Example Value / Function |
| :--- | :--- | :--- | :--- |
| `prov:wasDerivedFrom` | `rice:EvidenceClaim` | `rice:SourceDocument` | Links claim to `source:irri_rice_doctor_2024`. |
| `prov:wasAttributedTo` | `rice:SourceDocument` | `prov:Agent` | Links document to `agent:irri_institution`. |
| `prov:wasAssociatedWith` | `rice:EvidenceClaim` | `prov:Agent` | Links claim to `agent:richard_lindsay` (SME). |
| `prov:generatedAtTime` | `rice:EvidenceClaim` | `xsd:date` | Timestamp of SME review (`2026-08-11`). |
| `rice:sourceSection` | `rice:EvidenceClaim` | `xsd:string` | `"Symptoms"`, `"Diagnostic Tests"`, etc. |
| `rice:sourceTextSpan` | `rice:EvidenceClaim` | `xsd:string` | Verbatim text snippet extracted from manual. |
| `rice:smeApprovalStatus` | `rice:EvidenceClaim` | `xsd:string` | `"SME_approved"`, `"pending_review"`, `"rejected"`. |
| `rice:licensingStatus` | `rice:SourceDocument` | `xsd:string` | Legal classification (`"Train and redistribute"`). |

---

## 4. Master Provenance Claims Registry

All extracted evidence receipts are cataloged in **[`registry/provenance-claims-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/provenance-claims-registry.csv)**:

| Claim ID | Source ID | Section | Verbatim Text Span | SME Reviewer | Approval Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`claim_blb_001`** | `source:irri_rice_doctor_2024` | Symptoms | *"Lesions start as water-soaked, yellow-orange stripes on leaf tips or margins with wavy edges."* | Richard Lindsay (Pathogen SME) | `SME_approved` |
| **`claim_blb_002`** | `source:irri_rice_doctor_2024` | Diagnostic Tests | *"Cut a leaf section with lesions and place in clear water; cloudy bacterial ooze streams out into the water."* | Richard Lindsay (Pathogen SME) | `SME_approved` |
| **`claim_ndef_001`**| `source:irri_rice_doctor_2024` | Nutrient Disorders | *"Nitrogen deficiency causes general yellowing starting strictly on the lowest, oldest leaves as nitrogen is remobilized."* | Richard Lindsay (Pathogen SME) | `SME_approved` |
| **`claim_wstress_001`**|`source:irri_rice_doctor_2024` | Abiotic Stresses | *"Water deficit causes inward longitudinal leaf rolling and folding into tube-like shapes to reduce transpiration."* | Richard Lindsay (Pathogen SME) | `SME_approved` |

---

## 5. SPARQL Audit Queries for Graph Verification

To verify that any relationship has an unbroken chain of custody, the system runs SPARQL audit queries:

```sparql
# Audit Query: Fetch exact evidence receipt for Bacterial Leaf Blight
PREFIX rice: <https://openag.example/rice/ontology#>
PREFIX prov: <http://www.w3.org/ns/prov#>

SELECT ?disease ?claim ?span ?section ?reviewer ?source ?license
WHERE {
  ?disease rice:supportedBy ?claim .
  ?claim rice:sourceTextSpan ?span ;
         rice:sourceSection ?section ;
         rice:smeReviewer ?reviewer ;
         prov:wasDerivedFrom ?source .
  ?source rice:licensingStatus ?license .
  FILTER(?disease = <https://openag.example/rice/disease/bacterial_leaf_blight>)
}
```

---

## 6. Deliverable Files Created in Workspace

1. **[`registry/provenance-claims-registry.csv`](file:///Users/fs525/Desktop/Rice/registry/provenance-claims-registry.csv)**  
   Master CSV catalog of atomic claims, verbatim text spans, section names, SME review timestamps, and licensing states.
2. **[`kg/ontology/rice-provenance-provo-v0.1.ttl`](file:///Users/fs525/Desktop/Rice/kg/ontology/rice-provenance-provo-v0.1.ttl)**  
   W3C PROV-O Turtle ontology file mapping `prov:wasDerivedFrom`, `prov:wasAttributedTo`, `prov:wasAssociatedWith`, and claim bindings.
3. **[`docs/step10_execution.md`](file:///Users/fs525/Desktop/Rice/docs/step10_execution.md)**  
   Detailed execution documentation for Step 10.
