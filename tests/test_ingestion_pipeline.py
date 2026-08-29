"""
Telemetry Ingestion Pipeline Tests

Covers the four stages independently (mapping, connectors, quality gates,
transforms) and then end-to-end, including the property that matters most:
four vendors with four different unit conventions must produce identical
canonical values.
"""
import json
import time

import pytest

from ingestion import build_pipeline_from_config, load_source_specs
from ingestion.connectors import ConnectorConfig, build_connector
from ingestion.connectors.datadog import DatadogConnector
from ingestion.connectors.jsonl_file import JSONLFileConnector
from ingestion.connectors.otlp import OTLPConnector
from ingestion.connectors.prometheus import PrometheusConnector
from ingestion.connectors.series import SeriesColumn
from ingestion.mapping import CONVERTERS, FieldRule, MappingError, resolve_path
from ingestion.pipeline import IngestionPipeline
from ingestion.schema import CanonicalTelemetryRecord, SourceKind, make_event_id
from ingestion.sinks import MemorySink
from ingestion.transforms import (
    apply_transforms,
    clamp_scores,
    default_transforms,
    derive_cost,
    derive_total_tokens,
    normalize_environment,
)
from ingestion.validation import (
    CompletenessGate,
    DeduplicationGate,
    FreshnessGate,
    RangeGate,
    default_gates,
)


# --------------------------------------------------------------------------
# Mapping & unit conversion
# --------------------------------------------------------------------------

def test_converters_normalize_units_to_canonical_scale():
    assert CONVERTERS["ms_to_s"](2100) == pytest.approx(2.1)
    assert CONVERTERS["ns_to_s"](2_100_000_000) == pytest.approx(2.1)
    assert CONVERTERS["us_to_s"](2_100_000) == pytest.approx(2.1)
    assert CONVERTERS["cents_to_usd"](3.1) == pytest.approx(0.031)
    assert CONVERTERS["micros_to_usd"](31000) == pytest.approx(0.031)
    assert CONVERTERS["unit_to_pct"](0.945) == pytest.approx(94.5)


def test_iso8601_converter_round_trips_a_known_instant():
    from datetime import datetime, timezone
    expected = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    assert CONVERTERS["iso8601_to_epoch"]("2026-08-29T12:00:00Z") == pytest.approx(expected)
    assert CONVERTERS["iso8601_to_epoch"]("2026-08-29T12:00:00+00:00") == pytest.approx(expected)


def test_to_bool_treats_vendor_success_sentinels_as_not_an_error():
    to_bool = CONVERTERS["to_bool"]
    for ok_value in ("ok", "OK", "success", "false", 0, "", "unset"):
        assert to_bool(ok_value) is False, ok_value
    for error_value in ("ERROR", "timeout", 1, True):
        assert to_bool(error_value) is True, error_value


def test_otlp_unset_status_is_not_an_error():
    """
    OTLP leaves a successful span's status UNSET rather than marking it OK.
    Reading that as truthy would flag every healthy span as a failed request
    and drive the error rate to 100%.
    """
    to_bool = CONVERTERS["to_bool"]
    assert to_bool("STATUS_CODE_UNSET") is False
    assert to_bool("STATUS_CODE_OK") is False
    assert to_bool("STATUS_CODE_ERROR") is True


def test_healthy_otlp_spans_are_not_counted_as_errors():
    records = _connector_for("otlp").read().records
    assert not any(r.error for r in records), "healthy spans must not raise the error rate"


def test_resolve_path_handles_nesting_indexing_and_otlp_attributes():
    payload = {
        "a": {"b": {"c": 42}},
        "items": [{"name": "first"}, {"name": "second"}],
        "attributes": [
            {"key": "gen_ai.usage.total_tokens", "value": {"intValue": "1250"}},
            {"key": "rag.groundedness", "value": {"doubleValue": 0.945}},
        ],
    }
    assert resolve_path(payload, "a.b.c") == 42
    assert resolve_path(payload, "items.1.name") == "second"
    assert resolve_path(payload, "attributes[gen_ai.usage.total_tokens]") == "1250"
    assert resolve_path(payload, "attributes[rag.groundedness]") == 0.945
    assert resolve_path(payload, "a.missing.path") is None


