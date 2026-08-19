from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import threading
from pathlib import Path

import pytest

import qntylab.pinned_dsh_codex_write_path_materialization_v0r1 as contract
from qntylab.pinned_dsh_codex_write_path_materialization_v0r1 import (
    CODEX_BINARY,
    CODEX_HOME,
    D4_ROUTE_MARKER,
    FROZEN_DSH_ROOT,
    MATERIALIZATION_SCHEMA,
    MAX_LIVE_ATTEMPTS,
    PHASE_ID,
    REQUIRED_RUNTIME_ARTIFACTS,
    RUNTIME_CLOSURE_SCHEMA,
    RuntimeClosureError,
    acquire_episode_marker,
    api_key_gate,
    classify_d4,
    final_execution_gate,
    parse_d4_stdout,
    receipt_pass_reasons,
    runtime_closure,
    validate_materialization_record,
)
from qntylab.subscription_backed_product_execution_plumbing_v0 import (
    API_KEY_NAMES,
    QualificationError,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = (
    REPO_ROOT
    / "experiments/research/qnty_agent_orchestration_control_contract_v0"
    / "pinned_dsh_codex_write_path_materialization_v0r1"
)
RUNNER = PHASE_DIR / "run_pinned_dsh_d4_v0r1.py"
MATERIALIZATION_RECORD = PHASE_DIR / "materialization_record.json"
RUNTIME_MANIFEST = PHASE_DIR / "runtime_closure_manifest.json"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _runtime_root(root: Path) -> Path:
    for index, relpath in enumerate(REQUIRED_RUNTIME_ARTIFACTS):
        dependency = "import './dep.js'\n" if index == 0 else ""
        _write(root / relpath, dependency + f"export const value{index} = {index}\n")
    _write(Path(root) / Path(REQUIRED_RUNTIME_ARTIFACTS[0]).parent / "dep.js", "export const dep = 1\n")
    _write(root / "pnpm-lock.yaml", "frozen-lock\n")
    return root


def _expected_closure(value: dict) -> dict:
    return {
        "schema_version": value["schema_version"],
        "entrypoints": value["entrypoints"],
        "files": value["files"],
        "digest": value["digest"],
        "root": value["root"],
    }


# ---------------------------------------------------------------------------
# C1: final execution-byte binding and hostile path cases.
# ---------------------------------------------------------------------------


def test_c1_changed_entrypoint_changes_the_closure(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path / "dsh")
    before = runtime_closure(root)
    entrypoint = root / REQUIRED_RUNTIME_ARTIFACTS[1]
    entrypoint.write_text("export const changed = true\n", encoding="utf-8")
    after = runtime_closure(root)
    assert before["digest"] != after["digest"]
    assert before["files"] != after["files"]


def test_c1_rejects_symlink_runtime_artifact(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path / "dsh")
    entrypoint = root / REQUIRED_RUNTIME_ARTIFACTS[0]
    target = tmp_path / "target.js"
    target.write_text(entrypoint.read_text(), encoding="utf-8")
    entrypoint.unlink()
    entrypoint.symlink_to(target)
    with pytest.raises(RuntimeClosureError, match="symlink"):
        runtime_closure(root)


def test_c1_rejects_symlink_retarget_between_observation_and_gate(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path / "dsh")
    observed = runtime_closure(root)
    entrypoint = root / REQUIRED_RUNTIME_ARTIFACTS[2]
    first = tmp_path / "first.js"
    second = tmp_path / "second.js"
    first.write_text(entrypoint.read_text(), encoding="utf-8")
    second.write_text("export const hostile = true\n", encoding="utf-8")
    entrypoint.unlink()
    entrypoint.symlink_to(first)
    entrypoint.unlink()
    entrypoint.symlink_to(second)
    with pytest.raises(RuntimeClosureError, match="symlink"):
        runtime_closure(Path(observed["root"]))


def test_c1_rejects_missing_runtime_artifact(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path / "dsh")
    (root / REQUIRED_RUNTIME_ARTIFACTS[3]).unlink()
    with pytest.raises(RuntimeClosureError, match="missing"):
        runtime_closure(root)


def test_c1_rejects_path_escape(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path / "dsh")
    (tmp_path / "outside.js").write_text("export default 1\n", encoding="utf-8")
    with pytest.raises(RuntimeClosureError, match="escapes"):
        runtime_closure(root, entrypoints=("../outside.js",))


def test_c1_extra_local_generated_dependency_drift_changes_closure(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path / "dsh")
    before = runtime_closure(root)
    dependency = root / Path(REQUIRED_RUNTIME_ARTIFACTS[0]).parent / "dep.js"
    assert dependency.relative_to(root).as_posix() in before["files"]
    dependency.write_text("export const dep = 999\n", encoding="utf-8")
    after = runtime_closure(root)
    assert before["digest"] != after["digest"]


def test_c1_final_gate_rejects_wrong_dsh_root(tmp_path: Path) -> None:
    first = _runtime_root(tmp_path / "one")
    second = _runtime_root(tmp_path / "two")
    expected = runtime_closure(first)
    gate = final_execution_gate(
        dsh_root=second,
        expected_root=first,
        expected_closure=expected,
        record_path=tmp_path / "missing-record.json",
        source_record_path=tmp_path / "missing-source.json",
        node_version="v22.22.0",
        pnpm_version="11.7.0",
    )
    assert gate["passed"] is False
    assert gate["runtime_closure_match"] is False
    assert "wrong DSH root" in gate["reason"]


def test_c1_runner_binds_even_a_consistently_supplied_root_to_frozen_root() -> None:
    text = RUNNER.read_text()
    assert 'FROZEN_DSH_ROOT = Path("/home/swirky/DevHub/dsh-pinned-materialization-v0")' in (
        REPO_ROOT / "qntylab/pinned_dsh_codex_write_path_materialization_v0r1.py"
    ).read_text()
    assert "resolve_dsh_root(requested_root, expected_root=FROZEN_DSH_ROOT)" in text
    assert FROZEN_DSH_ROOT == Path("/home/swirky/DevHub/dsh-pinned-materialization-v0")


def test_c1_final_gate_detects_bytes_changed_after_initial_observation(tmp_path: Path) -> None:
    root = _runtime_root(tmp_path / "dsh")
    expected = runtime_closure(root)
    (root / REQUIRED_RUNTIME_ARTIFACTS[0]).write_text("export const afterObservation = true\n")
    gate = final_execution_gate(
        dsh_root=root,
        expected_root=root,
        expected_closure=expected,
        record_path=tmp_path / "missing-record.json",
        source_record_path=tmp_path / "missing-source.json",
        node_version="v22.22.0",
        pnpm_version="11.7.0",
    )
    assert gate["passed"] is False
    assert gate["runtime_closure_match"] is False


def test_c1_frozen_manifest_matches_the_live_known_checkout_when_present() -> None:
    root = Path("/home/swirky/DevHub/dsh-pinned-materialization-v0")
    if not root.is_dir():
        pytest.skip("known pinned checkout is not present")
    observed = runtime_closure(root)
    manifest = json.loads(RUNTIME_MANIFEST.read_text())
    assert observed["files"] == manifest["files"] == dict(contract.FROZEN_RUNTIME_CLOSURE_FILES)
    assert observed["digest"] == manifest["digest"] == contract.FROZEN_RUNTIME_CLOSURE_DIGEST
    assert len(observed["files"]) > len(REQUIRED_RUNTIME_ARTIFACTS)


# ---------------------------------------------------------------------------
# H1: exact materialization record schema and live evidence binding.
# ---------------------------------------------------------------------------


@pytest.fixture
def binding_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    root = _runtime_root(tmp_path / "dsh")
    closure = runtime_closure(root)
    lock_digest = hashlib.sha256((root / "pnpm-lock.yaml").read_bytes()).hexdigest()
    source = tmp_path / "source-record.json"
    source.write_text('{"source":true}\n', encoding="utf-8")
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(contract, "LOCKFILE_SHA256", lock_digest)
    monkeypatch.setattr(contract, "FROZEN_RUNTIME_CLOSURE_FILES", closure["files"])
    monkeypatch.setattr(contract, "FROZEN_RUNTIME_CLOSURE_DIGEST", closure["digest"])
    monkeypatch.setattr(contract, "SOURCE_MATERIALIZATION_RECORD_SHA256", source_digest)
    identity = {
        "root": str(root.resolve()),
        "commit": contract.DSH_COMMIT,
        "tree": contract.DSH_TREE,
        "tag": contract.DSH_TAG,
        "matches": True,
    }
    record = {
        "schema_version": MATERIALIZATION_SCHEMA,
        "phase_id": PHASE_ID,
        "dsh": {
            "repository": contract.DSH_REPOSITORY,
            "commit": contract.DSH_COMMIT,
            "tree": contract.DSH_TREE,
            "tag": contract.DSH_TAG,
        },
        "lockfile_sha256": lock_digest,
        "node": {"version": "v22.22.0", "range": contract.DSH_NODE_ENGINES},
        "pnpm": {"version": "11.7.0"},
        "build": {"target": contract.DSH_BUILD_TARGET, "success": True},
        "install": {"success": True, "frozen_lockfile": True},
        "runtime_closure": {
            "schema_version": RUNTIME_CLOSURE_SCHEMA,
            "entrypoints": list(REQUIRED_RUNTIME_ARTIFACTS),
            "files": closure["files"],
            "digest": closure["digest"],
        },
        "source_record_sha256": source_digest,
    }
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    return {
        "root": root,
        "closure": closure,
        "source": source,
        "identity": identity,
        "record": record,
        "record_path": record_path,
    }


def _validate_case(case: dict, record_path: Path | None = None) -> dict:
    return validate_materialization_record(
        record_path or case["record_path"],
        source_record_path=case["source"],
        dsh_root=case["root"],
        closure=case["closure"],
        identity=case["identity"],
        node_version="v22.22.0",
        pnpm_version="11.7.0",
    )


def _mutated_record(case: dict, mutate) -> Path:
    value = copy.deepcopy(case["record"])
    mutate(value)
    destination = case["record_path"].with_name("mutated.json")
    destination.write_text(json.dumps(value), encoding="utf-8")
    return destination


def test_h1_valid_exact_record_passes(binding_case: dict) -> None:
    assert _validate_case(binding_case)["passed"] is True


def test_h1_missing_and_malformed_records_fail(binding_case: dict) -> None:
    missing = binding_case["record_path"].with_name("missing.json")
    assert _validate_case(binding_case, missing)["passed"] is False
    malformed = binding_case["record_path"].with_name("malformed.json")
    malformed.write_text("{", encoding="utf-8")
    assert _validate_case(binding_case, malformed)["reasons"] == ["MATERIALIZATION_RECORD_MALFORMED"]


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda value: value.__setitem__("phase_id", "STALE"), "MATERIALIZATION_RECORD_PHASE_MISMATCH"),
        (lambda value: value["dsh"].__setitem__("commit", "0" * 40), "MATERIALIZATION_RECORD_DSH_IDENTITY_MISMATCH"),
        (lambda value: value["dsh"].__setitem__("tree", "0" * 40), "MATERIALIZATION_RECORD_DSH_IDENTITY_MISMATCH"),
        (lambda value: value.__setitem__("lockfile_sha256", "0" * 64), "RECORDED_LOCKFILE_DIGEST_MISMATCH"),
        (lambda value: value["pnpm"].__setitem__("version", "99.0.0"), "RECORDED_OR_LIVE_PNPM_MISMATCH"),
        (lambda value: value["node"].__setitem__("version", "v20.0.0"), "RECORDED_NODE_MISMATCH"),
        (lambda value: value["build"].__setitem__("target", "build:web"), "BUILD_TARGET_MISMATCH"),
        (lambda value: value["install"].__setitem__("success", False), "INSTALL_NOT_SUCCESSFUL"),
        (lambda value: value["build"].__setitem__("success", False), "BUILD_NOT_SUCCESSFUL"),
        (lambda value: value["runtime_closure"]["files"].__setitem__(next(iter(value["runtime_closure"]["files"])), "f" * 64), "RECORDED_RUNTIME_CLOSURE_MISMATCH"),
    ],
)
def test_h1_attack_records_fail(binding_case: dict, mutate, reason: str) -> None:
    result = _validate_case(binding_case, _mutated_record(binding_case, mutate))
    assert result["passed"] is False
    assert reason in result["reasons"]


