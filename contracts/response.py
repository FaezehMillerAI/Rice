"""Stable model-response boundary shared by SFT, evaluation, and deployment.

This module owns the model-facing JSON names, schema, prompt instructions,
strict parser, and canonical application representation.  It performs only
format/shape checks; diagnostic scoring and deployment policy live elsewhere.
"""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
import json
import re
from typing import Any, Mapping, TypedDict


RESPONSE_CONTRACT_VERSION = "v0.2"


class ResponseStatus(StrEnum):
    NEEDS_MORE_INFORMATION = "needs_more_information"
    PROVISIONAL_ASSESSMENT = "provisional_assessment"
    ESCALATION_REQUIRED = "escalation_required"


class ModelResponse(TypedDict):
    """Canonical response representation used by application code."""

    status: str
    observations_needed: list[str]
    differential: list[str]
    actions: list[str]
    escalation_required: bool
    grounding: list[str]
    safety_flags: list[str]
    user_response: str


# Compatibility name for code and artifacts that call this the compact format.
CompactResponse = ModelResponse

LIST_FIELDS = (
    "observations_needed",
    "differential",
    "actions",
    "grounding",
    "safety_flags",
)
RESPONSE_FIELD_ORDER = (
    "status",
    "observations_needed",
    "differential",
    "actions",
    "escalation_required",
    "grounding",
    "safety_flags",
    "user_response",
)
RESPONSE_FIELDS = set(RESPONSE_FIELD_ORDER)
RESPONSE_STATUSES = tuple(status.value for status in ResponseStatus)

STATUS_TO_BEHAVIOR = {
    ResponseStatus.NEEDS_MORE_INFORMATION.value: "ASK",
    ResponseStatus.PROVISIONAL_ASSESSMENT.value: "ANSWER",
    ResponseStatus.ESCALATION_REQUIRED.value: "ESCALATE",
}
BEHAVIOR_TO_STATUS = {
    behavior: status
    for status, behavior in STATUS_TO_BEHAVIOR.items()
}

# Canonical application key -> model-facing JSON key.  Future wire-format
# renames belong here; the rest of the application continues using canonical
# keys.
MODEL_RESPONSE_WIRE_FIELDS = {
    field: field
    for field in RESPONSE_FIELD_ORDER
}
RESPONSE_WIRE_FIELD_ORDER = tuple(
    MODEL_RESPONSE_WIRE_FIELDS[field]
    for field in RESPONSE_FIELD_ORDER
)


def make_model_response(
    *,
    status: str,
    observations_needed: list[str],
    differential: list[str],
    actions: list[str],
    escalation_required: bool,
    grounding: list[str],
    safety_flags: list[str],
    user_response: str,
) -> ModelResponse:
    """Create an isolated canonical response in the required field order."""
    return {
        "status": status,
        "observations_needed": deepcopy(observations_needed),
        "differential": deepcopy(differential),
        "actions": deepcopy(actions),
        "escalation_required": escalation_required,
        "grounding": deepcopy(grounding),
        "safety_flags": deepcopy(safety_flags),
        "user_response": user_response,
    }


def encode_model_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Translate canonical response keys to the model-facing wire format."""
    encoded: dict[str, Any] = {}
    for canonical in RESPONSE_FIELD_ORDER:
        if canonical in response:
            encoded[MODEL_RESPONSE_WIRE_FIELDS[canonical]] = deepcopy(
                response[canonical]
            )
    for key, value in response.items():
        if key not in RESPONSE_FIELDS:
            wire_key = MODEL_RESPONSE_WIRE_FIELDS.get(key, key)
            if wire_key in encoded:
                raise ValueError(
                    f"Duplicate model-response field after encoding: {wire_key}"
                )
            encoded[wire_key] = deepcopy(value)
    return encoded


def decode_model_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Translate model-facing wire keys to canonical application keys."""
    wire_to_canonical = {
        wire: canonical
        for canonical, wire in MODEL_RESPONSE_WIRE_FIELDS.items()
    }
    decoded: dict[str, Any] = {}
    for key, value in response.items():
        canonical = wire_to_canonical.get(key, key)
        if canonical in decoded:
            raise ValueError(
                f"Duplicate model-response field after decoding: {canonical}"
            )
        decoded[canonical] = deepcopy(value)
    return decoded


def _string_array_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "string",
            "minLength": 1,
            "pattern": r"\S",
        },
    }


def _wire(field: str) -> str:
    return MODEL_RESPONSE_WIRE_FIELDS[field]


