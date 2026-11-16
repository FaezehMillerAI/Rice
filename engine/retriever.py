"""
engine/retriever.py
Rice Pathogen SALM — Knowledge Graph Context Retriever (retrieve_kg)
Provides canonical retrieval from the Rice Knowledge Graph for SFT and evaluation inference.
"""

from copy import deepcopy
import json
import os
import sys
from typing import Dict, List, Any, Optional, Union, TypedDict

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from engine.diagnostic_engine import DiagnosticEngine


class PublicInput(TypedDict):
    user_text: str | None
    growth_stage_id: str | None
    production_system_id: str | None
    cultivar_id: str | None


class PublicCase(TypedDict):
    """Inference-available case fields; annotations and targets are excluded."""

    input: PublicInput
    language: str | None
    region_id: str | None


class RetrievedContext(TypedDict):
    """Shared KG-to-SLM context for SFT and evaluation inference."""

    normalized_observations: list[Any]
    candidate_causes: list[Any]
    supporting_evidence: list[Any]
    contradicting_evidence: list[Any]
    missing_observations: list[Any]
    suggested_questions: list[Any]
    retrieved_facts: list[Any]
    evidence_fact_ids: list[str]
    evidence_source_ids: list[str]


def empty_retrieved_context() -> RetrievedContext:
    """Build independent empty lists in the shared context schema."""
    return {
        "normalized_observations": [], "candidate_causes": [],
        "supporting_evidence": [], "contradicting_evidence": [],
        "missing_observations": [], "suggested_questions": [],
        "retrieved_facts": [], "evidence_fact_ids": [], "evidence_source_ids": [],
    }


_QUESTION_CONTEXT_KEYS = (
    "question_id",
    "target_observation_id",
    "canonical_text",
    "farmer_friendly_phrasing",
    "rationale",
)

_FACT_KEYS = (
    "claim_id",
    "subject_uri",
    "predicate_uri",
    "object_uri",
    "source_id",
    "source_section",
    "source_text_span",
)


