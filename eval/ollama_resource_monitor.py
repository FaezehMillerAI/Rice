"""Sample server-reported target-model residency within a prediction window.

This is a sampled maximum of /api/ps model residency, never total server RSS,
unique physical memory, or a guarantee of capturing transient allocations.
The caller supplies the probe; this module performs no HTTP or model loading.
"""

from __future__ import annotations

from copy import deepcopy
import math
from threading import Event, Lock, Thread, current_thread


SCOPE = "ollama_api_ps_model_resident_sampled_max_during_prediction"


def _finite_number(value, *, positive: bool) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and (value > 0 if positive else value >= 0)
    except (OverflowError, ValueError):
        return False


class OllamaMemoryMonitor:
    """Run immediate/background probes and freeze before parsing or scoring.

    A probe that finishes after ``freeze`` cannot affect values, counts, errors,
    or a subsequent window. Failed in-window probes make a numeric sampled
    maximum a partial measurement; callers should not treat it as a valid peak.
    ``stop`` waits at most 0.5 seconds for an outstanding probe, then ignores it.
    """

    _JOIN_TIMEOUT_S = 0.5

    def __init__(self, probe, interval_s: float = 0.1):
        if not callable(probe):
            raise ValueError("probe must be callable")
        if not _finite_number(interval_s, positive=True):
            raise ValueError("interval_s must be a finite positive number")
        self.probe = probe
        self.interval_s = float(interval_s)
        self._lock = Lock()
        self._event = Event()
        self._thread = None
        self._started = False
        self._running = False
        self._peak_resident = None
        self._peak_vram = None
        self._sample_count = 0
        self._failed_count = 0
        self._errors = []
        self._result = None

    def start(self) -> OllamaMemoryMonitor:
        """Start a fresh window without making a synchronous probe call."""
        with self._lock:
            if self._running:
                return self
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Previous Ollama memory sampling thread has not stopped")
            self._event = Event()
            self._started = self._running = True
            self._peak_resident = self._peak_vram = None
            self._sample_count = self._failed_count = 0
            self._errors = []
            self._result = None
            self._thread = Thread(target=self._run, name="OllamaResidentMemoryMonitor", daemon=True)
            try:
                self._thread.start()
            except Exception as exc:
                self._thread = None
                self._errors.append(f"Cannot start sampler: {type(exc).__name__}: {exc}")
        return self

    def freeze(self) -> OllamaMemoryMonitor:
        """Close the window immediately; never wait for a pending probe."""
        with self._lock:
            self._running = False
            self._event.set()
        return self

    def _sample(self) -> None:
        with self._lock:
            if not self._running:
                return
        error = None
        resident = vram = None
        try:
            result = self.probe()
            if not isinstance(result, dict):
                raise ValueError("Probe must return a memory-measurement dict")
            probe_error = result.get("predictor_memory_error") or result.get("error")
            if probe_error:
                raise ValueError(str(probe_error))
            resident = result.get("predictor_memory_mib")
            if not _finite_number(resident, positive=True):
                raise ValueError("Probe resident model memory must be finite and positive")
            vram = result.get("ollama_model_vram_mib")
            if vram is not None and not _finite_number(vram, positive=False):
                raise ValueError("Probe VRAM must be finite and nonnegative, or None")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        with self._lock:
            # Freeze is authoritative even if a request was already in flight.
            if not self._running:
                return
            if error is not None:
                self._failed_count += 1
                if error not in self._errors:
                    self._errors.append(error)
                return
            self._sample_count += 1
            self._peak_resident = resident if self._peak_resident is None else max(self._peak_resident, resident)
            if vram is not None:
                self._peak_vram = vram if self._peak_vram is None else max(self._peak_vram, vram)

    def _run(self) -> None:
        self._sample()
        while not self._event.wait(self.interval_s):
            self._sample()

    def stop(self) -> dict:
        """Freeze, perform a bounded join, and return an independent cached report."""
        self.freeze()
        with self._lock:
            if self._result is not None:
                return deepcopy(self._result)
            worker = self._thread
        join_error = None
        if worker is not None:
            if worker is current_thread():
                join_error = "Sampler cannot join its own thread; late probe results are ignored"
            else:
                worker.join(timeout=self._JOIN_TIMEOUT_S)
                if worker.is_alive():
                    join_error = "Sampler did not stop within 0.5 seconds; late probe results are ignored"
        with self._lock:
            if self._result is not None:
                return deepcopy(self._result)
            if join_error and join_error not in self._errors:
                self._errors.append(join_error)
            if not self._started:
                error = "Ollama memory monitor was not started"
            elif not self._sample_count:
                error = "No successful in-window Ollama model-residency samples"
            elif self._errors:
                error = "Partial in-window Ollama model-residency measurement"
            else:
                error = None
            if error is not None and self._errors:
                error += "; " + "; ".join(self._errors)
            self._result = {
                "predictor_memory_mib": self._peak_resident,
                "ollama_model_resident_mib": self._peak_resident,
                "ollama_model_vram_mib": self._peak_vram,
                "predictor_memory_scope": SCOPE,
                "predictor_memory_error": error,
                "ollama_memory_sample_count": self._sample_count,
                "ollama_memory_failed_sample_count": self._failed_count,
                "ollama_memory_probe_count": self._sample_count + self._failed_count,
                "ollama_memory_interval_s": self.interval_s,
                "ollama_memory_errors": list(self._errors),
            }
            return deepcopy(self._result)
