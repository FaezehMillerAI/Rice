"""Evaluation-facing adapter over KG retrieval, diagnosis, and metadata."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path

from contracts.retrieval import KGCatalogSnapshot
from engine.retriever import KGRetriever, to_compact_target_response


ROOT = Path(__file__).resolve().parents[1]


class KGAdapter:
    """Narrow evaluation facade over KG retrieval, diagnosis, and metadata."""

    def __init__(self, retriever: KGRetriever | None = None):
        self._retriever = retriever or KGRetriever(str(ROOT))
        self._engine = self._retriever.engine
        self.catalog: KGCatalogSnapshot = self._retriever.catalog_snapshot()
        if not self.catalog["causes"] or not self.catalog["questions"] or not self.catalog["claims"]:
            raise ValueError("KG registries are missing or empty")

    @property
    def retrieval_version(self) -> str:
        return self.catalog["retrieval_version"]

    @property
    def retrieval_contract_version(self) -> str:
        return self._retriever.contract_version

    def retrieve(self, public: dict, top_k_candidates: int, top_k_questions: int) -> dict:
        return self._retriever.retrieve(deepcopy(public), top_k_candidates, top_k_questions)

    def diagnose(
        self, public: dict, top_k_candidates: int = 3, top_k_questions: int = 3,
        *, family_id: str | None = None,
    ) -> tuple[dict, dict]:
        fields = self._retriever.extract_case_fields(public)
        context = {"growth_stage": fields["growth_stage"], "region": public.get("region_id")}
        if family_id is not None:
            if not isinstance(family_id, str) or not family_id.strip():
                raise ValueError("family_id must be a nonempty string")
            context["case_id"] = family_id
        verbose = self._engine.diagnose(
            fields["user_text"],
            context=context,
            explicit_obs=fields["explicit_obs"],
        )
        # Apply the same output budgets as the context supplied to KG+model.
        # Keep the engine's decision and scoring rules unchanged.
        compact_input = deepcopy(verbose)
        states = self._engine.normalize_observations(fields["user_text"], fields["explicit_obs"])
        questions = self._engine.rank_questions(verbose["differential"], states)
        compact_input["observations_needed"] = [
            {key: q[key] for key in ("question_id", "question", "reason", "priority")}
            for q in questions[:top_k_questions]
        ]
        compact_input["differential"] = verbose["differential"][:top_k_candidates]
        return to_compact_target_response(compact_input), verbose


def dataset_audit(cases: list[dict], kg: KGAdapter) -> dict:
    def coverage(field, known):
        ids = [item for case in cases for item in case["annotations"][field]]
        unique = set(ids)
        known = set(known)
        return {
            "unique_gold_ids": len(unique), "covered_unique_ids": len(unique & known),
            "gold_id_occurrences": len(ids), "covered_occurrences": sum(x in known for x in ids),
            "missing_ids": sorted(unique - known),
        }

    catalog = kg.catalog
    fact_ids = set(catalog["evidence_sources_by_fact"])
    source_ids = set(catalog["evidence_sources_by_fact"].values())
    quality_flags_available = any("quality_flags" in case["annotations"] for case in cases)
    return {
        "cases": len(cases), "origins": dict(Counter(case.get("origin", "unknown") for case in cases)),
        "schema_versions": dict(Counter(case.get("schema_version", "unspecified") for case in cases)),
        "quality_flags_available": quality_flags_available,
        "quality_flag_counts": dict(Counter(flag for case in cases for flag in case["annotations"].get("quality_flags", []))) if quality_flags_available else None,
        "quality_flagged_case_ids": [case["scenario_id"] for case in cases if case["annotations"].get("quality_flags")] if quality_flags_available else None,
        "first_behavior_counts": dict(Counter(case["annotations"]["correct_first_behavior"] for case in cases)),
        "differential_registry_coverage": coverage("acceptable_differential", catalog["causes"]),
        "question_registry_coverage": coverage("required_questions", catalog["questions"]),
        "fact_registry_coverage": coverage("supporting_fact_ids", fact_ids),
        "source_registry_coverage": coverage("supporting_source_ids", source_ids),
    }
