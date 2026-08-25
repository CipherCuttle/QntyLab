from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from qntylab import project_context, research_ledger


ROOT = Path(__file__).resolve().parents[1]
R2_AUTHORIZATION_PROJECT_ID = "JFPV3_PR_B_R2_ACTIVATION_PERSISTENCE_AND_FORWARD_RUNNER_IMPLEMENTATION_AUTHORIZATION_V0"
PROSPECTIVE_SHADOW_AUTHORIZATION_PROJECT_ID = "JFPV3_PROSPECTIVE_SHADOW_ACTIVATION_AND_FORWARD_COLLECTION_AUTHORIZATION_V0"
JH01_REAL_OPERATION_AUTHORIZATION_PROJECT_ID = "JH01_V1_REAL_ACTIVATION_AND_FORWARD_RECORDER_IMPLEMENTATION_V0"
JH01_REAL_PROSPECTIVE_AUTHORIZATION_PROJECT_ID = "JH01_V1_REAL_PROSPECTIVE_OPERATION_AUTHORIZATION_V0"
FUNDING_INCREMENTAL_IMPLEMENTATION_PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_EXECUTION_IMPLEMENTATION_V0"
DSH_STAGE_A_V1_AUTHORIZATION_PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1_HARD_ORCHESTRATION_AUTHORIZATION_V0"
DSH_STAGE_A_V1_EXECUTION_PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1_EXECUTION_V0"
DSH_STAGE_A_V1R1_PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R1_BOOTSTRAP_AND_RUNTIME_HARDENING_AUTHORIZATION_V0"
DSH_STAGE_A_V1R1_EXECUTION_PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R1_EXECUTION_V0"
DSH_STAGE_A_V1R2_EXECUTION_PROJECT_ID = "DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1R2_EXECUTION_V0"
DSH_STAGE_A_V1R3R2_EXECUTION_PROJECT_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R1"
DSH_STAGE_A_V1R3R2_V0R2R1_EXECUTION_PROJECT_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2R1"
DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_PROJECT_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3"
DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_PROJECT_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4"
QNTYSPOT_ACTIVE_PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_V0"
CLAIM_REPAIR_AUTHORIZATION_PROJECT_ID = "DSH_STAGE_A_CLAIM_ACQUISITION_TRANSPORT_AND_OBSERVABILITY_REPAIR_AUTHORIZATION_V0"
CLAIM_REPAIR_AUTHORIZATION_NEXT_ACTION = "No project implementation is currently authorized."


def _assert_project_is_not_active(registry: dict, project_id: str) -> None:
    assert all(record["project_id"] != project_id or record["state"] != "ACTIVE" for record in registry["project"])


def _assert_project_is_not_current_active(data: dict, project_id: str) -> None:
    active = data["active_project"]
    assert active is None or active["project_id"] != project_id


def _tracked_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs/ADR").mkdir(parents=True)
    (root / "docs/state").mkdir(parents=True)
    for relative in ("docs/ADR/one.md", "docs/ADR/two.md", "artifact.md"):
        (root / relative).write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    return root


def _adr_registry(*, second_global: bool = False, companions: int = 0, path: str = "docs/ADR/one.md", supersession: list[dict[str, str]] | None = None) -> dict:
    return {
        "schema_version": 1,
        "adr": [
            {"adr_id": "ADR-0001", "path": path, "status": "CURRENT_PROJECT_SPECIFIC", "authority_scope": "PROJECT"},
            {
                "adr_id": "ADR-0002",
                "path": "docs/ADR/two.md",
                "status": "CURRENT_GLOBAL",
                "authority_scope": "GLOBAL_ARCHITECTURE",
            },
        ]
        + ([{"adr_id": "ADR-0003", "path": "docs/ADR/one.md", "status": "CURRENT_GLOBAL", "authority_scope": "GLOBAL_ARCHITECTURE"}] if second_global else [])
        + [{"adr_id": f"ADR-COMPANION-{index}", "path": "docs/ADR/one.md", "status": "CURRENT_GLOBAL_COMPANION", "authority_scope": "GLOBAL_RESEARCH_DESIGN_PHILOSOPHY"} for index in range(companions)],
        "supersession": supersession or [],
    }


def _project(project_id: str = "ONE", **overrides: object) -> dict:
    value: dict[str, object] = {
        "project_id": project_id,
        "state": "ACTIVE",
        "authority_level": "PROJECT_CONTEXT_IMPLEMENTATION",
        "authoritative_artifacts": ["artifact.md"],
        "next_action": "Implement only the authorized bounded work.",
        "implementation_authorized": True,
    }
    value.update(overrides)
    return value


def test_exactly_one_current_global_adr_passes(tmp_path: Path) -> None:
    assert project_context.validate_adr_registry(_tracked_root(tmp_path), _adr_registry())["ADR-0002"]["status"] == "CURRENT_GLOBAL"


def test_duplicate_current_global_fails(tmp_path: Path) -> None:
    with pytest.raises(project_context.ProjectContextError, match="exactly one CURRENT_GLOBAL"):
        project_context.validate_adr_registry(_tracked_root(tmp_path), _adr_registry(second_global=True))


def test_zero_current_global_fails_even_with_companion(tmp_path: Path) -> None:
    registry = _adr_registry(companions=1)
    registry["adr"][1]["status"] = "CURRENT_GLOBAL_COMPANION"
    with pytest.raises(project_context.ProjectContextError, match="exactly one CURRENT_GLOBAL"):
        project_context.validate_adr_registry(_tracked_root(tmp_path), registry)


def test_one_global_and_multiple_companions_pass(tmp_path: Path) -> None:
    adrs = project_context.validate_adr_registry(_tracked_root(tmp_path), _adr_registry(companions=2))
    assert adrs["ADR-0002"]["status"] == "CURRENT_GLOBAL"
    assert [record["adr_id"] for record in adrs.values() if record["status"] == "CURRENT_GLOBAL_COMPANION"] == ["ADR-COMPANION-0", "ADR-COMPANION-1"]


def test_companion_cannot_claim_architecture_scope(tmp_path: Path) -> None:
    registry = _adr_registry(companions=1)
    registry["adr"][-1]["authority_scope"] = "GLOBAL_ARCHITECTURE"
    with pytest.raises(project_context.ProjectContextError, match="COMPANION.*GLOBAL_ARCHITECTURE"):
        project_context.validate_adr_registry(_tracked_root(tmp_path), registry)


def test_broken_and_escaping_adr_paths_fail(tmp_path: Path) -> None:
    root = _tracked_root(tmp_path)
    with pytest.raises(project_context.ProjectContextError, match="escapes repository|repository-relative"):
        project_context.validate_adr_registry(root, _adr_registry(path="../outside.md"))
    with pytest.raises(project_context.ProjectContextError, match="escapes repository|must be a file"):
        project_context.validate_adr_registry(root, _adr_registry(path="docs/ADR/missing.md"))


def test_untracked_authority_source_fails(tmp_path: Path) -> None:
    root = _tracked_root(tmp_path)
    (root / "untracked.md").write_text("not tracked\n", encoding="utf-8")
    with pytest.raises(project_context.ProjectContextError, match="not Git-tracked"):
        project_context.validate_projects_registry(root, {"schema_version": 1, "project": [_project(authoritative_artifacts=["untracked.md"])]})


def test_duplicate_project_id_and_unknown_state_fail(tmp_path: Path) -> None:
    root = _tracked_root(tmp_path)
    with pytest.raises(project_context.ProjectContextError, match="duplicate project ID"):
        project_context.validate_projects_registry(root, {"schema_version": 1, "project": [_project(), _project()]})
    with pytest.raises(project_context.ProjectContextError, match="unknown project state"):
        project_context.validate_projects_registry(root, {"schema_version": 1, "project": [_project(state="UNKNOWN")]})


@pytest.mark.parametrize("state", ["PLANNED_NOT_AUTHORIZED", "CLOSED_NEGATIVE"])
def test_non_active_project_cannot_authorize_implementation(tmp_path: Path, state: str) -> None:
    with pytest.raises(project_context.ProjectContextError, match="requires ACTIVE"):
        project_context.validate_projects_registry(_tracked_root(tmp_path), {"schema_version": 1, "project": [_project(state=state)]})


