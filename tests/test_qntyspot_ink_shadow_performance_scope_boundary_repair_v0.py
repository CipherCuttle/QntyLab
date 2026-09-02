from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
CLOSURE_PATH = (
    ROOT
    / "experiments/research/qntyspot_ink_shadow_performance_scope_boundary_repair_v0/closure.json"
)
REPAIR_PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_SCOPE_BOUNDARY_REPAIR_V0"
ARCHIVED_PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_V0"


def _projects() -> list[dict]:
    return tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))["project"]


def _project(project_id: str) -> dict:
    return next(record for record in _projects() if record["project_id"] == project_id)


def test_boundary_repair_archives_product_specific_work_and_revokes_authority() -> None:
    archived = _project(ARCHIVED_PROJECT_ID)
    assert archived["state"] == "ARCHIVED"
    assert archived["historical_canonical_state"] == "ACTIVE"
    assert archived["historical_activation_receipt_preserved"] is True
    assert archived["external_repository_identity"] == "CipherCuttle/QntySpot"
    assert archived["qntylab_current_role"] == "HISTORICAL_RESEARCH_PROVENANCE_ONLY"
    assert archived["future_reactivation_requires_separate_git_backed_qntylab_authorization"] is True
    assert archived["implementation_authorized"] is False
    assert archived["market_data_access_authorized"] is False
    assert archived["scientific_execution_authorized"] is False
    assert archived["qntyspot_execution_authority"] == "NONE"
    assert archived["trading_authority"] == "NONE"
    assert archived["capital_authority"] == "NONE"
    assert [record for record in _projects() if record["state"] == "ACTIVE"] == []


def test_boundary_repair_is_governance_only_and_non_escalating() -> None:
    repair = _project(REPAIR_PROJECT_ID)
    assert repair["state"] == "CLOSED_PASS"
    assert repair["phase_type"] == "GOVERNANCE_ONLY"
    assert repair["canonicalization_status"] == "EXACT_CANONICAL_MERGE_VERIFIED"
    assert repair["canonical_merge"] == "b2b24ef59a09a5aa039e7afeb0afa6f0610e8f87"
    assert repair["canonical_merge_pr"] == 235
    assert repair["hostile_review_count"] == 1
    assert repair["hostile_review_verdict"] == "HOSTILE_REVIEW_PASS"
    assert repair["hostile_governance_critical_total"] == 0
    assert repair["hostile_governance_high_total"] == 0
    assert repair["qntylab_repository_identity"] == "CipherCuttle/QntyLab"
    assert repair["qntyspot_repository_identity"] == "CipherCuttle/QntySpot"
    assert repair["active_project_after_closure"] == "NONE"
    assert repair["historical_receipts_preserved"] is True
    assert repair["historical_scientific_artifacts_mutated"] is False
    assert repair["qntyspot_repository_mutated"] is False
    assert repair["research_ledger_state_changed"] is False
    for key in (
        "implementation_authorized",
        "scientific_execution_authorized",
        "market_data_access_authorized",
        "historical_economic_outcome_inspection_authorized",
        "backtest_authorized",
        "strategy_test_authorized",
    ):
        assert repair[key] is False
    for key in (
        "qntyspot_execution_authority",
        "trading_authority",
        "capital_authority",
        "promotion_authority",
    ):
        assert repair[key] == "NONE"


def test_historical_receipts_are_byte_preserved_and_transition_remains_provenance() -> None:
    closure = json.loads(CLOSURE_PATH.read_text(encoding="utf-8"))
    assert closure["phase_state"] == "CLOSED_PASS_CANONICAL_MERGED"
    assert closure["canonical_merge"] == "b2b24ef59a09a5aa039e7afeb0afa6f0610e8f87"
    assert closure["canonical_merge_pr"] == 235
    assert closure["review"]["independent_hostile_review_count"] == 1
    assert closure["review"]["verdict"] == "PASS_NO_CRITICAL_HIGH"
    assert closure["review"]["critical_findings"] == 0
    assert closure["review"]["high_findings"] == 0
    for relative_path, expected in closure["preserved_provenance"].items():
        actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert f"sha256:{actual}" == expected, relative_path

    activation = json.loads(
        (
            ROOT
            / "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_activation_v0/activation.json"
        ).read_text(encoding="utf-8")
    )
    assert activation["canonical_state_transition"]["canonical_successor_state"] == "ACTIVE"
    assert closure["disposition"]["prior_state"] == "ACTIVE"
    assert closure["disposition"]["current_state"] == "ARCHIVED"


def test_project_context_has_no_active_authority_and_roadmap_is_current() -> None:
    data = project_context.context_data(ROOT)
    assert data["active_project"] is None
    assert data["current_permitted_next_action"] == "No project implementation is currently authorized."
    assert data["authority_conflicts_or_warnings"] == []
    assert project_context.render(ROOT, check=True) == 0
