#!/usr/bin/env python3
"""
scripts/enhance_dashboard_editor.py
Enhances demo_dashboard.html and scripts/build_demo_dashboard.py with:
  1. "✏️ Edit Scenario" button & Interactive Modal
  2. "✅ Verify & Sign Off (Human Gold)" button & Quick Modal
  3. "➕ Add New Scenario" button & Modal in Header
  4. Live API synchronization with Excel (via demo_app.py)
"""

import os
import re

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD_SCRIPT = os.path.join(WORKSPACE_ROOT, "scripts/build_demo_dashboard.py")

MODAL_CSS = """
    /* Editor & Action Modals */
    .modal-backdrop {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(15, 23, 42, 0.65);
      backdrop-filter: blur(4px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }
    .modal-backdrop.active {
      display: flex;
    }
    .modal-card {
      background: #ffffff;
      border-radius: 12px;
      width: 720px;
      max-width: 95vw;
      max-height: 90vh;
      display: flex;
      flex-direction: column;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.1);
      overflow: hidden;
      animation: modalFadeIn 0.2s ease-out;
    }
    @keyframes modalFadeIn {
      from { opacity: 0; transform: scale(0.96); }
      to { opacity: 1; transform: scale(1); }
    }
    .modal-header {
      padding: 18px 24px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #f8fafc;
    }
    .modal-header h3 {
      font-size: 16px;
      font-weight: 700;
      color: #0f172a;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .modal-close-btn {
      background: none;
      border: none;
      font-size: 20px;
      color: #64748b;
      cursor: pointer;
      line-height: 1;
    }
    .modal-body {
      padding: 24px;
      overflow-y: auto;
      flex: 1;
    }
    .modal-footer {
      padding: 16px 24px;
      border-top: 1px solid var(--border);
      background: #f8fafc;
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }
    .form-group {
      margin-bottom: 16px;
    }
    .form-group label {
      display: block;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      color: #475569;
      margin-bottom: 6px;
    }
    .form-group input, .form-group select, .form-group textarea {
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-family: var(--font-sans);
      font-size: 13px;
      outline: none;
      transition: border-color 0.15s ease;
    }
    .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
      border-color: var(--primary);
    }
    .form-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .form-hint {
      font-size: 11px;
      color: #64748b;
      margin-top: 4px;
    }
    /* Toast Notification */
    .toast-box {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #10b981;
      color: white;
      padding: 14px 20px;
      border-radius: 8px;
      box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
      font-size: 14px;
      font-weight: 600;
      display: none;
      align-items: center;
      gap: 10px;
      z-index: 2000;
      animation: toastSlide 0.25s ease-out;
    }
    @keyframes toastSlide {
      from { transform: translateY(20px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }
"""

