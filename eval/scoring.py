"""Deterministic per-case metrics and weighted score composition."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from contracts.response import STATUS_TO_BEHAVIOR, validate_response
from eval.rule_evaluator import question_agreement_exemption


BEHAVIORS = dict(STATUS_TO_BEHAVIOR)
SCORE_TABLE_COLUMNS = (
    ("behavior", "behavior_correctness"), ("P@1", "differential_top1_precision"),
    ("R@3", "differential_top3_recall"), ("F1", "differential_f1"),
    ("conf-R", "confounder_recall"), ("gnd", "groundedness"),
    ("Q-agr", "question_agreement"), ("E-agr", "evidence_agreement"),
    ("A-agr", "actions_agreement"), ("SF-agr", "safety_flags_agreement"),
    ("Escalation", "escalation_correctness"),
    ("consistency", "structured_output_vs_user_response_consistency"),
    ("safety", "response_safety_check"), ("schema", "schema_compliance"),
    ("resources", "resource_efficiency"),
)
SCORE_METRICS = (*(name for _, name in SCORE_TABLE_COLUMNS), "required_question_recall")
SCORE_CATEGORIES = {
    "behavior_correctness": ("behavior_correctness",),
    "differential_metrics": ("differential_top1_precision", "differential_top3_recall", "differential_f1"),
    "confounder_recall": ("confounder_recall",),
    "groundedness": ("groundedness",),
    "question_agreement": ("question_agreement",),
    "evidence_agreement": ("evidence_agreement",),
    "actions_agreement": ("actions_agreement",),
    "safety_flags_agreement": ("safety_flags_agreement",),
    "escalation_correctness": ("escalation_correctness",),
    "structured_output_vs_user_response_consistency": ("structured_output_vs_user_response_consistency",),
    "response_safety_check": ("response_safety_check",),
    "schema_compliance": ("schema_compliance",),
    "resource_efficiency": ("resource_efficiency",),
}
METRIC_LABELS = {
    "behavior_correctness": "Behavior Correctness",
    "differential_metrics": "Differential Metrics",
    "confounder_recall": "Confounder Recall",
    "groundedness": "Groundedness",
    "question_agreement": "Question Agreement",
    "evidence_agreement": "Evidence Agreement",
    "actions_agreement": "Actions Agreement",
    "safety_flags_agreement": "Safety_flags Agreement",
    "escalation_correctness": "Escalation Correctness",
    "structured_output_vs_user_response_consistency": "Structured_output vs User_response Consistency",
    "response_safety_check": "Response Safety Check",
    "schema_compliance": "Schema Compliance",
    "resource_efficiency": "Resource Efficiency",
}


def set_scores(predicted: list[str], gold: list[str]) -> tuple[float | None, float | None, float | None]:
    expected, actual = set(gold), set(predicted)
    if not expected:
        return None, None, None
    hits = len(actual & expected)
    precision = hits / len(actual) if actual else 0.0
    recall = hits / len(expected)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def evaluate_differential_ranking(predicted: list[str], gold: list[str]) -> dict:
    """Score primary diagnosis, top-three coverage, and full-set candidate F1."""
    expected, actual = set(gold), set(predicted)
    top1, top3 = predicted[:1], predicted[:3]
    hits = set(top3) & expected
    full_hits = actual & expected
    if expected:
        precision = float(bool(top1) and top1[0] == gold[0])
        recall = len(hits) / len(expected)
        f1 = 2 * len(full_hits) / (len(actual) + len(expected))
    else:
        precision = recall = f1 = None
    return {
        "differential_top1_precision": precision,
        "differential_top3_recall": recall,
        "differential_f1": f1,
        "differential_ranking": {
            "precision_cutoff": 1, "recall_cutoff": 3,
            "top1_ids": list(top1), "top3_ids": list(top3),
            "reference_top1_ids": list(gold[:1]), "reference_ranked_ids": list(gold),
            "top3_hit_ids": sorted(hits), "reference_ids": sorted(expected),
            "full_hit_ids": sorted(full_hits), "full_unique_count": len(actual),
            "candidate_count": len(predicted), "ignored_tail_count": max(0, len(predicted) - 3),
            "tail_count_scope": "top3_recall_only; all positions enter full-set F1",
            "duplicate_top3_count": len(top3) - len(set(top3)),
            "cutoff_policy": "slice_raw_positions_before_deduplicating_hits",
            "f1_definition": "full_differential_set_f1",
        },
    }


def evaluate_prediction(
    prediction: dict | None, annotations: dict, *, schema_errors=(),
    retrieved_fact_ids: list[str] | None = None, claims: dict | None = None,
) -> dict:
    """Ranked differential scores and exact-ID diagnostics, without semantic judging."""
    errors = list(dict.fromkeys([*schema_errors, *validate_response(prediction)]))
    valid = not errors
    response = prediction if valid else {}
    behavior = BEHAVIORS[response["status"]] if valid else "INVALID"
    differential = response.get("differential", [])
    ranked_differential = evaluate_differential_ranking(differential, annotations["acceptable_differential"])
    facts = response.get("grounding", [])
    fact_precision, fact_recall, _ = set_scores(facts, annotations["supporting_fact_ids"])
    # Exclude the raw first position before set matching; retain every later rank.
    confounder_recall = set_scores(differential[1:], annotations["required_confounders"])[1]
    question_recall = set_scores(response.get("observations_needed", []), annotations["required_questions"])[1]
    # Invalid output is a failure even for negative escalation cases.
    escalation_correctness = valid and response["escalation_required"] == annotations["escalation_required"]
    retrieved_precision = None
    if retrieved_fact_ids is not None:
        retrieved_precision = len(set(facts) & set(retrieved_fact_ids)) / len(set(facts)) if facts else 0.0
    return {
        "schema_compliance": valid,
        "schema_errors": errors,
        "first_behavior": behavior,
        "behavior_correctness": behavior == annotations["correct_first_behavior"],
        **ranked_differential,
        "confounder_recall": confounder_recall,
        "required_question_recall": question_recall,
        "escalation_correctness": escalation_correctness,
        "escalation_recall": float(valid and response["escalation_required"]) if annotations["escalation_required"] else None,
        "escalation_false_positive": bool(valid and response["escalation_required"] and not annotations["escalation_required"]),
        "gold_fact_id_precision": fact_precision,
        "gold_fact_id_recall": fact_recall,
        "retrieved_fact_id_precision": retrieved_precision,
        "grounding_id_count": len(set(facts)),
        "cause_ids_absent_from_registry": [x for x in differential if claims is not None and x not in claims.get("causes", {})],
    }


def validate_score_weights(weights: Any) -> dict[str, float]:
    """Accept nonnegative relative weights for the implemented score metrics."""
    if not isinstance(weights, dict) or not weights:
        raise ValueError("unified_weights must be a nonempty mapping")
    unknown = set(weights) - set(SCORE_METRICS)
    if unknown:
        raise ValueError(f"Unknown unified score metrics: {sorted(unknown, key=str)}")
    validated = {}
    for name, value in weights.items():
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Weight for {name} must be a finite nonnegative number")
        validated[name] = float(value)
    total = sum(validated.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("unified_weights must have a finite positive total")
    return validated


def load_score_weights(path: Path) -> dict[str, float]:
    import yaml

    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid score configuration: {path}: {exc}") from exc
    if not isinstance(config, dict) or "unified_weights" not in config:
        raise ValueError(f"Score configuration must contain unified_weights: {path}")
    return validate_score_weights(config["unified_weights"])


def assessment_state(value, applicable=True):
    if not applicable:
        return "not_applicable"
    return "scored" if value is not None else "failed"


def compute_weighted_score(
    metrics: dict, weights: dict, *, unavailable_metrics: dict | None = None,
    prediction_valid: bool | None = None, not_applicable_metrics: dict | None = None,
) -> dict:
    """Use fixed relative weights and score all null values as zero."""
    weights = validate_score_weights(weights)
    total_weight = math.fsum(weights.values())
    unavailable_metrics = unavailable_metrics or {}
    not_applicable_metrics = not_applicable_metrics or {}
    if "schema_compliance" not in metrics:
        raise ValueError("Missing score metric: schema_compliance")
    components = {}
    for name, weight in weights.items():
        if name not in metrics:
            raise ValueError(f"Missing score metric: {name}")
        value = metrics[name]
        applicable = name not in not_applicable_metrics
        if not applicable and value is not None:
            raise ValueError(f"Non-applicable score metric {name} must be null")
        if value is not None and (
            not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1
        ):
            raise ValueError(f"Score metric {name} must be null or a finite number in [0, 1]")
        components[name] = {
            "value": 0.0 if value is None else value,
            "raw_value": value, "zero_filled": value is None,
            "configured_weight": weight, "effective_weight": weight / total_weight,
            "contribution": 0.0, "applicable": applicable,
            "assessed": value is not None,
            "state": assessment_state(value, applicable),
            "not_applicable_reason": not_applicable_metrics.get(name),
            "missing_reason": (unavailable_metrics.get(name) or "metric_returned_none") if applicable and value is None else None,
        }
    applicable_weight = math.fsum(item["configured_weight"] for item in components.values() if item["applicable"])
    schema_gate_passed = metrics["schema_compliance"] is True
    if prediction_valid is not None and type(prediction_valid) is not bool:
        raise ValueError("prediction_valid must be a boolean or null")
    prediction_gate_passed = schema_gate_passed if prediction_valid is None else prediction_valid
    if prediction_gate_passed:
        for item in components.values():
            item["contribution"] = 100 * item["effective_weight"] * item["value"]
    score = min(100.0, math.fsum(item["contribution"] for item in components.values()))
    return {
        "score": score,
        "applicable_weight": applicable_weight, "schema_gate_passed": schema_gate_passed,
        "prediction_gate_passed": prediction_gate_passed,
        "unavailable_metrics": {name: item["missing_reason"] for name, item in components.items() if item["missing_reason"]},
        "not_applicable_metrics": {name: item["not_applicable_reason"] for name, item in components.items() if not item["applicable"]},
        "components": components,
    }


def validate_resource_budgets(resource: Any) -> dict:
    if not isinstance(resource, dict):
        raise ValueError("resource_budgets must be a mapping")
    result = {}
    for key in ("latency_s", "memory_mib"):
        value = resource.get(key)
        if value is not None and (type(value) not in (float, int) or not math.isfinite(value) or value <= 0):
            raise ValueError(f"resource_budgets.{key} must be a finite positive number or null")
        result[key] = value
    return result


def load_resource_budgets(path: Path) -> dict:
    import yaml

    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Score configuration must be a mapping")
    return validate_resource_budgets(config.get("resource_budgets", {}))


def evaluate_resources(latency: float, memory: float | None, budgets: dict) -> dict:
    """Linear efficiencies within budget; at or above the limit scores zero."""
    def efficiency(actual, budget):
        if (type(actual) not in (int, float) or not math.isfinite(actual) or actual < 0
                or type(budget) not in (int, float) or not math.isfinite(budget) or budget <= 0):
            return None
        return max(0.0, 1.0 - actual / budget)

    latency_score = efficiency(latency, budgets["latency_s"])
    memory_score = efficiency(memory, budgets["memory_mib"])
    return {
        "latency_efficiency": latency_score, "memory_efficiency": memory_score,
        "resource_efficiency": (latency_score + memory_score) / 2 if latency_score is not None and memory_score is not None else None,
    }


def group_category_scores(components: dict) -> dict:
    """Group configured components without adding another contribution to the total."""
    categories = {}
    for category, names in SCORE_CATEGORIES.items():
        selected = {name: components[name] for name in names if name in components}
        if not selected:
            continue
        if len(selected) == 1:
            metric, component = next(iter(selected.items()))
            categories[category] = {
                "metric": metric, "score_direction": "higher_is_better", **component,
            }
            continue
        applicable = [item for item in selected.values() if item["applicable"]]
        weight = math.fsum(item["configured_weight"] for item in selected.values())
        value = math.fsum(
            item["configured_weight"] * item["value"] for item in selected.values()
        ) / weight if weight else 0.0
        missing = {
            name: item["missing_reason"] for name, item in selected.items()
            if item["applicable"] and item["configured_weight"] and not item["assessed"]
        }
        categories[category] = {
            "metrics": list(selected), "components": selected,
            "score_direction": "higher_is_better", "value": value,
            "raw_value": value if applicable and not missing else None,
            "zero_filled": any(item["zero_filled"] and item["configured_weight"] > 0 for item in selected.values()),
            "configured_weight": weight,
            "effective_weight": math.fsum(item["effective_weight"] for item in selected.values()),
            "contribution": math.fsum(item["contribution"] for item in selected.values()),
            "applicable": bool(applicable),
            "assessed": bool(applicable) and not missing, "missing_reasons": missing,
            "missing_reason": "unassessed_components: " + ", ".join(missing) if missing else None,
        }
    return categories


def metric_exemptions(row: dict) -> dict:
    """Recognize applicability from references and usable prediction fields."""
    gold = row.get("gold", {})
    exempt = {}
    if gold.get("required_confounders") == []:
        exempt["confounder_recall"] = "no_required_confounders"
    if gold.get("required_questions") == []:
        exempt["required_question_recall"] = "no_required_questions"
    if reason := question_agreement_exemption(gold):
        exempt["question_agreement"] = reason
    if gold.get("acceptable_differential") == []:
        for metric in SCORE_CATEGORIES["differential_metrics"]:
            exempt[metric] = "no_reference_differential"
        prediction = row.get("prediction")
        if (row.get("prediction_valid") and isinstance(prediction, dict)
                and prediction.get("differential") == []
                and prediction.get("status") in {"needs_more_information", "escalation_required"}
                and gold.get("correct_first_behavior") in {"ASK", "ESCALATE"}):
            exempt["groundedness"] = "no_differential_required_or_predicted"
    return exempt


def finalize_score(row: dict, weights: dict, unavailable: dict) -> None:
    if row["metrics"]["resource_efficiency"] is None:
        unavailable["resource_efficiency"] = row["resource_measurement"].get("predictor_memory_error") or "resource_measurement_or_budget_unavailable"
    row["not_applicable_metrics"] = metric_exemptions(row)
    row["score_breakdown"] = compute_weighted_score(
        row["metrics"], weights, unavailable_metrics=unavailable,
        prediction_valid=row.get("prediction_valid"),
        not_applicable_metrics=row["not_applicable_metrics"],
    )
    breakdown = row["score_breakdown"]
    row["unavailable_metrics"] = breakdown["unavailable_metrics"]
    row["raw_score_metrics"] = {name: item["raw_value"] for name, item in breakdown["components"].items()}
    row["metrics"].update({name: item["value"] for name, item in breakdown["components"].items()})
    row["metrics"]["final_score"] = breakdown["score"]
    # Keep weighted results in configuration order in JSON and CSV reports.
    row["metrics"] = {
        **{name: row["metrics"][name] for name in weights},
        **{name: value for name, value in row["metrics"].items() if name not in weights},
    }
    row["category_scores"] = group_category_scores(breakdown["components"])
