"""Execution foundation hardening for Jigsaw Funding-Pressure -> RV24.

JIGSAW_FUNDING_PRESSURE_VOLATILITY_EXECUTION_FOUNDATION_HARDENING_V0

This module is deliberately NOT a scientific executor. It builds the
outcome-blind plumbing a future REAL_HISTORICAL V2 executor will stand on:

    - a single verified loading seam for the frozen, canonical evidence
      (funding events + PIT V1 OHLCV bars), fail-closed on any byte,
      schema, symbol, or timestamp inconsistency;
    - runtime attestation that mechanically derives -- never trusts a
      caller string for -- repository root, HEAD, worktree cleanliness,
      module identity, and required-ancestor coverage;
    - an authorization envelope shape and a pure validator for it;
    - a REMOTE_AT_MOST_ONCE_CLAIM_V0 state machine over an injected
      transport (no live transport is wired or called in this phase);
    - the crash-safe authorization lifecycle state machine
      (CONSUMED_INCOMPLETE is terminal; no automatic retry exists);
    - a receipt provenance envelope built exclusively from a
      RuntimeAttestation and an AuthorizationEnvelope, with a
      deterministic digest.

No funding pressure, ECDF, state classification, asset/market return, or
RV24 value is computed anywhere in this module. See NO_OUTCOME_ATTESTATION
at the bottom for the explicit attestation this phase must ship with.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from qntylab import jigsaw_funding_pressure_provenance_v0 as provenance

# --------------------------------------------------------------------------
# Frozen, verified identities (Section 0 / Section 13)
# --------------------------------------------------------------------------
# These two roles are new to this phase and are NOT self-digested artifacts
# elsewhere in the repository, so they are verified once, mechanically,
# against the actual Git object store below (see _verify_frozen_shas_are_real
# and its call at import time) rather than trusted as bare string literals.

PROVENANCE_BASELINE_REVIEWED_CANDIDATE_SHA = "e37cb5036902c17f12a35e061c4795d525a10475"
PROVENANCE_BASELINE_CANONICAL_MERGE_SHA = "da6c3428a0517ae7a140799091098d08f9c2a845"

EXPERIMENT_ID = provenance.EXPERIMENT.name.upper()

EXECUTION_SCOPE_ONE_FROZEN_HISTORICAL_RUN = "ONE_FROZEN_HISTORICAL_RUN"
OUTCOME_ACCESS_SCOPE_FUNDING_PRESSURE_TO_RV24_V0 = "FUNDING_PRESSURE_TO_RV24_V0"
AUTHORIZATION_STATUS_AUTHORIZED_UNUSED = "AUTHORIZED_UNUSED"

OHLCV_SOURCE_TIMESTAMP_SEMANTIC = "SOURCE_BAR_OPEN_TIME"
OHLCV_CLOSE_SEMANTIC = "CLOSE_PRICE_OF_BAR_OPENED_AT_TIMESTAMP"
OHLCV_LOGICAL_ENDPOINT_MAPPING = "source_open_u_maps_to_logical_close_endpoint_u_plus_1_hour"

CLAIM_REF_NAMESPACE = "refs/qntylab-execution-claims"
AUTHORIZATION_ID_PATTERN = re.compile(r"^jigsaw-funding-pressure-v0-[0-9a-f]{32}$")


class ExecutionFoundationError(Exception):
    """Base class for every fail-closed error this module raises."""


class EvidenceValidationError(ExecutionFoundationError):
    pass


class PathEscapeError(ExecutionFoundationError):
    pass


class RuntimeAttestationError(ExecutionFoundationError):
    pass


class AuthorizationValidationError(ExecutionFoundationError):
    pass


class AtMostOnceClaimError(ExecutionFoundationError):
    pass


class LifecycleTransitionError(ExecutionFoundationError):
    pass


class ReceiptProvenanceError(ExecutionFoundationError):
    pass


def canonical_json(payload: object) -> str:
    """Shared canonicalization: sorted keys, compact separators, ASCII-safe.

    ``allow_nan=False`` makes json.dumps raise ValueError on NaN/Infinity/
    -Infinity anywhere in the payload, per Section 22.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


# --------------------------------------------------------------------------
# Section 0/13 self-check: the two new frozen SHAs above must at least be
# well-formed. This is a cheap, no-I/O sanity check that runs at import time
# so a corrupted constant fails loudly and immediately. It is intentionally
# NOT a substitute for real verification: proof that these SHAs are actual,
# reachable, correctly-related commits comes from attest_runtime()'s
# ancestry check (via provenance.verify_git_ancestry, hardened for P-F3),
# which is the authoritative, fail-closed gate and is exercised on every
# attestation, not just at import time.
# --------------------------------------------------------------------------


