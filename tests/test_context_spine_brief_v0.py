"""PR-C contract tests for the packet-only Context Spine brief."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
BRIEF_COMMAND = [sys.executable, "-m", "qntylab.project_context", "--root", str(ROOT), "brief"]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _qnty_root(tmp_path: Path, *, task_id: str = "SYNTHETIC_TASK", protocol_id: str = "synthetic_protocol") -> Path:
    root = tmp_path / "qnty"
    task_root = root / "docs/control/tasks" / task_id
    task_root.mkdir(parents=True)
    receipt = {
        "phase": "synthetic_phase",
        "protocol_id": protocol_id,
        "receipt_index": 1,
        "receipt_kind": "qnty_cross_agent_handoff_receipt",
        "schema_version": "0.1.0",
        "task_id": task_id,
    }
    receipt_bytes = _canonical(receipt)
    receipt_path = task_root / "handoff_v001.json"
    receipt_path.write_bytes(receipt_bytes)
    active = {
        "control_kind": "qnty_active_task_pointer",
        "handoff_receipt_path": f"docs/control/tasks/{task_id}/handoff_v001.json",
        "handoff_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "phase": "synthetic_phase",
        "protocol_id": protocol_id,
        "schema_version": "0.1.0",
        "task_id": task_id,
    }
    (root / "docs/control").mkdir(exist_ok=True)
    (root / "docs/control/active_task.json").write_bytes(_canonical(active))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    _git(root, "add", ".")
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "fixture"],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
    )
    _git(root, "remote", "add", "origin", "https://github.com/CipherCuttle/Qnty.git")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def _packet() -> dict[str, Any]:
    return project_context.compile_context_spine(ROOT)


def _qnty_record(packet: dict[str, Any]) -> dict[str, Any]:
    return next(record for record in packet["external_repositories"] if record["repository_id"] == "Qnty")


def test_brief_uses_compiled_packet_only(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = _packet()

    def fail(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("brief renderer read a source")

    monkeypatch.setattr(project_context, "load_context_sources", fail)
    monkeypatch.setattr(project_context, "context_data", fail)
    monkeypatch.setattr(project_context, "_foundation", fail)
    assert "Qnty Ecosystem Brief" in project_context.brief_text(packet)


def test_brief_does_not_write_or_use_network(monkeypatch: pytest.MonkeyPatch) -> None:
    packet = _packet()

    def fail(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("brief renderer performed an external operation")

    monkeypatch.setattr(project_context.subprocess, "run", fail)
    monkeypatch.setattr(Path, "write_bytes", fail)
    monkeypatch.setattr(Path, "write_text", fail)
    assert project_context.brief_text(packet)


def test_brief_is_deterministic_and_has_no_host_path_or_clock_text() -> None:
    first = project_context.brief_text(_packet())
    second = project_context.brief_text(_packet())
    assert first == second
    for token in (str(ROOT), "/home/", "/tmp/", "file://", "http://", "https://", "timestamp", "generated_at", "hostname", "pid"):
        assert token not in first


def test_brief_without_qnty_root_is_truthful() -> None:
    text = project_context.brief_text(_packet())
    assert "adapter = READ_ONLY_ADAPTER_IMPLEMENTED" in text
    assert "context = UNAVAILABLE_WITHOUT_EXPLICIT_ROOT" in text
    assert "CONTEXT_PARTIAL" in text
    assert "QntyAgentEval" in text and "ADAPTER_NOT_IMPLEMENTED" in text
    assert "QntyPolicyGate" in text and "ADAPTER_NOT_IMPLEMENTED" in text


def test_brief_with_valid_qnty_root_shows_bounded_read_only_observation(tmp_path: Path) -> None:
    packet = project_context.compile_context_spine(ROOT, external_roots={"Qnty": _qnty_root(tmp_path)})
    text = project_context.brief_text(packet)
    assert "context = AVAILABLE_READ_ONLY" in text
    assert "task_id = SYNTHETIC_TASK" in text
    assert "protocol_id = synthetic_protocol" in text
    assert "handoff integrity = POINTER_DIGEST_MATCH" in text
    assert "continuity verifier status = NOT_EXECUTED" in text
    assert "next-action authority = NOT_ESTABLISHED" in text
    assert "CONTEXT_AVAILABLE" in text


def test_brief_preserves_conflicts_and_fails_closed(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    packet = _packet()
    packet["packet_status"] = project_context.ARCHITECTURE_CONFLICT
    packet["conflicts"] = [{"code": "TEST_CONFLICT", "detail": "canonical disagreement"}]
    monkeypatch.setattr(project_context, "compile_context_spine", lambda *args, **kwargs: packet)
    with pytest.raises(SystemExit) as exit_info:
        project_context.main(["--root", str(ROOT), "brief"])
    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    assert "ARCHITECTURE_CONFLICT" in output
    assert "TEST_CONFLICT: canonical disagreement" in output
    assert "CONTEXT_AVAILABLE" not in output


def test_brief_does_not_infer_or_launder_authority() -> None:
    text = project_context.brief_text(_packet())
    assert "Git identity selects bytes, not semantic authority." in text
    assert "Handoff is not Qnty acceptance." in text
    assert "NEXT_ACTION authority is not established" in text
    assert "no NEXT_ACTION field is emitted" in text
    assert "No science, runtime, live, trading, or capital authority is inferred." in text
    assert "NEXT_ACTION =" not in text
    assert "permitted next action" not in text.lower()


def test_brief_has_no_historical_task_protocol_or_action_literals() -> None:
    source = inspect.getsource(project_context.brief_text)
    sections = inspect.getsource(project_context._brief_sections)
    projects = project_context.load_context_sources(ROOT)[2]["project"]
    assert all(record["project_id"] not in source + sections for record in projects)
    assert all(record["next_action"] not in source + sections for record in projects)
    assert "SYNTHETIC_TASK" not in source + sections
    assert "synthetic_protocol" not in source + sections


def _bounds(text: str) -> tuple[int, int, int]:
    lines = text.splitlines()
    return (
        len(text.encode("utf-8")),
        len(lines),
        max((len(line.encode("utf-8")) for line in lines), default=0),
    )


def _assert_bounded(text: str) -> None:
    total_bytes, line_count, widest_line = _bounds(text)
    assert total_bytes <= project_context.BRIEF_MAX_BYTES
    assert line_count <= project_context.BRIEF_MAX_LINES
    assert widest_line <= project_context.BRIEF_MAX_LINE_BYTES


def _conflict_packet(conflicts: list[dict[str, str]]) -> dict[str, Any]:
    packet = _packet()
    packet["packet_status"] = project_context.ARCHITECTURE_CONFLICT
    packet["conflicts"] = conflicts
    return packet


def test_brief_output_is_bounded() -> None:
    text = project_context.brief_text(_packet())
    _assert_bounded(text)


def test_brief_bounds_are_byte_and_line_budgets_not_claimed_token_counts() -> None:
    names = [name for name in vars(project_context) if name.startswith("BRIEF_")]
    assert not [name for name in names if "TOKEN" in name]
    assert project_context.BRIEF_MAX_BYTES == project_context.BRIEF_MAX_LINES * (
        project_context.BRIEF_MAX_LINE_BYTES + 1
    )


def test_brief_bounds_a_single_whitespace_free_packet_value() -> None:
    # Pre-repair this rendered ~201_737 bytes: one 200_000-character value is a
    # single whitespace-delimited word, so a word-count proxy bounded nothing.
    baseline = len(project_context.brief_text(_packet()).encode("utf-8"))
    packet = _packet()
    packet["repository"]["durable_role"] = "A" * 200_000
    text = project_context.brief_text(packet)
    _assert_bounded(text)
    assert len(text.encode("utf-8")) - baseline <= project_context.BRIEF_MAX_LINE_BYTES
    assert project_context.BRIEF_LINE_TRUNCATION_MARKER in text
    assert "A" * (project_context.BRIEF_MAX_LINE_BYTES + 1) not in text


def test_brief_bounds_a_large_conflict_detail_value() -> None:
    packet = _conflict_packet([{"code": "HUGE_CONFLICT", "detail": "d" * 300_000}])
    text = project_context.brief_text(packet)
    _assert_bounded(text)
    assert "ARCHITECTURE_CONFLICT" in text
    assert "HUGE_CONFLICT" in text
    assert project_context.BRIEF_LINE_TRUNCATION_MARKER in text


def test_brief_holds_the_global_byte_ceiling_under_saturating_packet_growth() -> None:
    packet = _conflict_packet([{"code": f"C{index:05d}", "detail": "d" * 4_000} for index in range(5_000)])
    packet["repository"]["durable_role"] = "r" * 100_000
    for record in packet["external_repositories"]:
        record["durable_role"] = "x" * 100_000
        record["adapter_status"] = "y" * 100_000
    text = project_context.brief_text(packet)
    _assert_bounded(text)
    assert project_context.BRIEF_TRUNCATION_MARKER in text


def test_brief_line_budget_is_not_bypassed_by_embedded_newlines() -> None:
    packet = _packet()
    packet["repository"]["durable_role"] = "X\n" * 50_000
    text = project_context.brief_text(packet)
    _assert_bounded(text)


def test_brief_clamps_multibyte_values_without_splitting_a_codepoint() -> None:
    packet = _packet()
    packet["repository"]["durable_role"] = "\U0001f600" * 100_000
    text = project_context.brief_text(packet)
    _assert_bounded(text)
    assert text.encode("utf-8").decode("utf-8") == text


def test_brief_truncation_is_deterministic_and_explicit() -> None:
    packet = _conflict_packet([{"code": "C", "detail": "d" * 300_000} for _ in range(5_000)])
    first = project_context.brief_text(packet)
    assert first == project_context.brief_text(packet)
    assert first.encode("utf-8") == project_context.brief_text(packet).encode("utf-8")
    _assert_bounded(first)
    assert first.splitlines()[-1] == project_context.BRIEF_TRUNCATION_MARKER
    clamped = [line for line in first.splitlines() if line.endswith(project_context.BRIEF_LINE_TRUNCATION_MARKER)]
    assert all(len(line.encode("utf-8")) == project_context.BRIEF_MAX_LINE_BYTES for line in clamped)


def test_brief_render_is_byte_identical_across_repeated_renders() -> None:
    packet = _packet()
    packet["repository"]["durable_role"] = "A" * 200_000
    renders = {project_context.brief_text(packet).encode("utf-8") for _ in range(5)}
    assert len(renders) == 1


def test_brief_is_stable_across_cwd_locale_timezone_and_hashseed(tmp_path: Path) -> None:
    outputs = []
    for cwd, env in (
        (ROOT, {"TZ": "UTC", "LC_ALL": "C", "PYTHONHASHSEED": "1"}),
        (tmp_path, {"TZ": "Pacific/Auckland", "LC_ALL": "C", "PYTHONHASHSEED": "987"}),
    ):
        completed = subprocess.run(
            BRIEF_COMMAND,
            cwd=cwd,
            env={**os.environ, **env, "PYTHONPATH": str(ROOT)},
            check=True,
            capture_output=True,
        )
        outputs.append(completed.stdout)
    assert outputs[0] == outputs[1]


def test_cli_accepts_explicit_external_root_and_does_not_change_adapter_contract(tmp_path: Path) -> None:
    qnty = _qnty_root(tmp_path)
    command = [
        sys.executable,
        "-m",
        "qntylab.project_context",
        "--root",
        str(ROOT),
        "--external-root",
        f"Qnty={qnty}",
        "brief",
    ]
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    assert "context = AVAILABLE_READ_ONLY" in completed.stdout
    records = {record["repository_id"]: record for record in _packet()["external_repositories"]}
    assert records["QntyAgentEval"]["adapter_status"] == "ADAPTER_NOT_IMPLEMENTED"
    assert records["QntyPolicyGate"]["adapter_status"] == "ADAPTER_NOT_IMPLEMENTED"
