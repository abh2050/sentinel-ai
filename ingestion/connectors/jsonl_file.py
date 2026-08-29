"""
JSONL Application Log Connector

Reads newline-delimited JSON emitted directly by an application — the most
common "we already log this, just read it" integration path, and the one that
needs no vendor account at all.

Reads incrementally by byte offset so a growing log file is tailed across polls
instead of re-parsed from the top.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ingestion.connectors.base import ConnectorConfig, TelemetryConnector
from ingestion.mapping import FieldRule, SourceMapping
from ingestion.schema import SourceKind

# This source reports latency in milliseconds, cost in cents, and quality
# scores already on a 0-100 scale — a deliberately different unit mix from the
# OTLP source, to exercise unit reconciliation.
JSONL_MAPPING = SourceMapping(
    name="app_jsonl_logs",
    rules=[
        FieldRule("timestamp", "ts", "iso8601_to_epoch", required=True),
        FieldRule("trace_id", "request_id", "to_str"),
        FieldRule("service_name", "service", "to_str"),
        FieldRule("environment", "env", "to_str"),
        FieldRule("latency_seconds", "latency_ms", "ms_to_s"),
        FieldRule("cost_usd", "cost_cents", "cents_to_usd"),
        FieldRule("prompt_tokens", "tokens.prompt", "to_int"),
        FieldRule("output_tokens", "tokens.completion", "to_int"),
        FieldRule("total_tokens", "tokens.total", "to_int"),
        FieldRule("retrieved_chunks_count", "retrieval.chunks", "to_int"),
        FieldRule("groundedness_score", "eval.groundedness_pct", "pct_to_pct"),
        FieldRule("context_relevance_score", "eval.context_relevance_pct", "pct_to_pct"),
        FieldRule("answer_quality_score", "eval.answer_quality_pct", "pct_to_pct"),
        FieldRule("error", "status", "to_bool", default=False),
        FieldRule("error_type", "error_kind", "to_str"),
    ],
)


class JSONLFileConnector(TelemetryConnector):
    """Tails a newline-delimited JSON log file."""

    def __init__(self, config: ConnectorConfig):
        config.kind = SourceKind.JSONL
        super().__init__(config)
        self._byte_offset = 0

    @property
    def mapping(self) -> SourceMapping:
        return JSONL_MAPPING

    def fetch_raw(self) -> Any:
        path = Path(self.config.fixture_path or "")
        if not path.exists():
            raise FileNotFoundError(f"log file not found: {path}")

        # A shrinking file means rotation or truncation; restart from the top.
        if path.stat().st_size < self._byte_offset:
            self._byte_offset = 0

        records: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(self._byte_offset)
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    # A partial trailing line is normal when tailing an active
                    # writer; stop here and resume from this offset next poll.
                    break
            self._byte_offset = handle.tell()

        return records

    def reset_watermark(self) -> None:
        super().reset_watermark()
        self._byte_offset = 0
