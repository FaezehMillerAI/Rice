import csv, json

nodes = {}
edges = []

def add_node(id_str, label, group, shape, color, size, pref_label='', alt_labels=None, hidden_labels=None, node_type='', uri='', rationale='', effort=''):
    if id_str not in nodes:
        nodes[id_str] = {
            'id': id_str,
            'label': label,
            'group': group,
            'shape': shape,
            'color': color,
            'size': size,
            'prefLabel': pref_label or label.replace('\n', ' '),
            'altLabels': alt_labels or [],
            'hiddenLabels': hidden_labels or [],
            'type': node_type or group,
            'uri': uri or id_str,
            'rationale': rationale,
            'effort': effort
        }

# 1. Parse disease-registry.csv
with open('registry/disease-registry.csv') as f:
    r = csv.DictReader(f)
    for row in r:
        color = '#ef4444' if row['category'] == 'Pathogen' else ('#f59e0b' if 'nitrogen' in row['id'] else '#3b82f6')
        add_node(row['id'], row['canonical_name'], 'Disease', 'hexagon', color, 30, pref_label=row['skos_pref_label'], alt_labels=row['skos_alt_labels'].split('|'), node_type=row['type'], uri=row['id'])

# 2. Parse terminology-registry.csv
with open('registry/terminology-registry.csv') as f:
    r = csv.DictReader(f)
    for row in r:
        g = row['entity_type']
        shape = 'dot'
        color = '#fbbf24'
        size = 20
        if g == 'Sign': shape = 'diamond'; color = '#dc2626'; size = 24
        elif g == 'PlantPart': shape = 'ellipse'; color = '#10b981'; size = 18
        elif g == 'GrowthStage': shape = 'box'; color = '#06b6d4'; size = 18
        elif g == 'EnvironmentalCondition': shape = 'triangle'; color = '#3b82f6'; size = 20
        elif g == 'FieldDistribution': shape = 'square'; color = '#c084fc'; size = 20
        elif g == 'DiagnosticObservation': shape = 'star'; color = '#a855f7'; size = 22
        elif g == 'DiagnosticQuestion': shape = 'box'; color = '#06b6d4'; size = 22
        
        alt_l = [x.strip() for x in row['skos_alt_labels'].split('|') if x.strip()] if row['skos_alt_labels'] else []
        farmer_l = [x.strip() for x in row['farmer_phrasings'].split('|') if x.strip()] if row['farmer_phrasings'] else []
        add_node(row['term_id'], row['skos_pref_label'], g, shape, color, size, pref_label=row['skos_pref_label'], alt_labels=alt_l, hidden_labels=farmer_l, node_type=g, uri=row['term_id'])

# 3. Parse question-registry.csv
with open('registry/question-registry.csv') as f:
    r = csv.DictReader(f)
    for row in r:
        add_node(row['question_id'], row['question_id'].replace('q:', 'Q: '), 'DiagnosticQuestion', 'box', '#06b6d4', 24, pref_label=row['canonical_text'], hidden_labels=[row['farmer_friendly_phrasing']], node_type='DiagnosticQuestion', uri=row['question_id'], rationale=row['rationale'], effort=row['effort_score'])
        edges.append({'from': row['question_id'], 'to': row['target_observation_id'], 'label': 'observesParameter'})

# 4. Parse source-registry.csv
with open('registry/source-registry.csv') as f:
    r = csv.DictReader(f)
    for row in r:
        add_node(row['source_id'], row['title'], 'Source', 'ellipse', '#10b981', 24, pref_label=row['title'], node_type='SourceDocument', uri=row['source_id'])

# 5. Parse logic-state-registry.csv
with open('registry/logic-state-registry.csv') as f:
    r = csv.DictReader(f)
    for row in r:
        color = '#10b981' if row['state_id'] == 'state:TRUE' else ('#ef4444' if row['state_id'] == 'state:FALSE' else '#f59e0b')
        add_node(row['state_id'], row['state_name'], 'TruthState', 'ellipse', color, 18, pref_label=row['state_name'], node_type='TruthState', uri=row['state_id'], rationale=row['description'])

# 6. Parse evidence-rules.csv
with open('registry/evidence-rules.csv') as f:
    r = csv.DictReader(f)
    for row in r:
        label = 'supports' if row['evidence_type'] == 'Supporting' else 'contradicts'
        edges.append({'from': row['observation_id'], 'to': row['cause_id'], 'label': label, 'dashes': (row['evidence_type'] != 'Supporting')})

# 7. Parse provenance-claims-registry.csv (Step 10 PROV-O Integration)
with open('registry/provenance-claims-registry.csv') as f:
    r = csv.DictReader(f)
    for row in r:
        add_node(row['claim_id'], row['claim_id'].replace('claim:', 'Claim: '), 'Source', 'triangle', '#34d399', 22, pref_label=row['source_text_span'], node_type='EvidenceClaim', uri=row['claim_id'], rationale=f"Section: {row['source_section']} | SME: {row['sme_reviewer']} ({row['sme_approval_status']})")
        edges.append({'from': row['claim_id'], 'to': row['source_id'], 'label': 'wasDerivedFrom'})
        edges.append({'from': row['subject_uri'], 'to': row['claim_id'], 'label': 'supportedBy'})

# 8. Add PROV-O Agents & Diagnostic Contrasts & Pathogens
add_node('agent:irri_institution', 'IRRI Institution', 'Agent', 'square', '#10b981', 22, pref_label='International Rice Research Institute (IRRI)', node_type='PROV_Agent', uri='agent:irri_institution', rationale='Authoritative diagnostic publisher')
add_node('agent:richard_lindsay', 'Richard Lindsay (SME)', 'Agent', 'square', '#06b6d4', 22, pref_label='Richard Lindsay (Pathogen SME)', node_type='PROV_Agent', uri='agent:richard_lindsay', rationale='Lead Pathogen Subject Matter Expert')
edges.append({'from': 'source:irri_rice_doctor_2024', 'to': 'agent:irri_institution', 'label': 'wasAttributedTo'})
edges.append({'from': 'claim:claim_blb_001', 'to': 'agent:richard_lindsay', 'label': 'wasAssociatedWith'})

