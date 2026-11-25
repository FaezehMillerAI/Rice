# SFT

Train a LoRA/QLoRA adapter from the original scenarios with a shared YAML configuration and a model short name. Retrieval runs once per scenario during data preparation; prepared prompts and completions are reused during training.

## Configuration

`configs/sft/training_config.yaml` contains all model choices, data paths, quantization, LoRA, training, logging, and output settings. It is the default for the trainer.

| Short name | Hugging Face model |
| --- | --- |
| `qwen2.5-1.5b` | `Qwen/Qwen2.5-1.5B-Instruct` |
| `qwen3-4b` | `Qwen/Qwen3-4B-Instruct-2507` |
| `phi4-mini` | `microsoft/Phi-4-mini-instruct` |
| `smollm3-3b` | `HuggingFaceTB/SmolLM3-3B` |
| `qwen3.5-4b` | `Qwen/Qwen3.5-4B` |
| `llama3.2-3b` | `meta-llama/Llama-3.2-3B-Instruct` |

Omit `--model` to use `model: qwen2.5-1.5b` from the YAML. The trainer's `--help` lists the current model short names from the default YAML's `models` keys. Each `models` entry holds its full `id`, LoRA `target_modules`, and any `chat_template_kwargs`; the remaining settings are shared. Phi uses fused `qkv_proj`; Qwen3.5 also targets `in_proj_qkv`. SmolLM3 and Qwen3.5 disable thinking in their chat templates. Model loading uses `trust_remote_code=False`.

The defaults use `data/sft/train_dummy_v0.3.json` (200 cases) and `data/sft/validation_dummy_v0.3.json` (50 cases), 3 epochs, learning rate `1e-4`, LoRA rank 16, and 4-bit NF4 quantization. The configured `training.max_seq_length` is 3072 tokens for the complete prompt, target answer, and chat-template markers. Longer examples cause an explicit error before model loading, rather than truncating the prompt or assistant labels. Dry runs do not check token lengths.

The v0.3 dataset uses `FACT_*` and `SOURCE_*` evidence IDs from `main`. Its records use schema version `0.2.0`. The original v0.2 datasets are still available under `data/sft/`.

```yaml
output:
  root_dir: outputs/sft
  experiment_name: '{model}_ep{num_train_epochs}_lr{learning_rate}_seed{seed}'
  sample_preview_filename: sample_preview.json
  run_config_filename: run_config.json
  log_filename: train.log
  pid_filename: train.pid
```

Experiment-name templates support `{model}` and all fields in `training`. `{model}` uses the selected short name; `{num_train_epochs}`, `{learning_rate}`, and `{seed}` read their values from `training` and change with those settings. In experiment names, `learning_rate` uses compact scientific notation, such as `0.0001` → `1e-4` or `0.00025` → `2.5e-4`; the numeric training value is unchanged. When writing scientific notation as a YAML numeric value for PyYAML, use a form such as `1.0e-4`. Without `--output-dir`, training artifacts are saved under the YAML's `root_dir/experiment_name`, such as `outputs/sft/qwen3-4b_ep3_lr1e-4_seed42/`. Change the YAML template to `'{model}_baseline'` or use a fixed custom name to change this default. `--output-dir` directly overrides the complete output directory: relative paths are resolved from the project root, and absolute paths are used directly. No experiment name is appended to that override. There are no automatic hashes or rerun suffixes; the same path reuses the same directory. Artifact filename templates support only `{model}` and `{name}`, where `{name}` is the resolved experiment name. The sample preview and resolved configuration are saved during dry runs and training; set `sample_preview_filename: null` or `run_config_filename: null` to disable either file. `sample_preview.json` contains a summary and one processed prompt/completion sample from each of the training and validation splits. Actual training also saves the adapter, tokenizer, metrics, and checkpoints.

## Running

Run from the repository root, which contains both `sft/` and the shared `engine/` package. Use `--config` to select another shared YAML.

```bash
uv run python -m sft.trainer --model qwen3-4b --dry-run
uv run python -m sft.trainer --model qwen3-4b
uv run python -m sft.trainer --model phi4-mini --output-dir outputs/sft/phi4-mini_baseline
```

`--dry-run` prepares the data and prompt/completion examples and saves the configured sample preview without loading a tokenizer or model weights. Training loads the tokenizer and model with Hugging Face's default `from_pretrained` behavior: cached files are reused, and missing files are downloaded. The default-model command is `uv run python -m sft.trainer`.

Use `--background` to launch an independent worker that continues after SSH disconnects while the server remains running. The worker uses the `engine/` package in the same repository checkout. The configured `log_filename` and `pid_filename` are saved inside the actual output directory and support `{model}` and `{name}` templates. Each background launch appends combined stdout/stderr to the log, records its startup PID, and saves the PID file. Foreground runs do not automatically write this log. `--background --dry-run` can check preparation without loading a tokenizer or weights.

```bash
uv run python -m sft.trainer --model qwen3-4b --output-dir outputs/sft/qwen3_baseline --background
tail -n 100 -f outputs/sft/qwen3_baseline/train.log
```

Startup displays the worker PID, a command to follow its log, and a stop command containing the actual PID: `kill 12345` on POSIX or `Stop-Process -Id 12345` on Windows, with `12345` replaced by the worker's PID. A displayed PID confirms that the worker was spawned; runtime errors appear in the log. Pressing Ctrl+C stops `tail` only. After reconnecting, the saved PID can be used to stop the worker with `kill "$(cat outputs/sft/qwen3_baseline/train.pid)"`.

