"""
Canonical Telemetry Schema

Every upstream source — OTLP spans, Prometheus range queries, Datadog series,
application JSONL logs — is normalized into a single `CanonicalTelemetryRecord`
before it reaches the observability layer.

This is the contract that lets SentinelAI treat heterogeneous vendors uniformly:
downstream code (metrics collector, anomaly detector, agent pipeline) only ever
sees canonical records and never learns which vendor produced them.

Unit conventions (enforced at normalization time, not by convention):
  - latency          : seconds (float)
  - cost             : USD (float)
  - quality scores   : 0-100 percentage scale (float)
  - timestamp        : POSIX epoch seconds (float, UTC)
"""
from __future__ import annotations

import hashlib
import time
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    """Telemetry source families SentinelAI can ingest from."""
    OTLP = "otlp"
    PROMETHEUS = "prometheus"
    DATADOG = "datadog"
    JSONL = "jsonl"
    CUSTOM = "custom"


class CanonicalTelemetryRecord(BaseModel):
    """
    One observation of one AI/RAG request, normalized across vendors.

    Records are the atomic unit of the pipeline: connectors emit them,
    quality gates accept or quarantine them, and sinks load them.
    """

    # --- Identity & lineage -------------------------------------------------
    event_id: str = Field(description="Stable dedup key; derived from source + trace + timestamp")
    timestamp: float = Field(description="Event time, POSIX epoch seconds (UTC)")
    ingested_at: float = Field(default_factory=time.time, description="Pipeline arrival time")
    source_name: str = Field(description="Configured connector instance name")
    source_kind: SourceKind = Field(default=SourceKind.CUSTOM)
    trace_id: Optional[str] = Field(default=None, description="Upstream trace/span correlation id")

    # --- Service context ----------------------------------------------------
    service_name: str = Field(default="unknown-service")
    environment: str = Field(default="production")

    # Value ranges are deliberately unconstrained here. The schema's job is
    # shape and units; deciding whether a value is *plausible* belongs to the
    # quality gates, which quarantine a bad record with a named reason.
    # Enforcing bounds at parse time instead would reject those records as
    # unparseable, collapsing every distinct data-quality failure into one
    # opaque "malformed" bucket and leaving nothing to report on.

    # --- Core performance ---------------------------------------------------
    latency_seconds: float = Field(default=0.0)
    cost_usd: float = Field(default=0.0)

    # --- LLM token accounting ----------------------------------------------
    prompt_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)

    # --- RAG retrieval ------------------------------------------------------
    retrieved_chunks_count: int = Field(default=0)

    # --- RAG Triad quality (0-100) -----------------------------------------
    groundedness_score: float = Field(default=100.0)
    context_relevance_score: float = Field(default=100.0)
    answer_quality_score: float = Field(default=100.0)

    # --- Status -------------------------------------------------------------
    error: bool = Field(default=False)
    error_type: Optional[str] = Field(default=None)

    def to_metrics_event(self) -> Dict[str, Any]:
        """
        Project onto the event shape `MetricsCollector.record_query_event` expects.

        Keeping this projection in one place means the collector's interface can
        evolve without every connector needing to know about it.
        """
        return {
            "latency_seconds": self.latency_seconds,
            "cost_usd": self.cost_usd,
            "total_tokens": self.total_tokens,
            "retrieved_chunks_count": self.retrieved_chunks_count,
            "groundedness_score": self.groundedness_score,
            "context_relevance_score": self.context_relevance_score,
            "answer_quality_score": self.answer_quality_score,
            "error": self.error,
            "timestamp": self.timestamp,
        }


def make_event_id(source_name: str, timestamp: float, trace_id: Optional[str] = None) -> str:
    """
    Build a deterministic dedup key.

    Replaying the same upstream payload must produce the same ids, otherwise
    at-least-once delivery from the source turns into duplicate metrics.
    """
    basis = f"{source_name}|{trace_id or ''}|{timestamp:.6f}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:20]
