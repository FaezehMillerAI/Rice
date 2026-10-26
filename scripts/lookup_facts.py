"""
scripts/lookup_facts.py
Rice Pathogen SALM — Fast Concept & Fact Search Assistant for Scenario Authors
Helps Ginny & Aseel quickly find Concept IDs and Fact IDs without scrolling through Excel.

Usage:
    python3 scripts/lookup_facts.py "whitehead"
    python3 scripts/lookup_facts.py "FACT_030"
    python3 scripts/lookup_facts.py "symptom:lesion_shape"
    python3 scripts/lookup_facts.py --confounders
    python3 scripts/lookup_facts.py              (Interactive search mode)
"""

import os
import sys
import json
import zipfile
import re
import xml.etree.ElementTree as ET

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKBOOK_PATH = os.path.join(WORKSPACE_ROOT, "Scenarios/OneDrive_1_23-10-2026/rice_slm_diagnostic_scenarios.xlsx")
FACTS_JSON_PATH = os.path.join(WORKSPACE_ROOT, "data/scenarios/richard_facts_839.json")

CONFOUNDER_PAIRS = [
    {
        "pair": "Rice Blast vs. Stem Borer (Panicle Whiteheads)",
        "shared_symptom": "symptom:white_empty_panicles ('Whiteheads')",
        "discriminating_question": "question:whitehead_pull_test ('Does white panicle slide out easily or stay attached?')",
        "blast_rule": "Panicle remains firmly intact / attached at neck rot node (FACT_031).",
        "stem_borer_rule": "Panicle and stem easily separate and slide out cleanly when pulled (FACT_030, FACT_381). Stem base shows frass / larval bore holes (FACT_382)."
    },
    {
        "pair": "Rice Blast vs. Brown Spot (Leaf Lesions)",
        "shared_symptom": "Brown lesions on leaf blades",
        "discriminating_question": "question:lesion_shape ('What shape and center color are the leaf lesions?')",
        "blast_rule": "Spindle-shaped / elliptical / diamond lesions with gray-white center and brown/yellow margins (FACT_009, FACT_012).",
        "brown_spot_rule": "Circular to oval / sesame-seed spots with uniform dark brown color (FACT_501, FACT_504)."
    },
    {
        "pair": "Bacterial Leaf Blight vs. Sheath Blight (Canopy Blight)",
        "shared_symptom": "Extensive blighting / drying of foliage",
        "discriminating_question": "question:lesion_progression_direction ('Where did lesions begin and which direction are they moving?')",
        "blb_rule": "Starts at leaf tips / margins with wavy water-soaked edges moving down the blade (FACT_204, FACT_208).",
        "sheath_blight_rule": "Starts near water line on lower sheaths as snake-skin/banded lesions and moves upward (FACT_304, FACT_308)."
    },
    {
        "pair": "Bacterial Leaf Blight vs. Nitrogen Deficiency (Foliar Yellowing)",
        "shared_symptom": "Extensive foliar yellowing across the field",
        "discriminating_question": "question:lesion_margin_type ('Are leaf edges wavy and water-soaked, or is yellowing uniform on older leaves?')",
        "blb_rule": "Yellowing bordered by wavy, translucent water-soaked margins; develops bacterial ooze drops (FACT_211).",
        "nitrogen_rule": "Uniform pale green to yellow chlorosis starting on oldest lower leaves; no lesions or water-soaking (FACT_780, FACT_782)."
    }
]

