from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ACTIVATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r7/activation.json"
AUTHORIZATION_PATH = CONTRACT_ROOT / (
    "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r7/authorization.json"
)
V0R5_STATE = Path(
    "/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r5/episode-1"
)
V0R6_STATE = Path(
    "/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r6/episode-1"
)
V0R7_STATE = Path(
    "/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r7/episode-1"
)

# Frozen canonical binds for the V0R7 activation candidate.  The current
# canonical master IS the authorization merge (PR #227); the authorized
# execution source is independently bound and must never be conflated with it.
CURRENT_CANONICAL_MASTER = "908dfed34b5f22bb99e77c146a757a8e6299064c"
AUTHORIZATION_MERGE = "908dfed34b5f22bb99e77c146a757a8e6299064c"
AUTHORIZATION_MERGE_PARENTS = [
    "2c0804aeecdf19923036f17531c0d43d433c4aa0",
    "a8f1d3eb32bd8c14e6dee74a3396e56fb0c60fda",
]
AUTHORIZED_EXECUTION_SOURCE_SHA = "2c0804aeecdf19923036f17531c0d43d433c4aa0"
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R7"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R7"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r7"
AUTH_SHA256 = "e3543b3a0163f783b7e4404bfccc60d9fe2ad2bc898d11e81e0dd13a90000da8"
AUTH_BLOB = "564aa9592f818900c79a8bea4f3954cb460fd132"
CLAIM_BLOB = "6275cdbea5ceb9f13986fa1f42303a84f00f5a9c"
CLAIM_SHA256 = "086b46126b198ece22ec415b26f00bc6be1a0078968b2cda0d87e6b89f281a88"
CONTRACT_DIGEST = "cf1aff079d56428753bf8f58f1848839da35cfb9f75104fc1fd03cd13056c1e2"
RUNTIME_MANIFEST_DIGEST = "0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3"
EXECUTABLE_IDENTITY_DIGEST = "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"
COMPOSITE_LAUNCHER_DIGEST = "bf0baf30cc5b6ca9206c0bf4ea6357cfc37fc60b11ddf1ee06e8a9f8b252634c"
LAUNCH_POLICY_DIGEST = "018dda96bd3960b232d78a33e472a5161c112abd5e76dd954db19d47ace8e5d5"
MATERIALIZER_DIGEST = "ce18ebb9bb65cc01a07509189437cd1041ad09afaaee5ba318a6e822d82a09be"
FIXTURE_DIGEST = "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def test_current_canonical_master_and_frozen_authorization_identity() -> None:
    assert _git("rev-parse", "origin/master").stdout.strip() == CURRENT_CANONICAL_MASTER
    assert (
        _git("merge-base", "--is-ancestor", AUTHORIZED_EXECUTION_SOURCE_SHA, CURRENT_CANONICAL_MASTER).returncode
        == 0
    )
    assert _git("rev-list", "--parents", "-n", "1", AUTHORIZATION_MERGE).stdout.split() == [
        AUTHORIZATION_MERGE,
        *AUTHORIZATION_MERGE_PARENTS,
    ]
    assert hashlib.sha256(AUTHORIZATION_PATH.read_bytes()).hexdigest() == AUTH_SHA256
    assert _git("rev-parse", f"origin/master:{AUTHORIZATION_PATH.relative_to(ROOT)}").stdout.strip() == AUTH_BLOB
    authorization = _load(AUTHORIZATION_PATH)
    assert authorization["project_id"] == AUTHORIZATION_ID
    identity = _load(ACTIVATION_PATH)["authorization_identity"]
    assert identity["authorization_merge"] == AUTHORIZATION_MERGE
    assert identity["authorization_merge_parents"] == AUTHORIZATION_MERGE_PARENTS
    assert identity["authorization_artifact_sha256"] == AUTH_SHA256
    assert identity["authorization_artifact_git_blob"] == AUTH_BLOB


