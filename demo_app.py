#!/usr/bin/env python3
"""
demo_app.py
Rice Pathogen SALM — Multi-User Interactive Web Application & OneDrive Excel Sync Server
=======================================================================================
Enables Ginny, Aseel, Faezeh, and Richard to collaborate concurrently on:
  1. Inspecting all clinical scenarios, 842 Richard facts, sources, and Knowledge Graph.
  2. Verifying and signing off on Human Gold test scenarios with a single click.
  3. Modifying any scenario's farmer text, clinical observations, or responses.
  4. Adding new scenarios directly to Human Gold or AI-Drafted tracks.
  5. Automatically synchronizing all changes WITHOUT overwriting other users' edits:
     - Live OneDrive Excel Workbook (rice_slm_diagnostic_scenarios_completed.xlsx)
     - Append-only OneDrive sync journal (.rice_sync/events/)
     - Field-level 3-way merge + conflict resolution modal
     - SFT Training/Eval Dataset (workbook_scenarios_v0.2.jsonl)
     - Standalone Dashboard & Validation Audit Report

Usage:
  python3 demo_app.py [--port 8000] [--no-browser]
"""

import os
import sys
import json
import socket
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import urllib.parse

WORKSPACE_ROOT = os.path.abspath(os.path.dirname(__file__))

# Auto-switch to local .venv Python if system Python lacks openpyxl
venv_python = os.path.join(WORKSPACE_ROOT, ".venv/bin/python")
if os.path.exists(venv_python) and sys.executable != venv_python:
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        os.execv(venv_python, [venv_python] + sys.argv)

if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from engine.scenario_manager import (
    update_scenario,
    verify_scenario,
    add_scenario,
    list_scenarios_live,
    get_sync_status,
    sync_workbook_and_state,
    resolve_workbook_paths,
    is_onedrive_path,
)

DEFAULT_PORT = 8000


def _get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class RiceDemoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WORKSPACE_ROOT, **kwargs)

    def _send_json(self, payload: dict, status_code: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ["", "/", "/index.html"]:
            self.path = "/demo_dashboard.html"
            return super().do_GET()
        elif parsed.path == "/api/scenarios":
            try:
                data = list_scenarios_live()
                self._send_json(data, 200)
            except Exception as exc:
                self._send_json({"scenarios": [], "error": str(exc)}, 500)
            return
        elif parsed.path == "/api/status":
            try:
                self._send_json(get_sync_status(), 200)
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)}, 500)
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(length) if length > 0 else b"{}"

        try:
            body = json.loads(post_data.decode("utf-8"))
        except Exception:
            body = {}

        response_data = {"success": False, "error": "Unknown endpoint"}
        status_code = 400

        try:
            if parsed.path == "/api/scenarios/verify":
                sid = body.get("scenario_id")
                reviewer = body.get("reviewer") or body.get("actor") or "Aseel"
                notes = body.get("notes", "Verified as Human Gold Benchmark")
                response_data = verify_scenario(sid, reviewer, notes)
                status_code = 200 if response_data.get("success") else 400
            elif parsed.path == "/api/scenarios/update":
                response_data = update_scenario(body)
                if response_data.get("success"):
                    status_code = 200
                elif response_data.get("conflict"):
                    status_code = 409
                else:
                    status_code = 400
            elif parsed.path == "/api/scenarios/add":
                response_data = add_scenario(body)
                status_code = 200 if response_data.get("success") else 400
            elif parsed.path == "/api/sync":
                actor = body.get("actor", "ManualSync")
                sync_info = sync_workbook_and_state(actor=actor, force_export=True)
                live = list_scenarios_live()
                response_data = {
                    "success": sync_info.get("success", True),
                    "sync_info": sync_info,
                    **live,
                }
                status_code = 200 if sync_info.get("success", True) else 400
        except Exception as exc:
            response_data = {"success": False, "error": str(exc)}
            status_code = 500

        self._send_json(response_data, status_code)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def run_server():
    port = DEFAULT_PORT
    for arg_idx, arg in enumerate(sys.argv):
        if arg == "--port" and arg_idx + 1 < len(sys.argv):
            try:
                port = int(sys.argv[arg_idx + 1])
            except ValueError:
                pass

    no_browser = "--no-browser" in sys.argv

    # Initial OneDrive sync on startup
    primary_xlsx, _ = resolve_workbook_paths()
    try:
        sync_workbook_and_state(actor="Startup", force_export=False)
    except Exception as exc:
        print(f"[Startup Sync Warning] {exc}")

    httpd = None
    actual_port = port
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", p), RiceDemoHandler)
            actual_port = p
            break
        except OSError:
            continue

    if not httpd:
        print("Error: Could not bind to any port.")
        sys.exit(1)

    local_url = f"http://localhost:{actual_port}/"
    lan_ip = _get_lan_ip()
    lan_url = f"http://{lan_ip}:{actual_port}/"

    print("\n" + "=" * 78)
    print("🌾 RICE PATHOGEN SALM — MULTI-USER LIVE DEMO & ONEDRIVE EXCEL SYNC SERVER")
    print("=" * 78)
    print(f"Local URL : {local_url}")
    print(f"Team LAN  : {lan_url}  (share with another user on same network)")
    print(f"Workbook  : {primary_xlsx}")
    print(f"OneDrive  : {'YES (Live OneDrive Sync Active)' if is_onedrive_path(primary_xlsx) else 'LOCAL FALLBACK'}")
    print("Multi-User: Field-level 3-way merge + OneDrive .rice_sync journal ACTIVE.")
    print("Press Ctrl+C to stop server.\n")

    if not no_browser:
        try:
            webbrowser.open(local_url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping demo server.")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
