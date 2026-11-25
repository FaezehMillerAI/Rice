"""Outer-fence normalization preserves raw-schema scoring and resource scope."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import eval.evaluate_unified as unified
from eval.tests.test_resource_window import FakeRSSMonitor, ManualClock
from eval.tests.test_v03_evaluation import fake_generator, fake_resource_monitor, generated, reports
from eval.tests.test_weighted_scoring import perfect_metrics


ROOT = Path(__file__).resolve().parents[2]
METHOD = "strip_outer_markdown_json_fence"


def run_model_outputs(outputs, *, modes=("model-only",), clock=None,
                      monitor_factory=fake_resource_monitor, on_generate=None):
    """Use the real evaluator with local cases, a fake HF model and no HTTP."""
    first = unified.load_cases(ROOT / "data/eval/gold_eval_v0.3.json")[0]
    cases = []
    for index in range(len(outputs)):
        case = deepcopy(first)
        case["scenario_id"] = case["family_id"] = f"NORMALIZATION-{index:03d}"
        cases.append(case)
    responses = iter(list(outputs) * len(modes))

    def generate(messages, **kwargs):
        if on_generate is not None:
            on_generate()
        output = next(responses)
        if isinstance(output, Exception):
            raise output
        return deepcopy(output) if isinstance(output, dict) else generated(output)

    generator = fake_generator(generate)
    with tempfile.TemporaryDirectory() as temporary:
        dataset = Path(temporary) / "cases.json"
        dataset.write_text(json.dumps(cases), encoding="utf-8")
        directory = Path(temporary) / "reports"
        args = unified.build_parser().parse_args([
            "--dataset", str(dataset), "--modes", *modes,
            "--backend", "transformers", "--model", "qwen2.5-1.5b", "--device", "cpu",
            "--no-warmup", "--output-dir", str(directory),
        ])
        terminal = io.StringIO()
        with (
            patch.object(unified, "HFGenerator", return_value=generator),
            patch.object(unified, "ResourceMonitor", side_effect=monitor_factory),
            patch.object(unified, "perf_counter", side_effect=clock or (lambda: 0.0)),
            patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
            redirect_stdout(terminal),
        ):
            unified.run(args)
        rows, summary = reports(directory)
        user_outputs = [json.loads(line) for line in
                        (directory / "user_outputs.jsonl").read_text(encoding="utf-8").splitlines()]
    network.assert_not_called()
    return rows, summary, user_outputs, terminal.getvalue()


class PredictionNormalizationTests(unittest.TestCase):
    def test_only_complete_json_or_unlabelled_fences_are_removed(self):
        body = '{"example": "literal ``` inside a JSON string"}'
        for raw in (
            f"```json\n{body}\n```",
            f"```JSON\r\n{body}\r\n```",
            f"```\n{body}\n```",
            f" \n```JsOn\n{body}\n```\n ",
        ):
            with self.subTest(raw=raw):
                prepared, trace = unified.prepare_prediction_input(raw)
                self.assertEqual(prepared, body)
                self.assertEqual(trace, {"method": METHOD, "applied": True})
                self.assertEqual(unified.parse_response(prepared), (json.loads(body), []))
                # Strict parsing of the original model output remains unchanged.
                strict_prediction, errors = unified.parse_response(raw)
                self.assertIsNone(strict_prediction)
                self.assertTrue(errors)
        plain = " \n" + body + "\n "
        prepared, trace = unified.prepare_prediction_input(plain)
        self.assertEqual(prepared, plain)
        self.assertEqual(trace, {"method": METHOD, "applied": False})

    def test_prefix_suffix_wrong_labels_and_incomplete_fences_are_not_repaired(self):
        for raw in (
            'Here is the result:\n```json\n{}\n```',
            '```json\n{}\n```\nAdditional explanation.',
            '```python\n{}\n```',
            '```json\n[]\n```',
            '```json\n{}',
            '{}\n```',
            '```json\nnot JSON\n```',
        ):
            with self.subTest(raw=raw):
                prepared, trace = unified.prepare_prediction_input(raw)
                self.assertEqual(prepared, raw)
                self.assertEqual(trace, {"method": METHOD, "applied": False})
                self.assertIsNone(unified.parse_response(prepared)[0])

    def test_fenced_predictions_score_content_in_both_model_modes_and_keep_raw_output(self):
        prediction = deepcopy(unified.load_cases(ROOT / "data/eval/gold_eval_v0.3.json")[0]["target_response"])
        plain = json.dumps(prediction)
        fenced = f"```json\n{plain}\n```"
        rows, summary, user_outputs, _ = run_model_outputs(
            [plain, fenced], modes=("model-only", "kg+model"),
        )
        self.assertEqual(len(rows), 4)
        for mode in ("model-only", "kg+model"):
            ordinary, normalized = [row for row in rows if row["mode"] == mode]
            with self.subTest(mode=mode):
                self.assertEqual(ordinary["raw_output"], plain)
                self.assertEqual(ordinary["prediction_input"], plain)
                self.assertEqual(ordinary["output_normalization"], {"method": METHOD, "applied": False})
                self.assertTrue(ordinary["metrics"]["parse_valid"])
                self.assertTrue(ordinary["metrics"]["prediction_parse_valid"])
                self.assertTrue(ordinary["metrics"]["schema_compliance"])
                self.assertTrue(ordinary["prediction_valid"])
                self.assertEqual(ordinary["final_output_status"], "ready")

                self.assertEqual(normalized["raw_output"], fenced)
                self.assertEqual(normalized["prediction_input"], plain)
                self.assertEqual(normalized["output_normalization"], {"method": METHOD, "applied": True})
                self.assertEqual(normalized["prediction"], prediction)
                self.assertFalse(normalized["metrics"]["parse_valid"])
                self.assertTrue(normalized["metrics"]["prediction_parse_valid"])
                self.assertTrue(normalized["prediction_valid"])
                self.assertEqual(normalized["prediction_errors"], [])
                self.assertFalse(normalized["metrics"]["schema_compliance"])
                self.assertTrue(normalized["metrics"]["schema_errors"])
                self.assertFalse(normalized["score_breakdown"]["schema_gate_passed"])
                self.assertTrue(normalized["score_breakdown"]["prediction_gate_passed"])
                self.assertEqual(normalized["metrics"]["first_behavior"], "ASK")
                self.assertEqual(normalized["final_user_output"], prediction["user_response"])
                self.assertEqual(normalized["final_output_status"], "schema_invalid")
                self.assertEqual(set(normalized["raw_score_metrics"]), set(ordinary["raw_score_metrics"]))
                for metric in ordinary["raw_score_metrics"]:
                    if metric != "schema_compliance":
                        self.assertEqual(normalized["raw_score_metrics"][metric],
                                         ordinary["raw_score_metrics"][metric], metric)
                for metric in ("behavior_correctness", "differential_f1", "question_agreement",
                               "groundedness", "evidence_agreement", "actions_agreement",
                               "response_safety_check"):
                    self.assertEqual(normalized["raw_score_metrics"][metric], 1.0, metric)
                self.assertAlmostEqual(ordinary["metrics"]["final_score"] - normalized["metrics"]["final_score"], 5.0)
                self.assertGreater(normalized["metrics"]["final_score"], 80.0)
                self.assertEqual(summary["results"][mode]["behavior_confusion"]["ASK"], {"ASK": 2})
        for row, exported in zip(rows, user_outputs):
            self.assertEqual(exported["user_response"], prediction["user_response"])
            self.assertEqual(exported["status"], row["final_output_status"])
            self.assertEqual(exported["schema_compliance"], row["metrics"]["schema_compliance"])

    def test_malformed_duplicate_missing_fields_and_backend_failures_still_score_zero(self):
        prediction = deepcopy(unified.load_cases(ROOT / "data/eval/gold_eval_v0.3.json")[0]["target_response"])
        plain = json.dumps(prediction)
        duplicate = '{"status": "provisional_assessment", ' + plain[1:]
        missing = deepcopy(prediction)
        del missing["actions"]
        outputs = [
            f"```json\n{plain[:-1]},}}\n```",  # Trailing comma is not repaired.
            f"```json\n{duplicate}\n```",  # Duplicate keys are not collapsed.
            f"```\n{json.dumps(missing)}\n```",  # Required keys are not supplied.
            {**generated(f"```json\n{plain}\n```"), "backend_errors": ["Context limit exceeded"]},
            RuntimeError("Controlled inference failure"),
        ]
        rows, _, _, _ = run_model_outputs(outputs)
        self.assertEqual(len(rows), 5)
        for index, row in enumerate(rows):
            with self.subTest(index=index):
                self.assertFalse(row["prediction_valid"])
                self.assertTrue(row["prediction_errors"])
                self.assertFalse(row["metrics"]["schema_compliance"])
                self.assertEqual(row["metrics"]["first_behavior"], "INVALID")
                self.assertEqual(row["metrics"]["final_score"], 0.0)
                self.assertFalse(row["score_breakdown"]["prediction_gate_passed"])
                self.assertTrue(all(item["contribution"] == 0.0
                                    for item in row["score_breakdown"]["components"].values()))
        self.assertIsNone(rows[0]["prediction"])
        self.assertIsNone(rows[1]["prediction"])
        self.assertEqual(rows[2]["prediction"], missing)
        self.assertNotIn("actions", rows[2]["prediction"])
        self.assertTrue(rows[2]["metrics"]["prediction_parse_valid"])
        self.assertEqual(rows[0]["raw_output"], outputs[0])
        self.assertEqual(rows[1]["raw_output"], outputs[1])
        self.assertTrue(rows[3]["error"])
        self.assertTrue(rows[4]["error"])

    def test_cleanup_runs_after_the_resource_window_and_collector_stop(self):
        prediction = unified.load_cases(ROOT / "data/eval/gold_eval_v0.3.json")[0]["target_response"]
        raw = f"```json\n{json.dumps(prediction)}\n```"
        clock, windows = ManualClock(), []
        original = unified.prepare_prediction_input

        def generate_work():
            self.assertFalse(windows[-1].stopped)
            clock.advance(7)

        def cleanup(text):
            self.assertTrue(windows[-1].stopped)
            clock.advance(11)
            return original(text)

        with patch.object(unified, "prepare_prediction_input", side_effect=cleanup) as normalize:
            rows, _, _, _ = run_model_outputs(
                [raw], clock=clock, monitor_factory=lambda: FakeRSSMonitor(clock, windows),
                on_generate=generate_work,
            )
        normalize.assert_called_once_with(raw)
        self.assertEqual(rows[0]["metrics"]["latency_s"], 7.0)
        self.assertEqual(rows[0]["resource_measurement"]["prediction_window_s"], 7.0)
        self.assertEqual(rows[0]["resource_measurement_s"], 17.0)
        self.assertEqual(rows[0]["parsing_s"], 11.0)

    def test_prediction_gate_keeps_legacy_schema_gate_when_not_explicitly_supplied(self):
        metrics = perfect_metrics(schema_compliance=False)
        weights = {"behavior_correctness": 0.95, "schema_compliance": 0.05}
        legacy = unified.compute_weighted_score(metrics, weights)
        usable = unified.compute_weighted_score(metrics, weights, prediction_valid=True)
        unusable = unified.compute_weighted_score(perfect_metrics(), weights, prediction_valid=False)
        self.assertEqual(legacy["score"], 0.0)
        self.assertFalse(legacy["prediction_gate_passed"])
        self.assertEqual(usable["score"], 95.0)
        self.assertFalse(usable["schema_gate_passed"])
        self.assertTrue(usable["prediction_gate_passed"])
        self.assertEqual(usable["components"]["behavior_correctness"]["contribution"], 95.0)
        self.assertEqual(usable["components"]["schema_compliance"]["contribution"], 0.0)
        self.assertEqual(unusable["score"], 0.0)
        self.assertTrue(unusable["schema_gate_passed"])
        self.assertFalse(unusable["prediction_gate_passed"])


if __name__ == "__main__":
    unittest.main()
