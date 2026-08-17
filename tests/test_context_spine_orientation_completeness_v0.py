"""OC-B orientation completeness contract tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
POSITIVE_PROJECT = "QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_SOURCE_INPUT_AND_OPEN_EXECUTION_READINESS_R1"
POSITIVE_REFERENCE = "qntylab/qnty_edge_order_flow_v0_readiness.py"


def _packet() -> dict:
    return project_context.compile_context_spine(ROOT)


def test_orientation_packet_is_explicitly_partial_and_evidence_only() -> None:
    orientation = _packet()["project_orientation"]
    assert orientation["schema_version"] == "project-orientation-v0"
    assert orientation["project_orientation_scope"] == "PROJECT_CODE_REFERENCE_PROJECTION"
    assert orientation["project_code_reference_scope"] == "AUTHORITATIVE_ARTIFACTS_ONLY_FILTERED_TO_QNTYLAB_PYTHON"
    assert orientation["project_code_reference_completeness"] == "PARTIAL_PROJECTION_NOT_REPOSITORY_COMPLETENESS"
    assert orientation["module_inventory_provenance"] == "GIT_INDEX_TRACKED_QNTYLAB_PYTHON"
    assert all(set(row) == {"project_id", "project_state", "project_display_name", "project_code_references"} for row in orientation["rows"])
    assert all("next_action" not in row and "implementation_authorized" not in row for row in orientation["rows"])


def test_orientation_rows_are_sorted_and_reference_only_canonical_artifacts() -> None:
    orientation = _packet()["project_orientation"]
    rows = orientation["rows"]
    assert [row["project_id"] for row in rows] == sorted(row["project_id"] for row in rows)
    for row in rows:
        assert row["project_code_references"] == sorted(set(row["project_code_references"]))
        assert all(path.startswith("qntylab/") and path.endswith(".py") for path in row["project_code_references"])


def test_order_flow_positive_control_is_discoverable_without_production_hardcoding() -> None:
    orientation = _packet()["project_orientation"]
    row = next(row for row in orientation["rows"] if row["project_id"] == POSITIVE_PROJECT)
    assert POSITIVE_REFERENCE in row["project_code_references"]
    assert POSITIVE_PROJECT not in project_context._project_orientation.__doc__
    assert POSITIVE_REFERENCE not in project_context._project_orientation.__doc__


def test_brief_positive_control_and_truncation_pointer_are_machine_detectable() -> None:
    text = project_context.brief_text(_packet())
    assert POSITIVE_REFERENCE in text
    assert project_context.BRIEF_TRUNCATION_MARKER in text
    assert project_context.BRIEF_COMPLETE_PROJECTION in text


def test_module_inventory_is_git_index_tracked_qntylab_python() -> None:
    orientation = _packet()["project_orientation"]
    expected = sorted(
        path
        for path in subprocess.run(
            ["git", "ls-files", "--cached", "--", "qntylab/"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        if path.startswith("qntylab/") and path.endswith(".py")
    )
    assert orientation["module_inventory"] == expected
    assert "qntylab/project_context.py" in orientation["module_inventory"]


def test_orientation_serialization_is_deterministic_and_has_no_host_leakage() -> None:
    first = project_context.context_spine_bytes(ROOT)
    second = project_context.context_spine_bytes(ROOT)
    assert first == second
    decoded = json.loads(first)
    assert decoded["context_spine_version"] == 3
    assert str(ROOT) not in first.decode()


def test_truncated_brief_is_explicit_and_points_to_complete_spine() -> None:
    text = project_context._bounded_brief([["x" * 240] * project_context.BRIEF_MAX_LINES, ["unreachable"]])
    assert project_context.BRIEF_TRUNCATION_MARKER in text
    assert project_context.BRIEF_COMPLETE_PROJECTION in text
    assert len(text.encode("utf-8")) <= project_context.BRIEF_MAX_BYTES
    assert len(text.splitlines()) <= project_context.BRIEF_MAX_LINES
    assert max(len(line.encode("utf-8")) for line in text.splitlines()) <= project_context.BRIEF_MAX_LINE_BYTES
