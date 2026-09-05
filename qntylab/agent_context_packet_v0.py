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

Schema discrepancy record (governing contract): the forensic document
docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/agent_context_target.md
claims a "20-field schema" in its section 4.1, but its section 3 field table
enumerates exactly 19 fields (the 20th table row is the ~1000 B ``envelope``
row, which is a byte budget, not a field).  The governing contract for V0 is
the 19 enumerated field names, in the exact order given by ``FIELD_ORDER``
below.  This discrepancy must also be recorded in the C1 manifest entry in a
later phase.

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

Phase selection (fail closed, canonical only):

* ``--phase-id X`` selects the unique row with ``project_id == X`` in the
  canonical projects registry (parsed read-only with tomllib).  A selector
  only chooses which canonical record to describe; it NEVER grants authority.
* Without a selector, automatic selection requires exactly one ACTIVE row.
  Zero or multiple ACTIVE rows fail closed with a concise ambiguity error
  (no bulk row dumps).
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
  (canonical implementation surfaces), in row order, at most 4 items.
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
import tomllib
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

MAX_OUTPUT_CONTRACT_ITEMS = 4
MAX_RELEVANT_CODE_ITEMS = 6
MAX_RELEVANT_TESTS_ITEMS = 4

# Read-only qntylab.project_context symbols reused by this packet, in the
# deterministic order their anchors are emitted.
PROJECT_CONTEXT_SYMBOLS: tuple[str, ...] = (
    "PROJECT_STATES",
    "RepositorySnapshot",
    "_load_toml",
    "_git_state",
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


def _select_row(root: Path, registry_relative: str, phase_id: str | None) -> tuple[dict[str, Any], int | None]:
    registry_path = root / registry_relative
    try:
        with registry_path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AgentContextPacketError(f"cannot read projects registry: {exc}") from exc
    rows = data.get("project")
    if not isinstance(rows, list):
        raise AgentContextPacketError("projects registry missing 'project' array-of-tables")
    if phase_id is not None:
        matches = [row for row in rows if isinstance(row, dict) and row.get("project_id") == phase_id]
        if not matches:
            raise AgentContextPacketError(f"unknown phase: no canonical row with project_id {phase_id!r}")
        if len(matches) > 1:
            raise AgentContextPacketError("ambiguous phase selection: duplicate project_id rows")
        row = matches[0]
    else:
        candidates = [row for row in rows if isinstance(row, dict) and row.get("state") == "ACTIVE"]
        if len(candidates) == 0:
            raise AgentContextPacketError("ambiguous default phase selection: 0 ACTIVE canonical rows")
        if len(candidates) > 1:
            raise AgentContextPacketError("ambiguous default phase selection: multiple ACTIVE canonical rows")
        row = candidates[0]
    line = _row_line(registry_path.read_text(encoding="utf-8"), _bounded_str(row.get("project_id"), "project_id"))
    return row, line


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


def _verify_command(root: Path, row: dict[str, Any]) -> str:
    artifact = row.get("decision_artifact")
    if isinstance(artifact, str) and artifact:
        try:
            with (root / artifact).open("rb") as stream:
                decision = json.load(stream)
        except (OSError, json.JSONDecodeError):
            decision = None
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
    config = project_context._load_toml(root / "qntylab.toml")
    repository_id = _bounded_str(config.get("repository_id"), "qntylab.toml repository_id")
    authority = config.get("authority")
    if not isinstance(authority, dict):
        raise AgentContextPacketError("qntylab.toml missing [authority] table")
    registry_relative = _bounded_str(authority.get("project_registry"), "project_registry")

    git_state = project_context._git_state(root)
    clean, untracked_count = _git_status(root)

    row, row_line = _select_row(root, registry_relative, phase_id)
    project_id = _bounded_str(row.get("project_id"), "project_id")
    state = _bounded_str(row.get("state"), "state")
    if state not in project_context.PROJECT_STATES:
        raise AgentContextPacketError(f"selected row state is not a canonical project state: {state!r}")
    next_action = _bounded_str(row.get("next_action"), "next_action")

    row_pointer = _file_pointer(root, registry_relative, line=row_line)
    worktree_value = f"{'CLEAN' if clean else 'DIRTY'} untracked={untracked_count}"

    objective = _text_or_pointer(next_action, 500, row_pointer)
    next_action_value = _text_or_pointer(next_action, 120, row_pointer)

    input_items = [_file_pointer(root, "qntylab.toml"), row_pointer]
    decision_artifact = row.get("decision_artifact")
    decision_pointer: str | None = None
    if isinstance(decision_artifact, str) and decision_artifact and (root / decision_artifact).exists():
        decision_pointer = _file_pointer(root, decision_artifact)
        input_items.append(decision_pointer)

    output_items = [
        _file_pointer(root, artifact)
        for artifact in row.get("authoritative_artifacts", [])
        if isinstance(artifact, str) and artifact and (root / artifact).exists()
    ][:MAX_OUTPUT_CONTRACT_ITEMS]

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
        "VERIFY_COMMAND": _verify_command(root, row),
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