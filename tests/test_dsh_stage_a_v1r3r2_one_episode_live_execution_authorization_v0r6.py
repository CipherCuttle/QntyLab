from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ARTIFACT_ROOT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r6"
AUTH_PATH = ARTIFACT_ROOT / "authorization.json"
AUTH = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
REPAIR_SOURCE = ROOT / "qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py"
REPAIR_MERGE = "36e3085c18a747e3755097c97915f61f289d0835"
CANONICAL_MASTER = "e2b97a1478f29e6db3cc1918f1e90ff8547565a1"
REPAIR_CANDIDATE = "0178a1fd45984d1d71dec497b328078ebeae5a5a"
AUTH_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R6"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R6"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r6"
CLAIM_STATE = Path("/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r6/episode-1")
V0R5_STATE = Path("/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r5/episode-1")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def test_exact_canonical_repair_merge_and_parent_binding() -> None:
    assert _git("rev-parse", "origin/master").stdout.strip() == CANONICAL_MASTER
    assert _git("rev-parse", "HEAD").stdout.strip() == CANONICAL_MASTER
    assert _git("rev-list", "--parents", "-n", "1", CANONICAL_MASTER).stdout.split() == [
        CANONICAL_MASTER,
        REPAIR_MERGE,
        REPAIR_CANDIDATE,
    ]
    identity = AUTH["canonical_source_identity"]
    assert identity["canonical_master"] == CANONICAL_MASTER
    assert identity["canonical_merge_parents"] == [REPAIR_MERGE, REPAIR_CANDIDATE]
    assert identity["predecessor_required_state"] == "CLOSED_PASS"
    binding = AUTH["repair_predecessor_binding"]
    assert binding["authorization_canonical_merge"] == REPAIR_MERGE
    assert binding["authorization_candidate"] == REPAIR_CANDIDATE
    assert binding["historical_root_cause_reopened"] is False
    assert binding["v0r5_replay_authorized"] is False


def test_repaired_episode_claim_source_blob_and_digest_are_frozen() -> None:
    identity = AUTH["repaired_claim_identity"]
    assert identity["implementation_source_sha256"] == hashlib.sha256(REPAIR_SOURCE.read_bytes()).hexdigest()
    assert identity["implementation_git_blob"] == _git(
        "rev-parse", f"{CANONICAL_MASTER}:qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py"
    ).stdout.strip()
    assert identity["implementation_bound_to_canonical_master"] == CANONICAL_MASTER
    claim = AUTH["claim_contract"]
    assert claim["implementation_git_blob"] == identity["implementation_git_blob"]
    assert claim["implementation_source_sha256"] == identity["implementation_source_sha256"]
    assert identity["repair_authorization_artifact_sha256"] == hashlib.sha256(
        (CONTRACT_ROOT / "dsh_stage_a_claim_acquisition_transport_and_observability_repair_authorization_v0/authorization.json").read_bytes()
    ).hexdigest()
    assert identity["semantics"] == {
        "COMMITTED": "continue exactly once after durable claim completion and independent exact-SHA verification",
        "CONFIRMED_NO_REMOTE_WRITE": "record outcome, perform no provider I/O, and do not self-authorize retry",
        "WRITE_STATE_UNKNOWN": "record sanitized diagnostics, perform no provider I/O, and fail closed as BLOCK_NEVER_REPLAY",
    }


def test_pinned_dsh_contract_and_fixture_identities_are_unchanged() -> None:
    successor = AUTH["successor_contract_binding"]
    assert successor["qualified_launch_contract_digest"] == "50bd776263d05e9f2fe3e026c5e8904a12fa257a1667d11c1e22ef32376c24de"
    assert successor["historical_predecessor_contract_digest"] == "a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be"
    assert successor["pinned_dsh"] == {
        "repository": "deepseek-ai/deepseek-harness",
        "commit": "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca",
        "tree": "3bc8f89fe494a4755c188be354add4e8b1e7b188",
        "tag": "dsh-v0.1.0-rc.7",
    }
    assert successor["fixture"] == {
        "id": "STAGE_A_BOUNDED_RETRY_V0",
        "digest": "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552",
    }
    assert successor["historical_contract_substitution_allowed"] is False


def test_v0r6_is_fresh_one_episode_and_claim_absence_is_recorded() -> None:
    fresh = AUTH["fresh_identity"]
    assert fresh["future_activation_project_id"] == EXECUTION_ID
    assert fresh["episode_id"] == EPISODE_ID
    assert fresh["claim_remote_ref"] == CLAIM_REF
    assert fresh["episode_generation"] == "V0R6"
    assert fresh["collision_free_successor"] is True
    assert fresh["remote_claim_observation"] == "ABSENT"
    assert fresh["local_state_observation"] == "ABSENT"
    assert not CLAIM_STATE.exists()
    authority = AUTH["episode_authority"]
    assert authority["episode_count"] == authority["authorized_live_episodes"] == 1
    assert authority["second_episode_allowed"] is False
    assert authority["whole_episode_retry_allowed"] is False
    assert authority["timeout_allows_rerun"] is False
    assert authority["terminal_failure_allows_rerun"] is False
    claim = AUTH["claim_contract"]
    assert claim["created_during_authorization_construction"] is False
    assert claim["remote_claim_exists_at_construction"] is False
    assert claim["local_claim_exists_at_construction"] is False
    assert claim["production_claim_writes_during_authorization"] == 0
    assert claim["diagnostic_claim_writes_during_authorization"] == 0
    assert "-v0r5" in claim["historical_claim_refs_rejected"][-1]


