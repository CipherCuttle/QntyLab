from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
PHASE_ROOT = ROOT / "experiments/research/qntyspot_ink_shadow_performance_authorization_v0"
AUTH_PATH = PHASE_ROOT / "authorization.json"
NOTE_PATH = PHASE_ROOT / "authority_note.md"
AUTH = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_AUTHORIZATION_V0"
FUTURE_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_V0"
QNTYLAB_CANONICAL_BASE = "a4738278f42f961ad2f2470fefff6688ccde6bb6"
QNTYSPOT_CANONICAL_SOURCE = "b9a84c59bd43e7697ee970d2a7571647e5de4501"


def _artifact_sha256() -> str:
    return hashlib.sha256(AUTH_PATH.read_bytes()).hexdigest()


def _project_record() -> dict[str, object]:
    registry = tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))
    return next(item for item in registry["project"] if item["project_id"] == PROJECT_ID)


def test_candidate_is_branch_local_and_not_self_authorizing() -> None:
    assert AUTH["phase_state"] == "CANDIDATE_GOVERNANCE_ONLY"
    assert AUTH["state"] == "PLANNED_NOT_AUTHORIZED"
    assert AUTH["candidate_state"] == "ACTIVE_CANDIDATE"
    assert AUTH["canonicalization_status"] == "CANDIDATE_NOT_CANONICAL"
    assert AUTH["phase_type"] == "GOVERNANCE_ONLY"
    assert AUTH["authority_level"] == "BOUNDED_RESEARCH_AUTHORIZATION_ONLY"
    assert AUTH["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert AUTH["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert AUTH["implementation_authorized"] is False
    assert AUTH["authorization_effective_on_branch"] is False
    assert AUTH["branch_local_candidate_does_not_self_authorize"] is True


def test_exact_canonical_base_binding() -> None:
    identity = AUTH["canonical_source_identity"]
    assert identity["canonical_ref"] == "origin/master"
    assert identity["canonical_base_sha"] == QNTYLAB_CANONICAL_BASE
    assert identity["canonical_drift_behavior"] == "STOP_SOURCE_CONFLICT"
    assert identity["git_wins_over_prompt_memory_or_handoff"] is True


def test_exact_qntyspot_source_binding() -> None:
    binding = AUTH["qntyspot_source_binding"]
    assert binding["repository"] == "QntySpot"
    assert binding["canonical_ref"] == "origin/main"
    assert binding["canonical_commit"] == QNTYSPOT_CANONICAL_SOURCE
    assert binding["canonical_drift_behavior"] == "STOP_SOURCE_CONFLICT"
    assert binding["runtime_cross_repository_imports"] is False
    derivation = binding["derivation"]
    assert derivation["method"] == "AST literal extraction from qntyspot/ink.py at the exact canonical commit"
    assert derivation["source_path"] == "qntyspot/ink.py"
    assert derivation["source_git_blob"] == "07d4afa3f29119e72ca922910fb6ff9478b9ddb4"
    assert derivation["network_reads_performed"] is False
    assert binding["ink_chain_id"] == 57073
    assert binding["krakmask"] == {
        "symbol": "KRAKMASK",
        "address": "0x32bcb803f696c99eb263d60a05cafd8689026575",
        "decimals": 18,
    }
    assert binding["weth"] == {
        "symbol": "WETH9",
        "address": "0x4200000000000000000000000000000000000006",
        "decimals": 18,
    }
    assert binding["inkyswap_v2_pool"] == "0xed11ed4b195e84ba9b74c4d6ce13b7a43b354264"
    assert binding["inkyswap_v2_factory"] == "0x458c5d5b75ccba22651d2c5b61cb1ea1e0b0f95d"
    assert binding["deployed_runtime_bytecode"] == {
        "hash_algorithm": "SHA-256",
        "sha256": "c5c2b764b882b8c18004fe5ce77d8649dd8c26cea265f663b16196708d22bf20",
        "hashes_runtime_bytecode_bytes_not_hex_spelling": True,
    }
    assert binding["v2_fee_semantics"] == {
        "numerator": 997,
        "denominator": 1000,
        "fee_fraction": "3/1000",
        "fee_percent": "0.3%",
    }


def test_future_phase_identity_and_scope_are_unique() -> None:
    phase = AUTH["authorized_future_phase"]
    assert phase["project_id"] == FUTURE_ID
    assert phase["phase_count"] == 1
    assert phase["phase_is_separate"] is True
    assert AUTH["project_id"] != FUTURE_ID
    assert AUTH["forbidden_operations_in_this_phase"]
    assert "RUN_BACKTEST" in AUTH["forbidden_operations_in_this_phase"]
    assert "MODIFY_QNTYSPOT" in AUTH["forbidden_operations_in_this_phase"]


def test_cutoff_and_anti_leakage_contract_are_frozen() -> None:
    phase = AUTH["authorized_future_phase"]
    assert phase["historical_data_cutoff_utc"] == "2026-08-25T17:02:37Z"
    assert phase["required_order"] == [
        "PREREGISTER",
        "DEFINE_CHRONOLOGICAL_DEV_OUTER",
        "ACQUIRE_DEV",
        "SELECT_AND_FREEZE_EXACTLY_ONE_CANDIDATE",
        "ONLY_THEN_ACQUIRE_OUTER",
        "RUN_EXACTLY_ONE_SEALED_OUTER_EVALUATION",
    ]
    anti_leakage = phase["anti_leakage"]
    assert anti_leakage["outer_reuse_after_results"] is False
    assert anti_leakage["candidate_alteration_after_freeze"] is False
    assert anti_leakage["silent_parameter_expansion"] is False
    assert anti_leakage["qualification_fixture_is_a_strategy"] is False
    assert anti_leakage["outer_evaluation_count"] == 1
    family = phase["candidate_family_constraints"]
    assert family["finite_and_preregistered"] is True
    assert family["family_size_and_parameter_values"] is None
    assert family["must_be_frozen_before_dev_outcome_access"] is True
    assert family["parameter_selection_in_this_authorization"] is False
    assert family["parameter_fishing_after_dev_outcome_access"] is False


def test_required_baselines_and_costs_are_frozen() -> None:
    phase = AUTH["authorized_future_phase"]
    assert phase["required_baselines"] == [
        "HOLD_WETH",
        "BUY_AND_HOLD_KRAKMASK",
        "PERIODIC_DCA",
        "DUMB_SYMMETRIC_GRID",
        "SELECTED_QNTYSPOT_LADDER",
    ]
    assert phase["baseline_constraints"] == {
        "identical_initial_wealth": True,
        "identical_executable_market_semantics": True,
    }
    assert phase["required_costs"] == [
        "EXACT_AMM_FEE",
        "INTENDED_SIZE_PRICE_IMPACT",
        "EXPLICIT_GAS_TREATMENT_OR_SENSITIVITY",
        "TURNOVER",
    ]
    assert phase["gross_price_movement_is_strategy_pnl"] is False


def test_scientific_and_external_authority_firewalls_are_zero() -> None:
    assert AUTH["scientific_firewall"] == {
        "trading_authority": "NONE",
        "capital_authority": "NONE",
        "qntyspot_execution_authority": "NONE",
        "signing_authority": "NONE",
        "promotion_authority": "NONE",
        "scientific_execution_authority": "NONE",
        "positive_result_is_proof_of_alpha": False,
        "negative_result_must_be_preserved": True,
    }
    receipts = AUTH["construction_receipts"]
    for key in (
        "scientific_execution_count",
        "market_network_count",
        "external_market_data_requests",
        "historical_outcome_reads",
        "backtests",
        "strategy_tests",
        "research_ledger_trial_events",
        "research_ledger_candidate_events",
        "secret_reads",
        "signing_calls",
        "approval_calls",
        "broadcast_calls",
        "live_capital_calls",
        "outer_evaluations",
        "prospective_shadow_starts",
        "pnl_calculations",
        "sharpe_calculations",
        "drawdown_calculations",
    ):
        assert receipts[key] == 0, key
    assert receipts["research_ledger_state_changed"] is False
    assert receipts["qntyspot_changed"] is False
    assert receipts["spend_usd"] == "0"


def test_registry_projection_and_generated_roadmap_match() -> None:
    record = _project_record()
    assert record["state"] == "PLANNED_NOT_AUTHORIZED"
    assert record["candidate_state"] == "ACTIVE_CANDIDATE"
    assert record["authority_level"] == "BOUNDED_RESEARCH_AUTHORIZATION_ONLY"
    assert record["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert record["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert record["implementation_authorized"] is False
    assert record["canonical_base_sha"] == QNTYLAB_CANONICAL_BASE
    assert record["qntyspot_canonical_commit"] == QNTYSPOT_CANONICAL_SOURCE
    assert record["authorized_future_project_id"] == FUTURE_ID
    assert record["authorization_artifact_sha256"] == _artifact_sha256()
    _, _, registry = project_context.load_context_sources(ROOT)
    validated = project_context.validate_projects_registry(ROOT, registry)
    assert project_context.execution_authority_projection(ROOT, validated)["active_project"] is None
    assert project_context.execution_authority_projection(ROOT, validated)["issues"] == []
    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_bytes()
    assert roadmap == project_context._roadmap_bytes(ROOT)
    roadmap_text = roadmap.decode("utf-8")
    assert "QntySpot Ink shadow performance research authorization V0" in roadmap_text
    assert "QNTYSPOT_INK_SHADOW_PERFORMANCE_V0" in roadmap_text
    assert "PLANNED_NOT_AUTHORIZED" in roadmap_text


def test_authority_note_mirrors_the_immutable_artifact() -> None:
    note = NOTE_PATH.read_text(encoding="utf-8")
    assert QNTYLAB_CANONICAL_BASE in note
    assert QNTYSPOT_CANONICAL_SOURCE in note
    assert "does not" in note
    assert "AFTER_EXACT_CANONICAL_MERGE_ONLY" in note
    assert "TRADING_AUTHORITY = NONE" in note
    assert "CAPITAL_AUTHORITY = NONE" in note


def test_authorization_json_has_no_floating_point_numbers() -> None:
    raw = AUTH_PATH.read_text(encoding="utf-8")
    assert ".0" not in raw
    assert "pnl" not in raw.lower() or "pnl_calculations" in raw
