from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
ARTIFACT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_action_time_parity_authorization_v0"
AUTH_PATH = ARTIFACT / "authorization.json"
AUTH = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
REVIEW_PATH = ARTIFACT / "hostile_governance_review.md"

COMPOSITE_ROOT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0"
CONTRACT_PATH = COMPOSITE_ROOT / "evidence/contract.json"
QUALIFICATION_PATH = COMPOSITE_ROOT / "evidence/qualification.json"
QUALIFICATION_SCRIPT = COMPOSITE_ROOT / "qualification/run-composite-qualification.mjs"
COMPOSITE_LAUNCHER_PATH = COMPOSITE_ROOT / "launcher/qntylab-launch-dsh.mjs"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

V0R4_RESULT_ROOT = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_one_episode_live_execution_result_v0r4"
V0R4_EVIDENCE_PATH = V0R4_RESULT_ROOT / "execution_evidence.json"
V0R4_CLOSURE_PATH = V0R4_RESULT_ROOT / "closure.md"
V0R4_EVIDENCE = json.loads(V0R4_EVIDENCE_PATH.read_text(encoding="utf-8"))

REGISTRY_PATH = ROOT / "docs/state/projects.toml"
REGISTRY = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AND_ACTION_TIME_PARITY_AUTHORIZATION_V0"
FUTURE_ID = "DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AND_REQUALIFICATION_V0"
V0R4_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4"
CANONICAL_MASTER = "1913df60545616cb8eaf94f36f73f6686c683993"
A392 = "a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be"
SCRATCH_DSH_HOME = "/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home"
RUNTIME_MANIFEST_DIGEST = "0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3"
EXECUTABLE_IDENTITY_DIGEST = "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"


