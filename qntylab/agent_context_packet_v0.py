"""QNTYLAB_AGENT_CONTEXT_PACKET_V0 -- bounded agent context packet (increment C1).

Umbrella: QNTYLAB_REPOSITORY_ERGONOMICS_AND_MODULARITY_CLEANUP_V0.
Governing decision:
experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/decision.json
(sha256 d2c27eda957ae9f1a650ccc886b391b3a9f5a06f4dbd25a53d1b711355e4e652).

This module renders a DERIVED, NON-AUTHORITATIVE view of canonical repository
state for agent consumption.  It is never an authority source; it never grants,
upgrades, or relabels authority.  All values come from canonical repository
state (qntylab.toml, docs/state/projects.toml, git, and files pointed to by the
selected registry row).  There is no LLM summarization and no semantic
invention.

Schema contract (canonical binding, not local interpretation): the packet
schema is exactly the 19 named fields in ``FIELD_ORDER`` below, as authorized
by the canonical clarification project
QNTYLAB_AGENT_CONTEXT_PACKET_SCHEMA_CLARIFICATION_V0 (integrated via canonical
master; decision artifact
experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/c1_agent_context_packet_v0/schema_clarification.json,
sha256 269bf4ee0d19ccc07df60c1e7eac4fa25fa91e626c3cc5f8f202d0af2afa1f02).
The implementation does not adjudicate the historical forensic 19-vs-20
discrepancy itself: at generation time the packet mechanically re-validates
the canonical clarification row from the canonical validated projects
registry (state and decision state CLOSED_PASS, full decision-artifact
SHA-256 verified before the artifact is trusted) and its resolution record
(``schema_field_count == 19``, ``field_order == FIELD_ORDER``,
``envelope_is_schema_field is false``, ``no_twentieth_field_invented is
true``, ``byte_cap_unchanged == 8192``); any disagreement fails closed.
The envelope is byte-budget accounting, not a field; no twentieth field is
invented under any name.

Field order and per-field VALUE byte caps (UTF-8, fail closed):

    REPOSITORY 40, HEAD 45, WORKTREE 60, PHASE_ID 90, STATE 40,
    OBJECTIVE 500, AUTHORITY_SOURCE 120, ALLOWED_OPERATIONS 250,
    FORBIDDEN_OPERATIONS 250, INPUT_CONTRACTS 300, OUTPUT_CONTRACTS 300,
    LOAD_BEARING_INVARIANTS 700, RELEVANT_CODE 300, RELEVANT_TESTS 200,
    IMMUTABLE_PATHS 250, OPEN_BLOCKERS 200, REVIEW_LIFECYCLE 150,
    NEXT_ACTION 120, VERIFY_COMMAND 150.

The forensic "Est. bytes" figure for OBJECTIVE is 520 with an explicit note
that the value is capped at 500 B; the 20 B difference is envelope overhead,
so the enforced VALUE cap for OBJECTIVE is 500.  The total packet hard cap is
8192 bytes UTF-8 (the ~1000 B "envelope" row of the forensic table is a byte
budget for keys/separators, not a 20th field).

Render format (canonical, deterministic):

* One field per block, fields in FIELD_ORDER order, no blank lines.
* Scalar fields render ``KEY: value``.
* Bounded list fields render the first item on the ``KEY:`` line and each
  subsequent item on its own continuation line prefixed with exactly two
  spaces (``KEY: item0`` / ``  item1`` / ``  item2``).  The two-space
  continuation indent is rendering, not value bytes.
* The canonical VALUE of a list field is its items joined with ``\\n``; the
  canonical VALUE of a scalar field is the string itself.  Per-field caps are
  enforced on VALUE bytes (``len(value.encode("utf-8"))``), excluding the
  ``KEY: `` prefix, continuation indents, and newlines.
* An empty bounded list renders as the explicit deterministic token ``NONE``.
* Individual scalar values and list items must not contain newlines; a value
  that would overflow its cap fails closed.  There is no silent truncation,
  no ``...`` elision, no drop-last-items, and no partial packet on stdout.

Pointer grammar (forensic section 4.3): ``<repo-relative-path>[:<line>][#<sha12>]``

* ``path`` is repository-relative (never absolute, never a host path).
* ``line`` (1-based) is present only when mechanically locatable.
* ``sha12`` is the first 12 hex characters of the SHA-256 of the pointed-to
  file's current bytes (same identity convention as ``decision_artifact_sha256``
  in registry rows, presented as a 12-hex prefix).  Pointers bind to canonical
  file state as actually computed at generation time; nothing is claimed
  "verified" beyond that computation.
* Field-level overflow pointers (OBJECTIVE / NEXT_ACTION) are prefixed with
  ``POINTER `` and point at the selected row's line in the projects registry;
  the packet field name identifies which row field the pointer references.

Phase selection (fail closed, canonical only; no independent interpretation):

* Canonical project-context sources are loaded and the FULL projects registry
  is validated by reusing ``qntylab.project_context`` read-only functions
  (``load_context_sources`` and ``validate_projects_registry``) before any
  selection.  The packet is a derived view of canonically validated project
  state; a malformed registry fails closed even when the requested row itself
  looks structurally plausible (no selective-row bypass).
* ``--phase-id X`` selects the unique validated canonical record with
  ``project_id == X`` (record uniqueness is enforced by canonical
  validation).  A selector only chooses which canonical record to describe;
  it NEVER grants authority.
* Without a selector, default selection reuses the canonical operative-active
  projection (``execution_authority_projection`` -- the same semantics
  ``qntylab.project_context`` renders as ``Active project``), including its
  exclusion of ``ACTIVE_CANDIDATE``/unauthorized branch-local candidate rows.
  Exactly one operative ACTIVE canonical row is required; zero or multiple
  fail closed with a concise error (no bulk row dumps).
* Selection never derives from chat text, environment variables, branch
  names, caller assertions, or model memory.

Field semantics (all canonical, no invention):

* REPOSITORY: ``repository_id`` from qntylab.toml (not the directory name).
* HEAD: full HEAD SHA via ``qntylab.project_context._git_state``.
* WORKTREE: ``CLEAN`` or ``DIRTY`` plus untracked count from
  ``git status --porcelain=v1 --untracked-files=all``; dirty paths are never
  enumerated.
* PHASE_ID / STATE: exact canonical row values; STATE must be a member of
  ``qntylab.project_context.PROJECT_STATES`` and is never relabeled.
* OBJECTIVE: the row's canonical ``next_action`` verbatim when it fits the
  cap, otherwise a bounded ``POINTER `` to the row line.
* AUTHORITY_SOURCE: pointer to the selected row in the canonical projects
  registry (the CURRENT_PLANNING authority source).  The row's
  ``decision_artifact``, when present, is pointed to in INPUT_CONTRACTS.
* ALLOWED_OPERATIONS: at most 5 canonical operations derived only from
  explicit positive authorization facts in the row; ``NONE`` when none.
  Positive authority is never inferred from absence of prohibition.
* FORBIDDEN_OPERATIONS: at most 5 canonical prohibitions derived only from
  explicit row facts (``false`` flags / ``NONE`` authority levels).
* INPUT_CONTRACTS: pointers to canonical artifacts the phase consumes
  (qntylab.toml, the selected registry row, the row's decision artifact).
* OUTPUT_CONTRACTS: pointers to the row's ``authoritative_artifacts``
  (canonical implementation surfaces), in canonical row order.  EVERY
  canonical entry is considered; if the complete pointer list fits the
  300-byte field cap, all pointers are emitted; if it exceeds the cap, the
  packet fails closed.  There is no slicing, no first-N selection, no
  ``...`` elision, and no silent omission.  A canonical authoritative
  artifact that cannot be read or pointer-bound fails closed.
* LOAD_BEARING_INVARIANTS: at most 7 fixed canonical invariant statements
  (constants below, single-sourced from the governing decision, the forensic
  binding document sections 3-4, and qntylab/project_context.py validation
  semantics).
* RELEVANT_CODE: at most 6 mechanical pointers (the packet module itself and
  read-only ``qntylab/project_context.py`` symbols it reuses, anchored at
  their first definition lines computed by scanning the file under root).
  Files that do not exist under the repository root are skipped.
* RELEVANT_TESTS: at most 4 pointers (the C1 test file, then the legacy
  project-context regression test), existence-checked under the root.
* IMMUTABLE_PATHS: bounded pointers to protected surfaces: the row's
  decision artifact and, when the row carries ``forensic_audit_identity``,
  the forensic binding document
  ``docs/forensics/<identity>/agent_context_target.md`` (existence-checked).
* OPEN_BLOCKERS: the row's ``open_blockers`` list when present and
  non-empty, else the explicit token ``NONE``.
* REVIEW_LIFECYCLE: ``<current_stage> (policy: <policy>)`` from the row's
  ``review_lifecycle_current_stage`` / ``review_lifecycle_policy`` when
  present, else ``UNSPECIFIED``.  No historical review prose.
* NEXT_ACTION: the row's canonical ``next_action`` verbatim when it fits the
  cap, otherwise a bounded ``POINTER `` to the row line.  Never rewritten.
* VERIFY_COMMAND: the first entry of the row decision artifact's
  ``verification_commands`` when present, else the V0 phase constant
  ``python -m pytest -q tests/test_qntylab_agent_context_packet_v0.py``.

Determinism and mutation-freedom: identical HEAD + worktree state produce
byte-identical packets across PYTHONHASHSEED, locale, TZ, and cwd.  Packet
generation performs zero filesystem writes, no network access, and only
read-only git commands (``--no-optional-locks`` style, matching
qntylab.project_context).

CLI: ``python -m qntylab.agent_context_packet_v0 [--phase-id ID] [--root PATH]``.
``--root`` is a testability/deviation addition (mirroring
``qntylab.project_context``'s ``--root``); it defaults to the current
directory.  On success the packet text and nothing else goes to stdout with
exit 0.  On any failure stdout stays empty and a single deterministic bounded
error line goes to stderr with a non-zero exit code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from qntylab import project_context

PACKET_SCHEMA_ID = "QNTYLAB_AGENT_CONTEXT_PACKET_V0"

FIELD_ORDER: tuple[str, ...] = (
    "REPOSITORY",
    "HEAD",
    "WORKTREE",
    "PHASE_ID",
    "STATE",
    "OBJECTIVE",
    "AUTHORITY_SOURCE",
    "ALLOWED_OPERATIONS",
    "FORBIDDEN_OPERATIONS",
    "INPUT_CONTRACTS",
    "OUTPUT_CONTRACTS",
    "LOAD_BEARING_INVARIANTS",
    "RELEVANT_CODE",
    "RELEVANT_TESTS",
    "IMMUTABLE_PATHS",
    "OPEN_BLOCKERS",
    "REVIEW_LIFECYCLE",
    "NEXT_ACTION",
    "VERIFY_COMMAND",
)

FIELD_VALUE_CAPS: dict[str, int] = {
    "REPOSITORY": 40,
    "HEAD": 45,
    "WORKTREE": 60,
    "PHASE_ID": 90,
    "STATE": 40,
    "OBJECTIVE": 500,
    "AUTHORITY_SOURCE": 120,
    "ALLOWED_OPERATIONS": 250,
    "FORBIDDEN_OPERATIONS": 250,
    "INPUT_CONTRACTS": 300,
    "OUTPUT_CONTRACTS": 300,
    "LOAD_BEARING_INVARIANTS": 700,
    "RELEVANT_CODE": 300,
    "RELEVANT_TESTS": 200,
    "IMMUTABLE_PATHS": 250,
    "OPEN_BLOCKERS": 200,
    "REVIEW_LIFECYCLE": 150,
    "NEXT_ACTION": 120,
    "VERIFY_COMMAND": 150,
}

TOTAL_HARD_CAP = 8192

NONE_TOKEN = "NONE"
POINTER_PREFIX = "POINTER "
CONTINUATION_INDENT = "  "

# Fixed canonical invariant records (V0 constants; see module docstring).
LOAD_BEARING_INVARIANT_RECORDS: tuple[str, ...] = (
    "fail-closed overflow: non-zero exit, no partial stdout",
    "projects.toml schema_version=1 immutable",
    "at most one ACTIVE project in projects.toml",
    "phase selector never grants authority",
    "no silent truncation of canonical content",
    "packet is a derived non-authoritative view",
    "packet generation performs zero filesystem writes",
)

# V0 phase verification command used when the row's decision artifact does
# not carry a verification_commands entry.
VERIFY_COMMAND_V0 = "python -m pytest -q tests/test_qntylab_agent_context_packet_v0.py"

FORENSIC_BINDING_DOC_TEMPLATE = "docs/forensics/{identity}/agent_context_target.md"

# Canonical clarification project that authorizes the 19-field schema
# contract (P1-A binding; see module docstring).  The row is located in the
# canonical validated projects registry; the implementation never re-adjudicates
# the historical forensic 19-vs-20 discrepancy itself.
CANONICAL_SCHEMA_CLARIFICATION_PROJECT_ID = "QNTYLAB_AGENT_CONTEXT_PACKET_SCHEMA_CLARIFICATION_V0"

MAX_RELEVANT_CODE_ITEMS = 6
MAX_RELEVANT_TESTS_ITEMS = 4

# Read-only qntylab.project_context symbols reused by this packet, in the
# deterministic order their anchors are emitted.
PROJECT_CONTEXT_SYMBOLS: tuple[str, ...] = (
    "PROJECT_STATES",
    "_git_state",
    "load_context_sources",
    "validate_projects_registry",
    "execution_authority_projection",
)


class AgentContextPacketError(Exception):
    """Fail-closed packet construction error (rendered bounded on stderr)."""


# ---------------------------------------------------------------------------
# read-only helpers
# ---------------------------------------------------------------------------


def _git_status(root: Path) -> tuple[bool, int]:
    """Return (clean, untracked_count) from one read-only porcelain call."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    completed = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
        check=False,
        capture_output=True,
        env=environment,
    )
    if completed.returncode:
        message = completed.stderr.decode("utf-8", "replace").strip() or "git status failed"
        raise AgentContextPacketError(message)
    lines = completed.stdout.decode("utf-8", "surrogateescape").splitlines()
    untracked = sum(1 for line in lines if line.startswith("?? "))
    return (not lines, untracked)


