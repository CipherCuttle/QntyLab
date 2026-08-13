from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from qntylab import jh01_rv_persistence_incremental_forecast_value_prereg_v1 as prereg


ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/prospective_recorder_and_input_materialization_authorization_v0.json"


def auth() -> dict:
    return json.loads(AUTH_PATH.read_text(encoding="utf-8"))


def test_canonical_prereg_identity_merge_and_unchanged_bytes() -> None:
    value = auth()
    frozen = value["frozen_preregistration"]
    path = ROOT / frozen["path"]
    preregistration = json.loads(path.read_text(encoding="utf-8"))
    assert value["state"] == "CLOSED_BLOCKED"
    assert frozen["project_id"] == prereg.EXPERIMENT_ID
    assert frozen["candidate_id"] == prereg.CANDIDATE_ID
    assert preregistration["preregistration_digest"] == frozen["preregistration_digest"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == frozen["bytes_sha256"]
    assert frozen["canonical_merge_commit"] == "c32afe563c6093775cc0195e3c57ac192345b549"
    assert frozen["canonical_merge_parents"] == ["8d626d445d10868e5ac016b5e22cc6f0021a65a6", "f4db5315782f4c612cdd121f58073fcdad1f56c9"]
    assert frozen["canonical_merge_time_utc"] == "2026-08-13T19:55:05Z"
    assert frozen["canonical_freeze_deadline_satisfied"] is True


def test_schedule_panel_and_hard_timing_boundaries_remain_frozen() -> None:
    value, schedule, contract = auth(), auth()["frozen_schedule"], auth()["frozen_later_implementation_contract"]
    assert (schedule["first_origin"], schedule["last_origin"], schedule["required_valid_origins"], schedule["first_origin_changed"]) == (prereg.FIRST_DECISION, prereg.LAST_DECISION, 365, False)
    assert contract["persistence_window"] == "t <= AUTHORITATIVE_PERSISTENCE_TIME < t + 1 hour"
    assert contract["max_input_bar_close_rule"] == "MAX_INPUT_BAR_CLOSE <= t"
    assert "open/partial t+1 bar blocks" in contract["source_finality_rule"]
    assert "<= t" in contract["live_extension_rule"] and "never pre-download t+1" in contract["live_extension_rule"]
    assert json.loads((ROOT / value["frozen_preregistration"]["path"]).read_text())["frozen_target"]["ordered_20_symbol_panel_sha256"] == "e6d1447ff2be57f81eaf943b62218ce9a7b9a6f5bf2d25f9be255cb3f2040cd8"


def test_bootstrap_and_strict_training_cutoff_are_mechanically_derived() -> None:
    bootstrap = auth()["frozen_later_implementation_contract"]["bootstrap_source_range"]
    first = datetime.fromisoformat("2026-09-15T00:00:00+00:00")
    latest = first - timedelta(days=2)
    earliest = latest - timedelta(days=364)
    assert (earliest, latest, (latest - earliest).days + 1) == (datetime(2025, 9, 14, tzinfo=UTC), datetime(2026, 9, 13, tzinfo=UTC), 365)
    assert bootstrap["first_training_origin"] == "2025-09-14T00:00:00Z"
    assert bootstrap["first_required_bar_close"] == "2025-09-11T19:00:00Z"
    assert bootstrap["last_required_completed_training_target_bar_close"] == "2026-09-14T00:00:00Z"
    assert "o + 24h < t" in auth()["frozen_later_implementation_contract"]["training_target_cutoff_rule"]


def test_backend_is_correctly_rejected_as_non_authoritative_time() -> None:
    backend = auth()["persistence_backend_qualification"]
    assert backend["assessed_existing_primitive"] == "REMOTE_GIT_REF_PLUS_O_EXCL_RECEIPT"
    assert backend["proposed_backend"] == "NONE_QUALIFIED"
    assert backend["remote_or_externally_grounded_time"] == "NO"
    assert backend["caller_cannot_freely_backdate"] == "UNPROVEN"
    assert backend["read_after_unknown_write_supported"] == "UNPROVEN"
    assert backend["retention_horizon_proven"] is False
    assert backend["verdict"] == "BLOCKED"
    assert "caller-controlled" in backend["rejection"]


def test_exactly_one_duplicate_crash_clock_and_sealed_output_contracts() -> None:
    contract = auth()["frozen_later_implementation_contract"]
    assert "Same origin plus same digest" in contract["one_origin_one_artifact"]
    assert "BLOCKED_AMBIGUOUS_FORECAST_IDENTITY" in contract["one_origin_one_artifact"]
    assert "No latest-wins" in contract["one_origin_one_artifact"]
    assert "Interrogate authoritative backend state" in contract["crash_retry"]
    assert "UTC-aware" in contract["clock_contract"] and "naive datetimes are rejected" in contract["clock_contract"]
    assert "no catch-up" in contract["scheduler_requirements"]
    sealed = contract["sealed_training_state"]
    for forbidden in ("loss", "ranking", "adjusted-MSPE/HAC", "p-value", "classification", "rescue"):
        assert forbidden in sealed


def test_no_execution_or_downstream_authority_and_complete_kill_set() -> None:
    value = auth()
    assert value["implementation_authorized"] is False
    assert value["future_bounded_implementation_authorized"] is False
    assert value["ledger_changed"] is False
    assert all(flag is False for flag in value["outcome_blindness"].values())
    assert all(flag is False for flag in value["authority"].values())
    required = {"SOURCE_BAR_AFTER_ORIGIN", "OPEN_OR_PARTIAL_FUTURE_BAR_USED", "SELF_DECLARED_TIMESTAMP_USED_AS_AUTHORITY", "MULTIPLE_DIFFERENT_FORECASTS_FOR_ONE_ORIGIN", "BACKFILL_ATTEMPT", "UNAUTHORIZED_INTERIM_EVALUATION"}
    assert required.issubset(value["kill_conditions"])
    assert "TEST/NON-V1" in value["frozen_later_implementation_contract"]["dry_run"]
