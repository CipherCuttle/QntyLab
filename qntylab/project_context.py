"""Git-backed project context and authority map for QntyLab.

This module deliberately owns project/planning interpretation only.  Research
state remains the responsibility of :mod:`qntylab.research_ledger`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from qntylab import research_ledger
from qntylab import qnty_context_adapter


SCHEMA_VERSION = 1
PROJECT_STATES = frozenset(
    {
        "IDEA",
        "PLANNED_NOT_AUTHORIZED",
        "ACTIVE",
        "BLOCKED",
        "RESULT_PENDING_RECORDING",
        "CLOSED_PASS",
        "CLOSED_NEGATIVE",
        "CLOSED_BLOCKED",
        "SUPERSEDED",
        "ARCHIVED",
    }
)
ADR_STATUSES = frozenset({"CURRENT_GLOBAL", "CURRENT_GLOBAL_COMPANION", "CURRENT_PROJECT_SPECIFIC", "HISTORICAL"})
AUTHORITY_DOMAINS = (
    ("EXPERIMENT_SCIENCE", "immutable preregistration / frozen result or receipt"),
    ("GLOBAL_ARCHITECTURE", "current global ADR in docs/ADR/registry.toml"),
    ("PROJECT_SPECIFIC_ARCHITECTURE", "project-scoped ADR in docs/ADR/registry.toml"),
    ("ACCUMULATED_RESEARCH_STATE", "append-only experiments/research ledger"),
    ("CURRENT_PLANNING", "docs/state/projects.toml"),
    ("HUMAN_ORIENTATION", "generated docs/CURRENT_ROADMAP.md and README"),
    ("NON_AUTHORITATIVE_CONVENIENCE", "chat history, GPT memory, and handoff prose"),
)

# Context Spine foundation.  The compiler is a read-only projection of canonical
# repository state; it stores nothing, mutates nothing, and is never an
# authority source.  Cross-repository reads require an adapter that this
# foundation deliberately does not implement.
CONTEXT_SPINE_VERSION = 3
PROJECT_ORIENTATION_SCHEMA_VERSION = "project-orientation-v0"
PROJECT_ORIENTATION_SCOPE = "PROJECT_CODE_REFERENCE_PROJECTION"
PROJECT_CODE_REFERENCE_SCOPE = "AUTHORITATIVE_ARTIFACTS_ONLY_FILTERED_TO_QNTYLAB_PYTHON"
PROJECT_CODE_REFERENCE_COMPLETENESS = "PARTIAL_PROJECTION_NOT_REPOSITORY_COMPLETENESS"
MODULE_INVENTORY_PROVENANCE = "GIT_INDEX_TRACKED_QNTYLAB_PYTHON"
ECOSYSTEM_CATALOG_SCHEMA_VERSION = 2
# ADR-0007 source precedence, highest authority first.  The rank is the position
# in this tuple; a catalog may only classify a source, never reorder the ladder.
PRECEDENCE_CLASSES = (
    "CANONICAL_GIT_IDENTITY",
    "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE",
    "REGISTERED_ARCHITECTURE_CONTRACT",
    "APPEND_ONLY_LEDGER_OR_IMMUTABLE_RECEIPT",
    "VALIDATED_IMPLEMENTATION_AND_TESTS",
    "DETERMINISTIC_GENERATED_VIEW",
    "ORIENTATION_PROSE",
    "HISTORICAL_ARTIFACT",
    "NON_AUTHORITATIVE_CONVENIENCE",
)
# Where each declared authority source sits on that ladder.  The classification
# is a compiler decision precisely so that no source can classify itself: a
# generated view cannot declare itself canonical Git identity, and the ADR
# contract cannot be demoted, by editing configuration.  An authority key with
# no entry here fails closed rather than defaulting to a rank.
AUTHORITY_PRECEDENCE = {
    "ecosystem_catalog": "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE",
    "project_registry": "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE",
    "global_architecture_registry": "REGISTERED_ARCHITECTURE_CONTRACT",
    "research_ledger_root": "APPEND_ONLY_LEDGER_OR_IMMUTABLE_RECEIPT",
    "current_roadmap": "DETERMINISTIC_GENERATED_VIEW",
}
DIRECTORY_AUTHORITY_KEYS = frozenset({"research_ledger_root"})
# The complete set of files this compiler is able to write, keyed by the logical
# generated view.  This table — not ``[authority]`` — is what grants the writer a
# destination.  Configuration still declares where a generated view lives, but a
# declaration is only ever reconciled against this mapping and can never
# introduce a path that is absent from it, so every repository path outside the
# table is outside the writer's capability rather than merely unlisted by a
# denylist.  A second writable destination requires editing this contract, and
# the tests that pin it, instead of editing mutable repository state.
GENERATED_VIEW_DESTINATIONS = {"CURRENT_ROADMAP": "docs/CURRENT_ROADMAP.md"}
# Which ``[authority]`` key declares each generated view's location.
GENERATED_VIEW_AUTHORITY_KEYS = {"CURRENT_ROADMAP": "current_roadmap"}
CURRENT_ROADMAP_VIEW = "CURRENT_ROADMAP"
GIT_IDENTITY_SOURCE_ID = "CANONICAL_GIT_IDENTITY"
# The declaration that names every other authority source, and therefore itself a
# canonical source at the rank its own contents define.
CONFIG_SOURCE_PATH = "qntylab.toml"
# Authority sources whose bytes the Context Spine compiler actually parses.  The
# packet's binding claim covers exactly these files plus the declaration above; a
# source that is only located and type-checked contributes no compiled bytes, so
# claiming it would make the binding a statement about the worktree instead of
# about what was compiled.
COMPILED_AUTHORITY_KEYS = ("ecosystem_catalog", "global_architecture_registry", "project_registry")
CONTEXT_ACCESS_CLASSES = frozenset({"LOCAL_CANONICAL_SOURCES", "NARROW_READ_ONLY_ADAPTER"})
# Only the Qnty read-only adapter is implemented at this schema version; the
# catalog cannot declare observation for another repository without code.
ADAPTER_STATUSES = frozenset({"NOT_APPLICABLE", "ADAPTER_NOT_IMPLEMENTED", "READ_ONLY_ADAPTER_IMPLEMENTED"})
EXTERNAL_CONTEXT_STATES = {
    "ADAPTER_NOT_IMPLEMENTED": "UNAVAILABLE_WITHOUT_ADAPTER",
    "READ_ONLY_ADAPTER_IMPLEMENTED": "UNAVAILABLE_WITHOUT_EXPLICIT_ROOT",
}
CONTEXT_SPINE_COMPILED = "CONTEXT_SPINE_COMPILED"
ARCHITECTURE_CONFLICT = "ARCHITECTURE_CONFLICT"
CONTEXT_SPINE_PROHIBITIONS = (
    "CONTEXT_SPINE_IS_A_DERIVED_VIEW_AND_NEVER_AN_AUTHORITY_SOURCE",
    "CONTEXT_SPINE_DOES_NOT_MUTATE_ANY_REPOSITORY_OR_SCIENTIFIC_STATE",
    "CONTEXT_SPINE_DOES_NOT_CREATE_OR_TRANSITION_A_PERMITTED_NEXT_ACTION",
    "GIT_IDENTITY_SELECTS_BYTES_AND_GRANTS_NO_SEMANTIC_AUTHORITY",
    "EXTERNAL_REPOSITORY_STATE_IS_NOT_OBSERVED_WITHOUT_AN_IMPLEMENTED_ADAPTER",
    "EXTERNAL_ROOT_IS_EXPLICIT_INPUT_AND_NOT_PACKET_IDENTITY",
    "GENERATED_VIEWS_AND_REMEMBERED_SUMMARIES_CANNOT_OVERRIDE_CANONICAL_GIT",
)

EXECUTION_CANONICAL_REF = "refs/remotes/origin/master"
DSH_STAGE_A_V1R3R2_ACTIVATION_SCHEMA = "dsh-stage-a-v1r3r2-one-episode-live-execution-activation-v0"
DSH_STAGE_A_V1R3R2_V0R1_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R1"
DSH_STAGE_A_V1R3R2_V0R1_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R1"
DSH_STAGE_A_V1R3R2_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2R1"
DSH_STAGE_A_V1R3R2_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2R1"
DSH_STAGE_A_V1R3R2_V0R3_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R3"
DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3"
_FRESH_AUTHORIZATION_BINDINGS = {
    DSH_STAGE_A_V1R3R2_V0R1_EXECUTION_ID: DSH_STAGE_A_V1R3R2_V0R1_AUTHORIZATION_ID,
    DSH_STAGE_A_V1R3R2_EXECUTION_ID: DSH_STAGE_A_V1R3R2_AUTHORIZATION_ID,
    DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_ID: DSH_STAGE_A_V1R3R2_V0R3_AUTHORIZATION_ID,
}
_FRESH_EXECUTION_IDS_WITH_V0R2R1_BINDING_RULES = frozenset(
    {DSH_STAGE_A_V1R3R2_EXECUTION_ID, DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_ID}
)
_MISSING = object()

# These are the fields that form one execution-authority view.  The activation
# artifact uses a nested representation while the project registry is flat;
# keeping the mapping explicit prevents either source from silently growing a
# second, unbound authority vocabulary.
_EXECUTION_PROJECTION_FIELDS = (
    ("project_id", ("project_id",), ("project_id",)),
    ("state", ("active_execution_project", "state"), ("state",)),
    ("authority_level", ("active_execution_project", "authority_level"), ("authority_level",)),
    ("implementation_authorized", ("active_execution_project", "implementation_authorized"), ("implementation_authorized",)),
    ("implementation_completed", ("active_execution_project", "implementation_completed"), ("implementation_completed",)),
    ("episode_consumed", ("active_execution_project", "episode_consumed"), ("episode_consumed",)),
    ("authorized_live_episodes", ("active_execution_project", "authorized_live_episodes"), ("authorized_live_episodes",)),
    ("second_episode_authorized", ("active_execution_project", "second_episode_authorized"), ("second_episode_authorized",)),
    ("whole_episode_retry_allowed", ("active_execution_project", "whole_episode_retry_allowed"), ("whole_episode_retry_allowed",)),
    ("execution_closure_pr_budget", ("active_execution_project", "execution_closure_pr_budget"), ("execution_closure_pr_budget",)),
    ("activation_consumes_live_episode", ("active_execution_project", "activation_consumes_live_episode"), ("activation_consumes_live_episode",)),
    ("activation_consumes_execution_closure_pr_budget", ("active_execution_project", "activation_consumes_execution_closure_pr_budget"), ("activation_consumes_execution_closure_pr_budget",)),
    ("authorization_state", ("authorization_state",), ("authorization_state",)),
    ("authorization_effective", ("authorization_effective",), ("authorization_effective",)),
)
_CLOSURE_PROJECTION_FIELDS = (
    "project_id",
    "authorization_state",
    "authorization_effective",
    "episode_consumed",
    "authorized_live_episodes",
    "second_episode_authorized",
    "whole_episode_retry_allowed",
    "execution_closure_pr_budget",
    "activation_consumes_live_episode",
    "activation_consumes_execution_closure_pr_budget",
)
_EXECUTION_STATUS_FIELDS = (
    ("episode_started", ("execution_status", "episode_started"), ("episode_started",)),
    ("episode_claimed", ("execution_status", "episode_claimed"), ("episode_claimed",)),
    ("episode_consumed_status", ("execution_status", "episode_consumed"), ("episode_consumed",)),
)
_AUTHORITY_FIREWALL_FIELDS = (
    ("stage_b_authorized", ("authority_firewall", "stage_b_authorized"), ("stage_b_authorized",)),
    ("qnty_runtime_authority", ("authority_firewall", "qnty_runtime_authority"), ("qnty_runtime_authority",)),
    ("trading_authority", ("authority_firewall", "trading_authority"), ("trading_authority",)),
    ("capital_authority", ("authority_firewall", "capital_authority"), ("capital_authority",)),
    ("scientific_execution_authorized", ("authority_firewall", "scientific_execution_authorized"), ("scientific_execution_authorized",)),
    ("qnty_agent_eval", ("authority_firewall", "qnty_agent_eval"), ("qnty_agent_eval",)),
)
_RUNTIME_IDENTITY_FIELDS = (
    ("pinned_dsh_commit", ("runtime_identity", "commit"), ("pinned_dsh_commit",)),
    ("pinned_dsh_tree", ("runtime_identity", "tree"), ("pinned_dsh_tree",)),
    ("pinned_dsh_tag", ("runtime_identity", "tag"), ("pinned_dsh_tag",)),
    ("qualified_launch_contract_digest", ("runtime_identity", "qualified_launch_contract_digest"), ("qualified_launch_contract_digest",)),
    ("runtime_manifest_digest", ("runtime_identity", "runtime_manifest_digest"), ("runtime_manifest_digest",)),
    ("executable_identity_digest", ("runtime_identity", "executable_identity_digest"), ("executable_identity_digest",)),
    ("launch_policy_digest", ("runtime_identity", "launch_policy_digest"), ("launch_policy_digest",)),
    ("codex_repair_digest", ("runtime_identity", "codex_repair_digest"), ("codex_repair_digest",)),
    ("claude_repair_digest", ("runtime_identity", "claude_repair_digest"), ("claude_repair_digest",)),
    ("superseded_digest_rejected", ("runtime_identity", "superseded_digest_rejected"), ("superseded_launch_digest_rejected",)),
    ("fixture_digest", ("fixture", "fixture_digest"), ("fixture_digest",)),
)
_FRESH_AUTHORIZATION_FIELDS = (
    ("authorization_project_id", ("authorization_identity", "project_id"), ("authorization_project_id",)),
    ("authorization_candidate_commit", ("authorization_identity", "candidate_commit"), ("authorization_candidate_commit",)),
    ("authorization_canonical_merge", ("authorization_identity", "canonical_merge"), ("authorization_canonical_merge",)),
    ("authorization_artifact", ("authorization_identity", "artifact"), ("authorization_artifact",)),
    ("episode_id", ("episode_identity", "episode_id"), ("episode_id",)),
    ("claim_ref", ("episode_identity", "claim_ref"), ("claim_ref",)),
)


class ProjectContextError(RuntimeError):
    """A canonical Project Context source is malformed, conflicting, or untrusted."""


@dataclass(frozen=True)
class RepositorySnapshot:
    """Invocation-scoped Git index membership used by authority validation."""

    root: Path
    tracked_paths: frozenset[str]

    @classmethod
    def acquire(cls, root: Path) -> "RepositorySnapshot":
        resolved_root = root.resolve()
        output = _git_bytes(resolved_root, "ls-files", "--cached", "-z")
        tracked_paths = frozenset(os.fsdecode(path) for path in output.split(b"\0") if path)
        return cls(resolved_root, tracked_paths)

    def contains_file(self, path: str) -> bool:
        return path in self.tracked_paths

    def contains_directory(self, path: str) -> bool:
        normalized = PurePosixPath(path).as_posix()
        if normalized == ".":
            return bool(self.tracked_paths)
        prefix = normalized.rstrip("/") + "/"
        return any(tracked.startswith(prefix) for tracked in self.tracked_paths)


@dataclass(frozen=True)
class ValidatedContext:
    """All canonical registries validated once for one logical invocation."""

    root: Path
    snapshot: RepositorySnapshot
    config: dict[str, Any]
    adr_registry: dict[str, Any]
    projects_registry: dict[str, Any]
    adrs: dict[str, dict[str, Any]]
    projects: dict[str, dict[str, Any]]


def _snapshot_for(root: Path, snapshot: RepositorySnapshot | None) -> RepositorySnapshot:
    resolved_root = root.resolve()
    if snapshot is None:
        return RepositorySnapshot.acquire(resolved_root)
    if snapshot.root != resolved_root:
        raise ProjectContextError("repository snapshot root does not match requested root")
    return snapshot


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _git_bytes(root: Path, *args: str, check: bool = True) -> bytes:
    # An inherited GIT_DIR or GIT_WORK_TREE would silently point these reads at a
    # different repository, so the ambient Git location is dropped and ``-C``
    # remains the only thing that selects which repository is inspected.
    # ``--no-optional-locks`` keeps a read from refreshing the index stat cache,
    # which is the one way an otherwise read-only command rewrites ``.git/index``.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    completed = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        check=False,
        capture_output=True,
        env=environment,
    )
    if check and completed.returncode:
        message = completed.stderr.decode("utf-8", "replace").strip() or "git command failed"
        raise ProjectContextError(message)
    return completed.stdout


def _run_git(root: Path, *args: str, check: bool = True) -> str:
    return _git_bytes(root, *args, check=check).decode("utf-8", "replace")


def _git_succeeds(root: Path, *args: str) -> bool:
    completed = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def _lookup(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


def _load_json_authority(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectContextError(f"cannot read JSON {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectContextError(f"JSON object required: {label}")
    return value


def _activation_artifact_paths(record: dict[str, Any]) -> list[str]:
    return [
        artifact
        for artifact in record.get("authoritative_artifacts", [])
        if isinstance(artifact, str) and Path(artifact).name == "activation.json"
    ]


def _projection_parity_issues(
    activation: dict[str, Any],
    record: dict[str, Any],
    *,
    include_lifecycle: bool,
) -> list[str]:
    fields = _EXECUTION_PROJECTION_FIELDS if include_lifecycle else tuple(
        field for field in _EXECUTION_PROJECTION_FIELDS if field[0] in _CLOSURE_PROJECTION_FIELDS
    )
    runtime_fields = _RUNTIME_IDENTITY_FIELDS
    if record.get("project_id") in _FRESH_EXECUTION_IDS_WITH_V0R2R1_BINDING_RULES:
        runtime_fields = tuple(
            field for field in runtime_fields if field[0] not in {"codex_repair_digest", "claude_repair_digest"}
        )
    bindings = (*fields, *_EXECUTION_STATUS_FIELDS, *_AUTHORITY_FIREWALL_FIELDS, *runtime_fields)
    issues: list[str] = []
    for label, activation_path, registry_path in bindings:
        activation_value = _lookup(activation, activation_path)
        registry_value = _lookup(record, registry_path)
        if activation_value is _MISSING or registry_value is _MISSING:
            issues.append(f"activation/registry projection missing {label}")
        elif activation_value != registry_value:
            issues.append(
                f"activation/registry projection mismatch for {label}: "
                f"activation={activation_value!r}, registry={registry_value!r}"
            )
    return issues


def _fresh_v0r1_binding_issues(
    root: Path,
    activation: dict[str, Any],
    record: dict[str, Any],
    identity: dict[str, Any],
    *,
    snapshot: RepositorySnapshot | None = None,
) -> list[str]:
    """Enforce the fresh V0R1 authorization and pre-claim boundary.

    The generic #185 projection contract binds an activation to its registry
    row.  This small V0R1 extension binds that paired view to the exact fresh
    authorization artifact as well, so a parity-preserving historical or
    branch-local substitute cannot become effective authority.
    """
    expected_authorization_id = _FRESH_AUTHORIZATION_BINDINGS.get(record.get("project_id"))
    if expected_authorization_id is None:
        return []

    issues: list[str] = []
    for label, activation_path, registry_path in _FRESH_AUTHORIZATION_FIELDS:
        activation_value = _lookup(activation, activation_path)
        registry_value = _lookup(record, registry_path)
        if activation_value is _MISSING or registry_value is _MISSING:
            issues.append(f"fresh V0R1 binding missing {label}")
        elif activation_value != registry_value:
            issues.append(
                f"fresh V0R1 binding mismatch for {label}: "
                f"activation={activation_value!r}, registry={registry_value!r}"
            )

    authorization = activation.get("authorization_identity")
    if not isinstance(authorization, dict):
        return [*issues, "fresh V0R1 authorization identity must be an object"]
    if authorization.get("project_id") != expected_authorization_id:
        issues.append("fresh V0R1 activation cannot substitute historical authorization")
    if activation.get("project_id") != record.get("project_id"):
        issues.append("fresh V0R1 activation project identity is invalid")
    canonical_predecessor_merge = _lookup(activation, ("canonicalization", "canonical_predecessor_merge"))
    if authorization.get("canonical_merge") != canonical_predecessor_merge:
        issues.append("fresh V0R1 authorization canonical merge does not match activation predecessor")
    if authorization.get("canonical_merge") != record.get("canonical_predecessor_merge"):
        issues.append("fresh V0R1 authorization canonical merge does not match registry predecessor")
    candidate_commit = authorization.get("candidate_commit")
    canonical_sha = identity.get("canonical_sha")
    if not isinstance(candidate_commit, str) or not candidate_commit:
        issues.append("fresh V0R1 authorization candidate commit is missing")
    elif not isinstance(canonical_sha, str) or not canonical_sha or not _git_succeeds(
        root, "merge-base", "--is-ancestor", candidate_commit, canonical_sha
    ):
        issues.append("fresh V0R1 authorization candidate is not in canonical origin/master")

    is_v0r3 = record.get("project_id") == DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_ID
    is_v0r2r1 = record.get("project_id") == DSH_STAGE_A_V1R3R2_EXECUTION_ID
    artifact_value = authorization.get("artifact")
    if not isinstance(artifact_value, str):
        issues.append("fresh V0R1 authorization artifact is missing")
    else:
        authorization_path = _authority_path(
            root,
            artifact_value,
            label="fresh V0R1 authorization artifact",
            snapshot=snapshot,
        )
        authorization_document = _load_json_authority(
            authorization_path, label="fresh V0R1 authorization artifact"
        )
        if authorization_document.get("project_id") != authorization.get("project_id"):
            issues.append("fresh V0R1 authorization artifact identity does not match activation")
        if is_v0r3:
            future_identity = _lookup(
                authorization_document, ("fresh_identity", "future_activation_project_id")
            )
        else:
            future_identity = authorization_document.get("execution_project_id")
        if future_identity != activation.get("project_id"):
            issues.append("fresh authorization execution identity does not match activation")
        if is_v0r3:
            expected_content_sha = authorization.get("canonical_content_sha256")
            if not isinstance(expected_content_sha, str):
                issues.append("fresh V0R3 authorization canonical content digest is missing")
            elif hashlib.sha256(authorization_path.read_bytes()).hexdigest() != expected_content_sha:
                issues.append("fresh V0R3 authorization canonical content digest mismatch")
            expected_blob_sha = authorization.get("git_blob_sha")
            if not isinstance(expected_blob_sha, str):
                issues.append("fresh V0R3 authorization Git blob identity is missing")
            elif canonical_sha:
                actual_blob_sha = _run_git(
                    root, "rev-parse", f"{canonical_sha}:{artifact_value}", check=False
                ).strip()
                if actual_blob_sha != expected_blob_sha:
                    issues.append("fresh V0R3 authorization Git blob identity mismatch")
            qualified = authorization_document.get("qualified_launch_contract")
            activation_qualified = activation.get("qualified_launch_contract")
            if not isinstance(qualified, dict) or not isinstance(activation_qualified, dict):
                issues.append("fresh V0R3 qualified launch contract binding is incomplete")
            else:
                for field in (
                    "digest",
                    "contract_artifact",
                    "qualification_artifact",
                    "contract_artifact_sha256",
                    "qualification_artifact_sha256",
                    "launch_policy_digest",
                ):
                    if activation_qualified.get(field) != qualified.get(field):
                        issues.append(f"fresh V0R3 qualified launch contract mismatch for {field}")
                for field, expected in (
                    (qualified.get("contract_artifact"), qualified.get("contract_artifact_sha256")),
                    (qualified.get("qualification_artifact"), qualified.get("qualification_artifact_sha256")),
                ):
                    if isinstance(field, str) and isinstance(expected, str):
                        artifact_file = _authority_path(
                            root, field, label="fresh V0R3 qualified contract artifact", snapshot=snapshot
                        )
                        if hashlib.sha256(artifact_file.read_bytes()).hexdigest() != expected:
                            issues.append("fresh V0R3 qualified contract artifact digest mismatch")
            auth_runtime = authorization_document.get("runtime_binding")
            activation_profile = activation.get("profile_contract")
            if not isinstance(auth_runtime, dict) or not isinstance(activation_profile, dict):
                issues.append("fresh V0R3 runtime/profile binding is incomplete")
            else:
                if activation_profile.get("physical_profile") != auth_runtime.get("physical_profile"):
                    issues.append("fresh V0R3 physical profile mismatch")
                if activation_profile.get("live_profile") != auth_runtime.get("stage_a_live_profile"):
                    issues.append("fresh V0R3 live profile mismatch")
                if activation_profile.get("offline_qualification_patch_allowed_for_live") is not False:
                    issues.append("fresh V0R3 offline qualification patch cannot be live-bound")
        if is_v0r2r1:
            if activation.get("canonical_enforcement_bytes") != authorization_document.get("canonical_enforcement_bytes"):
                issues.append("fresh V0R2R1 canonical enforcement bytes are not authorization-bound")
            for contract_name in ("profile_contract",):
                authorized_contract = authorization_document.get(contract_name)
                activation_contract = activation.get(contract_name)
                if not isinstance(authorized_contract, dict) or not isinstance(activation_contract, dict):
                    issues.append(f"fresh V0R2R1 {contract_name} binding is incomplete")
                else:
                    for field, expected in authorized_contract.items():
                        if activation_contract.get(field) != expected:
                            issues.append(f"fresh V0R2R1 {contract_name} mismatch for {field}")
        if is_v0r2r1 or is_v0r3:
            authorized_secret = authorization_document.get("secret_binding_contract")
            activation_secret = activation.get("secret_binding_contract")
            if not isinstance(authorized_secret, dict) or not isinstance(activation_secret, dict):
                issues.append("fresh secret binding contract is incomplete")
            else:
                for field, expected in authorized_secret.items():
                    if activation_secret.get(field) != expected:
                        issues.append(f"fresh secret binding mismatch for {field}")
        auth_canonicalization = authorization_document.get("canonicalization")
        if not isinstance(auth_canonicalization, dict):
            issues.append("fresh V0R1 authorization canonicalization is missing")
        else:
            if auth_canonicalization.get("future_activation_project_id") != activation.get("project_id"):
                issues.append("fresh V0R1 authorization future activation identity is not artifact-bound")
            if auth_canonicalization.get("authorization_does_not_activate") is not True:
                issues.append("fresh V0R1 authorization must not self-activate")
        expected_candidate_base = (
            authorization.get("canonical_merge")
            if is_v0r3
            else candidate_commit
        )
        if _lookup(activation, ("canonicalization", "candidate_base_sha")) != expected_candidate_base:
            issues.append("fresh authorization activation candidate base is not authorization-bound")

        contract = authorization_document.get("qualified_launch_contract")
        pinned = authorization_document.get("pinned_dsh_identity")
        if is_v0r3:
            source_identity = _lookup(authorization_document, ("runtime_binding", "source_identity"))
            if isinstance(source_identity, dict):
                pinned = {
                    "repository": str(source_identity.get("remote", ""))
                    .removeprefix("https://github.com/")
                    .removesuffix(".git"),
                    "commit": source_identity.get("commit"),
                    "tree": source_identity.get("tree"),
                    "tag": source_identity.get("tag"),
                }
        runtime = activation.get("runtime_identity")
        if not isinstance(contract, dict) or not isinstance(pinned, dict) or not isinstance(runtime, dict):
            issues.append("fresh V0R1 qualified runtime binding is incomplete")
        else:
            repairs = contract.get("repair_digests")
            if not isinstance(repairs, dict):
                if is_v0r3:
                    governed = _lookup(authorization_document, ("runtime_binding", "governed_patches"))
                    repairs = (
                        {
                            "codex": governed.get("codex_executable_binding"),
                            "claude": governed.get("claude_hard_read_only"),
                        }
                        if isinstance(governed, dict)
                        else {}
                    )
                elif not is_v0r2r1:
                    issues.append("fresh V0R1 qualified runtime repair binding is incomplete")
                    repairs = {}
            runtime_bindings = {
                "repository": (runtime.get("repository"), pinned.get("repository")),
                "commit": (runtime.get("commit"), pinned.get("commit")),
                "tree": (runtime.get("tree"), pinned.get("tree")),
                "tag": (runtime.get("tag"), pinned.get("tag")),
                "qualified_launch_contract_digest": (runtime.get("qualified_launch_contract_digest"), contract.get("digest")),
                "runtime_manifest_digest": (runtime.get("runtime_manifest_digest"), contract.get("runtime_manifest_digest")),
                "executable_identity_digest": (runtime.get("executable_identity_digest"), contract.get("executable_identity_digest")),
                "launch_policy_digest": (runtime.get("launch_policy_digest"), contract.get("launch_policy_digest")),
            }
            if repairs:
                runtime_bindings.update(
                    {
                        "codex_repair_digest": (runtime.get("codex_repair_digest"), repairs.get("codex")),
                        "claude_repair_digest": (runtime.get("claude_repair_digest"), repairs.get("claude")),
                    }
                )
            for label, (actual, expected) in runtime_bindings.items():
                if actual != expected:
                    issues.append(f"fresh V0R1 authorization/runtime mismatch for {label}")

        episode_authority = authorization_document.get("episode_authority")
        active_project = activation.get("active_execution_project")
        if not isinstance(episode_authority, dict) or not isinstance(active_project, dict):
            issues.append("fresh V0R1 episode authority binding is incomplete")
        else:
            episode_bindings = {
                "authorized_live_episodes": (active_project.get("authorized_live_episodes"), episode_authority.get("live_episodes_max")),
                "second_episode_authorized": (active_project.get("second_episode_authorized"), episode_authority.get("second_episode_allowed")),
                "whole_episode_retry_allowed": (active_project.get("whole_episode_retry_allowed"), episode_authority.get("whole_episode_retry_allowed")),
            }
            for label, (actual, expected) in episode_bindings.items():
                if actual != expected:
                    issues.append(f"fresh V0R1 authorization/episode mismatch for {label}")

        parent = activation.get("parent_authority")
        authorized_parent = authorization_document.get("parent_authority")
        if not isinstance(parent, dict) or not isinstance(authorized_parent, dict):
            issues.append("fresh V0R1 parent budget binding is incomplete")
        else:
            retry_policy = authorized_parent.get("retry_policy")
            if not isinstance(retry_policy, dict):
                if not (is_v0r2r1 or is_v0r3):
                    issues.append("fresh V0R1 authorization retry policy binding is incomplete")
                retry_policy = {}
            spend_authority = authorization_document.get("spend_authority")
            expected_spend = authorized_parent.get("max_total_spend_usd")
            if expected_spend is None and isinstance(spend_authority, dict):
                try:
                    expected_spend = float(spend_authority.get("cap_usd"))
                except (TypeError, ValueError):
                    expected_spend = _MISSING
            expected_tokens = authorized_parent.get("max_tokens_per_request")
            if expected_tokens is None:
                expected_tokens = authorized_parent.get("max_output_tokens_per_request")
            expected_llm_retries = retry_policy.get("llm_retries")
            expected_provider_retry = retry_policy.get("provider_retry")
            actual_llm_retries = parent.get("llm_retries")
            actual_provider_retry = parent.get("provider_retry")
            if is_v0r2r1 or is_v0r3:
                expected_llm_retries = authorized_parent.get("provider_internal_retries")
                expected_provider_retry = authorized_parent.get("provider_internal_retries")
                actual_llm_retries = parent.get("provider_internal_retries")
                actual_provider_retry = parent.get("provider_internal_retries")
            parent_bindings = {
                "provider": (parent.get("provider"), authorized_parent.get("provider")),
                "model": (parent.get("model"), authorized_parent.get("model")),
                "route": (parent.get("route"), authorized_parent.get("route")),
                "max_request_attempts": (parent.get("max_request_attempts"), authorized_parent.get("max_request_attempts")),
                "max_tokens_per_request": (parent.get("max_tokens_per_request"), expected_tokens),
                "max_total_spend_usd": (parent.get("max_total_spend_usd"), expected_spend),
                "llm_retries": (actual_llm_retries, expected_llm_retries),
                "provider_retry": (actual_provider_retry, expected_provider_retry),
                "automatic_continuation": (
                    parent.get("automatic_continuation"),
                    False if is_v0r2r1 or is_v0r3 else retry_policy.get("automatic_continuation"),
                ),
            }
            for label, (actual, expected) in parent_bindings.items():
                if actual != expected:
                    issues.append(f"fresh V0R1 authorization/parent budget mismatch for {label}")

        child = activation.get("child_authority")
        authorized_child = authorization_document.get("child_authority")
        if child != authorized_child:
            issues.append("fresh V0R1 authorization/child budget mismatch")

        authorized_policies = authorization_document.get("child_execution_policies")
        authorized_claude = authorized_policies.get("claude") if isinstance(authorized_policies, dict) else None
        claude = activation.get("claude_policy")
        claude_bindings = {
            "allowed_tools": (claude.get("allowed_tools") if isinstance(claude, dict) else _MISSING, authorized_claude.get("allowed_tools") if isinstance(authorized_claude, dict) else _MISSING),
            "denied_tools": (claude.get("denied_tools") if isinstance(claude, dict) else _MISSING, authorized_claude.get("disallowed_tools") if isinstance(authorized_claude, dict) else _MISSING),
            "write_allowed": (claude.get("write_allowed") if isinstance(claude, dict) else _MISSING, authorized_claude.get("write_allowed") if isinstance(authorized_claude, dict) else _MISSING),
            "edit_allowed": (claude.get("edit_allowed") if isinstance(claude, dict) else _MISSING, authorized_claude.get("edit_allowed") if isinstance(authorized_claude, dict) else _MISSING),
            "bash_allowed": (claude.get("bash_allowed") if isinstance(claude, dict) else _MISSING, authorized_claude.get("bash_allowed") if isinstance(authorized_claude, dict) else _MISSING),
            "agent_allowed": (claude.get("agent_allowed") if isinstance(claude, dict) else _MISSING, authorized_claude.get("agent_allowed") if isinstance(authorized_claude, dict) else _MISSING),
            "task_allowed": (claude.get("task_allowed") if isinstance(claude, dict) else _MISSING, authorized_claude.get("task_allowed") if isinstance(authorized_claude, dict) else _MISSING),
            "mcp_allowed": (claude.get("mcp_allowed") if isinstance(claude, dict) else _MISSING, authorized_claude.get("mcp_allowed") if isinstance(authorized_claude, dict) else _MISSING),
        }
        for label, (actual, expected) in claude_bindings.items():
            if actual != expected:
                issues.append(f"fresh V0R1 authorization/Claude policy mismatch for {label}")

    episode = activation.get("episode_identity")
    claim = activation.get("claim_contract")
    if not isinstance(episode, dict) or not isinstance(claim, dict):
        issues.append("fresh V0R1 episode and claim identities are required")
    else:
        if episode.get("episode_count") != 1 or episode.get("episode_consumed") is not False:
            issues.append("fresh V0R1 activation must bind exactly one unconsumed episode")
        if episode.get("claim_ref") != claim.get("remote_claim_ref"):
            issues.append("fresh V0R1 episode and claim references disagree")
        if claim.get("remote_claim_exists") is not False or claim.get("local_claim_exists") is not False:
            issues.append("fresh V0R1 existing claim state fails closed")
        if claim.get("created_during_activation_construction") is not False:
            issues.append("fresh V0R1 activation construction cannot create a claim")

    construction = activation.get("construction_receipts")
    if not isinstance(construction, dict):
        issues.append("fresh V0R1 construction receipts are missing")
    elif record.get("project_id") in _FRESH_EXECUTION_IDS_WITH_V0R2R1_BINDING_RULES:
        expected_zeroes = {
            "claim_creations": 0,
            "external_provider_requests": 0,
            "fixture_mutations": 0,
            "live_dsh_calls": 0,
            "real_claude_child_turns": 0,
            "real_codex_child_turns": 0,
            "real_secret_reads": 0,
            "spend_usd": "0",
        }
        for field, expected in expected_zeroes.items():
            if construction.get(field) != expected:
                issues.append(f"fresh activation construction receipt {field} must be {expected!r}")
        if construction.get("activation_artifacts_created") != 1:
            issues.append("fresh activation construction must create exactly one activation artifact")
    else:
        for field in ("remote_claim_created", "local_claim_created", "episode_claimed", "episode_consumed"):
            if construction.get(field) is not False:
                issues.append(f"fresh V0R1 construction receipt {field} must be false")

    firewall = activation.get("authority_firewall")
    expected_firewall = {
        "stage_b_authorized": False,
        "qnty_runtime_authority": "NONE",
        "trading_authority": "NONE",
        "capital_authority": "NONE",
        "scientific_execution_authorized": False,
        "promotion_authority": "NONE",
        "qnty_agent_eval": "NOT_APPLICABLE",
    }
    if not isinstance(firewall, dict):
        issues.append("fresh V0R1 downstream authority firewall is missing")
    else:
        for field, expected in expected_firewall.items():
            if firewall.get(field) != expected:
                issues.append(f"fresh V0R1 downstream firewall is not closed for {field}")

    return issues


def _is_terminal_execution_closure(record: dict[str, Any]) -> bool:
    outcome = record.get("terminal_outcome")
    artifacts = record.get("authoritative_artifacts", [])
    has_result_artifact = any(
        isinstance(artifact, str)
        and ("execution_evidence.json" in artifact or artifact.endswith("/closure.md"))
        for artifact in artifacts
    )
    return (
        record.get("state") in {"CLOSED_PASS", "CLOSED_NEGATIVE", "CLOSED_BLOCKED"}
        and record.get("implementation_authorized") is False
        and record.get("implementation_completed") is True
        and record.get("episode_consumed") is False
        and record.get("active_project_after_closure") == "NONE"
        and isinstance(outcome, str)
        and bool(outcome)
        and "AUTHORIZATION_AVAILABLE" not in outcome
        and "ACTIVATION_READY" not in outcome
        and has_result_artifact
    )


def _canonical_activation_identity(
    root: Path,
    activation: dict[str, Any],
    *,
    canonical_ref: str = EXECUTION_CANONICAL_REF,
) -> dict[str, Any]:
    git = _git_state(root)
    canonical_sha = _run_git(root, "rev-parse", "--verify", canonical_ref, check=False).strip()
    candidate_base_sha = _lookup(activation, ("canonicalization", "candidate_base_sha"))
    candidate_is_ancestor = (
        isinstance(candidate_base_sha, str)
        and bool(candidate_base_sha)
        and _git_succeeds(root, "merge-base", "--is-ancestor", candidate_base_sha, git["head_sha"])
    )
    return {
        "canonical_ref": canonical_ref,
        "canonical_sha": canonical_sha or None,
        "head_sha": git["head_sha"],
        "worktree_clean": git["clean"],
        "candidate_base_sha": candidate_base_sha if isinstance(candidate_base_sha, str) else None,
        "candidate_base_is_ancestor": candidate_is_ancestor,
        "effective": bool(git["clean"] and canonical_sha and git["head_sha"] == canonical_sha and candidate_is_ancestor),
    }


def execution_authority_projection(
    root: Path,
    projects: dict[str, dict[str, Any]],
    *,
    canonical_ref: str = EXECUTION_CANONICAL_REF,
    snapshot: RepositorySnapshot | None = None,
) -> dict[str, Any]:
    """Project activation artifacts into effective live execution authority.

    An ACTIVE registry row is executable only when its activation artifact is
    parity-consistent and the clean checkout is exactly the canonical remote
    master.  A branch-local candidate is therefore observable but ineffective.
    A non-active execution row is accepted only when an explicit terminal result
    closure records that no active project remains.
    """
    snapshot = _snapshot_for(root, snapshot)
    issues: list[str] = []
    active_projects: list[dict[str, Any]] = []
    identity_by_project: dict[str, dict[str, Any]] = {}

    for record in projects.values():
        activation_paths = _activation_artifact_paths(record)
        if not activation_paths:
            if record.get("state") == "ACTIVE":
                active_projects.append(record)
            continue
        if len(activation_paths) != 1:
            issues.append(f"execution project {record['project_id']} requires exactly one activation artifact")
            continue

        activation_path = _authority_path(
            root,
            activation_paths[0],
            label=f"project {record['project_id']} activation artifact",
            snapshot=snapshot,
        )
        activation = _load_json_authority(activation_path, label=activation_paths[0])
        if activation.get("schema_version") != DSH_STAGE_A_V1R3R2_ACTIVATION_SCHEMA:
            # Older Stage-A activation schemas predate this projection contract
            # and retain their own immutable closure semantics.
            continue
        activation_project_id = activation.get("project_id")
        if activation_project_id != record["project_id"]:
            issues.append(
                f"activation project_id does not match registry: "
                f"activation={activation_project_id!r}, registry={record['project_id']!r}"
            )
            continue

        identity = _canonical_activation_identity(root, activation, canonical_ref=canonical_ref)
        identity_by_project[record["project_id"]] = identity
        activation_state = _lookup(activation, ("active_execution_project", "state"))
        if record.get("state") == "ACTIVE":
            issues.extend(_projection_parity_issues(activation, record, include_lifecycle=True))
            issues.extend(_fresh_v0r1_binding_issues(root, activation, record, identity, snapshot=snapshot))
            activation_authorized = _lookup(activation, ("active_execution_project", "implementation_authorized"))
            activation_completed = _lookup(activation, ("active_execution_project", "implementation_completed"))
            activation_consumed = _lookup(activation, ("active_execution_project", "episode_consumed"))
            if activation_authorized is not True:
                # ACTIVE is a lifecycle label, not executable authority by
                # itself; an explicitly unauthorized row remains inactive.
                continue
            if activation_completed is not False or activation_consumed is not False:
                issues.append(
                    f"active execution project {record['project_id']} has invalid lifecycle "
                    "(authorized ACTIVE rows must be incomplete and unconsumed)"
                )
                continue
            if not identity["effective"]:
                continue
            active_projects.append(record)
        elif _is_terminal_execution_closure(record):
            issues.extend(_projection_parity_issues(activation, record, include_lifecycle=False))
        elif activation_state == "ACTIVE":
            issues.extend(_projection_parity_issues(activation, record, include_lifecycle=True))
            issues.append(
                f"active activation {record['project_id']} lacks a valid ACTIVE registry row "
                "or explicit terminal execution closure"
            )

    if len(active_projects) > 1:
        issues.append("effective execution projection contains more than one ACTIVE project")
    return {
        "issues": sorted(set(issues)),
        "active_project": active_projects[0] if len(active_projects) == 1 and not issues else None,
        "identity_by_project": identity_by_project,
    }


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProjectContextError(f"cannot read TOML {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectContextError(f"TOML object required: {path}")
    return value


def _as_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectContextError(f"{label} must be a non-empty string")
    return value


def _authority_path(
    root: Path,
    raw_path: Any,
    *,
    label: str,
    expected: str = "file",
    snapshot: RepositorySnapshot | None = None,
) -> Path:
    snapshot = _snapshot_for(root, snapshot)
    raw = _as_string(raw_path, label)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ProjectContextError(f"authority path must be repository-relative without traversal: {raw}")
    lexical = root / candidate
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ProjectContextError(f"authority path escapes repository root: {raw}") from exc
    if lexical.is_symlink():
        raise ProjectContextError(f"authority path may not be a symlink: {raw}")
    if expected == "file" and not lexical.is_file():
        raise ProjectContextError(f"authority path must be a file: {raw}")
    if expected == "directory" and not lexical.is_dir():
        raise ProjectContextError(f"authority path must be a directory: {raw}")
    if not snapshot.contains_file(raw):
        raise ProjectContextError(f"authority source is not Git-tracked: {raw}")
    return lexical


def _authority_directory(
    root: Path,
    raw_path: Any,
    *,
    label: str,
    snapshot: RepositorySnapshot | None = None,
) -> Path:
    snapshot = _snapshot_for(root, snapshot)
    raw = _as_string(raw_path, label)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ProjectContextError(f"authority path must be repository-relative without traversal: {raw}")
    lexical = root / candidate
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ProjectContextError(f"authority path escapes repository root: {raw}") from exc
    if lexical.is_symlink() or not lexical.is_dir():
        raise ProjectContextError(f"authority path must be a non-symlink directory: {raw}")
    if not snapshot.contains_directory(raw):
        raise ProjectContextError(f"authority source is not Git-tracked: {raw}")
    return lexical


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProjectContextError(f"{label} must be an array")
    return value


def load_context_sources(
    root: Path,
    *,
    snapshot: RepositorySnapshot | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    snapshot = _snapshot_for(root, snapshot)
    config_path = _authority_path(root, CONFIG_SOURCE_PATH, label=CONFIG_SOURCE_PATH, snapshot=snapshot)
    config = _load_toml(config_path)
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ProjectContextError("unsupported qntylab.toml schema_version")
    _as_string(config.get("repository_id"), "repository_id")
    authority = config.get("authority")
    if not isinstance(authority, dict):
        raise ProjectContextError("qntylab.toml [authority] table is required")
    adr_path = _authority_path(
        root,
        authority.get("global_architecture_registry"),
        label="global_architecture_registry",
        snapshot=snapshot,
    )
    projects_path = _authority_path(root, authority.get("project_registry"), label="project_registry", snapshot=snapshot)
    _authority_path(root, authority.get("ecosystem_catalog"), label="ecosystem_catalog", snapshot=snapshot)
    _authority_path(root, authority.get("current_roadmap"), label="current_roadmap", snapshot=snapshot)
    _authority_directory(root, authority.get("research_ledger_root"), label="research_ledger_root", snapshot=snapshot)
    adr_registry = _load_toml(adr_path)
    projects_registry = _load_toml(projects_path)
    return config, adr_registry, projects_registry


def validate_adr_registry(
    root: Path,
    registry: dict[str, Any],
    *,
    snapshot: RepositorySnapshot | None = None,
) -> dict[str, dict[str, Any]]:
    snapshot = _snapshot_for(root, snapshot)
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise ProjectContextError("unsupported ADR registry schema_version")
    records = _require_list(registry.get("adr"), "ADR registry adr")
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ProjectContextError("ADR record must be a table")
        adr_id = _as_string(record.get("adr_id"), "ADR adr_id")
        if adr_id in by_id:
            raise ProjectContextError(f"duplicate ADR ID: {adr_id}")
        status = _as_string(record.get("status"), f"ADR {adr_id} status")
        if status not in ADR_STATUSES:
            raise ProjectContextError(f"unknown ADR status: {status}")
        _as_string(record.get("authority_scope"), f"ADR {adr_id} authority_scope")
        _authority_path(root, record.get("path"), label=f"ADR {adr_id} path", snapshot=snapshot)
        by_id[adr_id] = record
    current = [record for record in by_id.values() if record["status"] == "CURRENT_GLOBAL"]
    if len(current) != 1:
        raise ProjectContextError("exactly one CURRENT_GLOBAL ADR is required")
    if current[0]["authority_scope"] != "GLOBAL_ARCHITECTURE":
        raise ProjectContextError("CURRENT_GLOBAL ADR must have GLOBAL_ARCHITECTURE scope")
    companions = [record for record in by_id.values() if record["status"] == "CURRENT_GLOBAL_COMPANION"]
    for companion in companions:
        if companion["authority_scope"] == "GLOBAL_ARCHITECTURE":
            raise ProjectContextError("CURRENT_GLOBAL_COMPANION cannot have GLOBAL_ARCHITECTURE scope")

    edges: dict[str, set[str]] = {adr_id: set() for adr_id in by_id}
    for record in _require_list(registry.get("supersession", []), "ADR registry supersession"):
        if not isinstance(record, dict):
            raise ProjectContextError("ADR supersession must be a table")
        old = _as_string(record.get("superseded_adr_id"), "superseded_adr_id")
        new = _as_string(record.get("superseding_adr_id"), "superseding_adr_id")
        _as_string(record.get("scope"), "supersession scope")
        if old not in by_id or new not in by_id:
            raise ProjectContextError(f"supersession reference does not resolve: {old} -> {new}")
        if old == new:
            raise ProjectContextError(f"ADR self-supersession: {old}")
        edges[old].add(new)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(adr_id: str) -> None:
        if adr_id in visiting:
            raise ProjectContextError("ADR supersession cycle detected")
        if adr_id in visited:
            return
        visiting.add(adr_id)
        for successor in sorted(edges[adr_id]):
            visit(successor)
        visiting.remove(adr_id)
        visited.add(adr_id)

    for adr_id in sorted(by_id):
        visit(adr_id)
    return by_id


def validate_projects_registry(
    root: Path,
    registry: dict[str, Any],
    *,
    snapshot: RepositorySnapshot | None = None,
) -> dict[str, dict[str, Any]]:
    snapshot = _snapshot_for(root, snapshot)
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise ProjectContextError("unsupported projects registry schema_version")
    records = _require_list(registry.get("project"), "projects registry project")
    by_id: dict[str, dict[str, Any]] = {}
    edges: dict[str, set[str]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ProjectContextError("project record must be a table")
        project_id = _as_string(record.get("project_id"), "project_id")
        if project_id in by_id:
            raise ProjectContextError(f"duplicate project ID: {project_id}")
        state = _as_string(record.get("state"), f"project {project_id} state")
        if state not in PROJECT_STATES:
            raise ProjectContextError(f"unknown project state: {state}")
        _as_string(record.get("authority_level"), f"project {project_id} authority_level")
        _as_string(record.get("next_action"), f"project {project_id} next_action")
        if not isinstance(record.get("implementation_authorized"), bool):
            raise ProjectContextError(f"project {project_id} implementation_authorized must be boolean")
        if record["implementation_authorized"] and state != "ACTIVE":
            raise ProjectContextError(f"implementation_authorized=true requires ACTIVE: {project_id}")
        artifacts = _require_list(record.get("authoritative_artifacts"), f"project {project_id} authoritative_artifacts")
        if not artifacts:
            raise ProjectContextError(f"project {project_id} requires authoritative_artifacts")
        for artifact in artifacts:
            _authority_path(root, artifact, label=f"project {project_id} authoritative artifact", snapshot=snapshot)
        by_id[project_id] = record
        edges[project_id] = set()
    active = [record for record in by_id.values() if record["state"] == "ACTIVE"]
    if len(active) > 1:
        raise ProjectContextError("at most one ACTIVE project is permitted")

    for project_id, record in by_id.items():
        for field, reverse_field in (("supersedes", "superseded_by"), ("superseded_by", "supersedes")):
            targets = record.get(field, [])
            if not isinstance(targets, list) or not all(isinstance(item, str) for item in targets):
                raise ProjectContextError(f"project {project_id} {field} must be an array of IDs")
            for target in targets:
                if target not in by_id:
                    raise ProjectContextError(f"project supersession target does not resolve: {project_id} -> {target}")
                if target == project_id:
                    raise ProjectContextError(f"project self-supersession: {project_id}")
                reverse = by_id[target].get(reverse_field, [])
                if project_id not in reverse:
                    raise ProjectContextError(f"project supersession is not reciprocal: {project_id} {field} {target}")
                # ``superseded_by`` is the reciprocal spelling of a
                # ``supersedes`` edge, not a second precedence direction.
                source, successor = (project_id, target) if field == "supersedes" else (target, project_id)
                edges[source].add(successor)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(project_id: str) -> None:
        if project_id in visiting:
            raise ProjectContextError("project supersession cycle detected")
        if project_id in visited:
            return
        visiting.add(project_id)
        for successor in sorted(edges[project_id]):
            visit(successor)
        visiting.remove(project_id)
        visited.add(project_id)

    for project_id in sorted(by_id):
        visit(project_id)
    return by_id


def _validated_context(root: Path, *, snapshot: RepositorySnapshot | None = None) -> ValidatedContext:
    root = root.resolve()
    snapshot = _snapshot_for(root, snapshot)
    config, adr_registry, projects_registry = load_context_sources(root, snapshot=snapshot)
    adrs = validate_adr_registry(root, adr_registry, snapshot=snapshot)
    projects = validate_projects_registry(root, projects_registry, snapshot=snapshot)
    return ValidatedContext(root, snapshot, config, adr_registry, projects_registry, adrs, projects)


def _context_sources(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Derive the context-source set from the declared authority sources.

    The set is total over ``[authority]`` and carries a compiler-assigned
    precedence class, so it cannot under-report a canonical source, bind one
    source twice, or let configuration reorder the ADR-0007 ladder.
    """
    authority = config["authority"]
    unmapped = sorted(set(authority) - set(AUTHORITY_PRECEDENCE))
    if unmapped:
        raise ProjectContextError("declared authority sources have no precedence class: " + ", ".join(unmapped))
    sources = {
        GIT_IDENTITY_SOURCE_ID: {
            "source_id": GIT_IDENTITY_SOURCE_ID,
            "repository_id": config["repository_id"],
            "precedence_class": "CANONICAL_GIT_IDENTITY",
            "precedence_rank": 1,
            "source_kind": "INTRINSIC",
            "authority_key": None,
            "path": None,
        }
    }
    claimed: dict[str, str] = {}
    for key in sorted(authority):
        path = _as_string(authority[key], f"authority source {key}")
        if path in claimed:
            raise ProjectContextError(f"authority sources {claimed[path]} and {key} bind the same path: {path}")
        claimed[path] = key
        precedence_class = AUTHORITY_PRECEDENCE[key]
        sources[key.upper()] = {
            "source_id": key.upper(),
            "repository_id": config["repository_id"],
            "precedence_class": precedence_class,
            "precedence_rank": PRECEDENCE_CLASSES.index(precedence_class) + 1,
            "source_kind": "DIRECTORY" if key in DIRECTORY_AUTHORITY_KEYS else "FILE",
            "authority_key": key,
            "path": path,
        }
    return sources


