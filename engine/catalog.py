"""Read-only KG metadata exposed to non-engine consumers.

The diagnostic engine keeps richer mutable registries for its algorithms.  This
module projects only the stable metadata needed by evaluation so callers do not
reach through ``KGRetriever.engine`` or depend on registry implementation
details.
"""

from __future__ import annotations

from typing import Any, Mapping

from contracts.retrieval import KGCatalogSnapshot, RetrievedFact


_FACT_FIELDS = (
    "claim_id",
    "subject_uri",
    "predicate_uri",
    "object_uri",
    "source_id",
    "source_section",
    "source_text_span",
)


def _action_catalog(engine: Any) -> dict[str, list[str]]:
    """Project deterministic management metadata without diagnosing a case."""
    getter = getattr(engine, "get_management_actions", None)
    diseases = getattr(engine, "diseases", {})
    if not callable(getter) or not isinstance(diseases, dict):
        return {}

    catalog: dict[str, list[str]] = {}
    requests = [*((cause_id, False) for cause_id in diseases), ("", False), ("", True)]
    for cause_id, escalated in requests:
        rows = getter(cause_id, escalated)
        for row in rows if isinstance(rows, (list, tuple)) else []:
            if not isinstance(row, dict):
                continue
            action_id = row.get("action_id")
            action = row.get("action")
            if not isinstance(action_id, str) or not isinstance(action, str):
                continue
            texts = catalog.setdefault(action_id, [])
            if action not in texts:
                texts.append(action)
    return catalog


def _fact(row: Mapping[str, Any], claim_id: str) -> RetrievedFact:
    return {
        field: str(claim_id if field == "claim_id" else row.get(field, ""))
        for field in _FACT_FIELDS
    }


def build_kg_catalog_snapshot(
    engine: Any,
    richard_facts: Mapping[str, Mapping[str, Any]],
    *,
    retrieval_version: str,
) -> KGCatalogSnapshot:
    """Return an isolated, evaluator-facing snapshot of KG catalog metadata."""
    causes = {
        cause_id: {
            "id": str(row.get("id", cause_id)),
            "canonical_name": str(row.get("canonical_name", "")),
            "skos_pref_label": str(row.get("skos_pref_label", "")),
            "skos_alt_labels": [
                str(value)
                for value in row.get("skos_alt_labels", [])
                if str(value).strip()
            ],
        }
        for cause_id, row in engine.diseases.items()
    }
    questions = {
        question_id: {
            "question_id": str(row.get("question_id", question_id)),
            "canonical_text": str(row.get("canonical_text", "")),
            "farmer_friendly_phrasing": str(
                row.get("farmer_friendly_phrasing", "")
            ),
        }
        for question_id, row in engine.questions.items()
    }
    claims = {
        claim_id: _fact(row, claim_id)
        for claim_id, row in engine.claims.items()
    }

    evidence_sources_by_fact = {
        claim_id: fact["source_id"]
        for claim_id, fact in claims.items()
    }
    for fact_id, row in richard_facts.items():
        source_id = str(row.get("source_id", "")).strip()
        source_id = source_id or "source:irri_rice_doctor_2024"
        existing = evidence_sources_by_fact.get(fact_id)
        if existing is not None and existing != source_id:
            raise ValueError(
                f"Conflicting source IDs for KG fact {fact_id}: "
                f"{existing!r} and {source_id!r}"
            )
        evidence_sources_by_fact[fact_id] = source_id

    return {
        "retrieval_version": retrieval_version,
        "causes": causes,
        "questions": questions,
        "claims": claims,
        "evidence_sources_by_fact": evidence_sources_by_fact,
        "action_catalog": _action_catalog(engine),
    }
