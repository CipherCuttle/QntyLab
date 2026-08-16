"""Git-backed project context and authority map for QntyLab.

This module deliberately owns project/planning interpretation only.  Research
state remains the responsibility of :mod:`qntylab.research_ledger`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from qntylab import research_ledger


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
CONTEXT_SPINE_VERSION = 1
ECOSYSTEM_CATALOG_SCHEMA_VERSION = 1
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
GIT_IDENTITY_SOURCE_ID = "CANONICAL_GIT_IDENTITY"
CONTEXT_ACCESS_CLASSES = frozenset({"LOCAL_CANONICAL_SOURCES", "NARROW_READ_ONLY_ADAPTER"})
# No implemented-adapter token exists at this schema version, so a catalog
# cannot declare cross-repository observation that no code performs.
ADAPTER_STATUSES = frozenset({"NOT_APPLICABLE", "ADAPTER_NOT_IMPLEMENTED"})
EXTERNAL_CONTEXT_STATES = {"ADAPTER_NOT_IMPLEMENTED": "UNAVAILABLE_WITHOUT_ADAPTER"}
CONTEXT_SPINE_COMPILED = "CONTEXT_SPINE_COMPILED"
ARCHITECTURE_CONFLICT = "ARCHITECTURE_CONFLICT"
CONTEXT_SPINE_PROHIBITIONS = (
    "CONTEXT_SPINE_IS_A_DERIVED_VIEW_AND_NEVER_AN_AUTHORITY_SOURCE",
    "CONTEXT_SPINE_DOES_NOT_MUTATE_ANY_REPOSITORY_OR_SCIENTIFIC_STATE",
    "CONTEXT_SPINE_DOES_NOT_CREATE_OR_TRANSITION_A_PERMITTED_NEXT_ACTION",
    "GIT_IDENTITY_SELECTS_BYTES_AND_GRANTS_NO_SEMANTIC_AUTHORITY",
    "EXTERNAL_REPOSITORY_STATE_IS_NOT_OBSERVED_WITHOUT_AN_IMPLEMENTED_ADAPTER",
    "GENERATED_VIEWS_AND_REMEMBERED_SUMMARIES_CANNOT_OVERRIDE_CANONICAL_GIT",
)


class ProjectContextError(RuntimeError):
    """A canonical Project Context source is malformed, conflicting, or untrusted."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _run_git(root: Path, *args: str, check: bool = True) -> str:
    # An inherited GIT_DIR or GIT_WORK_TREE would silently point these reads at a
    # different repository, so the ambient Git location is dropped and ``-C``
    # remains the only thing that selects which repository is inspected.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if check and completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise ProjectContextError(message)
    return completed.stdout


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


def _authority_path(root: Path, raw_path: Any, *, label: str, expected: str = "file") -> Path:
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
    if _run_git(root, "ls-files", "--error-unmatch", "--", raw, check=False).strip() != raw:
        raise ProjectContextError(f"authority source is not Git-tracked: {raw}")
    return lexical


def _authority_directory(root: Path, raw_path: Any, *, label: str) -> Path:
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
    tracked = _run_git(root, "ls-files", "--", raw, check=False).splitlines()
    if not tracked:
        raise ProjectContextError(f"authority source is not Git-tracked: {raw}")
    return lexical


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProjectContextError(f"{label} must be an array")
    return value


