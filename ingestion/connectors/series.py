"""
Metric-Series Connector Base (Prometheus / Datadog family)

Span and log sources are event-oriented: one payload record equals one request.
Metrics backends are series-oriented: they return N independent time series of
pre-aggregated values, with no per-request rows at all.

Bridging that gap is a pivot. Each series contributes one column, and values
are aligned onto a shared time grid to produce one wide record per bucket.
Buckets missing a required column are dropped rather than silently defaulted,
because a half-populated record would feed the anomaly detector a metric that
looks like a healthy zero rather than an absent reading.
"""
from __future__ import annotations

from abc import abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from ingestion.connectors.base import ConnectorConfig, TelemetryConnector
from ingestion.mapping import CONVERTERS, FieldRule, SourceMapping


@dataclass(frozen=True)
class SeriesColumn:
    """Maps one upstream metric name onto one canonical field."""
    metric_name: str
    target: str
    converter: str = "to_float"
    required: bool = False


# The pivot emits canonical field names directly, so the mapping only needs to
# coerce primitive types rather than move fields around.
PIVOTED_MAPPING = SourceMapping(
    name="pivoted_series",
    rules=[
        FieldRule("timestamp", "timestamp", "to_float", required=True),
        FieldRule("latency_seconds", "latency_seconds", "to_float"),
        FieldRule("cost_usd", "cost_usd", "to_float"),
        FieldRule("total_tokens", "total_tokens", "to_int"),
        FieldRule("prompt_tokens", "prompt_tokens", "to_int"),
        FieldRule("output_tokens", "output_tokens", "to_int"),
        FieldRule("retrieved_chunks_count", "retrieved_chunks_count", "to_int"),
        FieldRule("groundedness_score", "groundedness_score", "to_float"),
        FieldRule("context_relevance_score", "context_relevance_score", "to_float"),
        FieldRule("answer_quality_score", "answer_quality_score", "to_float"),
        FieldRule("error", "error", "to_bool", default=False),
    ],
)


class MetricSeriesConnector(TelemetryConnector):
    """Base for backends that return aligned time series instead of events."""

    def __init__(self, config: ConnectorConfig, align_seconds: float = 10.0):
        super().__init__(config)
        # Series from different queries rarely share exact timestamps, so
        # values are snapped onto a grid of this resolution before joining.
        self.align_seconds = align_seconds

    @property
    def mapping(self) -> SourceMapping:
        return PIVOTED_MAPPING

    # -- Subclass contract --------------------------------------------------

    @property
    @abstractmethod
    def columns(self) -> List[SeriesColumn]:
        """Declares which upstream metric feeds which canonical field."""

    @abstractmethod
    def extract_series(self, payload: Any) -> List[Tuple[str, List[Tuple[float, float]]]]:
        """Return [(metric_name, [(epoch_seconds, value), ...]), ...]."""

    # -- Pivot --------------------------------------------------------------

    def fetch_raw(self) -> Any:
        payload = self._load_payload()
        return self.pivot(self.extract_series(payload))

    def pivot(self, series: List[Tuple[str, List[Tuple[float, float]]]]) -> List[Dict[str, Any]]:
        """Join independent series into wide, per-bucket records."""
        columns_by_metric = {col.metric_name: col for col in self.columns}
        buckets: Dict[float, Dict[str, Any]] = defaultdict(dict)

        for metric_name, points in series:
            column = columns_by_metric.get(metric_name)
            if column is None:
                continue  # Metric not part of the canonical model; ignore it.

            convert = CONVERTERS.get(column.converter, CONVERTERS["to_float"])
            for raw_ts, raw_value in points:
                try:
                    bucket = self._align(float(raw_ts))
                    buckets[bucket][column.target] = convert(raw_value)
                except (TypeError, ValueError):
                    continue  # Prometheus reports gaps as NaN/None.

        required = [col.target for col in self.columns if col.required]
        records: List[Dict[str, Any]] = []

        for bucket_ts in sorted(buckets):
            row = buckets[bucket_ts]
            if any(target not in row for target in required):
                continue
            row["timestamp"] = bucket_ts
            records.append(row)

        return records

    def _align(self, timestamp: float) -> float:
        if self.align_seconds <= 0:
            return timestamp
        return round(timestamp / self.align_seconds) * self.align_seconds
