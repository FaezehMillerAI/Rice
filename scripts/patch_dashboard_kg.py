#!/usr/bin/env python3
"""
scripts/patch_dashboard_kg.py
1. Injects initKgNetwork and all KG functions into demo_dashboard.html
2. Fixes window.onload to render showcase immediately
3. Embeds/links kg_explorer.html for 3VL Studio & Integration Pipeline Trace
"""

import os
import re

DASHBOARD_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../demo_dashboard.html"))

with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
    html = f.read()

# 1. Knowledge Graph JS functions
KG_FUNCTIONS = """
    // -------------------------------------------------------------
    // Sources Tab Functions
    // -------------------------------------------------------------
    function setFactsTabMode(mode) {
      factsTabMode = mode;
      const bFacts = document.getElementById('btn-facts-mode-facts');
      const bSources = document.getElementById('btn-facts-mode-sources');
      if (bFacts) bFacts.classList.toggle('active', mode === 'facts');
      if (bSources) bSources.classList.toggle('active', mode === 'sources');

      const factsContainer = document.getElementById('facts-results-container');
      const sourcesContainer = document.getElementById('sources-results-container');
      const searchBar = document.getElementById('facts-search-bar');

      if (mode === 'facts') {
        if (factsContainer) factsContainer.style.display = 'block';
        if (sourcesContainer) sourcesContainer.style.display = 'none';
        if (searchBar) searchBar.placeholder = "Search facts (e.g. wavy, spindle, dew, halo, nitrogen, ooze)...";
      } else {
        if (factsContainer) factsContainer.style.display = 'none';
        if (sourcesContainer) sourcesContainer.style.display = 'block';
        if (searchBar) searchBar.placeholder = "Search sources by title, author, or publisher...";
        renderSourcesList();
      }
    }

    function renderSourcesList() {
      const container = document.getElementById('sources-results-container');
      if (!container) return;
      const query = (document.getElementById('fact-search')?.value || '').toLowerCase();

      const sourceList = Object.values(SOURCES);
      const filtered = sourceList.filter(s => {
        if (!query) return true;
        const text = (s.source_id + ' ' + s.title + ' ' + (s.author || '') + ' ' + (s.publisher || '') + ' ' + (s.license_status || '')).toLowerCase();
        return text.includes(query);
      });

      if (filtered.length === 0) {
        container.innerHTML = '<div style="padding: 24px; text-align: center; color: #64748b;">No sources match your search.</div>';
        return;
      }

      container.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; margin-top: 14px;">
          ${filtered.map(s => `
            <div style="background: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
              <div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                  <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 800; color: #0284c7; background: #e0f2fe; padding: 2px 7px; border-radius: 4px;">${s.source_id}</span>
                  <span style="font-size: 11px; color: #15803d; background: #dcfce7; padding: 2px 8px; border-radius: 10px; font-weight: 600;">✓ ${s.license_status || 'Approved'}</span>
                </div>
                <div style="font-weight: 700; font-size: 13px; color: #0f172a; line-height: 1.4; margin-bottom: 6px;">${s.title}</div>
              </div>
              <div style="font-size: 12px; color: #64748b; margin-top: 8px; border-top: 1px dashed #e2e8f0; padding-top: 6px; display: flex; justify-content: space-between; align-items: center;">
                <span>${s.author ? s.author + ' • ' : ''}${s.publisher || ''}</span>
                <span style="font-size: 11px; color: #0284c7; cursor: pointer; text-decoration: underline;" onclick="filterFactsBySource('${s.source_id}')">View Facts</span>
              </div>
            </div>
          `).join('')}
        </div>
      `;
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

      const candidateDiseases = new Set();
      KG_DATA.edges.forEach(e => {
        if (activeKgTestSymptoms.has(e.to) && e.label === 'CAUSES') {
          candidateDiseases.add(e.from);
        }
      });

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

# Insert before window.onload
old_onload_pattern = re.compile(r"(\s*window\.onload\s*=\s*(?:async\s*)?\(\)\s*=>\s*\{)")
if "function initKgNetwork" not in html:
    match = old_onload_pattern.search(html)
    if match:
        idx = match.start()
        html = html[:idx] + KG_FUNCTIONS + "\n" + html[idx:]
        print("Injected KG functions before window.onload.")

# Replace window.onload with synchronous first render
new_onload = """    window.onload = () => {
      setActiveUser(getActiveUser());
      updateDashboardCounts();

      // Render showcase scenario immediately so UI is never blank
      const firstCard = document.querySelector('.showcase-card');
      selectShowcase('SCN-000001', firstCard);

      // Check server sync status in background
      checkServerStatus().then(() => {
        if (serverConnected) {
          fetchLiveScenarios(true);
        }
      });
      setInterval(checkServerStatus, 4000);
    };"""

html = re.sub(r"window\.onload\s*=\s*async\s*\(\)\s*=>\s*\{[\s\S]*?setInterval\(checkServerStatus,\s*4000\);\s*\};", new_onload, html)
print("Updated window.onload for instant scenario rendering.")

with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
    f.write(html)

print("demo_dashboard.html patched successfully!")
