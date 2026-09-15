#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================="
echo " Rice Pathogen SALM — Offline Diagnostic Field Bundle (V1.0)"
echo "================================================================="

if curl -s http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
    echo "[✓] Local Ollama service detected and active."
else
    echo "[!] Ollama service not detected. Hybrid Engine will operate in KG Deterministic Mode."
fi

python3 field_app/field_cli.py
