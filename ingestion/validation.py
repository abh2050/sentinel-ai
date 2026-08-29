"""
Data Quality Gates

Telemetry arriving from production is not clean: clocks drift, exporters retry
and duplicate, agents emit partial records during rollout, and a misconfigured
scrape can deliver negative or absurd values.

Feeding any of that straight into the anomaly detector is worse than dropping
it. A duplicated slow request drags the p95 up and pages someone; a record with
a zeroed groundedness score looks exactly like a hallucination incident.

Every gate returns a reason on rejection, and rejected records are quarantined
in a dead-letter buffer for inspection rather than silently discarded.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ingestion.schema import CanonicalTelemetryRecord


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    reason: Optional[str] = None

    @staticmethod
    def ok() -> "GateResult":
        return GateResult(accepted=True)

    @staticmethod
    def reject(reason: str) -> "GateResult":
        return GateResult(accepted=False, reason=reason)


class QualityGate(ABC):
    """A single accept/reject check applied to every canonical record."""

    name: str = "gate"

    @abstractmethod
    def check(self, record: CanonicalTelemetryRecord) -> GateResult:
        ...

    def reset(self) -> None:
        """
        Clear any accumulated state.

        Only stateful gates override this. It is called when a pipeline is
        rewound for replay: without it, a deliberate replay would be rejected
        wholesale as duplicate delivery.
        """


class RangeGate(QualityGate):
    """
    Rejects physically impossible values.

    Bounds are deliberately wide: this catches unit-conversion mistakes and
    corrupt scrapes, not slow requests. A genuinely slow request is an incident
    and must reach the detector.
    """

    name = "range"

    def __init__(self, max_latency_seconds: float = 600.0, max_cost_usd: float = 100.0):
        self.max_latency_seconds = max_latency_seconds
        self.max_cost_usd = max_cost_usd

    def check(self, record: CanonicalTelemetryRecord) -> GateResult:
        if record.latency_seconds < 0:
            return GateResult.reject("negative_latency")
        if record.latency_seconds > self.max_latency_seconds:
            # Almost always milliseconds mapped as seconds.
            return GateResult.reject("implausible_latency")
        if record.cost_usd < 0:
            return GateResult.reject("negative_cost")
        if record.cost_usd > self.max_cost_usd:
            return GateResult.reject("implausible_cost")

        for label, score in (
            ("groundedness", record.groundedness_score),
            ("context_relevance", record.context_relevance_score),
            ("answer_quality", record.answer_quality_score),
        ):
            if not 0.0 <= score <= 100.0:
                return GateResult.reject(f"score_out_of_range:{label}")

        return GateResult.ok()


class FreshnessGate(QualityGate):
    """
    Rejects records whose event time is unusable.

    Future timestamps mean a skewed exporter clock. Very old timestamps mean a
    backfill or a replayed queue — both are legitimate data, but folding them
    into a live rolling window would corrupt the current health picture.
    """

    name = "freshness"

    def __init__(self, max_age_seconds: float = 3600.0, max_skew_seconds: float = 120.0):
        self.max_age_seconds = max_age_seconds
        self.max_skew_seconds = max_skew_seconds

    def check(self, record: CanonicalTelemetryRecord) -> GateResult:
        now = time.time()
        if record.timestamp > now + self.max_skew_seconds:
            return GateResult.reject("timestamp_in_future")
        if record.timestamp < now - self.max_age_seconds:
            return GateResult.reject("stale_record")
        return GateResult.ok()


class DeduplicationGate(QualityGate):
    """
    Drops repeat deliveries.

    OTLP exporters and metrics agents both retry on failure, so at-least-once
    delivery is the norm. The seen-set is bounded and evicted oldest-first;
    duplicates arriving beyond that horizon are rare enough to accept.
    """

    name = "dedup"

    def __init__(self, capacity: int = 50_000):
        self.capacity = capacity
        self._seen: "OrderedDict[str, None]" = OrderedDict()

    def check(self, record: CanonicalTelemetryRecord) -> GateResult:
        if record.event_id in self._seen:
            self._seen.move_to_end(record.event_id)
            return GateResult.reject("duplicate_event")

        self._seen[record.event_id] = None
        if len(self._seen) > self.capacity:
            self._seen.popitem(last=False)
        return GateResult.ok()

    def reset(self) -> None:
        self._seen.clear()


class CompletenessGate(QualityGate):
    """
    Requires the metrics the detector actually alerts on.

    A record with no latency reading contributes nothing but dilutes the
    rolling window, pulling percentiles toward a value never observed.
    """

    name = "completeness"

    def __init__(self, required_fields: Optional[List[str]] = None):
        self.required_fields = required_fields or ["latency_seconds"]

    def check(self, record: CanonicalTelemetryRecord) -> GateResult:
        for field_name in self.required_fields:
            value = getattr(record, field_name, None)
            if value is None:
                return GateResult.reject(f"missing_field:{field_name}")
            if isinstance(value, (int, float)) and value == 0 and field_name == "latency_seconds":
                return GateResult.reject("zero_latency")
        return GateResult.ok()


@dataclass
class QualityReport:
    """Aggregate quality outcome for one pipeline run."""

    accepted: int = 0
    rejected: int = 0
    rejections_by_reason: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    dead_letter_samples: List[Dict[str, Any]] = field(default_factory=list)
    max_samples: int = 25

    def record_accept(self) -> None:
        self.accepted += 1

    def record_reject(self, record: CanonicalTelemetryRecord, gate: str, reason: str) -> None:
        self.rejected += 1
        self.rejections_by_reason[reason] += 1
        if len(self.dead_letter_samples) < self.max_samples:
            self.dead_letter_samples.append({
                "event_id": record.event_id,
                "source_name": record.source_name,
                "timestamp": record.timestamp,
                "gate": gate,
                "reason": reason,
            })

    @property
    def total(self) -> int:
        return self.accepted + self.rejected

    @property
    def acceptance_rate(self) -> float:
        return round((self.accepted / self.total) * 100.0, 2) if self.total else 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "total": self.total,
            "acceptance_rate_pct": self.acceptance_rate,
            "rejections_by_reason": dict(self.rejections_by_reason),
            "dead_letter_samples": self.dead_letter_samples,
        }


def default_gates() -> List[QualityGate]:
    """
    The standard gate chain, ordered cheapest-first.

    Dedup runs last so that a record rejected for being malformed does not
    consume a slot in the bounded seen-set.
    """
    return [CompletenessGate(), RangeGate(), FreshnessGate(), DeduplicationGate()]
