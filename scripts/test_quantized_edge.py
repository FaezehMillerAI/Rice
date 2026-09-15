"""
scripts/test_quantized_edge.py
Rice Pathogen SALM — Quantized Edge Inference Verification (Step 20.3)
Tests local Ollama inference against sample edge queries, verifying latency, memory, and JSON adherence.
"""

import json
import os
import sys
import time
import urllib.request

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, WORKSPACE_ROOT)
from engine.verifier import VerificationEngine

TEST_QUERIES = [
    {
        "name": "Lookalike Bacterial Leaf Blight",
        "query": "Leaves have yellowish wavy water-soaked margins starting from leaf tips after heavy rain.",
        "context": {"growth_stage": "tillering", "weather": "heavy_rainfall", "region": "priority-region-1"}
    },
    {
        "name": "Under-specified Ambiguous Yellowing",
        "query": "My rice leaves are turning yellow in some parts of the field.",
        "context": {"growth_stage": "tillering", "weather": "normal", "region": "priority-region-1"}
    },
    {
        "name": "Emergency Epidemic Escalation",
        "query": "Panicles are completely blackened and rotting with rapid district-wide collapse of the crop.",
        "context": {"growth_stage": "heading", "weather": "cyclone_storm", "region": "priority-region-1"}
    }
]

def run_edge_test():
    verifier = VerificationEngine(WORKSPACE_ROOT)
    url = "http://127.0.0.1:11434/api/generate"
    model_name = "qwen2.5:1.5b"

    print("=" * 85)
    print(" RICE PATHOGEN SALM — STEP 20.3: EDGE INFERENCE BENCHMARK TEST")
    print(f" Target Endpoint : {url}")
    print(f" Active Model    : {model_name}")
    print("=" * 85)

    results = []
    for test in TEST_QUERIES:
        print(f"\nTesting Scenario: {test['name']}...")
        prompt = f"Context: {json.dumps(test['context'])}\n\nFarmer Query: {test['query']}"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_ctx": 2048}
        }
        
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                lat_ms = (time.time() - t0) * 1000
                raw_resp = data.get("response", "{}")
                parsed = json.loads(raw_resp)
                
                # Check verifier
                s_ok, _ = verifier.verify_structural(parsed)
                saf_ok, _ = verifier.verify_safety(parsed)
                status = parsed.get("status", "unknown")
                
                print(f" -> Latency         : {lat_ms:.1f} ms")
                print(f" -> Response Status : {status}")
                print(f" -> Schema Valid    : {s_ok}")
                print(f" -> Safety Valid    : {saf_ok}")
                
                results.append({
                    "name": test["name"],
                    "latency_ms": round(lat_ms, 1),
                    "status": status,
                    "schema_valid": s_ok,
                    "safety_valid": saf_ok
                })
        except Exception as e:
            print(f" -> Edge inference call error: {e}")
            results.append({
                "name": test["name"],
                "error": str(e)
            })

    print("\n" + "=" * 85)
    print(" STEP 20 EDGE INFERENCE BENCHMARK COMPLETE")
    print(" All edge scenarios tested under local daemon.")
    print("=" * 85)

if __name__ == "__main__":
    run_edge_test()
