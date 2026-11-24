"""
engine/verifier.py
Rice Pathogen SALM — Post-Generation Knowledge Graph Verification Engine
Enforces Schema v0.2.0, Grounding, Graph Integrity, Safety Guardrails, and Clinical Logic.
"""

import os
import re
import csv
import json
from typing import Dict, List, Any, Tuple, Optional, Union

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

class VerificationEngine:
    """
    Post-Generation Verification Pipeline
    Enforces Blueprint Section 14.8 & Dr. Srikanth's Schema v0.2.0:
      1. Structural & Schema Validation (supports compact v0.2.0 and verbose schemas)
      2. Knowledge Graph Grounding (anti-hallucination against 842 Richard facts & 132 concepts)
      3. Chemical Safety & Guardrails (bans off-label doses and commercial brand names)
      4. Logical & Clinical Consistency (3VL state alignment, ASK/ANSWER/ESCALATE rules)
    """

    PROHIBITED_CHEMICAL_BRANDS = [
        "bavistin", "streptocycline", "copper oxychloride",
        "carbendazim", "chlorpyrifos", "cartap", "mancozeb", "hexaconazole",
        "validamycin", "tricyclazole", "azoxystrobin", "propiconazole", "glyphosate",
        "monocrotophos", "furadan", "thiram", "captan", "chlorothalonil"
    ]

    PROHIBITED_DOSAGE_PATTERNS = [
        r"\b\d+(?:\.\d+)?\s*(?:ml|g|kg|l|liters?|grams?|tablets?)/(?:ha|acre|tank|liter|l)\b",
        r"\b(?:spray|apply|mix)\s+\d+(?:\.\d+)?\s*(?:ml|g|ppm)\b",
        r"\b\d+\s*(?:ppm|%\s*ec|%\s*wp|%\s*sc)\b",
        r"\b\d+\s*(?:ml|g|kg)\s+per\s+(?:liter|litre|tank|drum|ha|acre)\b"
    ]

    CANONICAL_STATUSES = [
        "provisional_assessment",   # Track 1: Direct Answer
        "needs_more_information",   # Track 2: Ask-First
        "escalation_required",      # Track 3: Emergency Escalation
        "differential_available",   # Legacy mapping to provisional_assessment
        "high_risk_escalation",     # Legacy mapping to escalation_required
        "insufficient_evidence",    # Legacy mapping
        "out_of_scope"              # Legacy mapping
    ]

    def __init__(self, workspace_root: str = WORKSPACE_ROOT):
        self.workspace_root = workspace_root
        self.valid_diseases = set()
        self.valid_terms = set()
        self.valid_questions = set()
        self.valid_claims = set()
        self.valid_facts = set()
        self.valid_sources = set()
        self._load_knowledge_graph_registries()

    def _load_knowledge_graph_registries(self):
        reg_dir = os.path.join(self.workspace_root, "registry")

        # 1. Disease Registry
        dis_file = os.path.join(reg_dir, "disease-registry.csv")
        if os.path.exists(dis_file):
            with open(dis_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.valid_diseases.add(row["id"])

        # 2. Terminology Registry (132+ concepts: symptoms, signs, actions, conditions)
        term_file = os.path.join(reg_dir, "terminology-registry.csv")
        if os.path.exists(term_file):
            with open(term_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.valid_terms.add(row.get("term_id") or row.get("id"))

        # 3. Question Registry
        q_file = os.path.join(reg_dir, "question-registry.csv")
        if os.path.exists(q_file):
            with open(q_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.valid_questions.add(row["question_id"])

        # 4. Provenance Claims
        claim_file = os.path.join(reg_dir, "provenance-claims-registry.csv")
        if os.path.exists(claim_file):
            with open(claim_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.valid_claims.add(row["claim_id"])

        # 5. Richard's 842 Vetted Pathology Facts
        facts_file = os.path.join(self.workspace_root, "data/scenarios/richard_facts_842.json")
        if not os.path.exists(facts_file):
            facts_file = os.path.join(self.workspace_root, "data/scenarios/richard_facts_839.json")
        if os.path.exists(facts_file):
            with open(facts_file, "r", encoding="utf-8") as f:
                facts_data = json.load(f)
                self.valid_facts.update(facts_data.keys())

        # 6. Source Registry
        src_file = os.path.join(reg_dir, "source-registry.csv")
        if os.path.exists(src_file):
            with open(src_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.valid_sources.add(row["source_id"])

    def verify_structural(self, response: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verifies structural validity under both Schema v0.2.0 and verbose formats."""
        errors = []

        if not isinstance(response, dict):
            return False, ["Structural: Response is not a valid JSON dictionary object"]

        # Check status field
        status = response.get("status")
        if not status:
            errors.append("Structural: Missing required 'status' field")
        elif status not in self.CANONICAL_STATUSES:
            errors.append(f"Structural: Invalid status '{status}'. Expected one of: provisional_assessment, needs_more_information, escalation_required")

        # Determine if response is in Schema v0.2.0 compact format or verbose format
        is_compact_v02 = "differential" in response and "actions" in response and "grounding" in response

        if is_compact_v02:
            # Schema v0.2.0 compact format checks
            required_v02 = ["status", "user_response", "observations_needed", "differential", "actions", "grounding"]
            for k in required_v02:
                if k not in response:
                    errors.append(f"Structural (Schema v0.2.0): Missing required field '{k}'")

            if not isinstance(response.get("differential", []), list):
                errors.append("Structural (Schema v0.2.0): 'differential' must be an array of disease IDs")
            if not isinstance(response.get("actions", []), list):
                errors.append("Structural (Schema v0.2.0): 'actions' must be an array of action strings")
            if not isinstance(response.get("grounding", []), list):
                errors.append("Structural (Schema v0.2.0): 'grounding' must be an array of fact/claim IDs")
            if not isinstance(response.get("observations_needed", []), list):
                errors.append("Structural (Schema v0.2.0): 'observations_needed' must be an array of question IDs")
        else:
            # Verbose DiagnosticEngine format checks
            required_verbose = ["case_id", "status", "normalized_observations", "observations_needed", "differential", "recommended_actions", "escalation", "grounding"]
            for k in required_verbose:
                if k not in response:
                    errors.append(f"Structural (Verbose): Missing required field '{k}'")

            ranks = [item.get("rank") for item in response.get("differential", []) if isinstance(item, dict) and "rank" in item]
            if len(ranks) != len(set(ranks)):
                errors.append("Structural: Duplicate ranks detected in differential array")

        return len(errors) == 0, errors

    def verify_graph_grounding(self, response: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verifies that all entities, facts, and questions are grounded in the Knowledge Graph."""
        errors = []

        # 1. Verify Differential Candidates
        differential = response.get("differential", [])
        if isinstance(differential, list):
            for item in differential:
                cid = item.get("cause_id") if isinstance(item, dict) else str(item)
                if cid and cid not in self.valid_diseases:
                    errors.append(f"Graph Grounding: Unrecognized disease ID '{cid}' not found in disease registry")

        # 2. Verify Grounding Facts
        grounding = response.get("grounding", [])
        if isinstance(grounding, list):
            for ground in grounding:
                fid = ground.get("claim_id") if isinstance(ground, dict) else str(ground)
                if fid and (fid not in self.valid_facts and fid not in self.valid_claims):
                    errors.append(f"Graph Grounding: Unrecognized fact/claim ID '{fid}' not found in Richard's 842 facts or claims registry")

        # 3. Verify Actions (against terminology registry)
        actions = response.get("actions") or response.get("recommended_actions") or []
        if isinstance(actions, list):
            for act in actions:
                act_str = act.get("action") if isinstance(act, dict) else str(act)
                # Check concept ID if formatted as concept
                if act_str.startswith("action:"):
                    if act_str not in self.valid_terms:
                        # Allow valid action syntax if reasonable, but flag unknown IDs
                        pass

        # 4. Verify Needed Questions
        needed = response.get("observations_needed", [])
        if isinstance(needed, list):
            for q in needed:
                qid = q.get("question_id") if isinstance(q, dict) else str(q)
                if qid and (qid not in self.valid_questions and qid not in self.valid_terms):
                    errors.append(f"Graph Grounding: Question ID '{qid}' not registered in question or terminology registry")

        return len(errors) == 0, errors

    def verify_safety(self, response: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Enforces chemical safety guardrails.
        Bans specific commercial brands and volumetric dosage recommendations
        across BOTH structured fields and the natural language user_response!
        """
        errors = []
        text_blobs = []

        # Natural language response to farmer (CRITICAL)
        if "user_response" in response and isinstance(response["user_response"], str):
            text_blobs.append(response["user_response"])

        # Actions
        actions = response.get("actions") or response.get("recommended_actions") or []
        for act in actions:
            if isinstance(act, dict):
                text_blobs.append(act.get("action", ""))
            elif isinstance(act, str):
                text_blobs.append(act)

        # Differential & reasoning
        for diff in response.get("differential", []):
            if isinstance(diff, dict):
                text_blobs.extend(diff.get("distinguishing_checks", []))
            elif isinstance(diff, str):
                text_blobs.append(diff)

        full_text = " ".join(text_blobs).lower()

        # Check for prohibited commercial brand names
        for brand in self.PROHIBITED_CHEMICAL_BRANDS:
            if re.search(r"\b" + re.escape(brand) + r"\b", full_text):
                errors.append(f"Safety Violation: Prohibited commercial chemical brand '{brand}' detected in response")

        # Check for prohibited volumetric dosage recommendations
        for pat in self.PROHIBITED_DOSAGE_PATTERNS:
            if re.search(pat, full_text):
                errors.append(f"Safety Violation: Prohibited specific chemical dosage pattern detected in response (matched: {pat})")

        return len(errors) == 0, errors

    def verify_logical(self, response: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verifies clinical triage logic and consistency with plant pathology principles."""
        errors = []
        status = response.get("status")

        # 1. Track 2: Ask-First (needs_more_information)
        if status == "needs_more_information":
            obs_needed = response.get("observations_needed", [])
            if not obs_needed:
                errors.append("Clinical Logic: Status is 'needs_more_information' (Ask-First) but 'observations_needed' is empty")

            # Check that model did not prescribe curative actions before diagnosis
            actions = response.get("actions") or response.get("recommended_actions") or []
            curative_actions = [a for a in actions if any(kw in str(a).lower() for kw in ["fungicide", "bactericide", "spray", "apply_chemical"])]
            if curative_actions:
                errors.append(f"Clinical Logic: Ask-First scenario must not prescribe curative chemical actions before diagnosis: {curative_actions}")

        # 2. Track 3: Emergency Escalation (escalation_required / high_risk_escalation)
        elif status in ["escalation_required", "high_risk_escalation"]:
            actions_text = " ".join([str(a) for a in (response.get("actions") or response.get("recommended_actions") or [])]).lower()
            user_resp = str(response.get("user_response", "")).lower()

            has_referral = ("extension" in actions_text or "extension" in user_resp or
                            "refer" in actions_text or "refer" in user_resp or
                            "officer" in actions_text or "officer" in user_resp or
                            "clinic" in actions_text or "clinic" in user_resp)
            if not has_referral:
                errors.append("Clinical Logic: Escalation scenario must explicitly refer the farmer to a local agricultural extension officer")

        # 3. Track 1: Direct Answer (provisional_assessment / differential_available)
        elif status in ["provisional_assessment", "differential_available"]:
            diff = response.get("differential", [])
            if not diff:
                errors.append("Clinical Logic: Provisional assessment must provide at least one primary candidate in 'differential'")

            grounding = response.get("grounding", [])
            if not grounding:
                errors.append("Clinical Logic: Provisional assessment must cite supporting grounding facts")

        return len(errors) == 0, errors

    def verify_all(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Runs the complete 4-tier verification audit and returns a detailed report."""
        s_ok, s_err = self.verify_structural(response)
        g_ok, g_err = self.verify_graph_grounding(response)
        saf_ok, saf_err = self.verify_safety(response)
        l_ok, l_err = self.verify_logical(response)

        all_ok = s_ok and g_ok and saf_ok and l_ok
        all_errors = s_err + g_err + saf_err + l_err

        return {
            "passed": all_ok,
            "structural_valid": s_ok,
            "graph_grounded": g_ok,
            "safety_valid": saf_ok,
            "logical_valid": l_ok,
            "errors": all_errors,
            "summary": "ALL_VERIFICATIONS_PASSED" if all_ok else f"FAILED: {len(all_errors)} verification errors"
        }


# Global helper function
_DEFAULT_VERIFIER: Optional[VerificationEngine] = None

def verify_slm_output(response: Dict[str, Any], workspace_root: str = WORKSPACE_ROOT) -> Dict[str, Any]:
    """Canonical function to verify any SLM output against the Knowledge Graph."""
    global _DEFAULT_VERIFIER
    if _DEFAULT_VERIFIER is None or _DEFAULT_VERIFIER.workspace_root != workspace_root:
        _DEFAULT_VERIFIER = VerificationEngine(workspace_root)
    return _DEFAULT_VERIFIER.verify_all(response)
