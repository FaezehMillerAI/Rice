"""
scripts/export_kg_sqlite.py
Rice Pathogen SALM — Step 19 Deliverable: Compile Research KG to SQLite Mobile Package
Compiles the approved research Knowledge Graph registries into an indexed SQLite database for Android/offline edge deployment.
"""

import os
import csv
import sqlite3

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGISTRY_DIR = os.path.join(WORKSPACE_ROOT, "registry")
DATA_DIR = os.path.join(WORKSPACE_ROOT, "data")
OUTPUT_DB = os.path.join(DATA_DIR, "rice_kg_mobile.db")

def export_kg_to_sqlite():
    if os.path.exists(OUTPUT_DB):
        os.remove(OUTPUT_DB)

    conn = sqlite3.connect(OUTPUT_DB)
    cur = conn.cursor()

    # 1. Diseases / Conditions table
    cur.execute("""
        CREATE TABLE diseases (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            scientific_name TEXT,
            skos_pref_label TEXT NOT NULL,
            skos_alt_labels TEXT,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            v1_scope INTEGER NOT NULL
        )
    """)
    dis_file = os.path.join(REGISTRY_DIR, "disease-registry.csv")
    with open(dis_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cur.execute("""
                INSERT INTO diseases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["id"], r["type"], r["canonical_name"], r["scientific_name"],
                r["skos_pref_label"], r["skos_alt_labels"], r["category"],
                r["status"], 1 if r["v1_scope"].lower() == "true" else 0
            ))

    # 2. Terminology (Symptoms, Signs, PlantParts, Env, etc.)
    cur.execute("""
        CREATE TABLE terminology (
            term_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            canonical_term TEXT NOT NULL,
            skos_pref_label TEXT NOT NULL,
            skos_alt_labels TEXT,
            farmer_phrasings TEXT,
            description TEXT
        )
    """)
    cur.execute("CREATE INDEX idx_term_entity ON terminology(entity_type)")
    term_file = os.path.join(REGISTRY_DIR, "terminology-registry.csv")
    with open(term_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cur.execute("""
                INSERT INTO terminology VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                r["term_id"], r["entity_type"], r["canonical_term"],
                r["skos_pref_label"], r["skos_alt_labels"],
                r["farmer_phrasings"], r["description"]
            ))

    # 3. Diagnostic Questions
    cur.execute("""
        CREATE TABLE diagnostic_questions (
            question_id TEXT PRIMARY KEY,
            target_observation_id TEXT NOT NULL,
            canonical_text TEXT NOT NULL,
            rationale TEXT NOT NULL,
            effort_score INTEGER NOT NULL,
            observability_score INTEGER NOT NULL,
            reliability_score INTEGER NOT NULL,
            default_priority INTEGER NOT NULL,
            farmer_friendly_phrasing TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX idx_q_target ON diagnostic_questions(target_observation_id)")
    q_file = os.path.join(REGISTRY_DIR, "question-registry.csv")
    with open(q_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cur.execute("""
                INSERT INTO diagnostic_questions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["question_id"], r["target_observation_id"], r["canonical_text"],
                r["rationale"], int(r["effort_score"]), int(r["observability_score"]),
                int(r["reliability_score"]), int(r["default_priority"]),
                r["farmer_friendly_phrasing"]
            ))

    # 4. Evidence Rules (Supporting / Contradicting)
    cur.execute("""
        CREATE TABLE evidence_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cause_id TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            condition_truth_state TEXT NOT NULL,
            explanation TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX idx_ev_cause ON evidence_rules(cause_id)")
    cur.execute("CREATE INDEX idx_ev_obs ON evidence_rules(observation_id)")
    ev_file = os.path.join(REGISTRY_DIR, "evidence-rules.csv")
    with open(ev_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cur.execute("""
                INSERT INTO evidence_rules (cause_id, observation_id, evidence_type, condition_truth_state, explanation)
                VALUES (?, ?, ?, ?, ?)
            """, (
                r["cause_id"], r["observation_id"], r["evidence_type"],
                r["condition_truth_state"], r["explanation"]
            ))

    # 5. Provenance Claims Receipts
    cur.execute("""
        CREATE TABLE provenance_claims (
            claim_id TEXT PRIMARY KEY,
            subject_uri TEXT NOT NULL,
            predicate_uri TEXT NOT NULL,
            object_uri TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_section TEXT NOT NULL,
            source_text_span TEXT NOT NULL,
            sme_reviewer TEXT NOT NULL,
            sme_approval_status TEXT NOT NULL,
            review_date TEXT NOT NULL,
            confidence_level TEXT NOT NULL,
            licensing_status TEXT NOT NULL,
            graph_version TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX idx_claim_subject ON provenance_claims(subject_uri)")
    claim_file = os.path.join(REGISTRY_DIR, "provenance-claims-registry.csv")
    with open(claim_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cur.execute("""
                INSERT INTO provenance_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["claim_id"], r["subject_uri"], r["predicate_uri"], r["object_uri"],
                r["source_id"], r["source_section"], r["source_text_span"],
                r["sme_reviewer"], r["sme_approval_status"], r["review_date"],
                r["confidence_level"], r["licensing_status"], r["graph_version"]
            ))

    # 6. Source Registry
    cur.execute("""
        CREATE TABLE sources (
            source_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            publisher TEXT NOT NULL,
            author TEXT NOT NULL,
            publication_date TEXT NOT NULL,
            license_status TEXT NOT NULL,
            training_permission TEXT NOT NULL,
            reviewer TEXT NOT NULL
        )
    """)
    src_file = os.path.join(REGISTRY_DIR, "source-registry.csv")
    with open(src_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cur.execute("""
                INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["source_id"], r["title"], r["publisher"], r["author"],
                r["publication_date"], r["license_status"],
                r["training_permission"], r["reviewer"]
            ))

    conn.commit()
    conn.close()

    size_bytes = os.path.getsize(OUTPUT_DB)
    print(f"Successfully compiled research Knowledge Graph to mobile SQLite package:")
    print(f"  Target File: {OUTPUT_DB}")
    print(f"  Size: {size_bytes} bytes (~{round(size_bytes/1024, 1)} KB)")

if __name__ == "__main__":
    export_kg_to_sqlite()
