"""Hand-calculable per-class behavior diagnostics and report exports."""

from contextlib import redirect_stdout
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import eval.evaluate_unified as unified
from eval.tests.test_weighted_scoring import perfect_metrics, scored_record


ROOT = Path(__file__).resolve().parents[2]
CLASSES = ("ASK", "ANSWER", "ESCALATE")
CLASS_FIELDS = {"precision", "recall", "f1", "support", "predicted_n", "tp", "fp", "fn"}


def behavior_record(gold, predicted, *, mode="model-only", scenario_id="case"):
    row = scored_record(
        mode, scenario_id,
        perfect_metrics(
            first_behavior=predicted,
            behavior_correctness=gold == predicted,
            schema_compliance=predicted != "INVALID",
        ),
    )
    row["gold"]["correct_first_behavior"] = gold
    return row


def crossed_records():
    # Gold supports: 4 ASK, 3 ANSWER, 3 ESCALATE. Two outputs are INVALID.
    pairs = [
        ("ASK", "ASK"), ("ASK", "ASK"),
        ("ASK", "ANSWER"), ("ASK", "INVALID"),
        ("ANSWER", "ASK"), ("ANSWER", "ANSWER"), ("ANSWER", "ESCALATE"),
        ("ESCALATE", "ASK"), ("ESCALATE", "ESCALATE"), ("ESCALATE", "INVALID"),
    ]
    return [behavior_record(gold, predicted, scenario_id=f"case-{index}")
            for index, (gold, predicted) in enumerate(pairs)]


