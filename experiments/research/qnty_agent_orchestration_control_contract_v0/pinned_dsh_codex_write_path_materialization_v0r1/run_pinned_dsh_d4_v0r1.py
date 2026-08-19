#!/usr/bin/env python3
"""Exactly-once V0R1 live runner for the frozen pinned DSH Codex D4 route.

The product call is unreachable until the durable episode marker, append-only
attempt record, final runtime-closure byte gate, materialization binding, and
identity gates all pass.  V0 evidence and its frozen driver are read-only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from qntylab.pinned_dsh_codex_write_path_materialization_v0r1 import (  # noqa: E402
    CODEX_BINARY,
    CODEX_HOME,
    D4_DRIVER_RELPATH,
    D4_ROUTE_MARKER,
    D4_TURN_TIMEOUT_SECONDS,
    FROZEN_DSH_ROOT,
    FROZEN_RUNTIME_CLOSURE_DIGEST,
    FROZEN_RUNTIME_CLOSURE_FILES,
    MAX_LIVE_ATTEMPTS,
    PHASE_ID,
    RECEIPT_SCHEMA,
    SOURCE_MATERIALIZATION_RECORD_SHA256,
    acquire_episode_marker,
    api_key_gate,
    classify_d4,
    codex_identity,
    downstream_authority,
    driver_identity,
    dsh_identity,
    final_execution_gate,
    identity_gate,
    parse_d4_stdout,
    phase_verdict,
    resolve_dsh_root,
    runtime_closure,
    validate_materialization_record,
)
from qntylab.pinned_dsh_codex_write_path_materialization_v0 import (  # noqa: E402
    REQUIRED_RUNTIME_ARTIFACTS,
)
from qntylab.subscription_backed_codex_app_server_write_path_diagnostic_v0 import (  # noqa: E402
    WRITE_PROMPT,
    build_workspace,
    destroy_workspace,
    fixture_state,
)
from qntylab.subscription_backed_product_execution_plumbing_v0 import (  # noqa: E402
    ProductInvocation,
    QualificationError,
    changed_paths,
    sanitize_environment,
    sha256_bytes,
    sha256_file,
    utc_now,
    workspace_snapshot,
)

DEFAULT_DSH_ROOT = FROZEN_DSH_ROOT
MATERIALIZATION_RECORD = _HERE / "materialization_record.json"
SOURCE_MATERIALIZATION_RECORD = (
    _HERE.parent / "pinned_dsh_codex_write_path_materialization_v0" / "materialization_record.json"
)
CONSUMED_MARKER_PATH = _HERE / "d4_episode_started.json"
ATTEMPT_LOG_PATH = _HERE / "d4_attempts.jsonl"
RECEIPT_PATH = _HERE / "d4_receipt.json"
HARD_TIMEOUT_SECONDS = 300.0

_V0_RUNNER = (
    _HERE.parent / "pinned_dsh_codex_write_path_materialization_v0" / "run_pinned_dsh_d4_v0.py"
)
_SPEC = importlib.util.spec_from_file_location("_qntylab_pinned_dsh_v0_runner", _V0_RUNNER)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - repository invariant
    raise RuntimeError("cannot load immutable V0 runner helpers")
_V0 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_V0)
DescendantSampler = _V0.DescendantSampler
_terminate_tree = _V0._terminate_tree
observe_profile = _V0.observe_profile


def _tool_version(argv: list[str], cwd: Path) -> str:
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, check=False
    ).stdout.strip()


def _episode_artifacts_present() -> list[str]:
    return [
        str(path)
        for path in (CONSUMED_MARKER_PATH, ATTEMPT_LOG_PATH, RECEIPT_PATH)
        if os.path.lexists(path)
    ]


def _append_attempt(record: dict[str, Any]) -> None:
    with ATTEMPT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_receipt(record: dict[str, Any]) -> None:
    data = (json.dumps(record, indent=2, sort_keys=True, default=str) + "\n").encode()
    temporary = RECEIPT_PATH.with_suffix(".json.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, RECEIPT_PATH)


def run_driver_observed(
    argv: list[str], invocation: ProductInvocation, *, timeout_seconds: float
) -> tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]], int]:
    """Run one driver process and accept only one exact-route JSON object."""

    invocation.validate()
    clean_env, _sanitizer_presence = sanitize_environment()
    # The receipt contract covers exactly the four pay-per-token API names.
    # Membership, including an empty-valued variable, counts as present.
    presence = api_key_gate()["presence"]
    clean_env["QNTYLAB_PRODUCT_CWD"] = str(invocation.cwd.resolve())
    clean_env["QNTYLAB_WORKSPACE_SCOPE"] = str(invocation.workspace_scope.resolve())
    clean_env["QNTYLAB_PROFILE"] = invocation.profile

    process = subprocess.Popen(
        argv,
        cwd=invocation.cwd,
        env=clean_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    sampler = DescendantSampler(process.pid)
    sampler.start()
    stdout = stderr = b""
    wall_clock_exceeded = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        wall_clock_exceeded = True
        _terminate_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=15.0)
        except subprocess.TimeoutExpired:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    finally:
        sampler.stop()
        sampler.join(timeout=5.0)

    transport = {
        "state": "DRIVER_WALL_CLOCK_EXCEEDED" if wall_clock_exceeded else "DRIVER_EXITED",
        "wall_clock_exceeded": wall_clock_exceeded,
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "bridge_exit_code": process.returncode,
        "api_key_presence": presence,
    }
    if wall_clock_exceeded:
        return None, transport, sampler.snapshot(), sampler.samples

    parsed = parse_d4_stdout(stdout)
    transport["receipt_parse_state"] = parsed["state"]
    transport["receipt_parse_reason"] = parsed["reason"]
    receipt = parsed["receipt"]
    if receipt is not None:
        receipt = dict(receipt)
        receipt.update(
            {
                "stdoutSha256": transport["stdout_sha256"],
                "stderrSha256": transport["stderr_sha256"],
                "apiKeyPresence": presence,
                "bridgeExitCode": process.returncode,
            }
        )
    return receipt, transport, sampler.snapshot(), sampler.samples


def _initial_evidence(dsh_root: Path, driver: Path) -> dict[str, Any]:
    closure = runtime_closure(dsh_root)
    identity = dsh_identity(dsh_root)
    node_version = _tool_version(["node", "--version"], dsh_root)
    pnpm_version = _tool_version(["pnpm", "--version"], dsh_root)
    binding = validate_materialization_record(
        MATERIALIZATION_RECORD,
        source_record_path=SOURCE_MATERIALIZATION_RECORD,
        dsh_root=dsh_root,
        closure=closure,
        identity=identity,
        node_version=node_version,
        pnpm_version=pnpm_version,
    )
    driver_id = driver_identity(driver)
    codex_id = codex_identity()
    keys = api_key_gate()
    identities = identity_gate(dsh=identity, driver=driver_id, codex=codex_id, keys=keys)
    closure_frozen = (
        closure["files"] == dict(FROZEN_RUNTIME_CLOSURE_FILES)
        and closure["digest"] == FROZEN_RUNTIME_CLOSURE_DIGEST
    )
    return {
        "passed": binding["passed"] and identities["passed"] and closure_frozen,
        "dsh_identity": identity,
        "runtime_closure": closure,
        "runtime_closure_frozen_match": closure_frozen,
        "materialization_binding": binding,
        "driver_identity": driver_id,
        "codex_identity": codex_id,
        "api_key_gate": keys,
        "identity_gate": identities,
        "node_version": node_version,
        "pnpm_version": pnpm_version,
    }


def main() -> int:
    prior = _episode_artifacts_present()
    if prior:
        raise QualificationError("V0R1 live episode already consumed: " + ",".join(prior))

    requested_root = Path(os.environ.get("QNTYLAB_PINNED_DSH_ROOT", str(DEFAULT_DSH_ROOT)))
    dsh_root = resolve_dsh_root(requested_root, expected_root=FROZEN_DSH_ROOT)
    driver = _REPO_ROOT / D4_DRIVER_RELPATH
    initial = _initial_evidence(dsh_root, driver)

    receipt: dict[str, Any] | None = None
    transport: dict[str, Any] = {"state": "NOT_STARTED"}
    descendants: list[dict[str, Any]] = []
    samples = 0
    marker: dict[str, Any] = {"acquired": False, "path": str(CONSUMED_MARKER_PATH)}
    final_gate: dict[str, Any] = {"passed": False, "reason": "INITIAL_GATE_FAILED"}
    final_identity: dict[str, Any] = {"passed": False, "reasons": ["NOT_RUN"]}
    profile: dict[str, Any] = {}
    fixture_before: dict[str, Any] = {"class": "NOT_BUILT"}
    fixture_after: dict[str, Any] = {"class": "NOT_BUILT"}
    changed: list[str] = []
    started_at = ended_at = None
    config_after = None

    if initial["passed"]:
        root = Path(tempfile.mkdtemp(prefix="qntylab-pinned-dsh-d4-v0r1-"))
        workspace = build_workspace(root / "d4")
        prompt_file = root / "write_prompt.txt"
        prompt_file.write_text(WRITE_PROMPT, encoding="utf-8")
        try:
            profile = observe_profile(workspace)
            before = workspace_snapshot(workspace)
            fixture_before = fixture_state(workspace)
            invocation = ProductInvocation(
                route="DSH",
                product="CODEX_PROFILE_A",
                profile=CODEX_HOME,
                cwd=workspace,
                workspace_scope=workspace,
                prompt=WRITE_PROMPT,
                approval_mode="never",
                sandbox_mode="workspace-write",
            )
            started_at = utc_now()
            marker = acquire_episode_marker(
                CONSUMED_MARKER_PATH,
                attempt_path=ATTEMPT_LOG_PATH,
                receipt_path=RECEIPT_PATH,
                payload={
                    "phase_id": PHASE_ID,
                    "started_at": started_at,
                    "pid": os.getpid(),
                    "dsh_root": str(dsh_root),
                    "runtime_closure_digest": initial["runtime_closure"]["digest"],
                },
            )
            _append_attempt(
                {
                    "phase_id": PHASE_ID,
                    "started_at": started_at,
                    "pid": os.getpid(),
                    "dsh_root": str(dsh_root),
                    "workspace": str(workspace),
                    "marker_path": str(CONSUMED_MARKER_PATH),
                    "marker_sha256": marker["sha256"],
                }
            )

            final_node = _tool_version(["node", "--version"], dsh_root)
            final_pnpm = _tool_version(["pnpm", "--version"], dsh_root)
            final_gate = final_execution_gate(
                dsh_root=dsh_root,
                expected_root=Path(initial["runtime_closure"]["root"]),
                expected_closure=initial["runtime_closure"],
                record_path=MATERIALIZATION_RECORD,
                source_record_path=SOURCE_MATERIALIZATION_RECORD,
                node_version=final_node,
                pnpm_version=final_pnpm,
            )
            final_driver = driver_identity(driver)
            final_codex = codex_identity()
            final_keys = api_key_gate()
            final_dsh = dsh_identity(dsh_root)
            final_identity = identity_gate(
                dsh=final_dsh,
                driver=final_driver,
                codex=final_codex,
                keys=final_keys,
            )
            final_identity.update(
                {
                    "dsh": final_dsh,
                    "driver": final_driver,
                    "codex": final_codex,
                    "keys": final_keys,
                }
            )
            if final_gate["passed"] and final_identity["passed"]:
                os.environ["QNTYLAB_CODEX_BINDIR"] = str(Path(CODEX_BINARY).parent)
                os.environ["QNTYLAB_PROMPT_FILE"] = str(prompt_file)
                os.environ["QNTYLAB_TURN_TIMEOUT_MS"] = str(int(HARD_TIMEOUT_SECONDS * 1000))
                # This is the resolved root that the immediately preceding
                # final closure gate verified, not the original input spelling.
                os.environ["QNTYLAB_DSH_ROOT"] = final_gate["root"]
                receipt, transport, descendants, samples = run_driver_observed(
                    ["node", str(driver)], invocation, timeout_seconds=HARD_TIMEOUT_SECONDS
                )
                ended_at = utc_now()
            after = workspace_snapshot(workspace)
            fixture_after = fixture_state(workspace)
            changed = changed_paths(before, after)
            config_path = Path(CODEX_HOME) / "config.toml"
            config_after = sha256_file(config_path) if config_path.is_file() else None
        finally:
            destroy_workspace(workspace)
            destroy_workspace(root)

    all_gates = bool(initial["passed"] and final_gate["passed"] and final_identity["passed"])
    gate_reason = None
    if not initial["passed"]:
        gate_reason = "INITIAL_IDENTITY_OR_EVIDENCE_GATE_FAILED"
    elif not final_gate["passed"]:
        gate_reason = "FINAL_RUNTIME_OR_MATERIALIZATION_GATE_FAILED"
    elif not final_identity["passed"]:
        gate_reason = "FINAL_IDENTITY_GATE_FAILED"
    classification = classify_d4(
        gates_passed=all_gates,
        gate_reason=gate_reason,
        receipt=receipt,
        descendants=descendants,
        fixture_before_class=fixture_before["class"],
        fixture_after_class=fixture_after["class"],
        changed=changed,
        marker_acquired=bool(marker["acquired"]),
        expected_dsh_root=dsh_root,
        profile=profile,
    )
    record = {
        "schema_version": RECEIPT_SCHEMA,
        "phase_id": PHASE_ID,
        "generated_at": utc_now(),
        "attempts": 1 if marker["acquired"] else 0,
        "retries_used": 0,
        "max_live_attempts": MAX_LIVE_ATTEMPTS,
        "route_marker": D4_ROUTE_MARKER,
        "runtime_bytes_verified_at_final_execution_gate": bool(final_gate.get("runtime_closure_match")),
        "one_episode_crash_safe": True,
        "episode_marker": marker,
        "initial_evidence": initial,
        "final_execution_gate": final_gate,
        "final_identity_gate": final_identity,
        "materialization_record_sha256": initial["materialization_binding"]["record_sha256"],
        "source_materialization_record_sha256": SOURCE_MATERIALIZATION_RECORD_SHA256,
        "profile_observation": profile,
        "product_config_sha256_after": config_after,
        "product_config_modified": (
            None if config_after is None else config_after != profile.get("config_sha256_before")
        ),
        "live_attempt": {
            "started_at": started_at,
            "ended_at": ended_at,
            "driver_argv": ["node", str(driver)],
            "hard_timeout_seconds": HARD_TIMEOUT_SECONDS,
            "receipt": receipt,
            "transport": transport,
            "observed_descendant_processes": descendants,
            "descendant_samples_taken": samples,
            "fixture_before": fixture_before,
            "fixture_after": fixture_after,
            "changed_paths": changed,
        },
        "classification": classification,
        "verdict": phase_verdict(classification),
        "authority": downstream_authority(classification),
    }
    _write_receipt(record)
    print(
        json.dumps(
            {
                "d4": classification["d4"],
                "verdict": record["verdict"],
                "reason": classification["reason"],
                "target_mechanism_exercised": classification["target_mechanism_exercised"],
                "dsh_provider_entered": classification["dsh_provider_entered"],
                "codex_child_spawned": classification["codex_child_spawned"],
                "changed_paths": classification["changed_paths"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
