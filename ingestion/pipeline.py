"""
Telemetry Ingestion Pipeline

Orchestrates the full path from vendor payload to live observability:

    extract (connectors)
      -> normalize (declarative mapping, unit reconciliation)
      -> enrich    (derivation transforms)
      -> validate  (quality gates, dead-letter quarantine)
      -> load      (sinks -> MetricsCollector -> AnomalyDetector -> agents)

Design constraints this reflects:

  * A failing source degrades that source only. One unreachable vendor must not
    stop ingestion from the others, so fetch errors are captured per connector
    and reported rather than raised.
  * Every run is observable. Counts, per-source breakdowns, rejection reasons,
    and dead-letter samples are returned as a structured report, because a
    silent pipeline is indistinguishable from a healthy one.
  * Loading is ordered. Records from independent sources are merged and sorted
    by event time before reaching the collector's rolling window.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ingestion.connectors.base import TelemetryConnector
from ingestion.schema import CanonicalTelemetryRecord
from ingestion.sinks import TelemetrySink
from ingestion.transforms import Transform, apply_transforms, default_transforms
from ingestion.validation import QualityGate, QualityReport, default_gates


@dataclass
class SourceRunStats:
    """Per-connector outcome for a single run."""
    source_name: str
    source_kind: str
    records_read: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    mapping_errors: int = 0
    fetch_error: Optional[str] = None

    @property
    def healthy(self) -> bool:
        return self.fetch_error is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_kind": self.source_kind,
            "records_read": self.records_read,
            "records_accepted": self.records_accepted,
            "records_rejected": self.records_rejected,
            "mapping_errors": self.mapping_errors,
            "fetch_error": self.fetch_error,
            "healthy": self.healthy,
        }


@dataclass
class IngestionRunReport:
    """Structured result of one pipeline run."""
    started_at: float
    duration_seconds: float = 0.0
    sources: List[SourceRunStats] = field(default_factory=list)
    quality: QualityReport = field(default_factory=QualityReport)
    records_loaded: int = 0
    sinks_written: Dict[str, int] = field(default_factory=dict)

    @property
    def total_read(self) -> int:
        return sum(s.records_read for s in self.sources)

    @property
    def healthy_sources(self) -> int:
        return sum(1 for s in self.sources if s.healthy)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "duration_seconds": round(self.duration_seconds, 4),
            "total_read": self.total_read,
            "records_loaded": self.records_loaded,
            "sources_configured": len(self.sources),
            "sources_healthy": self.healthy_sources,
            "sources": [s.to_dict() for s in self.sources],
            "quality": self.quality.to_dict(),
            "sinks_written": self.sinks_written,
        }


class IngestionPipeline:
    """Runs connectors through normalization, validation, and loading."""

    def __init__(
        self,
        connectors: List[TelemetryConnector],
        sinks: List[TelemetrySink],
        gates: Optional[List[QualityGate]] = None,
        transforms: Optional[List[Transform]] = None,
    ):
        self.connectors = connectors
        self.sinks = sinks
        # Gates are stateful (dedup keeps a seen-set), so the chain is built
        # once and reused across runs rather than rebuilt per run.
        self.gates = gates if gates is not None else default_gates()
        self.transforms = transforms if transforms is not None else default_transforms()
        self.last_report: Optional[IngestionRunReport] = None

    def run_once(self) -> IngestionRunReport:
        """Execute one full extract-transform-validate-load cycle."""
        started = time.time()
        report = IngestionRunReport(started_at=started)
        accepted: List[CanonicalTelemetryRecord] = []

        for connector in self.connectors:
            if not connector.config.enabled:
                continue

            stats = SourceRunStats(
                source_name=connector.config.name,
                source_kind=connector.config.kind.value,
            )
            result = connector.read()

            if not result.ok:
                stats.fetch_error = result.fetch_error
                report.sources.append(stats)
                continue

            stats.records_read = len(result.records)
            stats.mapping_errors = len(result.mapping_errors)

            for record in result.records:
                record = apply_transforms(record, self.transforms)

                rejection = self._first_rejection(record, report.quality)
                if rejection:
                    stats.records_rejected += 1
                    continue

                report.quality.record_accept()
                stats.records_accepted += 1
                accepted.append(record)

            report.sources.append(stats)

        # Merge across sources before loading so the collector's rolling window
        # sees a single time-ordered stream.
        accepted.sort(key=lambda r: r.timestamp)

        for sink in self.sinks:
            try:
                written = sink.write(accepted)
                report.sinks_written[sink.name] = written
            except Exception as exc:  # noqa: BLE001 - a failing sink is reported, not fatal
                report.sinks_written[sink.name] = -1
                report.quality.rejections_by_reason[f"sink_error:{sink.name}"] += 1
                _ = exc

        report.records_loaded = len(accepted)
        report.duration_seconds = time.time() - started
        self.last_report = report
        return report

    def _first_rejection(
        self,
        record: CanonicalTelemetryRecord,
        quality: QualityReport,
    ) -> Optional[str]:
        """Apply gates in order, stopping at the first rejection."""
        for gate in self.gates:
            outcome = gate.check(record)
            if not outcome.accepted:
                reason = outcome.reason or "unspecified"
                quality.record_reject(record, gate.name, reason)
                return reason
        return None

    def describe_sources(self) -> List[Dict[str, Any]]:
        """Current connector inventory, for the API and dashboard."""
        return [
            {
                "name": c.config.name,
                "kind": c.config.kind.value,
                "enabled": c.config.enabled,
                "origin": c.config.endpoint or c.config.fixture_path,
                "mode": "live" if c.config.endpoint else "replay",
                "service_name": c.config.service_name,
                "environment": c.config.environment,
            }
            for c in self.connectors
        ]

    def reset(self) -> None:
        """
        Rewind for a full replay.

        Connector watermarks and gate state have to be cleared together: a
        rewind that left the dedup seen-set intact would re-read every record
        and then reject all of them as duplicates, which looks identical to a
        broken pipeline.
        """
        for connector in self.connectors:
            connector.reset_watermark()
        for gate in self.gates:
            gate.reset()
