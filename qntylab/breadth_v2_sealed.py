"""Frozen forward-observation boundary for Breadth V2.

This module constructs only the sealed observation contract.  It deliberately
does not read economic outcomes, execute strategies, or adjudicate families.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

CONTRACT_ID = "BREADTH_V2_SEALED_FORWARD_OBSERVATION_V0"
CONTRACT_VERSION = "V0"
SCREEN_ID = "QNTYLAB_BREADTH_V2_20260810"
PREREGISTRATION_COMMIT = "ca0d1c1272e282ee5e1f5fcbc9bc66b2d75eff83"
PREREGISTRATION_CONTRACT_IDENTITY = "QNTYLAB_BREADTH_V2_20260810"
DEVELOPMENT_CAMPAIGN_COMMIT = "18be3196f41a5ee38404a6aa9644f02af63e9d9c"
DEVELOPMENT_DECISION_IDENTITY = "5aa5a165239a893c2f6eded9c857a3bb107d7c22a807403758fe942ed43d5adb"
DEVELOPMENT_MANIFEST_IDENTITY = "c28f7a52a233a9fa2c1b45afd970b8e56c667ce1091844535fb0940f482ce452"
INPUT_UNIVERSE_IDENTITY = "8fef4c02d113027630072bcbb0802e35ab31be17c835aa2ebdae4261265589fb"
MINIMUM_COMPLETE_HOURS = 2160

ELIGIBLE_FAMILIES = ("MOVING_AVERAGE_TREND", "PRICE_BREAKOUT")
EXCLUDED_DEVELOPMENT_FAIL_FAMILIES = (
    "TIME_SERIES_MOMENTUM", "CROSS_SECTIONAL_MOMENTUM",
    "CROSS_SECTIONAL_REVERSAL", "FUNDING_CARRY", "VOLATILITY_TARGETING",
)
ELIGIBLE_VARIANT_IDS = {
    "MOVING_AVERAGE_TREND": (
        "variant_d5f7ee106ba428292feacd0b", "variant_2584eb63c90a1aa65da2e006",
        "variant_83dc90d06ac8234aaacd575b", "variant_104b54d3f448e98b07bb104f",
    ),
    "PRICE_BREAKOUT": (
        "variant_ac4a45549606e2d83bad89a9", "variant_057bf9fb96021b54541a31cc",
        "variant_81f0ae4565fe4e93e8ecfa09", "variant_5910c68e1b751a6d26bda998",
    ),
}

_UTC = timezone.utc
_EVIDENCE_TIMESTAMPS = (
    ("preregistration_commit", "2026-08-10T15:22:25Z", PREREGISTRATION_COMMIT),
    ("execution_contract_merge", "2026-08-10T16:14:36Z", "7f86d69cb9e47083bf985f741482f5b35d99a70c"),
    ("funding_source_materiality_merge", "2026-08-10T17:36:50Z", "5f353a48832d1f784a3fcd1fbf6a969578b5c39e"),
    ("input_bundle_materiality_merge", "2026-08-10T18:12:54Z", "d4ad8a3e11d4a58f028c51fca89f903d6186e888"),
)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(_UTC)


def derive_sealed_t0() -> datetime:
    """Derive T0 from committed evidence; there is no caller timestamp input."""
    latest = max(_parse(timestamp) for _, timestamp, _ in _EVIDENCE_TIMESTAMPS)
    boundary = latest.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if boundary != _parse("2026-08-10T19:00:00Z"):
        raise RuntimeError("committed SEALED_T0 evidence no longer reconciles")
    return boundary


SEALED_T0 = derive_sealed_t0()
EARLIEST_ELIGIBLE_ADJUDICATION_TIME = SEALED_T0 + timedelta(hours=MINIMUM_COMPLETE_HOURS)


def complete_hours(as_of: datetime) -> int:
    """Return complete UTC hours elapsed from the frozen T0."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return max(0, int((as_of.astimezone(_UTC) - SEALED_T0).total_seconds() // 3600))


