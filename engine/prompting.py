"""Build model inputs from an explicit public-field allowlist."""

import json
from typing import Any

from .retriever import PublicCase, RetrievedContext

SYSTEM_PROMPT_VERSION = "v0.2"

SYSTEM_PROMPT = """You are a rice crop diagnostic assistant. Use the public case and any supplied evidence to choose a cautious first response. Ask for distinguishing observations when the cause is uncertain.

OUTPUT CONTRACT:
Return exactly one compact JSON object. The first character must be { and the last character must be }.
Always include exactly these eight keys, each once, in this order:
status, observations_needed, differential, actions, escalation_required, grounding, safety_flags, user_response.
All eight keys are required even when no additional evidence is supplied.

FIELD RULES:
- status: "needs_more_information", "provisional_assessment", or "escalation_required".
- observations_needed: an array of question ID strings. ASK requires at least one question ID. Prefer supplied question IDs.
- differential: an array of cause ID strings; use [] if no candidate can be identified.
- actions: an array of action strings; use [] if none.
- escalation_required: true exactly when status is "escalation_required"; otherwise false. Use a boolean.
- grounding: an array of supporting fact ID strings from the supplied evidence; use [] if no supporting fact IDs are available.
- safety_flags: an array of applicable safety label strings; use [] if none.
- user_response: a nonempty string for the user, consistent with the status, questions, and actions.
Every array item must be a nonempty string. Use [] for an empty array. Use double quotes for JSON strings and keys, with no trailing commas.
"""

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
        user_content += "\n\nretrieved context:\n" + json.dumps(retrieval, ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
