"""Hermetic contract tests for the narrow Qnty read-only adapter."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from qntylab import project_context, qnty_context_adapter


ROOT = Path(__file__).resolve().parents[1]
QNTY_LOCATOR = "github.com/CipherCuttle/Qnty"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _qnty_root(
    tmp_path: Path,
    *,
    active_updates: dict[str, object] | None = None,
    receipt: dict[str, object] | None = None,
    remote_url: str = "https://github.com/CipherCuttle/Qnty.git",
) -> Path:
    root = tmp_path / "qnty"
    (root / "docs/control/tasks/SYNTHETIC_TASK").mkdir(parents=True)
    receipt_value: dict[str, object] = {
        "phase": "synthetic_phase",
        "protocol_id": "synthetic_protocol",
        "receipt_index": 1,
        "receipt_kind": "qnty_cross_agent_handoff_receipt",
        "schema_version": "0.1.0",
        "task_id": "SYNTHETIC_TASK",
    }
    if receipt:
        receipt_value.update(receipt)
    receipt_bytes = _canonical(receipt_value)
    receipt_path = root / "docs/control/tasks/SYNTHETIC_TASK/handoff_v001.json"
    receipt_path.write_bytes(receipt_bytes)
    active: dict[str, object] = {
        "control_kind": "qnty_active_task_pointer",
        "handoff_receipt_path": "docs/control/tasks/SYNTHETIC_TASK/handoff_v001.json",
        "handoff_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "phase": "synthetic_phase",
        "protocol_id": "synthetic_protocol",
        "schema_version": "0.1.0",
        "task_id": "SYNTHETIC_TASK",
    }
    if active_updates:
        active.update(active_updates)
    (root / "docs/control/active_task.json").write_bytes(_canonical(active))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    _git(root, "add", ".")
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "fixture"],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
    )
    _git(root, "remote", "add", "origin", remote_url)
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def _observe(root: Path) -> dict[str, object]:
    return qnty_context_adapter.observe(root, expected_locator=QNTY_LOCATOR, expected_branch="main")


def _packet(qnty_root: Path, **kwargs: object) -> dict[str, object]:
    return project_context.compile_context_spine(ROOT, external_roots={"Qnty": qnty_root, **kwargs})


def _qnty_record(packet: dict[str, object]) -> dict[str, object]:
    return next(record for record in packet["external_repositories"] if record["repository_id"] == "Qnty")  # type: ignore[index]


def _assert_conflict(packet: dict[str, object]) -> None:
    assert packet["packet_status"] == project_context.ARCHITECTURE_CONFLICT
    assert _qnty_record(packet)["context_state"] == project_context.ARCHITECTURE_CONFLICT
    assert _qnty_record(packet)["observation"] is None


def test_qnty_adapter_is_implemented_and_other_adapters_remain_unimplemented() -> None:
    records = {record["repository_id"]: record for record in project_context.compile_context_spine(ROOT)["external_repositories"]}  # type: ignore[index]
    assert records["Qnty"]["adapter_status"] == "READ_ONLY_ADAPTER_IMPLEMENTED"
    assert records["Qnty"]["context_state"] == "UNAVAILABLE_WITHOUT_EXPLICIT_ROOT"
    assert records["QntyAgentEval"]["adapter_status"] == "ADAPTER_NOT_IMPLEMENTED"
    assert records["QntyPolicyGate"]["adapter_status"] == "ADAPTER_NOT_IMPLEMENTED"


def test_no_root_is_unavailable_and_root_is_not_serialized(tmp_path: Path) -> None:
    qnty = _qnty_root(tmp_path)
    packet = project_context.compile_context_spine(ROOT)
    assert _qnty_record(packet)["observation"] is None
    serialized = project_context.context_spine_bytes(ROOT, external_roots={"Qnty": qnty}).decode()
    assert str(qnty) not in serialized
    assert "UNAVAILABLE_WITHOUT_EXPLICIT_ROOT" in project_context.context_spine_bytes(ROOT).decode()


def test_valid_pointer_observed_with_bounded_fields(tmp_path: Path) -> None:
    packet = _packet(_qnty_root(tmp_path))
    record = _qnty_record(packet)
    observation = record["observation"]
    assert record["context_state"] == "AVAILABLE_READ_ONLY"
    assert observation["control_pointer"] == {  # type: ignore[index]
        "task_id": "SYNTHETIC_TASK",
        "protocol_id": "synthetic_protocol",
        "phase": "synthetic_phase",
        "handoff_receipt_path": "docs/control/tasks/SYNTHETIC_TASK/handoff_v001.json",
        "handoff_receipt_sha256": observation["control_pointer"]["handoff_receipt_sha256"],  # type: ignore[index]
    }
    assert observation["handoff_integrity"] == "POINTER_DIGEST_MATCH"
    assert observation["continuity_verifier_status"] == "NOT_EXECUTED"
    assert observation["next_action_authority"] == "NOT_ESTABLISHED"
    identity = observation["generated_from"]["canonical_git_identity"]  # type: ignore[index]
    assert identity["compiled_inputs"] == [
        "docs/control/active_task.json",
        "docs/control/tasks/SYNTHETIC_TASK/handoff_v001.json",
    ]
    assert identity["compiled_bytes_bound_to_head_sha"] is True
    assert identity["unbound_compiled_inputs"] == []


def test_canonical_json_and_digest_are_mechanically_verified(tmp_path: Path) -> None:
    qnty = _qnty_root(tmp_path)
    assert _observe(qnty)["handoff_integrity"] == "POINTER_DIGEST_MATCH"
    active = qnty / "docs/control/active_task.json"
    active.write_bytes(active.read_bytes() + b"\n")
    with pytest.raises(qnty_context_adapter.QntyAdapterError, match="ACTIVE_TASK_MALFORMED"):
        _observe(qnty)


@pytest.mark.parametrize(
    "change, expected",
    [
        (lambda root: (root / "docs/control/active_task.json").write_text("{", encoding="utf-8"), "ACTIVE_TASK_MALFORMED"),
        (lambda root: _rewrite_active(root, control_kind="wrong_kind"), "ACTIVE_TASK_WRONG_CONTROL_KIND"),
        (lambda root: _rewrite_active(root, handoff_receipt_path="docs/control/tasks/SYNTHETIC_TASK/handoff_v002.json"), "PATH_NOT_REGULAR_NON_SYMLINK_FILE"),
        (lambda root: _rewrite_active(root, handoff_receipt_sha256="0" * 64), "HANDOFF_DIGEST_MISMATCH"),
        (lambda root: _rewrite_active(root, handoff_receipt_path="docs/control/tasks/SYNTHETIC_TASK/../../escape.json"), "HANDOFF_PATH_NOT_REPOSITORY_RELATIVE"),
    ],
)
def test_malformed_pointer_states_fail_closed(tmp_path: Path, change: object, expected: str) -> None:
    qnty = _qnty_root(tmp_path)
    change(qnty)  # type: ignore[operator]
    packet = _packet(qnty)
    _assert_conflict(packet)
    assert expected in json.dumps(packet["conflicts"])


def _rewrite_active(root: Path, **updates: object) -> None:
    path = root / "docs/control/active_task.json"
    value = json.loads(path.read_bytes())
    value.update(updates)
    path.write_bytes(_canonical(value))


def test_receipt_pointer_contradiction_and_wrong_kind_fail_closed(tmp_path: Path) -> None:
    qnty = _qnty_root(tmp_path, receipt={"receipt_kind": "wrong"})
    _assert_conflict(_packet(qnty))
    qnty = _qnty_root(tmp_path / "contradiction", receipt={"phase": "different"})
    _assert_conflict(_packet(qnty))


def test_receipt_symlink_and_untracked_file_fail_closed(tmp_path: Path) -> None:
    qnty = _qnty_root(tmp_path)
    receipt = qnty / "docs/control/tasks/SYNTHETIC_TASK/handoff_v001.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(receipt.read_bytes())
    receipt.unlink()
    receipt.symlink_to(outside)
    _assert_conflict(_packet(qnty))

    qnty = _qnty_root(tmp_path / "untracked")
    _git(qnty, "rm", "--cached", "-q", "--", "docs/control/tasks/SYNTHETIC_TASK/handoff_v001.json")
    _assert_conflict(_packet(qnty))


def test_wrong_root_fails_closed(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    _assert_conflict(_packet(wrong))


def test_unrelated_git_repo_with_copied_valid_control_files_fails_closed(tmp_path: Path) -> None:
    canonical = _qnty_root(tmp_path)
    unrelated = tmp_path / "unrelated"
    shutil.copytree(canonical, unrelated)
    _git(unrelated, "remote", "set-url", "origin", "https://github.com/Other/Repository.git")
    _assert_conflict(_packet(unrelated))


def test_wrong_origin_remote_fails_closed(tmp_path: Path) -> None:
    _assert_conflict(_packet(_qnty_root(tmp_path, remote_url="https://github.com/Other/Repository.git")))


def test_missing_origin_remote_fails_closed(tmp_path: Path) -> None:
    qnty = _qnty_root(tmp_path)
    _git(qnty, "remote", "remove", "origin")
    _assert_conflict(_packet(qnty))


def test_wrong_remote_tracking_branch_fails_closed(tmp_path: Path) -> None:
    qnty = _qnty_root(tmp_path)
    _git(qnty, "update-ref", "-d", "refs/remotes/origin/main")
    _git(qnty, "update-ref", "refs/remotes/origin/develop", "HEAD")
    _assert_conflict(_packet(qnty))


def test_head_not_canonical_remote_main_fails_closed(tmp_path: Path) -> None:
    qnty = _qnty_root(tmp_path)
    _git(qnty, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-q", "-m", "advance")
    _assert_conflict(_packet(qnty))


@pytest.mark.parametrize(
    "remote_url",
    [
        "https://github.com/CipherCuttle/Qnty.git",
        "git@github.com:CipherCuttle/Qnty.git",
        "ssh://git@github.com/CipherCuttle/Qnty.git",
    ],
)
def test_canonical_qnty_locator_accepts_known_github_spellings(tmp_path: Path, remote_url: str) -> None:
    record = _qnty_record(_packet(_qnty_root(tmp_path, remote_url=remote_url)))
    assert record["context_state"] == "AVAILABLE_READ_ONLY"


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_dirty_compiled_input_is_unbound_even_when_index_flags_claim_unchanged(tmp_path: Path, flag: str) -> None:
    qnty = _qnty_root(tmp_path)
    _rewrite_active(qnty, unused="dirty_but_valid")
    _git(qnty, "update-index", flag, "docs/control/active_task.json")
    observation = _qnty_record(_packet(qnty))["observation"]
    identity = observation["generated_from"]["canonical_git_identity"]  # type: ignore[index]
    assert identity["compiled_bytes_bound_to_head_sha"] is False
    assert identity["unbound_compiled_inputs"] == ["docs/control/active_task.json"]


def test_read_only_adapter_does_not_change_qnty_files_or_git_state(tmp_path: Path) -> None:
    qnty = _qnty_root(tmp_path)
    before_files = {path.relative_to(qnty): path.read_bytes() for path in qnty.rglob("*") if path.is_file() and ".git" not in path.parts}
    before_git = {path.relative_to(qnty / ".git"): path.read_bytes() for path in (qnty / ".git").rglob("*") if path.is_file()}
    _observe(qnty)
    after_files = {path.relative_to(qnty): path.read_bytes() for path in qnty.rglob("*") if path.is_file() and ".git" not in path.parts}
    after_git = {path.relative_to(qnty / ".git"): path.read_bytes() for path in (qnty / ".git").rglob("*") if path.is_file()}
    assert after_files == before_files
    assert after_git == before_git


def test_hostile_git_environment_cannot_redirect_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    qnty = _qnty_root(tmp_path)
    other = _qnty_root(tmp_path / "other")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git/index"))
    observation = _observe(qnty)
    expected = subprocess.run(["git", "-C", str(qnty), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    assert observation["generated_from"]["canonical_git_identity"]["head_sha"] == expected  # type: ignore[index]


def test_same_git_bytes_are_deterministic_across_absolute_roots(tmp_path: Path) -> None:
    first = _qnty_root(tmp_path)
    second = tmp_path / "different-root"
    shutil.copytree(first, second)
    assert _observe(first) == _observe(second)


def test_adapter_does_not_execute_or_import_qnty_code() -> None:
    source = Path(qnty_context_adapter.__file__).read_text(encoding="utf-8")
    assert "quantbot" not in source
    assert "continuity" in source
    assert all(token not in source for token in ("RECOVER_OR_RETIRE", "real_btc_candidate", "handoff_v049"))
