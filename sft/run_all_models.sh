#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv run --locked python -m sft.trainer --model qwen2.5-1.5b
uv run --locked python -m sft.trainer --model qwen3-4b
uv run --locked python -m sft.trainer --model phi4-mini
uv run --locked python -m sft.trainer --model smollm3-3b
uv run --locked python -m sft.trainer --model qwen3.5-4b
uv run --locked python -m sft.trainer --model llama3.2-3b
