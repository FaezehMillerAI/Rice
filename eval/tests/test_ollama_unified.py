"""Exercise the Ollama evaluator over HTTP without loading a language model."""

from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import csv
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import eval.evaluate_unified as unified


ROOT = Path(__file__).resolve().parents[2]
TAG = "unit-model:latest"


@contextmanager
def fake_ollama(*, thinking=True, responses=()):
    state = SimpleNamespace(calls=[], responses=list(responses), thinking=thinking)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body):
            payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            state.calls.append(("GET", self.path, None))
            if self.path == "/api/version":
                self.reply(200, {"version": "0.6-unit-test"})
            elif self.path == "/api/tags":
                self.reply(200, {"models": [{
                    "name": TAG, "model": TAG, "digest": "unit-test-model-digest",
                    "size": 123,
                    "details": {"family": "qwen2", "format": "gguf",
                                "parameter_size": "1B", "quantization_level": "Q4_K_M"},
                }]})
            else:
                self.reply(404, {"error": "Unknown test endpoint"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.calls.append(("POST", self.path, body))
            if self.path == "/api/show":
                self.reply(200, {
                    "capabilities": ["completion", *(["thinking"] if state.thinking else [])],
                    "model_info": {"general.architecture": "qwen2", "qwen2.context_length": 8192},
                    "details": {"family": "qwen2", "quantization_level": "Q4_K_M"},
                    "template": "{{ .System }}\n{{ .Prompt }}",
                    "parameters": "num_ctx 8192",
                })
            elif self.path == "/api/generate":
                status, output = state.responses.pop(0) if state.responses else (200, {
                    "response": '{"unvalidated":"raw model text"}',
                    "done": True, "done_reason": "stop",
                    "prompt_eval_count": 23, "eval_count": 7,
                })
                self.reply(status, output)
            else:
                self.reply(404, {"error": "Unknown test endpoint; pulling is forbidden"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    state.url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def arguments(url, *extra):
    return unified.build_parser().parse_args([
        "--backend", "ollama", "--model", "unit-model", "--ollama-url", url,
        "--ollama-timeout", "120", "--no-warmup", *extra,
    ])


def messages():
    return [{"role": "system", "content": "SYSTEM unchanged"},
            {"role": "user", "content": "USER unchanged"}]


class OllamaProtocolTests(unittest.TestCase):
    def test_preflight_and_generation_preserve_messages_and_server_response(self):
        with fake_ollama() as server:
            args = arguments(server.url)
            spec = unified.resolve_ollama_spec(args)
            self.assertEqual(spec["requested_model"], "unit-model")
            self.assertEqual(spec["variant"], "server-managed")
            self.assertEqual(spec["backend"], "ollama")
            generator = unified.OllamaGenerator(spec, args)
            result = generator.generate(messages(), max_new_tokens=19)

            self.assertEqual([(method, path) for method, path, _ in server.calls[:3]], [
                ("GET", "/api/version"), ("GET", "/api/tags"), ("POST", "/api/show"),
            ])
            self.assertEqual(server.calls[2][2], {"model": TAG})
            request = server.calls[-1][2]
            self.assertEqual(request["model"], TAG)
            self.assertEqual(request["system"], messages()[0]["content"])
            self.assertEqual(request["prompt"], messages()[1]["content"])
            self.assertIs(request["stream"], False)
            self.assertEqual(args.ollama_format, "none")
            self.assertNotIn("format", request)
            self.assertEqual(generator.runtime_metadata["format"], "none")
            self.assertIs(request["think"], False)
            self.assertIs(request["truncate"], False)
            self.assertIs(request["shift"], False)
            options = request["options"]
            self.assertEqual(options["temperature"], 0.1)
            self.assertEqual(options["top_p"], 0.9)
            self.assertEqual(options["seed"], args.seed)
            self.assertEqual(options["num_ctx"], generator.context_limit)
            self.assertEqual(options["num_predict"], 19)
            self.assertLessEqual(generator.context_limit, 8192)
            self.assertEqual(result["raw_output"], '{"unvalidated":"raw model text"}')
            self.assertEqual(result["raw_ollama_response"]["response"], result["raw_output"])
            self.assertEqual(result["ollama_request"], request)
            self.assertEqual(result["prompt_tokens"], 23)
            self.assertEqual(result["generated_tokens"], 7)
            self.assertFalse(result["output_budget_exhausted"])
            self.assertIsNone(result["cuda_peak_allocated_mib"])
            self.assertEqual(generator.device, "ollama-server")
            json.dumps(generator.runtime_metadata, allow_nan=False)

    def test_explicit_json_format_enables_constraint(self):
        with fake_ollama() as server:
            args = arguments(server.url, "--ollama-format", "json")
            generator = unified.OllamaGenerator(unified.resolve_ollama_spec(args), args)
            generator.generate(messages())
            self.assertEqual(server.calls[-1][2]["format"], "json")
            self.assertEqual(generator.runtime_metadata["format"], "json")

    def test_format_none_and_non_thinking_model_omit_unsupported_fields(self):
        with fake_ollama(thinking=False, responses=[(200, {"response": "untouched", "done": True})]) as server:
            args = arguments(server.url, "--ollama-format", "none")
            generator = unified.OllamaGenerator(unified.resolve_ollama_spec(args), args)
            result = generator.generate(messages())
            request = server.calls[-1][2]
            self.assertNotIn("format", request)
            self.assertNotIn("think", request)
            self.assertEqual(request["options"]["num_predict"], args.max_new_tokens)
            self.assertIsNone(result["prompt_tokens"])
            self.assertIsNone(result["generated_tokens"])
            self.assertEqual(result["raw_output"], "untouched")

    def test_server_length_stop_marks_exhausted_output_budget(self):
        with fake_ollama(responses=[(200, {
            "response": "truncated", "done": True, "done_reason": "length", "eval_count": 9,
        })]) as server:
            args = arguments(server.url)
            generator = unified.OllamaGenerator(unified.resolve_ollama_spec(args), args)
            self.assertTrue(generator.generate(messages(), max_new_tokens=9)["output_budget_exhausted"])

    def test_missing_exact_tag_fails_without_pulling(self):
        with fake_ollama() as server:
            args = arguments(server.url)
            args.model = "unit-model:missing"
            with self.assertRaises((ValueError, RuntimeError)):
                unified.OllamaGenerator(unified.resolve_ollama_spec(args), args)
            self.assertFalse(any(path == "/api/pull" for _, path, _ in server.calls))
            self.assertFalse(any(path == "/api/generate" for _, path, _ in server.calls))

    def test_http_error_preserves_original_body(self):
        error_body = '{"error":"MODEL_FAILURE_SENTINEL original detail"}'
        with fake_ollama(responses=[(500, error_body)]) as server:
            args = arguments(server.url)
            generator = unified.OllamaGenerator(unified.resolve_ollama_spec(args), args)
            with self.assertRaises(RuntimeError) as raised:
                generator.generate(messages())
            self.assertIn(error_body, str(raised.exception))

    def test_server_backend_rejects_local_adapter_and_device_controls(self):
        for extra in (
            ("--adapter", "unused-adapter"), ("--load-in-4bit",), ("--device", "cpu"),
            ("--dtype", "bfloat16"), ("--dtype", "float16"), ("--dtype", "float32"),
        ):
            with self.subTest(extra=extra):
                args = arguments("http://127.0.0.1:1", *extra)
                with self.assertRaises(ValueError):
                    unified.resolve_ollama_spec(args)


class OllamaRunTests(unittest.TestCase):
    def test_ollama_backend_retains_bad_json_denominators_reports_and_label_isolation(self):
        cases = json.loads((ROOT / "data/eval/gold_eval_v0.3.json").read_text(encoding="utf-8"))[:2]
        cases[0].pop("family_id", None)
        cases[1]["family_id"] = ""
        secrets = ("PRIVATE_INPUT_SENTINEL", "GOLD_NOTE_SENTINEL", "TARGET_SENTINEL",
                   "disease:GOLD_CAUSE_SENTINEL", "question:GOLD_QUESTION_SENTINEL",
                   "GOLD_FACT_SENTINEL", "GOLD_SOURCE_SENTINEL")
        for case in cases:
            case["input"]["private_note"] = secrets[0]
            case["annotations"].update({
                "private_note": secrets[1], "acceptable_differential": [secrets[3]],
                "required_questions": [secrets[4]], "supporting_fact_ids": [secrets[5]],
                "supporting_source_ids": [secrets[6]],
            })
            case["target_response"]["user_response"] = secrets[2]
        replies = [(200, {"response": "NOT JSON", "done": True}) for _ in range(4)]
        real_kg = unified.KGAdapter()
        with fake_ollama(responses=replies) as server, tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "test.json"
            dataset.write_text(json.dumps(cases), encoding="utf-8")
            report_dir = Path(temporary) / "reports"
            args = arguments(server.url, "--dataset", str(dataset), "--output-dir", str(report_dir),
                             "--limit", "2", "--modes", "kg-only", "model-only", "kg+model")
            terminal = io.StringIO()
            with (
                patch.object(unified, "HFGenerator", side_effect=AssertionError("HF backend must not load")),
                patch.object(unified, "KGAdapter", return_value=real_kg),
                patch.object(real_kg, "diagnose", wraps=real_kg.diagnose) as diagnose,
                redirect_stdout(terminal),
            ):
                unified.run(args)
            self.assertEqual(diagnose.call_count, 2)
            self.assertEqual({path.name for path in report_dir.iterdir()}, {
                "run_config.json", "predictions.jsonl", "user_outputs.jsonl", "summary.json", "case_metrics.csv",
                "behavior_per_class.csv",
            })
            rows = [json.loads(line) for line in
                    (report_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()]
            user_outputs = [json.loads(line) for line in
                            (report_dir / "user_outputs.jsonl").read_text(encoding="utf-8").splitlines()]
            summary = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
            config = json.loads((report_dir / "run_config.json").read_text(encoding="utf-8"))
            with (report_dir / "case_metrics.csv").open(encoding="utf-8-sig", newline="") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual(config["family_ids"], [case["scenario_id"] for case in cases])
            self.assertEqual(config["backend"], "ollama")
            self.assertEqual(config["arguments"]["backend"], "ollama")
            self.assertEqual(len(rows), 6)
            self.assertEqual(len(user_outputs), 6)
            self.assertEqual(len(csv_rows), 6)
            for row, user_output, csv_row in zip(rows, user_outputs, csv_rows):
                for field in ("scenario_id", "family_id", "mode"):
                    self.assertEqual(user_output[field], row[field])
                    self.assertEqual(csv_row[field], row[field])
                self.assertEqual(user_output["user_response"], row["final_user_output"])
                self.assertEqual(user_output["source"], row["final_output_source"])
                self.assertEqual(user_output["status"], row["final_output_status"])
                self.assertEqual(user_output["schema_compliance"], row["metrics"]["schema_compliance"])
                self.assertEqual(user_output["error"], row["error"])
                for field in ("final_user_output", "final_output_source", "final_output_status"):
                    self.assertEqual(csv_row[field], row[field] if row[field] is not None else "")
            for row in [*rows, *csv_rows]:
                self.assertEqual(row["family_id"], row["scenario_id"])
            for mode, result in summary["results"].items():
                self.assertEqual(result["n"], 2)
                self.assertEqual(result["metrics"]["schema_compliance"]["applicable_n"], 2)
                self.assertEqual(result["metrics"]["differential_f1"]["applicable_n"], 2)
                if mode != "kg-only":
                    self.assertEqual(result["metrics"]["schema_compliance"]["value"], 0.0)
                    self.assertEqual(result["metrics"]["differential_f1"]["value"], 0.0)
            for row in rows:
                if row["mode"] == "kg-only":
                    self.assertEqual(row["raw_kg_response"]["case_id"], row["scenario_id"])
                    self.assertEqual(row["final_output_source"], "kg_template")
                else:
                    self.assertEqual(row["raw_output"], "NOT JSON")
                    self.assertEqual(row["final_user_output"], "NOT JSON")
                    self.assertEqual(row["final_output_source"], "model_generated")
                    self.assertEqual(row["final_output_status"], "raw_output")
                    self.assertIsNone(row["prediction"])
                    self.assertIsNone(row["raw_kg_response"])
                    self.assertEqual(row["metrics"]["first_behavior"], "INVALID")
                    self.assertFalse(row["metrics"]["schema_compliance"])
                    self.assertEqual(row["metrics"]["final_score"], 0.0)
            self.assertIn("NOT JSON", terminal.getvalue())
            requests = [body for _, path, body in server.calls if path == "/api/generate"]
            self.assertEqual(len(requests), 4)
            remote_text = json.dumps(requests)
            for case in cases:
                self.assertNotIn(case["scenario_id"], remote_text)
            for secret in secrets:
                self.assertNotIn(secret, remote_text)
            self.assertTrue(all(request["model"] == TAG for request in requests))


if __name__ == "__main__":
    unittest.main()
