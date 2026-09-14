import csv
import re
import os
import json
from typing import Dict, List, Any, Optional, Tuple

class DiagnosticEngine:
    """Deterministic Diagnostic & Triage Reasoning Engine (Baseline 0)"""

    def __init__(self, workspace_root: str = "/Users/faezeh/Desktop/Rice"):
        self.workspace_root = workspace_root
        self.terms = {}
        self.diseases = {}
        self.questions = {}
        self.evidence_rules = []
        self.sources = {}
        self.claims = {}
        self._load_registries()

    def _load_registries(self):
        reg_dir = os.path.join(self.workspace_root, "registry")

        # Load Terminology Registry
        term_file = os.path.join(reg_dir, "terminology-registry.csv")
        if os.path.exists(term_file):
            with open(term_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tid = row["term_id"]
                    self.terms[tid] = {
                        "term_id": tid,
                        "canonical_name": row.get("canonical_term", row.get("canonical_name", "")),
                        "entity_type": row["entity_type"],
                        "skos_pref_label": row["skos_pref_label"],
                        "skos_alt_labels": [x.strip() for x in row.get("skos_alt_labels", "").split("|") if x.strip()],
                        "farmer_phrasings": [x.strip() for x in row.get("farmer_phrasings", "").split("|") if x.strip()],
                    }

        # Load Disease Registry
        dis_file = os.path.join(reg_dir, "disease-registry.csv")
        if os.path.exists(dis_file):
            with open(dis_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    did = row["id"]
                    self.diseases[did] = {
                        "id": did,
                        "canonical_name": row["canonical_name"],
                        "type": row["type"],
                        "category": row["category"],
                        "skos_pref_label": row["skos_pref_label"],
                        "pathogen_agent": row.get("pathogen_agent", ""),
                    }

        # Load Question Registry
        q_file = os.path.join(reg_dir, "question-registry.csv")
        if os.path.exists(q_file):
            with open(q_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    qid = row["question_id"]
                    self.questions[qid] = {
                        "question_id": qid,
                        "target_observation_id": row["target_observation_id"],
                        "canonical_text": row["canonical_text"],
                        "farmer_friendly_phrasing": row.get("farmer_friendly_phrasing", ""),
                        "rationale": row["rationale"],
                        "effort_score": float(row["effort_score"]),
                        "observability_score": float(row["observability_score"]),
                        "reliability_score": float(row["reliability_score"]),
                        "default_priority": int(row.get("default_priority", 1)),
                    }

        # Load Evidence Rules
        ev_file = os.path.join(reg_dir, "evidence-rules.csv")
        if os.path.exists(ev_file):
            with open(ev_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.evidence_rules.append(row)

        # Load Claims
        claim_file = os.path.join(reg_dir, "provenance-claims-registry.csv")
        if os.path.exists(claim_file):
            with open(claim_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.claims[row["claim_id"]] = row

    def normalize_observations(self, user_text: str, explicit_obs: Optional[List[Dict[str, str]]] = None) -> Dict[str, str]:
        obs_state_map = {}

        if explicit_obs:
            for item in explicit_obs:
                obs_state_map[item["term_id"]] = item["state"]

        text_lower = user_text.lower()

        for tid, data in self.terms.items():
            if tid in obs_state_map:
                continue
            if (data["canonical_name"] and data["canonical_name"].lower() in text_lower) or (data["skos_pref_label"] and data["skos_pref_label"].lower() in text_lower):
                obs_state_map[tid] = "TRUE"
                continue
            for phrase in data["farmer_phrasings"]:
                if phrase.lower() in text_lower:
                    obs_state_map[tid] = "TRUE"
                    break

        if any(k in text_lower for k in ["wavy", "water-soaked", "undulating", "stripes on leaf side", "burnt edges"]) and "symptom:water_soaked_wavy_lesion" not in obs_state_map:
            obs_state_map["symptom:water_soaked_wavy_lesion"] = "TRUE"
        if any(k in text_lower for k in ["lowest", "oldest", "lower leaves", "bottom leaves", "lower foliage"]) and "symptom:uniform_older_leaf_chlorosis" not in obs_state_map:
            obs_state_map["symptom:uniform_older_leaf_chlorosis"] = "TRUE"
        if any(k in text_lower for k in ["roll", "curl", "folding", "tube", "needles", "needle-like"]) and "symptom:leaf_rolling_folding" not in obs_state_map:
            obs_state_map["symptom:leaf_rolling_folding"] = "TRUE"
        if any(k in text_lower for k in ["yellow", "pale", "chlorosis", "losing green"]) and "symptom:leaf_yellowing" not in obs_state_map:
            obs_state_map["symptom:leaf_yellowing"] = "TRUE"
        if any(k in text_lower for k in ["cloudy", "milky fluid", "ooze stream", "cloudy white"]) and "sign:water_test_cloudy_streaming" not in obs_state_map:
            obs_state_map["sign:water_test_cloudy_streaming"] = "TRUE"
        if any(k in text_lower for k in ["milky beads", "sticky drops", "bacterial ooze"]) and "sign:bacterial_ooze_beads" not in obs_state_map:
            obs_state_map["sign:bacterial_ooze_beads"] = "TRUE"
        if any(k in text_lower for k in ["whole field", "entire field", "uniform across"]) and "field:uniform_fieldwide_distribution" not in obs_state_map:
            obs_state_map["field:uniform_fieldwide_distribution"] = "TRUE"
        if any(k in text_lower for k in ["patches", "patchy", "clumps", "spots"]) and "field:patchy_distribution" not in obs_state_map:
            obs_state_map["field:patchy_distribution"] = "TRUE"
        if any(k in text_lower for k in ["standing water", "flooded", "water stayed"]) and "env:standing_water" not in obs_state_map:
            obs_state_map["env:standing_water"] = "TRUE"
        if any(k in text_lower for k in ["storm", "typhoon", "cyclone", "heavy rain"]) and "env:heavy_rainfall" not in obs_state_map:
            obs_state_map["env:heavy_rainfall"] = "TRUE"
        if any(k in text_lower for k in ["unroll", "recover", "reversed"]) and "symptom:recovers_upon_rewatering" not in obs_state_map:
            obs_state_map["symptom:recovers_upon_rewatering"] = "TRUE"

        # Check negative assertions
        if re.search(r"\b(?:no|without|zero)\s+(?:wavy\s+)?lesions\b", text_lower) or "no lesions" in text_lower or "zero lesions" in text_lower:
            obs_state_map["symptom:water_soaked_wavy_lesion"] = "FALSE"
        if "clear water" in text_lower or "negative water test" in text_lower or "no bacterial stream" in text_lower:
            obs_state_map["sign:water_test_cloudy_streaming"] = "FALSE"
        if "bottom leaves green" in text_lower or "lower leaves healthy" in text_lower or "lowest leaves are healthy" in text_lower:
            obs_state_map["symptom:uniform_older_leaf_chlorosis"] = "FALSE"
        if "no bacterial ooze" in text_lower or "zero bacterial ooze" in text_lower:
            obs_state_map["sign:bacterial_ooze_beads"] = "FALSE"
        if "no leaf rolling" in text_lower:
            obs_state_map["symptom:leaf_rolling_folding"] = "FALSE"

        return obs_state_map

    def check_escalation(self, user_text: str, obs_state_map: Dict[str, str], context: Dict[str, Any]) -> Tuple[bool, List[str], Optional[str]]:
        triggers = []
        text_lower = user_text.lower()

        if any(k in text_lower for k in ["rapid uncontained", "spreading across entire", "collapsing", "uncontrollable", "destroying"]):
            triggers.append("trigger:rapid_uncontrolled_spread")
        if any(k in text_lower for k in ["panicle", "black grain", "head blight", "foul odor", "rotting"]):
            triggers.append("trigger:panicle_infection")
        if any(k in text_lower for k in ["seedling death", "kresek wilt", "nursery"]):
            triggers.append("trigger:seedling_mortality")

        if triggers:
            return True, triggers, "National Rice Research Institute / Official District Plant Pathologist"
        return False, [], None

    def score_candidates(self, obs_state_map: Dict[str, str], growth_stage: Optional[str] = "tillering") -> List[Dict[str, Any]]:
        candidate_profiles = {
            "disease:bacterial_leaf_blight": {
                "name": "Bacterial leaf blight",
                "type": "pathogen",
                "signs": ["sign:bacterial_ooze_beads", "sign:water_test_cloudy_streaming"],
                "symptoms": ["symptom:water_soaked_wavy_lesion", "symptom:leaf_yellowing", "symptom:leaf_tip_margin_necrosis"],
                "env": ["env:high_humidity", "env:heavy_rainfall", "env:standing_water"],
                "stages": ["stage:tillering", "stage:heading"],
                "field": ["field:patchy_distribution"],
                "contradicting_symptoms": ["symptom:uniform_older_leaf_chlorosis", "symptom:leaf_rolling_folding"],
                "contradicting_field": ["field:uniform_fieldwide_distribution"],
                "required_absent_penalties": ["symptom:water_soaked_wavy_lesion", "sign:water_test_cloudy_streaming"]
            },
            "disorder:nitrogen_deficiency": {
                "name": "Nitrogen deficiency",
                "type": "abiotic_confounder",
                "signs": [],
                "symptoms": ["symptom:uniform_older_leaf_chlorosis", "symptom:leaf_yellowing", "symptom:stunted_growth"],
                "env": [],
                "stages": ["stage:tillering"],
                "field": ["field:uniform_fieldwide_distribution"],
                "contradicting_symptoms": ["symptom:water_soaked_wavy_lesion"],
                "contradicting_signs": ["sign:bacterial_ooze_beads", "sign:water_test_cloudy_streaming"],
                "required_absent_penalties": ["symptom:uniform_older_leaf_chlorosis"]
            },
            "disorder:water_stress": {
                "name": "Water stress",
                "type": "abiotic_confounder",
                "signs": [],
                "symptoms": ["symptom:leaf_rolling_folding", "symptom:recovers_upon_rewatering", "symptom:leaf_tip_margin_necrosis", "symptom:leaf_yellowing"],
                "env": ["env:drought_conditions"],
                "stages": ["stage:tillering", "stage:heading"],
                "field": ["field:topography_elevation_dependent"],
                "contradicting_symptoms": ["symptom:water_soaked_wavy_lesion", "symptom:uniform_older_leaf_chlorosis"],
                "contradicting_signs": ["sign:bacterial_ooze_beads", "sign:water_test_cloudy_streaming"],
                "required_absent_penalties": ["symptom:leaf_rolling_folding"]
            }
        }

        scored = []
        for cid, prof in candidate_profiles.items():
            score = 0
            supporting = []
            contradicting = []
            missing = []

            # 1. Signs (+3)
            for s in prof["signs"]:
                state = obs_state_map.get(s, "UNKNOWN")
                if state == "TRUE":
                    score += 3
                    supporting.append(s)
                elif state == "FALSE" and s in prof.get("required_absent_penalties", []):
                    score -= 3
                    contradicting.append(s)
                elif state == "UNKNOWN":
                    missing.append(s)

            # 2. Symptoms (+2)
            for sym in prof["symptoms"]:
                state = obs_state_map.get(sym, "UNKNOWN")
                if state == "TRUE":
                    score += 2
                    supporting.append(sym)
                elif state == "FALSE" and sym in prof.get("required_absent_penalties", []):
                    score -= 3
                    contradicting.append(sym)
                elif state == "UNKNOWN":
                    missing.append(sym)

            # 3. Env (+2)
            for e in prof["env"]:
                state = obs_state_map.get(e, "UNKNOWN")
                if state == "TRUE":
                    score += 2
                    supporting.append(e)

            # 4. Stage (+1)
            if growth_stage and f"stage:{growth_stage}" in prof["stages"]:
                score += 1
                supporting.append(f"stage:{growth_stage}")

            # 5. Field (+1)
            for fp in prof["field"]:
                state = obs_state_map.get(fp, "UNKNOWN")
                if state == "TRUE":
                    score += 1
                    supporting.append(fp)

            # 6. Contradictions (-3)
            for c_sym in prof.get("contradicting_symptoms", []):
                if obs_state_map.get(c_sym) == "TRUE":
                    score -= 3
                    contradicting.append(c_sym)

            for c_sgn in prof.get("contradicting_signs", []):
                if obs_state_map.get(c_sgn) == "TRUE":
                    score -= 3
                    contradicting.append(c_sgn)

            for c_fld in prof.get("contradicting_field", []):
                if obs_state_map.get(c_fld) == "TRUE":
                    score -= 3
                    contradicting.append(c_fld)

            supporting_clean = [x for x in supporting if x not in contradicting]

            if score >= 6:
                conf = "high"
            elif score >= 2:
                conf = "medium"
            else:
                conf = "low"

            scored.append({
                "cause_id": cid,
                "display_name": prof["name"],
                "cause_type": prof["type"],
                "score": score,
                "confidence_band": conf,
                "supporting_observations": list(dict.fromkeys(supporting_clean)),
                "contradicting_observations": list(dict.fromkeys(contradicting)),
                "missing_distinguishing_observations": list(dict.fromkeys(missing)),
                "distinguishing_checks": [
                    "Check lesion margin shape (wavy vs no lesions)",
                    "Inspect whether lowest leaves chlorose first",
                    "Perform cut-leaf streaming test in clear water"
                ]
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        for i, item in enumerate(scored):
            item["rank"] = i + 1

        return scored

    def rank_questions(self, candidates: List[Dict[str, Any]], obs_state_map: Dict[str, str]) -> List[Dict[str, Any]]:
        obs_to_q = {
            "obs:lesion_margin_shape": "q:q_lesion_margin",
            "symptom:water_soaked_wavy_lesion": "q:q_lesion_margin",
            "obs:leaf_age_progression": "q:q_older_vs_younger",
            "symptom:uniform_older_leaf_chlorosis": "q:q_older_vs_younger",
            "obs:bacterial_ooze_test": "q:q_water_test",
            "sign:water_test_cloudy_streaming": "q:q_water_test",
            "obs:leaf_rolling_folding": "q:q_leaf_rolling",
            "symptom:leaf_rolling_folding": "q:q_leaf_rolling",
            "obs:rewatering_recovery": "q:q_rewatering_recovery",
            "symptom:recovers_upon_rewatering": "q:q_rewatering_recovery",
            "obs:field_spatial_pattern": "q:q_field_spatial_pattern",
            "field:patchy_distribution": "q:q_field_spatial_pattern",
            "field:uniform_fieldwide_distribution": "q:q_field_spatial_pattern"
        }

        confirmed = {k for k, v in obs_state_map.items() if v in ["TRUE", "FALSE"]}
        top_candidates = [c for c in candidates if c["score"] >= 2]
        candidates_count = max(2, len(top_candidates))

        ranked_questions = []
        seen_qids = set()
        for qid, qdata in self.questions.items():
            target_obs = qdata["target_observation_id"]

            if target_obs in confirmed or any(k in confirmed for k, v in obs_to_q.items() if v == qid):
                continue
            if qid in seen_qids:
                continue
            seen_qids.add(qid)

            rel = qdata["reliability_score"]
            obs_ease = qdata["observability_score"]
            effort = qdata["effort_score"]
            safety = 1.0

            utility = (candidates_count * rel * obs_ease * safety) / effort

            ranked_questions.append({
                "question_id": qid,
                "question": qdata["canonical_text"],
                "reason": qdata["rationale"],
                "priority": int(qdata["default_priority"]),
                "utility": utility
            })

        ranked_questions.sort(key=lambda x: x["utility"], reverse=True)
        for i, q in enumerate(ranked_questions):
            q["priority"] = i + 1

        return ranked_questions

    def get_management_actions(self, top_candidate_id: str, is_escalated: bool) -> List[Dict[str, Any]]:
        if is_escalated:
            return [{
                "action_id": "action:escalate_to_pathologist",
                "priority": 1,
                "action": "Isolate affected section and immediately submit leaf tissue sample to district plant clinic or agricultural extension authority.",
                "action_type": "escalation"
            }]

        action_map = {
            "disease:bacterial_leaf_blight": [
                {
                    "action_id": "action:avoid_excess_nitrogen",
                    "priority": 1,
                    "action": "Avoid excessive nitrogen top-dressing; split fertilizer applications into balanced doses.",
                    "action_type": "cultural"
                },
                {
                    "action_id": "action:ensure_field_drainage",
                    "priority": 2,
                    "action": "Drain standing water from paddy and allow soil surface to dry slightly to suppress bacterial propagation.",
                    "action_type": "cultural"
                },
                {
                    "action_id": "action:use_resistant_varieties",
                    "priority": 3,
                    "action": "Select certified resistant rice cultivars (e.g., carrying Xa4, xa5, or Xa21 genes) for upcoming planting cycle.",
                    "action_type": "genetic"
                }
            ],
            "disorder:nitrogen_deficiency": [
                {
                    "action_id": "action:balanced_fertilizer_split",
                    "priority": 1,
                    "action": "Apply balanced split nitrogen fertilizer (e.g., urea) in accordance with localized leaf color chart (LCC) guidance.",
                    "action_type": "agronomic"
                },
                {
                    "action_id": "action:organic_matter_incorporation",
                    "priority": 2,
                    "action": "Incorporate decomposed organic manure or crop residues during land preparation to enhance soil cation exchange.",
                    "action_type": "agronomic"
                }
            ],
            "disorder:water_stress": [
                {
                    "action_id": "action:alternate_wetting_drying",
                    "priority": 1,
                    "action": "Implement intermittent irrigation / Alternate Wetting and Drying (AWD) to restore plant root turgidity.",
                    "action_type": "water_management"
                },
                {
                    "action_id": "action:bund_maintenance",
                    "priority": 2,
                    "action": "Repair and heighten field bunds to prevent peripheral runoff and retain rainwater.",
                    "action_type": "water_management"
                }
            ]
        }
        return action_map.get(top_candidate_id, [
            {
                "action_id": "action:monitor_field",
                "priority": 1,
                "action": "Monitor affected field area daily for lesion edge evolution or leaf unrolling.",
                "action_type": "monitoring"
            }
        ])

    def diagnose(self, user_text: str, context: Optional[Dict[str, Any]] = None, explicit_obs: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        if context is None:
            context = {"growth_stage": "tillering", "region": "priority-region-1", "water_condition": None, "weather": None}

        # 1. Normalize Observations
        obs_state_map = self.normalize_observations(user_text, explicit_obs)

        # 2. Check Safety Escalation
        is_escalated, esc_triggers, refer_to = self.check_escalation(user_text, obs_state_map, context)

        # 3. Candidate Scoring
        candidates = self.score_candidates(obs_state_map, context.get("growth_stage", "tillering"))

        # 4. Question Utility Ranking
        needed_questions = self.rank_questions(candidates, obs_state_map)

        # 5. Determine Diagnostic Status
        has_distinguishing = (
            obs_state_map.get("symptom:water_soaked_wavy_lesion") in ["TRUE", "FALSE"] or
            obs_state_map.get("sign:water_test_cloudy_streaming") in ["TRUE", "FALSE"] or
            obs_state_map.get("sign:bacterial_ooze_beads") in ["TRUE", "FALSE"] or
            obs_state_map.get("symptom:uniform_older_leaf_chlorosis") in ["TRUE", "FALSE"] or
            obs_state_map.get("symptom:leaf_rolling_folding") in ["TRUE", "FALSE"]
        )

        top_score = candidates[0]["score"] if candidates else 0
        second_score = candidates[1]["score"] if len(candidates) > 1 else 0
        score_diff = top_score - second_score

        if is_escalated:
            status = "high_risk_escalation"
        elif not has_distinguishing or score_diff < 2:
            status = "needs_more_information"
        else:
            status = "differential_available"

        top_cid = candidates[0]["cause_id"] if candidates else "disease:bacterial_leaf_blight"
        actions = self.get_management_actions(top_cid, is_escalated)

        response = {
            "case_id": context.get("case_id", "case-auto-gen-001"),
            "status": status,
            "normalized_observations": {
                "growth_stage": context.get("growth_stage", "tillering") or "tillering",
                "affected_part": ["part:leaf"],
                "symptoms": [k for k, v in obs_state_map.items() if v == "TRUE" and "symptom:" in k],
                "distribution": "field:patchy_distribution" if obs_state_map.get("field:patchy_distribution") == "TRUE" else "field:uniform_fieldwide_distribution",
                "recent_conditions": [k for k, v in obs_state_map.items() if v == "TRUE" and "env:" in k],
                "region": context.get("region", "priority-region-1")
            },
            "observations_needed": [
                {
                    "question_id": q["question_id"],
                    "question": q["question"],
                    "reason": q["reason"],
                    "priority": q["priority"]
                }
                for q in needed_questions[:3]
            ],
            "differential": candidates,
            "recommended_actions": actions,
            "escalation": {
                "required": is_escalated,
                "triggers": esc_triggers,
                "refer_to": refer_to
            },
            "grounding": [
                {
                    "claim_id": "claim:claim_blb_001",
                    "source_id": "source:irri_rice_doctor_2024",
                    "source_section": "Symptoms",
                    "kg_nodes": ["disease:bacterial_leaf_blight", "symptom:water_soaked_wavy_lesion"]
                },
                {
                    "claim_id": "claim:claim_ndef_001",
                    "source_id": "source:irri_rice_doctor_2024",
                    "source_section": "Nutrient Disorders",
                    "kg_nodes": ["disorder:nitrogen_deficiency", "symptom:uniform_older_leaf_chlorosis"]
                }
            ],
            "safety_flags": ["PRINCIPLE_ACTIONS_ONLY_NO_CHEMICAL_DOSAGES"]
        }

        return response

def diagnose(user_text: str, context: Optional[Dict[str, Any]] = None, explicit_obs: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    engine = DiagnosticEngine()
    return engine.diagnose(user_text, context, explicit_obs)
