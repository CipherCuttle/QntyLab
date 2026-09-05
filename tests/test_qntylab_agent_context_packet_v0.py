"""Contract tests for QNTYLAB_AGENT_CONTEXT_PACKET_V0 (increment C1).

Covers the 19-field packet schema, fail-closed byte caps, canonical-only phase
selection, pointer binding, determinism, mutation-freedom, non-bulk-emission
guarantees, and legacy renderer stability, plus positive happy-path controls.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from qntylab import agent_context_packet_v0 as packet_module
from qntylab import project_context
from qntylab.agent_context_packet_v0 import (
    FIELD_ORDER,
    AgentContextPacketError,
    render_packet,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
UMBRELLA_PROJECT_ID = "QNTYLAB_REPOSITORY_ERGONOMICS_AND_MODULARITY_CLEANUP_V0"

QNTYLAB_TOML = """schema_version = 1
repository_id = "FIXTURE_REPO"

[authority]
project_registry = "docs/state/projects.toml"
current_roadmap = "docs/CURRENT_ROADMAP.md"
research_ledger_root = "experiments/research"
global_architecture_registry = "docs/ADR/registry.toml"
ecosystem_catalog = "docs/state/ecosystem_catalog.toml"
"""

# Minimal canonical authority sources required by
# qntylab.project_context.load_context_sources on the packet path.
ADR_REGISTRY_TOML = """schema_version = 1

[[adr]]
adr_id = "ADR-0001"
status = "CURRENT_GLOBAL"
authority_scope = "GLOBAL_ARCHITECTURE"
path = "docs/ADR/0001-architecture.md"

[[supersession]]
"""

ECOSYSTEM_CATALOG_TOML = """schema_version = 1

