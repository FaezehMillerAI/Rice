"""Final user responses are displayed verbatim without changing evaluation."""

from contextlib import redirect_stdout
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import eval.evaluate_unified as unified


OUTPUT_FIELDS = {"final_user_output", "final_output_source", "final_output_status"}


def example_row(**changes):
    row = {
        "scenario_id": "case-output-001", "family_id": "family-output-001", "mode": "model-only",
        "prediction": {"user_response": "Final response."}, "raw_output": "RAW_OUTPUT_SENTINEL",
        "metrics": {"schema_compliance": True, "final_score": 42.0}, "error": None,
        "gold": {"user_response": "GOLD_ONLY_SENTINEL"},
        "target_response": {"user_response": "TARGET_ONLY_SENTINEL"},
    }
    row.update(changes)
    return row


def fake_resource_monitor():
    monitor = Mock()
    monitor.start.return_value = monitor
    monitor.stop.return_value = {
        "process_peak_rss_mib": 128.0, "memory_measurement_scope": "evaluator_process_tree",
        "memory_sample_count": 1, "memory_measurement_error": None,
    }
    return monitor


def fake_generator(*raw_outputs):
    return SimpleNamespace(
        device="cpu", context_limit=8192,
        model=SimpleNamespace(config=SimpleNamespace(_commit_hash="unit-test")),
        generate=Mock(side_effect=[
            {
                "raw_output": raw, "prompt_tokens": 32, "generated_tokens": 20,
                "cuda_peak_allocated_mib": None, "output_budget_exhausted": False,
            }
            for raw in raw_outputs
        ]),
    )


class FinalUserOutputTests(unittest.TestCase):
    def finalize_unchanged(self, row):
        original = deepcopy(row)
        self.assertIsNone(unified.finalize_user_output(row))
        self.assertEqual({key: value for key, value in row.items() if key not in OUTPUT_FIELDS}, original)
        return row

    def test_structured_response_is_verbatim_and_source_follows_mode(self):
        text = " \n  Please inspect the lesion margins.\t "
        for mode in unified.MODES:
            with self.subTest(mode=mode):
                row = self.finalize_unchanged(example_row(mode=mode, prediction={"user_response": text}))
                self.assertEqual(row["final_user_output"], text)
                self.assertEqual(row["final_output_status"], "ready")
                self.assertEqual(row["final_output_source"],
                                 "kg_template" if mode == "kg-only" else "model_generated")
                self.assertEqual(row["metrics"]["final_score"], 42.0)
                self.assertTrue(OUTPUT_FIELDS.isdisjoint(row["metrics"]))

    def test_structured_text_remains_visible_with_schema_or_inference_failure(self):
        failure = {"type": "GenerationError", "message": "failure sentinel"}
        for valid, error, status in ((False, None, "schema_invalid"),
                                     (True, failure, "inference_error"),
                                     (False, failure, "inference_error")):
            with self.subTest(valid=valid, error=error):
                row = self.finalize_unchanged(example_row(
                    metrics={"schema_compliance": valid, "final_score": 0.0}, error=error))
                self.assertEqual(row["final_user_output"], "Final response.")
                self.assertEqual(row["final_output_status"], status)

    def test_unparsed_model_raw_text_is_preserved_without_parsing_or_repair(self):
        text = ' \n{"user_response": "unfinished raw text"\t '
        for mode in ("model-only", "kg+model"):
            for error in (None, {"type": "ContextLimitError", "message": "limit"}):
                with self.subTest(mode=mode, error=error):
                    row = self.finalize_unchanged(example_row(
                        mode=mode, prediction=None, raw_output=text, error=error,
                        metrics={"schema_compliance": False, "final_score": 0.0}))
                    self.assertEqual(row["final_user_output"], text)
                    self.assertEqual(row["final_output_source"], "model_generated")
                    self.assertEqual(row["final_output_status"], "inference_error" if error else "raw_output")
                    self.assertIsNone(row["prediction"])

    def test_parsed_missing_or_blank_response_never_falls_back_to_raw_or_gold(self):
        for prediction in ({}, {"user_response": ""}, {"user_response": " \n\t"},
                           {"user_response": None}, {"user_response": 123}):
            with self.subTest(prediction=prediction):
                row = self.finalize_unchanged(example_row(prediction=prediction))
                self.assertIsNone(row["final_user_output"])
                self.assertEqual(row["final_output_status"], "missing_user_response")
        row = self.finalize_unchanged(example_row(prediction={}, error={"type": "Failure"}))
        self.assertIsNone(row["final_user_output"])
        self.assertEqual(row["final_output_status"], "inference_error")

    def test_no_output_and_kg_raw_output_do_not_expose_gold_or_target(self):
        for mode, raw in (("kg-only", "KG_RAW_JSON_SENTINEL"), ("model-only", None),
                          ("kg+model", ""), ("model-only", 123)):
            for error in (None, {"type": "Failure"}):
                with self.subTest(mode=mode, raw=raw, error=error):
                    row = self.finalize_unchanged(example_row(
                        mode=mode, prediction=None, raw_output=raw, error=error))
                    self.assertIsNone(row["final_user_output"])
                    self.assertEqual(row["final_output_status"], "inference_error" if error else "no_output")

    def test_print_includes_identity_source_status_and_text_without_mutation(self):
        for prediction in ({"user_response": "PRINT_FINAL_SENTINEL"}, {}):
            with self.subTest(prediction=prediction):
                row = self.finalize_unchanged(example_row(prediction=prediction))
                original = deepcopy(row)
                output = io.StringIO()
                with redirect_stdout(output):
                    unified.print_final_user_output(row)
                printed = output.getvalue()
                for value in ("[Final user output]", row["mode"], row["scenario_id"],
                              row["final_output_source"], row["final_output_status"]):
                    self.assertIn(value, printed)
                self.assertIn(row["final_user_output"] or "<no user response>", printed)
                self.assertNotIn("GOLD_ONLY_SENTINEL", printed)
                self.assertNotIn("TARGET_ONLY_SENTINEL", printed)
                self.assertEqual(row, original)