class KGRetriever:
    """Retrieves subgraph context, candidate differential rankings, and evidence receipts."""

    version = "v0.2"

    def __init__(self, workspace_root: str = WORKSPACE_ROOT):
        self.workspace_root = workspace_root
        self.engine = DiagnosticEngine(workspace_root)
        self.richard_facts: Dict[str, Dict[str, Any]] = {}
        for rel in (
            "data/scenarios/richard_facts_842.json",
            "data/scenarios/richard_facts_839.json",
            "richard_facts_842.json",
            "richard_facts_839.json",
        ):
            rf_path = os.path.join(workspace_root, rel)
            if os.path.exists(rf_path):
                try:
                    with open(rf_path, "r", encoding="utf-8") as f:
                        self.richard_facts = json.load(f)
                    break
                except Exception:
                    self.richard_facts = {}

    def extract_case_fields(self, case_info: Union[Dict[str, Any], str]) -> Dict[str, Any]:
        """Extracts normalized user_text and growth_stage from various input formats."""
        if isinstance(case_info, str):
            return {
                "user_text": case_info,
                "growth_stage": "tillering",
                "explicit_obs": [],
            }

        user_text = ""
        growth_stage = "tillering"
        explicit_obs: List[Dict[str, str]] = []

        # Format A: Nested input object (Dr. Srikanth's schema)
        if "input" in case_info and isinstance(case_info["input"], dict):
            inp = case_info["input"]
            user_text = inp.get("user_text") or ""
            stage_id = inp.get("growth_stage_id") or ""
            if stage_id.startswith("growth_stage:"):
                growth_stage = stage_id.replace("growth_stage:", "")
            elif stage_id:
                growth_stage = stage_id

        # Format B: Flat dictionary or legacy scenario schema
        if not user_text:
            user_text = (
                case_info.get("user_text")
                or case_info.get("farmer_utterance")
                or case_info.get("query")
                or ""
            )

        if "growth_stage" in case_info and case_info["growth_stage"]:
            growth_stage = case_info["growth_stage"]
        elif "context" in case_info and isinstance(case_info["context"], dict):
            ctx = case_info["context"]
            growth_stage = ctx.get("growth_stage", growth_stage) or growth_stage

        if "explicit_observations" in case_info:
            explicit_obs = case_info["explicit_observations"]

        return {
            "user_text": user_text,
            "growth_stage": growth_stage,
            "explicit_obs": explicit_obs,
        }

    def _select_focused_facts(
        self,
        candidate_ids: List[str],
        obs_state_map: Dict[str, str],
        max_facts: int = 5,
    ) -> tuple[List[Dict[str, str]], List[str], List[str]]:
        """Select concise, candidate-ranked provenance facts across claims and Richard's vetted facts."""
        active_obs = {k for k, v in obs_state_map.items() if v == "TRUE"}
        candidate_rank = {cid: idx for idx, cid in enumerate(candidate_ids)}
        obs_tokens = [
            obs.split(":")[-1].replace("_", " ")
            for obs in active_obs
            if not obs.startswith("stage:")
        ]

        pool: List[tuple[tuple, str, Dict[str, str]]] = []

        # 1. Candidates from provenance-claims-registry.csv (source_priority=0)
        for claim_id, row in self.engine.claims.items():
            subj = row.get("subject_uri", "")
            obj = row.get("object_uri", "")
            if subj in candidate_rank:
                c_rank = candidate_rank[subj]
                obs_hit = 1 if obj in active_obs else 0
            elif obj in active_obs and not candidate_ids:
                c_rank = 0
                obs_hit = 1
            else:
                continue
            fact_entry = {key: str(row.get(key, "")) for key in _FACT_KEYS}
            pool.append(((c_rank, -obs_hit, 0, claim_id), claim_id, fact_entry))

        # 2. Candidates from Richard's 842 vetted facts (source_priority=1)
        if self.richard_facts and candidate_ids:
            disease_aliases = {
                "bacterial blight": "bacterial leaf blight",
                "yellow stem borer": "stem borer",
            }
            candidate_terms = [
                (idx, cid, cid.split(":")[-1].replace("_", " "))
                for idx, cid in enumerate(candidate_ids)
            ]
            for fid, fval in self.richard_facts.items():
                f_dis = str(fval.get("disease", "")).lower().strip()
                f_dis_norm = disease_aliases.get(f_dis, f_dis)
                f_stmt = str(fval.get("statement", "")).lower()
                matched_rank = None
                matched_cid = None
                for idx, cid, kw in candidate_terms:
                    if kw in f_dis_norm or (f_dis_norm and f_dis_norm in kw):
                        matched_rank = idx
                        matched_cid = cid
                        break
                if matched_rank is None:
                    continue
                obs_hits = sum(1 for tok in obs_tokens if tok in f_stmt)
                approved_bonus = 0 if str(fval.get("sme_review_status", "")).lower() == "approved" else 1
                cat = str(fval.get("category", "")).strip()
                pred_slug = "".join(ch if ch.isalnum() else "_" for ch in cat.lower()).strip("_") or "hasFact"
                src = str(fval.get("source_id", "")).strip() or "source:irri_rice_doctor_2024"
                fact_entry = {
                    "claim_id": fid,
                    "subject_uri": matched_cid,
                    "predicate_uri": f"rice:{pred_slug}",
                    "object_uri": "",
                    "source_id": src,
                    "source_section": cat,
                    "source_text_span": str(fval.get("statement", "")).strip(),
                }
                pool.append(((matched_rank, -obs_hits, 1 + approved_bonus, fid), fid, fact_entry))

        pool.sort(key=lambda item: item[0])

        facts: List[Dict[str, str]] = []
        evidence_fact_ids: List[str] = []
        evidence_source_ids: List[str] = []
        seen_fact_ids = set()

        for _, fid, fact_entry in pool:
            if fid in seen_fact_ids:
                continue
            facts.append(fact_entry)
            seen_fact_ids.add(fid)
            evidence_fact_ids.append(fid)
            src = fact_entry.get("source_id", "")
            if src and src not in evidence_source_ids:
                evidence_source_ids.append(src)
            if len(facts) >= max_facts:
                break

        if not evidence_source_ids:
            evidence_source_ids = ["source:irri_rice_doctor_2024"]

        return facts, evidence_fact_ids, evidence_source_ids

    def retrieve(
        self,
        case_info: Union[Dict[str, Any], str],
        top_k_candidates: int = 3,
        top_k_questions: int = 3,
    ) -> RetrievedContext:
        """
        Retrieve the nine-field KG-to-SLM context directly.

        Normalize observations once, then select candidates, questions, matching
        rule evidence and focused provenance claims. Returned lists and objects
        are independent of the engine registries and of other retrieval calls.
        """
        fields = self.extract_case_fields(case_info)
        user_text = fields["user_text"]
        growth_stage = fields["growth_stage"]
        explicit_obs = fields["explicit_obs"]

        # 1. Normalize Observations once from raw text + explicit observations
        obs_state_map = self.engine.normalize_observations(user_text, explicit_obs)
        if growth_stage and f"stage:{growth_stage}" not in obs_state_map:
            obs_state_map[f"stage:{growth_stage}"] = "TRUE"

        # 2. Score Candidates under 3VL Open-World Assumption
        scored_candidates = self.engine.score_candidates(obs_state_map, growth_stage)
        top_candidates = scored_candidates[:top_k_candidates]
        candidate_ids = [c["cause_id"] for c in top_candidates]

        # 3. Retrieve Missing Distinguishing Checks & Ranked Questions
        needed_questions = self.engine.rank_questions(scored_candidates, obs_state_map)
        question_ids = [q["question_id"] for q in needed_questions[:top_k_questions]]

        # 4. Retrieve Focused Evidence Provenance Facts & Source IDs
        facts, evidence_fact_ids, evidence_source_ids = self._select_focused_facts(
            candidate_ids, obs_state_map, max_facts=5
        )

        # 5. Assemble the nine-field public context without repeating NLP
        states = obs_state_map
        if growth_stage:
            states.setdefault(f"stage:{growth_stage}", "TRUE")
        state_names = {"TRUE": "PRESENT", "FALSE": "ABSENT", "UNKNOWN": "UNKNOWN"}

        questions = [
            {key: deepcopy(self.engine.questions[q].get(key, "")) for key in _QUESTION_CONTEXT_KEYS}
            for q in question_ids
            if q in self.engine.questions
        ]

        support, contradict = [], []
        for rule in self.engine.evidence_rules:
            expected = rule.get("condition_truth_state", "").removeprefix("state:")
            if rule["cause_id"] in candidate_ids and states.get(rule["observation_id"]) == expected:
                if rule.get("evidence_type", "").lower() == "supporting":
                    support.append(deepcopy(rule))
                elif rule.get("evidence_type", "").lower() == "contradicting":
                    contradict.append(deepcopy(rule))

        return {
            "normalized_observations": [
                {"concept_id": key, "state": state_names.get(state, state)}
                for key, state in states.items()
            ],
            "candidate_causes": candidate_ids,
            "supporting_evidence": support,
            "contradicting_evidence": contradict,
            "missing_observations": list(dict.fromkeys(q["target_observation_id"] for q in questions)),
            "suggested_questions": questions,
            "retrieved_facts": facts,
            "evidence_fact_ids": evidence_fact_ids,
            "evidence_source_ids": evidence_source_ids,
        }


