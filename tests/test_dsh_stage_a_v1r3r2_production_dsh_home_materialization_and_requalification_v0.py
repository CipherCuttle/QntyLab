"""Production Stage-A DSH_HOME materialization and requalification V0.

These tests bind the frozen evidence of the implementation phase: the
production materializer identity, the whole-home manifest, determinism, the
twenty negative controls, the action-time parity receipt, the offline
actual-DSH requalification, and the successor qualified launch contract.

They also assert the boundaries the phase was not permitted to cross: no live
authority, no V0R5, no secret read, no claim, no provider traffic, no spend, no
runtime rebuild, no composite launcher modification, and no mutation of the
ambient scratch DSH_HOME that remains the referent of the V0R4 evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0"
PHASE = CONTRACT_ROOT / "dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0"
EVIDENCE = PHASE / "evidence"

AUTHORIZATION_PATH = (
    CONTRACT_ROOT
    / "dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_action_time_parity_authorization_v0"
    / "authorization.json"
)
AUTHORIZATION_SHA256 = "e0a056b5b8905736ab174fa46407166ab8f1357ef1f6e082e69a3f51f265c221"

A392 = "a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be"
COMPOSITE_LAUNCHER_DIGEST = "6f212de0576127fea1dd2778a69c49a3b755a017a9d55f97f18b9057dc15c329"
RUNTIME_MANIFEST_DIGEST = "0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3"
EXECUTABLE_IDENTITY_DIGEST = "ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9"
PINNED_DSH_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"

AMBIENT_ROOTS = (
    "/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home",
    "/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r2-claude-repair-source",
    "/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair-source-2",
    "/home/swirky/node_modules",
)


def _load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


DIGESTS = _load("digests.json")
DETERMINISM = _load("determinism.json")
NEGATIVE_CONTROLS = _load("negative_controls.json")
PARITY = _load("action_time_parity_receipt.json")
QUALIFICATION = _load("offline_actual_dsh_qualification.json")
SUCCESSOR = _load("successor_contract.json")
HOME_MANIFEST = _load("dsh_home_manifest.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------- authority ---

def test_bound_to_the_exact_canonical_authorization_bytes() -> None:
    assert _sha256(AUTHORIZATION_PATH) == AUTHORIZATION_SHA256
    governing = SUCCESSOR["contract"]["governingAuthorization"]
    assert governing["artifactSha256"] == AUTHORIZATION_SHA256
    assert governing["canonicalMaster"] == "838b6e03608e4c2bc686a4f571dfbb340a333ddb"
    assert governing["projectId"] == (
        "DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AND_ACTION_TIME_PARITY_AUTHORIZATION_V0"
    )


def test_no_live_authority_and_no_v0r5_was_created() -> None:
    contract = SUCCESSOR["contract"]
    assert contract["LIVE_AUTHORITY"] is False
    assert contract["separateV0R5AuthorizationRequired"] is True
    assert contract["v0r5Created"] is False
    assert DIGESTS["LIVE_AUTHORITY"] is False
    assert DIGESTS["V0R5_CREATED"] is False
    assert PARITY["LIVE_AUTHORITY"] is False
    assert PARITY["v0r5Created"] is False
    # no V0R5 artifact directory may exist
    assert not list(CONTRACT_ROOT.glob("*v0r5*"))


def test_phase_consumed_no_secret_claim_provider_or_spend() -> None:
    for counters in (PARITY["counters"],):
        assert counters["REAL_SECRET_READS"] == 0
        assert counters["CLAIMS_CREATED"] == 0
        assert counters["PUBLIC_PROVIDER_REQUESTS"] == 0
        assert counters["REAL_MODEL_CALLS"] == 0
        assert counters["REAL_CODEX_TURNS"] == 0
        assert counters["REAL_CLAUDE_TURNS"] == 0
        assert counters["SPEND_USD"] == 0
    for receipt in QUALIFICATION.values():
        assert receipt["realSecretReads"] == 0
        assert receipt["claimsCreated"] == 0
        assert receipt["authoritativeClaims"] == 0
        assert receipt["publicProviderRequests"] == 0
        assert receipt["realModelCalls"] == 0
        assert receipt["realCodexTurns"] == 0
        assert receipt["realClaudeTurns"] == 0
        assert receipt["spendUsd"] == 0


# ------------------------------------------------------- frozen identities ---

def test_pinned_runtime_and_launcher_identities_are_unchanged() -> None:
    assert DIGESTS["RUNTIME_MANIFEST_DIGEST"] == RUNTIME_MANIFEST_DIGEST
    assert DIGESTS["EXECUTABLE_IDENTITY_DIGEST"] == EXECUTABLE_IDENTITY_DIGEST
    assert DIGESTS["PHYSICAL_RUNTIME_BYTES_CHANGED"] is False
    assert DIGESTS["DSH_SOURCE_BYTES_CHANGED"] is False
    assert DIGESTS["RUNTIME_REBUILT"] is False
    assert DIGESTS["COMPOSITE_LAUNCHER_MODIFIED"] is False

    launcher = ROOT / SUCCESSOR["contract"]["compositeLauncher"]["path"]
    assert _sha256(launcher) == COMPOSITE_LAUNCHER_DIGEST == DIGESTS["COMPOSITE_LAUNCHER_DIGEST"]

    source = SUCCESSOR["contract"]["pinnedDshSourceIdentity"]
    assert source["commit"] == PINNED_DSH_COMMIT
    assert source["tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert source["tag"] == "dsh-v0.1.0-rc.7"


def test_materializer_digest_matches_the_file_the_contract_binds() -> None:
    path = ROOT / SUCCESSOR["contract"]["productionDshHomeMaterializer"]["path"]
    assert path.is_file()
    digest = _sha256(path)
    assert digest == SUCCESSOR["NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST"]
    assert digest == SUCCESSOR["contract"]["productionDshHomeMaterializer"]["digest"]
    assert digest == DIGESTS["NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST"]


# ------------------------------------------------- successor supersedes a392 ---

def test_a392_is_preserved_as_predecessor_but_not_the_final_contract() -> None:
    contract = SUCCESSOR["contract"]
    assert contract["predecessorQualifiedContractDigest"] == A392
    assert DIGESTS["PREDECESSOR_QUALIFIED_CONTRACT_DIGEST"] == A392
    assert contract["predecessorStatus"] == (
        "PRESERVED_HISTORICALLY_SUPERSEDED_AS_THE_COMPLETE_FINAL_LIVE_CONTRACT"
    )
    successor_digest = SUCCESSOR["NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST"]
    assert successor_digest != A392
    assert successor_digest == DIGESTS["NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST"]


def test_successor_contract_binds_every_required_component() -> None:
    contract = SUCCESSOR["contract"]
    for key in (
        "predecessorQualifiedContractDigest",
        "governingAuthorization",
        "pinnedDshSourceIdentity",
        "runtimeManifestDigest",
        "executableIdentityDigest",
        "productionDshHomeMaterializer",
        "dshHomeManifestSchema",
        "productionDshHomeIdentity",
        "compositeLauncher",
        "stageAPolicy",
        "parentPolicy",
        "childController",
        "codexBoundary",
        "claudeBoundary",
        "workspaceContainment",
        "claimSecretOrdering",
        "fixtureIdentity",
    ):
        assert contract[key], f"successor contract must bind {key}"

    identity = contract["productionDshHomeIdentity"]
    assert identity["productionStubProviderExcluded"] is True
    assert identity["stubPresenceBehavior"] == "FAIL_CLOSED"
    assert identity["excludedQualificationOnlyPackages"] == ["@qntylab/dsh-stage-a-stub-provider"]
    assert set(identity["requiredDeepseekPackageTreeDigests"]) == {
        "dsh-llm",
        "dsh-llm-pi-ai",
        "dsh-subagent-claude-code",
        "dsh-subagent-codex",
        "dsh-subprocess",
        "dsh-tool-subagent",
    }
    assert set(identity["qntylabProductionPackages"]) == {
        "@qntylab/dsh-stage-a-gated-provider",
        "@qntylab/dsh-stage-a-parent-enforcement",
    }
    assert contract["fixtureIdentity"]["fixtureDigest"] == (
        "397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552"
    )


# ------------------------------------------------------------ home identity ---

def test_home_manifest_covers_the_whole_home_with_canonical_provenance() -> None:
    assert HOME_MANIFEST["classification"] == "PRODUCTION"
    assert HOME_MANIFEST["productionStubProviderPresent"] is False
    assert HOME_MANIFEST["provenance"]["ambientAuthorityUsed"] is False
    assert HOME_MANIFEST["provenance"]["ambientRootsUsed"] == []
    assert HOME_MANIFEST["provenance"]["pinnedRuntime"]["commit"] == PINNED_DSH_COMMIT

    objects = HOME_MANIFEST["objects"]
    assert len(objects) == DETERMINISM["objectCount"]
    # coverage is whole-home, far beyond the six packages the launcher checks
    assert len(objects) > 200
    for obj in objects:
        assert obj["classification"] == "PRODUCTION"
        assert obj["canonicalSource"]
        if obj["type"] == "file":
            assert obj["digest"]
        elif obj["type"] == "symlink":
            # containment is recorded, and no target encodes an absolute temp path
            assert obj["containment"] == "PINNED_DSH_RUNTIME_ROOT"
            assert not obj["targetRealpathRelativeToRuntimeRoot"].startswith("..")
            assert not obj["targetRealpathRelativeToRuntimeRoot"].startswith("/")
        elif obj["type"] == "package-tree":
            assert obj["packageTreeDigest"] and obj["wholeTreeDigest"]
        else:  # pragma: no cover - schema guard
            raise AssertionError(f"unknown object type: {obj['type']}")

    # every profile file is present and no stub provider is anywhere in the home
    paths = {obj["path"] for obj in objects}
    for name in ("cordis.yml", "cordis.patch.yml", "package.json", "pnpm-workspace.yaml"):
        assert f"profiles/headless/{name}" in paths
    assert "profiles/node_modules/@qntylab/dsh-stage-a-gated-provider" in paths
    assert "profiles/node_modules/@qntylab/dsh-stage-a-parent-enforcement" in paths
    assert not any("stub-provider" in path for path in paths)


def test_home_manifest_declares_its_nondeterministic_residue() -> None:
    residue = HOME_MANIFEST["nondeterministicResidue"]
    assert residue, "nondeterministic residue must be enumerated explicitly"
    fields = {item["field"] for item in residue}
    assert "materializedAtUtc" in fields
    assert "destinationAbsolutePath" in fields
    for item in residue:
        assert item["excludedFromIdentity"] is True
        assert item["reason"]
    # the identity body itself must not carry a temp absolute path
    serialized = json.dumps(HOME_MANIFEST)
    assert "/tmp/" not in serialized


def test_no_ambient_root_supplies_identity_in_the_frozen_evidence() -> None:
    serialized = json.dumps(HOME_MANIFEST) + json.dumps(SUCCESSOR)
    for ambient in AMBIENT_ROOTS:
        assert ambient not in serialized, f"evidence references ambient root {ambient}"


def test_ambient_scratch_dsh_home_was_not_repaired_or_backfilled() -> None:
    ambient = Path(AMBIENT_ROOTS[0])
    if not ambient.exists():
        return
    # the Stage-A package scope must still be absent: this is the untouched
    # physical referent of the V0R4 BLOCK_RUNTIME_IDENTITY evidence
    assert not (ambient / "profiles/node_modules/@qntylab").exists()
    assert not (ambient / "dsh-home-manifest.json").exists()


# ---------------------------------------------------------------- receipts ---

def test_two_independent_materializations_are_identical() -> None:
    assert DETERMINISM["terminal"] == "DETERMINISTIC"
    assert DETERMINISM["identical"] is True
    assert DETERMINISM["HOME_A_DIGEST"] == DETERMINISM["HOME_B_DIGEST"]
    assert DETERMINISM["HOME_A_DIGEST"] == DIGESTS["DSH_HOME_MANIFEST_DIGEST"]
    for key in (
        "profileFileDigestsEqual",
        "packageInventoryEqual",
        "symlinkIdentitiesEqual",
        "qntylabPackageDigestsEqual",
    ):
        assert DETERMINISM[key] is True


def test_all_twenty_negative_controls_executed_and_passed() -> None:
    assert NEGATIVE_CONTROLS["requiredControls"] == 20
    assert NEGATIVE_CONTROLS["executedControls"] == 20
    assert NEGATIVE_CONTROLS["passingControls"] == 20
    assert NEGATIVE_CONTROLS["terminal"] == "20_OF_20_PASS"
    names = [control["name"] for control in NEGATIVE_CONTROLS["controls"]]
    assert len(set(names)) == 20
    for index in range(1, 21):
        assert any(name.startswith(f"NC-{index:02d} ") for name in names), f"missing NC-{index:02d}"
    for control in NEGATIVE_CONTROLS["controls"]:
        assert control["status"] == "PASS"


def test_supplementary_controls_hold_the_hostile_review_repair() -> None:
    """The High finding's repair is held by executed controls, not by prose."""
    supplementary = NEGATIVE_CONTROLS["supplementaryControls"]
    names = [control["name"] for control in supplementary]
    assert any(name.startswith("NC-19b") for name in names)
    assert any(name.startswith("NC-19c") for name in names)
    for control in supplementary:
        assert control["status"] == "PASS"


