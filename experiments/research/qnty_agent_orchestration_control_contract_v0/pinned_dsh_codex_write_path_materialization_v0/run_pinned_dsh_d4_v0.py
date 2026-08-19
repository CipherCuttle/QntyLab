#!/usr/bin/env python3
"""Frozen lab-only runner for exactly one live D4 through the pinned DSH build.

One attempt, enforced by an on-disk consumed-episode guard rather than by a
promise.  D0-D3 are established by PR #135 and are not rerun here.  Codex-child
evidence comes from real ``/proc`` descendant observation; the loaded DSH build
is re-hashed against the pinned attestation immediately before the live call,
because ``lib/`` is gitignored and a clean tracked tree cannot vouch for it.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from qntylab.pinned_dsh_codex_write_path_materialization_v0 import (  # noqa: E402
    ARTIFACT_HASH_KEYS,
    CODEX_BINARY,
    CODEX_HOME,
    D4_DRIVER_RELPATH,
    D4_DRIVER_TIMEOUT_SECONDS,
    D4_ROUTE_MARKER,
    D4_TURN_TIMEOUT_SECONDS,
    LOCKFILE_SHA256,
    PHASE_ID,
    SUBSCRIPTION_AUTH_MODE,
    api_key_gate,
    classify_d4,
    classify_materialization,
    codex_identity,
    downstream_authority,
    driver_identity,
    dsh_identity,
    identity_gate,
    phase_verdict,
    runtime_artifact_hashes,
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

DEFAULT_DSH_ROOT = Path("/home/swirky/DevHub/dsh-pinned-materialization-v0")
RECEIPT_PATH = _HERE / "d4_receipt.json"
ATTEMPT_LOG_PATH = _HERE / "d4_attempts.jsonl"
MATERIALIZATION_RECORD = _HERE / "materialization_record.json"


# ---------------------------------------------------------------------------
# Real process observation: /proc descendants of the driver.
# ---------------------------------------------------------------------------


def _proc_table() -> dict[int, tuple[int, list[str]]]:
    table: dict[int, tuple[int, list[str]]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            stat = (entry / "stat").read_text()
            raw = (entry / "cmdline").read_bytes()
        except (OSError, ValueError):
            continue
        # comm may contain spaces/parens; ppid is the second field after ')'.
        tail = stat.rsplit(") ", 1)
        if len(tail) != 2:
            continue
        fields = tail[1].split()
        if len(fields) < 2:
            continue
        try:
            ppid = int(fields[1])
        except ValueError:
            continue
        argv = [part for part in raw.decode("utf-8", "replace").split("\0") if part]
        table[pid] = (ppid, argv)
    return table


class DescendantSampler(threading.Thread):
    """Sample descendants of one pid; record each distinct argv observed."""

    def __init__(self, root_pid: int, interval: float = 0.05) -> None:
        super().__init__(daemon=True)
        self.root_pid = root_pid
        self.interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._observed: dict[tuple[str, ...], dict[str, Any]] = {}
        self.samples = 0

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                (dict(value) for value in self._observed.values()),
                key=lambda item: item["argv"],
            )

    def _sample_once(self, table: dict[int, tuple[int, list[str]]]) -> None:
        for pid, (_ppid, argv) in table.items():
            if pid == self.root_pid or not argv:
                continue
            cursor, depth = pid, 0
            while depth < 32:
                parent = table.get(cursor, (0, []))[0]
                if parent == self.root_pid:
                    with self._lock:
                        self._observed.setdefault(
                            tuple(argv),
                            {"argv": list(argv), "depth": depth + 1, "first_seen": utc_now()},
                        )
                    break
                if parent in (0, 1):
                    break
                cursor, depth = parent, depth + 1

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                table = _proc_table()
            except OSError:
                self._stop.wait(self.interval)
                continue
            self._sample_once(table)
            self.samples += 1
            self._stop.wait(self.interval)
        # One final sweep so a child that exits during teardown is still seen.
        try:
            self._sample_once(_proc_table())
        except OSError:
            pass


def _terminate_tree(process: subprocess.Popen) -> None:
    """The driver runs in its own session; take the whole group down."""

    for sender, sig in ((os.killpg, signal.SIGTERM), (os.killpg, signal.SIGKILL)):
        try:
            sender(os.getpgid(process.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            break
        try:
            process.wait(timeout=5.0)
            return
        except subprocess.TimeoutExpired:
            continue


def run_driver_observed(
    argv: list[str], invocation: ProductInvocation, *, timeout_seconds: float
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """Run the frozen driver once, observing real descendant processes.

    Mirrors the predecessor bridge contract: credentials are stripped without
    being read, and only the last JSON line of stdout is trusted.  A harness
    deadline or an unparseable receipt is infrastructure, never a product FAIL.
    """

    invocation.validate()
    clean_env, presence = sanitize_environment()
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
    stdout, stderr, wall_clock_exceeded = b"", b"", False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        wall_clock_exceeded = True
        _terminate_tree(process)
        try:
            # A surviving grandchild can hold the inherited stderr pipe open,
            # so this second drain is bounded too.
            stdout, stderr = process.communicate(timeout=15.0)
        except subprocess.TimeoutExpired:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    finally:
        sampler.stop()
        sampler.join(timeout=5.0)

    descendants = sampler.snapshot()
    digests = {
        "stdoutSha256": sha256_bytes(stdout),
        "stderrSha256": sha256_bytes(stderr),
        "apiKeyPresence": presence,
        "bridgeExitCode": process.returncode,
    }
    if wall_clock_exceeded:
        return (
            {
                "status": "FAIL_CLOSED",
                "output": "",
                "error": "driver wall-clock deadline exceeded",
                "timedOut": True,
                "inconclusiveInfra": "D4_DRIVER_WALL_CLOCK_EXCEEDED",
                **digests,
            },
            descendants,
            sampler.samples,
        )
    try:
        text = stdout.decode("utf-8")
        value = json.loads(next(line for line in reversed(text.splitlines()) if line.strip()))
    except (StopIteration, UnicodeDecodeError, json.JSONDecodeError):
        value = {
            "status": "FAIL_CLOSED",
            "output": "",
            "error": "driver returned no parseable receipt",
            # The driver never emitted its own receipt, so nothing here proves
            # the pinned modules resolved.  That is infrastructure, not DSH.
            "inconclusiveInfra": "D4_DRIVER_PRODUCED_NO_PARSEABLE_RECEIPT",
        }
    if not isinstance(value, dict):
        value = {
            "status": "FAIL_CLOSED",
            "output": "",
            "error": "driver returned non-object JSON",
            "inconclusiveInfra": "D4_DRIVER_PRODUCED_NO_PARSEABLE_RECEIPT",
        }
    value.update(digests)
    return value, descendants, sampler.samples


# ---------------------------------------------------------------------------
# Materialization + profile observation.
# ---------------------------------------------------------------------------


def _tool_version(argv: list[str], cwd: Path) -> str:
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, check=False
    ).stdout.strip()


def load_build_evidence() -> dict[str, Any]:
    """Read the recorded build evidence.  Absent evidence fails closed."""

    if not MATERIALIZATION_RECORD.is_file():
        return {"install_ok": False, "build_ok": False, "present": False}
    record = json.loads(MATERIALIZATION_RECORD.read_text())
    return {
        "present": True,
        "install_ok": record.get("install", {}).get("exit_code") == 0
        and record.get("install", {}).get("lockfile_updated") is False,
        "build_ok": record.get("build", {}).get("exit_code") == 0,
        "recorded_lockfile_sha256": record.get("after", {}).get("LOCKFILE_SHA256_AFTER"),
    }


def observe_materialization(dsh_root: Path) -> tuple[dict, dict, dict, dict]:
    identity = dsh_identity(dsh_root)
    hashes = runtime_artifact_hashes(dsh_root)
    evidence = load_build_evidence()
    lockfile = dsh_root / "pnpm-lock.yaml"
    observed_lockfile = sha256_file(lockfile) if lockfile.is_file() else None
    lockfile_unchanged = observed_lockfile == LOCKFILE_SHA256
    materialization = classify_materialization(
        identity,
        hashes,
        node_version=_tool_version(["node", "--version"], dsh_root),
        pnpm_version=_tool_version(["pnpm", "--version"], dsh_root),
        install_ok=bool(evidence["install_ok"]),
        build_ok=bool(evidence["build_ok"]),
        lockfile_unchanged=lockfile_unchanged,
    )
    materialization["lockfile_sha256_observed"] = observed_lockfile
    materialization["lockfile_sha256_expected"] = LOCKFILE_SHA256
    materialization["build_evidence_source"] = (
        str(MATERIALIZATION_RECORD) if evidence["present"] else "ABSENT"
    )
    return identity, hashes, materialization, evidence


_TRUSTED = re.compile(r'^\[projects\."(?P<path>.*)"\]\s*$')


def _trusted_project_paths(config_text: str) -> list[str]:
    paths, current = [], None
    for line in config_text.splitlines():
        match = _TRUSTED.match(line.strip())
        if match:
            current = match.group("path")
            continue
        if current and line.strip().startswith("["):
            current = None
        elif current and line.strip() == 'trust_level = "trusted"':
            paths.append(current)
            current = None
    return paths


def observe_profile(workspace: Path) -> dict[str, Any]:
    """Record the effective product profile.  Key *names* only, never values.

    The pinned DSH provider sends no approval/sandbox policy on `thread/start`
    (unlike the D2/D3 routes, which sent and verified one), so the profile's
    own trust configuration is load-bearing for how this turn is governed.
    """

    home = Path(CODEX_HOME)
    config = home / "config.toml"
    auth = home / "auth.json"
    observation: dict[str, Any] = {
        "codex_home": str(home),
        "config_present": config.is_file(),
        "config_sha256_before": sha256_file(config) if config.is_file() else None,
        "auth_mode": None,
        "auth_key_names": [],
        "auth_api_key_slot_populated": None,
        "subscription_backed": None,
        "model": None,
        "mcp_servers": [],
        "workspace": str(workspace),
        "workspace_trusted": None,
        "policy_note": (
            "DSH's codex provider sends only {cwd, ephemeral} on thread/start; "
            "no approvalPolicy or sandboxPolicy is requested on this route."
        ),
    }
    if config.is_file():
        text = config.read_text(errors="replace")
        model = re.search(r'^model\s*=\s*"([^"]+)"', text, re.MULTILINE)
        observation["model"] = model.group(1) if model else None
        observation["mcp_servers"] = sorted(
            re.findall(r'^\[mcp_servers\.([^.\]]+)\]', text, re.MULTILINE)
        )
        trusted = _trusted_project_paths(text)
        resolved = str(workspace.resolve())
        observation["workspace_trusted"] = any(
            resolved == entry or resolved.startswith(entry.rstrip("/") + "/")
            for entry in trusted
        )
    if auth.is_file():
        try:
            payload = json.loads(auth.read_text())
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            observation["auth_key_names"] = sorted(payload)
            observation["auth_mode"] = payload.get("auth_mode")
            observation["auth_api_key_slot_populated"] = bool(payload.get("OPENAI_API_KEY"))
            observation["subscription_backed"] = (
                payload.get("auth_mode") == SUBSCRIPTION_AUTH_MODE
                and not payload.get("OPENAI_API_KEY")
            )
    return observation


def _write_record(record: dict[str, Any]) -> None:
    RECEIPT_PATH.write_text(
        json.dumps(record, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def main() -> int:
    if RECEIPT_PATH.exists():
        raise QualificationError(
            f"the single D4 episode is already consumed: {RECEIPT_PATH} exists"
        )

    dsh_root = Path(os.environ.get("QNTYLAB_PINNED_DSH_ROOT", str(DEFAULT_DSH_ROOT)))
    driver = _REPO_ROOT / D4_DRIVER_RELPATH

    identity, hashes, materialization, evidence = observe_materialization(dsh_root)
    driver_id = driver_identity(driver)
    codex_id = codex_identity()
    keys = api_key_gate()
    gate = identity_gate(dsh=identity, driver=driver_id, codex=codex_id, keys=keys)

    receipt: dict[str, Any] | None = None
    descendants: list[dict[str, Any]] = []
    samples = 0
    profile: dict[str, Any] = {}
    fixture_before: dict[str, Any] = {"class": "NOT_BUILT"}
    fixture_after: dict[str, Any] = {"class": "NOT_BUILT"}
    changed: list[str] = []
    started_at = ended_at = None
    config_after = None

    if materialization["materialized"] and gate["passed"]:
        root = Path(tempfile.mkdtemp(prefix="qntylab-pinned-dsh-d4-"))
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
            os.environ["QNTYLAB_CODEX_BINDIR"] = str(Path(CODEX_BINARY).parent)
            os.environ["QNTYLAB_PROMPT_FILE"] = str(prompt_file)
            os.environ["QNTYLAB_TURN_TIMEOUT_MS"] = str(int(D4_TURN_TIMEOUT_SECONDS * 1000))
            os.environ["QNTYLAB_DSH_ROOT"] = str(dsh_root)
            started_at = utc_now()
            # Append-only, written *before* the call, so an episode that
            # crashes or is discarded is still on the record.
            with ATTEMPT_LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "phase_id": PHASE_ID,
                            "started_at": started_at,
                            "pid": os.getpid(),
                            "dsh_root": str(dsh_root),
                            "workspace": str(workspace),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
            receipt, descendants, samples = run_driver_observed(
                ["node", str(driver)], invocation, timeout_seconds=D4_DRIVER_TIMEOUT_SECONDS
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

    classification = classify_d4(
        materialization=materialization,
        identity=gate,
        receipt=receipt,
        descendants=descendants,
        fixture_before_class=fixture_before["class"],
        fixture_after_class=fixture_after["class"],
        changed=changed,
        profile=profile,
    )

    record = {
        "schema_version": "pinned-dsh-codex-write-path-d4-receipt-v0",
        "phase_id": PHASE_ID,
        "generated_at": utc_now(),
        "attempts": 1,
        "retries_used": 0,
        "route_marker": D4_ROUTE_MARKER,
        "dsh_identity": identity,
        "materialization": materialization,
        "build_evidence": evidence,
        "runtime_artifact_hashes_labelled": {
            ARTIFACT_HASH_KEYS[relpath]: value for relpath, value in hashes.items()
        },
        "driver_identity": driver_id,
        "codex_identity": codex_id,
        "api_key_gate": keys,
        "identity_gate": gate,
        "profile_observation": profile,
        "product_config_sha256_after": config_after,
        "product_config_modified": (
            None
            if config_after is None
            else config_after != profile.get("config_sha256_before")
        ),
        "live_attempt": {
            "started_at": started_at,
            "ended_at": ended_at,
            "driver_argv": ["node", str(driver)],
            "turn_timeout_seconds": D4_TURN_TIMEOUT_SECONDS,
            "driver_timeout_seconds": D4_DRIVER_TIMEOUT_SECONDS,
            "receipt": receipt,
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
    _write_record(record)
    print(
        json.dumps(
            {
                "d4": classification["d4"],
                "verdict": record["verdict"],
                "reason": classification["reason"],
                "target_mechanism_exercised": classification["target_mechanism_exercised"],
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
