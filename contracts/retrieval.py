"""Stable boundary for knowledge-graph retrieval data.

The KG implementation lives in :mod:`engine.retriever`.  This module owns only
the data exchanged with training, evaluation, and deployment code.  Canonical
Python keys are intentionally separated from the model-facing wire keys so a
future prompt-interface rename can be handled here without changing consumers.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, Mapping, TypedDict, cast


RETRIEVAL_CONTRACT_VERSION = "v0.3"

RETRIEVAL_FIELD_ORDER = (
    "normalized_observations",
    "candidate_causes",
    "supporting_evidence",
    "contradicting_evidence",
    "missing_observations",
    "suggested_questions",
    "retrieved_facts",
    "evidence_fact_ids",
    "evidence_source_ids",
)
RETRIEVAL_FIELDS = set(RETRIEVAL_FIELD_ORDER)

# Canonical application key -> model-facing JSON key.  Keep all translation at
# this boundary; engine/SFT/eval/field code should use the canonical names.
RETRIEVAL_WIRE_FIELDS = {
    field: field
    for field in RETRIEVAL_FIELD_ORDER
}


class PublicInput(TypedDict):
    user_text: str | None
    growth_stage_id: str | None
    production_system_id: str | None
    cultivar_id: str | None


class PublicCase(TypedDict):
    """Inference-visible case fields; labels and targets are excluded."""

    input: PublicInput
    language: str | None
    region_id: str | None


ExplicitObservationState = Literal["TRUE", "FALSE", "UNKNOWN"]


class ExplicitObservation(TypedDict):
    """One normalized observation accepted by ``DiagnosticEngine``."""

    term_id: str
    state: ExplicitObservationState


class RetrievalRequest(PublicCase, total=False):
    """Canonical request plus optional observations supplied by field users."""

    explicit_observations: list[ExplicitObservation]


ObservationState = Literal["PRESENT", "ABSENT", "UNKNOWN"]
EvidenceTruthState = Literal["state:TRUE", "state:FALSE", "state:UNKNOWN"]
EvidenceType = Literal["Supporting", "Contradicting"]


class NormalizedObservation(TypedDict):
    concept_id: str
    state: ObservationState


class EvidenceRecord(TypedDict):
    cause_id: str
    observation_id: str
    evidence_type: EvidenceType
    condition_truth_state: EvidenceTruthState
    explanation: str


class SuggestedQuestion(TypedDict):
    question_id: str
    target_observation_id: str
    canonical_text: str
    farmer_friendly_phrasing: str
    rationale: str


class RetrievedFact(TypedDict):
    claim_id: str
    subject_uri: str
    predicate_uri: str
    object_uri: str
    source_id: str
    source_section: str
    source_text_span: str


class RetrievedContext(TypedDict):
    """Canonical nine-field KG context used inside the application."""

    normalized_observations: list[NormalizedObservation]
    candidate_causes: list[str]
    supporting_evidence: list[EvidenceRecord]
    contradicting_evidence: list[EvidenceRecord]
    missing_observations: list[str]
    suggested_questions: list[SuggestedQuestion]
    retrieved_facts: list[RetrievedFact]
    evidence_fact_ids: list[str]
    evidence_source_ids: list[str]


class CauseCatalogEntry(TypedDict):
    """Cause labels needed by evaluation without exposing engine registries."""

    id: str
    canonical_name: str
    skos_pref_label: str
    skos_alt_labels: list[str]


class QuestionCatalogEntry(TypedDict):
    """Question labels needed by evaluation consistency checks."""

    question_id: str
    canonical_text: str
    farmer_friendly_phrasing: str


class KGCatalogSnapshot(TypedDict):
    """Detached read-only-by-convention KG metadata exposed to consumers."""

    retrieval_version: str
    causes: dict[str, CauseCatalogEntry]
    questions: dict[str, QuestionCatalogEntry]
    claims: dict[str, RetrievedFact]
    evidence_sources_by_fact: dict[str, str]
    action_catalog: dict[str, list[str]]


_OBSERVATION_FIELDS = {"concept_id", "state"}
_EVIDENCE_FIELDS = {
    "cause_id",
    "observation_id",
    "evidence_type",
    "condition_truth_state",
    "explanation",
}
_QUESTION_FIELDS = {
    "question_id",
    "target_observation_id",
    "canonical_text",
    "farmer_friendly_phrasing",
    "rationale",
}
_FACT_FIELDS = {
    "claim_id",
    "subject_uri",
    "predicate_uri",
    "object_uri",
    "source_id",
    "source_section",
    "source_text_span",
}
_STRING_LIST_FIELDS = (
    "candidate_causes",
    "missing_observations",
    "evidence_fact_ids",
    "evidence_source_ids",
)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def ensure_explicit_observations(value: Any) -> list[ExplicitObservation]:
    """Validate and isolate observations at the KG request boundary."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("explicit_observations must be a list")

    result: list[ExplicitObservation] = []
    errors: list[str] = []
    for index, item in enumerate(value):
        path = f"explicit_observations[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        expected_fields = {"term_id", "state"}
        if set(item) != expected_fields:
            errors.append(
                f"{path} missing fields: {sorted(expected_fields - set(item))}; "
                f"extra fields: {sorted(set(item) - expected_fields)}"
            )
        term_id = item.get("term_id")
        state = item.get("state")
        if not _nonempty_string(term_id):
            errors.append(f"{path}.term_id must be a nonempty string")
        if state not in ("TRUE", "FALSE", "UNKNOWN"):
            errors.append(f"{path}.state must be TRUE, FALSE, or UNKNOWN")
        if _nonempty_string(term_id) and state in ("TRUE", "FALSE", "UNKNOWN"):
            result.append({"term_id": term_id, "state": state})

    if errors:
        raise ValueError("Invalid explicit observations: " + "; ".join(errors))
    return result


