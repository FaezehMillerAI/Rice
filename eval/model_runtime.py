"""Model resolution and Transformers/Ollama generation backends."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from time import perf_counter
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request
import warnings

from eval.model_registry import BUILTIN_MODELS


ROOT = Path(__file__).resolve().parents[1]


def _project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def resolve_model_spec(
    model: str | None,
    adapter: str | None,
    config_path: Path | None = None,
    *,
    project_path_fn: Callable[[str | Path], Path] | None = None,
    fingerprint_fn: Callable[[list[Path]], str] | None = None,
) -> dict:
    """Resolve a base model and optional PEFT adapter without loading weights."""
    project_path_fn = project_path_fn or _project_path
    fingerprint_fn = fingerprint_fn or _fingerprint
    registry = deepcopy(BUILTIN_MODELS)
    if config_path is not None:
        import yaml

        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or not isinstance(config.get("models"), dict):
            raise ValueError("Model configuration must contain a models mapping")
        registry = config["models"]
    adapter_dir, adapter_config, saved_config = None, {}, {}
    saved_config_path = None
    if adapter:
        adapter_dir = project_path_fn(adapter)
        adapter_file = adapter_dir / "adapter_config.json"
        if not adapter_file.is_file():
            raise ValueError(f"Adapter directory must contain adapter_config.json: {adapter_dir}")
        adapter_config = json.loads(adapter_file.read_text(encoding="utf-8"))
        for directory in (adapter_dir, adapter_dir.parent):
            saved = directory / "run_config.json"
            if saved.is_file():
                saved_config = json.loads(saved.read_text(encoding="utf-8"))
                if not isinstance(saved_config, dict):
                    raise ValueError(f"Training run configuration must be a JSON object: {saved}")
                saved_config_path = saved
                break
    selected = model or adapter_config.get("base_model_name_or_path")
    if not selected:
        raise ValueError("--model is required for model modes, unless --adapter records its base model")
    entry = registry.get(selected)
    base = entry["id"] if entry else selected
    local_base = project_path_fn(base)
    if local_base.is_dir():
        base = str(local_base)
    if not entry:
        entry = next((item for item in registry.values() if item["id"] == base), {})
    if Path(base).is_dir() and (Path(base) / "adapter_config.json").is_file():
        raise ValueError("--model points to an adapter; supply that directory with --adapter instead")
    recorded_base = adapter_config.get("base_model_name_or_path")
    if recorded_base and model and recorded_base != base:
        if not (project_path_fn(recorded_base).is_dir() and str(project_path_fn(recorded_base)) == base):
            raise ValueError(f"Adapter expects base {recorded_base!r}, but --model resolves to {base!r}")
    saved_model = saved_config.get("model", {})
    kwargs = entry.get("chat_template_kwargs", {})
    if isinstance(saved_model, dict):
        kwargs = saved_model.get("chat_template_kwargs", kwargs)
    tokenizer_dir = None
    if adapter_dir:
        for directory in (adapter_dir, adapter_dir.parent):
            if (directory / "tokenizer_config.json").is_file():
                tokenizer_dir = str(directory)
                break
    return {
        "requested_model": model, "base_model": base,
        "variant": "tuned" if adapter_dir else "base",
        "adapter": str(adapter_dir) if adapter_dir else None,
        "adapter_config": adapter_config,
        "adapter_sha256": fingerprint_fn([adapter_dir / "adapter_config.json", *adapter_dir.glob("adapter_model.*")]) if adapter_dir else None,
        "tokenizer": tokenizer_dir or base,
        "chat_template_kwargs": kwargs,
        "training_max_seq_length": saved_config.get("training", {}).get("max_seq_length"),
        "training_config_path": str(saved_config_path) if saved_config_path else None,
        "training_config_sha256": fingerprint_fn([saved_config_path]) if saved_config_path else None,
    }


def _require_transformers_dependencies(*, adapter: bool, load_in_4bit: bool) -> None:
    """Fail before model downloads when selected inference dependencies are missing."""
    missing = [name for name in ("torch", "transformers") if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError(
            f"Missing local inference dependencies: {', '.join(missing)}. "
            "Install default NVIDIA CUDA support with 'uv sync --locked', or CPU/MPS support "
            "with 'uv sync --locked --no-default-groups --group hf'; pass the same "
            "dependency-selection flags to 'uv run'."
        )
    if adapter and importlib.util.find_spec("peft") is None:
        raise RuntimeError(
            "Adapter inference requires peft. Add '--extra adapter' to the selected HF "
            "installation and uv run command, for example 'uv sync --locked --extra adapter'."
        )
    if load_in_4bit:
        missing = [name for name in ("accelerate", "bitsandbytes") if importlib.util.find_spec(name) is None]
        if missing:
            raise RuntimeError(
                f"Missing 4-bit inference dependencies: {', '.join(missing)}. "
                "Use 'uv sync --locked --extra quantization' "
                "and the same dependency-selection flags with 'uv run'; 4-bit loading requires "
                "a supported NVIDIA CUDA device."
            )


class HFGenerator:
    """Merge an optional LoRA into a plain base model before either model mode."""

    def __init__(
        self,
        spec: dict,
        args: argparse.Namespace,
        *,
        dependency_checker: Callable[..., None] | None = None,
    ):
        if spec["adapter"] and args.load_in_4bit:
            raise ValueError("Tuned adapters are merged into the unquantized base model; omit --load-in-4bit")
        quantized = args.load_in_4bit
        dependency_checker = dependency_checker or _require_transformers_dependencies
        dependency_checker(adapter=bool(spec["adapter"]), load_in_4bit=quantized)
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed

        self.torch, self.spec, self.args = torch, spec, args
        set_seed(args.seed)
        device = args.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
        if quantized and device != "cuda":
            raise ValueError("--load-in-4bit requires CUDA")
        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA is unavailable")
        requested_dtype = args.dtype
        if requested_dtype == "bfloat16" and quantized:
            raise ValueError("--dtype bfloat16 cannot be combined with --load-in-4bit; omit --load-in-4bit to evaluate full BF16 weights")
        if requested_dtype == "bfloat16" and device == "cuda" and not torch.cuda.is_bf16_supported():
            raise ValueError("--dtype bfloat16 requires a CUDA device with BF16 support; no dtype fallback was performed")
        if requested_dtype == "auto":
            dtype = torch.float32 if device == "cpu" else (
                torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else torch.float16
            )
        else:
            dtype = getattr(torch, requested_dtype)
        common = {"trust_remote_code": False, "local_files_only": args.local_files_only}
        revision = spec["adapter_config"].get("revision")
        tokenizer_kwargs = {**common}
        if revision and spec["tokenizer"] == spec["base_model"]:
            tokenizer_kwargs["revision"] = revision
        self.tokenizer = AutoTokenizer.from_pretrained(spec["tokenizer"], **tokenizer_kwargs)
        self.tokenizer.pad_token = self.tokenizer.pad_token or self.tokenizer.eos_token
        # Merge in FP32, then cast once to the same inference dtype as a plain model.
        loading_dtype = torch.float32 if spec["adapter"] else dtype
        kwargs = {**common, "dtype": loading_dtype, "attn_implementation": "sdpa"}
        if revision:
            kwargs["revision"] = revision
        if quantized:
            quantization = {
                "load_in_4bit": True, "bnb_4bit_quant_type": "nf4", "bnb_4bit_use_double_quant": True,
            }
            kwargs["quantization_config"] = BitsAndBytesConfig(
                **quantization,
                bnb_4bit_compute_dtype=dtype,
            )
            kwargs["device_map"] = {"": 0}
        self.model = AutoModelForCausalLM.from_pretrained(spec["base_model"], **kwargs)
        merge_s = None
        if spec["adapter"]:
            from peft import PeftModel
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "error", message=r".*Found missing adapter keys while loading the checkpoint:",
                        category=UserWarning,
                    )
                    adapter_model = PeftModel.from_pretrained(self.model, spec["adapter"], is_trainable=False)
            except UserWarning as exc:
                if "Found missing adapter keys while loading the checkpoint:" not in str(exc):
                    raise
                raise RuntimeError(
                    f"Adapter loading failed for {spec['adapter']}: PEFT reported missing adapter keys; "
                    f"refusing to evaluate an incomplete or incompatible tuned model. {exc}"
                ) from exc
            merge_start = perf_counter()
            try:
                self.model = adapter_model.merge_and_unload(safe_merge=True)
            except Exception as exc:
                raise RuntimeError(f"LoRA merge failed for {spec['adapter']}: {exc}") from exc
            merge_s = perf_counter() - merge_start
            if isinstance(self.model, PeftModel) or any("lora_" in name for name, _ in self.model.named_parameters()):
                raise RuntimeError("LoRA merge did not return a plain model with all adapter layers removed")
            del adapter_model
            self.model.to(device=device, dtype=dtype)
        elif not quantized:
            self.model.to(device)
        self.model.eval()
        self.runtime_metadata = {
            "profile": "merged_lora" if spec["adapter"] else "explicit_inference",
            "adapter_merged": bool(spec["adapter"]),
            "merge_method": "merge_and_unload" if spec["adapter"] else None,
            "merge_safe": bool(spec["adapter"]),
            "merge_dtype": str(loading_dtype) if spec["adapter"] else None,
            "merge_s": merge_s,
            "load_in_4bit": quantized,
            "quantization": deepcopy(quantization) if quantized else None,
            "compute_dtype": str(dtype),
            "autocast_dtype": None,
            "model_class": type(self.model).__name__,
        }
        self.device = self.model.get_input_embeddings().weight.device
        limits = [args.max_input_tokens + args.max_new_tokens]
        configs = [self.model.config, getattr(self.model.config, "text_config", None)]
        for config in configs:
            limit = getattr(config, "max_position_embeddings", None)
            if isinstance(limit, int) and 0 < limit < 10**9:
                limits.append(limit)
        token_limit = self.tokenizer.model_max_length
        if isinstance(token_limit, int) and 0 < token_limit < 10**9:
            limits.append(token_limit)
        self.context_limit = min(limits)

    def generate(self, messages: list[dict], *, max_new_tokens: int | None = None) -> dict:
        torch = self.torch
        output_budget = max_new_tokens if max_new_tokens is not None else self.args.max_new_tokens
        cuda = self.device.type == "cuda"
        if cuda:
            torch.cuda.reset_peak_memory_stats(self.device)
            torch.cuda.synchronize(self.device)
        encoded = self.tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_dict=True,
            return_tensors="pt", **self.spec["chat_template_kwargs"],
        )
        prompt_tokens = encoded["input_ids"].shape[-1]
        if prompt_tokens > self.args.max_input_tokens or prompt_tokens + output_budget > self.context_limit:
            raise ValueError(f"Prompt ({prompt_tokens} tokens) plus output budget ({output_budget}) exceeds input/context limit; no truncation performed")
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with torch.inference_mode():
            output = self.model.generate(
                **encoded, max_new_tokens=output_budget, do_sample=False,
                use_cache=True, pad_token_id=self.tokenizer.pad_token_id,
            )
        if cuda:
            torch.cuda.synchronize(self.device)
        completion = output[0, prompt_tokens:]
        eos_ids = self.model.generation_config.eos_token_id
        eos_ids = [eos_ids] if isinstance(eos_ids, int) else (eos_ids or [])
        return {
            "raw_output": self.tokenizer.decode(completion, skip_special_tokens=True),
            "prompt_tokens": prompt_tokens, "generated_tokens": len(completion),
            "output_budget_exhausted": len(completion) == output_budget and int(completion[-1]) not in eos_ids,
            "cuda_peak_allocated_mib": torch.cuda.max_memory_allocated(self.device) / 1024**2 if cuda else None,
        }


def resolve_ollama_spec(args: argparse.Namespace) -> dict:
    """Ollama names identify server models, not HF repositories or PEFT paths."""
    if not args.model:
        raise ValueError("Ollama requires --model with an installed tag, for example qwen2.5-1.5b")
    if args.adapter:
        raise ValueError("Ollama cannot load --adapter here; import the tuned model separately and use its Ollama --model tag, or use --backend transformers")
    if args.load_in_4bit or args.device != "auto" or args.dtype != "auto":
        raise ValueError("--load-in-4bit, --device and --dtype are Transformers options; Ollama manages its own quantization, device and dtype")
    url = urllib.parse.urlsplit(args.ollama_url)
    if url.scheme not in {"http", "https"} or not url.netloc or url.query or url.fragment:
        raise ValueError("--ollama-url must be an HTTP(S) server base URL")
    if args.ollama_timeout <= 0:
        raise ValueError("--ollama-timeout must be positive")
    return {
        "backend": "ollama", "requested_model": args.model, "ollama_model": args.model,
        "variant": "server-managed", "adapter": None,
        "server_url": args.ollama_url.rstrip("/"),
    }


def ollama_json(base_url: str, route: str, *, payload: dict | None = None, timeout: float = 120) -> dict:
    """Use the repository's urllib/API pattern while retaining explicit errors."""
    request = urllib.request.Request(
        base_url + route,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama {route}: HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Ollama {route} request failed: {exc}") from exc
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError(f"Ollama {route} returned an invalid API JSON response: {exc}") from exc
    if not isinstance(result, dict) or result.get("error"):
        raise RuntimeError(f"Ollama {route} returned an API error: {result}")
    return result


class OllamaGenerator:
    """Generate via Ollama's /api/generate endpoint without output repair."""

    def __init__(
        self,
        spec: dict,
        args: argparse.Namespace,
        *,
        request_json: Callable[..., dict] | None = None,
    ):
        self.spec, self.args = spec, args
        self._request_json = request_json or ollama_json
        self.device = "ollama-server"
        version = self.request("/api/version")
        tags = self.request("/api/tags").get("models", [])
        requested = spec["ollama_model"]
        names = {requested, requested + ":latest"}
        entry = next((item for item in tags if item.get("name", item.get("model")) in names), None)
        if not entry:
            installed = [item.get("name", item.get("model")) for item in tags]
            raise ValueError(f"Ollama model {requested!r} is not installed. Available tags: {installed}. No model was pulled or created.")
        spec["ollama_model"] = entry.get("name", entry.get("model"))
        spec["digest"] = entry.get("digest")
        self.show = self.request("/api/show", {"model": spec["ollama_model"]})
        limits = [args.max_input_tokens + args.max_new_tokens]
        for key, value in self.show.get("model_info", {}).items():
            if key.endswith(".context_length") and type(value) is int and value > 0:
                limits.append(value)
        self.context_limit = min(limits)
        self.runtime_metadata = {
            "server_version": version.get("version"), "tag": spec["ollama_model"],
            "digest": spec["digest"], "details": self.show.get("details"),
            "capabilities": self.show.get("capabilities", []),
            "model_parameters": self.show.get("parameters"),
            "template_sha256": hashlib.sha256(self.show.get("template", "").encode()).hexdigest(),
            "format": args.ollama_format, "temperature": 0.1, "top_p": 0.9,
            "seed": args.seed, "num_ctx": self.context_limit,
            "thinking": False if "thinking" in self.show.get("capabilities", []) else "model-default",
            "input_length_check": "server-returned counts; no local tokenizer precheck",
            "truncation_control": "truncate=false and shift=false requested; support depends on server version",
        }

    def request(self, route: str, payload: dict | None = None) -> dict:
        return self._request_json(
            self.spec["server_url"], route,
            payload=payload, timeout=self.args.ollama_timeout,
        )

    def generate(self, messages: list[dict], *, max_new_tokens: int | None = None) -> dict:
        if len(messages) != 2 or [message.get("role") for message in messages] != ["system", "user"]:
            raise ValueError("Ollama evaluation expects exactly one system message and one user message")
        budget = max_new_tokens if max_new_tokens is not None else self.args.max_new_tokens
        payload = {
            "model": self.spec["ollama_model"], "system": messages[0]["content"],
            "prompt": messages[1]["content"], "stream": False,
            "truncate": False, "shift": False,
            "options": {
                "temperature": 0.1, "top_p": 0.9, "seed": self.args.seed,
                "num_ctx": self.context_limit, "num_predict": budget,
            },
        }
        if self.args.ollama_format == "json":
            payload["format"] = "json"
        if "thinking" in self.show.get("capabilities", []):
            payload["think"] = False
        data = self.request("/api/generate", payload)
        text = data.get("response")
        if not isinstance(text, str) or data.get("done") is False:
            raise RuntimeError(f"Ollama returned a missing text or incomplete response: {data}")
        prompt_tokens, generated_tokens = data.get("prompt_eval_count"), data.get("eval_count")
        prompt_tokens = prompt_tokens if type(prompt_tokens) is int else None
        generated_tokens = generated_tokens if type(generated_tokens) is int else None
        errors = []
        if prompt_tokens is not None and (prompt_tokens > self.args.max_input_tokens or prompt_tokens + budget > self.context_limit):
            errors.append(f"Server-reported prompt length {prompt_tokens} exceeds the input/context budget; original output retained")
        return {
            "raw_output": text, "raw_ollama_response": data, "ollama_request": payload,
            "prompt_tokens": prompt_tokens, "generated_tokens": generated_tokens,
            "backend_errors": errors,
            "output_budget_exhausted": data.get("done_reason") == "length" or (not data.get("done_reason") and generated_tokens is not None and generated_tokens >= budget),
            "cuda_peak_allocated_mib": None,
        }
