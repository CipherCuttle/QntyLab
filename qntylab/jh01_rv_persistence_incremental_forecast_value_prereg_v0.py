"""Static, outcome-blind contract for the JH01 forecast-value preregistration.

This module deliberately contains no data reader, network client, feature
builder, fitting routine, or forecast evaluator.  It validates only the frozen
protocol that a separately authorised phase may later implement.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


EXPERIMENT_ID = "JH01_RV_PERSISTENCE_INCREMENTAL_FORECAST_VALUE_PREREG_V0"
ARTIFACT_RELATIVE_PATH = Path("experiments/research/jh01_rv_persistence_incremental_forecast_value_v0/preregistration.json")
SOURCE_PIECE_ID = "JH01_RV_PERSISTENCE"
TEMPORAL_REPLICATION_PIECE_ID = "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_V0R1"
PROSPECTIVE_FIRST_DECISION = "2026-07-20T00:00:00Z"
PROSPECTIVE_LAST_DECISION = "2027-07-19T00:00:00Z"
PROSPECTIVE_OBSERVATION_COUNT = 365
REQUIRED_KILL_CONDITIONS = frozenset({
    "SOURCE_BINDING_MISMATCH", "OUTCOME_UNSEEN_CLAIM_UNPROVEN",
    "PRE_FREEZE_OUTCOME_ACCESS", "UNAUTHORIZED_DATA_ACQUISITION",
    "TRAINING_TEST_OVERLAP", "FUTURE_BAR_USED_AT_FORECAST_ORIGIN",
    "NON_POINT_IN_TIME_NORMALIZATION", "REFIT_USES_HELD_OUT_OUTCOME",
    "DUPLICATE_OR_REORDERED_FORECAST_ORIGIN", "MISSING_OBSERVATION",
    "BENCHMARK_INFORMATION_SET_MISMATCH", "PROTOCOL_DIGEST_MISMATCH",
    "UNAUTHORIZED_EXECUTION", "POST_FREEZE_MODEL_OR_METRIC_MUTATION",
})


class ContractError(ValueError):
    """Raised when the frozen, outcome-blind contract has drifted."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def contract_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes({k: v for k, v in value.items() if k != "preregistration_digest"})).hexdigest()


def load_preregistration(root: Path) -> dict[str, Any]:
    return json.loads((root / ARTIFACT_RELATIVE_PATH).read_text(encoding="utf-8"))


def validate(value: Mapping[str, Any]) -> None:
    if value.get("experiment_id") != EXPERIMENT_ID:
        raise ContractError("experiment identity mismatch")
    if value.get("preregistration_digest") != contract_digest(value):
        raise ContractError("preregistration digest mismatch")
    if value.get("status") != "NOT_EXECUTED" or value.get("implementation_execution_authorized") is not False:
        raise ContractError("execution authority mismatch")
    source = value.get("source_binding", {})
    if source.get("discovery_piece_identity") != SOURCE_PIECE_ID or source.get("temporal_replication_piece_identity") != TEMPORAL_REPLICATION_PIECE_ID:
        raise ContractError("source identity mismatch")
    synthesis = source.get("jigsaw_synthesis", {})
    if synthesis.get("replication_relation") != "TEMPORAL_REPLICATION_EXPLICITLY_ESTABLISHED" or synthesis.get("independence_status") != "INDEPENDENCE_NOT_ESTABLISHED" or synthesis.get("independent_replication_established") is not False:
        raise ContractError("synthesis binding mismatch")
    target = value.get("frozen_target", {})
    if target.get("realized_measure") != "REALIZED_VOLATILITY_NOT_VARIANCE" or target.get("decision_time") != "00:00:00Z" or target.get("forecast_horizon_hours") != 24 or target.get("observation_overlap") != "NON_OVERLAPPING_DAILY_OUTCOMES":
        raise ContractError("target semantics mismatch")
    models = value.get("model_set", {})
    if models.get("candidate", {}).get("model_id") != "C_JH01" or models.get("primary_benchmark") != "B1_NAIVE_PERSISTENCE" or models.get("B2", {}).get("status") != "REDUNDANT_WITH_CANDIDATE":
        raise ContractError("model-equivalence contract mismatch")
    evaluation = value.get("evaluation_design", {})
    if evaluation.get("training_policy") != "EXPANDING_WINDOW" or evaluation.get("prospective_holdout", {}).get("first_decision") != PROSPECTIVE_FIRST_DECISION or evaluation.get("prospective_holdout", {}).get("last_decision") != PROSPECTIVE_LAST_DECISION or evaluation.get("prospective_holdout", {}).get("required_valid_origins") != PROSPECTIVE_OBSERVATION_COUNT:
        raise ContractError("prospective evaluation schedule mismatch")
    testing = value.get("loss_and_testing", {})
    if testing.get("primary_loss") != "MSE_ON_UNTRANSFORMED_RV24" or testing.get("primary_comparison") != "C_JH01_VS_B1_NAIVE_PERSISTENCE" or testing.get("primary_test", {}).get("method") != "CLARK_WEST_STYLE_ADJUSTED_MSPE_ONE_SIDED_HAC" or testing.get("materiality_gate", {}).get("minimum_relative_mse_reduction") != 0.05:
        raise ContractError("loss or primary comparison mismatch")
    if not REQUIRED_KILL_CONDITIONS.issubset(set(value.get("kill_conditions", ()) )):
        raise ContractError("kill conditions incomplete")
    if any(item is not False for item in value.get("outcome_blindness", {}).values()):
        raise ContractError("outcome-blindness breach declared")
    authority = value.get("authority", {})
    if not authority or any(item is not False for item in authority.values()):
        raise ContractError("downstream authority present")
