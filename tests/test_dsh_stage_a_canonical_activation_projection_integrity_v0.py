from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
ACTIVATION_PATH = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3r2_one_episode_live_execution_v0/activation.json"
)
PROJECT_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0"


def _source_records() -> tuple[dict, dict]:
    activation = json.loads(ACTIVATION_PATH.read_text(encoding="utf-8"))
    _, _, registry = project_context.load_context_sources(ROOT)
    record = next(item for item in registry["project"] if item["project_id"] == PROJECT_ID)
    return activation, copy.deepcopy(record)


def _commit(root: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=projection-test",
            "-c",
            "user.email=projection-test@example.invalid",
            "commit",
            "-qm",
            message,
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def _synthetic_repo(tmp_path: Path, *, state: str, canonical: bool, terminal: bool) -> tuple[Path, dict]:
    activation, record = _source_records()
    root = tmp_path / "repo"
    (root / "artifact").mkdir(parents=True)
    (root / "result").mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    base_sha = _commit(root, "base")

    activation["canonicalization"]["candidate_base_sha"] = base_sha
    (root / "artifact/activation.json").write_text(json.dumps(activation, indent=2) + "\n", encoding="utf-8")
    record["authoritative_artifacts"] = ["artifact/activation.json"]
    record["state"] = state
    if state == "ACTIVE":
        record["authority_level"] = activation["active_execution_project"]["authority_level"]
        record["implementation_authorized"] = True
        record["implementation_completed"] = False
    elif terminal:
        (root / "result/execution_evidence.json").write_text("{}\n", encoding="utf-8")
        (root / "result/closure.md").write_text("terminal closure\n", encoding="utf-8")
        record["authoritative_artifacts"] += ["result/execution_evidence.json", "result/closure.md"]
        record["implementation_authorized"] = False
        record["implementation_completed"] = True
        record["episode_consumed"] = False
        record["active_project_after_closure"] = "NONE"
        record["terminal_outcome"] = "BLOCK_AUTHORITY"
    else:
        record["implementation_authorized"] = False
        record["implementation_completed"] = True
        record["active_project_after_closure"] = "NONE"
        record["terminal_outcome"] = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_AUTHORIZATION_AVAILABLE"

    head_sha = _commit(root, "activation projection candidate")
    canonical_sha = head_sha if canonical else base_sha
    subprocess.run(["git", "-C", str(root), "update-ref", "refs/remotes/origin/master", canonical_sha], check=True)
    return root, record


def test_historical_pr183_contradiction_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, record = _synthetic_repo(tmp_path, state="CLOSED_PASS", canonical=True, terminal=False)
    monkeypatch.setattr(
        project_context,
        "load_context_sources",
        lambda _root, **_kwargs: (
            {"data": {"registry_status": "NOT_ESTABLISHED"}, "authority": {"research_ledger_root": "ledger"}},
            {},
            {"schema_version": 1, "project": [record]},
        ),
    )
    monkeypatch.setattr(project_context, "validate_adr_registry", lambda _root, _registry, **_kwargs: {})
    monkeypatch.setattr(
        project_context,
        "compile_context_spine",
        lambda _root: {"packet_status": project_context.CONTEXT_SPINE_COMPILED, "conflicts": []},
    )
    monkeypatch.setattr(project_context.research_ledger, "doctor", lambda _root: [])
    issues = project_context.doctor(root)
    assert issues
    assert "execution authority projection conflict" in issues[0]


def test_branch_local_candidate_is_not_effective_authority(tmp_path: Path) -> None:
    root, record = _synthetic_repo(tmp_path, state="ACTIVE", canonical=False, terminal=False)
    projection = project_context.execution_authority_projection(root, {PROJECT_ID: record})
    assert projection["issues"] == []
    assert projection["active_project"] is None
    assert projection["identity_by_project"][PROJECT_ID]["effective"] is False


def test_canonical_activation_projects_exactly_one_active_execution_project(tmp_path: Path) -> None:
    root, record = _synthetic_repo(tmp_path, state="ACTIVE", canonical=True, terminal=False)
    projection = project_context.execution_authority_projection(root, {PROJECT_ID: record})
    assert projection["issues"] == []
    assert projection["active_project"]["project_id"] == PROJECT_ID
    assert projection["active_project"]["state"] == "ACTIVE"
    assert projection["active_project"]["implementation_authorized"] is True
    assert projection["active_project"]["implementation_completed"] is False
    assert projection["active_project"]["episode_consumed"] is False
    assert len([item for item in (projection["active_project"],) if item["state"] == "ACTIVE"]) == 1


def test_terminal_closure_removes_effective_execution_authority(tmp_path: Path) -> None:
    root, record = _synthetic_repo(tmp_path, state="CLOSED_BLOCKED", canonical=True, terminal=True)
    projection = project_context.execution_authority_projection(root, {PROJECT_ID: record})
    assert projection["issues"] == []
    assert projection["active_project"] is None


def test_canonical_repository_preserves_pr184_closed_block_authority() -> None:
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    assert projection["active_project"]["project_id"] == "QNTYSPOT_INK_SHADOW_PERFORMANCE_V0"
