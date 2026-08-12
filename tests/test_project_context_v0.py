from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from qntylab import project_context, research_ledger


ROOT = Path(__file__).resolve().parents[1]


def _tracked_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs/ADR").mkdir(parents=True)
    (root / "docs/state").mkdir(parents=True)
    for relative in ("docs/ADR/one.md", "docs/ADR/two.md", "artifact.md"):
        (root / relative).write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    return root


def _adr_registry(*, second_global: bool = False, path: str = "docs/ADR/one.md", supersession: list[dict[str, str]] | None = None) -> dict:
    return {
        "schema_version": 1,
        "adr": [
            {"adr_id": "ADR-0001", "path": path, "status": "CURRENT_PROJECT_SPECIFIC", "authority_scope": "PROJECT"},
            {
                "adr_id": "ADR-0002",
                "path": "docs/ADR/two.md",
                "status": "CURRENT_GLOBAL",
                "authority_scope": "GLOBAL",
            },
        ]
        + ([{"adr_id": "ADR-0003", "path": "docs/ADR/one.md", "status": "CURRENT_GLOBAL", "authority_scope": "GLOBAL"}] if second_global else []),
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
    assert json.loads(first)["current_global_adr"]["adr_id"] == "ADR-0005"


def test_human_context_does_not_claim_no_queued_projects() -> None:
    text = project_context.context_text(project_context.context_data(ROOT))
    queued_section = text.split("## Authority boundary", maxsplit=1)[0]
    assert "- None." not in queued_section


def test_jh01_temporal_replication_v0_and_v0r1_are_closed_with_their_distinct_lineages_preserved() -> None:
    data = project_context.context_data(ROOT)
    _, _, registry = project_context.load_context_sources(ROOT)
    assert sum(record["state"] == "ACTIVE" for record in registry["project"]) == 0
    assert data["active_project"] is None
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
    assert all(item["project_id"] != "QNTY_HANDOFF" or "No implementation is authorized" in item["next_action"] for item in data["queued_but_unauthorized_projects"])
