# Rice SFT, Evaluation, and Deployment

This guide provides the shortest path for running the current SFT, unified evaluation, and Ollama deployment workflows on a new Linux machine. Run all commands from the repository root.

## 1. End-to-End Workflow

~~~text
SFT data + KG context
        |
        v
QLoRA/LoRA training -> adapter
        |
        +------> base/tuned evaluation
        |
        v
LoRA merge -> merged Hugging Face model
        |
        v
GGUF conversion + Q4_K_M quantization
        |
        v
ollama create -> local model tag
        |
        v
field_app: KG retrieval -> Ollama -> contract -> verifier -> KG fallback
~~~

- **SFT:** Uses the shared KG retriever and Prompt v0.3 to build training inputs, then trains a LoRA adapter with teacher forcing.
- **Evaluation:** Compares KG-only, base-model, and tuned-model results on the same benchmark. It preserves raw model output, does not repair JSON, and does not use the deployment fallback.
- **Deployment:** Merges the adapter, converts the merged model to GGUF, and serves it through Ollama. If the model output is invalid, the field application falls back to the deterministic KG path.

## 2. Set Up a New Machine

### 2.1 Prerequisites

- Linux x86_64.
- Git, curl, CMake, and C/C++ build tools.
- An NVIDIA driver and an available GPU. Run `nvidia-smi` first to verify the setup. The training environment uses the CUDA 12.9 PyTorch wheel.
- Access to Hugging Face, or a prepared local model cache. Meta Llama models also require the relevant access approval.
- Enough disk space for the model cache, adapters, merged models, and GGUF files.

### 2.2 Install uv

Use the official Linux installer:

~~~bash
curl -LsSf https://astral.sh/uv/install.sh | sh
~~~

Open a new terminal and verify the installation:

~~~bash
uv --version
~~~

### 2.3 Clone the Repository and Install Locked Dependencies

~~~bash
git clone git@github.com:FaezehMillerAI/Rice.git
cd Rice

uv sync --locked
~~~

`uv sync --locked` creates the project `.venv` from `uv.lock` and installs the locked dependencies. You do not need to activate the environment manually; use `uv run --locked ...` for subsequent commands.

Check Python, PyTorch, and CUDA:

~~~bash
uv run --locked python -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
~~~

## 3. SFT

The default configuration is `configs/sft/training_config.yaml`:

- **Model:** Selected by a short name such as `qwen3-4b`.
- **Data:** `data/sft/train_dummy_v0.3.json` and `data/sft/validation_dummy_v0.3.json`.
- **Training:** 3 epochs, learning rate `1e-4`, and LoRA rank 16.
- **Quantization:** 4-bit NF4 QLoRA.
- **Output:** `outputs/sft/<experiment-name>/`.

### 3.1 Train Qwen3-4B

First, validate the data and generated prompt:

~~~bash
uv run --locked python -m sft.trainer \
  --model qwen3-4b \
  --dry-run
~~~

Start training in the background:

~~~bash
uv run --locked python -u -m sft.trainer \
  --model qwen3-4b \
  --background
~~~

Default output directory:

~~~text
outputs/sft/qwen3-4b_ep3_lr1e-4_seed42
~~~

Follow the log or stop the training process:

~~~bash
tail -f outputs/sft/qwen3-4b_ep3_lr1e-4_seed42/train.log
kill "$(cat outputs/sft/qwen3-4b_ep3_lr1e-4_seed42/train.pid)"
~~~

### 3.2 Change the Learning Rate

~~~bash
# 5e-4
uv run --locked python -u -m sft.trainer \
  --config configs/sft/training_config_lr5e-4.yaml \
  --model qwen3-4b \
  --background

# 1e-3
uv run --locked python -u -m sft.trainer \
  --config configs/sft/training_config_lr1e-3.yaml \
  --model qwen3-4b \
  --background
~~~

### 3.3 Run Batch Queues

`sft/run_all_models.sh` trains the six-model `1e-4` baseline sequentially. `sft/run_lr_sweep.sh` then runs all six models at `5e-4` and `1e-3`, for 12 additional runs.

~~~bash
mkdir -p outputs/sft/logs

nohup bash sft/run_all_models.sh \
  > outputs/sft/logs/baseline_queue.log 2>&1 &
baseline_pid=$!

nohup env WAIT_FOR_PID="$baseline_pid" bash sft/run_lr_sweep.sh \
  > outputs/sft/logs/lr_sweep_queue.log 2>&1 &
~~~

Follow the queues:

~~~bash
tail -f outputs/sft/logs/baseline_queue.log
tail -f outputs/sft/logs/lr_sweep_queue.log
~~~

## 4. Evaluation

The default scoring configuration is `configs/eval/eval_config.yaml`, and the default benchmark is `data/eval/gold_eval_v0.4.json`. Reports are written to:

~~~text
outputs/eval/unified/<UTC_TIMESTAMP>/
~~~

The evaluator supports three modes:

- `kg-only`: Runs only the deterministic KG path.
- `model-only`: Gives the model only the public case fields.
- `kg+model`: Gives the model the public case fields and KG retrieval context.

### 4.1 KG Baseline

~~~bash
uv run --locked python -u -m eval.evaluate_unified \
  --modes kg-only
~~~

### 4.2 Base Model

Run a one-case smoke test first:

