from __future__ import annotations

import copy
import hashlib
import inspect
from pathlib import Path

import pytest

from qntylab import jh01_rv_persistence_temporal_replication_prereg_v0 as prereg


ROOT = Path(__file__).resolve().parents[1]


def _artifact() -> dict:
    return prereg.load_preregistration(ROOT)


def test_source_binding_is_exact_and_authenticated() -> None:
    value = _artifact()
    prereg.validate(value)
    source = value["source_binding"]
    assert source["source_project_id"] == prereg.SOURCE_PROJECT_ID
    assert source["source_experiment_id"] == prereg.SOURCE_EXPERIMENT_ID
    assert source["source_piece_id"] == prereg.SOURCE_PIECE_ID
    assert source["source_preregistration_digest"] == prereg.SOURCE_PREREGISTRATION_DIGEST
    assert source["source_snapshot_id"] == prereg.SOURCE_SNAPSHOT_ID
    assert source["source_snapshot_digest"] == prereg.SOURCE_SNAPSHOT_DIGEST
    assert set(source["canonical_source_artifacts"]) == {
        "experiments/research/jigsaw_harvest_v0/preregistration.json",
        "experiments/research/jigsaw_harvest_v0/execution_result.json",
        "experiments/research/jigsaw_harvest_v0/result.json",
    }
    for relative_path, expected_digest in source["canonical_source_artifacts"].items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected_digest
    # jigsaw_index.json and eligibility.json are derived, intentionally-growing
    # artifacts (qntylab.jigsaw_index / qntylab.jigsaw_synthesis): they are
    # expected to gain new canonical pieces over time, including this very
    # replication's own frozen evidence piece added by the separately
    # Git-backed JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_JIGSAW_EVIDENCE_
    # IMPLEMENTATION_V0 phase. The recorded jigsaw_index_sha256 /
    # jigsaw_synthesis_eligibility_sha256 fields are this preregistration's
    # own frozen point-in-time attestation of what it was authored against,
    # not a live invariant those by-design-mutable files must satisfy
    # forever after -- pin them to their frozen recorded values (proving
    # preregistration.json's own embedded fields are untouched) rather than
    # re-hashing the current, legitimately-evolved files.
    assert source["jigsaw_source_identity"]["jigsaw_index_sha256"] == "b229b55862fa06445daba5b4ad2a65a72a57a44e3fefef879867b7be29cf46d9"
    assert source["jigsaw_source_identity"]["jigsaw_synthesis_eligibility_sha256"] == "451417fd48168b08fef3d609d97244f40540c57e1c8d34ef7a8def5d9b7e57cd"


def test_panel_and_fixed_temporal_window_are_exact() -> None:
    value = _artifact()
    assert tuple(value["ordered_universe"]) == prereg.UNIVERSE
    assert value["universe_count"] == 20
    assert value["universe_digest"] == prereg.universe_digest(prereg.UNIVERSE)
    schedule = value["decision_schedule"]
    assert (schedule["first_decision"], schedule["last_decision"], schedule["decision_count"]) == (
        prereg.FIRST_DECISION, prereg.LAST_DECISION, 365,
    )
    assert (schedule["frequency"], schedule["decision_time"]) == ("P1D", "00:00:00Z")


def test_temporal_disjointness_and_coverage_are_mechanically_bound() -> None:
    value = _artifact()
    independence = value["independence_contract"]
    assert independence["replication_decision_dates_overlap_discovery"] is False
    assert independence["replication_outcome_dates_overlap_discovery"] is False
    assert prereg.derive_required_bar_coverage(prereg.FIRST_DECISION, prereg.LAST_DECISION) == (
        prereg.REQUIRED_FIRST_BAR_OPEN,
        prereg.REQUIRED_LAST_BAR_OPEN,
    )
    assert value["required_raw_coverage"]["first_bar_open"] == prereg.REQUIRED_FIRST_BAR_OPEN
    assert value["required_raw_coverage"]["last_bar_open"] == prereg.REQUIRED_LAST_BAR_OPEN


def test_measurement_and_inference_preserve_jh01_semantics() -> None:
    value = _artifact()
    measurement = value["measurement"]
    assert measurement["return_semantics"].startswith("r_i,h = log")
    assert "(1/20)" in measurement["market_return"]
    assert measurement["feature"] == "RV24_prior,t = sqrt(sum_{h=t-23}^{t} r_m,h^2)."
    assert measurement["outcome"] == "RV24_future,t = sqrt(sum_{h=t+1}^{t+24} r_m,h^2)."
    inference = value["inference"]
    assert inference["estimator"] == "OLS_WITH_INTERCEPT"
    assert inference["hypothesis_count"] == 1
    assert prereg.hac_lag(365) == inference["hac_lag"] == 5
    assert inference["holm_adjustment"] == "NOT_USED"
    assert inference["effect_size_ratio_threshold"] == "NOT_USED"
    assert inference["pooling_or_meta_analysis"] == "PROHIBITED"


