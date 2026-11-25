"""
Rice Pathogen SALM — Knowledge Graph Engine, Retriever & Verifier Package
Provides canonical functions to ground, contextualize, and verify SLM diagnostic reasoning.
"""

from contracts.retrieval import (
    PublicCase,
    PublicInput,
    RetrievedContext,
    empty_retrieved_context,
)
from .diagnostic_engine import DiagnosticEngine, diagnose
from .retriever import (
    KGRetriever,
    retrieve_kg,
    format_slm_prompt_context,
    to_compact_target_response,
)


__all__ = [
    "DiagnosticEngine",
    "KGRetriever",
    "PublicCase",
    "PublicInput",
    "RetrievedContext",
    "VerificationEngine",
    "diagnose",
    "empty_retrieved_context",
    "format_slm_prompt_context",
    "retrieve_kg",
    "to_compact_target_response",
    "verify_slm_output",
]


def __getattr__(name: str):
    """Load deployment verification only when a caller explicitly requests it.

    Training and evaluation import the ``engine`` package as part of loading the
    retriever.  Keeping verifier exports lazy prevents that unrelated workflow
    from depending on a separately maintained deployment component.
    """
    if name in {"VerificationEngine", "verify_slm_output"}:
        from .verifier import VerificationEngine, verify_slm_output

        return {
            "VerificationEngine": VerificationEngine,
            "verify_slm_output": verify_slm_output,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
