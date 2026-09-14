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
    assert "QntyLab-orderflow-operational" in service
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
