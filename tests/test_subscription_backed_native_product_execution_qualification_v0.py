from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from qntylab.subscription_backed_native_product_execution_qualification_v0 import (
    FIXTURE_BEFORE_BYTES,
    FIXTURE_TARGET_BYTES,
    QualificationError,
    _base_receipt,
    _workspace_receipt,
    api_key_gate,
    api_key_presence,
    canonical_json,
    fixture_observation,
    git_metadata_snapshot,
    overall_qualification_pass,
    parse_reviewer_verdict,
    parse_verifier_verdict,
    qntylab_snapshot,
    render_evidence_prompt,
    require_hashes,
    sha256_bytes,
    sha256_file,
    validate_role_receipt,
    workspace_identity,
    workspace_snapshot,
    write_exclusive_json,
)

PHASE = Path(__file__).parents[1] / "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0"
if str(PHASE) not in sys.path:
    sys.path.insert(0, str(PHASE))

import claude_reviewer_driver_v0 as claude_driver  # noqa: E402
import native_codex_role_driver_v0 as codex_driver  # noqa: E402
import run_qualification_batch_v0 as controller  # noqa: E402

FAKE_CODEX = Path(__file__).parent / "fixtures/fake_codex_app_server_v0.py"
FAKE_CLAUDE = Path(__file__).parent / "fixtures/fake_claude_code_v0.py"
ROOT = Path(__file__).parents[1]


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=root, capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def make_workspace(tmp_path: Path, *, target: bool = False) -> Path:
    root = tmp_path / "workspace"
    root.mkdir(parents=True)
    (root / "fixture.txt").write_bytes(FIXTURE_BEFORE_BYTES)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "-c", "user.name=Tests", "-c", "user.email=tests@invalid", "add", "fixture.txt")
    _git(root, "-c", "user.name=Tests", "-c", "user.email=tests@invalid", "commit", "-q", "-m", "fixture")
    if target:
        (root / "fixture.txt").write_bytes(FIXTURE_TARGET_BYTES)
    return root


def codex_receipt(tmp_path: Path, scenario: str, role: str = "BUILDER", *, timeout: int = 5, environment: dict[str, str] | None = None):
    workspace = make_workspace(tmp_path, target=role == "VERIFIER")
    prompt = b"prompt\n"
    return codex_driver.run_role(
        role=role,
        workspace=workspace,
        qntylab_root=ROOT,
        prompt=prompt,
        workspace_identity=workspace_identity(workspace)["identity_sha256"],
        prompt_template_sha256=sha256_bytes(prompt),
        driver_sha256="d" * 64,
        started_marker_sha256="m" * 64,
        timeout_seconds=timeout,
        argv=[sys.executable, str(FAKE_CODEX), scenario],
        environment=environment,
    )


# BUILDER attacks


def test_builder_expected_write_machine_passes(tmp_path: Path) -> None:
    receipt = codex_receipt(tmp_path, "write")
    assert receipt["machine_status"] == "PASS"
    assert receipt["workspace"]["changed_paths"] == ["fixture.txt"]
    assert receipt["workspace"]["fixture_after"]["sha256"] == sha256_bytes(FIXTURE_TARGET_BYTES)


@pytest.mark.parametrize(
    "scenario",
    ["prose_lies_about_write", "wrong_bytes", "extra_write", "deleted_file"],
)
def test_builder_no_write_wrong_bytes_extra_write_and_delete_fail(tmp_path: Path, scenario: str) -> None:
    assert codex_receipt(tmp_path, scenario)["machine_status"] == "FAIL"


@pytest.mark.parametrize("scenario", ["wrong_thread", "wrong_turn"])
def test_builder_wrong_thread_or_turn_fails(tmp_path: Path, scenario: str) -> None:
    receipt = codex_receipt(tmp_path, scenario)
    assert receipt["machine_status"] == "FAIL"
    assert receipt["protocol"]["terminal_binding_valid"] is False


