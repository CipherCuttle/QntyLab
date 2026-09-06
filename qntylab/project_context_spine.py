"""Context-source classification and read-only context views.

Generic machinery that classifies declared authority sources onto the ADR-0007
precedence ladder, detects architecture conflicts between canonical sources,
compares compiled inputs against HEAD, renders external-repository views, and
summarizes research-ledger state.  This module never interprets a specific
project's identity or lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qntylab import qnty_context_adapter
from qntylab import research_ledger
from qntylab.project_context_core import (
    ARCHITECTURE_CONFLICT,
    AUTHORITY_PRECEDENCE,
    CONFIG_SOURCE_PATH,
    CURRENT_ROADMAP_VIEW,
    DIRECTORY_AUTHORITY_KEYS,
    EXTERNAL_CONTEXT_STATES,
    GENERATED_VIEW_AUTHORITY_KEYS,
    GENERATED_VIEW_DESTINATIONS,
    GIT_IDENTITY_SOURCE_ID,
    PRECEDENCE_CLASSES,
    ProjectContextError,
    RepositorySnapshot,
    ValidatedContext,
    _as_string,
    _authority_path,
    _git_bytes,
    _git_state,
    _require_list,
    _run_git,
    _snapshot_for,
)


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
