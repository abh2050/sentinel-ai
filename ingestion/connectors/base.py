"""
Connector Base Class

A connector is responsible for exactly two things:
  1. Producing a raw vendor payload (from HTTP, a file, or a queue).
  2. Declaring the `SourceMapping` that translates that payload to canonical form.

Everything else — record selection, field mapping, id assignment, checkpointing —
is handled here so that adding a vendor stays cheap.

Every remote connector supports an offline `fixture_path` in place of a live
`endpoint`. That keeps the whole pipeline runnable (and testable in CI) with no
network access and no vendor credentials.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ingestion.mapping import MappingError, SourceMapping
from ingestion.schema import CanonicalTelemetryRecord, SourceKind, make_event_id


@dataclass
class ConnectorConfig:
    """Runtime configuration for one connector instance."""
    name: str
    kind: SourceKind = SourceKind.CUSTOM
    enabled: bool = True

    # Exactly one of these is used as the payload origin.
    endpoint: Optional[str] = None
    fixture_path: Optional[str] = None

    # Service context stamped onto every record from this source.
    service_name: str = "rag-service"
    environment: str = "production"

    # Live-fetch tuning.
    timeout_seconds: float = 10.0
    headers: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, Any] = field(default_factory=dict)

    # Cap on records pulled per run, protecting the pipeline from a
    # backfill-sized payload arriving in a single poll.
    max_records_per_run: int = 5000

    # Replay mode: shift captured fixture timestamps onto the current wall
    # clock so committed sample payloads never age out of the freshness gate.
    # The shift is computed once per connector instance, so event ids and
    # watermarks stay stable across polls. Ignored for live endpoints.
    rebase_replay_to_now: bool = True


@dataclass
class ConnectorReadResult:
    """Outcome of one connector read, including per-source failure detail."""
    source_name: str
    records: List[CanonicalTelemetryRecord] = field(default_factory=list)
    mapping_errors: List[str] = field(default_factory=list)
    fetch_error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.fetch_error is None


class TelemetryConnector(ABC):
    """Base class for all telemetry source connectors."""

    def __init__(self, config: ConnectorConfig):
        self.config = config
        # Watermark of the newest event time already emitted, so repeated polls
        # against an append-only source don't replay history.
        self._watermark: float = 0.0
        # Fixed replay shift, resolved on first read (see `rebase_replay_to_now`).
        self._replay_offset: Optional[float] = None

    # -- Subclass contract --------------------------------------------------

    @property
    @abstractmethod
    def mapping(self) -> SourceMapping:
        """The declarative payload -> canonical translation for this vendor."""

    @abstractmethod
    def fetch_raw(self) -> Any:
        """Return the raw vendor payload for this polling interval."""

    # -- Shared machinery ---------------------------------------------------

    def read(self) -> ConnectorReadResult:
        """
        Fetch, map, and emit canonical records.

        A fetch failure is captured rather than raised: one unreachable vendor
        must not take down ingestion for every other configured source.
        """
        result = ConnectorReadResult(source_name=self.config.name)

        try:
            payload = self.fetch_raw()
        except Exception as exc:  # noqa: BLE001 - isolate per-source failures
            result.fetch_error = f"{type(exc).__name__}: {exc}"
            return result

        mapping = self.mapping
        newest_seen = self._watermark

        # Map first, so the replay shift can be derived from the whole batch
        # before any record is materialized.
        mapped_batch: List[Dict[str, Any]] = []
        for raw_record in mapping.select_records(payload)[: self.config.max_records_per_run]:
            try:
                mapped_batch.append(mapping.apply(raw_record))
            except MappingError as exc:
                result.mapping_errors.append(str(exc))

        self._apply_replay_shift(mapped_batch)

        for fields in mapped_batch:
            try:
                record = self._build_record(fields)
            except MappingError as exc:
                result.mapping_errors.append(str(exc))
                continue

            # Skip anything at or before the watermark from the previous poll.
            if record.timestamp <= self._watermark:
                continue

            newest_seen = max(newest_seen, record.timestamp)
            result.records.append(record)

        self._watermark = newest_seen
        return result

    def _apply_replay_shift(self, mapped_batch: List[Dict[str, Any]]) -> None:
        """
        Slide captured fixture timestamps onto the current wall clock.

        Committed sample payloads would otherwise fail the freshness gate the
        moment they aged past its window. The offset is resolved once, from the
        newest record in the first batch, and reused for the life of the
        connector so ids and watermarks remain stable across polls.
        """
        if not self.config.fixture_path or not self.config.rebase_replay_to_now:
            return

        timestamps = [
            float(f["timestamp"]) for f in mapped_batch if f.get("timestamp") is not None
        ]
        if not timestamps:
            return

        if self._replay_offset is None:
            self._replay_offset = time.time() - max(timestamps)

        for fields in mapped_batch:
            if fields.get("timestamp") is not None:
                fields["timestamp"] = float(fields["timestamp"]) + self._replay_offset

    def _build_record(self, fields: Dict[str, Any]) -> CanonicalTelemetryRecord:
        """Stamp source context and identity onto mapped fields."""
        timestamp = fields.get("timestamp")
        if timestamp is None:
            raise MappingError("record produced no usable timestamp")

        fields.setdefault("service_name", self.config.service_name)
        fields.setdefault("environment", self.config.environment)
        fields["source_name"] = self.config.name
        fields["source_kind"] = self.config.kind
        fields["event_id"] = make_event_id(
            self.config.name, float(timestamp), fields.get("trace_id")
        )

        try:
            return CanonicalTelemetryRecord(**fields)
        except Exception as exc:  # noqa: BLE001 - reported as a mapping error
            raise MappingError(f"record failed schema validation: {exc}") from exc

    def reset_watermark(self) -> None:
        """Replay a source from the beginning on the next read."""
        self._watermark = 0.0

    # -- Payload loading helpers -------------------------------------------

    def _load_payload(self) -> Any:
        """
        Load JSON from a live endpoint or a local fixture.

        Fixtures let the same connector class serve both a real deployment and
        the offline demo without branching logic in subclasses.
        """
        if self.config.fixture_path:
            return self._load_fixture()
        if self.config.endpoint:
            return self._load_http()
        raise ValueError(
            f"connector '{self.config.name}' has neither an endpoint nor a fixture_path"
        )

    def _load_fixture(self) -> Any:
        path = Path(self.config.fixture_path)  # type: ignore[arg-type]
        if not path.exists():
            raise FileNotFoundError(f"fixture not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _load_http(self) -> Any:
        # Imported lazily so offline/fixture runs never require the dependency.
        import httpx

        response = httpx.get(
            self.config.endpoint,  # type: ignore[arg-type]
            params=self.config.query_params or None,
            headers=self.config.headers or None,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def iter_records(self) -> Iterator[CanonicalTelemetryRecord]:
        """Convenience iterator over a single read."""
        yield from self.read().records
