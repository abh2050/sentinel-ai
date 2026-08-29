"""
Connector Registry

Maps a source kind to its connector class so pipelines can be built from
configuration (YAML, JSON, env) rather than imports. Adding a vendor means
registering one class; no pipeline code changes.
"""
from __future__ import annotations

from typing import Any, Dict, Type

from ingestion.connectors.base import ConnectorConfig, TelemetryConnector
from ingestion.connectors.datadog import DatadogConnector
from ingestion.connectors.jsonl_file import JSONLFileConnector
from ingestion.connectors.otlp import OTLPConnector
from ingestion.connectors.prometheus import PrometheusConnector
from ingestion.schema import SourceKind

CONNECTOR_REGISTRY: Dict[str, Type[TelemetryConnector]] = {
    SourceKind.OTLP.value: OTLPConnector,
    SourceKind.PROMETHEUS.value: PrometheusConnector,
    SourceKind.DATADOG.value: DatadogConnector,
    SourceKind.JSONL.value: JSONLFileConnector,
}


def register_connector(kind: str, connector_cls: Type[TelemetryConnector]) -> None:
    """Register a custom connector class under a source kind."""
    CONNECTOR_REGISTRY[kind] = connector_cls


def build_connector(spec: Dict[str, Any]) -> TelemetryConnector:
    """
    Instantiate a connector from a plain config dict.

    Example:
        {"kind": "otlp", "name": "otel-collector",
         "fixture_path": "data/sample_sources/otlp_spans.json"}
    """
    spec = dict(spec)
    kind = spec.pop("kind", None)
    if kind is None:
        raise ValueError("connector spec requires a 'kind' field")

    connector_cls = CONNECTOR_REGISTRY.get(kind)
    if connector_cls is None:
        known = ", ".join(sorted(CONNECTOR_REGISTRY))
        raise ValueError(f"unknown connector kind '{kind}'. Registered kinds: {known}")

    align_seconds = spec.pop("align_seconds", None)
    config = ConnectorConfig(**spec)

    # Series connectors accept a grid resolution; event connectors do not.
    if align_seconds is not None and issubclass(connector_cls, (PrometheusConnector, DatadogConnector)):
        return connector_cls(config, align_seconds=align_seconds)  # type: ignore[call-arg]
    return connector_cls(config)
