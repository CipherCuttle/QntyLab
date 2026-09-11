from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from qntylab.research_ledger import sha256_path


ROOT = Path(__file__).resolve().parents[1]
ORIGIN_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/prospective_origin.json"
PREREG_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1.json"
ACTIVATION_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1_activation.json"
ACTIVATION_MERGE_SHA = "adee935bfa596af5e7e0ad0fe1e5aadf9f7faad5"
EXPECTED_ACTIVATION_UTC = "2026-09-11T17:59:07Z"
EXPECTED_ORIGIN_UTC = "2026-09-11T18:00:00Z"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _next_whole_hour_strictly_after(value: datetime) -> datetime:
    utc = value.astimezone(timezone.utc)
    return utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def test_origin_is_derived_only_from_verified_activation_merge_metadata() -> None:
    origin = _load(ORIGIN_PATH)
    git_timestamp = subprocess.check_output(
        ["git", "show", "-s", "--format=%cI", ACTIVATION_MERGE_SHA],
        cwd=ROOT,
        text=True,
    ).strip()
    activation_utc = _parse_utc(git_timestamp)
    expected_activation = _parse_utc(EXPECTED_ACTIVATION_UTC)
    assert activation_utc == expected_activation
    assert origin["activation_merge_sha"] == ACTIVATION_MERGE_SHA
    assert _parse_utc(origin["activation_merge_committed_at_utc"]) == expected_activation
    derived_origin = _next_whole_hour_strictly_after(activation_utc)
    assert derived_origin == _parse_utc(EXPECTED_ORIGIN_UTC)
    assert _parse_utc(origin["prospective_origin_utc"]) == derived_origin
    assert origin["materialization_integrity"] == {
        "derived_from_git_metadata_only": True,
        "market_data_accessed_to_choose_origin": False,
        "strategy_result_accessed_to_choose_origin": False,
        "origin_may_not_be_moved_after_materialization": True,
    }


def test_origin_binds_exact_source_contract_hashes() -> None:
    origin = _load(ORIGIN_PATH)
    sources = origin["source_contracts"]
    assert sources == {
        "preregistration_path": "experiments/specs/h003_defensive_followup_v1.json",
        "preregistration_sha256": "d56da275c4339163c77cd6e5599f151964be6f61323124f9f72d98e3974f44ca",
        "activation_contract_path": "experiments/specs/h003_defensive_followup_v1_activation.json",
        "activation_contract_sha256": "6d11a8e748e6a28560781a0d8044d913934bd2e199891932ed2fe4df3b3d7505",
    }
    assert sha256_path(PREREG_PATH) == sources["preregistration_sha256"]
    assert sha256_path(ACTIVATION_PATH) == sources["activation_contract_sha256"]


def test_origin_preserves_frozen_prospective_panel_and_return_ownership() -> None:
    origin = _load(ORIGIN_PATH)
    prereg = _load(PREREG_PATH)
    activation = _load(ACTIVATION_PATH)

    panel = prereg["prospective_panel"]
    assert origin["assets"] == panel["assets"] == ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
    assert origin["market"] == panel["market"] == "Binance Spot"
    assert origin["timeframe"] == panel["timeframe"] == "1h"
    assert origin["strategy"] == {
        "strategy_id": "H003_moving_average",
        "strategy_version": "existing-qntylab-strategies-v1",
        "fast": 48,
        "slow": 192,
        "mode": "long_flat",
        "leverage": 1.0,
    }

    recorder = activation["metadata"]["prospective_recorder"]
    assert recorder["status"] == "ARMED_BUT_INACTIVE_PENDING_ORIGIN_ARTIFACT"
    assert recorder["origin"] is None
    assert recorder["market_data_recording_authorized"] is False
    assert recorder["signal_recording_authorized"] is False

    ownership = origin["return_ownership"]
    assert ownership["pre_origin_closes_may_initialize_state_only"] is True
    assert ownership["pre_origin_return_or_transition_cost_in_metrics"] is False
    assert ownership["owned_return_requires_ending_bar_timestamp_strictly_greater_than_origin"] is True
    assert ownership["first_possible_owned_return_end_utc"] == "2026-09-11T19:00:00Z"


def test_origin_authorizes_shadow_recording_only_and_freezes_maturity() -> None:
    origin = _load(ORIGIN_PATH)
    prereg = _load(PREREG_PATH)
    panel = prereg["prospective_panel"]
    maturity = origin["maturity"]
    authority = origin["recorder_authority"]

    assert maturity["minimum_calendar_days_before_economic_verdict"] == panel["minimum_calendar_days_before_economic_verdict"] == 180
    assert maturity["minimum_genuine_position_state_changes_per_asset"] == panel["minimum_genuine_position_state_changes_per_asset_before_economic_verdict"] == 2
    assert maturity["maximum_calendar_days_for_regime_coverage_gate"] == panel["maximum_calendar_days_for_regime_coverage_gate"] == 365
    assert maturity["earliest_calendar_maturity_utc"] == "2027-03-10T18:00:00Z"
    assert maturity["regime_coverage_deadline_utc"] == "2027-09-11T18:00:00Z"

    assert authority["status_after_this_artifact_is_canonical"] == "ACTIVE_PROSPECTIVE_SHADOW_RECORDING"
    assert authority["recording_may_begin_only_after_artifact_is_canonical"] is True
    assert authority["market_data_recording_authorized"] is True
    assert authority["signal_recording_authorized"] is True
    assert authority["integrity_receipt_recording_authorized"] is True
    assert authority["economic_performance_verdict_before_maturity_forbidden"] is True
    assert authority["parameter_changes_forbidden"] is True
    assert authority["asset_changes_forbidden"] is True
    assert authority["qnty_acceptance"] == "NONE"
    assert authority["qntyspot_policy"] == "NONE"
    assert authority["live_execution"] == "FORBIDDEN"
    assert authority["capital"] == "NONE"
    assert authority["signing"] == "NONE"
    assert authority["submission"] == "NONE"
