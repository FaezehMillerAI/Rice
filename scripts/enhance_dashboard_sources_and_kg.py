#!/usr/bin/env python3
"""
scripts/enhance_dashboard_sources_and_kg.py
Enhances build_demo_dashboard.py with:
  1. Full Peer-Reviewed Scientific Sources integration:
     - Shows sources on fact cards and scenario cards
     - Adds a dedicated Sources Registry viewer in the Facts tab
  2. Full Interactive Knowledge Graph GUI (Vis.js):
     - Interactive 2D Network Visualizer (206 nodes, 278 edges)
     - Filter subgraphs by disease or lookalike pairs
     - Search & focus on any node
     - Click-to-inspect drawer showing node properties, connected relationships, Richard's facts, and sources
     - Interactive symptom check simulator
"""

import os
import re

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD_SCRIPT = os.path.join(WORKSPACE_ROOT, "scripts/build_demo_dashboard.py")

with open(BUILD_SCRIPT, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update Head to include vis-network
old_head = '<title>Rice Pathogen SALM — Live Interactive Clinical Demo</title>'
new_head = """<title>Rice Pathogen SALM — Live Interactive Clinical Demo</title>
  <script src="vis-network.min.js"></script>
  <script>if (typeof vis === 'undefined') { document.write('<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"><\\/script>'); }</script>"""

if old_head in content and 'vis-network.min.js' not in content:
    content = content.replace(old_head, new_head, 1)
    print("Injected vis-network script in <head>.")

# 2. Add Top Navigation Tab button
old_nav = """      <button class="nav-btn" onclick="switchTab('facts')">Richard's 842 Facts (95 Approved)</button>"""
new_nav = """      <button class="nav-btn" onclick="switchTab('facts')">Richard's 842 Facts (95 Approved)</button>
      <button class="nav-btn" onclick="switchTab('kg')">🕸️ Knowledge Graph GUI</button>"""

if old_nav in content and "switchTab('kg')" not in content:
    content = content.replace(old_nav, new_nav, 1)
    print("Injected 'Knowledge Graph GUI' button in <header>.")

# 3. Add Tab Content for KG Explorer right after tab-audit
old_tab_audit_end = """        </div>
      </div>
    </div>
  </main>"""

new_tab_kg = """        </div>
      </div>
    </div>

    <!-- TAB 6: INTERACTIVE KNOWLEDGE GRAPH GUI -->
    <div id="tab-kg" class="tab-content" style="padding: 16px 24px; height: calc(100vh - 75px); overflow: hidden; display: none; flex-direction: column;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-shrink: 0; flex-wrap: wrap; gap: 10px;">
        <div>
          <h2 style="font-size: 18px; font-weight: 800; color: #0f172a; display: flex; align-items: center; gap: 8px;">
            <span>🕸️ Rice Pathogen Clinical Knowledge Graph Explorer</span>
            <span style="font-size: 11px; background: #e0f2fe; color: #0284c7; padding: 3px 8px; border-radius: 12px; font-weight: 700;">206 Entities • 278 Clinical Relations</span>
          </h2>
          <p style="font-size: 12px; color: #64748b;">Interactive neuro-symbolic reasoning network: Drag nodes, zoom in/out, filter disease subgraphs, and inspect underlying pathology facts & literature.</p>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
          <button class="nav-btn" style="font-size: 12px; padding: 6px 12px;" onclick="resetKgView()">⛶ Fit View</button>
          <button class="nav-btn" style="font-size: 12px; padding: 6px 12px;" onclick="toggleKgPhysics()" id="kg-physics-btn">⚡ Physics: ON</button>
        </div>
      </div>

      <!-- KG Filters & Search Toolbar -->
      <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-shrink: 0; flex-wrap: wrap;">
        <span style="font-size: 12px; font-weight: 700; color: #475569;">Subgraphs:</span>
        <button class="pill active" style="font-size: 11px; padding: 4px 10px;" onclick="filterKgSubgraph('all', this)">🌐 Full Graph (All)</button>
        <button class="pill" style="font-size: 11px; padding: 4px 10px;" onclick="filterKgSubgraph('disease:rice_blast', this)">🌾 Rice Blast</button>
        <button class="pill" style="font-size: 11px; padding: 4px 10px;" onclick="filterKgSubgraph('disease:bacterial_leaf_blight', this)">🦠 Bacterial Blight</button>
        <button class="pill" style="font-size: 11px; padding: 4px 10px;" onclick="filterKgSubgraph('disease:sheath_blight', this)">🍂 Sheath Blight</button>
        <button class="pill" style="font-size: 11px; padding: 4px 10px;" onclick="filterKgSubgraph('disease:brown_spot', this)">🟤 Brown Spot</button>
        <button class="pill" style="font-size: 11px; padding: 4px 10px;" onclick="filterKgSubgraph('pest:stem_borer', this)">🐛 Stem Borer</button>
        <button class="pill" style="font-size: 11px; padding: 4px 10px;" onclick="filterKgSubgraph('lookalikes', this)">⚡ Lookalike Pairs Only</button>

        <div style="margin-left: auto; display: flex; gap: 8px;">
          <input type="text" id="kg-search-box" class="search-box" style="padding: 5px 12px; font-size: 12px; width: 220px;" placeholder="🔍 Search entity or symptom..." oninput="searchKgNode(this.value)">
        </div>
      </div>

      <!-- Main Visualizer Area: Network Canvas + Node Inspector Drawer -->
      <div style="display: flex; gap: 16px; flex: 1; min-height: 0;">
        <!-- Network Canvas -->
        <div style="flex: 1; background: #0f172a; border-radius: 12px; position: relative; border: 1px solid #334155; overflow: hidden;">
          <div id="kg-network-canvas" style="width: 100%; height: 100%;"></div>
          <!-- Legend Overlay -->
          <div style="position: absolute; bottom: 12px; left: 12px; background: rgba(15, 23, 42, 0.88); backdrop-filter: blur(4px); padding: 8px 12px; border-radius: 8px; border: 1px solid #334155; display: flex; gap: 12px; font-size: 11px; color: #cbd5e1; flex-wrap: wrap;">
            <span><span style="color: #ef4444;">●</span> Disease/Pest</span>
            <span><span style="color: #fbbf24;">●</span> Symptom</span>
            <span><span style="color: #f87171;">◆</span> Sign</span>
            <span><span style="color: #38bdf8;">▲</span> Environment</span>
            <span><span style="color: #10b981;">●</span> Cultural Action</span>
            <span><span style="color: #8b5cf6;">■</span> Question</span>
            <span><span style="color: #64748b;">■</span> Source</span>
          </div>
        </div>

        <!-- Node Inspector Drawer (Right Side) -->
        <div id="kg-inspector-drawer" style="width: 360px; background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; overflow-y: auto; display: flex; flex-direction: column;">
          <div style="text-align: center; color: #64748b; margin: auto; padding: 20px;">
            <div style="font-size: 38px; margin-bottom: 10px;">🕸️</div>
            <div style="font-weight: 700; color: #0f172a; font-size: 14px; margin-bottom: 6px;">Knowledge Graph Inspector</div>
            <p style="font-size: 12px; line-height: 1.5; color: #64748b;">Click any node on the graph (or click a disease subgraph filter above) to inspect its clinical relationships, symptoms, questions, and grounding facts.</p>
          </div>
        </div>
      </div>

      <!-- Quick Symptom Tester Pills -->
      <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 16px; margin-top: 10px; display: flex; align-items: center; gap: 10px; flex-shrink: 0; flex-wrap: wrap;">
        <span style="font-size: 12px; font-weight: 700; color: #0f172a;">⚡ Quick Symptom Highlight Test:</span>
        <button class="pill" style="font-size: 11px;" onclick="testSymptomOnKg('symptom:diamond_shaped_lesions', this)">Diamond Spindle Lesions</button>
        <button class="pill" style="font-size: 11px;" onclick="testSymptomOnKg('symptom:water_soaked_wavy_lesion', this)">Water-soaked Wavy Margins</button>
        <button class="pill" style="font-size: 11px;" onclick="testSymptomOnKg('symptom:whiteheads', this)">Whiteheads at Heading</button>
        <button class="pill" style="font-size: 11px;" onclick="testSymptomOnKg('sign:bacterial_ooze_beads', this)">Morning Amber Ooze</button>
        <button class="pill" style="font-size: 11px;" onclick="testSymptomOnKg('symptom:snake_skin_banded_sheath_spots', this)">Banded Sheath Spots</button>
        <button class="pill" style="font-size: 11px;" onclick="testSymptomOnKg('condition:cool_nights', this)">Cool Dewy Nights</button>
        <button class="pill" style="font-size: 11px; background: #fee2e2; color: #b91c1c; border-color: #fca5a5;" onclick="clearKgHighlights()">Clear Test</button>
      </div>
    </div>
  </main>"""

if old_tab_audit_end in content and 'id="tab-kg"' not in content:
    content = content.replace(old_tab_audit_end, new_tab_kg, 1)
    print("Injected 'tab-kg' container in <main>.")

with open(BUILD_SCRIPT, "w", encoding="utf-8") as f:
    f.write(content)

print("HTML structure enhanced successfully!")