def test_v0r5_is_read_only_historical_block_never_replay_state() -> None:
    protected = AUTH["v0r5_protection"]
    assert protected["terminal_state"] == "BLOCK_NEVER_REPLAY"
    assert protected["replay_allowed"] is False
    assert protected["claim_reset_allowed"] is False
    assert protected["delete_allowed"] is False
    assert protected["receipt_repair_allowed"] is False
    assert protected["second_episode_allowed"] is False
    assert protected["mutated_during_authorization"] is False
    assert V0R5_STATE.is_dir()
    assert sorted(path.name for path in V0R5_STATE.iterdir() if path.is_file()) == [
        "claim-intent.json",
        "claim.lock",
    ]
    assert not (V0R5_STATE / "claim-receipt.json").exists()


def test_parent_child_secret_order_and_fail_closed_claim_semantics() -> None:
    parent = AUTH["parent_policy"]
    assert (parent["provider"], parent["model"], parent["route"]) == ("openai", "gpt-5-mini", "llm-pi-ai")
    assert parent["maximum_logical_requests"] == 8
    assert parent["provider_internal_retries"] == 0
    assert parent["automatic_continuation"] is False
    assert parent["maximum_output_tokens"] == 4096
    assert parent["hard_spend_cap_usd"] == "1.00"
    assert parent["attempt_9_denied_before_provider_wire_io"] is True
    child = AUTH["child_policy"]
    assert child["exact_order"] == ["codex_initial", "claude_review", "codex_repair_if_critical_high", "claude_rereview_if_repaired"]
    assert child["codex_maximum_turns"] == child["claude_maximum_turns"] == 2
    assert child["claude_hard_read_only"] is True
    assert child["claude_allowed_tools"] == ["Read", "Glob", "Grep"]
    assert set(child["claude_denied_tools"]) >= {"Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"}
    order = AUTH["action_time_gate_order"]
    assert order.index("real secret read") > order.index("all remaining non-secret gates")
    assert order.index("create-only V0R6 claim using repaired claim primitive") > order.index("real secret read")
    assert order.index("actual pinned DSH invocation") > order.index("create-only V0R6 claim using repaired claim primitive")
    assert AUTH["repaired_claim_identity"]["semantics"]["CONFIRMED_NO_REMOTE_WRITE"].endswith("do not self-authorize retry")
    assert AUTH["repaired_claim_identity"]["semantics"]["WRITE_STATE_UNKNOWN"].endswith("BLOCK_NEVER_REPLAY")


def test_authorization_has_zero_activity_and_cannot_self_activate() -> None:
    assert AUTH["construction_receipts"] == {
        "secret_reads": 0,
        "production_claim_writes": 0,
        "diagnostic_claim_writes": 0,
        "dsh_invocations": 0,
        "provider_calls": 0,
        "real_model_calls": 0,
        "codex_turns": 0,
        "claude_turns": 0,
        "fixture_mutations": 0,
        "v0r6_activation": False,
        "v0r6_episode_consumed": False,
        "spend_usd": "0",
    }
    firewall = AUTH["authority_firewall"]
    assert firewall["v0r6_created"] is False
    assert firewall["v0r6_activated"] is False
    assert firewall["live_execution_performed"] is False
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["active_project_after_closure"] == "NONE"
    assert AUTH["activation_prerequisite"]["branch_local_candidate_does_not_self_authorize"] is True
    assert AUTH["canonicalization"]["merge_authority"] == "NO"
    auth_rel = "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r6/authorization.json"
    activation_rel = "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_v0r6/activation.json"
    assert _git("cat-file", "-e", f"{CANONICAL_MASTER}:{auth_rel}").returncode != 0
    assert _git("cat-file", "-e", f"{CANONICAL_MASTER}:{activation_rel}").returncode != 0


def test_registry_and_generated_roadmap_bind_inactive_v0r6_authorization() -> None:
    registry = tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))
    record = next(row for row in registry["project"] if row["project_id"] == AUTH_ID)
    assert record["state"] == "CLOSED_PASS"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["activation_exists"] is False
    assert record["effective_execution_authority"] is False
    assert record["canonical_base_sha"] == CANONICAL_MASTER
    assert record["canonical_predecessor_merge"] == REPAIR_MERGE
    assert record["authorization_artifact_sha256"] == hashlib.sha256(AUTH_PATH.read_bytes()).hexdigest()
    assert record["authorization_artifact_git_blob"] == _git(
        "hash-object", str(AUTH_PATH.relative_to(ROOT))
    ).stdout.strip()
    assert record["claim_implementation_git_blob"] == AUTH["repaired_claim_identity"]["implementation_git_blob"]
    assert record["claim_implementation_sha256"] == AUTH["repaired_claim_identity"]["implementation_source_sha256"]
    assert record["claim_created"] is False
    assert record["authorization_phase_secret_reads"] == 0
    assert record["hostile_review_count"] == 1
    assert record["hostile_review_verdict"] == "PASS"
    assert record["hostile_governance_critical_total"] == 0
    assert record["hostile_governance_high_total"] == 0
    _, _, loaded = project_context.load_context_sources(ROOT)
    validated = project_context.validate_projects_registry(ROOT, loaded)
    projection = project_context.execution_authority_projection(ROOT, validated)
    assert projection["issues"] == []
    assert projection["active_project"] is None
    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    assert "DSH Stage-A V1R3R2 fresh one-episode live execution authorization V0R6" in roadmap
    assert "V0R6 activation" in roadmap
    assert "Do not activate, execute" in roadmap