def test_fail_closed_panel_independence_and_authority_contracts() -> None:
    value = _artifact()
    assert "BLOCKED_BY_INPUT_CONTRACT" in value["panel_failure_semantics"]
    assert value["independence_contract"]["self_declaration_sufficient_for_independence"] is False
    assert value["independence_contract"]["same_history_reproduction_counts_as_replication"] is False
    assert value["jigsaw_index_eligibility"].startswith("NOT_A_JIGSAW_EVIDENCE_PIECE")
    assert all(item == "NONE" for item in value["authority"].values())
    assert value["outcome_blindness"] == {
        "post_discovery_market_outcomes_read": False,
        "replication_market_data_accessed": False,
        "replication_features_computed": False,
        "replication_outcomes_computed": False,
        "replication_regression_run": False,
        "scientific_result_exists": False,
    }
    shortened = copy.deepcopy(value)
    shortened["ordered_universe"] = shortened["ordered_universe"][:-1]
    shortened["universe_count"] = 19
    shortened["universe_digest"] = prereg.universe_digest(shortened["ordered_universe"])
    shortened["preregistration_digest"] = prereg.contract_digest(shortened)
    with pytest.raises(prereg.ContractError, match="ordered universe mismatch"):
        prereg.validate(shortened)


def test_classification_kill_conditions_and_non_execution_are_frozen() -> None:
    value = _artifact()
    assert set(value["classification"]) == {
        "REPLICATED_WITHIN_FROZEN_TEMPORAL_SCOPE",
        "OPPOSITE_DIRECTION_WITHIN_FROZEN_TEMPORAL_SCOPE",
        "INCONCLUSIVE",
        "BLOCKED_BY_INPUT_CONTRACT",
    }
    assert prereg.REQUIRED_KILL_CONDITIONS.issubset(value["kill_conditions"])
    artifact_dir = ROOT / prereg.ARTIFACT_RELATIVE_PATH.parent
    # No new scientific execution occurred at this path: neither a raw
    # execution result nor a materialization manifest was ever authorized or
    # created directly under the experiment root.
    assert not (artifact_dir / "execution_result.json").exists()
    assert not (artifact_dir / "materialization_manifest.json").exists()
    # result.json (the canonical Jigsaw evidence piece) is now expected to
    # exist -- but only because JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_
    # JIGSAW_EVIDENCE_IMPLEMENTATION_V0 was separately Git-backed-authorized
    # (via JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_JIGSAW_EVIDENCE_
    # AUTHORIZATION_V0) to create exactly this one evidence representation
    # from the already-frozen V0R1 result, with no new scientific
    # computation. Assert it is exactly that authorized artifact, not an
    # unbounded or fabricated one.
    result_path = artifact_dir / "result.json"
    assert result_path.exists()
    import json as _json

    result = _json.loads(result_path.read_text(encoding="utf-8"))
    assert result["schema_version"] == "jigsaw-evidence-piece-v0"
    assert result["source_piece_id"] == prereg.SOURCE_PIECE_ID
    assert result["replication_of_piece_identity"] == prereg.SOURCE_PIECE_ID
    assert result["real_experiment_recomputed"] is False
    provenance = result["provenance"]
    assert provenance["source_execution_result_digest"] == "3dba3a0f0700a768e981dcecfe5793532bcd4bc1db7dc4dbcd9e4806a722c5c1"
    assert provenance["provenance_correction_digest"] == "c396b6cc53d92a87c7dfa45920c05a772bb447c1f98de5bdbbae065e255b7154"
    assert provenance["post_start_repair"] is True
    assert provenance["pristine_first_execution"] is False


def test_contract_digest_is_deterministic_and_detects_scientific_mutation() -> None:
    value = _artifact()
    assert prereg.contract_digest(value) == prereg.contract_digest(copy.deepcopy(value)) == value["preregistration_digest"]
    mutated = copy.deepcopy(value)
    mutated["measurement"]["return_semantics"] = "simple returns"
    with pytest.raises(prereg.ContractError, match="digest mismatch"):
        prereg.validate(mutated)


def test_validator_has_no_market_data_or_execution_path() -> None:
    source = inspect.getsource(prereg)
    for forbidden in ("requests", "urllib", "csv", "pandas", "numpy", "data/", "materialize(", "execute("):
        assert forbidden not in source