def test_active_project_with_implementation_false_remains_unauthorized(tmp_path: Path) -> None:
    registry = project_context.validate_projects_registry(
        _tracked_root(tmp_path),
        {"schema_version": 1, "project": [_project(implementation_authorized=False)]},
    )
    assert registry["ONE"]["state"] == "ACTIVE"
    assert registry["ONE"]["implementation_authorized"] is False


def test_dsh_stage_a_v1_execution_closure_is_single_bounded_blocked_project() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    active_ids = {
        record["project_id"]
        for record in registry["project"]
        if record["state"] == "ACTIVE" and record.get("candidate_state") != "ACTIVE_CANDIDATE"
    }
    # V0R4 remains closed; the sole current ACTIVE row is the separately bound
    # QntySpot DEV acquisition successor.
    assert active_ids == {QNTYSPOT_ACTIVE_PROJECT_ID}
    execution = next(record for record in registry["project"] if record["project_id"] == DSH_STAGE_A_V1_EXECUTION_PROJECT_ID)
    authorization = next(record for record in registry["project"] if record["project_id"] == DSH_STAGE_A_V1_AUTHORIZATION_PROJECT_ID)
    v0r4 = next(record for record in registry["project"] if record["project_id"] == DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_PROJECT_ID)
    v0r3 = next(record for record in registry["project"] if record["project_id"] == DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_PROJECT_ID)

    assert v0r4["state"] == "CLOSED_BLOCKED"
    assert v0r4["terminal_outcome"] == "BLOCK_RUNTIME_IDENTITY"
    assert v0r4["active_project_after_closure"] == "NONE"
    assert v0r4["effective_execution_authority"] is False
    assert v0r4["implementation_authorized"] is False
    assert v0r4["episode_claimed"] is False
    assert v0r4["episode_consumed"] is False
    assert v0r4["second_episode_authorized"] is False
    assert v0r4["whole_episode_retry_allowed"] is False
    assert v0r4["activation_phase_spend_usd"] == 0.0
    _assert_project_is_not_active(registry, DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_PROJECT_ID)
    _assert_project_is_not_current_active(data, DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_PROJECT_ID)
    assert v0r3["state"] == "CLOSED_BLOCKED"
    assert data["active_project"]["project_id"] == QNTYSPOT_ACTIVE_PROJECT_ID
    assert data["current_permitted_next_action"].startswith("ACTIVE:")
    assert execution["state"] == "CLOSED_BLOCKED"
    assert execution["implementation_authorized"] is False
    assert execution["implementation_completed"] is True
    assert execution["authorization_project_id"] == DSH_STAGE_A_V1_AUTHORIZATION_PROJECT_ID
    assert execution["authorization_pr"] == 167
    assert execution["authorization_merge_sha"] == "c3d8f9d99c0400b2c5fd407068e96ee419d0028f"
    assert execution["episode_consumed"] is False
    assert execution["activation_consumes_live_episode"] is False
    assert execution["activation_consumes_execution_closure_pr_budget"] is False
    assert execution["authorized_live_episodes"] == 0
    assert execution["second_v1_episode_authorized"] is False
    assert execution["execution_closure_pr_budget"] == 1
    assert execution["stage_b_authorized"] is False
    assert execution["qnty_agent_eval"] == "NOT_APPLICABLE"
    assert execution["scientific_execution_authorized"] is False
    assert execution["qnty_runtime_authority"] == "NONE"
    assert execution["trading_authority"] == "NONE"
    assert execution["capital_authority"] == "NONE"
    assert execution["upstream_dsh_mutation_authorized"] is False
    assert execution["live_openai_calls"] == execution["live_dsh_calls"] == 0
    assert execution["live_codex_calls"] == execution["live_claude_calls"] == 0
    assert execution["spend_usd"] == 0.0
    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["implementation_authorized"] is False
    assert authorization["authorization_state"] == "AUTHORIZED_IF_CANONICAL"


def test_dsh_stage_a_v1r1_offline_qualification_is_closed_without_live_authority() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    project = next(record for record in registry["project"] if record["project_id"] == DSH_STAGE_A_V1R1_PROJECT_ID)
    receipt = json.loads(
        (
            ROOT
            / "experiments/research/qnty_agent_orchestration_control_contract_v0/"
            "dsh_multi_agent_orchestration_stage_a_v1r1_bootstrap_and_runtime_hardening_authorization_v0/"
            "qualification_receipt.json"
        ).read_text(encoding="utf-8")
    )

    assert project["state"] == "CLOSED_PASS"
    assert project["implementation_authorized"] is False
    assert project["implementation_completed"] is True
    assert project["active_project_after_closure"] == "NONE"
    assert receipt["qualification"] == "QUALIFIED_OFFLINE_BOOT_READY"
    assert receipt["boot_receipt"]["BOOT_READY"] == "YES"
    assert receipt["live_model_requests"] == 0
    assert receipt["native_codex_child_runs"] == 0
    assert receipt["native_claude_child_runs"] == 0
    assert receipt["stage_a_fixture_runs"] == 0
    assert receipt["spend_usd"] == 0.0
    assert data["active_project"]["project_id"] == QNTYSPOT_ACTIVE_PROJECT_ID
    assert data["current_permitted_next_action"].startswith("ACTIVE:")


def test_project_supersession_targets_self_and_cycles_fail(tmp_path: Path) -> None:
    root = _tracked_root(tmp_path)
    with pytest.raises(project_context.ProjectContextError, match="does not resolve"):
        project_context.validate_projects_registry(root, {"schema_version": 1, "project": [_project(supersedes=["MISSING"])]})
    with pytest.raises(project_context.ProjectContextError, match="self-supersession"):
        project_context.validate_projects_registry(root, {"schema_version": 1, "project": [_project(supersedes=["ONE"], superseded_by=["ONE"])]})
    one = _project("ONE", supersedes=["TWO"], superseded_by=[])
    two = _project("TWO", state="SUPERSEDED", implementation_authorized=False, supersedes=["ONE"], superseded_by=["ONE"])
    one["superseded_by"] = ["TWO"]
    with pytest.raises(project_context.ProjectContextError, match="cycle"):
        project_context.validate_projects_registry(root, {"schema_version": 1, "project": [one, two]})


def test_adr_supersession_references_and_cycles_fail(tmp_path: Path) -> None:
    root = _tracked_root(tmp_path)
    with pytest.raises(project_context.ProjectContextError, match="does not resolve"):
        project_context.validate_adr_registry(root, _adr_registry(supersession=[{"superseded_adr_id": "ADR-0001", "superseding_adr_id": "MISSING", "scope": "GLOBAL"}]))
    registry = _adr_registry(supersession=[
        {"superseded_adr_id": "ADR-0001", "superseding_adr_id": "ADR-0002", "scope": "GLOBAL"},
        {"superseded_adr_id": "ADR-0002", "superseding_adr_id": "ADR-0001", "scope": "GLOBAL"},
    ])
    with pytest.raises(project_context.ProjectContextError, match="cycle"):
        project_context.validate_adr_registry(root, registry)


def test_generated_roadmap_is_deterministic_and_check_detects_drift() -> None:
    expected = project_context._roadmap_bytes(ROOT)
    assert expected == project_context._roadmap_bytes(ROOT)
    project_context.render(ROOT, check=False)
    assert project_context.render(ROOT, check=True) == 0
    roadmap = ROOT / "docs/CURRENT_ROADMAP.md"
    original = roadmap.read_bytes()
    try:
        roadmap.write_bytes(original + b"manual drift\n")
        assert project_context.render(ROOT, check=True) == 1
    finally:
        roadmap.write_bytes(original)


def test_json_is_byte_stable_for_identical_state() -> None:
    command = [sys.executable, "-m", "qntylab.project_context", "--json"]
    first = subprocess.run(command, cwd=ROOT, check=True, capture_output=True).stdout
    second = subprocess.run(command, cwd=ROOT, check=True, capture_output=True).stdout
    assert first == second
    assert json.loads(first)["current_global_adr"]["adr_id"] == "ADR-0007"
    assert [item["adr_id"] for item in json.loads(first)["current_global_companions"]] == ["ADR-0005", "ADR-0006", "ADR-0008"]


