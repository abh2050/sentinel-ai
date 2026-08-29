"""
Ingestion Service

Holds the process-wide pipeline instance for the API layer.

The pipeline is stateful by design — connectors track watermarks and the dedup
gate keeps a seen-set — so it is constructed once and reused across requests
rather than rebuilt per call, which would replay every source on every poll.

Runs load into the live `MetricsCollector`, which is the seam that lets
ingested production telemetry drive the same anomaly detection and agent
remediation workflow as the built-in simulator. Records are also appended to a
JSONL landing zone for replay and offline analysis.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional

from ingestion import build_pipeline_from_config
from ingestion.pipeline import IngestionPipeline
from ingestion.sinks import JSONLSink, MetricsCollectorSink

LANDING_ZONE = Path(__file__).resolve().parent.parent / "data" / "landing" / "canonical_telemetry.jsonl"


class IngestionService:
    """Thread-safe wrapper around a single long-lived pipeline."""

    def __init__(self):
        self._pipeline: Optional[IngestionPipeline] = None
        # Reentrant: `run_once` and `reset` hold this lock and then touch the
        # `pipeline` property, which takes it again to build on first use. A
        # plain Lock deadlocks the worker thread on whichever of them runs
        # first, hanging the API permanently.
        self._lock = threading.RLock()
        self._last_report: Optional[Dict[str, Any]] = None
        self._run_count = 0

    @property
    def pipeline(self) -> IngestionPipeline:
        """Build on first use so import order never depends on config presence."""
        if self._pipeline is None:
            with self._lock:
                if self._pipeline is None:
                    self._pipeline = build_pipeline_from_config(
                        sinks=[MetricsCollectorSink(), JSONLSink(str(LANDING_ZONE))]
                    )
        return self._pipeline

    def describe_sources(self) -> Dict[str, Any]:
        sources = self.pipeline.describe_sources()
        return {
            "sources": sources,
            "total": len(sources),
            "healthy": sum(1 for s in sources if s["enabled"]),
            "landing_zone": str(LANDING_ZONE),
        }

    def run_once(self) -> Dict[str, Any]:
        """Execute one ingestion cycle. Serialized: the pipeline is stateful."""
        with self._lock:
            report = self.pipeline.run_once()
            self._run_count += 1
            self._last_report = report.to_dict()
            self._last_report["run_number"] = self._run_count
            return self._last_report

    def last_report(self) -> Optional[Dict[str, Any]]:
        return self._last_report

    def reset(self) -> Dict[str, Any]:
        """Rewind every connector so the next run replays all sources."""
        with self._lock:
            self.pipeline.reset()
            return {"success": True, "message": "All source watermarks rewound."}


ingestion_service = IngestionService()