def test_h1_unknown_field_fails_exact_schema(binding_case: dict) -> None:
    result = _validate_case(
        binding_case,
        _mutated_record(binding_case, lambda value: value.__setitem__("success_by_prose", True)),
    )
    assert "MATERIALIZATION_RECORD_TOP_LEVEL_SCHEMA_MISMATCH" in result["reasons"]


def test_h1_changed_source_record_bytes_fail(binding_case: dict) -> None:
    binding_case["source"].write_text('{"source":"changed"}\n', encoding="utf-8")
    result = _validate_case(binding_case)
    assert "SOURCE_MATERIALIZATION_RECORD_BYTES_MISMATCH" in result["reasons"]


# ---------------------------------------------------------------------------
# H2/H5: strict receipt schema and route-bound provenance.
# ---------------------------------------------------------------------------


def _receipt(root: Path, **updates) -> dict:
    value = {
        "status": "COMPLETED",
        "output": "NO_AGENT_OUTPUT",
        "lifecycle": {"ends": [{"stopReason": "completed"}]},
        "processes": [{"signal": "SIGTERM"}],
        "parentLlmProvider": "NONE",
        "parentLlmRequestCount": 0,
        "route": D4_ROUTE_MARKER,
        "startedAt": "2026-08-19T00:00:00Z",
        "endedAt": "2026-08-19T00:00:01Z",
        "timedOut": False,
        "error": None,
        "observed": {
            "requestedCwd": str(root),
            "codexHome": CODEX_HOME,
            "pathPrefix": str(Path(CODEX_BINARY).parent),
            "dshRoot": str(root),
            "childEnvKeys": ["CODEX_HOME", "PATH"],
            "providerName": "codex",
            "promptSha256": "a" * 64,
        },
        "outputPartCount": 0,
        "stdoutSha256": "b" * 64,
        "stderrSha256": "c" * 64,
        "apiKeyPresence": {name: False for name in API_KEY_NAMES},
        "bridgeExitCode": 0,
    }
    value.update(updates)
    return value


