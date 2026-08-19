from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_incremental_forecast_value_prereg_v0 as prereg


ROOT = Path(__file__).resolve().parents[1]


def artifact() -> dict:
    return prereg.load_preregistration(ROOT)


def test_contract_is_static_and_validates_unchanged_parent_evidence() -> None:
    value = artifact()
    prereg.validate(value, ROOT)
    assert value["evaluation_architectures"]["selected"] == "A_EXPLORATORY_610_INCREMENTAL_FORECAST_TEST"
    assert value["evaluation_contract"]["required_evaluation_origins"] == 244
    assert value["contamination_contract"]["independent_confirmation_claimed"] is False


def test_feature_is_continuous_frozen_family_without_sign_rescue() -> None:
    feature = artifact()["feature_contract"]
    assert feature["primary_predictor"] == "CONTINUOUS_FUNDING_PRESSURE_ECDF_PERCENTILE"
    assert feature["representation"] == "CONTINUOUS"
    assert feature["state_bins_used_as_primary"] is False
    assert feature["sign_reversal_rescue"] == "PROHIBITED"
    assert feature["new_transforms_added"] == []


def test_har_is_the_single_primary_baseline_and_naive_is_context_only() -> None:
    models = artifact()["model_contract"]
    assert models["primary_baseline"]["model_id"] == "BASELINE_1_HAR_RV_1_7_30"
    assert models["augmented_model"]["model_id"] == "M1_HAR_RV_1_7_30_PLUS_FUNDING_PERCENTILE"
    assert models["secondary_contextual_baseline"]["model_id"] == "BASELINE_0_NAIVE_RV24_PERSISTENCE"
    assert models["secondary_contextual_baseline"]["inferential_role"] == "DESCRIPTIVE_ONLY_NO_RESCUE"


def test_primary_test_and_materiality_boundary_are_frozen() -> None:
    testing = artifact()["testing_contract"]
    assert testing["primary_loss"] == "MSE_ON_UNTRANSFORMED_RV24"
    assert testing["primary_test"] == {
        "method": "CLARK_WEST_ADJUSTED_MSPE_ONE_SIDED_HAC",
        "alternative": "M1_LOWER_FORECAST_LOSS_THAN_M0",
        "adjusted_difference": "d_t = e0_t^2 - e1_t^2 + (f0_t - f1_t)^2; positive favors M1",
        "hac": "BARTLETT_NEWEY_WEST_FIXED_LAG_5",
        "alpha": 0.05,
    }
    assert testing["materiality_gate"] == "NONE_JUSTIFIABLE"


def test_contract_digest_rejects_scientific_mutation() -> None:
    value = copy.deepcopy(artifact())
    value["model_contract"]["augmented_model"]["model_id"] = "M1_SIGNED_FUNDING"
    with pytest.raises(prereg.ContractError, match="preregistration digest mismatch"):
        prereg.validate(value, ROOT)


def test_no_execution_capability_or_machine_local_jh01_access() -> None:
    source = inspect.getsource(prereg)
    for forbidden in ("requests", "urllib", "pandas", "numpy", "csv", "fit(", "execute(", "/home/swirky/.local/state/qntylab"):
        assert forbidden not in source
    value = artifact()
    assert all(item is False for item in value["outcome_blindness"].values())
    assert all(item == "NONE" or item is False for item in value["authority"].values())


def test_parent_artifacts_are_byte_bound() -> None:
    value = artifact()
    for relative_path, expected_digest in value["source_binding"]["immutable_artifacts"].items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected_digest