~~~bash
uv run --locked python -u -m eval.evaluate_unified \
  --modes model-only kg+model \
  --model qwen3-4b \
  --limit 1 \
  --show-steps
~~~

Remove `--limit 1 --show-steps` for a full evaluation.

### 4.3 Tuned Adapter

~~~bash
uv run --locked python -u -m eval.evaluate_unified \
  --modes model-only kg+model \
  --adapter outputs/sft/qwen3-4b_ep3_lr1e-4_seed42
~~~

The evaluator infers the base model from `adapter_config.json`. Do not pass an adapter path to `--model`.

Example background evaluation:

~~~bash
mkdir -p outputs/eval/logs

nohup uv run --locked python -u -m eval.evaluate_unified \
  --modes model-only kg+model \
  --adapter outputs/sft/qwen3-4b_ep3_lr1e-4_seed42 \
  > outputs/eval/logs/qwen3-4b_tuned.log 2>&1 &
~~~

## 5. Deployment

Deployment preparation is a one-time pipeline:

~~~text
adapter -> merged-hf -> Q4_K_M GGUF -> Ollama tag
~~~

The following examples use:

~~~bash
RUN=qwen3-4b_ep3_lr1e-4_seed42
DEPLOY=outputs/deploy/$RUN
TAG=rice-qwen3-4b-lr1e-4:q4_k_m
LLAMA_CPP=../llama.cpp
~~~

Set these variables in the same terminal before running the remaining commands. The export scripts refuse to overwrite existing artifacts by default; use a new `DEPLOY` directory when repeating the process.

### 5.1 Merge the LoRA Adapter

~~~bash
uv run --locked python -u scripts/merge_lora.py \
  --adapter "outputs/sft/$RUN" \
  --output-dir "$DEPLOY/merged-hf"
~~~

The script reads the exact base model from the adapter, performs a safe merge on CPU in FP32, and saves a complete FP16 model by default.

### 5.2 Prepare llama.cpp

GGUF conversion requires the external llama.cpp converter and `llama-quantize`. This setup is needed only once:

~~~bash
git clone https://github.com/ggml-org/llama.cpp.git "$LLAMA_CPP"

cmake -S "$LLAMA_CPP" -B "$LLAMA_CPP/build"
cmake --build "$LLAMA_CPP/build" --config Release -j
~~~

### 5.3 Convert and Quantize to GGUF

~~~bash
uv run --isolated \
  --with-requirements "$LLAMA_CPP/requirements/requirements-convert_hf_to_gguf.txt" \
  python scripts/export_quantized_gguf.py \
  --merged-dir "$DEPLOY/merged-hf" \
  --output-dir "$DEPLOY/gguf" \
  --converter "$LLAMA_CPP/convert_hf_to_gguf.py" \
  --quantizer "$LLAMA_CPP/build/bin/llama-quantize" \
  --quant-type Q4_K_M
~~~

`--isolated` gives the llama.cpp converter its own dependencies and avoids a conflict with the Transformers version used by the Rice project. The output contains the GGUF file, `Modelfile`, and `deployment_metadata.json`.

### 5.4 Install Ollama and Import the Model

Install Ollama on a new machine:

~~~bash
curl -fsSL https://ollama.com/install.sh | sh
~~~

If the installer does not start the service automatically, run this in a separate terminal:

~~~bash
ollama serve
~~~

Import the GGUF model:

~~~bash
ollama create "$TAG" -f "$DEPLOY/gguf/Modelfile"
ollama list
~~~

### 5.5 Evaluate the Quantized Ollama Model

~~~bash
uv run --locked python -u -m eval.evaluate_unified \
  --modes model-only kg+model \
  --backend ollama \
  --model "$TAG" \
  --ollama-format json \
  --limit 1
~~~

The Ollama backend can only use an imported model tag; it cannot load an adapter through `--adapter`.

### 5.6 Start the Field Application

~~~bash
./run_offline_pilot.sh --model "$TAG"
~~~

The field application:

1. Checks the Ollama server and exact model tag.
2. Reads the farmer description and growth stage from the terminal.
3. Retrieves KG context and builds Prompt v0.3.
4. Calls Ollama with the full response JSON schema as an output constraint.
5. Applies the response contract and current verifier.
6. Falls back to the deterministic KG path if the model path fails.
7. Displays the result and writes SQLite/JSONL telemetry.

`eval.evaluate_unified` is not part of field request handling; it is used only for pre-deployment evaluation.

## 6. Local Ollama Runtime on the Development Machine

The current development machine also has a local Ollama bundle under `runtime/ollama/`:

~~~bash
runtime/ollama/start.sh
runtime/ollama/status.sh
runtime/ollama/stop.sh
~~~

`runtime/` is ignored by Git, so these files will not appear in a fresh clone. On a new machine, install the system Ollama package as described in Section 5.4.

## 7. Common Output Directories

| Directory | Contents |
| --- | --- |
| `outputs/sft/` | Adapters, checkpoints, training logs, and configuration snapshots |
| `outputs/eval/unified/` | Unified evaluation report for each run |
| `outputs/deploy/` | Merged Hugging Face models, GGUF files, and deployment metadata |
| `telemetry/` | SQLite and JSONL records from the field CLI |

## 8. Official References

- [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
- [uv project locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [Install Ollama on Linux](https://github.com/ollama/ollama/blob/main/docs/linux.mdx)
- [Build llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)
