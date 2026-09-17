from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

from qntylab import order_flow_prospective_v1_operation as operation
from qntylab import order_flow_prospective_v1_recorder as recorder


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/research/qnty_edge_discovery_order_flow_v1"


def test_live_probe_receipt_and_activation_boundary_are_exact():
    probe = json.loads((EXP / "source_live_probe_result.json").read_text(encoding="utf-8"))
    activation = json.loads((EXP / "prospective_activation.json").read_text(encoding="utf-8"))

    assert probe["state"] == "PASS"
    assert probe["mode"] == "NON_SCIENTIFIC_SOURCE_QUALIFICATION"
    assert probe["scientific_evidence"] is False
    assert probe["probe_canonical_master_sha"] == operation.PROBE_CANONICAL_MASTER_SHA
    assert probe["worktree_mode"] == "CLEAN_DETACHED_WORKTREE"
    assert probe["head_verified_exact"] is True
    assert probe["worktree_clean"] is True
    assert probe["symbol_count"] == 5
    assert probe["symbols"] == list(recorder.PANEL)
    assert probe["payload_persisted"] is False
    assert probe["price_volume_feature_values_persisted"] is False

    assert activation["state"] == "AUTHORIZED_IF_CANONICAL"
    assert activation["activation_scope"] == "PROSPECTIVE_COLLECTION_ONLY"
    assert activation["candidate_branch_is_authority"] is False
    assert activation["activation_effective_on_branch"] is False
    assert activation["canonicalization_required_before_effect"] is True
    assert activation["activation_effective"] == "AFTER_EXACT_CANONICAL_MERGE_AND_MATCHING_LOCAL_UNIT_INSTALL_ONLY"
    assert activation["backfill"] == "FORBIDDEN"
    assert activation["source_substitution"] == "FORBIDDEN"
    assert activation["persistence"] == "GITHUB_IMMUTABLE_RELEASE_HASH_CHAIN_V1"
    branch_authority = activation["branch_authority"]
    assert branch_authority["real_market_data_access_authorized"] is False
    assert branch_authority["prospective_collection_authorized"] is False
    assert branch_authority["scheduler_authorized"] is False
    assert branch_authority["scientific_recording_authorized"] is False

    authority = activation["authority_after_canonicalization"]
    assert authority["real_market_data_access_authorized"] is True
    assert authority["prospective_collection_authorized"] is True
    assert authority["scheduler_authorized"] is True
    assert authority["scientific_recording_authorized"] is True
    assert authority["interim_scientific_evaluation_authorized"] is False
    assert authority["terminal_evaluation_authorized"] is False
    assert authority["router_authorized"] is False
    assert authority["qnty_authorized"] is False
    assert authority["qntyspot_authorized"] is False
    assert authority["trading_authorized"] is False
    assert authority["capital_authority"] == "NONE"
    assert authority["signing_authority"] == "NONE"
    assert authority["submission_authority"] == "NONE"

    assert operation.validate_activation_artifacts(ROOT)["state"] == "AUTHORIZED_IF_CANONICAL"


def test_project_context_authorizes_only_bounded_activation_implementation():
    authority = operation.validate_project_authority(ROOT)
    assert authority == {
        "project_id": operation.PROJECT_ID,
        "state": "ACTIVE",
        "implementation_authorized": True,
        "activation_effective_on_branch": False,
        "canonicalization_required_before_effect": True,
    }


def test_frozen_required_close_grid_is_exact():
    closes = operation.required_closes()
    assert len(closes) == 2905
    assert recorder.stamp(closes[0]) == recorder.FIRST_WARMUP_CLOSE
    assert recorder.stamp(closes[23]) == recorder.LAST_WARMUP_CLOSE
    assert recorder.stamp(closes[24]) == recorder.FIRST_ORIGIN
    assert recorder.stamp(closes[-2]) == recorder.LAST_ORIGIN
    assert recorder.stamp(closes[-1]) == recorder.TERMINAL_TAIL_CLOSE


def _synthetic_fetcher(calls):
    def fetcher(*, symbol, logical_close):
        calls.append((symbol, recorder.stamp(logical_close)))
        return [recorder.synthetic_row(symbol=symbol, logical_close=logical_close)]
    return fetcher