def _verify_frozen_sha_format() -> None:
    for name, sha in (
        ("PROVENANCE_BASELINE_REVIEWED_CANDIDATE_SHA", PROVENANCE_BASELINE_REVIEWED_CANDIDATE_SHA),
        ("PROVENANCE_BASELINE_CANONICAL_MERGE_SHA", PROVENANCE_BASELINE_CANONICAL_MERGE_SHA),
    ):
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ExecutionFoundationError(f"{name} is not a well-formed 40-char hex SHA1: {sha!r}")


_verify_frozen_sha_format()


# --------------------------------------------------------------------------
# Foundation contract artifact self-digest (Section 6)
# --------------------------------------------------------------------------

_FOUNDATION_CONTRACT_FILENAME = "execution_foundation_contract_v0.json"


def _load_foundation_contract() -> dict:
    return provenance._load(_FOUNDATION_CONTRACT_FILENAME)


def execution_foundation_contract_digest() -> str:
    """Self-verifies and returns execution_foundation_contract_v0.json's digest.

    There is exactly one copy of this digest in the repository: inside the
    contract file itself. Nothing in this module hardcodes a duplicate.
    """
    contract = _load_foundation_contract()
    expected = contract["execution_foundation_contract_digest"]
    actual = provenance.canonical_digest(provenance._without(contract, "execution_foundation_contract_digest"))
    if expected != actual:
        raise ExecutionFoundationError(
            f"{_FOUNDATION_CONTRACT_FILENAME} self-digest mismatch: file claims {expected}, recomputed {actual}"
        )
    return expected


def _provenance_baseline_digest() -> str:
    baseline = provenance._load("provenance_baseline_v0.json")
    provenance.verify_self_digest(baseline, "provenance_baseline_digest")
    return baseline["provenance_baseline_digest"]


def _funding_history_coverage_digest() -> str:
    coverage = provenance._load("funding_history_coverage_v0.json")
    provenance.verify_self_digest(coverage, "funding_history_coverage_digest")
    return coverage["funding_history_coverage_digest"]


# ==========================================================================
# SECTION 10 -- Immutable verified types
# ==========================================================================


@dataclass(frozen=True, slots=True)
class VerifiedFundingEvent:
    symbol: str
    funding_time_ms: int
    funding_time_utc: str
    funding_rate: Decimal


@dataclass(frozen=True, slots=True)
class VerifiedBarOpenClose:
    symbol: str
    source_open_time: str
    close: Decimal


@dataclass(frozen=True, slots=True)
class VerifiedEvidenceBundle:
    exact_panel: tuple[str, ...]
    funding_by_symbol: MappingProxyType
    bars_by_symbol: MappingProxyType
    provenance_baseline_digest: str
    funding_evidence_set_digest: str
    ohlcv_evidence_set_digest: str


# ==========================================================================
# SECTION 23/24 -- Path / CWD hardening, symlink / path-escape refusal
# ==========================================================================


def resolve_within_repository(relative_path: str, root: Path) -> Path:
    """Resolve relative_path under root, refusing anything that escapes root.

    Catches symlink escapes, `..` traversal, and absolute-path substitution.
    """
    root_resolved = root.resolve()
    candidate = root_resolved / relative_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathEscapeError(f"evidence path escapes repository root: {relative_path!r} resolved to {resolved}") from exc
    return resolved


# ==========================================================================
# SECTION 7/8/9 -- Verified real-evidence loader
# ==========================================================================


def _funding_raw_evidence_entry(symbol: str, baseline: dict) -> dict:
    relative_path = f"data/raw/{symbol}-perp-funding-events.jsonl"
    matches = [
        entry
        for entry in baseline["evidence_files"]
        if entry["logical_role"] == "funding_normalized_evidence" and entry["relative_path"] == relative_path
    ]
    if len(matches) != 1:
        raise EvidenceValidationError(
            f"expected exactly one funding raw-evidence entry for {symbol} in provenance baseline "
            f"at {relative_path!r}, found {len(matches)}"
        )
    return matches[0]


def _ohlcv_raw_evidence_entry(symbol: str, baseline: dict) -> dict:
    relative_path = f"experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_evidence_v0/raw/{symbol}-perp-1h.csv"
    matches = [
        entry
        for entry in baseline["evidence_files"]
        if entry["logical_role"] == "ohlcv_normalized_evidence" and entry["relative_path"] == relative_path
    ]
    if len(matches) != 1:
        raise EvidenceValidationError(
            f"expected exactly one OHLCV raw-evidence entry for {symbol} in provenance baseline "
            f"at {relative_path!r}, found {len(matches)}"
        )
    return matches[0]


