from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from qntylab.dsh_stage_a_v1r3r2_prelive_enforcement import (
    DIAGNOSTIC_CLAIM_NAMESPACE,
    ClaimBlocked,
    EpisodeClaim,
    credential_free_remote_identity,
    redact_diagnostic_text,
)


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, str]:
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
    return remote, source, head


def _claim(tmp_path: Path, *, suffix: str, remote: Path, source: Path, head: str) -> EpisodeClaim:
    # H1 exact-commit claim-source seam: the source is an EXPLICIT exact
    # immutable source SHA (the fixture head), never ambient HEAD. The canonical
    # ref is the exact fixture commit object itself (deterministic scratch
    # lineage), so ancestry is provable without a remote-tracking ref.
    return EpisodeClaim(
        tmp_path / suffix,
        remote=str(remote),
        ref=f"{DIAGNOSTIC_CLAIM_NAMESPACE}{suffix}",
        source_repo=source,
        authorized_execution_source_sha=head,
        canonical_ref=head,
    )


def test_positive_create_commits_and_independently_verifies_expected_sha(tmp_path: Path) -> None:
    remote, source, head = _fixture(tmp_path)
    claim = _claim(tmp_path, suffix="positive", remote=remote, source=source, head=head)

    outcome = claim.acquire_with_outcome(session_nonce="positive-session")

    assert outcome["classification"] == "COMMITTED"
    assert outcome["diagnostic"]["expected_sha"] == head
    assert outcome["diagnostic"]["observed_sha"] == head
    assert outcome["diagnostic"]["remote_ref_state_before"]["state"] == "ABSENT"
    assert outcome["diagnostic"]["remote_ref_state_after"]["state"] == "PRESENT"
    assert outcome["diagnostic"]["local_receipt_state"] == "PRESENT"
    assert claim.receipt_path.is_file()


def test_duplicate_create_never_overwrites_existing_ref(tmp_path: Path) -> None:
    remote, source, head = _fixture(tmp_path)
    first = _claim(tmp_path, suffix="duplicate", remote=remote, source=source, head=head)
    first.acquire(session_nonce="winner")

    duplicate = _claim(tmp_path, suffix="duplicate-other-state", remote=remote, source=source, head=head)
    duplicate.ref = first.ref
    outcome = duplicate.acquire_with_outcome(session_nonce="duplicate")

    assert outcome["classification"] == "COMMITTED"
    assert outcome["reason_code"] == "REMOTE_ALREADY_COMMITTED"
    assert "receipt" not in outcome
    observed = _git(remote, "show-ref", first.ref).stdout.split()[0]
    assert observed == head
    with pytest.raises(ClaimBlocked, match="BLOCK_NEVER_REPLAY"):
        duplicate.acquire(session_nonce="duplicate-retry")


def test_different_source_sha_collision_is_fail_closed_without_overwrite(tmp_path: Path) -> None:
    remote, source, first_head = _fixture(tmp_path)
    first = _claim(tmp_path, suffix="collision", remote=remote, source=source, head=first_head)
    first.acquire(session_nonce="winner")

    (source / "seed.txt").write_text("second\n", encoding="utf-8")
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
            "second",
        ],
        check=True,
    )
    second_head = _git(source, "rev-parse", "HEAD").stdout.strip()
    second = _claim(tmp_path, suffix="collision-other-state", remote=remote, source=source, head=second_head)
    second.ref = first.ref
    outcome = second.acquire_with_outcome(session_nonce="collision")

    assert outcome["classification"] == "WRITE_STATE_UNKNOWN"
    assert outcome["reason_code"] == "REMOTE_REF_COLLISION"
    assert _git(remote, "show-ref", first.ref).stdout.split()[0] == first_head
    assert not second.receipt_path.exists()


class _FailedPush(EpisodeClaim):
    def _run_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        if "push" in command:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="simulated create-only failure",
            )
        return super()._run_command(command)


class _AmbiguousAfterFailure(_FailedPush):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._remote_reads = 0

    def _remote_ref_state(self) -> dict[str, object]:
        self._remote_reads += 1
        if self._remote_reads == 2:
            return self._remote_state(
                "UNKNOWN",
                process_exit_code=1,
                stderr="network outcome unavailable",
            )
        return super()._remote_ref_state()


def test_confirmed_no_remote_write_requires_absent_before_and_after(tmp_path: Path) -> None:
    remote, source, head = _fixture(tmp_path)
    claim = _FailedPush(
        tmp_path / "confirmed-no-write",
        remote=str(remote),
        ref=f"{DIAGNOSTIC_CLAIM_NAMESPACE}confirmed-no-write",
        source_repo=source,
        authorized_execution_source_sha=head,
        canonical_ref=head,
    )

    outcome = claim.acquire_with_outcome(session_nonce="failed-session")

    assert outcome["classification"] == "CONFIRMED_NO_REMOTE_WRITE"
    assert outcome["diagnostic"]["remote_ref_state_before"]["state"] == "ABSENT"
    assert outcome["diagnostic"]["remote_ref_state_after"]["state"] == "ABSENT"
    assert outcome["production_retry_granted"] is False
    assert claim.intent_path.is_file()
    assert not claim.receipt_path.exists()
    assert claim.remote_ref_state()["state"] == "ABSENT"


def test_unknown_transport_state_fails_closed_without_receipt(tmp_path: Path) -> None:
    remote, source, head = _fixture(tmp_path)
    claim = _AmbiguousAfterFailure(
        tmp_path / "unknown",
        remote=str(remote),
        ref=f"{DIAGNOSTIC_CLAIM_NAMESPACE}unknown",
        source_repo=source,
        authorized_execution_source_sha=head,
        canonical_ref=head,
    )

    outcome = claim.acquire_with_outcome(session_nonce="ambiguous-session")

    assert outcome["classification"] == "WRITE_STATE_UNKNOWN"
    assert outcome["fail_closed"] is True
    assert outcome["execution_authority_granted"] is False
    assert outcome["diagnostic"]["remote_ref_state_after"]["state"] == "UNKNOWN"
    assert claim.intent_path.is_file()
    assert not claim.receipt_path.exists()
    with pytest.raises(ClaimBlocked, match="BLOCK_NEVER_REPLAY"):
        claim.acquire(session_nonce="ambiguous-retry")


def test_redaction_is_deterministic_and_removes_credential_shapes() -> None:
    raw = (
        "https://alice:password123@example.invalid/repo.git?token=abc "
        "Authorization: Bearer bearer-token token=secret-value"
    )

    first = redact_diagnostic_text(raw)
    second = redact_diagnostic_text(raw)

    assert first == second
    assert "password123" not in first
    assert "bearer-token" not in first
    assert "secret-value" not in first
    assert "<REDACTED>" in first
    assert (
        credential_free_remote_identity(raw)
        == "https://example.invalid/repo.git"
    )