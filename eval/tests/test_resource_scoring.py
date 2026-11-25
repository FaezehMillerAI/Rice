"""Checks for resource score normalization and server measurement boundaries."""

from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import eval.evaluate_unified as unified


class ResourceScoringTests(unittest.TestCase):
    def test_zero_reference_and_double_reference_have_hand_calculated_scores(self):
        budgets = {"latency_s": 10.0, "memory_mib": 8192.0}
        for latency, memory, expected in (
            (0, 0, 1.0),
            (10, 8192, 0.0),
            (20, 16384, 0.0),
        ):
            with self.subTest(latency=latency, memory=memory):
                result = unified.evaluate_resources(latency, memory, budgets)
                self.assertAlmostEqual(result["latency_efficiency"], expected)
                self.assertAlmostEqual(result["memory_efficiency"], expected)
                self.assertAlmostEqual(result["resource_efficiency"], expected)

    def test_combined_score_averages_distinct_latency_and_memory_scores(self):
        budgets = {"latency_s": 10.0, "memory_mib": 8192.0}
        result = unified.evaluate_resources(0, 8192, budgets)
        self.assertEqual(result["latency_efficiency"], 1.0)
        self.assertEqual(result["memory_efficiency"], 0.0)
        self.assertEqual(result["resource_efficiency"], 0.5)

    def test_values_within_the_reference_budget_remain_distinguishable(self):
        budgets = {"latency_s": 10.0, "memory_mib": 8192.0}
        smaller = unified.evaluate_resources(2.5, 2048, budgets)
        larger = unified.evaluate_resources(5, 4096, budgets)
        for metric in ("latency_efficiency", "memory_efficiency", "resource_efficiency"):
            with self.subTest(metric=metric):
                self.assertAlmostEqual(smaller[metric], 0.75)
                self.assertAlmostEqual(larger[metric], 0.5)
                self.assertGreater(smaller[metric], larger[metric])

    def test_lower_latency_or_memory_strictly_improves_through_the_reference_limit(self):
        budgets = {"latency_s": 10.0, "memory_mib": 8192.0}
        latency_results = [unified.evaluate_resources(value, 4096, budgets)
                           for value in (0, 2.5, 5, 7.5, 10)]
        memory_results = [unified.evaluate_resources(5, value, budgets)
                          for value in (0, 2048, 4096, 6144, 8192)]
        for results, changing, fixed in (
            (latency_results, "latency_efficiency", "memory_efficiency"),
            (memory_results, "memory_efficiency", "latency_efficiency"),
        ):
            with self.subTest(changing=changing):
                for smaller, larger in zip(results, results[1:]):
                    self.assertGreater(smaller[changing], larger[changing])
                    self.assertGreater(smaller["resource_efficiency"], larger["resource_efficiency"])
                    self.assertEqual(smaller[fixed], larger[fixed])

    def test_at_or_above_one_reference_zeroes_only_that_component(self):
        budgets = {"latency_s": 10.0, "memory_mib": 8192.0}
        for latency in (10, 20, 1_000_000):
            with self.subTest(latency=latency):
                result = unified.evaluate_resources(latency, 4096, budgets)
                self.assertEqual(result["latency_efficiency"], 0.0)
                self.assertEqual(result["memory_efficiency"], 0.5)
                self.assertEqual(result["resource_efficiency"], 0.25)
        for memory in (8192, 16384, 1_000_000):
            with self.subTest(memory=memory):
                result = unified.evaluate_resources(5, memory, budgets)
                self.assertEqual(result["latency_efficiency"], 0.5)
                self.assertEqual(result["memory_efficiency"], 0.0)
                self.assertEqual(result["resource_efficiency"], 0.25)

    def test_scores_stay_between_zero_and_one_for_nonnegative_measurements(self):
        budgets = {"latency_s": 10.0, "memory_mib": 8192.0}
        for latency in (0, 0.001, 5, 10, 20, 1_000_000):
            for memory in (0, 1, 4096, 8192, 16384, 1_000_000):
                with self.subTest(latency=latency, memory=memory):
                    result = unified.evaluate_resources(latency, memory, budgets)
                    for metric in ("latency_efficiency", "memory_efficiency", "resource_efficiency"):
                        self.assertGreaterEqual(result[metric], 0.0)
                        self.assertLessEqual(result[metric], 1.0)

    def test_missing_memory_or_budget_does_not_receive_a_complete_resource_score(self):
        for latency, memory, budgets in (
            (1, None, {"latency_s": 10, "memory_mib": 8192}),
            (None, 1024, {"latency_s": 10, "memory_mib": 8192}),
            (1, 1024, {"latency_s": None, "memory_mib": 8192}),
            (1, 1024, {"latency_s": 10, "memory_mib": None}),
        ):
            with self.subTest(latency=latency, memory=memory, budgets=budgets):
                self.assertIsNone(unified.evaluate_resources(latency, memory, budgets)["resource_efficiency"])

    def test_invalid_budget_values_are_rejected(self):
        for bad in (False, "10", -1, 0, float("inf"), float("nan")):
            for key in ("latency_s", "memory_mib"):
                with self.subTest(value=bad, key=key):
                    with self.assertRaises(ValueError):
                        unified.validate_resource_budgets({key: bad})
        self.assertEqual(unified.validate_resource_budgets({}), {"latency_s": None, "memory_mib": None})

    def test_custom_budget_file_and_cli_overrides_are_available(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.yaml"
            config.write_text("resource_budgets:\n  latency_s: 3\n  memory_mib: 1024\n", encoding="utf-8")
            self.assertEqual(unified.load_resource_budgets(config), {"latency_s": 3, "memory_mib": 1024})
        args = unified.build_parser().parse_args(["--latency-budget-s", "5", "--memory-budget-mib", "2048"])
        self.assertEqual(args.latency_budget_s, 5)
        self.assertEqual(args.memory_budget_mib, 2048)


class OllamaMemoryTests(unittest.TestCase):
    def setUp(self):
        self.generator = SimpleNamespace(spec={"ollama_model": "predictor:latest"})
        self.args = SimpleNamespace(ollama_url="http://example.invalid", ollama_timeout=120)

    def test_loaded_model_size_is_a_server_snapshot_not_evaluator_rss(self):
        response = {"models": [
            {"name": "other:latest", "size": 200 * 1024**2},
            {"name": "predictor:latest", "size": 2048 * 1024**2, "size_vram": 1024 * 1024**2},
        ]}
        with patch.object(unified, "ollama_json", return_value=response) as request:
            result = unified.measure_ollama_memory(self.generator, self.args)
        self.assertEqual(result["predictor_memory_mib"], 2048)
        self.assertEqual(result["ollama_model_vram_mib"], 1024)
        self.assertIsNone(result["predictor_memory_error"])
        self.assertEqual(result["predictor_memory_scope"], "ollama_server_reported_model_resident_snapshot")
        request.assert_called_once_with(self.args.ollama_url, "/api/ps", timeout=10)

    def test_missing_model_or_failed_probe_is_unavailable(self):
        for reply in ({"models": []}, {"models": [{"name": "predictor:latest", "size": 0}]}):
            with self.subTest(reply=reply), patch.object(unified, "ollama_json", return_value=reply):
                result = unified.measure_ollama_memory(self.generator, self.args)
                self.assertIsNone(result["predictor_memory_mib"])
                self.assertTrue(result["predictor_memory_error"])
        with patch.object(unified, "ollama_json", side_effect=RuntimeError("unavailable")):
            result = unified.measure_ollama_memory(self.generator, self.args)
            self.assertIsNone(result["predictor_memory_mib"])
            self.assertIn("unavailable", result["predictor_memory_error"])


if __name__ == "__main__":
    unittest.main()
