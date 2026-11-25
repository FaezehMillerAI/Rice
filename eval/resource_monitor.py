"""Sample RSS for the evaluator and its children, never a separate server.

This is a sampled peak of summed per-process RSS, not unique physical memory:
shared pages can be counted in more than one process. A partial sample is a
lower bound and carries an error. Sampling can miss allocations between polls.
An independently running Ollama server is outside this measurement scope.
"""

from __future__ import annotations

import math
import os
from threading import Event, Lock, Thread, current_thread

try:
    import psutil
except (ImportError, OSError) as exc:
    psutil = None
    _PSUTIL_IMPORT_ERROR = f"psutil unavailable: {type(exc).__name__}: {exc}"
else:
    _PSUTIL_IMPORT_ERROR = None


class ResourceMonitor:
    """One reusable measurement window; repeated active start/stop is safe.

    ``memory_sample_count`` counts samples with at least one successful RSS
    read. ``memory_measurement_error`` also flags incomplete process-tree reads,
    even if a numeric lower-bound peak could be collected. Start and stop take
    explicit boundary samples; polling covers the interval between them.
    """

    _JOIN_TIMEOUT_S = 0.5

    def __init__(self, interval_s: float = 0.02):
        if type(interval_s) not in (int, float) or not math.isfinite(interval_s) or interval_s <= 0:
            raise ValueError("interval_s must be a finite positive number")
        self.interval_s = float(interval_s)
        self._lifecycle_lock = Lock()
        self._lock = Lock()
        self._event = Event()
        self._thread = None
        self._process = None
        self._running = False
        self._started = False
        self._peak_rss = None
        self._sample_count = 0
        self._errors = []
        self._result = None

    def start(self) -> ResourceMonitor:
        with self._lifecycle_lock:
            with self._lock:
                if self._running:
                    return self
                if self._thread is not None and self._thread.is_alive():
                    raise RuntimeError("Previous memory sampling thread has not stopped")
                self._event = Event()
                self._thread = None
                self._process = None
                self._running = self._started = True
                self._peak_rss = None
                self._sample_count = 0
                self._errors = []
                self._result = None

            if psutil is None:
                self._record_error(_PSUTIL_IMPORT_ERROR or "psutil unavailable: package is not installed")
                return self
            try:
                self._process = psutil.Process(os.getpid())
            except Exception as exc:
                self._record_error(f"Cannot inspect evaluator process: {type(exc).__name__}: {exc}")
                return self

            # Ensure even a short case has a baseline, before starting the worker.
            self._sample()
            self._thread = Thread(target=self._run, name="EvaluatorRSSMonitor", daemon=True)
            try:
                self._thread.start()
            except Exception as exc:
                self._thread = None
                self._record_error(f"Cannot start memory sampler: {type(exc).__name__}: {exc}")
            return self

    def _record_error(self, message: str) -> None:
        with self._lock:
            if message not in self._errors:
                self._errors.append(message)

    def _sample(self) -> None:
        errors = []
        processes = [self._process]
        try:
            processes.extend(self._process.children(recursive=True))
        except Exception as exc:
            errors.append(f"Partial process-tree measurement; cannot enumerate children: {type(exc).__name__}: {exc}")

        seen, total_rss, successful_reads = set(), 0.0, 0
        for process in processes:
            pid = None
            try:
                pid = process.pid
                if pid in seen:
                    continue
                seen.add(pid)
                rss = process.memory_info().rss
                if type(rss) not in (int, float) or not math.isfinite(rss) or rss < 0:
                    raise ValueError("RSS must be a finite nonnegative number")
                total_rss += rss
                successful_reads += 1
            except Exception as exc:
                errors.append(f"Incomplete RSS measurement for PID {pid}: {type(exc).__name__}: {exc}")

        with self._lock:
            # A blocked worker must not change the report after stop returns.
            if not self._running:
                return
            if successful_reads:
                self._peak_rss = total_rss if self._peak_rss is None else max(self._peak_rss, total_rss)
                self._sample_count += 1
            for error in errors:
                if error not in self._errors:
                    self._errors.append(error)

    def _run(self) -> None:
        while not self._event.wait(self.interval_s):
            self._sample()

    def stop(self) -> dict:
        # Serialize closing and restarting a window, including the final read.
        with self._lifecycle_lock:
            with self._lock:
                if not self._started:
                    return {
                        "process_peak_rss_mib": None,
                        "memory_measurement_scope": "evaluator_process_tree",
                        "memory_sample_count": 0,
                        "memory_measurement_error": "Resource monitor was not started",
                    }
                if self._result is not None:
                    return dict(self._result)
                self._event.set()
                worker = self._thread
                final_sample = self._running and self._process is not None

            # Capture raw-output boundary allocations before the caller scores
            # the case. _sample uses the state lock, so do not hold it here.
            if final_sample:
                self._sample()
            with self._lock:
                self._running = False

            if worker is not None:
                if worker is current_thread():
                    self._record_error("Memory sampler cannot join its own thread")
                else:
                    worker.join(timeout=self._JOIN_TIMEOUT_S)
                    if worker.is_alive():
                        self._record_error("Memory sampler did not stop within 0.5 seconds; late samples are ignored")

            with self._lock:
                self._result = {
                    "process_peak_rss_mib": self._peak_rss / 1024**2 if self._peak_rss is not None else None,
                    "memory_measurement_scope": "evaluator_process_tree",
                    "memory_sample_count": self._sample_count,
                    "memory_measurement_error": "; ".join(self._errors) or None,
                }
                return dict(self._result)
