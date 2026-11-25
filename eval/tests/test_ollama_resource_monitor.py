"""Event-synchronized residency sampling tests without HTTP or models."""

from threading import Event, get_ident
from time import perf_counter
import unittest
from unittest.mock import Mock, patch

from eval.ollama_resource_monitor import OllamaMemoryMonitor, SCOPE


def sample(resident, vram=None, error=None):
    return {"predictor_memory_mib": resident, "ollama_model_vram_mib": vram,
            "predictor_memory_error": error}


class OllamaMemoryMonitorTests(unittest.TestCase):
    def window_with_results(self, results):
        """Block one additional call so preceding samples have been committed."""
        blocked, release = Event(), Event()
        values = iter(results)

        def probe():
            try:
                value = next(values)
            except StopIteration:
                blocked.set()
                if not release.wait(2):
                    raise RuntimeError("Test probe release timed out")
                return sample(99999, 99999)
            if isinstance(value, Exception):
                raise value
            return value

        monitor = OllamaMemoryMonitor(Mock(side_effect=probe), interval_s=0.001).start()
        self.addCleanup(release.set)
        self.assertTrue(blocked.wait(2))
        monitor.freeze()
        release.set()
        return monitor, monitor.stop()

    def test_start_is_async_and_first_probe_needs_no_interval_wait(self):
        entered, release = Event(), Event()
        called_on = []

        def probe():
            called_on.append(get_ident())
            entered.set()
            release.wait(2)
            return sample(1024, 512)

        monitor = OllamaMemoryMonitor(probe, interval_s=60)
        self.addCleanup(release.set)
        self.assertIs(monitor.start(), monitor)
        self.assertTrue(entered.wait(1))
        self.assertNotEqual(called_on, [get_ident()])
        monitor.freeze()
        release.set()
        result = monitor.stop()
        self.assertIsNone(result["predictor_memory_mib"])
        self.assertEqual(result["ollama_memory_sample_count"], 0)

    def test_in_window_resident_and_vram_maxima_are_independent(self):
        monitor, result = self.window_with_results([sample(1024, 800), sample(2048, 600), sample(1536, 900)])
        self.assertEqual(result["predictor_memory_mib"], 2048)
        self.assertEqual(result["ollama_model_resident_mib"], 2048)
        self.assertEqual(result["ollama_model_vram_mib"], 900)
        self.assertEqual(result["predictor_memory_scope"], SCOPE)
        self.assertEqual(result["ollama_memory_sample_count"], 3)
        self.assertEqual(result["ollama_memory_probe_count"], 3)
        self.assertEqual(result["ollama_memory_failed_sample_count"], 0)
        self.assertEqual(result["ollama_memory_interval_s"], 0.001)
        self.assertEqual(result["ollama_memory_errors"], [])
        self.assertIsNone(result["predictor_memory_error"])
        self.assertEqual(monitor.stop(), result)

    def test_freeze_discards_late_larger_values_and_late_errors(self):
        for late in (sample(99999, 99999), RuntimeError("late failure")):
            with self.subTest(late=late):
                entered, release = Event(), Event()
                calls = 0

                def probe():
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        return sample(100, 50)
                    entered.set()
                    release.wait(2)
                    if isinstance(late, Exception):
                        raise late
                    return late

                monitor = OllamaMemoryMonitor(probe, interval_s=0.001).start()
                self.addCleanup(release.set)
                self.assertTrue(entered.wait(2))
                monitor.freeze()
                release.set()
                result = monitor.stop()
                self.assertEqual(result["predictor_memory_mib"], 100)
                self.assertEqual(result["ollama_model_vram_mib"], 50)
                self.assertEqual(result["ollama_memory_sample_count"], 1)
                self.assertEqual(result["ollama_memory_failed_sample_count"], 0)
                self.assertIsNone(result["predictor_memory_error"])

    def test_errors_then_success_preserve_raw_maximum_but_mark_it_partial(self):
        _, result = self.window_with_results([sample(None, error="Model absent"), RuntimeError("probe failed"), sample(123, 0)])
        self.assertEqual(result["predictor_memory_mib"], 123)
        self.assertEqual(result["ollama_model_vram_mib"], 0)
        self.assertEqual(result["ollama_memory_sample_count"], 1)
        self.assertEqual(result["ollama_memory_failed_sample_count"], 2)
        self.assertEqual(result["ollama_memory_probe_count"], 3)
        self.assertIn("Partial", result["predictor_memory_error"])
        self.assertIn("Model absent", result["predictor_memory_error"])
        self.assertEqual(len(result["ollama_memory_errors"]), 2)

    def test_missing_vram_is_unavailable_without_inventing_a_zero(self):
        _, result = self.window_with_results([sample(123)])
        self.assertEqual(result["predictor_memory_mib"], 123)
        self.assertIsNone(result["ollama_model_vram_mib"])
        self.assertIsNone(result["predictor_memory_error"])

    def test_bad_probe_results_cannot_become_numeric_zero_peaks(self):
        bad = [None, [], {}, sample(None), sample(0), sample(-1), sample(True),
               sample(float("nan")), sample(float("inf")), sample("100"),
               sample(10, -1), sample(10, True), sample(10, float("nan")),
               {"predictor_memory_mib": 10, "error": "failed"}]
        _, result = self.window_with_results(bad)
        self.assertIsNone(result["predictor_memory_mib"])
        self.assertIsNone(result["ollama_model_vram_mib"])
        self.assertEqual(result["ollama_memory_sample_count"], 0)
        self.assertEqual(result["ollama_memory_failed_sample_count"], len(bad))
        self.assertIn("No successful", result["predictor_memory_error"])

    def test_zero_samples_and_stop_before_start_are_explicitly_unavailable(self):
        monitor = OllamaMemoryMonitor(Mock(return_value=sample(100)))
        result = monitor.stop()
        self.assertIsNone(result["predictor_memory_mib"])
        self.assertEqual(result["ollama_memory_probe_count"], 0)
        self.assertIn("not started", result["predictor_memory_error"])
        monitor.probe.assert_not_called()
        self.assertEqual(monitor.stop(), result)

    def test_stop_has_bounded_join_and_restart_rejects_a_live_old_worker(self):
        entered, release = Event(), Event()

        def probe():
            entered.set()
            release.wait(2)
            return sample(100)

        monitor = OllamaMemoryMonitor(probe).start()
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(1))
        started = perf_counter()
        result = monitor.stop()
        self.assertLess(perf_counter() - started, 0.8)
        self.assertIsNone(result["predictor_memory_mib"])
        self.assertIn("did not stop", result["predictor_memory_error"])
        with self.assertRaises(RuntimeError):
            monitor.start()
        release.set()
        monitor._thread.join(timeout=1)
        self.assertEqual(monitor.stop(), result)

    def test_active_start_is_idempotent_and_fresh_windows_reset_state(self):
        monitor, first = self.window_with_results([sample(200, 100), sample(None, error="first error")])
        entered, release = Event(), Event()
        calls = 0

        def probe():
            nonlocal calls
            calls += 1
            if calls == 1:
                return sample(50, 10)
            entered.set()
            release.wait(2)
            return sample(99999)

        monitor.probe = probe
        self.addCleanup(release.set)
        monitor.start()
        self.assertIs(monitor.start(), monitor)
        self.assertTrue(entered.wait(2))
        monitor.freeze()
        release.set()
        second = monitor.stop()
        self.assertEqual(first["predictor_memory_mib"], 200)
        self.assertEqual(second["predictor_memory_mib"], 50)
        self.assertEqual(second["ollama_memory_sample_count"], 1)
        self.assertEqual(second["ollama_memory_failed_sample_count"], 0)
        self.assertIsNone(second["predictor_memory_error"])
        second["ollama_memory_errors"].append("outside mutation")
        self.assertEqual(monitor.stop()["ollama_memory_errors"], [])

    def test_start_failure_is_reported_without_calling_probe(self):
        probe = Mock()
        monitor = OllamaMemoryMonitor(probe)
        with patch("eval.ollama_resource_monitor.Thread.start", side_effect=RuntimeError("thread unavailable")):
            monitor.start()
        result = monitor.stop()
        self.assertIsNone(result["predictor_memory_mib"])
        self.assertIn("thread unavailable", result["predictor_memory_error"])
        probe.assert_not_called()

    def test_constructor_rejects_noncallables_and_invalid_intervals(self):
        for probe in (None, {}, 1):
            with self.subTest(probe=probe), self.assertRaises(ValueError):
                OllamaMemoryMonitor(probe)
        for interval in (None, True, 0, -1, "0.1", float("nan"), float("inf"), 10**1000):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                OllamaMemoryMonitor(Mock(), interval_s=interval)


if __name__ == "__main__":
    unittest.main()