def _sha12_of_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:12]


def _read_bytes(root: Path, relative: str) -> bytes:
    candidate = root / relative
    try:
        return candidate.read_bytes()
    except OSError as exc:
        raise AgentContextPacketError(f"cannot read canonical file {relative}: {exc}") from exc


def _file_pointer(root: Path, relative: str, *, line: int | None = None) -> str:
    payload = _read_bytes(root, relative)
    digest = _sha12_of_bytes(payload)
    if line is not None:
        return f"{relative}:{line}#{digest}"
    return f"{relative}#{digest}"


def _definition_line(source: str, name: str) -> int | None:
    pattern = re.compile(rf"^(?:def|class)\s+{re.escape(name)}\b|^{re.escape(name)}\s*=")
    for number, line in enumerate(source.splitlines(), start=1):
        if pattern.match(line):
            return number
    return None


def _row_line(registry_text: str, project_id: str) -> int | None:
    for number, line in enumerate(registry_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("project_id"):
            continue
        if re.fullmatch(rf'project_id\s*=\s*"{re.escape(project_id)}"', stripped) or re.fullmatch(
            rf"project_id\s*=\s*'{re.escape(project_id)}'", stripped
        ):
            return number
    return None


def _bounded_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise AgentContextPacketError(f"{label} must be a non-empty string")
    return value


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------


def _canonical_projects(
    root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], project_context.RepositorySnapshot]:
    """Load and validate canonical project state via qntylab.project_context.

    This is the ONLY interpretation of registry validity on the packet path:
    canonical loaders/validators run first and the FULL registry must pass
    validation before any row can be selected (no selective-row bypass).
    """
    try:
        snapshot = project_context.RepositorySnapshot.acquire(root)
        config, _adr_registry, projects_registry = project_context.load_context_sources(root, snapshot=snapshot)
        projects = project_context.validate_projects_registry(root, projects_registry, snapshot=snapshot)
    except project_context.ProjectContextError as exc:
        raise AgentContextPacketError(f"canonical project context: {exc}") from exc
    return config, projects, snapshot


