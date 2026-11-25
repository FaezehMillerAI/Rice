"""Benchmark manifests select data without conflating full and limited runs."""

from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

import eval.evaluate_unified as unified


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/eval/eval_config.yaml"
DEFAULT_DATASET = "data/eval/gold_eval_v0.4.json"
DEFAULT_SCHEMA_VERSION = "0.4.0"
DATASET = ROOT / DEFAULT_DATASET
SLICE_PREFIXES = {
    "ambiguous_triage_count": "case-amb-",
    "lookalike_differential_count": "case-diff-",
    "negative_evidence_count": "case-neg-",
    "safety_escalation_count": "case-esc-",
    "multiturn_dialogue_count": "case-multi-",
    "contrast_differential_count": "case-contrast-",
}


def repository_config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def fake_resource_monitor():
    monitor = Mock()
    monitor.start.return_value = monitor
    monitor.stop.return_value = {
        "process_peak_rss_mib": 128.0,
        "memory_measurement_scope": "evaluator_process_tree",
        "memory_sample_count": 1,
        "memory_measurement_error": None,
    }
    return monitor


class BenchmarkSelectionTests(unittest.TestCase):
    def test_repository_manifest_matches_json_dataset_and_case_groups(self):
        benchmark = repository_config()["benchmark"]
        self.assertEqual(benchmark["benchmark_file"], DEFAULT_DATASET)
        self.assertEqual(benchmark["format"], "json")
        self.assertEqual(benchmark["schema_version"], DEFAULT_SCHEMA_VERSION)
        path = unified.resolve_benchmark_dataset(None, benchmark)
        self.assertEqual(path, DATASET.resolve())
        self.assertEqual(path.suffix, ".json")
        cases = unified.load_cases(path)
        self.assertEqual(benchmark["total_cases"], len(cases))
        self.assertEqual(len(cases), 65)
        self.assertEqual({case["schema_version"] for case in cases}, {DEFAULT_SCHEMA_VERSION})
        self.assertEqual(benchmark["first_behavior_counts"],
                         dict(Counter(case["annotations"]["correct_first_behavior"] for case in cases)))
        self.assertEqual(benchmark["first_behavior_counts"], {"ASK": 16, "ANSWER": 43, "ESCALATE": 6})
        actual_slices = {
            name: sum(case["scenario_id"].startswith(prefix) for case in cases)
            for name, prefix in SLICE_PREFIXES.items()
        }
        self.assertEqual(benchmark["slices"], actual_slices)
        self.assertEqual(list(actual_slices.values()), [16, 21, 11, 6, 7, 4])
        self.assertEqual(sum(actual_slices.values()), len(cases))
        unified.validate_benchmark_metadata(benchmark, cases)

    def test_dataset_audit_recognizes_current_and_legacy_fact_and_source_ids(self):
        current = unified.load_cases(DATASET)[0]
        legacy = unified.load_cases(ROOT / "data/eval/gold_eval_v0.3.json")[0]
        fields = {
            "fact_registry_coverage": ("supporting_fact_ids", "FACT_999999"),
            "source_registry_coverage": ("supporting_source_ids", "SOURCE_999999"),
        }
        expected_coverage = {}
        for key, (field, missing_id) in fields.items():
            known = set(current["annotations"][field]) | set(legacy["annotations"][field])
            occurrences = len(current["annotations"][field]) + len(legacy["annotations"][field])
            current["annotations"][field].append(missing_id)
            expected_coverage[key] = {
                "unique_gold_ids": len(known) + 1,
                "covered_unique_ids": len(known),
                "gold_id_occurrences": occurrences + 1,
                "covered_occurrences": occurrences,
                "missing_ids": [missing_id],
            }

        audit = unified.dataset_audit([current, legacy], unified.KGAdapter())

        for key, expected in expected_coverage.items():
            with self.subTest(key=key):
                self.assertEqual(audit[key], expected)

    def test_explicit_dataset_wins_over_absent_or_invalid_benchmark(self):
        malformed = {"benchmark_file": False, "format": "jsonl", "total_cases": -1}
        override = ROOT / "custom-cases.json"
        for benchmark in (None, {}, malformed):
            with self.subTest(benchmark=benchmark):
                self.assertEqual(unified.resolve_benchmark_dataset("custom-cases.json", benchmark),
                                 override.resolve())
                self.assertEqual(unified.resolve_benchmark_dataset(str(override.resolve()), benchmark),
                                 override.resolve())

    def test_config_selection_requires_a_nonempty_json_dataset_path(self):
        invalid = (None, [], {}, {"benchmark_file": None}, {"benchmark_file": False},
                   {"benchmark_file": 12}, {"benchmark_file": ""}, {"benchmark_file": "  "},
                   {"benchmark_file": "cases.json", "format": "jsonl"})
        for benchmark in invalid:
            with self.subTest(benchmark=benchmark):
                with self.assertRaises(ValueError):
                    unified.resolve_benchmark_dataset(None, benchmark)
        self.assertEqual(unified.resolve_benchmark_dataset(None, {"benchmark_file": DEFAULT_DATASET}),
                         DATASET.resolve())