add_node('pathogen:xanthomonas_oryzae_pv_oryzae', 'Xanthomonas oryzae pv. oryzae', 'Pathogen', 'hexagon', '#dc2626', 26, pref_label='Xanthomonas oryzae pv. oryzae', node_type='Pathogen', uri='pathogen:xanthomonas_oryzae_pv_oryzae')
edges.append({'from': 'pathogen:xanthomonas_oryzae_pv_oryzae', 'to': 'disease:bacterial_leaf_blight', 'label': 'causes'})

add_node('contrast:blb_vs_nitrogen_deficiency', 'BLB vs N-Def Contrast', 'DiagnosticContrast', 'star', '#a855f7', 28, pref_label='BLB vs Nitrogen Deficiency Contrast', node_type='DiagnosticContrast', uri='contrast:blb_vs_nitrogen_deficiency')
edges.append({'from': 'contrast:blb_vs_nitrogen_deficiency', 'to': 'disease:bacterial_leaf_blight', 'label': 'compares'})
edges.append({'from': 'contrast:blb_vs_nitrogen_deficiency', 'to': 'disorder:nitrogen_deficiency', 'label': 'compares'})
edges.append({'from': 'contrast:blb_vs_nitrogen_deficiency', 'to': 'obs:lesion_margin_shape', 'label': 'differentiatedBy'})
edges.append({'from': 'contrast:blb_vs_nitrogen_deficiency', 'to': 'obs:leaf_age_progression', 'label': 'differentiatedBy'})

add_node('contrast:blb_vs_water_stress', 'BLB vs Water Stress Contrast', 'DiagnosticContrast', 'star', '#a855f7', 28, pref_label='BLB vs Water Stress Contrast', node_type='DiagnosticContrast', uri='contrast:blb_vs_water_stress')
edges.append({'from': 'contrast:blb_vs_water_stress', 'to': 'disease:bacterial_leaf_blight', 'label': 'compares'})
edges.append({'from': 'contrast:blb_vs_water_stress', 'to': 'disorder:water_stress', 'label': 'compares'})
edges.append({'from': 'contrast:blb_vs_water_stress', 'to': 'obs:leaf_rolling_folding', 'label': 'differentiatedBy'})

add_node('contrast:nitrogen_deficiency_vs_water_stress', 'N-Def vs Water Stress Contrast', 'DiagnosticContrast', 'star', '#a855f7', 28, pref_label='Nitrogen Deficiency vs Water Stress Contrast', node_type='DiagnosticContrast', uri='contrast:nitrogen_deficiency_vs_water_stress')
edges.append({'from': 'contrast:nitrogen_deficiency_vs_water_stress', 'to': 'disorder:nitrogen_deficiency', 'label': 'compares'})
edges.append({'from': 'contrast:nitrogen_deficiency_vs_water_stress', 'to': 'disorder:water_stress', 'label': 'compares'})

# Domain Edges
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'symptom:leaf_yellowing', 'label': 'presentsAs'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'symptom:water_soaked_wavy_lesion', 'label': 'presentsAs'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'symptom:leaf_tip_margin_necrosis', 'label': 'presentsAs'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'sign:bacterial_ooze_beads', 'label': 'hasSign'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'sign:water_test_cloudy_streaming', 'label': 'hasSign'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'part:leaf', 'label': 'affectsPlantPart'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'part:leaf_sheath', 'label': 'affectsPlantPart'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'stage:tillering', 'label': 'occursAtStage'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'stage:heading', 'label': 'occursAtStage'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'env:high_humidity', 'label': 'favoredBy'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'env:heavy_rainfall', 'label': 'favoredBy'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'env:standing_water', 'label': 'favoredBy'})
edges.append({'from': 'disease:bacterial_leaf_blight', 'to': 'field:patchy_distribution', 'label': 'hasFieldDistribution'})

edges.append({'from': 'disorder:nitrogen_deficiency', 'to': 'symptom:leaf_yellowing', 'label': 'presentsAs'})
edges.append({'from': 'disorder:nitrogen_deficiency', 'to': 'symptom:uniform_older_leaf_chlorosis', 'label': 'presentsAs'})
edges.append({'from': 'disorder:nitrogen_deficiency', 'to': 'symptom:stunted_growth', 'label': 'presentsAs'})
edges.append({'from': 'disorder:nitrogen_deficiency', 'to': 'part:older_leaves', 'label': 'affectsPlantPart'})
edges.append({'from': 'disorder:nitrogen_deficiency', 'to': 'stage:tillering', 'label': 'occursAtStage'})
edges.append({'from': 'disorder:nitrogen_deficiency', 'to': 'field:uniform_fieldwide_distribution', 'label': 'hasFieldDistribution'})

edges.append({'from': 'disorder:water_stress', 'to': 'symptom:leaf_rolling_folding', 'label': 'presentsAs'})
edges.append({'from': 'disorder:water_stress', 'to': 'symptom:leaf_yellowing', 'label': 'presentsAs'})
edges.append({'from': 'disorder:water_stress', 'to': 'sign:recovers_upon_rewatering', 'label': 'hasSign'})
edges.append({'from': 'disorder:water_stress', 'to': 'part:leaf', 'label': 'affectsPlantPart'})
edges.append({'from': 'disorder:water_stress', 'to': 'field:elevation_dependent_distribution', 'label': 'hasFieldDistribution'})

nodes_list = list(nodes.values())
nodes_json = json.dumps(nodes_list, indent=2)
edges_json = json.dumps(edges, indent=2)

