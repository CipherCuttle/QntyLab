"""Generic registry validation for the QntyLab project context.

Structural validation of the ADR registry, the projects registry, and the
ecosystem catalog.  These validators accept or reject canonical registry
states; they never interpret any specific project's identity or lifecycle,
and they import only the generic primitives in
:mod:`qntylab.project_context_core`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qntylab import qnty_context_adapter
from qntylab.project_context_core import (
    ADAPTER_STATUSES,
    ADR_STATUSES,
    CONTEXT_ACCESS_CLASSES,
    ECOSYSTEM_CATALOG_SCHEMA_VERSION,
    PROJECT_STATES,
    SCHEMA_VERSION,
    ProjectContextError,
    RepositorySnapshot,
    _as_string,
    _authority_path,
    _require_list,
    _snapshot_for,
)


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
    :func:`qntylab.project_context.compile_context_spine` reports it as
    ``ARCHITECTURE_CONFLICT``.
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