_CODEX_CHILD = [{"argv": [CODEX_BINARY, "app-server", "--stdio"], "depth": 1}]


def _classify(root: Path, receipt: dict | None) -> dict:
    return classify_d4(
        gates_passed=True,
        gate_reason=None,
        receipt=receipt,
        descendants=_CODEX_CHILD,
        fixture_before_class="BEFORE",
        fixture_after_class="AFTER",
        changed=["fixture.txt"],
        marker_acquired=True,
        expected_dsh_root=root,
    )


def test_h2_strict_positive_receipt_is_the_only_pass(tmp_path: Path) -> None:
    root = tmp_path / "dsh"
    root.mkdir()
    classification = _classify(root, _receipt(root))
    assert classification["d4"] == "PASS"
    assert classification["target_mechanism_exercised"] is True


def test_h2_absent_error_is_allowed_as_clean(tmp_path: Path) -> None:
    root = tmp_path / "dsh"
    root.mkdir()
    receipt = _receipt(root)
    del receipt["error"]
    assert receipt_pass_reasons(receipt, expected_dsh_root=root) == []


@pytest.mark.parametrize(
    "attack",
    [
        "exit_missing", "exit_null", "exit_string", "exit_nonzero",
        "malformed_end", "missing_stop", "one_error", "empty_ends",
        "wrong_route", "wrong_status", "nonnull_error", "parent_provider",
        "parent_count", "credential_present",
        "unknown_lifecycle_key", "unknown_end_key",
    ],
)
def test_h2_no_malformed_or_contradictory_receipt_can_pass(tmp_path: Path, attack: str) -> None:
    root = tmp_path / "dsh"
    root.mkdir()
    receipt = _receipt(root)
    if attack == "exit_missing":
        del receipt["bridgeExitCode"]
    elif attack == "exit_null":
        receipt["bridgeExitCode"] = None
    elif attack == "exit_string":
        receipt["bridgeExitCode"] = "0"
    elif attack == "exit_nonzero":
        receipt["bridgeExitCode"] = 1
    elif attack == "malformed_end":
        receipt["lifecycle"] = {"ends": ["completed"]}
    elif attack == "missing_stop":
        receipt["lifecycle"] = {"ends": [{}]}
    elif attack == "one_error":
        receipt["lifecycle"] = {"ends": [{"stopReason": "completed"}, {"stopReason": "error"}]}
    elif attack == "empty_ends":
        receipt["lifecycle"] = {"ends": []}
    elif attack == "wrong_route":
        receipt["route"] = "UNRELATED"
    elif attack == "wrong_status":
        receipt["status"] = "FAIL_CLOSED"
    elif attack == "nonnull_error":
        receipt["error"] = "boom"
    elif attack == "parent_provider":
        receipt["parentLlmProvider"] = "deepseek"
    elif attack == "parent_count":
        receipt["parentLlmRequestCount"] = 1
    elif attack == "credential_present":
        receipt["apiKeyPresence"]["OPENAI_API_KEY"] = True
    elif attack == "unknown_lifecycle_key":
        receipt["lifecycle"]["unknown"] = True
    elif attack == "unknown_end_key":
        receipt["lifecycle"]["ends"][0]["unknown"] = True
    classification = _classify(root, receipt)
    assert classification["d4"] != "PASS"