def test_builder_timeout_process_failure_and_malformed_app_server_fail(tmp_path: Path) -> None:
    assert codex_receipt(tmp_path / "timeout", "stall", timeout=1)["timed_out"] is True
    assert codex_receipt(tmp_path / "failed", "turn_failed")["machine_status"] == "FAIL"
    workspace = make_workspace(tmp_path / "malformed")
    receipt = codex_driver.run_role(
        role="BUILDER", workspace=workspace, qntylab_root=ROOT, prompt=b"p",
        workspace_identity=workspace_identity(workspace)["identity_sha256"],
        prompt_template_sha256=sha256_bytes(b"p"), driver_sha256="d" * 64,
        started_marker_sha256="m" * 64, timeout_seconds=2,
        argv=[sys.executable, "-c", "print('not-json')"],
    )
    assert receipt["machine_status"] == "FAIL"


def test_builder_effective_policy_mismatch_fails(tmp_path: Path) -> None:
    receipt = codex_receipt(tmp_path, "effective_policy_downgrade")
    assert receipt["machine_status"] == "FAIL"
    assert receipt["effective_policy"]["contract_match"] is False


def test_builder_wrong_profile_and_api_key_presence_fail_closed(tmp_path: Path) -> None:
    receipt = codex_receipt(tmp_path / "api", "write", environment={"PATH": os.environ["PATH"], "OPENAI_API_KEY": "never-serialize"})
    assert receipt["api_key_gate"] == "FAIL"
    assert receipt["product_started"] is False
    clean = codex_receipt(tmp_path / "profile", "write")
    clean["profile"] = "/home/swirky/.codex-pro2"
    with pytest.raises(QualificationError):
        validate_role_receipt(
            clean, role="BUILDER", workspace=tmp_path / "profile/workspace",
            workspace_id=clean["workspace_identity"], prompt_sha=clean["prompt_sha256"],
            template_sha=clean["prompt_template_sha256"], driver_sha=clean["driver_sha256"],
            marker_sha=clean["started_marker_sha256"],
        )
    assert "never-serialize" not in json.dumps(receipt)


# REVIEWER attacks


def fake_claude_executable(tmp_path: Path) -> Path:
    target = tmp_path / "fake-claude"
    shutil.copy2(FAKE_CLAUDE, target)
    target.chmod(0o700)
    return target


def reviewer_receipt(tmp_path: Path, scenario: str, *, target: bool = True, timeout: int = 5, api_key: bool = False):
    workspace = make_workspace(tmp_path, target=target)
    fake = fake_claude_executable(tmp_path)
    environment = {"PATH": os.environ["PATH"], "FAKE_CLAUDE_SCENARIO": scenario}
    if api_key:
        environment["ANTHROPIC_API_KEY"] = "never-serialize"
    prompt = b"review evidence"
    return claude_driver.run_role(
        workspace=workspace, qntylab_root=ROOT, prompt=prompt,
        workspace_identity=workspace_identity(workspace)["identity_sha256"],
        prompt_template_sha256=sha256_bytes(prompt), driver_sha256="c" * 64,
        started_marker_sha256="m" * 64, timeout_seconds=timeout,
        argv=claude_driver.frozen_argv(str(fake)), environment=environment,
    )


def test_reviewer_valid_pass_and_valid_fail(tmp_path: Path) -> None:
    assert reviewer_receipt(tmp_path / "pass", "pass")["machine_status"] == "PASS"
    failed = reviewer_receipt(tmp_path / "fail", "fail")
    assert failed["machine_status"] == "FAIL"
    assert failed["structured_verdict"]["verdict"] == "FAIL"


@pytest.mark.parametrize("scenario", ["malformed_json", "extra_prose", "missing_field", "wrong_role"])
def test_reviewer_malformed_extra_prose_missing_fields_wrong_role_fail(tmp_path: Path, scenario: str) -> None:
    assert reviewer_receipt(tmp_path, scenario)["machine_status"] == "FAIL"


