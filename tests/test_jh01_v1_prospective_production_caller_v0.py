"""Unit tests for the JH01 V1 prospective production caller (Pieces B and C).

Synthetic fixtures only; no network; every campaign state directory is a
pytest ``tmp_path``.  The real state directory binding is never written to.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

import pytest

from qntylab import jh01_v1_prospective_operation_v0 as operation
from qntylab import jh01_v1_prospective_production_caller_v0 as caller
from qntylab import jh01_v1_prospective_recorder_implementation_v0 as recorder
from qntylab import jh01_v1_prospective_source_adapter_v0 as adapter

from tests._jh01_v1_prospective_fixtures import (
    FIRST_REQUIRED,
    ORIGIN,
    REQUIRED_CLOSE_COUNT,
    synthetic_archive_provider,
    synthetic_fetch_klines,
)


ROOT = Path(__file__).resolve().parents[1]
PINNED = "c" * 40


def fake_run_git(*, head: str = PINNED, remote: str = PINNED, porcelain: str = ""):
    def run_git(args):
        command = [str(part) for part in args]
        if command[0] == "fetch":
            return ""
        if command[:2] == ["rev-parse", "origin/master"]:
            return remote + "\n"
        if command[:2] == ["rev-parse", "HEAD"]:
            return head + "\n"
        if command[0] == "status":
            return porcelain
        raise AssertionError(f"unexpected git invocation: {command}")
    return run_git


class FakeTransport:
    def __init__(self, origin: datetime):
        self.origin = origin
        self.release: recorder.RemoteRelease | None = None
        self.create_calls = 0
        self.upload_calls = 0

    def find(self, origin_id: str):
        return () if self.release is None else (self.release,)

    def create(self, release: recorder.RemoteRelease):
        self.create_calls += 1
        self.release = recorder.RemoteRelease(release.origin_id, release.tag, release.artifact_digest, release.asset_name, None, None, target_commit=release.target_commit)
        return self.release

    def upload(self, tag: str, asset_name: str, content: bytes):
        self.upload_calls += 1
        assert self.release is not None
        self.release = recorder.RemoteRelease(self.release.origin_id, tag, self.release.artifact_digest, asset_name, sha256(content).hexdigest(), None, target_commit=self.release.target_commit)
        return self.release

    def publish(self, release: recorder.RemoteRelease):
        self.release = recorder.RemoteRelease(release.origin_id, release.tag, release.artifact_digest, release.asset_name, release.asset_sha256, self.origin + timedelta(minutes=10), target_commit=release.target_commit, immutable=True, repository_id="repo", owner_id="owner", release_id=7, purl=f"pkg:github/CipherCuttle/QntyLab@{release.tag}", package_id="repo")
        return self.release

    def acquire_attestation(self, release: recorder.RemoteRelease):
        return b"synthetic-bundle", b"synthetic-root\n"


class AmbiguousTransport(FakeTransport):
    def find(self, origin_id: str):
        assert self.release is not None
        return (self.release, self.release)


class FakeVerifier:
    def verify(self, *, asset: bytes, bundle: bytes, trusted_root: bytes, expectation: recorder.AttestationExpectation):
        assert bundle == b"synthetic-bundle"
        assert trusted_root == b"synthetic-root\n"
        return recorder.VerifiedAttestation(expectation, ORIGIN + timedelta(minutes=20), bundle, trusted_root)


def activate_real_campaign(tmp_path: Path) -> None:
    """Activate REAL_PROSPECTIVE from the canonical authority document in a
    temporary state directory; never touches the real campaign state."""
    operation.Operation(ROOT, tmp_path / "state").activate_real(activation_time=ORIGIN - timedelta(days=1))


def call_record_due(tmp_path: Path, *, now: datetime, transport=None, run_git=None, archive_provider=None, fetch_klines=None):
    return caller.record_due(
        ROOT,
        tmp_path / "state",
        now=now,
        run_git=run_git or fake_run_git(),
        archive_provider=archive_provider or synthetic_archive_provider(),
        fetch_klines=fetch_klines or synthetic_fetch_klines(),
        transport_factory=(lambda: transport) if transport is not None else None,
        verifier=FakeVerifier(),
        offline_reverify=lambda package: recorder.verify_retention_package(package),
    )


def test_target_commit_mismatch_rejected():
    with pytest.raises(caller.CallerBlocked, match="not origin/master"):
        caller.canonical_target_commit(fake_run_git(head="d" * 40))


def test_dirty_tracked_worktree_rejected_and_untracked_tolerated():
    with pytest.raises(caller.CallerBlocked, match="dirty"):
        caller.canonical_target_commit(fake_run_git(porcelain=" M qntylab/x.py\n"))
    assert caller.canonical_target_commit(fake_run_git(porcelain="?? notes/scratch.md\n")) == PINNED


def test_abbreviated_or_branchlike_identity_rejected():
    with pytest.raises(caller.CallerBlocked, match="40-hex"):
        caller.canonical_target_commit(fake_run_git(remote="c0ffee1234"))
    with pytest.raises(caller.CallerBlocked, match="40-hex"):
        caller.canonical_target_commit(fake_run_git(head="master"))


def test_record_due_before_first_origin_fails_closed_as_not_due_without_collection(tmp_path):
    activate_real_campaign(tmp_path)
    captured: list[dict] = []
    receipt = call_record_due(
        tmp_path,
        now=ORIGIN - timedelta(minutes=1),
        archive_provider=synthetic_archive_provider(),
        fetch_klines=synthetic_fetch_klines(capture=captured),
    )
    assert receipt == {"origin_state": "NOT_DUE", "origin_utc": "2026-09-15T00:00:00Z"}
    assert captured == []
    ledger = (tmp_path / "state" / "jh01_v1_operation_events.jsonl").read_text()
    assert "ORIGIN_RECORDED" not in ledger


def test_cli_record_due_before_origin_exits_nonzero(tmp_path, capsys):
    activate_real_campaign(tmp_path)
    rc = caller.main(
        ["--record-due", "--root", str(ROOT), "--state-dir", str(tmp_path / "state"), "--now", "2026-09-14T23:00:00Z"],
        run_git=fake_run_git(),
        archive_provider=synthetic_archive_provider(),
        fetch_klines=synthetic_fetch_klines(),
        verifier=FakeVerifier(),
        offline_reverify=lambda package: None,
    )
    assert rc == 3
    assert json.loads(capsys.readouterr().out)["origin_state"] == "NOT_DUE"


def test_due_synthetic_origin_completes_via_fake_transport_and_temp_state(tmp_path):
    activate_real_campaign(tmp_path)
    transport = FakeTransport(ORIGIN)
    receipt = call_record_due(tmp_path, now=ORIGIN + timedelta(minutes=1), transport=transport)
    assert receipt["origin_state"] == "RECORDED"
    assert receipt["publication_state"] == "ORIGIN_COMPLETE"
    assert receipt["target_commit"] == PINNED
    events = [json.loads(line) for line in (tmp_path / "state" / "jh01_v1_operation_events.jsonl").read_text().splitlines() if line.strip()]
    recorded = [event for event in events if event["event_type"] == "ORIGIN_RECORDED"]
    assert len(recorded) == 1
    retention_dirs = list((tmp_path / "state" / "retention").iterdir())
    assert len(retention_dirs) == 1
    assert (retention_dirs[0] / "forecast.json").is_file()


def test_duplicate_invocation_is_idempotent_with_no_second_origin(tmp_path):
    activate_real_campaign(tmp_path)
    transport = FakeTransport(ORIGIN)
    first = call_record_due(tmp_path, now=ORIGIN + timedelta(minutes=1), transport=transport)
    # Duplicate invocation on the same campaign day: the exact due origin has
    # already been recorded, so the caller must not collect or publish again.
    second = call_record_due(tmp_path, now=ORIGIN + timedelta(hours=1), transport=transport)
    third = call_record_due(tmp_path, now=ORIGIN + timedelta(minutes=30), transport=transport)
    assert first["origin_state"] == "RECORDED"
    assert second == {"origin_state": "NOT_DUE", "origin_utc": "2026-09-16T00:00:00Z"}
    assert third == {"origin_state": "NOT_DUE", "origin_utc": "2026-09-16T00:00:00Z"}
    assert transport.create_calls == 1
    assert transport.upload_calls == 1
    events = [json.loads(line) for line in (tmp_path / "state" / "jh01_v1_operation_events.jsonl").read_text().splitlines() if line.strip()]
    assert len([event for event in events if event["event_type"] == "ORIGIN_RECORDED"]) == 1


def test_unknown_remote_write_ambiguity_fails_closed_without_ledger_write(tmp_path):
    activate_real_campaign(tmp_path)
    # Simulate an unknown-outcome remote write: two matching releases exist.
    transport = AmbiguousTransport(ORIGIN)
    transport.release = recorder.RemoteRelease("origin", "tag", "", "forecast.json", None, None)
    with pytest.raises(recorder.RecorderBlocked, match="BLOCK_AMBIGUOUS_REMOTE"):
        call_record_due(tmp_path, now=ORIGIN + timedelta(minutes=1), transport=transport)
    events = (tmp_path / "state" / "jh01_v1_operation_events.jsonl").read_text()
    assert "ORIGIN_RECORDED" not in events


def test_cli_status_composes_preflight_and_campaign_status_read_only(tmp_path, capsys):
    activate_real_campaign(tmp_path)
    rc = caller.main(
        ["--status", "--root", str(ROOT), "--state-dir", str(tmp_path / "state"), "--now", "2026-09-14T12:00:00Z"],
        run_git=fake_run_git(),
    )
    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["git_preflight"]["target_commit"] == PINNED
    assert summary["campaign_status"]["campaign_state"] == "ARMED_BUT_INACTIVE"
    assert summary["campaign_status"]["operation_mode"] == "REAL_PROSPECTIVE"
    assert summary["campaign_status"]["completed_origin_count"] == 0
    assert summary["campaign_status"]["next_required_origin"] == "2026-09-15T00:00:00Z"
    assert summary["campaign_status"]["next_origin_due_state"] == "NOT_DUE"


def test_cli_dry_readiness_reports_ready_without_publication(tmp_path, capsys):
    activate_real_campaign(tmp_path)
    rc = caller.main(
        ["--dry-readiness", "--root", str(ROOT), "--state-dir", str(tmp_path / "state"), "--now", "2026-09-15T00:30:00Z"],
        run_git=fake_run_git(),
        archive_provider=synthetic_archive_provider(),
        fetch_klines=synthetic_fetch_klines(),
    )
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is True
    assert report["target_commit"] == PINNED
    assert report["validated_bar_count"] == 20 * REQUIRED_CLOSE_COUNT
    assert len(report["source_data_manifest_sha256"]) == 64
    assert not (tmp_path / "state" / "retention").exists()
