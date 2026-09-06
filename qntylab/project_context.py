"""Git-backed project context and authority map for QntyLab.

This module deliberately owns project/planning interpretation only.  Research
state remains the responsibility of :mod:`qntylab.research_ledger`.

This is the composition root of the project-context layer.  The generic
machinery lives in sibling modules behind a bounded seam:

- :mod:`qntylab.project_context_core` — canonical constants, fail-closed
  errors, Git index snapshots, and JSON/TOML/path primitives.
- :mod:`qntylab.project_context_registry` — generic ADR / projects / ecosystem
  registry validation.
- :mod:`qntylab.project_context_spine` — context-source classification,
  architecture-conflict detection, and read-only context views.
- :mod:`qntylab.project_context_brief` — bounded deterministic brief rendering.
- :mod:`qntylab.project_context_execution_authority` — the bounded domain
  extension projecting activation artifacts into effective execution
  authority; the only module that knows any specific execution domain's
  identities.

Every historical ``qntylab.project_context`` attribute remains resolvable from
this module, and the orchestration functions below resolve their collaborators
through this module's namespace so the long-standing monkeypatch surface is
preserved unchanged.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from qntylab import research_ledger
from qntylab import qnty_context_adapter
from qntylab.project_context_core import (
    ADAPTER_STATUSES,
    ADR_STATUSES,
    ARCHITECTURE_CONFLICT,
    AUTHORITY_DOMAINS,
    AUTHORITY_PRECEDENCE,
    COMPILED_AUTHORITY_KEYS,
    CONFIG_SOURCE_PATH,
    CONTEXT_ACCESS_CLASSES,
    CONTEXT_SPINE_COMPILED,
    CONTEXT_SPINE_PROHIBITIONS,
    CONTEXT_SPINE_VERSION,
    CURRENT_ROADMAP_VIEW,
    DIRECTORY_AUTHORITY_KEYS,
    ECOSYSTEM_CATALOG_SCHEMA_VERSION,
    EXTERNAL_CONTEXT_STATES,
    EXECUTION_CANONICAL_REF,
    GENERATED_VIEW_AUTHORITY_KEYS,
    GENERATED_VIEW_DESTINATIONS,
    GIT_IDENTITY_SOURCE_ID,
    MODULE_INVENTORY_PROVENANCE,
    PRECEDENCE_CLASSES,
    PROJECT_CODE_REFERENCE_COMPLETENESS,
    PROJECT_CODE_REFERENCE_SCOPE,
    PROJECT_ORIENTATION_SCHEMA_VERSION,
    PROJECT_ORIENTATION_SCOPE,
    SCHEMA_VERSION,
    ProjectContextError,
    RepositorySnapshot,
    ValidatedContext,
    _MISSING,
    _as_string,
    _authority_directory,
    _authority_path,
    _canonical_json,
    _git_bytes,
    _git_succeeds,
    _load_json_authority,
    _load_toml,
    _lookup,
    _require_list,
    _run_git,
    _snapshot_for,
)
from qntylab.project_context_brief import (
    BRIEF_COMPLETE_PROJECTION,
    BRIEF_LINE_TRUNCATION_MARKER,
    BRIEF_MAX_BYTES,
    BRIEF_MAX_LINE_BYTES,
    BRIEF_MAX_LINES,
    BRIEF_ORIENTATION_INDEX_ONLY,
    BRIEF_ORIENTATION_ROWS_REDUCED,
    BRIEF_TRUNCATION_MARKER,
    _BriefVariants,
    _bounded_brief,
    _brief_byte_length,
    _brief_external_record,
    _brief_field,
    _brief_line,
    _brief_qnty_lines,
    _brief_sections,
    _orientation_variants,
    _packed_reference_lines,
    brief_text,
)
from qntylab.project_context_spine import (
    _adr_view,
    _architecture_conflicts,
    _classified_paths,
    _context_sources,
    _external_repository_views,
    _generated_view_destination,
    _research_summary,
    _source_classification_conflicts,
    _unbound_compiled_inputs,
    context_text,
)

# Generic registry validation, bound here by explicit assignment (the seam
# consumers below resolve these names through this module's namespace).
from qntylab import project_context_registry as _registry

validate_adr_registry = _registry.validate_adr_registry
validate_projects_registry = _registry.validate_projects_registry
validate_ecosystem_catalog = _registry.validate_ecosystem_catalog
_catalog_repositories = _registry._catalog_repositories

# Generic canonical constants and Git state, bound here by explicit assignment.
from qntylab import project_context_core as _core

PROJECT_STATES = _core.PROJECT_STATES
_git_state = _core._git_state

# The bounded domain extension: the composition root is the only generic-layer
# module allowed to name the execution-authority projection module, and the
# generic machinery below consumes only this one seam function.
from qntylab import project_context_execution_authority as _execution_authority_extension

# Namespace compatibility: bind every name the domain extension declares
# public in its own explicit export contract.  The composition root names no
# domain identity itself — domain identities stay owned by the extension.
for _execution_authority_export in _execution_authority_extension.__all__:
    globals()[_execution_authority_export] = getattr(_execution_authority_extension, _execution_authority_export)


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


def _validated_context(root: Path, *, snapshot: RepositorySnapshot | None = None) -> ValidatedContext:
    root = root.resolve()
    snapshot = _snapshot_for(root, snapshot)
    config, adr_registry, projects_registry = load_context_sources(root, snapshot=snapshot)
    adrs = validate_adr_registry(root, adr_registry, snapshot=snapshot)
    projects = validate_projects_registry(root, projects_registry, snapshot=snapshot)
    return ValidatedContext(root, snapshot, config, adr_registry, projects_registry, adrs, projects)


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
