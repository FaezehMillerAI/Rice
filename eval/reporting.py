"""Aggregation and presentation of unified evaluation results."""

from __future__ import annotations

from collections import Counter
import csv
import json
import math
from pathlib import Path
import statistics
from typing import Any

from eval.scoring import (
    BEHAVIORS,
    SCORE_CATEGORIES,
    SCORE_METRICS,
    SCORE_TABLE_COLUMNS,
    group_category_scores,
)


def count_assessments(assessments) -> dict:
    values = []
    not_applicable = 0
    for applicable, value in assessments:
        if applicable:
            values.append(value)
        else:
            not_applicable += 1
    passed = values.count(1)
    partial = sum(value is not None and 0 < value < 1 for value in values)
    scored = sum(value is not None for value in values)
    return {
        "scored_n": scored, "passed_n": passed, "partial_n": partial,
        "failed_n": len(values) - scored, "not_applicable_n": not_applicable,
        "applicable_n": len(values), "assessed_n": scored,
        "pass_rate": passed / len(values) if values else None,
    }


def summarize(records: list[dict]) -> dict:
    metrics = (
        *SCORE_METRICS,
        "parse_valid", "prediction_parse_valid", "escalation_recall", "gold_fact_id_precision", "gold_fact_id_recall",
        "retrieved_fact_id_precision", "latency_s", "parsing_s", "cuda_peak_allocated_mib", "final_score",
        "unsupported_claim_rate", "structured_item_count",
        "process_peak_rss_mib", "predictor_memory_mib", "ollama_model_resident_mib", "ollama_model_vram_mib",
        "latency_efficiency", "memory_efficiency",
    )
    rows_by_mode = {}
    for row in records:
        rows_by_mode.setdefault(row["mode"], []).append(row)
    summary = {}
    for mode, rows in rows_by_mode.items():
        components_by_case = [row.get("score_breakdown", {}).get("components", {}) for row in rows]
        component_names = dict.fromkeys(name for components in components_by_case for name in components)
        means = {}
        for metric in metrics:
            if metric in component_names:
                # Keep applicability counts separate from the fixed-scale score mean.
                applicable = [(row, components.get(metric, {})) for row, components in zip(rows, components_by_case)
                              if metric not in row.get("not_applicable_metrics", {})
                              and components.get(metric, {}).get("applicable", True)]
                values = [row["metrics"].get(metric) or 0.0 for row in rows]
                assessed_n = sum(
                    component.get("assessed", row["metrics"].get(metric) is not None)
                    for row, component in applicable
                )
                means[metric] = {"value": statistics.mean(values), "applicable_n": len(applicable)}
                # Keep the existing schema metric shape for report consumers.
                if assessed_n != len(applicable):
                    means[metric]["assessed_n"] = assessed_n
            else:
                values = [row["metrics"][metric] for row in rows if row["metrics"].get(metric) is not None]
                means[metric] = {"value": statistics.mean(values) if values else None, "applicable_n": len(values)}
        recalls = {}
        confusion = {}
        per_class = {}
        for behavior in BEHAVIORS.values():
            subset = [row for row in rows if row["gold"]["correct_first_behavior"] == behavior]
            recalls[behavior] = {"value": statistics.mean(row["metrics"]["behavior_correctness"] for row in subset) if subset else None, "applicable_n": len(subset)}
            confusion[behavior] = dict(Counter(row["metrics"]["first_behavior"] for row in subset))
            # INVALID predictions remain false negatives for their gold class.
            tp = confusion[behavior].get(behavior, 0)
            support = len(subset)
            predicted_n = sum(row["metrics"]["first_behavior"] == behavior for row in rows)
            fp, fn = predicted_n - tp, support - tp
            per_class[behavior] = {
                "precision": tp / predicted_n if predicted_n else None,
                "recall": tp / support if support else None,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                "support": support, "predicted_n": predicted_n,
                "tp": tp, "fp": fp, "fn": fn,
            }
        summary[mode] = {
            "n": len(rows), "metrics": means, "behavior_recall": recalls, "behavior_confusion": confusion,
            "behavior_per_class": per_class,
            "final_score": means["final_score"]["value"], "score_breakdown": {},
            "category_scores": {},
            "inference_errors": sum(bool(row["error"]) for row in rows),
            "escalation_false_positives": sum(row["metrics"]["escalation_false_positive"] for row in rows),
            "output_budget_exhausted": sum(row.get("output_budget_exhausted", False) for row in rows),
            "latency_by_outcome": {},
        }
        scored_indices = [index for index, row in enumerate(rows) if row["metrics"].get("final_score") is not None]
        for name in component_names:
            components = [items.get(name, {}) for items in components_by_case]
            contributions = [components[index].get("contribution", 0.0) for index in scored_indices]
            outcomes = count_assessments((item["applicable"], item["raw_value"]) for item in components if item)
            summary[mode]["score_breakdown"][name] = {
                **outcomes,
                "mean_contribution_points": statistics.mean(contributions) if contributions else None,
                "eligible_n": outcomes["applicable_n"],
                "missing_reasons": dict(Counter(item["missing_reason"] for item in components if item.get("missing_reason"))),
                "not_applicable_reasons": dict(Counter(item["not_applicable_reason"] for item in components if item.get("not_applicable_reason"))),
            }
        case_categories = [group_category_scores(components) for components in components_by_case]
        for category, names in SCORE_CATEGORIES.items():
            selected = [name for name in names if name in component_names]
            if not selected:
                continue
            if len(selected) == 1:
                metric = selected[0]
                component = next(components[metric] for components in components_by_case if metric in components)
                summary[mode]["category_scores"][category] = {
                    "metric": metric, "value": means[metric]["value"],
                    "score_direction": "higher_is_better",
                    "weight": component["configured_weight"],
                    **summary[mode]["score_breakdown"][metric],
                }
                continue
            groups = [group.get(category) for group in case_categories]
            first = next(group for group in groups if group is not None)
            applicable = [group for group in groups if group and group["applicable"]]
            contributions = [groups[index]["contribution"] if groups[index] else 0.0 for index in scored_indices]
            summary[mode]["category_scores"][category] = {
                "metrics": selected, "score_direction": "higher_is_better",
                "value": statistics.mean(group["value"] for group in groups if group is not None),
                "weight": first["configured_weight"],
                "mean_contribution_points": statistics.mean(contributions) if contributions else None,
                "applicable_n": len(applicable),
                "eligible_n": len(applicable),
                "assessed_n": sum(bool(group and group["assessed"]) for group in groups),
                "missing_reasons": dict(Counter(group["missing_reason"] for group in groups if group and group["missing_reason"])),
                "components": {
                    metric: {
                        "value": means[metric]["value"],
                        "weight": next(components[metric]["configured_weight"] for components in components_by_case if metric in components),
                        **summary[mode]["score_breakdown"][metric],
                    } for metric in selected
                },
            }
        for name, subset in (
            ("schema_compliance", [row for row in rows if row["metrics"]["schema_compliance"]]),
            ("schema_invalid", [row for row in rows if not row["metrics"]["schema_compliance"]]),
            ("inference_error", [row for row in rows if row["error"]]),
        ):
            summary[mode]["latency_by_outcome"][name] = {
                "mean_s": statistics.mean(row["metrics"]["latency_s"] for row in subset) if subset else None,
                "n": len(subset),
            }
    return summary


