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
CONTEXT_SPINE_VERSION = 2
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


class ProjectContextError(RuntimeError):
    """A canonical Project Context source is malformed, conflicting, or untrusted."""


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
    config_path = _authority_path(root, CONFIG_SOURCE_PATH, label=CONFIG_SOURCE_PATH)
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


def _foundation(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, str]], dict[str, Any] | None]:
    """Load and reconcile the foundation without reading worktree Git state."""
    config, adr_registry, _ = load_context_sources(root)
    catalog_path = _authority_path(root, config["authority"]["ecosystem_catalog"], label="ecosystem_catalog")
    adrs = validate_adr_registry(root, adr_registry)
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


def compile_context_spine(root: Path, *, external_roots: dict[str, Path] | None = None) -> dict[str, Any]:
    """Compile the read-only Context Spine foundation packet.

    The local foundation is derived from canonical local repository bytes. Any
    external observation is opt-in through a named read-only adapter root and
    remains bounded by that adapter's contract.
    """
    root = root.resolve()
    config, adrs, normalized, global_adr, conflicts, north_star = _foundation(root)
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


def context_spine_bytes(root: Path, *, external_roots: dict[str, Path] | None = None) -> bytes:
    """Canonical serialization of the Context Spine packet, without a newline."""
    return _canonical_json(compile_context_spine(root, external_roots=external_roots))


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


def _generated_view_destination(root: Path, config: dict[str, Any], view: str) -> Path:
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
    return _authority_path(root, supported, label=key)


def render(root: Path, *, check: bool) -> int:
    config, _, _ = load_context_sources(root)
    # Resolving the destination is the first thing that happens and the only
    # thing that decides where bytes may land, so an unauthorized target is
    # rejected before a single repository byte can be produced or written.
    path = _generated_view_destination(root, config, CURRENT_ROADMAP_VIEW)
    # ADR-0007 stops architecture-affecting mutation while canonical sources
    # conflict, so a generated view is never rewritten during a conflict.  The
    # reconciliation alone is enough here, and it leaves the Git index untouched.
    if _foundation(root)[4]:
        print(f"project context error: {ARCHITECTURE_CONFLICT}; roadmap generation is blocked", file=sys.stderr)
        return 1
    expected = _roadmap_bytes(root)
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


def _brief_sections(packet: dict[str, Any]) -> list[list[str]]:
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

    return [
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
        [
            "## Authority boundaries",
            "",
            "- Git identity selects bytes, not semantic authority.",
            "- Handoff is not Qnty acceptance.",
            "- NEXT_ACTION authority is not established unless a canonical source says otherwise; no NEXT_ACTION field is emitted.",
            "- No science, runtime, live, trading, or capital authority is inferred.",
        ],
        [
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
        ],
    ]


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


def _bounded_brief(sections: list[list[str]]) -> str:
    lines: list[str] = []
    truncated = False
    for section in sections:
        candidate = lines + [_brief_line(line) for line in section]
        if len(candidate) > BRIEF_MAX_LINES or _brief_byte_length(candidate) > BRIEF_MAX_BYTES:
            truncated = True
            break
        lines = candidate
    if truncated:
        while lines and (
            len(lines) + 1 > BRIEF_MAX_LINES
            or _brief_byte_length(lines + [BRIEF_TRUNCATION_MARKER]) > BRIEF_MAX_BYTES
        ):
            lines.pop()
        lines.append(BRIEF_TRUNCATION_MARKER)
    text = "\n".join(lines)
    encoded = text.encode("utf-8")
    if len(encoded) > BRIEF_MAX_BYTES:
        # Unconditional backstop: the rendered brief never exceeds the ceiling,
        # whatever a future section composition does.
        keep = BRIEF_MAX_BYTES - len(BRIEF_TRUNCATION_MARKER) - 1
        text = encoded[:keep].decode("utf-8", "ignore") + "\n" + BRIEF_TRUNCATION_MARKER
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
            packet = compile_context_spine(root, external_roots=_parse_external_roots(args.external_roots))
            sys.stdout.buffer.write(_canonical_json(packet) + b"\n")
            raise SystemExit(0 if packet["packet_status"] == CONTEXT_SPINE_COMPILED else 1)
        if args.command == "brief":
            packet = compile_context_spine(root, external_roots=_parse_external_roots(args.external_roots))
            print(brief_text(packet))
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