def load_data():
    concepts = []
    facts = []

    # 1. Load Facts from JSON cache if available, else workbook
    if os.path.exists(FACTS_JSON_PATH):
        with open(FACTS_JSON_PATH, "r", encoding="utf-8") as f:
            facts_dict = json.load(f)
            for fid, fval in facts_dict.items():
                facts.append((
                    fid,
                    fval.get("source_id", ""),
                    fval.get("disease", ""),
                    fval.get("category", ""),
                    fval.get("statement", ""),
                    fval.get("section", "")
                ))

    # 2. Load Concepts from Workbook
    if os.path.exists(WORKBOOK_PATH):
        with zipfile.ZipFile(WORKBOOK_PATH) as z:
            shared_strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                ss_tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
                ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for si in ss_tree.iterfind('.//main:si', ns):
                    text = ''.join(t.text for t in si.iterfind('.//main:t', ns) if t.text)
                    shared_strings.append(text)

            wb_tree = ET.fromstring(z.read('xl/workbook.xml'))
            ns = {
                'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
                'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            }
            rels_tree = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
            r_ns = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
            rid_to_target = {rel.attrib['Id']: rel.attrib['Target'] for rel in rels_tree.iterfind('.//rel:Relationship', r_ns)}

            for s in wb_tree.iterfind('.//main:sheet', ns):
                if s.attrib['name'] == 'Concepts':
                    rid = s.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                    target = 'xl/' + rid_to_target[rid] if not rid_to_target[rid].startswith('xl/') else rid_to_target[rid]
                    stree = ET.fromstring(z.read(target))
                    for row in stree.iterfind('.//main:row', ns):
                        cells = []
                        for c in row.iterfind('.//main:c', ns):
                            val = c.find('main:v', ns)
                            t = c.attrib.get('t')
                            if val is not None and val.text:
                                idx = int(val.text) if t == 's' else None
                                cells.append(shared_strings[idx] if idx is not None and idx < len(shared_strings) else val.text)
                            else:
                                cells.append('')
                        if len(cells) >= 3 and cells[0] and cells[0] != "concept_id":
                            cid = cells[0].strip()
                            ctype = cells[1].strip() if len(cells) > 1 else ""
                            plain = cells[2].strip() if len(cells) > 2 else ""
                            note = cells[4].strip() if len(cells) > 4 else ""
                            concepts.append((cid, ctype, plain, note))

                if not facts and s.attrib['name'] == 'Facts':
                    rid = s.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                    target = 'xl/' + rid_to_target[rid] if not rid_to_target[rid].startswith('xl/') else rid_to_target[rid]
                    stree = ET.fromstring(z.read(target))
                    for row in stree.iterfind('.//main:row', ns):
                        cells = []
                        for c in row.iterfind('.//main:c', ns):
                            val = c.find('main:v', ns)
                            t = c.attrib.get('t')
                            if val is not None and val.text:
                                idx = int(val.text) if t == 's' else None
                                cells.append(shared_strings[idx] if idx is not None and idx < len(shared_strings) else val.text)
                            else:
                                cells.append('')
                        if len(cells) >= 5 and cells[0] and cells[0] != "Fact ID":
                            fid = cells[0].strip()
                            src = cells[1].strip() if len(cells) > 1 else ""
                            dis = cells[2].strip() if len(cells) > 2 else ""
                            cat = cells[3].strip() if len(cells) > 3 else ""
                            stmt = cells[4].strip() if len(cells) > 4 else ""
                            sec = cells[5].strip() if len(cells) > 5 else ""
                            facts.append((fid, src, dis, cat, stmt, sec))

    return concepts, facts

def print_confounders():
    print("\n" + "=" * 76)
    print("  CLINICAL TRIAGE & CONFOUNDER LOOKALIKE MATRIX")
    print("=" * 76 + "\n")
    for i, c in enumerate(CONFOUNDER_PAIRS, 1):
        print(f"[{i}] {c['pair']}")
        print(f"    • Shared Symptom:          {c['shared_symptom']}")
        print(f"    • Discriminating Question: {c['discriminating_question']}")
        for k, v in c.items():
            if k.endswith("_rule"):
                name = k.replace("_rule", "").replace("_", " ").title()
                print(f"    • {name} Rule: {v}")
        print()

def search(query: str, concepts, facts):
    query_clean = query.strip()
    if not query_clean:
        return

    # Check for direct ID lookup
    is_fact_id = re.match(r"^fact[-_]\d+$", query_clean.lower())
    is_concept_id = ":" in query_clean

    print(f"\n=======================================================")
    print(f" SEARCH RESULTS FOR: '{query_clean}'")
    print(f"=======================================================\n")

    terms = [t for t in query_clean.lower().split() if len(t) > 1]

    # 1. Match Concepts
    matched_concepts = []
    for cid, ctype, plain, note in concepts:
        haystack = f"{cid} {ctype} {plain} {note}".lower()
        if is_concept_id and query_clean.lower() in cid.lower():
            matched_concepts.append((100, cid, ctype, plain, note))
        elif any(t in haystack for t in terms):
            score = sum(3 if t in cid.lower() else (2 if t in plain.lower() else 1) for t in terms if t in haystack)
            matched_concepts.append((score, cid, ctype, plain, note))

    matched_concepts.sort(key=lambda x: x[0], reverse=True)

    print(f"--- MATCHING CONCEPTS ({len(matched_concepts)} found) ---")
    if matched_concepts:
        for _, cid, ctype, plain, note in matched_concepts[:8]:
            print(f"  • {cid:<36} [{ctype}] -> \"{plain}\"")
            if note:
                print(f"    Note: {note}")
    else:
        print("  (No direct concept matches)")

    # 2. Match Facts
    matched_facts = []
    for fid, src, dis, cat, stmt, sec in facts:
        norm_fid = fid.lower().replace("-", "_")
        target_norm = query_clean.lower().replace("-", "_")
        
        if is_fact_id and norm_fid == target_norm:
            matched_facts.append((100, fid, src, dis, cat, stmt, sec))
        else:
            haystack = f"{fid} {dis} {cat} {stmt} {sec}".lower()
            if any(t in haystack for t in terms):
                score = sum(3 if t in fid.lower() else (2 if t in stmt.lower() else 1) for t in terms if t in haystack)
                matched_facts.append((score, fid, src, dis, cat, stmt, sec))

    matched_facts.sort(key=lambda x: x[0], reverse=True)

    print(f"\n--- MATCHING FACTS ({len(matched_facts)} found, showing top 6) ---")
    if matched_facts:
        for _, fid, src, dis, cat, stmt, sec in matched_facts[:6]:
            print(f"  • [{fid}] ({dis} | {cat} | {src})")
            print(f"    Statement: \"{stmt}\"")
            if sec:
                print(f"    Section: {sec}")
            print()
    else:
        print("  (No fact matches)")

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg in ["--help", "-h"]:
            print(__doc__)
            return
        elif arg in ["--confounders", "--lookalikes", "-c"]:
            print_confounders()
            return
        else:
            query = " ".join(sys.argv[1:])
            concepts, facts = load_data()
            search(query, concepts, facts)
            return

    # Interactive REPL mode
    print("=" * 65)
    print(" RICE SALM — FAST CONCEPT & FACT SEARCH ASSISTANT")
    print(" Loaded 132 Concepts & 839 Atomic Pathology Facts.")
    print(" Type a search term, 'confounders', or 'exit'.")
    print("=" * 65)

    concepts, facts = load_data()
    while True:
        try:
            val = input("\nSearch > ").strip()
            if not val:
                continue
            if val.lower() in ["exit", "quit", "q"]:
                break
            if val.lower() in ["confounders", "--confounders", "matrix"]:
                print_confounders()
                continue
            search(val, concepts, facts)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting search assistant.")
            break

if __name__ == "__main__":
    main()