def test_reviewer_process_nonzero_timeout_mutation_and_api_key_fail(tmp_path: Path) -> None:
    assert reviewer_receipt(tmp_path / "nonzero", "process_failure")["machine_status"] == "FAIL"
    assert reviewer_receipt(tmp_path / "timeout", "timeout", timeout=1)["timed_out"] is True
    mutated = reviewer_receipt(tmp_path / "mutation", "workspace_mutation")
    assert mutated["machine_status"] == "FAIL"
    assert mutated["workspace"]["unauthorized_writes"] == ["reviewer-write.txt"]
    gated = reviewer_receipt(tmp_path / "api", "pass", api_key=True)
    assert gated["product_started"] is False and gated["api_key_gate"] == "FAIL"
    assert "never-serialize" not in json.dumps(gated)


def test_reviewer_false_pass_inconsistent_with_filesystem_fails(tmp_path: Path) -> None:
    receipt = reviewer_receipt(tmp_path, "false_pass", target=False)
    assert receipt["structured_verdict"]["verdict"] == "PASS"
    assert receipt["machine_status"] == "FAIL"


# VERIFIER attacks


def test_verifier_valid_pass_and_valid_fail(tmp_path: Path) -> None:
    passed = codex_receipt(tmp_path / "pass", "verifier_pass", role="VERIFIER")
    assert passed["machine_status"] == "PASS"
    failed = codex_receipt(tmp_path / "fail", "verifier_fail", role="VERIFIER")
    assert failed["machine_status"] == "FAIL"


def test_verifier_malformed_wrong_role_profile_timeout_api_key_and_mutation_fail(tmp_path: Path) -> None:
    assert codex_receipt(tmp_path / "bad", "verifier_malformed", role="VERIFIER")["machine_status"] == "FAIL"
    timeout = codex_receipt(tmp_path / "timeout", "stall", role="VERIFIER", timeout=1)
    assert timeout["timed_out"] is True
    gated = codex_receipt(tmp_path / "api", "verifier_pass", role="VERIFIER", environment={"PATH": os.environ["PATH"], "OPENROUTER_API_KEY": "x"})
    assert gated["product_started"] is False
    assert codex_receipt(tmp_path / "mutation", "verifier_mutation", role="VERIFIER")["machine_status"] == "FAIL"
    assert codex_receipt(tmp_path / "wrong-role", "verifier_wrong_role", role="VERIFIER")["machine_status"] == "FAIL"
    valid = codex_receipt(tmp_path / "role", "verifier_pass", role="VERIFIER")
    valid["role"] = "BUILDER"
    with pytest.raises(QualificationError):
        validate_role_receipt(
            valid, role="VERIFIER", workspace=tmp_path / "role/workspace",
            workspace_id=valid["workspace_identity"], prompt_sha=valid["prompt_sha256"],
            template_sha=valid["prompt_template_sha256"], driver_sha=valid["driver_sha256"],
            marker_sha=valid["started_marker_sha256"],
        )
    valid_profile = codex_receipt(tmp_path / "profile", "verifier_pass", role="VERIFIER")
    valid_profile["profile"] = "/home/swirky/.codex"
    with pytest.raises(QualificationError):
        validate_role_receipt(
            valid_profile, role="VERIFIER", workspace=tmp_path / "profile/workspace",
            workspace_id=valid_profile["workspace_identity"], prompt_sha=valid_profile["prompt_sha256"],
            template_sha=valid_profile["prompt_template_sha256"], driver_sha=valid_profile["driver_sha256"],
            marker_sha=valid_profile["started_marker_sha256"],
        )


def test_verifier_claimed_pass_cannot_override_contradictory_upstream() -> None:
    receipts = {
        "BUILDER": {"machine_status": "FAIL", "api_key_gate": "PASS"},
        "INDEPENDENT_REVIEWER": {"machine_status": "PASS", "api_key_gate": "PASS"},
        "VERIFIER": {"machine_status": "PASS", "api_key_gate": "PASS"},
    }
    assert overall_qualification_pass(receipts, {key: 1 for key in receipts}) is False


# Strict schemas and mutation accounting


