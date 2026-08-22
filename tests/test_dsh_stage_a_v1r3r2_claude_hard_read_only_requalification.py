import json
import hashlib
from copy import deepcopy
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0"


def test_phase_contract_binds_new_claude_policy_and_preserves_no_live_boundary():
    qualification = json.loads((PHASE / "qualification.json").read_text(encoding="utf-8"))
    assert qualification["sourceIdentity"] == {
        "repository": "deepseek-ai/deepseek-harness",
        "commit": "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca",
        "tree": "3bc8f89fe494a4755c188be354add4e8b1e7b188",
        "tag": "dsh-v0.1.0-rc.7",
    }
    policy = qualification["claudePolicy"]
    assert policy["allowedTools"] == ["Read", "Glob", "Grep"]
    assert policy["tools"] == ["Read", "Glob", "Grep"]
    assert policy["disallowedTools"] == ["Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion"]
    assert policy["settingSources"] == []
    assert policy["strictMcpConfig"] is True
    assert policy["mcpServers"] == {}
    assert policy["agents"] == {}
    assert policy["plugins"] == []
    assert policy["permissionMode"] == "dontAsk"
    assert policy["persistence"] is False
    assert all(policy[key] is False for key in (
        "writeAllowed", "editAllowed", "bashAllowed", "agentAllowed", "taskAllowed",
        "mcpAllowed", "delegationAllowed", "askUserQuestionAllowed",
    ))
    assert qualification["security"]["realSecretRead"] is False
    assert qualification["security"]["liveStageAEpisodes"] == 0
    assert qualification["security"]["spendUsd"] == 0
    assert qualification["oldAuthorityCompatibleWithNewRuntime"] is False


def test_claude_patch_is_pinned_to_actual_options_seam():
    patch = (PHASE / "repairs/claude-hard-read-only.patch").read_text(encoding="utf-8")
    for needle in (
        "tools: [...CLAUDE_ALLOWED_TOOLS]",
        "allowedTools: [...CLAUDE_ALLOWED_TOOLS]",
        "disallowedTools: [...CLAUDE_DISALLOWED_TOOLS]",
        "settingSources: []",
        "strictMcpConfig: true",
        "officialQuery",
    ):
        assert needle in patch


def test_project_registry_closes_without_new_authority():
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    record = projects["DSH_STAGE_A_V1R3R2_CLAUDE_HARD_READ_ONLY_REPAIR_AND_REQUALIFICATION_V0"]
    assert record["state"] == "CLOSED_PASS"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["active_project_after_closure"] == "NONE"
    assert record["stage_b_authorized"] is False
    assert record["qnty_runtime_authority"] == "NONE"


def _canonical_digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_policy_and_binding_digest_regressions_are_sensitive():
    digests = json.loads((PHASE / "evidence/digests.json").read_text(encoding="utf-8"))
    launch_policy = digests["components"]["launchPolicy"]
    baseline_launch = digests["LAUNCH_POLICY_DIGEST"]
    baseline_qualified = digests["QUALIFIED_LAUNCH_CONTRACT_DIGEST"]

    mutations = (
        ("allowedTools", lambda policy: policy["claudePolicy"]["allowedTools"].append("Write")),
        ("removeGrep", lambda policy: policy["claudePolicy"]["allowedTools"].remove("Grep")),
        ("bashAllowed", lambda policy: policy["claudePolicy"].__setitem__("bashAllowed", True)),
        ("claudeRepairDigest", lambda policy: policy.__setitem__("claudeRepairDigest", "mutated")),
        ("sdkVersion", lambda policy: policy["claudeSdkIdentity"].__setitem__("version", "mutated")),
    )
    for name, mutate in mutations:
        mutated = deepcopy(launch_policy)
        mutate(mutated)
        mutated_launch = _canonical_digest(mutated)
        mutated_qualified = _canonical_digest({
            "phaseId": digests["components"]["runtimeIdentity"]["phaseId"],
            "RUNTIME_MANIFEST_DIGEST": digests["RUNTIME_MANIFEST_DIGEST"],
            "EXECUTABLE_IDENTITY_DIGEST": digests["EXECUTABLE_IDENTITY_DIGEST"],
            "LAUNCH_POLICY_DIGEST": mutated_launch,
        })
        assert mutated_launch != baseline_launch, name
        assert mutated_qualified != baseline_qualified, name
