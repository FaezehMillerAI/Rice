"""Deterministic RSS tests; no models, subprocesses or servers are started."""

from contextlib import contextmanager
from threading import Barrier, Thread
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, call, patch

import eval.resource_monitor as resources


MIB = 1024**2


def process(pid, rss_mib, children=()):
    return SimpleNamespace(
        pid=pid, memory_info=Mock(return_value=SimpleNamespace(rss=rss_mib * MIB)),
        children=Mock(return_value=list(children)),
    )


@contextmanager
def controlled_sampler(root):
    """Keep boundary samples, while disabling nondeterministic polling."""
    worker = Mock()
    worker.is_alive.return_value = False
    api = SimpleNamespace(Process=Mock(return_value=root))
    with patch.object(resources, "psutil", api), patch.object(resources, "Thread", return_value=worker):
        yield api, worker


class ResourceMonitorTests(unittest.TestCase):
    def test_interval_requires_a_finite_positive_number(self):
        for value in (0, -0.01, float("nan"), float("inf"), -float("inf"), True, "0.02", None):
            with self.subTest(interval=value):
                with self.assertRaises(ValueError):
                    resources.ResourceMonitor(value)

    def test_current_process_and_children_are_summed_once_per_pid(self):
        child = process(101, 3)
        duplicate_child = process(101, 900)
        root = process(100, 10, [child, duplicate_child])
        root.children.return_value.append(root)
        with controlled_sampler(root) as (api, worker):
            monitor = resources.ResourceMonitor()
            self.assertIs(monitor.start(), monitor)
            result = monitor.stop()
        api.Process.assert_called_once()
        self.assertEqual(root.children.call_args_list, [call(recursive=True)] * 2)
        self.assertEqual(root.memory_info.call_count, 2)
        self.assertEqual(child.memory_info.call_count, 2)
        duplicate_child.memory_info.assert_not_called()
        self.assertEqual(result, {
            "process_peak_rss_mib": 13.0,
            "memory_measurement_scope": "evaluator_process_tree",
            "memory_sample_count": 2,
            "memory_measurement_error": None,
        })
        self.assertLessEqual(worker.join.call_args.kwargs["timeout"], 1.0)

    def test_missing_psutil_is_reported_as_unavailable(self):
        with patch.object(resources, "psutil", None), patch.object(resources, "Thread") as worker:
            result = resources.ResourceMonitor().start().stop()
        worker.assert_not_called()
        self.assertIsNone(result["process_peak_rss_mib"])
        self.assertEqual(result["memory_sample_count"], 0)
        self.assertIn("psutil", result["memory_measurement_error"])

    def test_start_middle_and_end_peaks_are_all_captured(self):
        for readings in ((30, 10, 20), (10, 30, 20), (10, 20, 30)):
            with self.subTest(readings=readings):
                root = process(100, 0)
                root.memory_info.side_effect = [SimpleNamespace(rss=value * MIB) for value in readings]
                with controlled_sampler(root):
                    monitor = resources.ResourceMonitor().start()
                    monitor._sample()  # One deterministic in-window polling tick.
                    result = monitor.stop()  # The closing boundary reads the third value.
                self.assertEqual(root.memory_info.call_count, 3)
                self.assertEqual(result["process_peak_rss_mib"], 30.0)
                self.assertEqual(result["memory_sample_count"], 3)
                self.assertIsNone(result["memory_measurement_error"])

    def test_partial_child_failure_keeps_a_flagged_lower_bound(self):
        child = process(101, 3)
        child.memory_info.side_effect = PermissionError("child access denied")
        root = process(100, 10, [child])
        with controlled_sampler(root):
            result = resources.ResourceMonitor().start().stop()
        self.assertEqual(result["process_peak_rss_mib"], 10.0)
        self.assertEqual(result["memory_sample_count"], 2)
        self.assertIn("child access denied", result["memory_measurement_error"])

    def test_final_sample_failure_preserves_prior_peak_and_flags_incomplete_measurement(self):
        root = process(100, 10)
        root.memory_info.side_effect = [SimpleNamespace(rss=10 * MIB), PermissionError("final RSS read denied")]
        with controlled_sampler(root):
            result = resources.ResourceMonitor().start().stop()
        self.assertEqual(result["process_peak_rss_mib"], 10.0)
        self.assertEqual(result["memory_sample_count"], 1)
        self.assertIn("final RSS read denied", result["memory_measurement_error"])

    def test_failed_child_enumeration_is_not_misreported_as_complete(self):
        root = process(100, 10)
        root.children.side_effect = PermissionError("children unavailable")
        with controlled_sampler(root):
            result = resources.ResourceMonitor().start().stop()
        self.assertEqual(result["process_peak_rss_mib"], 10.0)
        self.assertIn("children unavailable", result["memory_measurement_error"])

    def test_total_failure_does_not_fabricate_zero_rss(self):
        root = process(100, 10)
        root.memory_info.side_effect = ProcessLookupError("process exited")
        with controlled_sampler(root):
            result = resources.ResourceMonitor().start().stop()
        self.assertIsNone(result["process_peak_rss_mib"])
        self.assertEqual(result["memory_sample_count"], 0)
        self.assertIn("process exited", result["memory_measurement_error"])

    def test_process_constructor_failure_is_reported(self):
        api = SimpleNamespace(Process=Mock(side_effect=PermissionError("cannot inspect self")))
        with patch.object(resources, "psutil", api):
            result = resources.ResourceMonitor().start().stop()
        self.assertIsNone(result["process_peak_rss_mib"])
        self.assertEqual(result["memory_sample_count"], 0)
        self.assertIn("cannot inspect self", result["memory_measurement_error"])

    def test_invalid_rss_cannot_create_nonfinite_or_negative_report(self):
        for rss in (-1, float("nan"), float("inf")):
            with self.subTest(rss=rss):
                root = process(100, 0)
                root.memory_info.return_value.rss = rss
                with controlled_sampler(root):
                    result = resources.ResourceMonitor().start().stop()
                self.assertIsNone(result["process_peak_rss_mib"])
                self.assertEqual(result["memory_sample_count"], 0)
                self.assertIn("RSS must", result["memory_measurement_error"])

    def test_repeated_start_stop_and_restart_use_independent_windows(self):
        root = process(100, 10)
        with controlled_sampler(root) as (api, worker):
            monitor = resources.ResourceMonitor()
            self.assertIsNone(monitor.stop()["process_peak_rss_mib"])
            monitor.start()
            self.assertIs(monitor.start(), monitor)
            first = monitor.stop()
            self.assertEqual(first["memory_sample_count"], 2)
            self.assertEqual(root.memory_info.call_count, 2)
            root.memory_info.return_value.rss = 1000 * MIB  # Later scoring allocations are outside the window.
            self.assertEqual(monitor.stop(), first)
            self.assertEqual(root.memory_info.call_count, 2)
            first["process_peak_rss_mib"] = -1  # Caller cannot mutate the cached report.
            self.assertEqual(monitor.stop()["process_peak_rss_mib"], 10.0)
            self.assertEqual(root.memory_info.call_count, 2)
            root.memory_info.return_value.rss = 2 * MIB
            second = monitor.start().stop()
        self.assertEqual(api.Process.call_count, 2)
        self.assertEqual(worker.start.call_count, 2)
        self.assertEqual(second["process_peak_rss_mib"], 2.0)
        self.assertEqual(second["memory_sample_count"], 2)
        self.assertEqual(root.memory_info.call_count, 4)

    def test_late_sample_cannot_change_peak_or_cached_report_after_stop(self):
        root = process(100, 10)
        with controlled_sampler(root):
            monitor = resources.ResourceMonitor().start()
            result = monitor.stop()
            root.memory_info.return_value.rss = 1000 * MIB
            monitor._sample()  # Simulate an already-in-flight worker completing late.
            self.assertEqual(monitor.stop(), result)
            self.assertEqual(monitor._peak_rss, 10 * MIB)
            self.assertEqual(monitor._sample_count, 2)

    def test_concurrent_stop_calls_share_one_final_sample_and_cached_report(self):
        root = process(100, 10)
        reports, errors = [], []
        barrier = Barrier(3)
        with controlled_sampler(root):
            monitor = resources.ResourceMonitor().start()

            def stop_window():
                try:
                    barrier.wait(timeout=1)
                    reports.append(monitor.stop())
                except Exception as exc:
                    errors.append(exc)

            callers = [Thread(target=stop_window) for _ in range(2)]
            for caller in callers:
                caller.start()
            barrier.wait(timeout=1)
            for caller in callers:
                caller.join(timeout=1)
                self.assertFalse(caller.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0], reports[1])
        self.assertEqual(root.memory_info.call_count, 2)
        self.assertEqual(reports[0]["memory_sample_count"], 2)

    def test_join_is_bounded_and_unfinished_worker_is_flagged(self):
        root = process(100, 10)
        with controlled_sampler(root) as (_, worker):
            worker.is_alive.return_value = True
            monitor = resources.ResourceMonitor().start()
            result = monitor.stop()
            self.assertGreater(worker.join.call_args.kwargs["timeout"], 0)
            self.assertLessEqual(worker.join.call_args.kwargs["timeout"], 1.0)
            self.assertIn("did not stop", result["memory_measurement_error"])
            with self.assertRaises(RuntimeError):
                monitor.start()

    def test_real_worker_stops_promptly_without_a_process_or_server_launch(self):
        root = process(100, 5)
        api = SimpleNamespace(Process=Mock(return_value=root))
        with patch.object(resources, "psutil", api):
            monitor = resources.ResourceMonitor(interval_s=60).start()
            root.memory_info.return_value.rss = 9 * MIB
            started = time.monotonic()
            result = monitor.stop()  # Event wakes the worker despite its long interval.
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1.0)
        self.assertEqual(result["process_peak_rss_mib"], 9.0)
        self.assertEqual(result["memory_sample_count"], 2)
        self.assertIsNone(result["memory_measurement_error"])
        self.assertEqual(result["memory_measurement_scope"], "evaluator_process_tree")


if __name__ == "__main__":
    unittest.main()