def adjudication_is_authorized(as_of: datetime) -> bool:
    return complete_hours(as_of) >= MINIMUM_COMPLETE_HOURS


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_contract(*, as_of: datetime | None = None) -> dict[str, Any]:
    """Build the deterministic contract; ``as_of`` affects status only."""
    mature = as_of is not None and adjudication_is_authorized(as_of)
    contract: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "registered_screen_id": SCREEN_ID,
        "development_campaign_commit": DEVELOPMENT_CAMPAIGN_COMMIT,
        "development_decision_identity": DEVELOPMENT_DECISION_IDENTITY,
        "development_manifest_identity": DEVELOPMENT_MANIFEST_IDENTITY,
        "preregistration_commit": PREREGISTRATION_COMMIT,
        "preregistration_contract_identity": PREREGISTRATION_CONTRACT_IDENTITY,
        "eligible_families": list(ELIGIBLE_FAMILIES),
        "eligible_variant_ids": {k: list(v) for k, v in ELIGIBLE_VARIANT_IDS.items()},
        "excluded_development_fail_families": list(EXCLUDED_DEVELOPMENT_FAIL_FAMILIES),
        "source_contracts": {
            "input_universe": {"id": "BREADTH_V2_DEV_INPUT_UNIVERSE_V0R1", "sha256": INPUT_UNIVERSE_IDENTITY},
            "price": "BINANCE_USDM_PERPETUAL_1H_OHLCV",
            "funding": "BINANCE_USDM_FUNDING_SETTLEMENT_MATERIALIZER_V0",
        },
        "benchmark_contracts": {family: "BUY_AND_HOLD_PRIMARY_CASH_SECONDARY" for family in ELIGIBLE_FAMILIES},
        "cost_modes": {"BASELINE_EXECUTION": {"fee_bps": 10, "slippage_bps": 0}, "STRESS_EXECUTION": {"fee_bps": 10, "slippage_bps": 10}},
        "accounting_kernel_identity": "BREADTH_V2_PORTFOLIO_KERNEL_V0",
        "SEALED_T0": SEALED_T0.isoformat().replace("+00:00", "Z"),
        "SEALED_T0_derivation_evidence": [{"kind": k, "timestamp": t, "commit": c} for k, t, c in _EVIDENCE_TIMESTAMPS],
        "minimum_complete_hours": MINIMUM_COMPLETE_HOURS,
        "earliest_eligible_adjudication_time": EARLIEST_ELIGIBLE_ADJUDICATION_TIME.isoformat().replace("+00:00", "Z"),
        "observation_status": "SEALED_OBSERVATION_MATURE" if mature else "SEALED_OBSERVATION_ACTIVE",
        "historical_holdout_policy": "FORWARD_TIME_ONLY;_2023_AND_HISTORICAL_2026_ARE_NOT_FRESH_HOLDOUTS",
        "retrospective_holdout_prohibited": True,
        "sealed_adjudication_authorized": mature,
    }
    # Status is a later clock observation, not part of the scientific identity.
    identity_material = {k: v for k, v in contract.items() if k not in {
        "observation_status", "sealed_adjudication_authorized",
    }}
    contract["contract_digest"] = _canonical_digest(identity_material)
    return contract


def serialize_contract(contract: Mapping[str, Any]) -> str:
    return json.dumps(contract, sort_keys=True, indent=2) + "\n"


class SealedAdjudicationNotAuthorized(RuntimeError):
    """Raised when a caller attempts sealed forward evaluation before the
    frozen minimum horizon has elapsed.

    This is the outcome-peeking gate.  It never inspects, computes, or
    returns any economic result -- it only answers a yes/no readiness
    question derived from the frozen ``SEALED_T0`` and
    ``MINIMUM_COMPLETE_HOURS``.  Any future caller that would execute a
    Breadth V2 candidate against the sealed forward window (e.g. via
    ``qntylab.breadth_v2_runner.record_breadth_v2_evaluation``) MUST call
    :func:`enforce_sealed_adjudication_authorized` first.  This module does
    not wire the gate into the runner itself -- that wiring is deliberately
    out of scope for this contract-freezing phase.
    """


def enforce_sealed_adjudication_authorized(as_of: datetime) -> None:
    """Raise :class:`SealedAdjudicationNotAuthorized` unless the frozen
    minimum horizon has fully elapsed as of ``as_of``.

    Pure and side-effect-free beyond raising.  Reuses
    :func:`adjudication_is_authorized`/:func:`complete_hours` exactly; it
    does not redefine the boundary or the horizon.
    """
    if not adjudication_is_authorized(as_of):
        remaining = MINIMUM_COMPLETE_HOURS - complete_hours(as_of)
        raise SealedAdjudicationNotAuthorized(
            "sealed forward adjudication not authorized: "
            f"{max(0, remaining)} complete hour(s) remaining until "
            f"{EARLIEST_ELIGIBLE_ADJUDICATION_TIME.isoformat().replace('+00:00', 'Z')}"
        )
