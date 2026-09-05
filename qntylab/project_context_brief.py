"""Bounded deterministic brief rendering of a compiled Context Spine packet.

Pure rendering: the brief is a function of already-normalized packet data only.
It reads no repository state, performs no I/O, and consults no tokenizer; its
byte and line budgets are deterministic UTF-8 properties of the output itself.
"""

from __future__ import annotations

from typing import Any


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
