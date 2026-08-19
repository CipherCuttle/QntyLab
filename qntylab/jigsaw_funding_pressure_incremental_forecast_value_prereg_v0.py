"""Static, outcome-blind contract for the funding incremental forecast design.

This module validates only the preregistration.  It deliberately contains no
data reader, network client, feature builder, estimator, or evaluator.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_PREREGISTRATION_V0"
EXPERIMENT_ID = PROJECT_ID
CANDIDATE_ID = "CANDIDATE_FUNDING_PRESSURE_INCREMENTAL_RV_FORECAST_VALUE_V0"
ARTIFACT = Path("experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/preregistration.json")
FIRST_FORECAST_ORIGIN = "2024-10-19T00:00:00Z"
LAST_FORECAST_ORIGIN = "2025-06-19T00:00:00Z"
REQUIRED_EVALUATION_ORIGINS = 244
MINIMUM_TRAINING_ORIGINS = 365


class ContractError(ValueError):
    """Raised when the frozen design contract has drifted."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def contract_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_bytes({key: item for key, item in value.items() if key != "preregistration_digest"})
    ).hexdigest()


def load_preregistration(root: Path) -> dict[str, Any]:
    return json.loads((root / ARTIFACT).read_text(encoding="utf-8"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def validate(value: Mapping[str, Any], root: Path = Path(".")) -> None:
    _require(value.get("project_id") == PROJECT_ID, "project identity mismatch")
    _require(value.get("experiment_id") == EXPERIMENT_ID, "experiment identity mismatch")
    _require(value.get("candidate_id") == CANDIDATE_ID, "candidate identity mismatch")
    _require(value.get("status") == "PREREGISTERED_NOT_EXECUTED", "status is not design-only")
    _require(value.get("preregistration_digest") == contract_digest(value), "preregistration digest mismatch")

    parent = value.get("parent_binding", {})
    _require(parent.get("historical_experiment") == "JIGSAW_FUNDING_PRESSURE_VOLATILITY_V0", "historical parent mismatch")
    _require(parent.get("historical_disposition") == "NOT_SUPPORTED_UNDER_FROZEN_SPECIFICATION", "historical disposition mismatch")
    _require(parent.get("reverse_directional_hypothesis") == "NO", "reverse-direction rescue enabled")
    _require(parent.get("observed_contrast") == "-0.0002003650803348647161725358990165653289511751324777", "historical contrast mismatch")
    _require(parent.get("historical_daily_decisions") == 610, "historical decision count mismatch")

    feature = value.get("feature_contract", {})
    _require(feature.get("feature_id") == "FUNDING_PRESSURE", "feature identity mismatch")
    _require(feature.get("primary_predictor") == "CONTINUOUS_FUNDING_PRESSURE_ECDF_PERCENTILE", "primary predictor mismatch")
    _require(feature.get("representation") == "CONTINUOUS", "funding predictor is not continuous")
    _require(feature.get("formula_digest") == "sha256:c0e23ef865e746ec125455d2af4daddbf24b9f4b970809b52f693ccdee9c41f1", "feature formula mismatch")
    _require(feature.get("sign_reversal_rescue") == "PROHIBITED", "sign reversal rescue enabled")
    _require(feature.get("new_transforms_added") == [], "new funding transform added")
    _require(feature.get("state_bins_used_as_primary") is False, "binned state used as primary")

    outcome = value.get("outcome_contract", {})
    _require(outcome.get("outcome_id") == "FUTURE_MARKET_WIDE_REALIZED_VOLATILITY", "outcome identity mismatch")
    _require(outcome.get("formula_digest") == "sha256:b551dfade01104c63c5909b8d2b185c9513a4a84845edf534575cfb4818ec3ad", "outcome formula mismatch")
    _require(outcome.get("forward_horizon_hours") == 24 and outcome.get("annualization") == "NONE", "outcome horizon drift")
    _require(outcome.get("missingness") == "FAIL_CLOSED_NO_IMPUTATION_OR_GAP_BRIDGING", "missingness drift")

    architecture = value.get("evaluation_architectures", {})
    _require(architecture.get("selected") == "A_EXPLORATORY_610_INCREMENTAL_FORECAST_TEST", "architecture selection mismatch")
    _require(architecture.get("A", {}).get("classification") == "EXPLORATORY_FOLLOW_UP_WITH_PRIOR_OUTCOME_EXPOSURE", "A classification mismatch")
    _require(architecture.get("B", {}).get("outcome_blind_feasibility") == "NOT_ESTABLISHED", "B feasibility was overstated")
    _require(architecture.get("C", {}).get("marginal_information_value") == "LOWER_THAN_A_PER_COST_AND_DUPLICATES_JH01_PURPOSE", "C comparison drift")
    _require(architecture.get("D", {}).get("decision") == "REJECTED_BECAUSE_A_IS_A_BOUNDED_LOW_COST_DISCRIMINATOR", "D decision mismatch")

    models = value.get("model_contract", {})
    _require(models.get("primary_baseline", {}).get("model_id") == "BASELINE_1_HAR_RV_1_7_30", "primary baseline mismatch")
    _require(models.get("augmented_model", {}).get("model_id") == "M1_HAR_RV_1_7_30_PLUS_FUNDING_PERCENTILE", "augmented model mismatch")
    _require(models.get("secondary_contextual_baseline", {}).get("model_id") == "BASELINE_0_NAIVE_RV24_PERSISTENCE", "secondary baseline mismatch")
    _require(models.get("feature_search") is False and models.get("model_search") is False and models.get("lag_search") is False, "model or feature search enabled")

    evaluation = value.get("evaluation_contract", {})
    _require(evaluation.get("training_scheme") == "EXPANDING_WINDOW", "training scheme mismatch")
    _require(evaluation.get("minimum_training_origins") == MINIMUM_TRAINING_ORIGINS, "minimum training history mismatch")
    _require(evaluation.get("first_forecast_origin") == FIRST_FORECAST_ORIGIN, "first origin mismatch")
    _require(evaluation.get("last_forecast_origin") == LAST_FORECAST_ORIGIN, "last origin mismatch")
    _require(evaluation.get("required_evaluation_origins") == REQUIRED_EVALUATION_ORIGINS, "evaluation origin count mismatch")
    _require(evaluation.get("refit_cadence") == "EVERY_DAILY_ORIGIN", "refit cadence mismatch")
    _require(evaluation.get("training_target_cutoff") == "TARGET_COMPLETION_TIME < FORECAST_ORIGIN", "label cutoff mismatch")
    _require(evaluation.get("missingness") == "FAIL_CLOSED_ANY_MISSING_ROW_BLOCKS_VALID_EVALUATION", "evaluation missingness drift")

    testing = value.get("testing_contract", {})
    _require(testing.get("primary_loss") == "MSE_ON_UNTRANSFORMED_RV24", "primary loss mismatch")
    _require(testing.get("primary_test", {}).get("method") == "CLARK_WEST_ADJUSTED_MSPE_ONE_SIDED_HAC", "primary test mismatch")
    _require(testing.get("primary_test", {}).get("hac") == "BARTLETT_NEWEY_WEST_FIXED_LAG_5", "HAC convention mismatch")
    _require(testing.get("primary_test", {}).get("alpha") == 0.05, "alpha mismatch")
    _require(testing.get("materiality_gate") == "NONE_JUSTIFIABLE", "materiality gate drift")

    contamination = value.get("contamination_contract", {})
    _require(contamination.get("old_610_classification") == "PRIOR_EXPOSED_DEVELOPMENT_AND_EXPLORATORY_ONLY", "prior exposure classification mismatch")
    _require(contamination.get("independent_confirmation_claimed") is False, "independent confirmation claimed")
    _require(contamination.get("post_result_rescue_search") == "PROHIBITED", "post-result rescue enabled")

    blindness = value.get("outcome_blindness", {})
    _require(all(item is False for item in blindness.values()), "design phase accessed protected outcomes or executed")
    authority = value.get("authority", {})
    _require(all(item == "NONE" or item is False for item in authority.values()), "downstream authority present")

    for relative_path, expected_digest in value.get("source_binding", {}).get("immutable_artifacts", {}).items():
        actual = hashlib.sha256((root / relative_path).read_bytes()).hexdigest()
        _require(actual == expected_digest, f"immutable source changed: {relative_path}")


if __name__ == "__main__":
    validate(load_preregistration(Path(".")))
