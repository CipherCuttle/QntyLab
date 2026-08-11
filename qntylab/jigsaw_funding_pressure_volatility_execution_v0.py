"""Deterministic executor for JIGSAW_FUNDING_PRESSURE_VOLATILITY_PREREGISTRATION_V0.

This module implements, mechanically and without new scientific choices, the
exact feature/outcome/statistic/adjudication recipe frozen in
``experiments/research/jigsaw_funding_pressure_volatility_v0/preregistration.json``
(``contract_digest``: ``sha256:749641cbee99bc769a6095e2a5877e4ccf1c46db0a82860885eedc06734cd2d6``)
and bound to the certified PIT coverage in the paired
``pit_coverage_certificate.json``
(``pit_coverage_certificate_digest``:
``sha256:76bbf05d1ab253f039bdd565bd19b563d19f4e1117f344ae495cac46bea0ffcc``).

Scope discipline
-----------------
This is an *execution enablement* phase, not the historical experiment
itself. Nothing in this module reads the real certified 610-decision
evidence set, and no test in this repository's paired test file is allowed
to point these functions at that evidence root. Every numeric test must use
small, hand-checkable, artificial fixtures constructed specifically to
falsify implementation mistakes.

Every deterministic step of the frozen contract is a separate, pure,
side-effect-free function:

    select_latest_funding_event    -- feature.formula event selection (e_i)
    compute_funding_pressure       -- feature.cross_sectional_aggregation
    compute_pit_ecdf               -- feature.normalization (365-obs, fraction scale)
    classify_funding_state         -- feature.state_bins (rational 1/3, 2/3)
    compute_hourly_asset_returns   -- outcome hourly simple close-to-close return
    compute_equal_weight_market_returns -- outcome 20/20 equal-weight market return
    compute_rv24                   -- outcome.realized_volatility_estimator
    compute_primary_contrast       -- primary_statistic (HIGH minus LOW mean RV24)
    compute_preregistered_robustness -- the (empty) set of frozen robustness checks
    adjudicate_frozen_proposition  -- kill_conditions / primary_hypotheses
    build_execution_receipt        -- deterministic, canonical-JSON receipt

No hidden mutable configuration, no model calls, no randomness, no network
dependency during scientific execution. Every constant a caller must bind
against is declared once, at module scope, below.

F4 disposition (duplicate funding timestamp ties)
--------------------------------------------------
``qntylab.binance_um_funding_settlement._parse_rows`` enforces
``funding_time_ms`` strictly increasing within one archive month, so no
duplicate timestamp can survive parsing a single month's file. Across month
boundaries, ``materialize_from_objects`` only reaches
``MATERIALIZED_VERIFIED`` after ``_coverage_difference`` reconciles the
admitted archive rows 1:1 against the independent REST witness; two
admissible rows sharing a ``funding_time_ms`` with different
``funding_rate`` values cannot both survive that reconciliation into a
certified evidence set. As a defense in depth -- since this executor must
never *invent* a tie-break the frozen contract does not specify --
``select_latest_funding_event`` raises ``DuplicateFundingTimestampError``
(fail closed, not a silent pick) if it is ever handed two admissible events
for the same member that share the maximum eligible ``funding_time_ms`` with
disagreeing rates. This can only happen if a caller hands the executor an
evidence set that is not actually certified-clean; it is not expected to
occur against real certified evidence, and this phase does not access real
evidence to check.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Mapping, Sequence

from .research_ledger import canonical_bytes, sha256_bytes

# --------------------------------------------------------------------------
# Canonical parent bindings (verified by the orchestrator and re-verified in
# this worktree; see the phase report for the reproduction of both digests).
# --------------------------------------------------------------------------

EXPERIMENT_ID = "JIGSAW_FUNDING_PRESSURE_VOLATILITY_PREREGISTRATION_V0"
EXECUTION_PHASE_ID = "JIGSAW_FUNDING_PRESSURE_VOLATILITY_EXECUTION_ENABLEMENT_V0"

PREREGISTRATION_MERGE_SHA = "98e9dbcbec5dab18f7498cf4c5df77e14a8d5569"
CONTRACT_DIGEST = "sha256:749641cbee99bc769a6095e2a5877e4ccf1c46db0a82860885eedc06734cd2d6"
PIT_CERTIFICATION_MERGE_SHA = "23dd5cb5791d5b97dff7904e34fd18e383776856"
PIT_CERTIFICATE_DIGEST = "sha256:76bbf05d1ab253f039bdd565bd19b563d19f4e1117f344ae495cac46bea0ffcc"
FUNDING_MATERIALIZATION_INDEX_DIGEST = "sha256:ceb12a1686f96f328ef54d5bafc184b848fa40ff7a2c71e28dc434a4854486c1"
FUNDING_EVIDENCE_SET_DIGEST = "sha256:3677e5aeafd17c47e4951b2095d6247c8fb7cd3fb603cc70d5ea5658fd768faa"
OHLCV_EVIDENCE_SET_DIGEST = "sha256:249fcc9e0018770cb0bde80ff3d2a492fc4bf6edc0bb2c9abad2c3d44fe03d82"

# Exact ordered 20-member panel (order is identity-bearing for input binding
# even though the median/mean aggregations below are order independent).
PANEL: tuple[str, ...] = (
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT",
    "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT",
    "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT",
    "LDOUSDT", "APTUSDT",
)
MINIMUM_BREADTH = 20
MAX_FUNDING_EVENT_AGE = timedelta(hours=24)
HISTORY_OBSERVATIONS = 365
FORWARD_HOURS = 24
LOW_THRESHOLD = Fraction(1, 3)
HIGH_THRESHOLD = Fraction(2, 3)

FIRST_COMBINED_ELIGIBLE_DECISION = "2023-10-19T00:00:00Z"
LAST_COMBINED_ELIGIBLE_DECISION = "2025-06-19T00:00:00Z"
COMBINED_PIT_ELIGIBLE_DECISIONS_TOTAL = 610

KILL_CONDITIONS = (
    "KILLED_NO_CLEAN_FUNDING_STATE",
    "BLOCKED_BY_FUNDING_COVERAGE",
    "BLOCKED_BY_PIT_ALIGNMENT",
    "BLOCKED_BY_SEALED_BREADTH_BOUNDARY",
    "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST",
)
PRIMARY_PROPOSITION_SUPPORTED = "PRIMARY_PROPOSITION_SUPPORTED"

# This phase does not freeze/instantiate an execution implementation SHA: it
# is only known after this candidate is committed. Leaving it unset (rather
# than guessing the future commit hash) makes the authorization gate below
# provably unsatisfiable in this phase -- there is no artifact that can
# authorize a real run yet.
EXECUTION_IMPLEMENTATION_SHA: str | None = None


class InputBindingError(ValueError):
    """Supplied inputs do not bind to the frozen canonical parents; fail closed."""


class ExecutionNotAuthorizedError(RuntimeError):
    """No valid execution authorization artifact was supplied; fail closed."""


class DuplicateFundingTimestampError(ValueError):
    """Two admissible events for one member share a funding_time_ms with
    disagreeing rates. See the F4 disposition note in the module docstring:
    this is a fail-closed defense, never a tie-break."""


# --------------------------------------------------------------------------
# Feature: FUNDING_PRESSURE
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FundingEvent:
    symbol: str
    funding_time_ms: int
    funding_time_utc: str
    funding_rate: str  # exact decimal string, as materialized by
    # qntylab.binance_um_funding_settlement (never a float)


def _rate_decimal(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"non-finite/invalid funding rate: {raw!r}") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite funding rate: {raw!r}")
    return value


def _require_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(UTC)


def validate_decision_time(decision_time: datetime) -> datetime:
    """Enforce the frozen 'daily 00:00:00Z decision time' definition."""
    value = _require_utc(decision_time)
    if (value.hour, value.minute, value.second, value.microsecond) != (0, 0, 0, 0):
        raise ValueError("decision_time must be exactly 00:00:00.000000Z")
    return value


def select_latest_funding_event(events: Sequence[FundingEvent], decision_time: datetime) -> FundingEvent | None:
    """feature.formula: e_i = max{e: funding_time_i(e) <= t and t-24h < funding_time_i(e)}.

    Strict on the lower (age) bound and inclusive on the upper bound, exactly
    as ``member_eligibility`` states: ``decision_time-24h < funding_time <=
    decision_time``. An event exactly 24h old (age == 24h) therefore fails
    the strict lower bound and is rejected as stale. Returns None if no
    admissible event exists (fail-closed member absence).
    """
    t = validate_decision_time(decision_time)
    lower_exclusive = t - MAX_FUNDING_EVENT_AGE
    admissible = [e for e in events if lower_exclusive < _require_utc(datetime.fromisoformat(e.funding_time_utc.replace("Z", "+00:00"))) <= t]
    if not admissible:
        return None
    max_ts = max(e.funding_time_ms for e in admissible)
    tied = [e for e in admissible if e.funding_time_ms == max_ts]
    if len(tied) > 1:
        rates = {e.funding_rate for e in tied}
        if len(rates) > 1:
            raise DuplicateFundingTimestampError(
                f"member {tied[0].symbol!r} has {len(tied)} admissible events at "
                f"funding_time_ms={max_ts} with disagreeing rates {sorted(rates)}"
            )
        return tied[0]
    return tied[0]


def compute_funding_pressure(panel_events: Mapping[str, FundingEvent | None]) -> Decimal | None:
    """feature.cross_sectional_aggregation: MEDIAN(abs(latest_known_funding_rate)).

    FAIL_CLOSED (returns None): any missing member, any member with no
    admissible event, or an unparseable/non-finite rate blocks the entire
    daily state. Requires the exact 20-member panel, no more, no fewer.
    """
    if set(panel_events) != set(PANEL) or len(panel_events) != MINIMUM_BREADTH:
        return None
    magnitudes: list[Decimal] = []
    for symbol in PANEL:
        event = panel_events[symbol]
        if event is None or event.symbol != symbol:
            return None
        try:
            magnitudes.append(abs(_rate_decimal(event.funding_rate)))
        except ValueError:
            return None
    ordered = sorted(magnitudes)  # sorts by value; symbol order never enters
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def compute_pit_ecdf(prior_365: Sequence[Decimal], current: Decimal) -> Fraction:
    """feature.normalization: CDF365(current) = count(v <= current) / count(v),
    v = 365 prior daily observations plus current (366 total). Exact
    rational (Fraction) result -- never a float -- so tertile boundary
    comparisons in classify_funding_state are exact.
    """
    if len(prior_365) != HISTORY_OBSERVATIONS:
        raise ValueError(f"exactly {HISTORY_OBSERVATIONS} prior observations required for PIT warmup, got {len(prior_365)}")
    population = list(prior_365) + [current]
    count_le = sum(1 for v in population if v <= current)  # inclusive <= ECDF, ties share percentile
    return Fraction(count_le, len(population))


def classify_funding_state(percentile: Fraction) -> str:
    """feature.state_bins: LOW <= 1/3 (inclusive); MID strictly between;
    HIGH >= 2/3 (inclusive). Exact rational comparison, no float tolerance.
    """
    if percentile <= LOW_THRESHOLD:
        return "LOW"
    if percentile >= HIGH_THRESHOLD:
        return "HIGH"
    return "MID"


# --------------------------------------------------------------------------
# Outcome: FUTURE_MARKET_WIDE_REALIZED_VOLATILITY
# --------------------------------------------------------------------------


def compute_hourly_asset_returns(closes: Mapping[str, float | None], prior_closes: Mapping[str, float | None]) -> dict[str, float]:
    """outcome: hourly simple close-to-close return per member for one hourly
    interval. FAIL_CLOSED per member (omitted from the result) on a missing,
    non-finite, or non-positive close at either end; no gap bridging is
    performed here or anywhere else in this executor -- the caller supplies
    exactly the two adjacent hourly closes it wants a return for.
    """
    out: dict[str, float] = {}
    for symbol in closes:
        c1, c0 = closes.get(symbol), prior_closes.get(symbol)
        if c1 is None or c0 is None:
            continue
        if not (isinstance(c1, (int, float)) and isinstance(c0, (int, float))):
            continue
        if not (c1 == c1 and c0 == c0):  # NaN check without importing math for this
            continue
        if not (c0 > 0 and c1 > 0 and c0 not in (float("inf"), float("-inf")) and c1 not in (float("inf"), float("-inf"))):
            continue
        out[symbol] = c1 / c0 - 1.0
    return out


def compute_equal_weight_market_returns(hourly_asset_returns: Sequence[Mapping[str, float]]) -> list[float | None]:
    """outcome.market_return_definition: equal-weight arithmetic mean across
    all 20 panel members, per completed hourly interval. FAIL_CLOSED (None)
    for any interval that does not have exactly 20/20 valid member returns;
    no partial-panel averaging.
    """
    result: list[float | None] = []
    for hourly in hourly_asset_returns:
        if set(hourly) != set(PANEL) or len(hourly) != MINIMUM_BREADTH:
            result.append(None)
            continue
        result.append(sum(hourly[s] for s in PANEL) / MINIMUM_BREADTH)
    return result


def compute_rv24(market_returns_t1_to_t24: Sequence[float | None]) -> float | None:
    """outcome.realized_volatility_estimator: sqrt(mean(r_{t+1:t+24}^2)),
    zero-mean (no demeaning), no annualization. FAIL_CLOSED (None) unless
    exactly 24 completed, valid market returns are supplied.
    """
    if len(market_returns_t1_to_t24) != FORWARD_HOURS:
        return None
    if any(r is None for r in market_returns_t1_to_t24):
        return None
    mean_sq = sum(r * r for r in market_returns_t1_to_t24) / FORWARD_HOURS
    return mean_sq ** 0.5


# --------------------------------------------------------------------------
# Primary statistic and (empty) canonical robustness set
# --------------------------------------------------------------------------


def compute_primary_contrast(labeled_rv24: Sequence[tuple[str, float]]) -> dict[str, Any]:
    """primary_statistic: mean(RV24 | HIGH) - mean(RV24 | LOW), one signed
    contrast only. MID never enters the primary statistic. FAIL_CLOSED
    (value=None) if either required bin (HIGH or LOW) is empty -- an empty
    required bin never invents a result.
    """
    high = [rv for state, rv in labeled_rv24 if state == "HIGH"]
    low = [rv for state, rv in labeled_rv24 if state == "LOW"]
    mid_count = sum(1 for state, _ in labeled_rv24 if state == "MID")
    if not high or not low:
        return {"value": None, "high_count": len(high), "low_count": len(low), "mid_count": mid_count, "blocked_reason": "EMPTY_REQUIRED_PRIMARY_BIN"}
    mean_high, mean_low = sum(high) / len(high), sum(low) / len(low)
    return {"value": mean_high - mean_low, "high_count": len(high), "low_count": len(low), "mid_count": mid_count, "mean_high": mean_high, "mean_low": mean_low, "blocked_reason": None}


def compute_preregistered_robustness(primary: Mapping[str, Any]) -> dict[str, Any]:
    """The frozen ``preregistration.json`` contract does not define any
    robustness checks (no bootstrap, no calendar-half split, no cost
    sensitivity, no tail trim, no leave-one-out) -- only a single primary
    HIGH-minus-LOW contrast. Inventing one here would be exactly the kind of
    new scientific choice this phase must not make (governing spec section
    4). This function therefore returns an explicit, empty, clearly-labeled
    report rather than silently omitting robustness or inventing checks.

    It cannot replace or mutate the primary result: it takes the already
    computed primary contrast read-only and never returns anything under the
    key ``"value"`` or ``"primary"`` that a caller could substitute for
    ``compute_primary_contrast``'s output.
    """
    return {
        "canonical_robustness_checks_defined_in_contract": (),
        "checks": {},
        "note": "preregistration.json defines exactly one primary statistic and no robustness checks; none are invented here",
        "primary_value_echo_readonly": primary.get("value"),
    }


def adjudicate_frozen_proposition(*, funding_state_clean: bool, funding_coverage_ok: bool, pit_alignment_ok: bool, sealed_boundary_respected: bool, primary: Mapping[str, Any]) -> str:
    """kill_conditions / primary_hypotheses adjudication, in the frozen
    precedence implied by ``execution_gate``/``kill_conditions`` ordering:
    coverage and PIT/boundary integrity are checked before the funding state
    itself, which is checked before the directional contrast.
    """
    if not sealed_boundary_respected:
        return "BLOCKED_BY_SEALED_BREADTH_BOUNDARY"
    if not funding_coverage_ok:
        return "BLOCKED_BY_FUNDING_COVERAGE"
    if not pit_alignment_ok:
        return "BLOCKED_BY_PIT_ALIGNMENT"
    if not funding_state_clean:
        return "KILLED_NO_CLEAN_FUNDING_STATE"
    if primary.get("value") is None:
        return "KILLED_NO_CLEAN_FUNDING_STATE"
    if primary["value"] <= 0:
        return "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
    return PRIMARY_PROPOSITION_SUPPORTED


# --------------------------------------------------------------------------
# Input binding (fail closed on any parent/evidence mismatch)
# --------------------------------------------------------------------------


def validate_input_binding(supplied: Mapping[str, Any]) -> None:
    """Refuse inputs that do not bind to the frozen canonical parents. Fail
    closed: any mismatch raises InputBindingError and no computation proceeds.
    """
    checks = (
        ("preregistration_merge_sha", PREREGISTRATION_MERGE_SHA),
        ("contract_digest", CONTRACT_DIGEST),
        ("pit_certification_merge_sha", PIT_CERTIFICATION_MERGE_SHA),
        ("pit_certificate_digest", PIT_CERTIFICATE_DIGEST),
        ("funding_evidence_set_digest", FUNDING_EVIDENCE_SET_DIGEST),
        ("ohlcv_evidence_set_digest", OHLCV_EVIDENCE_SET_DIGEST),
    )
    for key, expected in checks:
        if key not in supplied:
            raise InputBindingError(f"missing required binding field: {key}")
        if supplied[key] != expected:
            raise InputBindingError(f"{key} mismatch: expected {expected!r}, got {supplied[key]!r}")
    panel = supplied.get("panel")
    if not isinstance(panel, (list, tuple)) or tuple(panel) != PANEL:
        raise InputBindingError("panel does not match the frozen exact ordered 20-member panel identity")
    window = supplied.get("decision_window")
    if not isinstance(window, Mapping):
        raise InputBindingError("missing decision_window binding")
    if window.get("first_combined_eligible_decision") != FIRST_COMBINED_ELIGIBLE_DECISION:
        raise InputBindingError("decision_window.first_combined_eligible_decision mismatch")
    if window.get("last_combined_eligible_decision") != LAST_COMBINED_ELIGIBLE_DECISION:
        raise InputBindingError("decision_window.last_combined_eligible_decision mismatch")
    if window.get("combined_pit_eligible_decisions_total") != COMBINED_PIT_ELIGIBLE_DECISIONS_TOTAL:
        raise InputBindingError("decision_window.combined_pit_eligible_decisions_total mismatch")


# --------------------------------------------------------------------------
# Authorization gate (schema only; no instance is created by this phase)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionAuthorizationSchema:
    """Documented shape of a future execution authorization artifact. This
    is a schema only -- this phase does NOT instantiate this dataclass with
    real values. See governing spec section 13.
    """

    authorization_id: str
    experiment_id: str
    preregistration_merge_sha: str
    contract_digest: str
    pit_certification_merge_sha: str
    pit_certificate_digest: str
    execution_implementation_sha: str
    funding_evidence_set_digest: str
    ohlcv_evidence_set_digest: str
    execution_scope: str  # must equal "ONE_FROZEN_HISTORICAL_RUN"
    outcome_access_scope: str  # must equal "EXACT_PREREGISTERED_OUTCOMES_ONLY"


REQUIRED_EXECUTION_SCOPE = "ONE_FROZEN_HISTORICAL_RUN"
REQUIRED_OUTCOME_ACCESS_SCOPE = "EXACT_PREREGISTERED_OUTCOMES_ONLY"


def authorize_execution(mode: str, authorization: Mapping[str, Any] | None) -> None:
    """Execution authority / outcome access authority gate.

    mode == "SYNTHETIC_FIXTURE": always permitted (test/dev only; no
    outcome-producing real data is implied by this mode).

    mode == "REAL_HISTORICAL": requires a fully matching authorization
    artifact. This phase creates no such artifact and does not freeze
    EXECUTION_IMPLEMENTATION_SHA (module constant is None), so this branch is
    provably unsatisfiable right now -- any REAL_HISTORICAL request is
    refused. This preserves execution_authority=NONE and
    outcome_access_authority=NONE from the canonical parents.
    """
    if mode == "SYNTHETIC_FIXTURE":
        return
    if mode != "REAL_HISTORICAL":
        raise ValueError(f"unknown execution mode: {mode!r}")
    if EXECUTION_IMPLEMENTATION_SHA is None:
        raise ExecutionNotAuthorizedError("no EXECUTION_IMPLEMENTATION_SHA has been frozen for this candidate; real execution is refused")
    if authorization is None:
        raise ExecutionNotAuthorizedError("real historical execution requires an execution authorization artifact; none supplied")
    required = {
        "preregistration_merge_sha": PREREGISTRATION_MERGE_SHA,
        "contract_digest": CONTRACT_DIGEST,
        "pit_certification_merge_sha": PIT_CERTIFICATION_MERGE_SHA,
        "pit_certificate_digest": PIT_CERTIFICATE_DIGEST,
        "execution_implementation_sha": EXECUTION_IMPLEMENTATION_SHA,
        "funding_evidence_set_digest": FUNDING_EVIDENCE_SET_DIGEST,
        "ohlcv_evidence_set_digest": OHLCV_EVIDENCE_SET_DIGEST,
        "execution_scope": REQUIRED_EXECUTION_SCOPE,
        "outcome_access_scope": REQUIRED_OUTCOME_ACCESS_SCOPE,
    }
    for key, expected in required.items():
        if authorization.get(key) != expected:
            raise ExecutionNotAuthorizedError(f"authorization field {key!r} does not match the frozen requirement")
    if "authorization_id" not in authorization or "experiment_id" not in authorization:
        raise ExecutionNotAuthorizedError("authorization missing identity fields")
    if authorization.get("experiment_id") != EXPERIMENT_ID:
        raise ExecutionNotAuthorizedError("authorization.experiment_id does not match this experiment")


# --------------------------------------------------------------------------
# Execution receipt
# --------------------------------------------------------------------------


def build_execution_receipt(
    *,
    panel: Sequence[str],
    decision_window: Mapping[str, Any],
    census: Mapping[str, int],
    state_counts: Mapping[str, int],
    primary: Mapping[str, Any],
    robustness: Mapping[str, Any],
    adjudication: str,
    execution_implementation_identity: str,
    artifact_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Deterministic execution receipt binding: experiment identity,
    preregistration merge SHA + contract digest, PIT certification merge SHA
    + PIT certificate digest, execution implementation identity, funding +
    OHLCV evidence-set digests, exact panel, decision-window identity,
    eligible/excluded census, state counts, primary statistic identity and
    value, robustness result identities, adjudication, and artifact hashes.
    No scientific authority beyond the exact frozen proposition is asserted.
    """
    body: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "execution_phase_id": EXECUTION_PHASE_ID,
        "preregistration_merge_sha": PREREGISTRATION_MERGE_SHA,
        "contract_digest": CONTRACT_DIGEST,
        "pit_certification_merge_sha": PIT_CERTIFICATION_MERGE_SHA,
        "pit_certificate_digest": PIT_CERTIFICATE_DIGEST,
        "execution_implementation_identity": execution_implementation_identity,
        "funding_evidence_set_digest": FUNDING_EVIDENCE_SET_DIGEST,
        "ohlcv_evidence_set_digest": OHLCV_EVIDENCE_SET_DIGEST,
        "panel": list(panel),
        "decision_window": dict(decision_window),
        "census": dict(census),
        "state_counts": dict(state_counts),
        "primary_statistic_identity": "mean(RV24|HIGH) - mean(RV24|LOW)",
        "primary_statistic": dict(primary),
        "robustness": dict(robustness),
        "adjudication": adjudication,
        "artifact_hashes": dict(artifact_hashes),
        "execution_authority": "NONE",
        "outcome_access_authority": "NONE",
        "router_authority": "NONE",
        "qnty_authority": "NONE",
        "strategy_authority": "NONE",
    }
    body["receipt_digest"] = sha256_bytes(canonical_bytes(body))
    return body


def receipt_json(receipt: Mapping[str, Any]) -> str:
    return json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