[[repository]]
repository_id = "FIXTURE_REPO"
durable_role = "IMPLEMENTATION"
default_branch = "master"
"""


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
    )


def _commit(root: Path) -> None:
    _git(root, "add", ".")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "fixture")


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(f'"{item}"' for item in value) + "]"
    return f'"{value}"'


def _toml_row(row: dict[str, Any]) -> str:
    lines = ["[[project]]"]
    for key, value in row.items():
        lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def _row(project_id: str, *, state: str = "ACTIVE", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "project_id": project_id,
        "state": state,
        "authority_level": "BOUNDED_IMPLEMENTATION",
        "authoritative_artifacts": ["artifact.md"],
        "next_action": "Implement the authorized bounded work.",
        "implementation_authorized": state == "ACTIVE",
    }
    row.update(overrides)
    return row


def _write(root: Path, relative: str, payload: bytes | str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    target.write_bytes(payload)


# Activation artifact of a prior (non-DSH) candidate schema: canonical
# qntylab.project_context.execution_authority_projection treats an ACTIVE row
# carrying such an artifact as a branch-local candidate that is observable but
# NOT operative (the same ACTIVE_CANDIDATE exclusion Project Context applies).
CANDIDATE_ACTIVATION_JSON = '{"schema_version": "prior-candidate-activation-legacy-v0"}\n'


def _candidate_row(project_id: str, **overrides: Any) -> dict[str, Any]:
    """Registry row mirroring canonical ACTIVE_CANDIDATE semantics: top-level
    state ACTIVE, but gated out of the operative-active set by its activation
    artifact."""
    return _row(
        project_id,
        candidate_state="ACTIVE_CANDIDATE",
        authoritative_artifacts=["artifact.md", "activation.json"],
        **overrides,
    )


def _fixture_root(
    tmp_path: Path,
    rows: list[dict[str, Any]],
    *,
    decision: dict[str, Any] | None = None,
    extra_files: dict[str, str] | None = None,
    commit: bool = True,
) -> Path:
    root = tmp_path / "repo"
    _write(root, "qntylab.toml", QNTYLAB_TOML)
    _write(root, "artifact.md", "tracked artifact\n")
    _write(
        root,
        "docs/state/projects.toml",
        "schema_version = 1\n\n" + "".join(_toml_row(row) for row in rows),
    )
    _write(root, "docs/ADR/registry.toml", ADR_REGISTRY_TOML)
    _write(root, "docs/ADR/0001-architecture.md", "# canonical architecture\n")
    _write(root, "docs/state/ecosystem_catalog.toml", ECOSYSTEM_CATALOG_TOML)
    if not (extra_files or {}).get("docs/CURRENT_ROADMAP.md"):
        _write(root, "docs/CURRENT_ROADMAP.md", "# canonical roadmap\n")
    _write(root, "experiments/research/.gitkeep", "")
    if decision is not None:
        import json

        _write(root, rows[0].get("decision_artifact", "decision.json"), json.dumps(decision))
    for relative, content in (extra_files or {}).items():
        _write(root, relative, content)
    if commit:
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        _commit(root)
    return root


def _run_cli(root: Path, *extra_args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    environment = dict(os.environ)
    if env_extra:
        environment.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "qntylab.agent_context_packet_v0", "--root", str(root), *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        env=environment,
    )


def _run_cli_ok(root: Path, *extra_args: str, env_extra: dict[str, str] | None = None) -> str:
    completed = _run_cli(root, *extra_args, env_extra=env_extra)
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert completed.stderr == b""
    return completed.stdout.decode("utf-8")


def _parse_packet(packet: str) -> tuple[list[str], dict[str, list[str]]]:
    """Parse rendered packet back into ordered fields and item lists."""
    order: list[str] = []
    items: dict[str, list[str]] = {}
    current: str | None = None
    for line in packet.splitlines():
        if line.startswith("  "):
            assert current is not None
            items[current].append(line[2:])
            continue
        key, separator, value = line.partition(": ")
        assert separator, line
        current = key
        items[key] = [value]
        order.append(key)
    return order, items


def _all_field_values(**overrides: str) -> dict[str, str]:
    values = {field: "v" for field in FIELD_ORDER}
    values.update(overrides)
    return values


def _snapshot_tree(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts:
            continue
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def _git_status_output(root: Path) -> str:
    completed = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
        check=True,
        capture_output=True,
    )
    return completed.stdout.decode("utf-8")


# ---------------------------------------------------------------------------
# schema / render format
# ---------------------------------------------------------------------------


def test_PACKET_SCHEMA_EXACT(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path, [_row("PHASE_ONE")])
    packet = _run_cli_ok(root)
    order, items = _parse_packet(packet)
    assert order == list(FIELD_ORDER)
    assert len(order) == 19
    assert items["REPOSITORY"] == ["FIXTURE_REPO"]
    assert items["STATE"] == ["ACTIVE"]
    assert items["PHASE_ID"] == ["PHASE_ONE"]


def test_PACKET_FIELD_ORDER_EXACT(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path, [_row("PHASE_ONE")])
    packet = _run_cli_ok(root)
    order, _ = _parse_packet(packet)
    assert order == list(packet_module.FIELD_ORDER)
    assert order.index("REPOSITORY") < order.index("HEAD") < order.index("WORKTREE")
    assert order[-1] == "VERIFY_COMMAND"


def test_PACKET_UNKNOWN_FIELD_REJECTED() -> None:
    values = _all_field_values()
    values["EXTRA_FIELD"] = "x"
    with pytest.raises(AgentContextPacketError, match="unknown fields"):
        render_packet(values)


def test_PACKET_MISSING_FIELD_REJECTED() -> None:
    values = _all_field_values()
    del values["OBJECTIVE"]
    with pytest.raises(AgentContextPacketError, match="missing fields"):
        render_packet(values)


def test_PACKET_OVER_8192_FAILS_CLOSED(monkeypatch: pytest.MonkeyPatch) -> None:
    # The per-field caps keep the total under 8192 by construction, so the
    # total-cap code path is exercised by relaxing per-field caps here; the
    # 8192 B total hard cap must still fail closed on its own.
    huge_caps = {field: 10**9 for field in FIELD_ORDER}
    monkeypatch.setattr(packet_module, "FIELD_VALUE_CAPS", huge_caps)
    values = _all_field_values(OBJECTIVE="x" * 9000)
    with pytest.raises(AgentContextPacketError, match="total hard cap"):
        render_packet(values)


def test_PACKET_OVERFLOW_EMITS_NO_PARTIAL_STDOUT(tmp_path: Path) -> None:
    long_id = "P" * 100  # PHASE_ID cap is 90
    root = _fixture_root(tmp_path, [_row(long_id)])
    completed = _run_cli(root, "--phase-id", long_id)
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr != b""


def test_PER_FIELD_OVERFLOW_FAILS_CLOSED(tmp_path: Path) -> None:
    long_id = "P" * 100
    root = _fixture_root(tmp_path, [_row(long_id)])
    completed = _run_cli(root, "--phase-id", long_id)
    assert completed.returncode != 0
    stderr = completed.stderr.decode("utf-8", "replace")
    assert "PHASE_ID" in stderr and "cap" in stderr
    assert len(stderr) < 400
    with pytest.raises(AgentContextPacketError, match="OBJECTIVE.*cap"):
        render_packet(_all_field_values(OBJECTIVE="x" * 600))


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_IDENTICAL_INPUTS_BYTE_IDENTICAL(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path, [_row("PHASE_ONE")])
    first = _run_cli_ok(root)
    second = _run_cli_ok(root)
    assert first == second


def test_NO_TIMESTAMP_OR_RANDOMNESS(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path, [_row("PHASE_ONE")])
    baseline = _run_cli_ok(root)
    for env_extra in (
        {"PYTHONHASHSEED": "0"},
        {"PYTHONHASHSEED": "12345"},
        {"TZ": "Asia/Tokyo"},
        {"LC_ALL": "C"},
        {"LC_ALL": "C", "TZ": "UTC", "PYTHONHASHSEED": "7"},
    ):
        assert _run_cli_ok(root, env_extra=env_extra) == baseline
    assert not any(re.search(pattern, baseline) for pattern in (r"\d{4}-\d{2}-\d{2}", r"[0-9a-f]{8}-[0-9a-f]{4}"))
    hex_runs = re.findall(r"[0-9a-f]{16,}", baseline)
    assert hex_runs and all(len(run) == 40 for run in hex_runs)  # only the full HEAD SHA


# ---------------------------------------------------------------------------
# phase selection
# ---------------------------------------------------------------------------


def test_EXPLICIT_PHASE_SELECTION_CANONICAL_ONLY(tmp_path: Path) -> None:
    rows = [
        _row("PHASE_ACTIVE"),
        _row("PHASE_CLOSED_PASS", state="CLOSED_PASS", implementation_authorized=False),
    ]
    root = _fixture_root(tmp_path, rows)
    packet = _run_cli_ok(root, "--phase-id", "PHASE_CLOSED_PASS")
    _, items = _parse_packet(packet)
    assert items["PHASE_ID"] == ["PHASE_CLOSED_PASS"]
    assert items["STATE"] == ["CLOSED_PASS"]  # verbatim, never relabeled


def test_UNKNOWN_PHASE_REJECTED(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path, [_row("PHASE_ONE")])
    completed = _run_cli(root, "--phase-id", "NO_SUCH_PHASE")
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert b"unknown phase" in completed.stderr


def test_AMBIGUOUS_DEFAULT_PHASE_SELECTION_REJECTED(tmp_path: Path) -> None:
    zero_active = _fixture_root(tmp_path, [_row("CLOSED_A", state="CLOSED_PASS", implementation_authorized=False)])
    completed = _run_cli(zero_active)
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert b"0 operative ACTIVE" in completed.stderr

    tmp_path_two = tmp_path / "two"
    tmp_path_two.mkdir()
    two_active = _fixture_root(
        tmp_path_two,
        [_row("ACTIVE_A"), _row("ACTIVE_B")],
    )
    completed = _run_cli(two_active)
    assert completed.returncode != 0
    assert completed.stdout == b""
    stderr = completed.stderr.decode("utf-8", "replace")
    # canonical registry validation forbids more than one ACTIVE row before
    # any packet-owned selection can run
    assert "at most one ACTIVE project is permitted" in stderr
    assert "ACTIVE_A" not in stderr and "ACTIVE_B" not in stderr  # no bulk row dumps
    assert len(stderr) < 400


def test_PHASE_SELECTOR_DOES_NOT_GRANT_AUTHORITY(tmp_path: Path) -> None:
    rows = [
        _row(
            "BLOCKED_PHASE",
            state="CLOSED_BLOCKED",
            implementation_authorized=False,
            scientific_execution_authorized=False,
            trading_authority="NONE",
        ),
        _row("ACTIVE_PHASE"),
    ]
    root = _fixture_root(tmp_path, rows)
    packet = _run_cli_ok(root, "--phase-id", "BLOCKED_PHASE")
    _, items = _parse_packet(packet)
    assert items["STATE"] == ["CLOSED_BLOCKED"]
    assert items["ALLOWED_OPERATIONS"] == ["NONE"]
    assert items["FORBIDDEN_OPERATIONS"] == [
        "scientific execution not authorized",
        "no trading authority",
    ]
    # positive control: derivation from explicit row facts only
    packet_active = _run_cli_ok(root, "--phase-id", "ACTIVE_PHASE")
    _, items_active = _parse_packet(packet_active)
    assert items_active["ALLOWED_OPERATIONS"] == ["implementation within authorized surfaces"]


# ---------------------------------------------------------------------------
# non-bulk emission
# ---------------------------------------------------------------------------


def test_PROJECTS_TOML_NOT_BULK_EMITTED(tmp_path: Path) -> None:
    rows = [_row("SELECTED_PHASE", next_action="Selected bounded action.")]
    for index in range(40):
        rows.append(
            _row(
                f"FILLER_PHASE_{index:02d}",
                state="CLOSED_PASS",
                implementation_authorized=False,
                next_action="BULK_MARKER_XYZ filler row prose that must never be emitted.",
            )
        )
    root = _fixture_root(tmp_path, rows)
    packet = _run_cli_ok(root, "--phase-id", "SELECTED_PHASE")
    assert "BULK_MARKER_XYZ" not in packet
    assert "FILLER_PHASE" not in packet
    assert "project_id" not in packet  # registry key names are never emitted
    assert len(packet.encode("utf-8")) <= 8192
    assert "Selected bounded action." in packet  # selected row content is bounded, present


def test_ROADMAP_NOT_BULK_EMITTED(tmp_path: Path) -> None:
    root = _fixture_root(
        tmp_path,
        [_row("PHASE_ONE")],
        extra_files={"docs/CURRENT_ROADMAP.md": "ROADMAP_BULK_MARKER " + "roadmap prose " * 200},
    )
    packet = _run_cli_ok(root)
    assert "ROADMAP_BULK_MARKER" not in packet


def test_SPINE_NOT_BULK_EMITTED(tmp_path: Path) -> None:
    root = _fixture_root(
        tmp_path,
        [_row("PHASE_ONE")],
        extra_files={"docs/state/context_spine.json": '{"marker": "SPINE_BULK_MARKER"}'},
    )
    packet = _run_cli_ok(root)
    assert "SPINE_BULK_MARKER" not in packet


# ---------------------------------------------------------------------------
# pointers
# ---------------------------------------------------------------------------


def test_POINTERS_BIND_TO_CANONICAL_STATE(tmp_path: Path) -> None:
    decision = {"verification_commands": ["python -m pytest -q tests/test_example.py"]}
    root = _fixture_root(
        tmp_path,
        [_row("PHASE_ONE", decision_artifact="decision.json")],
        decision=decision,
    )
    packet = _run_cli_ok(root)
    _, items = _parse_packet(packet)

    decision_bytes = (root / "decision.json").read_bytes()
    expected_prefix = hashlib.sha256(decision_bytes).hexdigest()[:12]
    pointers = items["INPUT_CONTRACTS"]
    assert f"decision.json#{expected_prefix}" in pointers
    toml_prefix = hashlib.sha256((root / "qntylab.toml").read_bytes()).hexdigest()[:12]
    assert f"qntylab.toml#{toml_prefix}" in pointers

    # corrupt the canonical file: the previously emitted pointer no longer
    # matches the file content, so the mismatch is detectable
    _write(root, "decision.json", decision_bytes + b"\n# corrupted")
    new_prefix = hashlib.sha256((root / "decision.json").read_bytes()).hexdigest()[:12]
    assert new_prefix != expected_prefix
    assert f"decision.json#{new_prefix}" not in packet


def test_RELEVANT_CODE_MAX_6(tmp_path: Path) -> None:
    stub_symbols = "\n".join(
        [
            "PROJECT_STATES = frozenset({'ACTIVE'})",
            "def _git_state(root):",
            "    raise NotImplementedError",
            "def load_context_sources(root):",
            "    raise NotImplementedError",
            "def validate_projects_registry(root, registry):",
            "    raise NotImplementedError",
            "def execution_authority_projection(root, projects):",
            "    raise NotImplementedError",
        ]
    )
    root = _fixture_root(
        tmp_path,
        [_row("PHASE_ONE")],
        extra_files={
            "qntylab/agent_context_packet_v0.py": "# stub packet module\n",
            "qntylab/project_context.py": stub_symbols,
        },
    )
    packet = _run_cli_ok(root)
    _, items = _parse_packet(packet)
    assert 1 <= len(items["RELEVANT_CODE"]) <= 6
    assert any(item.startswith("qntylab/agent_context_packet_v0.py:1#") for item in items["RELEVANT_CODE"])
    assert any(item.startswith("qntylab/project_context.py:") for item in items["RELEVANT_CODE"])


def test_RELEVANT_TESTS_MAX_4(tmp_path: Path) -> None:
    root = _fixture_root(
        tmp_path,
        [_row("PHASE_ONE")],
        extra_files={
            "tests/test_qntylab_agent_context_packet_v0.py": "# stub\n",
            "tests/test_project_context_v0.py": "# stub\n",
        },
    )
    packet = _run_cli_ok(root)
    _, items = _parse_packet(packet)
    assert 1 <= len(items["RELEVANT_TESTS"]) <= 4
    assert items["RELEVANT_TESTS"][0].startswith("tests/test_qntylab_agent_context_packet_v0.py:1#")


# ---------------------------------------------------------------------------
# bounded list fields
# ---------------------------------------------------------------------------


def test_LOAD_BEARING_INVARIANTS_MAX_7(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path, [_row("PHASE_ONE")])
    packet = _run_cli_ok(root)
    _, items = _parse_packet(packet)
    assert 1 <= len(items["LOAD_BEARING_INVARIANTS"]) <= 7
    assert len(items["LOAD_BEARING_INVARIANTS"]) == len(packet_module.LOAD_BEARING_INVARIANT_RECORDS)


def test_ALLOWED_OPERATIONS_MAX_5(tmp_path: Path) -> None:
    root = _fixture_root(
        tmp_path,
        [
            _row(
                "PHASE_ONE",
                implementation_authorized=True,
                scientific_execution_authorized=True,
                real_data_access_authorized=True,
            )
        ],
    )
    packet = _run_cli_ok(root)
    _, items = _parse_packet(packet)
    assert 1 <= len(items["ALLOWED_OPERATIONS"]) <= 5
    assert "implementation within authorized surfaces" in items["ALLOWED_OPERATIONS"]


def test_FORBIDDEN_OPERATIONS_MAX_5(tmp_path: Path) -> None:
    root = _fixture_root(
        tmp_path,
        [
            _row(
                "PHASE_ONE",
                implementation_authorized=False,
                scientific_execution_authorized=False,
                real_data_access_authorized=False,
                trading_authority="NONE",
                capital_authority="NONE",
                governance_only=True,
            )
        ],
    )
    packet = _run_cli_ok(root)
    _, items = _parse_packet(packet)
    assert len(items["FORBIDDEN_OPERATIONS"]) == 5


# ---------------------------------------------------------------------------
# worktree projection
# ---------------------------------------------------------------------------


def test_WORKTREE_DIRTY_STATE_DETERMINISTIC(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path, [_row("PHASE_ONE")])
    _write(root, "artifact.md", "modified tracked content\n")
    _write(root, "untracked_one.txt", "u1\n")
    _write(root, "untracked_two.txt", "u2\n")
    packet = _run_cli_ok(root)
    _, items = _parse_packet(packet)
    assert items["WORKTREE"] == ["DIRTY untracked=2"]
    assert _run_cli_ok(root) == packet  # deterministic across runs


# ---------------------------------------------------------------------------
# mutation-freedom
# ---------------------------------------------------------------------------


def test_PACKET_GENERATION_MUTATES_NOTHING(tmp_path: Path) -> None:
    root = _fixture_root(
        tmp_path,
        [_row("PHASE_ONE", decision_artifact="decision.json")],
        decision={"verification_commands": ["python -m pytest -q tests/test_example.py"]},
    )
    before_tree = _snapshot_tree(root)
    before_status = _git_status_output(root)
    _run_cli_ok(root)
    after_tree = _snapshot_tree(root)
    after_status = _git_status_output(root)
    assert before_tree == after_tree
    assert before_status == after_status  # no new untracked files, no mutations


def test_LEGACY_PROJECT_CONTEXT_SOURCE_UNCHANGED(tmp_path: Path) -> None:
    legacy_source = REPO_ROOT / "qntylab" / "project_context.py"
    before_digest = hashlib.sha256(legacy_source.read_bytes()).hexdigest()

    def _legacy_renders() -> tuple[bytes, bytes]:
        spine = subprocess.run(
            [sys.executable, "-m", "qntylab.project_context", "--root", str(REPO_ROOT), "spine"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        brief = subprocess.run(
            [sys.executable, "-m", "qntylab.project_context", "--root", str(REPO_ROOT), "brief"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        return spine.stdout, brief.stdout

    spine_before, brief_before = _legacy_renders()
    # packet generation against the live repository must not disturb the
    # legacy context renderers or their source module
    _run_cli_ok(REPO_ROOT, "--phase-id", UMBRELLA_PROJECT_ID)
    spine_after, brief_after = _legacy_renders()
    assert spine_before == spine_after  # SAME_INPUT -> SAME_OLD_RENDERER_OUTPUT
    assert brief_before == brief_after
    assert hashlib.sha256(legacy_source.read_bytes()).hexdigest() == before_digest


# ---------------------------------------------------------------------------
# positive controls
# ---------------------------------------------------------------------------


def test_HAPPY_PATH_FULL_PACKET_RENDER(tmp_path: Path) -> None:
    decision = {"verification_commands": ["python -m pytest -q tests/test_example.py"]}
    root = _fixture_root(
        tmp_path,
        [
            _row(
                "HAPPY_PHASE",
                decision_artifact="decision.json",
                review_lifecycle_current_stage="IMPLEMENTATION",
                review_lifecycle_policy="NORMAL_BOUNDED_COMPLETION_NOT_TERMINAL_ONE_REVIEW",
            )
        ],
        decision=decision,
        extra_files={
            "qntylab/agent_context_packet_v0.py": "# stub packet module\n",
            "tests/test_qntylab_agent_context_packet_v0.py": "# stub test\n",
        },
    )
    packet = _run_cli_ok(root)  # default selection: exactly one ACTIVE row
    order, items = _parse_packet(packet)
    assert order == list(FIELD_ORDER)
    assert len(order) == 19
    assert items["STATE"] == ["ACTIVE"]
    assert items["ALLOWED_OPERATIONS"] == ["implementation within authorized surfaces"]
    assert items["VERIFY_COMMAND"] == ["python -m pytest -q tests/test_example.py"]
    assert items["REVIEW_LIFECYCLE"] == ["IMPLEMENTATION (policy: NORMAL_BOUNDED_COMPLETION_NOT_TERMINAL_ONE_REVIEW)"]
    assert items["OPEN_BLOCKERS"] == ["NONE"]
    assert items["HEAD"] == [subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True,
    ).stdout.decode().strip()]
    assert len(packet.encode("utf-8")) <= 8192


def test_EXPLICIT_SELECTOR_CLOSED_PASS_ROW_RENDERS_TRUE_STATE(tmp_path: Path) -> None:
    root = _fixture_root(
        tmp_path,
        [_row("DONE_PHASE", state="CLOSED_PASS", implementation_authorized=False, next_action="CLOSED_PASS: completed.")],
    )
    packet = _run_cli_ok(root, "--phase-id", "DONE_PHASE")
    _, items = _parse_packet(packet)
    assert items["STATE"] == ["CLOSED_PASS"]
    assert items["OBJECTIVE"] == ["CLOSED_PASS: completed."]
    assert items["ALLOWED_OPERATIONS"] == ["NONE"]


# ---------------------------------------------------------------------------
# canonical-reuse adversarial tests (registry interpretation parity)
# ---------------------------------------------------------------------------


def _canonical_operative_active(root: Path) -> dict[str, Any] | None:
    """Derive the canonical Project Context operative-active record."""
    snapshot = project_context.RepositorySnapshot.acquire(root)
    _, _adr_registry, projects_registry = project_context.load_context_sources(root, snapshot=snapshot)
    projects = project_context.validate_projects_registry(root, projects_registry, snapshot=snapshot)
    projection = project_context.execution_authority_projection(root, projects, snapshot=snapshot)
    assert projection["issues"] == []
    return projection["active_project"]


def test_FULL_REGISTRY_VALIDATION_REQUIRED_NO_SELECTIVE_ROW_BYPASS(tmp_path: Path) -> None:
    # the requested row is structurally plausible, but ANOTHER registry row
    # violates canonical project-context validation => fail closed
    malformed = _row("BAD_PHASE", state="NOT_A_CANONICAL_STATE", implementation_authorized=False)
    root = _fixture_root(tmp_path, [_row("GOOD_PHASE"), malformed])
    completed = _run_cli(root, "--phase-id", "GOOD_PHASE")
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert b"canonical project context" in completed.stderr
    assert b"unknown project state" in completed.stderr


def test_DUPLICATE_UNRELATED_PROJECT_ID_REJECTED(tmp_path: Path) -> None:
    # confirmed in qntylab/project_context.py: canonical validation rejects
    # duplicate project IDs anywhere in the registry
    root = _fixture_root(
        tmp_path,
        [_row("PHASE_ONE"), _row("PHASE_ONE", state="CLOSED_PASS", implementation_authorized=False)],
    )
    completed = _run_cli(root, "--phase-id", "PHASE_ONE")
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert b"canonical project context" in completed.stderr
    assert b"duplicate project ID" in completed.stderr


def test_ACTIVE_CANDIDATE_EXCLUDED_FROM_DEFAULT_SELECTION(tmp_path: Path) -> None:
    # ACTIVE_CANDIDATE (branch-local candidate, activation-gated out of the
    # operative-active set) must never be selected merely because its
    # top-level state is ACTIVE; canonical operative-active count is 0
    root = _fixture_root(tmp_path, [_candidate_row("CANDIDATE_PHASE")], extra_files={"activation.json": CANDIDATE_ACTIVATION_JSON})
    assert _canonical_operative_active(root) is None  # canonical parity premise
    completed = _run_cli(root)
    assert completed.returncode != 0
    assert completed.stdout == b""
    stderr = completed.stderr.decode("utf-8", "replace")
    assert "0 operative ACTIVE" in stderr
    assert "CANDIDATE_PHASE" not in stderr


def test_GENUINE_ACTIVE_SELECTED_OVER_ACTIVE_CANDIDATE(tmp_path: Path) -> None:
    # canonical ACTIVE_CANDIDATE registry spelling (V0R7 precedent):
    # state PLANNED_NOT_AUTHORIZED + candidate_state ACTIVE_CANDIDATE
    root = _fixture_root(
        tmp_path,
        [
            _candidate_row("CANDIDATE_PHASE", state="PLANNED_NOT_AUTHORIZED"),
            _row("GENUINE_ACTIVE_PHASE"),
        ],
        extra_files={"activation.json": CANDIDATE_ACTIVATION_JSON},
    )
    packet = _run_cli_ok(root)  # default selection
    _, items = _parse_packet(packet)
    assert items["PHASE_ID"] == ["GENUINE_ACTIVE_PHASE"]
    assert items["STATE"] == ["ACTIVE"]


def test_PACKET_SELECTION_PARITY_WITH_PROJECT_CONTEXT(tmp_path: Path) -> None:
    # PACKET_DEFAULT_SELECTED_PHASE == PROJECT_CONTEXT_OPERATIVE_ACTIVE_PHASE
    root = _fixture_root(
        tmp_path,
        [
            _candidate_row("CANDIDATE_PHASE", state="PLANNED_NOT_AUTHORIZED"),
            _row("GENUINE_ACTIVE_PHASE"),
        ],
        extra_files={"activation.json": CANDIDATE_ACTIVATION_JSON},
    )
    canonical_active = _canonical_operative_active(root)
    assert canonical_active is not None
    packet = _run_cli_ok(root)
    _, items = _parse_packet(packet)
    assert items["PHASE_ID"] == [canonical_active["project_id"]]
    assert items["STATE"] == [canonical_active["state"]]


def test_EXPLICIT_SELECTOR_CANONICAL_PLANNED_ROW_IS_DESCRIPTIVE_ONLY(tmp_path: Path) -> None:
    root = _fixture_root(
        tmp_path,
        [
            _row(
                "PLANNED_PHASE",
                state="PLANNED_NOT_AUTHORIZED",
                implementation_authorized=False,
                next_action="Planned but not authorized.",
            ),
            _row("ACTIVE_PHASE"),
        ],
    )
    packet = _run_cli_ok(root, "--phase-id", "PLANNED_PHASE")
    _, items = _parse_packet(packet)
    assert items["STATE"] == ["PLANNED_NOT_AUTHORIZED"]  # verbatim, never relabeled
    assert items["ALLOWED_OPERATIONS"] == ["NONE"]  # describing grants no authority