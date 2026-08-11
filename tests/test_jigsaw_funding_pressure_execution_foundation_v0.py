"""Adversarial test matrix for the execution foundation hardening phase.

Real committed evidence is only ever used here for hash/schema/timestamp/
provenance checks (Section 11/28). No test in this file computes funding
pressure, an ECDF, a state label, a return, or RV24. Every value-level
adversarial scenario (tampering, cross-inconsistent timestamps, malformed
rows, ...) is built from synthetic fixtures.
"""
import dataclasses
import hashlib
import inspect
import os
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
import requests

from qntylab import jigsaw_funding_pressure_execution_foundation_v0 as foundation
from qntylab import jigsaw_funding_pressure_provenance_v0 as provenance

VALID_AUTH_ID = "jigsaw-funding-pressure-v0-" + "a" * 32

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "foundation-test",
    "GIT_AUTHOR_EMAIL": "foundation-test@example.invalid",
    "GIT_COMMITTER_NAME": "foundation-test",
    "GIT_COMMITTER_EMAIL": "foundation-test@example.invalid",
}


def _init_tiny_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "tiny-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=_GIT_ENV)
    (repo / "file.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, env=_GIT_ENV)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True, env=_GIT_ENV)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True, env=_GIT_ENV).strip()
    return repo, sha


# ==========================================================================
# Foundation contract artifact
# ==========================================================================


def test_execution_foundation_contract_digest_self_consistent():
    contract = foundation._load_foundation_contract()
    assert contract["execution_foundation_contract_digest"] == foundation.execution_foundation_contract_digest()
    mutated = dict(contract)
    mutated["exact_ordered_panel"] = list(reversed(mutated["exact_ordered_panel"]))
    mutated_digest = provenance.canonical_digest(provenance._without(mutated, "execution_foundation_contract_digest"))
    assert mutated_digest != contract["execution_foundation_contract_digest"]


def test_no_outcome_attestation_all_no():
    assert set(foundation.NO_OUTCOME_ATTESTATION.values()) == {False}
    assert foundation.NO_OUTCOME_ATTESTATION["REAL_REMOTE_AUTHORIZATION_CLAIM_CREATED"] is False


# ==========================================================================
# Evidence loader: funding row parsing (synthetic)
# ==========================================================================

VALID_FUNDING_ROW = {
    "symbol": "ALICEUSDT",
    "funding_time_ms": 1666108800000,
    "funding_time_utc": "2022-10-18T16:00:00.000Z",
    "funding_rate": "0.0001",
}


def test_parse_funding_row_accepts_valid_synthetic_row():
    event = foundation.parse_funding_row(VALID_FUNDING_ROW, symbol="ALICEUSDT")
    assert event.funding_rate == Decimal("0.0001")
    assert event.funding_time_ms == 1666108800000


def test_parse_funding_row_wrong_symbol_fails():
    with pytest.raises(foundation.EvidenceValidationError, match="symbol mismatch"):
        foundation.parse_funding_row(VALID_FUNDING_ROW, symbol="BCHUSDT")


@pytest.mark.parametrize("missing_field", ["symbol", "funding_time_ms", "funding_time_utc", "funding_rate"])
def test_parse_funding_row_missing_field_fails(missing_field):
    row = {k: v for k, v in VALID_FUNDING_ROW.items() if k != missing_field}
    with pytest.raises(foundation.EvidenceValidationError, match="missing required fields"):
        foundation.parse_funding_row(row, symbol="ALICEUSDT")


def test_parse_funding_row_timestamp_cross_inconsistency_fails():
    row = {**VALID_FUNDING_ROW, "funding_time_utc": "2022-10-18T16:00:01.000Z"}  # +1s vs. funding_time_ms
    with pytest.raises(foundation.EvidenceValidationError, match="identity mismatch"):
        foundation.parse_funding_row(row, symbol="ALICEUSDT")


def test_parse_funding_row_does_not_round_to_8h_grid():
    """A sub-second offset must survive verification exactly, never get snapped."""
    row = {**VALID_FUNDING_ROW, "funding_time_ms": 1666108800007, "funding_time_utc": "2022-10-18T16:00:00.007Z"}
    event = foundation.parse_funding_row(row, symbol="ALICEUSDT")
    assert event.funding_time_ms == 1666108800007
    assert event.funding_time_utc == "2022-10-18T16:00:00.007Z"


@pytest.mark.parametrize("bad_rate", ["Infinity", "-Infinity", "NaN"])
def test_parse_funding_row_nonfinite_rate_fails(bad_rate):
    row = {**VALID_FUNDING_ROW, "funding_rate": bad_rate}
    with pytest.raises(foundation.EvidenceValidationError, match="not finite"):
        foundation.parse_funding_row(row, symbol="ALICEUSDT")


def test_parse_funding_row_non_string_rate_fails():
    row = {**VALID_FUNDING_ROW, "funding_rate": 0.0001}
    with pytest.raises(foundation.EvidenceValidationError, match="decimal-syntax string"):
        foundation.parse_funding_row(row, symbol="ALICEUSDT")


def test_validate_funding_series_duplicate_timestamp_fails():
    event = foundation.parse_funding_row(VALID_FUNDING_ROW, symbol="ALICEUSDT")
    with pytest.raises(foundation.EvidenceValidationError, match="duplicate funding_time_ms"):
        foundation.validate_funding_series([event, event], symbol="ALICEUSDT")


# ==========================================================================
# Evidence loader: OHLCV row parsing (synthetic)
# ==========================================================================

VALID_OHLCV_ROW = {"timestamp": "2023-10-19T00:00:00Z", "open": "0.673", "high": "0.676", "low": "0.671", "close": "0.675", "volume": "379319.4"}


def test_parse_ohlcv_row_accepts_valid_synthetic_row():
    bar = foundation.parse_ohlcv_row(VALID_OHLCV_ROW, symbol="ALICEUSDT")
    assert bar.close == Decimal("0.675")
    assert bar.source_open_time == "2023-10-19T00:00:00Z"
    assert bar.symbol == "ALICEUSDT"


@pytest.mark.parametrize("missing_field", ["timestamp", "open", "high", "low", "close", "volume"])
def test_parse_ohlcv_row_missing_field_fails(missing_field):
    row = {k: v for k, v in VALID_OHLCV_ROW.items() if k != missing_field}
    with pytest.raises(foundation.EvidenceValidationError, match="missing required fields"):
        foundation.parse_ohlcv_row(row, symbol="ALICEUSDT")


def test_parse_ohlcv_row_non_hourly_timestamp_fails():
    row = {**VALID_OHLCV_ROW, "timestamp": "2023-10-19T00:30:00Z"}
    with pytest.raises(foundation.EvidenceValidationError, match="not on the hour"):
        foundation.parse_ohlcv_row(row, symbol="ALICEUSDT")


@pytest.mark.parametrize("bad_close", ["0", "-1.5", "Infinity", "NaN"])
def test_parse_ohlcv_row_nonpositive_or_nonfinite_close_fails(bad_close):
    row = {**VALID_OHLCV_ROW, "close": bad_close}
    with pytest.raises(foundation.EvidenceValidationError, match="close must be finite and positive"):
        foundation.parse_ohlcv_row(row, symbol="ALICEUSDT")


def test_parse_ohlcv_row_has_no_semantic_override_parameter():
    """Wrong bar semantic must be impossible, not merely refused at runtime."""
    sig = inspect.signature(foundation.parse_ohlcv_row)
    assert set(sig.parameters) == {"row", "symbol"}
    field_names = {f.name for f in dataclasses.fields(foundation.VerifiedBarOpenClose)}
    assert not any(name.endswith("_semantic") for name in field_names)


def test_validate_bar_series_duplicate_timestamp_fails():
    bar = foundation.parse_ohlcv_row(VALID_OHLCV_ROW, symbol="ALICEUSDT")
    with pytest.raises(foundation.EvidenceValidationError, match="duplicate source-open timestamp"):
        foundation.validate_bar_series([bar, bar], symbol="ALICEUSDT")


def test_validate_bar_series_non_monotonic_fails():
    bar1 = foundation.parse_ohlcv_row(VALID_OHLCV_ROW, symbol="ALICEUSDT")
    earlier_row = {**VALID_OHLCV_ROW, "timestamp": "2023-10-18T23:00:00Z"}
    bar0 = foundation.parse_ohlcv_row(earlier_row, symbol="ALICEUSDT")
    with pytest.raises(foundation.EvidenceValidationError, match="strictly increasing"):
        foundation.validate_bar_series([bar1, bar0], symbol="ALICEUSDT")


# ==========================================================================
# Evidence loader: path / symlink hardening (synthetic)
# ==========================================================================


def test_resolve_within_repository_accepts_normal_path(tmp_path):
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / "data" / "f.txt").write_text("ok", encoding="utf-8")
    resolved = foundation.resolve_within_repository("data/f.txt", repo)
    assert resolved == (repo / "data" / "f.txt").resolve()


