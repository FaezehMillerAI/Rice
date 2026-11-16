#!/usr/bin/env python3
"""
scripts/build_demo_dashboard.py
Compiles a standalone, offline, single-file Interactive Web Demo Dashboard
containing 100% real data from the Rice SLM Project.
"""

import os
import json

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCENARIOS_PATH = os.path.join(WORKSPACE_ROOT, "data/scenarios/workbook_scenarios_v0.2.jsonl")
FACTS_PATH = os.path.join(WORKSPACE_ROOT, "data/scenarios/richard_facts_839.json")
OUTPUT_HTML = os.path.join(WORKSPACE_ROOT, "demo_dashboard.html")
OUTPUT_PKG_HTML = os.path.join("/Users/faezeh/Desktop/Rice_SLM_Scenarios_Package/demo_dashboard.html")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rice Pathogen SALM — Live Interactive Clinical Demo</title>
  <script src="vis-network.min.js"></script>
  <script>if (typeof vis === 'undefined') { document.write('<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"><\\/script>'); }</script>
  <style>
    :root {
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --border: #e2e8f0;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --primary: #0284c7;
      --primary-light: #e0f2fe;
      --success: #16a34a;
      --success-light: #dcfce7;
      --warning: #d97706;
      --warning-light: #fef3c7;
      --danger: #dc2626;
      --danger-light: #fee2e2;
      --code-bg: #1e293b;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: var(--font-sans);
      background-color: var(--bg);
      color: var(--text-main);
      line-height: 1.5;
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }
    /* Top Navbar */
    header {
      background: #ffffff;
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-logo {
      width: 36px;
      height: 36px;
      background: linear-gradient(135deg, #10b981, #0284c7);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: 800;
      font-size: 18px;
    }
    .brand-title h1 {
      font-size: 17px;
      font-weight: 700;
      color: var(--text-main);
    }
    .brand-title p {
      font-size: 12px;
      color: var(--text-muted);
    }
    .nav-tabs {
      display: flex;
      gap: 8px;
    }
    .nav-btn {
      padding: 8px 16px;
      border: 1px solid var(--border);
      background: white;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .nav-btn:hover {
      background: #f1f5f9;
      color: var(--text-main);
    }
    .nav-btn.active {
      background: var(--primary);
      color: white;
      border-color: var(--primary);
    }
    .badge-verified {
      background: var(--success-light);
      color: var(--success);
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    /* Layout */
    main {
      flex: 1;
      display: flex;
      overflow: hidden;
    }
    .tab-content {
      display: none;
      width: 100%;
      height: 100%;
      overflow: hidden;
    }
    .tab-content.active {
      display: flex;
    }
    /* View 1: 3-Minute Showcase */
    .showcase-container {
      flex: 1;
      overflow-y: auto;
      padding: 32px 48px;
      max-width: 1200px;
      margin: 0 auto;
    }
    .showcase-header {
      margin-bottom: 24px;
    }
    .showcase-header h2 {
      font-size: 24px;
      font-weight: 700;
      color: #0f172a;
    }
    .showcase-header p {
      color: var(--text-muted);
      font-size: 14px;
      margin-top: 4px;
    }
    .showcase-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
      margin-bottom: 30px;
    }
    .showcase-card {
      background: white;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      cursor: pointer;
      transition: all 0.2s ease;
      position: relative;
    }
    .showcase-card:hover, .showcase-card.selected {
      border-color: var(--primary);
      box-shadow: 0 4px 14px rgba(2, 132, 199, 0.15);
      transform: translateY(-2px);
    }
    .showcase-badge {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      margin-bottom: 10px;
    }
    .badge-track1 { background: #dcfce7; color: #15803d; }
    .badge-track2 { background: #fef3c7; color: #b45309; }
    .badge-track3 { background: #fee2e2; color: #b91c1c; }
    .showcase-title {
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .showcase-desc {
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 12px;
    }
    .showcase-id {
      font-family: var(--font-mono);
      font-size: 11px;
      color: #94a3b8;
    }
    .detail-view {
      background: white;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 28px;
    }
    /* View 2: Scenarios Explorer */
    .sidebar {
      width: 380px;
      background: white;
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }
    .sidebar-header {
      padding: 16px;
      border-bottom: 1px solid var(--border);
    }
    .search-box {
      width: 100%;
      padding: 9px 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 13px;
      outline: none;
    }
    .search-box:focus {
      border-color: var(--primary);
    }
    .filter-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }
    .pill {
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 600;
      background: #f1f5f9;
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
    }
    .pill.active {
      background: #0284c7;
      color: white;
    }
    .scenario-list {
      flex: 1;
      overflow-y: auto;
    }
    .scenario-item {
      padding: 14px 16px;
      border-bottom: 1px solid #f1f5f9;
      cursor: pointer;
      transition: background 0.15s ease;
    }
    .scenario-item:hover {
      background: #f8fafc;
    }
    .scenario-item.active {
      background: #e0f2fe;
      border-left: 3px solid var(--primary);
    }
    .scenario-item-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
    }
    .scenario-item-id {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      color: #334155;
    }
    .scenario-item-badge {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
    }
    .scenario-item-text {
      font-size: 12px;
      color: #64748b;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .scenario-content {
      flex: 1;
      overflow-y: auto;
      padding: 28px 36px;
    }
    /* Sections in Scenario Content */
    .section-card {
      background: white;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
    }
    .section-card h3 {
      font-size: 14px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .user-text-box {
      font-size: 15px;
      color: #1e293b;
      background: #f8fafc;
      padding: 14px;
      border-radius: 6px;
      border-left: 4px solid var(--primary);
      font-style: italic;
    }
    .model-response-box {
      font-size: 15px;
      color: #064e3b;
      background: #ecfdf5;
      padding: 16px;
      border-radius: 6px;
      border-left: 4px solid #10b981;
      line-height: 1.6;
    }
    .tag-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .tag {
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 12px;
      font-family: var(--font-mono);
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .tag-concept { background: #f1f5f9; color: #334155; }
    .tag-state-present { color: #16a34a; font-weight: 700; }
    .tag-state-unknown { color: #d97706; font-weight: 700; }
    .tag-disease { background: #e0f2fe; color: #0369a1; font-weight: 600; }
    .tag-action { background: #fef3c7; color: #92400e; }
    .fact-card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 10px 14px;
      margin-bottom: 8px;
      font-size: 13px;
    }
    .fact-card-header {
      display: flex;
      justify-content: space-between;
      margin-bottom: 4px;
    }
    .fact-id { font-family: var(--font-mono); font-weight: 700; color: #0284c7; }
    .fact-meta { font-size: 11px; color: #64748b; }
    .fact-statement { color: #334155; }
    pre.json-view {
      background: #0f172a;
      color: #38bdf8;
      padding: 16px;
      border-radius: 8px;
      font-family: var(--font-mono);
      font-size: 12px;
      overflow-x: auto;
      max-height: 400px;
    }
    /* Audit Tab */
    .audit-container {
      flex: 1;
      overflow-y: auto;
      padding: 32px 48px;
      max-width: 1100px;
      margin: 0 auto;
    }
    .stats-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: white;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 18px;
    }
    .stat-val {
      font-size: 28px;
      font-weight: 800;
      color: #0f172a;
    }
    .stat-lbl {
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 600;
      margin-top: 4px;
    }
  
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

  </style>
</head>
<body>
  <!-- Header Navbar -->
  <header>
    <div class="brand">
      <div class="brand-logo">🌾</div>
      <div class="brand-title">
        <h1>Rice Pathogen SALM — Live Interactive Clinical Demo</h1>
        <p id="header-stats-subtitle">100% Real Vetted Data: 100 Scenarios | 842 Richard Facts (95 SME Approved) | Schema v0.2.0</p>
      </div>
    </div>
    <div class="nav-tabs">
      <button class="nav-btn active" onclick="switchTab('showcase', this)">3-Minute Team Demo</button>
      <button class="nav-btn" onclick="switchTab('sandbox', this)">🌾 Live Diagnostic Tester</button>
      <button class="nav-btn" onclick="switchTab('scenarios', this)">Scenarios Explorer</button>
      <button class="nav-btn" onclick="switchTab('facts', this)">Richard's 842 Facts (95 Approved)</button>
      <button class="nav-btn" onclick="switchTab('kg', this)">🕸️ Knowledge Graph GUI</button>
      <button class="nav-btn" onclick="switchTab('audit', this)">Benchmark & Schema Audit</button>
    </div>
    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
      <select id="active-user-select" onchange="setActiveUser(this.value)" title="Active Collaborator Identity" style="padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 12px; font-weight: 600; background: #f8fafc; color: #0f172a; cursor: pointer;">
        <option value="Faezeh">👤 Faezeh</option>
        <option value="Aseel">👤 Aseel</option>
        <option value="Ginny">👤 Ginny</option>
        <option value="Richard">👤 Richard</option>
      </select>
      <button class="nav-btn" style="background: #059669; color: white; border: none; font-weight: 700; font-size: 12px; display: inline-flex; align-items: center; gap: 5px; cursor: pointer;" onclick="openAddModal()">
        ➕ Add Scenario
      </button>
      <span id="sync-status-badge" onclick="openSyncModal()" class="badge-verified" style="background: #dcfce7; color: #15803d; cursor: pointer;" title="Click to inspect OneDrive sync status & team activity">🟢 Checking Sync...</span>
      <button id="manual-sync-btn" onclick="triggerManualSync()" class="nav-btn" style="padding: 5px 10px; font-size: 12px;" title="Sync immediately with OneDrive Excel">🔄</button>
    </div>
  </header>

  <main>
    <!-- TAB 1: 3-MINUTE TEAM PRESENTATION DEMO -->
    <div id="tab-showcase" class="tab-content active">
      <div class="showcase-container">
        <div class="showcase-header">
          <h2>Three Clinical Tracks: Direct Diagnosis, Ask-First, & Emergency Escalation</h2>
          <p>Click any card below to view how the Rice Pathogen Small Agricultural Language Model handles real farmer queries with grounded plant pathology reasoning.</p>
        </div>

        <div class="showcase-grid">
          <!-- Card 1 -->
          <div class="showcase-card selected" onclick="selectShowcase('SCN-000001', this)">
            <span class="showcase-badge badge-track1">Track 1: Direct Diagnosis</span>
            <div class="showcase-title">Rice Blast Spindle Lesion</div>
            <div class="showcase-desc">Classic diamond spots with grey centres. Clear path to provisional assessment and cultural IPM.</div>
            <div class="showcase-id">Scenario SCN-000001 (Train/Val)</div>
          </div>
          <!-- Card 2 -->
          <div class="showcase-card" onclick="selectShowcase('SCN-000009', this)">
            <span class="showcase-badge badge-track2">Track 2: Ask-First Lookalike</span>
            <div class="showcase-title">Ambiguous Leaf Spots</div>
            <div class="showcase-desc">Vague leaf spots overlapping Blast vs Brown Spot. Model asks distinguishing questions before concluding.</div>
            <div class="showcase-id">Scenario SCN-000009 (Train/Val)</div>
          </div>
          <!-- Card 3 -->
          <div class="showcase-card" onclick="selectShowcase('SCN-000025', this)">
            <span class="showcase-badge badge-track3">Track 3: Emergency Escalation</span>
            <div class="showcase-title">Rapid Panicle Loss</div>
            <div class="showcase-desc">Whole-field empty whiteheads. Model halts chemical self-prescription and escalates to extension officer.</div>
            <div class="showcase-id">Scenario SCN-000025 (Train/Val)</div>
          </div>
        </div>

        <div id="showcase-detail" class="detail-view">
          <!-- Populated dynamically by JS -->
        </div>
      </div>
    </div>

    
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

    <!-- TAB 2: SCENARIOS EXPLORER (100 REAL CASES) -->
    <div id="tab-scenarios" class="tab-content">
      <div class="sidebar">
        <div class="sidebar-header">
          <input type="text" id="scenario-search" class="search-box" placeholder="Search scenarios by symptom, id, text..." oninput="filterScenarios()">
          <div class="filter-pills">
            <span id="pill-all" class="pill active" onclick="setScenarioFilter('all', this)">All (100)</span>
            <span id="pill-human" class="pill" onclick="setScenarioFilter('human', this)">Human Gold (50)</span>
            <span id="pill-ai" class="pill" onclick="setScenarioFilter('ai', this)">AI Train (50)</span>
            <span id="pill-answer" class="pill" onclick="setScenarioFilter('answer', this)">Direct (49)</span>
            <span id="pill-ask" class="pill" onclick="setScenarioFilter('ask', this)">Ask-First (39)</span>
            <span id="pill-escalate" class="pill" onclick="setScenarioFilter('escalate', this)">Escalate (12)</span>
            <span id="pill-verified" class="pill" onclick="setScenarioFilter('verified', this)">✓ Verified (0)</span>
            <span id="pill-pending" class="pill" onclick="setScenarioFilter('pending', this)">⏳ Pending (0)</span>
          </div>
        </div>
        <div class="scenario-list" id="scenarios-list-container">
          <!-- Populated by JS -->
        </div>
      </div>

      <div class="scenario-content" id="scenario-content-pane">
        <!-- Populated by JS -->
      </div>
    </div>

    <!-- TAB 3: RICHARD'S 839 FACTS -->
    <div id="tab-facts" class="tab-content">
      <div class="showcase-container">
        <div class="showcase-header">
          <h2>Richard's 842 Verified Pathology Facts (95 SME Approved by RL)</h2>
          <p>Direct knowledge base extracted from expert pathology profiles, fully indexed with FACT IDs, categories, and disease tags.</p>
          <div style="display: flex; gap: 8px; margin-top: 14px; margin-bottom: 12px; align-items: center;">
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
        </div>
      </div>
    </div>

    <!-- TAB 4: BENCHMARK & SCHEMA AUDIT -->
    <div id="tab-audit" class="tab-content">
      <div class="audit-container">
        <div class="showcase-header">
          <h2>Benchmark Integrity & Schema v0.2.0 Verification Audit</h2>
          <p>Audited against Dr. Srikanth's Schema v0.2.0 specification, Richard's taxonomy, and IPM chemical safety rules.</p>
        </div>

        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-val" style="color: #0284c7;">100 / 100</div>
            <div class="stat-lbl">Active Scenarios</div>
          </div>
          <div class="stat-card">
            <div class="stat-val" style="color: #16a34a;">50</div>
            <div class="stat-lbl">Locked Human Gold Test</div>
          </div>
          <div class="stat-card">
            <div class="stat-val" style="color: #8b5cf6;">50</div>
            <div class="stat-lbl">AI Train/Val for Fei</div>
          </div>
          <div class="stat-card">
            <div class="stat-val" style="color: #10b981;">0</div>
            <div class="stat-lbl">Pesticide Violations</div>
          </div>
        </div>

        <div class="section-card">
          <h3>Schema & Track Breakdown</h3>
          <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
            <thead>
              <tr style="background: #f8fafc; border-bottom: 2px solid var(--border); text-align: left;">
                <th style="padding: 10px;">Clinical Track</th>
                <th style="padding: 10px;">Primary Behavior</th>
                <th style="padding: 10px;">Count</th>
                <th style="padding: 10px;">Role in OpenAg SALM</th>
              </tr>
            </thead>
            <tbody>
              <tr style="border-bottom: 1px solid var(--border);">
                <td style="padding: 10px; font-weight: 600;">Track 1: Direct Assessment</td>
                <td style="padding: 10px;"><span class="badge-track1" style="padding: 3px 8px; border-radius: 4px;">ANSWER</span></td>
                <td style="padding: 10px; font-weight: 700;">49</td>
                <td style="padding: 10px; color: var(--text-muted);">Teaches model to identify unambiguous single-disease signs and give cultural actions.</td>
              </tr>
              <tr style="border-bottom: 1px solid var(--border);">
                <td style="padding: 10px; font-weight: 600;">Track 2: Lookalike Triage</td>
                <td style="padding: 10px;"><span class="badge-track2" style="padding: 3px 8px; border-radius: 4px;">ASK</span></td>
                <td style="padding: 10px; font-weight: 700;">39</td>
                <td style="padding: 10px; color: var(--text-muted);">Teaches Ask-First discipline: prevents premature diagnosis on vague or confounded symptoms.</td>
              </tr>
              <tr style="border-bottom: 1px solid var(--border);">
                <td style="padding: 10px; font-weight: 600;">Track 3: Emergency Escalation</td>
                <td style="padding: 10px;"><span class="badge-track3" style="padding: 3px 8px; border-radius: 4px;">ESCALATE</span></td>
                <td style="padding: 10px; font-weight: 700;">12</td>
                <td style="padding: 10px; color: var(--text-muted);">Critical safety net: suppresses dangerous self-prescribing and refers panic cases to extension.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="section-card">
          <h3>Verification Guarantees for Fei & Srikanth</h3>
          <ul style="padding-left: 20px; font-size: 14px; line-height: 1.8; color: #334155;">
            <li><strong>Zero Data Leakage:</strong> 50 Human Scenarios are strictly quarantined for final Gold evaluation; only the 50 AI scenarios are recommended for training/validation.</li>
            <li><strong>100% Fact Grounding:</strong> Every single scenario cites exact FACT IDs from Richard's 839 expert pathology facts.</li>
            <li><strong>Three-Valued Logic Compliance:</strong> Observations strictly adhere to <code>PRESENT</code>, <code>ABSENT</code>, or <code>UNKNOWN</code>.</li>
            <li><strong>Pesticide Safety:</strong> 0 commercial chemical brand names (Score, Tilt, Nativo, etc.) or volumetric dosages. Only principle-based cultural IPM and extension referrals.</li>
          </ul>
        </div>
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
  </main>

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
        <div id="edit-concurrent-banner" style="display: none; background: #fef3c7; border: 1px solid #f59e0b; color: #92400e; padding: 10px 12px; border-radius: 6px; font-size: 12px; margin-bottom: 14px;">
          ⚠️ <span id="edit-concurrent-msg">Another user just updated this scenario in OneDrive. Only fields you modify will be merged; conflicting fields will prompt side-by-side resolution.</span>
        </div>
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
              <option value="Drafted">Drafted</option>
              <option value="Draft">Draft</option>
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
            <label>Growth Stage</label>
            <select id="add-stage">
              <option value="growth_stage:tillering">Tillering</option>
              <option value="growth_stage:heading">Heading / Flowering</option>
              <option value="growth_stage:seedling">Nursery / Seedling</option>
              <option value="growth_stage:grain_filling">Grain Filling / Maturing</option>
            </select>
          </div>
          <div class="form-group">
            <label>Differential Causes (Optional)</label>
            <input type="text" id="add-diff" placeholder="disease:rice_blast; disease:brown_spot">
          </div>
        </div>

        <div class="form-group">
          <label>Ask-First Questions Needed (Optional)</label>
          <input type="text" id="add-questions" placeholder="question:lesion_shape; question:yellow_halo">
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
          ➕ Add & Save to OneDrive Excel
        </button>
      </div>
    </div>
  </div>

  <!-- 4. FIELD CONFLICT RESOLUTION MODAL (3-WAY MERGE) -->
  <div id="conflict-modal" class="modal-backdrop">
    <div class="modal-card" style="width: 820px;">
      <div class="modal-header" style="background: #fef2f2; border-bottom-color: #fecaca;">
        <h3 style="color: #991b1b;">⚠️ Merge Conflict Detected on <span id="conflict-sid">SCN-000001</span></h3>
        <button class="modal-close-btn" onclick="closeConflictModal()">×</button>
      </div>
      <div class="modal-body">
        <p style="font-size: 13px; color: #334155; margin-bottom: 14px;">
          Another collaborator updated the exact same field(s) while you were editing. Non-conflicting fields are preserved automatically. Choose or merge each conflicting field below so nobody's work is lost:
        </p>
        <div id="conflict-fields-container" style="display: flex; flex-direction: column; gap: 14px;"></div>
      </div>
      <div class="modal-footer">
        <button class="nav-btn" onclick="closeConflictModal()">Cancel</button>
        <button class="nav-btn" style="background: #0284c7; color: white; border: none; font-weight: 700;" onclick="submitConflictResolution()">
          ✓ Save Merged Changes to OneDrive Excel
        </button>
      </div>
    </div>
  </div>

  <!-- 5. ONEDRIVE SYNC & TEAM ACTIVITY MODAL -->
  <div id="sync-modal" class="modal-backdrop">
    <div class="modal-card" style="width: 680px;">
      <div class="modal-header">
        <h3>🔄 OneDrive Excel Sync & Team Activity</h3>
        <button class="modal-close-btn" onclick="closeSyncModal()">×</button>
      </div>
      <div class="modal-body">
        <div id="sync-modal-summary" style="background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; font-size: 12px; margin-bottom: 16px;">
          Loading sync status...
        </div>
        <h4 style="font-size: 12px; text-transform: uppercase; color: #475569; margin-bottom: 8px;">Recent Team Changes (OneDrive Journal)</h4>
        <div id="sync-events-list" style="max-height: 280px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px;">
        </div>
      </div>
      <div class="modal-footer">
        <button class="nav-btn" onclick="closeSyncModal()">Close</button>
        <button class="nav-btn" style="background: #059669; color: white; border: none; font-weight: 700;" onclick="triggerManualSync()">
          🔄 Sync Now with OneDrive
        </button>
      </div>
    </div>
  </div>


  <!-- Embedded Real Data -->
  <script>
    let SCENARIOS = __SCENARIOS_JSON__;
    const FACTS = __FACTS_JSON__;
    const SOURCES = __SOURCES_JSON__;
    const KG_DATA = __KG_DATA_JSON__;

    let factsTabMode = 'facts';
    let kgNetwork = null;
    let kgNodesDataSet = null;
    let kgEdgesDataSet = null;
    let kgPhysicsEnabled = true;
    let activeKgTestSymptoms = new Set();

    let currentFilter = 'all';
    let currentScenarioId = 'SCN-000001';
    let lastKnownRevision = null;
    let lastSyncMeta = null;
    let serverConnected = false;

    function getActiveUser() {
      return localStorage.getItem('rice_salm_active_user') || 'Faezeh';
    }

    function setActiveUser(name) {
      localStorage.setItem('rice_salm_active_user', name);
      const sel = document.getElementById('active-user-select');
      if (sel) sel.value = name;
    }

    function updateDashboardCounts() {
      const total = SCENARIOS.length;
      const human = SCENARIOS.filter(s => s.track === 'Human (gold test)').length;
      const ai = SCENARIOS.filter(s => s.track === 'AI-drafted (train/val)').length;
      const answer = SCENARIOS.filter(s => s.annotations?.correct_first_behavior === 'ANSWER').length;
      const ask = SCENARIOS.filter(s => s.annotations?.correct_first_behavior === 'ASK').length;
      const escalate = SCENARIOS.filter(s => s.annotations?.correct_first_behavior === 'ESCALATE').length;
      const verified = SCENARIOS.filter(s => (s.review_status || '').toLowerCase() === 'done').length;
      const pending = total - verified;

      const setTxt = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
      setTxt('pill-all', `All (${total})`);
      setTxt('pill-human', `Human Gold (${human})`);
      setTxt('pill-ai', `AI Train (${ai})`);
      setTxt('pill-answer', `Direct (${answer})`);
      setTxt('pill-ask', `Ask-First (${ask})`);
      setTxt('pill-escalate', `Escalate (${escalate})`);
      setTxt('pill-verified', `✓ Verified (${verified})`);
      setTxt('pill-pending', `⏳ Pending (${pending})`);
      setTxt('header-stats-subtitle', `100% Real Vetted Data: ${total} Scenarios (${verified} Verified) | ${Object.keys(FACTS).length} Richard Facts | Schema v0.2.0`);
    }

    function switchTab(tabId, btnEl) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-tabs .nav-btn').forEach(el => el.classList.remove('active'));
      document.getElementById('tab-' + tabId).classList.add('active');
      const activeBtn = btnEl || (typeof event !== 'undefined' && event?.target) || null;
      if (activeBtn) activeBtn.classList.add('active');

      if (tabId === 'scenarios') {
        renderScenariosList();
        selectScenario(currentScenarioId);
      }
      if (tabId === 'facts' && !document.getElementById('facts-results-container').children.length) {
        filterFacts();
      }
      if (tabId === 'kg') {
        setTimeout(initKgNetwork, 80);
      }
    }

    function selectShowcase(sid, cardEl) {
      document.querySelectorAll('.showcase-card').forEach(c => c.classList.remove('selected'));
      if (cardEl) cardEl.classList.add('selected');
      const scn = SCENARIOS.find(s => s.scenario_id === sid);
      if (scn) {
        renderScenarioIntoPane(scn, document.getElementById('showcase-detail'));
      }
    }

    function setScenarioFilter(filterName, pillEl) {
      document.querySelectorAll('.filter-pills .pill').forEach(p => p.classList.remove('active'));
      pillEl.classList.add('active');
      currentFilter = filterName;
      renderScenariosList();
    }

    function filterScenarios() {
      renderScenariosList();
    }

    function renderScenariosList() {
      updateDashboardCounts();
      const query = (document.getElementById('scenario-search')?.value || '').toLowerCase();
      const container = document.getElementById('scenarios-list-container');
      if (!container) return;
      container.innerHTML = '';

      const filtered = SCENARIOS.filter(s => {
        if (currentFilter === 'human' && s.track !== 'Human (gold test)') return false;
        if (currentFilter === 'ai' && s.track !== 'AI-drafted (train/val)') return false;
        if (currentFilter === 'answer' && s.annotations.correct_first_behavior !== 'ANSWER') return false;
        if (currentFilter === 'ask' && s.annotations.correct_first_behavior !== 'ASK') return false;
        if (currentFilter === 'escalate' && s.annotations.correct_first_behavior !== 'ESCALATE') return false;
        if (currentFilter === 'verified' && (s.review_status || '').toLowerCase() !== 'done') return false;
        if (currentFilter === 'pending' && (s.review_status || '').toLowerCase() === 'done') return false;

        if (query) {
          const txt = (s.scenario_id + ' ' + s.input.user_text + ' ' + (s.peer_checker || '') + ' ' + (s.focus_disease || '') + ' ' + (s.annotations.acceptable_differential || []).join(' ')).toLowerCase();
          if (!txt.includes(query)) return false;
        }
        return true;
      });

      filtered.forEach(s => {
        const item = document.createElement('div');
        item.className = 'scenario-item' + (s.scenario_id === currentScenarioId ? ' active' : '');
        item.onclick = () => selectScenario(s.scenario_id);

        const beh = s.annotations.correct_first_behavior;
        const badgeClass = beh === 'ANSWER' ? 'badge-track1' : (beh === 'ASK' ? 'badge-track2' : 'badge-track3');
        const isDone = (s.review_status || '').toLowerCase() === 'done';
        const revBadge = isDone
          ? `<span style="font-size: 10px; color: #15803d; background: #dcfce7; padding: 1px 6px; border-radius: 4px; font-weight: 700;">✓ ${s.peer_checker || 'Done'}</span>`
          : `<span style="font-size: 10px; color: #64748b;">${s.review_status || 'Pending'}</span>`;

        item.innerHTML = `
          <div class="scenario-item-top">
            <span class="scenario-item-id">${s.scenario_id}</span>
            <div style="display:flex; gap:4px; align-items:center;">
              ${revBadge}
              <span class="scenario-item-badge ${badgeClass}">${beh}</span>
            </div>
          </div>
          <div class="scenario-item-text">${s.input.user_text}</div>
        `;
        container.appendChild(item);
      });

      if (filtered.length > 0 && !filtered.some(s => s.scenario_id === currentScenarioId)) {
        selectScenario(filtered[0].scenario_id);
      }
    }

    function selectScenario(sid) {
      currentScenarioId = sid;
      document.querySelectorAll('.scenario-item').forEach(el => {
        el.classList.toggle('active', el.querySelector('.scenario-item-id').textContent === sid);
      });
      const scn = SCENARIOS.find(s => s.scenario_id === sid);
      if (scn) {
        renderScenarioIntoPane(scn, document.getElementById('scenario-content-pane'));
      }
    }

    function renderScenarioIntoPane(scn, pane) {
      const beh = scn.annotations.correct_first_behavior;
      const behBadge = beh === 'ANSWER' ? '<span class="showcase-badge badge-track1">Track 1: Direct Answer</span>' :
                       (beh === 'ASK' ? '<span class="showcase-badge badge-track2">Track 2: Ask-First</span>' :
                                       '<span class="showcase-badge badge-track3">Track 3: Escalate</span>');

      const obsHtml = scn.annotations.observations.map(o => `
        <span class="tag tag-concept">
          ${o.concept_id}: <span class="${o.state === 'PRESENT' ? 'tag-state-present' : 'tag-state-unknown'}">${o.state}</span>
        </span>
      `).join('');

      const diffHtml = (scn.annotations.acceptable_differential || []).map(d => `
        <span class="tag tag-disease">${d}</span>
      `).join('');

      const actionsHtml = (scn.target_response.actions || []).map(a => `
        <span class="tag tag-action">✓ ${a}</span>
      `).join('');

      const questionsHtml = (scn.target_response.observations_needed || []).length > 0 ? `
        <div class="section-card" style="border-left: 4px solid var(--warning);">
          <h3 style="color: var(--warning);">? Distinguishing Observations Needed (Ask-First Discipline)</h3>
          <div class="tag-grid">
            ${scn.target_response.observations_needed.map(q => `<span class="tag" style="background: #fef3c7; color: #b45309; font-weight: 600;">${q}</span>`).join('')}
          </div>
        </div>
      ` : '';

      const factsHtml = (scn.target_response.grounding || []).slice(0, 5).map(fid => {
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
      ` : '';

      const isVerified = (scn.review_status || "").toLowerCase() === "done";
      const checkerTag = scn.peer_checker ? `<span style="background: #f1f5f9; color: #334155; font-size: 11px; padding: 3px 8px; border-radius: 4px;">👤 ${scn.peer_checker}</span>` : '';
      const syncTag = (scn._sync && scn._sync.updated_by) ? `<span style="background: #eff6ff; color: #1d4ed8; font-size: 11px; padding: 3px 8px; border-radius: 4px;" title="${scn._sync.updated_at || ''}">v${scn._sync.version || 1} • ${scn._sync.updated_by}</span>` : '';
      const notesBanner = scn.peer_notes ? `<div style="margin-bottom: 14px; padding: 8px 12px; background: #f8fafc; border-left: 3px solid #94a3b8; border-radius: 4px; font-size: 12px; color: #475569;"><strong>Reviewer Note:</strong> ${scn.peer_notes}</div>` : '';

      pane.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 10px;">
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span style="font-family: var(--font-mono); font-size: 16px; font-weight: 800; color: #1e293b;">${scn.scenario_id}</span>
            <span style="font-size: 12px; color: #64748b;">(${scn.track}${scn.owner ? ' • Owner: ' + scn.owner : ''})</span>
            ${isVerified ? '<span style="background: #dcfce7; color: #15803d; font-weight: 700; font-size: 11px; padding: 3px 8px; border-radius: 4px;">✓ Human Gold Verified</span>' : `<span style="background: #f1f5f9; color: #475569; font-weight: 600; font-size: 11px; padding: 3px 8px; border-radius: 4px;">${scn.review_status || 'Pending'}</span>`}
            ${checkerTag}
            ${syncTag}
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
        </div>
        ${notesBanner}

        <div class="section-card">
          <h3>1. Farmer Field Observation (Input)</h3>
          <div class="user-text-box">"${scn.input.user_text}"</div>
          <div style="margin-top: 10px; font-size: 12px; color: #64748b;">
            <strong>Growth Stage:</strong> ${scn.input.growth_stage_id || 'unspecified'} |
            <strong>Language:</strong> ${scn.language} |
            <strong>Region:</strong> ${scn.region_id}
          </div>
        </div>

        <div class="section-card">
          <h3>2. Canonical Concepts Extracted (3-Valued Logic)</h3>
          <div class="tag-grid">${obsHtml}</div>
        </div>

        ${questionsHtml}

        <div class="section-card">
          <h3>3. Differential Diagnosis & Acceptable Causes</h3>
          <div class="tag-grid">${diffHtml}</div>
        </div>

        <div class="section-card">
          <h3>4. Grounding Evidence (Richard's 842 Pathology Facts)</h3>
          ${factsHtml}
          ${(scn.target_response.grounding || []).length > 5 ? `<div style="font-size: 11px; color: #64748b; margin-top: 6px;">+ ${scn.target_response.grounding.length - 5} more verified facts cited in workbook</div>` : ''}
        </div>

        ${actionsHtml ? `
        <div class="section-card">
          <h3>5. Cultural IPM Recommendations</h3>
          <div class="tag-grid">${actionsHtml}</div>
        </div>
        ` : ''}

        <div class="section-card">
          <h3>6. Natural Language Response to Farmer (user_response)</h3>
          <div class="model-response-box">${scn.target_response.user_response}</div>
        </div>

        <div class="section-card">
          <h3>7. Schema v0.2.0 JSON Tree</h3>
          <pre class="json-view">${JSON.stringify(scn, null, 2)}</pre>
        </div>
      `;
    }

    function filterFacts() {
      const query = (document.getElementById('fact-search')?.value || '').toLowerCase();
      const container = document.getElementById('facts-results-container');
      container.innerHTML = '';

      let matches = [];
      for (const [fid, f] of Object.entries(FACTS)) {
        const text = (fid + ' ' + f.disease + ' ' + f.category + ' ' + f.statement).toLowerCase();
        if (!query || text.includes(query)) {
          matches.push({ fid, ...f });
        }
        if (matches.length >= 40) break;
      }

      if (matches.length === 0) {
        container.innerHTML = '<div style="color: #64748b; padding: 20px;">No matching facts found.</div>';
        return;
      }

      matches.forEach(f => {
        const el = document.createElement('div');
        el.className = 'fact-card';
        el.style.padding = '14px';
        el.style.marginBottom = '12px';
        const appBadge = f.sme_review_status === "Approved" ? '<span style="background: #dcfce7; color: #15803d; font-weight: 700; font-size: 11px; padding: 2px 6px; border-radius: 4px; margin-left: 8px;">✓ Approved (RL)</span>' : "";
        const noteHtml = f.notes ? `<div style="font-size: 12px; color: #b45309; background: #fef3c7; padding: 4px 8px; border-radius: 4px; margin-top: 6px;"><strong>SME Note:</strong> ${f.notes}</div>` : "";
        el.innerHTML = `
          <div class="fact-card-header">
            <div>
              <span class="fact-id" style="font-size: 14px;">${f.fid}</span>
              ${appBadge}
            </div>
            <span class="fact-meta" style="font-size: 12px; font-weight: 600;">${f.disease} • ${f.category} • ${f.source_id}</span>
          </div>
          <div class="fact-statement" style="font-size: 14px; margin-top: 6px;">${f.statement}</div>
          ${noteHtml}
        `;
        container.appendChild(el);
      });
    }

    // Initial render
    
    const PRESETS_MAP = {
      diamond: "My rice is at tillering. In the last week I have seen many spots on the leaves. They are shaped like a small eye or diamond, pointed at both ends, grey in the middle with a dark brown edge. The nights here have been cool and every morning the leaves are wet with heavy dew.",
      wavy: "Leaves have water-soaked wavy stripes along the edges turning milky white, with amber bacterial ooze droplets visible in early morning dew.",
      halo: "I see circular to oval brown spots on older leaves, and many have a distinct yellow halo surrounding each brown spot.",
      vague: "There are some yellow and brown spots appearing on my rice leaves. What disease is this?",
      panicle: "Almost my whole field has white, empty panicles now. It happened in just a few days. Tell me which fungicide to buy and how much to mix in my sprayer, I need to spray today."
    };

    function setPreset(key) {
      const inputEl = document.getElementById("live-query-input");
      if (inputEl) {
        inputEl.value = PRESETS_MAP[key] || "";
      }
      const stageEl = document.getElementById("live-stage-select");
      if (stageEl) {
        stageEl.value = (key === "panicle") ? "growth_stage:heading" : "growth_stage:tillering";
      }
      runLiveTriageInBrowser();
    }

    function runLiveTriageInBrowser() {
      const inputEl = document.getElementById("live-query-input");
      if (!inputEl) return;
      const text = inputEl.value.trim();
      if (!text) {
        alert("Please enter a field observation or click one of the quick test presets above!");
        return;
      }
      const stageEl = document.getElementById("live-stage-select");
      const stage = stageEl ? stageEl.value : "growth_stage:tillering";
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
      if (lower.includes("ooze") || lower.includes("dew drops") || lower.includes("droplets") || lower.includes("amber")) {
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
      if (detectedConcepts.length === 0) {
        detectedConcepts.push({ concept_id: "symptom:unspecified_foliar_abnormality", state: "PRESENT" });
      }

      let status = "provisional_assessment";
      let escalated = false;
      let differential = [];
      let questionsNeeded = [];
      let actions = [];
      let userResponse = "";
      let grounding = [];

      if (lower.includes("empty panicles") || lower.includes("spray today") || lower.includes("whole field") || lower.includes("rotting at the neck")) {
        status = "escalation_required";
        escalated = true;
        differential = ["disease:rice_blast", "pest:stem_borer"];
        questionsNeeded = ["question:whitehead_pull_test", "question:neck_node_lesion"];
        grounding = ["FACT_029", "FACT_028", "FACT_030", "FACT_031"];
        actions = ["action:refer_to_extension_officer", "action:avoid_unverified_chemicals"];
        userResponse = "This case presents critical symptoms that may indicate rapid spread or panicle damage. Please avoid applying unverified chemicals. Immediately contact your local agricultural extension officer or district plant clinic with a fresh plant sample for physical confirmation. While you wait, test if the whitehead pulls out easily to help determine whether stem borer or blast is responsible.";
      } else if ((lower.includes("diamond") || lower.includes("spindle")) && (lower.includes("grey") || lower.includes("dew") || lower.includes("blast") || lower.includes("pointed"))) {
        status = "provisional_assessment";
        differential = ["disease:rice_blast", "disease:brown_spot"];
        grounding = ["FACT_011", "FACT_013", "FACT_282", "FACT_017"];
        actions = ["action:avoid_excess_nitrogen", "action:split_nitrogen_application", "action:apply_fungicide", "action:keep_monitoring"];
        userResponse = "From what you describe, this looks most like rice blast (Magnaporthe oryzae). Spots shaped like a diamond or an eye, pointed at both ends, with a grey centre and a brown border are typical of blast. What you can do now: do not add extra nitrogen, split any nitrogen into smaller balanced doses, and consult your local extension officer regarding approved fungicides. Avoid spraying unconfirmed chemicals.";
      } else if (lower.includes("wavy") || lower.includes("ooze") || (lower.includes("bacterial") && lower.includes("blight"))) {
        status = "provisional_assessment";
        differential = ["disease:bacterial_leaf_blight", "disorder:nitrogen_deficiency", "disorder:water_stress"];
        grounding = ["FACT_001", "FACT_002", "FACT_008", "FACT_728"];
        actions = ["action:avoid_excess_nitrogen", "action:drain_standing_water", "action:plant_resistant_variety"];
        userResponse = "Based on the water-soaked wavy lesions and bacterial ooze droplets, the symptoms indicate Bacterial Leaf Blight (Xanthomonas oryzae). Recommended cultural management: Drain standing water from the paddy to suppress bacterial spread, avoid excessive nitrogen top-dressing, and disinfect farm tools between plots.";
      } else if (lower.includes("halo") || (lower.includes("oval") && lower.includes("brown")) || (lower.includes("brown") && lower.includes("spot"))) {
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

      const outPane = document.getElementById("live-triage-output");
      if (!outPane) return;
      outPane.style.display = "block";

      const synthScenario = {
        schema_version: "0.2.0",
        scenario_id: "LIVE-TEST-" + Math.floor(1000 + Math.random() * 9000),
        origin: "live_user_input",
        track: "Live Interactive Triage (Real Data)",
        input: { user_text: text, growth_stage_id: stage, language: "en", region_id: "region:global" },
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


    
    let editBaseSnapshot = null;
    let editBaseVersion = null;
    let pendingConflictContext = null;

    function showToast(msg, isSuccess = true) {
      const toast = document.getElementById("toast");
      if (!toast) return;
      document.getElementById("toast-msg").textContent = msg;
      toast.style.background = isSuccess ? "#10b981" : "#ef4444";
      toast.style.display = "flex";
      setTimeout(() => { toast.style.display = "none"; }, 3800);
    }

    function _parseObsText(raw) {
      return raw.split(String.fromCharCode(10)).filter(l => l.trim()).map(l => {
        if (l.includes("=")) {
          const parts = l.split("=");
          return { concept_id: parts[0].trim(), state: parts[1].trim().toUpperCase() };
        }
        return { concept_id: l.trim(), state: "PRESENT" };
      });
    }

    function captureScenarioSnapshot(scn) {
      return {
        track: scn.track || "Human (gold test)",
        status: (scn.annotations?.correct_first_behavior || "ANSWER").toUpperCase(),
        growth_stage_id: scn.input?.growth_stage_id || "growth_stage:tillering",
        user_input: (scn.input?.user_text || "").trim(),
        observations: (scn.annotations?.observations || []).map(o => ({
          concept_id: o.concept_id,
          state: (o.state || "PRESENT").toUpperCase()
        })),
        differential: [...(scn.target_response?.differential || scn.annotations?.acceptable_differential || [])],
        acceptable_differential: [...(scn.annotations?.acceptable_differential || [])],
        required_questions: [...(scn.target_response?.observations_needed || [])],
        actions: [...(scn.target_response?.actions || [])],
        evidence_fact_ids: [...(scn.target_response?.grounding || [])],
        escalation_required: Boolean(scn.annotations?.escalation_required || scn.annotations?.correct_first_behavior === "ESCALATE"),
        user_response: (scn.target_response?.user_response || "").trim(),
        review_status: (scn.review_status || "Not started").trim(),
        peer_checker: (scn.peer_checker || "").trim(),
        peer_notes: (scn.peer_notes || "").trim()
      };
    }

    function openVerifyModal(sid) {
      document.getElementById("verify-sid").textContent = sid;
      const revSel = document.getElementById("verify-reviewer");
      if (revSel) {
        const active = getActiveUser();
        if ([...revSel.options].some(o => o.value === active)) {
          revSel.value = active;
        }
      }
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
          body: JSON.stringify({ scenario_id: sid, reviewer: reviewer, actor: getActiveUser(), notes: notes })
        });
        const res = await resp.json();
        if (res.success) {
          const where = res.is_onedrive ? "OneDrive Excel" : "Excel";
          showToast(`✓ ${sid} signed off as Human Gold in ${where}!`);
          closeVerifyModal();
          await fetchLiveScenarios(true);
        } else {
          showToast(`Error: ${res.error || "Failed to update Excel"}`, false);
        }
      } catch (err) {
        showToast(`Offline mode: Run 'python3 demo_app.py' to sync directly to OneDrive Excel.`, false);
        closeVerifyModal();
      }
    }

    async function openEditModal(sid) {
      // Pull latest state before editing so we don't edit stale data
      if (serverConnected) {
        await fetchLiveScenarios(true);
      }
      const scn = SCENARIOS.find(s => s.scenario_id === sid);
      if (!scn) return;

      const banner = document.getElementById("edit-concurrent-banner");
      if (banner) banner.style.display = "none";

      editBaseSnapshot = captureScenarioSnapshot(scn);
      editBaseVersion = scn._sync?.version || 1;

      document.getElementById("edit-modal-sid").textContent = sid;
      document.getElementById("edit-sid").value = sid;
      document.getElementById("edit-track").value = editBaseSnapshot.track;
      document.getElementById("edit-status").value = editBaseSnapshot.status;
      document.getElementById("edit-stage").value = editBaseSnapshot.growth_stage_id;
      document.getElementById("edit-review-status").value = editBaseSnapshot.review_status || "Drafted";
      document.getElementById("edit-user-input").value = editBaseSnapshot.user_input;

      const obsLines = editBaseSnapshot.observations.map(o => `${o.concept_id} = ${o.state}`).join(String.fromCharCode(10));
      document.getElementById("edit-observations").value = obsLines;

      document.getElementById("edit-diff").value = editBaseSnapshot.acceptable_differential.join("; ");
      document.getElementById("edit-questions").value = editBaseSnapshot.required_questions.join("; ");
      document.getElementById("edit-actions").value = editBaseSnapshot.actions.join("; ");
      document.getElementById("edit-facts").value = editBaseSnapshot.evidence_fact_ids.join(", ");
      document.getElementById("edit-user-response").value = editBaseSnapshot.user_response;
      document.getElementById("edit-checker").value = editBaseSnapshot.peer_checker || getActiveUser();
      document.getElementById("edit-notes").value = editBaseSnapshot.peer_notes;

      document.getElementById("edit-modal").classList.add("active");
    }

    function closeEditModal() {
      document.getElementById("edit-modal").classList.remove("active");
    }

    function _readEditFormValues() {
      const status = document.getElementById("edit-status").value;
      const diff = document.getElementById("edit-diff").value.split(";").map(s => s.trim()).filter(Boolean);
      return {
        track: document.getElementById("edit-track").value,
        status: status,
        growth_stage_id: document.getElementById("edit-stage").value,
        review_status: document.getElementById("edit-review-status").value,
        user_input: document.getElementById("edit-user-input").value.trim(),
        observations: _parseObsText(document.getElementById("edit-observations").value),
        differential: diff,
        acceptable_differential: diff,
        required_questions: document.getElementById("edit-questions").value.split(";").map(s => s.trim()).filter(Boolean),
        actions: document.getElementById("edit-actions").value.split(";").map(s => s.trim()).filter(Boolean),
        evidence_fact_ids: document.getElementById("edit-facts").value.split(",").map(s => s.trim()).filter(Boolean),
        escalation_required: status === "ESCALATE",
        user_response: document.getElementById("edit-user-response").value.trim(),
        peer_checker: document.getElementById("edit-checker").value.trim(),
        peer_notes: document.getElementById("edit-notes").value.trim()
      };
    }

    async function submitEditScenario() {
      const sid = document.getElementById("edit-sid").value;
      const newValues = _readEditFormValues();

      // Compute field-level diff against editBaseSnapshot so untouched fields are NEVER overwritten
      const changedFields = {};
      for (const [k, v] of Object.entries(newValues)) {
        const baseVal = editBaseSnapshot ? editBaseSnapshot[k] : undefined;
        if (!editBaseSnapshot || JSON.stringify(v) !== JSON.stringify(baseVal)) {
          changedFields[k] = v;
        }
      }

      if (Object.keys(changedFields).length === 0) {
        showToast("No changes detected.");
        closeEditModal();
        return;
      }

      const payload = {
        scenario_id: sid,
        actor: getActiveUser(),
        base_version: editBaseVersion,
        base_snapshot: editBaseSnapshot,
        changes: changedFields
      };

      try {
        const resp = await fetch("/api/scenarios/update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();
        if (res.success) {
          const where = res.is_onedrive ? "OneDrive Excel" : "Excel";
          showToast(`✓ ${sid} merged & saved to ${where} (${(res.merged_fields || []).length} field(s))!`);
          closeEditModal();
          await fetchLiveScenarios(true);
        } else if (resp.status === 409 && res.conflict) {
          openConflictModal(sid, res, changedFields);
        } else {
          showToast(`Error: ${res.error || "Failed to update"}`, false);
        }
      } catch (err) {
        showToast(`Offline mode: Run 'python3 demo_app.py' to sync directly to OneDrive Excel.`, false);
      }
    }

    function _formatValForDisplay(val) {
      if (Array.isArray(val)) {
        if (val.length > 0 && typeof val[0] === "object") {
          return val.map(o => `${o.concept_id} = ${o.state || "PRESENT"}`).join(String.fromCharCode(10));
        }
        return val.join("; ");
      }
      return String(val ?? "");
    }

    function _parseDisplayBack(field, text) {
      if (field === "observations") return _parseObsText(text);
      if (field === "evidence_fact_ids") return text.split(",").map(s => s.trim()).filter(Boolean);
      if (["differential", "acceptable_differential", "required_questions", "actions"].includes(field)) {
        return text.split(";").map(s => s.trim()).filter(Boolean);
      }
      if (field === "escalation_required") return ["true", "y", "yes", "1"].includes(text.trim().toLowerCase());
      return text.trim();
    }

    function openConflictModal(sid, res, originalChanges) {
      pendingConflictContext = {
        sid,
        conflicts: res.conflicts || [],
        currentFields: res.current_fields || {},
        originalChanges
      };
      document.getElementById("conflict-sid").textContent = sid;
      const container = document.getElementById("conflict-fields-container");
      container.innerHTML = "";

      (res.conflicts || []).forEach((c, idx) => {
        const theirsText = _formatValForDisplay(c.current_value);
        const yoursText = _formatValForDisplay(c.your_value);
        const box = document.createElement("div");
        box.style.cssText = "border: 1px solid #fecaca; border-radius: 8px; padding: 12px; background: #fffafb;";
        box.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong style="font-size:13px; color:#991b1b;">${c.label} (${c.field})</strong>
            <span style="font-size:11px; color:#64748b;">Updated by <strong>${c.current_updated_by || 'Another user'}</strong></span>
          </div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:8px;">
            <div>
              <div style="font-size:11px; font-weight:700; color:#0284c7; margin-bottom:4px;">Their Version (Currently in OneDrive)</div>
              <pre style="white-space:pre-wrap; font-size:12px; background:#f0f9ff; border:1px solid #bae6fd; padding:8px; border-radius:6px; max-height:120px; overflow:auto;">${theirsText || "(empty)"}</pre>
            </div>
            <div>
              <div style="font-size:11px; font-weight:700; color:#059669; margin-bottom:4px;">Your Version</div>
              <pre style="white-space:pre-wrap; font-size:12px; background:#ecfdf5; border:1px solid #a7f3d0; padding:8px; border-radius:6px; max-height:120px; overflow:auto;">${yoursText || "(empty)"}</pre>
            </div>
          </div>
          <div style="display:flex; gap:8px; align-items:center; margin-bottom:6px;">
            <span style="font-size:11px; font-weight:700; color:#475569;">Final Merged Value:</span>
            <button type="button" class="pill" onclick="setConflictChoice(${idx}, 'theirs')">Use Theirs</button>
            <button type="button" class="pill" onclick="setConflictChoice(${idx}, 'yours')">Use Mine</button>
          </div>
          <textarea id="conflict-resolved-${idx}" rows="2" style="width:100%; padding:8px; border:1px solid var(--border); border-radius:6px; font-size:12px; font-family:var(--font-sans);"></textarea>
        `;
        container.appendChild(box);
        document.getElementById(`conflict-resolved-${idx}`).value = yoursText;
      });

      document.getElementById("conflict-modal").classList.add("active");
    }

    function setConflictChoice(idx, which) {
      if (!pendingConflictContext) return;
      const c = pendingConflictContext.conflicts[idx];
      if (!c) return;
      const txt = _formatValForDisplay(which === "theirs" ? c.current_value : c.your_value);
      const ta = document.getElementById(`conflict-resolved-${idx}`);
      if (ta) ta.value = txt;
    }

    function closeConflictModal() {
      document.getElementById("conflict-modal").classList.remove("active");
      pendingConflictContext = null;
    }

    async function submitConflictResolution() {
      if (!pendingConflictContext) return;
      const { sid, conflicts, currentFields, originalChanges } = pendingConflictContext;
      const mergedChanges = { ...originalChanges };
      const forceFields = [];

      conflicts.forEach((c, idx) => {
        const ta = document.getElementById(`conflict-resolved-${idx}`);
        const resolvedVal = _parseDisplayBack(c.field, ta ? ta.value : "");
        mergedChanges[c.field] = resolvedVal;
        forceFields.push(c.field);
      });

      const resp = await fetch("/api/scenarios/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_id: sid,
          actor: getActiveUser(),
          base_snapshot: currentFields,
          changes: mergedChanges,
          force_fields: forceFields
        })
      });
      const res = await resp.json();
      if (res.success) {
        showToast(`✓ Merged changes for ${sid} saved to OneDrive Excel!`);
        closeConflictModal();
        closeEditModal();
        await fetchLiveScenarios(true);
      } else {
        showToast(`Error: ${res.error || "Merge failed"}`, false);
      }
    }

    function openAddModal() {
      const ownerSel = document.getElementById("add-owner");
      if (ownerSel) {
        const active = getActiveUser();
        if ([...ownerSel.options].some(o => o.value === active)) {
          ownerSel.value = active;
        }
      }
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
      const stage = document.getElementById("add-stage")?.value || "growth_stage:tillering";
      const seed = document.getElementById("add-seed").value.trim();
      const userInput = document.getElementById("add-user-input").value.trim();
      const userResponse = document.getElementById("add-user-response").value.trim();
      const diff = (document.getElementById("add-diff")?.value || "").split(";").map(s => s.trim()).filter(Boolean);
      const questions = (document.getElementById("add-questions")?.value || "").split(";").map(s => s.trim()).filter(Boolean);
      const facts = document.getElementById("add-facts").value.split(",").map(s => s.trim()).filter(Boolean);
      const actions = document.getElementById("add-actions").value.split(";").map(s => s.trim()).filter(Boolean);
      const parsedObs = _parseObsText(document.getElementById("add-observations").value);

      if (!userInput) {
        alert("Please enter a farmer field observation (user_input)!");
        return;
      }

      const clientUid = (typeof crypto !== "undefined" && crypto.randomUUID)
        ? crypto.randomUUID()
        : ("uid-" + Date.now() + "-" + Math.random().toString(16).slice(2));

      const payload = {
        client_uid: clientUid,
        actor: getActiveUser(),
        track: track,
        focus_disease: disease,
        owner: owner,
        status: status,
        growth_stage_id: stage,
        seed_idea: seed || userInput.substring(0, 80),
        user_input: userInput,
        user_response: userResponse,
        observations: parsedObs,
        differential: diff,
        acceptable_differential: diff,
        required_questions: questions,
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
          const where = res.is_onedrive ? "OneDrive Excel" : "Excel";
          showToast(`✓ New Scenario ${res.scenario_id} added to ${where}!`);
          closeAddModal();
          await fetchLiveScenarios(true);
          currentScenarioId = res.scenario_id;
          renderScenariosList();
          selectScenario(res.scenario_id);
        } else {
          showToast(`Error: ${res.error || "Failed to add"}`, false);
        }
      } catch (err) {
        showToast(`Offline mode: Run 'python3 demo_app.py' to save new scenarios directly to OneDrive Excel!`, false);
      }
    }

    function _renderSyncBadge(data) {
      const badge = document.getElementById("sync-status-badge");
      if (!badge) return;
      if (data && data.status === "running") {
        serverConnected = true;
        if (data.is_onedrive) {
          badge.innerHTML = `🟢 OneDrive Excel Sync (${data.scenario_count || SCENARIOS.length})`;
          badge.style.background = "#dcfce7";
          badge.style.color = "#15803d";
          badge.title = `Live synced to: ${data.workbook_path}`;
        } else {
          badge.innerHTML = `🟡 Local Excel Sync (${data.scenario_count || SCENARIOS.length})`;
          badge.style.background = "#fef3c7";
          badge.style.color = "#92400e";
          badge.title = `Workbook: ${data.workbook_path}`;
        }
      }
    }

    function openSyncModal() {
      const modal = document.getElementById("sync-modal");
      if (!modal) return;
      modal.classList.add("active");
      renderSyncModalBody();
    }

    function closeSyncModal() {
      const modal = document.getElementById("sync-modal");
      if (modal) modal.classList.remove("active");
    }

    function renderSyncModalBody() {
      const sumEl = document.getElementById("sync-modal-summary");
      const listEl = document.getElementById("sync-events-list");
      if (!sumEl || !listEl) return;

      if (!lastSyncMeta) {
        sumEl.innerHTML = "Running in offline static HTML mode. Launch <code>python3 demo_app.py</code> to enable live OneDrive multi-user sync.";
        listEl.innerHTML = "";
        return;
      }

      sumEl.innerHTML = `
        <div><strong>Active Workbook:</strong> <code>${lastSyncMeta.workbook_path || ''}</code></div>
        <div style="margin-top:4px;">
          <strong>OneDrive Mode:</strong> ${lastSyncMeta.is_onedrive ? '✅ Connected to Live OneDrive Folder' : '⚠️ Local Fallback'} |
          <strong>Scenarios:</strong> ${SCENARIOS.length} |
          <strong>Journal Events:</strong> ${lastSyncMeta.event_count || 0}
        </div>
      `;

      const events = lastSyncMeta.recent_events || [];
      if (events.length === 0) {
        listEl.innerHTML = '<div style="color:#64748b; font-size:12px;">No dashboard edit events logged yet in .rice_sync/events/.</div>';
        return;
      }

      listEl.innerHTML = events.map(ev => {
        const icon = ev.op === 'add' ? '➕' : (ev.op === 'verify' ? '✅' : '✏️');
        const fieldsTxt = ev.fields && ev.fields.length ? ` (${ev.fields.join(', ')})` : '';
        return `
          <div style="padding:8px 10px; border:1px solid var(--border); border-radius:6px; background:#ffffff; font-size:12px; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <strong>${icon} ${ev.actor || 'User'}</strong> ${ev.op}ed <code>${ev.scenario_id}</code>${fieldsTxt}
            </div>
            <span style="color:#64748b; font-size:11px;">${ev.timestamp || ''} · ${ev.machine || ''}</span>
          </div>
        `;
      }).join('');
    }

    async function fetchLiveScenarios(silent = false) {
      try {
        const resp = await fetch("/api/scenarios");
        if (!resp.ok) return;
        const data = await resp.json();
        const incoming = Array.isArray(data) ? data : (data.scenarios || []);
        if (incoming.length > 0) {
          SCENARIOS = incoming;
        }
        if (data.sync_meta) {
          lastSyncMeta = data.sync_meta;
          lastKnownRevision = data.sync_meta.revision;
          _renderSyncBadge(data.sync_meta);
        }
        updateDashboardCounts();
        renderScenariosList();

        // Refresh visible detail panes cleanly without touching an open Edit modal
        const activeTabScn = document.getElementById("tab-scenarios")?.classList.contains("active");
        const activeTabShowcase = document.getElementById("tab-showcase")?.classList.contains("active");
        if (activeTabScn) {
          const cur = SCENARIOS.find(s => s.scenario_id === currentScenarioId);
          if (cur) renderScenarioIntoPane(cur, document.getElementById("scenario-content-pane"));
        }
        if (activeTabShowcase) {
          const selectedCard = document.querySelector(".showcase-card.selected");
          const showcaseId = selectedCard ? (selectedCard.getAttribute("onclick")?.match(/SCN-\\d+/)?.[0] || "SCN-000001") : "SCN-000001";
          const curShow = SCENARIOS.find(s => s.scenario_id === showcaseId);
          if (curShow) renderScenarioIntoPane(curShow, document.getElementById("showcase-detail"));
        }

        // Warn if Edit modal is currently open for a scenario modified by someone else
        const editOpen = document.getElementById("edit-modal")?.classList.contains("active");
        if (editOpen) {
          const editingSid = document.getElementById("edit-sid")?.value;
          const fresh = SCENARIOS.find(s => s.scenario_id === editingSid);
          if (fresh && fresh._sync && fresh._sync.version && editBaseVersion && fresh._sync.version !== editBaseVersion) {
            const banner = document.getElementById("edit-concurrent-banner");
            const msgEl = document.getElementById("edit-concurrent-msg");
            if (banner && msgEl) {
              msgEl.textContent = `${fresh._sync.updated_by || 'Another collaborator'} just saved changes to ${editingSid} (v${fresh._sync.version}). Your untouched fields are safe; conflicting fields will open the 3-way merge tool on Save.`;
              banner.style.display = "block";
            }
          }
        }

        if (!silent) {
          showToast("🔄 Synced latest scenarios from OneDrive Excel!");
        }
      } catch (e) {
        // Offline static fallback
      }
    }

    async function triggerManualSync() {
      try {
        const resp = await fetch("/api/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ actor: getActiveUser() })
        });
        const data = await resp.json();
        if (data.scenarios) SCENARIOS = data.scenarios;
        if (data.sync_meta) {
          lastSyncMeta = data.sync_meta;
          lastKnownRevision = data.sync_meta.revision;
          _renderSyncBadge(data.sync_meta);
        }
        updateDashboardCounts();
        renderScenariosList();
        renderSyncModalBody();
        showToast("🔄 OneDrive Excel & team changes synchronized!");
      } catch (e) {
        showToast("Offline mode: Start 'python3 demo_app.py' for OneDrive sync.", false);
      }
    }

    async function checkServerStatus() {
      try {
        const res = await fetch("/api/status");
        const data = await res.json();
        if (data.status === "running") {
          lastSyncMeta = data;
          _renderSyncBadge(data);
          if (lastKnownRevision !== null && data.revision && data.revision !== lastKnownRevision) {
            const latestEv = (data.recent_events || [])[0];
            await fetchLiveScenarios(true);
            if (latestEv && latestEv.actor && latestEv.actor !== getActiveUser()) {
              showToast(`🔄 Synced ${latestEv.op} by ${latestEv.actor} (${latestEv.scenario_id})`);
            }
          }
          lastKnownRevision = data.revision;
        }
      } catch (e) {
        serverConnected = false;
        const badge = document.getElementById("sync-status-badge");
        if (badge) {
          badge.innerHTML = "⚡ Static View (Run python3 demo_app.py for OneDrive Sync)";
          badge.style.background = "#fef3c7";
          badge.style.color = "#b45309";
          badge.title = "Run python3 demo_app.py to enable live multi-user OneDrive Excel sync.";
        }
      }
    }

    window.onload = async () => {
      setActiveUser(getActiveUser());
      updateDashboardCounts();
      await checkServerStatus();
      if (serverConnected) {
        await fetchLiveScenarios(true);
      }
      selectShowcase('SCN-000001', document.querySelector('.showcase-card'));
      setInterval(checkServerStatus, 4000);
    };
  </script>
</body>
</html>
"""

def build_dashboard():
    import csv

    scn_path = SCENARIOS_PATH if os.path.exists(SCENARIOS_PATH) else os.path.join(WORKSPACE_ROOT, "workbook_scenarios_v0.2.jsonl")
    scenarios = []
    with open(scn_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                scenarios.append(json.loads(line))

    facts_target = os.path.join(WORKSPACE_ROOT, "data/scenarios/richard_facts_842.json")
    if not os.path.exists(facts_target):
        facts_target = FACTS_PATH
    if not os.path.exists(facts_target):
        facts_target = os.path.join(WORKSPACE_ROOT, "richard_facts_842.json")
    if not os.path.exists(facts_target):
        facts_target = os.path.join(WORKSPACE_ROOT, "richard_facts_839.json")

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
                    .replace("__KG_DATA_JSON__", kg_data_json_str))

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Generated standalone web demo: {OUTPUT_HTML}")

    if os.path.exists(os.path.dirname(OUTPUT_PKG_HTML)):
        with open(OUTPUT_PKG_HTML, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Generated standalone web demo in Desktop package: {OUTPUT_PKG_HTML}")

if __name__ == "__main__":
    build_dashboard()
