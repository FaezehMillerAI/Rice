"""Interactive offline field console for compact diagnostic responses."""

from __future__ import annotations

import argparse
import json
from typing import Any

from field_app.hybrid_engine import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    HybridFieldEngine,
)
from field_app.telemetry_logger import FieldPilotTelemetryLogger


def _item_id(item: Any, *keys: str) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return str(item)


def format_payload(payload: dict[str, Any]) -> str:
    """Render the current compact contract while tolerating legacy dict items."""
    lines = [f"Diagnostic status: {payload.get('status', 'unknown')}"]
    user_response = payload.get("user_response")
    if isinstance(user_response, str) and user_response.strip():
        lines.extend(["", user_response.strip()])

    sections = (
        ("Questions / observations needed", "observations_needed", ("question_id", "question")),
        ("Differential", "differential", ("cause_id", "display_name")),
        ("Actions", "actions", ("action_id", "action")),
        ("Grounding", "grounding", ("claim_id", "fact_id")),
        ("Safety flags", "safety_flags", ("flag_id",)),
    )
    for title, field, keys in sections:
        items = payload.get(field, [])
        if isinstance(items, list) and items:
            lines.extend(["", f"{title}:"])
            lines.extend(f"  - {_item_id(item, *keys)}" for item in items)
    if payload.get("escalation_required") is True:
        lines.extend(["", "ESCALATION REQUIRED: contact a plant pathology professional."])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Exact installed tuned Ollama tag; default is RICE_OLLAMA_MODEL or "
            f"{DEFAULT_OLLAMA_MODEL!r}"
        ),
    )
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument(
        "--kg-only",
        action="store_true",
        help="Explicitly disable model inference and use the deterministic KG",
    )
    return parser


def run_cli(args: argparse.Namespace | None = None) -> None:
    args = args or build_parser().parse_args()
    print("=" * 75)
    print(" RICE PATHOGEN SALM — OFFLINE FIELD DIAGNOSTIC SYSTEM")
    print("=" * 75)

    engine = HybridFieldEngine(
        ollama_model=args.model,
        ollama_url=args.ollama_url,
        timeout_seconds=args.timeout,
        kg_only=args.kg_only,
    )
    if args.kg_only:
        print("Mode: deterministic KG only (explicitly selected)")
    else:
        metadata = engine.check_ollama_model()
        print(
            "Mode: hybrid | tuned Ollama model: "
            f"{metadata['model']} | digest: {metadata['digest'] or 'unknown'}"
        )
        print(f"Ollama server version: {metadata['server_version'] or 'unknown'}")

    logger = FieldPilotTelemetryLogger()
    officer_id = (
        input("Enter Extension Officer ID [e.g. EXT-ODISHA-042]: ").strip()
        or "EXT-ODISHA-DEFAULT"
    )
    district_code = (
        input("Enter District / Block Code [e.g. Sambalpur]: ").strip()
        or "Sambalpur"
    )

    while True:
        print("\n" + "-" * 75)
        utterance = input("Enter Farmer Utterance (or 'q' to quit): ").strip()
        if utterance.lower() in {"q", "quit", "exit"}:
            print("Exiting field terminal; local telemetry is saved.")
            break
        if not utterance:
            continue
        growth_stage = (
            input(
                "Growth Stage [tillering/heading/flowering/ripening] "
                "(default: tillering): "
            ).strip()
            or "tillering"
        )
        context = {
            "growth_stage": growth_stage,
            "region": "priority-region-1",
            "language": "en",
        }
        result = engine.diagnose(utterance, context)
        print(
            f"\nEngine: {result['engine_used']} "
            f"(latency: {result['latency_ms']} ms)"
        )
        if result["fallback_triggered"]:
            print(f"Fallback triggered: {result['fallback_reason']}")
        if not result["verification"]["passed"]:
            print(
                "WARNING: final response verification failed: "
                + json.dumps(result["verification"]["errors"], ensure_ascii=False)
            )
        print("\n" + format_payload(result["diagnostic_payload"]))

        agreement = input(
            "\nExtension Officer Validation [agree/disagree/partial/skip]: "
        ).strip().lower()
        confirmed_cause = ""
        notes = ""
        if agreement in {"agree", "disagree", "partial"}:
            confirmed_cause = input(
                "Confirmed Ground Truth Cause (if verified): "
            ).strip()
            notes = input("Field Notes / Crop Response Observations: ").strip()
        session_id = logger.log_session(
            officer_id,
            district_code,
            utterance,
            result,
            agreement if agreement in {"agree", "disagree", "partial"} else None,
            confirmed_cause,
            notes,
        )
        print(f"Telemetry recorded (Session ID: {session_id}).")


if __name__ == "__main__":
    run_cli()