def parse_funding_row(row: dict, *, symbol: str) -> VerifiedFundingEvent:
    """Parse and cross-validate a single normalized funding record.

    Repairs the previously deferred identity seam (Section 8): funding_time_ms
    MUST correspond exactly -- at millisecond precision, via exact integer
    arithmetic (no float division) -- to funding_time_utc. Times are never
    rounded or snapped to an 8-hour grid; the source value is preserved as-is.
    """
    required = {"symbol", "funding_time_ms", "funding_time_utc", "funding_rate"}
    missing = required - row.keys()
    if missing:
        raise EvidenceValidationError(f"funding row for {symbol} missing required fields: {sorted(missing)}")

    if row["symbol"] != symbol:
        raise EvidenceValidationError(f"funding row symbol mismatch: expected {symbol!r}, got {row['symbol']!r}")

    funding_time_ms = row["funding_time_ms"]
    if not isinstance(funding_time_ms, int) or isinstance(funding_time_ms, bool):
        raise EvidenceValidationError(f"{symbol}: funding_time_ms must be an integer millisecond epoch, got {funding_time_ms!r}")

    funding_time_utc_raw = row["funding_time_utc"]
    if not isinstance(funding_time_utc_raw, str) or not funding_time_utc_raw.endswith("Z"):
        raise EvidenceValidationError(f"{symbol}: funding_time_utc must be a 'Z'-suffixed UTC ISO8601 string, got {funding_time_utc_raw!r}")

    try:
        parsed = datetime.fromisoformat(funding_time_utc_raw[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceValidationError(f"{symbol}: funding_time_utc is not valid ISO8601: {funding_time_utc_raw!r}") from exc

    if parsed.microsecond % 1000:
        raise EvidenceValidationError(
            f"{symbol}: funding_time_utc has sub-millisecond precision unsupported by funding_time_ms: {funding_time_utc_raw!r}"
        )

    whole_seconds, ms_remainder = divmod(funding_time_ms, 1000)
    derived = datetime.fromtimestamp(whole_seconds, tz=UTC).replace(microsecond=ms_remainder * 1000)
    if derived != parsed:
        raise EvidenceValidationError(
            f"{symbol}: funding_time_ms/funding_time_utc identity mismatch: "
            f"funding_time_ms={funding_time_ms} implies {derived.isoformat()}, but funding_time_utc says {parsed.isoformat()}"
        )

    funding_rate_raw = row["funding_rate"]
    if not isinstance(funding_rate_raw, str):
        raise EvidenceValidationError(f"{symbol}: funding_rate must be a decimal-syntax string, got {funding_rate_raw!r}")
    try:
        funding_rate = Decimal(funding_rate_raw)
    except InvalidOperation as exc:
        raise EvidenceValidationError(f"{symbol}: funding_rate is not a valid decimal: {funding_rate_raw!r}") from exc
    if not funding_rate.is_finite():
        raise EvidenceValidationError(f"{symbol}: funding_rate is not finite: {funding_rate_raw!r}")

    return VerifiedFundingEvent(
        symbol=symbol,
        funding_time_ms=funding_time_ms,
        funding_time_utc=funding_time_utc_raw,
        funding_rate=funding_rate,
    )


def validate_funding_series(events: list[VerifiedFundingEvent], *, symbol: str) -> tuple[VerifiedFundingEvent, ...]:
    seen_ms: set[int] = set()
    for event in events:
        if event.funding_time_ms in seen_ms:
            raise EvidenceValidationError(f"{symbol}: duplicate funding_time_ms {event.funding_time_ms}")
        seen_ms.add(event.funding_time_ms)
    return tuple(events)


def parse_ohlcv_row(row: dict, *, symbol: str) -> VerifiedBarOpenClose:
    """Parse and validate a single PIT V1 hourly OHLCV row.

    The timestamp/close semantics (Section 9) are OWNED here, not accepted
    from any caller-supplied metadata: the column is always the source bar's
    OPEN time (SOURCE_BAR_OPEN_TIME) and `close` is always the close price of
    the bar that opened at that timestamp (CLOSE_PRICE_OF_BAR_OPENED_AT_TIMESTAMP).
    """
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - row.keys()
    if missing:
        raise EvidenceValidationError(f"{symbol}: OHLCV row missing required fields: {sorted(missing)}")

    ts_raw = row["timestamp"]
    if not isinstance(ts_raw, str) or not ts_raw.endswith("Z"):
        raise EvidenceValidationError(f"{symbol}: timestamp must be a 'Z'-suffixed UTC ISO8601 string, got {ts_raw!r}")
    try:
        ts = datetime.fromisoformat(ts_raw[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceValidationError(f"{symbol}: timestamp is not valid ISO8601: {ts_raw!r}") from exc
    if (ts.minute, ts.second, ts.microsecond) != (0, 0, 0):
        raise EvidenceValidationError(f"{symbol}: source bar open time is not on the hour: {ts_raw!r}")

    for field in ("open", "high", "low", "volume"):
        try:
            value = Decimal(row[field])
        except (InvalidOperation, TypeError) as exc:
            raise EvidenceValidationError(f"{symbol}: {field} is not a valid decimal: {row[field]!r}") from exc
        if not value.is_finite():
            raise EvidenceValidationError(f"{symbol}: {field} is not finite: {row[field]!r}")

    try:
        close = Decimal(row["close"])
    except (InvalidOperation, TypeError) as exc:
        raise EvidenceValidationError(f"{symbol}: close is not a valid decimal: {row['close']!r}") from exc
    if not close.is_finite() or close <= 0:
        raise EvidenceValidationError(f"{symbol}: close must be finite and positive, got {row['close']!r}")

    return VerifiedBarOpenClose(symbol=symbol, source_open_time=ts_raw, close=close)


def validate_bar_series(bars: list[VerifiedBarOpenClose], *, symbol: str) -> tuple[VerifiedBarOpenClose, ...]:
    seen: set[str] = set()
    prev_dt: datetime | None = None
    for bar in bars:
        if bar.source_open_time in seen:
            raise EvidenceValidationError(f"{symbol}: duplicate source-open timestamp {bar.source_open_time}")
        ts = datetime.fromisoformat(bar.source_open_time[:-1] + "+00:00")
        if prev_dt is not None and ts <= prev_dt:
            raise EvidenceValidationError(f"{symbol}: source-open timestamps are not strictly increasing at {bar.source_open_time}")
        seen.add(bar.source_open_time)
        prev_dt = ts
    return tuple(bars)


def _verify_ohlcv_semantics_are_frozen(baseline: dict) -> None:
    certificate = provenance._load("pit_coverage_certificate_v1.json")
    if certificate["source_timestamp_semantic"] != "BAR_OPEN_TIME":
        raise EvidenceValidationError("PIT V1 certificate source_timestamp_semantic drifted from BAR_OPEN_TIME")
    if certificate["close_value_semantic"] != OHLCV_CLOSE_SEMANTIC:
        raise EvidenceValidationError("PIT V1 certificate close_value_semantic drifted from the frozen loader semantic")
    if certificate["ohlcv_evidence_set_digest_v1"] != baseline["ohlcv_v1_evidence_set_digest"]:
        raise EvidenceValidationError("PIT V1 certificate ohlcv_evidence_set_digest_v1 does not match provenance baseline")


def _load_funding_symbol(symbol: str, baseline: dict, root: Path) -> tuple[VerifiedFundingEvent, ...]:
    entry = _funding_raw_evidence_entry(symbol, baseline)
    provenance.verify_evidence_entry(entry, root=root)
    resolved = resolve_within_repository(entry["relative_path"], root)
    events: list[VerifiedFundingEvent] = []
    for lineno, line in enumerate(resolved.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceValidationError(f"{symbol}: malformed funding JSONL at line {lineno}: {exc}") from exc
        events.append(parse_funding_row(row, symbol=symbol))
    return validate_funding_series(events, symbol=symbol)


def _load_ohlcv_symbol(symbol: str, baseline: dict, root: Path) -> tuple[VerifiedBarOpenClose, ...]:
    entry = _ohlcv_raw_evidence_entry(symbol, baseline)
    provenance.verify_evidence_entry(entry, root=root)
    resolved = resolve_within_repository(entry["relative_path"], root)
    bars: list[VerifiedBarOpenClose] = []
    with resolved.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            bars.append(parse_ohlcv_row(row, symbol=symbol))
    return validate_bar_series(bars, symbol=symbol)


def load_verified_frozen_evidence() -> VerifiedEvidenceBundle:
    """The single verified loading seam for REAL_HISTORICAL evidence.

    Zero parameters, by design: a caller cannot supply an alternate funding
    or OHLCV evidence root. All paths are derived from the canonical
    provenance baseline, which itself is derived from Path(__file__), never
    from cwd.

    Ordering (Section 7): VERIFY PROVENANCE BASELINE -> VERIFY FILE BYTES ->
    VERIFY SCHEMAS/SOURCE SEMANTICS -> PARSE -> RETURN IMMUTABLE BUNDLE.
    """
    provenance.verify_baseline()  # self-digests, evidence hashes, tracked-file
    # checks, materializer hashes, Git ancestry, funding structural coverage.

    root = provenance.ROOT
    baseline = provenance._load("provenance_baseline_v0.json")
    _verify_ohlcv_semantics_are_frozen(baseline)

    funding_by_symbol: dict[str, tuple[VerifiedFundingEvent, ...]] = {}
    bars_by_symbol: dict[str, tuple[VerifiedBarOpenClose, ...]] = {}
    for symbol in provenance.PANEL:
        funding_by_symbol[symbol] = _load_funding_symbol(symbol, baseline, root)
        bars_by_symbol[symbol] = _load_ohlcv_symbol(symbol, baseline, root)

    return VerifiedEvidenceBundle(
        exact_panel=tuple(provenance.PANEL),
        funding_by_symbol=MappingProxyType(funding_by_symbol),
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        provenance_baseline_digest=baseline["provenance_baseline_digest"],
        funding_evidence_set_digest=provenance.FUNDING_DIGEST,
        ohlcv_evidence_set_digest=provenance.OHLCV_DIGEST,
    )


# ==========================================================================
# SECTION 12/13 -- Runtime attestation
# ==========================================================================


@dataclass(frozen=True, slots=True)
class RuntimeAttestation:
    repository_root: str
    runtime_head_sha: str
    runtime_module_path: str
    runtime_executor_source_sha256: str
    worktree_clean: bool
    verified_ancestors: tuple[str, ...]


def _run_git_text(args: list[str], cwd: Path, git_runner) -> str:
    try:
        result = git_runner(["git", *args], cwd=cwd, capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeAttestationError(f"git command unavailable: git {' '.join(args)}: {exc}") from exc
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeAttestationError(f"git command failed: git {' '.join(args)}: {stderr}")
    return (result.stdout or "").strip()


def attest_runtime(
    *,
    repo_root: Path | None = None,
    module_path: Path | None = None,
    expected_repository_root: Path | None = None,
    expected_runtime_head_sha: str = PROVENANCE_BASELINE_CANONICAL_MERGE_SHA,
    required_ancestors: tuple[str, ...] = (
        provenance.PREREG_SHA,
        provenance.PIT_V1_SHA,
        PROVENANCE_BASELINE_CANONICAL_MERGE_SHA,
    ),
    git_runner=subprocess.run,
) -> RuntimeAttestation:
    """Mechanically derive the runtime's identity; never trust a caller string.

    Every field of the returned RuntimeAttestation is computed here from Git
    and the filesystem. The `expected_*` parameters are comparison targets
    only (defaulted to the frozen canonical values) -- they do not become
    part of the derived attestation itself.
    """
    root = (repo_root or provenance.ROOT).resolve()
    expected_root = (expected_repository_root or provenance.ROOT).resolve()
    module_resolved = (module_path or Path(__file__)).resolve()

    toplevel = Path(_run_git_text(["rev-parse", "--show-toplevel"], root, git_runner)).resolve()
    if toplevel != expected_root:
        raise RuntimeAttestationError(f"repository root mismatch: expected {expected_root}, git reports {toplevel}")

    head = _run_git_text(["rev-parse", "HEAD"], root, git_runner)
    if head != expected_runtime_head_sha:
        raise RuntimeAttestationError(f"runtime HEAD mismatch: expected {expected_runtime_head_sha}, got {head}")

    status = _run_git_text(["status", "--porcelain"], root, git_runner)
    if status != "":
        raise RuntimeAttestationError("worktree is not clean: `git status --porcelain` is non-empty")

    try:
        module_resolved.relative_to(toplevel)
    except ValueError as exc:
        raise RuntimeAttestationError(f"module path {module_resolved} resolves outside repository root {toplevel}") from exc

    source_sha256 = hashlib.sha256(module_resolved.read_bytes()).hexdigest()

    try:
        provenance.verify_git_ancestry(head, root=root, ancestors=required_ancestors, git_runner=git_runner)
    except AssertionError as exc:
        raise RuntimeAttestationError(str(exc)) from exc

    return RuntimeAttestation(
        repository_root=str(toplevel),
        runtime_head_sha=head,
        runtime_module_path=str(module_resolved),
        runtime_executor_source_sha256=source_sha256,
        worktree_clean=True,
        verified_ancestors=required_ancestors,
    )


# ==========================================================================
# SECTION 18/19 -- Authorization envelope + validator
# ==========================================================================


def is_valid_authorization_id(value: object) -> bool:
    return isinstance(value, str) and bool(AUTHORIZATION_ID_PATTERN.fullmatch(value))


@dataclass(frozen=True, slots=True)
class AuthorizationEnvelope:
    authorization_id: str
    experiment_id: str
    preregistration_merge_sha: str
    contract_digest: str
    pit_v1_merge_sha: str
    pit_v1_certificate_digest: str
    provenance_baseline_digest: str
    funding_history_coverage_digest: str
    execution_foundation_contract_digest: str
    funding_evidence_set_digest: str
    ohlcv_evidence_set_digest: str
    reviewed_executor_candidate_sha: str
    canonical_runtime_merge_sha: str
    executor_source_sha256: str
    execution_scope: str
    outcome_access_scope: str
    authorization_status: str


@dataclass(frozen=True, slots=True)
class AuthorizationBindingExpectations:
    experiment_id: str
    preregistration_merge_sha: str
    contract_digest: str
    pit_v1_merge_sha: str
    pit_v1_certificate_digest: str
    provenance_baseline_digest: str
    funding_history_coverage_digest: str
    execution_foundation_contract_digest: str
    funding_evidence_set_digest: str
    ohlcv_evidence_set_digest: str
    reviewed_executor_candidate_sha: str
    canonical_runtime_merge_sha: str
    executor_source_sha256: str
    execution_scope: str
    outcome_access_scope: str


def canonical_authorization_binding_expectations(*, executor_source_sha256: str) -> AuthorizationBindingExpectations:
    """Every binding this phase can freeze, plus the one it cannot yet.

    `executor_source_sha256` has no canonical value in this phase -- no V2
    executor exists yet -- so it is a required argument supplied by whoever
    is minting (or testing) a specific authorization, never invented here.
    """
    return AuthorizationBindingExpectations(
        experiment_id=EXPERIMENT_ID,
        preregistration_merge_sha=provenance.PREREG_SHA,
        contract_digest=provenance.CONTRACT_DIGEST,
        pit_v1_merge_sha=provenance.PIT_V1_SHA,
        pit_v1_certificate_digest=provenance.PIT_V1_DIGEST,
        provenance_baseline_digest=_provenance_baseline_digest(),
        funding_history_coverage_digest=_funding_history_coverage_digest(),
        execution_foundation_contract_digest=execution_foundation_contract_digest(),
        funding_evidence_set_digest=provenance.FUNDING_DIGEST,
        ohlcv_evidence_set_digest=provenance.OHLCV_DIGEST,
        reviewed_executor_candidate_sha=PROVENANCE_BASELINE_REVIEWED_CANDIDATE_SHA,
        canonical_runtime_merge_sha=PROVENANCE_BASELINE_CANONICAL_MERGE_SHA,
        executor_source_sha256=executor_source_sha256,
        execution_scope=EXECUTION_SCOPE_ONE_FROZEN_HISTORICAL_RUN,
        outcome_access_scope=OUTCOME_ACCESS_SCOPE_FUNDING_PRESSURE_TO_RV24_V0,
    )


def validate_authorization_envelope(envelope: AuthorizationEnvelope, expected: AuthorizationBindingExpectations) -> None:
    """Pure validator: fails on mutation of any bound identity. No defaults."""
    if not is_valid_authorization_id(envelope.authorization_id):
        raise AuthorizationValidationError(f"authorization_id is malformed: {envelope.authorization_id!r}")
    if envelope.authorization_status != AUTHORIZATION_STATUS_AUTHORIZED_UNUSED:
        raise AuthorizationValidationError(f"authorization_status is not AUTHORIZED_UNUSED: {envelope.authorization_status!r}")

    field_pairs = (
        ("experiment_id", envelope.experiment_id, expected.experiment_id),
        ("preregistration_merge_sha", envelope.preregistration_merge_sha, expected.preregistration_merge_sha),
        ("contract_digest", envelope.contract_digest, expected.contract_digest),
        ("pit_v1_merge_sha", envelope.pit_v1_merge_sha, expected.pit_v1_merge_sha),
        ("pit_v1_certificate_digest", envelope.pit_v1_certificate_digest, expected.pit_v1_certificate_digest),
        ("provenance_baseline_digest", envelope.provenance_baseline_digest, expected.provenance_baseline_digest),
        ("funding_history_coverage_digest", envelope.funding_history_coverage_digest, expected.funding_history_coverage_digest),
        ("execution_foundation_contract_digest", envelope.execution_foundation_contract_digest, expected.execution_foundation_contract_digest),
        ("funding_evidence_set_digest", envelope.funding_evidence_set_digest, expected.funding_evidence_set_digest),
        ("ohlcv_evidence_set_digest", envelope.ohlcv_evidence_set_digest, expected.ohlcv_evidence_set_digest),
        ("reviewed_executor_candidate_sha", envelope.reviewed_executor_candidate_sha, expected.reviewed_executor_candidate_sha),
        ("canonical_runtime_merge_sha", envelope.canonical_runtime_merge_sha, expected.canonical_runtime_merge_sha),
        ("executor_source_sha256", envelope.executor_source_sha256, expected.executor_source_sha256),
        ("execution_scope", envelope.execution_scope, expected.execution_scope),
        ("outcome_access_scope", envelope.outcome_access_scope, expected.outcome_access_scope),
    )
    for name, actual, want in field_pairs:
        if actual != want:
            raise AuthorizationValidationError(f"{name} mismatch: expected {want!r}, got {actual!r}")


# ==========================================================================
# SECTION 14-17 -- Remote at-most-once claim + crash semantics
# ==========================================================================


class ClaimOutcome(str, Enum):
    CLAIMED = "CLAIMED"
    ALREADY_CONSUMED = "ALREADY_CONSUMED"


@dataclass(frozen=True, slots=True)
class ClaimRefResult:
    status: str  # "CREATED" | "ALREADY_EXISTS"
    detail: str = ""


class AtMostOnceClaimTransport(Protocol):
    """Injected transport for REMOTE_AT_MOST_ONCE_CLAIM_V0.

    A real implementation would call GitHub's `POST /repos/.../git/refs`,
    which atomically fails with 422 "Reference already exists" if the ref
    is already there -- true create-if-absent semantics. This phase wires
    and calls only fakes/mocks; no live transport is constructed here.
    """

    def create_ref(self, ref: str, sha: str) -> ClaimRefResult: ...


def claim_ref_name(authorization_id: str) -> str:
    if not is_valid_authorization_id(authorization_id):
        raise AtMostOnceClaimError(f"cannot build claim ref for malformed authorization_id: {authorization_id!r}")
    return f"{CLAIM_REF_NAMESPACE}/{authorization_id}"


def claim_authorization_once(authorization_id: str, sha: str, transport: AtMostOnceClaimTransport) -> ClaimOutcome:
    """Fail closed on any transport error: network, permission, or malformed response.

    A second claim attempt against the same authorization_id -- even with
    the identical `sha` -- must observe ALREADY_CONSUMED, never CLAIMED.
    """
    ref = claim_ref_name(authorization_id)
    try:
        result = transport.create_ref(ref, sha)
    except Exception as exc:  # noqa: BLE001 - any transport failure fails closed
        raise AtMostOnceClaimError(f"at-most-once claim transport failed for {ref}: {exc}") from exc
    if not isinstance(result, ClaimRefResult) or result.status not in {"CREATED", "ALREADY_EXISTS"}:
        raise AtMostOnceClaimError(f"at-most-once claim transport returned a malformed response for {ref}: {result!r}")
    if result.status == "CREATED":
        return ClaimOutcome.CLAIMED
    return ClaimOutcome.ALREADY_CONSUMED


class AuthorizationLifecycleState(str, Enum):
    AUTHORIZED_UNUSED = "AUTHORIZED_UNUSED"
    CLAIMED = "CLAIMED"
    CONSUMED_INCOMPLETE = "CONSUMED_INCOMPLETE"
    CONSUMED_COMPLETE = "CONSUMED_COMPLETE"


_ALLOWED_LIFECYCLE_TRANSITIONS: dict[AuthorizationLifecycleState, frozenset[AuthorizationLifecycleState]] = {
    AuthorizationLifecycleState.AUTHORIZED_UNUSED: frozenset({AuthorizationLifecycleState.CLAIMED}),
    AuthorizationLifecycleState.CLAIMED: frozenset(
        {AuthorizationLifecycleState.CONSUMED_INCOMPLETE, AuthorizationLifecycleState.CONSUMED_COMPLETE}
    ),
    # Both consumed states are terminal for automatic execution: no automatic
    # "clear stale lock and retry" transition exists anywhere in this table.
    AuthorizationLifecycleState.CONSUMED_INCOMPLETE: frozenset(),
    AuthorizationLifecycleState.CONSUMED_COMPLETE: frozenset(),
}


def transition_authorization_lifecycle(
    current: AuthorizationLifecycleState, target: AuthorizationLifecycleState
) -> AuthorizationLifecycleState:
    allowed = _ALLOWED_LIFECYCLE_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise LifecycleTransitionError(f"illegal authorization lifecycle transition: {current.value} -> {target.value}")
    return target


# ==========================================================================
# SECTION 20-22 -- Receipt provenance envelope + digest
# ==========================================================================


@dataclass(frozen=True, slots=True)
class ReceiptProvenanceEnvelope:
    experiment_id: str
    authorization_id: str
    authorization_claim_identity: str
    preregistration_merge_sha: str
    contract_digest: str
    pit_v1_merge_sha: str
    pit_v1_certificate_digest: str
    provenance_baseline_digest: str
    funding_history_coverage_digest: str
    execution_foundation_contract_digest: str
    funding_evidence_set_digest: str
    ohlcv_evidence_set_digest: str
    reviewed_executor_candidate_sha: str
    canonical_runtime_merge_sha: str
    runtime_head_sha: str
    runtime_executor_source_sha256: str
    repository_root_identity: str
    runtime_module_path: str
    execution_scope: str
    outcome_access_scope: str
    downstream_strategy_authority: str = "NONE"
    downstream_router_authority: str = "NONE"
    downstream_qnty_authority: str = "NONE"


def validate_authorization_against_runtime(authorization: AuthorizationEnvelope, attestation: RuntimeAttestation) -> None:
    """The Section 13/21 cross-check: authorization identity vs. attested runtime identity."""
    if authorization.canonical_runtime_merge_sha != attestation.runtime_head_sha:
        raise ReceiptProvenanceError(
            f"authorization canonical_runtime_merge_sha {authorization.canonical_runtime_merge_sha!r} "
            f"does not match attested runtime_head_sha {attestation.runtime_head_sha!r}"
        )
    if authorization.executor_source_sha256 != attestation.runtime_executor_source_sha256:
        raise ReceiptProvenanceError(
            f"authorization executor_source_sha256 {authorization.executor_source_sha256!r} "
            f"does not match attested runtime_executor_source_sha256 {attestation.runtime_executor_source_sha256!r}"
        )


def build_receipt_provenance(
    *, authorization: AuthorizationEnvelope, attestation: RuntimeAttestation
) -> ReceiptProvenanceEnvelope:
    """The ONLY way to build a receipt provenance envelope.

    Runtime-derived identities (runtime_head_sha, runtime_executor_source_sha256,
    repository_root_identity, runtime_module_path) come exclusively from the
    RuntimeAttestation produced by attest_runtime(); the claim identity is
    mechanically derived from authorization_id. No parameter lets a caller
    override any of these independently (Section 21).
    """
    validate_authorization_against_runtime(authorization, attestation)
    return ReceiptProvenanceEnvelope(
        experiment_id=authorization.experiment_id,
        authorization_id=authorization.authorization_id,
        authorization_claim_identity=claim_ref_name(authorization.authorization_id),
        preregistration_merge_sha=authorization.preregistration_merge_sha,
        contract_digest=authorization.contract_digest,
        pit_v1_merge_sha=authorization.pit_v1_merge_sha,
        pit_v1_certificate_digest=authorization.pit_v1_certificate_digest,
        provenance_baseline_digest=authorization.provenance_baseline_digest,
        funding_history_coverage_digest=authorization.funding_history_coverage_digest,
        execution_foundation_contract_digest=authorization.execution_foundation_contract_digest,
        funding_evidence_set_digest=authorization.funding_evidence_set_digest,
        ohlcv_evidence_set_digest=authorization.ohlcv_evidence_set_digest,
        reviewed_executor_candidate_sha=authorization.reviewed_executor_candidate_sha,
        canonical_runtime_merge_sha=authorization.canonical_runtime_merge_sha,
        runtime_head_sha=attestation.runtime_head_sha,
        runtime_executor_source_sha256=attestation.runtime_executor_source_sha256,
        repository_root_identity=attestation.repository_root,
        runtime_module_path=attestation.runtime_module_path,
        execution_scope=authorization.execution_scope,
        outcome_access_scope=authorization.outcome_access_scope,
    )


def receipt_digest(envelope: ReceiptProvenanceEnvelope) -> str:
    payload = dataclasses.asdict(envelope)
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ==========================================================================
# SECTION 33 -- No-outcome attestation
# ==========================================================================

NO_OUTCOME_ATTESTATION = MappingProxyType(
    {
        "REAL_FUNDING_STATE_SERIES_COMPUTED": False,
        "REAL_FUNDING_PRESSURE_VALUES_COMPUTED": False,
        "REAL_ECDF_VALUES_COMPUTED": False,
        "REAL_STATE_LABELS_COMPUTED": False,
        "REAL_ASSET_RETURNS_COMPUTED": False,
        "REAL_MARKET_RETURNS_COMPUTED": False,
        "REAL_FUTURE_RV_COMPUTED": False,
        "REAL_PRIMARY_STATISTIC_COMPUTED": False,
        "REAL_REMOTE_AUTHORIZATION_CLAIM_CREATED": False,
        "ECONOMIC_OUTCOME_ACCESSED": False,
        "POST_SEALED_T0_ACCESSED": False,
    }
)
