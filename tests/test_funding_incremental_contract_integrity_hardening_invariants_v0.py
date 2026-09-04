"""Synthetic validation for the hardened evaluation boundary (Stage 3 invariants).

Governed phase ``FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0``.

Every fixture here is SYNTHETIC.  No real evidence is loaded, no real
evaluation outcome is read, no market or funding data is acquired, and no
network call is made.  The frozen V0 executor module is treated as read-only
truth; durable stores live under ``tmp_path`` only.

The twelve decision invariants are asserted as behavior (ordering,
exactly-once, fail-closed semantics) against the actual public API of
``qntylab.jigsaw_funding_pressure_incremental_forecast_value_hardened_evaluation_boundary_v1``.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as executor
from qntylab import (
    jigsaw_funding_pressure_incremental_forecast_value_hardened_evaluation_boundary_v1 as boundary,
)

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_MODULE_PATH = ROOT / (
    "qntylab/jigsaw_funding_pressure_incremental_forecast_value_hardened_evaluation_boundary_v1.py"
)
EXECUTOR_V0_RELATIVE_PATH = "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
REAL_CAPABLE_WRAPPER_V1_RELATIVE_PATH = (
    "qntylab/jigsaw_funding_pressure_incremental_forecast_value_real_capable_wrapper_v1.py"
)
EXECUTOR_V0_SHA256 = "1ffcfeb959cfc547fcda96384c1c8f58b3f5cbc174c5d535324480ede312e8c6"
REAL_CAPABLE_WRAPPER_V1_SHA256 = "b0d30af9f6def297c23981c554d6c2224ff1736a491db009a9d8ce7fcc9a9b2e"
EXECUTION_MODE = boundary.EXECUTION_MODE_SYNTHETIC_VALIDATION
PRIVATE_ASSEMBLY_IDENTIFIER = "_assemble_incremental_forecast_evaluation"

DECISION_INVARIANT_NAMES = (
    "AUTHORITY_FAILURE_PRECEDES_ROWS",
    "AUTHORITY_FAILURE_ZERO_OBSERVABLE_SCIENCE",
    "CONFLICTING_REPLAY_FAILS_CLOSED",
    "EXECUTION_MODE_IS_NOT_PROVENANCE",
    "EXACTLY_ONCE_PROCESS_BOUNDARY",
    "EXACTLY_ONCE_SECOND_WORKER",
    "FROZEN_V0_BYTES_UNCHANGED",
    "NO_PROCESS_LOCAL_PERSISTENCE_STATE",
    "PRIVATE_EXECUTION_SEAM_FORBIDDEN",
    "PROVENANCE_CONSTRUCTOR_HONESTY",
    "RESULT_RECORD_IS_DURABLE",
    "RESULT_RECORDING_PROSE_MATCHES_BEHAVIOR",
)


# ==========================================================================
# deterministic synthetic fixtures
# ==========================================================================


def _lcg(seed: int):
    state = seed

    def draw(modulus: int) -> int:
        nonlocal state
        state = (1103515245 * state + 12345) % (2**31)
        return state % modulus

    return draw


def synthetic_grids(*, seed: int = 20240101):
    """Deterministic RV24 / funding-pressure grids on the exact frozen days."""
    draw = _lcg(seed)
    pressure = {
        executor._stamp(day): Decimal(100 + draw(900)).scaleb(-7)
        for day in executor.required_pressure_days()
    }
    rv24 = {
        executor._stamp(day): Decimal(2000 + draw(3000)).scaleb(-6)
        for day in executor.required_rv24_days()
    }
    return rv24, pressure


def build_frozen_rows() -> tuple[executor.ForecastRow, ...]:
    rv24, pressure = synthetic_grids()
    return executor.build_causal_forecast_rows(rv24_by_day=rv24, pressure_by_day=pressure)


@pytest.fixture(scope="session")
def frozen_rows() -> tuple[executor.ForecastRow, ...]:
    rows = build_frozen_rows()
    assert len(rows) == executor.REQUIRED_DEVELOPMENT_ORIGINS + executor.REQUIRED_EVALUATION_ORIGINS
    return rows


@pytest.fixture(scope="session")
def frozen_direct_evaluation(frozen_rows) -> executor.IncrementalForecastEvaluation:
    """The frozen entrypoint run directly (the differential oracle side)."""
    return executor.run_incremental_forecast_evaluation(frozen_rows, execution_mode=EXECUTION_MODE)


def hostile_rows(count: int = 4, *, target: str = "0.01") -> tuple[executor.ForecastRow, ...]:
    """Arbitrary synthetic rows (NOT the frozen schedule) for the hostile matrix."""
    base = datetime(2024, 1, 1, tzinfo=UTC)

    def row_at(origin: datetime) -> executor.ForecastRow:
        return executor.ForecastRow(
            origin=executor._stamp(origin),
            target_completion=executor._stamp(executor.target_completion_time(origin)),
            funding_percentile=Fraction(1, 2),
            rv24_target=Decimal(target),
            rv24_lags=tuple(Decimal("0.02") for _ in range(30)),
        )

    return tuple(row_at(base + timedelta(days=index)) for index in range(count))


def mutated_copy(rows: tuple[executor.ForecastRow, ...]) -> tuple[executor.ForecastRow, ...]:
    """Same schedule, different content: the first row's RV24 target shifts."""
    first = rows[0]
    return (
        executor.ForecastRow(
            origin=first.origin,
            target_completion=first.target_completion,
            funding_percentile=first.funding_percentile,
            rv24_target=first.rv24_target + Decimal("0.125"),
            rv24_lags=first.rv24_lags,
        ),
    ) + tuple(rows[1:])


def _test_row_payload(row: executor.ForecastRow) -> dict[str, object]:
    """Canonical JSON payload of one row (same encoding as the boundary)."""
    return {
        "origin": row.origin,
        "target_completion": row.target_completion,
        "funding_percentile": row.funding_percentile,
        "rv24_target": row.rv24_target,
        "rv24_lags": list(row.rv24_lags),
    }


def synthetic_fixture_bytes() -> bytes:
    """The exact canonical fixture bytes of the pinned boundary fixture contract.

    Deterministically derived from the frozen synthetic row grid; must hash to
    ``boundary.EXPECTED_SYNTHETIC_FIXTURE_SHA256`` (asserted in the H3 tests).
    """
    return boundary.canonical_json_bytes(
        {
            "fixture_identity": boundary.SYNTHETIC_FIXTURE_IDENTITY,
            "schema_identity": boundary.SYNTHETIC_FIXTURE_SCHEMA_IDENTITY,
            "rows": [_test_row_payload(row) for row in build_frozen_rows()],
        }
    )


def decoded_fixture_rows() -> tuple[executor.ForecastRow, ...]:
    """Rows deterministically decoded from the authenticated fixture bytes."""
    return boundary.decode_synthetic_fixture_rows(synthetic_fixture_bytes())


@pytest.fixture(scope="session")
def verified_fixture_rows() -> tuple[executor.ForecastRow, ...]:
    """The only rows that can hold OFFLINE_SYNTHETIC_FIXTURE provenance."""
    return decoded_fixture_rows()


def fixture_receipt(*, batch_identity: str) -> boundary.VerifiedInputProvenance:
    """The only honest synthetic-factory path: authenticated fixture bytes."""
    return boundary.make_offline_synthetic_fixture_receipt_from_authenticated_fixture(
        synthetic_fixture_bytes(), batch_identity=batch_identity
    )


def admit(rows, *, batch_identity: str):
    """Factory receipt + admitted batch over the authenticated fixture rows."""
    receipt = fixture_receipt(batch_identity=batch_identity)
    return receipt, boundary.admit_verified_batch(receipt, rows)


