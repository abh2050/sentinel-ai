"""
OpenTelemetry (OTLP/JSON) Connector

Ingests OTLP trace exports and reads the GenAI semantic-convention attributes
(`gen_ai.*`) that LLM and RAG instrumentation emits.

OTLP nests spans under resourceSpans -> scopeSpans -> spans, and encodes
attributes as a key/value list rather than an object, so this connector
flattens the structure into one record per span before mapping runs.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ingestion.connectors.base import ConnectorConfig, TelemetryConnector
from ingestion.mapping import FieldRule, SourceMapping
from ingestion.schema import SourceKind

# GenAI semantic conventions:
# https://opentelemetry.io/docs/specs/semconv/gen-ai/
OTLP_MAPPING = SourceMapping(
    name="otlp_genai_spans",
    rules=[
        FieldRule("timestamp", "startTimeUnixNano", "epoch_ns_to_s", required=True),
        FieldRule("trace_id", "traceId", "to_str"),
        FieldRule("latency_seconds", "_duration_nanos", "ns_to_s"),
        FieldRule("service_name", "_resource.service.name", "to_str"),
        FieldRule("environment", "_resource.deployment.environment", "to_str"),
        FieldRule("prompt_tokens", "attributes[gen_ai.usage.input_tokens]", "to_int"),
        FieldRule("output_tokens", "attributes[gen_ai.usage.output_tokens]", "to_int"),
        FieldRule("total_tokens", "attributes[gen_ai.usage.total_tokens]", "to_int"),
        FieldRule("cost_usd", "attributes[gen_ai.usage.cost_usd]", "to_float"),
        FieldRule("retrieved_chunks_count", "attributes[rag.retrieved_chunks]", "to_int"),
        # This vendor emits the RAG triad on a 0-1 scale.
        FieldRule("groundedness_score", "attributes[rag.groundedness]", "unit_to_pct"),
        FieldRule("context_relevance_score", "attributes[rag.context_relevance]", "unit_to_pct"),
        FieldRule("answer_quality_score", "attributes[rag.answer_quality]", "unit_to_pct"),
        FieldRule("error", "status.code", "to_bool", default=False),
        FieldRule("error_type", "attributes[error.type]", "to_str"),
    ],
)


class OTLPConnector(TelemetryConnector):
    """Reads OTLP/JSON span exports from a collector endpoint or a fixture."""

    def __init__(self, config: ConnectorConfig):
        config.kind = SourceKind.OTLP
        super().__init__(config)

    @property
    def mapping(self) -> SourceMapping:
        return OTLP_MAPPING

    def fetch_raw(self) -> Any:
        payload = self._load_payload()
        return self._flatten_spans(payload)

    @staticmethod
    def _flatten_spans(payload: Any) -> List[Dict[str, Any]]:
        """
        Collapse resourceSpans -> scopeSpans -> spans into a flat span list.

        Resource-level attributes (service name, environment) live above the
        span, so they are attached to each span under `_resource` to keep the
        mapping paths flat. Span duration is precomputed the same way, since
        OTLP stores start and end instants rather than an elapsed value.
        """
        flattened: List[Dict[str, Any]] = []

        for resource_span in payload.get("resourceSpans", []) or []:
            resource_attrs = _attributes_to_dict(
                (resource_span.get("resource") or {}).get("attributes", [])
            )

            for scope_span in resource_span.get("scopeSpans", []) or []:
                for span in scope_span.get("spans", []) or []:
                    enriched = dict(span)
                    enriched["_resource"] = resource_attrs

                    start = _as_int(span.get("startTimeUnixNano"))
                    end = _as_int(span.get("endTimeUnixNano"))
                    enriched["_duration_nanos"] = max(0, end - start) if start and end else 0

                    flattened.append(enriched)

        return flattened


def _attributes_to_dict(attributes: Any) -> Dict[str, Any]:
    """Turn an OTLP attribute list into a plain dict, unwrapping AnyValue."""
    result: Dict[str, Any] = {}
    if not isinstance(attributes, list):
        return result

    for entry in attributes:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        value = entry.get("value")
        if key is None:
            continue
        if isinstance(value, dict):
            for union_key in ("stringValue", "intValue", "doubleValue", "boolValue"):
                if union_key in value:
                    result[key] = value[union_key]
                    break
        else:
            result[key] = value
    return result


def _as_int(value: Any) -> int:
    """OTLP encodes 64-bit nanosecond timestamps as strings to avoid precision loss."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
