"""Offline field gateway for the tuned Ollama model with KG fallback.

The model path uses the same prompt builder and strict compact response contract
as the unified evaluator.  Invalid output is never repaired: it triggers the
deterministic KG fallback, which is converted to that same compact contract.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any, Callable
import urllib.error
import urllib.request

from contracts.response import (
    RESPONSE_CONTRACT_VERSION,
    RESPONSE_JSON_SCHEMA,
    parse_response,
    prepare_prediction_input,
    validate_response,
)
from contracts.retrieval import (
    ExplicitObservation,
    RETRIEVAL_CONTRACT_VERSION,
    ensure_explicit_observations,
)
from engine.retriever import KGRetriever, to_compact_target_response
from engine.diagnostic_engine import DiagnosticEngine
from engine.prompting import (
    SYSTEM_PROMPT_VERSION,
    build_prompt,
    select_public_case,
)
from engine.verifier import VerificationEngine


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "rice-salm:latest"


class HybridFieldEngine:
    """Run the tuned edge model and fall back only when runtime checks fail."""

    def __init__(
        self,
        ollama_model: str | None = None,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        timeout_seconds: float = 120,
        *,
        kg_only: bool = False,
        kg_engine: DiagnosticEngine | None = None,
        retriever: KGRetriever | None = None,
        verifier: VerificationEngine | None = None,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self.ollama_model = (
            ollama_model
            or os.environ.get("RICE_OLLAMA_MODEL")
            or DEFAULT_OLLAMA_MODEL
        )
        self.ollama_url = ollama_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.kg_only = kg_only
        self.kg_engine = kg_engine or DiagnosticEngine(str(WORKSPACE_ROOT))
        self.retriever = retriever or KGRetriever(str(WORKSPACE_ROOT))
        self.verifier = verifier or VerificationEngine(str(WORKSPACE_ROOT))
        self._urlopen = urlopen or urllib.request.urlopen
        self.ollama_digest: str | None = None

    def _request(self, route: str, payload: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.ollama_url + route,
            data=(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload is not None
                else None
            ),
            headers={"Content-Type": "application/json"},
        )
        try:
            with self._urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama {route}: HTTP {exc.code}: {body}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Ollama {route} request failed: {exc}") from exc
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError(
                f"Ollama {route} returned invalid API JSON: {exc}"
            ) from exc
        if not isinstance(result, dict) or result.get("error"):
            raise RuntimeError(f"Ollama {route} returned an API error: {result}")
        return result

    def check_ollama_model(self) -> dict[str, Any]:
        """Require the configured tuned tag; never pull or substitute a base tag."""
        version = self._request("/api/version")
        models = self._request("/api/tags").get("models", [])
        if not isinstance(models, list):
            raise RuntimeError("Ollama /api/tags returned a non-list models field")
        entry = next(
            (
                item
                for item in models
                if isinstance(item, dict)
                and item.get("name", item.get("model")) == self.ollama_model
            ),
            None,
        )
        if entry is None:
            installed = [
                item.get("name", item.get("model"))
                for item in models
                if isinstance(item, dict)
            ]
            raise RuntimeError(
                f"Ollama model {self.ollama_model!r} is not installed; "
                f"available tags: {installed}. No model was pulled or substituted."
            )
        details = self._request("/api/show", {"model": self.ollama_model})
        self.ollama_digest = entry.get("digest")
        return {
            "server_version": version.get("version"),
            "model": self.ollama_model,
            "digest": self.ollama_digest,
            "details": details.get("details"),
        }

    @staticmethod
    def _public_case(user_utterance: str, context: dict[str, Any]) -> dict:
        stage = context.get("growth_stage_id") or context.get("growth_stage")
        if isinstance(stage, str) and stage and not stage.startswith("growth_stage:"):
            stage = f"growth_stage:{stage}"
        case = {
            "input": {
                "user_text": user_utterance,
                "growth_stage_id": stage,
                "production_system_id": context.get("production_system_id"),
                "cultivar_id": context.get("cultivar_id") or context.get("variety"),
            },
            "language": context.get("language", "en"),
            "region_id": context.get("region_id") or context.get("region"),
        }
        return select_public_case(case)

    def _check_for_delivery(
        self,
        response: dict,
    ) -> dict[str, Any]:
        """Apply the response contract, then the maintained deployment verifier."""
        contract_errors = validate_response(response)
        errors = list(contract_errors)
        verifier_report = self.verifier.verify_all(response)
        if verifier_report.get("passed") is not True:
            verifier_errors = verifier_report.get("errors") or [
                "Deployment verifier rejected the response"
            ]
            errors.extend(str(error) for error in verifier_errors)
        return {
            "allowed": not errors,
            "errors": errors,
            "contract": {"passed": not contract_errors, "errors": contract_errors},
            "verifier": verifier_report,
        }

    def _query_edge_slm(
        self,
        user_utterance: str,
        context: dict[str, Any],
        explicit_observations: list[ExplicitObservation],
    ) -> tuple[dict, float, dict, dict, str]:
        public_case = self._public_case(user_utterance, context)
        retrieval_input = {
            **public_case,
            "explicit_observations": explicit_observations,
        }
        retrieval = self.retriever.retrieve(retrieval_input)
        messages = build_prompt(public_case, retrieval)
        payload = {
            "model": self.ollama_model,
            "system": messages[0]["content"],
            "prompt": messages[1]["content"],
            "stream": False,
            "format": RESPONSE_JSON_SCHEMA,
            "think": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "seed": 42,
                "num_ctx": 4608,
                "num_predict": 512,
            },
        }
        started = time.perf_counter()
        api_response = self._request("/api/generate", payload)
        latency = time.perf_counter() - started
        raw_text = api_response.get("response")
        if not isinstance(raw_text, str) or api_response.get("done") is False:
            raise RuntimeError("Ollama returned a missing or incomplete response")
        normalized, normalization = prepare_prediction_input(raw_text)
        parsed, parse_errors = parse_response(normalized)
        if parse_errors or parsed is None:
            raise RuntimeError("; ".join(parse_errors))
        delivery_checks = self._check_for_delivery(parsed)
        if not delivery_checks["allowed"]:
            raise RuntimeError("; ".join(delivery_checks["errors"]))
        inference = {
            "prompt_tokens": api_response.get("prompt_eval_count"),
            "generated_tokens": api_response.get("eval_count"),
            "done_reason": api_response.get("done_reason"),
            "retrieval_version": self.retriever.version,
            "retrieval_contract_version": getattr(
                self.retriever,
                "contract_version",
                RETRIEVAL_CONTRACT_VERSION,
            ),
            "response_contract_version": RESPONSE_CONTRACT_VERSION,
            "system_prompt_version": SYSTEM_PROMPT_VERSION,
            "normalization": normalization,
        }
        return parsed, latency, delivery_checks, inference, raw_text

    def _kg_fallback(
        self,
        farmer_utterance: str,
        context: dict[str, Any],
        explicit_observations: list[ExplicitObservation],
    ) -> tuple[dict, float, dict]:
        started = time.perf_counter()
        verbose = self.kg_engine.diagnose(
            farmer_utterance,
            context,
            explicit_observations,
        )
        compact = to_compact_target_response(verbose)
        latency = time.perf_counter() - started
        delivery_checks = self._check_for_delivery(compact)
        return compact, latency, delivery_checks

    def diagnose(
        self,
        farmer_utterance: str,
        context: dict[str, Any] | None = None,
        explicit_observations: list[ExplicitObservation] | None = None,
    ) -> dict[str, Any]:
        """Try the tuned model, then return a compact KG fallback."""
        context = dict(context or {})
        context.setdefault("growth_stage", "tillering")
        context.setdefault("region", "priority-region-1")
        explicit_observations = ensure_explicit_observations(
            explicit_observations
        )

        model_error: str | None = "Explicit KG-only mode" if self.kg_only else None
        if not self.kg_only:
            try:
                response, latency, delivery_checks, inference, raw_output = self._query_edge_slm(
                    farmer_utterance,
                    context,
                    explicit_observations,
                )
                return {
                    "engine_used": "edge_slm",
                    "model_version": self.ollama_model,
                    "model_digest": self.ollama_digest,
                    "latency_ms": round(latency * 1000, 1),
                    "fallback_triggered": False,
                    "fallback_reason": None,
                    "contract_validation": delivery_checks["contract"],
                    "verification": delivery_checks["verifier"],
                    "inference": inference,
                    "raw_output": raw_output,
                    "diagnostic_payload": response,
                }
            except Exception as exc:  # Runtime boundary intentionally triggers fallback.
                model_error = f"SLM runtime/delivery-check failure: {exc}"

        compact, latency, delivery_checks = self._kg_fallback(
            farmer_utterance,
            context,
            explicit_observations,
        )
        return {
            "engine_used": "kg_deterministic" if self.kg_only else "kg_deterministic_fallback",
            "model_version": "baseline0_graph_engine_v1.0",
            "model_digest": None,
            "latency_ms": round(latency * 1000, 1),
            "fallback_triggered": not self.kg_only,
            "fallback_reason": model_error,
            "contract_validation": delivery_checks["contract"],
            "verification": delivery_checks["verifier"],
            "inference": {
                "retrieval_version": self.retriever.version,
                "retrieval_contract_version": getattr(
                    self.retriever,
                    "contract_version",
                    RETRIEVAL_CONTRACT_VERSION,
                ),
                "response_contract_version": RESPONSE_CONTRACT_VERSION,
                "system_prompt_version": SYSTEM_PROMPT_VERSION,
            },
            "raw_output": None,
            "diagnostic_payload": compact,
        }
