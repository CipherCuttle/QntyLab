"""Execution-authority projection: the bounded domain extension for Stage-A.

This module is the domain-specific extension behind the Project Context seam.
The generic project-context machinery knows only the seam function
:func:`execution_authority_projection` — a fail-closed projection that maps a
validated projects registry plus its activation artifacts onto effective live
execution authority.  Every Stage-A identity constant, runtime-identity field
map, and fresh-authorization binding rule lives here and nowhere else; the
generic core contains none of them.

Trusted-core boundary: this module performs the authority-relevant hash
bindings and Git ancestry checks, but it grants no authority by itself — its
output is a projection with issues, consumed fail-closed by the orchestration
layer in :mod:`qntylab.project_context`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

# Bounded seam: this module imports only the generic primitives below.  It must
# never import any other project-context layer, and no generic layer may import
# this module — the composition root binds the projection in.
from qntylab.project_context_core import (
    EXECUTION_CANONICAL_REF,
    RepositorySnapshot,
    _MISSING,
    _authority_path,
    _git_bytes,
    _git_succeeds,
    _git_state,
    _load_json_authority,
    _lookup,
    _run_git,
    _snapshot_for,
)


DSH_STAGE_A_V1R3R2_ACTIVATION_SCHEMA = "dsh-stage-a-v1r3r2-one-episode-live-execution-activation-v0"
DSH_STAGE_A_V1R3R2_V0R1_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R1"
DSH_STAGE_A_V1R3R2_V0R1_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R1"
DSH_STAGE_A_V1R3R2_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2R1"
DSH_STAGE_A_V1R3R2_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2R1"
DSH_STAGE_A_V1R3R2_V0R3_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R3"
DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3"
DSH_STAGE_A_V1R3R2_V0R4_AUTHORIZATION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R4"
DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4"
DSH_STAGE_A_V1R3R2_V0R6_EXECUTION_ID = "DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R6"
_FRESH_AUTHORIZATION_BINDINGS = {
    DSH_STAGE_A_V1R3R2_V0R1_EXECUTION_ID: DSH_STAGE_A_V1R3R2_V0R1_AUTHORIZATION_ID,
    DSH_STAGE_A_V1R3R2_EXECUTION_ID: DSH_STAGE_A_V1R3R2_AUTHORIZATION_ID,
    DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_ID: DSH_STAGE_A_V1R3R2_V0R3_AUTHORIZATION_ID,
    DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_ID: DSH_STAGE_A_V1R3R2_V0R4_AUTHORIZATION_ID,
}
_FRESH_EXECUTION_IDS_WITH_V0R2R1_BINDING_RULES = frozenset(
    {
        DSH_STAGE_A_V1R3R2_EXECUTION_ID,
        DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_ID,
        DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_ID,
        DSH_STAGE_A_V1R3R2_V0R6_EXECUTION_ID,
    }
)

# Explicit public export contract: the seam function plus the identity
# constants that were historically public on ``qntylab.project_context``.
# The composition root binds exactly these declared names generically, so the
# historical import surface survives while every identity stays owned here.
__all__ = (
    "execution_authority_projection",
    "DSH_STAGE_A_V1R3R2_ACTIVATION_SCHEMA",
    "DSH_STAGE_A_V1R3R2_V0R1_AUTHORIZATION_ID",
    "DSH_STAGE_A_V1R3R2_V0R1_EXECUTION_ID",
    "DSH_STAGE_A_V1R3R2_AUTHORIZATION_ID",
    "DSH_STAGE_A_V1R3R2_EXECUTION_ID",
    "DSH_STAGE_A_V1R3R2_V0R3_AUTHORIZATION_ID",
    "DSH_STAGE_A_V1R3R2_V0R3_EXECUTION_ID",
    "DSH_STAGE_A_V1R3R2_V0R4_AUTHORIZATION_ID",
    "DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_ID",
    "DSH_STAGE_A_V1R3R2_V0R6_EXECUTION_ID",
)

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
# V0R6 records the composite launcher policy digest flat as
# composite_launch_policy_digest.  The registry-path override binds the
# activation's nested launch_policy_digest to that composite field, scoped
# strictly to the V0R6 execution id so no other row's registry vocabulary is
# remapped.  (The V0R6 superseded digest lives only on the AUTHORIZATION row,
# which this parity view does not bind, so the superseded binding is dropped
# for exactly the V0R6 execution id inside _projection_parity_issues; the
# entry below is retained to keep the override vocabulary explicit.)
_V0R6_REGISTRY_PATH_OVERRIDES = {
    "launch_policy_digest": ("composite_launch_policy_digest",),
    "superseded_digest_rejected": ("superseded_launch_digest_rejected",),
}
_FRESH_AUTHORIZATION_FIELDS = (
    ("authorization_project_id", ("authorization_identity", "project_id"), ("authorization_project_id",)),
    ("authorization_candidate_commit", ("authorization_identity", "candidate_commit"), ("authorization_candidate_commit",)),
    ("authorization_canonical_merge", ("authorization_identity", "canonical_merge"), ("authorization_canonical_merge",)),
    ("authorization_artifact", ("authorization_identity", "artifact"), ("authorization_artifact",)),
    ("episode_id", ("episode_identity", "episode_id"), ("episode_id",)),
    ("claim_ref", ("episode_identity", "claim_ref"), ("claim_ref",)),
)


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
    registry_path_overrides = {}
    if record.get("project_id") == DSH_STAGE_A_V1R3R2_V0R6_EXECUTION_ID:
        registry_path_overrides = _V0R6_REGISTRY_PATH_OVERRIDES
        # The V0R6 execution row predates the flat superseded-digest field.
        # The rejected digest is recorded only on the V0R6 AUTHORIZATION row,
        # which this parity view does not bind, so the flat binding cannot
        # resolve for the V0R6 execution row.  Exclude it for exactly this
        # execution id; every other row (V0R5, V0R2R1, V0R3, V0R4) still
        # carries and enforces the flat superseded-launch-digest binding.
        runtime_fields = tuple(
            field for field in runtime_fields if field[0] != "superseded_digest_rejected"
        )
    bindings = (*fields, *_EXECUTION_STATUS_FIELDS, *_AUTHORITY_FIREWALL_FIELDS, *runtime_fields)
    issues: list[str] = []
    for label, activation_path, registry_path in bindings:
        registry_path = registry_path_overrides.get(label, registry_path)
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
    is_v0r4 = record.get("project_id") == DSH_STAGE_A_V1R3R2_V0R4_EXECUTION_ID
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
        if is_v0r3 or is_v0r4:
            future_identity = _lookup(
                authorization_document, ("fresh_identity", "future_activation_project_id")
            )
        else:
            future_identity = authorization_document.get("execution_project_id")
        if future_identity != activation.get("project_id"):
            issues.append("fresh authorization execution identity does not match activation")
        if is_v0r3 or is_v0r4:
            expected_content_sha = authorization.get("canonical_content_sha256")
            if not isinstance(expected_content_sha, str):
                issues.append("fresh V0R3 authorization canonical content digest is missing")
            elif hashlib.sha256(authorization_path.read_bytes()).hexdigest() != expected_content_sha:
                issues.append("fresh V0R3 authorization canonical content digest mismatch")
            if is_v0r4:
                canonical_auth_merge = authorization.get("canonical_merge")
                if not isinstance(canonical_auth_merge, str) or not canonical_auth_merge:
                    issues.append("fresh V0R4 authorization canonical merge is missing")
                elif isinstance(expected_content_sha, str):
                    canonical_authorization_bytes = _git_bytes(
                        root,
                        "show",
                        f"{canonical_auth_merge}:{artifact_value}",
                        check=False,
                    )
                    if hashlib.sha256(canonical_authorization_bytes).hexdigest() != expected_content_sha:
                        issues.append("fresh V0R4 authorization canonical merge bytes mismatch")
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
        if is_v0r2r1 or is_v0r3 or is_v0r4:
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
            if is_v0r3 or is_v0r4
            else candidate_commit
        )
        if _lookup(activation, ("canonicalization", "candidate_base_sha")) != expected_candidate_base:
            issues.append("fresh authorization activation candidate base is not authorization-bound")

        contract = authorization_document.get("qualified_launch_contract")
        pinned = authorization_document.get("pinned_dsh_identity")
        if is_v0r3 or is_v0r4:
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
                elif not (is_v0r2r1 or is_v0r4):
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
                if not (is_v0r2r1 or is_v0r3 or is_v0r4):
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
            if is_v0r2r1 or is_v0r3 or is_v0r4:
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
                    False if is_v0r2r1 or is_v0r3 or is_v0r4 else retry_policy.get("automatic_continuation"),
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