def test_record_due_records_only_current_close_and_anchors(tmp_path):
    now = recorder.hour(recorder.FIRST_WARMUP_CLOSE) + timedelta(minutes=5)
    calls = []
    anchors = []

    def anchorer(ledger, target_commit):
        anchors.append((len(ledger.events()), target_commit, ledger.ledger_sha256()))
        return {"immutable": True, "independent_restore": "PASS"}

    result = operation.record_due(
        ROOT,
        tmp_path,
        now=now,
        fetcher=_synthetic_fetcher(calls),
        clock=lambda: now,
        canonical_check=False,
        anchorer=anchorer,
    )

    assert result["state"] == "ANCHORED"
    assert result["logical_close_utc"] == recorder.FIRST_WARMUP_CLOSE
    assert result["missed_marked_this_run"] == 0
    assert len(calls) == 5
    assert [symbol for symbol, _ in calls] == list(recorder.PANEL)
    assert len(anchors) == 1
    events = recorder.EvidenceLedger(tmp_path).events()
    assert len(events) == 1
    assert events[0]["event_type"] == "OBSERVATION_STAGED"
    assert events[0]["payload"]["durable_scientific_state"] == "OBSERVED_PENDING_ANCHOR"


def test_overdue_closes_become_gaps_before_current_fetch(tmp_path):
    first = recorder.hour(recorder.FIRST_WARMUP_CLOSE)
    now = first + timedelta(hours=2, minutes=5)
    calls = []
    anchors = []

    def anchorer(ledger, target_commit):
        anchors.append(tuple(event["event_type"] for event in ledger.events()))
        return {"immutable": True, "independent_restore": "PASS"}

    result = operation.record_due(
        ROOT,
        tmp_path,
        now=now,
        fetcher=_synthetic_fetcher(calls),
        clock=lambda: now,
        canonical_check=False,
        anchorer=anchorer,
    )

    assert result["state"] == "ANCHORED"
    assert result["missed_marked_this_run"] == 2
    assert result["logical_close_utc"] == recorder.stamp(first + timedelta(hours=2))
    assert len(calls) == 5
    events = recorder.EvidenceLedger(tmp_path).events()
    assert [event["event_type"] for event in events] == [
        "WINDOW_MISSED",
        "WINDOW_MISSED",
        "OBSERVATION_STAGED",
    ]
    assert anchors[0] == ("WINDOW_MISSED",)
    assert anchors[1] == ("WINDOW_MISSED", "WINDOW_MISSED")
    assert anchors[2] == (
        "WINDOW_MISSED",
        "WINDOW_MISSED",
        "OBSERVATION_STAGED",
    )


def test_local_systemd_timer_is_hourly_nonpersistent_and_no_github_provider_runner():
    timer = (ROOT / "ops/systemd/user/order-flow-v1-prospective-record.timer").read_text(encoding="utf-8")
    service = (ROOT / "ops/systemd/user/order-flow-v1-prospective-record.service").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/order-flow-prospective-v1-activation.yml").read_text(encoding="utf-8")

    for minute in ("05", "20", "35", "50"):
        assert f"OnCalendar=*-*-* *:{minute}:00 UTC" in timer
    assert "Persistent=false" in timer
    assert "RandomizedDelaySec=0" in timer
    assert "WorkingDirectory=/srv/qntylab-orderflow/repo" in service
    assert "order_flow_prospective_v1_operation --record-due" in service
    assert "git checkout --detach origin/master" in service
    assert "contents: read" in workflow
    assert "schedule:" not in workflow
    assert "run_non_scientific_live_probe" not in workflow


