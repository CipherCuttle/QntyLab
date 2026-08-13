from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from qntylab import jh01_rv_persistence_incremental_forecast_value_prereg_v0 as prereg


ROOT = Path(__file__).resolve().parents[1]


def artifact() -> dict:
    return prereg.load_preregistration(ROOT)


def test_static_contract_is_deterministic_and_outcome_blind() -> None:
    value = artifact()
    prereg.validate(value)
    assert prereg.contract_digest(value) == value["preregistration_digest"]
    assert all(item is False for item in value["outcome_blindness"].values())
    source = inspect.getsource(prereg)
    for forbidden in ("requests", "urllib", "pandas", "numpy", "csv", "execute(", "fit("):
        assert forbidden not in source


def test_source_bindings_are_exact_current_file_hashes() -> None:
    value = artifact()
    for path, digest in value["source_binding"]["immutable_artifacts"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    synthesis = value["source_binding"]["jigsaw_synthesis"]
    assert synthesis == {
        "replication_relation": "TEMPORAL_REPLICATION_EXPLICITLY_ESTABLISHED",
        "independence_status": "INDEPENDENCE_NOT_ESTABLISHED",
        "independent_replication_established": False,
        "allowed_synthesis": "TEMPORAL_REPLICATION_CONTEXT_ONLY",
    }


def test_target_and_model_equivalence_are_frozen() -> None:
    value = artifact()
    assert value["frozen_target"]["rv24_prior_definition"] == "RV24_prior,t = sqrt(sum_{h=t-23}^{t} r_m,h^2)."
    assert value["frozen_target"]["rv24_future_definition"] == "RV24_future,t = sqrt(sum_{h=t+1}^{t+24} r_m,h^2)."
    assert value["frozen_target"]["observation_overlap"] == "NON_OVERLAPPING_DAILY_OUTCOMES"
    assert value["model_set"]["B2"]["status"] == "REDUNDANT_WITH_CANDIDATE"
    assert value["model_set"]["primary_benchmark"] == "B1_NAIVE_PERSISTENCE"
    assert value["loss_and_testing"]["excluded_loss"].startswith("QLIKE_EXCLUDED")


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("loss_and_testing", "primary_loss"), "QLIKE"),
        (("model_set", "primary_benchmark"), "B0_HISTORICAL_MEAN"),
        (("evaluation_design", "prospective_holdout", "first_decision"), "2025-07-20T00:00:00Z"),
    ],
)
def test_digest_detects_contract_mutation(path: tuple[str, ...], replacement: object) -> None:
    value = copy.deepcopy(artifact())
    cursor = value
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = replacement
    with pytest.raises(prereg.ContractError, match="digest mismatch"):
        prereg.validate(value)


def test_adversarial_integrity_controls_and_kill_switches_are_present() -> None:
    value = artifact()
    expected = {
        "FUTURE_BAR_USED_AT_FORECAST_ORIGIN", "NON_POINT_IN_TIME_NORMALIZATION",
        "REFIT_USES_HELD_OUT_OUTCOME", "TRAINING_TEST_OVERLAP",
        "BENCHMARK_INFORMATION_SET_MISMATCH", "DUPLICATE_OR_REORDERED_FORECAST_ORIGIN",
        "MISSING_OBSERVATION", "OUTCOME_UNSEEN_CLAIM_UNPROVEN",
    }
    assert expected.issubset(value["kill_conditions"])
    assert value["evaluation_design"]["prospective_holdout"]["required_valid_origins"] == 365
    assert "new horizon" in value["prohibited_rescues"]
    assert "new subgroup or asset panel" in value["prohibited_rescues"]


def test_append_only_ledger_exposes_preregistration_as_blocked_pending_prospective_input() -> None:
    candidates = [json.loads(line) for line in (ROOT / "experiments/research/candidates.jsonl").read_text().splitlines() if line]
    decisions = [json.loads(line) for line in (ROOT / "experiments/research/decisions.jsonl").read_text().splitlines() if line]
    candidate = next(item for item in candidates if item["candidate_id"] == "CANDIDATE_JH01_RV_PERSISTENCE_INCREMENTAL_FORECAST_VALUE_V0")
    decision = next(item for item in decisions if item["candidate_id"] == candidate["candidate_id"])
    assert candidate["variant_id"] == "variant_7ae666268986548df0cac7c2"
    assert candidate["parameters"]["execution_authorized"] is False
    assert decision["status"] == "BLOCKED"
    assert "PROSPECTIVE_HOLDOUT_UNMATERIALIZED" in decision["reason_codes"]
    for path, digest in decision["evidence_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
