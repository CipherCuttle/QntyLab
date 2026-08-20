import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/semantics_preserving_executor_successor_authorization_v0"
AUTHORIZATION = json.loads((ARTIFACT_DIR / "authorization.json").read_text(encoding="utf-8"))
DESIGN = json.loads((ARTIFACT_DIR / "successor_design.json").read_text(encoding="utf-8"))
CLOSURE = json.loads((ARTIFACT_DIR / "closure.json").read_text(encoding="utf-8"))


def test_authorization_is_blocked_and_grants_no_authority():
    assert AUTHORIZATION["state"] == "CLOSED_BLOCKED"
    assert AUTHORIZATION["authorization_created"] is False
    assert AUTHORIZATION["later_implementation_phases_authorized"] == 0
    assert AUTHORIZATION["scientific_execution_authorized"] is False
    assert CLOSURE["successor_implemented"] is False
    assert CLOSURE["evaluation_origins_consumed"] == 0
    assert CLOSURE["outcome_firewall"]["router_authority"] == "NONE"
    assert CLOSURE["outcome_firewall"]["qnty_authority"] == "NONE"
    assert CLOSURE["outcome_firewall"]["trading_authority"] == "NONE"
    assert CLOSURE["outcome_firewall"]["capital_authority"] == "NONE"


def test_historical_identity_and_frozen_bindings_are_preserved():
    bindings = AUTHORIZATION["frozen_bindings"]
    assert bindings["historical_implementation_candidate"] == "f6f12994d65c3dfeaf7839de560e58ad99547c62"
    assert bindings["historical_executor_sha256"] == hashlib.sha256(
        (ROOT / "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py").read_bytes()
    ).hexdigest()
    assert bindings["preregistration_file_sha256"] == hashlib.sha256(
        (ROOT / "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/preregistration.json").read_bytes()
    ).hexdigest()
    assert bindings["historical_source_mutated"] is False
    assert bindings["preregistered_scientific_semantics_changed"] is False


def test_static_design_rejects_all_four_non_equivalent_routes():
    rejected = DESIGN["rejected_alternatives"]
    assert set(rejected) == {
        "mutate_historical_source_to_extract_core",
        "duplicate_har_ols_forecast_and_statistics",
        "pass_real_rows_as_synthetic",
        "reuse_v2_one_shot_result",
    }
    gate = AUTHORIZATION["design_gate"]
    assert gate["one_shared_scientific_core_possible_without_historical_mutation"] is False
    assert gate["algorithm_duplication_required_under_immutable_history"] is True
    assert gate["v2_result_contract_substitution_allowed"] is False


def test_frozen_executor_has_no_real_loader_or_claim_path():
    source_path = ROOT / "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    attrs = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    forbidden = {
        "load_verified_frozen_evidence",
        "claim_authorization_once",
        "execute_authorized_frozen_experiment_v2",
        "compute_frozen_experiment",
    }
    assert not forbidden.intersection(names | attrs)

    run = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "run_incremental_forecast_evaluation"
    )
    calls = {
        node.func.id
        for node in ast.walk(run)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "require_authorized_execution_mode" in calls
    assert "fit_ordinary_least_squares" in calls
    assert "clark_west_statistic" in calls
    assert DESIGN["static_finding"]["scientific_assembly_is_inside_guarded_entrypoint"] is True
    assert DESIGN["static_finding"]["separate_pure_evaluation_core_exists"] is False


def test_required_differential_plan_is_complete_and_outcome_blind():
    plan = DESIGN["required_differential_test_plan_if_reopened"]
    assert len(plan) >= 16
    assert any("pseudo-random valid" in item for item in plan)
    assert any("malformed" in item for item in plan)
    assert any("frozen synthetic digest" in item for item in plan)
    firewall = AUTHORIZATION["outcome_firewall"]
    assert firewall["real_outcome_access"] is False
    assert firewall["scientific_execution"] is False
    assert firewall["evaluation_origins_consumed"] == 0
    assert firewall["real_forecast_rows_constructed"] is False
    assert firewall["claim_consumed"] is False
