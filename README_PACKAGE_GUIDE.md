# Rice Pathogen SALM — Scenarios & Demo Toolkit Guide
**Prepared for:** Ginny Hayes & Aseel Ali  
**From:** Faezeh  
**Package:** `Rice_SLM_Scenarios_Package.zip`  
**Target Delivery:** Team Baseline Demo & Monday Meeting Review  

---

## 1. Executive Summary & What Has Been Done for You

To help you prepare for Monday’s team meeting and the baseline demonstration without having to manually construct 50 scenarios from scratch:
1. **All 100 Scenarios Are Completed & 100% Grounded:**
   - 50 Human Gold Test Scenarios (pre-drafted from your seed ideas with full differential diagnoses, stage-specific actions, and observations).
   - 50 AI-Drafted Training/Validation Scenarios (covering Blast, Bacterial Blight, Sheath Blight, Stem Borer, and Brown Spot lookalikes).
   - **0 broken references, 0 hallucinated facts:** All grounded in Richard's **842 atomic pathology facts** and your **132-concept master vocabulary**.
2. **Richard's Latest Feedback Addressed:**
   - Incorporated Richard's updates from `Scenarios - Updated.zip` and documented all Row J clarifications in `RICHARD_SME_UPDATES_AND_MONDAY_MEETING_AGENDA.md`.
3. **Interactive Web Demonstration & Excel Live Auto-Sync:**
   - Built an interactive web app (`demo_app.py` / `demo_dashboard.html`) where you can explore scenarios, verify/sign off on Human Gold cases with one click, edit existing cases, or add brand-new ones. Any modification in the web demo **automatically synchronizes directly into the Master Excel sheet** on disk!

---

## 2. Inventory of Files in This Package

| # | File Name | Type | What It Does & How to Use It |
|---|---|---|---|
| **1** | `demo_dashboard.html` | Interactive Demo | **Double-click to open in any browser!** Interactive visual dashboard to explore all 100 scenarios, test live diagnosis triage, and inspect Richard's 842 facts. |
| **2** | `demo_app.py` | Live Web Server + Excel Sync | Run `python3 demo_app.py` in Terminal. Opens the dashboard at `http://localhost:8000` with **live bi-directional Excel auto-sync** (edits and new scenarios automatically update the Excel workbook on disk). |
| **3** | `rice_slm_diagnostic_scenarios_completed.xlsx` | Master Excel Workbook | The canonical Excel file containing all 100 scenarios, with reviewer columns, Row J feedback notes, and sign-off statuses. |
| **4** | `RICHARD_SME_UPDATES_AND_MONDAY_MEETING_AGENDA.md` | Meeting Briefing | Full briefing on Richard's latest email updates, Row J clarifications, and 4 focused discussion items for Monday's meeting. |
| **5** | `workbook_scenarios_v0.2.jsonl` | SFT / Benchmark Dataset | Machine-readable dataset in Dr. Srikanth's Schema v0.2.0 format, ready for SLM training and automated evaluation. |
| **6** | `SCENARIO_AUTHORING_AND_TRIAGE_GUIDE.md` | Protocol Guide | Authoring cheat sheet defining the 3 tracks (Answer, Ask, Escalate) and the 4 primary rice lookalike pairs. |
| **7** | `lookup_facts.py` | Search CLI | Terminal utility to instantly search Richard's facts and concepts by symptom keyword or Fact ID. |
| **8** | `diagnose.py` | CLI Diagnostic Tester | Interactive command-line triage tester simulating the SLM diagnostic flow for any rice symptoms. |
| **9** | `validation_report.md` | Quality Audit | Schema verification report confirming 100/100 scenario compliance. |

---

## 3. How to Run the Interactive Web Demonstration

### Method A: Full Interactive Demo with Live Excel Auto-Sync (Recommended)
Open Terminal, navigate to the folder, and run:
```bash
python3 demo_app.py
```
This automatically launches your browser at `http://localhost:8000`. In the web app:
* **Verify Human Gold Cases:** Click **`✅ Verify & Sign Off`** on any scenario to add your approval name. It immediately updates the Excel file!
* **Edit Scenarios:** Click **`✏️ Edit Scenario`** to refine farmer text, questions, or IPM actions. Changes save straight to Excel!
* **Add New Scenarios:** Click **`+ Add New Scenario`** in the top navigation bar to create and insert new clinical cases directly into the workbook.

### Method B: Instant Offline Viewing
Simply double-click `demo_dashboard.html` in your file explorer. It opens in Chrome/Safari with zero setup required.

---

## 4. Suggested Workflow for Ginny & Aseel

1. **Explore the 100 Scenarios via the Demo App:**
   - Launch `python3 demo_app.py` (or open `demo_dashboard.html`).
   - Filter by **Human Gold Test (50)**.
2. **Review & Polish:**
   - **Aseel:** Review Blast (`SCN-001` - `030`) and Stem Borer (`SCN-081` - `100`).
   - **Ginny:** Review Bacterial Blight (`SCN-031` - `057`) and Sheath Blight (`SCN-058` - `080`).
   - Polish phrasing using the **`✏️ Edit Scenario`** button or directly in the Excel workbook.
3. **Verify & Sign Off:**
   - Click **`✅ Verify & Sign Off`** to mark the scenario as approved.
4. **Monday Meeting Prep:**
   - Review `RICHARD_SME_UPDATES_AND_MONDAY_MEETING_AGENDA.md` for the outstanding Row J discussion points.