class BehaviorPerformanceTests(unittest.TestCase):
    def assert_class(self, actual, *, precision, recall, f1, support, predicted_n, tp, fp, fn):
        self.assertEqual(set(actual), CLASS_FIELDS)
        self.assertEqual(
            {key: actual[key] for key in ("support", "predicted_n", "tp", "fp", "fn")},
            {"support": support, "predicted_n": predicted_n, "tp": tp, "fp": fp, "fn": fn},
        )
        for key, expected in (("precision", precision), ("recall", recall), ("f1", f1)):
            if expected is None:
                self.assertIsNone(actual[key], key)
            else:
                self.assertAlmostEqual(actual[key], expected, msg=key)

    def test_cross_class_errors_and_invalid_predictions_have_expected_counts(self):
        rows = crossed_records()
        before = deepcopy(rows)
        result = unified.summarize(rows)["model-only"]
        classes = result["behavior_per_class"]
        self.assertEqual(tuple(classes), CLASSES)
        self.assert_class(classes["ASK"], precision=0.5, recall=0.5, f1=0.5,
                          support=4, predicted_n=4, tp=2, fp=2, fn=2)
        self.assert_class(classes["ANSWER"], precision=0.5, recall=1 / 3, f1=0.4,
                          support=3, predicted_n=2, tp=1, fp=1, fn=2)
        self.assert_class(classes["ESCALATE"], precision=0.5, recall=1 / 3, f1=0.4,
                          support=3, predicted_n=2, tp=1, fp=1, fn=2)

        self.assertEqual(result["behavior_confusion"], {
            "ASK": {"ASK": 2, "ANSWER": 1, "INVALID": 1},
            "ANSWER": {"ASK": 1, "ANSWER": 1, "ESCALATE": 1},
            "ESCALATE": {"ASK": 1, "ESCALATE": 1, "INVALID": 1},
        })
        self.assertEqual(result["behavior_recall"], {
            "ASK": {"value": 0.5, "applicable_n": 4},
            "ANSWER": {"value": 1 / 3, "applicable_n": 3},
            "ESCALATE": {"value": 1 / 3, "applicable_n": 3},
        })
        # Four correct cases at 100, four wrong valid cases at 75, two invalid at 0.
        self.assertAlmostEqual(result["final_score"], 70.0)
        self.assertAlmostEqual(result["metrics"]["behavior_correctness"]["value"], 0.4)
        counts = result["score_breakdown"]["behavior_correctness"]
        self.assertEqual((counts["scored_n"], counts["failed_n"], counts["passed_n"]), (10, 0, 4))
        self.assertAlmostEqual(sum(item["mean_contribution_points"]
                                   for item in result["score_breakdown"].values()), 70.0)
        for key in ("metrics", "score_breakdown", "category_scores"):
            self.assertNotIn("behavior_per_class", result[key])
            for behavior in CLASSES:
                self.assertNotIn(behavior, result[key])
        self.assertEqual(rows, before)

    def test_missing_gold_and_predicted_classes_distinguish_zero_from_unassessed(self):
        classes = unified.summarize([behavior_record("ASK", "ANSWER")])["model-only"]["behavior_per_class"]
        self.assertEqual(tuple(classes), CLASSES)
        # A class present only in gold has undefined precision, but recall/F1 zero.
        self.assert_class(classes["ASK"], precision=None, recall=0.0, f1=0.0,
                          support=1, predicted_n=0, tp=0, fp=0, fn=1)
        # A class present only in predictions has undefined recall, but precision/F1 zero.
        self.assert_class(classes["ANSWER"], precision=0.0, recall=None, f1=0.0,
                          support=0, predicted_n=1, tp=0, fp=1, fn=0)
        self.assert_class(classes["ESCALATE"], precision=None, recall=None, f1=None,
                          support=0, predicted_n=0, tp=0, fp=0, fn=0)

    def test_all_invalid_outputs_are_false_negatives_without_a_fourth_class(self):
        rows = [behavior_record(behavior, "INVALID", scenario_id=behavior) for behavior in CLASSES]
        rows[-1]["error"] = "inference failed"
        result = unified.summarize(rows)["model-only"]
        self.assertEqual(tuple(result["behavior_per_class"]), CLASSES)
        for behavior in CLASSES:
            with self.subTest(behavior=behavior):
                self.assert_class(result["behavior_per_class"][behavior],
                                  precision=None, recall=0.0, f1=0.0,
                                  support=1, predicted_n=0, tp=0, fp=0, fn=1)
                self.assertEqual(result["behavior_confusion"][behavior], {"INVALID": 1})
        self.assertEqual(result["inference_errors"], 1)

    def test_modes_count_the_same_scenario_ids_independently(self):
        predictions = {
            "kg-only": ("ASK", "ANSWER", "ESCALATE"),
            "model-only": ("ANSWER", "ANSWER", "INVALID"),
            "kg+model": ("ASK", "ASK", "ESCALATE"),
        }
        rows = [
            behavior_record(gold, predicted, mode=mode, scenario_id=f"shared-{gold}")
            for mode, outputs in predictions.items()
            for gold, predicted in zip(CLASSES, outputs)
        ]
        results = unified.summarize(rows)
        self.assertEqual(tuple(results), tuple(predictions))
        for behavior in CLASSES:
            self.assert_class(results["kg-only"]["behavior_per_class"][behavior],
                              precision=1.0, recall=1.0, f1=1.0,
                              support=1, predicted_n=1, tp=1, fp=0, fn=0)
        self.assert_class(results["model-only"]["behavior_per_class"]["ANSWER"],
                          precision=0.5, recall=1.0, f1=2 / 3,
                          support=1, predicted_n=2, tp=1, fp=1, fn=0)
        self.assert_class(results["model-only"]["behavior_per_class"]["ESCALATE"],
                          precision=None, recall=0.0, f1=0.0,
                          support=1, predicted_n=0, tp=0, fp=0, fn=1)
        self.assert_class(results["kg+model"]["behavior_per_class"]["ASK"],
                          precision=0.5, recall=1.0, f1=2 / 3,
                          support=1, predicted_n=2, tp=1, fp=1, fn=0)
        self.assert_class(results["kg+model"]["behavior_per_class"]["ESCALATE"],
                          precision=1.0, recall=1.0, f1=1.0,
                          support=1, predicted_n=1, tp=1, fp=0, fn=0)

    def test_terminal_table_keeps_summary_and_formats_each_mode_and_class(self):
        rows = [behavior_record("ASK", "ANSWER")]
        rows.extend(behavior_record("ASK", predicted, mode="kg-only", scenario_id=f"kg-{index}")
                    for index, predicted in enumerate(CLASSES))
        terminal = io.StringIO()
        with redirect_stdout(terminal):
            unified.print_summary(unified.summarize(rows))
        output = terminal.getvalue()
        title = output.index("Per-class behavior performance")
        start = output.index("=== Score summary ===")
        summary = [line.split() for line in output[start:title].splitlines()]
        index = next(i for i, cells in enumerate(summary) if cells[:2] == ["mode", "n"])
        header = summary[index]
        self.assertEqual(header[:3], ["mode", "n", "row"])
        self.assertEqual(header[-1], "total")
        self.assertEqual([row[0] for row in summary[index + 2:index + 6]],
                         ["model-only", "weighted", "kg-only", "weighted"])
        behavior_column = header.index("behavior")
        top1_column = header.index("P@1")
        row_column = header.index("row")
        for offset, mode, n, raw, points, raw_total, weighted_total in (
            (2, "model-only", "1", "0.00", "0.00", "7.00/8", "75.00/100"),
            (4, "kg-only", "3", "0.33", "8.33", "7.33/8", "83.33/100"),
        ):
            raw_row, weighted_row = summary[index + offset:index + offset + 2]
            self.assertEqual(raw_row[:3], [mode, n, "raw"])
            self.assertEqual(raw_row[behavior_column], raw)
            self.assertEqual(weighted_row[behavior_column - row_column], points)
            self.assertEqual(raw_row[top1_column], "1.00")
            self.assertEqual(weighted_row[top1_column - row_column], "-")
            self.assertEqual(raw_row[-1], raw_total)
            self.assertEqual(weighted_row[-1], weighted_total)
        table = [line.split() for line in output[title:].splitlines()]
        self.assertIn(["mode", "behavior", "precision", "recall", "f1", "support", "predicted"], table)
        data = [cells for cells in table if len(cells) == 7 and cells[0] in ("model-only", "kg-only")]
        self.assertEqual(data, [
            ["model-only", "ASK", "N/A", "0.00", "0.00", "1", "0"],
            ["model-only", "ANSWER", "0.00", "N/A", "0.00", "0", "1"],
            ["model-only", "ESCALATE", "N/A", "N/A", "N/A", "0", "0"],
            ["kg-only", "ASK", "1.00", "0.33", "0.50", "3", "1"],
            ["kg-only", "ANSWER", "0.00", "N/A", "0.00", "0", "1"],
            ["kg-only", "ESCALATE", "0.00", "N/A", "0.00", "0", "1"],
        ])

    def test_real_kg_run_exports_three_classes_with_json_null_and_csv_na(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "reports"
            args = unified.build_parser().parse_args([
                "--modes", "kg-only", "--dataset", str(ROOT / "data/eval/gold_eval_v0.3.json"),
                "--output-dir", str(directory), "--limit", "1", "--no-warmup",
            ])
            terminal = io.StringIO()
            with (
                patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")) as network,
                redirect_stdout(terminal),
            ):
                unified.run(args)
            network.assert_not_called()
            summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
            result = summary["results"]["kg-only"]
            classes = result["behavior_per_class"]
            self.assertEqual(tuple(classes), CLASSES)
            self.assert_class(classes["ASK"], precision=1.0, recall=1.0, f1=1.0,
                              support=1, predicted_n=1, tp=1, fp=0, fn=0)
            for behavior in ("ANSWER", "ESCALATE"):
                self.assert_class(classes[behavior], precision=None, recall=None, f1=None,
                                  support=0, predicted_n=0, tp=0, fp=0, fn=0)
            with (directory / "behavior_per_class.csv").open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                exported = list(reader)
                self.assertEqual(reader.fieldnames, [
                    "mode", "behavior", "precision", "recall", "f1", "support", "predicted_n", "tp", "fp", "fn",
                ])
            self.assertEqual(len(exported), 3)
            self.assertEqual([row["behavior"] for row in exported], list(CLASSES))
            self.assertTrue(all(row["mode"] == "kg-only" for row in exported))
            self.assertEqual({key: exported[0][key] for key in ("support", "predicted_n", "tp", "fp", "fn")},
                             {"support": "1", "predicted_n": "1", "tp": "1", "fp": "0", "fn": "0"})
            self.assertEqual([float(exported[0][key]) for key in ("precision", "recall", "f1")], [1.0, 1.0, 1.0])
            for row in exported[1:]:
                self.assertEqual([row[key] for key in ("precision", "recall", "f1")], ["N/A"] * 3)
                self.assertEqual([row[key] for key in ("support", "predicted_n", "tp", "fp", "fn")], ["0"] * 5)
            self.assertIn("Per-class behavior performance", terminal.getvalue())
            for expected in (
                ["kg-only", "ASK", "1.00", "1.00", "1.00", "1", "1"],
                ["kg-only", "ANSWER", "N/A", "N/A", "N/A", "0", "0"],
                ["kg-only", "ESCALATE", "N/A", "N/A", "N/A", "0", "0"],
            ):
                self.assertIn(expected, [line.split() for line in terminal.getvalue().splitlines()])


if __name__ == "__main__":
    unittest.main()
