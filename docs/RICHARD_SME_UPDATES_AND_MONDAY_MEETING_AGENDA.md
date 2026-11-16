# Richard's SME Pathology Updates & Monday Meeting Agenda
**Project:** Rice Pathogen Small Agricultural Language Model (OpenAg SALM)  
**Date:** November 5, 2026 (For Team Meeting on Monday)  
**Prepared by:** Faezeh (Knowledge Graph & Clinical Reasoning Lead)  
**Participants:** Richard (Plant Pathology SME), Ginny & Aseel (Scenario Authors), Dr. Srikanth, Fei, Josh  
**Master Workbook:** `rice_slm_diagnostic_scenarios_completed.xlsx` (in Desktop package)

---

## 1. Executive Summary of Richard's Updates

In response to the issues flagged in `rice_pathogen_facts` and `disease_profiles`, **Richard has thoroughly reviewed the master workbook and added detailed clarifications to Column J ("NOTES") in the `Data_Issues` sheet across 25 issues.**

### Key Upgrades Completed in the Knowledge Graph:
1. **Fact Base Expanded to 842 Facts:**
   - 3 new facts were added to resolve critical clinical gaps:
     * **`FACT_840` (Bacterial Blight):** Infection at booting stage causing poor quality grain and broken kernels.
     * **`FACT_841` (Sheath Blight):** Fungus forms sclerotia (dark-colored nodules) as survival and inoculum source (resolves Issue #10).
     * **`FACT_842` (Sheath Blight):** Symptoms observed from tillering to milk stage (resolves Issue #10).
2. **95 Pathology Facts Formally Approved:**
   - Richard formally reviewed and approved 95 core facts with status `Approved` and reviewer initials `RL`.
   - Notes were attached to specific facts clarifying relative terms (e.g. `"cool" is relative and vague`).
3. **Comprehensive Typo & Terminology Scrub:**
   - Spell-checked and fixed typos in fact text (e.g., `shite head` $\rightarrow$ `white head`, `wavey` $\rightarrow$ `wavy`, `intect` $\rightarrow$ `intact`, `developement` $\rightarrow$ `development`).
   - Standardized disease labels and corrected Source access dates to `DD/MM/YYYY`.
4. **All 100 Scenarios 100% Validated:**
   - The master workbook passes automated partner checks with **0 errors and 0 broken references**.
   - SQLite Knowledge Graph (`data/rice_kg_mobile.db`) has been recompiled with all 842 facts, 136 terminology concepts, and 32 sources.

---

## 2. Detailed Review of Richard's Column J Notes

Richard added comments to **Column J ("NOTES")** in `Data_Issues`. Here is the complete triage:

### Category A: Issues Resolved by Richard (Marked "Done" or "Resolved in Fact Table")
* **Issue #6 (Blast — Neck blast symptoms):**
  * *Richard's Note:* Added `FACT_289` (greyish-brown lesions at node below ear) and `FACT_290` (inflorescence breaks off at rotten neck) to `Disease_profile`.
* **Issue #7 (Blast — Gray mold layer & reddish-brown parts):**
  * *Richard's Note:* Amended fact text to explicitly state the affected plant parts (stem base and upper canopy).
* **Issue #9 (Bacterial Blight — Growth stage & sheath symptoms):**
  * *Richard's Note:* Added `FACT_057` (leaf sheath). Amended `FACT_053` to specify "Older plants", and added `FACT_840` for booting stage grain damage.
* **Issue #10 (Sheath Blight — Sclerotia & growth stages):**
  * *Richard's Note:* Sourced and added `FACT_841` (sclerotia dark nodules) and `FACT_842` (tillering to milk stage).
* **Issue #13 & #20 (Typos & Spelling):**
  * *Richard's Note:* Ran spell-check across all facts; fixed `shite head`, `wavey`, `Sesamia inference`, etc.
* **Issue #26 (Source Access Dates):**
  * *Richard's Note:* Standardized five day/month swapped access dates to uniform `DD/MM/YYYY`.

---

### Category B: Outstanding Issues & Questions for Monday's Meeting

These are the specific questions Richard raised in Column J where our team (Srikanth, Faezeh, Ginny, Aseel, Richard) needs to agree during Monday's meeting:

#### 1. Fact Approval & Evidence Rating Criteria (Issues #15 & #17 — Srikanth Review)
* **The Issue:** 747 facts are still awaiting SME evidence strength rating and review.
* **Richard's Question in Col J:**  
  > *"Please could I have some guidance about approving facts and describing the strength of evidence. Should this be based on:  
  > (1) the strength of evidence in the SOURCE?  
  > (2) the collected evidence from all SOURCES?  
  > (3) the strength of evidence based on my own SME understanding?  
  > Perhaps we can discuss in a meeting."*
* **Recommended Team Decision for Monday:**
  * Adopt a simple 2-tier rating:
    * **Tier 1 (Strong Consensus):** Supported by institutional extension guides (IRRI, CABI) or confirmed by Richard's expert agronomic judgment.
    * **Tier 2 (Context-Dependent):** Academic paper claims that depend on specific cultivars or micro-climates.
  * Richard can approve the remaining facts based on **Option 3 (his own SME expert knowledge)**, which is standard for agricultural SLM grounding.

#### 2. Symptom Partitioning: Leaf vs. Node/Neck/Panicle (Issue #2 & #6)
* **The Issue:** `FACT_098` mentions node lesions; `FACT_318` mentions lesions appearing within 96 hours.
* **Richard's Question in Col J:**  
  > *"The lesions are mentioned on nodes in the fact. The 'Main symptom' in the Disease Profile does not specify where the lesions are located, rather than specifying that they are leaf lesions. Should I leave this, or amend the Symptoms list to have separate lines for leaf vs. other parts (Node, neck, stem, etc.)?"*
* **Recommended Team Decision for Monday:**
  * In the Disease Profiles, separate **foliar symptoms** from **panicle/neck/stem symptoms**. This prevents confusion between leaf blast (Track 1 / Track 2) and catastrophic neck blast (Track 3: Escalation).

#### 3. Environmental Condition Phrasing (Issue #3)
* **The Issue:** Discrepancy between "waterlogged soils" and facts describing shallow flood / moist soil (`FACT_304`/`594`).
* **Richard's Question in Col J:**  
  > *"Both mention shallow flood and moist soil, both of which link to having waterlogged soil. Should I remove these FACTs, or would it be better to change the description to 'Excessively moist or waterlogged soils'? Also for bacterial ooze, I've now included FACT_078 'Small milky drops of ooze' to make it comprehensive."*
* **Recommended Team Decision for Monday:**
  * Approve Richard's suggested phrasing: *"Excessively moist or waterlogged soils"*.
  * Confirm that combining `FACT_078` (milky drops) + `FACT_229` (ooze) + `FACT_079` (ooze dries to crust) is biologically sound.

#### 4. Source Licensing & Copyright Permissions (Issues #23, #24, #25, #27, #28)
* **The Issue:** Training permissions on sources.
* **Richard's Notes in Col J:**
  * `SOURCE_020` is copyrighted by Elsevier; `SOURCE_021` appears open access but under U.S. Title 17; IRRI pages show `CC BY-NC-SA 3.0`.
  * `SOURCE_026` was registered but no facts were extracted because the source was deemed inadequate quality.
* **Recommended Team Decision for Monday (with Srikanth):**
  * For IRRI pages: Confirm `CC BY-NC-SA 3.0` for non-commercial research use.
  * For `SOURCE_026`: Remove or mark as inactive in `source-registry.csv` rather than renumbering all subsequent sources.

#### 5. Look-alike Scope & Action Guardrails (Issues #31, #32, #33)
* **The Issue:** Defining escalation triggers and pesticide safeguards.
* **Current Status in our Implementation (Ready to Present to Richard):**
  * **Escalation Rules (Issue #31):** Triggered when farmers request commercial chemical brands/doses, or when catastrophic panic symptoms appear (whole-field panicle rot / neck rot / rapid wilting).
  * **Look-alike Scope (Issue #32):** Brown Spot is fully supported as an acceptable differential (137 facts). Bacterial Leaf Streak (BLS) and Sheath Rot serve as differential distractors.
  * **Action Safeguards (Issue #33):** Zero chemical brand names or volumetric dosages are ever output. The SLM recommends cultural IPM (balanced nitrogen, water management, certified resistant seed) and directs chemical questions to human extension officers.

---

## 3. Demo Updates Summary

All demo assets have been synchronized to reflect Richard's latest updates:

| Asset | Status | Update Details |
|---|---|---|
| **`demo_rice_slm.py`** | Updated & Tested | Audit now reflects **842 verified facts** and **95 SME-approved facts** by `RL`. |
| **`diagnose.py`** | Updated & Tested | Interactive CLI tester loads all 842 facts and 132 concepts with live retrieval. |
| **`demo_dashboard.html`** | Rebuilt & Updated | Displays **"✓ Approved (RL)"** badges on approved facts, shows Richard's SME notes in gold callouts, and includes the live browser diagnostic tester tab. |
| **`data/rice_kg_mobile.db`** | Recompiled | SQLite mobile Knowledge Graph has 842 rows in `facts`, 136 in `terminology`, and 32 in `sources`. |
| **Desktop Package & Zip** | Synced | Updated in `/Users/faezeh/Desktop/Rice_SLM_Scenarios_Package/` and `Rice_SLM_Scenarios_Package.zip`. |

---

## 4. Suggested Agenda for Monday's Meeting

1. **Demonstration (5 mins):** Faezeh runs `demo_rice_slm.py --presentation` (or browser dashboard) to show the 3 tracks running on Richard's 842 facts.
2. **Review of Richard's Approved Facts (5 mins):** Celebrate the 95 approved facts and review the 3 new facts (`FACT_840-842`).
3. **Decisions on Outstanding Items (15 mins):**
   * *Item 1:* Establish guidelines for Richard to rate the remaining facts (Option 3: expert SME understanding).
   * *Item 2:* Formally approve symptom separation (leaf vs. node/panicle).
   * *Item 3:* Finalize IRRI and CABI license classification with Srikanth.
   * *Item 4:* Confirm the chemical safety guardrails (cultural IPM only, extension referral for spray rates).
4. **Handoff to Fei (5 mins):** Confirm Fei begins SFT on the 50 AI-drafted scenarios while the 50 Human scenarios remain locked for Gold benchmark testing.