def test_canonical_state_dir_is_fixed_and_xdg_override_is_ignored(monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/not-authorized")
    assert operation.default_state_dir() == operation.CANONICAL_STATE_DIR


def test_trusted_host_binding_uses_campaign_specific_fingerprint(monkeypatch):
    monkeypatch.setattr(operation, "_trusted_host_fingerprint", lambda path=operation.MACHINE_ID_PATH: operation.TRUSTED_HOST_BINDING_DIGEST)
    result = operation.validate_trusted_host(ROOT)
    assert result["context"] == operation.HOST_BINDING_CONTEXT
    assert result["digest"] == operation.TRUSTED_HOST_BINDING_DIGEST


def test_wrong_trusted_host_fails_closed(tmp_path):
    import pytest
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("different-machine\n", encoding="utf-8")
    with pytest.raises(operation.OperationBlocked, match="qualified trusted host"):
        operation.validate_trusted_host(ROOT, machine_id)


def test_noncanonical_recording_requires_injected_fetcher(tmp_path):
    import pytest
    now = recorder.hour(recorder.FIRST_WARMUP_CLOSE) + timedelta(minutes=5)
    with pytest.raises(operation.OperationBlocked, match="injected synthetic fetcher"):
        operation.record_due(ROOT, tmp_path, now=now, canonical_check=False, anchorer=lambda ledger, target: {"immutable": True})


def test_reconcile_restores_missing_local_ledger_from_remote(monkeypatch, tmp_path):
    import hashlib
    remote = recorder.EvidenceLedger(tmp_path / "remote")
    close = recorder.hour(recorder.FIRST_WARMUP_CLOSE)
    remote.record_batch(logical_close=close, rows=recorder.synthetic_batch(close), observed_at=close + timedelta(minutes=5))
    payload = remote.path.read_bytes()
    events = remote.events()
    metadata = {"schema": operation.EVIDENCE_RELEASE_SCHEMA, "event_count": 1, "head_event_digest": events[-1]["event_digest"], "ledger_sha256": hashlib.sha256(payload).hexdigest(), "previous_release_tag": None, "scientific_evaluation": "FORBIDDEN"}
    head = {"tag_name": operation._ledger_tag(events), "draft": False, "immutable": True, "_evidence_meta": metadata}
    monkeypatch.setattr(operation, "_evidence_release_state", lambda: {"published_head": head, "draft_head": None})
    monkeypatch.setattr(operation, "_download_release_bytes", lambda requested: payload)
    local = recorder.EvidenceLedger(tmp_path / "local")
    result = operation.reconcile_canonical_ledger(local)
    assert result["state"] == "RESTORED_REMOTE_HEAD"
    assert local.path.read_bytes() == payload
    assert local.events() == events


def test_runtime_pins_host_state_and_remote_reconciliation():
    runtime = json.loads((EXP / "prospective_runtime.json").read_text(encoding="utf-8"))
    assert runtime["state_dir"] == str(operation.CANONICAL_STATE_DIR)
    assert runtime["trusted_host_identity"] == {"method": "SHA256_CONTEXTUALIZED_SHA256_ETC_MACHINE_ID", "context": operation.HOST_BINDING_CONTEXT, "digest": operation.TRUSTED_HOST_BINDING_DIGEST, "probe_host_binding_required": True}
    assert runtime["remote_reconciliation_required_before_provider_access"] is True
    assert runtime["release_body_schema"] == operation.EVIDENCE_RELEASE_SCHEMA


def test_migration_host_binding_accepts_only_exact_hetzner_digest(monkeypatch):
    import pytest

    expected = "541ef1512288f24b4b831d975a58b8b4918ba84c70f922c5a677bae8c08d458e"
    assert operation.TRUSTED_HOST_BINDING_DIGEST == expected
    for digest in (
        "0902027d8e7eb13bf130934d46a48b61cd6b126fef13f371844f4d5de9e39f5e",
        "0" + expected[1:],
    ):
        monkeypatch.setattr(operation, "_trusted_host_fingerprint", lambda path, d=digest: d)
        with pytest.raises(operation.OperationBlocked, match="qualified trusted host"):
            operation.validate_trusted_host(ROOT)
    monkeypatch.setattr(operation, "_trusted_host_fingerprint", lambda path: expected)
    assert operation.validate_trusted_host(ROOT)["digest"] == expected


def test_migration_fingerprint_preserves_raw_bytes_and_context(tmp_path):
    from hashlib import sha256

    raw = b"synthetic-machine-id-for-offline-test\n"
    machine_id = tmp_path / "machine-id"
    machine_id.write_bytes(raw)
    assert operation.HOST_BINDING_CONTEXT == "QNTYLAB_ORDER_FLOW_V1_HOST_V1"
    expected = sha256(b"QNTYLAB_ORDER_FLOW_V1_HOST_V1:" + sha256(raw).hexdigest().encode()).hexdigest()
    assert operation._trusted_host_fingerprint(machine_id) == expected
    assert expected != sha256(b"QNTYLAB_ORDER_FLOW_V1_HOST_V1:" + sha256(raw.strip()).hexdigest().encode()).hexdigest()


def test_migration_rejects_laptop_state_and_accepts_exact_hetzner_state():
    import pytest

    expected = Path("/srv/qntylab-orderflow/state/order_flow_prospective_v1")
    assert operation.CANONICAL_STATE_DIR == expected
    assert operation._validate_recording_state_dir(expected) == expected
    for path in (
        Path("/home/swirky/.local/state/qntylab/order_flow_prospective_v1"),
        Path("/srv/qnty/state/order_flow_prospective_v1"),
        expected.parent / "other_campaign",
    ):
        with pytest.raises(operation.OperationBlocked, match="canonical recording state directory mismatch"):
            operation._validate_recording_state_dir(path)


def test_migration_runtime_service_and_frozen_blob_contracts():
    import subprocess

    runtime = json.loads((EXP / "prospective_runtime.json").read_text())
    service = (ROOT / operation.SERVICE_PATH).read_text()
    assert runtime["operational_worktree"] == "/srv/qntylab-orderflow/repo"
    assert runtime["python_executable"] == "/srv/qntylab-orderflow/venv/bin/python"
    assert runtime["state_dir"] == "/srv/qntylab-orderflow/state/order_flow_prospective_v1"
    assert runtime["python_required_major_minor"] == "3.12"
    for line in (
        "Documentation=file:///srv/qntylab-orderflow/repo/ops/systemd/user/order-flow-v1-prospective.md",
        "Environment=HOME=/home/viktor",
        "Environment=PATH=/usr/bin:/bin:/home/viktor/.local/bin:/snap/bin",
        "WorkingDirectory=/srv/qntylab-orderflow/repo",
        "Type=oneshot", "TimeoutStartSec=840", "SuccessExitStatus=3",
        "ExecStartPre=/bin/sh -c 'test -z \"$(/usr/bin/git status --porcelain)\"'",
        "ExecStartPre=/usr/bin/git fetch origin master",
        "ExecStartPre=/usr/bin/git checkout --detach origin/master",
        "StandardOutput=journal", "StandardError=journal",
    ):
        assert line in service.splitlines()
    assert "exec /srv/qntylab-orderflow/venv/bin/python -m qntylab.order_flow_prospective_v1_operation --record-due --root /srv/qntylab-orderflow/repo" in service
    assert "/home/swirky" not in service
    assert "[Install]" not in service
    for key, path in (
        ("operation_git_blob_sha", operation.OPERATION_PATH),
        ("service_git_blob_sha", operation.SERVICE_PATH),
        ("timer_git_blob_sha", operation.TIMER_PATH),
    ):
        assert subprocess.check_output(["git", "hash-object", str(path)], cwd=ROOT, text=True).strip() == runtime[key]
    assert runtime["timer_git_blob_sha"] == "f2cffbdfca53d8eccfcb942aed6e2379cba350cf"
    assert runtime["persistent_timer"] is False
    assert runtime["attempt_minutes_utc"] == [5, 20, 35, 50]
    assert operation.SOURCE_GIT_BLOB_SHA == "1b5550ee2b8bbae3905e7f88583ec88217121274"
    assert operation.RECORDER_GIT_BLOB_SHA == "02daadaa597dcf00789af66c01fe13e66031ec3d"
    assert operation.validate_activation_artifacts(ROOT)["state"] == "AUTHORIZED_IF_CANONICAL"


def test_migration_receipt_cannot_grant_cutover_or_scientific_authority():
    receipt = json.loads((EXP / "hetzner_host_migration_v1.json").read_text())
    assert receipt["candidate_id"] == recorder.CANDIDATE_ID
    assert receipt["mode"] == "NON_SCIENTIFIC_OPERATIONAL_HOST_MIGRATION"
    assert receipt["migration_state"] == "CANDIDATE_NOT_EFFECTIVE_UNTIL_CANONICAL_MERGE_AND_CUTOVER"
    assert receipt["new_host_digest"] == operation.TRUSTED_HOST_BINDING_DIGEST
    assert receipt["single_writer_cutover_required"] is True
    assert receipt["laptop_timer_must_stop_before_hetzner_timer_start"] is True
    assert receipt["state_transfer_method"] == "RESTORE_FROM_LATEST_IMMUTABLE_GITHUB_RELEASE"
    for key in ("manual_ledger_copy", "backfill", "source_substitution", "interim_evaluation"):
        assert receipt[key] == "FORBIDDEN"
    for key in ("provider_payload_persisted", "scientific_values_persisted", "hetzner_order_flow_timer_installed", "hetzner_order_flow_timer_started", "existing_qnty_modified", "cutover_ready"):
        assert receipt[key] is False
    assert all(value == "NONE" for value in receipt["authority"].values())
    assert receipt["github_auth_ready"] is False
    assert "BLOCKED_HETZNER_GITHUB_AUTH_REQUIRED" in receipt["qualification_blockers"]