def _select_row(
    root: Path,
    projects: dict[str, dict[str, Any]],
    phase_id: str | None,
    snapshot: project_context.RepositorySnapshot,
) -> dict[str, Any]:
    """Select one record from the already-validated canonical registry.

    Explicit selection: the unique validated canonical record with
    ``project_id == phase_id``; the selector grants no authority.  Default
    selection reuses the canonical operative-active projection (the same
    semantics qntylab.project_context renders as ``Active project``), so a
    branch-local ``ACTIVE_CANDIDATE`` row is never selected merely because
    its top-level state is ``ACTIVE``.
    """
    if phase_id is not None:
        row = projects.get(phase_id)
        if row is None:
            raise AgentContextPacketError(f"unknown phase: no canonical row with project_id {phase_id!r}")
        return row
    try:
        projection = project_context.execution_authority_projection(root, projects, snapshot=snapshot)
    except project_context.ProjectContextError as exc:
        raise AgentContextPacketError(f"canonical project context: {exc}") from exc
    if projection["issues"]:
        raise AgentContextPacketError("canonical execution authority projection conflict")
    active = projection["active_project"]
    if active is None:
        raise AgentContextPacketError("ambiguous default phase selection: 0 operative ACTIVE canonical rows")
    return active


# ---------------------------------------------------------------------------
# canonical decision-artifact verification (shared, fail closed)
# ---------------------------------------------------------------------------


