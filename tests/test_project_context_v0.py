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


def test_jh01_temporal_replication_input_materialization_is_the_only_active_authority() -> None:
    data = project_context.context_data(ROOT)
    expected_next_action = (
        "Acquire or materialize only the exact frozen 20-symbol, 1h input history required by "
        "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_PREREG_V0; authenticate source objects, verify exact temporal coverage and "
        "hourly continuity, preserve source bytes/provenance, establish a new immutable replication-input snapshot identity, and "
        "determine INPUT_READY or BLOCKED_BY_INPUT_CONTRACT. Raw-input integrity checks are authorized. Scientific feature/outcome "
        "computation, returns, RV24, regression, replication classification, Jigsaw evidence, State Snapshot, Router, Qnty, trading, "
        "promotion, and replication execution remain unauthorized."
    )
    assert data["active_project"] is not None
    assert data["active_project"]["project_id"] == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_INPUT_MATERIALIZATION_V0"
    assert data["active_project"]["state"] == "ACTIVE"
    assert data["active_project"]["authority_level"] == "INPUT_MATERIALIZATION_ONLY"
    assert data["active_project"]["implementation_authorized"] is True
    assert data["active_project"]["frozen_preregistration_project_id"] == "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_PREREG_V0"
    assert data["active_project"]["frozen_preregistration_digest"] == "46f923023b4b696307da2b9d6fc4c8db9d04b40b012de35e0bf738cc03c4be57"
    assert "c59fe389e0fe05ae22120f59396c8c13a77110178ae06c634940a3be7bfb2d30" not in str(data["active_project"])
    assert data["current_permitted_next_action"] == expected_next_action
    _, _, registry = project_context.load_context_sources(ROOT)
    assert sum(record["state"] == "ACTIVE" for record in registry["project"]) == 1
    for prohibited in ("returns", "RV24", "regression", "replication classification", "Jigsaw evidence", "State Snapshot", "replication execution"):
        assert prohibited in data["current_permitted_next_action"]
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
