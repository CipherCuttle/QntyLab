from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ARTIFACT_ROOT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r7"
AUTH_PATH = ARTIFACT_ROOT / "authorization.json"
AUTH = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
ENFORCEMENT_SOURCE = ROOT / "qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py"
CANONICAL_MASTER = "2c0804aeecdf19923036f17531c0d43d433c4aa0"
# The canonical master advanced to the exact authorization merge (PR #227)
# after this authorization phase merged; keep the artifact-bound base constant
# separate from the current canonical master exactly as the V0R6 test does.
CURRENT_CANONICAL_MASTER = "908dfed34b5f22bb99e77c146a757a8e6299064c"
ACTIVATION_MERGE = "1b0e936e9f1f696cd586e1cd1ea1bf3a5e1ae4c4"
CANONICAL_PARENT1 = "3a0e1aa15c6c5d01a93dd7e3460dd3a736c46474"
CANONICAL_PARENT2 = "835151b59c6113d11eeb82dd8017bf6809248733"
EXECUTION_CONTRACT_ROOT = "cf1aff079d56428753bf8f58f1848839da35cfb9f75104fc1fd03cd13056c1e2"
AUTH_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R7"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R7"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r7"
CLAIM_STATE = Path("/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r7/episode-1")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def test_exact_canonical_master_and_parent_binding() -> None:
    assert _git("rev-parse", "origin/master").stdout.strip() == ACTIVATION_MERGE
    assert _git("merge-base", "--is-ancestor", CANONICAL_MASTER, CURRENT_CANONICAL_MASTER).returncode == 0
    assert _git("merge-base", "--is-ancestor", CANONICAL_MASTER, "HEAD").returncode == 0
    assert _git("rev-list", "--parents", "-n", "1", CANONICAL_MASTER).stdout.split() == [
        CANONICAL_MASTER,
        CANONICAL_PARENT1,
        CANONICAL_PARENT2,
    ]
    identity = AUTH["canonical_source_identity"]
    assert identity["canonical_master"] == CANONICAL_MASTER
    assert identity["canonical_merge_parents"] == [CANONICAL_PARENT1, CANONICAL_PARENT2]
    assert identity["predecessor_required_state"] == "CLOSED_PASS"
    assert identity["git_wins_over_prompt_memory_or_handoff"] is True


def test_source_root_irreducible_independently_bound() -> None:
    invariant = AUTH["source_root_invariant"]
    assert invariant["authorized_execution_source_sha"] == CANONICAL_MASTER
    assert invariant["execution_contract_root"] == EXECUTION_CONTRACT_ROOT
    assert invariant["source_is_git_commit_object"] is True
    assert invariant["root_is_content_addressed_sha256"] is True
    assert invariant["source_and_root_independently_bound"] is True
    assert invariant["root_not_sha256_of_source"] is True
    assert invariant["source_is_ancestor_of_execution_checkout"] is True
    assert invariant["source_is_ancestor_of_canonical_commit"] is True
    assert invariant["revocation_state"] == "NOT_REVOKED"
    assert invariant["no_surrogate_sha256_source_identity"] is True
    assert invariant["mismatch_fails_closed_before_claim_committed"] is True
    # The source is a real git commit object.
    assert _git("cat-file", "-e", f"{CANONICAL_MASTER}^{{commit}}").returncode == 0
    # The root is a content-addressed sha256, not a git commit object.
    assert _git("cat-file", "-e", f"{EXECUTION_CONTRACT_ROOT}^{{commit}}").returncode != 0


def test_claim_owner_is_parent_guard_only() -> None:
    ownership = AUTH["claim_ownership"]
    assert ownership["sole_owner"] == "parent_enforcement_guard_ensureClaim_inside_reserve_before_next"
    assert ownership["external_orchestration_claim_acquisition"] is False
    assert ownership["dual_owner_claim_design"] is False
    assert ownership["pre_claim_shell_orchestration"] is False
    assert ownership["production_owner_transports_complete_resolved_binding"] is True
    assert ownership["production_owner_does_not_re_derive_or_default_identities"] is True


def test_repaired_claim_source_blob_and_digest_are_frozen() -> None:
    identity = AUTH["repaired_claim_identity"]
    assert identity["implementation_source_sha256"] == hashlib.sha256(ENFORCEMENT_SOURCE.read_bytes()).hexdigest()
    assert identity["implementation_git_blob"] == _git(
        "rev-parse", f"{CANONICAL_MASTER}:qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py"
    ).stdout.strip()
    assert identity["implementation_bound_to_canonical_master"] == CANONICAL_MASTER
    assert identity["claim_source_seam"] == "EXACT_IMMUTABLE_COMMIT_SHA"
    assert identity["claim_source_seam_implemented"] is True
    assert identity["claim_source_seam_checks"] == [
        "EXACT_FORMAT",
        "OBJECT_EXISTS",
        "CURRENT_CHECKOUT_RELATION",
        "CANONICAL_ANCESTRY",
        "REVOCATION_AND_SUPERSESSION",
        "RESOLVED_EXECUTION_INPUTS",
        "FAIL_CLOSED",
    ]
    claim = AUTH["claim_contract"]
    assert claim["implementation_git_blob"] == identity["implementation_git_blob"]
    assert claim["implementation_source_sha256"] == identity["implementation_source_sha256"]