def test_home_manifest_discloses_skipped_dependency_edges() -> None:
    """Skipped closure edges are enumerated, not silently dropped."""
    skipped = HOME_MANIFEST["provenance"]["skippedDependencyEdges"]
    assert skipped["loaderVisibleUnresolvedPackages"] == 0
    assert skipped["count"] == len(skipped["names"]) > 0
    assert skipped["names"] == sorted(skipped["names"])
    assert skipped["basis"]
    # a skipped name must never also be a materialized package
    materialized = {entry["packageName"] for entry in HOME_MANIFEST["packageInventory"]}
    assert not (set(skipped["names"]) & materialized)


def test_action_time_parity_receipt_passes_every_non_secret_gate() -> None:
    assert PARITY["terminal"] == "ACTION_TIME_PARITY_PASS"
    assert PARITY["singleProductionPreparationPathUsedByQualificationAndLive"] is True
    assert PARITY["hiddenQualificationOnlyPreparationUsed"] is False
    for gate in (
        "MATERIALIZER",
        "DSH_HOME_IDENTITY",
        "RUNTIME_IDENTITY",
        "EXECUTABLE_IDENTITY",
        "SUCCESSOR_CONTRACT",
        "COMPOSITE_PREFLIGHT",
        "WORKSPACE_CONTAINMENT",
        "FIXTURE_IDENTITY",
        "ALL_NON_SECRET_GATES",
    ):
        assert PARITY["gates"][gate] == "PASS", f"gate {gate} did not pass"
    assert PARITY["stopBoundary"] == "IMMEDIATELY_BEFORE_REAL_SECRET_READ"
    assert PARITY["realSecretPathInspected"] is False
    assert PARITY["fixture"]["canonicalFixtureMutated"] is False