On Windows, follow the log with `Get-Content -LiteralPath 'outputs/sft/qwen3_baseline/train.log' -Tail 100 -Wait` in PowerShell.

## Plotting Training Loss

Plot a run's recorded loss after training:

```bash
uv run python -m sft.plot_training_loss --run-dir outputs/sft/qwen2.5-1.5b_ep3_lr1e-4_seed42
```

The standalone command saves `training_loss.png` inside the exact supplied experiment directory. Its title automatically combines the model name and experiment directory name.

## Inputs, Retrieval, and Labels

The prompt contains a system message and a user message. The public case contains `input`, `language`, and `region_id`; `input` selects only `user_text`, `growth_stage_id`, `production_system_id`, and `cultivar_id`. `annotations` are excluded from the prompt and labels. The `natural_response` field has been removed from the actual datasets. Data preparation builds examples without schema, expert-constraint, or split-isolation validation.

SFT imports `engine.KGRetriever` from the same repository checkout, which also supplies the registries and provenance facts. `build_examples(scenarios)` creates a retriever and calls `retrieve(public_case)` directly. This method returns the nine-field `RetrievedContext` passed into the SLM prompt.

The trainer uses one retriever instance for both training and validation data and prints its version at startup. The foreground, background, and preview summaries include `retrieval_version` and `retrieval_revision`. The trainer records these as `retrieval.version` and `retrieval.git_revision` in `run_config.json`, including dry runs. The revision is the Git `HEAD` of the checkout that supplied the retriever, or `null` if Git cannot resolve it.

`SYSTEM_PROMPT_VERSION` in this checkout's `engine/prompting.py` identifies the shared SFT and evaluation system prompt, currently `v0.3`. Update this constant when the prompt changes. Startup prints `System prompt version: v0.3`; foreground and background summaries include `system_prompt_version`. Dry runs and training save it in `sample_preview.json` as `summary.system_prompt_version` and in `run_config.json` as `system_prompt.version`. The version is run metadata and is not inserted into the model's prompt text or output JSON.

```python
from sft.data_preparation import build_examples
from engine import KGRetriever

examples = build_examples(scenarios, retriever=KGRetriever())
```

The retriever receives only the public case. The shared `TypedDict` types are defined in `engine/retriever.py`: `PublicInput` has `user_text`, `growth_stage_id`, `production_system_id`, and `cultivar_id`, each `str | None`; `PublicCase` has `input: PublicInput`, `language: str | None`, and `region_id: str | None`. Retrieval resolves questions and claim text from the registries, preserves observation states, and includes rule evidence only when its truth-state condition matches the case. Callers use the returned context directly without an intermediate raw-response conversion.

`RetrievedContext` defines the KG-to-SLM interface:

| Field | Type | Content |
| --- | --- | --- |
| `normalized_observations` | `list[Any]` | Observations mapped to canonical KG concepts |
| `candidate_causes` | `list[Any]` | Candidate diseases or other causes |
| `supporting_evidence` | `list[Any]` | Evidence supporting candidate causes |
| `contradicting_evidence` | `list[Any]` | Evidence contradicting candidate causes |
| `missing_observations` | `list[Any]` | Observations still needed to distinguish causes |
| `suggested_questions` | `list[Any]` | Suggested clarifying questions |
| `retrieved_facts` | `list[Any]` | Retrieved KG facts |
| `evidence_fact_ids` | `list[str]` | Identifiers of retrieved evidence facts |
| `evidence_source_ids` | `list[str]` | Identifiers of evidence sources |

The first seven fields retain flexible item formats for the KG implementation; the last two contain string IDs. Data preparation passes all nine fields into the prompt and copies them into `metadata.retrieved_context`. The complete user message for an empty context looks like this:

```text
User query:
{"input":{"user_text":"Rice leaves are yellow after heavy rain.","growth_stage_id":null,"production_system_id":null,"cultivar_id":null},"language":"en","region_id":"region:global"}

retrieved context:
{"normalized_observations":[],"candidate_causes":[],"supporting_evidence":[],"contradicting_evidence":[],"missing_observations":[],"suggested_questions":[],"retrieved_facts":[],"evidence_fact_ids":[],"evidence_source_ids":[]}
```

The nine retrieval fields are input context. The assistant label is only the compact `target_response` JSON with eight fields: `status`, `observations_needed`, `differential`, `actions`, `escalation_required`, `grounding`, `safety_flags`, and `user_response`. The system prompt requires these eight fields and defines `user_response` as a concise, user-facing explanation consistent with the structured fields. The original `target_response` is serialized with all field values preserved, including `grounding` and `user_response`, regardless of the retrieved context. Empty `evidence_fact_ids` does not filter or clear the training label's grounding IDs. The original scenario is preserved.

Training uses teacher forcing: `input_ids` contains the prompt followed by the reference assistant answer. Prompt positions have `labels=-100`; completion and chat-template ending tokens are supervised. Inference supplies only the prompt and asks the model to generate the answer.

## Files

| File | Purpose |
| --- | --- |
| `engine/retriever.py` | Shared `KGRetriever`, public-case and context types, and nine-field retrieval |
| `engine/prompting.py` | Shared public-field selection, system prompt and prompt construction |
| `data_preparation.py` | Scenario loading and prompt/completion preparation |
| `trainer.py` | Tokenization, label masking, and LoRA/QLoRA training |
| `plot_training_loss.py` | Standalone loss plot for one experiment directory |
| `../configs/sft/training_config.yaml` | Shared configuration for all six models |
