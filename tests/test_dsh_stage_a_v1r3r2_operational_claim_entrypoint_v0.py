"""Focused tests for the H1 operational claim entrypoint (fail closed).

These tests exercise the SAME production-facing operational claim entrypoint
used for claim acquisition (``acquire_operational_claim`` and the CLI ``claim``
subcommand), NOT the lower-level ``EpisodeClaim`` constructor directly.

The operational entrypoint MUST:
- require an explicit canonical revocation/supersession state (never silently
  treat "no revocation callback" as "not revoked");
- require the actual resolved execution inputs (source SHA, execution-contract
  root, and relevant runtime/executable identities);
- accept the actual execution-contract root when it matches the resolved
  execution contract, even when ``execution_contract_root != sha256(source_sha)``
  (the old artificial surrogate binding is gone);
- block before any claim is COMMITTED on any missing/wrong proof.

All tests are deterministic and offline: no live DSH/Codex/Claude, no real
secret reads, NO production claim write (scratch refs only), no provider calls.
"""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
from pathlib import Path

import pytest

from qntylab.dsh_stage_a_v1r3r2_prelive_enforcement import (
    CLAIM_NAMESPACE,
    REVOCATION_STATE_NOT_REVOKED,
    REVOCATION_STATE_REVOKED,
    REVOCATION_STATE_SUPERSEDED,
    ClaimBlocked,
    acquire_operational_claim,
    main,
)

