# Rice Pathogen SALM — Scenario Authoring & Clinical Triage Guide
**Prepared by:** Faezeh (Knowledge Graph & Clinical Reasoning Lead)  
**For:** Ginny Hayes & Aseel Ali (Scenario Authors & Pathologist Leads)  
**Reference Workbook:** `Scenarios/OneDrive_1_23-10-2026/rice_slm_diagnostic_scenarios.xlsx`  
**Target Schema:** Dr. Srikanth Schema v0.2.0 (`sample_v0.2.json`)

---

## 1. Quick Answers to Your Open Team Decisions (`Our_Decisions`)

| # | Question from Workbook | Consensus Answer & Technical Guarantee |
|---|---|---|
| **12** | *Whose concept list is the master?* | **Your 132-concept taxonomy is officially adopted as the master vocabulary.** All prefixes (`pest:stem_borer`, `disease:rice_blast`, `disease:sheath_blight`, etc.) are now fully ingested into the Knowledge Graph and SQLite database. |
| **5** | *Can the system name Brown Spot as a cause (ANSWER)?* | **Yes! Brown Spot (`disease:brown_spot`) is fully in scope** as a diagnostic candidate and differential cause. It is backed by 137 atomic facts in Richard's dataset. |
| **6** | *What triggers ESCALATE beyond dosage requests?* | **Three clinical triggers:** (1) Acute systemic collapse / kresek wilt (>50% crop loss); (2) Unidentified suspected quarantine/biosecurity pathogen; (3) Dangerous off-label chemical requests. |
| **10** | *Exact `target_response.status` values?* | Matching Srikanth's & Fei's prompt contract: <br>• Track A (Ask): `"needs_more_information"` <br>• Track B (Answer): `"provisional_assessment"` <br>• Track C (Escalate): `"escalation_required"` |
| **11** | *Fact ID format (`FACT_030` vs `FACT-000030`)?* | **Both formats are fully supported.** You can write either in Excel; the automated exporter (`process_scenarios_workbook.py`) normalizes them automatically. |

---

## 2. Clinical Triage & Confounder Matrix

The most critical part of writing Track A (*Ask-First*) scenarios is asking the **single most discriminating question** instead of guessing when lookalikes share symptoms:

```
+-----------------------------------+---------------------------------------------------------+
| Lookalike Disease Pair            | Minimal Discriminating Question & Grounding             |
+-----------------------------------+---------------------------------------------------------+
| [1] Rice Blast vs. Stem Borer     | question:whitehead_pull_test                            |
|     Shared: Whiteheads at heading | • Blast: Panicle stays firmly attached (FACT_031)       |
|                                   | • Stem Borer: Panicle slides out easily (FACT_030, 381) |
+-----------------------------------+---------------------------------------------------------+
| [2] Rice Blast vs. Brown Spot     | question:lesion_shape                                   |
|     Shared: Brown leaf spots      | • Blast: Spindle / diamond, gray center (FACT_009)      |
|                                   | • Brown Spot: Round/oval, solid brown (FACT_501)        |
+-----------------------------------+---------------------------------------------------------+
| [3] Bacterial Blight vs. Sheath   | question:lesion_progression_direction                   |
|     Shared: Foliar canopy blight  | • BLB: Starts leaf tips/margins, moves DOWN (FACT_204)  |
|                                   | • Sheath: Starts at water line, moves UP (FACT_304)     |
+-----------------------------------+---------------------------------------------------------+
| [4] Bacterial Blight vs. Nitrogen | question:lesion_margin_type                             |
|     Shared: Canopy yellowing      | • BLB: Wavy water-soaked margins, ooze (FACT_211)       |
|                                   | • Nitrogen: Uniform chlorosis on old leaves (FACT_780)  |
+-----------------------------------+---------------------------------------------------------+
```

---

## 3. The 3 Diagnostic Track Rules

### Track A: Ask-First (`status: needs_more_information`)
* **When to use:** The farmer presents symptoms that could fit two or more diseases (e.g., "my crop has whiteheads" or "my leaves are turning yellow").
* **Target Behavior:** 
  * `differential`: List the 2–3 competing candidates.
  * `observations_needed`: Specify the exact discriminating question ID from the table above.
  * `actions`: Empty (`[]`). *Never recommend treatments before the cause is confirmed.*
  * `user_response`: Explain what you see, mention the potential lookalikes cautiously, and ask the farmer the discriminating question politely in plain English.

### Track B: Provisional Assessment (`status: provisional_assessment`)
* **When to use:** The scenario includes the discriminating observation (e.g., "the panicle pulled out easily" or "the lesions are spindle-shaped with gray centers").
* **Target Behavior:**
  * `differential`: Rank the primary cause first.
  * `observations_needed`: Empty (`[]`).
  * `actions`: 2–4 cultural/IPM practices (e.g., balanced fertilizer, water management, sanitation). *No chemical brand names or exact doses.*
  * `grounding`: Link the 3–8 supporting `FACT_*` IDs.
  * `user_response`: State the likely cause, explain why the symptoms match, and give immediate cultural recommendations and next-season advice.

### Track C: Escalation (`status: escalation_required`)
* **When to use:** Farmer requests specific chemical doses, reports rapid seedling death (>50% wilt), or describes symptoms not matching common local diseases.
* **Target Behavior:**
  * `escalation_required`: `true`.
  * `actions`: Immediate referral to local Agricultural Extension Officer / Plant Health Clinic.
  * `safety_flags`: `["safety:refer_to_extension", "safety:chemical_safety"]`.

---

## 4. Helper Tools Available in the Repository

### Tool 1: Instant Fact & Concept Search CLI (`scripts/lookup_facts.py`)
Run in your terminal to instantly find Concept IDs and Fact IDs without scrolling through Excel:
```bash
# Search by symptom keyword
python3 scripts/lookup_facts.py "whitehead"

# Direct Fact ID lookup
python3 scripts/lookup_facts.py "FACT_030"

# View the full confounder cheat-sheet
python3 scripts/lookup_facts.py --confounders

# Interactive Search Mode (prompts you repeatedly)
python3 scripts/lookup_facts.py
```

### Tool 2: Automated Partner Checker & Exporter (`scripts/process_scenarios_workbook.py`)
Run anytime you update the Excel workbook:
```bash
python3 scripts/process_scenarios_workbook.py
```
* **What it does:**
  1. Validates all 100 rows against the 132 Concept IDs and 839 Fact IDs.
  2. Flags any typos or broken IDs with exact row numbers.
  3. Automatically exports the data to `data/scenarios/workbook_scenarios_v0.2.jsonl` matching Srikanth's Schema v0.2.0.
  4. Generates `data/scenarios/validation_report.md` summarizing progress.
