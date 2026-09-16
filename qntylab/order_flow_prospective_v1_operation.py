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
import time
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
CANONICAL_STATE_DIR = Path("/home/swirky/.local/state/qntylab/order_flow_prospective_v1")
MACHINE_ID_PATH = Path("/etc/machine-id")
HOST_BINDING_CONTEXT = "QNTYLAB_ORDER_FLOW_V1_HOST_V1"
TRUSTED_HOST_BINDING_DIGEST = "0902027d8e7eb13bf130934d46a48b61cd6b126fef13f371844f4d5de9e39f5e"
EVIDENCE_RELEASE_SCHEMA = "ORDER_FLOW_V1_EVIDENCE_RELEASE_V1"
LEDGER_FILENAME = recorder.LEDGER_FILENAME
RELEASE_CONVERGENCE_ATTEMPTS = 6
RELEASE_CONVERGENCE_DELAY_SECONDS = 1.0

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
    return CANONICAL_STATE_DIR


def _validate_recording_state_dir(state_dir: Path) -> Path:
    resolved = state_dir.expanduser().resolve()
    if resolved != CANONICAL_STATE_DIR.resolve():
        raise OperationBlocked("canonical recording state directory mismatch")
    return resolved


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
    if runtime.get("state_dir") != str(CANONICAL_STATE_DIR):
        raise OperationBlocked("runtime canonical state directory changed")
    host_identity = runtime.get("trusted_host_identity")
    if not isinstance(host_identity, dict):
        raise OperationBlocked("trusted host identity contract is malformed")
    if host_identity.get("method") != "SHA256_CONTEXTUALIZED_SHA256_ETC_MACHINE_ID":
        raise OperationBlocked("trusted host identity method changed")
    if host_identity.get("context") != HOST_BINDING_CONTEXT:
        raise OperationBlocked("trusted host identity context changed")
    if host_identity.get("digest") != TRUSTED_HOST_BINDING_DIGEST:
        raise OperationBlocked("trusted host identity digest changed")
    if host_identity.get("probe_host_binding_required") is not True:
        raise OperationBlocked("trusted host binding requirement changed")
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


def _trusted_host_fingerprint(path: Path = MACHINE_ID_PATH) -> str:
    try:
        machine_digest = sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise OperationBlocked("trusted host machine-id is unavailable") from exc
    return sha256(f"{HOST_BINDING_CONTEXT}:{machine_digest}".encode("utf-8")).hexdigest()