def _validate_record_shape(
    *,
    field: str,
    index: int,
    value: Any,
    expected_fields: set[str],
    errors: list[str],
) -> dict[str, Any] | None:
    path = f"{field}[{index}]"
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return None
    if set(value) != expected_fields:
        errors.append(
            f"{path} missing fields: {sorted(expected_fields - set(value))}; "
            f"extra fields: {sorted(set(value) - expected_fields)}"
        )
    return value


def validate_retrieved_context(value: Any) -> list[str]:
    """Validate the canonical nine-field shape without scoring KG semantics."""
    if not isinstance(value, dict):
        return ["Retrieved context must be an object"]

    errors: list[str] = []
    if set(value) != RETRIEVAL_FIELDS:
        errors.append(
            f"Missing fields: {sorted(RETRIEVAL_FIELDS - set(value))}; "
            f"extra fields: {sorted(set(value) - RETRIEVAL_FIELDS)}"
        )

    for field in RETRIEVAL_FIELD_ORDER:
        if not isinstance(value.get(field), list):
            errors.append(f"{field} must be a list")

    for field in _STRING_LIST_FIELDS:
        items = value.get(field)
        if isinstance(items, list):
            for index, item in enumerate(items):
                if not _nonempty_string(item):
                    errors.append(f"{field}[{index}] must be a nonempty string")

    observations = value.get("normalized_observations")
    normalized_states: dict[str, str] = {}
    if isinstance(observations, list):
        for index, item in enumerate(observations):
            record = _validate_record_shape(
                field="normalized_observations",
                index=index,
                value=item,
                expected_fields=_OBSERVATION_FIELDS,
                errors=errors,
            )
            if record is None:
                continue
            if not _nonempty_string(record.get("concept_id")):
                errors.append(
                    f"normalized_observations[{index}].concept_id must be a nonempty string"
                )
            if record.get("state") not in ("PRESENT", "ABSENT", "UNKNOWN"):
                errors.append(
                    f"normalized_observations[{index}].state must be PRESENT, ABSENT, or UNKNOWN"
                )
            concept_id = record.get("concept_id")
            state = record.get("state")
            if _nonempty_string(concept_id) and state in (
                "PRESENT",
                "ABSENT",
                "UNKNOWN",
            ):
                normalized_states[concept_id] = state

    for field, expected_type in (
        ("supporting_evidence", "Supporting"),
        ("contradicting_evidence", "Contradicting"),
    ):
        items = value.get(field)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            record = _validate_record_shape(
                field=field,
                index=index,
                value=item,
                expected_fields=_EVIDENCE_FIELDS,
                errors=errors,
            )
            if record is None:
                continue
            for key in ("cause_id", "observation_id", "explanation"):
                if not _nonempty_string(record.get(key)):
                    errors.append(f"{field}[{index}].{key} must be a nonempty string")
            if record.get("evidence_type") != expected_type:
                errors.append(
                    f"{field}[{index}].evidence_type must be {expected_type}"
                )
            if record.get("condition_truth_state") not in (
                "state:TRUE",
                "state:FALSE",
                "state:UNKNOWN",
            ):
                errors.append(
                    f"{field}[{index}].condition_truth_state must be state:TRUE, "
                    "state:FALSE, or state:UNKNOWN"
                )

    questions = value.get("suggested_questions")
    if isinstance(questions, list):
        for index, item in enumerate(questions):
            record = _validate_record_shape(
                field="suggested_questions",
                index=index,
                value=item,
                expected_fields=_QUESTION_FIELDS,
                errors=errors,
            )
            if record is None:
                continue
            for key in _QUESTION_FIELDS:
                if not _nonempty_string(record.get(key)):
                    errors.append(
                        f"suggested_questions[{index}].{key} must be a nonempty string"
                    )

    facts = value.get("retrieved_facts")
    if isinstance(facts, list):
        for index, item in enumerate(facts):
            record = _validate_record_shape(
                field="retrieved_facts",
                index=index,
                value=item,
                expected_fields=_FACT_FIELDS,
                errors=errors,
            )
            if record is None:
                continue
            for key in _FACT_FIELDS:
                field_value = record.get(key)
                if key == "object_uri":
                    if not isinstance(field_value, str):
                        errors.append(
                            f"retrieved_facts[{index}].object_uri must be a string"
                        )
                elif not _nonempty_string(field_value):
                    errors.append(
                        f"retrieved_facts[{index}].{key} must be a nonempty string"
                    )

    candidate_ids = {
        item for item in value.get("candidate_causes", [])
        if _nonempty_string(item)
    } if isinstance(value.get("candidate_causes"), list) else set()
    missing_ids = {
        item for item in value.get("missing_observations", [])
        if _nonempty_string(item)
    } if isinstance(value.get("missing_observations"), list) else set()
    fact_ids = {
        item for item in value.get("evidence_fact_ids", [])
        if _nonempty_string(item)
    } if isinstance(value.get("evidence_fact_ids"), list) else set()
    source_ids = {
        item for item in value.get("evidence_source_ids", [])
        if _nonempty_string(item)
    } if isinstance(value.get("evidence_source_ids"), list) else set()

    for field in ("supporting_evidence", "contradicting_evidence"):
        items = value.get(field)
        if isinstance(items, list):
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                if _nonempty_string(item.get("cause_id")):
                    if item["cause_id"] not in candidate_ids:
                        errors.append(
                            f"{field}[{index}].cause_id is absent from candidate_causes"
                        )
                observation_id = item.get("observation_id")
                if _nonempty_string(observation_id):
                    if observation_id not in normalized_states:
                        errors.append(
                            f"{field}[{index}].observation_id is absent from "
                            "normalized_observations"
                        )
                    else:
                        expected_state = {
                            "state:TRUE": "PRESENT",
                            "state:FALSE": "ABSENT",
                            "state:UNKNOWN": "UNKNOWN",
                        }.get(item.get("condition_truth_state"))
                        if (
                            expected_state is not None
                            and normalized_states[observation_id] != expected_state
                        ):
                            errors.append(
                                f"{field}[{index}].condition_truth_state conflicts "
                                "with normalized_observations"
                            )

    if isinstance(questions, list):
        for index, item in enumerate(questions):
            if isinstance(item, dict) and _nonempty_string(
                item.get("target_observation_id")
            ) and item["target_observation_id"] not in missing_ids:
                errors.append(
                    f"suggested_questions[{index}].target_observation_id is absent "
                    "from missing_observations"
                )

    if isinstance(facts, list):
        retrieved_fact_ids = {
            item["claim_id"] for item in facts
            if isinstance(item, dict) and _nonempty_string(item.get("claim_id"))
        }
        retrieved_source_ids = {
            item["source_id"] for item in facts
            if isinstance(item, dict) and _nonempty_string(item.get("source_id"))
        }
        if retrieved_fact_ids != fact_ids:
            errors.append(
                "retrieved_facts claim IDs must equal evidence_fact_ids"
            )
        if not retrieved_source_ids.issubset(source_ids):
            errors.append(
                "retrieved_facts source IDs must be present in evidence_source_ids"
            )

    return errors