def test_resolve_within_repository_symlink_escape_fails(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("not evidence", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "evil-link.txt").symlink_to(secret)
    with pytest.raises(foundation.PathEscapeError):
        foundation.resolve_within_repository("evil-link.txt", repo)


def test_resolve_within_repository_traversal_fails(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "outside.txt").write_text("x", encoding="utf-8")
    with pytest.raises(foundation.PathEscapeError):
        foundation.resolve_within_repository("../outside.txt", repo)


# ==========================================================================
# Evidence loader: baseline-derived path lookup + byte verification
# ==========================================================================


def test_funding_raw_evidence_entry_wrong_symbol_fails():
    baseline = provenance._load("provenance_baseline_v0.json")
    with pytest.raises(foundation.EvidenceValidationError):
        foundation._funding_raw_evidence_entry("NOTASYMBOL", baseline)


def test_ohlcv_raw_evidence_entry_wrong_symbol_fails():
    baseline = provenance._load("provenance_baseline_v0.json")
    with pytest.raises(foundation.EvidenceValidationError):
        foundation._ohlcv_raw_evidence_entry("NOTASYMBOL", baseline)


def test_load_funding_symbol_tampered_bytes_fail_closed(tmp_path):
    baseline = provenance._load("provenance_baseline_v0.json")
    symbol = "ALICEUSDT"
    entry = foundation._funding_raw_evidence_entry(symbol, baseline)
    dest = tmp_path / entry["relative_path"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes((provenance.ROOT / entry["relative_path"]).read_bytes() + b"TAMPERED")
    with pytest.raises(AssertionError, match="evidence byte mismatch"):
        foundation._load_funding_symbol(symbol, baseline, tmp_path)


def test_load_ohlcv_symbol_tampered_bytes_fail_closed(tmp_path):
    baseline = provenance._load("provenance_baseline_v0.json")
    symbol = "ALICEUSDT"
    entry = foundation._ohlcv_raw_evidence_entry(symbol, baseline)
    dest = tmp_path / entry["relative_path"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes((provenance.ROOT / entry["relative_path"]).read_bytes() + b"TAMPERED")
    with pytest.raises(AssertionError, match="evidence byte mismatch"):
        foundation._load_ohlcv_symbol(symbol, baseline, tmp_path)


def test_load_funding_symbol_untracked_replacement_fails(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, env=_GIT_ENV)
    baseline = provenance._load("provenance_baseline_v0.json")
    symbol = "ALICEUSDT"
    entry = foundation._funding_raw_evidence_entry(symbol, baseline)
    dest = tmp_path / entry["relative_path"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes((provenance.ROOT / entry["relative_path"]).read_bytes())  # byte-identical, never `git add`-ed
    with pytest.raises(AssertionError, match="not Git-tracked"):
        foundation._load_funding_symbol(symbol, baseline, tmp_path)


def test_load_verified_frozen_evidence_takes_no_parameters():
    """An alternate caller-supplied evidence path for REAL_HISTORICAL mode is impossible."""
    assert dict(inspect.signature(foundation.load_verified_frozen_evidence).parameters) == {}


def test_load_verified_frozen_evidence_end_to_end_structural():
    """Structural-only pass over real committed evidence: hashes, schema, symbols,
    provenance. No funding_rate or close value is asserted on (Section 11/28)."""
    bundle = foundation.load_verified_frozen_evidence()
    assert bundle.exact_panel == tuple(provenance.PANEL)
    assert set(bundle.funding_by_symbol) == set(provenance.PANEL)
    assert set(bundle.bars_by_symbol) == set(provenance.PANEL)
    assert bundle.provenance_baseline_digest == foundation._provenance_baseline_digest()
    assert bundle.funding_evidence_set_digest == provenance.FUNDING_DIGEST
    assert bundle.ohlcv_evidence_set_digest == provenance.OHLCV_DIGEST
    for symbol in provenance.PANEL:
        assert len(bundle.funding_by_symbol[symbol]) > 0
        assert len(bundle.bars_by_symbol[symbol]) > 0
    with pytest.raises(TypeError):
        bundle.funding_by_symbol["ALICEUSDT"] = ()  # immutable mapping


# ==========================================================================
# Runtime attestation (synthetic single-commit repos only)
# ==========================================================================


def test_attest_runtime_passes_for_valid_synthetic_checkout(tmp_path):
    repo, sha = _init_tiny_repo(tmp_path)
    attestation = foundation.attest_runtime(
        repo_root=repo,
        expected_repository_root=repo,
        expected_runtime_head_sha=sha,
        module_path=repo / "file.txt",
        required_ancestors=(),
    )
    assert attestation.runtime_head_sha == sha
    assert attestation.worktree_clean is True
    assert attestation.repository_root == str(repo.resolve())
    assert attestation.runtime_executor_source_sha256 == hashlib.sha256((repo / "file.txt").read_bytes()).hexdigest()


def test_attest_runtime_wrong_repo_root_fails(tmp_path):
    repo, sha = _init_tiny_repo(tmp_path)
    other = tmp_path / "not-the-repo"
    other.mkdir()
    with pytest.raises(foundation.RuntimeAttestationError, match="repository root mismatch"):
        foundation.attest_runtime(repo_root=repo, expected_repository_root=other, expected_runtime_head_sha=sha, required_ancestors=())


def test_attest_runtime_wrong_head_fails(tmp_path):
    repo, sha = _init_tiny_repo(tmp_path)
    with pytest.raises(foundation.RuntimeAttestationError, match="runtime HEAD mismatch"):
        foundation.attest_runtime(repo_root=repo, expected_repository_root=repo, expected_runtime_head_sha="f" * 40, required_ancestors=())


def test_attest_runtime_dirty_worktree_fails(tmp_path):
    repo, sha = _init_tiny_repo(tmp_path)
    (repo / "untracked.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(foundation.RuntimeAttestationError, match="worktree is not clean"):
        foundation.attest_runtime(repo_root=repo, expected_repository_root=repo, expected_runtime_head_sha=sha, required_ancestors=())


def test_attest_runtime_wrong_module_path_fails(tmp_path):
    repo, sha = _init_tiny_repo(tmp_path)
    with pytest.raises(foundation.RuntimeAttestationError, match="resolves outside repository root"):
        foundation.attest_runtime(
            repo_root=repo,
            expected_repository_root=repo,
            expected_runtime_head_sha=sha,
            module_path=Path(__file__),
            required_ancestors=(),
        )


def test_attest_runtime_required_ancestor_missing_fails(tmp_path):
    repo, sha = _init_tiny_repo(tmp_path)
    with pytest.raises(foundation.RuntimeAttestationError, match="is not an ancestor"):
        foundation.attest_runtime(
            repo_root=repo,
            expected_repository_root=repo,
            expected_runtime_head_sha=sha,
            module_path=repo / "file.txt",
            required_ancestors=(provenance.PREREG_SHA,),
        )


def test_attest_runtime_git_command_unavailable_fails(tmp_path):
    repo, sha = _init_tiny_repo(tmp_path)

    def _broken_runner(*args, **kwargs):
        raise OSError("git executable not found")

    with pytest.raises(foundation.RuntimeAttestationError, match="git command unavailable"):
        foundation.attest_runtime(repo_root=repo, expected_repository_root=repo, expected_runtime_head_sha=sha, git_runner=_broken_runner)


def test_attest_runtime_no_git_metadata_fails(tmp_path):
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    with pytest.raises(foundation.RuntimeAttestationError):
        foundation.attest_runtime(repo_root=empty, expected_repository_root=empty, expected_runtime_head_sha="f" * 40, required_ancestors=())


# ==========================================================================
# Runtime <-> authorization cross-checks (Section 13/21)
# ==========================================================================


def _synthetic_attestation() -> foundation.RuntimeAttestation:
    return foundation.RuntimeAttestation(
        repository_root="/synthetic/repo",
        runtime_head_sha="b" * 40,
        runtime_module_path="/synthetic/repo/module.py",
        runtime_executor_source_sha256="c" * 64,
        worktree_clean=True,
        verified_ancestors=(provenance.PREREG_SHA, provenance.PIT_V1_SHA),
    )


def _synthetic_authorization(attestation: foundation.RuntimeAttestation) -> foundation.AuthorizationEnvelope:
    expected = foundation.canonical_authorization_binding_expectations(executor_source_sha256=attestation.runtime_executor_source_sha256)
    return foundation.AuthorizationEnvelope(
        authorization_id=VALID_AUTH_ID,
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
        reviewed_executor_candidate_sha=expected.reviewed_executor_candidate_sha,
        canonical_runtime_merge_sha=attestation.runtime_head_sha,
        executor_source_sha256=attestation.runtime_executor_source_sha256,
        execution_scope=expected.execution_scope,
        outcome_access_scope=expected.outcome_access_scope,
        authorization_status=foundation.AUTHORIZATION_STATUS_AUTHORIZED_UNUSED,
    )


def test_validate_authorization_against_runtime_passes_when_consistent():
    attestation = _synthetic_attestation()
    authorization = _synthetic_authorization(attestation)
    foundation.validate_authorization_against_runtime(authorization, attestation)  # must not raise


def test_validate_authorization_against_runtime_head_mismatch_fails():
    attestation = _synthetic_attestation()
    authorization = dataclasses.replace(_synthetic_authorization(attestation), canonical_runtime_merge_sha="f" * 40)
    with pytest.raises(foundation.ReceiptProvenanceError, match="runtime_head_sha"):
        foundation.validate_authorization_against_runtime(authorization, attestation)


def test_validate_authorization_against_runtime_source_digest_mismatch_fails():
    attestation = _synthetic_attestation()
    authorization = dataclasses.replace(_synthetic_authorization(attestation), executor_source_sha256="9" * 64)
    with pytest.raises(foundation.ReceiptProvenanceError, match="runtime_executor_source_sha256"):
        foundation.validate_authorization_against_runtime(authorization, attestation)


# ==========================================================================
# Authorization envelope validation (Section 18/19)
# ==========================================================================

MUTATION_FIELDS = [
    "experiment_id",
    "preregistration_merge_sha",
    "contract_digest",
    "pit_v1_merge_sha",
    "pit_v1_certificate_digest",
    "provenance_baseline_digest",
    "funding_history_coverage_digest",
    "execution_foundation_contract_digest",
    "funding_evidence_set_digest",
    "ohlcv_evidence_set_digest",
    "reviewed_executor_candidate_sha",
    "canonical_runtime_merge_sha",
    "executor_source_sha256",
    "execution_scope",
    "outcome_access_scope",
]


def _valid_expected() -> foundation.AuthorizationBindingExpectations:
    return foundation.canonical_authorization_binding_expectations(executor_source_sha256="f" * 64)


def _valid_envelope(expected: foundation.AuthorizationBindingExpectations) -> foundation.AuthorizationEnvelope:
    return foundation.AuthorizationEnvelope(
        authorization_id=VALID_AUTH_ID,
        authorization_status=foundation.AUTHORIZATION_STATUS_AUTHORIZED_UNUSED,
        **dataclasses.asdict(expected),
    )


def test_validate_authorization_envelope_accepts_valid_synthetic_envelope():
    expected = _valid_expected()
    foundation.validate_authorization_envelope(_valid_envelope(expected), expected)  # must not raise


@pytest.mark.parametrize("field", MUTATION_FIELDS)
def test_validate_authorization_envelope_rejects_each_identity_mutation(field):
    expected = _valid_expected()
    envelope = _valid_envelope(expected)
    mutated = dataclasses.replace(envelope, **{field: "WRONG-" + getattr(envelope, field)})
    with pytest.raises(foundation.AuthorizationValidationError, match=field):
        foundation.validate_authorization_envelope(mutated, expected)


def test_validate_authorization_envelope_rejects_wrong_execution_scope():
    expected = _valid_expected()
    envelope = dataclasses.replace(_valid_envelope(expected), execution_scope="SOME_OTHER_SCOPE")
    with pytest.raises(foundation.AuthorizationValidationError):
        foundation.validate_authorization_envelope(envelope, expected)


def test_validate_authorization_envelope_rejects_wrong_outcome_scope():
    expected = _valid_expected()
    envelope = dataclasses.replace(_valid_envelope(expected), outcome_access_scope="SOME_OTHER_SCOPE")
    with pytest.raises(foundation.AuthorizationValidationError):
        foundation.validate_authorization_envelope(envelope, expected)


@pytest.mark.parametrize("bad_status", ["AUTHORIZED_CONSUMED", "CLAIMED", "CONSUMED_INCOMPLETE", "", "authorized_unused"])
def test_validate_authorization_envelope_rejects_non_unused_status(bad_status):
    expected = _valid_expected()
    envelope = dataclasses.replace(_valid_envelope(expected), authorization_status=bad_status)
    with pytest.raises(foundation.AuthorizationValidationError, match="authorization_status"):
        foundation.validate_authorization_envelope(envelope, expected)


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        "not-even-close",
        "jigsaw-funding-pressure-v0-" + "g" * 32,  # non-hex char
        "JIGSAW-FUNDING-PRESSURE-V0-" + "a" * 32,  # wrong case
        "jigsaw-funding-pressure-v0-" + "a" * 31,  # too short
        "jigsaw-funding-pressure-v0-" + "a" * 33,  # too long
    ],
)
def test_validate_authorization_envelope_rejects_malformed_id(bad_id):
    expected = _valid_expected()
    envelope = dataclasses.replace(_valid_envelope(expected), authorization_id=bad_id)
    with pytest.raises(foundation.AuthorizationValidationError, match="authorization_id"):
        foundation.validate_authorization_envelope(envelope, expected)


# ==========================================================================
# Remote at-most-once claim (Section 14-16) -- synthetic transports only
# ==========================================================================


class FakeGitHubRefTransport:
    """Models GitHub's atomic create-if-absent ref semantics in memory."""

    def __init__(self):
        self._refs: dict[str, str] = {}

    def create_ref(self, ref: str, sha: str) -> foundation.ClaimRefResult:
        if ref in self._refs:
            return foundation.ClaimRefResult(status="ALREADY_EXISTS", detail=f"{ref} already points to {self._refs[ref]}")
        self._refs[ref] = sha
        return foundation.ClaimRefResult(status="CREATED")


class _RaisingTransport:
    def __init__(self, exc: Exception):
        self._exc = exc

    def create_ref(self, ref: str, sha: str):
        raise self._exc


class _MalformedResponseTransport:
    def create_ref(self, ref: str, sha: str):
        return "not-a-ClaimRefResult"


class _UnknownStatusTransport:
    def create_ref(self, ref: str, sha: str) -> foundation.ClaimRefResult:
        return foundation.ClaimRefResult(status="WEIRD")


def test_claim_ref_name_format():
    assert foundation.claim_ref_name(VALID_AUTH_ID) == f"refs/qntylab-execution-claims/{VALID_AUTH_ID}"


def test_claim_ref_name_rejects_malformed_authorization_id():
    with pytest.raises(foundation.AtMostOnceClaimError):
        foundation.claim_ref_name("not-a-valid-id")


def test_claim_first_creation_succeeds():
    outcome = foundation.claim_authorization_once(VALID_AUTH_ID, "a" * 40, FakeGitHubRefTransport())
    assert outcome == foundation.ClaimOutcome.CLAIMED


def test_claim_second_attempt_same_authorization_is_already_consumed():
    transport = FakeGitHubRefTransport()
    sha = "a" * 40
    assert foundation.claim_authorization_once(VALID_AUTH_ID, sha, transport) == foundation.ClaimOutcome.CLAIMED
    assert foundation.claim_authorization_once(VALID_AUTH_ID, sha, transport) == foundation.ClaimOutcome.ALREADY_CONSUMED


def test_claim_second_attempt_same_sha_is_not_treated_as_success():
    """`ref already points to same SHA` must NOT be a successful second execution."""
    transport = FakeGitHubRefTransport()
    sha = "a" * 40
    foundation.claim_authorization_once(VALID_AUTH_ID, sha, transport)
    outcome = foundation.claim_authorization_once(VALID_AUTH_ID, sha, transport)
    assert outcome != foundation.ClaimOutcome.CLAIMED
    assert outcome == foundation.ClaimOutcome.ALREADY_CONSUMED


def test_claim_network_error_fails_closed():
    with pytest.raises(foundation.AtMostOnceClaimError):
        foundation.claim_authorization_once(VALID_AUTH_ID, "a" * 40, _RaisingTransport(ConnectionError("network unreachable")))


def test_claim_permission_denied_fails_closed():
    with pytest.raises(foundation.AtMostOnceClaimError):
        foundation.claim_authorization_once(VALID_AUTH_ID, "a" * 40, _RaisingTransport(PermissionError("403 Forbidden")))


def test_claim_malformed_response_fails_closed():
    with pytest.raises(foundation.AtMostOnceClaimError):
        foundation.claim_authorization_once(VALID_AUTH_ID, "a" * 40, _MalformedResponseTransport())


def test_claim_unrecognized_status_fails_closed():
    with pytest.raises(foundation.AtMostOnceClaimError):
        foundation.claim_authorization_once(VALID_AUTH_ID, "a" * 40, _UnknownStatusTransport())


def test_claim_ref_name_is_deterministic():
    assert foundation.claim_ref_name(VALID_AUTH_ID) == foundation.claim_ref_name(VALID_AUTH_ID)


@pytest.mark.parametrize(
    "hostile_id",
    [
        "jigsaw-funding-pressure-v0-" + "a" * 16 + "/" + "a" * 15,  # embedded slash
        "jigsaw-funding-pressure-v0-" + ".." + "a" * 30,  # traversal
        "jigsaw-funding-pressure-v0-" + "%2e%2e" + "a" * 26,  # URL-encoded traversal
        "jigsaw-funding-pressure-v0-" + "a" * 31 + "?",  # query-char
        "jigsaw-funding-pressure-v0-" + "a" * 31 + "#",  # fragment-char
        "jigsaw-funding-pressure-v0-" + " " * 32,  # whitespace
        "JIGSAW-FUNDING-PRESSURE-V0-" + "A" * 32,  # case folding
    ],
)
def test_claim_ref_name_rejects_ref_hostile_authorization_ids(hostile_id):
    """Section 26: the frozen authorization-ID grammar must not be widened for ref convenience."""
    with pytest.raises(foundation.AtMostOnceClaimError):
        foundation.claim_ref_name(hostile_id)


# ==========================================================================
# F-01 REPAIR -- GitHubRestRemoteClaimTransport (Section 23-27) -- HTTP boundary
# is ALWAYS a fake/scripted session below. No test in this module may ever
# reach a real socket; see `_no_real_network` autouse fixture (Section 24).
# ==========================================================================


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Hard network guard (Section 24): patch requests.Session.request (the
    shared low-level entrypoint under .get()/.post()) to raise immediately
    if anything in this test module ever drives a REAL requests.Session.
    Every GitHubRestRemoteClaimTransport test below instead injects a fake
    `session` object, so this should never fire -- it exists as a backstop
    against an accidental live GitHub mutation.
    """

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("a test attempted a real network request via requests.Session -- forbidden in this suite")

    monkeypatch.setattr(requests.Session, "request", _forbidden, raising=True)


class _FakeResponse:
    """Stands in for requests.Response: only `.status_code` and `.json()` are used."""

    def __init__(self, status_code: int, json_body=None, *, json_raises: bool = False):
        self.status_code = status_code
        self._json_body = json_body
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json_body


class _ScriptedSession:
    """Fake requests.Session: returns pre-scripted responses/exceptions, records every call."""

    def __init__(self, *, post_response=None, post_exception=None, get_response=None, get_exception=None):
        self._post_response = post_response
        self._post_exception = post_exception
        self._get_response = get_response
        self._get_exception = get_exception
        self.post_calls: list[dict] = []
        self.get_calls: list[dict] = []

    def post(self, url, *, json, headers, timeout, allow_redirects):
        self.post_calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout, "allow_redirects": allow_redirects})
        if self._post_exception is not None:
            raise self._post_exception
        return self._post_response

    def get(self, url, *, headers, timeout, allow_redirects):
        self.get_calls.append({"url": url, "headers": headers, "timeout": timeout, "allow_redirects": allow_redirects})
        if self._get_exception is not None:
            raise self._get_exception
        return self._get_response


_CLAIM_REF = foundation.claim_ref_name(VALID_AUTH_ID)
_CLAIM_SHA = "b" * 40


def _transport(session, **overrides) -> foundation.GitHubRestRemoteClaimTransport:
    kwargs = {"owner": "acme-org", "repo": "acme-repo", "token": "unit-test-token", "session": session}
    kwargs.update(overrides)
    return foundation.GitHubRestRemoteClaimTransport(**kwargs)


def _created_body(ref=_CLAIM_REF, sha=_CLAIM_SHA):
    return {"ref": ref, "object": {"sha": sha, "type": "commit"}}


# --- 201 success and malformed-success matrix (Section 23) -----------------


def test_transport_201_exact_response_is_created():
    session = _ScriptedSession(post_response=_FakeResponse(201, _created_body()))
    result = _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)
    assert result == foundation.ClaimRefResult(status="CREATED")
    assert session.post_calls[0]["json"] == {"ref": _CLAIM_REF, "sha": _CLAIM_SHA}
    assert session.post_calls[0]["allow_redirects"] is False


def test_transport_201_wrong_ref_fails_closed():
    session = _ScriptedSession(post_response=_FakeResponse(201, _created_body(ref="refs/qntylab-execution-claims/someone-else")))
    with pytest.raises(foundation.RemoteClaimResponseError, match="response.ref"):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


def test_transport_201_wrong_sha_fails_closed():
    session = _ScriptedSession(post_response=_FakeResponse(201, _created_body(sha="c" * 40)))
    with pytest.raises(foundation.RemoteClaimResponseError, match="response.object.sha"):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


def test_transport_201_missing_object_fails_closed():
    session = _ScriptedSession(post_response=_FakeResponse(201, {"ref": _CLAIM_REF}))
    with pytest.raises(foundation.RemoteClaimResponseError, match="object"):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


def test_transport_201_non_commit_object_type_fails_closed():
    session = _ScriptedSession(post_response=_FakeResponse(201, {"ref": _CLAIM_REF, "object": {"sha": _CLAIM_SHA, "type": "tag"}}))
    with pytest.raises(foundation.RemoteClaimResponseError, match="object"):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


def test_transport_201_malformed_json_body_fails_closed():
    session = _ScriptedSession(post_response=_FakeResponse(201, json_raises=True))
    with pytest.raises(foundation.RemoteClaimResponseError, match="malformed"):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


def test_transport_201_non_object_json_body_fails_closed():
    session = _ScriptedSession(post_response=_FakeResponse(201, ["not", "an", "object"]))
    with pytest.raises(foundation.RemoteClaimResponseError, match="non-object"):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


# --- 409/422 exact-ref disambiguation (Section 11/15/23) --------------------


@pytest.mark.parametrize("status", [409, 422])
def test_transport_conflict_confirmed_existing_same_sha_is_already_exists(status):
    session = _ScriptedSession(
        post_response=_FakeResponse(status, {"message": "already exists"}),
        get_response=_FakeResponse(200, {"ref": _CLAIM_REF, "object": {"sha": _CLAIM_SHA, "type": "commit"}}),
    )
    result = _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)
    assert result.status == "ALREADY_EXISTS"


@pytest.mark.parametrize("status", [409, 422])
def test_transport_conflict_confirmed_existing_different_sha_is_still_already_exists(status):
    """Section 10/17: an existing ref pointing elsewhere is STILL a consumed authorization, not a fresh success."""
    session = _ScriptedSession(
        post_response=_FakeResponse(status, {"message": "already exists"}),
        get_response=_FakeResponse(200, {"ref": _CLAIM_REF, "object": {"sha": "d" * 40, "type": "commit"}}),
    )
    result = _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)
    assert result.status == "ALREADY_EXISTS"


@pytest.mark.parametrize("status", [409, 422])
def test_transport_conflict_get_404_fails_closed_no_retry(status):
    session = _ScriptedSession(post_response=_FakeResponse(status, {"message": "conflict"}), get_response=_FakeResponse(404, {"message": "Not Found"}))
    with pytest.raises(foundation.RemoteClaimResponseError, match="does not exist"):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)
    assert len(session.post_calls) == 1  # no automatic create retry


def test_transport_conflict_get_itself_ambiguous_fails_closed():
    session = _ScriptedSession(post_response=_FakeResponse(409, {}), get_exception=requests.exceptions.ConnectionError("reset"))
    with pytest.raises(foundation.RemoteClaimAmbiguousError):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


def test_transport_conflict_get_unexpected_status_fails_closed():
    session = _ScriptedSession(post_response=_FakeResponse(409, {}), get_response=_FakeResponse(500, {"message": "boom"}))
    with pytest.raises(foundation.RemoteClaimResponseError):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


def test_transport_conflict_get_wrong_ref_body_fails_closed():
    session = _ScriptedSession(
        post_response=_FakeResponse(409, {}),
        get_response=_FakeResponse(200, {"ref": "refs/qntylab-execution-claims/not-the-same", "object": {"sha": _CLAIM_SHA, "type": "commit"}}),
    )
    with pytest.raises(foundation.RemoteClaimResponseError):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


def test_transport_disambiguation_get_uses_exact_singular_endpoint_not_prefix_list():
    """Section 15: must use `git/ref/<x>` (exact), never `git/refs/<x>` (prefix list)."""
    session = _ScriptedSession(post_response=_FakeResponse(409, {}), get_response=_FakeResponse(404, {}))
    with pytest.raises(foundation.RemoteClaimResponseError):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)
    get_url = session.get_calls[0]["url"]
    assert "/git/ref/" in get_url
    assert "/git/refs/" not in get_url
    assert get_url.endswith(f"qntylab-execution-claims/{VALID_AUTH_ID}")


# --- Auth / permissions / rate limit / server errors (Section 14/23) -------


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 502, 503, 504])
def test_transport_definite_failure_statuses_fail_closed_no_retry(status):
    session = _ScriptedSession(post_response=_FakeResponse(status, {"message": "no"}))
    with pytest.raises(foundation.RemoteClaimResponseError):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)
    assert len(session.post_calls) == 1  # zero automatic POST retries


@pytest.mark.parametrize("status", [200, 202, 204])
def test_transport_unexpected_2xx_fails_closed(status):
    session = _ScriptedSession(post_response=_FakeResponse(status, {}))
    with pytest.raises(foundation.RemoteClaimResponseError):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


@pytest.mark.parametrize("status", [301, 302, 307])
def test_transport_unexpected_3xx_fails_closed(status):
    session = _ScriptedSession(post_response=_FakeResponse(status, {}))
    with pytest.raises(foundation.RemoteClaimResponseError):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)


# --- Network ambiguity (Section 12/13/23) -- the most important case -------


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ConnectTimeout("connect timed out"),
        requests.exceptions.ReadTimeout("read timed out"),
        requests.exceptions.ConnectionError("connection reset by peer"),
        requests.exceptions.SSLError("certificate verify failed"),
    ],
)
def test_transport_post_network_ambiguity_fails_closed_no_retry(exc):
    session = _ScriptedSession(post_exception=exc)
    with pytest.raises(foundation.RemoteClaimAmbiguousError):
        _transport(session).create_ref(_CLAIM_REF, _CLAIM_SHA)
    assert len(session.post_calls) == 1  # zero automatic POST retries


def test_transport_ambiguous_failure_never_reaches_claimed_via_claim_authorization_once():
    """End-to-end through the frozen orchestrator: ambiguity must never become CLAIMED."""
    session = _ScriptedSession(post_exception=requests.exceptions.ReadTimeout("read timed out"))
    transport = _transport(session)
    with pytest.raises(foundation.AtMostOnceClaimError):
        foundation.claim_authorization_once(VALID_AUTH_ID, _CLAIM_SHA, transport)


# --- Same-authorization replay through the frozen state machine (Section 17/23) ---


def test_transport_same_sha_replay_via_claim_authorization_once_is_already_consumed_not_claimed():
    backend_refs: dict[str, str] = {}

    def _post(url, *, json, headers, timeout, allow_redirects):
        ref, sha = json["ref"], json["sha"]
        if ref in backend_refs:
            return _FakeResponse(422, {"message": "Reference already exists"})
        backend_refs[ref] = sha
        return _FakeResponse(201, _created_body(ref=ref, sha=sha))

    def _get(url, *, headers, timeout, allow_redirects):
        segment = url.rsplit("/git/ref/", 1)[1]
        ref = f"refs/{segment}"
        if ref in backend_refs:
            return _FakeResponse(200, {"ref": ref, "object": {"sha": backend_refs[ref], "type": "commit"}})
        return _FakeResponse(404, {"message": "Not Found"})

    class _StatefulSession:
        post = staticmethod(_post)
        get = staticmethod(_get)

    transport = _transport(_StatefulSession())
    first = foundation.claim_authorization_once(VALID_AUTH_ID, _CLAIM_SHA, transport)
    second = foundation.claim_authorization_once(VALID_AUTH_ID, _CLAIM_SHA, transport)  # identical sha
    assert first == foundation.ClaimOutcome.CLAIMED
    assert second == foundation.ClaimOutcome.ALREADY_CONSUMED


# --- Globality: two independent callers contend on one shared backend (Section 17) ---


class _InMemoryGitHubRefBackend:
    """Shared by two independently-constructed transports to model two race participants."""

    def __init__(self):
        self._refs: dict[str, str] = {}

    def post(self, ref: str, sha: str) -> _FakeResponse:
        if ref in self._refs:
            return _FakeResponse(422, {"message": "Reference already exists"})
        self._refs[ref] = sha
        return _FakeResponse(201, {"ref": ref, "object": {"sha": sha, "type": "commit"}})

    def get(self, ref: str) -> _FakeResponse:
        if ref not in self._refs:
            return _FakeResponse(404, {"message": "Not Found"})
        return _FakeResponse(200, {"ref": ref, "object": {"sha": self._refs[ref], "type": "commit"}})


class _BackendBoundSession:
    def __init__(self, backend: _InMemoryGitHubRefBackend):
        self._backend = backend

    def post(self, url, *, json, headers, timeout, allow_redirects):
        return self._backend.post(json["ref"], json["sha"])

    def get(self, url, *, headers, timeout, allow_redirects):
        segment = url.rsplit("/git/ref/", 1)[1]
        return self._backend.get(f"refs/{segment}")


def test_transport_two_worktrees_share_one_remote_claim_authority():
    backend = _InMemoryGitHubRefBackend()
    transport_a = _transport(_BackendBoundSession(backend))
    transport_b = _transport(_BackendBoundSession(backend))
    outcome_a = foundation.claim_authorization_once(VALID_AUTH_ID, _CLAIM_SHA, transport_a)
    outcome_b = foundation.claim_authorization_once(VALID_AUTH_ID, _CLAIM_SHA, transport_b)  # same sha, different caller
    assert outcome_a == foundation.ClaimOutcome.CLAIMED
    assert outcome_b == foundation.ClaimOutcome.ALREADY_CONSUMED


# --- Secret handling (Section 7/25) -----------------------------------------


@pytest.mark.parametrize("bad_env", [{}, {foundation.GITHUB_CLAIM_TOKEN_ENV_VAR: ""}, {foundation.GITHUB_CLAIM_TOKEN_ENV_VAR: "   "}])
def test_transport_from_environment_missing_or_blank_token_fails_closed(bad_env):
    with pytest.raises(foundation.RemoteClaimConfigurationError):
        foundation.GitHubRestRemoteClaimTransport.from_environment(env=bad_env)


@pytest.mark.parametrize("bad_token", ["", "   "])
def test_transport_init_rejects_blank_token(bad_token):
    with pytest.raises(foundation.RemoteClaimConfigurationError):
        foundation.GitHubRestRemoteClaimTransport(owner="acme", repo="repo", token=bad_token, session=_ScriptedSession())


def test_transport_exception_text_never_contains_the_token():
    secret_token = "ghp_SUPERSECRETVALUE0123456789ABCDEF"  # noqa: S105 - synthetic, never a real credential
    session = _ScriptedSession(post_exception=requests.exceptions.ConnectionError("connection reset by peer"))
    transport = _transport(session, token=secret_token)
    with pytest.raises(foundation.RemoteClaimAmbiguousError) as excinfo:
        transport.create_ref(_CLAIM_REF, _CLAIM_SHA)
    assert secret_token not in str(excinfo.value)
    assert secret_token not in repr(excinfo.value)
    # ... but the request actually was authenticated:
    assert session.post_calls[0]["headers"]["Authorization"] == f"Bearer {secret_token}"


def test_transport_exposes_no_delete_or_update_claim_api():
    """Section 16: execution claims are append-only; no admin-style method may exist."""
    forbidden_names = {"delete_ref", "delete_claim", "update_ref", "update_claim", "reset_claim", "reset_ref", "move_ref", "clear_claim", "force_update_ref"}
    exposed = {name for name in dir(foundation.GitHubRestRemoteClaimTransport) if not name.startswith("__")}
    assert not (forbidden_names & exposed)


# ==========================================================================
# Crash semantics / authorization lifecycle (Section 17)
# ==========================================================================

_STATE = foundation.AuthorizationLifecycleState


def test_lifecycle_authorized_unused_to_claimed_allowed():
    assert foundation.transition_authorization_lifecycle(_STATE.AUTHORIZED_UNUSED, _STATE.CLAIMED) == _STATE.CLAIMED


def test_lifecycle_claimed_to_consumed_incomplete_allowed():
    assert foundation.transition_authorization_lifecycle(_STATE.CLAIMED, _STATE.CONSUMED_INCOMPLETE) == _STATE.CONSUMED_INCOMPLETE


def test_lifecycle_claimed_to_consumed_complete_allowed():
    assert foundation.transition_authorization_lifecycle(_STATE.CLAIMED, _STATE.CONSUMED_COMPLETE) == _STATE.CONSUMED_COMPLETE


def test_lifecycle_authorized_unused_cannot_skip_to_consumed():
    with pytest.raises(foundation.LifecycleTransitionError):
        foundation.transition_authorization_lifecycle(_STATE.AUTHORIZED_UNUSED, _STATE.CONSUMED_INCOMPLETE)


@pytest.mark.parametrize("target", list(_STATE))
def test_lifecycle_consumed_incomplete_is_terminal_no_automatic_retry(target):
    """0, 1, 300, or all decisions processed -- CONSUMED_INCOMPLETE never transitions out automatically."""
    with pytest.raises(foundation.LifecycleTransitionError):
        foundation.transition_authorization_lifecycle(_STATE.CONSUMED_INCOMPLETE, target)


@pytest.mark.parametrize("target", list(_STATE))
def test_lifecycle_consumed_complete_is_terminal(target):
    with pytest.raises(foundation.LifecycleTransitionError):
        foundation.transition_authorization_lifecycle(_STATE.CONSUMED_COMPLETE, target)


def test_lifecycle_transition_table_has_no_path_back_to_unused():
    """Exhaustive proof: no state transitions back to AUTHORIZED_UNUSED."""
    for state, allowed in foundation._ALLOWED_LIFECYCLE_TRANSITIONS.items():
        assert _STATE.AUTHORIZED_UNUSED not in allowed


# ==========================================================================
# Receipt provenance (Section 20-22)
# ==========================================================================


def test_build_receipt_provenance_copies_attestation_identities_mechanically():
    attestation = _synthetic_attestation()
    authorization = _synthetic_authorization(attestation)
    receipt = foundation.build_receipt_provenance(authorization=authorization, attestation=attestation)
    assert receipt.runtime_head_sha == attestation.runtime_head_sha
    assert receipt.runtime_executor_source_sha256 == attestation.runtime_executor_source_sha256
    assert receipt.repository_root_identity == attestation.repository_root
    assert receipt.runtime_module_path == attestation.runtime_module_path
    assert receipt.authorization_claim_identity == foundation.claim_ref_name(authorization.authorization_id)
    assert receipt.downstream_strategy_authority == "NONE"
    assert receipt.downstream_router_authority == "NONE"
    assert receipt.downstream_qnty_authority == "NONE"


def test_build_receipt_provenance_signature_has_no_override_params():
    """Caller cannot pass an independent runtime SHA, source digest, or claim identity."""
    params = set(inspect.signature(foundation.build_receipt_provenance).parameters)
    assert params == {"authorization", "attestation"}


def test_build_receipt_provenance_rejects_runtime_head_mismatch():
    attestation = _synthetic_attestation()
    authorization = dataclasses.replace(_synthetic_authorization(attestation), canonical_runtime_merge_sha="f" * 40)
    with pytest.raises(foundation.ReceiptProvenanceError):
        foundation.build_receipt_provenance(authorization=authorization, attestation=attestation)


def test_build_receipt_provenance_rejects_source_digest_mismatch():
    attestation = _synthetic_attestation()
    authorization = dataclasses.replace(_synthetic_authorization(attestation), executor_source_sha256="9" * 64)
    with pytest.raises(foundation.ReceiptProvenanceError):
        foundation.build_receipt_provenance(authorization=authorization, attestation=attestation)


def test_receipt_digest_reproducible():
    attestation = _synthetic_attestation()
    authorization = _synthetic_authorization(attestation)
    receipt = foundation.build_receipt_provenance(authorization=authorization, attestation=attestation)
    assert foundation.receipt_digest(receipt) == foundation.receipt_digest(receipt)


def test_receipt_digest_changes_on_mutation():
    attestation = _synthetic_attestation()
    authorization = _synthetic_authorization(attestation)
    receipt = foundation.build_receipt_provenance(authorization=authorization, attestation=attestation)
    original = foundation.receipt_digest(receipt)
    mutated = dataclasses.replace(receipt, downstream_strategy_authority="SOMETHING_ELSE")
    assert foundation.receipt_digest(mutated) != original


def test_canonical_json_rejects_non_finite_values():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            foundation.canonical_json({"x": bad})
