from __future__ import annotations

import copy
import hashlib
import inspect
import json
from datetime import timedelta
from pathlib import Path

import pytest

from qntylab import jh01_rv_persistence_incremental_forecast_value_prereg_v1 as prereg


ROOT = Path(__file__).resolve().parents[1]
V0 = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v0"


def artifact() -> dict:
    return prereg.load_preregistration(ROOT)


def test_v1_is_new_exact_365_origin_future_protocol() -> None:
    value = artifact()
    prereg.validate(value)
    schedule = prereg.origins()
    assert len(schedule) == 365
    assert schedule[0].isoformat().replace("+00:00", "Z") == "2026-09-15T00:00:00Z"
    assert schedule[-1].isoformat().replace("+00:00", "Z") == "2027-09-14T00:00:00Z"
    assert all(later - earlier == timedelta(days=1) for earlier, later in zip(schedule, schedule[1:]))


def test_v0_is_immutable_terminal_non_result_and_v1_is_distinct() -> None:
    value = artifact()
    closure = json.loads((V0 / "input_materialization_authorization_v0.json").read_text())
    assert value["candidate_id"] != "CANDIDATE_JH01_RV_PERSISTENCE_INCREMENTAL_FORECAST_VALUE_V0"
    assert closure["state"] == "CLOSED_BLOCKED"
    assert closure["prospective_integrity"] == "FAILED_FROZEN_START_ALREADY_ELAPSED_WITHOUT_PERSISTED_FORECAST"
    assert closure["forecast_evaluation_performed"] is False
    assert hashlib.sha256((V0 / "preregistration.json").read_bytes()).hexdigest() == "20bd204a0a78ef5810e7350e055d7ebb4e1368381ac65fda7acf4476a6068d1b"


def test_scientific_contract_is_equivalent_to_v0_except_timing_governance() -> None:
    v0 = json.loads((V0 / "preregistration.json").read_text())
    v1 = artifact()
    for key in ("model_set", "loss_and_testing", "classification", "search_accounting", "prohibited_rescues"):
        assert v1[key] == v0[key]
    for key in ("return_construction", "rv24_prior_definition", "rv24_future_definition", "realized_measure", "decision_time", "safe_known_after", "forecast_horizon_hours", "target_transformation", "annualization", "panel_aggregation", "missing_data_policy", "observation_overlap"):
        assert v1["frozen_target"][key] == v0["frozen_target"][key]
    assert v1["scientific_diff_from_v0"] == "TIMING_AND_PROSPECTIVE_GOVERNANCE_ONLY"
    assert v1["evaluation_design"]["training_policy"] == v0["evaluation_design"]["training_policy"] == "EXPANDING_WINDOW"
    assert v1["evaluation_design"]["refit_policy"] == v0["evaluation_design"]["refit_policy"]
    assert v1["evaluation_design"]["initial_training_history_boundary"]["latest_eligible_training_origin"] == "2026-09-13T00:00:00Z"


def test_persistence_boundary_and_sealed_evaluation_are_fail_closed() -> None:
    value = artifact()
    persistence = value["forecast_persistence_contract"]
    assert persistence["feature_information_cutoff"] == "MAX_INPUT_BAR_CLOSE <= t"
    assert persistence["open_or_partial_future_bars"] == "PROHIBITED"
    assert persistence["persistence_window"] == "t <= persistence_time < t + 1 hour"
    assert value["sealed_evaluation"]["interim_scientific_evaluation"] == "PROHIBITED"
    required = {"FORECAST_PERSISTED_BEFORE_ORIGIN", "FORECAST_PERSISTED_AT_OR_AFTER_FIRST_FUTURE_BAR_CLOSE", "SOURCE_BAR_AFTER_FORECAST_ORIGIN", "OPEN_OR_PARTIAL_FUTURE_BAR_USED", "UNAUTHORIZED_INTERIM_EVALUATION"}
    assert required.issubset(value["kill_conditions"])


def test_sources_are_digest_bound_without_pinning_mutable_global_aggregate() -> None:
    value = artifact()
    for path, digest in value["source_binding"]["immutable_artifacts"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    binding = value["source_binding"]
    assert binding["mutable_global_synthesis_aggregate_byte_pinned"] is False
    assert binding["jigsaw_pair_attestation_at_freeze"] == {"replication_relation": "TEMPORAL_REPLICATION_EXPLICITLY_ESTABLISHED", "independence_status": "INDEPENDENCE_NOT_ESTABLISHED", "independent_replication_established": False, "allowed_synthesis": "TEMPORAL_REPLICATION_CONTEXT_ONLY"}


def test_lead_time_and_no_execution_capability() -> None:
    value = artifact()
    lead = value["preregistration_lead_time"]
    assert lead["minimum_canonical_prereg_lead_days"] == 14
    assert lead["canonical_freeze_deadline"] == "2026-09-01T00:00:00Z"
    assert lead["eligibility_at_draft_freeze"] == "ELIGIBLE_PENDING_CANONICAL_MERGE_BY_DEADLINE"
    assert lead["canonical_freeze_gate"] == "MANDATORY_BEFORE_CANONICAL_MERGE"
    assert prereg.canonical_freeze_is_eligible("2026-09-01T00:00:00Z") is True
    assert prereg.canonical_freeze_is_eligible("2026-09-01T00:00:01Z") is False
    prereg.validate_canonical_freeze(value, "2026-09-01T00:00:00Z")
    with pytest.raises(prereg.ContractError, match="PREREG_CANONICAL_FREEZE_TOO_LATE"):
        prereg.validate_canonical_freeze(value, "2026-09-01T00:00:01Z")
    assert all(item is False for item in value["outcome_blindness"].values())
    assert all(item is False for item in value["authority"].values())
    source = inspect.getsource(prereg)
    for forbidden in ("requests", "urllib", "pandas", "numpy", "csv", "execute(", "fit("):
        assert forbidden not in source


def test_exact_ordered_panel_is_bound_to_immutable_discovery_source() -> None:
    value = artifact()
    source = json.loads((ROOT / "experiments/research/jigsaw_harvest_v0/preregistration.json").read_text())
    panel = value["frozen_target"]["ordered_20_symbol_panel"]
    assert panel == source["universe"]
    assert hashlib.sha256(prereg.canonical_bytes(panel)).hexdigest() == value["frozen_target"]["ordered_20_symbol_panel_sha256"]


def test_digest_rejects_post_freeze_scientific_or_timing_mutation() -> None:
    value = copy.deepcopy(artifact())
    value["model_set"]["primary_benchmark"] = "B0_HISTORICAL_MEAN"
    with pytest.raises(prereg.ContractError, match="digest mismatch"):
        prereg.validate(value)