def test_offline_qualification_ran_the_real_dsh_over_a_materialized_home() -> None:
    assert set(QUALIFICATION) == {"clean", "repair"}
    for scenario, receipt in QUALIFICATION.items():
        assert receipt["terminal"] == "PRODUCTION_OFFLINE_QUALIFICATION_PASS", scenario
        assert receipt["actualDshProcessConfirmed"] is True
        assert receipt["dshExitCode"] == 0
        assert receipt["dshHomeSource"] == "PRODUCTION_DSH_HOME_MATERIALIZER"
        assert receipt["qualificationOnlyHelperUsed"] is False
        assert receipt["ambientDshHomeUsed"] is False
        assert receipt["childController"] == "PASS"
        assert receipt["canonicalStageAPolicyActive"] is True
        assert receipt["workspaceContainment"] is True
        assert receipt["nativeChildSentinelLeaks"] == 0
        assert receipt["nativeExecutableIdentityMatches"] is True
        assert receipt["fakeNativeChildInvocations"] == receipt["expectedFakeNativeChildInvocations"]
        # the production home identity is recorded, and the stub only ever
        # arrives through the explicit qualification overlay
        assert receipt["productionHomeManifestDigest"] == DIGESTS["DSH_HOME_MANIFEST_DIGEST"]
        assert receipt["qualificationOverlayPackages"] == ["@qntylab/dsh-stage-a-stub-provider"]
    assert QUALIFICATION["clean"]["childTerminalOutcome"] == "PASS_NO_CRITICAL_HIGH"
    assert QUALIFICATION["repair"]["childTerminalOutcome"] == "PASS_AFTER_BOUNDED_REPAIR"


