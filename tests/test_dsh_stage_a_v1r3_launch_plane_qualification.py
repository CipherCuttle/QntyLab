from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = ROOT / (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "dsh_stage_a_v1r3_launch_plane_qualification_v0"
)
JS_TEST_FILE = PHASE_DIR / "test" / "qntylab-dsh-v1r3.test.mjs"
QUALIFICATION_JSON = PHASE_DIR / "qualification.json"
PHASE_MD = PHASE_DIR / "PHASE.md"


def _require_node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node executable not available on PATH")
    return node


def test_phase_changeset_files_present() -> None:
    for relative in [
        "PHASE.md",
        "qualification.json",
        "hostile_review.md",
        "materializer/qntylab-materialize-dsh-runtime.mjs",
        "launcher/qntylab-launch-dsh.mjs",
        "repairs/codex-executable-binding.patch",
        "mock/qualification-openai-mock.mjs",
        "test/qntylab-dsh-v1r3.test.mjs",
    ]:
        assert (PHASE_DIR / relative).is_file(), f"missing V1R3 changeset file: {relative}"


def test_qualification_json_declares_offline_bounded_authority() -> None:
    data = json.loads(QUALIFICATION_JSON.read_text())
    assert data["project_id"] == "DSH_STAGE_A_V1R3_LAUNCH_PLANE_QUALIFICATION_V0"
    assert data["authority"] == "BOUNDED_OFFLINE_LAUNCH_PLANE_QUALIFICATION"
    assert data["active_projects_after_closure"] == "NONE"
    counters = data["invariant_counters"]
    assert counters["paid_model_requests"] == 0
    assert counters["codex_model_turns"] == 0
    assert counters["claude_model_turns"] == 0
    assert counters["spend_usd"] == 0.0
    assert counters["secret_read"] is False
    # This phase does not silently claim a real materialization ran.
    residual = data["residual_scope_not_closed_by_this_run"]
    assert residual["real_pinned_commit_materialization_executed"] is False
    assert residual["qualified_launch_contract_digest_issued"] is False


def test_phase_doc_names_predecessor_and_boundary() -> None:
    text = PHASE_MD.read_text()
    assert "f3c864bead33d383a581200d582d1e62baca02c6" in text
    assert "549e8e947086aeef1ec18ea77dfb18e6f30f36ac" in text
    assert "Stage B" in text


def test_offline_node_suite_passes() -> None:
    node = _require_node()
    result = subprocess.run(
        [node, "--test", str(JS_TEST_FILE)],
        cwd=PHASE_DIR / "test",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"offline node:test suite failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "# fail 0" in result.stdout


def test_codex_repair_patch_is_flagged_as_unverified() -> None:
    # This patch cannot be verified against a real pinned checkout in this
    # offline environment (see PHASE.md); it must say so rather than being
    # silently presented as landed.
    text = (PHASE_DIR / "repairs" / "codex-executable-binding.patch").read_text()
    assert "NOT YET VERIFIED" in text


def test_registered_in_docs_state_and_roadmap() -> None:
    projects_toml = (ROOT / "docs/state/projects.toml").read_text()
    assert "DSH_STAGE_A_V1R3_LAUNCH_PLANE_QUALIFICATION_V0" in projects_toml
    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text()
    assert "V1R3" in roadmap