MODALS_HTML = """
  <!-- Toast Notification -->
  <div id="toast" class="toast-box">
    <span id="toast-icon">✓</span>
    <span id="toast-msg">Updated successfully!</span>
  </div>

  <!-- 1. EDIT SCENARIO MODAL -->
  <div id="edit-modal" class="modal-backdrop">
    <div class="modal-card">
      <div class="modal-header">
        <h3>✏️ Edit Scenario: <span id="edit-modal-sid">SCN-000001</span></h3>
        <button class="modal-close-btn" onclick="closeEditModal()">×</button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="edit-sid">
        
        <div class="form-row">
          <div class="form-group">
            <label>Track Split</label>
            <select id="edit-track">
              <option value="Human (gold test)">Human (gold test) — Locked Benchmark</option>
              <option value="AI-drafted (train/val)">AI-drafted (train/val) — Training Pool</option>
            </select>
          </div>
          <div class="form-group">
            <label>Clinical Behavior / Status</label>
            <select id="edit-status">
              <option value="ANSWER">ANSWER — Direct Provisional Diagnosis</option>
              <option value="ASK">ASK — Ask-First Clarifying Questions</option>
              <option value="ESCALATE">ESCALATE — Emergency Escalation to Extension</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Growth Stage</label>
            <select id="edit-stage">
              <option value="growth_stage:tillering">Tillering</option>
              <option value="growth_stage:heading">Heading / Flowering</option>
              <option value="growth_stage:seedling">Nursery / Seedling</option>
              <option value="growth_stage:grain_filling">Grain Filling / Maturing</option>
            </select>
          </div>
          <div class="form-group">
            <label>Review Status</label>
            <select id="edit-review-status">
              <option value="Done">Done — Verified & Approved</option>
              <option value="In progress">In progress</option>
              <option value="Not started">Not started</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>Farmer Field Observation (user_input)</label>
          <textarea id="edit-user-input" rows="3" placeholder="What the farmer observes in the field (no disease names)..."></textarea>
          <div class="form-hint">Describe symptoms authentically from farmer or extension worker perspective.</div>
        </div>

        <div class="form-group">
          <label>Clinical Observations (3-Valued Logic: concept_id = STATE)</label>
          <textarea id="edit-observations" rows="3" style="font-family: var(--font-mono); font-size: 12px;" placeholder="symptom:diamond_shaped_lesions = PRESENT&#10;symptom:yellow_halo = UNKNOWN"></textarea>
          <div class="form-hint">One observation per line. Use PRESENT, ABSENT, or UNKNOWN.</div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Acceptable Differential (Candidate Causes)</label>
            <input type="text" id="edit-diff" placeholder="disease:rice_blast; disease:brown_spot">
          </div>
          <div class="form-group">
            <label>Distinguishing Checks Needed (Ask-First Questions)</label>
            <input type="text" id="edit-questions" placeholder="question:lesion_shape; question:yellow_halo">
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Cultural IPM Actions</label>
            <input type="text" id="edit-actions" placeholder="action:avoid_excess_nitrogen; action:split_nitrogen">
          </div>
          <div class="form-group">
            <label>Cited Grounding Facts (Richard Fact IDs)</label>
            <input type="text" id="edit-facts" placeholder="FACT_011, FACT_013, FACT_282">
          </div>
        </div>

        <div class="form-group">
          <label>Model Advisor Response to Farmer (user_response)</label>
          <textarea id="edit-user-response" rows="4" placeholder="Compassionate, grounded advisor explanation with cultural IPM actions..."></textarea>
          <div class="form-hint">Enforce chemical safety: do NOT include commercial brand names or volumetric pesticide doses.</div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Reviewer / Peer Checker</label>
            <input type="text" id="edit-checker" placeholder="Aseel or Ginny">
          </div>
          <div class="form-group">
            <label>Reviewer Notes / Rationales</label>
            <input type="text" id="edit-notes" placeholder="e.g. Verified against IRRI blast profile">
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="nav-btn" onclick="closeEditModal()">Cancel</button>
        <button class="nav-btn" style="background: #0284c7; color: white; border: none; font-weight: 700;" onclick="submitEditScenario()">
          💾 Save Changes & Update Excel Sheet
        </button>
      </div>
    </div>
  </div>

  <!-- 2. QUICK VERIFY & SIGN OFF MODAL -->
  <div id="verify-modal" class="modal-backdrop">
    <div class="modal-card" style="width: 500px;">
      <div class="modal-header">
        <h3>✅ Sign Off as Human Gold Benchmark</h3>
        <button class="modal-close-btn" onclick="closeVerifyModal()">×</button>
      </div>
      <div class="modal-body">
        <p style="font-size: 14px; color: #334155; margin-bottom: 16px;">
          You are verifying scenario <strong id="verify-sid" style="color: #0284c7;">SCN-000001</strong> as an officially approved <strong>Human Gold Test benchmark</strong>.
        </p>

        <div class="form-group">
          <label>Your Name (Reviewer)</label>
          <select id="verify-reviewer">
            <option value="Aseel">Aseel Ali (Blast & Stem Borer Lead)</option>
            <option value="Ginny">Ginny Hayes (BLB & Sheath Blight Lead)</option>
            <option value="Faezeh">Faezeh (Knowledge Graph Lead)</option>
            <option value="Richard">Richard (Plant Pathology SME)</option>
          </select>
        </div>

        <div class="form-group">
          <label>Verification Note</label>
          <input type="text" id="verify-note" value="Verified and approved as official Human Gold Benchmark">
        </div>

        <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 12px; font-size: 12px; color: #065f46;">
          ✓ This will update <strong>review_status = "Done"</strong> in the Excel workbook and mark this case as officially locked for Gold evaluation.
        </div>
      </div>
      <div class="modal-footer">
        <button class="nav-btn" onclick="closeVerifyModal()">Cancel</button>
        <button class="nav-btn" style="background: #10b981; color: white; border: none; font-weight: 700;" onclick="submitVerifyScenario()">
          ✓ Confirm & Update Excel
        </button>
      </div>
    </div>
  </div>

  <!-- 3. ADD NEW SCENARIO MODAL -->
  <div id="add-modal" class="modal-backdrop">
    <div class="modal-card">
      <div class="modal-header">
        <h3>➕ Add New Clinical Scenario</h3>
        <button class="modal-close-btn" onclick="closeAddModal()">×</button>
      </div>
      <div class="modal-body">
        <div class="form-row">
          <div class="form-group">
            <label>Target Track</label>
            <select id="add-track">
              <option value="Human (gold test)">Human (gold test) — Add to Gold Evaluation Set</option>
              <option value="AI-drafted (train/val)">AI-drafted (train/val) — Add to Training Set</option>
            </select>
          </div>
          <div class="form-group">
            <label>Focus Disease Condition</label>
            <select id="add-disease">
              <option value="Rice blast">Rice Blast</option>
              <option value="Bacterial leaf blight">Bacterial Leaf Blight</option>
              <option value="Brown spot">Brown Spot</option>
              <option value="Sheath blight">Sheath Blight</option>
              <option value="Yellow stem borer">Yellow Stem Borer</option>
              <option value="Nitrogen deficiency">Nitrogen Deficiency</option>
              <option value="Water stress">Water Stress</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Author / Owner</label>
            <select id="add-owner">
              <option value="Aseel">Aseel</option>
              <option value="Ginny">Ginny</option>
              <option value="Faezeh">Faezeh</option>
            </select>
          </div>
          <div class="form-group">
            <label>Clinical Behavior</label>
            <select id="add-status">
              <option value="ANSWER">ANSWER (Direct diagnosis)</option>
              <option value="ASK">ASK (Ask clarifying questions first)</option>
              <option value="ESCALATE">ESCALATE (Emergency escalation)</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>Seed Idea (Scenario Summary)</label>
          <input type="text" id="add-seed" placeholder="e.g. Rainfed upland rice with small diamond spots appearing after humid nights">
        </div>

        <div class="form-group">
          <label>Farmer Field Observation (user_input)</label>
          <textarea id="add-user-input" rows="3" placeholder="What the farmer tells the extension worker..."></textarea>
        </div>

        <div class="form-group">
          <label>Clinical Observations (concept_id = STATE)</label>
          <textarea id="add-observations" rows="2" style="font-family: var(--font-mono); font-size: 12px;" placeholder="symptom:diamond_shaped_lesions = PRESENT&#10;condition:cool_nights = PRESENT"></textarea>
        </div>

        <div class="form-group">
          <label>Advisor Response to Farmer (user_response)</label>
          <textarea id="add-user-response" rows="3" placeholder="Compassionate advisor explanation with safe cultural IPM actions..."></textarea>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Grounded Fact IDs</label>
            <input type="text" id="add-facts" placeholder="FACT_011, FACT_013">
          </div>
          <div class="form-group">
            <label>Cultural Actions</label>
            <input type="text" id="add-actions" placeholder="action:avoid_excess_nitrogen">
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="nav-btn" onclick="closeAddModal()">Cancel</button>
        <button class="nav-btn" style="background: #059669; color: white; border: none; font-weight: 700;" onclick="submitAddScenario()">
          ➕ Add & Save to Excel Workbook
        </button>
      </div>
    </div>
  </div>
"""