def _catalog_repositories(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    repositories: dict[str, dict[str, Any]] = {}
    for record in _require_list(catalog.get("repository"), "ecosystem catalog repository"):
        if not isinstance(record, dict):
            raise ProjectContextError("ecosystem repository record must be a table")
        repository_id = _as_string(record.get("repository_id"), "ecosystem repository_id")
        if repository_id in repositories:
            raise ProjectContextError(f"duplicate ecosystem repository ID: {repository_id}")
        _as_string(record.get("durable_role"), f"repository {repository_id} durable_role")
        _as_string(record.get("default_branch"), f"repository {repository_id} default_branch")
        access = _as_string(record.get("context_access"), f"repository {repository_id} context_access")
        if access not in CONTEXT_ACCESS_CLASSES:
            raise ProjectContextError(f"unknown context_access: {access}")
        adapter_status = _as_string(record.get("adapter_status"), f"repository {repository_id} adapter_status")
        if adapter_status not in ADAPTER_STATUSES:
            raise ProjectContextError(f"unknown adapter_status: {adapter_status}")
        # A repository read through local canonical sources has no adapter, and
        # any other repository must declare one that is not implemented.
        if (access == "LOCAL_CANONICAL_SOURCES") != (adapter_status == "NOT_APPLICABLE"):
            raise ProjectContextError(f"repository {repository_id} adapter_status contradicts context_access")
        if adapter_status == "READ_ONLY_ADAPTER_IMPLEMENTED" and repository_id != qnty_context_adapter.QNTY_REPOSITORY_ID:
            raise ProjectContextError(f"implemented external adapter is not supported for {repository_id}")
        if adapter_status == "READ_ONLY_ADAPTER_IMPLEMENTED":
            _as_string(record.get("canonical_repository_locator"), f"repository {repository_id} canonical_repository_locator")
        repositories[repository_id] = record
    local = [record for record in repositories.values() if record["context_access"] == "LOCAL_CANONICAL_SOURCES"]
    if len(local) != 1:
        raise ProjectContextError("exactly one LOCAL_CANONICAL_SOURCES ecosystem repository is required")
    return repositories


def validate_ecosystem_catalog(config: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """Structurally validate the ecosystem catalog.

    The catalog declares durable ecosystem semantics only.  It does not declare
    context sources: those are derived from the authority sources this
    repository already owns, so the catalog cannot classify, omit, duplicate, or
    reorder them.  Malformed foundation state raises.  Disagreement between two
    individually valid canonical sources is not decided here;
    :func:`compile_context_spine` reports it as ``ARCHITECTURE_CONFLICT``.
    """
    if catalog.get("schema_version") != ECOSYSTEM_CATALOG_SCHEMA_VERSION:
        raise ProjectContextError("unsupported ecosystem catalog schema_version")
    ecosystem_id = _as_string(catalog.get("ecosystem_id"), "ecosystem_id")
    architecture = catalog.get("architecture")
    if not isinstance(architecture, dict):
        raise ProjectContextError("ecosystem catalog [architecture] table is required")
    references = {key: _as_string(architecture.get(key), f"ecosystem architecture {key}") for key in ("architecture_authority", "scientific_north_star")}
    repositories = _catalog_repositories(catalog)
    local_id = next(record["repository_id"] for record in repositories.values() if record["context_access"] == "LOCAL_CANONICAL_SOURCES")
    return {
        "ecosystem_id": ecosystem_id,
        "architecture_references": references,
        "repositories": repositories,
        "local_repository_id": local_id,
    }


def _adr_view(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in ("adr_id", "authority_scope", "path", "status")}


def _classified_paths(adrs: dict[str, dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """Canonical paths another source model has already placed on the ladder.

    Each entry maps a repository-relative path to the source model that
    classified it and the precedence class that classification implies.
    """
    classified = {CONFIG_SOURCE_PATH: (CONFIG_SOURCE_PATH, "REPOSITORY_MACHINE_READABLE_AUTHORITY_STATE")}
    for record in adrs.values():
        classified[record["path"]] = (f"ADR registry entry {record['adr_id']}", "REGISTERED_ARCHITECTURE_CONTRACT")
    return classified


def _source_classification_conflicts(config: dict[str, Any], adrs: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Disagreements about which precedence class one canonical path occupies.

    ``[authority]`` decides which path fills a role and the compiler decides the
    role's rank, but neither sees what a *different* canonical source already
    said about that path.  Pointing an authority key at a registered ADR document
    would otherwise compile clean while the packet asserted the same file both as
    a registered architecture contract and as something below it — and would then
    invite ``render`` to overwrite the contract with a generated view.  One
    canonical path may not silently occupy two mutually exclusive precedence
    classes, so the disagreement is reported rather than resolved.
    """
    classified = _classified_paths(adrs)
    conflicts = []
    for key in sorted(config["authority"]):
        path = config["authority"][key]
        if not isinstance(path, str) or path not in classified:
            continue
        owner, owning_class = classified[path]
        declared_class = AUTHORITY_PRECEDENCE.get(key)
        if declared_class != owning_class:
            conflicts.append(
                {
                    "code": "SOURCE_CLASSIFICATION_DISAGREEMENT",
                    "detail": f"authority source {key} classifies {path} as {declared_class or 'UNCLASSIFIED'}; {owner} classifies it as {owning_class}",
                }
            )
    return conflicts


def _architecture_conflicts(normalized: dict[str, Any], config: dict[str, Any], adrs: dict[str, dict[str, Any]], global_adr: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    conflicts: list[dict[str, str]] = _source_classification_conflicts(config, adrs)
    declared_repository = normalized["local_repository_id"]
    if declared_repository != config["repository_id"]:
        conflicts.append(
            {
                "code": "REPOSITORY_IDENTITY_DISAGREEMENT",
                "detail": f"qntylab.toml declares {config['repository_id']}; ecosystem catalog declares {declared_repository}",
            }
        )
    references = normalized["architecture_references"]
    if references["architecture_authority"] != global_adr["adr_id"]:
        conflicts.append(
            {
                "code": "ARCHITECTURE_AUTHORITY_DISAGREEMENT",
                "detail": f"ADR registry declares {global_adr['adr_id']} CURRENT_GLOBAL; ecosystem catalog declares {references['architecture_authority']}",
            }
        )
    north_star_id = references["scientific_north_star"]
    north_star = adrs.get(north_star_id)
    if north_star is None or north_star["status"] != "CURRENT_GLOBAL_COMPANION" or north_star["authority_scope"] != "GLOBAL_SCIENTIFIC_NORTH_STAR":
        conflicts.append(
            {
                "code": "SCIENTIFIC_NORTH_STAR_DISAGREEMENT",
                "detail": f"ecosystem catalog declares {north_star_id}, which the ADR registry does not register as a GLOBAL_SCIENTIFIC_NORTH_STAR companion",
            }
        )
        north_star = None
    return sorted(conflicts, key=lambda conflict: (conflict["code"], conflict["detail"])), north_star


def _foundation(
    root: Path,
    *,
    validated_context: ValidatedContext | None = None,
    snapshot: RepositorySnapshot | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, str]], dict[str, Any] | None]:
    """Load and reconcile the foundation without reading worktree Git state."""
    root = root.resolve()
    if validated_context is not None:
        if validated_context.root != root:
            raise ProjectContextError("validated context root does not match requested root")
        snapshot = validated_context.snapshot
        config = validated_context.config
        adrs = validated_context.adrs
    else:
        snapshot = _snapshot_for(root, snapshot)
        config, adr_registry, _ = load_context_sources(root, snapshot=snapshot)
        adrs = validate_adr_registry(root, adr_registry, snapshot=snapshot)
    catalog_path = _authority_path(
        root,
        config["authority"]["ecosystem_catalog"],
        label="ecosystem_catalog",
        snapshot=snapshot,
    )
    normalized = validate_ecosystem_catalog(config, _load_toml(catalog_path))
    global_adr = next(record for record in adrs.values() if record["status"] == "CURRENT_GLOBAL")
    conflicts, north_star = _architecture_conflicts(normalized, config, adrs, global_adr)
    return config, adrs, normalized, global_adr, conflicts, north_star


def _unbound_compiled_inputs(root: Path, relatives: list[str]) -> list[str]:
    """Compiled inputs whose worktree bytes are not the bytes HEAD records.

    ``git status``, the index stat cache, and the ``assume-unchanged`` and
    ``skip-worktree`` bits are self-reports about the index, not statements about
    the bytes this compiler read, so each input is compared directly against the
    blob HEAD stores for its path.  A path HEAD does not record is unbound.
    """
    unbound = []
    for relative in relatives:
        try:
            head = _git_bytes(root, "cat-file", "blob", f"HEAD:{relative}")
        except ProjectContextError:
            unbound.append(relative)
            continue
        if (root / relative).read_bytes() != head:
            unbound.append(relative)
    return unbound


def _external_repository_views(
    normalized: dict[str, Any], external_roots: dict[str, Path] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    supplied = external_roots or {}
    unknown = sorted(set(supplied) - set(normalized["repositories"]))
    if unknown:
        raise ProjectContextError("external root names unknown repository IDs: " + ", ".join(unknown))
    records: list[dict[str, Any]] = []
    conflicts: list[dict[str, str]] = []
    repository_keys = ("repository_id", "durable_role", "default_branch", "context_access", "adapter_status")
    for _, source in sorted(normalized["repositories"].items()):
        if source["repository_id"] == normalized["local_repository_id"]:
            continue
        record: dict[str, Any] = {
            **{key: source[key] for key in repository_keys},
            "context_state": EXTERNAL_CONTEXT_STATES.get(source["adapter_status"], "UNAVAILABLE"),
        }
        if source["repository_id"] == qnty_context_adapter.QNTY_REPOSITORY_ID and source["adapter_status"] == "READ_ONLY_ADAPTER_IMPLEMENTED":
            record["observation"] = None
            root = supplied.get(source["repository_id"])
            if root is not None:
                try:
                    record["observation"] = qnty_context_adapter.observe(
                        root,
                        expected_locator=source["canonical_repository_locator"],
                        expected_branch=source["default_branch"],
                    )
                    record["context_state"] = "AVAILABLE_READ_ONLY"
                except qnty_context_adapter.QntyAdapterError as exc:
                    record["context_state"] = ARCHITECTURE_CONFLICT
                    conflicts.append(
                        {
                            "code": "EXTERNAL_ADAPTER_CONTRACT_CONFLICT",
                            "detail": f"Qnty read-only adapter rejected explicit root: {exc}",
                        }
                    )
        records.append(record)
    return records, conflicts


def _project_orientation(
    root: Path,
    *,
    validated_context: ValidatedContext | None = None,
    snapshot: RepositorySnapshot | None = None,
) -> dict[str, Any]:
    """Project-scoped code references, with explicit partial-coverage semantics."""
    root = root.resolve()
    if validated_context is not None:
        if validated_context.root != root:
            raise ProjectContextError("validated context root does not match requested root")
        snapshot = validated_context.snapshot
        projects = validated_context.projects
    else:
        snapshot = _snapshot_for(root, snapshot)
        _, _, projects_registry = load_context_sources(root, snapshot=snapshot)
        projects = validate_projects_registry(root, projects_registry, snapshot=snapshot)
    module_inventory = sorted(
        path
        for path in snapshot.tracked_paths
        if path.startswith("qntylab/") and path.endswith(".py")
    )
    rows = []
    for project_id, project in sorted(projects.items()):
        references = sorted(
            {
                path
                for path in project["authoritative_artifacts"]
                if path.startswith("qntylab/") and path.endswith(".py")
            }
        )
        rows.append(
            {
                "project_id": project_id,
                "project_state": project["state"],
                "project_display_name": project.get("display_name", project_id),
                "project_code_references": references,
            }
        )
    return {
        "schema_version": PROJECT_ORIENTATION_SCHEMA_VERSION,
        "project_orientation_scope": PROJECT_ORIENTATION_SCOPE,
        "project_code_reference_scope": PROJECT_CODE_REFERENCE_SCOPE,
        "project_code_reference_completeness": PROJECT_CODE_REFERENCE_COMPLETENESS,
        "module_inventory_provenance": MODULE_INVENTORY_PROVENANCE,
        "module_inventory": module_inventory,
        "rows": rows,
    }


def _compile_context_spine(
    root: Path,
    *,
    external_roots: dict[str, Path] | None,
    validated_context: ValidatedContext,
) -> dict[str, Any]:
    """Compile the read-only Context Spine foundation packet.

    The local foundation is derived from canonical local repository bytes. Any
    external observation is opt-in through a named read-only adapter root and
    remains bounded by that adapter's contract.
    """
    root = root.resolve()
    config, adrs, normalized, global_adr, conflicts, north_star = _foundation(
        root,
        validated_context=validated_context,
    )
    sources = _context_sources(config)
    git = _git_state(root)
    compiled_inputs = sorted({CONFIG_SOURCE_PATH, *(config["authority"][key] for key in COMPILED_AUTHORITY_KEYS)})
    unbound = _unbound_compiled_inputs(root, compiled_inputs)
    external, adapter_conflicts = _external_repository_views(normalized, external_roots)
    conflicts = sorted([*conflicts, *adapter_conflicts], key=lambda conflict: (conflict["code"], conflict["detail"]))
    local = normalized["repositories"][normalized["local_repository_id"]]
    repository_keys = ("repository_id", "durable_role", "default_branch", "context_access", "adapter_status")
    return {
        "context_spine_version": CONTEXT_SPINE_VERSION,
        "ecosystem_id": normalized["ecosystem_id"],
        "packet_status": ARCHITECTURE_CONFLICT if conflicts else CONTEXT_SPINE_COMPILED,
        "generated_from": {
            "repository_id": config["repository_id"],
            "canonical_git_identity": {
                "repository_id": config["repository_id"],
                "head_sha": git["head_sha"],
                # Worktree status is the coarser, separate statement: it describes
                # the whole checkout, including files this compilation never read.
                "worktree_status": "CLEAN" if git["clean"] else "DIRTY",
                # The binding claim is decided only by the bytes actually compiled,
                # each compared against its blob at HEAD, and it names them so the
                # claim is auditable rather than a vague whole-tree assertion.
                "compiled_bytes_bound_to_head_sha": not unbound,
                "compiled_inputs": compiled_inputs,
                "unbound_compiled_inputs": unbound,
            },
            "git_identity_semantics": "GIT_IDENTITY_SELECTS_BYTES_NOT_SEMANTIC_AUTHORITY",
        },
        "architecture": {
            "current_global": _adr_view(global_adr),
            "scientific_north_star": _adr_view(north_star) if north_star else {"adr_id": normalized["architecture_references"]["scientific_north_star"], "authority_scope": None, "path": None, "status": "NOT_ESTABLISHED"},
            "companions": [_adr_view(adrs[adr_id]) for adr_id in sorted(adrs) if adrs[adr_id]["status"] == "CURRENT_GLOBAL_COMPANION"],
        },
        "repository": {key: local[key] for key in repository_keys},
        "project_orientation": _project_orientation(root, validated_context=validated_context),
        "external_repositories": external,
        "context_sources": sorted(sources.values(), key=lambda source: (source["precedence_rank"], source["source_id"])),
        "conflicts": conflicts,
        "prohibitions": list(CONTEXT_SPINE_PROHIBITIONS),
        "architecture_relevance_contract": {
            "contract_reference": global_adr["adr_id"],
            "contract_path": global_adr["path"],
            "default_relevance": "NOT_REQUIRED",
            "evaluation_status": "NOT_IMPLEMENTED",
        },
    }


def compile_context_spine(
    root: Path,
    *,
    external_roots: dict[str, Path] | None = None,
    snapshot: RepositorySnapshot | None = None,
    validated_context: ValidatedContext | None = None,
) -> dict[str, Any]:
    context = validated_context or _validated_context(root, snapshot=snapshot)
    return _compile_context_spine(root, external_roots=external_roots, validated_context=context)


def context_spine_bytes(root: Path, *, external_roots: dict[str, Path] | None = None) -> bytes:
    """Canonical serialization of the Context Spine packet, without a newline."""
    return _canonical_json(compile_context_spine(root, external_roots=external_roots))


def doctor(
    root: Path,
    *,
    snapshot: RepositorySnapshot | None = None,
    validated_context: ValidatedContext | None = None,
) -> list[str]:
    try:
        context = validated_context or _validated_context(root, snapshot=snapshot)
        config = context.config
        projects = context.projects
        projection = execution_authority_projection(root, projects, snapshot=context.snapshot)
        if projection["issues"]:
            raise ProjectContextError("execution authority projection conflict: " + "; ".join(projection["issues"]))
        packet = _compile_context_spine(root, external_roots=None, validated_context=context)
        if packet["packet_status"] != CONTEXT_SPINE_COMPILED:
            raise ProjectContextError("context spine conflict: " + "; ".join(f"{item['code']}: {item['detail']}" for item in packet["conflicts"]))
        data = config.get("data")
        if not isinstance(data, dict) or data.get("registry_status") != "NOT_ESTABLISHED":
            raise ProjectContextError("dataset registry status must be NOT_ESTABLISHED for V0")
        ledger_issues = research_ledger.doctor(root / config["authority"]["research_ledger_root"])
        if ledger_issues:
            raise ProjectContextError("research ledger conflict: " + "; ".join(sorted(ledger_issues)))
    except ProjectContextError as exc:
        return [str(exc)]
    return []


def _git_state(root: Path) -> dict[str, Any]:
    head_sha = _run_git(root, "rev-parse", "HEAD").strip()
    branch = _run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).strip()
    status = _run_git(root, "status", "--porcelain=v1", "--untracked-files=all")
    changed_paths = sorted({line[3:] for line in status.splitlines() if len(line) >= 4})
    return {
        "branch": branch or None,
        "clean": not changed_paths,
        "detached": not bool(branch),
        "head_sha": head_sha,
        "changed_paths": changed_paths,
    }


def _research_summary(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    research_root = root / config["authority"]["research_ledger_root"]
    try:
        state, trial_index, _ = research_ledger.verify_indexes_current(research_root)
        statuses: dict[str, int] = {}
        for row in state["variants"].values():
            statuses[row["status"]] = statuses.get(row["status"], 0) + 1
        return {
            "canonical_source": config["authority"]["research_ledger_root"],
            "completed_trial_count": len(trial_index["trials"]),
            "ledger_doctor_issues": research_ledger.doctor(research_root),
            "variant_status_counts": dict(sorted(statuses.items())),
        }
    except research_ledger.LedgerError as exc:
        return {"canonical_source": config["authority"]["research_ledger_root"], "error": str(exc)}


def context_data(
    root: Path,
    *,
    snapshot: RepositorySnapshot | None = None,
    validated_context: ValidatedContext | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    context = validated_context or _validated_context(root, snapshot=snapshot)
    config = context.config
    adrs = context.adrs
    projects = context.projects
    projection = execution_authority_projection(root, projects, snapshot=context.snapshot)
    if projection["issues"]:
        raise ProjectContextError("execution authority projection conflict: " + "; ".join(projection["issues"]))
    global_adr = next(record for record in adrs.values() if record["status"] == "CURRENT_GLOBAL")
    global_companions = [
        {key: record[key] for key in ("adr_id", "path", "authority_scope")}
        for record in adrs.values()
        if record["status"] == "CURRENT_GLOBAL_COMPANION"
    ]
    active = projection["active_project"]
    queued = sorted(
        (
            {
                "project_id": record["project_id"],
                "display_name": record.get("display_name", record["project_id"]),
                "next_action": record["next_action"],
            }
            for record in projects.values()
            if record["state"] == "PLANNED_NOT_AUTHORIZED"
        ),
        key=lambda record: record["project_id"],
    )
    stale = sorted(
        (
            {"project_id": record["project_id"], "state": record["state"], "next_action": record["next_action"]}
            for record in projects.values()
            if record["state"] in {"SUPERSEDED", "ARCHIVED", "CLOSED_PASS", "CLOSED_NEGATIVE", "CLOSED_BLOCKED"}
        ),
        key=lambda record: record["project_id"],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "repository_id": config["repository_id"],
        "authority_boundary": "Git-tracked canonical sources only; chat, GPT memory, and handoff prose cannot override Git.",
        "git": _git_state(root),
        "current_global_adr": {key: global_adr[key] for key in ("adr_id", "path", "authority_scope")},
        "current_global_companions": global_companions,
        "active_project": active,
        "current_permitted_next_action": active["next_action"] if active else "No project implementation is currently authorized.",
        "queued_but_unauthorized_projects": queued,
        "superseded_or_stale_planning": stale,
        "research_ledger": _research_summary(root, config),
        "future_dataset_registry": config["data"],
        "authority_domains": [{"domain": domain, "source": source} for domain, source in AUTHORITY_DOMAINS],
        "authority_conflicts_or_warnings": doctor(root, validated_context=context),
    }


def _roadmap_bytes(
    root: Path,
    *,
    validated_context: ValidatedContext | None = None,
    snapshot: RepositorySnapshot | None = None,
) -> bytes:
    if validated_context is not None:
        projects = validated_context.projects
    else:
        root = root.resolve()
        snapshot = _snapshot_for(root, snapshot)
        _, _, projects_registry = load_context_sources(root, snapshot=snapshot)
        projects = validate_projects_registry(root, projects_registry, snapshot=snapshot)
    groups = (("Active", "ACTIVE"), ("Queued — not authorized", "PLANNED_NOT_AUTHORIZED"), ("Closed / stale", None))
    lines = [
        "# GENERATED — DO NOT EDIT BY HAND",
        "",
        "This is a deterministic projection of `docs/state/projects.toml`; it is not an independent source of authority.",
        "",
    ]
    for heading, state in groups:
        records = [
            record
            for record in projects.values()
            if record["state"] == state
            or (state is None and record["state"] in {"SUPERSEDED", "ARCHIVED", "CLOSED_PASS", "CLOSED_NEGATIVE", "CLOSED_BLOCKED"})
        ]
        lines.extend((f"## {heading}", ""))
        if not records:
            lines.extend(("- None.", ""))
            continue
        for record in sorted(records, key=lambda item: item["project_id"]):
            name = record.get("display_name", record["project_id"])
            lines.append(f"- `{name}` — `{record['state']}`. {record['next_action']}")
        lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def _generated_view_destination(
    root: Path,
    config: dict[str, Any],
    view: str,
    *,
    snapshot: RepositorySnapshot | None = None,
) -> Path:
    """The one path this compiler may write for ``view``, or a closed failure.

    The destination is taken from :data:`GENERATED_VIEW_DESTINATIONS`;
    configuration never supplies it.  ``[authority]`` still declares the roadmap
    location, because that declaration is useful machine-readable repository
    state, but its only role here is to be reconciled: naming some other file is
    a disagreement about repository layout, not a grant of a new write
    capability, so it fails closed rather than redirecting the writer.  The
    declaration is likewise not normalized, repaired, or quietly followed toward
    the supported path — writing somewhere the repository did not declare would
    be the same defect wearing a different mask.

    Because the accepted value is one compiler-owned literal, a path this
    repository has never classified, or does not contain yet, is refused for the
    same reason a registered ADR is: it is not the supported destination.
    """
    supported = GENERATED_VIEW_DESTINATIONS[view]
    key = GENERATED_VIEW_AUTHORITY_KEYS[view]
    declared = config["authority"].get(key)
    if declared != supported:
        raise ProjectContextError(
            f"generated view {view} is written only to {supported}; "
            f"qntylab.toml declares {key} = {declared!r}"
        )
    # Resolved through the same guard as every other authority source, so the
    # supported path must still be a Git-tracked, non-symlink file inside this
    # repository before any byte is written to it.
    return _authority_path(root, supported, label=key, snapshot=snapshot)


def render(
    root: Path,
    *,
    check: bool,
    snapshot: RepositorySnapshot | None = None,
    validated_context: ValidatedContext | None = None,
) -> int:
    context = validated_context or _validated_context(root, snapshot=snapshot)
    config = context.config
    # Resolving the destination is the first thing that happens and the only
    # thing that decides where bytes may land, so an unauthorized target is
    # rejected before a single repository byte can be produced or written.
    path = _generated_view_destination(root, config, CURRENT_ROADMAP_VIEW, snapshot=context.snapshot)
    # ADR-0007 stops architecture-affecting mutation while canonical sources
    # conflict, so a generated view is never rewritten during a conflict.  The
    # reconciliation alone is enough here, and it leaves the Git index untouched.
    if _foundation(root, validated_context=context)[4]:
        print(f"project context error: {ARCHITECTURE_CONFLICT}; roadmap generation is blocked", file=sys.stderr)
        return 1
    expected = _roadmap_bytes(root, validated_context=context)
    if check:
        if path.read_bytes() != expected:
            print("project context error: generated roadmap is stale; run python -m qntylab.project_context render", file=sys.stderr)
            return 1
        print("roadmap current")
        return 0
    path.write_bytes(expected)
    print(path.relative_to(root))
    return 0


def context_text(data: dict[str, Any]) -> str:
    git = data["git"]
    active = data["active_project"]
    lines = [
        "# QntyLab Project Context",
        "",
        f"- Git: `{git['head_sha']}` on `{git['branch'] or 'DETACHED'}`; {'clean' if git['clean'] else 'dirty'}.",
        f"- Current global architecture: `{data['current_global_adr']['adr_id']}` — `{data['current_global_adr']['path']}`.",
        "",
        "## Current global companion guidance",
        "",
    ]
    if data["current_global_companions"]:
        lines.extend(
            f"- `{item['adr_id']}` — `{item['authority_scope']}` — `{item['path']}`."
            for item in data["current_global_companions"]
        )
    else:
        lines.append("- None.")
    lines.extend(("", f"- Active project: `{active['project_id'] if active else 'none'}`.", f"- Permitted next action: {data['current_permitted_next_action']}", "", "## Queued but not authorized", ""))
    if data["queued_but_unauthorized_projects"]:
        lines.extend(f"- `{item['display_name']}`" for item in data["queued_but_unauthorized_projects"])
    else:
        lines.append("- None.")
    lines.extend(("", "## Authority boundary", "", f"{data['authority_boundary']}", "", "## Research state"))
    research = data["research_ledger"]
    if "error" in research:
        lines.append(f"Research ledger conflict: {research['error']}")
    else:
        lines.append(f"Canonical ledger: `{research['canonical_source']}`; {research['completed_trial_count']} completed trials.")
    lines.extend(("", "## Warnings", ""))
    if data["authority_conflicts_or_warnings"]:
        lines.extend(f"- {issue}" for issue in data["authority_conflicts_or_warnings"])
    else:
        lines.append("- None.")
    return "\n".join(lines)


# Brief output bounds.  These are deterministic UTF-8 byte and line budgets, not
# tokenizer counts: no tokenizer is consulted, so no token limit is claimed.  A
# byte budget is the property that actually holds, because a single packet value
# carrying no whitespace bounds nothing under a word count.
BRIEF_MAX_LINES = 120
BRIEF_MAX_LINE_BYTES = 240
BRIEF_MAX_BYTES = BRIEF_MAX_LINES * (BRIEF_MAX_LINE_BYTES + 1)
BRIEF_LINE_TRUNCATION_MARKER = "...[LINE_TRUNCATED]"
BRIEF_TRUNCATION_MARKER = "- TRUNCATED: deterministic brief byte/line budget reached."
BRIEF_COMPLETE_PROJECTION = "- Complete projection: python -m qntylab.project_context spine"
# Reduced-fidelity orientation markers.  A section that cannot be rendered in
# full degrades through these instead of being dropped whole, so the reference
# evidence that makes the projection machine-checkable against the repository
# survives budget pressure from unrelated growth.
BRIEF_ORIENTATION_ROWS_REDUCED = (
    "- ORIENTATION_ROWS_REDUCED: rows carrying no project_code_references omitted for the brief budget."
)
BRIEF_ORIENTATION_INDEX_ONLY = (
    "- ORIENTATION_ROWS_REPLACED_BY_REFERENCE_INDEX: per-project attribution omitted for the brief budget."
)
# Control characters are flattened to spaces so an embedded newline in a packet
# value cannot smuggle extra rendered lines past the line budget.
_BRIEF_CONTROL_TRANSLATION = {code: " " for code in (*range(0x20), 0x7F)}


def _brief_field(value: Any, missing: str = "NOT_PRESENT_IN_PACKET") -> str:
    if value is None:
        return missing
    return str(value)


def _brief_external_record(packet: dict[str, Any], repository_id: str) -> dict[str, Any] | None:
    return next(
        (record for record in packet.get("external_repositories", []) if record.get("repository_id") == repository_id),
        None,
    )


def _brief_qnty_lines(record: dict[str, Any] | None) -> list[str]:
    if record is None:
        return [f"- {field} = NOT_PRESENT_IN_PACKET" for field in ("adapter", "context")]
    lines = [
        f"- adapter = {_brief_field(record.get('adapter_status'))}",
        f"- context = {_brief_field(record.get('context_state'))}",
    ]
    observation = record.get("observation")
    if not isinstance(observation, dict):
        unavailable = record.get("context_state", "NOT_AVAILABLE_WITHOUT_EXPLICIT_ROOT")
        lines.extend(
            f"- {field} = {unavailable}"
            for field in ("head SHA", "task_id", "protocol_id", "phase", "handoff integrity", "continuity verifier status", "next-action authority")
        )
        return lines
    identity = observation.get("generated_from", {}).get("canonical_git_identity", {})
    pointer = observation.get("control_pointer", {})
    lines.extend(
        [
            f"- head SHA = {_brief_field(identity.get('head_sha'))}",
            f"- task_id = {_brief_field(pointer.get('task_id'))}",
            f"- protocol_id = {_brief_field(pointer.get('protocol_id'))}",
            f"- phase = {_brief_field(pointer.get('phase'))}",
            f"- handoff integrity = {_brief_field(observation.get('handoff_integrity'))}",
            f"- continuity verifier status = {_brief_field(observation.get('continuity_verifier_status'))}",
            f"- next-action authority = {_brief_field(observation.get('next_action_authority'))}",
        ]
    )
    return lines


class _BriefVariants(tuple):
    """One brief section offered at decreasing fidelity, most complete first.

    Bounded rendering admits the first variant that fits the remaining budget.
    A section that would overflow therefore degrades to a smaller rendering of
    the same material instead of being dropped whole, which is what lets
    required control content survive growth in unrelated sections.
    """

    __slots__ = ()


def _packed_reference_lines(references: list[str]) -> list[str]:
    """Pack reference paths greedily into deterministic budget-width lines."""
    if not references:
        return ["- NONE"]
    lines: list[str] = []
    current = ""
    for reference in references:
        candidate = f"{current}, {reference}" if current else f"- {reference}"
        if current and len(candidate.encode("utf-8")) > BRIEF_MAX_LINE_BYTES:
            lines.append(current)
            current = f"- {reference}"
        else:
            current = candidate
    lines.append(current)
    return lines


def _orientation_variants(orientation: dict[str, Any]) -> _BriefVariants:
    """Render project orientation at three decreasing fidelities.

    ``project_code_references`` are the evidence that the projection is grounded
    in real repository paths, so they are the last orientation material to go:
    full attributed rows degrade to the rows that actually carry references, and
    those degrade to a packed index of every distinct referenced path.  The
    reduction is content-driven and carries no project, path or phase literal.
    """
    header = [
        "## Project orientation",
        "",
        f"- scope = {_brief_field(orientation.get('project_orientation_scope'))}",
        f"- reference scope = {_brief_field(orientation.get('project_code_reference_scope'))}",
        f"- completeness = {_brief_field(orientation.get('project_code_reference_completeness'))}",
        f"- module inventory provenance = {_brief_field(orientation.get('module_inventory_provenance'))}",
    ]
    rows = [row for row in orientation.get("rows", []) if isinstance(row, dict)]

    def _row_line(row: dict[str, Any]) -> str:
        references = ", ".join(row.get("project_code_references", [])) or "NONE"
        return (
            f"- {row.get('project_display_name', row.get('project_id', 'UNKNOWN'))}"
            f" [{row.get('project_id', 'UNKNOWN')}] ({row.get('project_state', 'UNKNOWN')})"
            f" -> {references}"
        )

    referencing = [row for row in rows if row.get("project_code_references")]
    index = sorted({reference for row in rows for reference in row.get("project_code_references", [])})
    return _BriefVariants(
        (
            [*header, "- project_code_references =", *(_row_line(row) for row in rows), ""],
            [
                *header,
                BRIEF_ORIENTATION_ROWS_REDUCED,
                "- project_code_references =",
                *(_row_line(row) for row in referencing),
                "",
            ],
            [
                *header,
                BRIEF_ORIENTATION_INDEX_ONLY,
                "- project_code_reference_index =",
                *_packed_reference_lines(index),
                "",
            ],
        )
    )


def _brief_sections(packet: dict[str, Any]) -> list[list[str] | _BriefVariants]:
    conflicts = packet.get("conflicts") or []
    status = "ARCHITECTURE_CONFLICT" if conflicts else "CONTEXT_AVAILABLE"
    qnty = _brief_external_record(packet, "Qnty")
    if not conflicts and (qnty is None or qnty.get("context_state") != "AVAILABLE_READ_ONLY"):
        status = "CONTEXT_PARTIAL"
    repository = packet.get("repository", {})
    external = {
        record.get("repository_id"): record
        for record in packet.get("external_repositories", [])
        if isinstance(record, dict)
    }
    orientation_section = _orientation_variants(packet.get("project_orientation", {}))
    authority_section = [
        "## Authority boundaries",
        "",
        "- Git identity selects bytes, not semantic authority.",
        "- Handoff is not Qnty acceptance.",
        "- NEXT_ACTION authority is not established unless a canonical source says otherwise; no NEXT_ACTION field is emitted.",
        "- No science, runtime, live, trading, or capital authority is inferred.",
    ]
    conflicts_section = [
        "## Conflicts / blockers",
        "",
        *(
            ["**ARCHITECTURE_CONFLICT**"]
            + [f"- {item.get('code', 'CONFLICT')}: {item.get('detail', 'unspecified conflict')}" for item in conflicts]
            if conflicts
            else ["- None."]
        ),
        "",
        "- unavailable external roots = "
        + (", ".join(record["repository_id"] for record in packet.get("external_repositories", []) if record.get("context_state") == "UNAVAILABLE_WITHOUT_EXPLICIT_ROOT") or "None"),
    ]
    sections: list[list[str] | _BriefVariants] = [
        [
            "# Qnty Ecosystem Brief",
            "",
            f"**Orientation status: {status}**",
            "",
            "This is a deterministic view of the compiled Context Spine packet.",
        ],
        [
            "## Canonical identity",
            "",
            f"- QntyLab canonical head = {_brief_field(packet.get('generated_from', {}).get('canonical_git_identity', {}).get('head_sha'))}",
            f"- Context Spine packet version = {_brief_field(packet.get('context_spine_version'))}",
            f"- ecosystem catalog version = {_brief_field(packet.get('ecosystem_catalog_version'))}",
        ],
        [
            "## Architecture",
            "",
            f"- QntyLab durable role = {_brief_field(repository.get('durable_role'))}",
            f"- Qnty durable role = {_brief_field(external.get('Qnty', {}).get('durable_role'))}",
            f"- QntyAgentEval role = {_brief_field(external.get('QntyAgentEval', {}).get('durable_role'))}",
            f"- QntyPolicyGate role = {_brief_field(external.get('QntyPolicyGate', {}).get('durable_role'))}",
        ],
        [
            "## Current QntyLab state",
            "",
            "- active project(s) = NOT_PRESENT_IN_PACKET (Context Spine foundation packet)",
            "- queued/not-authorized = NOT_PRESENT_IN_PACKET (Context Spine foundation packet)",
            f"- architecture conflicts = {len(conflicts)}",
        ],
        ["## External repositories", "", "For Qnty:", *_brief_qnty_lines(qnty), ""],
        [
            "For QntyAgentEval:",
            f"- adapter = {_brief_field(external.get('QntyAgentEval', {}).get('adapter_status'))}",
            "",
            "For QntyPolicyGate:",
            f"- adapter = {_brief_field(external.get('QntyPolicyGate', {}).get('adapter_status'))}",
        ],
    ]
    # Authority boundaries are fixed safety content.  Render them before the
    # variable-length conflict and orientation sections so bounded truncation
    # cannot silently remove them as the packet grows.
    sections.append(authority_section)
    if conflicts:
        sections.append(conflicts_section)
    sections.append(orientation_section)
    if not conflicts:
        sections.append(conflicts_section)
    return sections


def _brief_line(line: str) -> str:
    """Flatten and clamp one rendered line to a deterministic UTF-8 byte budget."""
    flattened = line.translate(_BRIEF_CONTROL_TRANSLATION)
    encoded = flattened.encode("utf-8")
    if len(encoded) <= BRIEF_MAX_LINE_BYTES:
        return flattened
    keep = BRIEF_MAX_LINE_BYTES - len(BRIEF_LINE_TRUNCATION_MARKER)
    return encoded[:keep].decode("utf-8", "ignore") + BRIEF_LINE_TRUNCATION_MARKER


def _brief_byte_length(lines: list[str]) -> int:
    return len("\n".join(lines).encode("utf-8"))


def _bounded_brief(sections: list[list[str] | _BriefVariants]) -> str:
    lines: list[str] = []
    truncated = False
    for section in sections:
        # A section may offer decreasing fidelities.  Admitting the first one
        # that fits keeps required content present when only optional detail
        # overflows, instead of deleting the whole section for one line.
        variants = section if isinstance(section, _BriefVariants) else (section,)
        for index, variant in enumerate(variants):
            rendered_section = [_brief_line(line) for line in variant]
            candidate = lines + rendered_section
            if any(BRIEF_LINE_TRUNCATION_MARKER in line for line in rendered_section):
                truncated = True
            if len(candidate) > BRIEF_MAX_LINES or _brief_byte_length(candidate) > BRIEF_MAX_BYTES:
                continue
            if index:
                truncated = True
            lines = candidate
            break
        else:
            truncated = True
            break
    if truncated:
        while lines and (
            len(lines) + 2 > BRIEF_MAX_LINES
            or _brief_byte_length(lines + [BRIEF_COMPLETE_PROJECTION, BRIEF_TRUNCATION_MARKER]) > BRIEF_MAX_BYTES
        ):
            lines.pop()
        lines.extend((BRIEF_COMPLETE_PROJECTION, BRIEF_TRUNCATION_MARKER))
    text = "\n".join(lines)
    encoded = text.encode("utf-8")
    if len(encoded) > BRIEF_MAX_BYTES:
        # Unconditional backstop: the rendered brief never exceeds the ceiling,
        # whatever a future section composition does.
        keep = BRIEF_MAX_BYTES - len(BRIEF_TRUNCATION_MARKER) - len(BRIEF_COMPLETE_PROJECTION) - 2
        text = encoded[:keep].decode("utf-8", "ignore") + "\n" + BRIEF_COMPLETE_PROJECTION + "\n" + BRIEF_TRUNCATION_MARKER
    return text


def brief_text(packet: dict[str, Any]) -> str:
    """Render only already-normalized Context Spine packet data."""
    return _bounded_brief(_brief_sections(packet))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QntyLab Git-backed project context")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--external-root", action="append", default=[], dest="external_roots", metavar="REPOSITORY_ID=PATH")
    subparsers = parser.add_subparsers(dest="command")
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--strict", action="store_true")
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--check", action="store_true")
    spine_parser = subparsers.add_parser("spine", help="emit the read-only Context Spine foundation packet as canonical JSON")
    spine_parser.add_argument("--external-root", action="append", dest="external_roots", metavar="REPOSITORY_ID=PATH", default=argparse.SUPPRESS)
    subparsers.add_parser("brief", help="emit a bounded deterministic view of the compiled Context Spine packet")
    return parser


def _parse_external_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        repository_id, separator, raw_path = value.partition("=")
        if not separator or not repository_id or not raw_path or repository_id in roots:
            raise ProjectContextError("external root must be a unique REPOSITORY_ID=PATH binding")
        roots[repository_id] = Path(raw_path)
    return roots


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        snapshot = RepositorySnapshot.acquire(root)
        if args.command == "doctor":
            issues = doctor(root, snapshot=snapshot)
            if issues:
                for issue in issues:
                    print(f"SOURCE_CONFLICT: {issue}", file=sys.stderr)
                raise SystemExit(1)
            print("project context ok")
            return
        if args.command == "render":
            raise SystemExit(render(root, check=args.check, snapshot=snapshot))
        if args.command == "spine":
            packet = compile_context_spine(
                root,
                external_roots=_parse_external_roots(args.external_roots),
                snapshot=snapshot,
            )
            sys.stdout.buffer.write(_canonical_json(packet) + b"\n")
            raise SystemExit(0 if packet["packet_status"] == CONTEXT_SPINE_COMPILED else 1)
        if args.command == "brief":
            packet = compile_context_spine(
                root,
                external_roots=_parse_external_roots(args.external_roots),
                snapshot=snapshot,
            )
            print(brief_text(packet))
            raise SystemExit(0 if packet["packet_status"] == CONTEXT_SPINE_COMPILED else 1)
        data = context_data(root, snapshot=snapshot)
        if args.as_json:
            sys.stdout.buffer.write(_canonical_json(data) + b"\n")
        else:
            print(context_text(data))
    except (OSError, ProjectContextError, research_ledger.LedgerError) as exc:
        print(f"project context error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
