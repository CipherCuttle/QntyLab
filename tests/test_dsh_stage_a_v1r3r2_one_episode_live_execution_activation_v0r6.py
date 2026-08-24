from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ACTIVATION_PATH = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r6/activation.json"
AUTHORIZATION_PATH = CONTRACT_ROOT / (
    "dsh_stage_a_v1r3r2_one_episode_live_execution_authorization_v0r6/authorization.json"
)
V0R5_STATE = Path(
    "/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r5/episode-1"
)
V0R6_STATE = Path(
    "/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r6/episode-1"
)

# The V0R6 activation authorization identity is frozen to the exact canonical
# authorization merge that predates this closure PR.  The current canonical
# master (post-closure) is a later commit whose parents are not the
# authorization candidate pair; keep the activation-bound base constant
# separate from the current canonical master exactly as the V0R5 test does.
CANONICAL_MASTER = "6a20d9cfb2c485d7f43ccc04141c6365b5add9a0"
CURRENT_CANONICAL_MASTER = "4195433872140634784c404f88fa0c70a6bcfd11"
AUTHORIZATION_BASE = "e2b97a1478f29e6db3cc1918f1e90ff8547565a1"
AUTHORIZATION_CANDIDATE = "c668856fed89dbe327e230dbb94bb8835c19a834"
AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R6"
EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R6"
EPISODE_ID = f"{EXECUTION_ID}#EPISODE_1"
CLAIM_REF = "refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r6"
AUTH_SHA256 = "d7e5ae4861f6013697305aee18e0238d30c1d2f950796d4a93e04f1c2534560a"
AUTH_BLOB = "18889029dd443883563b28ceb7f81f45f0d5761e"
CLAIM_BLOB = "4c29b6565b01e1bd908abae6a93a09451a6b9d06"
CLAIM_SHA256 = "789a592f1da35b0afb07645947bc82696d361623a6150fc4ff37008b2961081f"
CONTRACT_DIGEST = "50bd776263d05e9f2fe3e026c5e8904a12fa257a1667d11c1e22ef32376c24de"
FIXTURE_DIGEST = "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def test_current_canonical_master_and_frozen_authorization_identity_are_distinct() -> None:
    assert _git("rev-parse", "origin/master").stdout.strip() == CURRENT_CANONICAL_MASTER
    assert _git("merge-base", "--is-ancestor", CANONICAL_MASTER, CURRENT_CANONICAL_MASTER).returncode == 0
    assert _git("rev-list", "--parents", "-n", "1", CANONICAL_MASTER).stdout.split() == [
        CANONICAL_MASTER,
        AUTHORIZATION_BASE,
        AUTHORIZATION_CANDIDATE,
    ]
    authorization = _load(AUTHORIZATION_PATH)
    identity = _load(ACTIVATION_PATH)["authorization_identity"]
    assert authorization["project_id"] == AUTHORIZATION_ID
    assert authorization["phase_state"] == "CLOSED_PASS"
    assert identity["canonical_merge"] == CANONICAL_MASTER
    assert identity["canonical_merge_parents"] == [AUTHORIZATION_BASE, AUTHORIZATION_CANDIDATE]
    assert hashlib.sha256(AUTHORIZATION_PATH.read_bytes()).hexdigest() == AUTH_SHA256
    assert _git("rev-parse", f"origin/master:{AUTHORIZATION_PATH.relative_to(ROOT)}").stdout.strip() == AUTH_BLOB


