from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from qntylab import jh01_rv_persistence_incremental_forecast_value_input_materialization_authorization_v0 as gate


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v0/input_materialization_authorization_v0.json"


def receipt(origin: str, *, persistence_time: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "candidate_id": gate.CANDIDATE_ID,
        "forecast_origin": origin,
        "forecast_artifact_digest": "a" * 64,
        "persistence_mechanism": "GIT_COMMIT",
        "persistence_time": persistence_time,
        "immutable": True,
        "committed": True,
    }
    value.update(overrides)
    return value


def test_frozen_calendar_census_and_fail_closed_artifact() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    prereg = ROOT / artifact["frozen_preregistration"]["path"]
    assert hashlib.sha256(prereg.read_bytes()).hexdigest() == artifact["frozen_preregistration"]["sha256"]
    assert artifact["pre_freeze_origin_census"]["count"] == 24
    assert artifact["pre_freeze_origin_census"]["origins"] == list(gate.assess("2026-08-13T00:13:11Z", ())["pre_freeze_origins"])
    assert artifact["pre_target_forecast_persistence_search"]["missing_origins"] == list(gate.assess("2026-08-13T00:13:11Z", ())["missing_pre_target_forecast_origins"])
    assert artifact["prospective_integrity"] == "FAILED_FROZEN_START_ALREADY_ELAPSED_WITHOUT_PERSISTED_FORECAST"
    assert artifact["materialization_authorized"] is False


def test_freeze_before_first_target_with_valid_receipt_is_eligible() -> None:
    assert gate.assess("2026-07-20T12:00:00Z", ()) == {
        "pre_freeze_origins": (), "missing_pre_target_forecast_origins": (),
        "prospective_integrity": "ESTABLISHED", "materialization_authorized": True,
        "scientific_execution_authorized": False,
    }


def test_elapsed_origin_without_receipt_blocks() -> None:
    result = gate.assess("2026-07-21T00:00:00Z", ())
    assert result["missing_pre_target_forecast_origins"] == ("2026-07-20T00:00:00Z",)
    assert result["materialization_authorized"] is False


def test_persistence_window_accepts_only_origin_through_pre_target() -> None:
    origin = "2026-07-20T00:00:00Z"
    for time in ("2026-07-20T00:00:00Z", "2026-07-20T00:00:01Z", "2026-07-20T23:59:59Z"):
        result = gate.assess("2026-07-21T00:00:00Z", (receipt(origin, persistence_time=time),))
        assert result["prospective_integrity"] == "ESTABLISHED"


def test_pre_origin_persistence_is_rejected_even_before_target() -> None:
    origin = "2026-07-20T00:00:00Z"
    for time in ("2026-07-19T23:59:59Z", "2026-07-01T00:00:00Z"):
        result = gate.assess("2026-07-21T00:00:00Z", (receipt(origin, persistence_time=time),))
        assert result["materialization_authorized"] is False


def test_receipt_at_or_after_target_is_rejected() -> None:
    origin = "2026-07-20T00:00:00Z"
    for time in ("2026-07-21T00:00:00Z", "2026-07-21T00:00:01Z"):
        assert gate.assess("2026-07-21T01:00:00Z", (receipt(origin, persistence_time=time),))["materialization_authorized"] is False


def test_mtime_and_uncommitted_files_are_rejected() -> None:
    origin = "2026-07-20T00:00:00Z"
    for row in (
        receipt(origin, persistence_time="2026-07-20T01:00:00Z", persistence_mechanism="FILESYSTEM_MTIME"),
        receipt(origin, persistence_time="2026-07-20T01:00:00Z", committed=False),
    ):
        assert gate.assess("2026-07-21T00:00:00Z", (row,))["materialization_authorized"] is False


def test_wrong_candidate_or_origin_is_rejected() -> None:
    origin = "2026-07-20T00:00:00Z"
    for row in (
        receipt(origin, persistence_time="2026-07-20T01:00:00Z", candidate_id="OTHER"),
        receipt("2026-07-19T00:00:00Z", persistence_time="2026-07-20T01:00:00Z"),
    ):
        assert gate.assess("2026-07-21T00:00:00Z", (row,))["materialization_authorized"] is False


def test_partial_coverage_and_one_missing_of_twenty_four_block() -> None:
    elapsed = gate.assess("2026-08-13T00:13:11Z", ())["pre_freeze_origins"]
    receipts = tuple(receipt(origin, persistence_time=origin) for origin in elapsed[:-1])
    result = gate.assess("2026-08-13T00:13:11Z", receipts)
    assert result["missing_pre_target_forecast_origins"] == (elapsed[-1],)
    assert result["materialization_authorized"] is False


def test_fixed_start_and_origin_count_are_not_substitutable() -> None:
    assert gate.FIRST_DECISION == "2026-07-20T00:00:00Z"
    assert gate.REQUIRED_ORIGINS == 365
    assert len(gate.origins()) == 365
    assert gate.origins()[-1] == gate.parse_time(gate.LAST_DECISION)


def test_gate_has_no_market_or_scientific_execution_capability() -> None:
    source = inspect.getsource(gate)
    for forbidden in ("requests", "urllib", "pandas", "numpy", "binance", "evaluate(", "fit("):
        assert forbidden not in source.lower()
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert all(artifact[key] is False for key in (
        "market_data_acquired", "held_out_market_data_accessed", "held_out_outcomes_accessed",
        "forecast_evaluation_performed", "scientific_execution_authorized", "jigsaw_mutated",
    ))