# ------------------------------------------------------- production sources ---

def test_production_sources_never_reach_the_qualification_only_helper() -> None:
    """Production code must not import, invoke, or be steered by the old helper.

    The successor contract legitimately *names* the helper's path in order to
    record it as a non-authority, so a bare substring scan would be wrong. What
    must hold is that no production module imports the qualification script,
    calls the helper, or honours the ambient qualified-home override.
    """
    modules = (
        "materializer/qntylab-materialize-stage-a-dsh-home.mjs",
        "preparation/prepare-production-launch.mjs",
        "contract/successor-contract.mjs",
        "parity/run-action-time-parity.mjs",
    )
    for relative in modules:
        source = (PHASE / relative).read_text(encoding="utf-8")
        imports = re.findall(r"^\s*import\s[^\n]*?from\s+'([^']+)'", source, re.MULTILINE)
        for target in imports:
            assert "run-composite-qualification" not in target, (
                f"{relative} imports the qualification-only helper module"
            )
        assert "prepareDisposableDshHome(" not in source, f"{relative} calls the helper"
        assert "QNTYLAB_QUALIFIED_DSH_HOME" not in source, (
            f"{relative} honours the ambient qualified-home override"
        )

    # the contract records the helper as an explicit non-authority
    materializer = SUCCESSOR["contract"]["productionDshHomeMaterializer"]
    assert materializer["isTheOnlyProductionDshHomeAuthority"] is True
    assert materializer["qualificationOnlyHelperIsProductionAuthority"] is False
    assert materializer["qualificationOnlyHelperPath"].endswith("run-composite-qualification.mjs")