def test_strict_role_verdict_schemas_reject_null_unknown_and_prose() -> None:
    reviewer = {
        "role": "INDEPENDENT_REVIEWER", "verdict": "PASS",
        "builder_task_satisfied": True, "changed_paths_match": True, "fixture_match": True,
        "unauthorized_writes": [], "reasons": [],
    }
    verifier = {
        "role": "VERIFIER", "verdict": "PASS", "builder_result_valid": True,
        "reviewer_result_consistent": True, "workspace_matches_contract": True,
        "unauthorized_writes": [], "reasons": [],
    }
    assert parse_reviewer_verdict(canonical_json(reviewer))["verdict"] == "PASS"
    assert parse_verifier_verdict(canonical_json(verifier))["verdict"] == "PASS"
    for mutation in ({**reviewer, "fixture_match": None}, {**reviewer, "extra": True}):
        with pytest.raises(QualificationError):
            parse_reviewer_verdict(mutation)
    with pytest.raises(QualificationError):
        parse_verifier_verdict(json.dumps(verifier) + " success")


def test_symlink_and_empty_directory_are_accounted_without_following(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    before = workspace_snapshot(workspace)
    (workspace / "escape").symlink_to("/etc/passwd")
    (workspace / "empty").mkdir()
    after = workspace_snapshot(workspace)
    assert after["escape"].startswith("SYMLINK:")
    assert after["empty"].startswith("DIR:")
    assert "/etc/passwd" not in after
    assert sorted(set(after) - set(before)) == ["empty", "escape"]


def test_api_key_gate_presence_only() -> None:
    presence = api_key_presence({"OPENAI_API_KEY": "secret"})
    assert presence["OPENAI_API_KEY"] is True
    assert api_key_gate(presence) == "FAIL"
    assert api_key_gate({name: False for name in presence}) == "PASS"


def test_exclusive_write_prevents_receipt_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    write_exclusive_json(path, {"a": 1})
    with pytest.raises(QualificationError):
        write_exclusive_json(path, {"a": 2})
    assert json.loads(path.read_text()) == {"a": 1}


def test_frozen_hash_binding_detects_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "driver.py"
    target.write_text("one")
    require_hashes(tmp_path, {"driver.py": sha256_file(target)})
    target.write_text("two")
    with pytest.raises(QualificationError):
        require_hashes(tmp_path, {"driver.py": sha256_bytes(b"one")})


def test_rendered_prompt_binds_exact_evidence() -> None:
    first = render_evidence_prompt(b"template", {"x": 1})
    second = render_evidence_prompt(b"template", {"x": 2})
    assert first != second and sha256_bytes(first) != sha256_bytes(second)


# CONTROLLER attacks


def make_controller_repo(tmp_path: Path) -> tuple[Path, Path, dict]:
    repo = tmp_path / "repo"
    prompt_root = repo / "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0/prompts"
    prompt_root.mkdir(parents=True)
    for name in ("builder.txt", "reviewer.txt", "verifier.txt"):
        (prompt_root / name).write_bytes((PHASE / "prompts" / name).read_bytes())
    manifest_path = prompt_root.parent / "prelive_freeze.json"
    manifest_path.write_text("{}")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "-c", "user.name=Tests", "-c", "user.email=tests@invalid", "add", ".")
    _git(repo, "-c", "user.name=Tests", "-c", "user.email=tests@invalid", "commit", "-q", "-m", "fixture")
    manifest = {
        "prelive_sha": "a" * 40,
        "hashes": {
            "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0/native_codex_role_driver_v0.py": "d" * 64,
            "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0/claude_reviewer_driver_v0.py": "c" * 64,
        },
    }
    return repo, manifest_path, manifest


