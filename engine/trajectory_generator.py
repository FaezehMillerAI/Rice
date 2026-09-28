"""
Rice Pathogen SALM — Synthetic Teacher Trajectory Generator (Step 17 / Phase 8.1 / Step 22 Expansion)
Synthesizes high-diversity, expert-grounded multi-turn SFT training trajectories
using the Baseline 0 Diagnostic Engine as an automated teacher across 5 rice conditions:
  1. Bacterial Leaf Blight (disease:bacterial_leaf_blight)
  2. Nitrogen Deficiency (disorder:nitrogen_deficiency)
  3. Water-Related Stress (disorder:water_stress)
  4. Rice Blast (disease:rice_blast)
  5. Brown Spot (disease:brown_spot)
"""

import json
import random
from typing import Dict, List, Any, Optional

from engine.diagnostic_engine import DiagnosticEngine
from engine.verifier import VerificationEngine

SYSTEM_PROMPT = """You are the Rice Pathogen Small Agriculture Language Model (SALM), an expert AI diagnostic assistant specialized in rice crop pathology, agronomy, and integrated pest management (IPM).

Your operational rules:
1. Ground all reasoning in the canonical Rice Knowledge Graph and Three-Valued Logic (3VL: TRUE, FALSE, UNKNOWN).
2. For under-specified queries, ask high-utility clarifying questions rather than prematurely guessing.
3. For look-alike conditions (e.g. Bacterial Leaf Blight vs Nitrogen Deficiency vs Water Stress vs Rice Blast vs Brown Spot), evaluate confounding causes and provide distinguishing checks.
4. Enforce principle-level cultural management advice. NEVER recommend commercial chemical brand names or volumetric pesticide dosages.
5. If catastrophic symptoms or out-of-distribution conditions appear, escalate immediately to human plant pathology extension officers.
6. Always explain your reasoning step-by-step inside a <thought>...</thought> block, followed by the exact structured JSON response schema."""