def test_required_field_missing_raises_mapping_error():
    rule = FieldRule("timestamp", "ts", "to_float", required=True)
    with pytest.raises(MappingError, match="required field"):
        rule.apply({"other": 1})


def test_optional_field_falls_back_to_default():
    rule = FieldRule("cost_usd", "cost", "to_float", default=0.0)
    assert rule.apply({"other": 1}) == 0.0


# --------------------------------------------------------------------------
# Connectors
# --------------------------------------------------------------------------

def _connector_for(kind: str):
    spec = next(s for s in load_source_specs() if s["kind"] == kind)
    return build_connector(spec)


@pytest.mark.parametrize("kind", ["otlp", "prometheus", "datadog", "jsonl"])
def test_every_configured_source_yields_records(kind):
    result = _connector_for(kind).read()
    assert result.ok, result.fetch_error
    assert result.records, f"{kind} connector produced no records"


@pytest.mark.parametrize("kind", ["otlp", "prometheus", "datadog", "jsonl"])
def test_connector_stamps_source_identity_and_kind(kind):
    connector = _connector_for(kind)
    record = connector.read().records[0]
    assert record.source_kind == SourceKind(kind)
    assert record.source_name == connector.config.name
    assert record.event_id


def test_all_sources_agree_after_normalization():
    """
    The core promise of the canonical schema.

    Each fixture encodes the same underlying observations in a different unit
    convention: OTLP uses nanoseconds and 0-1 scores, Datadog uses milliseconds
    and micro-dollars, the app log uses cents. After normalization the values
    must be indistinguishable.
    """
    first_by_source = {}
    for kind in ("otlp", "prometheus", "datadog", "jsonl"):
        records = _connector_for(kind).read().records
        first_by_source[kind] = min(records, key=lambda r: r.timestamp)

    latencies = [r.latency_seconds for r in first_by_source.values()]
    costs = [r.cost_usd for r in first_by_source.values()]
    groundedness = [r.groundedness_score for r in first_by_source.values()]

    assert max(latencies) - min(latencies) < 0.01, f"latency disagreement: {latencies}"
    assert max(costs) - min(costs) < 0.001, f"cost disagreement: {costs}"
    assert max(groundedness) - min(groundedness) < 0.5, f"score disagreement: {groundedness}"


def test_otlp_computes_duration_from_span_endpoints():
    record = _connector_for("otlp").read().records[0]
    # Fixture spans are healthy-baseline requests around 2.1s.
    assert 1.0 < record.latency_seconds < 4.0


def test_otlp_lifts_resource_attributes_onto_each_span():
    record = _connector_for("otlp").read().records[0]
    assert record.service_name == "rag-service"


def test_prometheus_skips_nan_gaps():
    """A NaN scrape gap must not become a 0.0 reading."""
    connector = _connector_for("prometheus")
    for record in connector.read().records:
        assert record.cost_usd >= 0.0
        assert record.cost_usd == record.cost_usd  # NaN != NaN


def test_datadog_null_points_are_dropped_not_zeroed():
    for record in _connector_for("datadog").read().records:
        assert record.latency_seconds > 0.0


def test_watermark_prevents_replaying_the_same_records():
    connector = _connector_for("otlp")
    first = connector.read().records
    second = connector.read().records
    assert first, "expected records on first read"
    assert not second, "watermark should suppress already-emitted records"


def test_reset_watermark_allows_replay():
    connector = _connector_for("otlp")
    assert connector.read().records
    connector.reset_watermark()
    assert connector.read().records


def test_replay_rebasing_places_fixtures_in_the_present():
    """Committed fixtures must not age out of the freshness window."""
    record = _connector_for("jsonl").read().records[0]
    assert abs(record.timestamp - time.time()) < 3600


def test_unreachable_source_is_isolated_not_fatal():
    connector = build_connector({
        "kind": "otlp",
        "name": "broken-source",
        "fixture_path": "/nonexistent/path/spans.json",
    })
    result = connector.read()
    assert not result.ok
    assert "FileNotFoundError" in result.fetch_error


def test_connector_without_origin_reports_configuration_error():
    connector = OTLPConnector(ConnectorConfig(name="no-origin"))
    result = connector.read()
    assert not result.ok
    assert "neither an endpoint nor a fixture_path" in result.fetch_error


