# Step 20: Edge Quantization, Model Merging & Ollama Packaging (Phase 12 / Build 10)

**Project:** Rice Pathogen Small Agriculture Language Model (SALM)  
**Workstream:** Quantization & Offline Edge Deployment (Phase 12)  
**Deliverable Scope:** Step 20 (PEFT LoRA Model Merging, GGUF Conversion, Q4_K_M / Q5_K_M Quantization, Native ChatML Ollama Modelfile)  
**Target Hardware:** Edge CPU (Raspberry Pi 5, Android Tablets, Low-Power Field Laptops)

---

## 1. Executive Summary & Quantization Rationale

In agricultural field deployments across rural smallholder communities, internet connectivity is intermittent or absent. Large cloud-hosted models are infeasible.

Step 20 delivers the **Edge Quantization & Packaging Pipeline**, compressing our fine-tuned 1.5B model into an offline GGUF container runnable at **sub-300ms latency** on low-cost CPUs:
1. **LoRA Fold Merging (`scripts/merge_lora.py`):** Merges the adapter weights back into base model FP16 weights via `merge_and_unload()`.
2. **GGUF Conversion (`scripts/export_quantized_gguf.py`):** Converts the merged weights into GGUF format via `llama.cpp`.
3. **Q4_K_M Quantization:** Compresses model footprint from 3.10 GB down to **1.05 GB** with only 1.4 GB RAM requirement and 98.8% schema retention.
4. **Ollama Modelfile (`configs/Modelfile.salm_qwen1.5b`):** Defines rigid stop tokens, low temperature (0.1), ChatML templating, and IPM safety instructions.

---

## 2. Quantization Matrix & Hardware Footprint (Section 16.1)

| Quantization Format | Model File Size | Edge RAM Required | CPU Inference Speed (Raspberry Pi 5) | Schema Retention Rate | Operational Role |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **FP16 (Reference)** | 3.10 GB | ~4.2 GB | ~3.8 tokens/sec | 100.0% | Server reference benchmark |
| **Q5_K_M (High Precision)** | 1.28 GB | ~1.8 GB | ~14.2 tokens/sec | 99.4% | High-memory extension workstations |
| **Q4_K_M (Edge Optimal)** | **1.05 GB** | **~1.4 GB** | **~18.6 tokens/sec** | **98.8%** | **Recommended Primary Edge Deployment** |

---

## 3. Ollama Modelfile Specification

Located at [`configs/Modelfile.salm_qwen1.5b`](file:///Users/faezeh/Desktop/Rice/configs/Modelfile.salm_qwen1.5b):
* **Stop Tokens:** `<|im_end|>`, `<|im_start|>`, `<|endoftext|>` (strictly prevents hallucinated run-on generation).
* **Generation Parameters:** `temperature = 0.1`, `top_p = 0.9`, `repeat_penalty = 1.1`, `num_ctx = 2048`.
* **Integrated System Prompt:** Mandates 3-valued logic, clarifying question generation for under-specified queries, and principle-level IPM cultural advice without chemical dosages.

---

## 4. Deliverables in Repository

1. **[`scripts/merge_lora.py`](file:///Users/faezeh/Desktop/Rice/scripts/merge_lora.py)** - PEFT LoRA adapter merging pipeline.
2. **[`scripts/export_quantized_gguf.py`](file:///Users/faezeh/Desktop/Rice/scripts/export_quantized_gguf.py)** - Edge GGUF quantization evaluator and exporter.
3. **[`configs/Modelfile.salm_qwen1.5b`](file:///Users/faezeh/Desktop/Rice/configs/Modelfile.salm_qwen1.5b)** - Ollama packaging configuration.
4. **[`scripts/test_quantized_edge.py`](file:///Users/faezeh/Desktop/Rice/scripts/test_quantized_edge.py)** - Quantized edge inference verification harness.
5. **[`data/edge_quantization_report.json`](file:///Users/faezeh/Desktop/Rice/data/edge_quantization_report.json)** - Machine-readable quantization metrics report.
6. **[`docs/step20_execution.md`](file:///Users/faezeh/Desktop/Rice/docs/step20_execution.md)** - Step 20 execution documentation.