def test_repaired_claim_identity_and_runtime_bindings_are_frozen() -> None:
    activation = _load(ACTIVATION_PATH)
    claim = activation["repaired_claim_identity"]
    assert hashlib.sha256((ROOT / claim["implementation_path"]).read_bytes()).hexdigest() == CLAIM_SHA256
    assert _git("rev-parse", f"{AUTHORIZATION_BASE}:{claim['implementation_path']}").stdout.strip() == CLAIM_BLOB
    assert claim["implementation_git_blob"] == CLAIM_BLOB
    assert claim["implementation_source_sha256"] == CLAIM_SHA256
    assert activation["qualified_launch_contract"]["digest"] == CONTRACT_DIGEST
    assert activation["runtime_identity"]["qualified_launch_contract_digest"] == CONTRACT_DIGEST
    assert activation["runtime_identity"]["commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert activation["runtime_identity"]["tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert activation["runtime_identity"]["tag"] == "dsh-v0.1.0-rc.7"
    assert activation["fixture"]["fixture_digest"] == FIXTURE_DIGEST


def test_candidate_is_inert_until_a_separate_canonical_activation_merge() -> None:
    activation = _load(ACTIVATION_PATH)
    assert activation["phase_state"] == "ACTIVE_CANDIDATE"
    assert activation["effective_execution_authority"] is False
    assert activation["effective_only_after_exact_canonical_merge"] is True
    assert activation["canonicalization"]["candidate_base_sha"] == CANONICAL_MASTER
    assert activation["canonicalization"]["branch_local_candidate_does_not_self_authorize"] is True
    assert activation["activation_prerequisite"]["activation_does_not_execute_episode"] is True
    assert _git(
        "cat-file", "-e", f"{CANONICAL_MASTER}:{ACTIVATION_PATH.relative_to(ROOT)}"
    ).returncode != 0


def test_one_episode_claim_tuple_and_zero_activity() -> None:
    activation = _load(ACTIVATION_PATH)
    episode = activation["episode_identity"]
    claim = activation["claim_contract"]
    assert episode == {
        "execution_project_id": EXECUTION_ID,
        "episode_id": EPISODE_ID,
        "episode_generation": "V0R6",
        "episode_count": 1,
        "authorized_live_episodes": 1,
        "episode_claimed": False,
        "episode_consumed": False,
        "second_episode_allowed": False,
        "whole_episode_retry_allowed": False,
        "timeout_allows_rerun": False,
        "terminal_failure_allows_rerun": False,
        "claim_ref": CLAIM_REF,
    }
    assert claim["remote_claim_ref"] == CLAIM_REF
    assert claim["remote_claim_exists"] is False
    assert claim["local_claim_exists"] is False
    assert claim["created_during_activation_construction"] is False
    assert not V0R6_STATE.exists()
    assert activation["construction_receipts"] == {
        "activation_artifacts_created": 1,
        "secret_reads": 0,
        "production_claim_writes": 0,
        "diagnostic_claim_writes": 0,
        "provider_calls": 0,
        "real_model_calls": 0,
        "codex_turns": 0,
        "claude_turns": 0,
        "dsh_invocations": 0,
        "fixture_mutations": 0,
        "spend_usd": "0",
        "episode_claimed": False,
        "episode_consumed": False,
    }
    assert _git("ls-remote", "origin", CLAIM_REF).stdout.strip() == ""


def test_v0r5_protection_and_future_policy_are_unchanged() -> None:
    activation = _load(ACTIVATION_PATH)
    protection = activation["v0r5_protection"]
    assert protection["protected_claim_ref"].endswith("-v0r5")
    assert protection["known_remote_claim_state"] == "ABSENT"
    assert protection["known_local_files"] == ["claim-intent.json", "claim.lock"]
    assert protection["receipt_present"] is False
    assert protection["terminal_state"] == "BLOCK_NEVER_REPLAY"
    assert protection["replay_allowed"] is False
    assert protection["claim_reset_allowed"] is False
    assert protection["delete_allowed"] is False
    assert protection["receipt_repair_allowed"] is False
    assert protection["second_episode_allowed"] is False
    assert protection["mutated_during_activation"] is False
    assert V0R5_STATE.is_dir()
    assert sorted(path.name for path in V0R5_STATE.iterdir() if path.is_file()) == [
        "claim-intent.json",
        "claim.lock",
    ]
    assert not (V0R5_STATE / "claim-receipt.json").exists()
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
    assert child["order"] == [
        "codex_initial",
        "claude_review",
        "codex_repair_if_critical_high",
        "claude_rereview_if_repaired",
    ]
    assert child["codex_maximum_turns"] == child["claude_maximum_turns"] == 2
    assert child["claude_hard_read_only"] is True
    assert child["allowed_tools"] == ["Read", "Glob", "Grep"]
    assert set(child["denied_tools"]) == {
        "Write", "Edit", "Bash", "Agent", "Task", "mcp__*", "AskUserQuestion", "delegation"
    }


def test_registry_records_terminal_closure_and_projection_is_clean() -> None:
    registry = tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))
    record = next(row for row in registry["project"] if row["project_id"] == EXECUTION_ID)
    activation = _load(ACTIVATION_PATH)
    assert record["state"] == "CLOSED_BLOCKED"
    assert record["candidate_state"] == "CLOSED_BLOCKED"
    assert record["canonicalization_status"] == "CLOSED"
    assert record["activation_exists"] is True
    assert record["activation_authorized"] is False
    assert record["activation_authorized_after_canonicalization"] is True
    assert record["effective_execution_authority"] is False
    assert record["v0r5_reused"] is False
    assert record["implementation_authorized"] is False
    assert record["implementation_completed"] is True
    assert record["active_project_after_closure"] == "NONE"
    assert record["terminal_outcome"] == "V0R6_LIVE_EPISODE_CLOSED_BLOCKED_NO_REPLAY"
    assert record["canonical_base_sha"] == CANONICAL_MASTER
    assert record["canonical_predecessor_merge_parents"] == [AUTHORIZATION_BASE, AUTHORIZATION_CANDIDATE]
    assert record["authorization_artifact_sha256"] == AUTH_SHA256
    assert record["authorization_artifact_git_blob"] == AUTH_BLOB
    assert record["canonical_activation_merge"] == CURRENT_CANONICAL_MASTER
    assert activation["authority_firewall"]["effective_execution_authority"] is False
    artifact_names = {str(path).rsplit("/", 1)[-1] for path in record["authoritative_artifacts"]}
    assert {"execution_evidence.json", "closure.md"} <= artifact_names
    _, _, loaded = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, loaded)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    assert projection["active_project"] is None
    assert projection["identity_by_project"][EXECUTION_ID]["effective"] is False
    roadmap = (ROOT / "docs/CURRENT_ROADMAP.md").read_text(encoding="utf-8")
    assert "DSH Stage-A V1R3R2 one-episode live execution activation V0R6" in roadmap
    assert "V0R6_LIVE_EPISODE_CLOSED_BLOCKED_NO_REPLAY" in roadmap


