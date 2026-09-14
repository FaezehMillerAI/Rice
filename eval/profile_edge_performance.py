import time
import json
import os
import sys

sys.path.insert(0, "/Users/faezeh/Desktop/Rice")

from engine.slm_baselines import query_ollama

def profile_models():
    models_to_test = ["qwen2.5:1.5b", "llama3.2:1b", "smollm2:1.7b"]
    query = "the rice leaves are yellow in patches after heavy rain and standing water"
    system_prompt = "You are a rice diagnostic model. Output JSON with status, differential, observations_needed."

    print("=" * 80)
    print(" RICE PATHOGEN SALM — EDGE LATENCY & TOKEN THROUGHPUT PROFILING")
    print(f" Test Query: \"{query}\"")
    print("=" * 80)

    results = []

    for model in models_to_test:
        print(f"\nProfiling Model: {model} ...")
        # Warmup
        try:
            query_ollama("test", "test", model, timeout=15)
        except Exception:
            pass

        # Benchmark 3 runs
        latencies = []
        tokens_list = []
        parsed_ok = 0

        for r in range(3):
            t0 = time.time()
            res, lat, toks = query_ollama(query, system_prompt, model, timeout=30)
            latencies.append(lat)
            tokens_list.append(toks)
            if isinstance(res, dict) and "error" not in res and len(res) > 0:
                parsed_ok += 1

        avg_latency = sum(latencies) / len(latencies)
        avg_tokens = sum(tokens_list) / len(tokens_list)
        tps = (avg_tokens / avg_latency) if avg_latency > 0 else 0.0

        print(f"  * Avg Latency: {avg_latency*1000:.1f} ms")
        print(f"  * Avg Output Tokens: {avg_tokens:.1f}")
        print(f"  * Throughput: {tps:.1f} tokens/sec")
        print(f"  * JSON Parse Success: {parsed_ok}/3")

        results.append({
            "model_name": model,
            "avg_latency_ms": round(avg_latency * 1000, 1),
            "avg_tokens": round(avg_tokens, 1),
            "throughput_tps": round(tps, 1),
            "json_success_rate": round(parsed_ok / 3 * 100, 1)
        })

    out_file = "/Users/faezeh/Desktop/Rice/data/edge_profiling_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved Edge Profiling Report to {out_file}\n")

if __name__ == "__main__":
    profile_models()