# Global singleton helper
_DEFAULT_RETRIEVER: Optional[KGRetriever] = None


def retrieve_kg(
    case_info: Union[Dict[str, Any], str],
    top_k_candidates: int = 3,
    top_k_questions: int = 3,
    workspace_root: str = WORKSPACE_ROOT,
) -> RetrievedContext:
    """
    Public API: Retrieves relevant Knowledge Graph context for a given case.

    Returns the nine-field RetrievedContext:
    normalized_observations, candidate_causes, supporting_evidence,
    contradicting_evidence, missing_observations, suggested_questions,
    retrieved_facts, evidence_fact_ids, and evidence_source_ids.
    """
    global _DEFAULT_RETRIEVER
    if _DEFAULT_RETRIEVER is None or _DEFAULT_RETRIEVER.workspace_root != workspace_root:
        _DEFAULT_RETRIEVER = KGRetriever(workspace_root)
    return _DEFAULT_RETRIEVER.retrieve(
        case_info,
        top_k_candidates=top_k_candidates,
        top_k_questions=top_k_questions,
    )


def to_compact_target_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a verbose DiagnosticEngine response into the compact diagnostic response schema:
    {
        "status": "needs_more_information" | "provisional_assessment" | "escalation_required",
        "observations_needed": List[str],  # Question IDs
        "differential": List[str],         # Cause IDs
        "actions": List[str],              # Action IDs
        "escalation_required": bool,
        "grounding": List[str],            # Fact/claim IDs
        "safety_flags": List[str],         # Escalation trigger IDs
        "user_response": str
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

    recommended_actions = response.get("recommended_actions", [])
    actions = [
        a["action_id"] if isinstance(a, dict) else str(a)
        for a in recommended_actions
    ]

    grounding = [
        g["claim_id"] if isinstance(g, dict) else str(g)
        for g in response.get("grounding", [])
    ]

    safety_flags = list(esc_dict.get("triggers", [])) if isinstance(esc_dict, dict) else []

    def readable_text(item, fields, fallback):
        if isinstance(item, dict):
            for field in fields:
                value = item.get(field)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return fallback

    candidate_names = [
        readable_text(item, ("display_name",), cause_id)
        for item, cause_id in zip(response.get("differential", []), differential)
    ]
    question_texts = [
        readable_text(item, ("farmer_friendly_phrasing", "canonical_text", "question", "text"), question_id)
        for item, question_id in zip(response.get("observations_needed", []), observations_needed)
    ]
    action_texts = [
        readable_text(item, ("action",), "Monitor field conditions closely.")
        for item in recommended_actions
    ]
    if compact_status == "escalation_required":
        user_response = (
            "This case presents critical symptoms that may indicate rapid spread or panicle damage. "
            "Please avoid applying unverified chemicals. Immediately contact your local agricultural extension "
            "officer or district plant clinic with a fresh plant sample for physical confirmation."
        )
    elif compact_status == "needs_more_information":
        q_text = ""
        if question_texts:
            q_text = "\nPlease check:\n" + "\n".join(
                f"{index}. {text}" for index, text in enumerate(question_texts, start=1)
            )
        user_response = (
            "The symptoms you described could have more than one cause, including "
            f"{', '.join(candidate_names) if candidate_names else 'disease or nutrient and water stresses'}. "
            f"We need more field observations before confirming the cause.{q_text}"
        )
    else:
        act_text = action_texts[0].rstrip() if action_texts else "Monitor field conditions closely."
        if act_text and act_text[-1] not in ".!?":
            act_text += "."
        user_response = (
            f"Based on the available evidence, {candidate_names[0] if candidate_names else 'the identified condition'} "
            "is a possible cause. This is a provisional assessment. "
            f"Recommended next step: {act_text} Avoid commercial chemical sprays without extension confirmation."
        )

    return {
        "status": compact_status,
        "observations_needed": observations_needed,
        "differential": differential,
        "actions": actions,
        "escalation_required": escalation_required,
        "grounding": grounding,
        "safety_flags": safety_flags,
        "user_response": user_response,
    }