class TrajectoryGenerator:
    def __init__(self, workspace_root: str = "/Users/faezeh/Desktop/Rice"):
        self.workspace_root = workspace_root
        self.engine = DiagnosticEngine(workspace_root)
        self.verifier = VerificationEngine(workspace_root)
        
        # 1. Bacterial Leaf Blight Templates
        self.blb_phrasings = [
            "The leaves have water-soaked wavy lesions starting from the tips and margins.",
            "I noticed wavy yellowish-orange stripes along the leaf edges after heavy rains.",
            "Tips of rice leaves are drying up with wavy, water-soaked borders.",
            "Rice leaf blades show yellowish lesions along the edges that turn brown and necrotic.",
            "Water-soaked stripes along leaf margins with cloudy liquid coming out during cut-leaf water test.",
            "Leaf margins are turning yellow-orange and drying up with irregular wavy boundaries.",
            "There are long wavy yellowish lesions on the upper leaves in flooded patches of my field.",
            "Water soaked stripes on leaf edges during tillering stage following a severe storm.",
            "The leaf tips look scorched with wavy margins, and water stayed in the field for days.",
            "Yellowing with distinctive wavy edges spreading from leaf tips across several vegetative tillers."
        ]
        
        # 2. Nitrogen Deficiency Templates
        self.ndef_phrasings = [
            "The lower bottom leaves are uniformly yellowing, but upper leaves remain pale green.",
            "The entire field looks pale yellow, starting from the oldest bottom leaves with stunted tillering.",
            "Leaves at the bottom of the rice plants are turning yellow and drying from the tip down evenly.",
            "Uniform yellowing across the whole field, lowest leaves chlorotic first, no lesions on blades.",
            "Old leaves yellowing uniformly across all rows during early tillering, plants look stunted.",
            "General pale yellow color on older leaves throughout the field with no wavy stripes.",
            "Bottom leaves turning yellow evenly across the whole plot; no spots or wavy lesions seen.",
            "Stunted rice crop with uniform lower leaf chlorosis and reduced tiller numbers.",
            "Whole field shows even light yellow discoloration on bottom foliage.",
            "Lower leaves drying up uniformly from tip backwards; upper new leaves still pale green."
        ]
        
        # 3. Water Stress Templates
        self.wstress_phrasings = [
            "Rice leaves are rolling inward like tubes and wilting in the high elevated corners of the field.",
            "Leaves are curled inward lengthwise and drooping due to lack of irrigation water.",
            "Severe leaf rolling and tip drying in upland patches with no standing water.",
            "Leaves fold into tight tubes during hot afternoon hours and look wilted.",
            "Inward longitudinal leaf curling across dry sandy sections of the paddy.",
            "Plants are wilting with rolled up leaves, but they recover after evening watering.",
            "Dry soil conditions with leaves rolled up and tips turning yellow-brown without lesions.",
            "Leaf blades rolling into needles in high elevation areas without water.",
            "Temporary wilting and leaf folding during prolonged dry spell at tillering.",
            "Inward leaf rolling and drooping across unirrigated sections of the paddy."
        ]
        
        # 4. Rice Blast Templates (New)
        self.blast_phrasings = [
            "The leaves have diamond spindle-shaped lesions with grey or whitish centers and reddish-brown margins.",
            "I noticed spindle-shaped spots with ash-grey centers on upper leaves after several cool, foggy nights.",
            "Diamond-shaped lesions spreading across leaf blades with brown borders during vegetative tillering.",
            "Grey spore felt visible on the underside of spindle lesions during early morning dewy hours.",
            "Lesions shaped like eyes or spindles with dark brown edges and greyish center on the leaf surface.",
            "There is purplish brown rot at the leaf collar junction where blade meets sheath in several patches.",
            "Spindle-shaped elliptical spots appeared after heavy split of nitrogen fertilizer during foggy weather.",
            "Foliage has diamond lesions that coalesce and cause partial leaf blighting in focal hotspots.",
            "Elliptical spots with pointy ends, gray centers, and brown borders on upper leaves.",
            "Leaves show classic spindle-shaped blast spots with grey centers after prolonged dew periods."
        ]
        
        # 5. Brown Spot Templates (New)
        self.bspot_phrasings = [
            "Numerous small circular to oval dark brown spots resembling sesame seeds with yellow halos on leaf blades.",
            "Small round brown spots scattered uniformly across leaves in our unfertilized sandy field.",
            "Leaves are covered with small oval brown spots with distinct yellowish rings around each speck.",
            "Dark brown sesame-like spots all over the rice foliage; soil is poor and lacking fertilizer.",
            "Oval brown spots with prominent yellow halos on seedlings grown from farm-saved seed.",
            "Uniform brown spotting across all tillers on nutrient-deficient, sandy soil.",
            "Small circular brown lesions with light yellow margins spreading across older and younger leaves.",
            "Brown specks resembling sesame seeds on leaf blades without any water-soaked wavy borders.",
            "Leaves have numerous small dark spots surrounded by chlorotic yellow halos in degraded soil.",
            "Dark brown oval lesions with bright yellow halos across entire field plots lacking potassium."
        ]
        
        # 6. Ambiguous / Under-specified Templates
        self.ambiguous_phrasings = [
            "My rice leaves are turning yellow.",
            "Some plants in my field have yellowish leaves during tillering.",
            "I noticed discoloration on the leaf blades.",
            "The rice crop is showing yellowing in some areas.",
            "Leaves are turning yellow-brown during early vegetative stage.",
            "There is general yellowing of foliage in my rice field.",
            "Several tillers have pale yellow leaves.",
            "The rice plants look unhealthy and leaves are yellow.",
            "I see yellow patches in my paddy field.",
            "Foliage is losing green color and turning pale yellow.",
            "There are some spots and yellowing on the rice foliage.",
            "Leaves look discolored after rain and cool nights."
        ]
        
        # 7. Escalation Templates
        self.escalation_phrasings = [
            "Panicles are rotting with severe black grain discoloration and complete head blight across all fields.",
            "Catastrophic sudden wilting and total death of all seedlings within 24 hours across entire nursery.",
            "Uncontrollable rapid spread of black rotting panicles with complete grain loss across 10 hectares.",
            "Entire nursery bed collapsed overnight with complete systemic rotting and foul smell.",
            "Panicles completely blackened and rotting with rapid district-wide collapse of the crop.",
            "Panicle neck nodes are blackened and rotting, snapping off and causing complete empty whiteheads across the field."
        ]
        
        self.growth_stages = ["seedling", "tillering", "heading", "flowering", "ripening"]
        self.weather_conditions = ["heavy_rainfall", "high_humidity", "standing_water", "drought", "prolonged_dry_spell", "cool_foggy", "dewy_mornings", "normal_weather"]
        self.water_conditions = ["flooded", "standing_water", "normal_irrigation", "drained", "dry_soil", "severe_drought"]
        self.field_distributions = ["patchy_distribution", "uniform_fieldwide_distribution", "focal_hotspots", "elevation_dependent_distribution"]
        self.varieties = ["local_inbred", "hybrid_rice", "ir64", "swarna", "bpt5204", "unknown"]

    def generate_thought_trace(self, utterance: str, context: Dict[str, Any], explicit_obs: List[Dict[str, Any]], res: Dict[str, Any]) -> str:
        """Generates a detailed, scientifically transparent 3VL reasoning chain-of-thought."""
        lines = ["<thought>"]
        lines.append("1. OBSERVATION EXTRACTION & SKOS NORMALIZATION:")
        lines.append(f'   - Farmer Utterance: "{utterance}"')
        lines.append(f'   - Phenological Context: Growth Stage = {context.get("growth_stage", "unspecified")}, Water = {context.get("water_condition", "unspecified")}, Weather = {context.get("weather", "unspecified")}')
        
        if explicit_obs:
            for obs in explicit_obs:
                lines.append(f'   - Extracted Observation: `{obs["term_id"]}` (State = {obs["state"]})')
        else:
            lines.append("   - Extracted Observation: `symptom:leaf_yellowing` (State = TRUE from utterance)")
        
        lines.append("\n2. THREE-VALUED LOGIC (3VL) CANDIDATE EVALUATION:")
        lines.append("   - Evaluating candidates under Open-World Assumption (Score = 3*sign + 2*symptom + 2*env + 1*stage + 1*field - 3*contradiction)")
        
        status = res.get("status", "unknown")
        if status == "high_risk_escalation":
            lines.append("   - CRITICAL SAFETY TRIGGER DETECTED: Emergency pathogen escalation condition triggered.")
            lines.append("   - Action: Suppress standard differential diagnosis and trigger official pathology extension escalation.")
        elif status == "needs_more_information":
            lines.append("   - Under-specified symptom profile: Missing critical distinguishing parameters (lesion margin, leaf age, lesion shape, water test).")
            lines.append("   - Candidate Differential retained: Bacterial Leaf Blight, Nitrogen Deficiency, Water-Related Stress, Rice Blast, Brown Spot.")
            lines.append(f'   - Question Utility Ranking: Generated {len(res.get("observations_needed", []))} clarifying questions to separate candidates.')
        else:
            diff = res.get("differential", [])
            for d in diff:
                lines.append(f'   - Candidate `{d["cause_id"]}` (Rank {d.get("rank")}, Confidence: {d.get("confidence_band", "unknown")}):')
                lines.append(f'     * Supporting Observations: {", ".join(d.get("supporting_observations", [])) or "None"}')
                lines.append(f'     * Contradicting Observations: {", ".join(d.get("contradicting_observations", [])) or "None"}')
                lines.append(f'     * Missing Distinguishing: {", ".join(d.get("missing_distinguishing_observations", [])) or "None"}')
        
        lines.append("\n3. SAFETY & PROVENANCE VERIFICATION:")
        esc_info = res.get("escalation", {})
        esc_req = esc_info.get("required", False) if isinstance(esc_info, dict) else False
        lines.append(f'   - Escalation Required: {esc_req}')
        lines.append("   - Prohibited Chemicals Checked: 0 brand names or dosages prescribed (Strictly principle-level cultural management).")
        lines.append(f'   - Grounding Claims Bound: {len(res.get("grounding", []))} PROV-O claims linked.')
        lines.append("</thought>")
        
        return "\n".join(lines)

    def generate_single_sample(self, scenario_type: str, sample_idx: int) -> Optional[Dict[str, Any]]:
        """Generates a single verified SFT ChatML training sample."""
        growth_stage = random.choice(self.growth_stages)
        water = random.choice(self.water_conditions)
        weather = random.choice(self.weather_conditions)
        variety = random.choice(self.varieties)
        
        context = {
            "growth_stage": growth_stage,
            "water_condition": water,
            "weather": weather,
            "variety": variety,
            "case_id": f"sft-{scenario_type[:3]}-{sample_idx:04d}"
        }
        
        explicit_obs = []
        messages = []
        
        if scenario_type == "ambiguous":
            utterance = random.choice(self.ambiguous_phrasings)
            explicit_obs = [{"term_id": "symptom:leaf_yellowing", "state": "TRUE"}]
            if random.random() < 0.5:
                explicit_obs.append({"term_id": f"stage:{growth_stage}", "state": "TRUE"})
            
        elif scenario_type == "blb_positive":
            utterance = random.choice(self.blb_phrasings)
            explicit_obs = [
                {"term_id": "symptom:leaf_yellowing", "state": "TRUE"},
                {"term_id": "symptom:water_soaked_wavy_lesion", "state": "TRUE"},
                {"term_id": "part:leaf", "state": "TRUE"}
            ]
            if "rain" in weather or "flood" in water or "humid" in weather:
                explicit_obs.append({"term_id": "env:heavy_rainfall", "state": "TRUE"})
                explicit_obs.append({"term_id": "field:patchy_distribution", "state": "TRUE"})
            if random.random() < 0.4:
                explicit_obs.append({"term_id": "sign:water_test_cloudy_streaming", "state": "TRUE"})
                
        elif scenario_type == "ndef_positive":
            utterance = random.choice(self.ndef_phrasings)
            explicit_obs = [
                {"term_id": "symptom:leaf_yellowing", "state": "TRUE"},
                {"term_id": "symptom:uniform_older_leaf_chlorosis", "state": "TRUE"},
                {"term_id": "part:older_leaves", "state": "TRUE"},
                {"term_id": "field:uniform_fieldwide_distribution", "state": "TRUE"}
            ]
            if random.random() < 0.5:
                explicit_obs.append({"term_id": "symptom:stunted_growth", "state": "TRUE"})
                
        elif scenario_type == "wstress_positive":
            utterance = random.choice(self.wstress_phrasings)
            explicit_obs = [
                {"term_id": "symptom:leaf_rolling_folding", "state": "TRUE"},
                {"term_id": "field:elevation_dependent_distribution", "state": "TRUE"},
                {"term_id": "part:leaf", "state": "TRUE"}
            ]
            if "dry" in water or "drought" in weather:
                explicit_obs.append({"term_id": "sign:recovers_upon_rewatering", "state": "TRUE"})

        elif scenario_type == "blast_positive":
            utterance = random.choice(self.blast_phrasings)
            explicit_obs = [
                {"term_id": "symptom:spindle_shaped_lesion", "state": "TRUE"},
                {"term_id": "part:leaf", "state": "TRUE"}
            ]
            if "cool" in weather or "fog" in weather or "dew" in weather or "humid" in weather:
                explicit_obs.append({"term_id": "env:cool_night_temperatures", "state": "TRUE"})
                explicit_obs.append({"term_id": "env:prolonged_dew_periods", "state": "TRUE"})
            if random.random() < 0.35:
                explicit_obs.append({"term_id": "sign:gray_spore_felt", "state": "TRUE"})
            if random.random() < 0.3:
                explicit_obs.append({"term_id": "field:focal_hotspots", "state": "TRUE"})
            if random.random() < 0.2:
                explicit_obs.append({"term_id": "symptom:collar_rot", "state": "TRUE"})

        elif scenario_type == "bspot_positive":
            utterance = random.choice(self.bspot_phrasings)
            explicit_obs = [
                {"term_id": "symptom:oval_brown_spots", "state": "TRUE"},
                {"term_id": "symptom:yellow_halo_around_brown_spot", "state": "TRUE"},
                {"term_id": "part:leaf", "state": "TRUE"}
            ]
            if random.random() < 0.5:
                explicit_obs.append({"term_id": "env:nutrient_depleted_poor_soil", "state": "TRUE"})
            if random.random() < 0.4:
                explicit_obs.append({"term_id": "field:uniform_fieldwide_distribution", "state": "TRUE"})
                
        elif scenario_type == "negative_3vl":
            sub_opt = random.choice(["blb_neg", "streaming_neg", "blast_neg", "bspot_neg"])
            if sub_opt == "blb_neg":
                utterance = "Leaves are yellow across the whole field, but there are definitely no wavy lesions or water-soaked stripes."
                explicit_obs = [
                    {"term_id": "symptom:leaf_yellowing", "state": "TRUE"},
                    {"term_id": "symptom:uniform_older_leaf_chlorosis", "state": "TRUE"},
                    {"term_id": "symptom:water_soaked_wavy_lesion", "state": "FALSE"},
                    {"term_id": "field:uniform_fieldwide_distribution", "state": "TRUE"}
                ]
            elif sub_opt == "streaming_neg":
                utterance = "Leaf tips are turning brown and drying, but when I did the cut leaf water test, the water remained completely clear with no cloudy streaming."
                explicit_obs = [
                    {"term_id": "symptom:leaf_yellowing", "state": "TRUE"},
                    {"term_id": "sign:water_test_cloudy_streaming", "state": "FALSE"},
                    {"term_id": "symptom:leaf_rolling_folding", "state": "TRUE"}
                ]
            elif sub_opt == "blast_neg":
                utterance = "Spots on leaf blades, but they are circular sesame dots with halos and definitely not diamond or spindle shaped."
                explicit_obs = [
                    {"term_id": "symptom:spindle_shaped_lesion", "state": "FALSE"},
                    {"term_id": "symptom:oval_brown_spots", "state": "TRUE"}
                ]
            else:
                utterance = "Leaf lesions are diamond spindle shaped with gray center, not small oval sesame spots."
                explicit_obs = [
                    {"term_id": "symptom:oval_brown_spots", "state": "FALSE"},
                    {"term_id": "symptom:spindle_shaped_lesion", "state": "TRUE"}
                ]
                
        elif scenario_type == "escalation":
            utterance = random.choice(self.escalation_phrasings)
            if "panicle" in utterance.lower() or "neck" in utterance.lower():
                explicit_obs = [
                    {"term_id": "symptom:neck_rot_blackened_node", "state": "TRUE"}
                ]
            else:
                explicit_obs = [
                    {"term_id": "symptom:leaf_tip_margin_necrosis", "state": "TRUE"}
                ]
            context["water_condition"] = "flooded"
            context["weather"] = "cyclone_storm"
            
        elif scenario_type == "multiturn":
            path = random.choice(["blb", "ndef", "wstress", "blast", "bspot"])
            if path == "blb":
                turn1_user = "The rice leaves in my paddy are turning yellow in patches after rain."
                turn1_obs = [{"term_id": "symptom:leaf_yellowing", "state": "TRUE"}]
                turn2_user = "I checked the leaves: the lesions have irregular wavy, water-soaked edges on the top leaf blades."
                turn2_obs = [
                    {"term_id": "symptom:leaf_yellowing", "state": "TRUE"},
                    {"term_id": "symptom:water_soaked_wavy_lesion", "state": "TRUE"},
                    {"term_id": "field:patchy_distribution", "state": "TRUE"}
                ]
            elif path == "ndef":
                turn1_user = "Our rice crop looks yellowish and tillers seem weak across the whole field."
                turn1_obs = [{"term_id": "symptom:leaf_yellowing", "state": "TRUE"}]
                turn2_user = "I inspected leaf age: strictly the lowest, oldest leaves are pale yellow and dying, while upper leaves stay pale green."
                turn2_obs = [
                    {"term_id": "symptom:leaf_yellowing", "state": "TRUE"},
                    {"term_id": "symptom:uniform_older_leaf_chlorosis", "state": "TRUE"},
                    {"term_id": "field:uniform_fieldwide_distribution", "state": "TRUE"}
                ]
            elif path == "wstress":
                turn1_user = "Rice leaf blades are rolling and tips look dry in the upland area."
                turn1_obs = [{"term_id": "symptom:leaf_rolling_folding", "state": "TRUE"}]
                turn2_user = "After running canal water to irrigate yesterday evening, the rolled leaves uncurled and recovered overnight."
                turn2_obs = [
                    {"term_id": "symptom:leaf_rolling_folding", "state": "TRUE"},
                    {"term_id": "symptom:recovers_upon_rewatering", "state": "TRUE"}
                ]
            elif path == "blast":
                turn1_user = "There are brown spots appearing on the leaves during foggy morning weather."
                turn1_obs = [{"term_id": "symptom:leaf_yellowing", "state": "TRUE"}]
                turn2_user = "Looking closely, the spots are diamond and spindle-shaped with ash-gray centers and reddish-brown borders."
                turn2_obs = [
                    {"term_id": "symptom:spindle_shaped_lesion", "state": "TRUE"},
                    {"term_id": "env:cool_night_temperatures", "state": "TRUE"}
                ]
            else: # bspot
                turn1_user = "I noticed small speckled spots on the leaves across our unfertilized sandy field."
                turn1_obs = [{"term_id": "symptom:leaf_yellowing", "state": "TRUE"}]
                turn2_user = "The spots are small, circular to oval like sesame seeds, with prominent yellow halos around each brown spot."
                turn2_obs = [
                    {"term_id": "symptom:oval_brown_spots", "state": "TRUE"},
                    {"term_id": "symptom:yellow_halo_around_brown_spot", "state": "TRUE"},
                    {"term_id": "env:nutrient_depleted_poor_soil", "state": "TRUE"}
                ]

            turn1_res = self.engine.diagnose(turn1_user, context, turn1_obs)
            turn1_thought = self.generate_thought_trace(turn1_user, context, turn1_obs, turn1_res)
            
            messages.append({"role": "system", "content": SYSTEM_PROMPT})
            messages.append({"role": "user", "content": f"Context: {json.dumps(context)}\n\nFarmer Query: {turn1_user}"})
            messages.append({"role": "assistant", "content": f"{turn1_thought}\n\n```json\n{json.dumps(turn1_res, indent=2)}\n```"})
            
            turn2_res = self.engine.diagnose(turn2_user, context, turn2_obs)
            turn2_thought = self.generate_thought_trace(turn2_user, context, turn2_obs, turn2_res)
            
            messages.append({"role": "user", "content": f"Observation Follow-up: {turn2_user}"})
            messages.append({"role": "assistant", "content": f"{turn2_thought}\n\n```json\n{json.dumps(turn2_res, indent=2)}\n```"})
            
            s_ok, _ = self.verifier.verify_structural(turn2_res)
            saf_ok, _ = self.verifier.verify_safety(turn2_res)
            g_ok, _ = self.verifier.verify_graph(turn2_res)
            l_ok, _ = self.verifier.verify_logical(turn2_res)
            
            if s_ok and saf_ok and g_ok and l_ok:
                return {
                    "id": f"sft-traj-{sample_idx:05d}",
                    "scenario_type": scenario_type,
                    "turns": 2,
                    "messages": messages,
                    "metadata": {
                        "growth_stage": growth_stage,
                        "primary_cause": turn2_res.get("differential", [{}])[0].get("cause_id", "none") if turn2_res.get("differential") else "none",
                        "verified": True
                    }
                }
            return None

        # Single Turn Execution
        res = self.engine.diagnose(utterance, context, explicit_obs)
        thought_trace = self.generate_thought_trace(utterance, context, explicit_obs, res)
        
        s_ok, _ = self.verifier.verify_structural(res)
        saf_ok, _ = self.verifier.verify_safety(res)
        g_ok, _ = self.verifier.verify_graph(res)
        l_ok, _ = self.verifier.verify_logical(res)
        
        if not (s_ok and saf_ok and g_ok and l_ok):
            return None
            
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
        messages.append({"role": "user", "content": f"Context: {json.dumps(context)}\n\nFarmer Query: {utterance}"})
        messages.append({"role": "assistant", "content": f"{thought_trace}\n\n```json\n{json.dumps(res, indent=2)}\n```"})
        
        primary_cause = res.get("differential", [{}])[0].get("cause_id", "none") if res.get("differential") else res.get("status")
        
        return {
            "id": f"sft-traj-{sample_idx:05d}",
            "scenario_type": scenario_type,
            "turns": 1,
            "messages": messages,
            "metadata": {
                "growth_stage": growth_stage,
                "water_condition": water,
                "weather": weather,
                "primary_cause": primary_cause,
                "verified": True
            }
        }
