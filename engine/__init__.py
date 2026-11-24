"""
Rice Pathogen SALM — Knowledge Graph Engine, Retriever & Verifier Package
Provides canonical functions to ground, contextualize, and verify SLM diagnostic reasoning.
"""

from .diagnostic_engine import DiagnosticEngine, diagnose
from .retriever import (
    KGRetriever,
    PublicCase,
    PublicInput,
    RetrievedContext,
    empty_retrieved_context,
    retrieve_kg,
    format_slm_prompt_context,
    to_compact_target_response,
)
from .verifier import (
    VerificationEngine,
    verify_slm_output,
)