def hand_built_receipt(**overrides: object) -> boundary.VerifiedInputProvenance:
    """A receipt assembled outside the two factories (self-consistent digest)."""
    payload: dict[str, object] = {
        "provenance_kind": boundary.PROVENANCE_KIND_OFFLINE_SYNTHETIC_FIXTURE,
        "factory_identity": "hand_built_factory_v1/forged",
        "content_digest": "sha256:" + "ff" * 32,
        "schema_identity": "ForecastRowV0/offline-synthetic-fixture/1",
        "batch_identity": "forged-batch-v0",
        "anchor": {"fixture_digest": "sha256:" + "ee" * 32},
    }
    payload.update(overrides)
    return boundary.VerifiedInputProvenance(
        **payload,  # type: ignore[arg-type]
        receipt_digest="sha256:" + boundary.sha256_hex(boundary.canonical_json_bytes(payload)),
    )


# ==========================================================================
# fresh-process worker (the program travels inline; pristine import)
# ==========================================================================


_CHILD_PROGRAM = r'''
"""Fresh-process worker (argv: REPO_ROOT ACTION STORE_DIR [identity digest binding result]).

Emits exactly one JSON line describing the observed durable state or the
fail-closed error class.  The boundary module is imported pristine: a
module-global store would be empty here and every lookup would fail.
"""
import json
import pathlib
import sys

REPO_ROOT, ACTION, STORE_DIR = sys.argv[1], sys.argv[2], sys.argv[3]
IDENTITY = sys.argv[4] if len(sys.argv) > 4 else ""
DIGEST = sys.argv[5] if len(sys.argv) > 5 else ""
BINDING = sys.argv[6] if len(sys.argv) > 6 else ""
RESULT = sys.argv[7] if len(sys.argv) > 7 else ""

sys.path.insert(0, REPO_ROOT)

from qntylab.jigsaw_funding_pressure_incremental_forecast_value_hardened_evaluation_boundary_v1 import (  # noqa: E402
    AlreadyClaimedError,
    ConflictingReplayError,
    DurableClaimRecord,
    DurableRecordCorruptionError,
    HardenedDurableClaimStore,
)


def _fields(record: DurableClaimRecord) -> dict:
    return {
        "claim_identity": record.claim_identity,
        "claim_digest": record.claim_digest,
        "result_digest": record.result_digest,
        "authorization_binding": record.authorization_binding,
        "recorded_at_utc": record.recorded_at_utc,
        "outcome_state": record.outcome_state,
        "schema_version": record.schema_version,
    }


def emit(payload) -> None:
    print(json.dumps(payload, sort_keys=True))


def main() -> None:
    store = HardenedDurableClaimStore(pathlib.Path(STORE_DIR))
    if ACTION == "claim":
        record = store.claim_once(IDENTITY, DIGEST, BINDING)
        emit({"claimed": True, "record": _fields(record)})
    elif ACTION == "claim_and_record":
        store.claim_once(IDENTITY, DIGEST, BINDING)
        record = store.record_result(IDENTITY, DIGEST, RESULT)
        emit({"recorded": True, "record": _fields(record)})
    elif ACTION == "lookup":
        record = store.lookup(IDENTITY)
        emit({"found": record is not None, "record": None if record is None else _fields(record)})
    elif ACTION == "read_all":
        emit({"records": [_fields(item) for item in store.read_records()]})
    else:  # pragma: no cover - fixed action set
        raise SystemExit(f"unknown action {ACTION!r}")


if __name__ == "__main__":
    try:
        main()
    except (AlreadyClaimedError, ConflictingReplayError, DurableRecordCorruptionError) as exc:
        emit({"error": type(exc).__name__, "message": str(exc)})
'''


def _child_argv(action: str, store_dir: Path, *rest: str) -> list[str]:
    return [sys.executable, "-c", _CHILD_PROGRAM, str(ROOT), action, str(store_dir), *rest]


def run_child(action: str, store_dir: Path, *rest: str) -> dict[str, object]:
    completed = subprocess.run(
        _child_argv(action, store_dir, *rest), capture_output=True, text=True, timeout=180
    )
    assert completed.returncode == 0, f"worker failed:\n{completed.stderr}"
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert lines, f"worker produced no output:\n{completed.stderr}"
    return json.loads(lines[-1])


# ==========================================================================
# offline git fixtures (synthetic authorization blob; no canonical state)
# ==========================================================================


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def make_synthetic_repo(root: Path, relative: str, payload: bytes) -> tuple[Path, str]:
    """A throwaway offline git repo carrying exactly one synthetic blob."""
    repo = root / "synthetic-repo"
    repo.mkdir(parents=True, exist_ok=True)
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    git(repo, "init")
    git(repo, "add", "--", relative)
    git(
        repo,
        "-c",
        "user.email=invariant-suite@example.invalid",
        "-c",
        "user.name=invariant suite",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "synthetic validation blob",
    )
    return repo, git(repo, "rev-parse", "HEAD")


AUTHORIZATION_RELATIVE = "authorization/offline_synthetic_grant_v0.txt"
AUTHORIZATION_BYTES = b"OFFLINE_SYNTHETIC_AUTHORIZATION_GRANT_V0\n"


@pytest.fixture()
def authorization_token() -> boundary.OfflineAuthorizationToken:
    """The canonical grant receipt, freshly authenticated offline from local
    Git (no network, no token use, no remote refs)."""
    return boundary.authenticate_canonical_hardening_authorization()


@pytest.fixture()
def claim_store(tmp_path: Path) -> boundary.HardenedDurableClaimStore:
    return boundary.HardenedDurableClaimStore(tmp_path / "claims")


def make_git_anchored_receipt_for(rows, tmp_path: Path) -> tuple[Path, boundary.VerifiedInputProvenance]:
    """Commit the canonical GIT_ANCHORED artifact bundle binding ``rows``."""
    payload = boundary.git_anchored_artifact_bytes(rows)
    relative = "hostile/bundle_v0.json"
    repo, commit = make_synthetic_repo(tmp_path, relative, payload)
    receipt = boundary.make_git_anchored_receipt(
        rows,
        batch_identity="hostile-bundle-v0",
        repository_root=repo,
        pinned_commit=commit,
        artifact_relative_path=relative,
        expected_blob_sha256=hashlib.sha256(payload).hexdigest(),
    )
    return repo, receipt


@pytest.fixture(scope="session")
def recorded_run(tmp_path_factory: pytest.TempPathFactory, verified_fixture_rows) -> dict[str, object]:
    """One full hardened run over the frozen panel: claim -> core -> RECORDED."""
    token = boundary.authenticate_canonical_hardening_authorization()
    store = boundary.HardenedDurableClaimStore(tmp_path_factory.mktemp("recorded-store") / "claims")
    hardened = boundary.HardenedEvaluationBoundary(store)
    receipt = fixture_receipt(batch_identity="recorded-run-batch-v0")
    batch = hardened.admit_batch(receipt, verified_fixture_rows)
    claim_identity = "recorded-run-identity-v0"
    outcome = hardened.run_evaluation(
        authorization_token=token,
        batch=batch,
        claim_identity=claim_identity,
        execution_mode=EXECUTION_MODE,
    )
    assert outcome.record.outcome_state == boundary.OUTCOME_RECORDED
    return {
        "token": token,
        "batch": batch,
        "store": store,
        "boundary": hardened,
        "outcome": outcome,
        "claim_identity": claim_identity,
    }


# ==========================================================================
# invariant 1 -- PROVENANCE_CONSTRUCTOR_HONESTY
# ==========================================================================