def test_h2_empty_credential_value_is_present_and_blocks_gate() -> None:
    gate = api_key_gate({"OPENAI_API_KEY": ""})
    assert gate["presence"]["OPENAI_API_KEY"] is True
    assert gate["passed"] is False


def test_h2_runner_receipt_credential_schema_is_exactly_four_api_names() -> None:
    runner = _load_runner()
    assert set(runner.api_key_gate({})["presence"]) == set(API_KEY_NAMES)
    text = RUNNER.read_text()
    assert 'presence = api_key_gate()["presence"]' in text


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"not json\n",
        b'{"hello":"world"}\n',
        b'{"route":"WRONG","status":"COMPLETED"}\n',
        b"42\n",
        b"[]\n",
        b'{"a":1}\n{"b":2}\n',
        b"driver crashed before output",
    ],
)
def test_h5_unrelated_or_unparseable_output_is_not_d4_evidence(payload: bytes, tmp_path: Path) -> None:
    parsed = parse_d4_stdout(payload)
    assert parsed["receipt"] is None
    root = tmp_path / "dsh"
    root.mkdir()
    classification = _classify(root, parsed["receipt"])
    assert classification["d4"] == "INCONCLUSIVE_INFRA"
    assert classification["target_mechanism_exercised"] is False
    assert classification["dsh_provider_entered"] is False
    assert classification["turn_started"] is False


