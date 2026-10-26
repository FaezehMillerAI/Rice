"""
engine/retriever.py
Rice Pathogen SALM — Knowledge Graph Context Retriever (retrieve_kg)
Provides canonical retrieval from the Rice Knowledge Graph for SFT fine-tuning and inference.
"""

import os
import sys
from typing import Dict, List, Any, Optional, Union

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from engine.diagnostic_engine import DiagnosticEngine

class KGRetriever:
    """Retrieves subgraph context, candidate differential rankings, and evidence receipts."""

    def __init__(self, workspace_root: str = WORKSPACE_ROOT):
        self.workspace_root = workspace_root
        self.engine = DiagnosticEngine(workspace_root)
        self.richard_facts = {}
        rf_path = os.path.join(workspace_root, "data/scenarios/richard_facts_839.json")
        if os.path.exists(rf_path):
            try:
                import json
                with open(rf_path, "r", encoding="utf-8") as f:
                    self.richard_facts = json.load(f)
            except Exception:
                self.richard_facts = {}

    def extract_case_fields(self, case_info: Union[Dict[str, Any], str]) -> Dict[str, Any]:
        """Extracts normalized user_text and growth_stage from various input formats."""
        if isinstance(case_info, str):
            return {
                "user_text": case_info,
                "growth_stage": "tillering",
                "explicit_obs": []
            }

        user_text = ""
        growth_stage = "tillering"
        explicit_obs = []

        # Format A: Nested input object (Dr. Srikanth's / Colleague's schema)
        # {"input": {"user_text": "...", "growth_stage_id": "growth_stage:heading", ...}}
        if "input" in case_info and isinstance(case_info["input"], dict):
            inp = case_info["input"]
            user_text = inp.get("user_text", "")
            stage_id = inp.get("growth_stage_id") or ""
            if stage_id.startswith("growth_stage:"):
                growth_stage = stage_id.replace("growth_stage:", "")
            elif stage_id:
                growth_stage = stage_id

        # Format B: Flat dictionary or scenario schema
        if not user_text:
            user_text = (
                case_info.get("user_text") or
                case_info.get("farmer_utterance") or
                case_info.get("query") or
                ""
            )

        if "growth_stage" in case_info:
            growth_stage = case_info["growth_stage"]
        elif "context" in case_info and isinstance(case_info["context"], dict):
            ctx = case_info["context"]
            growth_stage = ctx.get("growth_stage", growth_stage) or growth_stage

        if "explicit_observations" in case_info:
            explicit_obs = case_info["explicit_observations"]

        return {
            "user_text": user_text,
            "growth_stage": growth_stage,
            "explicit_obs": explicit_obs
        }

    def retrieve(
        self,
        case_info: Union[Dict[str, Any], str],
        top_k_candidates: int = 3,
        top_k_questions: int = 3
    ) -> Dict[str, Any]:
        """
        Retrieves relevant KG context matching the fine-tuning prompt template:
        {
            "observations": [...],
            "candidates": [...],
            "missing_checks": [...],
            "graph_context": {...},
            "evidence_fact_ids": [...],
            "evidence_source_ids": [...]
        }
        """
        fields = self.extract_case_fields(case_info)
        user_text = fields["user_text"]
        growth_stage = fields["growth_stage"]
        explicit_obs = fields["explicit_obs"]

        # 1. Normalize Observations from raw text using KG terminology registry
        obs_state_map = self.engine.normalize_observations(user_text, explicit_obs)
        if growth_stage and f"stage:{growth_stage}" not in obs_state_map:
            obs_state_map[f"stage:{growth_stage}"] = "TRUE"

        # List of confirmed active observations
        active_observations = [k for k, v in obs_state_map.items() if v == "TRUE"]

        # 2. Score Candidates under 3VL Open-World Assumption
        scored_candidates = self.engine.score_candidates(obs_state_map, growth_stage)
        top_candidates = scored_candidates[:top_k_candidates]
        candidate_ids = [c["cause_id"] for c in top_candidates]

        # 3. Retrieve Missing Distinguishing Checks & Ranked Questions
        needed_questions = self.engine.rank_questions(scored_candidates, obs_state_map)
        missing_checks = [q["question_id"] for q in needed_questions[:top_k_questions]]

        # 4. Construct Subgraph Context for Candidates
        graph_context = {}
        for c in top_candidates:
            cid = c["cause_id"]
            dis_info = self.engine.diseases.get(cid, {})
            supporting_rules = [
                r["observation_id"] for r in self.engine.evidence_rules
                if r["cause_id"] == cid and r.get("evidence_type", "").lower() == "supporting"
            ]
            contradicting_rules = [
                r["observation_id"] for r in self.engine.evidence_rules
                if r["cause_id"] == cid and r.get("evidence_type", "").lower() == "contradicting"
            ]

            graph_context[cid] = {
                "canonical_name": dis_info.get("canonical_name", cid),
                "type": dis_info.get("type", "pathogen"),
                "category": dis_info.get("category", ""),
                "supporting_symptoms": supporting_rules,
                "contradicting_symptoms": contradicting_rules,
                "distinguishing_checks": c.get("distinguishing_checks", [])
            }

        # 5. Retrieve Evidence Provenance Fact IDs and Source IDs
        evidence_fact_ids = []
        evidence_source_ids = []

        # First check Richard's 839 real facts
        if self.richard_facts:
            # Map candidate IDs to normalized disease keywords
            candidate_keywords = []
            for cid in candidate_ids:
                clean = cid.split(":")[-1].replace("_", " ")
                candidate_keywords.append(clean)

            # Match facts that correlate with candidate causes and observations
            for fid, fval in self.richard_facts.items():
                f_dis = fval.get("disease", "").lower()
                f_stmt = fval.get("statement", "").lower()
                f_src = fval.get("source_id", "")

                dis_match = any(kw in f_dis or f_dis in kw for kw in candidate_keywords)
                if dis_match:
                    # Check if statement mentions any active observation or key term
                    obs_match = any(
                        obs.split(":")[-1].replace("_", " ") in f_stmt
                        for obs in active_observations
                    )
                    if obs_match or len(evidence_fact_ids) < 4:
                        if fid not in evidence_fact_ids:
                            evidence_fact_ids.append(fid)
                        if f_src and f_src not in evidence_source_ids:
                            evidence_source_ids.append(f_src)

                if len(evidence_fact_ids) >= 10:
                    break

        # Fallback / supplement with engine claims
        for claim_id, row in self.engine.claims.items():
            subj = row.get("subject_uri", "")
            obj = row.get("object_uri", "")
            src = row.get("source_id", "")

            # Link claim if it describes any candidate or matches extracted observation
            if subj in candidate_ids or obj in obs_state_map:
                if claim_id not in evidence_fact_ids:
                    evidence_fact_ids.append(claim_id)
                if src and src not in evidence_source_ids:
                    evidence_source_ids.append(src)

        if not evidence_source_ids:
            evidence_source_ids = ["SOURCE_001"]

        return {
            # Fei's template keys
            "observations": active_observations,
            "candidates": candidate_ids,
            "missing_checks": missing_checks,
            "graph_context": graph_context,
            "evidence_fact_ids": evidence_fact_ids,
            "evidence_source_ids": evidence_source_ids,
            # Srikanth's Excalidraw Section 5 alias keys
            "normalized_observations": active_observations,
            "candidate_causes": candidate_ids,
            "missing_observations": missing_checks,
            "suggested_questions": missing_checks
        }