class BenchmarkMetadataTests(unittest.TestCase):
    def setUp(self):
        self.cases = deepcopy(unified.load_cases(DATASET)[:2])

    def test_optional_metadata_and_custom_slices_are_not_inferred_from_ids(self):
        benchmark = {
            "total_cases": 2, "schema_version": DEFAULT_SCHEMA_VERSION,
            "first_behavior_counts": {"ASK": 2, "ANSWER": 0, "ESCALATE": 0},
            "slices": {"custom_experiment_count": 999},
        }
        original = deepcopy((benchmark, self.cases))
        unified.validate_benchmark_metadata({}, self.cases)
        unified.validate_benchmark_metadata(benchmark, self.cases)
        unified.validate_benchmark_metadata({"first_behavior_counts": {"ASK": 2}}, self.cases)
        self.assertEqual((benchmark, self.cases), original)

    def test_total_cases_rejects_mismatches_nonintegers_and_booleans(self):
        for count in (0, -1, 1, 3, 2.0, "2", True, False, None):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    unified.validate_benchmark_metadata({"total_cases": count}, self.cases)

    def test_schema_version_must_match_every_case(self):
        for version in ("0.2.0", "0.3.0", "", None, True, 0.3):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    unified.validate_benchmark_metadata({"schema_version": version}, self.cases)
        self.cases[1]["schema_version"] = "0.2.0"
        with self.assertRaises(ValueError):
            unified.validate_benchmark_metadata({"schema_version": DEFAULT_SCHEMA_VERSION}, self.cases)

    def test_behavior_counts_reject_bad_types_unknown_labels_and_wrong_counts(self):
        invalid = (None, [], 2, {}, {"ASK": True}, {"ASK": 2.0}, {"ASK": "2"},
                   {"ASK": -1}, {"ASK": 1}, {"ASK": 2, "ANSWER": 1},
                   {"ASK": 2, "ESCALATE": False}, {"UNKNOWN": 2}, {"ASK": 2, "UNKNOWN": 0})
        for counts in invalid:
            with self.subTest(counts=counts):
                with self.assertRaises(ValueError):
                    unified.validate_benchmark_metadata({"first_behavior_counts": counts}, self.cases)


class BenchmarkRunTests(unittest.TestCase):
    def run_kg(self, arguments):
        args = unified.build_parser().parse_args(["--modes", "kg-only", "--no-warmup", *arguments])
        with (
            patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
            patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
            redirect_stdout(io.StringIO()),
        ):
            result = unified.run(args)
        network.assert_not_called()
        return result

    def test_custom_config_selects_two_cases_and_validates_before_limit(self):
        cases = unified.load_cases(DATASET)[:2]
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            dataset = folder / "two_cases.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            config = repository_config()
            benchmark = {
                "benchmark_file": str(dataset), "format": "json",
                "schema_version": DEFAULT_SCHEMA_VERSION,
                "total_cases": 2, "first_behavior_counts": {"ASK": 2},
                "slices": {"custom_group_count": 2},
            }
            config["benchmark"] = deepcopy(benchmark)
            config_path = folder / "config.yaml"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            directory = folder / "reports"
            self.run_kg(["--score-config", str(config_path), "--limit", "1",
                         "--output-dir", str(directory)])
            metadata = json.loads((directory / "run_config.json").read_text(encoding="utf-8"))
            summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in
                    (directory / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(Path(metadata["dataset"]), dataset)
        self.assertEqual(metadata["benchmark"], {
            "selection": "config", "configured": benchmark, "loaded_cases": 2, "evaluated_cases": 1,
        })
        self.assertEqual(summary["run"]["benchmark"], metadata["benchmark"])
        self.assertEqual(metadata["scenario_ids"], [cases[0]["scenario_id"]])
        self.assertEqual(len(rows), 1)
        self.assertEqual(summary["results"]["kg-only"]["n"], 1)

    def test_explicit_temporary_dataset_skips_repository_full_dataset_constraints(self):
        benchmark = repository_config()["benchmark"]
        selected_cases = unified.load_cases(DATASET)[:2]
        self.assertNotEqual(len(selected_cases), benchmark["total_cases"])
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "selected_cases.json"
            dataset.write_text(json.dumps(selected_cases), encoding="utf-8")
            directory = Path(temporary) / "reports"
            self.run_kg(["--score-config", str(CONFIG), "--dataset", str(dataset),
                         "--limit", "1", "--output-dir", str(directory)])
            metadata = json.loads((directory / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(metadata["dataset"]), dataset)
        self.assertEqual(metadata["benchmark"], {
            "selection": "command_line", "configured": benchmark,
            "loaded_cases": len(selected_cases), "evaluated_cases": 1,
        })
        self.assertEqual(metadata["scenario_ids"], [selected_cases[0]["scenario_id"]])


if __name__ == "__main__":
    unittest.main()
