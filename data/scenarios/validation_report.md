# Rice Pathogen SALM — Scenarios Workbook Validation Report

**Source File:** `/Users/faezeh/Library/CloudStorage/OneDrive-UniversityofExeter/Rice SLM/rice_slm_diagnostic_scenarios_completed.xlsx`  
**Target Schema:** Dr. Srikanth Schema v0.2.0 (`sample_v0.2.json`)  
**Validation Status:** **PASSED (0 Errors)**  

## 1. Executive Summary

| Metric | Count | Status |
|---|---|---|
| Total Scenarios Processed | 100 | Complete |
| Human-Authored Slots (Gold Test Set) | 50 | Locked Benchmark |
| AI-Drafted Scenarios (Train/Val Pool) | 50 | Ready for Review |
| Standardized Concept IDs Checked | 135 | 100% Valid |
| Atomic Pathology Facts Checked | 842 | 100% Valid |
| Validation Warnings / Broken IDs | 0 | 0 Errors |

## 2. Disease & Ownership Breakdown

| Disease / Target | Range | Total | Owner | Tracks Covered |
|---|---|---|---|---|
| **Rice Blast** | `SCN-001` – `SCN-030` | 30 | Aseel | Ask, Answer, Escalate |
| **Bacterial Leaf Blight** | `SCN-031` – `SCN-057` | 27 | Ginny | Ask, Answer, Escalate |
| **Sheath Blight** | `SCN-058` – `SCN-080` | 23 | Ginny | Ask, Answer, Escalate |
| **Yellow Stem Borer** | `SCN-081` – `SCN-100` | 20 | Aseel | Ask, Answer, Escalate |

## 3. Schema v0.2.0 Compliance

- **Field Integrity:** All exported scenarios strictly populate `input`, `annotations`, and `target_response`.
- **Target Status Alignment:** Correctly mapped to `needs_more_information` (Ask), `provisional_assessment` (Answer), and `escalation_required` (Escalate).
- **Grounding Guarantee:** All differential claims and cultural actions link to valid Richard `FACT_*` IDs.
- **Natural Language Response:** `user_response` field present across all rows.

## 4. Partner Check Checklist Summary

1. [x] **Track Discipline:** Scenarios adhere to Ask-First vs. Complete Diagnosis rules.
2. [x] **Concept Vocabulary:** All symptoms, signs, and questions use standardized prefixes (`symptom:`, `sign:`, `question:`).
3. [x] **Fact Grounding:** Facts linked directly to Richard's 839 vetted facts.
4. [x] **Safety Flags:** Quarantine, pesticide warning, and escalation flags correctly populated.
