"""
Load Targets (Sinks)

The final stage of the pipeline. `MetricsCollectorSink` is the one that closes
the loop: it hands canonical records to the existing observability layer, so
ingested production telemetry drives the same anomaly detector and agent
pipeline that the built-in simulator drives.

Sinks are additive — a run can fan out to several at once (live metrics plus a
durable JSONL landing file for replay).
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from ingestion.schema import CanonicalTelemetryRecord


class TelemetrySink(ABC):
    """A destination for validated canonical records."""

    name: str = "sink"

    @abstractmethod
    def write(self, records: List[CanonicalTelemetryRecord]) -> int:
        """Write a batch; return the number of records accepted."""

    def flush(self) -> None:
        """Release any buffered resources. No-op unless a sink buffers."""


class MetricsCollectorSink(TelemetrySink):
    """
    Loads records into the live `MetricsCollector`.

    This is the seam between the data pipeline and the reliability platform:
    everything upstream is vendor-agnostic ETL, everything downstream is the
    existing detection and remediation workflow, unchanged.
    """

    name = "metrics_collector"

    def __init__(self, collector=None):
        # Imported lazily so the ingestion package stays independently testable.
        if collector is None:
            from observability.metrics_collector import metrics_collector as default_collector
            collector = default_collector
        self._collector = collector

    def write(self, records: List[CanonicalTelemetryRecord]) -> int:
        written = 0
        # Ordering matters: the collector maintains a rolling window and
        # computes percentiles per arrival, so out-of-order events would
        # produce snapshots that never existed.
        for record in sorted(records, key=lambda r: r.timestamp):
            self._collector.record_query_event(record.to_metrics_event())
            written += 1
        return written


class JSONLSink(TelemetrySink):
    """
    Appends canonical records to a newline-delimited JSON file.

    Serves as the durable landing zone: raw-but-normalized records kept for
    replay, backfill, and offline analysis independent of the in-memory window.
    """

    name = "jsonl"

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, records: List[CanonicalTelemetryRecord]) -> int:
        if not records:
            return 0
        with self.path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.model_dump(mode="json")) + "\n")
        return len(records)


class MemorySink(TelemetrySink):
    """Collects records in memory. Used by tests and dry runs."""

    name = "memory"

    def __init__(self, capacity: Optional[int] = None):
        self.records: List[CanonicalTelemetryRecord] = []
        self.capacity = capacity

    def write(self, records: List[CanonicalTelemetryRecord]) -> int:
        self.records.extend(records)
        if self.capacity is not None and len(self.records) > self.capacity:
            self.records = self.records[-self.capacity:]
        return len(records)

    def clear(self) -> None:
        self.records.clear()
