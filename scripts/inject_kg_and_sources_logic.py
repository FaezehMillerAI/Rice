#!/usr/bin/env python3
"""
scripts/inject_kg_and_sources_logic.py
Fully integrates:
  1. Sources data and rendering in Scenarios and Facts tabs
  2. Interactive Vis.js Knowledge Graph GUI with node inspector, search, filters, and symptom testing
"""

import os
import csv
import json

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD_SCRIPT = os.path.join(WORKSPACE_ROOT, "scripts/build_demo_dashboard.py")

with open(BUILD_SCRIPT, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Update variables in JS: add SOURCES and KG_DATA
old_vars = """    const SCENARIOS = __SCENARIOS_JSON__;
    const FACTS = __FACTS_JSON__;"""

new_vars = """    const SCENARIOS = __SCENARIOS_JSON__;
    const FACTS = __FACTS_JSON__;
    const SOURCES = __SOURCES_JSON__;
    const KG_DATA = __KG_DATA_JSON__;

    let factsTabMode = 'facts';
    let kgNetwork = null;
    let kgNodesDataSet = null;
    let kgEdgesDataSet = null;
    let kgPhysicsEnabled = true;
    let activeKgTestSymptoms = new Set();"""

if old_vars in text:
    text = text.replace(old_vars, new_vars, 1)
    print("Injected SOURCES and KG_DATA JS variables.")

# 2. Update switchTab to handle 'kg'
old_switch_tab = """      if (tabId === 'facts' && !document.getElementById('facts-results-container').children.length) {
        filterFacts();
      }"""

new_switch_tab = """      if (tabId === 'facts' && !document.getElementById('facts-results-container').children.length) {
        filterFacts();
      }
      if (tabId === 'kg') {
        setTimeout(initKgNetwork, 80);
      }"""

if old_switch_tab in text:
    text = text.replace(old_switch_tab, new_switch_tab, 1)
    print("Injected 'kg' tab handler in switchTab.")

# 3. Update Facts Tab Header to add the Sources Toggle
old_facts_header = """          <div style="margin-top: 14px;">
            <input type="text" id="fact-search" class="search-box" style="max-width: 500px;" placeholder="Search facts (e.g. wavy, spindle, dew, halo, nitrogen, ooze)..." oninput="filterFacts()">
          </div>
        </div>
        <div id="facts-results-container">
          <!-- Populated by JS -->
        </div>"""

new_facts_header = """          <div style="display: flex; gap: 8px; margin-top: 14px; margin-bottom: 12px; align-items: center;">
            <button id="btn-facts-mode-facts" class="pill active" style="font-size: 12px; padding: 6px 14px;" onclick="setFactsTabMode('facts')">🔬 842 Pathology Facts</button>
            <button id="btn-facts-mode-sources" class="pill" style="font-size: 12px; padding: 6px 14px;" onclick="setFactsTabMode('sources')">📚 32 Scientific Sources Registry</button>
          </div>
          <div id="facts-search-bar" style="margin-top: 6px;">
            <input type="text" id="fact-search" class="search-box" style="max-width: 500px;" placeholder="Search facts (e.g. wavy, spindle, dew, halo, nitrogen, ooze)..." oninput="filterFacts()">
          </div>
        </div>
        <div id="facts-results-container">
          <!-- Populated by JS -->
        </div>
        <div id="sources-results-container" style="display: none; padding-top: 10px;">
          <!-- Populated by JS -->
        </div>"""

if old_facts_header in text:
    text = text.replace(old_facts_header, new_facts_header, 1)
    print("Injected Sources view toggle in tab-facts.")

# 4. Enhance renderScenarioIntoPane with Sources Section and Source Badges on Facts
old_facts_block = """      const factsHtml = (scn.target_response.grounding || []).slice(0, 5).map(fid => {
        const f = FACTS[fid];
        if (!f) return `<div class="fact-card"><span class="fact-id">${fid}</span>: Verified Fact</div>`;
        return `
          <div class="fact-card">
            <div class="fact-card-header">
              <span class="fact-id">${fid}</span>
              <span class="fact-meta">${f.disease} • ${f.category}</span>
            </div>
            <div class="fact-statement">${f.statement}</div>
          </div>
        `;
      }).join('');"""

new_facts_and_sources_block = """      const factsHtml = (scn.target_response.grounding || []).slice(0, 5).map(fid => {
        const f = FACTS[fid];
        if (!f) return `<div class="fact-card"><span class="fact-id">${fid}</span>: Verified Fact</div>`;
        const sInfo = f.source_id && SOURCES[f.source_id] ? SOURCES[f.source_id] : null;
        const sBadge = sInfo ? `<span style="background: #e0f2fe; color: #0284c7; padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 10px;" title="${sInfo.title}">📚 ${f.source_id}</span>` : '';
        return `
          <div class="fact-card">
            <div class="fact-card-header">
              <span class="fact-id">${fid}</span>
              <span class="fact-meta">${f.disease} • ${f.category}</span>
              ${sBadge}
            </div>
            <div class="fact-statement">${f.statement}</div>
          </div>
        `;
      }).join('');

      // Supporting Peer-Reviewed Sources
      const scnSourceIds = Array.from(new Set([
        ...(scn.annotations.supporting_source_ids || []),
        ...(scn.target_response.grounding || []).map(fid => FACTS[fid] ? FACTS[fid].source_id : null).filter(Boolean)
      ]));

      const sourcesCardsHtml = scnSourceIds.map(sid => {
        const s = SOURCES[sid] || { title: sid, publisher: 'IRRI / Scientific Literature', author: '', publication_date: '', license_status: 'Creative Commons' };
        return `
          <div style="background: white; border: 1px solid #e9d5ff; border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 800; color: #6b21a8; background: #f3e8ff; padding: 2px 6px; border-radius: 4px;">${sid}</span>
                <span style="font-size: 10px; color: #15803d; background: #dcfce7; padding: 1px 6px; border-radius: 10px; font-weight: 600;">✓ Training Allowed</span>
              </div>
              <div style="font-weight: 700; font-size: 12px; color: #1e1b4b; line-height: 1.35; margin-bottom: 4px;">${s.title}</div>
            </div>
            <div style="font-size: 11px; color: #64748b; margin-top: 6px; border-top: 1px dashed #f3e8ff; padding-top: 4px;">
              ${s.author ? s.author + ' • ' : ''}${s.publisher || ''} ${s.publication_date ? '(' + s.publication_date + ')' : ''}
            </div>
          </div>
        `;
      }).join('');

      const sourcesHtml = scnSourceIds.length > 0 ? `
        <div class="section-card" style="border-left: 4px solid #8b5cf6; background: #faf5ff;">
          <h3 style="color: #6b21a8; display: flex; justify-content: space-between; align-items: center;">
            <span>5. Peer-Reviewed Sources & Institutional Registries (Scientific Provenance)</span>
            <span style="font-size: 11px; font-weight: 600; background: #f3e8ff; color: #6b21a8; padding: 2px 8px; border-radius: 10px;">${scnSourceIds.length} Vetted Sources</span>
          </h3>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; margin-top: 10px;">
            ${sourcesCardsHtml}
          </div>
        </div>
      ` : '';"""

if old_facts_block in text:
    text = text.replace(old_facts_block, new_facts_and_sources_block, 1)
    print("Injected sources cards logic in renderScenarioIntoPane.")

# Update pane.innerHTML to insert sourcesHtml before Section 5 (which becomes 6)
old_audit_trail_section = """        <div class="section-card" style="background: #f8fafc;">
          <h3>5. Verification & SME Audit Trail</h3>"""

new_audit_trail_section = """        ${sourcesHtml}

        <div class="section-card" style="background: #f8fafc;">
          <h3>6. Verification & SME Audit Trail</h3>"""

if old_audit_trail_section in text:
    text = text.replace(old_audit_trail_section, new_audit_trail_section, 1)
    print("Injected ${sourcesHtml} in pane.innerHTML.")

# Update JSON tree title to Section 7
old_json_title = "<h3>6. Schema v0.2.0 JSON Tree</h3>"
new_json_title = "<h3>7. Schema v0.2.0 JSON Tree</h3>"
if old_json_title in text:
    text = text.replace(old_json_title, new_json_title, 1)
elif "<h3>7. Schema v0.2.0 JSON Tree</h3>" not in text:
    text = text.replace("<h3>6. Schema v0.2.0", "<h3>7. Schema v0.2.0", 1)

# 5. Add Sources functions and Knowledge Graph Vis.js functions to script
JS_KG_AND_SOURCES = """
    // -------------------------------------------------------------
    // Sources Tab Functions
    // -------------------------------------------------------------
    function setFactsTabMode(mode) {
      factsTabMode = mode;
      document.getElementById('btn-facts-mode-facts').classList.toggle('active', mode === 'facts');
      document.getElementById('btn-facts-mode-sources').classList.toggle('active', mode === 'sources');

      const factsContainer = document.getElementById('facts-results-container');
      const sourcesContainer = document.getElementById('sources-results-container');
      const searchBar = document.getElementById('facts-search-bar');

      if (mode === 'facts') {
        factsContainer.style.display = 'block';
        sourcesContainer.style.display = 'none';
        searchBar.style.display = 'block';
        filterFacts();
      } else {
        factsContainer.style.display = 'none';
        sourcesContainer.style.display = 'grid';
        searchBar.style.display = 'none';
        renderSourcesList();
      }
    }

    function renderSourcesList() {
      const container = document.getElementById('sources-results-container');
      container.style.gridTemplateColumns = 'repeat(auto-fit, minmax(320px, 1fr))';
      container.style.gap = '14px';
      container.innerHTML = '';

      Object.values(SOURCES).forEach(s => {
        const card = document.createElement('div');
        card.className = 'section-card';
        card.style.margin = '0';
        card.style.display = 'flex';
        card.style.flexDirection = 'column';
        card.style.justifyContent = 'space-between';
        card.style.border = '1px solid #cbd5e1';

        card.innerHTML = `
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 800; color: #6b21a8; background: #f3e8ff; padding: 2px 8px; border-radius: 4px;">${s.source_id}</span>
              <span style="font-size: 11px; color: #0369a1; background: #e0f2fe; padding: 2px 8px; border-radius: 10px; font-weight: 700;">${s.fact_count || 0} Facts</span>
            </div>
            <h4 style="font-size: 13px; font-weight: 700; color: #0f172a; margin-bottom: 6px; line-height: 1.4;">${s.title}</h4>
            <div style="font-size: 12px; color: #64748b; margin-bottom: 8px;">
              ${s.author ? '<strong>Author:</strong> ' + s.author + '<br>' : ''}
              <strong>Publisher:</strong> ${s.publisher || 'Not stated'} ${s.publication_date ? '• ' + s.publication_date : ''}
            </div>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; padding-top: 8px; border-top: 1px solid #f1f5f9;">
            <span style="font-size: 11px; color: #15803d; font-weight: 600;">✓ ${s.license_status || 'Creative Commons'}</span>
            <button class="pill" style="font-size: 11px; padding: 2px 8px;" onclick="filterFactsBySource('${s.source_id}')">View ${s.fact_count || 0} Facts</button>
          </div>
        `;
        container.appendChild(card);
      });
    }

    function filterFactsBySource(sourceId) {
      setFactsTabMode('facts');
      const input = document.getElementById('fact-search');
      if (input) input.value = sourceId;
      filterFacts();
    }

    // -------------------------------------------------------------
    // Interactive Knowledge Graph GUI (Vis.js)
    // -------------------------------------------------------------
    function initKgNetwork() {
      const container = document.getElementById('kg-network-canvas');
      if (!container) return;

      if (kgNetwork !== null) {
        kgNetwork.fit({ animation: false });
        return;
      }

      if (typeof vis === 'undefined') {
        container.innerHTML = '<div style="color: white; padding: 30px; text-align: center;">Loading Knowledge Graph visualizer library...</div>';
        setTimeout(initKgNetwork, 200);
        return;
      }

      kgNodesDataSet = new vis.DataSet(KG_DATA.nodes);
      kgEdgesDataSet = new vis.DataSet(KG_DATA.edges);

      const data = { nodes: kgNodesDataSet, edges: kgEdgesDataSet };
      const options = {
        nodes: {
          borderWidth: 2,
          shadow: true,
          font: { color: '#ffffff', size: 12, face: 'system-ui' }
        },
        edges: {
          width: 1.5,
          smooth: { type: 'continuous' },
          font: { size: 9, color: '#94a3b8', strokeWidth: 2, strokeColor: '#0f172a', align: 'horizontal' },
          arrows: { to: { enabled: true, scaleFactor: 0.6 } }
        },
        physics: {
          forceAtlas2Based: {
            gravitationalConstant: -26,
            centralGravity: 0.005,
            springLength: 90,
            springConstant: 0.18,
            damping: 0.4
          },
          maxVelocity: 140,
          solver: 'forceAtlas2Based',
          stabilization: { iterations: 120 }
        },
        interaction: {
          hover: true,
          tooltipDelay: 150,
          zoomView: true,
          dragView: true
        }
      };

      kgNetwork = new vis.Network(container, data, options);

      kgNetwork.on('click', function(params) {
        if (params.nodes && params.nodes.length > 0) {
          selectKgNode(params.nodes[0]);
        }
      });
    }

    function selectKgNode(nodeId) {
      const node = KG_DATA.nodes.find(n => n.id === nodeId);
      if (!node) return;

      const drawer = document.getElementById('kg-inspector-drawer');
      const connectedEdges = KG_DATA.edges.filter(e => e.from === nodeId || e.to === nodeId);

      const relationshipsHtml = connectedEdges.map(e => {
        const isFrom = e.from === nodeId;
        const otherId = isFrom ? e.to : e.from;
        const otherNode = KG_DATA.nodes.find(n => n.id === otherId);
        const direction = isFrom ? `→ ${e.label} →` : `← ${e.label} ←`;
        return `
          <div style="font-size: 12px; margin-bottom: 6px; padding: 6px 8px; background: #f8fafc; border-radius: 6px; border: 1px solid #f1f5f9; display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span style="font-size: 10px; color: #64748b; font-weight: 700;">${direction}</span>
              <strong style="color: #0f172a; cursor: pointer; text-decoration: underline;" onclick="selectKgNode('${otherId}')">${otherNode ? otherNode.label : otherId}</strong>
            </div>
            <span style="font-size: 10px; color: #475569; background: #e2e8f0; padding: 1px 6px; border-radius: 4px;">${otherNode ? otherNode.group : ''}</span>
          </div>
        `;
      }).join('');

      // Find matching facts
      let matchingFacts = [];
      const nodeLabelLower = (node.meta.title || node.label || '').toLowerCase();
      for (const [fid, f] of Object.entries(FACTS)) {
        if (f.disease.toLowerCase() === nodeLabelLower || f.statement.toLowerCase().includes(nodeLabelLower)) {
          matchingFacts.push({ fid, ...f });
        }
        if (matchingFacts.length >= 5) break;
      }

      const factsListHtml = matchingFacts.map(f => `
        <div style="font-size: 11px; padding: 6px 8px; background: #fffbeb; border-radius: 6px; border: 1px solid #fef3c7; margin-bottom: 6px;">
          <div style="display: flex; justify-content: space-between; font-weight: 700; color: #b45309; margin-bottom: 2px;">
            <span>${f.fid}</span>
            <span>${f.category}</span>
          </div>
          <div style="color: #451a03; line-height: 1.3;">${f.statement}</div>
        </div>
      `).join('');

      drawer.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="background: ${node.color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700;">${node.group}</span>
          <span style="font-family: var(--font-mono); font-size: 10px; color: #64748b;">${node.id}</span>
        </div>
        <h3 style="font-size: 16px; font-weight: 800; color: #0f172a; margin-bottom: 6px; line-height: 1.3;">${node.meta.title || node.label}</h3>
        ${node.meta.scientific_name ? `<div style="font-style: italic; font-size: 12px; color: #64748b; margin-bottom: 8px;">${node.meta.scientific_name}</div>` : ''}

        ${node.meta.alt_labels ? `
          <div style="margin-bottom: 12px;">
            <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">Alternative / Farmer Phrasings:</div>
            <div style="font-size: 12px; color: #334155; margin-top: 2px;">${node.meta.alt_labels}</div>
          </div>
        ` : ''}

        <div style="margin-bottom: 14px;">
          <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 6px;">Connected Relationships (${connectedEdges.length}):</div>
          <div style="max-height: 200px; overflow-y: auto;">
            ${relationshipsHtml || '<div style="font-size: 12px; color: #94a3b8;">No direct relations.</div>'}
          </div>
        </div>

        <div>
          <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 6px;">Grounded Pathology Facts:</div>
          <div>
            ${factsListHtml || '<div style="font-size: 12px; color: #94a3b8;">No direct facts linked.</div>'}
          </div>
        </div>
      `;
    }

    function filterKgSubgraph(filterType, pillEl) {
      document.querySelectorAll('#tab-kg .pill').forEach(p => p.classList.remove('active'));
      if (pillEl) pillEl.classList.add('active');

      if (!kgNodesDataSet || !kgEdgesDataSet) return;

      if (filterType === 'all') {
        const updates = KG_DATA.nodes.map(n => ({ id: n.id, hidden: false }));
        const edgeUpdates = KG_DATA.edges.map((e, idx) => ({ id: e.id || idx, hidden: false }));
        kgNodesDataSet.update(updates);
        kgNetwork.fit({ animation: true });
        return;
      }

      if (filterType === 'lookalikes') {
        const lookalikeEdges = KG_DATA.edges.filter(e => e.label === 'LOOKALIKE' || e.dashes);
        const activeNodeIds = new Set();
        lookalikeEdges.forEach(e => {
          activeNodeIds.add(e.from);
          activeNodeIds.add(e.to);
        });

        const updates = KG_DATA.nodes.map(n => ({
          id: n.id,
          hidden: !activeNodeIds.has(n.id)
        }));
        kgNodesDataSet.update(updates);
        kgNetwork.fit({ animation: true });
        return;
      }

      // Filter by specific disease subgraph (1-hop neighbors)
      const connectedNodeIds = new Set([filterType]);
      KG_DATA.edges.forEach(e => {
        if (e.from === filterType) connectedNodeIds.add(e.to);
        if (e.to === filterType) connectedNodeIds.add(e.from);
      });

      const updates = KG_DATA.nodes.map(n => ({
        id: n.id,
        hidden: !connectedNodeIds.has(n.id)
      }));
      kgNodesDataSet.update(updates);
      kgNetwork.fit({ animation: true });

      // Automatically select the center disease node in the drawer
      selectKgNode(filterType);
    }

    function searchKgNode(query) {
      if (!query || !query.trim() || !kgNetwork) return;
      const q = query.trim().toLowerCase();
      const match = KG_DATA.nodes.find(n =>
        n.label.toLowerCase().includes(q) ||
        (n.meta.title && n.meta.title.toLowerCase().includes(q)) ||
        (n.meta.alt_labels && n.meta.alt_labels.toLowerCase().includes(q)) ||
        n.id.toLowerCase().includes(q)
      );

      if (match) {
        kgNetwork.focus(match.id, { scale: 1.25, animation: true });
        selectKgNode(match.id);
      }
    }

    function resetKgView() {
      if (kgNetwork) kgNetwork.fit({ animation: true });
    }

    function toggleKgPhysics() {
      if (!kgNetwork) return;
      kgPhysicsEnabled = !kgPhysicsEnabled;
      kgNetwork.setOptions({ physics: { enabled: kgPhysicsEnabled } });
      const btn = document.getElementById('kg-physics-btn');
      if (btn) btn.textContent = kgPhysicsEnabled ? '⚡ Physics: ON' : '⚡ Physics: OFF';
    }

    function testSymptomOnKg(symptomId, btnEl) {
      if (!kgNodesDataSet || !kgNetwork) return;

      if (activeKgTestSymptoms.has(symptomId)) {
        activeKgTestSymptoms.delete(symptomId);
        btnEl.classList.remove('active');
      } else {
        activeKgTestSymptoms.add(symptomId);
        btnEl.classList.add('active');
      }

      if (activeKgTestSymptoms.size === 0) {
        clearKgHighlights();
        return;
      }

      // Find diseases that cause all active symptoms
      const candidateDiseases = new Set();
      KG_DATA.edges.forEach(e => {
        if (activeKgTestSymptoms.has(e.to) && e.label === 'CAUSES') {
          candidateDiseases.add(e.from);
        }
      });

      // Highlight on canvas
      const updates = KG_DATA.nodes.map(n => {
        if (candidateDiseases.has(n.id)) {
          return { id: n.id, color: '#22c55e', size: 34, hidden: false };
        } else if (activeKgTestSymptoms.has(n.id)) {
          return { id: n.id, color: '#eab308', size: 24, hidden: false };
        } else {
          return { id: n.id, color: n.color, size: n.size, hidden: false };
        }
      });
      kgNodesDataSet.update(updates);

      // Focus on first candidate
      if (candidateDiseases.size > 0) {
        const first = Array.from(candidateDiseases)[0];
        kgNetwork.focus(first, { scale: 1.1, animation: true });
        selectKgNode(first);
      }
    }

    function clearKgHighlights() {
      activeKgTestSymptoms.clear();
      document.querySelectorAll('#tab-kg .pill').forEach(p => {
        if (p.textContent.includes('Diamond') || p.textContent.includes('Wavy') || p.textContent.includes('Whiteheads') || p.textContent.includes('Ooze') || p.textContent.includes('Sheath') || p.textContent.includes('Cool')) {
          p.classList.remove('active');
        }
      });
      if (kgNodesDataSet) {
        kgNodesDataSet.update(KG_DATA.nodes);
        kgNetwork.fit({ animation: true });
      }
    }
"""

# Insert JS_KG_AND_SOURCES right before window.onload
old_onload = "    window.onload = () => {"
if old_onload in text and "initKgNetwork" not in text:
    text = text.replace(old_onload, JS_KG_AND_SOURCES + "\n" + old_onload, 1)
    print("Injected JS_KG_AND_SOURCES into <script>.")

# 6. Update build_dashboard() function in Python to assemble SOURCES and KG_DATA
old_build_fn = """def build_dashboard():
    scenarios = []
    with open(SCENARIOS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                scenarios.append(json.loads(line))

    with open(FACTS_PATH, "r", encoding="utf-8") as f:
        facts = json.load(f)

    scenarios_json_str = json.dumps(scenarios)
    facts_json_str = json.dumps(facts)

    html_content = HTML_TEMPLATE.replace("__SCENARIOS_JSON__", scenarios_json_str).replace("__FACTS_JSON__", facts_json_str)"""

new_build_fn = """def build_dashboard():
    import csv

    scenarios = []
    with open(SCENARIOS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                scenarios.append(json.loads(line))

    facts_target = os.path.join(WORKSPACE_ROOT, "data/scenarios/richard_facts_842.json")
    if not os.path.exists(facts_target):
        facts_target = FACTS_PATH

    with open(facts_target, "r", encoding="utf-8") as f:
        facts = json.load(f)

    # 1. Load Sources Registry
    sources = {}
    sources_reg_path = os.path.join(WORKSPACE_ROOT, "registry/source-registry.csv")
    if os.path.exists(sources_reg_path):
        with open(sources_reg_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sid = r["source_id"]
                sources[sid] = {
                    "source_id": sid,
                    "title": r.get("title", sid),
                    "publisher": r.get("publisher", "Scientific Literature"),
                    "author": r.get("author", ""),
                    "publication_date": r.get("publication_date", ""),
                    "license_status": r.get("license_status", "Creative Commons"),
                    "training_permission": r.get("training_permission", "Allowed"),
                    "reviewer": r.get("reviewer", "Richard / Srikanth"),
                    "fact_count": 0
                }

    for f in facts.values():
        sid = f.get("source_id")
        if sid and sid in sources:
            sources[sid]["fact_count"] += 1

    # 2. Build KG Network Data (206 nodes, 278 edges)
    nodes = []
    edges = []
    node_ids = set()

    def add_node(nid, label, group, shape, color, size, meta=None):
        if nid not in node_ids:
            node_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "group": group,
                "shape": shape,
                "color": color,
                "size": size,
                "font": {"color": "#ffffff" if color not in ["#fbbf24", "#fef08a"] else "#1e293b", "size": 12},
                "meta": meta or {}
            })

    def add_edge(from_id, to_id, label, color="#94a3b8", dashes=False):
        if from_id in node_ids and to_id in node_ids:
            edges.append({
                "from": from_id,
                "to": to_id,
                "label": label,
                "color": {"color": color, "highlight": "#38bdf8"},
                "dashes": dashes,
                "arrows": "to",
                "font": {"size": 9, "color": "#94a3b8", "strokeWidth": 2, "strokeColor": "#0f172a"}
            })

    disease_colors = {
        "disease:rice_blast": "#ef4444",
        "disease:bacterial_leaf_blight": "#dc2626",
        "disease:sheath_blight": "#ea580c",
        "disease:brown_spot": "#b45309",
        "pest:stem_borer": "#7c3aed",
        "disorder:nitrogen_deficiency": "#eab308",
        "disorder:water_stress": "#0284c7",
        "disorder:iron_toxicity": "#0f766e",
        "disease:bacterial_leaf_streak": "#f43f5e",
        "disease:stem_rot": "#9333ea"
    }

    dis_path = os.path.join(WORKSPACE_ROOT, "registry/disease-registry.csv")
    if os.path.exists(dis_path):
        with open(dis_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cid = r["id"]
                color = disease_colors.get(cid, "#dc2626")
                add_node(cid, r["canonical_name"], "Disease", "hexagon", color, 28, {
                    "title": r["canonical_name"],
                    "scientific_name": r["scientific_name"],
                    "pref_label": r["skos_pref_label"],
                    "alt_labels": r["skos_alt_labels"],
                    "type": r["type"]
                })

    term_path = os.path.join(WORKSPACE_ROOT, "registry/terminology-registry.csv")
    if os.path.exists(term_path):
        with open(term_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cid = r["term_id"]
                etype = r.get("entity_type", "")
                shape = "dot"
                color = "#fbbf24"
                size = 16
                if etype == "Sign": shape = "diamond"; color = "#f87171"; size = 20
                elif etype == "EnvironmentalCondition": shape = "triangle"; color = "#38bdf8"; size = 18
                elif etype == "Action": shape = "ellipse"; color = "#10b981"; size = 18
                elif etype == "DiagnosticQuestion": shape = "box"; color = "#a855f7"; size = 18
                elif etype == "PlantPart": shape = "ellipse"; color = "#4ade80"; size = 14

                add_node(cid, r["skos_pref_label"], etype or "Concept", shape, color, size, {
                    "title": r["skos_pref_label"],
                    "pref_label": r["skos_pref_label"],
                    "alt_labels": r["skos_alt_labels"],
                    "farmer_phrasings": r.get("farmer_phrasings", ""),
                    "type": etype
                })

    q_path = os.path.join(WORKSPACE_ROOT, "registry/question-registry.csv")
    if os.path.exists(q_path):
        with open(q_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                qid = r["question_id"]
                add_node(qid, r.get("farmer_friendly_phrasing") or r.get("canonical_text", qid), "Question", "box", "#8b5cf6", 18, {
                    "title": r.get("farmer_friendly_phrasing", qid),
                    "canonical_text": r.get("canonical_text"),
                    "rationale": r.get("rationale"),
                    "type": "Question"
                })

    for sid, s in sources.items():
        add_node(sid, s["title"][:22] + "...", "Source", "square", "#64748b", 14, {
            "title": s["title"],
            "publisher": s["publisher"],
            "author": s["author"],
            "year": s["publication_date"],
            "license": s["license_status"],
            "type": "Source"
        })

    for s in scenarios:
        diff = s.get("target_response", {}).get("differential", [])
        acc_diff = s.get("annotations", {}).get("acceptable_differential", [])
        primary = diff[0] if diff else (acc_diff[0] if acc_diff else None)
        if not primary: continue

        for obs in s.get("annotations", {}).get("observations", []):
            if obs.get("state") == "PRESENT":
                add_edge(primary, obs.get("concept_id"), "CAUSES", "#f59e0b")

        for act in s.get("target_response", {}).get("actions", []):
            add_edge(primary, act, "MANAGED_BY", "#10b981")

        for q in s.get("target_response", {}).get("observations_needed", []):
            add_edge(primary, q, "DIFFERENTIATED_BY", "#8b5cf6")

        for other in acc_diff:
            if other != primary:
                add_edge(primary, other, "LOOKALIKE", "#ef4444", dashes=True)

        for src in s.get("annotations", {}).get("supporting_source_ids", []):
            add_edge(primary, src, "EVIDENCE", "#64748b")

    ev_path = os.path.join(WORKSPACE_ROOT, "registry/evidence-rules.csv")
    if os.path.exists(ev_path):
        with open(ev_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cid = r["cause_id"]
                obs_id = r["observation_id"]
                etype = r["evidence_type"]
                add_edge(cid, obs_id, etype.upper(), "#10b981" if etype == "Supporting" else "#ef4444")

    # Deduplicate edges
    seen_edges = set()
    deduped_edges = []
    for e in edges:
        k = (e["from"], e["to"], e["label"])
        if k not in seen_edges:
            seen_edges.add(k)
            deduped_edges.append(e)

    kg_data = {"nodes": nodes, "edges": deduped_edges}

    scenarios_json_str = json.dumps(scenarios)
    facts_json_str = json.dumps(facts)
    sources_json_str = json.dumps(sources)
    kg_data_json_str = json.dumps(kg_data)

    html_content = (HTML_TEMPLATE
                    .replace("__SCENARIOS_JSON__", scenarios_json_str)
                    .replace("__FACTS_JSON__", facts_json_str)
                    .replace("__SOURCES_JSON__", sources_json_str)
                    .replace("__KG_DATA_JSON__", kg_data_json_str))"""

if old_build_fn in text:
    text = text.replace(old_build_fn, new_build_fn, 1)
    print("Injected enhanced build_dashboard() python logic.")

with open(BUILD_SCRIPT, "w", encoding="utf-8") as f:
    f.write(text)

print("build_demo_dashboard.py updated successfully!")