def test_repaired_claim_identity_and_independent_source_root_binding_are_frozen() -> None:
    activation = _load(ACTIVATION_PATH)
    claim = activation["repaired_claim_identity"]
    assert hashlib.sha256((ROOT / claim["implementation_path"]).read_bytes()).hexdigest() == CLAIM_SHA256
    assert _git("rev-parse", f"origin/master:{claim['implementation_path']}").stdout.strip() == CLAIM_BLOB
    assert claim["implementation_git_blob"] == CLAIM_BLOB
    assert claim["implementation_source_sha256"] == CLAIM_SHA256
    # Explicit non-conflation: the execution source SHA and the contract root
    # are bound separately; neither is derived from the other, and the source
    # is independent from the authorization merge commit itself.
    assert activation["authorized_execution_source_sha"] == AUTHORIZED_EXECUTION_SOURCE_SHA
    assert activation["execution_contract_root"] == CONTRACT_DIGEST
    invariant = activation["source_root_invariant"]
    assert invariant["root_not_sha256_of_source"] is True
    assert invariant["source_and_root_independently_bound"] is True
    assert AUTHORIZED_EXECUTION_SOURCE_SHA != AUTHORIZATION_MERGE
    runtime = activation["runtime_identity"]
    assert runtime["qualified_launch_contract_digest"] == CONTRACT_DIGEST
    assert runtime["runtime_manifest_digest"] == RUNTIME_MANIFEST_DIGEST
    assert runtime["executable_identity_digest"] == EXECUTABLE_IDENTITY_DIGEST
    assert runtime["composite_launcher_digest"] == COMPOSITE_LAUNCHER_DIGEST
    assert runtime["launch_policy_digest"] == LAUNCH_POLICY_DIGEST
    assert runtime["production_materializer_digest"] == MATERIALIZER_DIGEST
    assert runtime["commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert runtime["tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert runtime["tag"] == "dsh-v0.1.0-rc.7"
    assert activation["fixture"]["fixture_digest"] == FIXTURE_DIGEST


def test_candidate_is_inert_until_a_separate_canonical_activation_merge() -> None:
    activation = _load(ACTIVATION_PATH)
    assert ACTIVATION_PATH.is_file()
    assert activation["phase_state"] == "ACTIVE_CANDIDATE"
    assert activation["activation_state"] == "AUTHORIZED_IF_CANONICAL"
    assert activation["activation_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert activation["effective_execution_authority"] is False
    assert activation["branch_local_effective_execution_authority"] is False
    assert activation["effective_only_after_exact_canonical_merge"] is True
    assert activation["canonicalization"]["candidate_base_sha"] == CURRENT_CANONICAL_MASTER
    assert activation["canonicalization"]["branch_local_candidate_does_not_self_authorize"] is True
    assert activation["activation_prerequisite"]["activation_does_not_execute_episode"] is True
    assert activation["authority_firewall"]["effective_execution_authority"] is False
    assert _git("cat-file", "-e", f"{CURRENT_CANONICAL_MASTER}:{ACTIVATION_PATH.relative_to(ROOT)}").returncode != 0


def test_one_episode_claim_tuple_and_zero_activity() -> None:
    activation = _load(ACTIVATION_PATH)
    episode = activation["episode_identity"]
    claim = activation["claim_contract"]
    assert episode == {
        "execution_project_id": EXECUTION_ID,
        "episode_id": EPISODE_ID,
        "episode_generation": "V0R7",
        "episode_count": 1,
        "authorized_live_episodes": 1,
        "episode_claimed_initial": False,
        "episode_consumed_initial": False,
        "second_episode_allowed": False,
        "whole_episode_retry_allowed": False,
        "timeout_allows_rerun": False,
        "terminal_failure_allows_rerun": False,
        "replay_allowed": False,
        "claim_ref": CLAIM_REF,
    }
    assert claim["remote_claim_ref"] == CLAIM_REF
    assert claim["state_dir"] == str(V0R7_STATE)
    assert claim["remote_claim_exists"] is False
    assert claim["local_claim_exists"] is False
    assert claim["created_during_activation_construction"] is False
    assert claim["remote_caller_selectable"] is False
    assert claim["claim_ref_caller_selectable"] is False
    assert claim["sole_owner"] == "parent_enforcement_guard_ensureClaim_inside_reserve_before_next"
    assert claim["owner_path"].endswith("lib/guard.mjs")
    assert claim["pre_claim_shell_orchestration"] is False
    assert claim["external_orchestration_claim_acquisition"] is False
    assert not V0R7_STATE.exists()
    assert activation["construction_receipts"] == {
        "secret_reads": 0,
        "production_claims_created": 0,
        "provider_model_calls": 0,
        "dsh_invocations": 0,
        "child_turns": 0,
        "codex_turns": 0,
        "claude_turns": 0,
        "spend_usd": "0",
        "episodes_consumed": 0,
        "episode_claimed": False,
        "episode_consumed": False,
    }
    assert activation["activation_consumes_live_episode"] is False
    assert _git("ls-remote", "origin", CLAIM_REF).stdout.strip() == ""
    assert _git("show-ref", "--verify", CLAIM_REF).returncode != 0


def test_protection_blocks_gate_order_and_policies_are_frozen() -> None:
    activation = _load(ACTIVATION_PATH)
    v0r5 = activation["v0r5_protection"]
    assert v0r5["protected_claim_ref"].endswith("-v0r5")
    assert v0r5["known_remote_claim_state"] == "ABSENT"
    assert v0r5["known_local_files"] == ["claim-intent.json", "claim.lock"]
    assert v0r5["receipt_present"] is False
    assert v0r5["terminal_state"] == "BLOCK_NEVER_REPLAY"
    assert v0r5["replay_allowed"] is False
    assert v0r5["mutated_during_activation"] is False
    assert V0R5_STATE.is_dir()
    assert sorted(path.name for path in V0R5_STATE.iterdir() if path.is_file()) == [
        "claim-intent.json",
        "claim.lock",
    ]
    assert not (V0R5_STATE / "claim-receipt.json").exists()
    v0r6 = activation["v0r6_protection"]
    assert v0r6["protected_claim_ref"].endswith("-v0r6")
    assert v0r6["terminal_state"] == "CLOSED_BLOCKED"
    assert v0r6["replay_allowed"] is False
    assert v0r6["mutated_during_activation"] is False
    gates = activation["action_time_gate_order"]
    assert len(gates) == 22
    assert gates.index("real secret read") < gates.index(
        "create-only V0R7 claim using repaired claim primitive"
    ) < gates.index("require COMMITTED before provider I/O")
    secret = activation["secret_binding_contract"]
    assert secret["binding_mechanism"] == "EXPLICIT_EXTRA_ENV_ONLY"
    assert secret["read_timing"] == "AFTER_ALL_NON_SECRET_GATES_BEFORE_CLAIM"
    assert secret["parent_only_env_injection"] is True
    assert secret["activation_phase_secret_reads"] == 0
    assert activation["parent_policy"] == {
        "provider": "openai",
        "model": "gpt-5-mini",
        "route": "llm-pi-ai",
        "maximum_logical_requests": 8,
        "provider_internal_retries": 0,
        "automatic_continuation": False,
        "maximum_output_tokens": 4096,
        "hard_spend_cap_usd": "1.00",
        "attempt_9_denied_before_provider_wire_io": True,
        "alternate_provider_allowed": False,
        "model_substitution_allowed": False,
        "auxiliary_routes_denied": True,
    }
    child = activation["child_policy"]
    assert child["exact_order"] == [
        "codex_initial",
        "claude_review",
        "codex_repair_if_critical_high",
        "claude_rereview_if_repaired",
    ]
    assert child["codex_maximum_turns"] == child["claude_maximum_turns"] == 2
    assert child["claude_hard_read_only"] is True
    assert child["claude_allowed_tools"] == ["Read", "Glob", "Grep"]
    assert set(child["claude_denied_tools"]) == {
        "Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"
    }
    assert activation["claude_policy"]["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert set(activation["claude_policy"]["denied_tools"]) == {
        "Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"
    }


def test_registry_records_the_activation_candidate_and_projection_is_clean() -> None:
    registry = tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))
    record = next(row for row in registry["project"] if row["project_id"] == EXECUTION_ID)
    auth_record = next(row for row in registry["project"] if row["project_id"] == AUTHORIZATION_ID)
    assert record["state"] == "PLANNED_NOT_AUTHORIZED"
    assert record["candidate_state"] == "ACTIVE_CANDIDATE"
    assert record["activation_exists"] is True
    assert record["activation_authorized"] is False
    assert record["activation_authorized_after_canonicalization"] is True
    assert record["effective_execution_authority"] is False
    assert record["implementation_authorized"] is False
    assert record["canonical_base_sha"] == CURRENT_CANONICAL_MASTER
    assert record["canonical_predecessor_merge_parents"] == AUTHORIZATION_MERGE_PARENTS
    assert record["authorization_artifact_sha256"] == AUTH_SHA256
    assert record["authorization_artifact_git_blob"] == AUTH_BLOB
    assert record["claim_ref"] == CLAIM_REF
    assert record["claim_state_dir"] == str(V0R7_STATE)
    assert record["hostile_review_count"] == 1
    assert record["hostile_review_verdict"] == "HOSTILE_REVIEW_PASS"
    assert record["hostile_governance_critical_total"] == 0
    assert record["hostile_governance_high_total"] == 0
    assert record["hostile_governance_medium_total"] == 0
    assert record["hostile_governance_low_total"] == 2
    assert record["targeted_governance_rereview_used"] is False
    assert record["terminal_outcome"] == (
        "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_ACTIVATION_V0R7_MERGE_READY"
    )
    artifact_names = {str(path).rsplit("/", 1)[-1] for path in record["authoritative_artifacts"]}
    assert {"activation.json", "test_dsh_stage_a_v1r3r2_one_episode_live_execution_activation_v0r7.py"} <= (
        artifact_names
    )
    # Minimal precedent-consistent update of the existing authorization entry.
    assert auth_record["activation_exists"] is True
    _, _, loaded = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, loaded)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    # The only ACTIVE project is the QntySpot DEV acquisition; the V0R7
    # activation candidate must never project as an effective active project.
    assert projection["active_project"] is not None
    assert projection["active_project"]["project_id"] == "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_V0"
    assert projection["identity_by_project"].get(EXECUTION_ID, {}).get("effective") is not True
    check = subprocess.run(
        [sys.executable, "-m", "qntylab.project_context", "render", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    assert "DSH Stage-A V1R3R2 one-episode live execution activation V0R7" in roadmap


def test_activation_review_block_matches_durable_hostile_review_receipt() -> None:
    review = _load(ACTIVATION_PATH)["review"]
    assert review["verdict"] == "HOSTILE_REVIEW_PASS"
    assert review["critical_findings"] == 0
    assert review["high_findings"] == 0
    assert review["medium_findings"] == 0
    assert review["low_findings"] == 2
    assert review["targeted_rereview_used"] is False
