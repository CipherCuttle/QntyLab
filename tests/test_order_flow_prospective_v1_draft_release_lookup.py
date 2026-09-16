from __future__ import annotations

from types import SimpleNamespace
import json
from pathlib import Path

import pytest

from qntylab import order_flow_prospective_v1_operation as operation


def _anchor_fixture(tmp_path: Path) -> tuple[object, str, dict]:
    ledger = operation.recorder.EvidenceLedger(tmp_path)
    ledger.mark_missed(
        logical_close=operation.recorder.FIRST_WARMUP_CLOSE,
        detected_at="2026-09-15T02:00:00Z",
    )
    tag = operation._ledger_tag(ledger.events())
    metadata = operation._ledger_release_metadata(ledger, previous_release_tag=None)
    return ledger, tag, metadata


def _release(tag: str, metadata: dict, *, draft: bool, assets: list[dict] | None = None) -> dict:
    return {
        "tag_name": tag,
        "draft": draft,
        "immutable": not draft,
        "body": json.dumps(metadata, sort_keys=True, separators=(",", ":")),
        "assets": assets or [],
    }


def _patch_anchor_environment(monkeypatch, snapshots: list[dict | None], writes: list[tuple[str, ...]]) -> None:
    monkeypatch.setattr(operation, "_release_snapshot", lambda _tag: snapshots.pop(0))
    monkeypatch.setattr(operation.time, "sleep", lambda _seconds: None)

    def fake_run(args, **_kwargs):
        command = tuple(args)
        if len(command) >= 3 and command[0:2] == ("gh", "release"):
            writes.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(operation, "_run", fake_run)
    monkeypatch.setattr(operation, "_verify_release", lambda _release, _ledger: {"verified": True})


def test_release_snapshot_falls_back_to_matching_draft_listing(monkeypatch):
    tag = f"{operation.RELEASE_PREFIX}000001-0123456789abcdef01234567"
    draft = {
        "tag_name": tag,
        "draft": True,
        "immutable": False,
        "assets": [],
    }

    monkeypatch.setattr(
        operation,
        "_run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="HTTP 404: Not Found",
        ),
    )
    monkeypatch.setattr(operation, "_list_evidence_releases", lambda: [draft])

    assert operation._release_snapshot(tag) == draft


def test_release_snapshot_rejects_duplicate_matching_drafts(monkeypatch):
    tag = f"{operation.RELEASE_PREFIX}000001-0123456789abcdef01234567"
    draft = {
        "tag_name": tag,
        "draft": True,
        "immutable": False,
        "assets": [],
    }

    monkeypatch.setattr(
        operation,
        "_run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="HTTP 404: Not Found",
        ),
    )
    monkeypatch.setattr(
        operation,
        "_list_evidence_releases",
        lambda: [draft, dict(draft)],
    )

    with pytest.raises(operation.OperationBlocked, match="multiple evidence releases"):
        operation._release_snapshot(tag)


def test_anchor_waits_for_new_draft_after_create_without_repeating_create(tmp_path, monkeypatch):
    ledger, tag, metadata = _anchor_fixture(tmp_path)
    draft = _release(tag, metadata, draft=True)
    asset = {
        "name": operation.LEDGER_FILENAME,
        "digest": f"sha256:{metadata['ledger_sha256']}",
    }
    published = _release(tag, metadata, draft=False, assets=[asset])
    writes: list[tuple[str, ...]] = []
    _patch_anchor_environment(monkeypatch, [None, None, draft, _release(tag, metadata, draft=True, assets=[asset]), published], writes)
    monkeypatch.setattr(operation, "_evidence_release_state", lambda: {"published_head": None, "draft_head": None})

    assert operation.ensure_immutable_anchor(ledger, "a" * 40) == {"verified": True}
    assert sum(command[2] == "create" for command in writes) == 1
    assert sum(command[2] == "upload" for command in writes) == 1
    assert sum(command[2] == "edit" for command in writes) == 1


def test_anchor_fails_closed_after_bounded_create_read_exhaustion(tmp_path, monkeypatch):
    ledger, tag, _metadata = _anchor_fixture(tmp_path)
    writes: list[tuple[str, ...]] = []
    snapshots = [None] * (1 + operation.RELEASE_CONVERGENCE_ATTEMPTS)
    _patch_anchor_environment(monkeypatch, snapshots, writes)
    monkeypatch.setattr(operation, "_evidence_release_state", lambda: {"published_head": None, "draft_head": None})

    with pytest.raises(operation.OperationBlocked, match="did not converge"):
        operation.ensure_immutable_anchor(ledger, "b" * 40)
    assert len(snapshots) == 0
    assert sum(command[2] == "create" for command in writes) == 1
    assert not any(command[2] in {"upload", "edit"} for command in writes)


def test_anchor_waits_for_uploaded_asset_without_repeating_upload(tmp_path, monkeypatch):
    ledger, tag, metadata = _anchor_fixture(tmp_path)
    draft = _release(tag, metadata, draft=True)
    asset = {"name": operation.LEDGER_FILENAME, "digest": f"sha256:{metadata['ledger_sha256']}"}
    published = _release(tag, metadata, draft=False, assets=[asset])
    writes: list[tuple[str, ...]] = []
    _patch_anchor_environment(monkeypatch, [draft, draft, _release(tag, metadata, draft=True, assets=[asset]), published], writes)
    monkeypatch.setattr(operation, "_evidence_release_state", lambda: {"published_head": None, "draft_head": draft})

    assert operation.ensure_immutable_anchor(ledger, "c" * 40) == {"verified": True}
    assert sum(command[2] == "upload" for command in writes) == 1
    assert sum(command[2] == "edit" for command in writes) == 1


def test_anchor_waits_for_published_immutable_state_without_repeating_publish(tmp_path, monkeypatch):
    ledger, tag, metadata = _anchor_fixture(tmp_path)
    asset = {"name": operation.LEDGER_FILENAME, "digest": f"sha256:{metadata['ledger_sha256']}"}
    draft = _release(tag, metadata, draft=True, assets=[asset])
    published = _release(tag, metadata, draft=False, assets=[asset])
    writes: list[tuple[str, ...]] = []
    _patch_anchor_environment(monkeypatch, [draft, draft, published], writes)
    monkeypatch.setattr(operation, "_evidence_release_state", lambda: {"published_head": None, "draft_head": draft})

    assert operation.ensure_immutable_anchor(ledger, "d" * 40) == {"verified": True}
    assert sum(command[2] == "edit" for command in writes) == 1