def score_table_columns(include_question_recall: bool) -> tuple:
    if include_question_recall:
        return SCORE_TABLE_COLUMNS + (("Q-R", "required_question_recall"),)
    return SCORE_TABLE_COLUMNS


def format_score(value, *, precision=2) -> str:
    return "N/A" if value is None else f"{value:.{precision}f}"


def score_table_rows(raw_values: list, weighted: list[str], final_score) -> tuple[list[str], list[str]]:
    available_raw = [value for value in raw_values if value is not None]
    raw_total = f"{math.fsum(available_raw):.2f}/{len(available_raw)}" if available_raw else "N/A"
    weighted_total = f"{final_score:.2f}/100" if final_score is not None else "N/A"
    return ["raw", *(format_score(value) for value in raw_values), raw_total], ["weighted", *weighted, weighted_total]


def print_table(headers: tuple, rows: list[list[str]], *, left_columns: int = 1) -> None:
    widths = [max([len(header), *(len(row[index]) for row in rows)])
              for index, header in enumerate(headers)]

    def format_row(cells):
        return "  ".join(cell.ljust(width) if index < left_columns else cell.rjust(width)
                         for index, (cell, width) in enumerate(zip(cells, widths)))

    print(format_row(headers), flush=True)
    print("  ".join("-" * width for width in widths), flush=True)
    for row in rows:
        print(format_row(row), flush=True)


def print_case_score(row: dict) -> None:
    breakdown = row["score_breakdown"]
    components = breakdown["components"]
    metric_columns = score_table_columns("required_question_recall" in components)
    headers = ("row", *(label for label, _ in metric_columns), "total")
    labels = {"scored": "Scored", "failed": "Fail", "not_applicable": "N/A"}
    outcomes = [labels[components[name]["state"]] if name in components else "-" for _, name in metric_columns]
    raw_values = [row["metrics"].get(name) for _, name in metric_columns]
    weighted = [format_score(components[name]["contribution"]) if name in components else "-"
                for _, name in metric_columns]
    raw_row, weighted_row = score_table_rows(raw_values, weighted, breakdown["score"])
    print(f"\n=== Case score | {row['mode']} | {row['scenario_id']} ===", flush=True)
    print_table(headers, [["status", *outcomes, ""], raw_row, weighted_row])


