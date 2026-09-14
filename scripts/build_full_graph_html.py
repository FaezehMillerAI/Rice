import csv
import json
import os

def build_html():
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
    with open('registry/disease-registry.csv', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            color = '#ef4444' if row['category'] == 'Pathogen' else ('#f59e0b' if 'nitrogen' in row['id'] else '#3b82f6')
            add_node(row['id'], row['canonical_name'], 'Disease', 'hexagon', color, 28, pref_label=row['skos_pref_label'], alt_labels=row['skos_alt_labels'].split('|'), node_type=row['type'], uri=row['id'])

    # 2. Parse terminology-registry.csv
    with open('registry/terminology-registry.csv', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            g = row['entity_type']
            shape = 'dot'
            color = '#fbbf24'
            size = 18
            if g == 'Sign': shape = 'diamond'; color = '#dc2626'; size = 22
            elif g == 'PlantPart': shape = 'ellipse'; color = '#10b981'; size = 16
            elif g == 'GrowthStage': shape = 'box'; color = '#06b6d4'; size = 16
            elif g == 'EnvironmentalCondition': shape = 'triangle'; color = '#3b82f6'; size = 18
            elif g == 'FieldDistribution': shape = 'square'; color = '#c084fc'; size = 18
            elif g == 'DiagnosticObservation': shape = 'star'; color = '#a855f7'; size = 20
            elif g == 'DiagnosticQuestion': shape = 'box'; color = '#06b6d4'; size = 20
            
            alt_l = [x.strip() for x in row.get('skos_alt_labels', '').split('|') if x.strip()]
            farmer_l = [x.strip() for x in row.get('farmer_phrasings', '').split('|') if x.strip()]
            add_node(row['term_id'], row['skos_pref_label'], g, shape, color, size, pref_label=row['skos_pref_label'], alt_labels=alt_l, hidden_labels=farmer_l, node_type=g, uri=row['term_id'])

    # 3. Parse question-registry.csv
    with open('registry/question-registry.csv', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            add_node(row['question_id'], row['question_id'].replace('q:', 'Q: '), 'DiagnosticQuestion', 'box', '#06b6d4', 22, pref_label=row['canonical_text'], hidden_labels=[row.get('farmer_friendly_phrasing', '')], node_type='DiagnosticQuestion', uri=row['question_id'], rationale=row['rationale'], effort=row['effort_score'])
            edges.append({'from': row['question_id'], 'to': row['target_observation_id'], 'label': 'observesParameter'})

    # 4. Parse source-registry.csv
    with open('registry/source-registry.csv', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            add_node(row['source_id'], row['title'], 'Source', 'ellipse', '#10b981', 20, pref_label=row['title'], node_type='SourceDocument', uri=row['source_id'])

    # 5. Parse logic-state-registry.csv
    with open('registry/logic-state-registry.csv', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            color = '#10b981' if row['state_id'] == 'state:TRUE' else ('#ef4444' if row['state_id'] == 'state:FALSE' else '#f59e0b')
            add_node(row['state_id'], row['state_name'], 'TruthState', 'ellipse', color, 16, pref_label=row['state_name'], node_type='TruthState', uri=row['state_id'], rationale=row['description'])

    # 6. Parse evidence-rules.csv
    with open('registry/evidence-rules.csv', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            label = 'supports' if row['evidence_type'] == 'Supporting' else 'contradicts'
            edges.append({'from': row['observation_id'], 'to': row['cause_id'], 'label': label, 'dashes': (row['evidence_type'] != 'Supporting')})

    # 7. Parse provenance-claims-registry.csv
    with open('registry/provenance-claims-registry.csv', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            add_node(row['claim_id'], row['claim_id'].replace('claim:', 'Claim: '), 'Source', 'triangle', '#34d399', 18, pref_label=row['source_text_span'], node_type='EvidenceClaim', uri=row['claim_id'], rationale=f"Section: {row['source_section']} | SME: {row['sme_reviewer']} ({row['sme_approval_status']})")
            edges.append({'from': row['claim_id'], 'to': row['source_id'], 'label': 'wasDerivedFrom'})
            edges.append({'from': row['subject_uri'], 'to': row['claim_id'], 'label': 'supportedBy'})

    # 8. Add PROV-O Agents & Diagnostic Contrasts & Pathogens
    add_node('agent:irri_institution', 'IRRI Institution', 'Agent', 'square', '#10b981', 20, pref_label='International Rice Research Institute (IRRI)', node_type='PROV_Agent', uri='agent:irri_institution', rationale='Authoritative diagnostic publisher')
    add_node('agent:richard_lindsay', 'Richard Lindsay (SME)', 'Agent', 'square', '#06b6d4', 20, pref_label='Richard Lindsay (Pathogen SME)', node_type='PROV_Agent', uri='agent:richard_lindsay', rationale='Lead Pathogen Subject Matter Expert')
    edges.append({'from': 'source:irri_rice_doctor_2024', 'to': 'agent:irri_institution', 'label': 'wasAttributedTo'})
    edges.append({'from': 'claim:claim_blb_001', 'to': 'agent:richard_lindsay', 'label': 'wasAssociatedWith'})

    add_node('pathogen:xanthomonas_oryzae_pv_oryzae', 'Xanthomonas oryzae pv. oryzae', 'Pathogen', 'hexagon', '#dc2626', 24, pref_label='Xanthomonas oryzae pv. oryzae', node_type='Pathogen', uri='pathogen:xanthomonas_oryzae_pv_oryzae')
    edges.append({'from': 'pathogen:xanthomonas_oryzae_pv_oryzae', 'to': 'disease:bacterial_leaf_blight', 'label': 'causes'})

    add_node('contrast:blb_vs_nitrogen_deficiency', 'BLB vs N-Def Contrast', 'DiagnosticContrast', 'star', '#a855f7', 26, pref_label='BLB vs Nitrogen Deficiency Contrast', node_type='DiagnosticContrast', uri='contrast:blb_vs_nitrogen_deficiency')
    edges.append({'from': 'contrast:blb_vs_nitrogen_deficiency', 'to': 'disease:bacterial_leaf_blight', 'label': 'compares'})
    edges.append({'from': 'contrast:blb_vs_nitrogen_deficiency', 'to': 'disorder:nitrogen_deficiency', 'label': 'compares'})
    edges.append({'from': 'contrast:blb_vs_nitrogen_deficiency', 'to': 'obs:lesion_margin_shape', 'label': 'differentiatedBy'})
    edges.append({'from': 'contrast:blb_vs_nitrogen_deficiency', 'to': 'obs:leaf_age_progression', 'label': 'differentiatedBy'})

    add_node('contrast:blb_vs_water_stress', 'BLB vs Water Stress Contrast', 'DiagnosticContrast', 'star', '#a855f7', 26, pref_label='BLB vs Water Stress Contrast', node_type='DiagnosticContrast', uri='contrast:blb_vs_water_stress')
    edges.append({'from': 'contrast:blb_vs_water_stress', 'to': 'disease:bacterial_leaf_blight', 'label': 'compares'})
    edges.append({'from': 'contrast:blb_vs_water_stress', 'to': 'disorder:water_stress', 'label': 'compares'})
    edges.append({'from': 'contrast:blb_vs_water_stress', 'to': 'obs:leaf_rolling_folding', 'label': 'differentiatedBy'})

    add_node('contrast:nitrogen_deficiency_vs_water_stress', 'N-Def vs Water Stress Contrast', 'DiagnosticContrast', 'star', '#a855f7', 26, pref_label='Nitrogen Deficiency vs Water Stress Contrast', node_type='DiagnosticContrast', uri='contrast:nitrogen_deficiency_vs_water_stress')
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

    with open('all_nodes_data.json', 'w', encoding='utf-8') as f:
        json.dump({'nodes': nodes_list, 'edges': edges}, f, indent=2)

    print(f"Generated {len(nodes_list)} nodes and {len(edges)} edges.")

    template_path = '/Users/faezeh/.gemini/antigravity/brain/113d63da-7dc7-4cc4-a7e7-f624a10988db/scratch/explorer_template.html'
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()
    
    final_html = template.replace('__NODES_JSON__', nodes_json).replace('__EDGES_JSON__', edges_json).replace('__NODES_COUNT__', str(len(nodes_list))).replace('__EDGES_COUNT__', str(len(edges)))
    
    with open('kg_explorer.html', 'w', encoding='utf-8') as f:
        f.write(final_html)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(final_html)
    print("Written kg_explorer.html and index.html successfully.")

if __name__ == '__main__':
    build_html()