def _phase_changed_paths() -> set[str]:
    """Paths this phase changes relative to canonical master, committed or not.

    Comparing against HEAD alone would be empty (and pass vacuously) until the
    phase commit lands, so this compares against the working tree and adds any
    untracked files.
    """
    tracked = subprocess.run(
        ["git", "diff", "--name-only", CANONICAL_MASTER],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return set(tracked) | set(untracked)


def _registry(project_id: str) -> dict:
    matches = [entry for entry in REGISTRY["project"] if entry["project_id"] == project_id]
    assert len(matches) == 1, f"expected exactly one registry entry for {project_id}, found {len(matches)}"
    return matches[0]


def test_canonical_predecessor_is_exactly_the_merged_v0r4_closure() -> None:
    predecessor = AUTH["canonical_predecessor"]
    assert predecessor["project_id"] == V0R4_ID
    assert predecessor["canonical_master"] == predecessor["canonical_predecessor_merge"] == CANONICAL_MASTER
    assert predecessor["required_state"] == "CLOSED_BLOCKED"
    assert predecessor["required_terminal_outcome"] == "BLOCK_RUNTIME_IDENTITY"
    assert predecessor["binding_mismatch_behavior"] == "BLOCK_AUTH"

    # The bound predecessor bytes must be the exact canonical V0R4 closure bytes.
    assert predecessor["execution_evidence_artifact_sha256"] == hashlib.sha256(V0R4_EVIDENCE_PATH.read_bytes()).hexdigest()
    assert predecessor["closure_artifact_sha256"] == hashlib.sha256(V0R4_CLOSURE_PATH.read_bytes()).hexdigest()

    # The canonical master this authorization binds must really be the merge of PR #204.
    merged = subprocess.run(
        ["git", "rev-parse", f"{CANONICAL_MASTER}^{{commit}}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert merged == CANONICAL_MASTER


def test_v0r4_remains_closed_blocked_and_unconsumed() -> None:
    entry = _registry(V0R4_ID)
    assert entry["state"] == "CLOSED_BLOCKED"
    assert entry["terminal_outcome"] == "BLOCK_RUNTIME_IDENTITY"
    assert entry["episode_claimed"] is False
    assert entry["episode_consumed"] is False
    assert entry["claim_created"] is False
    assert entry["effective_execution_authority"] is False

    assert V0R4_EVIDENCE["terminal_outcome"] == "BLOCK_RUNTIME_IDENTITY"
    assert V0R4_EVIDENCE["closure"]["rerun_authorized"] is False
    assert V0R4_EVIDENCE["closure"]["episode_claimed_after"] is False
    assert V0R4_EVIDENCE["closure"]["episode_consumed_after"] is False

    predecessor = AUTH["canonical_predecessor"]
    assert predecessor["v0r4_immutable_historical_evidence"] is True
    for forbidden in ("v0r4_reopen_allowed", "v0r4_rerun_allowed", "v0r4_episode_reuse_allowed", "v0r4_claim_tuple_reuse_allowed"):
        assert predecessor[forbidden] is False


def test_no_active_project_exists_after_this_authorization() -> None:
    entry = _registry(AUTHORIZATION_ID)
    assert entry["state"] == "CLOSED_PASS"
    assert entry["active_project_after_closure"] == "NONE"
    assert AUTH["authority_firewall"]["active_project_after_closure"] == "NONE"

    # No registry project may be left in an active/authorized-implementation state.
    for project in REGISTRY["project"]:
        assert project["state"] not in {"ACTIVE", "IN_PROGRESS", "AUTHORIZED_ACTIVE"}, project["project_id"]
        if project.get("implementation_authorized"):
            raise AssertionError(f"{project['project_id']} still claims implementation authority")


def test_future_implementation_scope_is_exactly_bounded() -> None:
    future = AUTH["authorized_future_project"]
    assert future["project_id"] == FUTURE_ID
    assert future["count"] == 1
    assert future["authority_level"] == "BOUNDED_PRELIVE_RUNTIME_PROFILE_MATERIALIZATION_REPAIR_ONLY"
    assert future["effective_only_after_canonical_merge_of_this_authorization"] is True
    assert future["second_implementation_phase_authorized"] is False
    assert future["implementation_retry_authorized"] is False
    assert future["grants_live_authority"] is False
    assert future["grants_successor_live_authority_automatically"] is False
    assert future["next_phase_after_implementation"] == "SEPARATE_FRESH_GIT_BACKED_AUTHORITY_REQUIRED"

    # The registry projection must agree with the artifact.
    entry = _registry(AUTHORIZATION_ID)
    assert entry["authorized_future_project_id"] == FUTURE_ID
    assert entry["authorized_future_project_count"] == 1
    assert entry["authorized_future_project_exists"] is False

    forbidden = set(future["forbidden_scope"])
    for must_be_forbidden in (
        "create V0R5",
        "activate V0R5",
        "execute V0R5",
        "execute any live episode",
        "read the real provider secret",
        "create any claim",
        "perform real provider or model I/O",
        "spend money",
        "invoke real Codex or Claude children",
        "rebuild or modify the pinned DSH runtime bytes",
        "modify the qualified composite launcher",
        "modify the Stage-A production packages",
        "freeze an ambient machine directory as canonical authority",
        "Stage B",
        "Qnty runtime authority",
        "scientific execution",
        "trading",
        "capital",
        "promotion",
        "broader production deployment",
    ):
        assert must_be_forbidden in forbidden, must_be_forbidden

    # Authorized scope may not silently contain live or successor-live authority.
    authorized_blob = " ".join(future["authorized_scope"]).lower()
    for leak in ("v0r5", "secret", "claim", "spend", "stage b", "live episode", "provider i/o"):
        assert leak not in authorized_blob, f"authorized scope leaks '{leak}'"


def test_scratch_dsh_home_cannot_be_declared_canonical_authority() -> None:
    source = AUTH["source_of_profile_bytes"]
    assert source["old_scratch_dsh_home_is_authoritative_source"] is False
    assert source["forbidden_authoritative_source"] == SCRATCH_DSH_HOME
    assert source["freeze_ambient_machine_directory_as_authority"] is False
    assert source["ambient_cross_check_may_not_confer_authority"] is True
    assert source["required_derivation"] == "GIT_BOUND_OR_CONTRACT_BOUND_CANONICAL_SOURCES_ONLY"
    assert source["unresolvable_provenance_behavior"] == "STOP_AND_REPORT_SOURCE_CONFLICT"

    # Every ambient root observed in the forensic sweep must be explicitly denied authority.
    denied = set(source["additional_forbidden_ambient_authorities"]) | {source["forbidden_authoritative_source"]}
    observed = set(AUTH["forensic_findings"]["F3_ambient_node_modules_is_an_unverified_symlink_farm"]["symlink_target_roots"])
    observed.add(AUTH["forensic_findings"]["ambient_scratch_dsh_home"])
    assert observed <= denied, f"ambient roots without an explicit denial: {sorted(observed - denied)}"

    entry = _registry(AUTHORIZATION_ID)
    assert entry["scratch_dsh_home_canonical_authority"] is False
    assert entry["scratch_dsh_home_may_be_declared_authoritative"] is False
    assert entry["ambient_dsh_home_dependency_removal_required"] is True
    assert set(entry["forbidden_ambient_authorities"]) == denied

    # H-01: declaring the ambient home non-authoritative is not enough; mutating it
    # would manufacture a passing live path without a real production materializer
    # and would destroy the physical referent of the immutable V0R4 evidence.
    assert source["historical_ambient_dsh_home_mutation_authorized"] is False
    assert source["historical_ambient_dsh_home_repair_or_backfill_authorized"] is False
    assert source["ambient_root_mutation_authorized"] is False
    assert source["ambient_cross_check_must_be_read_only"] is True
    assert source["ambient_mutation_behavior"] == "FORBIDDEN_BLOCKS_IMPLEMENTATION"
    assert entry["historical_ambient_dsh_home_mutation_authorized"] is False
    assert entry["historical_ambient_dsh_home_repair_or_backfill_authorized"] is False
    assert entry["ambient_root_mutation_authorized"] is False
    assert entry["ambient_cross_check_must_be_read_only"] is True

    forbidden = AUTH["authorized_future_project"]["forbidden_scope"]
    assert "modify, repair, or backfill the historical ambient scratch DSH_HOME" in forbidden
    assert "modify, repair, or backfill any forbidden ambient root" in forbidden

    # This phase must not itself have touched the ambient home.
    assert AUTH["construction_receipts"]["ambient_dsh_home_bytes_modified"] == 0
    assert AUTH["forensic_findings"]["method"] == "READ_ONLY_INSPECTION_ONLY"

    # The failed live DSH_HOME recorded here must be the one V0R4 actually recorded.
    assert AUTH["root_cause"]["v0r4_failed_dsh_home"] == SCRATCH_DSH_HOME
    assert V0R4_EVIDENCE["runtime_identity"]["dsh_home_path"] == SCRATCH_DSH_HOME


def test_qualification_only_helper_cannot_remain_the_production_authority() -> None:
    helper = AUTH["root_cause"]["qualification_only_helper"]
    assert helper["symbol"] == "prepareDisposableDshHome"
    assert helper["is_production_authority"] is False
    assert helper["may_remain_the_production_authority_path"] is False
    assert helper["was_executed_on_the_live_v0r4_path"] is False

    # The bound helper bytes must be the exact current qualification script.
    assert helper["file_sha256"] == hashlib.sha256(QUALIFICATION_SCRIPT.read_bytes()).hexdigest()
    script = QUALIFICATION_SCRIPT.read_text(encoding="utf-8")
    assert "function prepareDisposableDshHome(" in script
    assert SCRATCH_DSH_HOME in script, "the ambient default is expected to still be present in the historical helper"

    assert "qualification-only helper cannot be used as the production authority path" in AUTH["required_negative_controls"]

    entry = _registry(AUTHORIZATION_ID)
    assert entry["qualification_only_helper_is_production_authority"] is False
    assert entry["qualification_only_helper_may_remain_production_authority"] is False
    assert entry["qualification_only_helper_sha256"] == helper["file_sha256"]


def test_root_cause_classification_is_the_materialization_gap() -> None:
    root_cause = AUTH["root_cause"]
    assert root_cause["classification"] == "QUALIFICATION_TO_ACTION_TIME_DSH_HOME_MATERIALIZATION_GAP"
    assert set(root_cause["rejected_classifications"]) == {
        "DSH_UPSTREAM_FAILURE",
        "COMPOSITE_LAUNCHER_FAILURE",
        "OPENAI_FAILURE",
        "CODEX_FAILURE",
        "CLAUDE_FAILURE",
    }
    assert root_cause["action_time_equivalent_materialization_executed"] is False
    assert root_cause["v0r4_terminal_outcome"] == V0R4_EVIDENCE["terminal_outcome"]
    assert root_cause["v0r4_launcher_preflight_error"] == V0R4_EVIDENCE["non_secret_gates"]["launcher_preflight_error"]
    assert _registry(AUTHORIZATION_ID)["root_cause_classification"] == root_cause["classification"]


def test_successor_contract_must_bind_the_new_materializer_and_supersede_a392() -> None:
    successor = AUTH["successor_contract_requirement"]
    assert successor["predecessor_qualified_contract_digest"] == A392 == CONTRACT["qualifiedContractDigest"]
    assert successor["predecessor_contract_artifact_sha256"] == hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    assert successor["predecessor_qualification_artifact_sha256"] == hashlib.sha256(QUALIFICATION_PATH.read_bytes()).hexdigest()
    assert successor["a392_preserved_historically"] is True
    assert successor["a392_remains_final_complete_live_contract"] is False
    assert successor["a392_may_be_cited_as_final_live_contract_after_new_materializer_is_trusted"] is False
    assert successor["successor_contract_grants_live_authority"] is False
    assert successor["successor_contract_requires_separate_future_live_authorization"] is True
    assert set(successor["must_compute"]) == {
        "NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST",
        "NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST",
    }

    bindings = successor["successor_contract_minimum_bindings"]
    for required in (
        "predecessor a392 digest",
        "pinned DSH source identity",
        "physical runtime manifest",
        "executable identity",
        "production DSH_HOME materializer path",
        "production DSH_HOME materializer digest",
        "materialized DSH_HOME manifest schema",
        "exact headless profile identities",
        "exact @deepseek-ai package tree identities",
        "exact @qntylab package identities",
        "composite launcher path/digest",
        "Stage-A policy",
        "parent policy",
        "child controller",
        "Codex boundary",
        "Claude boundary",
        "workspace containment",
        "claim/secret order",
        "fixture identity",
    ):
        assert required in bindings, required

    entry = _registry(AUTHORIZATION_ID)
    assert entry["a392_remains_final_complete_live_contract"] is False
    assert entry["successor_contract_required"] is True
    assert entry["successor_contract_issued_this_phase"] is False
    assert entry["new_production_dsh_home_materializer_digest_required"] is True
    assert entry["new_qualified_launch_contract_digest_required"] is True


def test_action_time_parity_is_required_and_not_skippable() -> None:
    parity = AUTH["action_time_parity_requirement"]
    assert parity["required"] is True
    assert parity["skippable"] is False
    assert parity["waivable"] is False
    assert parity["single_production_preparation_path_used_by_both_qualification_and_live_execution"] is True
    assert parity["qualification_only_prerequisite_creation_forbidden"] is True
    assert parity["must_exercise_same_constructor_as_live"] is True
    assert parity["must_exercise_same_preflight_as_live"] is True
    assert parity["receipt_name"] == "ACTION_TIME_PARITY_RECEIPT"
    assert parity["stop_boundary"] == "IMMEDIATELY_BEFORE_REAL_SECRET_READ"
    assert parity["required_chain_from_empty_disposable_environment"] == [
        "EMPTY DSH_HOME DESTINATION",
        "PRODUCTION DSH_HOME MATERIALIZER",
        "PRODUCTION COMPOSITE PREFLIGHT",
        "PRODUCTION FIXTURE PREPARATION",
        "ALL NON-SECRET LIVE GATES PASS",
        "STOP IMMEDIATELY BEFORE REAL SECRET READ",
    ]
    assert parity["expected_receipts"] == {
        "REAL_SECRET_READS": 0,
        "CLAIMS_CREATED": 0,
        "PUBLIC_PROVIDER_REQUESTS": 0,
        "REAL_MODEL_CALLS": 0,
        "REAL_CODEX_TURNS": 0,
        "REAL_CLAUDE_TURNS": 0,
        "SPEND_USD": 0,
    }

    entry = _registry(AUTHORIZATION_ID)
    assert entry["action_time_parity_receipt_required"] is True
    assert entry["action_time_parity_skippable"] is False
    assert entry["action_time_parity_stop_boundary"] == parity["stop_boundary"]


def test_production_materializer_contract_forbids_stub_and_ambient_substitution() -> None:
    materializer = AUTH["production_materializer_contract"]
    assert materializer["required"] is True
    assert materializer["must_be_first_class_production_component"] is True
    assert materializer["must_be_deterministic"] is True
    assert materializer["must_be_identity_covered"] is True
    assert materializer["must_be_bound_into_successor_contract"] is True
    assert materializer["production_stub_provider_allowed"] is False
    assert materializer["stub_presence_in_production_materialization_behavior"] == "FAIL_CLOSED"
    assert materializer["qualification_only_optional_package"] == "@qntylab/dsh-stage-a-stub-provider"
    assert set(materializer["required_qntylab_packages"]) == {
        "@qntylab/dsh-stage-a-gated-provider",
        "@qntylab/dsh-stage-a-parent-enforcement",
    }
    assert "@qntylab/dsh-stage-a-stub-provider" not in materializer["required_qntylab_packages"]

    destination = materializer["destination_policy"]
    assert destination["must_require_empty_or_fresh_destination"] is True
    assert destination["must_reject_non_empty_destination"] is True
    assert destination["must_reject_reuse_of_a_persistent_directory"] is True
    assert destination["destination_inside_qntylab_forbidden"] is True
    assert destination["destination_inside_dsh_runtime_forbidden"] is True
    assert destination["destination_inside_operator_home_forbidden"] is True

    for rejection in (
        "missing required packages",
        "unexpected @qntylab packages",
        "modified package bytes",
        "package symlinks escaping allowed roots",
        "ambient package substitution",
    ):
        assert rejection in materializer["must_reject"], rejection

    # The launcher tolerates the stub, so the materializer must be the enforcement point.
    launcher = COMPOSITE_LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "dsh-stage-a-stub-provider" in launcher
    assert "optionalQnty" in launcher
    assert AUTH["forensic_findings"]["F7_launcher_currently_tolerates_the_stub_provider"]["launcher_digest"] == (
        hashlib.sha256(COMPOSITE_LAUNCHER_PATH.read_bytes()).hexdigest()
    )


def test_all_twenty_negative_controls_are_required() -> None:
    controls = AUTH["required_negative_controls"]
    assert len(controls) == 20
    assert len(set(controls)) == 20
    assert _registry(AUTHORIZATION_ID)["required_negative_control_count"] == 20
    for required in (
        "empty destination succeeds",
        "production stub-provider presence fails",
        "symlink escape fails",
        "stale scratch DSH_HOME cannot substitute",
        "caller-supplied arbitrary DSH_HOME cannot bypass materializer",
        "materializer-byte substitution invalidates contract",
        "home-manifest substitution invalidates contract",
        "qualification-only helper cannot be used as the production authority path",
    ):
        assert required in controls, required

    determinism = AUTH["determinism_requirement"]
    assert determinism["independent_materializations_required"] == 2
    assert determinism["persistent_scratch_directory_as_source_of_truth"] is False
    assert determinism["identity_equality_required_for_all_deterministic_materialized_bytes"] is True


def test_runtime_rebuild_and_launcher_modification_authority_is_not_leaked() -> None:
    runtime = AUTH["runtime_binding"]
    assert runtime["pinned_dsh_commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert runtime["pinned_dsh_tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert runtime["pinned_dsh_tag"] == "dsh-v0.1.0-rc.7"
    assert runtime["expected_unchanged_runtime_manifest_digest"] == RUNTIME_MANIFEST_DIGEST
    assert runtime["expected_unchanged_executable_identity_digest"] == EXECUTABLE_IDENTITY_DIGEST
    assert runtime["physical_runtime_byte_change_authorized"] is False
    assert runtime["runtime_rebuild_authorized"] is False
    assert runtime["runtime_repatch_authorized"] is False
    assert runtime["composite_launcher_modification_authorized"] is False
    assert runtime["stage_a_package_modification_authorized"] is False
    assert runtime["silent_rebuild_forbidden"] is True
    assert runtime["if_runtime_identities_must_change"] == "STOP_AND_REPORT_SOURCE_CONFLICT_OR_SCOPE_EXPANSION_REQUIRED"

    # The frozen identities must match the canonical V0R4 evidence they claim to preserve.
    canonical = V0R4_EVIDENCE["canonical"]
    assert canonical["runtime_manifest_digest"] == RUNTIME_MANIFEST_DIGEST
    assert canonical["executable_identity_digest"] == EXECUTABLE_IDENTITY_DIGEST
    assert canonical["composite_launcher_digest"] == hashlib.sha256(COMPOSITE_LAUNCHER_PATH.read_bytes()).hexdigest()
    assert canonical["qualified_launch_contract_digest"] == A392

    entry = _registry(AUTHORIZATION_ID)
    assert entry["runtime_rebuild_authorized"] is False
    assert entry["runtime_byte_modification_authorized"] is False
    assert entry["composite_launcher_modification_authorized"] is False
    assert entry["stage_a_package_modification_authorized"] is False


def test_v0r5_is_not_created_and_no_live_authority_is_granted() -> None:
    frozen = AUTH["frozen_authority_flags"]
    assert frozen == {
        "live_execution_authorized": False,
        "secret_read_authorized": False,
        "claim_authorized": False,
        "provider_io_authorized": False,
        "real_children_authorized": False,
        "v0r5_authorized": False,
        "v0r5_created": False,
        "stage_b_authorized": False,
    }

    firewall = AUTH["authority_firewall"]
    for flag in (
        "authorization_effective",
        "implementation_authorized_this_phase",
        "materializer_implemented_this_phase",
        "activation_created_this_phase",
        "live_execution_authorized_this_phase",
        "real_secret_read_authorized_this_phase",
        "claim_authorized_this_phase",
        "real_provider_io_authorized_this_phase",
        "successor_contract_issued_this_phase",
        "v0r5_authorized",
        "stage_b_authorized",
        "scientific_execution_authorized",
        "production_deployment_authorized",
    ):
        assert firewall[flag] is False, flag
    for authority in ("qnty_runtime_authority", "trading_authority", "capital_authority", "promotion_authority", "broader_production_authority"):
        assert firewall[authority] == "NONE", authority

    assert AUTH["canonicalization"]["authorization_does_not_authorize_v0r5"] is True
    assert AUTH["canonicalization"]["authorization_does_not_implement"] is True
    assert AUTH["canonicalization"]["authorization_does_not_activate"] is True

    # No V0R5 project or artifact may exist anywhere.
    assert not [entry for entry in REGISTRY["project"] if "V0R5" in entry["project_id"]]
    assert not list(CONTRACT_ROOT.glob("*v0r5*"))
    tracked = subprocess.run(
        ["git", "ls-files", "*v0r5*", "*V0R5*"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert tracked == ""


def test_materializer_implementation_is_not_performed_during_authorization() -> None:
    entry = _registry(AUTHORIZATION_ID)
    assert entry["phase_type"] == "GOVERNANCE_ONLY_BOUNDED_REPAIR_AUTHORIZATION"
    assert entry["implementation_authorized"] is False
    assert entry["implementation_completed"] is False
    assert entry["materializer_implemented_this_phase"] is False
    assert entry["production_materializer_required"] is True

    boundary = AUTH["authorization_phase_boundary"]
    for forbidden in (
        "implement the materializer",
        "modify the composite launcher",
        "modify the runtime",
        "modify Stage-A packages",
        "run DSH",
        "read the secret",
        "create a claim",
        "call OpenAI",
        "call Codex",
        "call Claude",
        "spend",
        "create V0R5",
        "activate V0R5",
        "execute V0R5",
    ):
        assert forbidden in boundary["this_phase_may_not"], forbidden
    assert boundary["merge_authorized"] is False

    # No production materializer implementation may have been added by this phase.
    # Diff canonical master against the WORKING TREE (not HEAD): before the phase
    # commit lands, a HEAD-only diff is empty and would pass vacuously.
    changed = _phase_changed_paths()
    allowed = {
        "docs/CURRENT_ROADMAP.md",
        "docs/state/projects.toml",
        str(AUTH_PATH.relative_to(ROOT)),
        str(REVIEW_PATH.relative_to(ROOT)),
        "tests/test_dsh_stage_a_v1r3r2_production_dsh_home_materialization_authorization_v0.py",
    }
    assert changed, "expected this phase to change the governance files it claims to change"
    assert changed <= allowed, f"authorization phase touched files outside its boundary: {sorted(changed - allowed)}"
    assert not [path for path in changed if path.endswith(".mjs")]


def test_no_live_activity_occurred_during_authorization() -> None:
    receipts = AUTH["construction_receipts"]
    assert receipts["spend_usd"] == "0"
    for counter in (
        "real_secret_reads",
        "claims_created",
        "live_dsh_calls",
        "external_provider_requests",
        "real_model_calls",
        "codex_child_turns",
        "claude_child_turns",
        "fixture_mutations",
        "activation_artifacts_created",
        "materializer_artifacts_created",
        "successor_contract_digests_issued",
        "runtime_bytes_modified",
        "launcher_bytes_modified",
        "stage_a_package_bytes_modified",
        "ambient_dsh_home_bytes_modified",
    ):
        assert receipts[counter] == 0, counter

    entry = _registry(AUTHORIZATION_ID)
    assert entry["authorization_phase_spend_usd"] == 0.0
    for counter in (
        "authorization_phase_secret_reads",
        "authorization_phase_claim_creations",
        "authorization_phase_live_dsh_calls",
        "authorization_phase_external_provider_requests",
        "authorization_phase_real_model_calls",
        "authorization_phase_codex_child_turns",
        "authorization_phase_claude_child_turns",
        "authorization_phase_fixture_mutations",
        "authorization_phase_runtime_bytes_modified",
        "authorization_phase_launcher_bytes_modified",
        "authorization_phase_ambient_dsh_home_bytes_modified",
    ):
        assert entry[counter] == 0, counter


def test_stale_v0r4_test_repair_authority_is_narrow_and_justified() -> None:
    repair = AUTH["stale_test_repair_authority"]
    assert repair["granted"] is True
    assert repair["scope"] == "NARROW_TEST_ONLY"
    assert repair["permanently_stale"] is True
    assert repair["production_semantics_change_allowed"] is False
    assert repair["other_test_changes_authorized"] is False
    assert repair["deletion_of_the_test_authorized"] is False
    assert repair["weakening_to_a_trivially_true_assertion_authorized"] is False
    assert repair["must_preserve_historical_purpose"] is True

    stale_test = ROOT / repair["test_file"]
    assert stale_test.exists()
    assert f"def {repair['test_name']}(" in stale_test.read_text(encoding="utf-8")

    # The staleness claim must be true: the activation artifact IS now in canonical history.
    activation_relative = (
        "experiments/research/qnty_agent_orchestration_control_contract_v0/"
        "dsh_stage_a_v1r3r2_one_episode_live_execution_v0r4/activation.json"
    )
    history = subprocess.run(
        ["git", "log", CANONICAL_MASTER, "--oneline", "--", activation_relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert history.strip() != "", "the stale-test repair authority is only justified if the artifact is in canonical history"

    # This authorization phase must NOT have already applied the repair.
    assert repair["observed_state_at_authorization"] == "FAILING"
    assert repair["test_file"] not in _phase_changed_paths(), (
        "the stale test may only be repaired by the future implementation phase"
    )


def test_hostile_review_ran_exactly_once_with_no_unrepaired_critical_or_high() -> None:
    review = AUTH["review_policy"]
    assert review["exactly_one_independent_hostile_review_required"] is True
    assert review["hostile_review_completed"] is True
    assert review["hostile_review_count"] == 1
    assert review["review_loops_after_targeted_rereview"] is False
    assert REVIEW_PATH.exists()
    assert str(REVIEW_PATH.relative_to(ROOT)) == review["hostile_review_artifact"]

    # What must be zero is UNREPAIRED Critical/High, not findings discovered.
    assert review["unrepaired_critical_findings"] == 0
    assert review["unrepaired_high_findings"] == 0
    assert review["critical_findings"] - review["critical_findings_repaired"] == review["unrepaired_critical_findings"]
    assert review["high_findings"] - review["high_findings_repaired"] == review["unrepaired_high_findings"]

    # Medium/Low repair is outside this phase's authority, so they must be
    # recorded as accepted rather than silently fixed.
    assert review["medium_and_low_repair_authorized"] is False
    assert review["medium_findings_repaired"] == 0
    assert review["medium_findings_accepted_without_repair"] == review["medium_findings"]

    # A targeted rereview is required exactly when a Critical/High was repaired.
    repaired_ch = review["critical_findings_repaired"] + review["high_findings_repaired"]
    assert review["targeted_rereview_used"] is (repaired_ch > 0)
    if review["targeted_rereview_used"]:
        assert review["targeted_rereview_count"] == 1
        assert review["targeted_rereview_verdict"] == "PASS"

    # Every finding must be accounted for as either repaired or explicitly accepted.
    total = review["critical_findings"] + review["high_findings"] + review["medium_findings"] + review["low_findings"]
    assert len(review["repaired_findings"]) + len(review["accepted_without_repair_findings"]) == total

    review_text = REVIEW_PATH.read_text(encoding="utf-8")
    for finding_id in review["repaired_findings"] + review["accepted_without_repair_findings"]:
        assert finding_id in review_text, f"{finding_id} is not documented in the review artifact"

    entry = _registry(AUTHORIZATION_ID)
    assert entry["hostile_review_count"] == 1
    assert entry["hostile_review_verdict"] == "PASS"
    assert entry["hostile_governance_critical_total"] == review["critical_findings"]
    assert entry["hostile_governance_high_total"] == review["high_findings"]
    assert entry["hostile_governance_medium_total"] == review["medium_findings"]
    assert entry["hostile_governance_low_total"] == review["low_findings"]
    assert entry["hostile_governance_unrepaired_critical_total"] == 0
    assert entry["hostile_governance_unrepaired_high_total"] == 0
    assert entry["hostile_governance_high_repaired_total"] == review["high_findings_repaired"]
    assert entry["hostile_governance_medium_accepted_without_repair"] == review["medium_findings_accepted_without_repair"]
    assert entry["targeted_governance_rereview_used"] == review["targeted_rereview_used"]
    assert entry["targeted_governance_rereview_count"] == review["targeted_rereview_count"]
    assert entry["targeted_governance_rereview_verdict"] == review["targeted_rereview_verdict"]


def test_registry_and_artifact_terminal_verdicts_agree() -> None:
    entry = _registry(AUTHORIZATION_ID)
    assert entry["terminal_outcome"] == AUTH["terminal_verdict"] == "DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AUTHORIZATION_READY"
    assert entry["authorization_state"] == AUTH["authorization_state"] == "AUTHORIZED_IF_CANONICAL"
    assert entry["authorization_effective"] == AUTH["authorization_effective"] == "AFTER_EXACT_CANONICAL_MERGE_ONLY"
    assert entry["canonical_base_sha"] == AUTH["canonicalization"]["candidate_base_sha"] == CANONICAL_MASTER
    assert entry["authority_level"] == AUTH["authority_level"] == "BOUNDED_PRELIVE_RUNTIME_PROFILE_MATERIALIZATION_REPAIR_ONLY"

    # Every artifact this registry entry claims as authoritative must exist and be Git-tracked.
    for relative in entry["authoritative_artifacts"]:
        assert (ROOT / relative).exists(), relative
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", relative],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert tracked.returncode == 0, f"{relative} is not Git-tracked"