def test_current_contract_root_and_digests_are_bound() -> None:
    successor = AUTH["successor_contract_binding"]
    assert successor["qualified_launch_contract_digest"] == EXECUTION_CONTRACT_ROOT
    assert successor["historical_predecessor_contract_digest"] == "e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82"
    assert successor["runtime_manifest_digest"] == "0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3"
    assert successor["executable_identity_digest"] == "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"
    assert successor["composite_launch_policy_digest"] == "018dda96bd3960b232d78a33e472a5161c112abd5e76dd954db19d47ace8e5d5"
    assert successor["composite_launcher_digest"] == "bf0baf30cc5b6ca9206c0bf4ea6357cfc37fc60b11ddf1ee06e8a9f8b252634c"
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


def test_v0r7_is_fresh_one_episode_and_claim_absence_is_recorded() -> None:
    fresh = AUTH["fresh_identity"]
    assert fresh["future_activation_project_id"] == EXECUTION_ID
    assert fresh["episode_id"] == EPISODE_ID
    assert fresh["claim_remote_ref"] == CLAIM_REF
    assert fresh["episode_generation"] == "V0R7"
    assert fresh["collision_free_successor"] is True
    assert fresh["remote_claim_observation"] == "ABSENT"
    assert fresh["local_state_observation"] == "ABSENT"
    assert fresh["v0r5_reused"] is False
    assert fresh["v0r6_reused"] is False
    assert not CLAIM_STATE.exists()


def test_episode_authority_is_single_and_no_rerun() -> None:
    episode = AUTH["episode_authority"]
    assert episode["episode_count"] == 1
    assert episode["authorized_live_episodes"] == 1
    assert episode["second_episode_allowed"] is False
    assert episode["whole_episode_retry_allowed"] is False
    assert episode["activation_consumes_episode"] is False
    assert episode["authorization_construction_consumes_episode"] is False
    assert episode["timeout_seconds"] == 1800
    assert episode["timeout_allows_rerun"] is False
    assert episode["terminal_failure_allows_rerun"] is False
    assert episode["claim_crossed_timeout_or_crash_behavior"] == "BLOCK_NEVER_REPLAY"


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
    assert order.index("create-only V0R7 claim using repaired claim primitive") > order.index("real secret read")
    assert order.index("actual pinned DSH invocation") > order.index("create-only V0R7 claim using repaired claim primitive")
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
        "v0r7_activation": False,
        "v0r7_episode_consumed": False,
        "spend_usd": "0",
    }
    firewall = AUTH["authority_firewall"]
    assert firewall["v0r7_created"] is False
    assert firewall["v0r7_activated"] is False
    assert firewall["live_execution_performed"] is False
    assert firewall["stage_b_authorized"] is False
    assert firewall["qnty_runtime_authority"] == "NONE"
    assert firewall["active_project_after_closure"] == "NONE"
    assert AUTH["activation_prerequisite"]["branch_local_candidate_does_not_self_authorize"] is True
    assert AUTH["canonicalization"]["merge_authority"] == "NO"
    auth_rel = "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r7/authorization.json"
    activation_rel = "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r7/activation.json"
    # The authorization artifact exists in the working tree; the activation
    # artifact must NOT exist (this phase constructs authorization only).
    assert (ROOT / auth_rel).is_file()
    assert not (ROOT / activation_rel).exists()


def test_registry_and_generated_roadmap_bind_inactive_v0r7_authorization() -> None:
    registry = tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))
    record = next(row for row in registry["project"] if row["project_id"] == AUTH_ID)
    assert record["state"] == "PLANNED_NOT_AUTHORIZED"
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is False
    # The separate V0R7 activation candidate now exists on its own branch and
    # is recorded by the registry; it does not self-authorize before its own
    # exact canonical merge.
    assert record["activation_exists"] is True
    assert record["effective_execution_authority"] is False
    assert record["canonical_base_sha"] == CANONICAL_MASTER
    assert record["canonical_predecessor_merge"] == CANONICAL_PARENT1
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
    # The only ACTIVE project is the QntySpot DEV acquisition; V0R7 is not active.
    assert projection["active_project"] is not None
    assert projection["active_project"]["project_id"] == "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_V0"
    assert projection["active_project"]["project_id"] != AUTH_ID
    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    assert "DSH Stage-A V1R3R2 fresh one-episode live execution authorization V0R7" in roadmap
    assert "V0R7 activation" in roadmap
    assert "Do not activate, execute" in roadmap