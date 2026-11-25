"""Deterministic integration checks for the predictor resource window.

The clock advances only at named operations; no real model, HTTP or sampler
thread is used. Parsing, scoring and collector shutdown have deliberately large
costs so including them in predictor latency cannot pass unnoticed.
"""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import eval.evaluate_unified as unified


ROOT = Path(__file__).resolve().parents[2]


class ManualClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeRSSMonitor:
    def __init__(self, clock, windows):
        self.clock, self.windows = clock, windows
        self.events = []
        self.stopped = False

    def start(self):
        self.windows.append(self)
        self.events.append("rss.start")
        self.clock.advance(19)  # Monitor startup precedes the predictor timer.
        return self

    def stop(self):
        self.events.append("rss.stop")
        self.clock.advance(17)
        self.stopped = True
        return {
            "process_peak_rss_mib": 128.0,
            "memory_measurement_scope": "evaluator_process_tree",
            "memory_sample_count": 2,
            "memory_measurement_error": None,
        }


def generated(prediction):
    return {
        "raw_output": json.dumps(prediction), "prompt_tokens": 32,
        "generated_tokens": 20, "cuda_peak_allocated_mib": None,
        "output_budget_exhausted": False,
    }


def read_reports(directory):
    rows = [json.loads(line) for line in
            (directory / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    return rows, summary


class ResourceWindowTests(unittest.TestCase):
    def test_three_modes_time_prediction_work_and_retain_failed_cases(self):
        cases = unified.load_cases(ROOT / "data/eval/gold_eval_v0.3.json")[:2]
        prediction = deepcopy(cases[0]["target_response"])
        clock, windows = ManualClock(), []
        adapter = unified.KGAdapter()
        original_select = unified.select_public_case
        original_diagnose, original_retrieve = adapter.diagnose, adapter.retrieve
        original_prompt = unified.build_prompt
        original_parse, original_evaluate = unified.parse_response, unified.evaluate_prediction

        def select(case):
            # Dataset validation also selects fields before any predictor window.
            if windows and not windows[-1].stopped:
                windows[-1].events.append("public")
                clock.advance(2)
            return original_select(case)

        def diagnose(public, *args, **kwargs):
            windows[-1].events.append("diagnose")
            clock.advance(3)
            if public["input"]["user_text"] == cases[1]["input"]["user_text"]:
                raise RuntimeError("Controlled KG failure")
            return original_diagnose(public, *args, **kwargs)

        def retrieve(*args, **kwargs):
            windows[-1].events.append("retrieve")
            clock.advance(3)
            return original_retrieve(*args, **kwargs)

        def prompt(*args, **kwargs):
            windows[-1].events.append("prompt")
            clock.advance(5)
            return original_prompt(*args, **kwargs)

        def generate(messages, *, max_new_tokens=None):
            windows[-1].events.append("generate")
            clock.advance(7)
            if len(windows) % 2 == 0:
                raise RuntimeError("Controlled model failure")
            return generated(prediction)

        def parse(raw):
            self.assertTrue(windows[-1].stopped)
            windows[-1].events.append("parse")
            clock.advance(11)
            return original_parse(raw)

        def evaluate(*args, **kwargs):
            self.assertTrue(windows[-1].stopped)
            windows[-1].events.append("score")
            clock.advance(13)
            return original_evaluate(*args, **kwargs)

        generator = SimpleNamespace(
            device="cpu", context_limit=8192,
            model=SimpleNamespace(config=SimpleNamespace(_commit_hash="fake-window-model")),
            generate=Mock(side_effect=generate),
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "reports"
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", *unified.MODES,
                "--backend", "transformers", "--model", "qwen2.5-1.5b", "--device", "cpu", "--no-warmup",
                "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "perf_counter", side_effect=clock),
                patch.object(unified, "ResourceMonitor", side_effect=lambda: FakeRSSMonitor(clock, windows)),
                patch.object(unified, "KGAdapter", return_value=adapter),
                patch.object(adapter, "diagnose", side_effect=diagnose),
                patch.object(adapter, "retrieve", side_effect=retrieve),
                patch.object(unified, "select_public_case", side_effect=select),
                patch.object(unified, "build_prompt", side_effect=prompt),
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "parse_response", side_effect=parse),
                patch.object(unified, "evaluate_prediction", side_effect=evaluate),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected HTTP")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, summary = read_reports(directory)

        network.assert_not_called()
        self.assertEqual(len(rows), 6)
        self.assertEqual(generator.generate.call_count, 4)
        expected_latency = {"kg-only": 5.0, "model-only": 14.0, "kg+model": 17.0}
        work = {
            "kg-only": ["diagnose"], "model-only": ["prompt", "generate"],
            "kg+model": ["retrieve", "prompt", "generate"],
        }
        for row, window in zip(rows, windows):
            failed = row["scenario_id"] == cases[1]["scenario_id"]
            with self.subTest(mode=row["mode"], failed=failed):
                self.assertEqual(row["metrics"]["latency_s"], expected_latency[row["mode"]])
                self.assertEqual(row["resource_measurement"]["prediction_window_s"], expected_latency[row["mode"]])
                self.assertEqual(row["resource_measurement_s"], 17.0)
                self.assertEqual(row["parsing_s"], 0.0 if failed else 11.0)
                self.assertEqual(row["metrics"]["parsing_s"], row["parsing_s"])
                self.assertEqual(row["evaluation_s"], 13.0)
                self.assertEqual(row["metrics"]["predictor_memory_mib"], 128.0)
                self.assertEqual(window.events, [
                    "rss.start", "public", *work[row["mode"]], "rss.stop",
                    *([] if failed else ["parse"]), "score",
                ])
                self.assertEqual(row["resource_measurement"]["raw_output_produced"], not failed)
                if failed:
                    self.assertFalse(row["metrics"]["schema_compliance"])
                    self.assertEqual(row["metrics"]["final_score"], 0.0)
                    self.assertEqual(row["error"]["type"], "RuntimeError")
        for mode in unified.MODES:
            result = summary["results"][mode]
            self.assertEqual(result["n"], 2)
            self.assertEqual(result["inference_errors"], 1)
            self.assertEqual(result["metrics"]["schema_compliance"], {"value": 0.5, "applicable_n": 2})
            self.assertEqual(result["metrics"]["final_score"]["applicable_n"], 2)

    def test_ollama_freezes_before_shutdown_and_adds_residency_to_local_rss(self):
        case = unified.load_cases(ROOT / "data/eval/gold_eval_v0.3.json")[0]
        clock, windows, server_monitors = ManualClock(), [], []
        original_parse = unified.parse_response

        class FakeServerMonitor:
            def __init__(self, probe):
                self.frozen = self.stopped = False
                server_monitors.append(self)

            def start(self):
                windows[-1].events.append("server.start")
                return self

            def freeze(self):
                windows[-1].events.append("server.freeze")
                clock.advance(19)
                self.frozen = True

            def stop(self):
                if not self.frozen or not windows[-1].stopped:
                    raise AssertionError("Server must freeze before RSS shutdown, then stop")
                windows[-1].events.append("server.stop")
                clock.advance(23)
                self.stopped = True
                return {
                    "ollama_model_resident_mib": 1000.0, "ollama_model_vram_mib": 400.0,
                    "predictor_memory_error": None, "ollama_memory_sample_count": 2,
                }

        def generate(messages, *, max_new_tokens=None):
            windows[-1].events.append("generate")
            clock.advance(7)
            return generated(case["target_response"])

        def parse(raw):
            self.assertTrue(server_monitors[-1].stopped)
            windows[-1].events.append("parse")
            clock.advance(11)
            return original_parse(raw)

        spec = {"ollama_model": "window-test:latest", "variant": "server-managed", "adapter": None}
        generator = SimpleNamespace(
            spec=spec, device="ollama-server", context_limit=8192,
            runtime_metadata={}, generate=Mock(side_effect=generate),
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "reports"
            dataset = Path(temporary) / "cases.json"
            dataset.write_text(json.dumps([case]), encoding="utf-8")
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--backend", "ollama",
                "--model", "window-test:latest", "--no-warmup", "--output-dir", str(directory),
            ])
            with (
                patch.object(unified, "perf_counter", side_effect=clock),
                patch.object(unified, "ResourceMonitor", side_effect=lambda: FakeRSSMonitor(clock, windows)),
                patch.object(unified, "OllamaMemoryMonitor", FakeServerMonitor),
                patch.object(unified, "resolve_ollama_spec", return_value=spec),
                patch.object(unified, "OllamaGenerator", return_value=generator),
                patch.object(unified, "parse_response", side_effect=parse),
                patch.object(unified, "measure_ollama_memory", side_effect=AssertionError("No post-output probe")) as probe,
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected HTTP")) as network,
                redirect_stdout(io.StringIO()),
            ):
                unified.run(args)
            rows, _ = read_reports(directory)

        network.assert_not_called()
        probe.assert_not_called()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["metrics"]["latency_s"], 7.0)
        self.assertEqual(row["parsing_s"], 11.0)
        self.assertEqual(row["resource_measurement_s"], 59.0)
        self.assertEqual(row["metrics"]["process_peak_rss_mib"], 128.0)
        self.assertEqual(row["metrics"]["ollama_model_resident_mib"], 1000.0)
        self.assertEqual(row["metrics"]["predictor_memory_mib"], 1128.0)
        self.assertEqual(windows[0].events, [
            "rss.start", "server.start", "generate", "server.freeze", "rss.stop", "server.stop", "parse",
        ])


if __name__ == "__main__":
    unittest.main()
