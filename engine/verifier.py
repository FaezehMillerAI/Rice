import re
import os
import json
import csv
from typing import Dict, List, Any, Tuple

class VerificationEngine:
    """
    Post-Generation Verification Pipeline
    Enforces Blueprint Section 14.8 (Structural, Graph, Safety, Logical checks).
    """

    PROHIBITED_CHEMICAL_BRANDS = [
        "bavistin", "streptocycline", "copper oxychloride",
        "carbendazim", "chlorpyrifos", "cartap", "mancozeb", "hexaconazole",
        "validamycin", "tricyclazole", "azoxystrobin", "propiconazole", "glyphosate"
    ]

    PROHIBITED_DOSAGE_PATTERNS = [
        r"\b\d+(?:\.\d+)?\s*(?:ml|g|kg|l|liters?|grams?|tablets?)/(?:ha|acre|tank|liter|l)\b",
        r"\b(?:spray|apply|mix)\s+\d+(?:\.\d+)?\s*(?:ml|g|ppm)\b",
        r"\b\d+\s*(?:ppm|%\s*ec|%\s*wp|%\s*sc)\b"
    ]

    def __init__(self, workspace_root: str = "/Users/faezeh/Desktop/Rice"):
        self.workspace_root = workspace_root
        self.valid_diseases = set()
        self.valid_terms = set()
        self.valid_claims = set()
        self._load_registries()

    def _load_registries(self):
        reg_dir = os.path.join(self.workspace_root, "registry")

        dis_file = os.path.join(reg_dir, "disease-registry.csv")
        if os.path.exists(dis_file):
            with open(dis_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.valid_diseases.add(row["id"])

        term_file = os.path.join(reg_dir, "terminology-registry.csv")
        if os.path.exists(term_file):
            with open(term_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.valid_terms.add(row["term_id"])

        claim_file = os.path.join(reg_dir, "provenance-claims-registry.csv")
        if os.path.exists(claim_file):
            with open(claim_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.valid_claims.add(row["claim_id"])

    def verify_structural(self, response: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []
        required_keys = [
            "case_id", "status", "normalized_observations", "observations_needed",
            "differential", "recommended_actions", "escalation", "grounding", "safety_flags"
        ]
        for k in required_keys:
            if k not in response:
                errors.append(f"Structural: Missing required root field '{k}'")

        valid_statuses = [
            "needs_more_information", "differential_available",
            "high_risk_escalation", "insufficient_evidence", "out_of_scope"
        ]
        if response.get("status") not in valid_statuses:
            errors.append(f"Structural: Invalid status '{response.get('status')}'")

        ranks = [item.get("rank") for item in response.get("differential", []) if isinstance(item, dict)]
        if len(ranks) != len(set(ranks)):
            errors.append("Structural: Duplicate ranks detected in differential array")

        return len(errors) == 0, errors

    def verify_graph(self, response: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []
        for diff in response.get("differential", []):
            if isinstance(diff, dict):
                cid = diff.get("cause_id")
                if cid not in self.valid_diseases:
                    errors.append(f"Graph: Cause ID '{cid}' does not exist in disease registry")
            else:
                errors.append(f"Graph: Differential item is not an object: '{diff}'")

        for ground in response.get("grounding", []):
            if isinstance(ground, dict):
                claim_id = ground.get("claim_id")
                if claim_id not in self.valid_claims:
                    errors.append(f"Graph: Provenance Claim ID '{claim_id}' does not exist in claims registry")
            else:
                errors.append(f"Graph: Grounding item is not an object: '{ground}'")

        return len(errors) == 0, errors

    def verify_safety(self, response: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []
        text_blobs = []
        for act in response.get("recommended_actions", []):
            if isinstance(act, dict):
                text_blobs.append(act.get("action", ""))
            elif isinstance(act, str):
                text_blobs.append(act)
        for diff in response.get("differential", []):
            if isinstance(diff, dict):
                text_blobs.extend(diff.get("distinguishing_checks", []))
            elif isinstance(diff, str):
                text_blobs.append(diff)
        
        full_text = " ".join(text_blobs).lower()

        for brand in self.PROHIBITED_CHEMICAL_BRANDS:
            if re.search(r"\b" + re.escape(brand) + r"\b", full_text):
                errors.append(f"Safety Violation: Response mentions prohibited commercial chemical product '{brand}'")

        for pat in self.PROHIBITED_DOSAGE_PATTERNS:
            if re.search(pat, full_text):
                errors.append(f"Safety Violation: Response contains prohibited volumetric dosage recommendation '{pat}'")

        return len(errors) == 0, errors

    def verify_logical(self, response: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []
        for diff in response.get("differential", []):
            if isinstance(diff, dict):
                supp = set(diff.get("supporting_observations", [])) if isinstance(diff.get("supporting_observations"), list) else set()
                contra = set(diff.get("contradicting_observations", [])) if isinstance(diff.get("contradicting_observations"), list) else set()
                overlap = supp.intersection(contra)
                if overlap:
                    errors.append(f"Logical: Observation(s) {overlap} present in both supporting and contradicting for {diff.get('cause_id')}")

        if response.get("status") == "needs_more_information":
            if not response.get("observations_needed"):
                errors.append("Logical: Status is 'needs_more_information' but 'observations_needed' is empty")

        return len(errors) == 0, errors

    def verify_all(self, response: Dict[str, Any]) -> Dict[str, Any]:
        s_ok, s_err = self.verify_structural(response)
        g_ok, g_err = self.verify_graph(response)
        saf_ok, saf_err = self.verify_safety(response)
        l_ok, l_err = self.verify_logical(response)

        all_ok = s_ok and g_ok and saf_ok and l_ok
        all_errors = s_err + g_err + saf_err + l_err

        return {
            "passed": all_ok,
            "structural_valid": s_ok,
            "graph_valid": g_ok,
            "safety_valid": saf_ok,
            "logical_valid": l_ok,
            "errors": all_errors
        }
