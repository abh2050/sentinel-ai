"""
Prometheus Connector

Reads the `/api/v1/query_range` matrix response and pivots the returned series
into canonical records.

Prometheus values arrive as strings (to preserve float64 precision through
JSON) and gaps are encoded as the literal "NaN", both of which are handled
during extraction.
"""
from __future__ import annotations

import math
from typing import Any, List, Tuple

from ingestion.connectors.base import ConnectorConfig
from ingestion.connectors.series import MetricSeriesConnector, SeriesColumn
from ingestion.schema import SourceKind


class PrometheusConnector(MetricSeriesConnector):
    """Pulls RAG service metrics from a Prometheus range query."""

    def __init__(self, config: ConnectorConfig, align_seconds: float = 10.0):
        config.kind = SourceKind.PROMETHEUS
        super().__init__(config, align_seconds=align_seconds)

    @property
    def columns(self) -> List[SeriesColumn]:
        return [
            SeriesColumn("rag_request_latency_p95_seconds", "latency_seconds", "to_float", required=True),
            SeriesColumn("rag_request_cost_usd", "cost_usd", "to_float"),
            SeriesColumn("rag_request_tokens_total", "total_tokens", "to_int"),
            SeriesColumn("rag_retrieved_chunks", "retrieved_chunks_count", "to_int"),
            # Prometheus gauges here are on a 0-1 ratio scale.
            SeriesColumn("rag_groundedness_ratio", "groundedness_score", "unit_to_pct"),
            SeriesColumn("rag_context_relevance_ratio", "context_relevance_score", "unit_to_pct"),
            SeriesColumn("rag_answer_quality_ratio", "answer_quality_score", "unit_to_pct"),
        ]

    def extract_series(self, payload: Any) -> List[Tuple[str, List[Tuple[float, float]]]]:
        if payload.get("status") != "success":
            raise ValueError(f"prometheus query failed: {payload.get('error', 'unknown error')}")

        series: List[Tuple[str, List[Tuple[float, float]]]] = []

        for entry in (payload.get("data") or {}).get("result", []) or []:
            metric_name = (entry.get("metric") or {}).get("__name__")
            if not metric_name:
                continue

            points: List[Tuple[float, float]] = []
            for pair in entry.get("values", []) or []:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                timestamp, raw_value = pair
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                if math.isnan(value) or math.isinf(value):
                    continue  # Explicit gap in the series.
                points.append((float(timestamp), value))

            if points:
                series.append((metric_name, points))

        return series
