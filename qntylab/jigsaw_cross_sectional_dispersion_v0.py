"""Frozen contract for JIGSAW_CROSS_SECTIONAL_DISPERSION_PREREGISTRATION_V0.

This module freezes the CROSS_SECTIONAL_DISPERSION feature recipe and the
family-first pooling/consistency rule that will condition the already-frozen,
already-FAILED Breadth V2 CROSS_SECTIONAL_MOMENTUM measurement process.

It is deliberately NOT an execution module. There is no ``materialize()``,
``analyze()``, ``run()``, or ``main()`` here, no file I/O, and no economic
outcome is computed by importing or testing this module. Real-data
measurement is authorized only under the separately bounded
``JIGSAW_CROSS_SECTIONAL_DISPERSION_EXECUTION_V0`` phase, which must reuse
these exact frozen functions/constants by reference rather than
reimplementing or adjusting them after seeing outcomes.

Reused by reference, not reimplemented:
- 20-asset frozen panel: ``qntylab.breadth_v2_runner.FROZEN_PANEL_ORDER``
- cross-sectional ranking mechanics: ``qntylab.breadth_v2_strategies.cross_sectional_weights``
- PIT percentile / LOW-MID-HIGH binning: ``qntylab.jigsaw_trend_condition_dependence_v0.historical_percentile`` / ``state_bin``
- SEALED_T0 boundary: ``qntylab.breadth_v2_sealed.SEALED_T0``

CROSS_SECTIONAL_MOMENTUM is reused here purely as a FIXED MEASUREMENT
PROCESS. Its Breadth V2 "FAIL" family status is unchanged and is not being
reopened for strategy advancement; see ``breadth_v2_sealed.EXCLUDED_DEVELOPMENT_FAIL_FAMILIES``
which already excludes it from the sealed observation stream.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import numpy as np

from .breadth_v2_runner import FROZEN_PANEL_ORDER
from .breadth_v2_sealed import SEALED_T0 as _SEALED_T0_DATETIME
from .jigsaw_trend_condition_dependence_v0 import NORMALIZATION_DAYS, historical_percentile, state_bin

# --- Identity -----------------------------------------------------------

EXPERIMENT_ID = "JIGSAW_CROSS_SECTIONAL_DISPERSION_V0"
HYPOTHESIS_ID = "CROSS_SECTIONAL_DISPERSION_CONDITIONS_CROSS_SECTIONAL_MOMENTUM_V0"
FEATURE_ID = "CROSS_SECTIONAL_DISPERSION"
FEATURE_VERSION = "v0"
MEASUREMENT_PROCESS_ID = "CROSS_SECTIONAL_MOMENTUM"
MEASUREMENT_PROCESS_FAMILY_STATUS_AT_REGISTRATION = "FAIL"
MEASUREMENT_PROCESS_STRATEGY_VERSION = "breadth-v2-preregistered-v1"
PIECE_TYPE = "CONDITION_DEPENDENCE"
AUTHORITY = "NON_AUTHORITATIVE"
PROMOTION_ELIGIBLE = False
PIT_UNIVERSE_CLAIM = "NONE"
ROUTER_AUTHORITY = "NONE"

# --- Reused-by-reference frozen panel ------------------------------------

PANEL = tuple(FROZEN_PANEL_ORDER)
assert len(PANEL) == 20

# --- Measurement-process variant treatment (FAMILY-FIRST) ----------------

# The exact four already-registered CROSS_SECTIONAL_MOMENTUM lookback
# variants from experiments/research/candidates.jsonl (CANDIDATE_BREADTH_V2_CSMOM_*).
# No coordinate is added, dropped, or selected here.
MEASUREMENT_VARIANT_LOOKBACKS_HOURS: tuple[int, ...] = (24, 72, 168, 336)
MEASUREMENT_VARIANT_TAIL_FRACTION = 0.2
MEASUREMENT_VARIANT_GROSS_EXPOSURE = 2.0
MEASUREMENT_VARIANT_MODE = "long_short"

# --- Dispersion recipe (frozen; independent of which CSMOM lookback is
# being conditioned, so exactly one dispersion recipe exists) -------------

DISPERSION_RETURN_HORIZON_HOURS = 24
DISPERSION_STATISTIC = "CROSS_SECTIONAL_SAMPLE_STDEV_DDOF1"
MINIMUM_CROSS_SECTIONAL_BREADTH = len(PANEL)  # 20/20; whole-panel fail-closed, mirrors CSMOM's own missingness rule

# --- Decision grid / horizon (reused from prior Jigsaw convention;
# applied to the already-realized frozen CSMOM hourly path re-binned into
# non-overlapping daily blocks -- see literature_design_note.md for why) --

DECISION_GRID = {
    "frequency": "DAILY",
    "timestamp": "00:00:00Z",
    "horizon_hours": 24,
    "non_overlapping": True,
}

# --- Development sample ---------------------------------------------------

# CROSS_SECTIONAL_MOMENTUM's own Breadth V2 development execution shows the
# whole-panel missing-member rule blocks *all* DEV_2022 and DEV_2025 cells
# (0/8 usable each); only DEV_2024 has any usable measurement cells
# (8/8 usable). This experiment cannot measure outside where the fixed
# process itself produced usable observations, so the development sample is
# bound to DEV_2024 -- this is a discovered constraint, not a choice made to
# reach a preferred sample.
DEVELOPMENT_WINDOW = {"id": "DEV_2024", "start": "2024-01-01T00:00:00Z", "end": "2024-12-31T23:00:00Z"}
# Calendar-fixed halves of the single usable window, used only as a weaker
# substitute for cross-window temporal-stability robustness (see below).
CALENDAR_HALVES = {
    "H1_2024": ("2024-01-01T00:00:00Z", "2024-06-30T23:00:00Z"),
    "H2_2024": ("2024-07-01T00:00:00Z", "2024-12-31T23:00:00Z"),
}
# Warm-up observations strictly before DEVELOPMENT_WINDOW are permitted only
# to seed the 365-day trailing PIT percentile normalization of dispersion;
# they may never be labelled as economic decisions.
NORMALIZATION_WARMUP_DAYS = NORMALIZATION_DAYS  # bound by identity to the reused Jigsaw normalization (365)

# --- Cost / funding semantics (reused by reference from Breadth V2
# Section 7; no new cost mode is introduced) -------------------------------

COST_MODES = {
    "BASELINE_EXECUTION": {"fee_bps": 10.0, "slippage_bps": 0.0},
    "STRESS_EXECUTION": {"fee_bps": 10.0, "slippage_bps": 10.0},
}
PRIMARY_COST_MODE = "BASELINE_EXECUTION"

# --- Label ------------------------------------------------------------

LABEL = "MEASUREMENT_STRATEGY_UTILITY"
FLAT_UTILITY = 0.0
GATED_STRATEGY_UTILITY = "NOT_MEASURED"
GATE_TRANSITION_COSTS = "NOT_INTRODUCED"

# --- Multiplicity -------------------------------------------------------

NUMBER_OF_PRIMARY_STATE_HYPOTHESES = 1
FAMILY_CONSISTENCY_MINIMUM_VARIANTS = 3  # of 4 registered CSMOM lookbacks must be directionally consistent
DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD = 0.90  # descriptive-only; frozen before outcomes

# --- Robustness / uncertainty conventions reused from the prior Jigsaw
# piece (bind by identical constant, not reimplementation) ----------------

BOOTSTRAP_METHOD = "MOVING_BLOCK_BOOTSTRAP"
BOOTSTRAP_BLOCK_CALENDAR_DAYS = 7
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 271828

# --- Sealed boundary (imported by reference; never redefined) -----------

SEALED_T0 = _SEALED_T0_DATETIME
SEALED_T0_ISO = "2026-08-10T19:00:00Z"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def cross_sectional_dispersion(period_returns: Mapping[str, float]) -> float:
    """Frozen dispersion statistic: sample stdev (ddof=1) of simple
    ``DISPERSION_RETURN_HORIZON_HOURS`` returns across the eligible panel at
    one point-in-time decision boundary.

    ``period_returns`` must already be computed by the caller strictly from
    ``close(t)`` and ``close(t - DISPERSION_RETURN_HORIZON_HOURS)`` for each
    panel member (no forward information); this function performs no time
    lookups itself and is therefore trivially free of look-ahead.

    Fails closed (raises) unless every one of the 20 frozen panel members is
    present and finite -- ``MINIMUM_CROSS_SECTIONAL_BREADTH`` is 20/20, not a
    partial-panel threshold, so this mirrors CSMOM's own "missing panel
    members block the whole panel" rule rather than inventing a new one.
    """
    if set(period_returns) != set(PANEL):
        raise ValueError("cross_sectional_dispersion requires the exact frozen 20-asset panel, no more, no fewer")
    values = np.array([period_returns[symbol] for symbol in PANEL], dtype=float)
    if len(values) < MINIMUM_CROSS_SECTIONAL_BREADTH or not np.all(np.isfinite(values)):
        raise ValueError("cross_sectional_dispersion requires a complete, finite panel observation")
    return float(np.std(values, ddof=1))


def dispersion_percentile_and_bin(trailing_dispersion_values: np.ndarray, index: int) -> tuple[float, str]:
    """PIT percentile + LOW/MID/HIGH bin, delegating byte-for-byte to the
    already-frozen Jigsaw normalization functions (no reimplementation)."""
    percentile = historical_percentile(trailing_dispersion_values, index)
    return percentile, state_bin(percentile)


def family_consistency(per_variant_high_minus_low: Mapping[int, float | None]) -> dict[str, Any]:
    """Family-first consistency criterion across the 4 registered CSMOM
    lookback variants. Order-invariant and selection-free: it never returns,
    ranks, or privileges any single "best" variant, only a symmetric count
    of directional agreement with the frozen hypothesis sign (negative:
    higher dispersion -> weaker utility).

    Returns the count/threshold verdict; callers decide CANDIDATE vs
    CONCENTRATED using ``FAMILY_CONSISTENCY_MINIMUM_VARIANTS`` unchanged.
    """
    if set(per_variant_high_minus_low) != set(MEASUREMENT_VARIANT_LOOKBACKS_HOURS):
        raise ValueError("family_consistency requires all four registered CSMOM lookback variants, no more, no fewer")
    directional = {
        lookback: (value is not None and value < 0.0)
        for lookback, value in per_variant_high_minus_low.items()
    }
    consistent_count = sum(directional.values())
    return {
        "per_variant_directionally_consistent": dict(sorted(directional.items())),
        "consistent_count": consistent_count,
        "of_variants": len(MEASUREMENT_VARIANT_LOOKBACKS_HOURS),
        "minimum_required": FAMILY_CONSISTENCY_MINIMUM_VARIANTS,
        "family_consistent": consistent_count >= FAMILY_CONSISTENCY_MINIMUM_VARIANTS,
    }


def contract_payload() -> dict[str, Any]:
    """Everything that must be frozen before any outcome is observed."""
    return {
        "experiment_id": EXPERIMENT_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "feature_id": FEATURE_ID,
        "feature_version": FEATURE_VERSION,
        "measurement_process_id": MEASUREMENT_PROCESS_ID,
        "measurement_process_family_status_at_registration": MEASUREMENT_PROCESS_FAMILY_STATUS_AT_REGISTRATION,
        "measurement_process_strategy_version": MEASUREMENT_PROCESS_STRATEGY_VERSION,
        "piece_type": PIECE_TYPE,
        "authority": AUTHORITY,
        "promotion_eligible": PROMOTION_ELIGIBLE,
        "pit_universe_claim": PIT_UNIVERSE_CLAIM,
        "router_authority": ROUTER_AUTHORITY,
        "panel": list(PANEL),
        "measurement_variant_lookbacks_hours": list(MEASUREMENT_VARIANT_LOOKBACKS_HOURS),
        "measurement_variant_tail_fraction": MEASUREMENT_VARIANT_TAIL_FRACTION,
        "measurement_variant_gross_exposure": MEASUREMENT_VARIANT_GROSS_EXPOSURE,
        "measurement_variant_mode": MEASUREMENT_VARIANT_MODE,
        "dispersion_return_horizon_hours": DISPERSION_RETURN_HORIZON_HOURS,
        "dispersion_statistic": DISPERSION_STATISTIC,
        "minimum_cross_sectional_breadth": MINIMUM_CROSS_SECTIONAL_BREADTH,
        "decision_grid": DECISION_GRID,
        "development_window": DEVELOPMENT_WINDOW,
        "calendar_halves": CALENDAR_HALVES,
        "normalization_warmup_days": NORMALIZATION_WARMUP_DAYS,
        "cost_modes": COST_MODES,
        "primary_cost_mode": PRIMARY_COST_MODE,
        "label": LABEL,
        "flat_utility": FLAT_UTILITY,
        "gated_strategy_utility": GATED_STRATEGY_UTILITY,
        "gate_transition_costs": GATE_TRANSITION_COSTS,
        "number_of_primary_state_hypotheses": NUMBER_OF_PRIMARY_STATE_HYPOTHESES,
        "family_consistency_minimum_variants": FAMILY_CONSISTENCY_MINIMUM_VARIANTS,
        "distinctness_abs_correlation_kill_threshold": DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD,
        "bootstrap_method": BOOTSTRAP_METHOD,
        "bootstrap_block_calendar_days": BOOTSTRAP_BLOCK_CALENDAR_DAYS,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "sealed_t0": SEALED_T0_ISO,
    }


def contract_digest() -> str:
    return hashlib.sha256(_canonical_bytes(contract_payload())).hexdigest()


def is_pre_sealed_t0(timestamp_iso: str) -> bool:
    """Fail-closed PIT/sealed-boundary guard: any timestamp at or after
    SEALED_T0 is inadmissible for this experiment's development sample."""
    from datetime import UTC, datetime

    value = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00")).astimezone(UTC)
    return value < SEALED_T0
