#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

kg_only=false
model_argument=false
previous=""
for argument in "$@"; do
  if [[ "$argument" == "--kg-only" ]]; then
    kg_only=true
  fi
  if [[ "$argument" == --model=* || "$previous" == "--model" ]]; then
    model_argument=true
  fi
  previous="$argument"
done

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install uv, then run: uv sync --locked" >&2
  exit 127
fi

if [[ "$kg_only" != true && "$model_argument" != true && -z "${RICE_OLLAMA_MODEL:-}" ]]; then
  echo "Hybrid mode requires an exact tuned Ollama tag." >&2
  echo "Set RICE_OLLAMA_MODEL or pass --model; use --kg-only for explicit KG-only mode." >&2
  exit 2
fi

echo "================================================================="
echo " Rice Pathogen SALM — Offline Diagnostic Field Bundle"
echo "================================================================="

exec uv run --locked python -m field_app.field_cli "$@"
