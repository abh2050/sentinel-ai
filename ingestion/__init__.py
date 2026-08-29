"""
SentinelAI Telemetry Ingestion Layer

Connects heterogeneous observability sources to the reliability platform:

    OTLP spans ─┐
    Prometheus ─┤
    Datadog    ─┼─> normalize ─> enrich ─> validate ─> MetricsCollector ─> Agents
    App JSONL  ─┘

Pipelines are built from configuration, so onboarding a new vendor is a
registry entry plus a field mapping — not a change to the pipeline itself.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.connectors import ConnectorConfig, TelemetryConnector, build_connector
from ingestion.pipeline import IngestionPipeline, IngestionRunReport, SourceRunStats
from ingestion.schema import CanonicalTelemetryRecord, SourceKind, make_event_id
from ingestion.sinks import JSONLSink, MemorySink, MetricsCollectorSink, TelemetrySink
from ingestion.validation import QualityReport

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "ingestion_sources.json"

__all__ = [
    "CanonicalTelemetryRecord",
    "SourceKind",
    "make_event_id",
    "ConnectorConfig",
    "TelemetryConnector",
    "build_connector",
    "IngestionPipeline",
    "IngestionRunReport",
    "SourceRunStats",
    "QualityReport",
    "TelemetrySink",
    "MetricsCollectorSink",
    "JSONLSink",
    "MemorySink",
    "load_source_specs",
    "build_pipeline_from_config",
]


def load_source_specs(config_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Read connector specs from the JSON source catalog.

    Relative `fixture_path` values are resolved against the repository root so
    the pipeline behaves the same regardless of the working directory.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)

    repo_root = path.resolve().parent.parent
    specs: List[Dict[str, Any]] = []

    for spec in catalog.get("sources", []):
        spec = dict(spec)
        fixture = spec.get("fixture_path")
        if fixture and not Path(fixture).is_absolute():
            spec["fixture_path"] = str(repo_root / fixture)
        specs.append(spec)

    return specs


def build_pipeline_from_config(
    config_path: Optional[Path] = None,
    sinks: Optional[List[TelemetrySink]] = None,
) -> IngestionPipeline:
    """
    Construct the pipeline described by the source catalog.

    Defaults to loading into the live `MetricsCollector`, which is what makes
    ingested telemetry drive the existing detection and remediation workflow.
    """
    specs = load_source_specs(config_path)
    connectors = [build_connector(spec) for spec in specs]
    return IngestionPipeline(
        connectors=connectors,
        sinks=sinks if sinks is not None else [MetricsCollectorSink()],
    )