def test_canonical_companion_is_current_but_not_architecture_authority() -> None:
    data = project_context.context_data(ROOT)
    assert data["current_global_adr"]["adr_id"] == "ADR-0007"
    assert data["current_global_companions"] == [
        {
            "adr_id": "ADR-0005",
            "path": "docs/ADR/0005-qntylab-north-star-market-intelligence-architecture.md",
            "authority_scope": "GLOBAL_SCIENTIFIC_NORTH_STAR",
        },
        {
            "adr_id": "ADR-0006",
            "path": "docs/ADR/0006-qntylab-research-design-philosophy.md",
            "authority_scope": "GLOBAL_RESEARCH_DESIGN_PHILOSOPHY",
        },
        {
            "adr_id": "ADR-0008",
            "path": "docs/ADR/0008-qnty-agent-orchestration-runtime-boundary.md",
            "authority_scope": "QNTY_AGENT_ORCHESTRATION_RUNTIME_BOUNDARY",
        },
    ]


def test_human_context_does_not_claim_no_queued_projects() -> None:
    text = project_context.context_text(project_context.context_data(ROOT))
    queued_section = text.split("## Authority boundary", maxsplit=1)[0]
    assert "- None." not in queued_section


def test_funding_incremental_implementation_freeze_is_closed_without_escalation() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    # The source-bound implementation freeze and the blocked Stage-A V1
    # execution, V0R1, V0R2R1, V0R3, and V0R4 live episodes are all closed.
    # V0R2R1 became canonically effective after PR #193 merged, then closed
    # BLOCK_RUNTIME_INFRA because this environment cannot materialize or launch
    # the pinned DSH runtime. V0R3 and then V0R4 each closed
    # BLOCK_RUNTIME_IDENTITY before secret or runtime execution, so no closed
    # episode is reopened; the sole ACTIVE row is the QntySpot successor.
    assert {
        record["project_id"]
        for record in registry["project"]
        if record["state"] == "ACTIVE" and record.get("candidate_state") != "ACTIVE_CANDIDATE"
    } == {QNTYSPOT_ACTIVE_PROJECT_ID}
    for closed_episode_id in (
        DSH_STAGE_A_V1R3R2_EXECUTION_PROJECT_ID,
        DSH_STAGE_A_V1R3R2_V0R2R1_EXECUTION_PROJECT_ID,
        DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_PROJECT_ID,
        DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_PROJECT_ID,
    ):
        episode = next(record for record in registry["project"] if record["project_id"] == closed_episode_id)
        assert episode["state"] == "CLOSED_BLOCKED", closed_episode_id
        _assert_project_is_not_active(registry, closed_episode_id)
        _assert_project_is_not_current_active(data, closed_episode_id)
    assert data["active_project"]["project_id"] == QNTYSPOT_ACTIVE_PROJECT_ID
    assert data["current_permitted_next_action"].startswith("ACTIVE:")
    _assert_project_is_not_active(registry, FUNDING_INCREMENTAL_IMPLEMENTATION_PROJECT_ID)
    _assert_project_is_not_current_active(data, FUNDING_INCREMENTAL_IMPLEMENTATION_PROJECT_ID)
    project = next(
        record for record in registry["project"] if record["project_id"] == FUNDING_INCREMENTAL_IMPLEMENTATION_PROJECT_ID
    )
    assert project["state"] == "CLOSED_PASS"
    assert project["authority_level"] == "SOURCE_BOUND_IMPLEMENTATION_AND_SYNTHETIC_VALIDATION_ONLY"
    assert project["phase_type"] == "SOURCE_BOUND_IMPLEMENTATION_FREEZE"
    assert project["implementation_authorized"] is False
    assert project["synthetic_validation_authorized"] is True
    assert project["governing_preregistration_project_id"] == "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_PREREGISTRATION_V0"
    assert project["governing_preregistration_digest"] == "d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef"
    assert project["selected_architecture"] == "A_EXPLORATORY_610_INCREMENTAL_FORECAST_TEST"
    for field in (
        "real_evidence_execution_authorized",
        "scientific_execution_authorized",
        "outcome_access_authorized",
        "market_data_access_authorized",
        "funding_acquisition_authorized",
        "scientific_result_recording_authorized",
        "trial_completion_authorized",
        "state_snapshot_authorized",
        "router_authorized",
        "qnty_authorized",
        "trading_authorized",
        "promotion_authorized",
        "critical_high_repair_required",
        "targeted_rereview_used",
    ):
        assert project[field] is False, field
    assert project["capital_authority"] == "NONE"
    assert project["downstream_authority"] == "NONE"
    assert project["active_project_after_closure"] == "NONE"
    # The single hostile implementation review closed clean.
    assert project["hostile_review_count"] == 1
    assert project["hostile_review_verdict"] == "PASS"
    assert project["hostile_review_critical"] == 0
    assert project["hostile_review_high"] == 0
    assert project["synthetic_validation_result"] == "PASS"
    assert project["numerical_determinism"] == "PASS"
    assert project["final_implementation_sha"] == project["reviewed_implementation_candidate_sha"]
    assert project["implementation_source_path"] == "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
    next_action = project["next_action"]
    assert "CLOSED_PASS" in next_action
    assert "PREREGISTERED_NOT_EXECUTED" in next_action
    assert "separate Git-backed execution authorization" in next_action
    for disclaimed in (
        "No real evidence execution",
        "no evaluation origin was consumed",
        "No State Snapshot, Router, Qnty, trading, promotion, or capital authority",
    ):
        assert disclaimed in next_action, disclaimed


