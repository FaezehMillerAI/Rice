"""Benchmark selection, validation, and gold annotation loading."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from typing import Callable

from eval.scoring import BEHAVIORS


ROOT = Path(__file__).resolve().parents[1]


def _project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def resolve_benchmark_dataset(dataset_override: str | None, benchmark: dict | None) -> Path:
    """An explicit CLI path wins; otherwise the YAML benchmark selects the data."""
    if dataset_override is not None:
        if not isinstance(dataset_override, str) or not dataset_override.strip():
            raise ValueError("--dataset must be a nonempty path")
        return _project_path(dataset_override)
    if not isinstance(benchmark, dict):
        raise ValueError("Configure benchmark.benchmark_file or pass --dataset")
    path = benchmark.get("benchmark_file")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("benchmark.benchmark_file must be a nonempty path unless --dataset is provided")
    if benchmark.get("format", "json") != "json":
        raise ValueError("The unified evaluator requires benchmark.format=json")
    return _project_path(path)


def validate_benchmark_metadata(benchmark: dict, cases: list[dict]) -> None:
    """Check the full configured dataset before applying a run-specific limit."""
    if "total_cases" in benchmark:
        count = benchmark["total_cases"]
        if type(count) is not int or count <= 0 or count != len(cases):
            raise ValueError(f"benchmark.total_cases={count!r} does not match {len(cases)} loaded cases")
    if "schema_version" in benchmark:
        version = benchmark["schema_version"]
        if not isinstance(version, str) or not version or any(case.get("schema_version") != version for case in cases):
            raise ValueError(f"Dataset schema_version does not match benchmark.schema_version={version!r}")
    if "first_behavior_counts" in benchmark:
        counts = benchmark["first_behavior_counts"]
        actual = dict(Counter(case["annotations"]["correct_first_behavior"] for case in cases))
        if (
            not isinstance(counts, dict) or set(counts) - set(BEHAVIORS.values())
            or any(type(value) is not int or value < 0 for value in counts.values())
            or any(counts.get(name, 0) != actual.get(name, 0) for name in BEHAVIORS.values())
        ):
            raise ValueError(f"benchmark.first_behavior_counts={counts!r} does not match {actual}")


def scoring_annotations(case: dict) -> dict:
    """Copy scoring labels, with action and safety references from target_response."""
    sid = case.get("scenario_id", "<unknown>")
    annotations = case.get("annotations")
    if not isinstance(annotations, dict):
        raise ValueError(f"{sid}: annotations must be an object")
    gold = deepcopy(annotations)
    target = case.get("target_response")
    if not isinstance(target, dict):
        raise ValueError(f"{sid}: reference target_response must be an object")
    for field in ("actions", "safety_flags"):
        values = target.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"{sid}: target_response.{field} must be a list of nonempty strings")
        gold[field] = deepcopy(values)
    return gold


def load_cases(
    path: Path,
    *,
    select_public_case_fn: Callable[[dict], dict] | None = None,
) -> list[dict]:
    """Load and validate cases without exposing private labels to a predictor."""
    if select_public_case_fn is None:
        from engine.prompting import select_public_case

        select_public_case_fn = select_public_case
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data if isinstance(data, list) else [data]
    if not cases:
        raise ValueError("Dataset is empty")
    seen = set()
    gold_lists = ("acceptable_differential", "required_confounders", "required_questions", "supporting_fact_ids", "supporting_source_ids")
    for case in cases:
        sid = case.get("scenario_id")
        if not isinstance(sid, str) or not sid or sid in seen:
            raise ValueError(f"Missing or duplicate scenario_id: {sid!r}")
        seen.add(sid)
        family_id = case.get("family_id")
        if family_id is not None and (
            not isinstance(family_id, str) or (family_id and not family_id.strip())
        ):
            raise ValueError(f"{sid}: family_id must be a nonempty string when provided")
        public = select_public_case_fn(case)
        if not isinstance(public["input"]["user_text"], str) or not public["input"]["user_text"].strip():
            raise ValueError(f"{sid}: missing user_text")
        gold = scoring_annotations(case)
        for key in gold_lists:
            if not isinstance(gold.get(key), list) or any(not isinstance(x, str) or not x.strip() for x in gold[key]):
                raise ValueError(f"{sid}: annotations.{key} must be a list of IDs")
        if gold.get("correct_first_behavior") not in BEHAVIORS.values() or type(gold.get("escalation_required")) is not bool:
            raise ValueError(f"{sid}: invalid behavior/escalation annotation")
        if (gold["correct_first_behavior"] == "ESCALATE") != gold["escalation_required"]:
            raise ValueError(f"{sid}: conflicting behavior/escalation annotation")
    return cases