def ensure_retrieved_context(value: Any) -> RetrievedContext:
    """Return a valid context or raise a path-oriented ``ValueError``."""
    errors = validate_retrieved_context(value)
    if errors:
        raise ValueError("Invalid retrieved context: " + "; ".join(errors))
    return cast(RetrievedContext, value)


def make_retrieved_context(
    *,
    normalized_observations: list[NormalizedObservation],
    candidate_causes: list[str],
    supporting_evidence: list[EvidenceRecord],
    contradicting_evidence: list[EvidenceRecord],
    missing_observations: list[str],
    suggested_questions: list[SuggestedQuestion],
    retrieved_facts: list[RetrievedFact],
    evidence_fact_ids: list[str],
    evidence_source_ids: list[str],
) -> RetrievedContext:
    """Create, isolate, and validate a context in canonical field order."""
    context: RetrievedContext = {
        "normalized_observations": deepcopy(normalized_observations),
        "candidate_causes": deepcopy(candidate_causes),
        "supporting_evidence": deepcopy(supporting_evidence),
        "contradicting_evidence": deepcopy(contradicting_evidence),
        "missing_observations": deepcopy(missing_observations),
        "suggested_questions": deepcopy(suggested_questions),
        "retrieved_facts": deepcopy(retrieved_facts),
        "evidence_fact_ids": deepcopy(evidence_fact_ids),
        "evidence_source_ids": deepcopy(evidence_source_ids),
    }
    return ensure_retrieved_context(context)