def print_summary(results: dict) -> None:
    """Print average unweighted scores and points for each mode."""
    metric_columns = score_table_columns(any(
        "required_question_recall" in result.get("score_breakdown", {}) for result in results.values()
    ))
    headers = ("mode", "n", "row", *(label for label, _ in metric_columns), "total")
    rows, details = [], []
    for mode, result in results.items():
        def display(metric, *, precision=2):
            return format_score(result["metrics"][metric]["value"], precision=precision)

        breakdown = result.get("score_breakdown", {})
        raw_values = [result["metrics"][name]["value"] for _, name in metric_columns]
        weighted = [format_score(breakdown[name]["mean_contribution_points"]) if name in breakdown else "-"
                    for _, name in metric_columns]
        raw_row, weighted_row = score_table_rows(raw_values, weighted, result["final_score"])
        rows.extend(([mode, str(result["n"]), *raw_row], ["", "", *weighted_row]))
        details.append(
            f"  {mode}: latency={display('latency_s', precision=6)}s | memory={display('predictor_memory_mib')} MiB "
            f"| CUDA peak={display('cuda_peak_allocated_mib')} MiB"
        )
    print("\n=== Score summary ===", flush=True)
    print_table(headers, rows)
    for detail in details:
        print(detail, flush=True)
    print_behavior_performance(results)


def print_behavior_performance(results: dict) -> None:
    """Display unweighted per-class behavior diagnostics for every mode."""
    headers = ("mode", "behavior", "precision", "recall", "f1", "support", "predicted")
    rows = []
    for mode, result in results.items():
        for behavior, item in result["behavior_per_class"].items():
            values = [format_score(item[key]) for key in ("precision", "recall", "f1")]
            rows.append([mode, behavior, *values, str(item["support"]), str(item["predicted_n"])])
    print("\n=== Per-class behavior performance ===", flush=True)
    print_table(headers, rows, left_columns=2)


def finalize_user_output(row: dict) -> None:
    """Expose the actual answer independently of scores, without repairing it."""
    prediction = row.get("prediction")
    text = prediction.get("user_response") if isinstance(prediction, dict) else None
    row["final_output_source"] = "kg_template" if row["mode"] == "kg-only" else "model_generated"
    if isinstance(text, str) and text.strip():
        status = "inference_error" if row.get("error") else "ready" if row.get("metrics", {}).get("schema_compliance") is True else "schema_invalid"
    elif row["mode"] != "kg-only" and prediction is None and isinstance(row.get("raw_output"), str) and row["raw_output"].strip():
        text = row["raw_output"]
        status = "inference_error" if row.get("error") else "raw_output"
    else:
        text = None
        status = "inference_error" if row.get("error") else "missing_user_response" if isinstance(prediction, dict) else "no_output"
    row["final_user_output"] = text
    row["final_output_status"] = status


def print_final_user_output(row: dict) -> None:
    print(f"\n[Final user output] {row['mode']} | {row['scenario_id']} | source={row['final_output_source']} | status={row['final_output_status']}", flush=True)
    print(row["final_user_output"] if row["final_user_output"] is not None else "<no user response>", flush=True)


def print_case_steps(row: dict) -> None:
    """Display inference stages and errors without dumping scoring details."""
    def show(label: str, value: Any) -> None:
        print(f"\n{label}", flush=True)
        print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), flush=True)

    family_id = row.get("family_id") or row["scenario_id"]
    print(f"\n=== {row['mode']} | {row['scenario_id']} | family_id={family_id} ===", flush=True)
    show("[1] Public input", row["public_input"])
    if row["mode"] == "kg-only":
        context = row.get("raw_kg_response")
    elif row["mode"] == "model-only":
        context = None
    else:
        context = row.get("retrieved_context")
    show("[2] KG context (disabled for model-only)" if row["mode"] == "model-only" else "[2] KG context", context)
    show("[3] Inference request", row.get("ollama_request") or row.get("messages"))
    print("\n[4] Raw output", flush=True)
    print(row.get("raw_output") if row.get("raw_output") is not None else "<no output>", flush=True)
    if row.get("output_normalization", {}).get("applied"):
        show("[4a] Prediction input (outer Markdown fence removed)", row.get("prediction_input"))
    show("[5] Parsed prediction", row.get("prediction"))
    schema_errors = row.get("metrics", {}).get("schema_errors", [])
    if row.get("error") or schema_errors:
        show("[Errors]", {"error": row.get("error"), "schema_errors": schema_errors})


def write_csv_reports(directory: Path, records: list[dict], results: dict) -> None:
    with (directory / "behavior_per_class.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["mode", "behavior", "precision", "recall", "f1", "support", "predicted_n", "tp", "fp", "fn"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mode, result in results.items():
            for behavior, item in result["behavior_per_class"].items():
                writer.writerow({key: "N/A" if value is None else value
                                 for key, value in {"mode": mode, "behavior": behavior, **item}.items()})
    with (directory / "case_metrics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        case_fields = ("scenario_id", "family_id", "mode", "final_output_source", "final_output_status", "final_user_output")
        fields = [*case_fields, *records[0]["metrics"], "assessment_states"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in records:
            values = {
                **{key: row[key] for key in case_fields}, **row["metrics"],
                "assessment_states": {
                    "metrics": {name: item["state"] for name, item in row["score_breakdown"]["components"].items()},
                },
            }
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in values.items()})