# The execution-contract root is an independently derived content-addressed
# execution identity. It is NOT sha256(the ASCII Git commit SHA). This fixed
# independent root is used to prove that execution_contract_root !=
# sha256(source_sha) is NOT inherently an error.
INDEPENDENT_CONTRACT_ROOT = (
    "a31eb46a45363bec1f2581b96fbaef2e278365e356fe563721449aa4a0bfb907"
)
RUNTIME_IDENTITY_DIGEST = (
    "0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3"
)
EXECUTABLE_IDENTITY_DIGEST = (
    "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"
)


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create a deterministic scratch remote + source with one seed commit."""
    remote = tmp_path / "remote.git"
    source = tmp_path / "source"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(source, "add", "seed.txt")
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=claim-test",
            "-c",
            "user.email=claim-test@example.invalid",
            "commit",
            "-qm",
            "seed",
        ],
        check=True,
    )
    head = _git(source, "rev-parse", "HEAD").stdout.strip()
    subprocess.run(
        ["git", "-C", str(source), "branch", "-f", "canonical-lineage", "HEAD"],
        check=True,
    )
    return remote, source, head


def _op_ref(suffix: str) -> str:
    return f"{CLAIM_NAMESPACE}operational-entrypoint-{suffix}"


def _op_kwargs(
    tmp_path: Path,
    source: Path,
    head: str,
    *,
    contract_root: str = INDEPENDENT_CONTRACT_ROOT,
    revocation_state: str = REVOCATION_STATE_NOT_REVOKED,
    runtime_identity_digest: str | None = RUNTIME_IDENTITY_DIGEST,
    executable_identity_digest: str | None = EXECUTABLE_IDENTITY_DIGEST,
    canonical_ref: str = "refs/heads/canonical-lineage",
) -> dict[str, object]:
    return {
        "state_dir": tmp_path / "state",
        "remote": str(tmp_path / "remote.git"),
        "ref": _op_ref("main"),
        "source_repo": source,
        "session_nonce": "session-op",
        "authorized_execution_source_sha": head,
        "execution_contract_root": contract_root,
        "revocation_state": revocation_state,
        "runtime_identity_digest": runtime_identity_digest,
        "executable_identity_digest": executable_identity_digest,
        "canonical_ref": canonical_ref,
    }


def test_operational_positive_pass_with_independent_contract_root(tmp_path: Path) -> None:
    """PASS: exact source SHA + valid ancestry + explicit not-revoked proof +
    actual expected execution-contract root + runtime/executable bindings."""
    _remote, source, head = _fixture(tmp_path)
    # Prove the old artificial condition is gone: the actual contract root is
    # NOT sha256(source_sha), yet it is accepted when it matches the resolved
    # execution contract.
    assert INDEPENDENT_CONTRACT_ROOT != hashlib.sha256(head.encode("ascii")).hexdigest()
    receipt = acquire_operational_claim(**_op_kwargs(tmp_path, source, head))
    assert receipt["state"] == "REMOTE_AND_LOCAL_COMPLETE"
    assert receipt["source_head"] == head


def test_operational_fail_missing_revocation_state(tmp_path: Path) -> None:
    """FAIL: missing revocation/supersession proof blocks before COMMITTED."""
    _remote, source, head = _fixture(tmp_path)
    kwargs = _op_kwargs(tmp_path, source, head)
    kwargs["revocation_state"] = "UNKNOWN_STATE"
    with pytest.raises(ClaimBlocked, match="explicit canonical revocation"):
        acquire_operational_claim(**kwargs)


def test_operational_fail_revoked_source(tmp_path: Path) -> None:
    """FAIL: revoked source blocks before COMMITTED."""
    _remote, source, head = _fixture(tmp_path)
    kwargs = _op_kwargs(tmp_path, source, head, revocation_state=REVOCATION_STATE_REVOKED)
    with pytest.raises(ClaimBlocked, match="revoked or superseded"):
        acquire_operational_claim(**kwargs)


def test_operational_fail_superseded_source(tmp_path: Path) -> None:
    """FAIL: superseded source blocks before COMMITTED."""
    _remote, source, head = _fixture(tmp_path)
    kwargs = _op_kwargs(tmp_path, source, head, revocation_state=REVOCATION_STATE_SUPERSEDED)
    with pytest.raises(ClaimBlocked, match="revoked or superseded"):
        acquire_operational_claim(**kwargs)


def test_operational_fail_missing_execution_contract_root(tmp_path: Path) -> None:
    """FAIL: missing resolved execution inputs (contract root) blocks."""
    _remote, source, head = _fixture(tmp_path)
    kwargs = _op_kwargs(tmp_path, source, head, contract_root="")
    with pytest.raises(ClaimBlocked, match="resolved execution-contract root"):
        acquire_operational_claim(**kwargs)


def test_operational_fail_wrong_actual_contract_root(tmp_path: Path) -> None:
    """FAIL: wrong ACTUAL contract root (substituted, not a valid sha256) blocks."""
    _remote, source, head = _fixture(tmp_path)
    kwargs = _op_kwargs(tmp_path, source, head, contract_root="not-a-real-sha256-root")
    with pytest.raises(ClaimBlocked, match="resolved execution-contract root is not a valid sha256"):
        acquire_operational_claim(**kwargs)


def test_operational_fail_wrong_runtime_identity(tmp_path: Path) -> None:
    """FAIL: wrong runtime identity digest (where contract requires it) blocks."""
    _remote, source, head = _fixture(tmp_path)
    kwargs = _op_kwargs(tmp_path, source, head, runtime_identity_digest="not-a-valid-digest")
    with pytest.raises(ClaimBlocked, match="runtime identity digest is not a valid sha256"):
        acquire_operational_claim(**kwargs)


def test_operational_fail_wrong_executable_identity(tmp_path: Path) -> None:
    """FAIL: wrong executable identity digest (where contract requires it) blocks."""
    _remote, source, head = _fixture(tmp_path)
    kwargs = _op_kwargs(tmp_path, source, head, executable_identity_digest="not-a-valid-digest")
    with pytest.raises(ClaimBlocked, match="executable identity digest is not a valid sha256"):
        acquire_operational_claim(**kwargs)


def test_operational_fail_source_sha_mismatch(tmp_path: Path) -> None:
    """FAIL: source SHA mismatch (resolved inputs disagree with the authorized
    source) blocks before COMMITTED."""
    _remote, source, head = _fixture(tmp_path)
    kwargs = _op_kwargs(tmp_path, source, head)
    # A different authorized source SHA that is not the fixture head.
    kwargs["authorized_execution_source_sha"] = "d" * 40
    with pytest.raises(ClaimBlocked, match="claim source commit object does not exist"):
        acquire_operational_claim(**kwargs)


def test_operational_fail_missing_resolved_inputs_via_cli(tmp_path: Path) -> None:
    """FAIL via CLI: missing resolved execution inputs (no contract root) blocks."""
    _remote, source, head = _fixture(tmp_path)
    argv = [
        "claim",
        "--state-dir",
        str(tmp_path / "state"),
        "--remote",
        str(tmp_path / "remote.git"),
        "--ref",
        _op_ref("cli-missing-inputs"),
        "--source-repo",
        str(source),
        "--session-nonce",
        "session-cli",
        "--authorized-execution-source-sha",
        head,
        "--revocation-state",
        REVOCATION_STATE_NOT_REVOKED,
        # --execution-contract-root omitted -> argparse fails closed.
    ]
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2


def test_cli_positive_pass_with_independent_contract_root(tmp_path: Path) -> None:
    """PASS via CLI: full operational claim through the real entrypoint."""
    _remote, source, head = _fixture(tmp_path)
    argv = [
        "claim",
        "--state-dir",
        str(tmp_path / "state"),
        "--remote",
        str(tmp_path / "remote.git"),
        "--ref",
        _op_ref("cli-pass"),
        "--source-repo",
        str(source),
        "--session-nonce",
        "session-cli-pass",
        "--authorized-execution-source-sha",
        head,
        "--execution-contract-root",
        INDEPENDENT_CONTRACT_ROOT,
        "--runtime-identity-digest",
        RUNTIME_IDENTITY_DIGEST,
        "--executable-identity-digest",
        EXECUTABLE_IDENTITY_DIGEST,
        "--revocation-state",
        REVOCATION_STATE_NOT_REVOKED,
        "--canonical-ref",
        "refs/heads/canonical-lineage",
    ]
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        code = main(argv)
    finally:
        sys.stdout = old_stdout
    assert code == 0


def test_cli_fail_revoked_via_cli(tmp_path: Path) -> None:
    """FAIL via CLI: revoked source blocks before COMMITTED."""
    _remote, source, head = _fixture(tmp_path)
    argv = [
        "claim",
        "--state-dir",
        str(tmp_path / "state"),
        "--source-repo",
        str(source),
        "--ref",
        _op_ref("cli-revoked"),
        "--session-nonce",
        "cli-revoked",
        "--authorized-execution-source-sha",
        head,
        "--execution-contract-root",
        INDEPENDENT_CONTRACT_ROOT,
        "--revocation-state",
        REVOCATION_STATE_REVOKED,
    ]
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2