def _verified_decision_artifact(root: Path, row: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Verify a canonical row's decision artifact binding, fail closed.

    Accepts one canonical validated project row.  When the row carries both
    ``decision_artifact`` and ``decision_artifact_sha256``, the full SHA-256
    of the actual artifact bytes is computed and compared against the row's
    declared 64-hex digest BEFORE the artifact is trusted for any purpose
    (pointer emission, JSON parsing, verification-command consumption, or any
    other packet value derived from it).  Returns ``(relative_path,
    parsed_decision)`` on success, or ``None`` when the row carries no
    decision artifact.  Failures (artifact missing, digest malformed, digest
    mismatch, artifact unreadable, artifact not valid JSON) fail closed; a
    new hash is never recomputed and accepted, modified worktree bytes are
    never treated as canonical, and no command is ever consumed from
    unverified bytes.
    """
    artifact = row.get("decision_artifact")
    if not (isinstance(artifact, str) and artifact):
        return None
    digest = row.get("decision_artifact_sha256")
    payload = _read_bytes(root, artifact)
    if isinstance(digest, str) and digest:
        # digest binding declared: full verification is mandatory before any use
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise AgentContextPacketError(f"decision artifact digest malformed for {artifact}")
        if hashlib.sha256(payload).hexdigest() != digest:
            raise AgentContextPacketError(f"decision artifact digest mismatch for {artifact}")
    try:
        decision = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if isinstance(digest, str) and digest:
            raise AgentContextPacketError(f"decision artifact is not valid JSON: {artifact}") from exc
        return artifact, None  # no digest binding declared: pointer-only legacy path
    if not isinstance(decision, dict):
        if isinstance(digest, str) and digest:
            raise AgentContextPacketError(f"decision artifact is not a JSON object: {artifact}")
        return artifact, None
    return artifact, decision


# ---------------------------------------------------------------------------
# canonical schema contract binding (P1-A)
# ---------------------------------------------------------------------------


def _validate_canonical_schema_contract(root: Path, projects: dict[str, dict[str, Any]]) -> None:
    """Bind FIELD_ORDER to the canonical schema clarification, fail closed.

    Locates the canonical clarification row in the already-validated projects
    registry, requires CLOSED_PASS state and decision state, verifies the
    full SHA-256 of the decision artifact bytes BEFORE trusting the artifact,
    then requires the resolution record to match the frozen 19-field contract
    exactly.  Any disagreement fails closed.  This is a mechanical binding to
    QNTYLAB_AGENT_CONTEXT_PACKET_SCHEMA_CLARIFICATION_V0, not a local
    interpretation of the historical forensic discrepancy.
    """
    row = projects.get(CANONICAL_SCHEMA_CLARIFICATION_PROJECT_ID)
    if row is None:
        raise AgentContextPacketError(
            f"canonical schema clarification row absent: {CANONICAL_SCHEMA_CLARIFICATION_PROJECT_ID}"
        )
    if row.get("state") != "CLOSED_PASS" or row.get("decision_state") != "CLOSED_PASS":
        raise AgentContextPacketError("canonical schema clarification row is not CLOSED_PASS")
    verified = _verified_decision_artifact(root, row)
    if verified is None or not isinstance(verified[1], dict):
        raise AgentContextPacketError("canonical schema clarification decision artifact is unavailable")
    _artifact_relative, decision = verified
    resolution = decision.get("resolution")
    if not isinstance(resolution, dict):
        raise AgentContextPacketError("canonical schema clarification resolution record missing")
    if resolution.get("schema_field_count") != 19:
        raise AgentContextPacketError("canonical schema clarification schema_field_count != 19")
    if resolution.get("field_order") != list(FIELD_ORDER):
        raise AgentContextPacketError("canonical schema clarification field_order != FIELD_ORDER")
    if resolution.get("envelope_is_schema_field") is not False:
        raise AgentContextPacketError("canonical schema clarification envelope_is_schema_field is not false")
    if resolution.get("no_twentieth_field_invented") is not True:
        raise AgentContextPacketError("canonical schema clarification no_twentieth_field_invented is not true")
    if resolution.get("byte_cap_unchanged") != TOTAL_HARD_CAP:
        raise AgentContextPacketError("canonical schema clarification byte_cap_unchanged != 8192")


# ---------------------------------------------------------------------------
# field value construction
# ---------------------------------------------------------------------------


def _text_or_pointer(value: str, cap: int, pointer: str) -> str:
    if len(value.encode("utf-8")) <= cap:
        return value
    bounded_pointer = POINTER_PREFIX + pointer
    if len(bounded_pointer.encode("utf-8")) > cap:
        raise AgentContextPacketError(f"canonical content cannot fit field cap even as pointer ({cap} B)")
    return bounded_pointer


def _pointer_list(items: list[str], cap: int) -> str:
    if not items:
        return NONE_TOKEN
    value = "\n".join(items)
    if len(value.encode("utf-8")) > cap:
        raise AgentContextPacketError(f"pointer list exceeds field cap ({cap} B)")
    return value


def _allowed_operations(row: dict[str, Any]) -> list[str]:
    operations: list[str] = []
    if row.get("implementation_authorized") is True:
        operations.append("implementation within authorized surfaces")
    if row.get("scientific_execution_authorized") is True:
        operations.append("scientific execution within authorized surfaces")
    if row.get("real_data_access_authorized") is True:
        operations.append("real data access within authorized surfaces")
    return operations[:5]


def _forbidden_operations(row: dict[str, Any]) -> list[str]:
    prohibitions: list[str] = []
    if row.get("scientific_execution_authorized") is False:
        prohibitions.append("scientific execution not authorized")
    if row.get("real_data_access_authorized") is False:
        prohibitions.append("real data access not authorized")
    if row.get("trading_authority") == "NONE":
        prohibitions.append("no trading authority")
    if row.get("capital_authority") == "NONE":
        prohibitions.append("no capital authority")
    if row.get("governance_only") is True:
        prohibitions.append("governance-only: no authority beyond the governing decision")
    return prohibitions[:5]


def _verify_command(verified_decision: tuple[str, dict[str, Any] | None] | None) -> str:
    """Derive VERIFY_COMMAND from ALREADY-VERIFIED decision data.

    The decision artifact is never reopened or re-parsed here: verification
    happens exactly once, before any packet value is derived from it.
    """
    if verified_decision is not None:
        _artifact_relative, decision = verified_decision
        if isinstance(decision, dict):
            commands = decision.get("verification_commands")
            if isinstance(commands, list) and commands and isinstance(commands[0], str):
                return commands[0]
    return VERIFY_COMMAND_V0


def _relevant_code(root: Path) -> list[str]:
    items: list[str] = []
    packet_module = "qntylab/agent_context_packet_v0.py"
    if (root / packet_module).exists():
        items.append(_file_pointer(root, packet_module, line=1))
    project_context_module = "qntylab/project_context.py"
    module_path = root / project_context_module
    if module_path.exists():
        source = module_path.read_text(encoding="utf-8", errors="replace")
        for symbol in PROJECT_CONTEXT_SYMBOLS:
            line = _definition_line(source, symbol)
            if line is not None:
                items.append(_file_pointer(root, project_context_module, line=line))
    return items[:MAX_RELEVANT_CODE_ITEMS]


def _relevant_tests(root: Path) -> list[str]:
    items: list[str] = []
    for candidate in (
        "tests/test_qntylab_agent_context_packet_v0.py",
        "tests/test_project_context_v0.py",
    ):
        if (root / candidate).exists():
            items.append(_file_pointer(root, candidate, line=1))
    return items[:MAX_RELEVANT_TESTS_ITEMS]


def build_packet(root: Path, *, phase_id: str | None = None) -> str:
    """Build the deterministic packet text for ``root`` (read-only)."""
    root = Path(root).resolve()
    config, projects, snapshot = _canonical_projects(root)
    repository_id = _bounded_str(config.get("repository_id"), "qntylab.toml repository_id")
    registry_relative = _bounded_str(config["authority"].get("project_registry"), "project_registry")

    # P1-A: bind the 19-field schema contract to the canonical clarification
    # BEFORE any packet value is constructed.
    _validate_canonical_schema_contract(root, projects)

    git_state = project_context._git_state(root)
    clean, untracked_count = _git_status(root)

    row = _select_row(root, projects, phase_id, snapshot)
    project_id = _bounded_str(row.get("project_id"), "project_id")
    state = _bounded_str(row.get("state"), "state")
    if state not in project_context.PROJECT_STATES:
        raise AgentContextPacketError(f"selected row state is not a canonical project state: {state!r}")
    next_action = _bounded_str(row.get("next_action"), "next_action")

    row_line = _row_line((root / registry_relative).read_text(encoding="utf-8"), project_id)
    row_pointer = _file_pointer(root, registry_relative, line=row_line)
    worktree_value = f"{'CLEAN' if clean else 'DIRTY'} untracked={untracked_count}"

    objective = _text_or_pointer(next_action, 500, row_pointer)
    next_action_value = _text_or_pointer(next_action, 120, row_pointer)

    # P1-C: the decision binding is verified exactly ONCE, before the
    # decision pointer may be emitted, the decision JSON may be parsed, or
    # any verification command may be consumed.
    verified_decision = _verified_decision_artifact(root, row)
    decision_pointer: str | None = None
    input_items = [_file_pointer(root, "qntylab.toml"), row_pointer]
    if verified_decision is not None:
        decision_pointer = _file_pointer(root, verified_decision[0])
        input_items.append(decision_pointer)

    # P1-B: EVERY canonical authoritative artifact is considered, in
    # canonical row order.  The complete pointer list is emitted when it fits
    # the field cap; otherwise the packet fails closed.  No slicing, no
    # first-N, no elision, no silent omission; a canonical authoritative
    # artifact that cannot be read or pointer-bound fails closed.
    output_items = [_file_pointer(root, artifact) for artifact in row.get("authoritative_artifacts", [])]

    immutable_items: list[str] = []
    if decision_pointer is not None:
        immutable_items.append(decision_pointer)
    forensic_identity = row.get("forensic_audit_identity")
    if isinstance(forensic_identity, str) and forensic_identity:
        forensic_relative = FORENSIC_BINDING_DOC_TEMPLATE.format(identity=forensic_identity)
        if (root / forensic_relative).exists():
            immutable_items.append(_file_pointer(root, forensic_relative))

    stage = row.get("review_lifecycle_current_stage")
    policy = row.get("review_lifecycle_policy")
    if isinstance(stage, str) and stage:
        review_value = f"{stage} (policy: {policy})" if isinstance(policy, str) and policy else stage
    else:
        review_value = "UNSPECIFIED"

    open_blockers = row.get("open_blockers")
    blockers_value = (
        "\n".join(str(item) for item in open_blockers)
        if isinstance(open_blockers, list) and open_blockers
        else NONE_TOKEN
    )

    values: dict[str, str] = {
        "REPOSITORY": repository_id,
        "HEAD": git_state["head_sha"],
        "WORKTREE": worktree_value,
        "PHASE_ID": project_id,
        "STATE": state,
        "OBJECTIVE": objective,
        "AUTHORITY_SOURCE": row_pointer,
        "ALLOWED_OPERATIONS": "\n".join(allowed) if (allowed := _allowed_operations(row)) else NONE_TOKEN,
        "FORBIDDEN_OPERATIONS": "\n".join(forbidden) if (forbidden := _forbidden_operations(row)) else NONE_TOKEN,
        "INPUT_CONTRACTS": _pointer_list(input_items, FIELD_VALUE_CAPS["INPUT_CONTRACTS"]),
        "OUTPUT_CONTRACTS": _pointer_list(output_items, FIELD_VALUE_CAPS["OUTPUT_CONTRACTS"]),
        "LOAD_BEARING_INVARIANTS": _pointer_list(
            list(LOAD_BEARING_INVARIANT_RECORDS), FIELD_VALUE_CAPS["LOAD_BEARING_INVARIANTS"]
        ),
        "RELEVANT_CODE": _pointer_list(_relevant_code(root), FIELD_VALUE_CAPS["RELEVANT_CODE"]),
        "RELEVANT_TESTS": _pointer_list(_relevant_tests(root), FIELD_VALUE_CAPS["RELEVANT_TESTS"]),
        "IMMUTABLE_PATHS": _pointer_list(immutable_items, FIELD_VALUE_CAPS["IMMUTABLE_PATHS"]),
        "OPEN_BLOCKERS": blockers_value,
        "REVIEW_LIFECYCLE": review_value,
        "NEXT_ACTION": next_action_value,
        "VERIFY_COMMAND": _verify_command(verified_decision),
    }
    return render_packet(values)


# ---------------------------------------------------------------------------
# rendering + validation (fail closed)
# ---------------------------------------------------------------------------


def render_packet(values: dict[str, str]) -> str:
    """Render and validate the packet; raise on any contract violation."""
    missing = [field for field in FIELD_ORDER if field not in values]
    if missing:
        raise AgentContextPacketError(f"packet missing fields: {', '.join(missing)}")
    unknown = [key for key in values if key not in FIELD_ORDER]
    if unknown:
        raise AgentContextPacketError(f"packet has unknown fields: {', '.join(sorted(unknown))}")
    for field in FIELD_ORDER:
        value = values[field]
        if not isinstance(value, str):
            raise AgentContextPacketError(f"field {field} value must be a string")
        if "\n" in value and field not in _MULTILINE_FIELDS:
            raise AgentContextPacketError(f"field {field} must be a single line")
        size = len(value.encode("utf-8"))
        cap = FIELD_VALUE_CAPS[field]
        if size > cap:
            raise AgentContextPacketError(f"field {field} value exceeds cap: {size} > {cap} B")
    packet = "".join(_render_field(field, values[field]) for field in FIELD_ORDER)
    _validate_rendered(packet)
    total = len(packet.encode("utf-8"))
    if total > TOTAL_HARD_CAP:
        raise AgentContextPacketError(f"packet exceeds total hard cap: {total} > {TOTAL_HARD_CAP} B")
    return packet


def _render_field(field: str, value: str) -> str:
    lines = value.split("\n")
    rendered = [f"{field}: {lines[0]}"]
    rendered.extend(CONTINUATION_INDENT + item for item in lines[1:])
    return "\n".join(rendered) + "\n"


_MULTILINE_FIELDS = frozenset(
    {
        "ALLOWED_OPERATIONS",
        "FORBIDDEN_OPERATIONS",
        "INPUT_CONTRACTS",
        "OUTPUT_CONTRACTS",
        "LOAD_BEARING_INVARIANTS",
        "RELEVANT_CODE",
        "RELEVANT_TESTS",
        "IMMUTABLE_PATHS",
        "OPEN_BLOCKERS",
    }
)


def _validate_rendered(packet: str) -> None:
    """Re-parse rendered output against the ordered registry (defense in depth)."""
    seen: list[str] = []
    for line in packet.splitlines():
        if line.startswith(CONTINUATION_INDENT):
            if not seen:
                raise AgentContextPacketError("rendered packet starts with a continuation line")
            continue
        key, separator, _ = line.partition(": ")
        if not separator or key != line[: len(key)] or " " in key or key != key.strip():
            raise AgentContextPacketError(f"rendered packet has malformed field line: {line[:60]!r}")
        seen.append(key)
    if seen != list(FIELD_ORDER):
        raise AgentContextPacketError(
            "rendered packet field order mismatch: unknown, missing, duplicate, or reordered fields"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qntylab.agent_context_packet_v0",
        description="Render the QNTYLAB_AGENT_CONTEXT_PACKET_V0 derived context packet (read-only).",
    )
    parser.add_argument("--phase-id", default=None, help="canonical project_id of the phase to describe")
    parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    args = parser.parse_args(argv)
    try:
        packet = build_packet(Path(args.root), phase_id=args.phase_id)
    except AgentContextPacketError as exc:
        message = str(exc)
        if len(message.encode("utf-8")) > 300:
            message = message[:300]
        print(f"agent_context_packet_v0: error: {message}", file=sys.stderr)
        return 1
    except Exception as exc:  # fail closed on unexpected errors too
        print(f"agent_context_packet_v0: error: unexpected failure: {type(exc).__name__}", file=sys.stderr)
        return 1
    sys.stdout.write(packet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())