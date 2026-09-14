import json
import re
import time
import urllib.request
from typing import Dict, List, Any, Optional, Tuple

def query_ollama(prompt: str, system_prompt: str = "", model_name: str = "qwen2.5:1.5b", timeout: int = 40) -> Tuple[Dict[str, Any], float, int]:
    """Queries live local Ollama endpoint and returns (parsed_json, latency_seconds, token_count)."""
    url = "http://127.0.0.1:11434/api/generate"
    full_prompt = f"{system_prompt}\n\nUser Query: {prompt}" if system_prompt else prompt
    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "top_p": 0.9
        }
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    start_t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            latency = time.time() - start_t
            raw_text = res_data.get("response", "{}")
            eval_count = res_data.get("eval_count", len(raw_text.split()))
            try:
                parsed = json.loads(raw_text)
            except Exception:
                # Try extracting json snippet if model wrapped in markdown
                match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                else:
                    parsed = {"error": "JSON parse error", "raw": raw_text}
            return parsed, latency, eval_count
    except Exception as e:
        latency = time.time() - start_t
        return {"error": str(e), "raw": "{}"}, latency, 0

class Baseline1Untuned:
    """
    Phase 7.2: Baseline 1 (Live Multi-Model Untuned SLM Without Retrieval)
    Supports zero_shot and 1shot_exemplar prompt strategies.
    """

    def __init__(self, model_name: str = "qwen2.5:1.5b", strategy: str = "zero_shot"):
        self.model_name = model_name
        self.strategy = strategy

    def generate_response(self, user_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if context is None:
            context = {"growth_stage": "tillering", "region": "priority-region-1"}

        case_id = context.get("case_id", "case-slm-b1-live")

        if self.strategy == "1shot_exemplar":
            system_prompt = """You are a rice crop diagnostic AI. Output strictly valid JSON matching schemas/response.schema.json.
Example format:
{
  "case_id": "case-demo",
  "status": "needs_more_information",
  "normalized_observations": { "growth_stage": "tillering", "affected_part": ["part:leaf"], "symptoms": ["symptom:leaf_yellowing"], "distribution": "field:patchy_distribution", "recent_conditions": [], "region": "priority-region-1" },
  "observations_needed": [ { "question_id": "q:q_lesion_margin", "question": "Are there wavy lesions on leaf margins?", "reason": "Distinguishes BLB.", "priority": 1 } ],
  "differential": [ { "cause_id": "disease:bacterial_leaf_blight", "display_name": "Bacterial leaf blight", "cause_type": "pathogen", "score": 6, "confidence_band": "medium", "supporting_observations": ["symptom:leaf_yellowing"], "contradicting_observations": [], "missing_distinguishing_observations": ["obs:lesion_margin_shape"], "distinguishing_checks": ["Check lesion edge"], "rank": 1 } ],
  "recommended_actions": [ { "action_id": "action:avoid_excess_nitrogen", "priority": 1, "action": "Avoid excess nitrogen fertilizer.", "action_type": "cultural" } ],
  "escalation": { "required": false, "triggers": [], "refer_to": null },
  "grounding": [],
  "safety_flags": ["PRINCIPLE_ACTIONS_ONLY_NO_CHEMICAL_DOSAGES"]
}
Never recommend commercial pesticide brands or dosage rates. Return pure JSON only."""
        else:
            system_prompt = """You are a rice crop diagnostic language model. Output strictly valid JSON with root fields: case_id, status, normalized_observations, observations_needed, differential, recommended_actions, escalation, grounding, safety_flags. Status must be one of: "needs_more_information", "differential_available", "high_risk_escalation", "insufficient_evidence". Do NOT include preamble."""

        prompt = f"Case ID: {case_id}\nContext: Growth stage: {context.get('growth_stage')}, Region: {context.get('region')}\nFarmer Input: {user_text}"
        
        raw_json, latency, token_count = query_ollama(prompt, system_prompt, self.model_name)
        
        if not isinstance(raw_json, dict) or "error" in raw_json:
            return {
                "case_id": case_id,
                "status": "insufficient_evidence",
                "normalized_observations": {},
                "observations_needed": [],
                "differential": [],
                "recommended_actions": [],
                "escalation": {"required": False, "triggers": [], "refer_to": None},
                "grounding": [],
                "safety_flags": ["RAW_MODEL_PARSE_ERROR"],
                "_meta": {"latency_sec": latency, "tokens": token_count, "model": self.model_name, "strategy": self.strategy}
            }

        raw_json["case_id"] = case_id
        if "differential" not in raw_json or not isinstance(raw_json["differential"], list):
            raw_json["differential"] = []
        if "recommended_actions" not in raw_json or not isinstance(raw_json["recommended_actions"], list):
            raw_json["recommended_actions"] = []
        if "escalation" not in raw_json or not isinstance(raw_json["escalation"], dict):
            raw_json["escalation"] = {"required": False, "triggers": [], "refer_to": None}
        if "grounding" not in raw_json or not isinstance(raw_json["grounding"], list):
            raw_json["grounding"] = []
        if "safety_flags" not in raw_json or not isinstance(raw_json["safety_flags"], list):
            raw_json["safety_flags"] = []
        if "observations_needed" not in raw_json or not isinstance(raw_json["observations_needed"], list):
            raw_json["observations_needed"] = []

        raw_json["_meta"] = {"latency_sec": latency, "tokens": token_count, "model": self.model_name, "strategy": self.strategy}
        return raw_json


class Baseline2RAG:
    """
    Phase 7.3: Baseline 2 (Live Multi-Model SLM with Graph & Document Retrieval)
    Supports dense_rag and compact_contrast_rag prompt strategies.
    """

    def __init__(self, workspace_root: str = "/Users/faezeh/Desktop/Rice", model_name: str = "qwen2.5:1.5b", strategy: str = "compact_contrast_rag"):
        self.workspace_root = workspace_root
        self.model_name = model_name
        self.strategy = strategy

    def generate_response(self, user_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if context is None:
            context = {"growth_stage": "tillering", "region": "priority-region-1"}

        case_id = context.get("case_id", "case-slm-b2-live")

        if self.strategy == "compact_contrast_rag":
            # Compact Contrast Prompt optimized for sub-2B edge models
            system_prompt = """You are a rice crop diagnostic AI grounded by a verified Knowledge Graph.
Allowed Candidates: 'disease:bacterial_leaf_blight', 'disorder:nitrogen_deficiency', 'disorder:water_stress'.
Distinguishing Checks:
- BLB vs N-Def: BLB has wavy margin lesions ('obs:lesion_margin_shape') and milky water ooze stream ('obs:bacterial_ooze_test'). N-Def has uniform yellowing starting on oldest lower leaves ('obs:leaf_age_progression').
- BLB vs Water Stress: Water stress has inward leaf rolling ('obs:leaf_rolling_folding') that unrolls after water.
Rule: If lesion shape or ooze sign is missing/unknown, set status to "needs_more_information", ask 'q:q_lesion_margin' or 'q:q_older_vs_younger'.
Never prescribe commercial pesticide brand names or chemical dosages. Ground diagnoses using 'claim:claim_blb_001' or 'claim:claim_ndef_001'.
Output valid JSON matching response.schema.json."""
            kg_context = "Knowledge Base: BLB (wavy lesions, heavy rain, standing water), Nitrogen Deficiency (uniform lower leaves, no lesions), Water Stress (inward leaf roll)."
        else:
            # Dense full RAG prompt
            system_prompt = """You are a rice crop diagnostic language model grounded by an authoritative Knowledge Graph.
Allowed Diseases: 'disease:bacterial_leaf_blight', 'disorder:nitrogen_deficiency', 'disorder:water_stress'.
Output valid JSON adhering to schemas/response.schema.json."""
            kg_context = """Knowledge Graph Context:
- Triples:
  * disease:bacterial_leaf_blight presentsAs symptom:water_soaked_wavy_lesion, favoredBy env:heavy_rainfall, favoredBy env:standing_water, hasFieldDistribution field:patchy_distribution
  * disorder:nitrogen_deficiency presentsAs symptom:uniform_older_leaf_chlorosis, hasFieldDistribution field:uniform_fieldwide_distribution
  * disorder:water_stress presentsAs symptom:leaf_rolling_folding, favoredBy env:drought_conditions
- Contrasts:
  * contrast:blb_vs_nitrogen_deficiency differentiatedBy obs:lesion_margin_shape, obs:leaf_age_progression
  * contrast:blb_vs_water_stress differentiatedBy obs:leaf_rolling_folding
- Questions:
  * q:q_lesion_margin ("Are there visible yellow/brown wavy lesions at leaf margins?")
  * q:q_older_vs_younger ("Are lowest older leaves chlorosing uniformly first?")
- Claims: claim:claim_blb_001 (IRRI Rice Doctor Symptoms), claim:claim_ndef_001 (IRRI Nutrient Disorders)"""

        prompt = f"Case ID: {case_id}\nContext: Growth stage: {context.get('growth_stage')}, Region: {context.get('region')}\n{kg_context}\nFarmer Input: {user_text}"
        
        raw_json, latency, token_count = query_ollama(prompt, system_prompt, self.model_name)
        
        if not isinstance(raw_json, dict) or "error" in raw_json:
            return {
                "case_id": case_id,
                "status": "insufficient_evidence",
                "normalized_observations": {},
                "observations_needed": [],
                "differential": [],
                "recommended_actions": [],
                "escalation": {"required": False, "triggers": [], "refer_to": None},
                "grounding": [],
                "safety_flags": ["RAW_MODEL_PARSE_ERROR"],
                "_meta": {"latency_sec": latency, "tokens": token_count, "model": self.model_name, "strategy": self.strategy}
            }

        raw_json["case_id"] = case_id
        if "differential" not in raw_json or not isinstance(raw_json["differential"], list):
            raw_json["differential"] = []
        if "recommended_actions" not in raw_json or not isinstance(raw_json["recommended_actions"], list):
            raw_json["recommended_actions"] = []
        if "escalation" not in raw_json or not isinstance(raw_json["escalation"], dict):
            raw_json["escalation"] = {"required": False, "triggers": [], "refer_to": None}
        if "grounding" not in raw_json or not isinstance(raw_json["grounding"], list):
            raw_json["grounding"] = []
        if "safety_flags" not in raw_json or not isinstance(raw_json["safety_flags"], list):
            raw_json["safety_flags"] = []
        if "observations_needed" not in raw_json or not isinstance(raw_json["observations_needed"], list):
            raw_json["observations_needed"] = []

        raw_json["_meta"] = {"latency_sec": latency, "tokens": token_count, "model": self.model_name, "strategy": self.strategy}
        return raw_json
