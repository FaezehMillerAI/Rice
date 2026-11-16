"""
engine/scenario_manager.py
Rice Pathogen SALM — Multi-User OneDrive Scenario Synchronization & Merge Engine
================================================================================
Enables Ginny, Aseel, Faezeh, and Richard to:
  1. Modify, verify, and add scenarios from the interactive web dashboard.
  2. Automatically write every change directly to the live OneDrive Excel workbook
     (`rice_slm_diagnostic_scenarios_completed.xlsx`).
  3. Collaborate simultaneously (on the same server OR across separate computers
     connected via OneDrive) WITHOUT overwriting each other's changes:
     - Field-level 3-way merge + Optimistic Concurrency Control (HTTP 409 on true
       same-field collisions with interactive merge resolution).
     - Append-only immutable event journal inside OneDrive (`.rice_sync/events/`),
       so concurrent edits/additions on two laptops never get clobbered.
     - Hidden `_SyncMeta` sheet inside the `.xlsx` to track applied events,
       `client_uid -> scenario_id` mappings, and manual Excel direct-edit detection.
     - Automatic detection & merging of OneDrive conflict `.xlsx` copies.
"""

import os
import sys
import json
import glob
import time
import uuid
import socket
import shutil
import hashlib
import threading
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

LOCAL_FALLBACK_XLSX = os.path.join(
    WORKSPACE_ROOT, "Scenarios/OneDrive_1_23-10-2026/rice_slm_diagnostic_scenarios_completed.xlsx"
)
DESKTOP_PKG_DIR = "/Users/faezeh/Desktop/Rice_SLM_Scenarios_Package"

_PROCESS_LOCK = threading.RLock()
_SYNC_META_SHEET = "_SyncMeta"
_META_CHUNK_SIZE = 25000
_LOCK_TTL_SECONDS = 20.0
_LOCK_WAIT_SECONDS = 8.0