def test_v0r6_terminal_closure_projection_reports_zero_issues() -> None:
    """The V0R6 CLOSED_BLOCKED terminal closure must project cleanly.

    This is the acceptance condition for the closure-projection repair: a
    terminal closure row with execution_evidence.json + closure.md artifacts
    projects with zero issues and no active project.
    """
    _, _, registry = project_context.load_context_sources(ROOT)
    projects = project_context.validate_projects_registry(ROOT, registry)
    projection = project_context.execution_authority_projection(ROOT, projects)
    assert projection["issues"] == []
    assert projection["active_project"] is None
    record = projects[EXECUTION_ID]
    assert record["state"] == "CLOSED_BLOCKED"
    assert record["implementation_authorized"] is False
    assert record["active_project_after_closure"] == "NONE"


def test_non_v0r6_row_with_mismatched_digest_still_reports_issue() -> None:
    """Global fail-closed parity must NOT be weakened by the V0R6 repair.

    A non-V0R6 terminal-closure row with a genuine runtime-identity mismatch
    (launch_policy_digest) must still report a projection issue.  The V0R5 row
    is used because it is a real, immutable terminal-closure row; the mutation
    is made on the in-memory record only, so no registry bytes change.
    """
    from qntylab import project_context as _context

    _, _, registry = _context.load_context_sources(ROOT)
    projects = _context.validate_projects_registry(ROOT, registry)
    v0r5 = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R5"
    record = dict(projects[v0r5])
    assert record["state"] == "CLOSED_BLOCKED"
    record["launch_policy_digest"] = "wrong"
    projection = _context.execution_authority_projection(ROOT, {v0r5: record})
    assert projection["active_project"] is None
    assert any("launch_policy_digest" in issue for issue in projection["issues"])
