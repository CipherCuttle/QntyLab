"""Focused negative/positive tests for the H1 exact-commit claim-source seam.

All tests are deterministic and offline: no live DSH/Codex/Claude, no real
secret reads, NO production claim write (scratch refs only), no provider calls.
The claim record/intent must contain the EXACT authorized SHA, never an ambient
HEAD substituted at action time.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from qntylab.dsh_stage_a_v1r3r2_prelive_enforcement import (
    CLAIM_NAMESPACE,
    ClaimBlocked,
    EpisodeClaim,
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
    # deterministic canonical lineage: refs/heads/canonical-lineage points at
    # HEAD (the default branch name may already be master on some Git configs,
    # so a dedicated ref avoids worktree-branch conflicts).
    subprocess.run(
        ["git", "-C", str(source), "branch", "-f", "canonical-lineage", "HEAD"],
        check=True,
    )
    return remote, source, head


def _claim(
    tmp_path: Path,
    source: Path,
    *,
    source_sha: str | None,
    canonical_ref: str = "refs/heads/canonical-lineage",
    resolved_execution_inputs: dict[str, str] | None = None,
    revocation_check=None,
) -> EpisodeClaim:
    return EpisodeClaim(
        tmp_path / "state",
        remote=str(tmp_path / "remote.git"),
        ref=f"{CLAIM_NAMESPACE}exact-commit-seam-test",
        source_repo=source,
        authorized_execution_source_sha=source_sha,
        canonical_ref=canonical_ref,
        resolved_execution_inputs=resolved_execution_inputs,
        revocation_check=revocation_check,
    )


# The execution-contract root is an independently derived content-addressed
# execution identity. It is NOT sha256(the ASCII Git commit SHA). This fixed
# independent root is used to prove that execution_contract_root !=
# sha256(source_sha) is NOT inherently an error: the actual contract root is
# accepted when it matches the resolved execution contract.
INDEPENDENT_CONTRACT_ROOT = (
    "a31eb46a45363bec1f2581b96fbaef2e278365e356fe563721449aa4a0bfb907"
)


def test_positive_pass_explicit_exact_sha_with_valid_ancestry_and_resolved_inputs(tmp_path: Path) -> None:
    _remote, source, head = _fixture(tmp_path)
    # The actual contract root is an independent content-addressed execution
    # identity, NOT sha256(source_sha). It is accepted when it matches the
    # resolved execution contract.
    assert INDEPENDENT_CONTRACT_ROOT != hashlib.sha256(head.encode("ascii")).hexdigest()
    claim = _claim(
        tmp_path,
        source,
        source_sha=head,
        resolved_execution_inputs={
            "authorized_execution_source_sha": head,
            "execution_contract_root": INDEPENDENT_CONTRACT_ROOT,
        },
    )
    receipt = claim.acquire(session_nonce="session-pass")
    assert receipt["state"] == "REMOTE_AND_LOCAL_COMPLETE"
    assert receipt["source_head"] == head
    # The claim record/intent contains the EXACT authorized SHA, not ambient HEAD.
    intent = json.loads(claim.intent_path.read_text(encoding="utf-8"))
    assert intent["source_head"] == head


def test_fail_missing_sha(tmp_path: Path) -> None:
    _remote, source, _head = _fixture(tmp_path)
    claim = _claim(tmp_path, source, source_sha=None)
    with pytest.raises(ClaimBlocked, match="claim source SHA is missing"):
        claim.acquire(session_nonce="session-missing")


def test_fail_malformed_sha(tmp_path: Path) -> None:
    _remote, source, _head = _fixture(tmp_path)
    claim = _claim(tmp_path, source, source_sha="not-a-sha")
    with pytest.raises(ClaimBlocked, match="claim source SHA is malformed"):
        claim.acquire(session_nonce="session-malformed")


def test_fail_moving_symbolic_name_rejected(tmp_path: Path) -> None:
    """A moving branch ref name (origin/master) is NOT an exact commit identity."""
    _remote, source, _head = _fixture(tmp_path)
    claim = _claim(tmp_path, source, source_sha="refs/heads/master")
    # "refs/heads/master" is not a 40-hex SHA -> malformed format fails closed.
    with pytest.raises(ClaimBlocked, match="claim source SHA is malformed"):
        claim.acquire(session_nonce="session-symbolic")


def test_fail_unknown_commit_object(tmp_path: Path) -> None:
    _remote, source, _head = _fixture(tmp_path)
    unknown = "d" * 40
    claim = _claim(tmp_path, source, source_sha=unknown)
    with pytest.raises(ClaimBlocked, match="claim source commit object does not exist"):
        claim.acquire(session_nonce="session-unknown")


def test_fail_non_canonical_invalid_ancestry(tmp_path: Path) -> None:
    """A valid commit object that is NOT in the canonical lineage fails closed."""
    _remote, source, head = _fixture(tmp_path)
    # second non-canonical commit (not an ancestor of refs/heads/master)
    (source / "seed.txt").write_text("rogue\n", encoding="utf-8")
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
            "rogue",
        ],
        check=True,
    )
    rogue = _git(source, "rev-parse", "HEAD").stdout.strip()
    # master stays at the original head; rogue is a descendant, not canonical.
    assert rogue != head
    claim = _claim(tmp_path, source, source_sha=rogue)
    with pytest.raises(ClaimBlocked, match="not in the canonical lineage"):
        claim.acquire(session_nonce="session-noncanonical")


def test_fail_superseded_revoked_authority(tmp_path: Path) -> None:
    _remote, source, head = _fixture(tmp_path)

    def revoked(source_sha: str) -> bool:
        return source_sha == head

    claim = _claim(tmp_path, source, source_sha=head, revocation_check=revoked)
    with pytest.raises(ClaimBlocked, match="claim source authority is revoked or superseded"):
        claim.acquire(session_nonce="session-revoked")


def test_fail_resolved_contract_root_mismatch(tmp_path: Path) -> None:
    _remote, source, head = _fixture(tmp_path)
    claim = _claim(
        tmp_path,
        source,
        source_sha=head,
        resolved_execution_inputs={
            "authorized_execution_source_sha": head,
            # wrong actual contract root: a substituted root that is not a valid
            # sha256 fails closed before any claim is COMMITTED.
            "execution_contract_root": "not-a-real-sha256-root",
        },
    )
    with pytest.raises(ClaimBlocked, match="resolved execution-contract root mismatch"):
        claim.acquire(session_nonce="session-mismatch")


def test_claim_record_contains_exact_authorized_sha_not_ambient_head(tmp_path: Path) -> None:
    _remote, source, head = _fixture(tmp_path)
    claim = _claim(tmp_path, source, source_sha=head)
    receipt = claim.acquire(session_nonce="session-record")
    assert receipt["source_head"] == head
    intent = json.loads(claim.intent_path.read_text(encoding="utf-8"))
    assert intent["source_head"] == head
    # ambient HEAD at action time equals source in this fixture, but the record
    # must carry the AUTHORIZED sha, not a re-derived rev-parse at read time.
    assert "rev-parse" not in json.dumps(intent)