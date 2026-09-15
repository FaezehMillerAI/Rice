"""
field_app/telemetry_logger.py
Rice Pathogen SALM — Field Pilot Telemetry & Ground Truth Capture (Step 21.2)
Logs field sessions to local SQLite database and JSONL with cryptographic HMAC audit signatures.
"""

import hashlib
import hmac
import json
import os
import sqlite3
import time
import uuid
from typing import Dict, Any, Optional

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TELEMETRY_DIR = os.path.join(WORKSPACE_ROOT, "telemetry")
DB_PATH = os.path.join(TELEMETRY_DIR, "field_pilot.db")
JSONL_PATH = os.path.join(TELEMETRY_DIR, "field_pilot_logs.jsonl")
HMAC_SECRET = b"salm-rural-field-pilot-secret-2026"

class FieldPilotTelemetryLogger:
    def __init__(self, db_path: str = DB_PATH, jsonl_path: str = JSONL_PATH):
        self.db_path = db_path
        self.jsonl_path = jsonl_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS field_telemetry (
            session_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            officer_id TEXT NOT NULL,
            district_code TEXT NOT NULL,
            farmer_utterance TEXT NOT NULL,
            engine_used TEXT NOT NULL,
            fallback_triggered INTEGER NOT NULL,
            latency_ms REAL NOT NULL,
            top1_cause TEXT,
            status TEXT NOT NULL,
            officer_agreement TEXT,
            confirmed_cause TEXT,
            officer_notes TEXT,
            synced INTEGER DEFAULT 0,
            payload_json TEXT NOT NULL,
            signature TEXT NOT NULL
        )
        """)
        conn.commit()
        conn.close()

    def _generate_hmac(self, data_str: str) -> str:
        return hmac.new(HMAC_SECRET, data_str.encode("utf-8"), hashlib.sha256).hexdigest()

    def log_session(
        self,
        officer_id: str,
        district_code: str,
        farmer_utterance: str,
        diagnostic_result: Dict[str, Any],
        officer_agreement: Optional[str] = None,
        confirmed_cause: Optional[str] = None,
        officer_notes: Optional[str] = None
    ) -> str:
        session_id = str(uuid.uuid4())
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        payload = diagnostic_result["diagnostic_payload"]
        
        diff = payload.get("differential", [])
        top1_cause = diff[0]["cause_id"] if diff and isinstance(diff[0], dict) else None
        status = payload.get("status", "unknown")

        record = {
            "session_id": session_id,
            "timestamp": ts,
            "officer_id": officer_id,
            "district_code": district_code,
            "farmer_utterance": farmer_utterance,
            "engine_used": diagnostic_result["engine_used"],
            "fallback_triggered": 1 if diagnostic_result["fallback_triggered"] else 0,
            "latency_ms": diagnostic_result["latency_ms"],
            "top1_cause": top1_cause,
            "status": status,
            "officer_agreement": officer_agreement or "pending_review",
            "confirmed_cause": confirmed_cause or "",
            "officer_notes": officer_notes or "",
            "diagnostic_payload": payload
        }

        record_sig = self._generate_hmac(json.dumps(record, sort_keys=True))
        record["signature"] = record_sig

        # 1. Write to SQLite
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO field_telemetry 
            (session_id, timestamp, officer_id, district_code, farmer_utterance, engine_used, 
             fallback_triggered, latency_ms, top1_cause, status, officer_agreement, confirmed_cause, officer_notes, synced, payload_json, signature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            session_id, ts, officer_id, district_code, farmer_utterance,
            record["engine_used"], record["fallback_triggered"], record["latency_ms"],
            top1_cause, status, record["officer_agreement"], record["confirmed_cause"],
            record["officer_notes"], json.dumps(payload), record_sig
        ))
        conn.commit()
        conn.close()

        # 2. Append to JSONL log
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return session_id
