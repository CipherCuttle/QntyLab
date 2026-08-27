"""Production caller composing the frozen JH01 V1 campaign primitives.

This module owns no recorder logic, no second forecast implementation, and no
scientific metrics.  It is the smallest composition layer that:

- runs the canonical Git preflight and pins ``target_commit`` to the exact
  full SHA of ``origin/master`` when ``HEAD`` equals it and the tracked
  worktree is clean (Piece C);
- materializes and validates source bars for the exact due origin through the
  unbound source adapter;
- delegates publication to ``Operation.record_due`` with a qualified
  transport/runtime/verifier composition.

Only ``--record-due`` reaches real collection or publication.  Before
``2026-09-15T00:00:00Z`` it fails closed as ``NOT_DUE`` with a nonzero exit.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable, Sequence

from . import jh01_v1_prospective_operation_v0 as operation
from . import jh01_v1_prospective_recorder_implementation_v0 as recorder
from . import jh01_v1_prospective_source_adapter_v0 as adapter

REAL_STATE_DIRNAME = "jh01_v1_real_prospective_operation_v0"
LEDGER_FILENAME = "jh01_v1_operation_events.jsonl"
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

RunGit = Callable[[Sequence[str]], str]
TransportFactory = Callable[[], recorder.ReleaseTransport]


class CallerBlocked(RuntimeError):
    """The production caller preflight rejects the requested operation."""


def default_state_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    return base / "qntylab" / REAL_STATE_DIRNAME


def real_ledger_path(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / LEDGER_FILENAME


def make_run_git(root: Path) -> RunGit:
    def run_git(args: Sequence[str]) -> str:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
        if result.returncode:
            raise CallerBlocked(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout
    return run_git


def canonical_target_commit(run_git: RunGit) -> str:
    """Piece C: pin target_commit to the exact full SHA of origin/master.

    Requires ``git fetch origin`` first, then ``HEAD == origin/master`` and an
    empty tracked-worktree status.  Branch names, abbreviated SHAs, stale
    activation commits, caller-provided arbitrary SHAs, and preconfigured
    historical SHAs are all rejected: only this derived value is ever used.
    """
    run_git(("fetch", "origin"))
    remote_master = run_git(("rev-parse", "origin/master")).strip()
    head = run_git(("rev-parse", "HEAD")).strip()
    porcelain = run_git(("status", "--porcelain"))
    if not _FULL_SHA.fullmatch(remote_master) or not _FULL_SHA.fullmatch(head):
        raise CallerBlocked("canonical preflight requires full 40-hex commit identities")
    if head != remote_master:
        raise CallerBlocked("canonical preflight rejected: HEAD is not origin/master")
    dirty_tracked = [line for line in porcelain.splitlines() if line.strip() and not line.startswith("?? ")]
    if dirty_tracked:
        raise CallerBlocked("canonical preflight rejected: tracked worktree is dirty")
    return head


def first_required_close(root: Path) -> datetime:
    contract = recorder.frozen_contract(root)
    return operation._instant(contract["repair"]["repair"]["repaired_first_required_source_close"])


def _due(operation_obj: operation.Operation, *, now: datetime) -> tuple[operation.DueState, datetime | None]:
    return operation.due_state(operation_obj.ledger, now=now)


def status_summary(root: Path, state_dir: Path, *, now: datetime, run_git: RunGit | None = None) -> dict[str, Any]:
    """Read-only composition of the canonical Git preflight and campaign status."""
    operation_obj = operation.Operation(root, state_dir)
    summary: dict[str, Any] = {"campaign_status": operation_obj.status(now=now)}
    try:
        summary["git_preflight"] = {
            "target_commit": canonical_target_commit(run_git or make_run_git(root)),
            "state": "CANONICAL_PIN_OK",
        }
    except CallerBlocked as exc:
        summary["git_preflight"] = {"state": "BLOCKED", "reason": str(exc)}
    return summary


def dry_readiness(
    root: Path,
    state_dir: Path,
    *,
    now: datetime,
    run_git: RunGit | None = None,
    archive_provider: adapter.ArchiveProvider | None = None,
    fetch_klines: adapter.FetchKlines | None = None,
) -> dict[str, Any]:
    """Everything except real collection/publication: no record_due, no release."""
    target_commit = canonical_target_commit(run_git or make_run_git(root))
    operation_obj = operation.Operation(root, state_dir)
    campaign = operation_obj.status(now=now)
    state, origin = _due(operation_obj, now=now)
    report: dict[str, Any] = {"target_commit": target_commit, "campaign_status": campaign, "due_state": state.value}
    if state is not operation.DueState.DUE or origin is None:
        return {**report, "ready": False, "reason": f"due_state={state.value}"}
    required = first_required_close(root)
    bars = adapter.materialize_origin_bars(
        origin=origin,
        first_required_close=required,
        archive_provider=archive_provider,
        fetch_klines=fetch_klines,
    )
    manifest = recorder.source_manifest(bars, panel=adapter.frozen_panel(), origin=origin, first_required_close=required)
    return {
        **report,
        "ready": True,
        "origin_utc": operation._stamp(origin),
        "validated_bar_count": len(bars),
        "source_data_manifest_sha256": manifest["source_data_manifest_sha256"],
    }


def record_due(
    root: Path,
    state_dir: Path,
    *,
    now: datetime,
    run_git: RunGit | None = None,
    archive_provider: adapter.ArchiveProvider | None = None,
    fetch_klines: adapter.FetchKlines | None = None,
    transport_factory: TransportFactory | None = None,
    verifier: recorder.AttestationVerifier | None = None,
    offline_reverify: operation.OfflineReverify | None = None,
    go_binary: Path = Path("go"),
) -> dict[str, Any]:
    """Full production path; the only mode reaching real collection/publication."""
    target_commit = canonical_target_commit(run_git or make_run_git(root))
    operation_obj = operation.Operation(root, state_dir)
    state, origin = _due(operation_obj, now=now)
    if state is operation.DueState.NOT_DUE:
        next_origin = operation.required_origins()[len(operation_obj.ledger.origin_events())] if len(operation_obj.ledger.origin_events()) < len(operation.required_origins()) else None
        return {"origin_state": operation.DueState.NOT_DUE.value, "origin_utc": operation._stamp(next_origin) if next_origin else None}
    if state is not operation.DueState.DUE or origin is None:
        raise CallerBlocked(f"record-due refused in due state {state.value}")
    required = first_required_close(root)
    if archive_provider is None:
        # H1 repair: reuse digest-verified monthly archives across attempts so
        # a full materialization fits the one-hour DUE window budget.  The
        # cache lives inside this campaign's state dir and never reuses bytes
        # without checksum verification (see adapter.cached_archive_provider).
        archive_provider = adapter.cached_archive_provider(state_dir / "jh01_v1_source_archive_cache_v0")
    bars = adapter.materialize_origin_bars(
        origin=origin,
        first_required_close=required,
        archive_provider=archive_provider,
        fetch_klines=fetch_klines,
    )
    runtime = recorder.PublicationRuntime(
        (transport_factory or (lambda: recorder.GitHubReleaseTransport()))(),
        verifier if verifier is not None else _default_verifier(),
    )
    offline = offline_reverify or (lambda package: recorder.offline_reverify_v0r3_qualified_package(root, go_binary=go_binary))
    receipt = operation_obj.record_due(now=now, bars=bars, runtime=runtime, target_commit=target_commit, offline_reverify=offline)
    return {**receipt, "target_commit": target_commit}


def _default_verifier() -> recorder.AttestationVerifier:
    executable = os.environ.get("QNTYLAB_JH01_SIGSTORE_VERIFIER")
    if not executable:
        raise CallerBlocked("ATTESTATION_VERIFIER_REQUIRED: set QNTYLAB_JH01_SIGSTORE_VERIFIER or inject a verifier")
    return recorder.ExternalSigstoreVerifier(Path(executable))


def main(
    argv: Sequence[str] | None = None,
    *,
    run_git: RunGit | None = None,
    archive_provider: adapter.ArchiveProvider | None = None,
    fetch_klines: adapter.FetchKlines | None = None,
    transport_factory: TransportFactory | None = None,
    verifier: recorder.AttestationVerifier | None = None,
    offline_reverify: operation.OfflineReverify | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="JH01 V1 prospective production caller")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="read-only Git preflight plus campaign status")
    mode.add_argument("--dry-readiness", action="store_true", help="materialize+validate bars without record_due or releases")
    mode.add_argument("--record-due", action="store_true", help="full collection and authoritative publication path")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--state-dir", type=Path, default=None, help="defaults to the real campaign state dir binding")
    parser.add_argument("--now", required=True, help="UTC timestamp (hour-aligned)")
    parser.add_argument("--go-binary", type=Path, default=Path("go"))
    args = parser.parse_args(argv)
    state_dir = args.state_dir or default_state_dir()
    now = operation._instant(args.now)
    try:
        if args.status:
            print(json.dumps(status_summary(args.root, state_dir, now=now, run_git=run_git), sort_keys=True))
            return 0
        if args.dry_readiness:
            report = dry_readiness(
                args.root, state_dir, now=now, run_git=run_git,
                archive_provider=archive_provider, fetch_klines=fetch_klines,
            )
            print(json.dumps(report, sort_keys=True))
            return 0 if report["ready"] else 3
        receipt = record_due(
            args.root, state_dir, now=now, run_git=run_git,
            archive_provider=archive_provider, fetch_klines=fetch_klines,
            transport_factory=transport_factory, verifier=verifier,
            offline_reverify=offline_reverify, go_binary=args.go_binary,
        )
        print(json.dumps(receipt, sort_keys=True))
        if receipt.get("origin_state") == operation.DueState.NOT_DUE.value:
            return 3
        recovery = receipt.get("recovery")
        if receipt.get("origin_state") == operation.DueState.RECORDED.value and recovery != "IDEMPOTENT_AUTHORITATIVE_RECOVERY":
            return 0
        return 0 if recovery == "IDEMPOTENT_AUTHORITATIVE_RECOVERY" else 2
    except (CallerBlocked, operation.OperationBlocked, recorder.RecorderBlocked, adapter.SourceAdapterBlocked) as exc:
        print(json.dumps({"blocked": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised by shell integration
    sys.exit(main())