RESPONSE_JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": (
        "https://rice-salm.local/schemas/compact-response-"
        f"{RESPONSE_CONTRACT_VERSION}.json"
    ),
    "title": "Rice SALM compact diagnostic response",
    "type": "object",
    "additionalProperties": False,
    "required": list(RESPONSE_WIRE_FIELD_ORDER),
    "properties": {
        _wire("status"): {
            "type": "string",
            "enum": list(RESPONSE_STATUSES),
        },
        _wire("observations_needed"): _string_array_schema(),
        _wire("differential"): _string_array_schema(),
        _wire("actions"): _string_array_schema(),
        _wire("escalation_required"): {"type": "boolean"},
        _wire("grounding"): _string_array_schema(),
        _wire("safety_flags"): _string_array_schema(),
        _wire("user_response"): {
            "type": "string",
            "minLength": 1,
            "pattern": r"\S",
        },
    },
    "allOf": [
        {
            "if": {
                "properties": {
                    _wire("status"): {
                        "const": ResponseStatus.NEEDS_MORE_INFORMATION.value
                    }
                }
            },
            "then": {
                "properties": {
                    _wire("observations_needed"): {"minItems": 1}
                }
            },
        },
        {
            "if": {
                "properties": {
                    _wire("status"): {
                        "const": ResponseStatus.ESCALATION_REQUIRED.value
                    }
                }
            },
            "then": {
                "properties": {
                    _wire("escalation_required"): {"const": True}
                }
            },
            "else": {
                "properties": {
                    _wire("escalation_required"): {"const": False}
                }
            },
        },
    ],
}


def render_model_response_instructions() -> str:
    """Render the prompt section from the same wire mapping as the schema."""
    names = ", ".join(RESPONSE_WIRE_FIELD_ORDER)
    return f"""OUTPUT CONTRACT:
Return exactly one compact JSON object. The first character must be {{ and the last character must be }}.
Always include exactly these eight keys, each once, in this order:
{names}.
All eight keys are required even when no additional evidence is supplied.

FIELD RULES:
- {_wire("status")}: "needs_more_information", "provisional_assessment", or "escalation_required".
- {_wire("observations_needed")}: an array of question ID strings. ASK requires at least one question ID. Prefer supplied question IDs.
- {_wire("differential")}: an array of cause ID strings; use [] if no candidate can be identified.
- {_wire("actions")}: an array of action strings; use [] if none.
- {_wire("escalation_required")}: true exactly when {_wire("status")} is "escalation_required"; otherwise false. Use a boolean.
- {_wire("grounding")}: an array of supporting fact ID strings from the supplied evidence; use [] if no supporting fact IDs are available.
- {_wire("safety_flags")}: an array of applicable safety label strings; use [] if none.
- {_wire("user_response")}: a nonempty string for the user, consistent with the status, questions, and actions.
Every array item must be a nonempty string. Use [] for an empty array. Use double quotes for JSON strings and keys, with no trailing commas.
"""


MODEL_RESPONSE_INSTRUCTIONS = render_model_response_instructions()


def parse_response(raw_text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Parse the whole completion and translate wire keys to canonical keys."""

    def unique_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate JSON key: {key}")
            value[key] = item
        return value

    def reject_constant(value):
        raise ValueError(f"Non-JSON numeric constant: {value}")

    try:
        value = json.loads(
            raw_text,
            object_pairs_hook=unique_keys,
            parse_constant=reject_constant,
        )
        if not isinstance(value, dict):
            return None, ["Response must be a JSON object"]
        return decode_model_response(value), []
    except (ValueError, TypeError) as exc:
        return None, [f"JSON parse error: {exc}"]


def prepare_prediction_input(raw_text: Any) -> tuple[Any, dict[str, Any]]:
    """Remove only a complete outer Markdown JSON fence, without JSON repair."""
    trace = {"method": "strip_outer_markdown_json_fence", "applied": False}
    if isinstance(raw_text, str):
        match = re.fullmatch(
            r"\x60{3}(?:json)?\s*(\{[\s\S]*\})\s*\x60{3}",
            raw_text.strip(),
            re.IGNORECASE,
        )
        if match:
            trace["applied"] = True
            return match.group(1), trace
    return raw_text, trace


def validate_response(value: Any) -> list[str]:
    """Validate the canonical eight-field shape, independently of scoring."""
    if not isinstance(value, dict):
        return ["Response must be an object"]
    errors = []
    if set(value) != RESPONSE_FIELDS:
        errors.append(
            f"Missing fields: {sorted(RESPONSE_FIELDS - set(value))}; "
            f"extra fields: {sorted(set(value) - RESPONSE_FIELDS)}"
        )
    status = value.get("status")
    if not isinstance(status, str) or status not in RESPONSE_STATUSES:
        errors.append("Invalid status")
    for field in LIST_FIELDS:
        items = value.get(field)
        if not isinstance(items, list) or any(
            not isinstance(item, str) or not item.strip()
            for item in items
        ):
            errors.append(f"{field} must be a list of nonempty strings")
    escalation = value.get("escalation_required")
    if type(escalation) is not bool:
        errors.append("escalation_required must be a boolean")
    elif escalation != (status == ResponseStatus.ESCALATION_REQUIRED.value):
        errors.append("status and escalation_required disagree")
    user_response = value.get("user_response")
    if not isinstance(user_response, str) or not user_response.strip():
        errors.append("user_response must be a nonempty string")
    if (
        status == ResponseStatus.NEEDS_MORE_INFORMATION.value
        and not value.get("observations_needed")
    ):
        errors.append("ASK requires at least one question ID")
    return errors