def validate_trusted_host(root: Path, machine_id_path: Path = MACHINE_ID_PATH) -> dict[str, str]:
    runtime = _json(root / RUNTIME_PATH)
    host_identity = runtime.get("trusted_host_identity")
    expected = host_identity.get("digest") if isinstance(host_identity, dict) else None
    actual = _trusted_host_fingerprint(machine_id_path)
    if expected != TRUSTED_HOST_BINDING_DIGEST or actual != expected:
        raise OperationBlocked("executing host does not match the qualified trusted host")
    return {
        "method": "SHA256_CONTEXTUALIZED_SHA256_ETC_MACHINE_ID",
        "context": HOST_BINDING_CONTEXT,
        "digest": actual,
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
    validate_trusted_host(root)
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
    result = _run(("gh", "api", "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28", f"repos/{REPOSITORY}/releases/tags/{tag}"), check=False)
    if result.returncode:
        detail = f"{result.stdout}\n{result.stderr}"
        if "HTTP 404" in detail or "Not Found" in detail:
            matches = [
                release
                for release in _list_evidence_releases()
                if release.get("tag_name") == tag
            ]
            if len(matches) > 1:
                raise OperationBlocked("multiple evidence releases exist for one tag")
            return matches[0] if matches else None
        raise OperationBlocked(f"GitHub release lookup failed: {detail.strip()}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OperationBlocked("GitHub release lookup returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise OperationBlocked("GitHub release lookup returned non-object JSON")
    return value


def _wait_for_release_state(
    tag: str,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    attempts: int = RELEASE_CONVERGENCE_ATTEMPTS,
    delay_seconds: float = RELEASE_CONVERGENCE_DELAY_SECONDS,
) -> dict[str, Any]:
    """Wait briefly for a successful GitHub write to become readable."""
    if attempts < 1:
        raise OperationBlocked("GitHub release convergence requires a positive attempt budget")
    for attempt in range(attempts):
        release = _release_snapshot(tag)
        if release is not None and release.get("tag_name") == tag and predicate(release):
            return release
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    raise OperationBlocked("GitHub release state did not converge after successful write")


def _release_metadata(release: dict[str, Any]) -> dict[str, Any]:
    try:
        metadata = json.loads(release.get("body") or "")
    except json.JSONDecodeError as exc:
        raise OperationBlocked("evidence release metadata is malformed") from exc
    if not isinstance(metadata, dict) or metadata.get("schema") != EVIDENCE_RELEASE_SCHEMA:
        raise OperationBlocked("evidence release metadata schema mismatch")
    count = metadata.get("event_count")
    if not isinstance(count, int) or count < 1:
        raise OperationBlocked("evidence release event count is malformed")
    for key in ("head_event_digest", "ledger_sha256"):
        value = metadata.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise OperationBlocked(f"evidence release metadata digest is malformed: {key}")
    previous = metadata.get("previous_release_tag")
    if previous is not None and (not isinstance(previous, str) or not previous.startswith(RELEASE_PREFIX)):
        raise OperationBlocked("evidence release previous tag is malformed")
    return metadata


def _release_assets(release: dict[str, Any]) -> list[dict[str, Any]]:
    return [asset for asset in release.get("assets", []) if isinstance(asset, dict) and asset.get("name") == LEDGER_FILENAME]


def _ledger_tag(events: Sequence[dict[str, Any]]) -> str:
    if not events:
        raise OperationBlocked("cannot tag an empty evidence ledger")
    digest = events[-1].get("event_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise OperationBlocked("ledger last event digest is malformed")
    return f"{RELEASE_PREFIX}{len(events):06d}-{digest[:24]}"


def _ledger_release_metadata(ledger: recorder.EvidenceLedger, *, previous_release_tag: str | None) -> dict[str, Any]:
    events = ledger.events()
    if not events or not ledger.path.is_file():
        raise OperationBlocked("cannot describe an empty evidence ledger")
    return {"schema": EVIDENCE_RELEASE_SCHEMA, "event_count": len(events), "head_event_digest": events[-1]["event_digest"], "ledger_sha256": sha256(ledger.path.read_bytes()).hexdigest(), "previous_release_tag": previous_release_tag, "scientific_evaluation": "FORBIDDEN"}


def _list_evidence_releases() -> list[dict[str, Any]]:
    result = _run(("gh", "api", "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28", f"repos/{REPOSITORY}/releases?per_page=100"))
    try:
        releases = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OperationBlocked("GitHub release listing returned malformed JSON") from exc
    if not isinstance(releases, list):
        raise OperationBlocked("GitHub release listing returned non-list JSON")
    return [release for release in releases if isinstance(release, dict) and isinstance(release.get("tag_name"), str) and release["tag_name"].startswith(RELEASE_PREFIX)]


def _evidence_release_state() -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    for release in _list_evidence_releases():
        metadata = _release_metadata(release)
        expected_tag = f"{RELEASE_PREFIX}{metadata['event_count']:06d}-{metadata['head_event_digest'][:24]}"
        if release.get("tag_name") != expected_tag:
            raise OperationBlocked("evidence release tag/metadata mismatch")
        assets = _release_assets(release)
        if len(assets) > 1:
            raise OperationBlocked("evidence release asset cardinality mismatch")
        if assets and assets[0].get("digest") != f"sha256:{metadata['ledger_sha256']}":
            raise OperationBlocked("evidence release asset/metadata digest mismatch")
        if release.get("draft") is False:
            if release.get("immutable") is not True or len(assets) != 1:
                raise OperationBlocked("published evidence release is not immutable and complete")
        elif release.get("draft") is not True:
            raise OperationBlocked("evidence release draft state is malformed")
        parsed.append({**release, "_evidence_meta": metadata})
    published = [item for item in parsed if item.get("draft") is False]
    drafts = [item for item in parsed if item.get("draft") is True]
    if len(drafts) > 1:
        raise OperationBlocked("more than one evidence release draft exists")
    counts = [item["_evidence_meta"]["event_count"] for item in published]
    if len(set(counts)) != len(counts):
        raise OperationBlocked("competing published evidence releases exist at one event count")
    published_head = max(published, key=lambda item: item["_evidence_meta"]["event_count"], default=None)
    draft_head = drafts[0] if drafts else None
    if published_head is not None:
        meta = published_head["_evidence_meta"]
        if meta["event_count"] == 1:
            if meta["previous_release_tag"] is not None:
                raise OperationBlocked("first evidence release unexpectedly names a predecessor")
        else:
            previous = _release_snapshot(meta["previous_release_tag"])
            if previous is None or previous.get("draft") is not False:
                raise OperationBlocked("evidence release predecessor is unavailable")
            previous_meta = _release_metadata(previous)
            if previous_meta["event_count"] != meta["event_count"] - 1:
                raise OperationBlocked("evidence release predecessor count mismatch")
    if draft_head is not None:
        dmeta = draft_head["_evidence_meta"]
        if published_head is None:
            if dmeta["event_count"] != 1 or dmeta["previous_release_tag"] is not None:
                raise OperationBlocked("first evidence draft has invalid predecessor state")
        else:
            pmeta = published_head["_evidence_meta"]
            if dmeta["event_count"] != pmeta["event_count"] + 1 or dmeta["previous_release_tag"] != published_head["tag_name"]:
                raise OperationBlocked("evidence draft does not extend the published head")
    return {"published_head": published_head, "draft_head": draft_head}


def _download_release_bytes(tag: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="qntylab-orderflow-download-") as directory:
        _run(("gh", "release", "download", tag, "--repo", REPOSITORY, "--pattern", LEDGER_FILENAME, "--dir", directory))
        restored = Path(directory) / LEDGER_FILENAME
        if not restored.is_file():
            raise OperationBlocked("downloaded evidence release ledger is missing")
        return restored.read_bytes()


def _events_from_ledger_bytes(payload: bytes) -> tuple[dict[str, Any], ...]:
    with tempfile.TemporaryDirectory(prefix="qntylab-orderflow-validate-") as directory:
        path = Path(directory) / LEDGER_FILENAME
        path.write_bytes(payload)
        return recorder.EvidenceLedger(Path(directory)).events()


def _replace_ledger_bytes(ledger: recorder.EvidenceLedger, payload: bytes) -> None:
    with ledger._exclusive_lock():
        temp = ledger.state_dir / f".{LEDGER_FILENAME}.restore"
        try:
            with temp.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, ledger.path)
        finally:
            if temp.exists():
                temp.unlink()
    ledger.events()


def _verify_release(release: dict[str, Any], ledger: recorder.EvidenceLedger) -> dict[str, Any]:
    metadata = _release_metadata(release)
    if release.get("draft") is not False or release.get("immutable") is not True:
        raise OperationBlocked("evidence release is not published immutable")
    events = ledger.events()
    ledger_sha = sha256(ledger.path.read_bytes()).hexdigest()
    if metadata["event_count"] != len(events) or metadata["head_event_digest"] != events[-1]["event_digest"] or metadata["ledger_sha256"] != ledger_sha:
        raise OperationBlocked("immutable evidence release metadata differs from local ledger")
    assets = _release_assets(release)
    if len(assets) != 1 or assets[0].get("digest") != f"sha256:{ledger_sha}":
        raise OperationBlocked("immutable evidence release asset digest mismatch")
    if _download_release_bytes(release["tag_name"]) != ledger.path.read_bytes():
        raise OperationBlocked("independent immutable evidence restore differs from local ledger")
    return {"tag": release["tag_name"], "ledger_sha256": ledger_sha, "immutable": True, "independent_restore": "PASS"}


def reconcile_canonical_ledger(ledger: recorder.EvidenceLedger) -> dict[str, Any]:
    state = _evidence_release_state()
    published = state["published_head"]
    draft = state["draft_head"]
    local = ledger.events()
    if published is None:
        if len(local) > 1:
            raise OperationBlocked("multiple local events exist without a published remote head")
        if draft is not None and (not local or _ledger_tag(local) != draft["tag_name"]):
            raise OperationBlocked("unrecoverable first evidence draft conflicts with local state")
        return {"state": "NO_REMOTE_HEAD" if draft is None else "LOCAL_MATCHES_FIRST_DRAFT"}
    payload = _download_release_bytes(published["tag_name"])
    meta = published["_evidence_meta"]
    remote = _events_from_ledger_bytes(payload)
    if sha256(payload).hexdigest() != meta["ledger_sha256"] or len(remote) != meta["event_count"] or remote[-1]["event_digest"] != meta["head_event_digest"]:
        raise OperationBlocked("remote evidence ledger does not match release metadata")
    if not local:
        if draft is not None:
            raise OperationBlocked("remote draft exists but local recovery state is absent")
        _replace_ledger_bytes(ledger, payload)
        return {"state": "RESTORED_REMOTE_HEAD", "tag": published["tag_name"]}
    if tuple(local) == tuple(remote):
        if draft is not None:
            raise OperationBlocked("remote draft exists beyond the matching local published head")
        return {"state": "LOCAL_MATCHES_REMOTE_HEAD", "tag": published["tag_name"]}
    if len(local) < len(remote):
        if tuple(local) != tuple(remote[:len(local)]) or draft is not None:
            raise OperationBlocked("local evidence ledger diverges from immutable remote history")
        _replace_ledger_bytes(ledger, payload)
        return {"state": "RESTORED_NEWER_REMOTE_HEAD", "tag": published["tag_name"]}
    if len(local) == len(remote) + 1 and tuple(remote) == tuple(local[:-1]) and local[-1]["previous_event_digest"] == remote[-1]["event_digest"]:
        if draft is not None and _ledger_tag(local) != draft["tag_name"]:
            raise OperationBlocked("remote draft conflicts with the local unanchored suffix")
        return {"state": "LOCAL_HAS_ONE_UNANCHORED_EXTENSION"}
    raise OperationBlocked("local evidence ledger is more than one event ahead of or diverges from immutable remote history")


def ensure_immutable_anchor(ledger: recorder.EvidenceLedger, target_commit: str) -> dict[str, Any]:
    events = ledger.events()
    if not events or not ledger.path.is_file():
        return {"state": "NO_LEDGER"}
    tag = _ledger_tag(events)
    state = _evidence_release_state()
    published = state["published_head"]
    draft = state["draft_head"]
    if published is None:
        if len(events) != 1:
            raise OperationBlocked("first evidence release must contain exactly one event")
        previous_tag = None
    else:
        pmeta = published["_evidence_meta"]
        if pmeta["event_count"] == len(events):
            if published["tag_name"] != tag:
                raise OperationBlocked("local ledger conflicts with published evidence at this event count")
            return _verify_release(published, ledger)
        if pmeta["event_count"] != len(events) - 1 or events[-1]["previous_event_digest"] != pmeta["head_event_digest"]:
            raise OperationBlocked("local ledger is not the single next event after published evidence")
        previous_tag = published["tag_name"]
    metadata = _ledger_release_metadata(ledger, previous_release_tag=previous_tag)
    release = _release_snapshot(tag)
    if draft is not None:
        if draft["tag_name"] != tag:
            raise OperationBlocked("a competing evidence draft already exists")
        release = draft
    if release is None:
        _run(("gh", "release", "create", tag, "--repo", REPOSITORY, "--target", target_commit, "--title", tag, "--notes", json.dumps(metadata, sort_keys=True, separators=(",", ":")), "--prerelease", "--draft"))
        release = _wait_for_release_state(
            tag,
            lambda candidate: candidate.get("draft") is True
            and _release_metadata(candidate) == metadata,
        )
    if release is None or release.get("draft") is not True or _release_metadata(release) != metadata:
        raise OperationBlocked("draft evidence release is unavailable or mismatched")
    assets = _release_assets(release)
    if len(assets) == 0:
        _run(("gh", "release", "upload", tag, f"{ledger.path}#{LEDGER_FILENAME}", "--repo", REPOSITORY))
        release = _wait_for_release_state(
            tag,
            lambda candidate: candidate.get("draft") is True
            and _release_metadata(candidate) == metadata
            and len(_release_assets(candidate)) == 1
            and _release_assets(candidate)[0].get("digest")
            == f"sha256:{metadata['ledger_sha256']}",
        )
        assets = _release_assets(release)
    if len(assets) != 1 or assets[0].get("digest") != f"sha256:{metadata['ledger_sha256']}":
        raise OperationBlocked("draft evidence asset digest mismatch")
    _run(("gh", "release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--prerelease"))
    release = _wait_for_release_state(
        tag,
        lambda candidate: candidate.get("draft") is False
        and candidate.get("immutable") is True
        and _release_metadata(candidate) == metadata
        and len(_release_assets(candidate)) == 1
        and _release_assets(candidate)[0].get("digest")
        == f"sha256:{metadata['ledger_sha256']}",
    )
    return _verify_release(release, ledger)

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
    if canonical_check:
        state_dir = _validate_recording_state_dir(state_dir)
        target_commit = canonical_preflight(root)
    else:
        if fetcher is None:
            raise OperationBlocked("noncanonical recording requires an injected synthetic fetcher")
        target_commit = _git(root, "rev-parse", "HEAD")
    validate_activation_artifacts(root)

    if sys.version_info[:2] != (3, 12):
        raise OperationBlocked("activated runtime requires Python 3.12")

    ledger = recorder.EvidenceLedger(state_dir)
    if canonical_check:
        reconcile_canonical_ledger(ledger)
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
    state_dir = _validate_recording_state_dir(state_dir)
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