# Global singleton helper
_DEFAULT_RETRIEVER = None

def retrieve_kg(
    case_info: Union[Dict[str, Any], str],
    top_k_candidates: int = 3,
    top_k_questions: int = 3,
    workspace_root: str = WORKSPACE_ROOT
) -> Dict[str, Any]:
    """
    Public API: Retrieves relevant Knowledge Graph context for a given case.
    
    Args:
        case_info: Case dictionary containing user_text and context, or raw query string.
        top_k_candidates: Number of top candidate causes to retrieve.
        top_k_questions: Number of top distinguishing question checks to retrieve.
        workspace_root: Optional root directory of the Rice project.
        
    Returns:
        Dictionary with keys:
            - observations: List[str]
            - candidates: List[str]
            - missing_checks: List[str]
            - graph_context: Dict[str, Any]
            - evidence_fact_ids: List[str]
            - evidence_source_ids: List[str]
    """
    global _DEFAULT_RETRIEVER
    if _DEFAULT_RETRIEVER is None or _DEFAULT_RETRIEVER.workspace_root != workspace_root:
        _DEFAULT_RETRIEVER = KGRetriever(workspace_root)
    return _DEFAULT_RETRIEVER.retrieve(
        case_info,
        top_k_candidates=top_k_candidates,
        top_k_questions=top_k_questions
    )

