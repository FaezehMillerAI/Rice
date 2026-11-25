"""SFT entry point: one YAML configuration and a short model name."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
from typing import Any

from contracts.response import RESPONSE_CONTRACT_VERSION
from contracts.retrieval import RETRIEVAL_CONTRACT_VERSION
from .data_preparation import build_examples, load_scenarios
from engine.prompting import SYSTEM_PROMPT_VERSION
from engine.retriever import KGRetriever, WORKSPACE_ROOT

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = "configs/sft/training_config.yaml"


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_config(path: str | Path = DEFAULT_CONFIG_PATH, model_name: str | None = None) -> dict[str, Any]:
    """Read shared settings and select one model from the YAML registry."""
    import yaml

    with resolve_path(path).open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    name = model_name or config["model"]
    selected = config["models"][name]
    config["model_name"] = name
    config["model"] = {
        "base_model_name_or_path": selected["id"],
        "chat_template_kwargs": selected.get("chat_template_kwargs", {}),
        "trust_remote_code": False,
    }
    config["lora"]["target_modules"] = selected["target_modules"]
    return config


def resolve_output_paths(config: dict[str, Any]) -> dict[str, Path | None]:
    output = config["output"]
    values = {"model": config["model_name"], **config["training"]}
    mantissa, exponent = format(Decimal(str(values["learning_rate"])).normalize(), "e").split("e")
    values["learning_rate"] = f"{mantissa}e{int(exponent)}"
    name = output["experiment_name"].format(**values)
    directory = resolve_path(output["root_dir"]) / name

    def filename(key: str) -> Path | None:
        value = output[key]
        return directory / value.format(model=config["model_name"], name=name) if value else None

    return {
        "directory": directory,
        "preview": filename("sample_preview_filename"),
        "run_config": filename("run_config_filename"),
        "log": filename("log_filename"),
        "pid": filename("pid_filename"),
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_retrieval_revision() -> str | None:
    try:
        revision = subprocess.check_output(
            ["git", "-C", WORKSPACE_ROOT, "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return revision.strip() or None


def prepare_data(
    config: dict[str, Any], retriever: KGRetriever | None = None,
) -> dict[str, list[dict[str, Any]]]:
    kg_retriever = retriever if retriever is not None else KGRetriever()
    return {
        "train": build_examples(
            load_scenarios(resolve_path(config["dataset"]["train_data_path"])), retriever=kg_retriever,
        ),
        "validation": build_examples(
            load_scenarios(resolve_path(config["dataset"]["val_data_path"])), retriever=kg_retriever,
        ),
    }


def load_tokenizer(config: dict[str, Any]):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        config["model"]["base_model_name_or_path"], trust_remote_code=False,
    )
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token
    tokenizer.padding_side = "right"
    return tokenizer


def _chat_ids(tokenizer: Any, messages: list[dict[str, str]], *, generation: bool, chat_template_kwargs=None) -> list[int]:
    encoded = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=generation, return_dict=True,
        **(chat_template_kwargs or {}),
    )
    return list(encoded["input_ids"])


def tokenize_examples(examples, tokenizer, max_length, *, chat_template_kwargs=None):
    """Keep complete assistant targets; reject overflow instead of losing labels."""
    rows = []
    stats = {"examples": len(examples), "longest_sequence": 0, "longest_prompt": 0, "supervised_tokens": 0}
    for example in examples:
        prompt_ids = _chat_ids(tokenizer, example["prompt"], generation=True, chat_template_kwargs=chat_template_kwargs)
        input_ids = _chat_ids(
            tokenizer, example["prompt"] + example["completion"], generation=False,
            chat_template_kwargs=chat_template_kwargs,
        )
        scenario_id = example.get("scenario_id", "unknown scenario")
        if len(input_ids) > max_length:
            raise ValueError(
                f"{scenario_id}: sequence requires {len(input_ids)} tokens "
                f"(prompt={len(prompt_ids)}), exceeding max_seq_length={max_length}. "
                "Increase training.max_seq_length or reduce KG context; no tokens were truncated."
            )
        prompt_length = len(prompt_ids)
        if prompt_length >= len(input_ids):
            raise ValueError(f"{scenario_id}: no assistant tokens remain for supervision")
        labels = [-100] * prompt_length + input_ids[prompt_length:]
        rows.append({"input_ids": input_ids, "labels": labels})
        stats["longest_sequence"] = max(stats["longest_sequence"], len(input_ids))
        stats["longest_prompt"] = max(stats["longest_prompt"], prompt_length)
        stats["supervised_tokens"] += len(input_ids) - prompt_length
    return rows, stats


def build_sft_config(config, *, use_cuda: bool, use_mps: bool, bf16: bool):
    from trl import SFTConfig

    training = config["training"].copy()
    maximum = training.pop("max_seq_length")
    directory = resolve_output_paths(config)["directory"]
    return SFTConfig(
        output_dir=str(directory), run_name=directory.name, max_length=maximum,
        completion_only_loss=True, packing=False,
        eval_strategy="steps", save_strategy="steps", load_best_model_at_end=True,
        metric_for_best_model="eval_loss", greater_is_better=False,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit" if use_cuda else "adamw_torch",
        bf16=bf16, fp16=(use_cuda and not bf16) or use_mps, report_to="none",
        **training, **config["logging"],
    )


def load_trainable_model(config):
    import torch
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig, set_seed

    set_seed(config["training"]["seed"])
    use_cuda = torch.cuda.is_available()
    use_mps = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    bf16 = use_cuda and torch.cuda.is_bf16_supported()
    settings = build_sft_config(config, use_cuda=use_cuda, use_mps=use_mps, bf16=bf16)
    dtype = torch.bfloat16 if bf16 else (torch.float16 if use_cuda or use_mps else torch.float32)
    kwargs = {
        "dtype": dtype, "trust_remote_code": False,
        "attn_implementation": "sdpa",
    }
    quantization = config["quantization"]
    quantized = use_cuda and quantization["load_in_4bit"]
    if quantized:
        kwargs["quantization_config"] = BitsAndBytesConfig(
            **quantization, bnb_4bit_compute_dtype=dtype,
        )
    if use_cuda or use_mps:
        kwargs["device_map"] = "auto"
    model = AutoModelForCausalLM.from_pretrained(config["model"]["base_model_name_or_path"], **kwargs)
    model.config.use_cache = False
    if quantized:
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
        )
    model = get_peft_model(model, LoraConfig(task_type=TaskType.CAUSAL_LM, **config["lora"]))
    model.print_trainable_parameters()
    return model, settings


def launch_background(args, config, paths) -> dict[str, Any]:
    """Detach a worker with all output redirected to the experiment log."""
    command = [
        sys.executable, "-u", "-m", "sft.trainer",
        "--config", str(resolve_path(args.config)),
        "--model", config["model_name"],
        "--output-dir", str(paths["directory"]),
    ]
    if args.dry_run:
        command.append("--dry-run")
    kwargs = {
        "cwd": str(PROJECT_ROOT), "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT, "close_fds": True,
        "env": {**os.environ, "SFT_BACKGROUND": "1", "PYTHONIOENCODING": "utf-8"},
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    paths["log"].parent.mkdir(parents=True, exist_ok=True)
    with paths["log"].open("a", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, **kwargs)
        log.write(f"\nStarted SFT background worker: PID {process.pid}\n")
        log.flush()
    paths["pid"].parent.mkdir(parents=True, exist_ok=True)
    paths["pid"].write_text(f"{process.pid}\n", encoding="utf-8")
    summary = {
        "pid": process.pid, "output_dir": str(paths["directory"]),
        "log_file": str(paths["log"]), "pid_file": str(paths["pid"]),
        "retrieval_version": config["retrieval"]["version"],
        "retrieval_revision": config["retrieval"]["git_revision"],
        "retrieval_contract_version": RETRIEVAL_CONTRACT_VERSION,
        "response_contract_version": RESPONSE_CONTRACT_VERSION,
        "system_prompt_version": config["system_prompt"]["version"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if os.name == "nt":
        log_path = str(paths["log"]).replace("'", "''")
        print(f"View log: Get-Content -LiteralPath '{log_path}' -Tail 100 -Wait")
        print(f"Stop: Stop-Process -Id {process.pid}")
    else:
        print(f"View log: tail -n 100 -f {shlex.quote(str(paths['log']))}")
        print(f"Stop: kill {process.pid}")
    return summary


def run(args: argparse.Namespace) -> dict[str, Any]:
    if os.name != "nt" and os.environ.get("SFT_BACKGROUND") == "1":
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    config = load_config(args.config, args.model)
    retriever = KGRetriever()
    retrieval_revision = get_retrieval_revision()
    config["retrieval"] = {"version": retriever.version, "git_revision": retrieval_revision}
    config["system_prompt"] = {"version": SYSTEM_PROMPT_VERSION}
    config["contracts"] = {
        "retrieval": RETRIEVAL_CONTRACT_VERSION,
        "response": RESPONSE_CONTRACT_VERSION,
    }
    print(f"Retrieval version: {retriever.version}")
    print(f"Retrieval contract: {RETRIEVAL_CONTRACT_VERSION}")
    print(f"Response contract: {RESPONSE_CONTRACT_VERSION}")
    print(f"System prompt version: {SYSTEM_PROMPT_VERSION}")
    if args.output_dir:
        directory = resolve_path(args.output_dir)
        config["output"]["root_dir"] = str(directory.parent)
        config["output"]["experiment_name"] = directory.name
    paths = resolve_output_paths(config)
    config["output"]["experiment_name"] = paths["directory"].name
    if args.background:
        return launch_background(args, config, paths)
    examples = prepare_data(config, retriever=retriever)
    summary = {
        "model_name": config["model_name"],
        "model_id": config["model"]["base_model_name_or_path"],
        "retrieval_version": retriever.version,
        "retrieval_revision": retrieval_revision,
        "retrieval_contract_version": RETRIEVAL_CONTRACT_VERSION,
        "response_contract_version": RESPONSE_CONTRACT_VERSION,
        "system_prompt_version": SYSTEM_PROMPT_VERSION,
        "output_dir": str(paths["directory"]),
        "splits": {name: len(rows) for name, rows in examples.items()},
        "label": "assistant target_response JSON tokens; prompt labels are -100",
    }
    tokenized = {}
    tokenizer = None
    if not args.dry_run:
        tokenizer = load_tokenizer(config)
        summary["tokenization"] = {}
        for name, rows in examples.items():
            tokenized[name], summary["tokenization"][name] = tokenize_examples(
                rows, tokenizer, config["training"]["max_seq_length"],
                chat_template_kwargs=config["model"]["chat_template_kwargs"],
            )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if paths["preview"]:
        write_json(paths["preview"], {
            "summary": summary, "examples": {name: rows[0] for name, rows in examples.items()},
        })
        print(f"Sample preview: {paths['preview']}")
    if paths["run_config"]:
        write_json(paths["run_config"], config)
    if args.dry_run:
        return summary

    from datasets import Dataset
    from trl import SFTTrainer

    model, settings = load_trainable_model(config)
    trainer = SFTTrainer(
        model=model, args=settings,
        train_dataset=Dataset.from_list(tokenized["train"]),
        eval_dataset=Dataset.from_list(tokenized["validation"]), processing_class=tokenizer,
    )
    result = trainer.train()
    trainer.save_model(settings.output_dir)
    tokenizer.save_pretrained(settings.output_dir)
    trainer.save_state()
    trainer.log_metrics("train", result.metrics)
    trainer.save_metrics("train", result.metrics)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SFT using a short model name")
    parser.add_argument("--model", help="Model short name from the YAML: " + ", ".join(load_config()["models"]))
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Default config path: configs/sft/training_config.yaml")
    parser.add_argument("--output-dir", help="Override the full output directory; relative paths use the project root")
    parser.add_argument("--dry-run", action="store_true", help="Build data and prompts without training")
    parser.add_argument("--background", action="store_true", help="Run detached and print log, PID, tail and stop commands")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
