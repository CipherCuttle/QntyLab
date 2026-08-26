from __future__ import annotations

import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]

RECONCILIATION_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_AUTHORIZATION_V0"
CORRECTION_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_CORRECTION_AUTHORIZATION_V0"
CLAIM_OWNER_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION_AUTHORIZATION_V0"
IMPLEMENTATION_ID = "DSH_STAGE_A_V1R3R2_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION_V0"
QNTYSPOT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_V0"

FINAL_CANDIDATE = "8ee3a671bc9be1d55811e701d0a2b82f3e1d39ee"
CANONICAL_MERGE = "3a0e1aa15c6c5d01a93dd7e3460dd3a736c46474"
CANONICAL_MERGE_PARENTS = [
    "abdaf42f67038ef970b2c233ad80baa1643ea6de",
    "8ee3a671bc9be1d55811e701d0a2b82f3e1d39ee",
]
CURRENT_EXECUTION_CONTRACT_ROOT = "cf1aff079d56428753bf8f58f1848839da35cfb9f75104fc1fd03cd13056c1e2"

NEXT_ACTION_SEMANTICS = (
    "A LATER phase MAY construct exactly ONE fresh separately Git-backed bounded "
    "Stage-A V1R3R2 one-episode live execution authorization against the repaired "
    "canonical current-generation execution contract"
)


def _records() -> dict[str, dict[str, object]]:
    registry = tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))
    return {item["project_id"]: item for item in registry["project"]}


def _roadmap_sections() -> dict[str, str]:
    text = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    return sections


def test_all_three_dsh_authorizations_are_closed_pass_with_exact_canonical_merge() -> None:
    records = _records()
    for project_id in (RECONCILIATION_AUTHORIZATION_ID, CORRECTION_AUTHORIZATION_ID, CLAIM_OWNER_AUTHORIZATION_ID):
        record = records[project_id]
        assert record["state"] == "CLOSED_PASS"
        assert record["candidate_state"] == "CANONICAL_AUTHORIZATION_EFFECTIVE"
        assert record["canonicalization_status"] == "EXACT_CANONICAL_MERGE_VERIFIED"
        assert record["canonical_authorization_merge"] == CANONICAL_MERGE
        assert record["canonical_authorization_merge_parents"] == CANONICAL_MERGE_PARENTS
        assert record["repair_authority_was_effective"] is True
        assert record["implementation_completed"] is True
        assert record["implementation_authorized"] is False
        assert record["effective_repair_authority"] is False
        assert record["secret_read_authorized"] is False
        assert record["live_dsh_authorized"] is False
        assert record["v0r7_authorized"] is False
        assert record["stage_b_authorized"] is False
        assert record["terminal_outcome"] == f"{project_id}_CANONICAL_CLOSED_PASS"
        assert NEXT_ACTION_SEMANTICS in record["next_action"]


def test_claim_owner_authorization_binds_the_closed_implementation() -> None:
    record = _records()[CLAIM_OWNER_AUTHORIZATION_ID]
    assert record["implementation_project_id"] == IMPLEMENTATION_ID
    assert record["implementation_project_state"] == "CLOSED_PASS"
    assert record["implementation_candidate_sha"] == FINAL_CANDIDATE
    assert record["implementation_canonical_merge"] == CANONICAL_MERGE
    assert record["current_execution_contract_root"] == CURRENT_EXECUTION_CONTRACT_ROOT


def test_implementation_row_is_closed_pass_with_exact_binds() -> None:
    record = _records()[IMPLEMENTATION_ID]
    assert record["display_name"] == "DSH Stage-A V1R3R2 production claim-owner integration correction V0"
    assert record["state"] == "CLOSED_PASS"
    assert record["candidate_state"] == "CANONICAL_TERMINAL_EFFECTIVE"
    assert record["canonicalization_status"] == "CLOSED"
    assert record["authority_level"] == "BOUNDED_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION_ONLY"
    assert record["phase_type"] == "OFFLINE_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION"
    assert record["authorization_project_id"] == CLAIM_OWNER_AUTHORIZATION_ID
    assert record["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["final_implementation_candidate"] == FINAL_CANDIDATE
    assert record["canonical_implementation_merge"] == CANONICAL_MERGE
    assert record["canonical_implementation_merge_parents"] == CANONICAL_MERGE_PARENTS
    assert record["current_execution_contract_root"] == CURRENT_EXECUTION_CONTRACT_ROOT
    assert record["governing_authorization_state"] == "CLOSED_PASS"
    for flag in (
        "v0r7_authorized",
        "live_dsh_authorized",
        "stage_b_authorized",
        "secret_read_authorized",
        "provider_io_authorized",
        "model_execution_authorized",
        "scientific_execution_authorized",
    ):
        assert record[flag] is False
    assert record["qnty_runtime_authority"] == "NONE"
    assert record["trading_authority"] == "NONE"
    assert record["capital_authority"] == "NONE"
    assert record["promotion_authority"] == "NONE"
    assert record["active_project_after_closure"] == "NONE"
    assert record["terminal_outcome"] == f"{IMPLEMENTATION_ID}_CLOSED_PASS"
    assert NEXT_ACTION_SEMANTICS in record["next_action"]


def test_roadmap_places_closed_rows_and_keeps_dsh_out_of_queued() -> None:
    sections = _roadmap_sections()
    queued = sections["Queued — not authorized"]
    closed = sections["Closed / stale"]
    for project_id, display in (
        (RECONCILIATION_AUTHORIZATION_ID, "execution contract reconciliation authorization V0"),
        (CORRECTION_AUTHORIZATION_ID, "execution contract reconciliation correction authorization V0"),
        (CLAIM_OWNER_AUTHORIZATION_ID, "production claim-owner integration correction authorization V0"),
        (IMPLEMENTATION_ID, "production claim-owner integration correction V0"),
    ):
        assert project_id not in queued
        assert display in closed
        assert "CLOSED_PASS" in closed


def test_no_dsh_live_project_is_active_and_qntyspot_remains_the_only_active_row() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    validated = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, validated)
    assert projection["issues"] == []
    active = projection["active_project"]
    assert active is not None
    assert active["project_id"] == QNTYSPOT_ID
    records = _records()
    active_rows = [record["project_id"] for record in records.values() if record["state"] == "ACTIVE"]
    assert active_rows == [QNTYSPOT_ID]


def test_qntyspot_row_is_preserved_unweakened() -> None:
    record = _records()[QNTYSPOT_ID]
    assert record["state"] == "ACTIVE"
    assert record["implementation_authorized"] is True
    assert record["implementation_completed"] is False
    assert record["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_AND_FRESH_CLEAN_WORKTREE_ONLY"