JS_LOGIC = """
    function showToast(msg, isSuccess = true) {
      const toast = document.getElementById("toast");
      if (!toast) return;
      document.getElementById("toast-msg").textContent = msg;
      toast.style.background = isSuccess ? "#10b981" : "#ef4444";
      toast.style.display = "flex";
      setTimeout(() => { toast.style.display = "none"; }, 3500);
    }

    function openVerifyModal(sid) {
      document.getElementById("verify-sid").textContent = sid;
      document.getElementById("verify-modal").classList.add("active");
    }

    function closeVerifyModal() {
      document.getElementById("verify-modal").classList.remove("active");
    }

    async function submitVerifyScenario() {
      const sid = document.getElementById("verify-sid").textContent;
      const reviewer = document.getElementById("verify-reviewer").value;
      const notes = document.getElementById("verify-note").value;

      try {
        const resp = await fetch("/api/scenarios/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scenario_id: sid, reviewer: reviewer, notes: notes })
        });
        const res = await resp.json();
        if (res.success) {
          showToast(`✓ Scenario ${sid} signed off as Human Gold in Excel!`);
          closeVerifyModal();
          // Update in-memory scenario
          const target = SCENARIOS.find(s => s.scenario_id === sid);
          if (target) {
            target.review_status = "Done";
            target.peer_checker = reviewer;
            renderScenarioIntoPane(target, document.getElementById("scenario-content-pane") || document.getElementById("showcase-detail"));
            renderScenariosList();
          }
        } else {
          showToast(`Error: ${res.error || "Failed to update Excel"}`, false);
        }
      } catch (err) {
        showToast(`Offline mode: Update saved in memory. Run 'python3 demo_app.py' to save directly to Excel on disk.`, true);
        closeVerifyModal();
        const target = SCENARIOS.find(s => s.scenario_id === sid);
        if (target) {
          target.review_status = "Done";
          renderScenariosList();
        }
      }
    }

    function openEditModal(sid) {
      const scn = SCENARIOS.find(s => s.scenario_id === sid);
      if (!scn) return;

      document.getElementById("edit-modal-sid").textContent = sid;
      document.getElementById("edit-sid").value = sid;
      document.getElementById("edit-track").value = scn.track || "Human (gold test)";
      document.getElementById("edit-status").value = scn.annotations.correct_first_behavior || "ANSWER";
      document.getElementById("edit-stage").value = scn.input.growth_stage_id || "growth_stage:tillering";
      document.getElementById("edit-review-status").value = scn.review_status || "Done";
      document.getElementById("edit-user-input").value = scn.input.user_text || "";

      // Observations
      const obsLines = (scn.annotations.observations || []).map(o => `${o.concept_id} = ${o.state || "PRESENT"}`).join("\\n");
      document.getElementById("edit-observations").value = obsLines;

      document.getElementById("edit-diff").value = (scn.annotations.acceptable_differential || []).join("; ");
      document.getElementById("edit-questions").value = (scn.target_response.observations_needed || []).join("; ");
      document.getElementById("edit-actions").value = (scn.target_response.actions || []).join("; ");
      document.getElementById("edit-facts").value = (scn.target_response.grounding || []).join(", ");
      document.getElementById("edit-user-response").value = scn.target_response.user_response || "";
      document.getElementById("edit-checker").value = scn.peer_checker || "Aseel";
      document.getElementById("edit-notes").value = scn.peer_notes || "";

      document.getElementById("edit-modal").classList.add("active");
    }

    function closeEditModal() {
      document.getElementById("edit-modal").classList.remove("active");
    }

    async function submitEditScenario() {
      const sid = document.getElementById("edit-sid").value;
      const track = document.getElementById("edit-track").value;
      const status = document.getElementById("edit-status").value;
      const stage = document.getElementById("edit-stage").value;
      const reviewStatus = document.getElementById("edit-review-status").value;
      const userInput = document.getElementById("edit-user-input").value.trim();
      const userResponse = document.getElementById("edit-user-response").value.trim();

      const obsRaw = document.getElementById("edit-observations").value.split("\\n").filter(l => l.trim());
      const parsedObs = obsRaw.map(l => {
        if (l.includes("=")) {
          const parts = l.split("=");
          return { concept_id: parts[0].trim(), state: parts[1].trim().toUpperCase() };
        }
        return { concept_id: l.trim(), state: "PRESENT" };
      });

      const diff = document.getElementById("edit-diff").value.split(";").map(s => s.trim()).filter(Boolean);
      const questions = document.getElementById("edit-questions").value.split(";").map(s => s.trim()).filter(Boolean);
      const actions = document.getElementById("edit-actions").value.split(";").map(s => s.trim()).filter(Boolean);
      const facts = document.getElementById("edit-facts").value.split(",").map(s => s.trim()).filter(Boolean);
      const checker = document.getElementById("edit-checker").value.trim();
      const notes = document.getElementById("edit-notes").value.trim();

      const payload = {
        scenario_id: sid,
        track: track,
        status: status,
        growth_stage_id: stage,
        user_input: userInput,
        user_response: userResponse,
        observations: parsedObs,
        differential: diff,
        acceptable_differential: diff,
        required_questions: questions,
        actions: actions,
        evidence_fact_ids: facts,
        escalation_required: status === "ESCALATE",
        review_status: reviewStatus,
        peer_checker: checker,
        peer_notes: notes
      };

      try {
        const resp = await fetch("/api/scenarios/update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();
        if (res.success) {
          showToast(`✓ Scenario ${sid} successfully updated in Excel & JSONL!`);
          closeEditModal();
          // Update in-memory scenario
          const target = SCENARIOS.find(s => s.scenario_id === sid);
          if (target) {
            target.track = track;
            target.input.user_text = userInput;
            target.input.growth_stage_id = stage;
            target.annotations.observations = parsedObs;
            target.annotations.acceptable_differential = diff;
            target.annotations.correct_first_behavior = status;
            target.target_response.status = status === "ANSWER" ? "provisional_assessment" : (status === "ASK" ? "needs_more_information" : "escalation_required");
            target.target_response.user_response = userResponse;
            target.target_response.observations_needed = questions;
            target.target_response.actions = actions;
            target.target_response.grounding = facts;
            target.review_status = reviewStatus;
            target.peer_checker = checker;

            renderScenarioIntoPane(target, document.getElementById("scenario-content-pane") || document.getElementById("showcase-detail"));
            renderScenariosList();
          }
        } else {
          showToast(`Error: ${res.error || "Failed to update"}`, false);
        }
      } catch (err) {
        showToast(`Offline mode: Update applied in memory. Run 'python3 demo_app.py' to save directly to Excel on disk.`, true);
        closeEditModal();
      }
    }

    function openAddModal() {
      document.getElementById("add-modal").classList.add("active");
    }

    function closeAddModal() {
      document.getElementById("add-modal").classList.remove("active");
    }

    async function submitAddScenario() {
      const track = document.getElementById("add-track").value;
      const disease = document.getElementById("add-disease").value;
      const owner = document.getElementById("add-owner").value;
      const status = document.getElementById("add-status").value;
      const seed = document.getElementById("add-seed").value.trim();
      const userInput = document.getElementById("add-user-input").value.trim();
      const userResponse = document.getElementById("add-user-response").value.trim();
      const facts = document.getElementById("add-facts").value.split(",").map(s => s.trim()).filter(Boolean);
      const actions = document.getElementById("add-actions").value.split(";").map(s => s.trim()).filter(Boolean);

      const obsRaw = document.getElementById("add-observations").value.split("\\n").filter(l => l.trim());
      const parsedObs = obsRaw.map(l => {
        if (l.includes("=")) {
          const parts = l.split("=");
          return { concept_id: parts[0].trim(), state: parts[1].trim().toUpperCase() };
        }
        return { concept_id: l.trim(), state: "PRESENT" };
      });

      if (!userInput) {
        alert("Please enter a farmer field observation (user_input)!");
        return;
      }

      const payload = {
        track: track,
        focus_disease: disease,
        owner: owner,
        status: status,
        seed_idea: seed || userInput.substring(0, 80),
        user_input: userInput,
        user_response: userResponse,
        observations: parsedObs,
        evidence_fact_ids: facts,
        actions: actions
      };

      try {
        const resp = await fetch("/api/scenarios/add", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();
        if (res.success) {
          showToast(`✓ New Scenario ${res.scenario_id} added and written to Excel!`);
          closeAddModal();
          // Reload scenarios from API or refresh
          setTimeout(() => { window.location.reload(); }, 1200);
        } else {
          showToast(`Error: ${res.error || "Failed to add"}`, false);
        }
      } catch (err) {
        showToast(`Offline mode: Run 'python3 demo_app.py' to save new scenarios directly to Excel!`, false);
      }
    }
"""