def empty_retrieved_context() -> RetrievedContext:
    """Return a fresh empty context; no list is shared across calls."""
    return make_retrieved_context(
        normalized_observations=[],
        candidate_causes=[],
        supporting_evidence=[],
        contradicting_evidence=[],
        missing_observations=[],
        suggested_questions=[],
        retrieved_facts=[],
        evidence_fact_ids=[],
        evidence_source_ids=[],
    )


def encode_retrieved_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and translate a canonical context to its prompt payload."""
    canonical = ensure_retrieved_context(context)
    return {
        RETRIEVAL_WIRE_FIELDS[field]: deepcopy(canonical[field])
        for field in RETRIEVAL_FIELD_ORDER
    }


def decode_retrieved_context(context: Mapping[str, Any]) -> RetrievedContext:
    """Translate wire keys, validate them, and return canonical field order."""
    wire_to_canonical = {
        wire: canonical
        for canonical, wire in RETRIEVAL_WIRE_FIELDS.items()
    }
    decoded: dict[str, Any] = {}
    for key, value in context.items():
        canonical = wire_to_canonical.get(key, key)
        if canonical in decoded:
            raise ValueError(f"Duplicate retrieval field after decoding: {canonical}")
        decoded[canonical] = deepcopy(value)
    validated = ensure_retrieved_context(decoded)
    return cast(
        RetrievedContext,
        {field: deepcopy(validated[field]) for field in RETRIEVAL_FIELD_ORDER},
    )