def fake_role_receipt(role: str, kwargs: dict, *, pass_role: bool, mutate_builder: bool = True) -> dict:
    workspace = Path(kwargs["workspace"])
    repo = Path(kwargs["qntylab_root"])
    before = workspace_snapshot(workspace)
    git_before = git_metadata_snapshot(workspace)
    fixture_before = fixture_observation(workspace)
    qbefore = qntylab_snapshot(repo)
    if role == "BUILDER" and pass_role and mutate_builder:
        (workspace / "fixture.txt").write_bytes(FIXTURE_TARGET_BYTES)
    observed = _workspace_receipt(workspace, before, git_before, fixture_before)
    qafter = qntylab_snapshot(repo)
    if role == "BUILDER":
        structured = {"role": role, "verdict": "PASS" if pass_role else "FAIL"}
    elif role == "INDEPENDENT_REVIEWER":
        structured = {
            "role": role, "verdict": "PASS" if pass_role else "FAIL",
            "builder_task_satisfied": pass_role, "changed_paths_match": pass_role,
            "fixture_match": pass_role, "unauthorized_writes": [],
            "reasons": [] if pass_role else ["rejected"],
        }
    else:
        structured = {
            "role": role, "verdict": "PASS" if pass_role else "FAIL",
            "builder_result_valid": pass_role, "reviewer_result_consistent": pass_role,
            "workspace_matches_contract": pass_role, "unauthorized_writes": [],
            "reasons": [] if pass_role else ["rejected"],
        }
    return _base_receipt(
        role=role, version=("2.1.223 (Claude Code)" if role == "INDEPENDENT_REVIEWER" else "codex-cli 0.147.0"), cwd=workspace,
        workspace_id=kwargs["workspace_identity"], prompt=kwargs["prompt"],
        template_sha=kwargs["prompt_template_sha256"], driver_sha=kwargs["driver_sha256"],
        marker_sha=kwargs["started_marker_sha256"], started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:00:01Z", timeout_seconds=kwargs["timeout_seconds"],
        timed_out=False, product_started=True,
        process_exit={"disposed": True, "termination": ("EXITED" if role == "INDEPENDENT_REVIEWER" else "ALREADY_EXITED"), "exit_code": 0, "exit_signal": 0},
        lifecycle="COMPLETED", protocol={"terminal_binding_valid": True},
        effective_policy={"contract_match": True}, workspace=observed,
        qntylab_before=qbefore, qntylab_after=qafter, gate="PASS", structured=structured,
        machine_status="PASS" if pass_role else "FAIL",
        failure_class="NONE" if pass_role else f"{role}_PRODUCT_FAILURE",
    )


def run_controller_case(tmp_path: Path, monkeypatch, outcomes: dict[str, object]):
    repo, manifest_path, manifest = make_controller_repo(tmp_path)
    monkeypatch.setattr(controller, "validate_prelive_manifest", lambda *_: manifest)
    calls: list[str] = []

    def codex_runner(**kwargs):
        role = kwargs["role"]
        calls.append(role)
        marker = manifest_path.parent / "live_batch_v0" / controller.ROLE_FILENAMES[role][0]
        assert marker.is_file(), "product runner started before durable marker"
        outcome = outcomes[role]
        if outcome == "CRASH":
            raise QualificationError("crash")
        return fake_role_receipt(role, kwargs, pass_role=bool(outcome))

    def claude_runner(**kwargs):
        role = "INDEPENDENT_REVIEWER"
        calls.append(role)
        marker = manifest_path.parent / "live_batch_v0" / controller.ROLE_FILENAMES[role][0]
        assert marker.is_file(), "product runner started before durable marker"
        outcome = outcomes[role]
        if outcome == "CRASH":
            raise QualificationError("crash")
        return fake_role_receipt(role, kwargs, pass_role=bool(outcome))

    result = controller.execute_batch(
        repo_root=repo, prelive_manifest_path=manifest_path,
        codex_runner=codex_runner, claude_runner=claude_runner,
    )
    return result, calls, manifest_path


def test_controller_full_pass_exactly_once_and_markers_precede_products(tmp_path: Path, monkeypatch) -> None:
    result, calls, manifest_path = run_controller_case(tmp_path, monkeypatch, {role: True for role in controller.ROLE_FILENAMES})
    assert calls == ["BUILDER", "INDEPENDENT_REVIEWER", "VERIFIER"]
    assert result["qualification_pass"] is True
    assert result["role_attempts"] == {role: 1 for role in controller.ROLE_FILENAMES}
    live = manifest_path.parent / "live_batch_v0"
    assert all((live / names[0]).is_file() for names in controller.ROLE_FILENAMES.values())
    with pytest.raises(QualificationError):
        controller.execute_batch(repo_root=manifest_path.parents[4], prelive_manifest_path=manifest_path)