def test_unknown_connector_kind_is_rejected():
    with pytest.raises(ValueError, match="unknown connector kind"):
        build_connector({"kind": "splunk", "name": "x"})


# --------------------------------------------------------------------------
# Series pivot
# --------------------------------------------------------------------------

def test_series_pivot_joins_independent_series_on_a_time_grid():
    connector = PrometheusConnector(
        ConnectorConfig(name="t", fixture_path="unused"), align_seconds=10.0
    )
    rows = connector.pivot([
        ("rag_request_latency_p95_seconds", [(1000.0, 2.1), (1010.0, 2.2)]),
        ("rag_request_cost_usd", [(1000.0, 0.03), (1010.0, 0.032)]),
    ])
    assert len(rows) == 2
    assert rows[0]["latency_seconds"] == pytest.approx(2.1)
    assert rows[0]["cost_usd"] == pytest.approx(0.03)


def test_series_pivot_drops_buckets_missing_a_required_column():
    """
    A bucket with cost but no latency must be dropped, not defaulted.

    A zero-filled latency would read to the detector as an impossibly fast
    request and drag the p95 down, masking a real regression.
    """
    connector = PrometheusConnector(
        ConnectorConfig(name="t", fixture_path="unused"), align_seconds=10.0
    )
    rows = connector.pivot([
        ("rag_request_latency_p95_seconds", [(1000.0, 2.1)]),
        ("rag_request_cost_usd", [(1000.0, 0.03), (2000.0, 0.04)]),
    ])
    assert len(rows) == 1
    assert rows[0]["timestamp"] == pytest.approx(1000.0)


def test_series_pivot_snaps_misaligned_timestamps_into_one_bucket():
    connector = DatadogConnector(
        ConnectorConfig(name="t", fixture_path="unused"), align_seconds=10.0
    )
    rows = connector.pivot([
        ("rag.request.latency.p95", [(1002.0, 2100.0)]),
        ("rag.request.cost", [(999.0, 31000.0)]),
    ])
    assert len(rows) == 1, "near-simultaneous points should share a bucket"
    assert rows[0]["latency_seconds"] == pytest.approx(2.1)
    assert rows[0]["cost_usd"] == pytest.approx(0.031)


def test_unmapped_upstream_metrics_are_ignored():
    connector = PrometheusConnector(
        ConnectorConfig(name="t", fixture_path="unused"), align_seconds=10.0
    )
    rows = connector.pivot([
        ("rag_request_latency_p95_seconds", [(1000.0, 2.1)]),
        ("node_cpu_seconds_total", [(1000.0, 99.0)]),
    ])
    assert "node_cpu_seconds_total" not in rows[0]


# --------------------------------------------------------------------------
# Quality gates
# --------------------------------------------------------------------------

def _record(**overrides) -> CanonicalTelemetryRecord:
    base = {
        "event_id": make_event_id("test", time.time()),
        "timestamp": time.time(),
        "source_name": "test",
        "latency_seconds": 2.1,
        "cost_usd": 0.03,
        "total_tokens": 1250,
        "retrieved_chunks_count": 5,
        "groundedness_score": 94.5,
    }
    base.update(overrides)
    return CanonicalTelemetryRecord(**base)


def test_range_gate_rejects_negative_and_implausible_values():
    gate = RangeGate()
    assert gate.check(_record()).accepted
    assert gate.check(_record(latency_seconds=-1.0)).reason == "negative_latency"
    assert gate.check(_record(latency_seconds=9999.0)).reason == "implausible_latency"
    assert gate.check(_record(cost_usd=-0.5)).reason == "negative_cost"
    assert gate.check(_record(groundedness_score=9450.0)).reason.startswith("score_out_of_range")


def test_range_gate_allows_genuinely_slow_requests_through():
    """An incident-level latency is signal, not bad data — it must reach the detector."""
    assert RangeGate().check(_record(latency_seconds=11.8)).accepted


def test_freshness_gate_rejects_skewed_and_stale_timestamps():
    gate = FreshnessGate(max_age_seconds=3600, max_skew_seconds=120)
    assert gate.check(_record()).accepted
    assert gate.check(_record(timestamp=time.time() + 600)).reason == "timestamp_in_future"
    assert gate.check(_record(timestamp=time.time() - 7200)).reason == "stale_record"


