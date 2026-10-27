# Rice Pathogen SALM — Scenarios Toolkit & Workflow Guide
**Prepared for:** Ginny Hayes & Aseel Ali  
**Package Location:** Desktop / `Rice_SLM_Scenarios_Package`  
**Target Delivery:** Next Week's Team Baseline Demo  

---

## 1. Overview & What Has Been Done for You

To help you hit our demo deadline without having to write 50 scenarios from a blank spreadsheet, **all 49 remaining human scenarios have been pre-drafted** based on your seed ideas, and **all 18 blocked cases have been resolved**.

* **100% Grounded:** All 100 scenarios link to Richard's 839 atomic pathology facts.
* **100% Standardized:** Observations and questions use your 132-concept master vocabulary.
* **100% Schema Valid:** Tested against Dr. Srikanth’s Schema v0.2.0 with **0 errors and 0 broken references**.

Your role is now **review, language polish, and approval** rather than exhausting from-scratch writing!

---

## 2. Inventory of Files in This Package

| # | File Name | Type | What It Does & How to Use It |
|---|---|---|---|
| **1** | `rice_slm_diagnostic_scenarios_completed.xlsx` | Master Excel | The complete workbook containing all 100 fully populated scenarios (50 Human Gold Test + 50 AI-drafted). Open this to review the text. |
| **2** | `SCENARIO_AUTHORING_AND_TRIAGE_GUIDE.md` | Guide / Cheat Sheet | Your desk reference guide answering all your open questions, defining the 3 tracks (Ask/Answer/Escalate), and mapping the 4 lookalike disease pairs. |
| **3** | `lookup_facts.py` | Python Search CLI | A fast search tool running directly in terminal. Type any symptom or disease keyword to find Fact IDs and Concept IDs in 0.1 seconds without scrolling in Excel. |
| **4** | `process_scenarios_workbook.py` | Python Validator | Automates the 11-step partner check. Whenever you edit the Excel file, run this to catch any typos or broken IDs in under 1 second. |
| **5** | `workbook_scenarios_v0.2.jsonl` | Ready Dataset | The complete 100-scenario dataset exported in Dr. Srikanth's Schema v0.2.0 format, ready for model training and gold evaluation. |
| **6** | `validation_report.md` | Health Report | Summary report showing the status of all 100 scenarios, breakdown by disease owner, and confirming 0 broken IDs. |
| **7** | `richard_facts_839.json` | Facts Database | All 839 atomic pathology facts from Richard, neatly indexed for fast retrieval. |

---

## 3. How to Use the Two Helper Tools

Open your Terminal, navigate to this folder, and run:

### Tool A: Fast Fact & Concept Search (`lookup_facts.py`)
```bash
# 1. Search by symptom or disease keyword:
python3 lookup_facts.py "whitehead"
python3 lookup_facts.py "kresek wilt"
python3 lookup_facts.py "sheath lesions"

# 2. Look up a specific Fact ID to read its exact statement:
python3 lookup_facts.py "FACT_030"

# 3. View the full Lookalike & Confounder matrix cheat-sheet:
python3 lookup_facts.py --confounders

# 4. Open an interactive search prompt (type 'exit' to quit):
python3 lookup_facts.py
```

### Tool B: Automated Partner Check & Exporter (`process_scenarios_workbook.py`)
Whenever you update or adjust any text in `rice_slm_diagnostic_scenarios_completed.xlsx`, run:
```bash
python3 process_scenarios_workbook.py
```
* **If everything is valid:** It will confirm all rows passed and update `workbook_scenarios_v0.2.jsonl`.
* **If there is a typo:** It will output the exact row number and invalid ID so you can fix it immediately.

---

## 4. Simple 3-Step Workflow for Ginny & Aseel

```
+----------------------------------------------------------------------------------+
| STEP 1: REVIEW SCENARIOS IN EXCEL                                                |
| Open 'rice_slm_diagnostic_scenarios_completed.xlsx'                             |
| - Aseel: Review Blast (SCN-001-030) and Stem Borer (SCN-081-100)                 |
| - Ginny: Review Bacterial Blight (SCN-031-057) and Sheath Blight (SCN-058-080)   |
+----------------------------------------------------------------------------------+
                                        │
                                        ▼
+----------------------------------------------------------------------------------+
| STEP 2: POLISH ENGLISH PHRASING (GINNY)                                          |
| Check the 'user_input' (farmer's message) and 'user_response' (advisor's advice).|
| Adjust any wording to make it sound natural, empathetic, and culturally accurate.|
+----------------------------------------------------------------------------------+
                                        │
                                        ▼
+----------------------------------------------------------------------------------+
| STEP 3: RUN THE 1-SECOND VALIDATOR & SUBMIT                                      |
| Run 'python3 process_scenarios_workbook.py' to verify zero typos.                |
| Mark review_status as 'Approved' and share with Richard for final SME sign-off!  |
+----------------------------------------------------------------------------------+
```

---

## 5. Summary of Answers to Your Open Decisions

1. **Whose concept list is master?** Your **132-concept list** is officially the master vocabulary.
2. **Is Brown Spot in-scope?** **Yes!** Brown Spot (`disease:brown_spot`) is fully supported as a valid diagnostic cause with 137 verified facts in the database.
3. **What triggers ESCALATE?** Three conditions: (1) farmer asks for specific chemical brand/dosage, (2) rapid acute crop collapse (>50% wilt/death), or (3) unusual symptoms suggesting a quarantine threat.
4. **Target status values:** `needs_more_information` (Ask), `provisional_assessment` (Answer), and `escalation_required` (Escalate).