def test_h5_multiple_route_objects_are_ambiguous_not_product_evidence(tmp_path: Path) -> None:
    raw = json.dumps(_receipt(tmp_path)) + "\n" + json.dumps(_receipt(tmp_path)) + "\n"
    parsed = parse_d4_stdout(raw.encode())
    assert parsed["receipt"] is None
    assert parsed["reason"] == "MULTIPLE_D4_ROUTE_OBJECTS"


def test_h5_route_marker_without_structural_provenance_is_infrastructure(tmp_path: Path) -> None:
    root = tmp_path / "dsh"
    root.mkdir()
    classification = _classify(root, {"route": D4_ROUTE_MARKER, "status": "COMPLETED"})
    assert classification["d4"] == "INCONCLUSIVE_INFRA"
    assert classification["target_mechanism_exercised"] is False
    assert classification["dsh_provider_entered"] is False


# ---------------------------------------------------------------------------
# H3: durable, exclusive, never-cleared episode consumption.
# ---------------------------------------------------------------------------


def _acquire(tmp_path: Path) -> dict:
    return acquire_episode_marker(
        tmp_path / "started.json",
        attempt_path=tmp_path / "attempts.jsonl",
        receipt_path=tmp_path / "receipt.json",
        payload={"phase_id": PHASE_ID, "attempt": 1},
    )


def test_h3_clean_first_acquisition_is_durable_and_second_is_refused(tmp_path: Path) -> None:
    first = _acquire(tmp_path)
    assert first["acquired"] is True
    assert (tmp_path / "started.json").is_file()
    with pytest.raises(QualificationError, match="already consumed"):
        _acquire(tmp_path)


