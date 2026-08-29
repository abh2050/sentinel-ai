"""
Declarative Source-to-Canonical Field Mapping

Connecting a new telemetry vendor should be a mapping declaration, not a new
code path. A `SourceMapping` describes where each canonical field lives inside
a vendor payload and which unit conversion to apply on the way out.

Unit reconciliation is the part that bites in production: one vendor reports
latency in milliseconds, another in nanoseconds; one reports groundedness on a
0-1 scale, another as a 0-100 percentage. Converters are named and applied
declaratively so the conversion is visible in the mapping rather than buried in
a connector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


class MappingError(ValueError):
    """Raised when a required source field is missing or cannot be converted."""


# --------------------------------------------------------------------------
# Unit converters
# --------------------------------------------------------------------------

def _iso8601_to_epoch(value: Any) -> float:
    """Parse ISO-8601 (with or without trailing 'Z') into epoch seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


# Values that mean "no error", spelled the way each vendor spells it.
# OTLP's status enum is the subtle one: a span that succeeded is normally left
# UNSET rather than explicitly OK, so both must read as success. Treating them
# as truthy would mark every healthy span as a failed request.
_NON_ERROR_SENTINELS = {
    "", "0", "false", "none", "null",
    "ok", "success", "unset", "healthy", "pass", "passed",
    "status_code_ok", "status_code_unset",
}


def _to_bool(value: Any) -> bool:
    """Coerce vendor-specific error signals (`"ERROR"`, `1`, `"STATUS_CODE_ERROR"`) to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in _NON_ERROR_SENTINELS


CONVERTERS: Dict[str, Callable[[Any], Any]] = {
    "identity": lambda v: v,
    # Time
    "ns_to_s": lambda v: float(v) / 1_000_000_000.0,
    "us_to_s": lambda v: float(v) / 1_000_000.0,
    "ms_to_s": lambda v: float(v) / 1_000.0,
    "s_to_s": lambda v: float(v),
    "epoch_ms_to_s": lambda v: float(v) / 1_000.0,
    "epoch_ns_to_s": lambda v: float(v) / 1_000_000_000.0,
    "iso8601_to_epoch": _iso8601_to_epoch,
    # Money
    "usd_to_usd": lambda v: float(v),
    "cents_to_usd": lambda v: float(v) / 100.0,
    "micros_to_usd": lambda v: float(v) / 1_000_000.0,
    # Scores: canonical scale is 0-100
    "unit_to_pct": lambda v: float(v) * 100.0,
    "pct_to_pct": lambda v: float(v),
    # Primitives
    "to_float": lambda v: float(v),
    "to_int": lambda v: int(float(v)),
    "to_str": lambda v: str(v),
    "to_bool": _to_bool,
}


# --------------------------------------------------------------------------
# Path resolution
# --------------------------------------------------------------------------

def resolve_path(payload: Any, path: str) -> Any:
    """
    Resolve a dotted path against nested dicts/lists.

    Supports list indexing (`spans.0.name`) and a flat-scan escape hatch for
    OTLP-style attribute lists, where an attribute is located by key rather
    than position: `attributes[gen_ai.usage.total_tokens]`.

    Returns None when any segment is missing, so callers can apply defaults.
    """
    current = payload
    for segment in _split_path(path):
        if current is None:
            return None

        # attributes[some.key] -> scan a list of {key, value} pairs
        if segment.startswith("[") and segment.endswith("]"):
            wanted = segment[1:-1]
            current = _lookup_attribute_list(current, wanted)
            continue

        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _split_path(path: str) -> List[str]:
    """Split `a.b[key].c` into `['a', 'b', '[key]', 'c']`."""
    segments: List[str] = []
    buffer = ""
    depth = 0
    for char in path:
        if char == "[":
            if buffer:
                segments.append(buffer)
                buffer = ""
            depth += 1
            buffer += char
        elif char == "]":
            depth -= 1
            buffer += char
            segments.append(buffer)
            buffer = ""
        elif char == "." and depth == 0:
            if buffer:
                segments.append(buffer)
            buffer = ""
        else:
            buffer += char
    if buffer:
        segments.append(buffer)
    return segments


def _lookup_attribute_list(container: Any, wanted_key: str) -> Any:
    """
    Pull a value out of an OTLP-style attribute list.

    OTLP encodes attributes as `[{"key": "...", "value": {"intValue": "42"}}]`,
    so the value itself is a single-entry union that has to be unwrapped.
    """
    if isinstance(container, dict):
        return container.get(wanted_key)
    if not isinstance(container, (list, tuple)):
        return None

    for entry in container:
        if not isinstance(entry, dict) or entry.get("key") != wanted_key:
            continue
        value = entry.get("value")
        if not isinstance(value, dict):
            return value
        # Unwrap the OTLP AnyValue union
        for union_key in ("stringValue", "intValue", "doubleValue", "boolValue"):
            if union_key in value:
                return value[union_key]
        return value
    return None


# --------------------------------------------------------------------------
# Mapping declarations
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldRule:
    """Maps one vendor field onto one canonical field."""
    target: str
    source_path: str
    converter: str = "identity"
    default: Any = None
    required: bool = False

    def apply(self, payload: Any) -> Any:
        raw = resolve_path(payload, self.source_path)

        if raw is None:
            if self.required:
                raise MappingError(
                    f"required field '{self.target}' not found at path '{self.source_path}'"
                )
            return self.default

        convert = CONVERTERS.get(self.converter)
        if convert is None:
            raise MappingError(f"unknown converter '{self.converter}' for field '{self.target}'")

        try:
            return convert(raw)
        except (TypeError, ValueError) as exc:
            raise MappingError(
                f"could not convert '{self.target}' via '{self.converter}': {raw!r} ({exc})"
            ) from exc


@dataclass(frozen=True)
class SourceMapping:
    """
    A complete vendor payload -> canonical record translation.

    `record_selector` is the dotted path to the list of per-record objects
    inside a payload envelope; None means the payload is already a list of
    records (or a single record).
    """
    name: str
    rules: List[FieldRule] = field(default_factory=list)
    record_selector: Optional[str] = None
    constants: Dict[str, Any] = field(default_factory=dict)

    def select_records(self, payload: Any) -> List[Any]:
        target = payload if self.record_selector is None else resolve_path(payload, self.record_selector)
        if target is None:
            return []
        if isinstance(target, list):
            return target
        return [target]

    def apply(self, record: Any) -> Dict[str, Any]:
        """Translate one vendor record into canonical field values."""
        mapped: Dict[str, Any] = dict(self.constants)
        for rule in self.rules:
            value = rule.apply(record)
            if value is not None:
                mapped[rule.target] = value
        return mapped
