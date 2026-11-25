"""Evaluate KG-only, model-only and KG+model against test annotations.

Examples (run from the repository root)::

    uv run python -m eval.evaluate_unified --modes kg-only
    uv run python -m eval.evaluate_unified --model qwen2.5-1.5b
    uv run python -m eval.evaluate_unified --backend transformers --model Qwen/Qwen2.5-1.5B-Instruct --dtype bfloat16
    uv run python -m eval.evaluate_unified --backend ollama --model qwen2.5-1.5b
    uv run python -m eval.evaluate_unified --backend transformers --model qwen2.5-1.5b --adapter path/to/adapter

No annotations or target responses are passed to a predictor. Raw outputs are
retained for strict schema scoring. Complete outer Markdown JSON fences may be
removed for prediction parsing; no JSON content repair or KG fallback is used.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from typing import Any
import urllib.error
import urllib.parse
import urllib.request
import warnings


ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "engine/__init__.py").is_file():
    raise RuntimeError(f"The repository root at {ROOT} has no KG engine.")
# Resolve this repository's eval and engine packages first, including when
# executed as a script.
sys.path.insert(0, str(ROOT))

from engine.retriever import KGRetriever, to_compact_target_response
from engine.prompting import SYSTEM_PROMPT_VERSION, build_prompt, select_public_case
from contracts.response import (
    LIST_FIELDS,
    RESPONSE_CONTRACT_VERSION,
    RESPONSE_FIELDS,
    STATUS_TO_BEHAVIOR,
    parse_response,
    prepare_prediction_input,
    validate_response,
)
from contracts.retrieval import KGCatalogSnapshot, RETRIEVAL_CONTRACT_VERSION
from eval.resource_monitor import ResourceMonitor
from eval.ollama_resource_monitor import OllamaMemoryMonitor
from eval.rule_evaluator import evaluate_rule_quality, question_agreement_exemption
from eval.response_consistency import (
    RESPONSE_CONSISTENCY_VERSION, evaluate_response_consistency,
)
from eval.response_safety import RESPONSE_SAFETY_VERSION, evaluate_response_safety
from eval.model_registry import BUILTIN_MODELS
from eval.scoring import (
    BEHAVIORS,
    METRIC_LABELS,
    SCORE_CATEGORIES,
    SCORE_METRICS,
    SCORE_TABLE_COLUMNS,
    assessment_state,
    compute_weighted_score,
    evaluate_differential_ranking,
    evaluate_prediction,
    evaluate_resources,
    finalize_score,
    group_category_scores,
    load_resource_budgets,
    load_score_weights,
    metric_exemptions,
    set_scores,
    validate_resource_budgets,
    validate_score_weights,
)
from eval.reporting import (
    count_assessments,
    finalize_user_output,
    format_score,
    print_behavior_performance,
    print_case_score,
    print_case_steps,
    print_final_user_output,
    print_summary,
    print_table,
    score_table_columns,
    score_table_rows,
    summarize,
    write_csv_reports,
)
from eval.benchmark import (
    load_cases as _load_cases,
    resolve_benchmark_dataset,
    scoring_annotations,
    validate_benchmark_metadata,
)
from eval.kg_adapter import KGAdapter, dataset_audit
from eval.model_runtime import (
    HFGenerator as _RuntimeHFGenerator,
    OllamaGenerator as _RuntimeOllamaGenerator,
    _require_transformers_dependencies,
    ollama_json,
    resolve_model_spec as _resolve_model_spec,
    resolve_ollama_spec,
)

EVALUATOR_VERSION = "v0.3.0"
MODES = ("kg-only", "model-only", "kg+model")


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def load_cases(path: Path) -> list[dict]:
    """Compatibility wrapper that preserves facade-level selector patching."""
    return _load_cases(path, select_public_case_fn=select_public_case)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def git_revision(root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False,
        ).stdout.strip() or None
    except OSError:
        return None


def measure_ollama_memory(generator, args: argparse.Namespace, *, timeout_s: float = 10.0) -> dict:
    """One resident-model probe, sampled during prediction by OllamaMemoryMonitor.

    API contract: https://docs.ollama.com/api/ps
    """
    try:
        payload = ollama_json(args.ollama_url, "/api/ps", timeout=min(args.ollama_timeout, timeout_s))
        name = generator.spec["ollama_model"]
        aliases = {name, name + ":latest"} if ":" not in name else {name}
        model = next((item for item in payload.get("models", []) if item.get("name") in aliases or item.get("model") in aliases), None)
        if model is None:
            raise ValueError("Predictor model is absent from /api/ps")
        size = model.get("size")
        if type(size) not in (int, float) or not math.isfinite(size) or size <= 0:
            raise ValueError("/api/ps did not provide a positive resident model size")
        vram = model.get("size_vram")
        return {
            "predictor_memory_mib": size / 1024**2,
            "ollama_model_resident_mib": size / 1024**2,
            "ollama_model_vram_mib": vram / 1024**2 if type(vram) in (int, float) and math.isfinite(vram) and vram >= 0 else None,
            "predictor_memory_scope": "ollama_server_reported_model_resident_snapshot",
            "predictor_memory_error": None,
        }
    except Exception as exc:
        return {
            "predictor_memory_mib": None, "ollama_model_resident_mib": None,
            "ollama_model_vram_mib": None,
            "predictor_memory_scope": "ollama_server_reported_model_resident_snapshot",
            "predictor_memory_error": f"{type(exc).__name__}: {exc}",
        }






def resolve_model_spec(model: str | None, adapter: str | None, config_path: Path | None = None) -> dict:
    """Resolve model metadata while preserving facade-level path/fingerprint seams."""
    return _resolve_model_spec(
        model, adapter, config_path,
        project_path_fn=project_path,
        fingerprint_fn=fingerprint,
    )


class HFGenerator(_RuntimeHFGenerator):
    """Compatibility wrapper that resolves the facade dependency checker at runtime."""

    def __init__(self, spec: dict, args: argparse.Namespace):
        super().__init__(
            spec, args,
            dependency_checker=_require_transformers_dependencies,
        )


class OllamaGenerator(_RuntimeOllamaGenerator):
    """Compatibility wrapper that resolves the facade HTTP helper at runtime."""

    def __init__(self, spec: dict, args: argparse.Namespace):
        super().__init__(spec, args, request_json=ollama_json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--dataset", help="Override benchmark.benchmark_file in --score-config; relative paths resolve from the repository root")
    parser.add_argument("--backend", choices=("transformers", "ollama"), default="transformers", help="Model runtime (default: transformers)")
    parser.add_argument("--model", help="HF short name/ID/local base directory, or an installed Ollama model tag")
    parser.add_argument("--adapter", help="Explicit local PEFT adapter directory; base may be inferred from adapter_config.json")
    parser.add_argument("--config", help="Optional YAML model registry override; built-in aliases are used by default")
    parser.add_argument("--score-config", default="configs/eval/eval_config.yaml", help="YAML with score weights and resource_budgets")
    parser.add_argument("--latency-budget-s", type=float, help="Override the latency scoring limit from score config")
    parser.add_argument("--memory-budget-mib", type=float, help="Override the predictor memory scoring limit from score config")
    parser.add_argument("--output-dir", help="New report directory; defaults to outputs/eval/unified/TIMESTAMP")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "mps"), default="auto")
    parser.add_argument("--dtype", choices=("auto", "bfloat16", "float16", "float32"), default="auto", help="Transformers weight dtype; auto uses float32 on CPU, BF16 on supported CUDA devices and float16 otherwise")
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--local-files-only", action="store_true", help="Use cached/local model files only")
    parser.add_argument("--warmup", action=argparse.BooleanOptionalAction, default=True, help="Run a short synthetic model warm-up before timed cases")
    parser.add_argument("--max-input-tokens", type=int, default=4096)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--top-k-candidates", type=int, default=3)
    parser.add_argument("--top-k-questions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-timeout", type=float, default=120)
    parser.add_argument("--ollama-format", choices=("json", "none"), default="none", help="Output format constraint; disabled by default, use json to enable JSON steering")
    parser.add_argument("--limit", type=int, help="Evaluate only the first N cases (recorded in reports)")
    parser.add_argument("--show-steps", action="store_true", help="Print public input, KG context, inference request, raw/parsed output and errors for each case")
    return parser


def prepare_generator(spec: dict, args: argparse.Namespace, metadata: dict, directory: Path):
    """Defer predictor loading until KG-only cases have completed."""
    load_start = perf_counter()
    try:
        generator_type = OllamaGenerator if args.backend == "ollama" else HFGenerator
        generator = generator_type(spec, args)
    except Exception as exc:
        write_json(directory / "load_error.json", {"error_type": type(exc).__name__, "error": str(exc)})
        raise
    metadata["model_load_s"] = perf_counter() - load_start
    metadata["effective_device"] = str(generator.device)
    model_dtype = getattr(generator.model, "dtype", None) if args.backend == "transformers" else None
    metadata["effective_dtype"] = str(model_dtype) if model_dtype is not None else None
    metadata["model_numerics"] = getattr(generator, "runtime_metadata", None) if args.backend == "transformers" else None
    if isinstance(metadata["model_numerics"], dict):
        numerics = metadata["model_numerics"]
        print(f"Numerics={numerics['profile']} | dtype={numerics['compute_dtype']} | adapter merged={numerics['adapter_merged']} | load_in_4bit={numerics['load_in_4bit']}", flush=True)
    metadata["context_token_limit"] = generator.context_limit
    metadata["model_commit"] = getattr(generator.model.config, "_commit_hash", None) if args.backend == "transformers" else None
    metadata["ollama"] = generator.runtime_metadata if args.backend == "ollama" else None
    write_json(directory / "run_config.json", metadata)
    if args.warmup:
        public = {
            "input": {"user_text": "Rice leaves are yellow. What should I check?", "growth_stage_id": None, "production_system_id": None, "cultivar_id": None},
            "language": "en", "region_id": None,
        }
        warmup_start = perf_counter()
        try:
            generator.generate(build_prompt(public), max_new_tokens=min(16, args.max_new_tokens))
        except Exception as exc:
            write_json(directory / "load_error.json", {"phase": "warmup", "error_type": type(exc).__name__, "error": str(exc)})
            raise
        metadata["warmup_s"] = perf_counter() - warmup_start
        print(f"Model warm-up complete ({metadata['warmup_s']:.3f}s; excluded from case latency)", flush=True)
        write_json(directory / "run_config.json", metadata)
    return generator


def evaluate_case_rules(row: dict, kg: KGAdapter, causes: dict, action_catalog: dict) -> dict:
    prediction, gold, valid = row["prediction"], row["gold"], row["prediction_valid"]
    language = (row["public_input"] or {}).get("language")
    context = row["retrieved_context"]
    claims = kg.catalog["claims"]
    if context:
        # Focused facts can come from sources outside the provenance CSV.
        claims = {**{fact["claim_id"]: fact for fact in context["retrieved_facts"]}, **claims}
    for trace, result in (
        ("rule_evaluation", evaluate_rule_quality(
            prediction, gold, valid=valid, claims=claims, questions=kg.catalog["questions"],
        )),
        ("response_consistency", evaluate_response_consistency(
            prediction, valid=valid, causes=causes, questions=kg.catalog["questions"],
            action_catalog=action_catalog, language=language,
        )),
        ("response_safety", evaluate_response_safety(
            prediction.get("user_response") if isinstance(prediction, dict) else None,
            valid=valid, escalation_required=gold["escalation_required"], language=language,
        )),
    ):
        row[trace] = result.pop(trace)
        row["metrics"].update(result)

    unavailable = {}
    if row["metrics"]["groundedness"] is None:
        unavailable["groundedness"] = row["rule_evaluation"]["checks"]["differential_grounding"]["unassessed_reason"]
    for metric, trace in (
        ("structured_output_vs_user_response_consistency", "response_consistency"),
        ("response_safety_check", "response_safety"),
    ):
        if row["metrics"][metric] is None:
            unavailable[metric] = row[trace].get("unassessed_reason") or f"{trace}_unassessed"
    return unavailable


def run(args: argparse.Namespace) -> Path:
    for key in ("max_input_tokens", "max_new_tokens", "top_k_candidates", "top_k_questions"):
        if getattr(args, key) <= 0:
            raise ValueError(f"--{key.replace('_', '-')} must be positive")
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    modes = [mode for mode in MODES if mode in args.modes]
    needs_model = any(mode != "kg-only" for mode in modes)
    kg_enabled_by_mode = {mode: mode != "model-only" for mode in modes}
    if not needs_model and (args.model or args.adapter):
        raise ValueError("--model/--adapter were provided, but no model mode was selected")
    score_config_path = project_path(args.score_config)
    # Freeze both weights and budgets from one read, even if the user edits YAML mid-run.
    import yaml
    score_config_bytes = score_config_path.read_bytes()
    try:
        score_config = yaml.safe_load(score_config_bytes.decode("utf-8-sig"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid score configuration: {exc}") from exc
    if not isinstance(score_config, dict):
        raise ValueError("Score configuration must be a mapping")
    score_weights = validate_score_weights(score_config.get("unified_weights"))
    resource_budgets = validate_resource_budgets(score_config.get("resource_budgets", {}))
    for argument, key in (("latency_budget_s", "latency_s"), ("memory_budget_mib", "memory_mib")):
        value = getattr(args, argument)
        if value is not None:
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"--{argument.replace('_', '-')} must be finite and positive")
            resource_budgets[key] = value
    benchmark = score_config.get("benchmark")
    dataset_path = resolve_benchmark_dataset(args.dataset, benchmark)
    cases = load_cases(dataset_path)
    loaded_case_count = len(cases)
    if args.dataset is None:
        validate_benchmark_metadata(benchmark, cases)
    if args.limit:
        cases = cases[:args.limit]
    kg = KGAdapter()
    consistency_action_catalog = deepcopy(kg.catalog["action_catalog"])
    consistency_causes = deepcopy(kg.catalog["causes"])
    spec = None
    if needs_model:
        spec = resolve_ollama_spec(args) if args.backend == "ollama" else resolve_model_spec(
            args.model, args.adapter, project_path(args.config) if args.config else None,
        )
    directory = project_path(args.output_dir) if args.output_dir else ROOT / "outputs/eval/unified" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(f"Report directory is not empty: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    metadata = {
        "evaluator_version": EVALUATOR_VERSION, "system_prompt_version": SYSTEM_PROMPT_VERSION,
        "response_contract_version": RESPONSE_CONTRACT_VERSION,
        "retrieval_contract_version": (
            RETRIEVAL_CONTRACT_VERSION
            if any(kg_enabled_by_mode.values())
            else None
        ),
        "response_consistency_version": RESPONSE_CONSISTENCY_VERSION,
        "response_safety_version": RESPONSE_SAFETY_VERSION,
        "retrieval_version": kg.retrieval_version if any(kg_enabled_by_mode.values()) else None,
        "kg_enabled_by_mode": kg_enabled_by_mode,
        "git_revision": git_revision(ROOT), "kg_git_revision": git_revision(ROOT),
        "evaluator_sha256": fingerprint([
            Path(__file__), ROOT / "eval/scoring.py", ROOT / "eval/reporting.py",
            ROOT / "eval/benchmark.py", ROOT / "eval/kg_adapter.py",
            ROOT / "eval/model_runtime.py",
            ROOT / "eval/resource_monitor.py",
            ROOT / "eval/ollama_resource_monitor.py", ROOT / "eval/rule_evaluator.py",
            ROOT / "eval/model_registry.py", ROOT / "eval/response_consistency.py", ROOT / "eval/response_safety.py",
            ROOT / "engine/prompting.py", ROOT / "contracts/response.py",
            ROOT / "contracts/retrieval.py",
        ]),
        "retriever_sha256": fingerprint([ROOT / "engine/retriever.py", ROOT / "engine/diagnostic_engine.py"]),
        "registry_sha256": fingerprint(list((ROOT / "registry").glob("*.csv"))),
        "dataset": str(dataset_path), "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "benchmark": {
            "selection": "command_line" if args.dataset is not None else "config",
            "configured": deepcopy(benchmark), "loaded_cases": loaded_case_count, "evaluated_cases": len(cases),
        },
        "scenario_ids": [case["scenario_id"] for case in cases],
        "family_ids": [case.get("family_id") or case["scenario_id"] for case in cases],
        "modes": modes, "backend": args.backend if needs_model else None, "model": spec, "arguments": vars(args),
        "dataset_audit": dataset_audit(cases, kg),
        "dataset_schema_versions": sorted({case.get("schema_version", "unspecified") for case in cases}),
        "evaluation_method": "deterministic_gold_rules", "metric_labels": dict(METRIC_LABELS),
        "user_outputs_file": "user_outputs.jsonl",
        "scoring": {
            "config": str(score_config_path), "config_sha256": hashlib.sha256(score_config_bytes).hexdigest(),
            "weights": score_weights, "scale": [0, 100],
            "categories": {
                category: [metric for metric in names if metric in score_weights]
                for category, names in SCORE_CATEGORIES.items() if any(metric in score_weights for metric in names)
            },
            "resource_budgets": resource_budgets,
            "resource_formula": "mean(max(0,1-latency_s/latency_limit_s), max(0,1-memory_mib/memory_limit_mib))",
            "resource_window": "public_input_ready_to_raw_output; JSON parsing and evaluation excluded",
            "resource_memory": "absolute sampled occupancy including loaded model state; measurement scopes are reported per case",
            "formula": "100 * sum(configured weight * zero_fill(metric)) / sum(configured weights)",
            "null_metric_policy": "applicable_null_is_fail_and_scores_zero_with_weight_retained",
            "question_agreement_formula": "N/A if gold behavior is ANSWER and required_questions is empty; otherwise 1 if both sets are empty, or 2 * matched_unique_question_ids / (predicted_unique_question_ids + reference_unique_question_ids)",
            "differential_top1_precision_formula": "I(differential[0] == acceptable_differential[0]); zero if prediction is empty; null if gold is empty",
            "differential_top3_recall_formula": "count(unique differential[:3] intersect unique acceptable_differential) / count(unique acceptable_differential)",
            "differential_f1_formula": "2 * count(set(differential) intersect set(acceptable_differential)) / (count(set(differential)) + count(set(acceptable_differential))); null if gold is empty",
            "differential_cutoffs": {"precision": 1, "recall": 3, "slice_before_deduplication": True},
            "differential_f1_scope": "full_prediction_and_gold_sets; independent of Top-1 Precision and Top-3 Recall",
            "confounder_recall_formula": "count(set(differential[1:]) intersect set(required_confounders)) / count(set(required_confounders)); null if gold is empty",
            "groundedness_formula": "supported_unique_differential_claims / unique_differential_claims",
            "evidence_agreement_formula": "1 if both sets are empty; otherwise 2 * matched_unique_fact_ids / (predicted_unique_fact_ids + reference_unique_fact_ids)",
            "actions_agreement_formula": "2 * matched_unique_action_strings / (predicted_unique_action_strings + reference_unique_action_strings)",
            "safety_flags_agreement_formula": "2 * matched_unique_safety_flags / (predicted_unique_safety_flags + reference_unique_safety_flags)",
            "structured_output_vs_user_response_consistency_formula": "mean of applicable field-dimension scores; no gold input; see per-case response_consistency checks",
            "response_safety_check_formula": "1 if all applicable baseline safety rules pass; otherwise Fail, with zero contribution and any raw null retained",
            "groundedness_matching": "prediction.grounding -> provenance registry or case-retrieved facts -> exact subject_uri equality with prediction.differential; independent of gold supporting_fact_ids, predicate_uri and object_uri",
            "unsupported_claim_rate_formula": "1 - raw groundedness; null when unassessed or invalid; diagnostic only, no score weight",
            "aggregation": "arithmetic mean of per-case scores, including failures and N/A scores counted as zero",
            "schema_input": "unchanged_raw_output",
            "prediction_normalization": "strip_complete_outer_markdown_json_fence_only",
            "invalid_output_policy": "invalid normalized prediction or inference/backend error receives zero; outer fence violations affect schema compliance only",
            "not_applicable_policy": "retain the N/A status and null raw value; use zero in case scores and metric means without redistributing weight",
            "metric_pass_rate": "passed_n / applicable_n; passed means full credit, applicable includes numeric zero and unassessed results",
        },
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata.update({key: None for key in ("model_load_s", "effective_device", "effective_dtype", "context_token_limit", "model_commit", "ollama", "warmup_s")})
    write_json(directory / "run_config.json", metadata)
    print(f"Evaluation {EVALUATOR_VERSION} | modes={', '.join(modes)} | cases={len(cases)}", flush=True)
    print(f"Dataset={dataset_path} | source={metadata['benchmark']['selection']} | selected={len(cases)}/{loaded_case_count}", flush=True)
    if spec:
        name = spec.get("base_model", spec.get("ollama_model"))
        print(f"Backend={args.backend} | model={name} | variant={spec['variant']} | adapter={spec['adapter']}", flush=True)
    print(f"Prompt={SYSTEM_PROMPT_VERSION} | retrieval={metadata['retrieval_version'] or 'disabled'}", flush=True)
    if "model-only" in modes:
        print("model-only: KG retrieval disabled; public input only", flush=True)
    total_weight = math.fsum(score_weights.values())
    print("Score weights: " + ", ".join(f"{name}={weight / total_weight:.2%}" for name, weight in score_weights.items()), flush=True)
    print(f"Evaluator=deterministic_gold_rules | weighted metrics={len(score_weights)} | consistency={RESPONSE_CONSISTENCY_VERSION} | response safety={RESPONSE_SAFETY_VERSION} | resource scoring limits={resource_budgets}", flush=True)
    generator = None
    records = []
    with (
        (directory / "predictions.jsonl").open("w", encoding="utf-8") as output,
        (directory / "user_outputs.jsonl").open("w", encoding="utf-8") as user_outputs,
    ):
        for mode in modes:
            print(f"\n{'=' * 72}\nMethod: {mode}\n{'=' * 72}\n", flush=True)
            if mode != "kg-only" and generator is None:
                generator = prepare_generator(spec, args, metadata, directory)
            for case in cases:
                # Family IDs group related cases; scenario IDs still identify each row.
                family_id = case.get("family_id") or case["scenario_id"]
                gold = scoring_annotations(case)
                row = {
                    "scenario_id": case["scenario_id"], "family_id": family_id,
                    "mode": mode, "public_input": None,
                    "gold": gold, "gold_safety_flags_source": "target_response.safety_flags",
                    "gold_actions_source": "target_response.actions",
                    "prediction": None, "raw_output": None, "prediction_input": None,
                    "output_normalization": {"method": "strip_outer_markdown_json_fence", "applied": False},
                    "prediction_valid": False, "prediction_errors": [],
                    "retrieved_context": None, "raw_retrieval": None, "raw_kg_response": None,
                    "messages": None, "error": None,
                }
                monitor = ResourceMonitor().start()
                server_monitor = OllamaMemoryMonitor(
                    lambda: measure_ollama_memory(generator, args, timeout_s=1.0)
                ) if mode != "kg-only" and args.backend == "ollama" else None
                start = perf_counter()
                parse_errors = []
                facts = None
                try:
                    if server_monitor is not None:
                        server_monitor.start()
                    public = select_public_case(case)
                    row["public_input"] = public
                    if mode == "kg-only":
                        row["prediction"], row["raw_kg_response"] = kg.diagnose(
                            deepcopy(public), args.top_k_candidates, args.top_k_questions,
                            family_id=family_id,
                        )
                        row["raw_output"] = json.dumps(row["prediction"], ensure_ascii=False)
                    else:
                        if mode == "kg+model":
                            retrieval_start = perf_counter()
                            facts = []  # A failed retrieval is still an applicable KG-mode failure.
                            context = kg.retrieve(public, args.top_k_candidates, args.top_k_questions)
                            row["retrieved_context"] = context
                            row["raw_retrieval"] = deepcopy(context)
                            facts = context["evidence_fact_ids"]
                            row["retrieval_s"] = perf_counter() - retrieval_start
                        else:
                            context = None
                            row["retrieval_s"] = 0.0
                        row["messages"] = build_prompt(public, context)
                        row.update(generator.generate(row["messages"]))
                except Exception as exc:
                    row["error"] = {"type": type(exc).__name__, "message": str(exc)}
                    parse_errors = [f"Inference failed: {type(exc).__name__}: {exc}"]
                latency = perf_counter() - start
                measurement_start = perf_counter()
                if server_monitor is not None:
                    server_monitor.freeze()
                resources = monitor.stop()
                rss = resources["process_peak_rss_mib"]
                if server_monitor is not None:
                    resources.update(server_monitor.stop())
                    resident = resources.get("ollama_model_resident_mib")
                    memory_errors = [error for error in (resources["memory_measurement_error"], resources.get("predictor_memory_error")) if error]
                    resources.update({
                        "predictor_memory_mib": rss + resident if rss is not None and resident is not None and not memory_errors else None,
                        "predictor_memory_scope": "sampled_process_tree_rss_plus_ollama_model_resident_sampled_max",
                        "predictor_memory_error": "; ".join(memory_errors) or None,
                    })
                else:
                    gpu = row.get("cuda_peak_allocated_mib")
                    resources.update({
                        "predictor_memory_mib": rss + (gpu or 0.0) if rss is not None and not resources["memory_measurement_error"] else None,
                        "predictor_memory_scope": "sampled_process_tree_rss_plus_pytorch_cuda_allocated_peak" if gpu is not None else "sampled_process_tree_rss",
                        "predictor_memory_error": resources["memory_measurement_error"],
                    })
                resources.update({
                    "measurement_window": "public_input_ready_to_raw_output",
                    "prediction_window_s": latency,
                    "raw_output_produced": row["raw_output"] is not None,
                })
                row["resource_measurement"] = resources
                row["resource_measurement_s"] = perf_counter() - measurement_start
                parsing_start = perf_counter()
                raw_prediction, raw_parse_errors = None, list(parse_errors)
                if row["error"] is None:
                    raw_prediction, raw_parse_errors = parse_response(row["raw_output"])
                    row["prediction_input"], row["output_normalization"] = prepare_prediction_input(row["raw_output"])
                    if row["output_normalization"]["applied"]:
                        row["prediction"], parse_errors = parse_response(row["prediction_input"])
                    else:
                        row["prediction"], parse_errors = raw_prediction, raw_parse_errors
                    if row.get("backend_errors"):
                        row["error"] = {"type": "ContextLimitError", "message": "; ".join(row["backend_errors"])}
                row["parsing_s"] = perf_counter() - parsing_start
                evaluation_start = perf_counter()
                row["metrics"] = evaluate_prediction(
                    row["prediction"], gold, schema_errors=[*parse_errors, *row.get("backend_errors", [])],
                    retrieved_fact_ids=facts, claims={"causes": kg.catalog["causes"]},
                )
                row["prediction_valid"] = row["metrics"]["schema_compliance"]
                row["prediction_errors"] = list(row["metrics"]["schema_errors"])
                # Raw formatting compliance is independent of the usable prediction.
                raw_schema_errors = list(dict.fromkeys([
                    *raw_parse_errors, *validate_response(raw_prediction), *row.get("backend_errors", []),
                ]))
                row["metrics"]["schema_compliance"] = not raw_schema_errors
                row["metrics"]["schema_errors"] = raw_schema_errors
                row["metrics"].update({
                    "parse_valid": raw_prediction is not None and not raw_parse_errors,
                    "prediction_parse_valid": row["prediction"] is not None and not parse_errors,
                    "latency_s": latency, "parsing_s": row["parsing_s"], "cuda_peak_allocated_mib": row.get("cuda_peak_allocated_mib"),
                    "process_peak_rss_mib": resources["process_peak_rss_mib"],
                    "predictor_memory_mib": resources["predictor_memory_mib"],
                    "ollama_model_resident_mib": resources.get("ollama_model_resident_mib"),
                    "ollama_model_vram_mib": resources.get("ollama_model_vram_mib"),
                })
                unavailable = evaluate_case_rules(row, kg, consistency_causes, consistency_action_catalog)
                row["metrics"].update(evaluate_resources(latency, resources["predictor_memory_mib"], resource_budgets))
                finalize_score(row, score_weights, unavailable)
                finalize_user_output(row)
                row["evaluation_s"] = perf_counter() - evaluation_start
                output.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                output.flush()
                user_outputs.write(json.dumps({
                    "scenario_id": row["scenario_id"], "family_id": row["family_id"], "mode": row["mode"],
                    "source": row["final_output_source"], "status": row["final_output_status"],
                    "user_response": row["final_user_output"],
                    "schema_compliance": row["metrics"]["schema_compliance"], "error": row["error"],
                }, ensure_ascii=False, allow_nan=False) + "\n")
                user_outputs.flush()
                records.append(row)
                print(f"[{mode}] {case['scenario_id']} | family_id={family_id} | {row['metrics']['first_behavior']} | schema={row['metrics']['schema_compliance']} | {latency:.6f}s", flush=True)
                if args.show_steps:
                    print_case_steps(row)
                print_final_user_output(row)
                print_case_score(row)
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_json(directory / "run_config.json", metadata)
    results = summarize(records)
    write_json(directory / "summary.json", {"run": metadata, "results": results})
    write_csv_reports(directory, records, results)
    print_summary(results)
    audit = metadata["dataset_audit"]
    for field in ("differential_registry_coverage", "question_registry_coverage", "fact_registry_coverage"):
        item = audit[field]
        if item["missing_ids"]:
            print(f"Coverage: {field} = {item['covered_unique_ids']}/{item['unique_gold_ids']} unique gold IDs; see summary.json", flush=True)
    print(f"Reports: {directory}", flush=True)
    return directory


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")


if __name__ == "__main__":
    main()
