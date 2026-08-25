import hashlib
import json
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "experiments/research/qntyspot_ink_shadow_performance_authorization_v0/authorization.json"
PROJECTS_PATH = ROOT / "docs/state/projects.toml"


def load_auth():
    return json.loads(AUTH_PATH.read_text(encoding="utf-8"))


def load_project():
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return next(row for row in registry["project"] if row["project_id"] == "QNTYSPOT_INK_SHADOW_PERFORMANCE_AUTHORIZATION_V0")


def load_active_project():
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return next(row for row in registry["project"] if row["project_id"] == "QNTYSPOT_INK_SHADOW_PERFORMANCE_V0")


def test_branch_local_candidate_does_not_self_authorize():
    auth = load_auth()
    assert auth["phase_state"] == "PLANNED_NOT_AUTHORIZED"
    assert auth["candidate_state"] == "ACTIVE_CANDIDATE"
    assert auth["canonicalization_status"] == "CANDIDATE_NOT_CANONICAL"
    assert auth["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert auth["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert auth["implementation_authorized"] is False
    assert auth["authorization_effective_on_branch"] is False
    gate = auth["canonical_merge_gate"]
    assert gate["candidate_branch_is_authority"] is False
    assert gate["branch_local_candidate_does_not_self_authorize"] is True
    assert gate["exact_candidate_commit_must_be_ancestor_of_canonical_master"] is True


def test_canonical_registry_closes_authorization_and_activates_exactly_one_successor():
    authorization = load_project()
    active = load_active_project()
    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["candidate_state"] == "CANONICAL_AUTHORIZATION_EFFECTIVE"
    assert authorization["canonicalization_status"] == "EXACT_CANONICAL_MERGE_VERIFIED"
    assert authorization["authorization_candidate_commit"] == "b0c132468d4e637fa0d3197044f588081ba025e1"
    assert authorization["authorization_canonical_merge"] == "112e004ff516ef141a4dcf661d9ae4fe454aa85c"
    assert active["state"] == "ACTIVE"
    assert active["governing_authorization_project_id"] == authorization["project_id"]
    assert active["governing_authorization_canonical_merge"] == "112e004ff516ef141a4dcf661d9ae4fe454aa85c"
    assert active["qntyspot_source_commit"] == "b9a84c59bd43e7697ee970d2a7571647e5de4501"
    assert active["historical_data_cutoff_utc"] == "2026-08-25T17:02:37Z"
    assert active["implementation_authorized"] is False
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    assert [row for row in registry["project"] if row["state"] == "ACTIVE"] == [active]


def test_exact_canonical_base_binding():
    auth = load_auth()
    expected = "a4738278f42f961ad2f2470fefff6688ccde6bb6"
    assert auth["canonical_merge_gate"]["canonical_base_sha"] == expected
    assert auth["canonical_source_identity"]["canonical_commit"] == expected
    assert subprocess.run(
        ["git", "merge-base", "--is-ancestor", expected, "HEAD"],
        cwd=ROOT,
        check=False,
    ).returncode == 0


def test_exact_qntyspot_source_binding():
    source = load_auth()["qntyspot_source_binding"]
    assert source["canonical_commit"] == "b9a84c59bd43e7697ee970d2a7571647e5de4501"
    assert source["ink_chain_id"] == 57073
    assert source["base_token"] == {
        "symbol": "KRAKMASK",
        "address": "0x32bcb803f696c99eb263d60a05cafd8689026575",
        "decimals": 18,
    }
    assert source["quote_token"]["address"] == "0x4200000000000000000000000000000000000006"
    assert source["inkyswap_v2_factory"] == "0x458c5d5b75ccba22651d2c5b61cb1ea1e0b0f95d"
    assert source["inkyswap_v2_pool"] == "0xed11ed4b195e84ba9b74c4d6ce13b7a43b354264"
    assert source["deployed_runtime_bytecode_identity"] == {
        "identity_type": "RUNTIME_BYTECODE_SHA256",
        "sha256": "c5c2b764b882b8c18004fe5ce77d8649dd8c26cea265f663b16196708d22bf20",
    }
    assert source["v2_fee_semantics"] == {
        "fee_numerator": 997,
        "fee_denominator": 1000,
        "fee_decimal": "0.003",
        "description": "fixed 0.3% Uniswap V2-style fee",
    }
    assert source["qntyspot_mutation_authorized"] is False
    assert source["runtime_cross_repository_imports_authorized"] is False


def test_future_phase_is_unique_and_cutoff_is_frozen():
    auth = load_auth()
    future = auth["authorized_future_phase"]
    assert future["project_id"] == "QNTYSPOT_INK_SHADOW_PERFORMANCE_V0"
    assert future["project_id"] != auth["project_id"]
    assert future["exactly_one_future_phase"] is True
    assert future["future_phase_count"] == 1
    assert future["historical_data_cutoff_utc"] == "2026-08-25T17:02:37Z"
    assert future["strictly_later_data_belongs_only_to"] == "FUTURE_PROSPECTIVE_LINEAGE"
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    ids = [row["project_id"] for row in registry["project"]]
    assert ids.count(auth["project_id"]) == 1
    assert ids.count(future["project_id"]) == 1
    assert load_active_project()["project_id"] == future["project_id"]


def test_future_phase_anti_leakage_and_baselines_are_complete():
    future = load_auth()["authorized_future_phase"]
    assert future["anti_leakage_contract"]["required_order"] == [
        "PREREGISTER",
        "DEFINE_CHRONOLOGICAL_DEV_OUTER",
        "ACQUIRE_DEV",
        "SELECT_AND_FREEZE_EXACTLY_ONE_CANDIDATE",
        "ONLY_THEN_ACQUIRE_OUTER",
        "EXACTLY_ONE_OUTER_EVALUATION",
    ]
    assert future["anti_leakage_contract"]["outer_reuse_after_results"] is False
    assert future["anti_leakage_contract"]["candidate_alteration_after_freeze"] is False
    assert future["anti_leakage_contract"]["silent_parameter_expansion"] is False
    assert future["anti_leakage_contract"]["outer_rerun_authorized"] is False
    assert future["required_baselines"] == [
        "HOLD_WETH",
        "BUY_AND_HOLD_KRAKMASK",
        "PERIODIC_DCA",
        "DUMB_SYMMETRIC_GRID",
        "SELECTED_QNTYSPOT_LADDER",
    ]
    assert future["baseline_contract"] == {
        "identical_initial_wealth": True,
        "identical_executable_market_semantics": True,
    }
    assert set(future["required_costs"]) == {
        "EXACT_AMM_FEE",
        "INTENDED_SIZE_PRICE_IMPACT",
        "EXPLICIT_GAS_TREATMENT_AND_SENSITIVITY",
        "TURNOVER",
    }
    assert future["gross_price_movement_as_strategy_pnl"] is False


def test_scientific_firewall_and_zero_execution():
    auth = load_auth()
    firewall = auth["scientific_firewall"]
    assert firewall["trading_authority"] == "NONE"
    assert firewall["capital_authority"] == "NONE"
    assert firewall["qntyspot_execution_authority"] == "NONE"
    assert firewall["signing_authority"] == "NONE"
    assert firewall["promotion_authority"] == "NONE"
    for key in (
        "scientific_execution_authorized",
        "historical_market_data_acquisition_authorized",
        "historical_economic_outcome_inspection_authorized",
        "backtest_authorized",
        "strategy_test_authorized",
        "outer_evaluation_authorized",
        "prospective_shadow_authorized",
        "research_ledger_candidate_proposal_authorized",
        "research_ledger_mutation_authorized",
        "secret_read_authorized",
        "merge_authorized",
        "broadcast_authorized",
        "live_capital_authorized",
        "alpha_claim_authorized",
    ):
        assert firewall[key] is False
    receipts = auth["construction_receipts"]
    for key in (
        "scientific_execution_count",
        "market_network_count",
        "market_data_acquisition_count",
        "backtest_count",
        "strategy_test_count",
        "outer_evaluation_count",
        "prospective_shadow_start_count",
        "secret_read_count",
        "signature_count",
        "approval_count",
        "broadcast_count",
        "live_capital_count",
    ):
        assert receipts[key] == 0
    assert receipts["research_ledger_state_changed"] is False
    assert receipts["qntyspot_changed"] is False


def test_qualification_fixture_is_not_a_strategy():
    boundary = load_auth()["qualification_fixture_boundary"]
    assert boundary["fixture_may_be_treated_as_strategy"] is False
    assert boundary["fixture_may_authorize_research"] is False
    assert boundary["fixture_may_authorize_trading"] is False
    assert boundary["fixture_may_authorize_capital"] is False
    assert load_auth()["authorized_future_phase"]["anti_leakage_contract"]["qualification_fixture_is_strategy"] is False


def test_project_registry_and_artifact_digest_are_aligned():
    project = load_project()
    assert project["state"] == "CLOSED_PASS"
    assert project["implementation_authorized"] is False
    assert project["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert project["hostile_review_count"] == 1
    assert project["hostile_review_verdict"] == "PASS"
    assert project["authorization_artifact_sha256"] == hashlib.sha256(AUTH_PATH.read_bytes()).hexdigest()


def test_active_contract_preserves_scope_order_costs_and_firewall():
    active = load_active_project()
    assert active["authorized_operations"] == [
        "PREREGISTER",
        "DEFINE_CHRONOLOGICAL_DEV_OUTER",
        "ACQUIRE_DEV",
        "EVALUATE_PREREGISTERED_CANDIDATES_ON_DEV",
        "SELECT_AND_FREEZE_EXACTLY_ONE_CANDIDATE",
        "ONLY_THEN_ACQUIRE_OUTER",
        "EXACTLY_ONE_OUTER_EVALUATION",
        "RECONSTRUCT_METRICS",
        "COMPARE_FROZEN_BASELINES",
        "PRODUCE_PROSPECTIVE_SHADOW_CONTINUATION_CONTRACT",
    ]
    assert active["required_baselines"] == load_auth()["authorized_future_phase"]["required_baselines"]
    assert set(active["required_costs"]) == set(load_auth()["authorized_future_phase"]["required_costs"])
    assert active["outer_rerun_authorized"] is False
    assert active["qualification_fixture_is_strategy"] is False
    for key in (
        "scientific_execution_authorized",
        "market_data_access_authorized",
        "historical_economic_outcome_inspection_authorized",
        "backtest_authorized",
        "strategy_test_authorized",
        "research_ledger_mutation_authorized",
    ):
        assert active[key] is False
    for key in ("qntyspot_execution_authority", "trading_authority", "capital_authority", "signing_authority", "promotion_authority"):
        assert active[key] == "NONE"
