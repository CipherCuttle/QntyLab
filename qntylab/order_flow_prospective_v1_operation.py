"""Activated local operation path for Order Flow Prospective V1.

This module is the only production composition path for the activated campaign.
It preserves the already-qualified recorder/source bytes, executes only on a
clean dedicated checkout pinned to canonical ``origin/master``, records the
earliest required prospective logical close, and anchors every changed
cumulative ledger to an immutable GitHub release before another source fetch.

It performs no scientific evaluation and grants no Router/Qnty/QntySpot,
trading, signing, submission, or capital authority.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Callable, Sequence

from . import order_flow_prospective_v1_recorder as recorder
from . import order_flow_prospective_v1_source as source
from . import project_context


PROBE_CANONICAL_MASTER_SHA = "1bd98b3769f27e9ded363058c316bd00e81cea0f"
SOURCE_GIT_BLOB_SHA = "1b5550ee2b8bbae3905e7f88583ec88217121274"
RECORDER_GIT_BLOB_SHA = "02daadaa597dcf00789af66c01fe13e66031ec3d"
PROJECT_ID = "QNTY_EDGE_ORDER_FLOW_PROSPECTIVE_V1_ACTIVATION"

ACTIVATION_PATH = Path(
    "experiments/research/qnty_edge_discovery_order_flow_v1/prospective_activation.json"
)
PROBE_RESULT_PATH = Path(
    "experiments/research/qnty_edge_discovery_order_flow_v1/source_live_probe_result.json"
)
RUNTIME_PATH = Path(
    "experiments/research/qnty_edge_discovery_order_flow_v1/prospective_runtime.json"
)
SOURCE_PATH = Path("qntylab/order_flow_prospective_v1_source.py")
RECORDER_PATH = Path("qntylab/order_flow_prospective_v1_recorder.py")
OPERATION_PATH = Path("qntylab/order_flow_prospective_v1_operation.py")
SERVICE_PATH = Path("ops/systemd/user/order-flow-v1-prospective-record.service")
TIMER_PATH = Path("ops/systemd/user/order-flow-v1-prospective-record.timer")

REPOSITORY = "CipherCuttle/QntyLab"
RELEASE_PREFIX = "order-flow-v1-evidence-"
STATE_DIRNAME = "order_flow_prospective_v1"
LEDGER_FILENAME = recorder.LEDGER_FILENAME

Anchorer = Callable[[recorder.EvidenceLedger, str], dict[str, Any]]
Fetcher = Callable[..., Sequence[Sequence[Any]]]


class OperationBlocked(RuntimeError):
    """The activated operation path failed closed."""


def _run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise OperationBlocked(f"command failed ({' '.join(args)}): {detail}")
    return result


def _git(root: Path, *args: str) -> str:
    return _run(("git", *args), cwd=root).stdout.strip()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OperationBlocked(f"malformed or missing activation artifact: {path}") from exc
    if not isinstance(value, dict):
        raise OperationBlocked(f"activation artifact must be an object: {path}")
    return value


def default_state_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    return base / "qntylab" / STATE_DIRNAME


def _assert_git_identity(root: Path, path: Path, expected_blob: str) -> None:
    actual = _git(root, "hash-object", str(path))
    if actual != expected_blob:
        raise OperationBlocked(f"qualified file Git blob drifted: {path}")
    frozen = _run(
        ("git", "show", f"{PROBE_CANONICAL_MASTER_SHA}:{path.as_posix()}"),
        cwd=root,
    ).stdout.encode("utf-8")
    current = (root / path).read_bytes()
    if frozen != current:
        raise OperationBlocked(f"qualified file bytes differ from live-probe canonical SHA: {path}")


def validate_activation_artifacts(root: Path) -> dict[str, Any]:
    """Validate the result-blind activation boundary without provider access."""
    probe = _json(root / PROBE_RESULT_PATH)
    activation = _json(root / ACTIVATION_PATH)
    runtime = _json(root / RUNTIME_PATH)

    expected_probe = {
        "state": "PASS",
        "mode": "NON_SCIENTIFIC_SOURCE_QUALIFICATION",
        "scientific_evidence": False,
        "probe_canonical_master_sha": PROBE_CANONICAL_MASTER_SHA,
        "probe_logical_close_utc": "2026-09-14T00:00:00Z",
        "worktree_mode": "CLEAN_DETACHED_WORKTREE",
        "head_verified_exact": True,
        "worktree_clean": True,
        "host_class": "TRUSTED_NON_US_OPERATOR_HOST",
        "symbol_count": 5,
        "symbols": list(recorder.PANEL),
        "payload_persisted": False,
        "price_volume_feature_values_persisted": False,
    }
    for key, expected in expected_probe.items():
        if probe.get(key) != expected:
            raise OperationBlocked(f"live probe receipt mismatch: {key}")

    expected_activation = {
        "state": "AUTHORIZED_IF_CANONICAL",
        "activation_scope": "PROSPECTIVE_COLLECTION_ONLY",
        "candidate_branch_is_authority": False,
        "activation_effective_on_branch": False,
        "canonicalization_required_before_effect": True,
        "activation_effective": "AFTER_EXACT_CANONICAL_MERGE_AND_MATCHING_LOCAL_UNIT_INSTALL_ONLY",
        "probe_canonical_master_sha": PROBE_CANONICAL_MASTER_SHA,
        "source_implementation_path": SOURCE_PATH.as_posix(),
        "source_git_blob_sha": SOURCE_GIT_BLOB_SHA,
        "recorder_implementation_path": RECORDER_PATH.as_posix(),
        "recorder_git_blob_sha": RECORDER_GIT_BLOB_SHA,
        "operational_host_class": "TRUSTED_NON_US_LOCAL_HOST",
        "first_warmup_logical_close_utc": recorder.FIRST_WARMUP_CLOSE,
        "last_warmup_logical_close_utc": recorder.LAST_WARMUP_CLOSE,
        "first_origin_utc": recorder.FIRST_ORIGIN,
        "last_origin_utc": recorder.LAST_ORIGIN,
        "terminal_tail_logical_close_utc": recorder.TERMINAL_TAIL_CLOSE,
        "backfill": "FORBIDDEN",
        "source_substitution": "FORBIDDEN",
        "persistence": "GITHUB_IMMUTABLE_RELEASE_HASH_CHAIN_V1",
    }
    for key, expected in expected_activation.items():
        if activation.get(key) != expected:
            raise OperationBlocked(f"activation contract mismatch: {key}")

    branch_authority = activation.get("branch_authority")
    if not isinstance(branch_authority, dict):
        raise OperationBlocked("branch activation authority is malformed")
    for key in (
        "real_market_data_access_authorized",
        "prospective_collection_authorized",
        "scheduler_authorized",
        "scientific_recording_authorized",
    ):
        if branch_authority.get(key) is not False:
            raise OperationBlocked(f"branch-local live authority opened: {key}")

    authority = activation.get("authority_after_canonicalization")
    if not isinstance(authority, dict):
        raise OperationBlocked("post-canonical activation authority is malformed")
    for key in (
        "real_market_data_access_authorized",
        "prospective_collection_authorized",
        "scheduler_authorized",
        "scientific_recording_authorized",
    ):
        if authority.get(key) is not True:
            raise OperationBlocked(f"required activation authority missing: {key}")
    for key in (
        "interim_scientific_evaluation_authorized",
        "terminal_evaluation_authorized",
        "router_authorized",
        "qnty_authorized",
        "qntyspot_authorized",
        "trading_authorized",
    ):
        if authority.get(key) is not False:
            raise OperationBlocked(f"forbidden downstream authority opened: {key}")
    if authority.get("capital_authority") != "NONE":
        raise OperationBlocked("capital authority must remain NONE")
    if authority.get("signing_authority") != "NONE":
        raise OperationBlocked("signing authority must remain NONE")
    if authority.get("submission_authority") != "NONE":
        raise OperationBlocked("submission authority must remain NONE")

    if runtime.get("source_access_host") != "LOCAL_TRUSTED_NON_US_HOST_ONLY":
        raise OperationBlocked("runtime source host boundary changed")
    if runtime.get("github_actions_real_provider_access") != "FORBIDDEN":
        raise OperationBlocked("GitHub Actions provider-access firewall changed")
    if runtime.get("persistence") != "GITHUB_IMMUTABLE_RELEASE_HASH_CHAIN_V1":
        raise OperationBlocked("runtime persistence contract changed")
    if runtime.get("release_repository") != REPOSITORY:
        raise OperationBlocked("runtime release repository changed")
    if runtime.get("release_prefix") != RELEASE_PREFIX:
        raise OperationBlocked("runtime release prefix changed")
    if runtime.get("release_asset") != LEDGER_FILENAME:
        raise OperationBlocked("runtime release asset changed")
    for key, path in (
        ("operation_git_blob_sha", OPERATION_PATH),
        ("service_git_blob_sha", SERVICE_PATH),
        ("timer_git_blob_sha", TIMER_PATH),
    ):
        expected_blob = runtime.get(key)
        if not isinstance(expected_blob, str) or _git(root, "hash-object", str(path)) != expected_blob:
            raise OperationBlocked(f"runtime Git blob identity mismatch: {key}")
    if runtime.get("interim_evaluation") != "FORBIDDEN":
        raise OperationBlocked("runtime interim evaluation boundary changed")

    try:
        _git(root, "merge-base", "--is-ancestor", PROBE_CANONICAL_MASTER_SHA, "HEAD")
    except OperationBlocked as exc:
        raise OperationBlocked("live-probe canonical SHA is not an ancestor of HEAD") from exc
    _assert_git_identity(root, SOURCE_PATH, SOURCE_GIT_BLOB_SHA)
    _assert_git_identity(root, RECORDER_PATH, RECORDER_GIT_BLOB_SHA)

    return {
        "state": "AUTHORIZED_IF_CANONICAL",
        "probe_canonical_master_sha": PROBE_CANONICAL_MASTER_SHA,
        "source_git_blob_sha": SOURCE_GIT_BLOB_SHA,
        "recorder_git_blob_sha": RECORDER_GIT_BLOB_SHA,
    }


def validate_project_authority(root: Path) -> dict[str, Any]:
    """Require canonical project-context authority for this bounded phase."""
    data = project_context.context_data(root)
    active = data.get("active_project")
    if not isinstance(active, dict) or active.get("project_id") != PROJECT_ID:
        raise OperationBlocked("canonical project context does not authorize Order Flow V1 activation")
    if active.get("state") != "ACTIVE" or active.get("implementation_authorized") is not True:
        raise OperationBlocked("Order Flow V1 project authority is not ACTIVE implementation authority")
    if active.get("implementation_completed") is not False:
        raise OperationBlocked("Order Flow V1 activation phase lifecycle is malformed")
    for key, expected in (
        ("candidate_branch_is_authority", False),
        ("activation_effective_on_branch", False),
        ("canonicalization_required_before_effect", True),
        ("real_market_data_access_authorized_on_branch", False),
        ("prospective_collection_authorized_on_branch", False),
        ("scheduler_authorized_on_branch", False),
        ("scientific_recording_authorized_on_branch", False),
        ("post_canonical_real_market_data_access_authorized", True),
        ("post_canonical_prospective_collection_authorized", True),
        ("post_canonical_scheduler_authorized", True),
        ("post_canonical_scientific_recording_authorized", True),
        ("interim_scientific_evaluation_authorized", False),
        ("terminal_evaluation_authorized", False),
        ("router_authorized", False),
        ("qnty_authorized", False),
        ("qntyspot_authorized", False),
    ):
        if active.get(key) is not expected:
            raise OperationBlocked(f"canonical project authority mismatch: {key}")
    for key in ("trading_authority", "capital_authority", "signing_authority", "submission_authority"):
        if active.get(key) != "NONE":
            raise OperationBlocked(f"forbidden downstream authority opened: {key}")
    if active.get("backfill") != "FORBIDDEN" or active.get("source_substitution") != "FORBIDDEN":
        raise OperationBlocked("canonical no-backfill/source-substitution boundary changed")
    return {
        "project_id": PROJECT_ID,
        "state": "ACTIVE",
        "implementation_authorized": True,
        "activation_effective_on_branch": False,
        "canonicalization_required_before_effect": True,
    }

def _validate_installed_units(root: Path) -> None:
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    for repo_path in (SERVICE_PATH, TIMER_PATH):
        installed = unit_dir / repo_path.name
        if not installed.is_file():
            raise OperationBlocked(f"activated systemd unit is not installed: {installed}")
        if installed.read_bytes() != (root / repo_path).read_bytes():
            raise OperationBlocked(f"installed systemd unit differs from canonical repo bytes: {installed}")


def canonical_preflight(root: Path) -> str:
    """Require the already-synchronized dedicated worktree to equal origin/master."""
    if _git(root, "status", "--porcelain"):
        raise OperationBlocked("operational worktree is not clean")
    _git(root, "fetch", "origin", "master")
    target = _git(root, "rev-parse", "origin/master")
    head = _git(root, "rev-parse", "HEAD")
    if len(target) != 40 or len(head) != 40:
        raise OperationBlocked("canonical Git identities must be full SHAs")
    if head != target:
        raise OperationBlocked(
            "operational checkout is stale; synchronize it before starting Python"
        )
    validate_activation_artifacts(root)
    validate_project_authority(root)
    _validate_installed_units(root)
    return head


def required_closes() -> tuple[datetime, ...]:
    first = recorder.hour(recorder.FIRST_WARMUP_CLOSE)
    last = recorder.hour(recorder.TERMINAL_TAIL_CLOSE)
    count = int((last - first).total_seconds() // 3600) + 1
    return tuple(first + timedelta(hours=index) for index in range(count))


def next_required_close(ledger: recorder.EvidenceLedger) -> datetime | None:
    closes = required_closes()
    events = tuple(
        event
        for event in ledger.events()
        if event.get("event_type") in {"OBSERVATION_STAGED", "WINDOW_MISSED"}
    )
    if len(events) > len(closes):
        raise OperationBlocked("ledger contains more terminal closes than the frozen grid")
    for index, event in enumerate(events):
        expected = recorder.stamp(closes[index])
        if event.get("payload", {}).get("logical_close_utc") != expected:
            raise OperationBlocked("ledger terminal closes are not the frozen ordered prefix")
    return None if len(events) == len(closes) else closes[len(events)]


def _release_snapshot(tag: str) -> dict[str, Any] | None:
    result = _run(
        (
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2022-11-28",
            f"repos/{REPOSITORY}/releases/tags/{tag}",
        ),
        check=False,
    )
    if result.returncode:
        text = f"{result.stdout}\n{result.stderr}"
        if "HTTP 404" in text or "Not Found" in text:
            return None
        raise OperationBlocked(f"GitHub release lookup failed: {text.strip()}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OperationBlocked("GitHub release lookup returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise OperationBlocked("GitHub release lookup returned non-object JSON")
    return value


def _verify_release(tag: str, ledger: recorder.EvidenceLedger, expected_sha256: str) -> dict[str, Any]:
    release = _release_snapshot(tag)
    if release is None:
        raise OperationBlocked("expected immutable release is missing")
    if release.get("draft") is not False or release.get("immutable") is not True:
        raise OperationBlocked("evidence release is not published immutable")
    assets = [
        asset
        for asset in release.get("assets", [])
        if isinstance(asset, dict) and asset.get("name") == LEDGER_FILENAME
    ]
    if len(assets) != 1:
        raise OperationBlocked("immutable evidence release asset cardinality mismatch")
    if assets[0].get("digest") != f"sha256:{expected_sha256}":
        raise OperationBlocked("immutable evidence release asset digest mismatch")

    with tempfile.TemporaryDirectory(prefix="qntylab-orderflow-restore-") as directory:
        _run(
            (
                "gh",
                "release",
                "download",
                tag,
                "--repo",
                REPOSITORY,
                "--pattern",
                LEDGER_FILENAME,
                "--dir",
                directory,
            )
        )
        restored = Path(directory) / LEDGER_FILENAME
        if not restored.is_file():
            raise OperationBlocked("independent immutable evidence restore is missing")
        if restored.read_bytes() != ledger.path.read_bytes():
            raise OperationBlocked("independent immutable evidence restore differs from local ledger")
    return {
        "tag": tag,
        "ledger_sha256": expected_sha256,
        "immutable": True,
        "independent_restore": "PASS",
    }


def ensure_immutable_anchor(ledger: recorder.EvidenceLedger, target_commit: str) -> dict[str, Any]:
    """Publish/resume/verify the current cumulative ledger as one immutable release."""
    events = ledger.events()
    if not events or not ledger.path.is_file():
        return {"state": "NO_LEDGER"}
    ledger_sha = sha256(ledger.path.read_bytes()).hexdigest()
    last_digest = events[-1].get("event_digest")
    if not isinstance(last_digest, str) or len(last_digest) != 64:
        raise OperationBlocked("ledger last event digest is malformed")
    tag = f"{RELEASE_PREFIX}{last_digest[:24]}"

    release = _release_snapshot(tag)
    if release is not None and release.get("immutable") is True:
        return _verify_release(tag, ledger, ledger_sha)
    if release is not None and release.get("draft") is not True:
        raise OperationBlocked("existing evidence release is neither resumable draft nor immutable")

    if release is None:
        _run(
            (
                "gh",
                "release",
                "create",
                tag,
                "--repo",
                REPOSITORY,
                "--target",
                target_commit,
                "--title",
                tag,
                "--notes",
                "Order Flow Prospective V1 cumulative scientific recording snapshot. "
                "No interim evaluation or downstream authority.",
                "--prerelease",
                "--draft",
            )
        )
        release = _release_snapshot(tag)
    if release is None or release.get("draft") is not True:
        raise OperationBlocked("draft evidence release is unavailable")

    assets = [
        asset
        for asset in release.get("assets", [])
        if isinstance(asset, dict) and asset.get("name") == LEDGER_FILENAME
    ]
    if len(assets) == 0:
        _run(
            (
                "gh",
                "release",
                "upload",
                tag,
                f"{ledger.path}#{LEDGER_FILENAME}",
                "--repo",
                REPOSITORY,
            )
        )
        release = _release_snapshot(tag)
        assets = [
            asset
            for asset in (release or {}).get("assets", [])
            if isinstance(asset, dict) and asset.get("name") == LEDGER_FILENAME
        ]
    if len(assets) != 1 or assets[0].get("digest") != f"sha256:{ledger_sha}":
        raise OperationBlocked("draft evidence asset digest mismatch")

    _run(
        (
            "gh",
            "release",
            "edit",
            tag,
            "--repo",
            REPOSITORY,
            "--draft=false",
            "--prerelease",
        )
    )
    return _verify_release(tag, ledger, ledger_sha)


def record_due(
    root: Path,
    state_dir: Path,
    *,
    now: datetime,
    fetcher: Fetcher | None = None,
    clock: Callable[[], datetime] | None = None,
    canonical_check: bool = True,
    anchorer: Anchorer = ensure_immutable_anchor,
) -> dict[str, Any]:
    """Record the frozen next close; overdue closes become gaps, never backfill."""
    now = recorder.parse_utc(now)
    target_commit = canonical_preflight(root) if canonical_check else _git(root, "rev-parse", "HEAD")
    validate_activation_artifacts(root)

    if sys.version_info[:2] != (3, 12):
        raise OperationBlocked("activated runtime requires Python 3.12")

    ledger = recorder.EvidenceLedger(state_dir)
    if ledger.events():
        anchorer(ledger, target_commit)

    missed = 0
    recorded_close: str | None = None

    while True:
        close = next_required_close(ledger)
        if close is None:
            return {
                "state": "COMPLETE",
                "target_commit": target_commit,
                "missed_marked_this_run": missed,
                "last_recorded_close_utc": recorded_close,
            }
        if now < close:
            return {
                "state": "NOT_DUE",
                "target_commit": target_commit,
                "next_logical_close_utc": recorder.stamp(close),
                "missed_marked_this_run": missed,
                "last_recorded_close_utc": recorded_close,
            }

        if now >= close + recorder.RECORDING_WINDOW:
            source.stage_due_hour(
                ledger,
                logical_close=close,
                observed_at=now,
                fetcher=fetcher,
                clock=clock,
            )
            missed += 1
            anchorer(ledger, target_commit)
            continue

        source.stage_due_hour(
            ledger,
            logical_close=close,
            observed_at=now,
            fetcher=fetcher,
            clock=clock,
        )
        recorded_close = recorder.stamp(close)
        break

    anchor = anchorer(ledger, target_commit)
    next_close = next_required_close(ledger)
    return {
        "state": "ANCHORED",
        "target_commit": target_commit,
        "logical_close_utc": recorded_close,
        "missed_marked_this_run": missed,
        "ledger_sha256": ledger.ledger_sha256(),
        "anchor": anchor,
        "next_logical_close_utc": recorder.stamp(next_close) if next_close is not None else None,
    }


def status(root: Path, state_dir: Path) -> dict[str, Any]:
    authority = validate_activation_artifacts(root)
    project_authority = validate_project_authority(root)
    ledger = recorder.EvidenceLedger(state_dir)
    next_close = next_required_close(ledger)
    return {
        **authority,
        "project_authority": project_authority,
        "ledger_event_count": len(ledger.events()),
        "ledger_sha256": ledger.ledger_sha256(),
        "next_logical_close_utc": recorder.stamp(next_close) if next_close is not None else None,
        "interim_evaluation": "FORBIDDEN",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Order Flow Prospective V1 activated local operation")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--record-due", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--now", default=None, help="UTC timestamp; defaults to current wall clock")
    args = parser.parse_args(argv)

    state_dir = args.state_dir or default_state_dir()
    now = recorder.parse_utc(args.now) if args.now else datetime.now(UTC)
    try:
        if args.status:
            print(json.dumps(status(args.root, state_dir), sort_keys=True))
            return 0
        result = record_due(args.root, state_dir, now=now)
        print(json.dumps(result, sort_keys=True))
        return 3 if result["state"] == "NOT_DUE" else 0
    except (OperationBlocked, source.SourceBlocked, recorder.RecorderBlocked) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
