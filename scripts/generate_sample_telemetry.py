#!/usr/bin/env python3
"""
Sample Telemetry Fixture Generator

Produces one captured payload per supported vendor, in that vendor's real wire
format, so the ingestion pipeline can be demonstrated and tested end-to-end
without vendor credentials or network access.

Each source deliberately uses a different unit convention (seconds vs
milliseconds, dollars vs cents vs micro-dollars, 0-1 ratios vs 0-100
percentages) so the normalization layer is exercised rather than bypassed.

A small number of intentionally malformed records are included to exercise the
quality gates: a unit-error score, a negative latency, a duplicate delivery,
and a record with no latency at all. These are expected to be rejected — the
counts in the pipeline report are part of what the demo shows.

Fixtures use a fixed reference timestamp and are re-based onto the current
clock at read time (see `ConnectorConfig.rebase_replay_to_now`), so they stay
valid indefinitely once committed.

Usage:
    python scripts/generate_sample_telemetry.py
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "data" / "sample_sources"

# Fixed reference point keeps regeneration deterministic and diffs readable.
REFERENCE_TIME = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
RECORD_COUNT = 60
STEP_SECONDS = 10

random.seed(20260829)


def healthy_sample(index: int) -> Dict[str, float]:
    """One healthy request observation in canonical units."""
    return {
        "latency_s": round(random.normalvariate(2.1, 0.18), 3),
        "cost_usd": round(random.normalvariate(0.031, 0.003), 5),
        "prompt_tokens": int(random.normalvariate(1050, 80)),
        "output_tokens": int(random.normalvariate(240, 30)),
        "chunks": 5,
        "groundedness": round(random.normalvariate(94.5, 1.4), 2),
        "context_relevance": round(random.normalvariate(92.0, 1.8), 2),
        "answer_quality": round(random.normalvariate(94.0, 1.6), 2),
    }


def build_samples() -> List[Dict[str, Any]]:
    samples = []
    for i in range(RECORD_COUNT):
        sample = healthy_sample(i)
        sample["offset_s"] = i * STEP_SECONDS
        sample["index"] = i
        samples.append(sample)
    return samples


# --------------------------------------------------------------------------
# OTLP / OpenTelemetry spans
# --------------------------------------------------------------------------

def _otlp_attr(key: str, value: Any) -> Dict[str, Any]:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


def write_otlp(samples: List[Dict[str, Any]]) -> Path:
    """OTLP/JSON trace export using GenAI semantic conventions (0-1 scores)."""
    spans = []
    for sample in samples[:30]:
        start = REFERENCE_TIME + timedelta(seconds=sample["offset_s"])
        start_nanos = int(start.timestamp() * 1_000_000_000)
        duration_nanos = int(sample["latency_s"] * 1_000_000_000)

        spans.append({
            "traceId": f"{sample['index']:032x}",
            "spanId": f"{sample['index']:016x}",
            "name": "rag.query",
            "kind": "SPAN_KIND_SERVER",
            "startTimeUnixNano": str(start_nanos),
            "endTimeUnixNano": str(start_nanos + duration_nanos),
            "attributes": [
                _otlp_attr("gen_ai.system", "anthropic"),
                _otlp_attr("gen_ai.usage.input_tokens", sample["prompt_tokens"]),
                _otlp_attr("gen_ai.usage.output_tokens", sample["output_tokens"]),
                _otlp_attr("gen_ai.usage.total_tokens", sample["prompt_tokens"] + sample["output_tokens"]),
                _otlp_attr("gen_ai.usage.cost_usd", sample["cost_usd"]),
                _otlp_attr("rag.retrieved_chunks", sample["chunks"]),
                # This exporter reports the RAG triad on a 0-1 scale.
                _otlp_attr("rag.groundedness", round(sample["groundedness"] / 100.0, 4)),
                _otlp_attr("rag.context_relevance", round(sample["context_relevance"] / 100.0, 4)),
                _otlp_attr("rag.answer_quality", round(sample["answer_quality"] / 100.0, 4)),
            ],
            "status": {"code": "STATUS_CODE_UNSET"},
        })

    # Dirty record: groundedness exported on the wrong scale (94.5 as a "ratio"
    # becomes 9450%). Expected rejection: score_out_of_range.
    bad_start = int((REFERENCE_TIME + timedelta(seconds=310)).timestamp() * 1_000_000_000)
    spans.append({
        "traceId": f"{999:032x}",
        "spanId": f"{999:016x}",
        "name": "rag.query",
        "startTimeUnixNano": str(bad_start),
        "endTimeUnixNano": str(bad_start + 2_000_000_000),
        "attributes": [
            _otlp_attr("gen_ai.usage.input_tokens", 1000),
            _otlp_attr("gen_ai.usage.output_tokens", 200),
            _otlp_attr("rag.retrieved_chunks", 5),
            _otlp_attr("rag.groundedness", 94.5),
        ],
        "status": {"code": "STATUS_CODE_UNSET"},
    })

    payload = {
        "resourceSpans": [{
            "resource": {
                "attributes": [
                    _otlp_attr("service.name", "rag-service"),
                    _otlp_attr("deployment.environment", "production"),
                ]
            },
            "scopeSpans": [{
                "scope": {"name": "sentinel.instrumentation.rag", "version": "1.0.0"},
                "spans": spans,
            }],
        }]
    }

    path = OUTPUT_DIR / "otlp_spans.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Prometheus range query
# --------------------------------------------------------------------------

def write_prometheus(samples: List[Dict[str, Any]]) -> Path:
    """Prometheus query_range matrix response (string values, 0-1 ratios)."""
    def series(metric_name: str, key: str, scale: float = 1.0) -> Dict[str, Any]:
        return {
            "metric": {
                "__name__": metric_name,
                "service": "rag-service",
                "env": "prod",
                "instance": "rag-service-7d9f:8000",
            },
            "values": [
                [
                    int((REFERENCE_TIME + timedelta(seconds=s["offset_s"])).timestamp()),
                    str(round(s[key] * scale, 6)),
                ]
                for s in samples
            ],
        }

    result = [
        series("rag_request_latency_p95_seconds", "latency_s"),
        series("rag_request_cost_usd", "cost_usd"),
        series("rag_retrieved_chunks", "chunks"),
        series("rag_groundedness_ratio", "groundedness", scale=0.01),
        series("rag_context_relevance_ratio", "context_relevance", scale=0.01),
        series("rag_answer_quality_ratio", "answer_quality", scale=0.01),
    ]

    # Prometheus reports scrape gaps as NaN; the connector must skip them
    # rather than pivoting a NaN into the record.
    result[1]["values"][5][1] = "NaN"
    result[1]["values"][6][1] = "NaN"

    payload = {"status": "success", "data": {"resultType": "matrix", "result": result}}

    path = OUTPUT_DIR / "prometheus_range.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Datadog timeseries
# --------------------------------------------------------------------------

def write_datadog(samples: List[Dict[str, Any]]) -> Path:
    """Datadog timeseries response (epoch ms, latency in ms, cost in micros)."""
    def series(metric_name: str, key: str, scale: float = 1.0) -> Dict[str, Any]:
        return {
            "metric": metric_name,
            "scope": "service:rag-service,env:production",
            "tags": ["service:rag-service", "env:production"],
            "pointlist": [
                [
                    int((REFERENCE_TIME + timedelta(seconds=s["offset_s"])).timestamp() * 1000),
                    round(s[key] * scale, 4),
                ]
                for s in samples
            ],
        }

    payload = {
        "status": "ok",
        "series": [
            series("rag.request.latency.p95", "latency_s", scale=1000.0),
            series("rag.request.cost", "cost_usd", scale=1_000_000.0),
            series("rag.retrieval.chunks", "chunks"),
            series("rag.eval.groundedness", "groundedness"),
            series("rag.eval.context_relevance", "context_relevance"),
            series("rag.eval.answer_quality", "answer_quality"),
        ],
    }

    # Datadog nulls out interpolation gaps.
    payload["series"][0]["pointlist"][12][1] = None

    path = OUTPUT_DIR / "datadog_series.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Application JSONL logs
# --------------------------------------------------------------------------

def write_jsonl(samples: List[Dict[str, Any]]) -> Path:
    """Application request log (ISO timestamps, latency in ms, cost in cents)."""
    lines: List[str] = []

    for sample in samples[:40]:
        ts = REFERENCE_TIME + timedelta(seconds=sample["offset_s"])
        lines.append(json.dumps({
            "ts": ts.isoformat().replace("+00:00", "Z"),
            "request_id": f"req-{sample['index']:05d}",
            "service": "rag-service",
            "env": "production",
            "latency_ms": round(sample["latency_s"] * 1000.0, 1),
            "cost_cents": round(sample["cost_usd"] * 100.0, 5),
            "tokens": {
                "prompt": sample["prompt_tokens"],
                "completion": sample["output_tokens"],
                "total": sample["prompt_tokens"] + sample["output_tokens"],
            },
            "retrieval": {"chunks": sample["chunks"], "index": "kb-prod-v4"},
            "eval": {
                "groundedness_pct": sample["groundedness"],
                "context_relevance_pct": sample["context_relevance"],
                "answer_quality_pct": sample["answer_quality"],
            },
            "status": "ok",
        }))

    # --- Deliberately malformed records, one per gate ---------------------

    # Negative latency from a clock going backwards mid-request.
    lines.append(json.dumps({
        "ts": (REFERENCE_TIME + timedelta(seconds=410)).isoformat().replace("+00:00", "Z"),
        "request_id": "req-90001",
        "service": "rag-service", "env": "production",
        "latency_ms": -145.0,
        "cost_cents": 3.1,
        "tokens": {"prompt": 1000, "completion": 200, "total": 1200},
        "retrieval": {"chunks": 5},
        "eval": {"groundedness_pct": 94.0, "context_relevance_pct": 92.0, "answer_quality_pct": 93.0},
        "status": "ok",
    }))

    # No latency recorded at all — the field the detector alerts on.
    lines.append(json.dumps({
        "ts": (REFERENCE_TIME + timedelta(seconds=420)).isoformat().replace("+00:00", "Z"),
        "request_id": "req-90002",
        "service": "rag-service", "env": "production",
        "cost_cents": 2.9,
        "tokens": {"prompt": 980, "completion": 210, "total": 1190},
        "retrieval": {"chunks": 5},
        "eval": {"groundedness_pct": 93.5, "context_relevance_pct": 91.0, "answer_quality_pct": 92.5},
        "status": "ok",
    }))

    # Exact duplicate of the previous line's neighbour: at-least-once redelivery.
    duplicate_source = json.loads(lines[10])
    lines.append(json.dumps(duplicate_source))

    path = OUTPUT_DIR / "rag_events.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    samples = build_samples()

    written = [
        write_otlp(samples),
        write_prometheus(samples),
        write_datadog(samples),
        write_jsonl(samples),
    ]

    print("Generated telemetry fixtures:")
    for path in written:
        size_kb = path.stat().st_size / 1024.0
        print(f"  {path.relative_to(REPO_ROOT)}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
