"""Fresh, outcome-gated V2 executor for the frozen funding-pressure experiment.

The calculation helpers are pure and operate only on verified evidence types.
The controlled entrypoint performs the Foundation V0 order: bind, verify,
attest, validate, claim, then compute.  This module never creates an
authorization or invokes the production claim transport by itself.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from contextlib import contextmanager
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from pathlib import Path

from qntylab import jigsaw_funding_pressure_execution_foundation_v0 as foundation
from qntylab import jigsaw_funding_pressure_provenance_v0 as provenance

EXPERIMENT_ID = "JIGSAW_FUNDING_PRESSURE_VOLATILITY_PREREGISTRATION_V0"
V2_PHASE_ID = "JIGSAW_FUNDING_PRESSURE_VOLATILITY_EXECUTION_ENABLEMENT_V2"
V2_MODULE_PATH = "qntylab/jigsaw_funding_pressure_execution_v2.py"
PANEL = tuple(provenance.PANEL)
DECISION_COUNT = 610
FIRST_DECISION = datetime(2023, 10, 19, tzinfo=UTC)
LAST_DECISION = datetime(2025, 6, 19, tzinfo=UTC)
FORWARD_HOURS = 24
HISTORY_OBSERVATIONS = 365
SQRT_PRECISION = 50
SQRT_ROUNDING = ROUND_HALF_EVEN
V2_DECIMAL_CONTEXT = Context(prec=SQRT_PRECISION, rounding=SQRT_ROUNDING)
V2_CONTRACT_RELATIVE_PATH = "experiments/research/jigsaw_funding_pressure_volatility_v0/execution_enablement_v2_contract.json"
V2_REQUIRED_ANCESTORS = (
    provenance.PREREG_SHA,
    provenance.PIT_V1_SHA,
    "95a4a3659bdcca1df9223f69e06cee50a2b00369",
    "3685c13eb2c0237e16cab1a33ce8ea024424569b",
)
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


class V2Error(Exception):
    pass


class FrozenContractError(V2Error):
    pass


class ComputationError(V2Error):
    pass


class ReleaseBindingError(V2Error):
    pass


@contextmanager
def _v2_decimal_context():
    """Run contract-visible Decimal arithmetic independently of ambient state."""
    with localcontext(V2_DECIMAL_CONTEXT):
        yield


def decision_schedule() -> tuple[datetime, ...]:
    schedule = tuple(FIRST_DECISION + timedelta(days=i) for i in range(DECISION_COUNT))
    if schedule[-1] != LAST_DECISION:
        raise FrozenContractError("frozen decision schedule arithmetic drifted")
    return schedule


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ComputationError("timestamps must be timezone-aware UTC values")
    return value.astimezone(UTC)


def select_latest_eligible_funding(
    events: Sequence[foundation.VerifiedFundingEvent], decision_time: datetime, *, symbol: str
) -> foundation.VerifiedFundingEvent:
    t = _utc(decision_time)
    if any(event.symbol != symbol for event in events):
        raise ComputationError("wrong funding symbol")
    eligible = [
        event
        for event in events
        if t - timedelta(hours=24) < _utc(event.funding_time_utc) <= t
    ]
    if not eligible:
        raise ComputationError(f"missing eligible funding event for {symbol}")
    latest_ms = max(event.funding_time_ms for event in eligible)
    latest = [event for event in eligible if event.funding_time_ms == latest_ms]
    if len(latest) != 1:
        raise ComputationError(f"duplicate latest funding timestamp for {symbol}")
    return latest[0]


def median_abs_funding(events_by_symbol: Mapping[str, foundation.VerifiedFundingEvent]) -> Decimal:
    if tuple(events_by_symbol) != PANEL:
        raise ComputationError("funding input is not the exact ordered 20-member panel")
    with _v2_decimal_context():
        values: list[Decimal] = []
        for symbol in PANEL:
            try:
                event = events_by_symbol[symbol]
            except KeyError as exc:
                raise ComputationError(f"missing funding member {symbol}") from exc
            value = abs(event.funding_rate)
            if not value.is_finite():
                raise ComputationError("non-finite funding rate")
            values.append(value)
        values.sort()
        # N=20 is frozen as the arithmetic mean of the two central order statistics.
        return (values[9] + values[10]) / Decimal(2)


def ecdf_percentile(prior_365: Sequence[Decimal], current: Decimal) -> Fraction:
    if len(prior_365) != HISTORY_OBSERVATIONS:
        raise ComputationError("ECDF requires exactly 365 prior observations")
    if not current.is_finite() or any(not value.is_finite() for value in prior_365):
        raise ComputationError("ECDF values must be finite")
    values = tuple(prior_365) + (current,)
    return Fraction(sum(value <= current for value in values), 366)


def classify_state(percentile: Fraction) -> str:
    if percentile <= Fraction(1, 3):
        return "LOW"
    if percentile >= Fraction(2, 3):
        return "HIGH"
    return "MID"


def source_open_for_logical_close(logical_close: datetime) -> str:
    return (_utc(logical_close) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")


def hourly_asset_returns(
    bars: Sequence[foundation.VerifiedBarOpenClose], decision_time: datetime
) -> tuple[Decimal, ...]:
    if any(bar.symbol != bars[0].symbol for bar in bars) if bars else True:
        raise ComputationError("wrong or empty OHLCV series")
    by_open = {_utc(bar.source_open_time): bar.close for bar in bars}
    if len(by_open) != len(bars):
        raise ComputationError("duplicate source-open timestamp")
    t = _utc(decision_time)
    source_times = [_utc(source_open_for_logical_close(t + timedelta(hours=i))) for i in range(25)]
    if any(source_times[i + 1] != _utc(source_open_for_logical_close(t + timedelta(hours=i + 1))) for i in range(24)):
        raise ComputationError("non-contiguous OHLCV endpoint mapping")
    try:
        closes = [by_open[source] for source in source_times]
    except KeyError as exc:
        raise ComputationError("missing hourly bar; gap bridging is forbidden") from exc
    if any(not close.is_finite() or close <= 0 for close in closes):
        raise ComputationError("close prices must be finite and positive")
    with _v2_decimal_context():
        return tuple(closes[i + 1] / closes[i] - Decimal(1) for i in range(FORWARD_HOURS))


def market_returns(asset_returns_by_symbol: Sequence[Mapping[str, Decimal]]) -> tuple[Decimal, ...]:
    if len(asset_returns_by_symbol) != FORWARD_HOURS:
        raise ComputationError("exactly 24 hourly intervals are required")
    result: list[Decimal] = []
    for row in asset_returns_by_symbol:
        if tuple(row) != PANEL:
            raise ComputationError("each market return requires the exact 20-member panel")
        try:
            values = [row[symbol] for symbol in PANEL]
        except KeyError as exc:
            raise ComputationError("missing asset return") from exc
        if any(not value.is_finite() for value in values):
            raise ComputationError("non-finite asset return")
        with _v2_decimal_context():
            result.append(sum(values, Decimal(0)) / Decimal(len(PANEL)))
    return tuple(result)


def rv24(market_return_values: Sequence[Decimal]) -> Decimal:
    if len(market_return_values) != FORWARD_HOURS or any(
        not value.is_finite() for value in market_return_values
    ):
        raise ComputationError("RV24 requires exactly 24 finite market returns")
    with _v2_decimal_context():
        mean_square = sum((value * value for value in market_return_values), Decimal(0)) / Decimal(FORWARD_HOURS)
        result = mean_square.sqrt()
    if not result.is_finite():
        raise ComputationError("RV24 square root is non-finite")
    return result


@dataclass(frozen=True, slots=True)
class FrozenDecision:
    timestamp: str
    pressure: Decimal
    percentile_numerator: int
    percentile_denominator: int
    state: str
    rv24: Decimal


@dataclass(frozen=True, slots=True)
class FrozenExperimentResult:
    experiment_id: str
    schedule_identity: str
    decision_count: int
    decisions: tuple[FrozenDecision, ...]
    state_counts: Mapping[str, int]
    mean_rv24_high: Decimal | None
    mean_rv24_low: Decimal | None
    primary_contrast: Decimal | None
    adjudication: str
    result_digest: str


def _result_payload(result_without_digest: Mapping[str, object]) -> str:
    def safe(value: object) -> object:
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ComputationError("result contains a non-finite Decimal")
            return str(value)
        if isinstance(value, Mapping):
            return {str(key): safe(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [safe(item) for item in value]
        return value

    return foundation.canonical_json(safe(result_without_digest))


def adjudicate_primary(rows: Sequence[tuple[str, Decimal]]) -> tuple[Decimal | None, str]:
    high = [value for state, value in rows if state == "HIGH"]
    low = [value for state, value in rows if state == "LOW"]
    if not high or not low:
        return None, "BLOCKED_EMPTY_REQUIRED_PRIMARY_BIN"
    with _v2_decimal_context():
        contrast = sum(high, Decimal(0)) / len(high) - sum(low, Decimal(0)) / len(low)
    return contrast, "POSITIVE_DIRECTIONAL_CONTRAST" if contrast > 0 else "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"


def compute_frozen_experiment(bundle: foundation.VerifiedEvidenceBundle) -> FrozenExperimentResult:
    """Pure calculation core. It performs no I/O or external effect."""
    if bundle.exact_panel != PANEL:
        raise ComputationError("evidence panel mismatch")
    schedule = decision_schedule()
    all_days = tuple(
        FIRST_DECISION - timedelta(days=HISTORY_OBSERVATIONS) + timedelta(days=i)
        for i in range(HISTORY_OBSERVATIONS + DECISION_COUNT)
    )
    pressures: list[Decimal] = []
    for timestamp in all_days:
        selected = {
            symbol: select_latest_eligible_funding(bundle.funding_by_symbol[symbol], timestamp, symbol=symbol)
            for symbol in PANEL
        }
        pressures.append(median_abs_funding(selected))
    rows: list[FrozenDecision] = []
    for index, timestamp in enumerate(schedule, start=HISTORY_OBSERVATIONS):
        current = pressures[index]
        percentile = ecdf_percentile(pressures[index - HISTORY_OBSERVATIONS : index], current)
        state = classify_state(percentile)
        returns = market_returns(
            tuple(
                {symbol: hourly_asset_returns(bundle.bars_by_symbol[symbol], timestamp)[hour] for symbol in PANEL}
                for hour in range(FORWARD_HOURS)
            )
        )
        rows.append(FrozenDecision(timestamp.isoformat().replace("+00:00", "Z"), current, percentile.numerator, percentile.denominator, state, rv24(returns)))
    primary, adjudication = adjudicate_primary([(row.state, row.rv24) for row in rows])
    high = [row.rv24 for row in rows if row.state == "HIGH"]
    low = [row.rv24 for row in rows if row.state == "LOW"]
    with _v2_decimal_context():
        mean_high = sum(high, Decimal(0)) / len(high) if high else None
        mean_low = sum(low, Decimal(0)) / len(low) if low else None
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "schedule_identity": f"{rows[0].timestamp}..{rows[-1].timestamp};00:00:00Z;daily",
        "decision_count": len(rows),
        "decisions": [dataclasses.asdict(row) for row in rows],
        "state_counts": {state: sum(row.state == state for row in rows) for state in ("LOW", "MID", "HIGH")},
        "mean_rv24_high": mean_high,
        "mean_rv24_low": mean_low,
        "primary_contrast": primary,
        "adjudication": adjudication,
    }
    digest = "sha256:" + hashlib.sha256(_result_payload(payload).encode("utf-8")).hexdigest()
    return FrozenExperimentResult(EXPERIMENT_ID, payload["schedule_identity"], len(rows), tuple(rows), payload["state_counts"], mean_high, mean_low, primary, adjudication, digest)


@dataclass(frozen=True, slots=True)
class V2AuthorizationEnvelope:
    foundation: foundation.AuthorizationEnvelope
    execution_enablement_v2_contract_digest: str


def parse_authorization_envelope(payload: Mapping[str, object]) -> V2AuthorizationEnvelope:
    required = {field.name for field in dataclasses.fields(foundation.AuthorizationEnvelope)} | {"execution_enablement_v2_contract_digest"}
    if set(payload) != required:
        raise foundation.AuthorizationValidationError("authorization fields must be exact; missing or extra fields present")
    values = {name: payload[name] for name in required if name != "execution_enablement_v2_contract_digest"}
    if not all(isinstance(value, str) for value in values.values()) or not isinstance(payload["execution_enablement_v2_contract_digest"], str):
        raise foundation.AuthorizationValidationError("authorization fields must be strings")
    return V2AuthorizationEnvelope(foundation.AuthorizationEnvelope(**values), payload["execution_enablement_v2_contract_digest"])


def v2_contract_digest(*, repository_root: Path | None = None) -> str:
    root = (repository_root or provenance.ROOT).resolve()
    path = foundation.resolve_within_repository(V2_CONTRACT_RELATIVE_PATH, root)
    contract = json.loads(path.read_text(encoding="utf-8"))
    expected = contract.get("execution_enablement_v2_contract_digest")
    actual = provenance.canonical_digest(provenance._without(contract, "execution_enablement_v2_contract_digest"))
    if expected != actual:
        raise FrozenContractError("V2 contract self-digest mismatch")
    return expected


def validate_v2_authorization(envelope: V2AuthorizationEnvelope, *, repository_root: Path | None = None) -> None:
    if envelope.execution_enablement_v2_contract_digest != v2_contract_digest(repository_root=repository_root):
        raise foundation.AuthorizationValidationError("V2 contract digest mismatch")
    expected = foundation.canonical_authorization_binding_expectations(executor_source_sha256=envelope.foundation.executor_source_sha256)
    expected = dataclasses.replace(expected, reviewed_executor_candidate_sha=envelope.foundation.reviewed_executor_candidate_sha, canonical_runtime_merge_sha=envelope.foundation.canonical_runtime_merge_sha)
    foundation.validate_authorization_envelope(envelope.foundation, expected)
    if not _SHA1.fullmatch(envelope.foundation.reviewed_executor_candidate_sha) or not _SHA1.fullmatch(envelope.foundation.canonical_runtime_merge_sha) or not _SHA256.fullmatch(envelope.foundation.executor_source_sha256):
        raise foundation.AuthorizationValidationError("V2 release identity is malformed")


@dataclass(frozen=True, slots=True)
class V2RuntimeAttestation:
    foundation: foundation.RuntimeAttestation
    candidate_source_sha256: str


def attest_v2_runtime(*, authorization: V2AuthorizationEnvelope, repo_root: Path | None = None, git_runner=subprocess.run) -> V2RuntimeAttestation:
    root = (repo_root or provenance.ROOT).resolve()
    def git(args: list[str]) -> str:
        return foundation._run_git_text(args, root, git_runner)
    top = Path(git(["rev-parse", "--show-toplevel"])).resolve()
    if top != root:
        raise foundation.RuntimeAttestationError("wrong repository root")
    head = git(["rev-parse", "HEAD"])
    status = git(["status", "--porcelain"])
    if status:
        raise foundation.RuntimeAttestationError("worktree is not clean")
    if head != authorization.foundation.canonical_runtime_merge_sha:
        raise foundation.RuntimeAttestationError("runtime HEAD does not equal authorized canonical merge")
    for ancestor in V2_REQUIRED_ANCESTORS + (authorization.foundation.reviewed_executor_candidate_sha,):
        try:
            provenance.verify_git_ancestry(head, root=root, ancestors=(ancestor,), git_runner=git_runner)
        except AssertionError as exc:
            raise foundation.RuntimeAttestationError(str(exc)) from exc
    module = foundation.resolve_within_repository(V2_MODULE_PATH, root)
    runtime_bytes = module.read_bytes()
    runtime_digest = hashlib.sha256(runtime_bytes).hexdigest()
    candidate_bytes = git(["show", f"{authorization.foundation.reviewed_executor_candidate_sha}:{V2_MODULE_PATH}"]).encode("utf-8")
    if candidate_bytes != runtime_bytes:
        raise ReleaseBindingError("candidate V2 source bytes differ from runtime source bytes")
    if runtime_digest != authorization.foundation.executor_source_sha256:
        raise ReleaseBindingError("authorized V2 source digest differs from runtime source digest")
    attested = foundation.RuntimeAttestation(str(top), head, str(module), runtime_digest, True, V2_REQUIRED_ANCESTORS + (authorization.foundation.reviewed_executor_candidate_sha,))
    return V2RuntimeAttestation(attested, hashlib.sha256(candidate_bytes).hexdigest())


def execute_authorized_frozen_experiment_v2(
    *,
    authorization: V2AuthorizationEnvelope,
    evidence_loader: Callable[[], foundation.VerifiedEvidenceBundle],
    runtime_attestor: Callable[[V2AuthorizationEnvelope], V2RuntimeAttestation],
    transport: foundation.AtMostOnceClaimTransport,
    computation: Callable[[foundation.VerifiedEvidenceBundle], FrozenExperimentResult] = compute_frozen_experiment,
) -> dict[str, object]:
    """Controlled seam; computation is unreachable until the remote claim succeeds."""
    bundle = evidence_loader()
    runtime = runtime_attestor(authorization)
    validate_v2_authorization(authorization)
    foundation.validate_authorization_against_runtime(authorization.foundation, runtime.foundation)
    outcome = foundation.claim_authorization_once(authorization.foundation.authorization_id, runtime.foundation.runtime_head_sha, transport)
    if outcome is not foundation.ClaimOutcome.CLAIMED:
        raise foundation.AtMostOnceClaimError("authorization is already consumed")
    result = computation(bundle)
    receipt = foundation.build_receipt_provenance(authorization=authorization.foundation, attestation=runtime.foundation)
    return {
        "phase_id": V2_PHASE_ID,
        "provenance": dataclasses.asdict(receipt),
        "provenance_digest": foundation.receipt_digest(receipt),
        "result_digest": result.result_digest,
        "primary_statistic": result.primary_contrast,
        "adjudication": result.adjudication,
        "completion_state": foundation.AuthorizationLifecycleState.CONSUMED_COMPLETE.value,
        "downstream_strategy_authority": "NONE",
        "downstream_router_authority": "NONE",
        "downstream_qnty_authority": "NONE",
    }
