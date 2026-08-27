"""Dedicated canonical JH01 V1 operational checkout synchronization (H-02).

The production caller must never run against a human development checkout.
This module owns the minimum deterministic synchronization policy for the
dedicated non-development Git worktree:

1. ``git fetch origin`` (fail closed on failure);
2. the operational worktree must be clean (fail closed when dirty);
3. operational HEAD is synchronized to EXACTLY ``origin/master`` using
   fast-forward-only semantics: detached-HEAD checkout of the resolved
   ``origin/master`` commit.  If the current HEAD is not an ancestor of
   ``origin/master`` (diverged), the sync FAILS CLOSED before any market
   data acquisition or publication.  No force reset, no arbitrary branch
   execution, and the human development checkout is never touched.
4. BEFORE any network effects (acquisition/publication), the frozen recorder
   and wrapper file digests in the operational checkout are verified against
   the exact frozen identities; any mismatch raises ``STOP_SOURCE_CONFLICT``.

This module owns no recorder logic and no science.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
from typing import Sequence

FROZEN_RECORDER_SHA256 = "4f5e1791be9f17c1871f9b510329a1632412e028d2a84223fa59e83bbe95ec1a"
FROZEN_WRAPPER_SHA256 = "1176037ff0d3102afc67670202154970e4af1491cff1cd19bc9526c9c9d67c41"

FROZEN_RECORDER_RELPATH = "qntylab/jh01_v1_prospective_recorder_implementation_v0.py"
FROZEN_WRAPPER_RELPATH = "qntylab/jh01_v1_prospective_operation_v0.py"

DEFAULT_OPERATIONAL_ROOT = Path("/home/swirky/DevHub/repos/QntyLab-jh01-operational")


class OperationalCheckoutBlocked(RuntimeError):
    """The dedicated operational checkout failed its synchronization gate."""


def _run_git(root: Path, args: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise OperationalCheckoutBlocked(
            f"git {' '.join(args)} failed in operational checkout: {result.stderr.strip()}"
        )
    return result.stdout


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def verify_frozen_identities(root: Path) -> dict[str, str]:
    """Digest gate: frozen recorder and wrapper must match exactly.

    Runs BEFORE any network effects (acquisition/publication).  Any mismatch
    is a source conflict and fails closed.
    """
    observed: dict[str, str] = {}
    for relpath, expected in (
        (FROZEN_RECORDER_RELPATH, FROZEN_RECORDER_SHA256),
        (FROZEN_WRAPPER_RELPATH, FROZEN_WRAPPER_SHA256),
    ):
        path = root / relpath
        if not path.is_file():
            raise OperationalCheckoutBlocked(f"STOP_SOURCE_CONFLICT: frozen source missing: {relpath}")
        observed_digest = _file_sha256(path)
        observed[relpath] = observed_digest
        if observed_digest != expected:
            raise OperationalCheckoutBlocked(
                f"STOP_SOURCE_CONFLICT: frozen source identity mismatch for {relpath}: "
                f"expected {expected}, observed {observed_digest}"
            )
    return observed


def sync_operational_checkout(root: Path) -> str:
    """Synchronize the dedicated operational worktree to exactly origin/master.

    Returns the resolved full SHA of ``origin/master``.  Fails closed on any
    fetch failure, dirty tracked worktree, diverged HEAD, or frozen source
    identity mismatch.  Never touches any other checkout.
    """
    _run_git(root, ("fetch", "origin"))
    remote_master = _run_git(root, ("rev-parse", "origin/master")).strip()
    head = _run_git(root, ("rev-parse", "HEAD")).strip()
    porcelain = _run_git(root, ("status", "--porcelain"))
    dirty_tracked = [line for line in porcelain.splitlines() if line.strip() and not line.startswith("?? ")]
    if dirty_tracked:
        raise OperationalCheckoutBlocked(
            "operational checkout rejected: tracked worktree is dirty"
        )
    if head != remote_master:
        ancestor = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", head, remote_master],
            capture_output=True, text=True, check=False,
        )
        if ancestor.returncode != 0:
            raise OperationalCheckoutBlocked(
                "operational checkout rejected: HEAD has diverged from origin/master; "
                "refusing to synchronize (fast-forward-only policy)"
            )
        checkout = subprocess.run(
            ["git", "-C", str(root), "checkout", "--detach", remote_master],
            capture_output=True, text=True, check=False,
        )
        if checkout.returncode:
            raise OperationalCheckoutBlocked(
                f"operational checkout detach to origin/master failed: {checkout.stderr.strip()}"
            )
    verify_frozen_identities(root)
    return remote_master


__all__ = [
    "DEFAULT_OPERATIONAL_ROOT",
    "FROZEN_RECORDER_RELPATH",
    "FROZEN_RECORDER_SHA256",
    "FROZEN_WRAPPER_RELPATH",
    "FROZEN_WRAPPER_SHA256",
    "OperationalCheckoutBlocked",
    "sync_operational_checkout",
    "verify_frozen_identities",
]