def test_PROVENANCE_CONSTRUCTOR_HONESTY_forged_receipts_fail_closed_everywhere(
    claim_store: boundary.HardenedDurableClaimStore,
) -> None:
    rows = hostile_rows()
    forged = hand_built_receipt()
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_offline_synthetic_fixture_receipt(forged, rows)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.admit_verified_batch(forged, rows)
    hardened = boundary.HardenedEvaluationBoundary(claim_store)
    with pytest.raises(boundary.ProvenanceRejectedError):
        hardened.admit_batch(forged, rows)
    # No batch object ever existed, and admission touched no durable state.
    assert claim_store.read_records() == ()


def test_PROVENANCE_CONSTRUCTOR_HONESTY_arbitrary_rows_never_gain_verified_provenance(
    verified_fixture_rows: tuple[executor.ForecastRow, ...],
) -> None:
    """Arbitrary/unverified rows can NEVER gain verified synthetic provenance:
    the genuine pinned-fixture receipt refuses any other row content."""
    rows_b = mutated_copy(verified_fixture_rows)
    receipt_a = fixture_receipt(batch_identity="mismatch-probe-a")
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_offline_synthetic_fixture_receipt(receipt_a, rows_b)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.admit_verified_batch(receipt_a, rows_b)
    # And no constructor accepting arbitrary rows + a fixture identity exists.
    assert not hasattr(boundary, "make_offline_synthetic_fixture_receipt")


def test_PROVENANCE_CONSTRUCTOR_HONESTY_invented_fixture_identity_cannot_provenance_arbitrary_rows(
    tmp_path: Path,
) -> None:
    """The OLD laundering API is gone: arbitrary rows plus an invented (or even
    genuine) fixture identity cannot be elevated to verified provenance."""
    assert not hasattr(boundary, "offline_authorization_check")
    rows = hostile_rows(target="0.25")
    bundle = boundary.git_anchored_artifact_bytes(rows)
    repo, commit = make_synthetic_repo(tmp_path, "hostile/laundry_v0.json", bundle)
    receipt = boundary.make_git_anchored_receipt(
        rows,
        batch_identity="laundry-batch-v0",
        repository_root=repo,
        pinned_commit=commit,
        artifact_relative_path="hostile/laundry_v0.json",
        expected_blob_sha256=hashlib.sha256(bundle).hexdigest(),
    )
    # The git-anchored receipt binds ITS OWN rows; presenting it for the pinned
    # fixture rows (or any unrelated rows) fails closed.
    verified_fixture = decoded_fixture_rows()
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_offline_synthetic_fixture_receipt(receipt, verified_fixture)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_git_anchored_receipt(receipt, mutated_copy(rows))


def test_PROVENANCE_CONSTRUCTOR_HONESTY_receipt_substitution_between_batches_fails(
    tmp_path: Path,
) -> None:
    rows_git = hostile_rows(count=2, target="0.50")
    repo, receipt_git = make_git_anchored_receipt_for(rows_git, tmp_path)
    receipt_fixture = fixture_receipt(batch_identity="swap-fixture")
    verified_fixture = decoded_fixture_rows()
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_offline_synthetic_fixture_receipt(receipt_fixture, rows_git)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_git_anchored_receipt(receipt_git, verified_fixture)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.admit_verified_batch(receipt_fixture, rows_git)
    assert repo.is_dir()


def test_PROVENANCE_CONSTRUCTOR_HONESTY_tampered_receipt_fields_fail_self_digest(
    verified_fixture_rows: tuple[executor.ForecastRow, ...],
) -> None:
    rows = verified_fixture_rows
    good_receipt, _ = admit(rows, batch_identity="tamper-probe")
    for field, value in (
        ("receipt_digest", "sha256:" + "00" * 32),
        ("content_digest", "sha256:" + "00" * 32),
        ("batch_identity", "mutated-batch"),
        ("anchor", {"fixture_digest": "sha256:" + "11" * 32}),
        ("provenance_kind", boundary.PROVENANCE_KIND_GIT_ANCHORED),
        ("factory_identity", "mutated-factory"),
    ):
        tampered = replace(good_receipt, **{field: value})
        with pytest.raises(boundary.ProvenanceRejectedError):
            boundary.verify_offline_synthetic_fixture_receipt(tampered, rows)


def test_PROVENANCE_CONSTRUCTOR_HONESTY_content_mutation_after_binding_fails_reverify(
    verified_fixture_rows: tuple[executor.ForecastRow, ...],
) -> None:
    rows = verified_fixture_rows
    _, batch = admit(rows, batch_identity="mutation-probe")
    assert batch.reverify() == rows
    mutated = mutated_copy(rows)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.admit_verified_batch(batch.provenance, mutated)
    # The already-admitted batch still re-verifies against ITS OWN bound rows
    # (the binding is immutable); the mutated rows simply never admit.
    assert batch.rows == rows


def test_PROVENANCE_CONSTRUCTOR_HONESTY_copy_equivalent_rows_bind_by_content() -> None:
    rows = decoded_fixture_rows()
    receipt, _ = admit(rows, batch_identity="copy-probe")
    fresh_copy = decoded_fixture_rows()
    assert fresh_copy == rows  # equal content, distinct objects
    verified = boundary.verify_offline_synthetic_fixture_receipt(receipt, fresh_copy)
    assert verified == fresh_copy
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_offline_synthetic_fixture_receipt(receipt, mutated_copy(rows))


def test_PROVENANCE_CONSTRUCTOR_HONESTY_git_anchored_factory_verifies_and_fails_closed(
    tmp_path: Path,
) -> None:
    rows = hostile_rows()
    repo, receipt = make_git_anchored_receipt_for(rows, tmp_path)
    assert boundary.verify_git_anchored_receipt(receipt, rows) == rows

    payload = boundary.git_anchored_artifact_bytes(rows)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.make_git_anchored_receipt(
            rows,
            batch_identity="hostile-bundle-v0",
            repository_root=repo,
            pinned_commit=git(repo, "rev-parse", "HEAD"),
            artifact_relative_path="hostile/bundle_v0.json",
            expected_blob_sha256="9" * 64,
        )
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.make_git_anchored_receipt(
            rows,
            batch_identity="hostile-bundle-v0",
            repository_root=repo,
            pinned_commit=git(repo, "rev-parse", "HEAD"),
            artifact_relative_path="hostile/absent_v0.json",
            expected_blob_sha256=hashlib.sha256(payload).hexdigest(),
        )
    # A blob that is NOT a canonical row-binding bundle cannot provenance rows.
    raw_repo, raw_commit = make_synthetic_repo(tmp_path, "hostile/raw_v0.bin", b"HOSTILE_SYNTHETIC_BLOB_V0\n")
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.make_git_anchored_receipt(
            rows,
            batch_identity="raw-blob-v0",
            repository_root=raw_repo,
            pinned_commit=raw_commit,
            artifact_relative_path="hostile/raw_v0.bin",
            expected_blob_sha256=hashlib.sha256(b"HOSTILE_SYNTHETIC_BLOB_V0\n").hexdigest(),
        )
    foreign = tmp_path / "not-a-repo"
    foreign.mkdir()
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_git_anchored_receipt(receipt, rows, repository_root=foreign)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_git_anchored_receipt(receipt, mutated_copy(rows))


# ==========================================================================
# invariant 2 -- EXECUTION_MODE_IS_NOT_PROVENANCE
# ==========================================================================


