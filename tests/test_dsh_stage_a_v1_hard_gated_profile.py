from __future__ import annotations

import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import yaml

from qntylab.dsh_stage_a_v1_hard_orchestration import CLAUDE_TOOL, CODEX_TOOL


ROOT = Path(__file__).parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_v1_hard_orchestration_authorization_v0"
PROFILE = ARTIFACT / "profile"


# Exact child/delegation rows read from the pinned DSH base composition at
# 99f6f02fecdb7dff40c3fbc9470f5907c29f74ca.  The test below applies the
# pinned include patch semantics to these rows and then inspects the composed
# result; it does not treat the profile patch text as the composition.
PINNED_BASE_CHILD_ROWS = [
    {"id": "subagent", "name": "@deepseek-ai/dsh-subagent"},
    {
        "id": "subagent-spawn-in-process",
        "name": "@deepseek-ai/dsh-subagent-spawn-in-process",
        "config": {"providerName": "spawn"},
    },
    {
        "id": "subagent-fork-in-process",
        "name": "@deepseek-ai/dsh-subagent-fork-in-process",
        "config": {"providerName": "fork"},
    },
    {"id": "tool-subagent-control", "name": "@deepseek-ai/dsh-tool-subagent-control"},
    {"id": "tool-subagent-list-agents", "name": "@deepseek-ai/dsh-tool-subagent-control/list-agents"},
    {
        "id": "tool-subagent",
        "name": "@deepseek-ai/dsh-tool-subagent",
        "config": {"provider": "spawn", "toolName": "subagent", "backgroundMode": "continuable"},
    },
    {
        "id": "tool-subagent-fork",
        "name": "@deepseek-ai/dsh-tool-subagent",
        "config": {"provider": "fork", "toolName": "subagent_fork", "backgroundMode": "one-shot"},
    },
    {"id": "tool-subagent-report", "name": "@deepseek-ai/dsh-tool-subagent-report"},
    {
        "id": "workflow-worker-thread",
        "name": "@deepseek-ai/dsh-workflow-worker-thread",
        "config": {"provider": "spawn"},
    },
    {"id": "tool-workflow", "name": "@deepseek-ai/dsh-tool-workflow"},
    {"id": "tool-ralph", "name": "@deepseek-ai/dsh-tool-ralph"},
]
MODEL_FACING_DELEGATION_IDS = frozenset(
    {
        "tool-subagent-control",
        "tool-subagent-list-agents",
        "tool-subagent",
        "tool-subagent-fork",
        "tool-subagent-report",
        "tool-workflow",
        "tool-ralph",
        "tool-subagent-codex",
        "tool-subagent-claude-code",
    }
)


class _PinnedPatchLoader(yaml.SafeLoader):
    pass


_PinnedPatchLoader.add_constructor(
    "tag:yaml.org,2002:js",
    lambda loader, node: f"!!js {loader.construct_scalar(node)}",
)


def _compose_pinned_rows():
    """Mirror pinned include.applyEntryPatches for the relevant rows."""

    rows = deepcopy(PINNED_BASE_CHILD_ROWS)
    index = {row["id"]: row for row in rows}
    for patch in yaml.load(
        (PROFILE / "cordis.patch.yml").read_text(encoding="utf-8"),
        Loader=_PinnedPatchLoader,
    ):
        inserts = patch.get("insert")
        if inserts is not None:
            rows.extend(deepcopy(inserts))
            index.update({row["id"]: row for row in inserts})
            continue
        if patch["id"] not in index:
            continue
        target = index[patch["id"]]
        for key, value in patch.items():
            if key != "id":
                target[key] = deepcopy(value)
    return rows


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


def test_v1_composed_profile_exposes_only_the_two_gated_child_routes():
    composed = _compose_pinned_rows()
    delegation_rows = [row for row in composed if row["id"] in MODEL_FACING_DELEGATION_IDS]
    enabled = [row for row in delegation_rows if not row.get("disabled", False)]
    assert [row["id"] for row in enabled] == ["tool-subagent-codex", "tool-subagent-claude-code"]
    assert enabled[0]["config"] == {
        "provider": "qntylab-gated-codex",
        "toolName": "subagent_codex",
        "backgroundMode": "one-shot",
        "maxDepth": "provider-managed",
    }
    assert enabled[1]["config"] == {
        "provider": "qntylab-gated-claude-code",
        "toolName": "subagent_claude_code",
        "backgroundMode": "one-shot",
        "maxDepth": "provider-managed",
    }

    disabled_ids = {row["id"] for row in delegation_rows if row.get("disabled") is True}
    assert disabled_ids == MODEL_FACING_DELEGATION_IDS - {"tool-subagent-codex", "tool-subagent-claude-code"}
    assert {row["config"]["provider"] for row in enabled} == {
        "qntylab-gated-codex",
        "qntylab-gated-claude-code",
    }
    assert all(row.get("config", {}).get("provider") not in {"spawn", "fork", "raw-codex", "raw-claude-code"} for row in enabled)


def test_authorization_artifact_records_alternate_surface_closure():
    authorization = json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))
    authority = authorization["delegation_authority"]
    integration = authorization["gated_provider_integration"]
    assert authority["alternate_delegation_surfaces_disabled"] is True
    assert authority["only_gated_child_routes_model_visible"] is True
    assert authority["generic_spawn_executable"] is False
    assert authority["generic_fork_executable"] is False
    assert authority["workflow_child_bypass_executable"] is False
    assert integration["final_model_facing_delegation_tools"] == ["subagent_codex", "subagent_claude_code"]
    assert integration["raw_codex_tool_route"] is False
    assert integration["raw_claude_code_tool_route"] is False
    inspected = integration["pinned_base_child_rows_inspected"]
    assert inspected["source_commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert set(inspected["disabled_rows"]) == {
        "subagent-spawn-in-process",
        "subagent-fork-in-process",
        "tool-subagent-control",
        "tool-subagent-list-agents",
        "tool-subagent",
        "tool-subagent-fork",
        "tool-subagent-report",
        "workflow-worker-thread",
        "tool-workflow",
        "tool-ralph",
    }


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