def test_registry_records_the_closed_implementation_phase() -> None:
    import tomllib

    registry = tomllib.loads((ROOT / "docs/state/projects.toml").read_text(encoding="utf-8"))
    entries = [
        project
        for project in registry["project"]
        if project["project_id"]
        == "DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AND_REQUALIFICATION_V0"
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["state"] == "CLOSED_PASS"
    assert entry["implementation_completed"] is True
    assert entry["implementation_authorized_after_closure"] is False
    assert entry["active_project_after_closure"] == "NONE"
    assert entry["live_authority_created"] is False
    assert entry["v0r5_created"] is False
    assert entry["secret_reads"] == 0
    assert entry["claims_created"] == 0
    assert entry["public_provider_requests"] == 0
    assert entry["real_model_calls"] == 0
    assert entry["real_child_turns"] == 0
    assert entry["spend_usd"] == 0.0
    assert entry["ambient_dsh_home_bytes_modified"] == 0
    assert entry["runtime_bytes_modified"] == 0
    assert entry["composite_launcher_modified"] is False
    assert entry["m01_package_manager_invoked"] is False
    assert entry["m01_runtime_rebuild_performed"] is False
    assert entry["new_qualified_launch_contract_digest"] == (
        SUCCESSOR["NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST"]
    )
    assert entry["production_materializer_digest"] == (
        SUCCESSOR["NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST"]
    )
    assert entry["a392_remains_final_complete_live_contract"] is False
    # the hostile review outcome is recorded truthfully, with no unrepaired High
    assert entry["hostile_review_count"] == 1
    assert entry["hostile_unrepaired_critical_total"] == 0
    assert entry["hostile_unrepaired_high_total"] == 0
    assert entry["hostile_high_total"] == entry["hostile_high_repaired_total"] == 1
    assert entry["targeted_rereview_used"] is True
    assert entry["targeted_rereview_count"] == 1
    assert "PLACEHOLDER" not in entry["hostile_review_verdict"]
    assert entry["loader_visible_unresolved_packages"] == 0


def test_no_active_project_remains() -> None:
    result = subprocess.run(
        ["python", "-m", "qntylab.project_context", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    context = json.loads(result.stdout)
    assert context["active_project"] in (None, "none", "NONE")
