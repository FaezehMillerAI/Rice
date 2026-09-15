"""
field_app/hybrid_engine.py
Rice Pathogen SALM — Hybrid Offline Field Diagnostic Gateway (Step 21.1)
Combines Quantized Edge SLM with Deterministic Knowledge Graph Fallback Engine.
"""

import json
import os
import sys
import time
import urllib.request
from typing import Dict, Any, Optional, List, Tuple

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, WORKSPACE_ROOT)

from engine.diagnostic_engine import DiagnosticEngine
from engine.verifier import VerificationEngine

class HybridFieldEngine:
    def __init__(
        self,
        ollama_model: str = "qwen2.5:1.5b",
        ollama_endpoint: str = "http://127.0.0.1:11434/api/generate",
        timeout_seconds: int = 15
    ):
        self.ollama_model = ollama_model
        self.ollama_endpoint = ollama_endpoint
        self.timeout_seconds = timeout_seconds
        
        self.verifier = VerificationEngine(WORKSPACE_ROOT)
        self.kg_engine = DiagnosticEngine(WORKSPACE_ROOT)

    def _query_edge_slm(self, user_utterance: str, context: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
        full_prompt = f"Context: {json.dumps(context, ensure_ascii=False)}\n\nFarmer Query: {user_utterance}"
        payload = {
            "model": self.ollama_model,
            "prompt": full_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_ctx": 2048
            }
        }
        
        t0 = time.time()
        req = urllib.request.Request(
            self.ollama_endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            latency = time.time() - t0
            raw_text = res_data.get("response", "{}")
            parsed = json.loads(raw_text)
            return parsed, latency

    def diagnose(
        self,
        farmer_utterance: str,
        context: Optional[Dict[str, Any]] = None,
        explicit_observations: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Executes primary SLM diagnostic inference with automatic fallback to KG Baseline 0.
        """
        if context is None:
            context = {"growth_stage": "tillering", "region": "priority-region-1"}
        if explicit_observations is None:
            explicit_observations = []

        # Step 1: Attempt Edge SLM
        slm_error = None
        slm_response = None
        latency_slm = 0.0
        
        try:
            slm_response, latency_slm = self._query_edge_slm(farmer_utterance, context)
            
            # Step 2: 4-Layer Post-Generation Verification
            s_ok, s_err = self.verifier.verify_structural(slm_response)
            saf_ok, saf_err = self.verifier.verify_safety(slm_response)
            g_ok, g_err = self.verifier.verify_graph(slm_response)
            l_ok, l_err = self.verifier.verify_logical(slm_response)
            
            all_passed = s_ok and saf_ok and g_ok and l_ok
            if all_passed:
                return {
                    "engine_used": "edge_slm",
                    "model_version": self.ollama_model,
                    "latency_ms": round(latency_slm * 1000, 1),
                    "fallback_triggered": False,
                    "verification": {
                        "passed": True,
                        "structural": s_ok,
                        "safety": saf_ok,
                        "graph": g_ok,
                        "logical": l_ok
                    },
                    "diagnostic_payload": slm_response
                }
            else:
                err_list = []
                if not s_ok: err_list.append(f"Structural: {s_err}")
                if not saf_ok: err_list.append(f"Safety: {saf_err}")
                if not g_ok: err_list.append(f"Graph: {g_err}")
                if not l_ok: err_list.append(f"Logical: {l_err}")
                slm_error = "Verification failed: " + "; ".join(err_list)
        except Exception as e:
            slm_error = f"SLM runtime exception: {str(e)}"

        # Step 3: Trigger Deterministic KG Fallback (Baseline 0)
        t_fallback_start = time.time()
        kg_response = self.kg_engine.diagnose(farmer_utterance, context, explicit_observations)
        latency_kg = time.time() - t_fallback_start

        return {
            "engine_used": "kg_deterministic_fallback",
            "model_version": "baseline0_graph_engine_v1.0",
            "latency_ms": round(latency_kg * 1000, 1),
            "fallback_triggered": True,
            "fallback_reason": slm_error,
            "verification": {
                "passed": True,
                "structural": True,
                "safety": True,
                "graph": True,
                "logical": True
            },
            "diagnostic_payload": kg_response
        }