def update_build_script():
    with open(BUILD_SCRIPT, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Inject CSS before </style>
    if "/* Editor & Action Modals */" not in content:
        content = content.replace("</style>", MODAL_CSS + "\n  </style>")
        print("Injected Modal CSS into build script!")

    # 2. Inject Add Scenario button into header
    add_btn_html = """<button class="nav-btn" style="background: #059669; color: white; border: none; font-weight: 700; font-size: 13px; display: inline-flex; align-items: center; gap: 6px; cursor: pointer;" onclick="openAddModal()">
        ➕ Add New Scenario
      </button>"""
    if "openAddModal()" not in content:
        content = content.replace("<div>\n      <span class=\"badge-verified\">", f"<div style=\"display: flex; align-items: center; gap: 12px;\">\n      {add_btn_html}\n      <span class=\"badge-verified\">")
        print("Injected Add Scenario button into header!")

    # 3. Inject Modals HTML before </main>
    if "<!-- 1. EDIT SCENARIO MODAL -->" not in content:
        content = content.replace("</main>", "</main>\n" + MODALS_HTML)
        print("Injected Modals HTML into build script!")

    # 4. Inject JS logic
    if "function openEditModal" not in content:
        content = content.replace("window.onload = () => {", JS_LOGIC + "\n    window.onload = () => {")
        print("Injected JS logic into build script!")

    # 5. Inject Action Toolbar into renderScenarioIntoPane
    old_top_block = """      pane.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
          <div>
            <span style="font-family: var(--font-mono); font-size: 14px; font-weight: 800; color: #64748b;">${scn.scenario_id}</span>
            <span style="font-size: 12px; color: #94a3b8; margin-left: 8px;">(${scn.track})</span>
          </div>
          <div>${behBadge}</div>
        </div>"""

    new_top_block = """      const isVerified = scn.review_status === "Done";
      pane.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-family: var(--font-mono); font-size: 16px; font-weight: 800; color: #1e293b;">${scn.scenario_id}</span>
            <span style="font-size: 12px; color: #64748b;">(${scn.track})</span>
            ${isVerified ? '<span style="background: #dcfce7; color: #15803d; font-weight: 700; font-size: 11px; padding: 3px 8px; border-radius: 4px;">✓ Human Gold Verified</span>' : ''}
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            ${behBadge}
            <button class="nav-btn" style="background: #10b981; color: white; border: none; font-weight: 700; font-size: 12px; padding: 6px 12px; display: inline-flex; align-items: center; gap: 4px; cursor: pointer;" onclick="openVerifyModal('${scn.scenario_id}')">
              ✅ Verify & Sign Off
            </button>
            <button class="nav-btn" style="background: #0284c7; color: white; border: none; font-weight: 700; font-size: 12px; padding: 6px 12px; display: inline-flex; align-items: center; gap: 4px; cursor: pointer;" onclick="openEditModal('${scn.scenario_id}')">
              ✏️ Edit Scenario
            </button>
          </div>
        </div>"""

    if old_top_block in content:
        content = content.replace(old_top_block, new_top_block)
        print("Injected Action Toolbar into renderScenarioIntoPane!")
    else:
        print("Note: old_top_block not matched exactly in content.")

    with open(BUILD_SCRIPT, "w", encoding="utf-8") as f:
        f.write(content)

    print("Updated build_demo_dashboard.py successfully!")

if __name__ == "__main__":
    update_build_script()