class FinalUserOutputRunTests(unittest.TestCase):
    def read_reports(self, directory):
        predictions = [json.loads(line) for line in
                       (directory / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
        user_outputs = [json.loads(line) for line in
                        (directory / "user_outputs.jsonl").read_text(encoding="utf-8").splitlines()]
        with (directory / "case_metrics.csv").open(encoding="utf-8-sig", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        return predictions, user_outputs, csv_rows

    def assert_reports_align(self, predictions, user_outputs, csv_rows):
        self.assertEqual(len(predictions), len(user_outputs))
        self.assertEqual(len(predictions), len(csv_rows))
        for row, output, csv_row in zip(predictions, user_outputs, csv_rows):
            self.assertEqual(output, {
                "scenario_id": row["scenario_id"], "family_id": row["family_id"], "mode": row["mode"],
                "source": row["final_output_source"], "status": row["final_output_status"],
                "user_response": row["final_user_output"], "schema_compliance": row["metrics"]["schema_compliance"],
                "error": row["error"],
            })
            for field in OUTPUT_FIELDS:
                self.assertEqual(csv_row[field], row[field] or "")
            self.assertTrue(OUTPUT_FIELDS.isdisjoint(row["metrics"]))

    def test_real_kg_case_writes_aligned_outputs_and_prints_without_show_steps(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--modes", "kg-only", "--limit", "1", "--no-warmup", "--output-dir", str(directory),
            ])
            self.assertFalse(args.show_steps)
            printed = io.StringIO()
            with (
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(printed),
            ):
                unified.run(args)
            predictions, user_outputs, csv_rows = self.read_reports(directory)
        network.assert_not_called()
        self.assertEqual(len(predictions), 1)
        self.assert_reports_align(predictions, user_outputs, csv_rows)
        row = predictions[0]
        self.assertEqual(row["final_output_source"], "kg_template")
        self.assertEqual(row["final_output_status"], "ready")
        self.assertEqual(row["final_user_output"], row["prediction"]["user_response"])
        self.assertIn("[Final user output]", printed.getvalue())
        self.assertIn(row["final_user_output"], printed.getvalue())

    def test_blank_model_response_is_contract_invalid_and_receives_no_credit(self):
        dataset = unified.ROOT / "data/eval/gold_eval_v0.3.json"
        cases = unified.load_cases(dataset)[:2]
        expected = [
            {**case["target_response"], "user_response": text}
            for case, text in zip(cases, ("", " \n\t"))
        ]
        generator = fake_generator(*(json.dumps(prediction) for prediction in expected))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--dataset", str(dataset), "--modes", "model-only", "--model", "qwen2.5-1.5b", "--device", "cpu",
                "--limit", "2", "--no-warmup", "--output-dir", str(directory),
            ])
            printed = io.StringIO()
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(printed),
            ):
                unified.run(args)
            predictions, user_outputs, csv_rows = self.read_reports(directory)

        network.assert_not_called()
        self.assertEqual(generator.generate.call_count, 2)
        self.assertEqual(len(predictions), 2)
        self.assert_reports_align(predictions, user_outputs, csv_rows)
        for row, prediction, csv_row in zip(predictions, expected, csv_rows):
            with self.subTest(scenario=row["scenario_id"]):
                self.assertEqual(row["prediction"], prediction)
                self.assertFalse(row["metrics"]["schema_compliance"])
                self.assertFalse(row["prediction_valid"])
                self.assertIn(
                    "user_response must be a nonempty string",
                    row["prediction_errors"],
                )
                self.assertEqual(row["final_output_status"], "missing_user_response")
                self.assertIsNone(row["final_user_output"])
                self.assertFalse(row["metrics"]["behavior_correctness"])
                behavior = row["score_breakdown"]["components"]["behavior_correctness"]
                self.assertEqual(behavior["contribution"], 0)
                self.assertEqual(row["metrics"]["final_score"], 0)
        self.assertEqual(printed.getvalue().count("<no user response>"), 2)

    def test_invalid_model_schema_displays_original_response_but_still_scores_zero(self):
        text = " \nVISIBLE_MODEL_RESPONSE_SENTINEL\t "
        prediction = {"user_response": text}
        raw = json.dumps(prediction)
        generator = fake_generator(raw)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--modes", "model-only", "--backend", "transformers", "--model", "qwen2.5-1.5b", "--device", "cpu",
                "--limit", "1", "--no-warmup", "--output-dir", str(directory),
            ])
            printed = io.StringIO()
            with (
                patch.object(unified, "HFGenerator", return_value=generator),
                patch.object(unified, "ResourceMonitor", side_effect=fake_resource_monitor),
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(printed),
            ):
                unified.run(args)
            predictions, user_outputs, csv_rows = self.read_reports(directory)
            summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        network.assert_not_called()
        generator.generate.assert_called_once()
        self.assert_reports_align(predictions, user_outputs, csv_rows)
        row = predictions[0]
        self.assertEqual(row["prediction"], prediction)
        self.assertEqual(row["raw_output"], raw)
        self.assertEqual(row["final_user_output"], text)
        self.assertEqual(row["final_output_source"], "model_generated")
        self.assertEqual(row["final_output_status"], "schema_invalid")
        self.assertFalse(row["metrics"]["schema_compliance"])
        self.assertEqual(row["score_breakdown"]["components"]["schema_compliance"]["state"], "scored")
        self.assertEqual(row["metrics"]["final_score"], 0.0)
        self.assertTrue(all(item["contribution"] == 0.0 for item in row["score_breakdown"]["components"].values()))
        self.assertEqual(summary["results"]["model-only"]["final_score"], 0.0)
        self.assertIn(text, printed.getvalue())


if __name__ == "__main__":
    unittest.main()