def test_h3_crash_immediately_after_acquisition_still_consumes(tmp_path: Path) -> None:
    _acquire(tmp_path)
    # Simulated crash: no attempt and no receipt is created, marker persists.
    assert not (tmp_path / "attempts.jsonl").exists()
    assert not (tmp_path / "receipt.json").exists()
    with pytest.raises(QualificationError, match="CONSUMED_MARKER"):
        _acquire(tmp_path)


@pytest.mark.parametrize("existing", ["attempts.jsonl", "receipt.json", "started.json"])
def test_h3_any_prior_episode_evidence_prohibits_acquisition(tmp_path: Path, existing: str) -> None:
    (tmp_path / existing).write_text("{}\n", encoding="utf-8")
    with pytest.raises(QualificationError, match="already consumed"):
        _acquire(tmp_path)


def test_h3_concurrent_acquisition_has_exactly_one_winner(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)
    successes: list[dict] = []
    failures: list[Exception] = []

    def contender() -> None:
        barrier.wait()
        try:
            successes.append(_acquire(tmp_path))
        except Exception as exc:  # captured for deterministic assertion
            failures.append(exc)

    threads = [threading.Thread(target=contender) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], QualificationError)


# ---------------------------------------------------------------------------
# Narrow H4/H6/H7 regressions and structural one-call proof.
# ---------------------------------------------------------------------------


def _load_runner():
    spec = importlib.util.spec_from_file_location("_v0r1_runner_test", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_h4_timeout_remains_product_fail_only_for_valid_product_receipt(tmp_path: Path) -> None:
    root = tmp_path / "dsh"
    root.mkdir()
    receipt = _receipt(
        root,
        status="FAIL_CLOSED",
        timedOut=True,
        lifecycle={"ends": [{"stopReason": "timeout"}]},
    )
    classification = _classify(root, receipt)
    assert classification["d4"] == "FAIL"
    assert classification["failure_mechanism"] == "DSH_CODEX_TURN_TIMEOUT"
    assert classification["turn_terminal_observed"] is False


def test_h6_runner_preserves_process_group_termination_contract() -> None:
    text = RUNNER.read_text()
    assert "start_new_session=True" in text
    assert "_terminate_tree(process)" in text
    assert "process.communicate(timeout=15.0)" in text


def test_h7_profile_observation_remains_read_only(tmp_path: Path) -> None:
    runner = _load_runner()
    observation = runner.observe_profile(tmp_path)
    assert observation["codex_home"] == CODEX_HOME
    assert "config_sha256_before" in observation
    assert "access_token" not in json.dumps(observation)
    text = RUNNER.read_text()
    assert "config.toml\").write" not in text


def test_runner_has_one_live_call_after_marker_attempt_and_final_gate() -> None:
    tree = ast.parse(RUNNER.read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_driver_observed"
    ]
    assert len(calls) == 1
    for loop in [node for node in ast.walk(tree) if isinstance(node, (ast.For, ast.While, ast.AsyncFor))]:
        assert calls[0] not in list(ast.walk(loop))
    text = RUNNER.read_text()
    assert text.index("acquire_episode_marker(") < text.index("run_driver_observed(", text.index("def main"))
    assert text.index("_append_attempt(", text.index("def main")) < text.index("run_driver_observed(", text.index("def main"))
    assert text.index("final_execution_gate(", text.index("def main")) < text.index("run_driver_observed(", text.index("def main"))
    assert "HARD_TIMEOUT_SECONDS = 300.0" in text
    assert "unlink(CONSUMED_MARKER_PATH" not in text
    assert "attempts\": 1 if marker[\"acquired\"] else 0" in text
    assert MAX_LIVE_ATTEMPTS == 1


def test_checked_in_materialization_record_matches_known_checkout_when_present() -> None:
    root = Path("/home/swirky/DevHub/dsh-pinned-materialization-v0")
    if not root.is_dir():
        pytest.skip("known pinned checkout is not present")
    source = PHASE_DIR.parent / "pinned_dsh_codex_write_path_materialization_v0/materialization_record.json"
    result = validate_materialization_record(
        MATERIALIZATION_RECORD,
        source_record_path=source,
        dsh_root=root,
        closure=runtime_closure(root),
        identity=contract.dsh_identity(root),
        node_version="v22.22.0",
        pnpm_version="11.7.0",
    )
    assert result["passed"] is True, result