def test_EXECUTION_MODE_IS_NOT_PROVENANCE_receipt_identity_is_mode_invariant(
    verified_fixture_rows: tuple[executor.ForecastRow, ...],
) -> None:
    rows = verified_fixture_rows
    receipt_a, batch_a = admit(rows, batch_identity="mode-invariance-probe")
    receipt_b, batch_b = admit(rows, batch_identity="mode-invariance-probe")
    assert receipt_a == receipt_b
    assert receipt_a.receipt_digest == receipt_b.receipt_digest
    assert batch_a.canonical_batch_digest() == batch_b.canonical_batch_digest()
    payload = receipt_a.to_receipt_payload()
    serialized = json.dumps(payload, sort_keys=True)
    assert "execution_mode" not in payload
    assert EXECUTION_MODE not in serialized
    assert "MODE_SUBSTITUTION_PROBE" not in serialized


def test_EXECUTION_MODE_IS_NOT_PROVENANCE_mode_change_cannot_conflict_or_reexecute(
    recorded_run: dict[str, object],
) -> None:
    run = recorded_run
    replay = run["boundary"].run_evaluation(
        authorization_token=run["token"],
        batch=run["batch"],
        claim_identity=run["claim_identity"],
        execution_mode="MODE_SUBSTITUTION_PROBE",
    )
    # A different mode did NOT change the claim digest: no ConflictingReplayError.
    assert replay.evaluation is None  # the frozen core is deliberately not re-executed
    assert replay.record == run["outcome"].record
    assert replay.record.outcome_state == boundary.OUTCOME_RECORDED
    assert replay.instrumentation.core_invocations == 0
    assert "IDEMPOTENT_RECORDED_REPLAY" in replay.instrumentation.events


# ==========================================================================
# invariant 3 -- PRIVATE_EXECUTION_SEAM_FORBIDDEN
# ==========================================================================