FIELD_LABELS = {
    "track": "Track Split",
    "focus_disease": "Focus Disease",
    "owner": "Owner",
    "seed_idea": "Seed Idea",
    "growth_stage_id": "Growth Stage",
    "status": "Clinical Behavior / Status",
    "user_input": "Farmer Field Observation",
    "observations": "Clinical Observations",
    "differential": "Differential Causes",
    "acceptable_differential": "Acceptable Differential",
    "required_questions": "Ask-First Questions",
    "actions": "Cultural IPM Actions",
    "escalation_required": "Escalation Required",
    "user_response": "Advisor Response to Farmer",
    "evidence_fact_ids": "Cited Grounding Facts",
    "review_status": "Review Status",
    "peer_checker": "Reviewer / Peer Checker",
    "peer_notes": "Reviewer Notes",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _machine_id() -> str:
    return socket.gethostname() or "unknown-host"


def is_onedrive_path(path: str) -> bool:
    low = (path or "").lower()
    return ("onedrive" in low) or ("cloudstorage" in low)


def resolve_workbook_paths() -> Tuple[str, List[str]]:
    """Returns (primary_xlsx, mirror_xlsx_list), prioritizing live OneDrive."""
    candidates: List[str] = []

    env_path = os.environ.get("RICE_WORKBOOK_PATH", "").strip()
    if env_path:
        candidates.append(os.path.abspath(env_path))

    cfg_file = os.path.join(WORKSPACE_ROOT, "sync_config.json")
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as cf:
                cfg_path = json.load(cf).get("workbook_path", "").strip()
            if cfg_path:
                candidates.append(os.path.abspath(cfg_path))
        except Exception:
            pass

    # If demo_app is run directly inside OneDrive Rice SLM folder
    root_xlsx = os.path.join(WORKSPACE_ROOT, "rice_slm_diagnostic_scenarios_completed.xlsx")
    if os.path.exists(root_xlsx):
        candidates.append(root_xlsx)

    # Cross-platform live OneDrive discovery (macOS CloudStorage & Windows/macOS home OneDrive)
    onedrive_patterns = [
        "/Users/faezeh/Library/CloudStorage/OneDrive-UniversityofExeter/Rice SLM/rice_slm_diagnostic_scenarios_completed.xlsx",
        os.path.expanduser("~/Library/CloudStorage/OneDrive*/Rice SLM/rice_slm_diagnostic_scenarios_completed.xlsx"),
        os.path.expanduser("~/Library/CloudStorage/OneDrive*/*/Rice SLM/rice_slm_diagnostic_scenarios_completed.xlsx"),
        os.path.expanduser("~/OneDrive*/Rice SLM/rice_slm_diagnostic_scenarios_completed.xlsx"),
        os.path.expanduser("~/OneDrive*/*/Rice SLM/rice_slm_diagnostic_scenarios_completed.xlsx"),
    ]
    for pat in onedrive_patterns:
        if "*" in pat:
            candidates.extend(sorted(glob.glob(pat)))
        elif os.path.exists(pat):
            candidates.append(pat)

    if os.path.exists(LOCAL_FALLBACK_XLSX):
        candidates.append(LOCAL_FALLBACK_XLSX)

    deduped: List[str] = []
    for p in candidates:
        ap = os.path.abspath(p)
        if os.path.exists(ap) and ap not in deduped:
            deduped.append(ap)

    primary = deduped[0] if deduped else LOCAL_FALLBACK_XLSX
    mirrors: List[str] = []
    for m in [LOCAL_FALLBACK_XLSX, root_xlsx]:
        am = os.path.abspath(m)
        if am != os.path.abspath(primary) and os.path.exists(os.path.dirname(am)):
            if m == root_xlsx and not os.path.exists(root_xlsx):
                continue
            if am not in mirrors:
                mirrors.append(am)

    return primary, mirrors


def get_sync_dirs(primary_xlsx: Optional[str] = None) -> Dict[str, str]:
    wb_path = primary_xlsx or resolve_workbook_paths()[0]
    base_dir = os.path.dirname(wb_path)
    sync_dir = os.path.join(base_dir, ".rice_sync")
    return {
        "base_dir": base_dir,
        "sync_dir": sync_dir,
        "events_dir": os.path.join(sync_dir, "events"),
        "backups_dir": os.path.join(sync_dir, "backups"),
        "conflicts_dir": os.path.join(sync_dir, "conflicts_resolved"),
        "lock_file": os.path.join(sync_dir, "lock.json"),
    }


def _ensure_sync_dirs(primary_xlsx: str) -> Dict[str, str]:
    dirs = get_sync_dirs(primary_xlsx)
    for k in ("sync_dir", "events_dir", "backups_dir", "conflicts_dir"):
        os.makedirs(dirs[k], exist_ok=True)
    return dirs


@contextmanager
def _acquire_onedrive_lock(primary_xlsx: str, actor: str = "system"):
    """Thread lock + cooperative OneDrive file lease lock."""
    with _PROCESS_LOCK:
        dirs = _ensure_sync_dirs(primary_xlsx)
        lock_file = dirs["lock_file"]
        token = f"{_machine_id()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        deadline = time.time() + _LOCK_WAIT_SECONDS

        while True:
            now = time.time()
            can_claim = True
            if os.path.exists(lock_file):
                try:
                    with open(lock_file, "r", encoding="utf-8") as lf:
                        info = json.load(lf)
                    age = now - float(info.get("epoch", 0))
                    if age < _LOCK_TTL_SECONDS and info.get("token") != token:
                        can_claim = False
                except Exception:
                    can_claim = True

            if can_claim or now >= deadline:
                try:
                    with open(lock_file, "w", encoding="utf-8") as lf:
                        json.dump({
                            "token": token,
                            "actor": actor,
                            "machine": _machine_id(),
                            "epoch": now,
                            "timestamp": _now_iso(),
                        }, lf)
                except Exception:
                    pass
                break
            time.sleep(0.25)

        try:
            yield dirs
        finally:
            try:
                if os.path.exists(lock_file):
                    with open(lock_file, "r", encoding="utf-8") as lf:
                        info = json.load(lf)
                    if info.get("token") == token:
                        os.remove(lock_file)
            except Exception:
                pass


def normalize_sid(sid: str) -> str:
    sid = str(sid or "").strip()
    if sid.startswith("SCN-"):
        num_part = sid[4:]
        if num_part.isdigit():
            return f"SCN-{int(num_part):06d}"
    return sid


def format_excel_sid(sid: str) -> str:
    sid = normalize_sid(sid)
    if sid.startswith("SCN-") and sid[4:].isdigit():
        num = int(sid[4:])
        return f"SCN-{num:03d}"
    return sid


def _parse_split_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    import re
    return [x.strip() for x in re.split(r"[,;\n\r]+", str(val)) if x.strip()]


def _parse_observations(val: Any) -> List[Dict[str, str]]:
    if not val:
        return []
    if isinstance(val, list):
        out = []
        for item in val:
            if isinstance(item, dict):
                cid = str(item.get("concept_id", "")).strip()
                st = str(item.get("state", "PRESENT")).strip().upper() or "PRESENT"
                if cid:
                    out.append({"concept_id": cid, "state": st})
            elif str(item).strip():
                text = str(item).strip()
                if "=" in text:
                    c, s = text.split("=", 1)
                    out.append({"concept_id": c.strip(), "state": s.strip().upper()})
                else:
                    out.append({"concept_id": text, "state": "PRESENT"})
        return out

    import re
    out = []
    for line in re.split(r"[\n\r;]+", str(val)):
        line = line.strip()
        if not line:
            continue
        if "=" in line:
            c, s = line.split("=", 1)
            out.append({"concept_id": c.strip(), "state": s.strip().upper()})
        else:
            out.append({"concept_id": line, "state": "PRESENT"})
    return out


def _normalize_field_value(field: str, val: Any) -> Any:
    if field == "observations":
        return _parse_observations(val)
    if field in ("differential", "acceptable_differential", "required_questions", "actions", "evidence_fact_ids"):
        return _parse_split_list(val)
    if field == "escalation_required":
        if isinstance(val, bool):
            return val
        return str(val or "").strip().upper() in ("Y", "YES", "TRUE", "1")
    if field == "status":
        return str(val or "").strip().upper()
    return str(val or "").strip()


def _row_to_fields(sheet, row_idx: int) -> Dict[str, Any]:
    raw_esc = str(sheet.cell(row_idx, 25).value or "").strip().upper()
    diff = _parse_split_list(sheet.cell(row_idx, 19).value)
    adiff = _parse_split_list(sheet.cell(row_idx, 20).value) or diff
    return {
        "track": str(sheet.cell(row_idx, 2).value or "").strip(),
        "owner": str(sheet.cell(row_idx, 3).value or "").strip(),
        "focus_disease": str(sheet.cell(row_idx, 8).value or "").strip(),
        "seed_idea": str(sheet.cell(row_idx, 10).value or "").strip(),
        "growth_stage_id": str(sheet.cell(row_idx, 13).value or "").strip(),
        "user_input": str(sheet.cell(row_idx, 16).value or "").strip(),
        "status": str(sheet.cell(row_idx, 17).value or sheet.cell(row_idx, 9).value or "").strip().upper(),
        "observations": _parse_observations(sheet.cell(row_idx, 18).value),
        "differential": diff,
        "acceptable_differential": adiff,
        "required_questions": _parse_split_list(sheet.cell(row_idx, 22).value),
        "actions": _parse_split_list(sheet.cell(row_idx, 24).value),
        "escalation_required": raw_esc in ("Y", "YES", "TRUE", "1"),
        "user_response": str(sheet.cell(row_idx, 28).value or "").strip(),
        "evidence_fact_ids": _parse_split_list(sheet.cell(row_idx, 29).value),
        "review_status": str(sheet.cell(row_idx, 34).value or "").strip(),
        "peer_checker": str(sheet.cell(row_idx, 35).value or "").strip(),
        "peer_notes": str(sheet.cell(row_idx, 36).value or "").strip(),
    }


def _apply_fields_to_row(sheet, row_idx: int, fields: Dict[str, Any]) -> None:
    if "track" in fields:
        sheet.cell(row_idx, 2, _normalize_field_value("track", fields["track"]))
    if "owner" in fields:
        sheet.cell(row_idx, 3, _normalize_field_value("owner", fields["owner"]))
    if "focus_disease" in fields:
        sheet.cell(row_idx, 8, _normalize_field_value("focus_disease", fields["focus_disease"]))
    if "seed_idea" in fields:
        sheet.cell(row_idx, 10, _normalize_field_value("seed_idea", fields["seed_idea"]))
    if "growth_stage_id" in fields:
        sheet.cell(row_idx, 13, _normalize_field_value("growth_stage_id", fields["growth_stage_id"]))
    if "user_input" in fields:
        sheet.cell(row_idx, 16, _normalize_field_value("user_input", fields["user_input"]))
    if "status" in fields:
        st = _normalize_field_value("status", fields["status"])
        sheet.cell(row_idx, 17, st)
    if "observations" in fields:
        obs_list = _normalize_field_value("observations", fields["observations"])
        obs_str = "\n".join(f"{o['concept_id']} = {o.get('state', 'PRESENT')}" for o in obs_list)
        sheet.cell(row_idx, 18, obs_str)
    if "differential" in fields:
        diff_list = _normalize_field_value("differential", fields["differential"])
        sheet.cell(row_idx, 19, "; ".join(diff_list))
    if "acceptable_differential" in fields:
        adiff_list = _normalize_field_value("acceptable_differential", fields["acceptable_differential"])
        sheet.cell(row_idx, 20, "; ".join(adiff_list))
    if "required_questions" in fields:
        rq_list = _normalize_field_value("required_questions", fields["required_questions"])
        sheet.cell(row_idx, 22, "; ".join(rq_list))
    if "actions" in fields:
        act_list = _normalize_field_value("actions", fields["actions"])
        sheet.cell(row_idx, 24, "; ".join(act_list))
    if "escalation_required" in fields:
        esc = "Y" if _normalize_field_value("escalation_required", fields["escalation_required"]) else "N"
        sheet.cell(row_idx, 25, esc)
    if "user_response" in fields:
        sheet.cell(row_idx, 28, _normalize_field_value("user_response", fields["user_response"]))
    if "evidence_fact_ids" in fields:
        ef_list = _normalize_field_value("evidence_fact_ids", fields["evidence_fact_ids"])
        sheet.cell(row_idx, 29, ", ".join(ef_list))
    if "review_status" in fields:
        sheet.cell(row_idx, 34, _normalize_field_value("review_status", fields["review_status"]))
    if "peer_checker" in fields:
        sheet.cell(row_idx, 35, _normalize_field_value("peer_checker", fields["peer_checker"]))
    if "peer_notes" in fields:
        sheet.cell(row_idx, 36, _normalize_field_value("peer_notes", fields["peer_notes"]))


def _fields_hash(fields: Dict[str, Any]) -> str:
    payload = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _read_sync_meta(wb) -> Dict[str, Any]:
    default_meta = {
        "revision": 1,
        "applied_event_ids": [],
        "client_uid_map": {},
        "row_snapshots": {},
        "last_sync_at": _now_iso(),
    }
    if _SYNC_META_SHEET not in wb.sheetnames:
        return default_meta
    ws = wb[_SYNC_META_SHEET]
    chunks = []
    for r in range(1, ws.max_row + 1):
        val = ws.cell(r, 1).value
        if val is not None:
            chunks.append(str(val))
    raw = "".join(chunks).strip()
    if not raw:
        return default_meta
    try:
        parsed = json.loads(raw)
        for k, v in default_meta.items():
            parsed.setdefault(k, v)
        return parsed
    except Exception:
        return default_meta


def _write_sync_meta(wb, meta: Dict[str, Any]) -> None:
    if _SYNC_META_SHEET in wb.sheetnames:
        ws = wb[_SYNC_META_SHEET]
        ws.delete_rows(1, ws.max_row + 1)
    else:
        ws = wb.create_sheet(title=_SYNC_META_SHEET)
    ws.sheet_state = "hidden"
    raw = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    chunks = [raw[i:i + _META_CHUNK_SIZE] for i in range(0, len(raw), _META_CHUNK_SIZE)] or ["{}"]
    for idx, ch in enumerate(chunks, 1):
        ws.cell(idx, 1, ch)


def _find_scenario_row(sheet, scenario_id: str) -> Optional[int]:
    target_sid = normalize_sid(scenario_id)
    alt_sid = format_excel_sid(scenario_id)
    for r in range(3, sheet.max_row + 1):
        cell_val = str(sheet.cell(r, 1).value or "").strip()
        if cell_val in (target_sid, alt_sid, scenario_id):
            return r
    return None


def _next_scenario_id_and_row(sheet) -> Tuple[int, str, str, int]:
    max_num = 0
    last_non_empty_row = 2
    for r in range(3, sheet.max_row + 1):
        val = str(sheet.cell(r, 1).value or "").strip()
        if val:
            last_non_empty_row = r
        if val.startswith("SCN-"):
            num_part = val[4:]
            if num_part.isdigit():
                max_num = max(max_num, int(num_part))
    next_num = max_num + 1
    return next_num, f"SCN-{next_num:03d}", f"SCN-{next_num:06d}", last_non_empty_row + 1


def _detect_manual_excel_edits(sheet, meta: Dict[str, Any]) -> int:
    """Detects rows edited directly in Excel Desktop/Web and updates row_snapshots."""
    snapshots = meta.setdefault("row_snapshots", {})
    changes = 0
    for r in range(3, sheet.max_row + 1):
        raw_sid = str(sheet.cell(r, 1).value or "").strip()
        if not raw_sid:
            continue
        sid = normalize_sid(raw_sid)
        cur_fields = _row_to_fields(sheet, r)
        snap = snapshots.get(sid)
        if snap is None:
            snapshots[sid] = {
                "version": 1,
                "updated_by": cur_fields.get("peer_checker") or cur_fields.get("owner") or "Workbook",
                "updated_at": _now_iso(),
                "fields": cur_fields,
            }
        elif snap.get("fields") != cur_fields:
            snap["version"] = int(snap.get("version", 1)) + 1
            snap["updated_by"] = "Excel Direct Edit"
            snap["updated_at"] = _now_iso()
            snap["fields"] = cur_fields
            changes += 1
    if changes > 0:
        meta["revision"] = int(meta.get("revision", 1)) + changes
    return changes


def _write_event_file(events_dir: str, event: Dict[str, Any]) -> str:
    os.makedirs(events_dir, exist_ok=True)
    ts_safe = event["timestamp"].replace(":", "").replace("-", "")
    actor_safe = "".join(ch for ch in str(event.get("actor", "user")) if ch.isalnum()) or "user"
    fname = f"{ts_safe}_{actor_safe}_{event['event_id']}.json"
    fpath = os.path.join(events_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(event, f, ensure_ascii=False, indent=2)
    return fpath


def _load_all_events(events_dir: str) -> List[Dict[str, Any]]:
    if not os.path.exists(events_dir):
        return []
    events = []
    for fname in sorted(os.listdir(events_dir)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(events_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                ev = json.load(f)
            if "event_id" in ev:
                events.append(ev)
        except Exception:
            continue
    events.sort(key=lambda e: (e.get("timestamp", ""), e.get("event_id", "")))
    return events


def _merge_conflict_copies(wb, meta: Dict[str, Any], primary_xlsx: str, conflicts_dir: str) -> int:
    """Detects OneDrive conflict copies of the workbook, merges unseen edits/rows, and archives them."""
    import openpyxl

    base_dir = os.path.dirname(primary_xlsx)
    canon_name = os.path.basename(primary_xlsx)
    stem = os.path.splitext(canon_name)[0]
    merged_count = 0

    try:
        entries = os.listdir(base_dir)
    except Exception:
        return 0

    sheet = wb["Scenarios"]
    snapshots = meta.setdefault("row_snapshots", {})

    for fname in sorted(entries):
        if fname == canon_name or not fname.endswith(".xlsx") or fname.startswith("~$"):
            continue
        if not fname.startswith(stem):
            continue
        conflict_path = os.path.join(base_dir, fname)
        try:
            c_wb = openpyxl.load_workbook(conflict_path)
            if "Scenarios" not in c_wb.sheetnames:
                continue
            c_sheet = c_wb["Scenarios"]
            c_meta = _read_sync_meta(c_wb)
            c_snaps = c_meta.get("row_snapshots", {})

            for r in range(3, c_sheet.max_row + 1):
                raw_sid = str(c_sheet.cell(r, 1).value or "").strip()
                if not raw_sid:
                    continue
                sid = normalize_sid(raw_sid)
                c_fields = _row_to_fields(c_sheet, r)
                existing_row = _find_scenario_row(sheet, sid)

                if existing_row is None:
                    # New scenario added in the conflict copy -> append it!
                    _, new_excel_sid, new_canon_sid, new_row = _next_scenario_id_and_row(sheet)
                    sheet.cell(new_row, 1, new_excel_sid)
                    sheet.cell(new_row, 4, "English")
                    sheet.cell(new_row, 5, f"SCN-FAMILY-{new_canon_sid[4:]}")
                    sheet.cell(new_row, 6, "Merged from OneDrive Conflict Copy")
                    _apply_fields_to_row(sheet, new_row, c_fields)
                    snapshots[new_canon_sid] = {
                        "version": 1,
                        "updated_by": c_snaps.get(sid, {}).get("updated_by", "OneDrive Merge"),
                        "updated_at": _now_iso(),
                        "fields": _row_to_fields(sheet, new_row),
                    }
                    merged_count += 1
                else:
                    cur_fields = _row_to_fields(sheet, existing_row)
                    base_fields = snapshots.get(sid, {}).get("fields", {})
                    c_base_fields = c_snaps.get(sid, {}).get("fields", base_fields)
                    to_apply = {}
                    for fld, c_val in c_fields.items():
                        cur_val = cur_fields.get(fld)
                        if c_val != cur_val:
                            # Conflict copy changed this field relative to its base, and primary didn't
                            if cur_val == base_fields.get(fld) and c_val != c_base_fields.get(fld):
                                to_apply[fld] = c_val
                    if to_apply:
                        _apply_fields_to_row(sheet, existing_row, to_apply)
                        snapshots[sid] = {
                            "version": int(snapshots.get(sid, {}).get("version", 1)) + 1,
                            "updated_by": c_snaps.get(sid, {}).get("updated_by", "OneDrive Merge"),
                            "updated_at": _now_iso(),
                            "fields": _row_to_fields(sheet, existing_row),
                        }
                        merged_count += 1

            os.makedirs(conflicts_dir, exist_ok=True)
            archived_name = f"{_now_iso().replace(':', '')}_{fname}"
            shutil.move(conflict_path, os.path.join(conflicts_dir, archived_name))
        except Exception:
            continue

    if merged_count > 0:
        meta["revision"] = int(meta.get("revision", 1)) + merged_count
    return merged_count


def _replay_pending_events(wb, meta: Dict[str, Any], events_dir: str) -> int:
    """Replays immutable OneDrive event files not yet applied to this workbook."""
    events = _load_all_events(events_dir)
    if not events:
        return 0

    applied = set(meta.get("applied_event_ids", []))
    client_uid_map = meta.setdefault("client_uid_map", {})
    snapshots = meta.setdefault("row_snapshots", {})
    sheet = wb["Scenarios"]
    replayed = 0

    for ev in events:
        eid = ev.get("event_id")
        if not eid or eid in applied:
            continue

        op = ev.get("op")
        actor = ev.get("actor", "Collaborator")
        ts = ev.get("timestamp", _now_iso())

        if op == "verify":
            sid = normalize_sid(ev.get("scenario_id", ""))
            row_idx = _find_scenario_row(sheet, sid)
            if row_idx:
                changes = {
                    "review_status": ev.get("review_status", "Done"),
                    "peer_checker": ev.get("peer_checker", actor),
                    "peer_notes": ev.get("peer_notes", "Verified and signed off"),
                }
                _apply_fields_to_row(sheet, row_idx, changes)
                snap = snapshots.setdefault(sid, {"version": 0, "fields": {}})
                snap["version"] = int(snap.get("version", 1)) + 1
                snap["updated_by"] = actor
                snap["updated_at"] = ts
                snap["fields"] = _row_to_fields(sheet, row_idx)
                replayed += 1

        elif op == "update":
            sid = normalize_sid(ev.get("scenario_id", ""))
            row_idx = _find_scenario_row(sheet, sid)
            if row_idx:
                changed_fields = ev.get("changed_fields", {})
                base_fields = ev.get("base_fields", {})
                cur_fields = _row_to_fields(sheet, row_idx)
                to_apply = {}
                for fld, new_val in changed_fields.items():
                    norm_new = _normalize_field_value(fld, new_val)
                    cur_val = cur_fields.get(fld)
                    base_val = _normalize_field_value(fld, base_fields[fld]) if fld in base_fields else cur_val
                    # Apply if current wasn't modified differently, OR event is newer than current snapshot
                    if cur_val == base_val or cur_val == norm_new or ts >= snapshots.get(sid, {}).get("updated_at", ""):
                        to_apply[fld] = norm_new
                if to_apply:
                    _apply_fields_to_row(sheet, row_idx, to_apply)
                    snap = snapshots.setdefault(sid, {"version": 0, "fields": {}})
                    snap["version"] = int(snap.get("version", 1)) + 1
                    snap["updated_by"] = actor
                    snap["updated_at"] = ts
                    snap["fields"] = _row_to_fields(sheet, row_idx)
                    replayed += 1

        elif op == "add":
            cuid = ev.get("client_uid")
            if cuid and cuid in client_uid_map:
                applied.add(eid)
                continue
            fields = ev.get("fields", {})
            next_num, new_excel_sid, new_canon_sid, new_row = _next_scenario_id_and_row(sheet)
            _populate_new_row(sheet, new_row, next_num, new_excel_sid, fields)
            if cuid:
                client_uid_map[cuid] = new_canon_sid
            snapshots[new_canon_sid] = {
                "version": 1,
                "updated_by": actor,
                "updated_at": ts,
                "fields": _row_to_fields(sheet, new_row),
            }
            replayed += 1

        applied.add(eid)

    meta["applied_event_ids"] = list(applied)[-5000:]
    if replayed > 0:
        meta["revision"] = int(meta.get("revision", 1)) + replayed
    return replayed


def _populate_new_row(sheet, new_row: int, next_num: int, new_excel_sid: str, data: Dict[str, Any]) -> None:
    track = data.get("track", "Human (gold test)")
    disease = data.get("focus_disease", "Rice blast")
    owner = data.get("owner") or ("Ginny" if "bacterial" in str(disease).lower() or "sheath" in str(disease).lower() else "Aseel")
    status = str(data.get("status", "ANSWER")).strip().upper() or "ANSWER"
    seed_idea = data.get("seed_idea") or str(data.get("user_input", ""))[:80]

    sheet.cell(new_row, 1, new_excel_sid)
    sheet.cell(new_row, 2, track)
    sheet.cell(new_row, 3, owner)
    sheet.cell(new_row, 4, "English")
    sheet.cell(new_row, 5, f"SCN-FAMILY-{next_num:03d}")
    sheet.cell(new_row, 6, "New Addition")
    sheet.cell(new_row, 7, "Direct" if status == "ANSWER" else ("Clarification" if status == "ASK" else "Escalation"))
    sheet.cell(new_row, 8, disease)
    sheet.cell(new_row, 9, status)
    sheet.cell(new_row, 10, seed_idea)

    fields_to_write = {
        "growth_stage_id": data.get("growth_stage_id", "growth_stage:tillering"),
        "user_input": data.get("user_input", ""),
        "status": status,
        "observations": data.get("observations", []),
        "differential": data.get("differential", []),
        "acceptable_differential": data.get("acceptable_differential", data.get("differential", [])),
        "required_questions": data.get("required_questions", []),
        "actions": data.get("actions", []),
        "escalation_required": data.get("escalation_required", status == "ESCALATE"),
        "user_response": data.get("user_response", ""),
        "evidence_fact_ids": data.get("evidence_fact_ids", data.get("grounding", [])),
        "review_status": data.get("review_status", "Done" if "Human" in track else "Draft"),
        "peer_checker": data.get("peer_checker", owner),
        "peer_notes": data.get("peer_notes", "Added via interactive dashboard"),
    }
    _apply_fields_to_row(sheet, new_row, fields_to_write)


def _save_workbook_safely(wb, primary_xlsx: str, mirror_xlsx_list: List[str], backups_dir: str) -> None:
    os.makedirs(backups_dir, exist_ok=True)
    if os.path.exists(primary_xlsx):
        ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        bak_path = os.path.join(backups_dir, f"backup_{ts_tag}.xlsx")
        try:
            shutil.copy2(primary_xlsx, bak_path)
            baks = sorted(glob.glob(os.path.join(backups_dir, "backup_*.xlsx")))
            for old in baks[:-15]:
                os.remove(old)
        except Exception:
            pass

    wb.save(primary_xlsx)

    for m_path in mirror_xlsx_list:
        try:
            os.makedirs(os.path.dirname(m_path), exist_ok=True)
            shutil.copy2(primary_xlsx, m_path)
        except Exception:
            pass


def run_revalidation_and_sync(primary_xlsx: Optional[str] = None) -> None:
    """Exports JSONL + validation report + rebuilds dashboard + syncs OneDrive & Desktop packages."""
    wb_path, _ = resolve_workbook_paths()
    target_wb = primary_xlsx or wb_path

    # 1. Run process_scenarios_workbook.py in-process
    try:
        from scripts.process_scenarios_workbook import process_and_export
        process_and_export(workbook_path=target_wb)
    except Exception as exc:
        print(f"[Sync Warning] process_and_export failed: {exc}")

    # 2. Rebuild demo_dashboard.html in-process
    try:
        from scripts.build_demo_dashboard import build_dashboard
        build_dashboard()
    except Exception as exc:
        print(f"[Sync Warning] build_dashboard failed: {exc}")

    # 3. Mirror updated artifacts into OneDrive folder (so colleagues running from OneDrive stay current)
    onedrive_dir = os.path.dirname(target_wb)
    if os.path.abspath(onedrive_dir) != os.path.abspath(WORKSPACE_ROOT) and is_onedrive_path(target_wb):
        for rel in [
            "data/scenarios/workbook_scenarios_v0.2.jsonl",
            "data/scenarios/richard_facts_839.json",
            "data/scenarios/richard_facts_842.json",
            "data/scenarios/validation_report.md",
            "demo_dashboard.html",
            "demo_app.py",
            "vis-network.min.js",
        ]:
            src = os.path.join(WORKSPACE_ROOT, rel)
            if os.path.exists(src):
                dst = os.path.join(onedrive_dir, os.path.basename(rel))
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass
        # Also mirror engine/ and scripts/ into OneDrive folder so `python3 demo_app.py` works directly inside OneDrive
        engine_src_dir = os.path.join(WORKSPACE_ROOT, "engine")
        if os.path.isdir(engine_src_dir):
            for fname in os.listdir(engine_src_dir):
                if fname.endswith(".py"):
                    src = os.path.join(engine_src_dir, fname)
                    dst = os.path.join(onedrive_dir, "engine", fname)
                    try:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                    except Exception:
                        pass
        for sub in ["scripts/process_scenarios_workbook.py", "scripts/build_demo_dashboard.py"]:
            src = os.path.join(WORKSPACE_ROOT, sub)
            dst = os.path.join(onedrive_dir, sub)
            if os.path.exists(src):
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                except Exception:
                    pass
        proc_src = os.path.join(WORKSPACE_ROOT, "scripts/process_scenarios_workbook.py")
        if os.path.exists(proc_src):
            try:
                shutil.copy2(proc_src, os.path.join(onedrive_dir, "process_scenarios_workbook.py"))
            except Exception:
                pass

    # 4. Synchronize Desktop Package if present
    if os.path.exists(DESKTOP_PKG_DIR):
        for rel in [
            "data/scenarios/workbook_scenarios_v0.2.jsonl",
            "data/scenarios/richard_facts_839.json",
            "data/scenarios/richard_facts_842.json",
            "data/scenarios/validation_report.md",
            "demo_dashboard.html",
            "demo_app.py",
            "demo_rice_slm.py",
            "diagnose.py",
            "vis-network.min.js",
        ]:
            src = os.path.join(WORKSPACE_ROOT, rel)
            if os.path.exists(src):
                try:
                    shutil.copy2(src, os.path.join(DESKTOP_PKG_DIR, os.path.basename(rel)))
                except Exception:
                    pass
        try:
            shutil.copy2(target_wb, os.path.join(DESKTOP_PKG_DIR, os.path.basename(target_wb)))
        except Exception:
            pass


def sync_workbook_and_state(actor: str = "SyncCheck", force_export: bool = False) -> Dict[str, Any]:
    """Replays OneDrive events, merges conflict copies, detects manual Excel edits, and updates JSONL if changed."""
    import openpyxl

    primary_xlsx, mirrors = resolve_workbook_paths()
    with _acquire_onedrive_lock(primary_xlsx, actor=actor) as dirs:
        if not os.path.exists(primary_xlsx):
            return {"success": False, "error": f"Workbook not found at {primary_xlsx}"}

        wb = openpyxl.load_workbook(primary_xlsx)
        sheet = wb["Scenarios"]
        meta = _read_sync_meta(wb)

        had_meta_sheet = _SYNC_META_SHEET in wb.sheetnames
        manual_edits = _detect_manual_excel_edits(sheet, meta)
        conflict_merges = _merge_conflict_copies(wb, meta, primary_xlsx, dirs["conflicts_dir"])
        replayed_events = _replay_pending_events(wb, meta, dirs["events_dir"])

        changed = (manual_edits > 0) or (conflict_merges > 0) or (replayed_events > 0) or (not had_meta_sheet)
        if changed:
            meta["last_sync_at"] = _now_iso()
            _write_sync_meta(wb, meta)
            _save_workbook_safely(wb, primary_xlsx, mirrors, dirs["backups_dir"])

        if changed or force_export:
            run_revalidation_and_sync(primary_xlsx)

        return {
            "success": True,
            "workbook_path": primary_xlsx,
            "is_onedrive": is_onedrive_path(primary_xlsx),
            "revision": meta.get("revision", 1),
            "manual_edits_detected": manual_edits,
            "conflict_merges": conflict_merges,
            "replayed_events": replayed_events,
            "last_sync_at": meta.get("last_sync_at"),
            "workbook_mtime": os.path.getmtime(primary_xlsx),
        }


def get_sync_status() -> Dict[str, Any]:
    """Lightweight status for polling (checks file mtime & pending events)."""
    primary_xlsx, _ = resolve_workbook_paths()
    dirs = get_sync_dirs(primary_xlsx)
    mtime = os.path.getmtime(primary_xlsx) if os.path.exists(primary_xlsx) else 0
    event_files = []
    if os.path.exists(dirs["events_dir"]):
        event_files = sorted(f for f in os.listdir(dirs["events_dir"]) if f.endswith(".json"))

    # Read JSONL scenario count fast
    jsonl_path = os.path.join(WORKSPACE_ROOT, "data/scenarios/workbook_scenarios_v0.2.jsonl")
    if not os.path.exists(jsonl_path):
        jsonl_path = os.path.join(WORKSPACE_ROOT, "workbook_scenarios_v0.2.jsonl")
    scn_count = 0
    if os.path.exists(jsonl_path):
        with open(jsonl_path, "r", encoding="utf-8") as f:
            scn_count = sum(1 for line in f if line.strip())

    recent_events = []
    for fname in event_files[-15:][::-1]:
        try:
            with open(os.path.join(dirs["events_dir"], fname), "r", encoding="utf-8") as ef:
                ev = json.load(ef)
            recent_events.append({
                "event_id": ev.get("event_id"),
                "op": ev.get("op"),
                "scenario_id": ev.get("scenario_id"),
                "actor": ev.get("actor"),
                "machine": ev.get("machine"),
                "timestamp": ev.get("timestamp"),
                "fields": list((ev.get("changed_fields") or {}).keys()) if ev.get("op") == "update" else [],
            })
        except Exception:
            continue

    revision_sig = f"{int(mtime * 1000)}:{len(event_files)}:{scn_count}"
    return {
        "status": "running",
        "excel_sync": True,
        "workbook_path": primary_xlsx,
        "onedrive_dir": os.path.dirname(primary_xlsx),
        "is_onedrive": is_onedrive_path(primary_xlsx),
        "workbook_mtime": mtime,
        "event_count": len(event_files),
        "scenario_count": scn_count,
        "revision": revision_sig,
        "recent_events": recent_events,
    }


def list_scenarios_live() -> Dict[str, Any]:
    """Ensures workbook is synced with OneDrive events/edits, then returns enriched scenarios + sync_meta."""
    sync_info = sync_workbook_and_state(actor="Reader", force_export=False)

    jsonl_path = os.path.join(WORKSPACE_ROOT, "data/scenarios/workbook_scenarios_v0.2.jsonl")
    if not os.path.exists(jsonl_path):
        jsonl_path = os.path.join(WORKSPACE_ROOT, "workbook_scenarios_v0.2.jsonl")

    scenarios = []
    if os.path.exists(jsonl_path):
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    scenarios.append(json.loads(line))

    # Attach row_version & last_updated metadata from workbook _SyncMeta
    primary_xlsx, _ = resolve_workbook_paths()
    row_snapshots = {}
    if os.path.exists(primary_xlsx):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(primary_xlsx, read_only=True)
            if _SYNC_META_SHEET in wb.sheetnames:
                ws = wb[_SYNC_META_SHEET]
                chunks = [str(row[0]) for row in ws.iter_rows(values_only=True) if row and row[0] is not None]
                if chunks:
                    meta = json.loads("".join(chunks))
                    row_snapshots = meta.get("row_snapshots", {})
        except Exception:
            pass

    for s in scenarios:
        sid = s.get("scenario_id")
        snap = row_snapshots.get(sid, {})
        s["_sync"] = {
            "version": snap.get("version", 1),
            "updated_by": snap.get("updated_by", s.get("peer_checker") or s.get("owner") or ""),
            "updated_at": snap.get("updated_at", ""),
        }

    status = get_sync_status()
    status["sync_details"] = sync_info
    return {"scenarios": scenarios, "sync_meta": status}


def verify_scenario(
    scenario_id: str,
    reviewer: str = "Aseel",
    notes: str = "Verified and signed off as Human Gold Benchmark",
) -> Dict[str, Any]:
    """Sets review_status='Done', peer_checker, peer_notes in OneDrive Excel + journal, without touching other columns."""
    import openpyxl

    primary_xlsx, mirrors = resolve_workbook_paths()
    with _acquire_onedrive_lock(primary_xlsx, actor=reviewer) as dirs:
        wb = openpyxl.load_workbook(primary_xlsx)
        sheet = wb["Scenarios"]
        meta = _read_sync_meta(wb)

        _detect_manual_excel_edits(sheet, meta)
        _merge_conflict_copies(wb, meta, primary_xlsx, dirs["conflicts_dir"])
        _replay_pending_events(wb, meta, dirs["events_dir"])

        target_sid = normalize_sid(scenario_id)
        matched_row = _find_scenario_row(sheet, target_sid)
        if not matched_row:
            return {"success": False, "error": f"Scenario {scenario_id} not found in Excel sheet."}

        changes = {
            "review_status": "Done",
            "peer_checker": str(reviewer).strip(),
            "peer_notes": str(notes).strip(),
        }
        _apply_fields_to_row(sheet, matched_row, changes)

        event = {
            "event_id": uuid.uuid4().hex[:12],
            "op": "verify",
            "scenario_id": target_sid,
            "actor": reviewer,
            "machine": _machine_id(),
            "timestamp": _now_iso(),
            **changes,
        }
        _write_event_file(dirs["events_dir"], event)
        meta.setdefault("applied_event_ids", []).append(event["event_id"])

        snap = meta.setdefault("row_snapshots", {}).setdefault(target_sid, {"version": 0, "fields": {}})
        snap["version"] = int(snap.get("version", 1)) + 1
        snap["updated_by"] = reviewer
        snap["updated_at"] = event["timestamp"]
        snap["fields"] = _row_to_fields(sheet, matched_row)
        meta["revision"] = int(meta.get("revision", 1)) + 1
        meta["last_sync_at"] = event["timestamp"]

        _write_sync_meta(wb, meta)
        _save_workbook_safely(wb, primary_xlsx, mirrors, dirs["backups_dir"])
        run_revalidation_and_sync(primary_xlsx)

        return {
            "success": True,
            "scenario_id": target_sid,
            "row": matched_row,
            "review_status": "Done",
            "peer_checker": reviewer,
            "peer_notes": notes,
            "version": snap["version"],
            "workbook_path": primary_xlsx,
            "is_onedrive": is_onedrive_path(primary_xlsx),
        }


def update_scenario(data: Dict[str, Any]) -> Dict[str, Any]:
    """3-way field-level merge update into OneDrive Excel + event journal."""
    import openpyxl

    sid = data.get("scenario_id", "")
    target_sid = normalize_sid(sid)
    actor = str(data.get("actor") or data.get("peer_checker") or "Collaborator").strip()
    force_fields = set(data.get("force_fields") or [])
    base_snapshot = data.get("base_snapshot")
    incoming_changes = data.get("changes")

    # Backward compatibility: if caller sent flat payload instead of `changes`
    if incoming_changes is None:
        incoming_changes = {}
        for fld in FIELD_LABELS:
            if fld in data:
                incoming_changes[fld] = data[fld]

    primary_xlsx, mirrors = resolve_workbook_paths()
    with _acquire_onedrive_lock(primary_xlsx, actor=actor) as dirs:
        wb = openpyxl.load_workbook(primary_xlsx)
        sheet = wb["Scenarios"]
        meta = _read_sync_meta(wb)

        _detect_manual_excel_edits(sheet, meta)
        _merge_conflict_copies(wb, meta, primary_xlsx, dirs["conflicts_dir"])
        _replay_pending_events(wb, meta, dirs["events_dir"])

        matched_row = _find_scenario_row(sheet, target_sid)
        if not matched_row:
            return {"success": False, "error": f"Scenario {sid} not found in Excel sheet."}

        current_fields = _row_to_fields(sheet, matched_row)
        snap = meta.setdefault("row_snapshots", {}).setdefault(target_sid, {
            "version": 1,
            "updated_by": current_fields.get("peer_checker") or current_fields.get("owner") or "",
            "updated_at": _now_iso(),
            "fields": current_fields,
        })

        # 3-way field-level conflict check
        conflicts = []
        fields_to_apply: Dict[str, Any] = {}
        normalized_base: Dict[str, Any] = {}

        for fld, raw_new in incoming_changes.items():
            if fld not in FIELD_LABELS:
                continue
            new_val = _normalize_field_value(fld, raw_new)
            cur_val = current_fields.get(fld)

            if base_snapshot and fld in base_snapshot:
                base_val = _normalize_field_value(fld, base_snapshot[fld])
                normalized_base[fld] = base_val
                if new_val == base_val:
                    continue  # User did not actually change this field -> preserve current!
                if cur_val != base_val and cur_val != new_val and fld not in force_fields:
                    conflicts.append({
                        "field": fld,
                        "label": FIELD_LABELS.get(fld, fld),
                        "base_value": base_val,
                        "your_value": new_val,
                        "current_value": cur_val,
                        "current_updated_by": snap.get("updated_by", "Another user"),
                        "current_updated_at": snap.get("updated_at", ""),
                    })
                    continue
            else:
                normalized_base[fld] = cur_val

            if new_val != cur_val:
                fields_to_apply[fld] = new_val

        if conflicts:
            return {
                "success": False,
                "conflict": True,
                "scenario_id": target_sid,
                "conflicts": conflicts,
                "current_fields": current_fields,
                "current_version": snap.get("version", 1),
                "error": f"Field conflict detected on {target_sid} ({len(conflicts)} field(s) modified by {snap.get('updated_by', 'another user')}).",
            }

        if fields_to_apply:
            _apply_fields_to_row(sheet, matched_row, fields_to_apply)
            event = {
                "event_id": uuid.uuid4().hex[:12],
                "op": "update",
                "scenario_id": target_sid,
                "actor": actor,
                "machine": _machine_id(),
                "timestamp": _now_iso(),
                "base_fields": normalized_base,
                "changed_fields": fields_to_apply,
            }
            _write_event_file(dirs["events_dir"], event)
            meta.setdefault("applied_event_ids", []).append(event["event_id"])

            snap["version"] = int(snap.get("version", 1)) + 1
            snap["updated_by"] = actor
            snap["updated_at"] = event["timestamp"]
            snap["fields"] = _row_to_fields(sheet, matched_row)
            meta["revision"] = int(meta.get("revision", 1)) + 1
            meta["last_sync_at"] = event["timestamp"]

            _write_sync_meta(wb, meta)
            _save_workbook_safely(wb, primary_xlsx, mirrors, dirs["backups_dir"])
            run_revalidation_and_sync(primary_xlsx)

        return {
            "success": True,
            "scenario_id": target_sid,
            "row": matched_row,
            "merged_fields": list(fields_to_apply.keys()),
            "version": snap.get("version", 1),
            "workbook_path": primary_xlsx,
            "is_onedrive": is_onedrive_path(primary_xlsx),
        }


def add_scenario(data: Dict[str, Any]) -> Dict[str, Any]:
    """Appends a new scenario row conflict-free using client_uid + OneDrive event journal."""
    import openpyxl

    actor = str(data.get("actor") or data.get("owner") or "Collaborator").strip()
    client_uid = str(data.get("client_uid") or uuid.uuid4().hex).strip()

    primary_xlsx, mirrors = resolve_workbook_paths()
    with _acquire_onedrive_lock(primary_xlsx, actor=actor) as dirs:
        wb = openpyxl.load_workbook(primary_xlsx)
        sheet = wb["Scenarios"]
        meta = _read_sync_meta(wb)

        _detect_manual_excel_edits(sheet, meta)
        _merge_conflict_copies(wb, meta, primary_xlsx, dirs["conflicts_dir"])
        _replay_pending_events(wb, meta, dirs["events_dir"])

        client_uid_map = meta.setdefault("client_uid_map", {})
        if client_uid in client_uid_map:
            existing_sid = client_uid_map[client_uid]
            return {
                "success": True,
                "scenario_id": existing_sid,
                "excel_id": format_excel_sid(existing_sid),
                "deduplicated": True,
                "workbook_path": primary_xlsx,
                "is_onedrive": is_onedrive_path(primary_xlsx),
            }

        next_num, new_excel_sid, new_canon_sid, new_row = _next_scenario_id_and_row(sheet)
        _populate_new_row(sheet, new_row, next_num, new_excel_sid, data)
        client_uid_map[client_uid] = new_canon_sid

        event = {
            "event_id": uuid.uuid4().hex[:12],
            "op": "add",
            "client_uid": client_uid,
            "scenario_id": new_canon_sid,
            "actor": actor,
            "machine": _machine_id(),
            "timestamp": _now_iso(),
            "fields": data,
        }
        _write_event_file(dirs["events_dir"], event)
        meta.setdefault("applied_event_ids", []).append(event["event_id"])

        meta.setdefault("row_snapshots", {})[new_canon_sid] = {
            "version": 1,
            "updated_by": actor,
            "updated_at": event["timestamp"],
            "fields": _row_to_fields(sheet, new_row),
        }
        meta["revision"] = int(meta.get("revision", 1)) + 1
        meta["last_sync_at"] = event["timestamp"]

        _write_sync_meta(wb, meta)
        _save_workbook_safely(wb, primary_xlsx, mirrors, dirs["backups_dir"])
        run_revalidation_and_sync(primary_xlsx)

        return {
            "success": True,
            "scenario_id": new_canon_sid,
            "excel_id": new_excel_sid,
            "row": new_row,
            "track": data.get("track", "Human (gold test)"),
            "workbook_path": primary_xlsx,
            "is_onedrive": is_onedrive_path(primary_xlsx),
        }