def test_dedup_gate_rejects_repeat_delivery():
    gate = DeduplicationGate()
    record = _record()
    assert gate.check(record).accepted
    assert gate.check(record).reason == "duplicate_event"


def test_dedup_gate_evicts_oldest_beyond_capacity():
    gate = DeduplicationGate(capacity=2)
    first = _record(event_id="a")
    gate.check(first)
    gate.check(_record(event_id="b"))
    gate.check(_record(event_id="c"))
    # "a" was evicted, so it is no longer recognised as a duplicate.
    assert gate.check(first).accepted


def test_completeness_gate_rejects_missing_latency():
    gate = CompletenessGate()
    assert gate.check(_record()).accepted
    assert gate.check(_record(latency_seconds=0.0)).reason == "zero_latency"


# --------------------------------------------------------------------------
# Transforms
# --------------------------------------------------------------------------

def test_derive_total_tokens_from_components():
    record = derive_total_tokens(_record(total_tokens=0, prompt_tokens=1000, output_tokens=250))
    assert record.total_tokens == 1250


def test_derive_cost_only_when_source_reported_none():
    derived = derive_cost(_record(cost_usd=0.0, prompt_tokens=1000, output_tokens=250))
    assert derived.cost_usd > 0

    reported = derive_cost(_record(cost_usd=0.0295, prompt_tokens=1000, output_tokens=250))
    assert reported.cost_usd == pytest.approx(0.0295), "must not overwrite a reported cost"


def test_normalize_environment_collapses_aliases():
    for alias in ("prod", "PROD", "live", "prd"):
        assert normalize_environment(_record(environment=alias)).environment == "production"
    assert normalize_environment(_record(environment="stg")).environment == "staging"


def test_clamp_scores_fixes_rounding_drift_but_not_unit_errors():
    assert clamp_scores(_record(groundedness_score=100.0000001)).groundedness_score == 100.0
    # A 0-1 score mapped as a percentage is a unit bug; leave it for RangeGate.
    assert clamp_scores(_record(groundedness_score=9450.0)).groundedness_score == 9450.0


def test_transform_chain_is_resilient_to_a_failing_transform():
    def explodes(_record_in):
        raise RuntimeError("boom")

    record = apply_transforms(_record(total_tokens=0, prompt_tokens=10, output_tokens=5),
                              [explodes, derive_total_tokens])
    assert record.total_tokens == 15


# --------------------------------------------------------------------------
# End-to-end pipeline
# --------------------------------------------------------------------------

def test_pipeline_ingests_every_configured_source():
    sink = MemorySink()
    pipeline = build_pipeline_from_config(sinks=[sink])
    report = pipeline.run_once()

    assert len(report.sources) == 4
    assert report.healthy_sources == 4
    assert report.records_loaded > 100
    assert {r.source_kind.value for r in sink.records} == {"otlp", "prometheus", "datadog", "jsonl"}


def test_pipeline_quarantines_the_seeded_bad_records():
    """The fixtures carry one record per failure mode; each must be caught."""
    pipeline = build_pipeline_from_config(sinks=[MemorySink()])
    report = pipeline.run_once()
    reasons = report.quality.rejections_by_reason

    assert reasons.get("negative_latency") == 1
    assert reasons.get("zero_latency") == 1
    assert reasons.get("duplicate_event") == 1
    assert any(r.startswith("score_out_of_range") for r in reasons)
    assert report.quality.dead_letter_samples, "rejections must be inspectable"


def test_pipeline_loads_records_in_time_order():
    """The collector keeps a rolling window, so out-of-order loads corrupt percentiles."""
    sink = MemorySink()
    build_pipeline_from_config(sinks=[sink]).run_once()
    timestamps = [r.timestamp for r in sink.records]
    assert timestamps == sorted(timestamps)


def test_pipeline_report_accounting_is_internally_consistent():
    report = build_pipeline_from_config(sinks=[MemorySink()]).run_once()
    assert report.quality.accepted + report.quality.rejected == report.quality.total
    assert report.quality.accepted == report.records_loaded
    assert sum(s.records_accepted for s in report.sources) == report.quality.accepted


