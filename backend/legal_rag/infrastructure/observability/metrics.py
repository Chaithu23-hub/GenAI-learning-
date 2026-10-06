"""Thread-safe in-process metrics, exposable in Prometheus text format.

Zero external deps. Prometheus/OpenTelemetry export can be swapped in later
by writing a second adapter that satisfies the same `Metrics` surface.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

LabelValues = tuple[tuple[str, str], ...]  # sorted, immutable, hashable


def _norm(labels: dict[str, str] | None) -> LabelValues:
    return tuple(sorted((labels or {}).items()))


def _fmt_labels(labels: LabelValues) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
    return "{" + inner + "}"


def _escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Counter:
    def __init__(self, name: str, help_text: str):
        self.name = name
        self.help = help_text
        self._values: dict[LabelValues, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        with self._lock:
            self._values[_norm(labels)] += amount

    def render(self) -> str:
        with self._lock:
            snapshot = dict(self._values)
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        if not snapshot:
            lines.append(f"{self.name} 0")
        for labels, value in sorted(snapshot.items()):
            lines.append(f"{self.name}{_fmt_labels(labels)} {value}")
        return "\n".join(lines)


class Histogram:
    """Bucketed histogram, Prometheus-compatible cumulative buckets."""

    DEFAULT_BUCKETS = (
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
    )

    def __init__(self, name: str, help_text: str, buckets: tuple[float, ...] | None = None):
        self.name = name
        self.help = help_text
        self.buckets = tuple(sorted(buckets or self.DEFAULT_BUCKETS)) + (float("inf"),)
        self._counts: dict[LabelValues, list[float]] = defaultdict(
            lambda: [0.0] * len(self.buckets)
        )
        self._sums: dict[LabelValues, float] = defaultdict(float)
        self._observations: dict[LabelValues, int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        key = _norm(labels)
        with self._lock:
            counts = self._counts[key]
            for i, upper in enumerate(self.buckets):
                if value <= upper:
                    counts[i] += 1
            self._sums[key] += value
            self._observations[key] += 1

    @contextmanager
    def time(self, **labels: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe(time.perf_counter() - started, **labels)

    def render(self) -> str:
        with self._lock:
            counts = {k: list(v) for k, v in self._counts.items()}
            sums = dict(self._sums)
            observations = dict(self._observations)
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        for key in sorted(set(counts) | set(sums) | set(observations)):
            label_str_extra = list(key) + [("le", "")]
            for i, upper in enumerate(self.buckets):
                label_str_extra[-1] = ("le", "+Inf" if upper == float("inf") else str(upper))
                lines.append(
                    f"{self.name}_bucket{_fmt_labels(tuple(label_str_extra))} "
                    f"{counts[key][i]}"
                )
            lines.append(f"{self.name}_sum{_fmt_labels(key)} {sums[key]}")
            lines.append(f"{self.name}_count{_fmt_labels(key)} {observations[key]}")
        return "\n".join(lines)


class MetricsRegistry:
    """Central registry. Services get a metrics object via the container."""

    def __init__(self):
        self._build()

    def _build(self):
        self.requests = Counter(
            "legal_rag_requests_total",
            "Total requests processed by the QA service, labelled by outcome.",
        )
        self.guardrail_blocks = Counter(
            "legal_rag_guardrail_blocks_total",
            "Requests blocked by the input guardrail, labelled by reason.",
        )
        self.greetings = Counter(
            "legal_rag_greetings_total",
            "Requests short-circuited by the greeting handler.",
        )
        self.ingested_chunks = Counter(
            "legal_rag_ingested_chunks_total",
            "Total chunks upserted by the ingestion service.",
        )
        self.agent_stops = Counter(
            "legal_rag_agent_stops_total",
            "Agent terminations labelled by stop_reason.",
        )
        self.tokens = Counter(
            "legal_rag_tokens_total",
            "Estimated tokens consumed, labelled by component.",
        )
        self.request_duration = Histogram(
            "legal_rag_request_duration_seconds",
            "QA request latency, labelled by outcome.",
        )

    def reset(self) -> None:
        """Zero every metric in place; callers keep the same registry object."""
        self._build()

    def render_prometheus(self) -> str:
        parts = [
            self.requests.render(),
            self.guardrail_blocks.render(),
            self.greetings.render(),
            self.ingested_chunks.render(),
            self.agent_stops.render(),
            self.tokens.render(),
            self.request_duration.render(),
        ]
        return "\n".join(parts) + "\n"


_singleton: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    global _singleton
    if _singleton is None:
        _singleton = MetricsRegistry()
    return _singleton


def reset_metrics() -> None:
    """Zero the singleton in place — cached references stay valid."""
    get_metrics().reset()
