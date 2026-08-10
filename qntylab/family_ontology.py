"""Canonical strategy-family ontology (Research Factory V2, Seam 1).

Historical candidate/decision/trial events carry ten raw ``family_id`` labels that
represent six real strategy families plus one non-strategy measurement family.
Generation-1 events wrote ``FAMILY_*`` labels; generation-2 events wrote
lower-case labels.  Nothing reconciled them, so raw-label family queries
silently lose variants -- most importantly the generation-1 H003 24/96 variant,
which is registered under ``FAMILY_MOVING_AVERAGE`` while its three siblings are
registered under ``moving_average_trend``.

This module freezes exactly one alias map.  It never rewrites history: the
resolution happens in the corpus/index layer, reading legacy labels and
returning canonical family identity.  Unknown or ambiguous labels fail closed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

FAMILY_ONTOLOGY_VERSION = "FAMILY_ONTOLOGY_V1"

TIME_SERIES_MOMENTUM = "TIME_SERIES_MOMENTUM"
MOVING_AVERAGE_TREND = "MOVING_AVERAGE_TREND"
PRICE_BREAKOUT = "PRICE_BREAKOUT"
MEAN_REVERSION = "MEAN_REVERSION"
SHORT_HORIZON_REVERSAL = "SHORT_HORIZON_REVERSAL"
VOLATILITY_SCALED_TREND = "VOLATILITY_SCALED_TREND"
JIGSAW_CONDITION_DEPENDENCE = "JIGSAW_CONDITION_DEPENDENCE"


class FamilyOntologyError(RuntimeError):
    """Raised when a family label cannot be resolved to exactly one canonical family."""


# Canonical families.  ``is_strategy_family`` separates return-generating strategy
# families from non-strategy measurement families, so corpus counts of "strategy
# families" cannot be inflated by measurement work.
CANONICAL_FAMILIES: dict[str, dict[str, Any]] = {
    TIME_SERIES_MOMENTUM: {
        "canonical_family_id": TIME_SERIES_MOMENTUM,
        "mechanism": "Own-asset return continuation over a single lookback horizon.",
        "is_strategy_family": True,
    },
    MOVING_AVERAGE_TREND: {
        "canonical_family_id": MOVING_AVERAGE_TREND,
        "mechanism": "Fast/slow moving-average crossover trend following.",
        "is_strategy_family": True,
    },
    PRICE_BREAKOUT: {
        "canonical_family_id": PRICE_BREAKOUT,
        "mechanism": "Entry on penetration of a trailing price channel.",
        "is_strategy_family": True,
    },
    MEAN_REVERSION: {
        "canonical_family_id": MEAN_REVERSION,
        "mechanism": "Fade deviations beyond a volatility-scaled band.",
        "is_strategy_family": True,
    },
    SHORT_HORIZON_REVERSAL: {
        "canonical_family_id": SHORT_HORIZON_REVERSAL,
        "mechanism": "Fade very short horizon directional moves.",
        "is_strategy_family": True,
    },
    VOLATILITY_SCALED_TREND: {
        "canonical_family_id": VOLATILITY_SCALED_TREND,
        "mechanism": "Moving-average trend sized inversely to realized volatility.",
        "is_strategy_family": True,
    },
    JIGSAW_CONDITION_DEPENDENCE: {
        "canonical_family_id": JIGSAW_CONDITION_DEPENDENCE,
        "mechanism": "Measurement of state-conditioned utility of a frozen strategy; not a tradable family.",
        "is_strategy_family": False,
    },
}

# Frozen alias map.  Every ``family_id`` ever written to the canonical streams
# must appear here.  Adding an alias is a deliberate, reviewable change.
FAMILY_ALIASES: dict[str, str] = {
    # time-series momentum
    "FAMILY_MOMENTUM": TIME_SERIES_MOMENTUM,
    "time_series_momentum": TIME_SERIES_MOMENTUM,
    "TIME_SERIES_MOMENTUM": TIME_SERIES_MOMENTUM,
    # moving-average trend
    "FAMILY_MOVING_AVERAGE": MOVING_AVERAGE_TREND,
    "moving_average_trend": MOVING_AVERAGE_TREND,
    "MOVING_AVERAGE_TREND": MOVING_AVERAGE_TREND,
    # price breakout
    "FAMILY_BREAKOUT": PRICE_BREAKOUT,
    "price_breakout": PRICE_BREAKOUT,
    "PRICE_BREAKOUT": PRICE_BREAKOUT,
    # mean reversion
    "FAMILY_MEAN_REVERSION": MEAN_REVERSION,
    "mean_reversion": MEAN_REVERSION,
    "MEAN_REVERSION": MEAN_REVERSION,
    # short-horizon reversal
    "FAMILY_SHORT_HORIZON_REVERSAL": SHORT_HORIZON_REVERSAL,
    "short_horizon_reversal": SHORT_HORIZON_REVERSAL,
    "SHORT_HORIZON_REVERSAL": SHORT_HORIZON_REVERSAL,
    # volatility-scaled trend
    "FAMILY_VOLATILITY_SCALED_TREND": VOLATILITY_SCALED_TREND,
    "volatility_scaled_trend": VOLATILITY_SCALED_TREND,
    "VOLATILITY_SCALED_TREND": VOLATILITY_SCALED_TREND,
    # non-strategy measurement family
    "FAMILY_JIGSAW_CONDITION_DEPENDENCE": JIGSAW_CONDITION_DEPENDENCE,
    "jigsaw_condition_dependence": JIGSAW_CONDITION_DEPENDENCE,
    "JIGSAW_CONDITION_DEPENDENCE": JIGSAW_CONDITION_DEPENDENCE,
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def resolve_family(raw_family_id: str) -> str:
    """Resolve a raw historical ``family_id`` to exactly one canonical family.

    Fails closed: an unknown, empty, or non-string label raises rather than
    defaulting to a bucket, so a mislabelled variant can never be silently
    absorbed into a family it does not belong to.
    """
    if not isinstance(raw_family_id, str) or not raw_family_id.strip():
        raise FamilyOntologyError("family_id must be a non-empty string")
    canonical = FAMILY_ALIASES.get(raw_family_id)
    if canonical is None:
        raise FamilyOntologyError(
            f"unmapped family_id {raw_family_id!r}: add an explicit alias to FAMILY_ALIASES "
            f"({FAMILY_ONTOLOGY_VERSION}); ontology fails closed on unknown labels"
        )
    return canonical


def family_record(canonical_family_id: str) -> dict[str, Any]:
    record = CANONICAL_FAMILIES.get(canonical_family_id)
    if record is None:
        raise FamilyOntologyError(f"unknown canonical family: {canonical_family_id!r}")
    return dict(record)


def is_strategy_family(canonical_family_id: str) -> bool:
    return bool(family_record(canonical_family_id)["is_strategy_family"])


def aliases_for(canonical_family_id: str) -> list[str]:
    family_record(canonical_family_id)
    return sorted(alias for alias, target in FAMILY_ALIASES.items() if target == canonical_family_id)


def ontology_payload() -> dict[str, Any]:
    """Immutable, digestible description of the frozen ontology."""
    return {
        "aliases": dict(sorted(FAMILY_ALIASES.items())),
        "families": {key: dict(sorted(value.items())) for key, value in sorted(CANONICAL_FAMILIES.items())},
        "ontology_version": FAMILY_ONTOLOGY_VERSION,
    }


def ontology_digest() -> str:
    return hashlib.sha256(_canonical_bytes(ontology_payload())).hexdigest()


def verify_alias_coverage(raw_family_ids: list[str]) -> None:
    """Assert every observed raw label resolves; used by the corpus rebuild."""
    unmapped = sorted({value for value in raw_family_ids if value not in FAMILY_ALIASES})
    if unmapped:
        raise FamilyOntologyError(f"unmapped family_id labels present in canonical history: {unmapped}")


def _canonical_targets_are_declared() -> None:
    undeclared = sorted({target for target in FAMILY_ALIASES.values() if target not in CANONICAL_FAMILIES})
    if undeclared:
        raise FamilyOntologyError(f"alias targets missing from CANONICAL_FAMILIES: {undeclared}")


_canonical_targets_are_declared()