def test_one_broken_source_does_not_stop_the_others():
    specs = load_source_specs()
    connectors = [build_connector(s) for s in specs]
    connectors.append(build_connector({
        "kind": "prometheus", "name": "down-backend", "fixture_path": "/nope.json",
    }))

    sink = MemorySink()
    report = IngestionPipeline(connectors=connectors, sinks=[sink]).run_once()

    assert report.healthy_sources == 4
    assert len(report.sources) == 5
    assert report.records_loaded > 100, "healthy sources must still load"

    broken = next(s for s in report.sources if s.source_name == "down-backend")
    assert broken.fetch_error is not None


def test_disabled_sources_are_skipped():
    specs = [dict(s) for s in load_source_specs()]
    for spec in specs:
        if spec["kind"] != "jsonl":
            spec["enabled"] = False

    pipeline = IngestionPipeline([build_connector(s) for s in specs], sinks=[MemorySink()])
    report = pipeline.run_once()
    assert len(report.sources) == 1
    assert report.sources[0].source_kind == "jsonl"


def test_pipeline_reset_enables_a_genuine_replay():
    """
    Rewinding must clear watermarks *and* dedup state.

    Clearing only the watermarks would re-read every record and then reject all
    of them as duplicates — indistinguishable from a broken pipeline.
    """
    sink = MemorySink()
    pipeline = build_pipeline_from_config(sinks=[sink])

    first = pipeline.run_once()
    assert first.records_loaded > 0

    assert pipeline.run_once().records_loaded == 0, "watermark should suppress a re-poll"

    pipeline.reset()
    replayed = pipeline.run_once()
    assert replayed.records_loaded == first.records_loaded


def test_describe_sources_reports_replay_versus_live_mode():
    pipeline = build_pipeline_from_config(sinks=[MemorySink()])
    described = pipeline.describe_sources()
    assert len(described) == 4
    assert all(d["mode"] == "replay" for d in described)
    assert {d["kind"] for d in described} == {"otlp", "prometheus", "datadog", "jsonl"}


def test_a_failing_sink_is_reported_without_losing_the_run():
    class ExplodingSink(MemorySink):
        name = "exploding"

        def write(self, records):
            raise RuntimeError("downstream unavailable")

    good = MemorySink()
    specs = load_source_specs()
    pipeline = IngestionPipeline(
        [build_connector(s) for s in specs], sinks=[ExplodingSink(), good]
    )
    report = pipeline.run_once()

    assert report.sinks_written["exploding"] == -1
    assert report.sinks_written["memory"] > 0
    assert good.records, "a healthy sink must still receive the batch"


# --------------------------------------------------------------------------
# Integration with the existing observability layer
# --------------------------------------------------------------------------

def test_ingested_records_reach_the_metrics_collector():
    """The seam that makes ingested telemetry drive the existing agent workflow."""
    from observability.metrics_collector import MetricsCollector
    from ingestion.sinks import MetricsCollectorSink

    collector = MetricsCollector()
    before = len(collector.raw_records)

    specs = load_source_specs()
    pipeline = IngestionPipeline(
        [build_connector(s) for s in specs], sinks=[MetricsCollectorSink(collector)]
    )
    report = pipeline.run_once()

    assert len(collector.raw_records) > before
    assert report.sinks_written["metrics_collector"] == report.records_loaded

    metrics = collector.get_current_metrics()
    assert metrics["p95_latency"] > 0
    assert metrics["sample_count"] > 0


def test_canonical_record_projects_onto_the_collector_event_shape():
    event = _record().to_metrics_event()
    required = {
        "latency_seconds", "cost_usd", "total_tokens", "retrieved_chunks_count",
        "groundedness_score", "context_relevance_score", "answer_quality_score",
        "error", "timestamp",
    }
    assert required.issubset(event.keys())


def test_event_ids_are_stable_across_identical_payloads():
    """Deterministic ids are what make at-least-once delivery deduplicable."""
    assert make_event_id("s", 1000.0, "trace-1") == make_event_id("s", 1000.0, "trace-1")
    assert make_event_id("s", 1000.0, "trace-1") != make_event_id("s", 1000.0, "trace-2")


def test_source_catalog_is_valid_json_and_fully_resolvable():
    specs = load_source_specs()
    assert len(specs) == 4
    for spec in specs:
        assert "kind" in spec and "name" in spec
        build_connector(spec)  # must not raise
