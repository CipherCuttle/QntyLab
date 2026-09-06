"""Generic primitives for the Git-backed QntyLab project context.

This module holds only repository-agnostic machinery: canonical constants,
fail-closed errors, Git index snapshots, and the JSON/TOML/path guards shared
by every project-context layer.  It knows nothing about any specific project,
execution domain, or extension, and it imports nothing from the other
``qntylab.project_context_*`` modules.
"""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


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

_MISSING = object()


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


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProjectContextError(f"{label} must be an array")
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