@pytest.mark.parametrize(
    "outcomes,expected_calls,expected_attempts",
    [
        ({"BUILDER": False, "INDEPENDENT_REVIEWER": True, "VERIFIER": True}, ["BUILDER"], {"BUILDER": 1, "INDEPENDENT_REVIEWER": 0, "VERIFIER": 0}),
        ({"BUILDER": "CRASH", "INDEPENDENT_REVIEWER": True, "VERIFIER": True}, ["BUILDER"], {"BUILDER": 1, "INDEPENDENT_REVIEWER": 0, "VERIFIER": 0}),
        ({"BUILDER": True, "INDEPENDENT_REVIEWER": False, "VERIFIER": True}, ["BUILDER", "INDEPENDENT_REVIEWER"], {"BUILDER": 1, "INDEPENDENT_REVIEWER": 1, "VERIFIER": 0}),
        ({"BUILDER": True, "INDEPENDENT_REVIEWER": "CRASH", "VERIFIER": True}, ["BUILDER", "INDEPENDENT_REVIEWER"], {"BUILDER": 1, "INDEPENDENT_REVIEWER": 1, "VERIFIER": 0}),
        ({"BUILDER": True, "INDEPENDENT_REVIEWER": True, "VERIFIER": "CRASH"}, ["BUILDER", "INDEPENDENT_REVIEWER", "VERIFIER"], {"BUILDER": 1, "INDEPENDENT_REVIEWER": 1, "VERIFIER": 1}),
    ],
)
def test_controller_fail_closed_dependency_and_crash_markers(tmp_path: Path, monkeypatch, outcomes, expected_calls, expected_attempts) -> None:
    result, calls, _ = run_controller_case(tmp_path, monkeypatch, outcomes)
    assert result["qualification_pass"] is False
    assert calls == expected_calls
    assert result["role_attempts"] == expected_attempts


def test_stale_receipt_prompt_driver_workspace_and_role_laundering_rejected(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path, target=True)
    kwargs = {
        "workspace": workspace, "qntylab_root": ROOT, "prompt": b"p",
        "workspace_identity": workspace_identity(workspace)["identity_sha256"],
        "prompt_template_sha256": "t" * 64, "driver_sha256": "d" * 64,
        "started_marker_sha256": "m" * 64, "timeout_seconds": 180,
    }
    receipt = fake_role_receipt("VERIFIER", kwargs, pass_role=True)
    base = dict(
        receipt=receipt, role="VERIFIER", workspace=workspace,
        workspace_id=kwargs["workspace_identity"], prompt_sha=sha256_bytes(b"p"),
        template_sha="t" * 64, driver_sha="d" * 64, marker_sha="m" * 64,
    )
    validate_role_receipt(**base)
    for field, value in (
        ("workspace_id", "w" * 64), ("prompt_sha", "p" * 64),
        ("driver_sha", "x" * 64), ("marker_sha", "s" * 64), ("role", "BUILDER"),
    ):
        mutated = dict(base)
        mutated[field] = value
        with pytest.raises(QualificationError):
            validate_role_receipt(**mutated)


def test_result_never_passes_without_all_three_machine_passes() -> None:
    good = {role: {"machine_status": "PASS", "api_key_gate": "PASS"} for role in controller.ROLE_FILENAMES}
    attempts = {role: 1 for role in controller.ROLE_FILENAMES}
    assert overall_qualification_pass(good, attempts) is True
    for role in controller.ROLE_FILENAMES:
        bad = {key: dict(value) for key, value in good.items()}
        bad[role]["machine_status"] = "FAIL"
        assert overall_qualification_pass(bad, attempts) is False
    assert overall_qualification_pass(good, {**attempts, "VERIFIER": 0}) is False