def test_jh01_temporal_replication_v0_and_v0r1_are_closed_with_their_distinct_lineages_preserved() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    # JH01 temporal replication and the bounded real-operation implementation
    # remain closed and are not the current active project.
    _assert_project_is_not_active(registry, JH01_REAL_OPERATION_AUTHORIZATION_PROJECT_ID)
    _assert_project_is_not_current_active(data, JH01_REAL_OPERATION_AUTHORIZATION_PROJECT_ID)
    implementation = next(record for record in registry["project"] if record["project_id"] == JH01_REAL_OPERATION_AUTHORIZATION_PROJECT_ID)
    assert implementation["state"] == "CLOSED_PASS"
    assert implementation["implementation_authorized"] is False
    assert implementation["implementation_authority_consumed"] is True
    execution = next(record for record in registry["project"] if record["project_id"] == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_EXECUTION_V0")
    assert execution["state"] == "CLOSED_BLOCKED"
    assert execution["authority_level"] == "FROZEN_REPLICATION_EXECUTION_INTERRUPTED_NO_RERUN"
    assert execution["implementation_authorized"] is False
    assert execution["superseded_by"] == ["JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_EXECUTION_V0R1"]
    assert execution["frozen_preregistration_project_id"] == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_PREREG_V0"
    assert execution["frozen_preregistration_digest"] == "46f923023b4b696307da2b9d6fc4c8db9d04b40b012de35e0bf738cc03c4be57"
    assert execution["frozen_input_qualification_digest"] == "8f82db32ce0f453f6f67e5cd4b421e0848752b7f24a9b39f05ec979fe9382593"
    assert execution["frozen_replication_input_snapshot_id"] == "jh01-rv-temporal-input-v0-ce0e0d1945eb5d6096cc8c24933e0ec19bb8a882c4cce526cb01ff4487b11efa"
    assert execution["frozen_replication_input_snapshot_digest"] == "ce0e0d1945eb5d6096cc8c24933e0ec19bb8a882c4cce526cb01ff4487b11efa"
    assert set(execution["authoritative_artifacts"]) == {
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/preregistration.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/materialization_request.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/materialization_receipt.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/per_symbol_manifest.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/snapshot_manifest.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/input_qualification.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/hostile_execution_review.md",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/execution_request.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/execution_started.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/execution_interruption.md",
    }
    action = execution["next_action"].lower()
    for required_text in (
        "interrupted",
        "execution_interrupted_after_real_outcome_access",
        "no repair, rerun",
        "alternative calculation",
        "result reconstruction",
        "jigsaw evidence creation",
        "state snapshot",
        "qnty, trading",
        "superseding git-backed governance",
    ):
        assert required_text in action

    v0r1 = next(record for record in registry["project"] if record["project_id"] == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_EXECUTION_V0R1")
    assert v0r1["state"] == "CLOSED_PASS"
    assert v0r1["authority_level"] == "FROZEN_SUPERSEDING_EXECUTION_COMPLETE_NO_RERUN"
    assert v0r1["implementation_authorized"] is False
    assert v0r1["supersedes"] == [execution["project_id"]]
    assert v0r1["prior_execution_terminal_state"] == "EXECUTION_INTERRUPTED_AFTER_REAL_OUTCOME_ACCESS"
    assert v0r1["prior_frozen_execution_implementation_sha"] == "e638dc2e3b044697902230a5c0705fb49de1f21a"
    assert v0r1["prior_frozen_execution_source_path"] == "qntylab/jh01_rv_persistence_temporal_replication_execution_v0.py"
    assert v0r1["prior_frozen_execution_source_immutable"] is True
    assert v0r1["prior_execution_request_digest"] == "19d2e0827a76f37176e71b36a56d635c8f9ed1970f47664e1effd13a6d2327ec"
    assert v0r1["prior_execution_started_digest"] == "9c8b00ad68c1e1ba389512c94a4c145264844a4e24fae75c038fcc9e0144f285"
    assert v0r1["frozen_preregistration_digest"] == execution["frozen_preregistration_digest"]
    assert v0r1["frozen_input_qualification_digest"] == execution["frozen_input_qualification_digest"]
    assert v0r1["frozen_replication_input_snapshot_id"] == execution["frozen_replication_input_snapshot_id"]
    assert v0r1["frozen_replication_input_snapshot_digest"] == execution["frozen_replication_input_snapshot_digest"]
    assert v0r1["repair_reason"] == "STRICT_ZIP_ADJACENT_PAIR_CARDINALITY_DEFECT"
    assert v0r1["repair_scope"] == "ADJACENT_PAIR_ITERATION_ONLY"
    assert v0r1["post_start_repair"] is True
    assert v0r1["pristine_first_execution"] is False
    assert v0r1["v0r1_executor_must_be_distinct_from_v0"] is True
    assert v0r1["v0r1_artifact_namespace"] == "experiments/research/jh01_rv_persistence_temporal_replication_v0/v0r1"
    assert v0r1["v0r1_real_execution_count"] == 1
    assert v0r1["frozen_v0r1_execution_implementation_sha"] == "758e02718ce82bebeae3e63d17ecc6e3d4a9a23a"
    assert v0r1["frozen_v0r1_result_sha"] == "939f47d8c24abf5e84a1071550eaab463647182e"
    assert v0r1["frozen_v0r1_result_digest"] == "3dba3a0f0700a768e981dcecfe5793532bcd4bc1db7dc4dbcd9e4806a722c5c1"
    assert v0r1["frozen_v0r1_provenance_correction_digest"] == "c396b6cc53d92a87c7dfa45920c05a772bb447c1f98de5bdbbae065e255b7154"
    assert v0r1["v0r1_classification"] == "REPLICATED_WITHIN_FROZEN_TEMPORAL_SCOPE"
    for field in (
        "input_reacquisition_authorized",
        "jigsaw_evidence_authorized",
        "state_snapshot_authorized",
        "router_authorized",
        "qnty_authorized",
        "trading_authorized",
    ):
        assert v0r1[field] is False
    for forbidden_text in (
        "no further real-sample execution",
        "no further real-sample execution or scientific mutation",
        "jigsaw evidence incorporation",
        "state snapshot",
        "router",
        "qnty, trading",
        "post-start-repair provenance",
        "must consume the v0r1 provenance correction",
        "must not treat the truncated prior_execution_started_digest as authoritative",
    ):
        assert forbidden_text in v0r1["next_action"].lower()

    materialization = next(record for record in registry["project"] if record["project_id"] == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_INPUT_MATERIALIZATION_V0")
    assert materialization["state"] == "CLOSED_PASS"
    assert materialization["authority_level"] == "INPUT_MATERIALIZATION_ONLY"
    assert materialization["implementation_authorized"] is False
    assert materialization["frozen_preregistration_digest"] == "46f923023b4b696307da2b9d6fc4c8db9d04b40b012de35e0bf738cc03c4be57"
    assert "scientific replication execution remains unauthorized" in materialization["next_action"].lower()
    assert set(materialization["authoritative_artifacts"]) == {
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/preregistration.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/materialization_request.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/materialization_receipt.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/per_symbol_manifest.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/snapshot_manifest.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/input_qualification.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/materialization/hostile_materialization_review.md",
    }
    preregistration = next(record for record in data["superseded_or_stale_planning"] if record["project_id"] == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_PREREG_V0")
    preregistration_registry = next(record for record in registry["project"] if record["project_id"] == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_PREREG_V0")
    assert preregistration["state"] == "CLOSED_PASS"
    assert preregistration_registry["implementation_authorized"] is False
    assert preregistration["next_action"] == (
        "JH01 temporal-replication preregistration is frozen and closed. No market-data access, acquisition, materialization, "
        "feature/outcome computation, regression execution, Jigsaw evidence creation, State Snapshot, Router, Qnty, trading, "
        "or promotion authority is granted. Replication input materialization requires a separate Git-backed authorization."
    )
    harvest = next(record for record in data["superseded_or_stale_planning"] if record["project_id"] == "JIGSAW_HARVEST_V0")
    assert harvest["state"] == "CLOSED_PASS"
    assert harvest["next_action"] == "Jigsaw Harvest V0 is closed. Preserve its four bounded evidence pieces; no State Snapshot, Router, Qnty, or trading implementation is authorized by this phase."


def test_jfp_historical_execution_v0_authorizes_only_jfp03_with_frozen_holm_family() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = {record["project_id"]: record for record in registry["project"]}

    # V0 and the replacement input-materialization phase are closed blocked;
    # this historical execution project is not the current active project.
    _assert_project_is_not_active(registry, "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_HISTORICAL_EXECUTION_V0")
    _assert_project_is_not_current_active(data, "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_HISTORICAL_EXECUTION_V0")
    execution = projects["JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_HISTORICAL_EXECUTION_V0"]
    assert execution["state"] == "CLOSED_BLOCKED"
    assert execution["authority_level"] == "FROZEN_DESIGN_UNDERSPECIFIED_BEFORE_REAL_ACCESS"
    assert execution["implementation_authorized"] is False

    # frozen digests bind byte-for-byte to the already-closed prereg/census/materialization phases.
    prereg = projects["JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_PREREG_V0"]
    materialization = projects["JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_INPUT_MATERIALIZATION_V0"]
    assert materialization["state"] == "CLOSED_PASS"
    assert prereg["state"] == "CLOSED_PASS"
    assert execution["frozen_preregistration_digest"] == "9e9236b34b131c13cebfb0b8043ef59043b2928fa6fcd88dd7b10909d9e8ccfe"
    assert execution["frozen_preregistration_digest"] == materialization["frozen_preregistration_digest"]
    assert execution["frozen_candidate_census_digest"] == "d718dc1c60ceccdbd7a836a1e07b911a51511456289c09d7ff9b8c6af452df94"
    assert execution["frozen_materialization_request_digest"] == materialization["frozen_materialization_request_digest"] == "97026d1a2fadfde7babf7f0c6c7802db6cbc8e92aa55c3b8a7e3d23d1e8456dc"
    assert execution["frozen_input_qualification_digest"] == materialization["frozen_input_qualification_digest"] == "472ef1da4ab7ab2fe5f98aa85fa1c24b666d40bea5aae6b390bcf0627ed60727"
    assert execution["frozen_input_snapshot_id"] == materialization["frozen_input_snapshot_id"] == "jfp-input-v0-9dab9e5f71242116206b30ea61d3b217e760dd43d176022d80c4a43c7153712f"
    assert execution["frozen_input_snapshot_digest"] == materialization["frozen_input_snapshot_digest"] == "9dab9e5f71242116206b30ea61d3b217e760dd43d176022d80c4a43c7153712f"
    assert execution["frozen_materialization_dispositions"] == materialization["state_dispositions"] == "JFP01=BLOCKED_CANDIDATE,JFP02=BLOCKED_CANDIDATE,JFP03=READY"

    # materialization artifacts are unchanged: JFP03 is READY with exactly 60 authenticated objects,
    # and JFP01/JFP02 remain candidate-local BLOCKED_CANDIDATE with no scientific outcome access.
    qualification = json.loads((ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/materialization/input_qualification.json").read_text(encoding="utf-8"))
    assert qualification["input_qualification_digest"] == execution["frozen_input_qualification_digest"]
    assert qualification["execution_authorized"] is False
    by_candidate = {row["candidate_id"]: row for row in qualification["ordered_candidates"]}
    assert by_candidate["JFP01"]["disposition"] == "BLOCKED_CANDIDATE"
    assert by_candidate["JFP02"]["disposition"] == "BLOCKED_CANDIDATE"
    assert by_candidate["JFP03"]["disposition"] == "READY"
    assert by_candidate["JFP03"]["authenticated_object_count"] == 60
    assert execution["jfp03_ready_authenticated_object_count"] == 60

    # execution authority is JFP03-only; JFP01/JFP02 execution is explicitly denied.
    assert execution["execution_candidate_ids"] == ["JFP03"]
    assert execution["jfp01_execution_authorized"] is False
    assert execution["jfp02_execution_authorized"] is False
    assert execution["jfp03_execution_authorized"] is False

    # the frozen three-hypothesis Holm family cannot be shrunk, and blocked candidates
    # never receive a fabricated raw p-value.
    assert execution["holm_family_size"] == 3
    assert execution["jfp03_raw_alpha_threshold"] == "0.05/3"
    assert execution["jfp03_holm_rule"] == "holm_adjusted_p_JFP03 = min(1.0, 3.0 * raw_p_JFP03)"
    assert "raw_p_value = null" in execution["blocked_candidate_multiplicity_semantics"]
    assert "must never be recorded as raw p = 1" in execution["blocked_candidate_multiplicity_semantics"]

    # one-shot execution semantics: executor must freeze before real access, at most one real
    # execution is allowed, and a post-access rerun requires superseding governance.
    assert execution["input_reacquisition_authorized"] is False
    assert execution["real_execution_count_allowed"] == 0
    assert execution["executor_freeze_required_before_real_access"] is True
    assert execution["post_access_rerun_authorized"] is False
    assert "separately authorized input-materialization phase" in execution["next_action"].lower()
    assert "no executor" in execution["next_action"].lower()

    # every downstream authority remains false/NONE for this governance-only phase.
    for field in (
        "jigsaw_evidence_authorized",
        "jigsaw_index_mutation_authorized",
        "synthesis_mutation_authorized",
        "prospective_deployment_authorized",
        "state_snapshot_authorized",
        "forecaster_authorized",
        "router_authorized",
        "qnty_authorized",
        "shadow_deployment_authorized",
        "paper_trading_authorized",
        "trading_authorized",
        "promotion_authorized",
    ):
        assert execution[field] is False, field
    assert execution["capital_authority"] == "NONE"

    # the frozen preregistration and candidate census remain byte-unchanged.
    census = json.loads((ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/candidate_census.json").read_text(encoding="utf-8"))
    assert census["candidate_census_digest"] == execution["frozen_candidate_census_digest"]
    assert census["candidate_ids"] == ["JFP01", "JFP02", "JFP03"]

    # registry invariants remain valid.
    assert data["authority_conflicts_or_warnings"] == []


def test_jfp03_v0r1_scientific_execution_is_consumed_blocked_and_non_escalating() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = {record["project_id"]: record for record in registry["project"]}
    project_id = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R1_HISTORICAL_SCIENTIFIC_EXECUTION_AUTHORIZATION_V0"
    authorization = projects[project_id]
    execution = projects["JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R1_HISTORICAL_SCIENTIFIC_EXECUTION_V0"]

    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["phase_type"] == "GOVERNANCE_ONLY"
    assert authorization["authority_level"] == "HISTORICAL_SCIENTIFIC_EXECUTION_AUTHORIZATION_ONLY"
    assert authorization["bound_snapshot_id"] == "jfp-input-v0r3-24311649d541c28d068addc2fc76121d614a11f0f191581c7dd988ba0b99c69f"
    assert authorization["bound_snapshot_digest"] == "24311649d541c28d068addc2fc76121d614a11f0f191581c7dd988ba0b99c69f"
    assert authorization["bound_qualification_digest"] == "420b0a4a84a57814d13393eb008affc05eb81223e06a9cf4a86c7772bc8bef5d"
    assert authorization["bound_design_digest"] == "a52d4999038e0be814ee8770322303fce84bed9ec8941b812748a18867633736"
    assert authorization["input_qualification"] == "READY"
    assert authorization["source_object_count"] == 63
    assert authorization["logical_warmup_rows"] == 721
    assert authorization["first_har720_complete"] is True
    assert authorization["last_target_24h_complete"] is True

    assert authorization["historical_scientific_execution_authorized"] is False
    assert authorization["historical_scientific_execution_runs_allowed"] == 1
    assert authorization["historical_scientific_execution_runs_consumed"] == 1
    assert authorization["historical_scientific_execution_performed"] is True
    assert authorization["claim_digest"] == "c2a0135a320c26e293d86d9ccbbf80553ee5f863be05d7184fab5074ad84038a"
    assert authorization["result_digest"] == "aa42724ef37466babaf7fb81a44524fe9568d8679d0a2cf967ee9faaf9ae6dbb"
    assert authorization["terminal_classification"] == "BLOCKED_CANDIDATE"
    assert authorization["rerun_authorized"] is False
    assert authorization["input_reacquisition_authorized"] is False
    assert authorization["network_access_authorized"] is False
    assert authorization["bound_runtime_identity_digest"] == "35e70c8893e018c32f925734b666a1ba6abbac9d5942298de533d66ce1c22d60"
    assert authorization["bound_execution_workspace_root"] == "/home/swirky/DevHub/repos/QntyLab"
    assert authorization["bound_git_common_dir"] == "/home/swirky/DevHub/repos/QntyLab/.git"
    assert authorization["bound_git_common_dir_device"] == 66307
    assert authorization["bound_git_common_dir_inode"] == 7740500
    assert authorization["claim_path_relative_to_git_common_dir"] == "qntylab-claims/jfp03-v0r1-historical-scientific-execution-v0.json"
    for field in (
        "scientific_feature_computation_authorized",
        "scientific_target_computation_authorized",
        "regression_authorized",
        "hac_authorized",
        "p_values_authorized",
        "real_afi_computed",
        "real_har_computed",
        "real_target_computed",
        "real_regression_executed",
        "real_hac_computed",
        "real_p_values_computed",
        "jigsaw_evidence_authorized",
        "jigsaw_synthesis_authorized",
        "promotion_authorized",
        "prospective_deployment_authorized",
        "state_snapshot_authorized",
        "forecaster_authorized",
        "router_authorized",
        "qnty_authorized",
        "paper_trading_authorized",
        "trading_authorized",
    ):
        assert authorization[field] is False, field
    assert authorization["capital_authority"] == "NONE"
    assert authorization["downstream_authority"] == "NONE"
    assert authorization["implementation_authorized"] is False

    result_path = ROOT / authorization["result_path"]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    canonical_result = json.dumps(
        {key: value for key, value in result.items() if key != "result_digest"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical_result).hexdigest() == authorization["result_digest"]
    assert result["terminal_classification"] == execution["terminal_classification"] == "BLOCKED_CANDIDATE"
    assert result["integrity_failure"] == execution["integrity_failure"]
    assert result["expected_observation_count"] == execution["expected_observation_count"] == 43848
    assert result["actual_observation_count"] is None
    assert execution["actual_observation_count"] == "NULL_IN_BLOCKED_RESULT"
    assert execution["historical_scientific_execution_runs_allowed"] == 1
    assert execution["historical_scientific_execution_runs_consumed"] == 1
    assert execution["historical_scientific_execution_performed"] is True
    assert execution["scientific_values_are_null"] is True
    assert execution["result_immutable"] is True
    assert execution["replay_authorized"] is False
    assert execution["rerun_authorized"] is False
    assert execution["rescue_run_authorized"] is False
    assert execution["downstream_authority"] == "NONE"
    assert execution["capital_authority"] == "NONE"
    assert execution["implementation_authorized"] is False
    _assert_project_is_not_current_active(data, execution["project_id"])
    assert data["authority_conflicts_or_warnings"] == []


def test_closed_harvest_does_not_authorize_state_snapshot() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = {record["project_id"]: record for record in registry["project"]}
    assert projects["STATE_SNAPSHOT_V0"]["state"] == "PLANNED_NOT_AUTHORIZED"
    assert projects["STATE_SNAPSHOT_V0"]["implementation_authorized"] is False
    assert projects["JIGSAW_HARVEST_V0"]["implementation_authorized"] is False
    assert any(record["project_id"] == "STATE_SNAPSHOT_V0" for record in data["queued_but_unauthorized_projects"])


def test_research_ledger_is_the_canonical_research_source() -> None:
    data = project_context.context_data(ROOT)
    _, trials, _ = research_ledger.verify_indexes_current(ROOT / "experiments/research")
    assert data["research_ledger"]["completed_trial_count"] == len(trials["trials"])
    assert data["research_ledger"]["canonical_source"] == "experiments/research"


def test_project_context_introduces_no_qnty_or_trading_authority() -> None:
    data = project_context.context_data(ROOT)
    assert "Qnty authority" not in data["current_permitted_next_action"]


def test_jh01_jigsaw_evidence_authorization_v0_is_governance_only_and_binds_v0r1_identities() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = {record["project_id"]: record for record in registry["project"]}

    authorization = projects["JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_JIGSAW_EVIDENCE_AUTHORIZATION_V0"]
    v0r1 = projects["JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_EXECUTION_V0R1"]

    # (1) the project is represented correctly in canonical project state.
    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["authority_level"] == "GOVERNANCE_AUTHORIZATION_ONLY"
    assert authorization["phase_type"] == "GOVERNANCE_ONLY"
    assert authorization["source_piece_id"] == "JH01_RV_PERSISTENCE"
    assert authorization["frozen_v0r1_project_id"] == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_EXECUTION_V0R1"
    assert not any(record["project_id"] == authorization["project_id"] for record in data["queued_but_unauthorized_projects"])
    assert any(record["project_id"] == authorization["project_id"] for record in data["superseded_or_stale_planning"])

    # (2)+(3) the phase grants no execution, mutation, or downstream authority whatsoever.
    for field in (
        "scientific_execution_authorized",
        "real_data_execution_authorized",
        "input_reacquisition_authorized",
        "frozen_result_mutation_authorized",
        "jigsaw_evidence_mutation_authorized",
        "jigsaw_index_mutation_authorized",
        "synthesis_mutation_authorized",
        "pristine_first_execution_assertion_authorized",
        "independent_replication_established_change_authorized_this_phase",
        "original_jh01_discovery_piece_mutation_authorized",
    ):
        assert authorization[field] is False, field
    assert authorization["implementation_authorized"] is False

    # (4)+(5) the exact frozen V0R1 result and provenance-correction digests are bound, and match
    # the identities already recorded against the closed V0R1 execution project itself.
    assert authorization["frozen_v0r1_result_digest"] == "3dba3a0f0700a768e981dcecfe5793532bcd4bc1db7dc4dbcd9e4806a722c5c1"
    assert authorization["frozen_v0r1_result_digest"] == v0r1["frozen_v0r1_result_digest"]
    assert authorization["frozen_v0r1_provenance_correction_digest"] == "c396b6cc53d92a87c7dfa45920c05a772bb447c1f98de5bdbbae065e255b7154"
    assert authorization["frozen_v0r1_provenance_correction_digest"] == v0r1["frozen_v0r1_provenance_correction_digest"]
    assert authorization["canonical_corrected_v0_execution_started_digest"] == "9c8b00ad68c1e1ba389512c94a4c145264844a4e24fae75c038fcc9e0144f285"
    assert authorization["canonical_corrected_v0_execution_started_digest"] == v0r1["prior_execution_started_digest"]

    # (6) the later implementation must consume both digests together, never the malformed one alone.
    assert authorization["result_and_correction_must_be_consumed_together"] is True
    assert "must consume the frozen v0r1 execution result digest together with" in authorization["next_action"].lower()
    assert "malformed prior digest embedded in the frozen result as authoritative" in authorization["next_action"].lower()

    # (7) pristine-first execution can never be asserted downstream.
    assert authorization["post_start_repair_qualification_must_be_preserved"] is True
    assert "must not assert v0r1 was a pristine first execution" in authorization["next_action"].lower()
    assert "must preserve the post-start-repair qualification" in authorization["next_action"].lower()

    # (8) downstream State Snapshot / Router / Qnty / trading / promotion authority remains absent.
    for field in ("state_snapshot_authorized", "router_authorized", "qnty_authorized", "trading_authorized", "promotion_authorized"):
        assert authorization[field] is False, field
    assert "no state snapshot, router, qnty, trading, or promotion authority is granted" in authorization["next_action"].lower()

    # (9) the current Jigsaw evidence/index/synthesis artifacts are untouched by this phase, and the
    # recorded independent_replication_established snapshot matches the live synthesis file exactly
    # so this governance record cannot silently drift from the artifact it describes.
    assert "experiments/research/jigsaw_index.json" not in authorization["authoritative_artifacts"]
    assert "experiments/research/jigsaw_synthesis_eligibility_v0/eligibility.json" not in authorization["authoritative_artifacts"]
    eligibility = json.loads((ROOT / "experiments/research/jigsaw_synthesis_eligibility_v0/eligibility.json").read_text(encoding="utf-8"))
    assert eligibility["global_constraints"]["independent_replication_established"] == "NO"
    assert authorization["independent_replication_established_current_value"] == "NO"
    assert "independent_replication_established remains no and unchanged" in authorization["next_action"].lower()

    # (10) project-context/state invariants remain valid: registry validation and the doctor pass clean.
    assert data["authority_conflicts_or_warnings"] == []
    # This JH01 governance phase and JFP03 input materialization are closed;
    # neither historical project is the current active project.
    _assert_project_is_not_active(registry, authorization["project_id"])
    _assert_project_is_not_current_active(data, authorization["project_id"])
    for forbidden_text in (
        "narrowest truthful representation",
        "no scientific rerun, recomputation, or input reacquisition is authorized",
        "original jh01_rv_persistence discovery piece remains immutable",
    ):
        assert forbidden_text in authorization["next_action"].lower()
    assert all(item["project_id"] != "QNTY_HANDOFF" or "No implementation is authorized" in item["next_action"] for item in data["queued_but_unauthorized_projects"])


def test_jfp03_terminal_evidence_extraction_authorization_is_governance_only_and_fail_closed() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = {record["project_id"]: record for record in registry["project"]}

    authorization = projects["JIGSAW_TERMINAL_RESEARCH_EVIDENCE_EXTRACTION_AUTHORIZATION_V0"]
    predecessor = projects[authorization["predecessor_project_id"]]

    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["authority_level"] == "GOVERNANCE_AUTHORIZATION_ONLY"
    assert authorization["phase_type"] == "GOVERNANCE_ONLY"
    assert authorization["implementation_authorized"] is False
    _assert_project_is_not_current_active(data, authorization["project_id"])
    assert not any(record["project_id"] == authorization["project_id"] for record in data["queued_but_unauthorized_projects"])

    assert authorization["terminal_result_path"] == predecessor["result_path"]
    assert authorization["terminal_result_digest"] == predecessor["result_digest"]
    assert authorization["terminal_claim_digest"] == predecessor["claim_digest"]
    assert authorization["terminal_classification"] == predecessor["terminal_classification"] == "BLOCKED_CANDIDATE"
    assert authorization["frozen_snapshot_id"] == predecessor["bound_snapshot_id"]
    assert authorization["frozen_snapshot_digest"] == predecessor["bound_snapshot_digest"]
    assert authorization["frozen_qualification_digest"] == predecessor["bound_qualification_digest"]
    assert authorization["integrity_failure"] == predecessor["integrity_failure"]
    assert authorization["scientific_values_are_null"] is True

    for field in (
        "scientific_execution_authorized",
        "replay_authorized",
        "rerun_authorized",
        "rescue_run_authorized",
        "input_reacquisition_authorized",
        "frozen_result_mutation_authorized",
        "jigsaw_evidence_mutation_authorized",
        "jigsaw_index_mutation_authorized",
        "synthesis_mutation_authorized",
        "state_snapshot_authorized",
        "forecaster_authorized",
        "router_authorized",
        "qnty_authorized",
        "paper_trading_authorized",
        "trading_authorized",
        "promotion_authorized",
    ):
        assert authorization[field] is False, field
    assert authorization["capital_authority"] == authorization["downstream_authority"] == "NONE"

    action = authorization["next_action"].lower()
    for required_text in (
        "exactly one later, separately git-backed bounded implementation phase",
        "independently re-establish the exact afi denominator failure from authenticated frozen source bytes",
        "existing jigsaw-evidence-piece-v0 schema without changing jigsaw_index.py",
        "stop and report the invariant that fails",
        "must never be laundered into negative scientific evidence",
        "does not authorize a second failure-mode piece",
        "must not pre-authorize a schema change",
    ):
        assert required_text in action


def test_jfpv3_r2_implementation_authorization_closes_without_escalation() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    _assert_project_is_not_active(registry, R2_AUTHORIZATION_PROJECT_ID)
    authorization = next(record for record in registry["project"] if record["project_id"] == R2_AUTHORIZATION_PROJECT_ID)
    assert authorization["project_id"] == R2_AUTHORIZATION_PROJECT_ID
    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["phase_type"] == "IMPLEMENTATION_QUALIFICATION_CLOSURE"
    assert authorization["implementation_authorized"] is False
    assert authorization["authorized_implementation_phase"] == "JFPV3_PR_B_R2"
    assert authorization["preauthorization_r2_scratch_authority"] == "NONE"
    assert authorization["r1_canonical_merge"] == "779dac12c0e7a6db0a733ecd77c2980444ae7916"
    assert authorization["r1_implementation_digest"] == "7a8bbfe5b72d787608436232fd87bbe876be24b0d524a38f2d7dd6bbc5d53e01"
    assert authorization["frozen_preregistration_digest"] == "7b0e6eeda726ddcc6e5a2a99d931df51bfbff492557fdefc30eae629c998da16"
    assert authorization["frozen_universe_contract_digest"] == "883172c10174d52a298293b2299ab28af4095c33217e2c2a24de3a258208c9fd"
    assert authorization["frozen_source_contract_digest"] == "64b918c8e062c55d1434a34ff5f7e3368dd59a7e2358edcacfa80bf1ab2e2348"
    assert authorization["frozen_scientific_contract_digest"] == "8b37028ef1ebc5baf7a04bfc742069f0b1ecd0931c4017c565324e980a140e90"
    assert authorization["frozen_schedule_contract_digest"] == "5e326a165bdf6dda8dd137ec69a4677f6029f99ae0487a80724a3c0667a36ffc"
    for field in (
        "real_activation_authorized", "real_data_execution_authorized", "real_prospective_market_data_authorized",
        "real_prospective_ohlcv_authorized", "historical_v3_backtest_authorized", "scientific_execution_authorized",
        "scientific_inference_authorized", "interim_inference_authorized", "jigsaw_mutation_authorized",
        "state_snapshot_authorized", "router_authorized", "qnty_authorized", "trading_authorized", "promotion_authorized",
        "paper_trading_authorized", "pr_a_mutation_authorized", "pr_b_v0_history_mutation_authorized", "r1_history_mutation_authorized",
    ):
        assert authorization[field] is False, field
    assert authorization["capital_authority"] == "NONE"
    assert authorization["real_activation_must_follow_canonical_r2"] is True
    assert authorization["hostile_governance_review_count"] == 1
    assert authorization["hostile_governance_review_verdict"] == "PASS"
    assert authorization["hostile_governance_critical_total"] == 0
    assert authorization["hostile_governance_high_total"] == 0
    assert authorization["hostile_governance_open_critical"] == 0
    assert authorization["hostile_governance_open_high"] == 0
    assert authorization["targeted_governance_rereview_used"] is True
    assert authorization["qntyageval_applicability"] == "NO_MATCH"
    assert authorization["qntyageval_lookup_performed"] is True
    assert authorization["qntyageval_run_performed"] is False
    assert "activation persistence and forward runner are implemented and frozen" in authorization["next_action"].lower()
    assert "new bounded authority" in authorization["next_action"].lower()
    _assert_project_is_not_current_active(data, R2_AUTHORIZATION_PROJECT_ID)
    active = data["active_project"]
    assert data["current_permitted_next_action"] == (
        active["next_action"] if active else "No project implementation is currently authorized."
    )
    assert authorization["next_action_after_closure"] == "CANONICALIZE_R2_THEN_SEPARATELY_AUTHORIZE_OR_EXECUTE_ACTIVATION_AS_ALLOWED"
    assert authorization["r2_activation_transaction_implemented"] is True
    assert authorization["shadow_activated"] is False
    assert authorization["open_critical"] == 0
    assert authorization["open_high"] == 0


def test_jfpv3_prospective_shadow_authorization_is_one_shot_and_non_scientific() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    authorization = next(record for record in registry["project"] if record["project_id"] == PROSPECTIVE_SHADOW_AUTHORIZATION_PROJECT_ID)
    _assert_project_is_not_current_active(data, PROSPECTIVE_SHADOW_AUTHORIZATION_PROJECT_ID)
    assert authorization["state"] == "CLOSED_PASS"
    assert authorization["authority_level"] == "FROZEN_PROSPECTIVE_SHADOW_OPERATION_AUTHORIZATION_ONLY"
    assert authorization["phase_type"] == "GOVERNANCE_ONLY"
    assert authorization["implementation_authorized"] is False
    assert authorization["generation_id"] == authorization["candidate_id"] == "JFPV3_01"
    assert authorization["canonical_r2_final_candidate"] == "64d2e421545b0fd4a0364c0814d4b87eef779fa2"
    assert authorization["canonical_r2_merge"] == "bc4f3a327f23d057da1ad970e9eeb7ed2fe10c91"
    assert authorization["canonical_r2_implementation_digest"] == "3f80bcd2dd60aaae6e1307883cca2e996f631f7bbc3b76037eafef8450167e2b"
    assert authorization["canonical_r2_manifest_digest"] == "b1ca7d2bb5025b272bfdcd871a1889f6f25842c2be83c479d19ebad16075520e"
    assert authorization["activation_authorized_after_canonicalization"] is True
    assert authorization["activation_authorization_canonicalization_required"] is True
    assert authorization["activations_authorized"] == authorization["committed_activation_count_allowed"] == 1
    assert authorization["activate_shadow_command"] == "python -m qntylab.jfp_v3_shadow activate-shadow"
    assert authorization["forward_collection_authorized_after_activation"] is True
    assert authorization["collect_due_command"] == "python -m qntylab.jfp_v3_shadow collect-due"
    assert authorization["forward_collection_requires_committed_activation"] is True
    assert authorization["forward_collection_requires_due_origin"] is True
    assert authorization["real_binance_source_access_authorized_only_when_due"] is True
    for field in (
        "duplicate_activation_authorized", "replacement_origins_authorized", "schedule_extension_authorized",
        "early_origin_execution_authorized", "interim_inference_authorized", "terminal_evaluation_authorized",
        "historical_v3_backtest_authorized", "jigsaw_mutation_authorized", "state_snapshot_authorized",
        "forecaster_authorized", "router_authorized", "qnty_authorized", "paper_trading_authorized",
        "trading_authorized", "promotion_authorized",
    ):
        assert authorization[field] is False, field
    assert authorization["capital_authority"] == "NONE"
    assert authorization["activation_attempt_1"] == "BLOCKED_BY_ACTIVATION_IMPLEMENTATION_DEFECT"
    assert authorization["activation_attempt_2"] == "BLOCKED_BY_ACTIVATION_PERSISTENCE_IMPLEMENTATION"
    assert authorization["valid_activation_count"] == 0
    assert authorization["shadow_run_id"] == "NONE_BEFORE_AUTHORIZED_ACTIVATION"
    assert authorization["prospective_contamination"] == "NONE"
    assert authorization["shadow_activated"] is False
    assert authorization["real_network_used"] is False
    assert authorization["real_market_data_accessed"] is False
    assert authorization["real_prospective_ohlcv_accessed"] is False
    assert authorization["real_prospective_features_computed"] == 0
    assert authorization["real_prospective_outcomes_computed"] == 0
    assert authorization["real_prospective_regressions_run"] == 0
    assert authorization["real_prospective_p_values_computed"] == 0
    assert authorization["real_prospective_partial_r2_computed"] == 0
    assert authorization["scientific_classifications_computed"] == 0
    assert authorization["next_action"].startswith("CLOSED_PASS: Canonicalize this authorization")


def test_jh01_real_operation_authorization_is_single_active_source_bound_phase() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    authorization = next(record for record in registry["project"] if record["project_id"] == JH01_REAL_OPERATION_AUTHORIZATION_PROJECT_ID)
    artifact = json.loads((ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/real_activation_and_forward_recorder_implementation_authorization_v0.json").read_text(encoding="utf-8"))

    _assert_project_is_not_current_active(data, JH01_REAL_OPERATION_AUTHORIZATION_PROJECT_ID)
    assert authorization["state"] == "CLOSED_PASS"
    assert artifact["state"] == "ACTIVE"
    assert authorization["phase_type"] == "IMPLEMENTATION"
    assert authorization["implementation_authorized"] is False
    assert authorization["implementation_authority_consumed"] is True
    assert authorization["frozen_preregistration_digest"] == artifact["lineage"]["preregistration_digest"]
    assert authorization["canonical_recorder_merge"] == artifact["lineage"]["recorder_qualification_merge"] == "b50e8e3cd17199265cb7040588d97822d45dd170"
    assert authorization["qualified_implementation_candidate"] == artifact["lineage"]["qualified_implementation_candidate"] == "5dc86826040b9bd3403f03c31cfc8a64249ed907"
    assert authorization["qualified_recorder_module_immutable"] is True
    assert authorization["wrapper_first_required"] is True
    assert artifact["frozen_contract"]["required_valid_origins"] == 365
    assert artifact["frozen_contract"]["persistence_window"] == "t <= persistence_time < t + 1 hour"
    assert artifact["authority_firewall"]["real_v1_collection_authorized"] is False
    assert artifact["authority_firewall"]["real_market_data_authorized"] is False
    assert artifact["authority_firewall"]["real_github_forecast_publication_authorized"] is False
    assert artifact["authority_firewall"]["scientific_evaluation_authorized"] is False
    assert artifact["authority_firewall"]["capital_authority"] == "NONE"
    assert artifact["hostile_governance_review"]["review_count"] == 1
    assert artifact["hostile_governance_review"]["critical_total"] == artifact["hostile_governance_review"]["high_total"] == 0
    assert artifact["hostile_governance_review"]["targeted_rereview_used"] is False
    assert artifact["qntyageval"] == {"applicability": "NO_MATCH", "lookup_performed": True, "run_performed": False}
    assert data["authority_conflicts_or_warnings"] == []


def test_jh01_real_prospective_authority_is_exact_and_fail_closed() -> None:
    from qntylab import jh01_v1_prospective_operation_v0 as operation

    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = {record["project_id"]: record for record in registry["project"]}
    project = projects[JH01_REAL_PROSPECTIVE_AUTHORIZATION_PROJECT_ID]
    path = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/real_prospective_operation_authorization_v0.json"
    artifact = json.loads(path.read_text(encoding="utf-8"))

    _assert_project_is_not_current_active(data, JH01_REAL_PROSPECTIVE_AUTHORIZATION_PROJECT_ID)
    assert project["state"] == "CLOSED_PASS"
    assert artifact["state"] == "ACTIVE"
    assert project["phase_type"] == "GOVERNANCE_ONLY"
    assert project["implementation_authorized"] is False
    assert artifact["schedule_digest"] == operation.schedule_digest()
    assert artifact["required_origin_count"] == 365
    assert artifact["real_v1_activation_authorized"] is True
    assert artifact["forward_collection_authorized"] is True
    assert artifact["scientific_evaluation_authorized"] is False
    assert artifact["interim_metrics_authorized"] is False
    assert artifact["downstream_authority"] == "NONE"
    assert artifact["real_market_data_accessed"] is False
    assert artifact["real_activation_count"] == 0
    assert artifact["real_forecasts_persisted"] == 0
    assert artifact["qntyageval"] == {"applicability": "NO_MATCH", "lookup_performed": True, "run_performed": False}

    operation.build_activation_contract(ROOT, mode=operation.OperationMode.REAL_PROSPECTIVE)

    mutations = (
        ("wrapper_implementation_identity", "wrong-wrapper"),
        ("qualified_recorder_identity", "wrong-recorder"),
        ("preregistration_digest", "wrong-preregistration"),
        ("schedule_digest", "wrong-schedule"),
        ("required_origin_count", 364),
        ("first_live_origin", "2026-09-16T00:00:00Z"),
        ("scientific_evaluation_authorized", True),
        ("forward_collection_authorized", False),
        ("state", "CLOSED_PASS"),
    )
    for key, value in mutations:
        mutated = dict(artifact)
        mutated[key] = value
        with pytest.raises(operation.OperationBlocked):
            operation._load_real_operation_authority(ROOT, fixture=mutated)

    before = hashlib.sha256((ROOT / "qntylab/jh01_v1_prospective_operation_v0.py").read_bytes()).hexdigest()
    recorder_before = hashlib.sha256((ROOT / "qntylab/jh01_v1_prospective_recorder_implementation_v0.py").read_bytes()).hexdigest()
    assert before == "1176037ff0d3102afc67670202154970e4af1491cff1cd19bc9526c9c9d67c41"
    assert recorder_before == "4f5e1791be9f17c1871f9b510329a1632412e028d2a84223fa59e83bbe95ec1a"
    assert not (ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/real_prospective_operation_authorization_v0.receipt.json").exists()


def test_jfpv3_prospective_authorization_binds_immutable_r2_and_scientific_bytes() -> None:
    expected = {
        "qntylab/jfp_v3_shadow.py": "d0c434b37244da977a1285322122f36012a787beb1d5eb944f87e34b2a2c174b",
        "experiments/research/jigsaw_fast_prospective_signal_discovery_v3/preregistration.json": "7b0e6eeda726ddcc6e5a2a99d931df51bfbff492557fdefc30eae629c998da16",
        "experiments/research/jigsaw_fast_prospective_signal_discovery_v3/universe_contract.json": "883172c10174d52a298293b2299ab28af4095c33217e2c2a24de3a258208c9fd",
        "experiments/research/jigsaw_fast_prospective_signal_discovery_v3/source_contract.json": "64b918c8e062c55d1434a34ff5f7e3368dd59a7e2358edcacfa80bf1ab2e2348",
        "experiments/research/jigsaw_fast_prospective_signal_discovery_v3/scientific_contract.json": "8b37028ef1ebc5baf7a04bfc742069f0b1ecd0931c4017c565324e980a140e90",
        "experiments/research/jigsaw_fast_prospective_signal_discovery_v3/schedule_contract.json": "5e326a165bdf6dda8dd137ec69a4677f6029f99ae0487a80724a3c0667a36ffc",
    }
    for relative, expected_digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected_digest, relative
    assert not (ROOT / "data/jfp_v3_shadow/events.jsonl").exists()