html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rice Pathogen SALM — Knowledge Graph & PROV-O Provenance ({len(nodes_list)} Nodes | {len(edges)} Edges)</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Fira+Code:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-dark: #070b14;
      --panel-bg: rgba(15, 23, 42, 0.85);
      --card-bg: rgba(30, 41, 59, 0.8);
      --accent-green: #10b981;
      --accent-cyan: #06b6d4;
      --accent-blue: #3b82f6;
      --accent-purple: #a855f7;
      --accent-yellow: #f59e0b;
      --accent-red: #ef4444;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --border-color: rgba(255, 255, 255, 0.12);
      --glow-green: 0 0 20px rgba(16, 185, 129, 0.5);
      --glow-cyan: 0 0 20px rgba(6, 182, 212, 0.5);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', sans-serif;
      background-color: var(--bg-dark);
      color: var(--text-main);
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}
    header {{
      background: var(--panel-bg);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 20;
    }}
    .brand {{ display: flex; align-items: center; gap: 14px; }}
    .brand-icon {{
      width: 40px; height: 40px;
      background: linear-gradient(135deg, var(--accent-green), var(--accent-cyan));
      border-radius: 10px; display: flex; align-items: center; justify-content: center;
      font-size: 20px; color: #000; box-shadow: var(--glow-green);
    }}
    .brand h1 {{ font-size: 19px; font-weight: 800; letter-spacing: -0.5px; }}
    .brand-badge {{
      font-size: 11px; background: rgba(16, 185, 129, 0.2); color: var(--accent-green);
      padding: 4px 12px; border-radius: 20px; font-weight: 700; border: 1px solid var(--accent-green);
    }}
    .header-actions {{ display: flex; align-items: center; gap: 12px; }}
    .story-btn {{
      background: linear-gradient(135deg, var(--accent-purple), var(--accent-blue));
      color: #fff; border: none; padding: 8px 16px; border-radius: 8px; font-size: 12px;
      font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 8px;
      box-shadow: 0 0 15px rgba(168, 85, 247, 0.4);
    }}
    .tab-buttons {{
      display: flex; background: rgba(0, 0, 0, 0.4); padding: 3px; border-radius: 10px; border: 1px solid var(--border-color);
    }}
    .tab-btn {{
      background: transparent; color: var(--text-muted); border: none; padding: 8px 18px;
      border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 13px; transition: all 0.2s;
      display: flex; align-items: center; gap: 8px;
    }}
    .tab-btn.active {{ background: linear-gradient(135deg, var(--accent-blue), var(--accent-cyan)); color: #fff; }}
    .main-container {{ flex: 1; display: flex; position: relative; overflow: hidden; }}
    #graph-tab {{ flex: 1; display: flex; width: 100%; height: 100%; position: relative; }}
    #mynetwork {{ flex: 1; height: 100%; background: radial-gradient(circle at center, #0f172a 0%, #030712 100%); }}
    .search-overlay {{
      position: absolute; top: 20px; left: 20px; z-index: 10; display: flex; gap: 10px;
      background: var(--panel-bg); backdrop-filter: blur(12px); padding: 8px 14px; border-radius: 12px;
      border: 1px solid var(--border-color); width: 340px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }}
    .search-overlay input {{ background: transparent; border: none; outline: none; color: #fff; font-size: 13px; width: 100%; }}
    .controls-overlay {{
      position: absolute; bottom: 20px; left: 20px; z-index: 10; display: flex; gap: 8px;
      background: var(--panel-bg); backdrop-filter: blur(12px); padding: 8px; border-radius: 10px; border: 1px solid var(--border-color);
    }}
    .ctrl-btn {{
      background: var(--card-bg); border: 1px solid var(--border-color); color: var(--text-main);
      width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
      cursor: pointer; font-size: 14px; transition: all 0.2s;
    }}
    .sidebar {{
      width: 420px; background: var(--panel-bg); backdrop-filter: blur(16px); border-left: 1px solid var(--border-color);
      display: flex; flex-direction: column; overflow-y: auto; z-index: 10;
    }}
    .sidebar-header {{ padding: 18px 20px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; }}
    .filter-section {{ padding: 16px 20px; border-bottom: 1px solid var(--border-color); }}
    .filter-title {{ font-size: 11px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 12px; font-weight: 700; }}
    .filter-chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .chip {{ font-size: 11px; padding: 5px 11px; border-radius: 20px; cursor: pointer; border: 1px solid var(--border-color); background: var(--card-bg); color: var(--text-main); font-weight: 600; }}
    .chip.active {{ border-color: var(--accent-cyan); background: rgba(6, 182, 212, 0.2); color: #fff; }}
    .node-details {{ padding: 20px; flex: 1; }}
    .empty-state {{ text-align: center; padding: 50px 20px; color: var(--text-muted); }}
    .detail-card {{ background: var(--card-bg); border-radius: 10px; padding: 14px; margin-bottom: 12px; border: 1px solid var(--border-color); }}
    .detail-title {{ font-size: 10px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 4px; font-weight: 700; }}
    .detail-value {{ font-size: 13px; font-weight: 600; word-break: break-word; }}
    .tag-list {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }}
    .tag {{ background: rgba(6, 182, 212, 0.2); color: var(--accent-cyan); font-size: 11px; padding: 3px 8px; border-radius: 6px; font-family: 'Fira Code', monospace; border: 1px solid rgba(6, 182, 212, 0.3); }}
    
    #triage-tab {{ flex: 1; display: none; padding: 28px; overflow-y: auto; }}
    .triage-grid {{ display: grid; grid-template-columns: 1fr 1.25fr; gap: 28px; width: 100%; max-width: 1440px; margin: 0 auto; }}
    .triage-card {{ background: var(--panel-bg); backdrop-filter: blur(16px); border: 1px solid var(--border-color); border-radius: 16px; padding: 24px; display: flex; flex-direction: column; gap: 18px; }}
    .triage-card-title {{ font-size: 17px; font-weight: 700; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 14px; }}
    .obs-row {{ display: flex; justify-content: space-between; align-items: center; background: var(--card-bg); padding: 14px 16px; border-radius: 10px; border: 1px solid var(--border-color); }}
    .obs-info {{ display: flex; flex-direction: column; gap: 3px; }}
    .obs-name {{ font-size: 14px; font-weight: 700; }}
    .obs-id {{ font-size: 11px; color: var(--text-muted); font-family: 'Fira Code', monospace; }}
    .btn-3vl-group {{ display: flex; background: var(--bg-dark); border-radius: 8px; padding: 3px; gap: 3px; border: 1px solid var(--border-color); }}
    .btn-3vl {{ border: none; padding: 6px 14px; font-size: 11px; font-weight: 800; border-radius: 6px; cursor: pointer; background: transparent; color: var(--text-muted); }}
    .btn-3vl[data-state="TRUE"].active {{ background: var(--accent-green); color: #000; }}
    .btn-3vl[data-state="FALSE"].active {{ background: var(--accent-red); color: #fff; }}
    .btn-3vl[data-state="UNKNOWN"].active {{ background: var(--accent-yellow); color: #000; }}
    .diff-item {{ background: var(--card-bg); border-radius: 12px; padding: 18px; border: 1px solid var(--border-color); display: flex; flex-direction: column; gap: 12px; }}
    .diff-item.rank-1 {{ border-color: var(--accent-green); box-shadow: var(--glow-green); }}
    .diff-header {{ display: flex; justify-content: space-between; align-items: center; }}
    .diff-name {{ font-size: 16px; font-weight: 800; }}
    .score-badge {{ padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: 800; font-family: 'Fira Code', monospace; }}
    .score-high {{ background: rgba(16, 185, 129, 0.2); color: var(--accent-green); border: 1px solid var(--accent-green); }}
    .score-med {{ background: rgba(245, 158, 11, 0.2); color: var(--accent-yellow); border: 1px solid var(--accent-yellow); }}
    .score-low {{ background: rgba(239, 68, 68, 0.2); color: var(--accent-red); border: 1px solid var(--accent-red); }}
    .evidence-section {{ display: flex; flex-direction: column; gap: 6px; font-size: 12px; }}
    .bucket-title {{ font-weight: 800; font-size: 11px; text-transform: uppercase; }}
    .bucket-supporting {{ color: var(--accent-green); }}
    .bucket-contradicting {{ color: var(--accent-red); }}
    .bucket-missing {{ color: var(--accent-yellow); }}
    .utility-question-box {{ background: rgba(6, 182, 212, 0.15); border: 1px solid var(--accent-cyan); border-radius: 12px; padding: 16px; box-shadow: var(--glow-cyan); }}
    .utility-title {{ font-size: 11px; text-transform: uppercase; font-weight: 800; color: var(--accent-cyan); margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }}
    .story-modal {{ display: none; position: fixed; inset: 0; background: rgba(0, 0, 0, 0.85); backdrop-filter: blur(12px); z-index: 100; align-items: center; justify-content: center; padding: 20px; }}
    .story-card {{ background: var(--panel-bg); border: 1px solid var(--accent-purple); border-radius: 18px; max-width: 640px; width: 100%; padding: 30px; display: flex; flex-direction: column; gap: 20px; }}
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-icon"><i class="fa-solid fa-wheat-awn"></i></div>
      <div>
        <h1>Rice Pathogen SALM</h1>
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">IAAIR × Exeter × OpenAg Provenance Graph</div>
      </div>
      <span class="brand-badge"><i class="fa-solid fa-certificate"></i> {len(nodes_list)} Nodes | {len(edges)} Edges</span>
    </div>

    <div class="header-actions">
      <button class="story-btn" onclick="startStoryMode()"><i class="fa-solid fa-play"></i> Interactive Story Mode</button>
      <div class="tab-buttons">
        <button class="tab-btn active" onclick="switchTab('graph')"><i class="fa-solid fa-network-wired"></i> Graph Visualizer</button>
        <button class="tab-btn" onclick="switchTab('triage')"><i class="fa-solid fa-notes-medical"></i> 3VL Triage Studio</button>
      </div>
    </div>
  </header>

  <div class="main-container">
    <div id="graph-tab">
      <div id="mynetwork"></div>

      <div class="search-overlay">
        <i class="fa-solid fa-magnifying-glass"></i>
        <input type="text" id="graph-search" placeholder="Search across all {len(nodes_list)} nodes..." oninput="searchGraph(this.value)">
      </div>

      <div class="controls-overlay">
        <button class="ctrl-btn" title="Zoom In" onclick="zoomNetwork(1.2)"><i class="fa-solid fa-plus"></i></button>
        <button class="ctrl-btn" title="Zoom Out" onclick="zoomNetwork(0.8)"><i class="fa-solid fa-minus"></i></button>
        <button class="ctrl-btn" title="Fit All Nodes" onclick="fitNetwork()"><i class="fa-solid fa-expand"></i></button>
        <button class="ctrl-btn" title="Toggle Particles" id="particle-toggle" style="color: var(--text-muted);" onclick="toggleParticles()"><i class="fa-solid fa-sparkles"></i></button>
      </div>

      <div class="sidebar">
        <div class="sidebar-header">
          <h2><i class="fa-solid fa-sliders"></i> Filter & Entity Inspector</h2>
        </div>

        <div class="filter-section">
          <div class="filter-title">Entity Categories ({len(nodes_list)} Total)</div>
          <div class="filter-chips">
            <div class="chip active" onclick="toggleFilter('all', this)">All ({len(nodes_list)})</div>
            <div class="chip" onclick="toggleFilter('Disease', this)">Diseases</div>
            <div class="chip" onclick="toggleFilter('Symptom', this)">Symptoms</div>
            <div class="chip" onclick="toggleFilter('Sign', this)">Signs</div>
            <div class="chip" onclick="toggleFilter('DiagnosticContrast', this)">Contrasts</div>
            <div class="chip" onclick="toggleFilter('DiagnosticQuestion', this)">Questions</div>
            <div class="chip" onclick="toggleFilter('Source', this)">Sources & Claims</div>
            <div class="chip" onclick="toggleFilter('Agent', this)">PROV-O Agents</div>
          </div>
        </div>

        <div class="node-details" id="node-inspector">
          <div class="empty-state">
            <i class="fa-solid fa-hand-pointer"></i>
            <p>Click any node or claim receipt to inspect verbatim text spans, SME reviewer sign-offs, and PROV-O provenance.</p>
          </div>
        </div>
      </div>
    </div>

    <div id="triage-tab">
      <div class="triage-grid">
        <div class="triage-card">
          <div class="triage-card-title">
            <span><i class="fa-solid fa-clipboard-check"></i> Field Observations (3VL Input)</span>
            <button class="tab-btn" style="padding: 4px 10px; font-size: 11px;" onclick="resetSimulator()">Reset Case</button>
          </div>
          <p style="font-size: 12px; color: var(--text-muted);">
            Toggle truth states (<strong>TRUE</strong> = Present, <strong>FALSE</strong> = Absent, <strong>UNKNOWN</strong> = Unobserved). Under Open World Assumption, UNKNOWN never penalizes candidate causes!
          </p>

          <div class="obs-row">
            <div class="obs-info"><span class="obs-name">Leaf Yellowing (Chlorosis)</span><span class="obs-id">obs:leaf_yellowing</span></div>
            <div class="btn-3vl-group">
              <button class="btn-3vl active" data-obs="leaf_yellowing" data-state="TRUE" onclick="setObs('leaf_yellowing', 'TRUE')">TRUE</button>
              <button class="btn-3vl" data-obs="leaf_yellowing" data-state="FALSE" onclick="setObs('leaf_yellowing', 'FALSE')">FALSE</button>
              <button class="btn-3vl" data-obs="leaf_yellowing" data-state="UNKNOWN" onclick="setObs('leaf_yellowing', 'UNKNOWN')">UNKNOWN</button>
            </div>
          </div>

          <div class="obs-row">
            <div class="obs-info"><span class="obs-name">Water-Soaked Wavy Lesions</span><span class="obs-id">obs:lesion_margin_shape</span></div>
            <div class="btn-3vl-group">
              <button class="btn-3vl" data-obs="lesion_margin_shape" data-state="TRUE" onclick="setObs('lesion_margin_shape', 'TRUE')">TRUE</button>
              <button class="btn-3vl" data-obs="lesion_margin_shape" data-state="FALSE" onclick="setObs('lesion_margin_shape', 'FALSE')">FALSE</button>
              <button class="btn-3vl active" data-obs="lesion_margin_shape" data-state="UNKNOWN" onclick="setObs('lesion_margin_shape', 'UNKNOWN')">UNKNOWN</button>
            </div>
          </div>

          <div class="obs-row">
            <div class="obs-info"><span class="obs-name">Uniform Older Leaf Yellowing</span><span class="obs-id">obs:leaf_age_progression</span></div>
            <div class="btn-3vl-group">
              <button class="btn-3vl" data-obs="leaf_age_progression" data-state="TRUE" onclick="setObs('leaf_age_progression', 'TRUE')">TRUE</button>
              <button class="btn-3vl" data-obs="leaf_age_progression" data-state="FALSE" onclick="setObs('leaf_age_progression', 'FALSE')">FALSE</button>
              <button class="btn-3vl active" data-obs="leaf_age_progression" data-state="UNKNOWN" onclick="setObs('leaf_age_progression', 'UNKNOWN')">UNKNOWN</button>
            </div>
          </div>

          <div class="obs-row">
            <div class="obs-info"><span class="obs-name">Cut-Leaf Water Ooze Streaming</span><span class="obs-id">obs:bacterial_ooze_test</span></div>
            <div class="btn-3vl-group">
              <button class="btn-3vl" data-obs="bacterial_ooze_test" data-state="TRUE" onclick="setObs('bacterial_ooze_test', 'TRUE')">TRUE</button>
              <button class="btn-3vl" data-obs="bacterial_ooze_test" data-state="FALSE" onclick="setObs('bacterial_ooze_test', 'FALSE')">FALSE</button>
              <button class="btn-3vl active" data-obs="bacterial_ooze_test" data-state="UNKNOWN" onclick="setObs('bacterial_ooze_test', 'UNKNOWN')">UNKNOWN</button>
            </div>
          </div>

          <div class="obs-row">
            <div class="obs-info"><span class="obs-name">Inward Leaf Rolling / Folding</span><span class="obs-id">obs:leaf_rolling_folding</span></div>
            <div class="btn-3vl-group">
              <button class="btn-3vl" data-obs="leaf_rolling_folding" data-state="TRUE" onclick="setObs('leaf_rolling_folding', 'TRUE')">TRUE</button>
              <button class="btn-3vl" data-obs="leaf_rolling_folding" data-state="FALSE" onclick="setObs('leaf_rolling_folding', 'FALSE')">FALSE</button>
              <button class="btn-3vl active" data-obs="leaf_rolling_folding" data-state="UNKNOWN" onclick="setObs('leaf_rolling_folding', 'UNKNOWN')">UNKNOWN</button>
            </div>
          </div>
        </div>

        <div class="triage-card">
          <div class="triage-card-title">
            <span><i class="fa-solid fa-square-poll-vertical"></i> Live Differential & Question Utility</span>
          </div>

          <div class="utility-question-box" id="top-question-box">
            <div class="utility-title"><i class="fa-solid fa-wand-magic-sparkles"></i> Top Question Utility Selection (Step 7 Engine)</div>
            <div id="top-question-text" style="font-size: 14px; font-weight: 700; line-height: 1.4;">Calculating best next question...</div>
            <div id="top-question-meta" style="font-size: 12px; color: var(--text-muted); margin-top: 6px;"></div>
          </div>

          <div id="differential-results" style="display: flex; flex-direction: column; gap: 14px;"></div>
        </div>
      </div>
    </div>
  </div>

  <div class="story-modal" id="story-modal">
    <div class="story-card">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 12px; color: var(--accent-purple); font-weight: 800; text-transform: uppercase;" id="story-step-num">Step 1 of 5</span>
        <button class="ctrl-btn" onclick="closeStoryMode()"><i class="fa-solid fa-xmark"></i></button>
      </div>
      <h3 style="font-size: 20px; font-weight: 800; color: #fff;" id="story-title">Farmer Input: "My leaves are yellowing"</h3>
      <p style="font-size: 14px; color: var(--text-muted); line-height: 1.6;" id="story-desc">Farmer reports yellowing leaves during tillering. Under binary logic, missing fields would be assumed FALSE. Under 3VL Open World Assumption, missing observations remain UNKNOWN!</p>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
        <button class="tab-btn" id="story-prev-btn" onclick="prevStoryStep()">Previous</button>
        <button class="story-btn" id="story-next-btn" onclick="nextStoryStep()">Next Step <i class="fa-solid fa-arrow-right"></i></button>
      </div>
    </div>
  </div>

  <script>
    const nodesData = {nodes_json};
    const edgesData = {edges_json};

    let network;
    let nodesDataset = new vis.DataSet(nodesData);
    let edgesDataset = new vis.DataSet(edgesData);
    let enableParticles = false;
    let particleStep = 0;
    let animFrameId = null;

    function initNetwork() {{
      const container = document.getElementById('mynetwork');
      const data = {{ nodes: nodesDataset, edges: edgesDataset }};
      const options = {{
        nodes: {{
          font: {{ color: '#f8fafc', face: 'Inter', size: 12, strokeWidth: 3, strokeColor: '#070b14' }},
          borderWidth: 2,
          shadow: false
        }},
        edges: {{
          color: {{ color: 'rgba(100, 116, 139, 0.4)', highlight: '#06b6d4' }},
          arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
          font: {{ color: '#94a3b8', size: 9, face: 'Fira Code', strokeWidth: 2, strokeColor: '#070b14' }},
          smooth: {{ type: 'continuous' }}
        }},
        physics: {{
          solver: 'forceAtlas2Based',
          forceAtlas2Based: {{ gravitationalConstant: -90, centralGravity: 0.012, springLength: 130, springConstant: 0.08 }},
          stabilization: {{ enabled: true, iterations: 150, updateInterval: 25 }}
        }},
        interaction: {{ hover: true, tooltipDelay: 150 }}
      }};

      network = new vis.Network(container, data, options);

      // Freeze physics after initial layout stabilizes to achieve 0% idle GPU load
      network.on("stabilizationIterationsDone", function () {{
        network.setOptions({{ physics: false }});
      }});

      network.on('click', function(params) {{
        if (params.nodes.length > 0) {{
          const nodeId = params.nodes[0];
          const node = nodesData.find(n => n.id === nodeId);
          renderInspector(node);
          highlightNeighborhood(nodeId);
        }} else {{
          resetHighlight();
        }}
      }});

      network.on("afterDrawing", function (ctx) {{
        if (!enableParticles) return;
        particleStep += 0.008;

        const positions = network.getPositions();
        edgesData.forEach(edge => {{
          const fromPos = positions[edge.from];
          const toPos = positions[edge.to];
          if (fromPos && toPos) {{
            const progress = (particleStep + (edge.from.length % 7) * 0.15) % 1;
            const x = fromPos.x + (toPos.x - fromPos.x) * progress;
            const y = fromPos.y + (toPos.y - fromPos.y) * progress;

            ctx.beginPath();
            ctx.arc(x, y, 2.5, 0, 2 * Math.PI, false);
            ctx.fillStyle = 'rgba(6, 182, 212, 0.85)';
            ctx.fill();
          }}
        }});
      }});
    }}

    function highlightNeighborhood(nodeId) {{
      const connectedNodes = network.getConnectedNodes(nodeId);
      connectedNodes.push(nodeId);
      const updateNodes = nodesData.map(n => ({{ id: n.id, opacity: connectedNodes.includes(n.id) ? 1.0 : 0.15 }}));
      nodesDataset.update(updateNodes);
    }}

    function resetHighlight() {{
      const updateNodes = nodesData.map(n => ({{ id: n.id, opacity: 1.0 }}));
      nodesDataset.update(updateNodes);
    }}

    function renderInspector(node) {{
      const container = document.getElementById('node-inspector');
      if (!node) return;

      let html = `
        <div class="detail-card" style="border-left: 4px solid ${{node.color}};">
          <div class="detail-title">Entity Type</div>
          <div class="detail-value" style="color: ${{node.color}}; font-weight: 800;">${{node.type || node.group}}</div>
        </div>
        <div class="detail-card">
          <div class="detail-title">Canonical SKOS Label / Title</div>
          <div class="detail-value" style="font-size: 15px; font-weight: 800; color: #fff;">${{node.prefLabel || node.label}}</div>
        </div>
        <div class="detail-card">
          <div class="detail-title">Stable Graph URI</div>
          <div class="detail-value"><span class="tag">${{node.uri || node.id}}</span></div>
        </div>
      `;

      if (node.altLabels && node.altLabels.length > 0) {{
        html += `
          <div class="detail-card">
            <div class="detail-title">SKOS Alt Labels (Synonyms)</div>
            <div class="tag-list">${{node.altLabels.map(l => `<span class="tag">${{l}}</span>`).join('')}}</div>
          </div>
        `;
      }}

      if (node.hiddenLabels && node.hiddenLabels.length > 0) {{
        html += `
          <div class="detail-card">
            <div class="detail-title">Farmer Vernacular Phrasings</div>
            <div class="tag-list">${{node.hiddenLabels.map(l => `<span class="tag" style="background: rgba(245,158,11,0.2); color: #f59e0b; border-color: rgba(245,158,11,0.3);">"${{l}}"</span>`).join('')}}</div>
          </div>
        `;
      }}

      if (node.rationale) {{
        html += `
          <div class="detail-card">
            <div class="detail-title">Provenance / Scientific Rationale</div>
            <div class="detail-value" style="color: var(--accent-green); line-height: 1.4;">${{node.rationale}}</div>
          </div>
        `;
      }}

      container.innerHTML = html;
    }}

    function searchGraph(query) {{
      if (!query) {{ resetHighlight(); return; }}
      const q = query.toLowerCase();
      const match = nodesData.find(n => n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q) || (n.hiddenLabels && n.hiddenLabels.some(h => h.toLowerCase().includes(q))));
      if (match) {{
        network.focus(match.id, {{ scale: 1.2, animation: {{ duration: 500, easingFunction: 'easeInOutQuad' }} }});
        highlightNeighborhood(match.id);
        renderInspector(match);
      }}
    }}

    function animateParticles() {{
      if (!enableParticles) return;
      network.redraw();
      animFrameId = requestAnimationFrame(animateParticles);
    }}

    function toggleParticles() {{
      enableParticles = !enableParticles;
      const btn = document.getElementById('particle-toggle');
      if (btn) {{
        btn.style.color = enableParticles ? 'var(--accent-cyan)' : 'var(--text-muted)';
      }}
      if (enableParticles) {{
        animateParticles();
      }} else if (animFrameId) {{
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
        network.redraw();
      }}
    }}

    function toggleFilter(group, chipEl) {{
      document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      chipEl.classList.add('active');

      if (group === 'all') {{
        nodesDataset.clear();
        nodesDataset.add(nodesData);
      }} else {{
        const filtered = nodesData.filter(n => n.group === group || n.type === group);
        nodesDataset.clear();
        nodesDataset.add(filtered);
      }}
    }}

    function switchTab(tab) {{
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      if (tab === 'graph') {{
        document.getElementById('graph-tab').style.display = 'flex';
        document.getElementById('triage-tab').style.display = 'none';
        event.target.classList.add('active');
      }} else {{
        document.getElementById('graph-tab').style.display = 'none';
        document.getElementById('triage-tab').style.display = 'flex';
        event.target.classList.add('active');
        runTriageSimulation();
      }}
    }}

    let currentObsState = {{ leaf_yellowing: 'TRUE', lesion_margin_shape: 'UNKNOWN', leaf_age_progression: 'UNKNOWN', bacterial_ooze_test: 'UNKNOWN', leaf_rolling_folding: 'UNKNOWN' }};

    function setObs(param, state) {{
      currentObsState[param] = state;
      document.querySelectorAll(`[data-obs="${{param}}"]`).forEach(btn => {{
        btn.classList.remove('active');
        if (btn.getAttribute('data-state') === state) btn.classList.add('active');
      }});
      runTriageSimulation();
    }}

    function resetSimulator() {{
      currentObsState = {{ leaf_yellowing: 'TRUE', lesion_margin_shape: 'UNKNOWN', leaf_age_progression: 'UNKNOWN', bacterial_ooze_test: 'UNKNOWN', leaf_rolling_folding: 'UNKNOWN' }};
      Object.keys(currentObsState).forEach(param => setObs(param, currentObsState[param]));
    }}

    function runTriageSimulation() {{
      const candidates = [
        {{ id: 'disease:bacterial_leaf_blight', name: 'Bacterial Leaf Blight (BLB)', type: 'pathogen', supporting: [], contradicting: [], missing: [], score: 0 }},
        {{ id: 'disorder:nitrogen_deficiency', name: 'Nitrogen Deficiency', type: 'abiotic_confounder', supporting: [], contradicting: [], missing: [], score: 0 }},
        {{ id: 'disorder:water_stress', name: 'Water-Related Stress', type: 'abiotic_confounder', supporting: [], contradicting: [], missing: [], score: 0 }}
      ];

      if (currentObsState.leaf_yellowing === 'TRUE') {{
        candidates[0].supporting.push('leaf yellowing (+2)'); candidates[0].score += 2;
        candidates[1].supporting.push('leaf yellowing (+2)'); candidates[1].score += 2;
        candidates[2].supporting.push('leaf yellowing (+2)'); candidates[2].score += 2;
      }} else if (currentObsState.leaf_yellowing === 'FALSE') {{
        candidates[0].contradicting.push('no yellowing (-3)'); candidates[0].score -= 3;
        candidates[1].contradicting.push('no yellowing (-3)'); candidates[1].score -= 3;
        candidates[2].contradicting.push('no yellowing (-3)'); candidates[2].score -= 3;
      }}

      if (currentObsState.lesion_margin_shape === 'TRUE') {{
        candidates[0].supporting.push('water-soaked wavy lesions (+3)'); candidates[0].score += 3;
        candidates[1].contradicting.push('wavy lesions present (-3)'); candidates[1].score -= 3;
        candidates[2].contradicting.push('wavy lesions present (-3)'); candidates[2].score -= 3;
      }} else if (currentObsState.lesion_margin_shape === 'FALSE') {{
        candidates[0].contradicting.push('no lesions (-3)'); candidates[0].score -= 3;
        candidates[1].supporting.push('absence of lesions (+1)'); candidates[1].score += 1;
        candidates[2].supporting.push('absence of lesions (+1)'); candidates[2].score += 1;
      }} else {{
        candidates[0].missing.push('lesion margin shape'); candidates[1].missing.push('lesion margin shape');
      }}

      if (currentObsState.leaf_age_progression === 'TRUE') {{
        candidates[1].supporting.push('uniform older leaf chlorosis (+3)'); candidates[1].score += 3;
        candidates[0].contradicting.push('bottom-leaf uniform yellowing (-2)'); candidates[0].score -= 2;
      }} else if (currentObsState.leaf_age_progression === 'FALSE') {{
        candidates[1].contradicting.push('not older leaves first (-3)'); candidates[1].score -= 3;
      }} else {{ candidates[1].missing.push('leaf age progression'); }}

      if (currentObsState.bacterial_ooze_test === 'TRUE') {{
        candidates[0].supporting.push('cloudy bacterial ooze streaming (+5 definitive)'); candidates[0].score += 5;
        candidates[1].contradicting.push('bacterial ooze streaming (-5)'); candidates[1].score -= 5;
        candidates[2].contradicting.push('bacterial ooze streaming (-5)'); candidates[2].score -= 5;
      }} else if (currentObsState.bacterial_ooze_test === 'FALSE') {{
        candidates[0].contradicting.push('negative ooze test (-3)'); candidates[0].score -= 3;
      }} else {{ candidates[0].missing.push('bacterial ooze streaming test'); }}

      if (currentObsState.leaf_rolling_folding === 'TRUE') {{
        candidates[2].supporting.push('inward leaf rolling (+4)'); candidates[2].score += 4;
        candidates[0].contradicting.push('leaf rolling (-1)'); candidates[0].score -= 1;
      }} else if (currentObsState.leaf_rolling_folding === 'FALSE') {{
        candidates[2].contradicting.push('no leaf rolling (-3)'); candidates[2].score -= 3;
      }} else {{ candidates[2].missing.push('leaf rolling status'); }}

      candidates.sort((a, b) => b.score - a.score);

      const resContainer = document.getElementById('differential-results');
      let html = '';

      candidates.forEach((cand, idx) => {{
        let badgeClass = cand.score >= 4 ? 'score-high' : (cand.score >= 1 ? 'score-med' : 'score-low');
        let rankClass = idx === 0 ? 'rank-1' : '';
        html += `
          <div class="diff-item ${{rankClass}}">
            <div class="diff-header">
              <span class="diff-name">#${{idx + 1}} ${{cand.name}} ${{idx === 0 ? '🏆' : ''}}</span>
              <span class="score-badge ${{badgeClass}}">Score: ${{cand.score}}</span>
            </div>
            
            <div class="evidence-section">
              <div class="bucket-title bucket-supporting"><i class="fa-solid fa-circle-check"></i> Supporting Evidence (${{cand.supporting.length}}):</div>
              <div>${{cand.supporting.length > 0 ? cand.supporting.join(', ') : 'None'}}</div>
            </div>

            <div class="evidence-section">
              <div class="bucket-title bucket-contradicting"><i class="fa-solid fa-circle-xmark"></i> Contradicting Evidence (${{cand.contradicting.length}}):</div>
              <div>${{cand.contradicting.length > 0 ? cand.contradicting.join(', ') : 'None'}}</div>
            </div>

            <div class="evidence-section">
              <div class="bucket-title bucket-missing"><i class="fa-solid fa-circle-question"></i> Missing Distinguishing Observations (${{cand.missing.length}}):</div>
              <div>${{cand.missing.length > 0 ? cand.missing.join(', ') : 'None (Fully Specified)'}}</div>
            </div>
          </div>
        `;
      }});

      resContainer.innerHTML = html;

      const qBoxText = document.getElementById('top-question-text');
      const qBoxMeta = document.getElementById('top-question-meta');

      if (currentObsState.lesion_margin_shape === 'UNKNOWN') {{
        qBoxText.innerHTML = `<strong>q:q_lesion_margin:</strong> "Are there visible yellow or brown lesions starting at the leaf tip or margins, and do they have wavy edges?"`;
        qBoxMeta.innerHTML = `<i class="fa-solid fa-chart-line" style="color: var(--accent-cyan);"></i> <strong>Utility Score: 50.0</strong> | User Effort: Low (1) | Separates: BLB vs N-Def & Water Stress`;
      }} else if (currentObsState.leaf_age_progression === 'UNKNOWN') {{
        qBoxText.innerHTML = `<strong>q:q_older_vs_younger:</strong> "Are the lowest (older) leaves turning yellow first in a uniform pattern while upper leaves stay green?"`;
        qBoxMeta.innerHTML = `<i class="fa-solid fa-chart-line" style="color: var(--accent-cyan);"></i> <strong>Utility Score: 40.0</strong> | User Effort: Low (1) | Identifies Nitrogen Deficiency`;
      }} else if (currentObsState.bacterial_ooze_test === 'UNKNOWN' && currentObsState.lesion_margin_shape === 'TRUE') {{
        qBoxText.innerHTML = `<strong>q:q_water_test:</strong> "When cut leaf tissue is placed in a glass of clear water, does a cloudy stream issue into the water?"`;
        qBoxMeta.innerHTML = `<i class="fa-solid fa-chart-line" style="color: var(--accent-cyan);"></i> <strong>Utility Score: 20.0 (Definitive)</strong> | User Effort: Medium (2) | Confirms BLB Vascular Ooze`;
      }} else {{
        qBoxText.innerHTML = `<i class="fa-solid fa-check-double" style="color: var(--accent-green);"></i> All Key Distinguishing Questions Answered! Differential fully resolved.`;
        qBoxMeta.innerHTML = `Case observations are fully specified. No further clarifying questions required.`;
      }}
    }}

    const storySteps = [
      {{ step: "Step 1 of 5", title: 'Initial Farmer Input: "My leaves are yellowing"', desc: 'Farmer reports yellowing leaves during tillering. Under binary logic, missing fields would be assumed FALSE. Under 3VL Open World Assumption, missing observations remain UNKNOWN (0 penalty score)!', action: () => resetSimulator() }},
      {{ step: "Step 2 of 5", title: "Step 7 Question Engine Selects Top Question", desc: "Because Bacterial Leaf Blight, Nitrogen Deficiency, and Water Stress all share yellowing, the Question Utility Engine evaluates available questions and picks q:q_lesion_margin (Utility 50.0).", action: () => {{ resetSimulator(); }} }},
      {{ step: "Step 3 of 5", title: 'Farmer Responds: "No lesions visible at all"', desc: 'Observation lesion_margin_shape transitions from UNKNOWN to FALSE! BLB is immediately penalized (-3), demoting it, while Nitrogen Deficiency rises to #1!', action: () => {{ setObs('lesion_margin_shape', 'FALSE'); }} }},
      {{ step: "Step 4 of 5", title: 'Engine Asks Next Question: q:q_older_vs_younger', desc: 'The engine automatically presents the next highest-utility question: "Are bottom leaves yellowing first?"', action: () => {{ setObs('lesion_margin_shape', 'FALSE'); }} }},
      {{ step: "Step 5 of 5", title: 'Farmer Confirms: "Yes, bottom leaves yellowed first"', desc: 'leaf_age_progression transitions to TRUE! Nitrogen Deficiency reaches top confidence score (+5) with 0 contradicting evidence!', action: () => {{ setObs('lesion_margin_shape', 'FALSE'); setObs('leaf_age_progression', 'TRUE'); }} }}
    ];

    let currentStoryIdx = 0;
    function startStoryMode() {{ currentStoryIdx = 0; renderStoryStep(); document.getElementById('story-modal').style.display = 'flex'; switchTab('triage'); }}
    function closeStoryMode() {{ document.getElementById('story-modal').style.display = 'none'; }}
    function renderStoryStep() {{ const step = storySteps[currentStoryIdx]; document.getElementById('story-step-num').innerText = step.step; document.getElementById('story-title').innerText = step.title; document.getElementById('story-desc').innerText = step.desc; step.action(); }}
    function nextStoryStep() {{ if (currentStoryIdx < storySteps.length - 1) {{ currentStoryIdx++; renderStoryStep(); }} else {{ closeStoryMode(); }} }}
    function prevStoryStep() {{ if (currentStoryIdx > 0) {{ currentStoryIdx--; renderStoryStep(); }} }}

    window.onload = function() {{ initNetwork(); }};
  </script>
</body>
</html>"""

with open('kg_explorer.html', 'w') as f:
    f.write(html_template)

print('Successfully updated kg_explorer.html with PROV-O provenance nodes!')
