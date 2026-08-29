"""
Enrichment & Derivation Transforms

Applied after mapping and before quality gates. Transforms fill in fields a
source did not provide, using values it did, so that downstream consumers see a
uniformly populated record regardless of how complete the upstream vendor was.

Every transform is total: given any record it returns a record, never raising.
A transform that cannot derive a value leaves it untouched rather than guessing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from ingestion.schema import CanonicalTelemetryRecord

Transform = Callable[[CanonicalTelemetryRecord], CanonicalTelemetryRecord]


@dataclass(frozen=True)
class TokenPricing:
    """
    Per-token USD pricing used to derive cost when a source omits it.

    Metrics backends commonly export token counts but no cost, since billing
    lives in a separate system. Deriving it here keeps cost anomaly detection
    working across sources that never report spend directly.
    """
    prompt_usd_per_token: float = 0.00000015
    output_usd_per_token: float = 0.00000060

    def cost_for(self, prompt_tokens: int, output_tokens: int) -> float:
        return (prompt_tokens * self.prompt_usd_per_token) + (
            output_tokens * self.output_usd_per_token
        )


DEFAULT_PRICING = TokenPricing()


def derive_total_tokens(record: CanonicalTelemetryRecord) -> CanonicalTelemetryRecord:
    """Fill `total_tokens` from its components when only the parts were sent."""
    if record.total_tokens == 0 and (record.prompt_tokens or record.output_tokens):
        record.total_tokens = record.prompt_tokens + record.output_tokens
    return record


def derive_cost(record: CanonicalTelemetryRecord, pricing: TokenPricing = DEFAULT_PRICING) -> CanonicalTelemetryRecord:
    """Estimate cost from token counts when the source reports no spend."""
    if record.cost_usd == 0.0 and (record.prompt_tokens or record.output_tokens):
        record.cost_usd = round(pricing.cost_for(record.prompt_tokens, record.output_tokens), 6)
    return record


def clamp_scores(record: CanonicalTelemetryRecord) -> CanonicalTelemetryRecord:
    """
    Pull marginally out-of-range scores back to the valid band.

    Evaluators that average sub-scores can emit 100.0000001 or -0.0001 from
    floating-point drift. Clamping a rounding artifact is correct; a wildly
    out-of-range score is a unit error and is left for `RangeGate` to reject.
    """
    tolerance = 1.0
    for attr in ("groundedness_score", "context_relevance_score", "answer_quality_score"):
        value = getattr(record, attr)
        if 100.0 < value <= 100.0 + tolerance:
            setattr(record, attr, 100.0)
        elif -tolerance <= value < 0.0:
            setattr(record, attr, 0.0)
    return record


def normalize_environment(record: CanonicalTelemetryRecord) -> CanonicalTelemetryRecord:
    """
    Collapse vendor-specific environment spellings onto a canonical set.

    Splitting one logical environment across `prod`, `production`, and `PROD`
    fragments the baseline and weakens every comparison built on top of it.
    """
    aliases = {
        "prod": "production",
        "prd": "production",
        "live": "production",
        "stg": "staging",
        "stage": "staging",
        "dev": "development",
        "devel": "development",
    }
    normalized = (record.environment or "").strip().lower()
    record.environment = aliases.get(normalized, normalized or "production")
    return record


def default_transforms() -> List[Transform]:
    """
    The standard transform chain.

    Order matters: `total_tokens` must be derived before cost, since cost
    derivation reads the component counts.
    """
    return [
        normalize_environment,
        derive_total_tokens,
        derive_cost,
        clamp_scores,
    ]


def apply_transforms(
    record: CanonicalTelemetryRecord,
    transforms: List[Transform],
) -> CanonicalTelemetryRecord:
    """Run a transform chain, skipping any transform that fails on a record."""
    for transform in transforms:
        try:
            record = transform(record)
        except Exception:  # noqa: BLE001 - one bad transform must not drop the record
            continue
    return record
