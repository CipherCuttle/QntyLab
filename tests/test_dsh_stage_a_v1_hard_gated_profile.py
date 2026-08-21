from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from qntylab.dsh_stage_a_v1_hard_orchestration import CLAUDE_TOOL, CODEX_TOOL


ROOT = Path(__file__).parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_v1_hard_orchestration_authorization_v0"
PROFILE = ARTIFACT / "profile"


def _block(text: str, row_id: str) -> str:
    match = re.search(rf"^    - id: {re.escape(row_id)}\n.*?(?=^    - id:|\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, row_id
    return match.group(0)


def test_v1_model_facing_routes_have_no_raw_provider_bypass():
    patch = (PROFILE / "cordis.patch.yml").read_text(encoding="utf-8")
    codex_tool = _block(patch, "tool-subagent-codex")
    claude_tool = _block(patch, "tool-subagent-claude-code")
    assert "provider: qntylab-gated-codex" in codex_tool
    assert "toolName: subagent_codex" in codex_tool
    assert "provider: qntylab-gated-claude-code" in claude_tool
    assert "toolName: subagent_claude_code" in claude_tool
    assert "provider: codex" not in codex_tool
    assert "provider: claude-code" not in claude_tool

    codex_gate = _block(patch, "qntylab-gated-codex")
    claude_gate = _block(patch, "qntylab-gated-claude-code")
    assert "rawProvider: codex" in codex_gate and f"toolName: {CODEX_TOOL}" in codex_gate
    assert "rawProvider: claude-code" in claude_gate and f"toolName: {CLAUDE_TOOL}" in claude_gate
    assert "@qntylab/dsh-gated-provider" in (PROFILE / "package.json").read_text(encoding="utf-8")


def test_v1_profile_is_distinct_and_declares_runtime_gate_bindings():
    v0 = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_authorization_v0/profile/cordis.patch.yml"
    v1 = PROFILE / "cordis.patch.yml"
    assert v0.read_bytes() != v1.read_bytes()
    text = v1.read_text(encoding="utf-8")
    assert "QNTYLAB_DSH_STAGE_A_STATE_PATH" in text
    assert "QNTYLAB_ROOT" in text
    assert "QNTYLAB_PYTHON" in text
    assert "SubagentProvider.start" in (PROFILE / "PROFILE.md").read_text(encoding="utf-8")


def test_gate_cli_consumes_state_and_denies_replayed_budget(tmp_path):
    state = tmp_path / "authority.json"
    command = [sys.executable, "-m", "qntylab.dsh_stage_a_v1_hard_orchestration", "--state", str(state)]
    first = subprocess.run([*command, "authorize", CODEX_TOOL], cwd=ROOT, text=True, capture_output=True, check=True)
    grant = json.loads(first.stdout)
    completed = subprocess.run(
        [*command, "complete", "--token", grant["token"], "--tool", CODEX_TOOL, "--role", grant["role"]],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(completed.stdout)["state"] == "TEST_REQUIRED"
    replay = subprocess.run([*command, "authorize", CODEX_TOOL], cwd=ROOT, text=True, capture_output=True)
    assert replay.returncode != 0
    assert "denied" in replay.stderr.lower()
