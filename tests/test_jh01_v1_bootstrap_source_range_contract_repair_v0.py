from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from qntylab.jh01_v1_bootstrap_source_range_contract_repair_v0 import derive_bootstrap_source_range


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/bootstrap_source_range_contract_repair_v0.json"
PREREG = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/preregistration.json"
HISTORICAL = "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/prospective_recorder_and_input_materialization_authorization_v0.json"
V0R3 = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/github_release_attestation_offline_policy_qualification_v0r3.json"


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_frozen_schedule_and_b3_dependency_derivation() -> None:
    result = derive_bootstrap_source_range(datetime(2026, 9, 15, tzinfo=UTC))
    assert result.strict_completion_operator == "o + 24h < T"
    assert result.latest_eligible_training_origin == datetime(2026, 9, 13, tzinfo=UTC)
    assert result.first_training_origin == datetime(2025, 9, 14, tzinfo=UTC)
    assert len(result.training_origins) == 365
    assert len(result.b3_rv24_origins) == 30
    assert result.b3_rv24_origins[0] == result.first_training_origin
    assert result.b3_rv24_origins[-1] == datetime(2025, 8, 16, tzinfo=UTC)
    assert len(result.rv24_return_closes) == 24
    assert result.rv24_return_closes == tuple(datetime(2025, 8, 15, hour, tzinfo=UTC) for hour in range(1, 24)) + (datetime(2025, 8, 16, tzinfo=UTC),)
    assert result.earliest_required_source_close == datetime(2025, 8, 15, tzinfo=UTC)
    assert result.latest_required_completed_training_target_close == datetime(2026, 9, 14, tzinfo=UTC)


def test_off_by_one_mutations_are_not_the_frozen_contract() -> None:
    result = derive_bootstrap_source_range(datetime(2026, 9, 15, tzinfo=UTC))
    assert result.latest_eligible_training_origin + timedelta(hours=24) < result.first_live_origin
    assert result.latest_eligible_training_origin + timedelta(days=1, hours=24) == result.first_live_origin
    assert len(derive_bootstrap_source_range(datetime(2026, 9, 15, tzinfo=UTC), b3_longest_lag_days=28).b3_rv24_origins) == 29
    assert result.earliest_required_return_close - timedelta(hours=1) == result.earliest_required_source_close


def test_repair_artifact_matches_code_and_preserves_frozen_predecessors() -> None:
    value = json.loads(ARTIFACT.read_text())
    result = derive_bootstrap_source_range(_time(value["mechanical_inputs"]["first_live_origin"]))
    derived = value["mechanical_derivation"]
    assert value["state"] == "CLOSED_PASS"
    assert derived["latest_eligible_training_origin"] == result.latest_eligible_training_origin.isoformat().replace("+00:00", "Z")
    assert derived["first_training_origin"] == result.first_training_origin.isoformat().replace("+00:00", "Z")
    assert derived["training_origin_count"] == len(result.training_origins) == 365
    assert derived["b3_rv24_observation_count"] == len(result.b3_rv24_origins) == 30
    assert derived["earliest_b3_rv24_timestamp"] == result.earliest_b3_rv24_origin.isoformat().replace("+00:00", "Z")
    assert derived["earliest_required_hourly_return_close"] == result.earliest_required_return_close.isoformat().replace("+00:00", "Z")
    assert derived["earliest_required_source_close"] == result.earliest_required_source_close.isoformat().replace("+00:00", "Z")
    assert derived["latest_completed_training_target_source_close"] == result.latest_required_completed_training_target_close.isoformat().replace("+00:00", "Z")
    assert value["repair"]["repaired_first_required_bar_close"] == derived["earliest_required_source_close"]
    assert value["repair"]["repaired_first_required_source_close"] == derived["earliest_required_source_close"]
    assert _time(value["repair"]["old_first_required_bar_close"]) - result.earliest_required_source_close == timedelta(days=27, hours=19)
    assert value["repair"]["delta_seconds"] == 2401200
    assert hashlib.sha256(PREREG.read_bytes()).hexdigest() == value["frozen_preregistration"]["bytes_sha256"]
    historical = subprocess.run(["git", "show", f"{value['historical_predecessor']['reviewed_sha']}:{HISTORICAL}"], cwd=ROOT, check=True, capture_output=True).stdout
    assert hashlib.sha256(historical).hexdigest() == hashlib.sha256((ROOT / HISTORICAL).read_bytes()).hexdigest()
    assert json.loads(historical)["frozen_later_implementation_contract"]["bootstrap_source_range"]["first_required_bar_close"] == value["repair"]["old_first_required_bar_close"]
    assert json.loads(V0R3.read_text())["state"] == "CLOSED_PASS"


def test_repair_has_no_scientific_or_implementation_authority() -> None:
    value = json.loads(ARTIFACT.read_text())
    assert value["state"] != "CLOSED_PASS" or value["qnty_agent_eval"] == "NO_MATCH"
    assert not any(value["outcome_blindness"].values())
    assert not any(value["authority"].values())
    assert value["ledger_changed"] is False
    assert value["supersession"]["historical_artifact_rewritten"] is False
