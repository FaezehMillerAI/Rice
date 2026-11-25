"""Build model inputs from an explicit public-field allowlist."""

import json
from typing import Any

from contracts.response import MODEL_RESPONSE_INSTRUCTIONS
from contracts.retrieval import (
    PublicCase,
    RetrievedContext,
    encode_retrieved_context,
)

SYSTEM_PROMPT_VERSION = "v0.3"

_DIAGNOSTIC_INSTRUCTIONS = (
    "You are a rice crop diagnostic assistant. Use the public case and any "
    "supplied evidence to choose a cautious first response. Ask for "
    "distinguishing observations when the cause is uncertain."
)
SYSTEM_PROMPT = (
    _DIAGNOSTIC_INSTRUCTIONS
    + "\n\n"
    + MODEL_RESPONSE_INSTRUCTIONS
)

def select_public_case(case: dict[str, Any]) -> PublicCase:
    """Copy only inference-available fields; discard all labels and metadata."""
    input_data = case["input"]
    return {
        "input": {
            "user_text": input_data.get("user_text"),
            "growth_stage_id": input_data.get("growth_stage_id"),
            "production_system_id": input_data.get("production_system_id"),
            "cultivar_id": input_data.get("cultivar_id"),
        },
        "language": case.get("language"),
        "region_id": case.get("region_id"),
    }


def build_prompt(
    public_case: PublicCase, retrieval: RetrievedContext | None = None
) -> list[dict[str, str]]:
    """Build public-only input when retrieval is None; otherwise append context."""
    user_content = "User query:\n" + json.dumps(public_case, ensure_ascii=False, indent=2)
    if retrieval is not None:
        payload = encode_retrieved_context(retrieval)
        user_content += "\n\nretrieved context:\n" + json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
