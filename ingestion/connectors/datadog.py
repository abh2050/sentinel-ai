"""
Datadog Connector

Reads the timeseries query response (`/api/v1/query`) and pivots the returned
series into canonical records.

Datadog reports point timestamps in epoch milliseconds and bills LLM cost in
whole micro-dollars, so both are converted during extraction and mapping.
"""
from __future__ import annotations

from typing import Any, List, Tuple

from ingestion.connectors.base import ConnectorConfig
from ingestion.connectors.series import MetricSeriesConnector, SeriesColumn
from ingestion.schema import SourceKind


class DatadogConnector(MetricSeriesConnector):
    """Pulls RAG service metrics from a Datadog timeseries query."""

    def __init__(self, config: ConnectorConfig, align_seconds: float = 10.0):
        config.kind = SourceKind.DATADOG
        super().__init__(config, align_seconds=align_seconds)

    @property
    def columns(self) -> List[SeriesColumn]:
        return [
            SeriesColumn("rag.request.latency.p95", "latency_seconds", "ms_to_s", required=True),
            SeriesColumn("rag.request.cost", "cost_usd", "micros_to_usd"),
            SeriesColumn("rag.request.tokens.total", "total_tokens", "to_int"),
            SeriesColumn("rag.retrieval.chunks", "retrieved_chunks_count", "to_int"),
            SeriesColumn("rag.eval.groundedness", "groundedness_score", "pct_to_pct"),
            SeriesColumn("rag.eval.context_relevance", "context_relevance_score", "pct_to_pct"),
            SeriesColumn("rag.eval.answer_quality", "answer_quality_score", "pct_to_pct"),
        ]

    def extract_series(self, payload: Any) -> List[Tuple[str, List[Tuple[float, float]]]]:
        status = payload.get("status")
        if status is not None and status != "ok":
            raise ValueError(f"datadog query failed: {payload.get('error', 'unknown error')}")

        series: List[Tuple[str, List[Tuple[float, float]]]] = []

        for entry in payload.get("series", []) or []:
            metric_name = entry.get("metric")
            if not metric_name:
                continue

            points: List[Tuple[float, float]] = []
            for pair in entry.get("pointlist", entry.get("points", [])) or []:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                timestamp_ms, raw_value = pair
                if raw_value is None:
                    continue  # Datadog nulls out interpolation gaps.
                try:
                    points.append((float(timestamp_ms) / 1000.0, float(raw_value)))
                except (TypeError, ValueError):
                    continue

            if points:
                series.append((metric_name, points))

        return series