def test_PRIVATE_EXECUTION_SEAM_FORBIDDEN_repo_scan_only_grandfathered_hits() -> None:
    hits = []
    for path in sorted((ROOT / "qntylab").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if PRIVATE_ASSEMBLY_IDENTIFIER in path.read_text(encoding="utf-8"):
            hits.append(path.relative_to(ROOT).as_posix())
    assert set(hits) == set(boundary.GRANDFATHERED_PRIVATE_ASSEMBLY_LOCATIONS)

    # Classification: the frozen executor DEFINES the assembly and calls it
    # internally from the public entrypoint.
    executor_tree = ast.parse((ROOT / EXECUTOR_V0_RELATIVE_PATH).read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in ast.walk(executor_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert PRIVATE_ASSEMBLY_IDENTIFIER in defined

    # Classification: the frozen real-capable wrapper IMPORTS (and calls) it.
    wrapper_tree = ast.parse(
        (ROOT / REAL_CAPABLE_WRAPPER_V1_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    imported = [
        alias.name
        for node in ast.walk(wrapper_tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]
    assert PRIVATE_ASSEMBLY_IDENTIFIER in imported

    # The boundary module has ZERO occurrences: textual AND import.
    boundary_text = BOUNDARY_MODULE_PATH.read_text(encoding="utf-8")
    assert PRIVATE_ASSEMBLY_IDENTIFIER not in boundary_text
    boundary_tree = ast.parse(boundary_text)
    boundary_imports = [
        alias.name
        for node in ast.walk(boundary_tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]
    assert PRIVATE_ASSEMBLY_IDENTIFIER not in boundary_imports


# ==========================================================================
# invariants 4 and 12 -- AUTHORITY_FAILURE_PRECEDES_ROWS /
# AUTHORITY_FAILURE_ZERO_OBSERVABLE_SCIENCE
# ==========================================================================


def assert_zero_observable_science(
    hardened: boundary.HardenedEvaluationBoundary,
    store: boundary.HardenedDurableClaimStore,
    claim_identity: str,
) -> None:
    assert hardened.instrumentation.rows_constructed == 0
    assert hardened.instrumentation.core_invocations == 0
    assert store.lookup(claim_identity) is None
    assert store.read_records() == ()
    assert not store.shard_path(claim_identity).exists()


@pytest.mark.parametrize(
    "forged_token",
    [None, "SYNTHETIC_VALIDATION", 123, True, object(), []],
    ids=["missing", "mode-string", "int", "bool", "bare-object", "list"],
)
def test_AUTHORITY_FAILURE_PRECEDES_ROWS_forged_tokens_fail_closed(
    claim_store: boundary.HardenedDurableClaimStore, forged_token: object
) -> None:
    rows = decoded_fixture_rows()
    _, batch = admit(rows, batch_identity="authority-forged-probe")
    hardened = boundary.HardenedEvaluationBoundary(claim_store)
    with pytest.raises(boundary.AuthorityRejectedError):
        hardened.run_evaluation(
            authorization_token=forged_token,  # type: ignore[arg-type]
            batch=batch,
            claim_identity="authority-forged-identity",
            execution_mode=EXECUTION_MODE,
        )
    assert_zero_observable_science(hardened, claim_store, "authority-forged-identity")


def test_AUTHORITY_FAILURE_ZERO_OBSERVABLE_SCIENCE_counters_and_no_claim_persisted(
    claim_store: boundary.HardenedDurableClaimStore, authorization_token
) -> None:
    rows = decoded_fixture_rows()
    _, batch = admit(rows, batch_identity="zero-science-probe")
    hardened = boundary.HardenedEvaluationBoundary(claim_store)
    for bad_token in (None, "SYNTHETIC_VALIDATION", 3.14):
        with pytest.raises(boundary.AuthorityRejectedError):
            hardened.run_evaluation(
                authorization_token=bad_token,  # type: ignore[arg-type]
                batch=batch,
                claim_identity="zero-science-identity",
                execution_mode=EXECUTION_MODE,
            )
        # Explicit counter assertions after EVERY authority failure.
        assert hardened.instrumentation.rows_constructed == 0
        assert hardened.instrumentation.core_invocations == 0
        assert hardened.instrumentation.events == ()
    # No claim was persisted by any of the failed attempts.
    assert claim_store.lookup("zero-science-identity") is None
    assert claim_store.read_records() == ()
    assert not claim_store.shard_path("zero-science-identity").exists()
    # The genuine token remains usable afterwards (no poison state).
    record = claim_store.claim_once(
        "zero-science-identity",
        "sha256:" + "44" * 32,
        authorization_token.binding_digest(),
    )
    assert record.outcome_state == boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME


def test_AUTHORITY_FAILURE_PRECEDES_ROWS_failed_canonical_authentication_no_side_effects(
    tmp_path: Path, claim_store: boundary.HardenedDurableClaimStore
) -> None:
    """Every wrong-repository scenario fails closed with
    AuthorityRejectedError and touches no durable state.  The attacker's
    throwaway repo is self-consistent (its own commit, its own blob digest,
    even a canonical-looking origin URL) yet can never authenticate."""
    repo, commit = make_synthetic_repo(tmp_path, AUTHORIZATION_RELATIVE, AUTHORIZATION_BYTES)
    with pytest.raises(boundary.AuthorityRejectedError):
        boundary.authenticate_canonical_hardening_authorization(root=repo)
    # A canonical-looking origin URL does not help the throwaway repo either.
    git(repo, "remote", "add", "origin", "https://github.com/CipherCuttle/QntyLab.git")
    with pytest.raises(boundary.AuthorityRejectedError):
        boundary.authenticate_canonical_hardening_authorization(root=repo)
    # An unrelated non-repository directory fails closed too.
    foreign = tmp_path / "not-a-repo"
    foreign.mkdir()
    with pytest.raises(boundary.AuthorityRejectedError):
        boundary.authenticate_canonical_hardening_authorization(root=foreign)
    assert not hasattr(boundary, "offline_authorization_check")
    assert claim_store.read_records() == ()


# ==========================================================================
# crash windows
# ==========================================================================


def test_CRASH_WINDOW_BEFORE_CLAIM_authority_failure_no_side_effects_rerun_allowed(
    claim_store: boundary.HardenedDurableClaimStore,
) -> None:
    rows = decoded_fixture_rows()
    _, batch = admit(rows, batch_identity="before-claim-probe")
    hardened = boundary.HardenedEvaluationBoundary(claim_store)
    with pytest.raises(boundary.AuthorityRejectedError):
        hardened.run_evaluation(
            authorization_token="not-a-token",  # type: ignore[arg-type]
            batch=batch,
            claim_identity="before-claim-identity",
            execution_mode=EXECUTION_MODE,
        )
    # The crash window left nothing behind: no shard, no record.
    assert not claim_store.shard_path("before-claim-identity").exists()
    assert claim_store.read_records() == ()
    # A rerun is allowed: the identity is freely claimable again.
    record = claim_store.claim_once(
        "before-claim-identity", "sha256:" + "55" * 32, "sha256:" + "66" * 32
    )
    assert record.outcome_state == boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME


def test_CRASH_WINDOW_AFTER_CLAIM_BEFORE_EVALUATION_duplicate_fails_fresh_observer_no_retry(
    claim_store: boundary.HardenedDurableClaimStore, authorization_token
) -> None:
    rows = decoded_fixture_rows()
    _, batch = admit(rows, batch_identity="after-claim-probe")
    claim_digest = boundary.HardenedEvaluationBoundary._claim_digest(
        claim_identity="after-claim-identity",
        authorization_binding=authorization_token.binding_digest(),
        batch_digest=batch.canonical_batch_digest(),
    )
    claim_store.claim_once(
        "after-claim-identity", claim_digest, authorization_token.binding_digest()
    )

    hardened = boundary.HardenedEvaluationBoundary(claim_store)
    with pytest.raises(boundary.AlreadyClaimedError):
        hardened.run_evaluation(
            authorization_token=authorization_token,
            batch=batch,
            claim_identity="after-claim-identity",
            execution_mode=EXECUTION_MODE,
        )
    assert hardened.instrumentation.rows_constructed == 0
    assert hardened.instrumentation.core_invocations == 0

    # A fresh process observes the durable claim state independently.
    fresh = run_child("lookup", claim_store.directory, "after-claim-identity")
    assert fresh["found"] is True
    assert fresh["record"]["outcome_state"] == boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME

    # No automatic retry exists: the state is still CLAIMED_WITHOUT_OUTCOME.
    assert (
        claim_store.lookup("after-claim-identity").outcome_state
        == boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME
    )


def test_CRASH_WINDOW_AFTER_EVALUATION_BEFORE_RECORD_no_silent_reexecution_reconcile_represents_only(
    claim_store: boundary.HardenedDurableClaimStore, authorization_token
) -> None:
    rows = decoded_fixture_rows()
    _, batch = admit(rows, batch_identity="after-eval-probe")
    claim_digest = boundary.HardenedEvaluationBoundary._claim_digest(
        claim_identity="after-eval-identity",
        authorization_binding=authorization_token.binding_digest(),
        batch_digest=batch.canonical_batch_digest(),
    )
    claim_store.claim_once(
        "after-eval-identity", claim_digest, authorization_token.binding_digest()
    )

    hardened = boundary.HardenedEvaluationBoundary(claim_store)
    # The duplicate-claim guard prevents any silent re-execution.
    with pytest.raises(boundary.AlreadyClaimedError):
        hardened.run_evaluation(
            authorization_token=authorization_token,
            batch=batch,
            claim_identity="after-eval-identity",
            execution_mode=EXECUTION_MODE,
        )
    assert hardened.instrumentation.core_invocations == 0

    # Reconciliation only represents observed state; it never invents outcomes.
    observed = hardened.reconcile("after-eval-identity")
    assert observed is not None
    assert observed.outcome_state == boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME
    assert observed.result_digest is None
    assert observed.claim_digest == claim_digest
    with pytest.raises(boundary.ConflictingReplayError):
        hardened.reconcile("after-eval-identity", "sha256:" + "99" * 32)
    assert hardened.reconcile("never-claimed-identity") is None
    # Nothing was invented on disk either.
    assert claim_store.lookup("after-eval-identity").result_digest is None


def test_CRASH_WINDOW_AFTER_RECORD_BEFORE_RETURN_fresh_observer_recorded_replay_zero_core(
    recorded_run: dict[str, object], frozen_direct_evaluation
) -> None:
    run = recorded_run
    fresh = run_child("lookup", run["store"].directory, run["claim_identity"])
    assert fresh["found"] is True
    assert fresh["record"]["outcome_state"] == boundary.OUTCOME_RECORDED
    assert fresh["record"]["result_digest"] == frozen_direct_evaluation.result_digest

    replay = run["boundary"].run_evaluation(
        authorization_token=run["token"],
        batch=run["batch"],
        claim_identity=run["claim_identity"],
        execution_mode=EXECUTION_MODE,
    )
    assert replay.evaluation is None  # original durable result state, no re-execution
    assert replay.record == run["outcome"].record
    assert replay.record.result_digest == frozen_direct_evaluation.result_digest
    assert replay.instrumentation.core_invocations == 0
    assert replay.instrumentation.rows_constructed == 0


# ==========================================================================
# FROZEN_V0 differential + invariants 9, 10, 11
# ==========================================================================


def test_FROZEN_V0_DIFFERENTIAL_direct_and_boundary_result_digests_identical(
    recorded_run: dict[str, object], frozen_direct_evaluation
) -> None:
    boundary_evaluation = recorded_run["outcome"].evaluation
    assert boundary_evaluation.execution_mode == EXECUTION_MODE
    assert boundary_evaluation.result_digest == frozen_direct_evaluation.result_digest
    # The durable record carries exactly that digest.
    assert recorded_run["outcome"].record.result_digest == frozen_direct_evaluation.result_digest


def test_FROZEN_V0_BYTES_UNCHANGED_live_hashes_match_decision_pins() -> None:
    assert (
        hashlib.sha256((ROOT / EXECUTOR_V0_RELATIVE_PATH).read_bytes()).hexdigest()
        == EXECUTOR_V0_SHA256
    )
    assert (
        hashlib.sha256((ROOT / REAL_CAPABLE_WRAPPER_V1_RELATIVE_PATH).read_bytes()).hexdigest()
        == REAL_CAPABLE_WRAPPER_V1_SHA256
    )
    # The boundary module names all twelve invariants as plain constants.
    for name in DECISION_INVARIANT_NAMES:
        assert getattr(boundary, name) == name


def test_NO_PROCESS_LOCAL_PERSISTENCE_STATE_fresh_interpreter_observes_durable_state(
    recorded_run: dict[str, object],
) -> None:
    """A fresh interpreter with a pristine import of the boundary module sees
    the durable state an earlier process wrote.  A module-global store would
    be empty here and the lookup would fail."""
    run = recorded_run
    fresh = run_child("lookup", run["store"].directory, run["claim_identity"])
    assert fresh["found"] is True
    assert fresh["record"]["outcome_state"] == boundary.OUTCOME_RECORDED
    assert fresh["record"]["result_digest"] == run["outcome"].evaluation.result_digest


def test_NO_PROCESS_LOCAL_PERSISTENCE_STATE_no_module_level_mutable_containers() -> None:
    tree = ast.parse(BOUNDARY_MODULE_PATH.read_text(encoding="utf-8"))
    flagged: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        else:
            targets, value = [], None
        # Dunders (e.g. __all__) are static API manifests, never durable state.
        if any(
            isinstance(target, ast.Name) and target.id.startswith("__") and target.id.endswith("__")
            for target in targets
        ):
            continue
        if isinstance(
            value, (ast.Dict, ast.DictComp, ast.Set, ast.SetComp, ast.List, ast.ListComp)
        ):
            flagged.extend(ast.unparse(target) for target in targets)
    assert flagged == [], f"module-level mutable containers must not be durable state: {flagged}"


def test_RESULT_RECORDING_PROSE_MATCHES_BEHAVIOR_public_recording_on_disk_and_rereadable(
    recorded_run: dict[str, object],
) -> None:
    run = recorded_run
    result_digest = run["outcome"].evaluation.result_digest
    # The public recording path produced an actual on-disk JSONL record.
    shard = run["store"].shard_path(run["claim_identity"])
    assert shard.is_file()
    lines = [
        boundary.DurableClaimRecord.from_json_line(line)
        for line in shard.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines
    assert lines[-1].outcome_state == boundary.OUTCOME_RECORDED
    assert lines[-1].result_digest == result_digest
    # The record re-reads identically after the writing process is done.
    assert run["store"].latest_record_for(run["claim_identity"]) == lines[-1]
    fresh = run_child("read_all", run["store"].directory)
    assert fresh["records"][-1]["result_digest"] == result_digest


# ==========================================================================
# invariants 5, 6, 7, 8 -- exactly-once, conflicts, durability
# ==========================================================================


def test_EXACTLY_ONCE_PROCESS_BOUNDARY_child_sees_parent_claim_duplicate_fails(
    claim_store: boundary.HardenedDurableClaimStore,
) -> None:
    identity = "process-boundary-identity-v0"
    digest = "sha256:" + "aa" * 32
    binding = "sha256:" + "bb" * 32
    parent_record = claim_store.claim_once(identity, digest, binding)
    assert parent_record.outcome_state == boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME

    child = run_child("claim", claim_store.directory, identity, digest, binding)
    assert child.get("error") == "AlreadyClaimedError"

    # The claim is independently observable by the fresh process.
    child_lookup = run_child("lookup", claim_store.directory, identity)
    assert child_lookup["found"] is True
    assert child_lookup["record"]["claim_digest"] == digest


def test_EXACTLY_ONCE_PROCESS_BOUNDARY_record_observable_as_recorded_from_fresh_child(
    claim_store: boundary.HardenedDurableClaimStore,
) -> None:
    identity = "process-boundary-recorded-identity-v0"
    digest = "sha256:" + "cc" * 32
    binding = "sha256:" + "dd" * 32
    result = "sha256:" + "ee" * 32
    claim_store.claim_once(identity, digest, binding)
    claim_store.record_result(identity, digest, result)

    child = run_child("lookup", claim_store.directory, identity)
    assert child["found"] is True
    assert child["record"]["outcome_state"] == boundary.OUTCOME_RECORDED
    assert child["record"]["result_digest"] == result


def test_EXACTLY_ONCE_SECOND_WORKER_two_independent_processes_exactly_one_establishes(
    tmp_path: Path,
) -> None:
    store_dir = tmp_path / "race-store"
    identity = "second-worker-identity-v0"
    digest = "sha256:" + "ab" * 32
    binding = "sha256:" + "cd" * 32

    argv = _child_argv("claim", store_dir, identity, digest, binding)
    procs = [
        subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    outcomes = []
    for proc in procs:
        stdout, stderr = proc.communicate(timeout=180)
        assert proc.returncode == 0, stderr
        outcomes.append(json.loads([line for line in stdout.splitlines() if line.strip()][-1]))

    errors = sorted(str(outcome.get("error", "")) for outcome in outcomes)
    assert errors == ["", "AlreadyClaimedError"]  # exactly one process established the claim
    winner = next(outcome for outcome in outcomes if "error" not in outcome)
    assert winner["record"]["outcome_state"] == boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME
    assert winner["record"]["claim_digest"] == digest

    after = run_child("read_all", store_dir)
    assert len(after["records"]) == 1
    assert after["records"][0]["claim_identity"] == identity


def test_CONFLICTING_REPLAY_FAILS_CLOSED_in_process_and_fresh_subprocess_state_intact(
    claim_store: boundary.HardenedDurableClaimStore,
) -> None:
    identity = "conflict-identity-v0"
    good_digest = "sha256:" + "01" * 32
    other_digest = "sha256:" + "02" * 32
    binding = "sha256:" + "03" * 32
    original = claim_store.claim_once(identity, good_digest, binding)

    with pytest.raises(boundary.ConflictingReplayError):
        claim_store.claim_once(identity, other_digest, binding)

    child = run_child("claim", claim_store.directory, identity, other_digest, binding)
    assert child.get("error") == "ConflictingReplayError"

    # The durable state remains observable and uncorrupted: exactly the
    # original record survives.
    records = claim_store.read_records()
    assert len(records) == 1
    assert records[0] == original
    assert claim_store.lookup(identity).claim_digest == good_digest
    child_lookup = run_child("lookup", claim_store.directory, identity)
    assert child_lookup["record"]["claim_digest"] == good_digest


def test_CONFLICTING_REPLAY_FAILS_CLOSED_result_recording_digest_mismatch(
    claim_store: boundary.HardenedDurableClaimStore,
) -> None:
    identity = "conflict-record-identity-v0"
    digest = "sha256:" + "04" * 32
    binding = "sha256:" + "05" * 32
    claim_store.claim_once(identity, digest, binding)
    with pytest.raises(boundary.ConflictingReplayError):
        claim_store.record_result(identity, "sha256:" + "06" * 32, "sha256:" + "07" * 32)
    # No result was recorded under the conflicting digest.
    assert claim_store.lookup(identity).result_digest is None
    assert (
        claim_store.lookup(identity).outcome_state == boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME
    )


def test_RESULT_RECORD_IS_DURABLE_producer_exit_fresh_reader_exact_fields(tmp_path: Path) -> None:
    store_dir = tmp_path / "durable-store"
    identity = "durable-producer-identity-v0"
    digest = "sha256:" + "11" * 32
    binding = "sha256:" + "22" * 32
    result = "sha256:" + "33" * 32

    producer = run_child("claim_and_record", store_dir, identity, digest, binding, result)
    assert producer["recorded"] is True

    reader = run_child("lookup", store_dir, identity)
    assert reader["found"] is True
    fields = reader["record"]
    for required in (
        "claim_identity",
        "claim_digest",
        "result_digest",
        "authorization_binding",
        "recorded_at_utc",
        "outcome_state",
    ):
        assert required in fields
    assert fields["claim_identity"] == identity
    assert fields["claim_digest"] == digest
    assert fields["result_digest"] == result
    assert fields["authorization_binding"] == binding
    assert fields["outcome_state"] == boundary.OUTCOME_RECORDED
    assert fields["schema_version"] == boundary.DURABLE_RECORD_SCHEMA_VERSION


# ==========================================================================
# adversarial paths (hostile-input matrix) and store contract details
# ==========================================================================


def test_ADVERSARIAL_mode_substitution_claim_persisted_core_refuses_no_record(
    claim_store: boundary.HardenedDurableClaimStore, authorization_token
) -> None:
    rows = decoded_fixture_rows()
    _, batch = admit(rows, batch_identity="mode-substitution-probe")
    hardened = boundary.HardenedEvaluationBoundary(claim_store)
    with pytest.raises(executor.UnauthorizedExecutionError):
        hardened.run_evaluation(
            authorization_token=authorization_token,
            batch=batch,
            claim_identity="mode-substitution-identity",
            execution_mode="NOT_A_REAL_MODE",
        )
    # The claim persisted (crash-window semantics) but no outcome was recorded:
    # the frozen mode guard refused the substituted mode.
    record = claim_store.lookup("mode-substitution-identity")
    assert record.outcome_state == boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME
    assert record.result_digest is None
    assert hardened.instrumentation.rows_constructed == len(rows)
    assert hardened.instrumentation.core_invocations == 1


def test_ADVERSARIAL_same_identity_different_content_conflicting_replay(
    recorded_run: dict[str, object], tmp_path: Path
) -> None:
    run = recorded_run
    rows = hostile_rows(target="0.75")
    _, receipt = make_git_anchored_receipt_for(rows, tmp_path)
    different_batch = boundary.admit_verified_batch(receipt, rows)
    with pytest.raises(boundary.ConflictingReplayError):
        run["boundary"].run_evaluation(
            authorization_token=run["token"],
            batch=different_batch,
            claim_identity=run["claim_identity"],
            execution_mode=EXECUTION_MODE,
        )
    # The original RECORDED record is untouched and the store is uncorrupted.
    record = run["store"].lookup(run["claim_identity"])
    assert record.outcome_state == boundary.OUTCOME_RECORDED
    assert record.result_digest == run["outcome"].evaluation.result_digest
    assert len(run["store"].read_records()) == 2


@pytest.mark.parametrize(
    ("scenario", "overrides", "resign"),
    [
        ("truncated_content_digest", {"content_digest": "sha256:abc"}, True),
        ("wrong_type_content_digest", {"content_digest": 123}, True),
        ("unknown_provenance_kind", {"provenance_kind": "TOTALLY_UNKNOWN_KIND"}, True),
        ("anchor_tampered_after_signing", {"anchor": {"fixture_digest": "sha256:" + "11" * 32}}, False),
        ("batch_identity_tampered_after_signing", {"batch_identity": "mutated-batch"}, False),
    ],
)
def test_ADVERSARIAL_malformed_receipt_matrix_fails_closed(
    scenario: str, overrides: dict[str, object], resign: bool
) -> None:
    rows = decoded_fixture_rows()
    good_receipt, _ = admit(rows, batch_identity="matrix-probe")
    payload = good_receipt.to_receipt_payload()
    payload.update(overrides)
    receipt_digest = (
        "sha256:" + boundary.sha256_hex(boundary.canonical_json_bytes(payload))
        if resign
        else good_receipt.receipt_digest
    )
    forged = boundary.VerifiedInputProvenance(
        **payload,  # type: ignore[arg-type]
        receipt_digest=receipt_digest,
    )
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_offline_synthetic_fixture_receipt(forged, rows)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.admit_verified_batch(forged, rows)


def test_DURABLE_RECORD_corrupt_and_torn_lines_fail_closed(tmp_path: Path) -> None:
    store = boundary.HardenedDurableClaimStore(tmp_path / "corrupt-store")
    digest = "sha256:" + "21" * 32
    store.claim_once("torn-identity", digest, "sha256:" + "23" * 32)
    shard = store.shard_path("torn-identity")
    with shard.open("a", encoding="utf-8") as handle:
        handle.write('{"claim_identity": "torn-identity", "cla')  # torn append
    with pytest.raises(boundary.DurableRecordCorruptionError):
        store.read_records()
    with pytest.raises(boundary.DurableRecordCorruptionError):
        store.lookup("torn-identity")

    schema_store = boundary.HardenedDurableClaimStore(tmp_path / "schema-store")
    schema_store.claim_once("schema-identity", digest, "sha256:" + "24" * 32)
    bad_record = {
        "claim_identity": "schema-identity",
        "claim_digest": digest,
        "result_digest": None,
        "authorization_binding": "sha256:" + "25" * 32,
        "recorded_at_utc": "2026-01-01T00:00:00Z",
        "outcome_state": boundary.OUTCOME_CLAIMED_WITHOUT_OUTCOME,
        "schema_version": "UNKNOWN_SCHEMA_V999",
    }
    with schema_store.shard_path("schema-identity").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(bad_record, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(boundary.DurableRecordCorruptionError):
        schema_store.read_records()


def test_DURABLE_RECORD_recorded_at_utc_is_not_semantic_identity(
    claim_store: boundary.HardenedDurableClaimStore,
) -> None:
    """A crash-window recovery append over the same semantic claim with a
    different timestamp creates NO conflict and NO new identity: the duplicate
    claim over the RECORDED state is an idempotent replay."""
    identity = "timestamp-identity-v0"
    digest = "sha256:" + "31" * 32
    binding = "sha256:" + "32" * 32
    first = claim_store.claim_once(identity, digest, binding)
    recovered = boundary.DurableClaimRecord(
        claim_identity=first.claim_identity,
        claim_digest=first.claim_digest,
        result_digest="sha256:" + "cd" * 32,
        authorization_binding=first.authorization_binding,
        recorded_at_utc="1999-12-31T23:59:59Z",
        outcome_state=boundary.OUTCOME_RECORDED,
    )
    with claim_store.shard_path(identity).open("a", encoding="utf-8") as handle:
        handle.write(recovered.to_json_line() + "\n")
    replay = claim_store.claim_once(identity, digest, binding)
    assert replay == recovered
    assert replay.outcome_state == boundary.OUTCOME_RECORDED


# ==========================================================================
# targeted hostile-review regressions (H1-H4, PR #245 review PRR_kwDOTo27Xs8AAAABMQI3yw)
# ==========================================================================


def test_H1_FORGED_AUTHORIZATION_TOKEN_REJECTED(
    claim_store: boundary.HardenedDurableClaimStore,
) -> None:
    """A directly constructed OfflineAuthorizationToken with plausible fields
    is a descriptive receipt only: admission independently re-authenticates the
    canonical grant from Git, the forged binding cannot match it, and the
    forged token yields ZERO rows, ZERO core invocations, and no persisted
    claim or result."""
    rows = decoded_fixture_rows()
    _, batch = admit(rows, batch_identity="h1-forged-probe")
    forged = boundary.OfflineAuthorizationToken(
        grant_identity="INVARIANT_SUITE_OFFLINE_GRANT_V0",
        pinned_authorization_sha256=hashlib.sha256(AUTHORIZATION_BYTES).hexdigest(),
        verification_commit="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        verified_at_commit_binding="sha256:" + "ab" * 32,
    )
    hardened = boundary.HardenedEvaluationBoundary(claim_store)
    with pytest.raises(boundary.AuthorityRejectedError):
        hardened.run_evaluation(
            authorization_token=forged,
            batch=batch,
            claim_identity="h1-forged-identity",
            execution_mode=EXECUTION_MODE,
        )
    assert hardened.instrumentation.rows_constructed == 0
    assert hardened.instrumentation.core_invocations == 0
    assert claim_store.lookup("h1-forged-identity") is None
    assert claim_store.read_records() == ()
    assert not claim_store.shard_path("h1-forged-identity").exists()


def test_H2_CALLER_SELECTED_GIT_AUTHORITY_REJECTED(
    tmp_path: Path, claim_store: boundary.HardenedDurableClaimStore
) -> None:
    """A throwaway git repository with a self-consistent authorization blob
    (matching SHA/path/commit chosen by the attacker) can never authenticate
    the canonical grant: the trust root is source-pinned and the caller cannot
    select it.  The canonical offline positive control still works with no
    network access, no GitHub API, no token use and no remote refs."""
    # Attacker: fully self-consistent throwaway repo, canonical-looking origin.
    repo, commit = make_synthetic_repo(tmp_path, AUTHORIZATION_RELATIVE, AUTHORIZATION_BYTES)
    digest = hashlib.sha256(AUTHORIZATION_BYTES).hexdigest()
    git(repo, "remote", "add", "origin", "https://github.com/CipherCuttle/QntyLab.git")
    # The old caller-selected verification API no longer exists at all.
    assert not hasattr(boundary, "offline_authorization_check")
    with pytest.raises(boundary.AuthorityRejectedError):
        boundary.authenticate_canonical_hardening_authorization(root=repo)
    # Even a forged receipt built from the attacker's repo is refused at
    # admission, with zero observable science and no durable claim.
    rows = decoded_fixture_rows()
    _, batch = admit(rows, batch_identity="h2-throwaway-probe")
    forged = boundary.OfflineAuthorizationToken(
        grant_identity=boundary.CANONICAL_GRANT_IDENTITY,
        pinned_authorization_sha256=digest,
        verification_commit=commit,
        verified_at_commit_binding="sha256:" + "cd" * 32,
    )
    hardened = boundary.HardenedEvaluationBoundary(claim_store)
    with pytest.raises(boundary.AuthorityRejectedError):
        hardened.run_evaluation(
            authorization_token=forged,
            batch=batch,
            claim_identity="h2-throwaway-identity",
            execution_mode=EXECUTION_MODE,
        )
    assert hardened.instrumentation.rows_constructed == 0
    assert hardened.instrumentation.core_invocations == 0
    assert claim_store.lookup("h2-throwaway-identity") is None
    assert claim_store.read_records() == ()
    # Positive control: canonical offline authentication succeeds from local
    # Git only, and every git invocation stays a local read-only command.
    commands: list[list[str]] = []
    real_run = subprocess.run

    def recording_run(args, **kwargs):  # type: ignore[no-untyped-def]
        commands.append(list(args))
        return real_run(args, **kwargs)

    subprocess.run = recording_run  # type: ignore[assignment]
    try:
        token = boundary.authenticate_canonical_hardening_authorization()
    finally:
        subprocess.run = real_run  # type: ignore[assignment]
    assert token.verification_commit == boundary.EXPECTED_CANONICAL_AUTHORIZATION_COMMIT
    assert token.pinned_authorization_sha256 == boundary.EXPECTED_CANONICAL_AUTHORIZATION_SHA256
    local_read_only = {"cat-file", "rev-parse", "merge-base", "ls-tree", "config"}
    for argv in commands:
        if argv[:1] == ["git"]:
            subcommands = {arg for arg in argv[2:] if not arg.startswith("-") and arg != "origin"} \
                & local_read_only
            assert subcommands, f"unexpected non-local git invocation: {argv}"
        assert not any(arg in {"ls-remote", "fetch", "clone", "push", "pull"} for arg in argv)


def test_H3_ARBITRARY_ROWS_CANNOT_GAIN_SYNTHETIC_PROVENANCE(
    verified_fixture_rows: tuple[executor.ForecastRow, ...],
) -> None:
    """Arbitrary ForecastRows can never be promoted to VERIFIED synthetic
    provenance: (1) no constructor accepts rows + a fixture identity; (2)
    untrusted rows with an invented fixture identity fail; (3) arbitrary rows
    presented with the GENUINE fixture identity fail; (4) fixture bytes changed
    after the receipt fail; (5) a self-consistent receipt whose content digest
    does not match the pinned row digest fails; (6) exact authenticated fixture
    bytes decode, verify, and admit; (7) copy-equivalent rows verify by
    deterministic derivation from the same authenticated fixture contract."""
    genuine_rows = verified_fixture_rows
    genuine_receipt = fixture_receipt(batch_identity="h3-genuine")
    # (2) untrusted arbitrary rows + invented fixture identity: no such API.
    assert not hasattr(boundary, "make_offline_synthetic_fixture_receipt")
    arbitrary = hostile_rows(target="0.31")
    # (3) arbitrary rows + the genuine fixture identity (the genuine receipt):
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_offline_synthetic_fixture_receipt(genuine_receipt, arbitrary)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.admit_verified_batch(genuine_receipt, arbitrary)
    # (4) fixture bytes changed after the receipt: re-authentication refuses.
    tampered = synthetic_fixture_bytes()[:-1] + b" "
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.decode_synthetic_fixture_rows(tampered)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.make_offline_synthetic_fixture_receipt_from_authenticated_fixture(
            tampered, batch_identity="h3-tampered"
        )
    # (5) a receipt whose row content digest is valid-looking but does not
    # match the pinned fixture row digest (even fully re-signed) is refused.
    forged_payload = genuine_receipt.to_receipt_payload()
    forged_payload["content_digest"] = "sha256:" + boundary.sha256_hex(
        boundary.canonical_json_bytes([{"origin": "forged"}])
    )
    forged = boundary.VerifiedInputProvenance(
        **forged_payload,  # type: ignore[arg-type]
        receipt_digest="sha256:" + boundary.sha256_hex(boundary.canonical_json_bytes(forged_payload)),
    )
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_offline_synthetic_fixture_receipt(forged, genuine_rows)
    # (6) the exact authenticated fixture is accepted end to end.
    receipt = fixture_receipt(batch_identity="h3-exact")
    batch = boundary.admit_verified_batch(receipt, decoded_fixture_rows())
    assert batch.reverify() == genuine_rows
    # (7) copy-equivalent rows (equal content, distinct objects) verify.
    fresh = decoded_fixture_rows()
    assert fresh == genuine_rows
    assert boundary.verify_offline_synthetic_fixture_receipt(receipt, fresh) == fresh
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_offline_synthetic_fixture_receipt(receipt, mutated_copy(genuine_rows))


def test_H4_UNRELATED_GIT_BLOB_CANNOT_PROVENANCE_ARBITRARY_ROWS(tmp_path: Path) -> None:
    """The authenticated Git artifact must bind the exact rows: a valid
    committed bundle for rows A cannot provenance unrelated arbitrary rows B
    (the digest authenticated INSIDE the artifact bytes must equal the digest
    of the presented rows), while the exact rows bound by the bundle are
    accepted."""
    rows_a = hostile_rows(count=3, target="0.41")
    bundle = boundary.git_anchored_artifact_bytes(rows_a)
    repo, commit = make_synthetic_repo(tmp_path, "hostile/h4_bundle_v0.json", bundle)
    blob_digest = hashlib.sha256(bundle).hexdigest()
    rows_b = hostile_rows(count=3, target="0.67")
    # The factory refuses to pair blob A with unrelated rows B.
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.make_git_anchored_receipt(
            rows_b,
            batch_identity="h4-unrelated",
            repository_root=repo,
            pinned_commit=commit,
            artifact_relative_path="hostile/h4_bundle_v0.json",
            expected_blob_sha256=blob_digest,
        )
    # A receipt for A cannot be verified against B either.
    receipt_a = boundary.make_git_anchored_receipt(
        rows_a,
        batch_identity="h4-exact",
        repository_root=repo,
        pinned_commit=commit,
        artifact_relative_path="hostile/h4_bundle_v0.json",
        expected_blob_sha256=blob_digest,
    )
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.verify_git_anchored_receipt(receipt_a, rows_b)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.admit_verified_batch(receipt_a, rows_b)
    # The exact rows bound by the authenticated artifact are accepted.
    assert boundary.verify_git_anchored_receipt(receipt_a, rows_a) == rows_a
    batch = boundary.admit_verified_batch(receipt_a, rows_a)
    assert batch.reverify() == rows_a
    # A byte-modified artifact (digest no longer matching the pin) fails.
    tampered = bundle[:-1] + b" "
    repo2, commit2 = make_synthetic_repo(tmp_path, "hostile/h4_tampered_v0.json", tampered)
    with pytest.raises(boundary.ProvenanceRejectedError):
        boundary.make_git_anchored_receipt(
            rows_a,
            batch_identity="h4-tampered",
            repository_root=repo2,
            pinned_commit=commit2,
            artifact_relative_path="hostile/h4_tampered_v0.json",
            expected_blob_sha256=blob_digest,
        )
    assert repo.is_dir() and repo2.is_dir()