def to_compact_target_response(response: Dict[str, Any], user_response: Optional[str] = None) -> Dict[str, Any]:
    """
    Converts a verbose DiagnosticEngine response into the compact SFT target schema:
    {
        "status": "needs_more_information" | "provisional_assessment" | "escalation_required",
        "observations_needed": List[str],  # Question IDs
        "differential": List[str],        # Cause IDs
        "actions": List[str],             # Action strings
        "escalation_required": bool,
        "grounding": List[str],           # Fact/claim IDs
        "safety_flags": List[str]
    }
    """
    raw_status = response.get("status", "needs_more_information")
    if raw_status == "differential_available":
        compact_status = "provisional_assessment"
    elif raw_status == "high_risk_escalation":
        compact_status = "escalation_required"
    else:
        compact_status = "needs_more_information"

    esc_dict = response.get("escalation", {})
    escalation_required = esc_dict.get("required", False) if isinstance(esc_dict, dict) else bool(esc_dict)
    if escalation_required:
        compact_status = "escalation_required"

    observations_needed = [
        q["question_id"] if isinstance(q, dict) else str(q)
        for q in response.get("observations_needed", [])
    ]

    differential = [
        d["cause_id"] if isinstance(d, dict) else str(d)
        for d in response.get("differential", [])
    ]

    actions = [
        a["action"] if isinstance(a, dict) else str(a)
        for a in response.get("recommended_actions", [])
    ]

    grounding = [
        g["claim_id"] if isinstance(g, dict) else str(g)
        for g in response.get("grounding", [])
    ]

    safety_flags = response.get("safety_flags", [])

    # Synthesize conversational user_response for farmers/extension officers (Srikanth 19-Oct schema mandate)
    if not user_response:
        if escalation_required:
            user_response = (
                "This case presents critical symptoms that may indicate rapid spread or panicle damage. "
                "Please avoid applying unverified chemicals. Immediately contact your local agricultural extension "
                "officer or district plant clinic with a fresh plant sample for physical confirmation."
            )
        elif compact_status == "needs_more_information":
            q_text = ""
            if observations_needed:
                q_text = " Please check: " + ", ".join(observations_needed[:2]) + "."
            user_response = (
                "The symptoms you described could indicate multiple overlapping conditions (such as "
                f"{', '.join(differential[:2]) if differential else 'pathogen or nutrient stresses'}). "
                f"To avoid misdiagnosis, we need a few more distinguishing field observations before confirming.{q_text}"
            )
        else:
            act_text = actions[0] if actions else "monitor field conditions closely."
            user_response = (
                f"Based on the available evidence, the provisional assessment points to {differential[0] if differential else 'the identified condition'}. "
                f"Recommended cultural action: {act_text} Avoid commercial chemical sprays without extension confirmation."
            )

    return {
        "status": compact_status,
        "user_response": user_response,
        "observations_needed": observations_needed,
        "differential": differential,
        "actions": actions,
        "escalation_required": escalation_required,
        "grounding": grounding,
        "safety_flags": safety_flags
    }


