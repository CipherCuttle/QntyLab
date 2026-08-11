from __future__ import annotations

import dataclasses
import hashlib
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext, localcontext
from fractions import Fraction

import pytest

from qntylab import jigsaw_funding_pressure_execution_foundation_v0 as foundation
from qntylab import jigsaw_funding_pressure_execution_v2 as v2


def event(symbol: str, timestamp: datetime, rate: str, *, ms_offset: int = 0) -> foundation.VerifiedFundingEvent:
    timestamp = timestamp.astimezone(UTC)
    ms = int(timestamp.timestamp() * 1000) + ms_offset
    iso = (timestamp + timedelta(milliseconds=ms_offset)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return foundation.VerifiedFundingEvent(symbol, ms, iso, Decimal(rate))


def bar(symbol: str, timestamp: datetime, close: str) -> foundation.VerifiedBarOpenClose:
    return foundation.VerifiedBarOpenClose(symbol, timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"), Decimal(close))


def test_schedule_is_exactly_610_daily_decisions():
    schedule = v2.decision_schedule()
    assert len(schedule) == 610
    assert schedule[0] == v2.FIRST_DECISION
    assert schedule[-1] == v2.LAST_DECISION
    assert all(item.hour == item.minute == item.second == item.microsecond == 0 for item in schedule)


def test_funding_window_is_strict_at_left_and_inclusive_at_right():
    t = datetime(2024, 1, 2, tzinfo=UTC)
    symbol = "BCHUSDT"
    exact_left = event(symbol, t - timedelta(hours=24), "1")
    one_ms_inside = event(symbol, t - timedelta(hours=24) + timedelta(milliseconds=1), "2")
    exact_right = event(symbol, t, "3")
    after = event(symbol, t + timedelta(milliseconds=1), "4")
    selected = v2.select_latest_eligible_funding([exact_left, one_ms_inside, exact_right, after], t, symbol=symbol)
    assert selected.funding_rate == Decimal("3")
    assert v2.select_latest_eligible_funding([one_ms_inside], t, symbol=symbol).funding_rate == Decimal("2")


def test_funding_fail_closed_for_missing_wrong_symbol_and_duplicate_latest():
    t = datetime(2024, 1, 2, tzinfo=UTC)
    with pytest.raises(v2.ComputationError):
        v2.select_latest_eligible_funding([], t, symbol="BCHUSDT")
    with pytest.raises(v2.ComputationError):
        v2.select_latest_eligible_funding([event("XRPUSDT", t, "1")], t, symbol="BCHUSDT")
    duplicate = event("BCHUSDT", t, "1")
    with pytest.raises(v2.ComputationError):
        v2.select_latest_eligible_funding([duplicate, duplicate], t, symbol="BCHUSDT")


def test_even_20_median_is_deterministic_and_absolute():
    values = {symbol: event(symbol, datetime(2024, 1, 1, tzinfo=UTC), str(index - 10)) for index, symbol in enumerate(v2.PANEL)}
    assert v2.median_abs_funding(values) == Decimal("5")


def test_contract_decimal_arithmetic_is_independent_of_ambient_context():
    original_prec = getcontext().prec
    original_rounding = getcontext().rounding
    values = {
        symbol: event(
            symbol,
            datetime(2024, 1, 1, tzinfo=UTC),
            "0" if index < 9 else "1.7901234" if index == 9 else "1.7901235" if index == 10 else "2",
        )
        for index, symbol in enumerate(v2.PANEL)
    }
    asset_returns = tuple(
        {symbol: Decimal("1.234567") if symbol == v2.PANEL[0] else Decimal("0") for symbol in v2.PANEL}
        for _ in range(24)
    )
    primary_rows = (("HIGH", Decimal("1.234567")), ("HIGH", Decimal("2.345678")), ("LOW", Decimal("0.123456")), ("LOW", Decimal("0.234567")))

    def calculate():
        return (
            v2.median_abs_funding(values),
            v2.hourly_asset_returns(
                [bar("BCHUSDT", datetime(2024, 1, 1, tzinfo=UTC) - timedelta(hours=1) + timedelta(hours=i), str(i + 1)) for i in range(25)],
                datetime(2024, 1, 1, tzinfo=UTC),
            )[0],
            v2.market_returns(asset_returns)[0],
            v2.rv24(v2.market_returns(asset_returns)),
            v2.adjudicate_primary(primary_rows)[0],
        )

    with localcontext() as ambient:
        ambient.prec = 2
        ambient.rounding = ROUND_DOWN
        low_precision = calculate()
    with localcontext() as ambient:
        ambient.prec = 7
        ambient.rounding = ROUND_UP
        other_precision = calculate()

    assert low_precision == other_precision
    assert getcontext().prec == original_prec
    assert getcontext().rounding == original_rounding
    assert low_precision[0] == Decimal("1.79012345")


def test_ecdf_uses_366_inclusive_observations_and_exact_boundaries():
    prior = [Decimal("0")] * 121 + [Decimal("1")] * 244
    assert v2.ecdf_percentile(prior, Decimal("0")) == Fraction(122, 366)
    assert v2.classify_state(Fraction(1, 3)) == "LOW"
    assert v2.classify_state(Fraction(2, 3)) == "HIGH"
    assert v2.classify_state(Fraction(1, 2)) == "MID"
    with pytest.raises(v2.ComputationError):
        v2.ecdf_percentile(prior[:-1], Decimal("0"))


def test_ohlcv_mapping_uses_source_open_t_minus_one_hour():
    t = datetime(2024, 1, 2, tzinfo=UTC)
    bars = [bar("BCHUSDT", t - timedelta(hours=1) + timedelta(hours=i), str(i + 1)) for i in range(25)]
    returns = v2.hourly_asset_returns(bars, t)
    assert len(returns) == 24
    assert returns[0] == Decimal("1")
    assert bars[0].source_open_time == v2.source_open_for_logical_close(t)
    assert bars[1].source_open_time == v2.source_open_for_logical_close(t + timedelta(hours=1))


def test_ohlcv_missing_hour_and_failed_v0_endpoint_alignment_fail_closed():
    t = datetime(2024, 1, 2, tzinfo=UTC)
    bars = [bar("BCHUSDT", t + timedelta(hours=i), str(i + 1)) for i in range(24)]
    with pytest.raises(v2.ComputationError):
        v2.hourly_asset_returns(bars, t)


def test_market_return_and_rv24_analytic_paths():
    zero = tuple({symbol: Decimal("0") for symbol in v2.PANEL} for _ in range(24))
    assert v2.rv24(v2.market_returns(zero)) == Decimal("0")
    constant = tuple({symbol: Decimal("0.25") for symbol in v2.PANEL} for _ in range(24))
    assert v2.rv24(v2.market_returns(constant)) == Decimal("0.25")
    with pytest.raises(v2.ComputationError):
        v2.market_returns(zero[:-1])


def test_primary_adjudication_positive_zero_negative_and_empty_bins():
    assert v2.adjudicate_primary((("HIGH", Decimal("2")), ("LOW", Decimal("1")))) == (Decimal("1"), "POSITIVE_DIRECTIONAL_CONTRAST")
    assert v2.adjudicate_primary((("HIGH", Decimal("1")), ("LOW", Decimal("1"))))[1] == "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
    assert v2.adjudicate_primary((("HIGH", Decimal("1")), ("LOW", Decimal("2"))))[1] == "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
    assert v2.adjudicate_primary((("MID", Decimal("1")),))[1] == "BLOCKED_EMPTY_REQUIRED_PRIMARY_BIN"


def test_contract_is_self_digest_and_outcome_blind():
    digest = v2.v2_contract_digest()
    assert digest.startswith("sha256:")
    assert v2.v2_contract_digest() == digest


def test_parser_has_one_identity_channel_and_rejects_v1_override():
    expected = foundation.canonical_authorization_binding_expectations(executor_source_sha256="a" * 64)
    payload = {
        **{field.name: getattr(expected, field.name) for field in dataclasses.fields(expected)},
        "authorization_id": "jigsaw-funding-pressure-v0-" + "a" * 32,
        "authorization_status": "AUTHORIZED_UNUSED",
        "execution_enablement_v2_contract_digest": v2.v2_contract_digest(),
    }
    parsed = v2.parse_authorization_envelope(payload)
    assert parsed.foundation.executor_source_sha256 == "a" * 64
    payload["actual_execution_implementation_sha"] = "b" * 40
    with pytest.raises(foundation.AuthorizationValidationError):
        v2.parse_authorization_envelope(payload)


class FakeTransport:
    def __init__(self, status: str):
        self.status = status

    def create_ref(self, ref: str, sha: str) -> foundation.ClaimRefResult:
        return foundation.ClaimRefResult(self.status)


def test_claim_happens_before_computation_and_replay_never_computes(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(v2, "validate_v2_authorization", lambda envelope: calls.append("bind"))
    expected = foundation.canonical_authorization_binding_expectations(executor_source_sha256="b" * 64)
    auth = v2.V2AuthorizationEnvelope(
        foundation.AuthorizationEnvelope(
            authorization_id="jigsaw-funding-pressure-v0-" + "a" * 32,
            experiment_id=expected.experiment_id,
            preregistration_merge_sha=expected.preregistration_merge_sha,
            contract_digest=expected.contract_digest,
            pit_v1_merge_sha=expected.pit_v1_merge_sha,
            pit_v1_certificate_digest=expected.pit_v1_certificate_digest,
            provenance_baseline_digest=expected.provenance_baseline_digest,
            funding_history_coverage_digest=expected.funding_history_coverage_digest,
            execution_foundation_contract_digest=expected.execution_foundation_contract_digest,
            funding_evidence_set_digest=expected.funding_evidence_set_digest,
            ohlcv_evidence_set_digest=expected.ohlcv_evidence_set_digest,
            reviewed_executor_candidate_sha="c" * 40,
            canonical_runtime_merge_sha="a" * 40,
            executor_source_sha256="b" * 64,
            execution_scope=expected.execution_scope,
            outcome_access_scope=expected.outcome_access_scope,
            authorization_status="AUTHORIZED_UNUSED",
        ),
        v2.v2_contract_digest(),
    )
    runtime = v2.V2RuntimeAttestation(foundation.RuntimeAttestation("/repo", "a" * 40, "/repo/qntylab/jigsaw_funding_pressure_execution_v2.py", "b" * 64, True, ()), "b" * 64)
    monkeypatch.setattr(v2.foundation, "validate_authorization_against_runtime", lambda authorization, attestation: calls.append("release"))
    def attest(envelope):
        calls.append("attest")
        return runtime
    def load():
        calls.append("load")
        return object()
    def compute(bundle):
        calls.append("compute")
        return object()
    with pytest.raises(foundation.AtMostOnceClaimError):
        v2.execute_authorized_frozen_experiment_v2(
            authorization=auth, evidence_loader=load, runtime_attestor=attest,
            transport=FakeTransport("ALREADY_EXISTS"), computation=compute,
        )
    assert "compute" not in calls
    calls.clear()
    with pytest.raises(foundation.AtMostOnceClaimError):
        v2.execute_authorized_frozen_experiment_v2(
            authorization=auth, evidence_loader=load, runtime_attestor=attest,
            transport=FakeTransport("ALREADY_EXISTS"), computation=compute,
        )
    assert "compute" not in calls


def test_foundation_lifecycle_consumed_states_are_terminal():
    for state in (foundation.AuthorizationLifecycleState.CONSUMED_INCOMPLETE, foundation.AuthorizationLifecycleState.CONSUMED_COMPLETE):
        with pytest.raises(foundation.LifecycleTransitionError):
            foundation.transition_authorization_lifecycle(state, foundation.AuthorizationLifecycleState.AUTHORIZED_UNUSED)


class GitBytesRunner:
    def __init__(self, stdout: object, returncode: int = 0, stderr: object = b""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[dict[str, object]] = []

    def __call__(self, args, **kwargs):
        self.calls.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, self.stderr)


@pytest.mark.parametrize("blob", [b"example\n", b"example\n\n", b"\nexample\n"])
def test_lossless_git_blob_retrieval_preserves_all_source_bytes(blob, tmp_path):
    runner = GitBytesRunner(blob)
    assert v2._run_git_bytes(["show", "candidate:path"], tmp_path, runner) == blob
    assert runner.calls[0]["text"] is False


def test_lossless_git_blob_retrieval_fails_closed_on_git_error(tmp_path):
    with pytest.raises(foundation.RuntimeAttestationError, match="git command failed"):
        v2._run_git_bytes(["show", "candidate:path"], tmp_path, GitBytesRunner(b"", returncode=1, stderr=b"missing blob"))


def test_lossless_git_blob_retrieval_rejects_text_stdout(tmp_path):
    with pytest.raises(foundation.RuntimeAttestationError, match="non-byte stdout"):
        v2._run_git_bytes(["show", "candidate:path"], tmp_path, GitBytesRunner("example\n"))


def _attestation_fixture(tmp_path, candidate_bytes, *, authorized_digest=None):
    module = tmp_path / v2.V2_MODULE_PATH
    module.parent.mkdir(parents=True)
    module.write_bytes(candidate_bytes)
    head = "a" * 40
    candidate = "b" * 40
    digest = authorized_digest or hashlib.sha256(candidate_bytes).hexdigest()
    expected = foundation.canonical_authorization_binding_expectations(executor_source_sha256=digest)
    envelope = dataclasses.replace(expected, reviewed_executor_candidate_sha=candidate, canonical_runtime_merge_sha=head)
    authorization = v2.V2AuthorizationEnvelope(envelope, "unused")

    class Runner:
        def __call__(self, args, **kwargs):
            command = args[1:]
            if command == ["rev-parse", "--show-toplevel"]:
                return subprocess.CompletedProcess(args, 0, str(tmp_path), b"")
            if command == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, head, b"")
            if command == ["status", "--porcelain"]:
                return subprocess.CompletedProcess(args, 0, "", b"")
            if command == ["show", f"{candidate}:{v2.V2_MODULE_PATH}"]:
                return subprocess.CompletedProcess(args, 0, candidate_bytes, b"")
            if command[:2] == ["merge-base", "--is-ancestor"]:
                return subprocess.CompletedProcess(args, 0, "", "")
            raise AssertionError(command)

    return authorization, Runner()


def test_attestation_exact_source_identity_passes_and_digest_matches(tmp_path, monkeypatch):
    blob = b"\nexample\n\n"
    authorization, runner = _attestation_fixture(tmp_path, blob)
    monkeypatch.setattr(v2.provenance, "verify_git_ancestry", lambda *args, **kwargs: None)
    result = v2.attest_v2_runtime(authorization=authorization, repo_root=tmp_path, git_runner=runner)
    assert result.candidate_source_sha256 == hashlib.sha256(blob).hexdigest()


def test_attestation_source_mismatch_fails_closed(tmp_path, monkeypatch):
    authorization, runner = _attestation_fixture(tmp_path, b"candidate\n")
    (tmp_path / v2.V2_MODULE_PATH).write_bytes(b"runtime\n")
    monkeypatch.setattr(v2.provenance, "verify_git_ancestry", lambda *args, **kwargs: None)
    with pytest.raises(v2.ReleaseBindingError, match="source bytes differ"):
        v2.attest_v2_runtime(authorization=authorization, repo_root=tmp_path, git_runner=runner)


def test_attestation_authorized_digest_mismatch_fails_closed(tmp_path, monkeypatch):
    blob = b"same\n"
    authorization, runner = _attestation_fixture(tmp_path, blob, authorized_digest="f" * 64)
    monkeypatch.setattr(v2.provenance, "verify_git_ancestry", lambda *args, **kwargs: None)
    with pytest.raises(v2.ReleaseBindingError, match="source digest"):
        v2.attest_v2_runtime(authorization=authorization, repo_root=tmp_path, git_runner=runner)