def load_context_sources(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    config_path = _authority_path(root, "qntylab.toml", label="qntylab.toml")
    config = _load_toml(config_path)
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ProjectContextError("unsupported qntylab.toml schema_version")
    _as_string(config.get("repository_id"), "repository_id")
    authority = config.get("authority")
    if not isinstance(authority, dict):
        raise ProjectContextError("qntylab.toml [authority] table is required")
    adr_path = _authority_path(root, authority.get("global_architecture_registry"), label="global_architecture_registry")
    projects_path = _authority_path(root, authority.get("project_registry"), label="project_registry")
    _authority_path(root, authority.get("ecosystem_catalog"), label="ecosystem_catalog")
    _authority_path(root, authority.get("current_roadmap"), label="current_roadmap")
    _authority_directory(root, authority.get("research_ledger_root"), label="research_ledger_root")
    adr_registry = _load_toml(adr_path)
    projects_registry = _load_toml(projects_path)
    return config, adr_registry, projects_registry


def validate_adr_registry(root: Path, registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
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
        _authority_path(root, record.get("path"), label=f"ADR {adr_id} path")
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


def validate_projects_registry(root: Path, registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
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
            _authority_path(root, artifact, label=f"project {project_id} authoritative artifact")
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


def _architecture_conflicts(normalized: dict[str, Any], config: dict[str, Any], adrs: dict[str, dict[str, Any]], global_adr: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    conflicts: list[dict[str, str]] = []
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


def _foundation(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, str]], dict[str, Any] | None]:
    """Load and reconcile the foundation without reading worktree Git state."""
    config, adr_registry, _ = load_context_sources(root)
    catalog_path = _authority_path(root, config["authority"]["ecosystem_catalog"], label="ecosystem_catalog")
    adrs = validate_adr_registry(root, adr_registry)
    normalized = validate_ecosystem_catalog(config, _load_toml(catalog_path))
    global_adr = next(record for record in adrs.values() if record["status"] == "CURRENT_GLOBAL")
    conflicts, north_star = _architecture_conflicts(normalized, config, adrs, global_adr)
    return config, adrs, normalized, global_adr, conflicts, north_star


def compile_context_spine(root: Path) -> dict[str, Any]:
    """Compile the read-only Context Spine foundation packet.

    The packet is derived only from canonical local repository bytes.  It binds
    the Git identity that selected those bytes without treating that identity as
    semantic authority, and it never observes another repository.
    """
    root = root.resolve()
    config, adrs, normalized, global_adr, conflicts, north_star = _foundation(root)
    sources = _context_sources(config)
    git = _git_state(root)
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
                "worktree_status": "CLEAN" if git["clean"] else "DIRTY",
                # An uncommitted worktree compiled bytes the head commit does not
                # contain, so the packet states outright that it is not bound.
                "compiled_bytes_bound_to_head_sha": git["clean"],
            },
            "git_identity_semantics": "GIT_IDENTITY_SELECTS_BYTES_NOT_SEMANTIC_AUTHORITY",
        },
        "architecture": {
            "current_global": _adr_view(global_adr),
            "scientific_north_star": _adr_view(north_star) if north_star else {"adr_id": normalized["architecture_references"]["scientific_north_star"], "authority_scope": None, "path": None, "status": "NOT_ESTABLISHED"},
            "companions": [_adr_view(adrs[adr_id]) for adr_id in sorted(adrs) if adrs[adr_id]["status"] == "CURRENT_GLOBAL_COMPANION"],
        },
        "repository": {key: local[key] for key in repository_keys},
        "external_repositories": [
            {
                **{key: record[key] for key in repository_keys},
                "context_state": EXTERNAL_CONTEXT_STATES.get(record["adapter_status"], "UNAVAILABLE"),
            }
            for _, record in sorted(normalized["repositories"].items())
            if record["repository_id"] != normalized["local_repository_id"]
        ],
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


def context_spine_bytes(root: Path) -> bytes:
    """Canonical serialization of the Context Spine packet, without a newline."""
    return _canonical_json(compile_context_spine(root))


def doctor(root: Path) -> list[str]:
    try:
        config, adr_registry, projects_registry = load_context_sources(root)
        validate_adr_registry(root, adr_registry)
        validate_projects_registry(root, projects_registry)
        packet = compile_context_spine(root)
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


def context_data(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config, adr_registry, projects_registry = load_context_sources(root)
    adrs = validate_adr_registry(root, adr_registry)
    projects = validate_projects_registry(root, projects_registry)
    global_adr = next(record for record in adrs.values() if record["status"] == "CURRENT_GLOBAL")
    global_companions = [
        {key: record[key] for key in ("adr_id", "path", "authority_scope")}
        for record in adrs.values()
        if record["status"] == "CURRENT_GLOBAL_COMPANION"
    ]
    active = next((record for record in projects.values() if record["state"] == "ACTIVE"), None)
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
        "authority_conflicts_or_warnings": doctor(root),
    }


def _roadmap_bytes(root: Path) -> bytes:
    _, _, projects_registry = load_context_sources(root)
    projects = validate_projects_registry(root, projects_registry)
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


def render(root: Path, *, check: bool) -> int:
    config, _, _ = load_context_sources(root)
    # ADR-0007 stops architecture-affecting mutation while canonical sources
    # conflict, so a generated view is never rewritten during a conflict.  The
    # reconciliation alone is enough here, and it leaves the Git index untouched.
    if _foundation(root)[4]:
        print(f"project context error: {ARCHITECTURE_CONFLICT}; roadmap generation is blocked", file=sys.stderr)
        return 1
    expected = _roadmap_bytes(root)
    path = root / config["authority"]["current_roadmap"]
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QntyLab Git-backed project context")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", dest="as_json")
    subparsers = parser.add_subparsers(dest="command")
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--strict", action="store_true")
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--check", action="store_true")
    subparsers.add_parser("spine", help="emit the read-only Context Spine foundation packet as canonical JSON")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "doctor":
            issues = doctor(root)
            if issues:
                for issue in issues:
                    print(f"SOURCE_CONFLICT: {issue}", file=sys.stderr)
                raise SystemExit(1)
            print("project context ok")
            return
        if args.command == "render":
            raise SystemExit(render(root, check=args.check))
        if args.command == "spine":
            packet = compile_context_spine(root)
            sys.stdout.buffer.write(_canonical_json(packet) + b"\n")
            raise SystemExit(0 if packet["packet_status"] == CONTEXT_SPINE_COMPILED else 1)
        data = context_data(root)
        if args.as_json:
            sys.stdout.buffer.write(_canonical_json(data) + b"\n")
        else:
            print(context_text(data))
    except (OSError, ProjectContextError, research_ledger.LedgerError) as exc:
        print(f"project context error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
