import json
import sys
import os

# Ensure project root in path
sys.path.insert(0, "/Users/faezeh/Desktop/Rice")

from engine.integration_pipeline import IntegrationPipeline

def print_banner(title):
    print("\n" + "=" * 80)
    print(f" {title.upper()} ")
    print("=" * 80)

def print_step_header(num, title):
    print(f"\n>>> STEP {num}: {title}")
    print("-" * 80)

def run_trace():
    manager_query = "the rice leaves are yellow in patches after heavy rain and standing water"
    context = {
        "case_id": "case-mgr-demo-001",
        "growth_stage": "tillering",
        "region": "priority-region-1",
        "water_condition": "standing_water",
        "weather": "heavy_rain_storm",
        "variety": "IR64"
    }

    print_banner("Rice Pathogen SALM — End-to-End Integration Pipeline Trace")
    print(f"Target Scenario: \"{manager_query}\"")
    print(f"Context: Growth Stage = {context['growth_stage']}, Region = {context['region']}")

    pipeline = IntegrationPipeline()
    trace = pipeline.run_full_trace(manager_query, context)

    steps = trace["pipeline_steps"]

    # STEP 1
    s1 = steps["step1_terminology_normalization"]
    print_step_header(1, "Observation Extraction & SKOS Terminology Normalization")
    print(f"Farmer Utterance: \"{manager_query}\"\n")
    print(f"{'Source Token Span':<25} | {'Term ID':<35} | {'SKOS Pref Label':<28} | {'State'}")
    print("-" * 105)
    for item in s1["extracted_normalized_terms"]:
        print(f"{item['raw_token_span']:<25} | {item['term_id']:<35} | {item['skos_pref_label']:<28} | {item['truth_state']}")

    # STEP 2
    s2 = steps["step2_candidate_generation"]
    print_step_header(2, "Knowledge Graph Candidate Condition Generation")
    print("Retrieved candidate conditions from ontology matching chlorosis and moisture:")
    for c in s2["candidates"]:
        p_str = f" [Pathogen: {c['pathogen']}]" if c['pathogen'] else " [Abiotic]"
        print(f"  * {c['cause_id']} ({c['display_name']}){p_str}")
        print(f"    - Category: {c['category']}")
        print(f"    - Contrasts Linked: {', '.join(c['active_contrast_pairs'])}")
        print(f"    - Rationale: {c['retrieval_rationale']}")

    # STEP 3
    s3 = steps["step3_candidate_scoring"]
    print_step_header(3, "3-Valued Logic (3VL) Candidate Scoring Matrix")
    print(f"Formula: {s3['formula']}\n")
    print(f"{'Candidate Cause':<32} | {'Arithmetic Computation':<45} | {'Score':<6} | {'Band':<8} | {'Status'}")
    print("-" * 125)
    for sc in s3["scored_candidates"]:
        print(f"{sc['cause_id']:<32} | {sc['formula_arithmetic']:<45} | {sc['total_score']:<6} | {sc['confidence_band']:<8} | {sc['status']}")

    # STEP 4
    s4 = steps["step4_evidence_partitioning"]
    print_step_header(4, "Evidence Partitioning (Supporting vs Contradicting vs Unknown)")
    for cid, ev in s4["evidence_by_candidate"].items():
        print(f"\nCandidate: {cid}")
        print("  [+] Supporting Observations:")
        for supp in ev["supporting_observations"]:
            print(f"      - {supp}")
        print("  [-] Contradicting Observations:")
        if ev["contradicting_observations"]:
            for contra in ev["contradicting_observations"]:
                print(f"      - {contra}")
        else:
            print("      (None - zero contradictions)")
        print("  [?] Missing Distinguishing Observations (Unknowns):")
        for unk in ev["missing_distinguishing_observations"]:
            print(f"      - {unk}")

    # STEP 5
    s5 = steps["step5_question_utility_calculation"]
    print_step_header(5, "Unknowns & Mathematical Question Utility Selection")
    print(f"Formula: {s5['formula']}\n")
    print(f"{'Rank':<5} | {'Question ID':<22} | {'Target Observation':<32} | {'Formula Arithmetic':<25} | {'Utility':<8} | {'Action'}")
    print("-" * 135)
    for q in s5["ranked_questions"]:
        print(f"{q['rank']:<5} | {q['question_id']:<22} | {q['target_observation']:<32} | {q['utility_formula']:<25} | {q['calculated_utility']:<8.1f} | {q['action']}")
    print(f"\nTop Selected Question to Present: \"{s5['ranked_questions'][0]['question_text']}\"")

    # STEP 6
    s6 = steps["step6_hybrid_evidence_retrieval"]
    print_step_header(6, "Hybrid Knowledge Graph & PROV-O Evidence Retrieval")
    print("Retrieved Triples:")
    for tr in s6["graph_context"]["retrieved_triples"]:
        print(f"  * {tr}")
    print("\nProvenance Receipts (W3C PROV-O):")
    for r in s6["graph_context"]["provenance_receipts"]:
        print(f"  * {r['claim_id']} ({r['source_id']} > {r['source_section']})")
        print(f"    Verbatim: \"{r['verbatim_text']}\"")
        print(f"    SME Sign-off: {r['sme_reviewer']} [{r['sme_status']}]")

    # STEP 7
    s7 = steps["step7_post_generation_verification"]
    print_step_header(7, "4-Layer Post-Generation Verification (Section 14.8)")
    for check_name, check_data in s7["verification_checks"].items():
        status_str = "[PASS]" if check_data["passed"] else "[FAIL]"
        print(f"  {status_str} {check_name:<20}: {check_data['details']}")
    print(f"\nOverall Verification Status: {s7['overall_status']}")

    # STEP 8
    s8 = steps["step8_structured_response"]
    print_step_header(8, "Final JSON Response Contract Output (schemas/response.schema.json)")
    print(json.dumps(s8["json_response"], indent=2))

    # Save to data/manager_integration_trace.json
    out_file = "/Users/faezeh/Desktop/Rice/data/manager_integration_trace.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2)
    print_banner(f"Integration Pipeline Execution Complete — Saved to {out_file}")

if __name__ == "__main__":
    run_trace()
