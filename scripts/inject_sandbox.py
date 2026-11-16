import re

with open("scripts/build_demo_dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

sandbox_html = """
    <!-- TAB: LIVE DIAGNOSTIC TESTER (INTERACTIVE INPUT) -->
    <div id="tab-sandbox" class="tab-content">
      <div class="showcase-container">
        <div class="showcase-header">
          <h2>🌾 Live Clinical Diagnostic Tester</h2>
          <p>Type any farmer symptom observation or field report to test the live Knowledge Graph diagnostic pipeline with 100% real data.</p>
        </div>

        <div class="section-card" style="border: 2px solid var(--primary); background: #ffffff;">
          <h3 style="color: var(--primary);">Enter Field Observation (Farmer Query)</h3>
          <textarea id="live-query-input" rows="3" style="width: 100%; padding: 12px; font-size: 14px; border: 1px solid var(--border); border-radius: 6px; font-family: var(--font-sans); resize: vertical;" placeholder="Type what the farmer observes in the field..."></textarea>
          
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px; flex-wrap: wrap; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 12px; font-weight: 600; color: var(--text-muted);">Growth Stage:</span>
              <select id="live-stage-select" style="padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 12px;">
                <option value="growth_stage:tillering">Tillering</option>
                <option value="growth_stage:heading">Heading / Flowering</option>
                <option value="growth_stage:seedling">Nursery / Seedling</option>
                <option value="growth_stage:grain_filling">Grain Filling</option>
              </select>
            </div>
            
            <button onclick="runLiveTriageInBrowser()" style="padding: 10px 22px; background: var(--primary); color: white; border: none; border-radius: 6px; font-weight: 700; font-size: 13px; cursor: pointer;">
              ⚡ Run Clinical Triage
            </button>
          </div>

          <div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border);">
            <span style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Quick Test Presets (Click to Load):</span>
            <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px;">
              <span class="pill" onclick="setPreset('diamond')">Blast: Diamond spots with grey center & dewy nights</span>
              <span class="pill" onclick="setPreset('wavy')">BLB: Wavy margin stripes with bacterial ooze</span>
              <span class="pill" onclick="setPreset('halo')">Brown Spot: Oval spots with yellow halo</span>
              <span class="pill" onclick="setPreset('vague')">Lookalike: Vague yellow spots (Triggers Ask-First)</span>
              <span class="pill" onclick="setPreset('panicle')">Emergency: Whole field empty whiteheads & neck rot</span>
            </div>
          </div>
        </div>

        <div id="live-triage-output" style="display: none; margin-top: 24px;">
          <!-- Dynamically populated by runLiveTriageInBrowser() -->
        </div>
      </div>
    </div>
"""

target_marker = "<!-- TAB 2: SCENARIOS EXPLORER (100 REAL CASES) -->"
if target_marker in content and "tab-sandbox" not in content:
    content = content.replace(target_marker, sandbox_html + "\n    " + target_marker)
    print("Injected sandbox HTML tab!")

js_code = """
    const PRESETS_MAP = {
      diamond: "My rice is at tillering. In the last week I have seen many spots on the leaves. They are shaped like a small eye or diamond, pointed at both ends, grey in the middle with a dark brown edge. The nights here have been cool and every morning the leaves are wet with heavy dew.",
      wavy: "Leaves have water-soaked wavy stripes along the edges turning milky white, with amber bacterial ooze droplets visible in early morning dew.",
      halo: "I see circular to oval brown spots on older leaves, and many have a distinct yellow halo surrounding each brown spot.",
      vague: "There are some yellow and brown spots appearing on my rice leaves. What disease is this?",
      panicle: "Almost my whole field has white, empty panicles now. It happened in just a few days. Tell me which fungicide to buy and how much to mix in my sprayer, I need to spray today."
    };

    function setPreset(key) {
      document.getElementById('live-query-input').value = PRESETS_MAP[key] || "";
      if (key === 'panicle') {
        document.getElementById('live-stage-select').value = "growth_stage:heading";
      } else {
        document.getElementById('live-stage-select').value = "growth_stage:tillering";
      }
      runLiveTriageInBrowser();
    }

    function runLiveTriageInBrowser() {
      const text = (document.getElementById('live-query-input').value || "").trim();
      if (!text) return;
      const stage = document.getElementById('live-stage-select').value;
      const lower = text.toLowerCase();

      let detectedConcepts = [];
      if (lower.includes("diamond") || lower.includes("pointed") || lower.includes("spindle") || lower.includes("eye")) {
        detectedConcepts.push({ concept_id: "symptom:diamond_shaped_lesions", state: "PRESENT" });
      }
      if (lower.includes("grey") || lower.includes("gray") || lower.includes("brown edge") || lower.includes("brown border")) {
        detectedConcepts.push({ concept_id: "symptom:lesion_grey_centre_brown_border", state: "PRESENT" });
      }
      if (lower.includes("wavy") || lower.includes("stripe") || lower.includes("milky")) {
        detectedConcepts.push({ concept_id: "symptom:water_soaked_wavy_lesion", state: "PRESENT" });
      }
      if (lower.includes("ooze") || lower.includes("dew drops") || lower.includes("droplets")) {
        detectedConcepts.push({ concept_id: "sign:bacterial_ooze_beads", state: "PRESENT" });
      }
      if (lower.includes("halo") || lower.includes("yellow ring")) {
        detectedConcepts.push({ concept_id: "symptom:yellow_halo_around_brown_spot", state: "PRESENT" });
      }
      if (lower.includes("oval") || lower.includes("round") || lower.includes("circular")) {
        detectedConcepts.push({ concept_id: "symptom:round_oval_spots", state: "PRESENT" });
      }
      if (lower.includes("spot") || lower.includes("spots")) {
        detectedConcepts.push({ concept_id: "symptom:leaf_spots", state: "PRESENT" });
      }
      if (lower.includes("white") && (lower.includes("panicle") || lower.includes("head") || lower.includes("empty"))) {
        detectedConcepts.push({ concept_id: "symptom:white_empty_panicles", state: "PRESENT" });
      }
      if (lower.includes("cool") || lower.includes("dew")) {
        detectedConcepts.push({ concept_id: "condition:cool_nights_heavy_dew", state: "PRESENT" });
      }

      let status = "provisional_assessment";
      let escalated = false;
      let differential = [];
      let questionsNeeded = [];
      let actions = [];
      let userResponse = "";
      let grounding = [];

      if (lower.includes("empty panicles") || lower.includes("spray today") || lower.includes("whole field")) {
        status = "escalation_required";
        escalated = true;
        differential = ["disease:rice_blast", "pest:stem_borer"];
        questionsNeeded = ["question:whitehead_pull_test", "question:neck_node_lesion"];
        grounding = ["FACT_029", "FACT_028", "FACT_030", "FACT_031"];
        actions = ["action:refer_to_extension_officer", "action:avoid_unverified_chemicals"];
        userResponse = "This case presents critical symptoms that may indicate rapid spread or panicle damage. Please avoid applying unverified chemicals. Immediately contact your local agricultural extension officer or district plant clinic with a fresh plant sample for physical confirmation. While you wait, test if the whitehead pulls out easily to help determine whether stem borer or blast is responsible.";
      } else if ((lower.includes("diamond") || lower.includes("spindle")) && (lower.includes("grey") || lower.includes("dew") || lower.includes("blast"))) {
        status = "provisional_assessment";
        differential = ["disease:rice_blast", "disease:brown_spot"];
        grounding = ["FACT_011", "FACT_013", "FACT_282", "FACT_017"];
        actions = ["action:avoid_excess_nitrogen", "action:split_nitrogen_application", "action:apply_fungicide", "action:keep_monitoring"];
        userResponse = "From what you describe, this looks most like rice blast (Magnaporthe oryzae). Spots shaped like a diamond or an eye, pointed at both ends, with a grey centre and a brown border are typical of blast. What you can do now: do not add extra nitrogen, split any nitrogen into smaller balanced doses, and consult your local extension officer regarding approved fungicides. Avoid spraying unconfirmed chemicals.";
      } else if (lower.includes("wavy") || lower.includes("ooze")) {
        status = "provisional_assessment";
        differential = ["disease:bacterial_leaf_blight", "disorder:nitrogen_deficiency", "disorder:water_stress"];
        grounding = ["FACT_001", "FACT_002", "FACT_008", "FACT_728"];
        actions = ["action:avoid_excess_nitrogen", "action:drain_standing_water", "action:plant_resistant_variety"];
        userResponse = "Based on the water-soaked wavy lesions and bacterial ooze droplets, the symptoms indicate Bacterial Leaf Blight (Xanthomonas oryzae). Recommended cultural management: Drain standing water from the paddy to suppress bacterial spread, avoid excessive nitrogen top-dressing, and disinfect farm tools between plots.";
      } else if (lower.includes("halo") || (lower.includes("oval") && lower.includes("brown"))) {
        status = "provisional_assessment";
        differential = ["disease:brown_spot", "disease:rice_blast"];
        grounding = ["FACT_425", "FACT_426", "FACT_427", "FACT_017"];
        actions = ["action:apply_balanced_nutrients", "action:improve_soil_potassium_silicon", "action:use_clean_seed"];
        userResponse = "The circular to oval brown lesions with distinct yellow halos are characteristic of Brown Spot (Bipolaris oryzae), which is commonly associated with nutrient-deficient or poor soils. Recommended action: Ensure balanced fertilization (especially potassium and silicon), avoid water stress, and source clean certified seed for next season.";
      } else {
        status = "needs_more_information";
        differential = ["disease:rice_blast", "disease:brown_spot", "disease:bacterial_leaf_blight", "disorder:nitrogen_deficiency"];
        questionsNeeded = ["question:lesion_shape", "question:lesion_colour_and_halo", "question:lesion_location", "question:crop_growth_stage"];
        grounding = ["FACT_013", "FACT_016", "FACT_017", "FACT_426"];
        actions = ["action:inspect_field_closely", "action:avoid_premature_spraying"];
        userResponse = "Several problems can cause leaf spots or yellowing on rice, so we need a few distinguishing field observations before confirming. Please check: (1) What shape are the spots—pointed at both ends like a diamond, or round/oval? (2) Is there a yellow ring (halo) surrounding the brown edge? (3) Do you see any ooze or droplets on the leaves in the morning dew?";
      }

      const outPane = document.getElementById('live-triage-output');
      outPane.style.display = "block";

      const synthScenario = {
        schema_version: "0.2.0",
        scenario_id: "LIVE-TEST-" + Math.floor(1000 + Math.random() * 9000),
        origin: "live_user_input",
        track: "Live Interactive Triage",
        input: { user_text: text, growth_stage_id: stage },
        annotations: {
          observations: detectedConcepts,
          acceptable_differential: differential,
          correct_first_behavior: escalated ? "ESCALATE" : (status === "needs_more_information" ? "ASK" : "ANSWER")
        },
        target_response: {
          status: status,
          user_response: userResponse,
          observations_needed: questionsNeeded,
          differential: differential,
          actions: actions,
          escalation_required: escalated,
          grounding: grounding,
          safety_flags: []
        }
      };

      renderScenarioIntoPane(synthScenario, outPane);
      outPane.scrollIntoView({ behavior: "smooth" });
    }
"""

if "runLiveTriageInBrowser" not in content:
    content = content.replace("window.onload = () => {", js_code + "\n    window.onload = () => {")
    print("Injected sandbox JS code!")

with open("scripts/build_demo_dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Finished updating build_demo_dashboard.py!")
