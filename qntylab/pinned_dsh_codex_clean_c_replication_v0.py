"""Single final D exposure: exact C treatment plus ephemeral Profile A observation.

This module deliberately owns one live boundary.  It constructs D from the
canonical C request builder and intervention patch, proves request equality,
writes one irrevocable marker immediately before the product call, captures
Profile A raw bytes only in a private temporary directory, and records only
sanitized evidence in Git.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from qntylab import pinned_dsh_codex_sandbox_policy_ownership_forensics_v0 as c_phase
from qntylab import pinned_dsh_codex_terminal_error_permission_policy_forensics_v0 as base


PHASE_ID = "PINNED_DSH_CODEX_CLEAN_C_REPLICATION_V0"
ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_clean_c_replication_v0"
AUTHORIZATION_ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_clean_c_replication_authorization_v0/authorization.json"
AUTHORIZATION_PR = 161
AUTHORIZATION_MERGE_SHA = "e0c74578d86816d6edd7afd5d60b099bbd7d4fc1"
EXPECTED_CANONICAL_MASTER = AUTHORIZATION_MERGE_SHA
EXECUTION_BRANCH = "agent/pinned-dsh-codex-clean-c-replication-v0"

DSH_REPOSITORY = "deepseek-ai/deepseek-harness"
DSH_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
DSH_TREE = "3bc8f89fe494a4755c188be354add4e8b1e7b188"
DSH_TAG = "dsh-v0.1.0-rc.7"
FROZEN_DSH_ROOT = Path("/home/swirky/DevHub/dsh-pinned-materialization-v0")
CODEX_HOME = Path("/home/swirky/.codex")
PINNED_CODEX_BINARY = Path("/home/swirky/.codex/packages/standalone/releases/0.147.0-x86_64-unknown-linux-musl/bin/codex")
CODEX_VERSION = "codex-cli 0.147.0"
CODEX_BINARY_SHA256 = "cb0a15567e9a60a5820d54b0f6ae86d504dc3805c1eab21a47f70e3eb7b73a40"
DRIVER = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_codex_app_server_write_path_diagnostic_v0/pinned_dsh_codex_route_driver_v0.mjs"
WRAPPER = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_terminal_error_permission_policy_forensics_v0/codex_stdio_capture_wrapper.mjs"
C_PATCH = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_sandbox_policy_ownership_forensics_v0/intervention_c.patch"

FORBIDDEN_API_ENV = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY")
OTHER_CREDENTIAL_ENV = ("OPENROUTER_API_KEY", "GITHUB_TOKEN", "GH_TOKEN")
PROFILE_PATH = CODEX_HOME / "config.toml"
PROMPT = base.PROMPT
PROMPT_SHA256 = "5998d2259d56942c071536866262fa7a7b72c1780ae41137b8e0de1aafef8683"
FIXTURE_BEFORE_SHA256 = "be9351741a8155d01fd028d158546f1005e73ceeb0bb2d093335feac4144e450"
FIXTURE_AFTER_SHA256 = "f72c713b7b432dd18949ca10f1be6dbcf493479945653609d1c715b2d8d74356"
AUTHORIZATION_PROFILE_HASH = "cb07d9468bb9f7e21b3cc507b20f31a6bffbc8328ef5b250bd7f9a12141ab6c7"
BEFORE = b"BEFORE\n"
AFTER = b"AFTER\n"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def c_request() -> list[dict[str, Any]]:
    """Load the exact request construction from canonical C source."""
    return c_phase.intervention_c_requests()


def d_request() -> list[dict[str, Any]]:
    """D is a deep copy of C; there is no D-specific product change."""
    return copy.deepcopy(c_request())


def request_equivalence() -> dict[str, Any]:
    c_value = c_request()
    d_value = d_request()
    semantic_diff = base.semantic_request_delta(c_value, d_value)
    return {
        "schema_version": "pinned-dsh-clean-c-request-equivalence-v0",
        "phase_id": PHASE_ID,
        "c_request": c_value,
        "d_request": d_value,
        "c_request_digest": sha256_bytes(canonical(c_value).encode()),
        "d_request_digest": sha256_bytes(canonical(d_value).encode()),
        "semantic_diff": semantic_diff,
        "c_to_d_product_request_delta_count": len(semantic_diff),
        "required_delta_count": 0,
        "comparison_stages": ["initialize", "thread/start", "turn/start"],
        "pass": semantic_diff == [],
    }


def authorization() -> dict[str, Any]:
    return json.loads(AUTHORIZATION_ARTIFACT.read_text(encoding="utf-8"))


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def canonical_authorization_gate() -> dict[str, Any]:
    auth = authorization()
    origin_master = git_output("rev-parse", "origin/master")
    ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", AUTHORIZATION_MERGE_SHA, "HEAD"], cwd=ROOT, check=False).returncode == 0
    return {
        "authorization_pr": AUTHORIZATION_PR,
        "authorization_merge_sha": AUTHORIZATION_MERGE_SHA,
        "origin_master": origin_master,
        "canonical_master_match": origin_master == EXPECTED_CANONICAL_MASTER,
        "authorization_head_ancestor": ancestry,
        "artifact_phase_id": auth["phase_id"],
        "authorization_effective": auth["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY",
        "d_live_exposures": auth["later_live_budget"]["d_live_exposures_authorized"],
        "d_retries": auth["later_live_budget"]["d_retries_authorized"],
        "required_delta_count": auth["frozen_d_request"]["c_to_d_product_request_delta_count"],
        "profile_mutation_authorized": auth["governance_boundary"]["profile_a_mutation_authorized"],
        "profile_restoration_authorized": auth["governance_boundary"]["profile_restoration_authorized"],
        "raw_snapshot_policy": auth["observation_only_delta"]["raw_snapshot_policy"],
        "authorization_profile_hash": auth["authorization_profile_baseline"]["authorization_profile_hash"],
        "pass": (
            origin_master == EXPECTED_CANONICAL_MASTER
            and ancestry
            and auth["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
            and auth["later_live_budget"]["d_live_exposures_authorized"] == 1
            and auth["later_live_budget"]["d_retries_authorized"] == 0
            and auth["frozen_d_request"]["c_to_d_product_request_delta_count"] == 0
            and auth["governance_boundary"]["profile_a_mutation_authorized"] is False
            and auth["governance_boundary"]["profile_restoration_authorized"] is False
            and auth["observation_only_delta"]["raw_snapshot_policy"] == "EPHEMERAL_LOCAL_ONLY"
            and auth["authorization_profile_baseline"]["authorization_profile_hash"] == AUTHORIZATION_PROFILE_HASH
        ),
    }


def credential_presence(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {key: key in source for key in FORBIDDEN_API_ENV}


def credential_gate(presence: Mapping[str, object]) -> str:
    if set(presence) != set(FORBIDDEN_API_ENV) or any(type(value) is not bool for value in presence.values()):
        return "BLOCK_MALFORMED"
    return "BLOCK" if any(presence.values()) else "PASS"


def profile_hash() -> str | None:
    return sha256_file(PROFILE_PATH) if PROFILE_PATH.is_file() and not PROFILE_PATH.is_symlink() else None


def safe_stat(path: Path) -> dict[str, Any]:
    value = path.stat()
    return {
        "regular_file": stat.S_ISREG(value.st_mode),
        "symlink": path.is_symlink(),
        "mode": format(stat.S_IMODE(value.st_mode), "04o"),
        "size_bytes": value.st_size,
        "mtime_ns": value.st_mtime_ns,
    }


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def capture_profile_snapshot(label: str, snapshot_dir: Path) -> dict[str, Any]:
    raw = PROFILE_PATH.read_bytes()
    target = snapshot_dir / f"{label}.config.toml"
    _write_private(target, raw)
    return {
        "label": label,
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
        "stat": safe_stat(PROFILE_PATH),
        "ephemeral_path_used": True,
        "raw_content_serialized": False,
    }


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(value[key], child))
        return result
    return {prefix: value}


def _secret_key(path: str) -> bool:
    lowered = path.lower()
    return any(token in lowered for token in ("token", "api_key", "apikey", "secret", "password", "cookie", "bearer", "credential", "auth"))


def _value_class(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int) and not isinstance(value, bool):
        return "INTEGER"
    if isinstance(value, float):
        return "FLOAT"
    if isinstance(value, str):
        return "STRING"
    if isinstance(value, list):
        return "ARRAY"
    if isinstance(value, Mapping):
        return "TABLE"
    return type(value).__name__.upper()


def _safe_value(path: str, value: Any) -> Any:
    return "<REDACTED>" if _secret_key(path) else value


def classify_key(path: str) -> str:
    lowered = path.lower()
    if any(token in lowered for token in ("sandbox", "sandboxpolicy")):
        return "SANDBOX_LOAD_BEARING"
    if "approval" in lowered:
        return "APPROVAL_LOAD_BEARING"
    if "trust" in lowered:
        return "TRUST_LOAD_BEARING"
    if any(token in lowered for token in ("writableroot", "writable_root")):
        return "WRITABLE_ROOT_LOAD_BEARING"
    if any(token in lowered for token in ("workspace", "runtimeworkspace", "workspace_root")):
        return "WORKSPACE_LOAD_BEARING"
    if "model" in lowered:
        return "MODEL_LOAD_BEARING"
    if _secret_key(path):
        return "AUTHENTICATION_ONLY"
    if "session" in lowered:
        return "SESSION_STATE"
    if any(token in lowered for token in ("telemetry", "metadata")):
        return "TELEMETRY_OR_METADATA"
    if any(token in lowered for token in ("timestamp", "updated_at", "created_at")):
        return "TIMESTAMP_OR_VOLATILE_STATE"
    return "UNKNOWN"


def redacted_profile_diff(before_raw: bytes, after_raw: bytes) -> dict[str, Any]:
    if before_raw == after_raw:
        return {
            "schema_version": "pinned-dsh-profile-observation-redacted-diff-v0",
            "profile_bytes_changed": False,
            "semantic_config_changed": "NO",
            "changed_keys": [],
            "raw_bytes_included": False,
        }
    try:
        before = _flatten(tomllib.loads(before_raw.decode("utf-8")))
        after = _flatten(tomllib.loads(after_raw.decode("utf-8")))
        keys = sorted(set(before) | set(after))
        changed = []
        for key in keys:
            if before.get(key, "<ABSENT>") == after.get(key, "<ABSENT>"):
                continue
            secret = _secret_key(key)
            changed.append({
                "key_path": key,
                "before_present": key in before,
                "after_present": key in after,
                "before_value_class": _value_class(before[key]) if key in before else "ABSENT",
                "after_value_class": _value_class(after[key]) if key in after else "ABSENT",
                "safe_before_value": _safe_value(key, before[key]) if key in before else "<ABSENT>",
                "safe_after_value": _safe_value(key, after[key]) if key in after else "<ABSENT>",
                "secret_redacted": "YES" if secret else "NO",
                "load_bearing_classification": classify_key(key),
            })
        return {
            "schema_version": "pinned-dsh-profile-observation-redacted-diff-v0",
            "profile_bytes_changed": True,
            "semantic_config_changed": "YES" if changed else "NO",
            "changed_keys": changed,
            "raw_bytes_included": False,
        }
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return {
            "schema_version": "pinned-dsh-profile-observation-redacted-diff-v0",
            "profile_bytes_changed": True,
            "semantic_config_changed": "UNKNOWN",
            "changed_keys": [],
            "parse_status": "FAILED_SANITIZED",
            "parse_error_class": type(error).__name__,
            "raw_bytes_included": False,
        }


def workspace_snapshot(workspace: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        result[str(path.relative_to(workspace))] = sha256_file(path)
    return result


def changed_paths(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def normalize_requests(events: list[dict[str, Any]], workspace: Path) -> list[dict[str, Any]]:
    return base.normalize_observed_requests(events, workspace)


def _contains_text(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return needle.lower() in value.lower()
    if isinstance(value, Mapping):
        return any(_contains_text(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_contains_text(item, needle) for item in value)
    return False


def _effective_sandbox(events: list[dict[str, Any]]) -> str:
    def walk(value: Any, effective: bool = False) -> str | None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_effective = effective or str(key).lower() in {"effective", "effective_sandbox", "effectiveSandbox"}
                if str(key).lower() == "sandbox" and child_effective and child in {"workspaceWrite", "workspace-write"}:
                    return "workspaceWrite" if child == "workspaceWrite" else "workspace-write"
                found = walk(child, child_effective)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child, effective)
                if found:
                    return found
        return None

    for event in events:
        if event.get("direction") != "request":
            found = walk(event)
            if found:
                return found
    return "NOT_OBSERVABLE"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_consumed_marker(marker: Path, payload: Mapping[str, Any]) -> None:
    data = (json.dumps(dict(payload), sort_keys=True) + "\n").encode()
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def product_identity_gate() -> dict[str, Any]:
    dsh_commit = git_output("-C", str(FROZEN_DSH_ROOT), "rev-parse", "HEAD")
    dsh_tree = git_output("-C", str(FROZEN_DSH_ROOT), "rev-parse", "HEAD^{tree}")
    dsh_tag = subprocess.run(["git", "-C", str(FROZEN_DSH_ROOT), "describe", "--tags", "--exact-match", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    codex_hash = sha256_file(PINNED_CODEX_BINARY)
    value = {
        "dsh_repository": DSH_REPOSITORY,
        "dsh_commit": dsh_commit,
        "dsh_tree": dsh_tree,
        "dsh_tag": dsh_tag,
        "codex_version": CODEX_VERSION,
        "codex_binary": str(PINNED_CODEX_BINARY),
        "codex_binary_sha256": codex_hash,
        "prompt_sha256": sha256_bytes(PROMPT.encode()),
    }
    value["pass"] = (
        dsh_commit == DSH_COMMIT
        and dsh_tree == DSH_TREE
        and dsh_tag == DSH_TAG
        and codex_hash == CODEX_BINARY_SHA256
        and value["prompt_sha256"] == PROMPT_SHA256
        and "0.147.0" in str(PINNED_CODEX_BINARY)
    )
    return value


def prelive_gates() -> dict[str, Any]:
    equivalence = request_equivalence()
    auth_gate = canonical_authorization_gate()
    profile_initial = profile_hash()
    credentials = credential_presence()
    identity = product_identity_gate()
    fixture_before = sha256_bytes(BEFORE)
    worktree_clean = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout == ""
    marker_absent = not (ARTIFACT_DIR / "live_canary_consumed.marker").exists()
    receipt_absent = not (ARTIFACT_DIR / "live_canary_receipt.json").exists()
    gates = {
        "authorization": auth_gate,
        "request_equivalence": equivalence,
        "profile_hash_initial": profile_initial,
        "profile_baseline_match": profile_initial == AUTHORIZATION_PROFILE_HASH,
        "credential_presence": credentials,
        "credential_gate": credential_gate(credentials),
        "identity": identity,
        "fixture_before_digest": fixture_before,
        "fixture_baseline_match": fixture_before == FIXTURE_BEFORE_SHA256,
        "worktree_clean": worktree_clean,
        "marker_absent": marker_absent,
        "prior_receipt_absent": receipt_absent,
    }
    gates["pass"] = (
        auth_gate["pass"]
        and equivalence["pass"]
        and profile_initial == AUTHORIZATION_PROFILE_HASH
        and gates["credential_gate"] == "PASS"
        and identity["pass"]
        and fixture_before == FIXTURE_BEFORE_SHA256
        and worktree_clean
        and marker_absent
        and receipt_absent
    )
    return gates


def create_prelive_freeze() -> dict[str, Any]:
    gates = prelive_gates()
    if not gates["pass"]:
        raise RuntimeError("PRELIVE_BLOCKED: freeze gates did not pass")
    equivalence = gates["request_equivalence"]
    freeze = {
        "schema_version": "pinned-dsh-clean-c-prelive-freeze-v0",
        "phase_id": PHASE_ID,
        "authorization_pr": AUTHORIZATION_PR,
        "authorization_merge_sha": AUTHORIZATION_MERGE_SHA,
        "frozen_candidate_head": git_output("rev-parse", "HEAD"),
        "implementation_branch": EXECUTION_BRANCH,
        "dsh_identity": product_identity_gate(),
        "prompt_sha256": PROMPT_SHA256,
        "fixture_before_sha256": FIXTURE_BEFORE_SHA256,
        "expected_fixture_after_sha256": FIXTURE_AFTER_SHA256,
        "authorization_profile_hash": AUTHORIZATION_PROFILE_HASH,
        "profile_hash_initial": gates["profile_hash_initial"],
        "c_request_digest": equivalence["c_request_digest"],
        "d_request_digest": equivalence["d_request_digest"],
        "c_to_d_product_request_delta_count": equivalence["c_to_d_product_request_delta_count"],
        "allowed_changed_paths": ["fixture.txt"],
        "d_live_exposures_authorized": 1,
        "d_retries_authorized": 0,
        "credential_policy": {"forbidden_environment": list(FORBIDDEN_API_ENV), "presence_only": True, "all_false_required": True, "pay_per_token_fallback": False},
        "implementation_sha256": sha256_file(Path(__file__)),
        "dsh_patch_sha256": sha256_file(C_PATCH),
        "driver_sha256": sha256_file(DRIVER),
        "wrapper_sha256": sha256_file(WRAPPER),
        "classification_table": ["CLEAN_CONFIRMATION_PASS", "PROFILE_MUTATED_RECORDED", "WRITE_FAILURE_WITH_STABLE_PROFILE", "INCONCLUSIVE_INFRA", "PRELIVE_BLOCKED"],
        "prelive_gate": "PASS",
        "immutable_after_commit": True,
    }
    write_json(ARTIFACT_DIR / "prelive_freeze.json", freeze)
    return freeze


def _errors(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for ordinal, event in enumerate(events, start=1):
        error = event.get("error")
        if not isinstance(error, Mapping):
            continue
        method = event.get("method") or event.get("request_method")
        result.append({
            "event_ordinal": ordinal,
            "stage": method if method in {"initialize", "thread/start", "turn/start"} else "terminal/other",
            "method": method,
            "code": error.get("code"),
            "message": base._sanitize(error.get("message")),
            "fatal": "UNKNOWN",
        })
    return result


def _terminal(events: list[dict[str, Any]]) -> tuple[dict[str, Any], str | None, str | None]:
    terminal_events = [event for event in events if event.get("method") == "turn/completed"]
    terminal = terminal_events[-1] if terminal_events else {}
    params = terminal.get("params", {}) if isinstance(terminal.get("params"), Mapping) else {}
    turn = params.get("turn", {}) if isinstance(params.get("turn"), Mapping) else {}
    return terminal, turn.get("status"), turn.get("error")


def classify_result(receipt: Mapping[str, Any]) -> str:
    if receipt.get("prelive_gate") != "PASS":
        return "PRELIVE_BLOCKED"
    if receipt.get("profile_bytes_changed"):
        return "PROFILE_MUTATED_RECORDED"
    if receipt.get("timeout") or receipt.get("infrastructure_failure"):
        return "INCONCLUSIVE_INFRA"
    clean = (
        receipt.get("product_invocation_count") == 1
        and receipt.get("identity_gate") == "PASS"
        and receipt.get("credential_gate") == "PASS"
        and receipt.get("request_equivalence_gate") == "PASS"
        and receipt.get("fixture_before_digest") == FIXTURE_BEFORE_SHA256
        and receipt.get("fixture_after_digest") == FIXTURE_AFTER_SHA256
        and receipt.get("changed_paths") == ["fixture.txt"]
        and receipt.get("unauthorized_writes") == []
        and receipt.get("turn_started") is True
        and receipt.get("terminal_status") == "completed"
        and receipt.get("read_only_message_observed") is False
        and receipt.get("sandbox_denial_observed") is False
        and receipt.get("approval_request_observed") is False
        and receipt.get("expected_write_occurred") is True
        and receipt.get("profile_hash_before") == receipt.get("profile_hash_after")
    )
    if clean:
        return "CLEAN_CONFIRMATION_PASS"
    if receipt.get("profile_hash_before") == receipt.get("profile_hash_after"):
        return "WRITE_FAILURE_WITH_STABLE_PROFILE"
    return "INCONCLUSIVE_INFRA"


def _snapshot_diff_and_delete(snapshot_dir: Path, before_raw: bytes, after_raw: bytes) -> tuple[dict[str, Any], bool, bool]:
    diff = redacted_profile_diff(before_raw, after_raw)
    write_json(ARTIFACT_DIR / "redacted_profile_diff.json", diff)
    before_path = snapshot_dir / "before.config.toml"
    after_path = snapshot_dir / "after.config.toml"
    before_path.unlink(missing_ok=True)
    after_path.unlink(missing_ok=True)
    snapshot_dir.rmdir()
    return diff, not before_path.exists(), not after_path.exists()


def run_live() -> dict[str, Any]:
    """Run exactly one D attempt after all gates; marker makes retry impossible."""
    gates = prelive_gates()
    if not gates["pass"]:
        raise RuntimeError("PRELIVE_BLOCKED: immediate gates failed")
    snapshot_dir = Path(tempfile.mkdtemp(prefix="qntylab-clean-c-profile-"))
    os.chmod(snapshot_dir, 0o700)
    control = Path(tempfile.mkdtemp(prefix="qntylab-clean-c-control-"))
    workspace = Path(tempfile.mkdtemp(prefix="qntylab-clean-c-workspace-"))
    dsh_copy = Path(tempfile.mkdtemp(prefix="qntylab-clean-c-dsh-")) / "dsh"
    before_raw = b""
    after_raw = b""
    try:
        fixture = workspace / "fixture.txt"
        fixture.write_bytes(BEFORE)
        subprocess.run(["git", "-C", str(workspace), "init", "-q"], check=True)
        fixture_before_snapshot = workspace_snapshot(workspace)
        if sha256_file(fixture) != FIXTURE_BEFORE_SHA256:
            raise RuntimeError("PRELIVE_BLOCKED: fixture baseline drift")
        shutil.copytree(FROZEN_DSH_ROOT, dsh_copy, symlinks=True)
        patch_result = subprocess.run(["patch", "-p1", "-d", str(dsh_copy)], input=C_PATCH.read_text(encoding="utf-8"), capture_output=True, text=True, check=False)
        if patch_result.returncode != 0:
            raise RuntimeError("PRELIVE_BLOCKED: canonical C patch did not apply")
        trace = control / "rpc-trace.jsonl"
        prompt_file = control / "prompt.txt"
        prompt_file.write_text(PROMPT, encoding="utf-8")
        wrapper_dir = control / "bin"
        wrapper_dir.mkdir()
        shutil.copy2(WRAPPER, wrapper_dir / "codex")
        (wrapper_dir / "codex").chmod(0o755)

        before_observation = capture_profile_snapshot("before", snapshot_dir)
        before_raw = PROFILE_PATH.read_bytes()
        if before_observation["sha256"] != AUTHORIZATION_PROFILE_HASH:
            raise RuntimeError("PRELIVE_BLOCKED: Profile A changed between gate and capture")

        marker = ARTIFACT_DIR / "live_canary_consumed.marker"
        marker_payload = {
            "phase_id": PHASE_ID,
            "authorization_pr": AUTHORIZATION_PR,
            "authorization_merge_sha": AUTHORIZATION_MERGE_SHA,
            "implementation_head": git_output("rev-parse", "HEAD"),
            "dsh_commit": DSH_COMMIT,
            "dsh_tree": DSH_TREE,
            "dsh_tag": DSH_TAG,
            "codex_version": CODEX_VERSION,
            "codex_binary_sha256": CODEX_BINARY_SHA256,
            "prompt_sha256": PROMPT_SHA256,
            "c_request_digest": request_equivalence()["c_request_digest"],
            "d_request_digest": request_equivalence()["d_request_digest"],
            "profile_sha256_before": before_observation["sha256"],
            "fixture_before_sha256": FIXTURE_BEFORE_SHA256,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "irrevocable": True,
        }
        write_consumed_marker(marker, marker_payload)

        env = os.environ.copy()
        for name in FORBIDDEN_API_ENV + OTHER_CREDENTIAL_ENV:
            env.pop(name, None)
        env.update({
            "QNTYLAB_PRODUCT_CWD": str(workspace),
            "QNTYLAB_WORKSPACE_SCOPE": str(workspace),
            "QNTYLAB_PROFILE": str(CODEX_HOME),
            "QNTYLAB_CODEX_BINDIR": str(wrapper_dir),
            "QNTYLAB_PROMPT_FILE": str(prompt_file),
            "QNTYLAB_TURN_TIMEOUT_MS": "300000",
            "QNTYLAB_DSH_ROOT": str(dsh_copy),
            "QNTYLAB_REAL_CODEX_BINARY": str(PINNED_CODEX_BINARY),
            "QNTYLAB_RPC_TRACE": str(trace),
        })
        started = datetime.now(timezone.utc).isoformat()
        child_returncode: int | None = None
        child_stdout = ""
        child_stderr = ""
        timed_out = False
        infrastructure_failure = None
        try:
            completed = subprocess.run(["node", str(DRIVER)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=360, check=False)
            child_returncode = completed.returncode
            child_stdout = completed.stdout
            child_stderr = completed.stderr
        except subprocess.TimeoutExpired as error:
            timed_out = True
            child_stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
            child_stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
        except OSError as error:
            infrastructure_failure = type(error).__name__
        ended = datetime.now(timezone.utc).isoformat()

        # This is intentionally the first operation after the product exits.
        after_observation = capture_profile_snapshot("after", snapshot_dir)
        after_raw = PROFILE_PATH.read_bytes()
        diff, before_deleted, after_deleted = _snapshot_diff_and_delete(snapshot_dir, before_raw, after_raw)

        events = base._read_trace(trace)
        observed_requests = normalize_requests(events, workspace)
        expected_requests = [{"method": item["method"], "params": item["params"]} for item in d_request()]
        observed_request_diff = base.semantic_request_delta(expected_requests, observed_requests)
        terminal, terminal_status, terminal_error = _terminal(events)
        errors = _errors(events)
        error_32600 = next((item for item in errors if item.get("code") == -32600), None)
        turn_started = any(event.get("method") == "turn/started" for event in events)
        terminal_observed = bool(terminal)
        paths_after = workspace_snapshot(workspace)
        paths = changed_paths(fixture_before_snapshot, paths_after)
        driver_last = None
        for line in reversed([line for line in child_stdout.splitlines() if line.strip()]):
            try:
                driver_last = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        fixture_after_digest = sha256_file(fixture)
        receipt = {
            "schema_version": "pinned-dsh-clean-c-replication-receipt-v0",
            "phase_id": PHASE_ID,
            "authorization_pr": AUTHORIZATION_PR,
            "authorization_merge_sha": AUTHORIZATION_MERGE_SHA,
            "d_consumed": True,
            "product_invocation_count": 1,
            "d_retries": 0,
            "dsh_process_launched": True,
            "codex_child_spawned": any(event.get("direction") == "process" for event in events),
            "started_at": started,
            "ended_at": ended,
            "stop_reason": driver_last.get("lifecycle", {}).get("ends", [{}])[-1].get("stopReason") if isinstance(driver_last, Mapping) else ("timeout" if timed_out else "process_error" if infrastructure_failure else "unknown"),
            "timeout": timed_out,
            "child_exit": child_returncode,
            "terminal_observed": terminal_observed,
            "terminal_status": terminal_status,
            "turn_started": turn_started,
            "turn_id_observed": any(isinstance(event.get("result"), Mapping) and isinstance(event["result"].get("turn"), Mapping) and event["result"]["turn"].get("id") for event in events),
            "identity_gate": "PASS",
            "credential_gate": "PASS",
            "request_equivalence_gate": "PASS" if not observed_request_diff else "FAIL",
            "c_request_digest": request_equivalence()["c_request_digest"],
            "d_request_digest": request_equivalence()["d_request_digest"],
            "observed_request_semantic_diff": observed_request_diff,
            "c_to_d_product_request_delta_count": 0,
            "approval_policy_requested": "never",
            "sandbox_requested": "workspace-write",
            "effective_sandbox_if_observable": _effective_sandbox(events),
            "write_attempt_observed": any(event.get("method") == "item/started" for event in events),
            "read_only_message_observed": any(_contains_text(event, "workspace is read-only") for event in events),
            "sandbox_denial_observed": _contains_text(terminal_error, "sandbox") or _contains_text(terminal_error, "denied"),
            "approval_request_observed": any("approval" in str(event.get("method", "")).lower() for event in events),
            "jsonrpc_errors": errors,
            "jsonrpc_32600_observed": error_32600 is not None,
            "jsonrpc_32600_fatal": "NO" if error_32600 and turn_started and terminal_observed else "UNKNOWN",
            "jsonrpc_32600_event_ordinal": error_32600.get("event_ordinal") if error_32600 else "UNKNOWN",
            "jsonrpc_32600_stage": error_32600.get("stage") if error_32600 else "UNKNOWN",
            "fixture_before_digest": FIXTURE_BEFORE_SHA256,
            "fixture_after_digest": fixture_after_digest,
            "expected_write_occurred": fixture_after_digest == FIXTURE_AFTER_SHA256 and paths == ["fixture.txt"],
            "changed_paths": paths,
            "unauthorized_writes": sorted(set(paths) - {"fixture.txt"}),
            "profile_hash_before": before_observation["sha256"],
            "profile_hash_after": after_observation["sha256"],
            "profile_size_before": before_observation["size_bytes"],
            "profile_size_after": after_observation["size_bytes"],
            "profile_stat_before": before_observation["stat"],
            "profile_stat_after": after_observation["stat"],
            "profile_bytes_changed": before_observation["sha256"] != after_observation["sha256"],
            "redacted_profile_diff_path": "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_clean_c_replication_v0/redacted_profile_diff.json",
            "raw_profile_before_deleted": before_deleted,
            "raw_profile_after_deleted": after_deleted,
            "stderr_sha256": sha256_bytes(child_stderr.encode()),
            "stdout_sha256": sha256_bytes(child_stdout.encode()),
            "infrastructure_failure": infrastructure_failure,
            "driver_status": driver_last.get("status") if isinstance(driver_last, Mapping) else "MISSING",
            "profile_observation": "RAW_BYTES_EPHEMERAL_ONLY",
        }
        receipt["classification"] = classify_result(receipt)
        receipt["causal_update"] = "SANDBOX_OWNERSHIP_STRONGLY_CAUSALLY_SUPPORTED" if receipt["classification"] == "CLEAN_CONFIRMATION_PASS" else "NO_CAUSAL_UPDATE"
        receipt["root_cause_claim_strength"] = "STRONG_CAUSAL_SUPPORT" if receipt["classification"] == "CLEAN_CONFIRMATION_PASS" else "NOT_PROVEN"
        write_json(ARTIFACT_DIR / "profile_observation.json", {
            "schema_version": "pinned-dsh-profile-observation-v0",
            "profile_path": str(PROFILE_PATH),
            "profile_sha256_before": before_observation["sha256"],
            "profile_sha256_after": after_observation["sha256"],
            "profile_size_before": before_observation["size_bytes"],
            "profile_size_after": after_observation["size_bytes"],
            "profile_stat_before": before_observation["stat"],
            "profile_stat_after": after_observation["stat"],
            "profile_bytes_changed": receipt["profile_bytes_changed"],
            "raw_profile_before_deleted": before_deleted,
            "raw_profile_after_deleted": after_deleted,
            "raw_profile_values_serialized": False,
        })
        write_json(ARTIFACT_DIR / "live_canary_receipt.json", receipt)
        return receipt
    finally:
        if snapshot_dir.exists():
            for path in snapshot_dir.glob("*.config.toml"):
                path.unlink(missing_ok=True)
            snapshot_dir.rmdir()
        shutil.rmtree(control, ignore_errors=True)
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.rmtree(dsh_copy.parent, ignore_errors=True)


def close_phase(receipt: Mapping[str, Any]) -> dict[str, Any]:
    closure = {
        "artifact_type": "PINNED_DSH_CODEX_CLEAN_C_REPLICATION_CLOSURE",
        "schema_version": "v0",
        "phase_id": PHASE_ID,
        "authorization_pr": AUTHORIZATION_PR,
        "authorization_merge_sha": AUTHORIZATION_MERGE_SHA,
        "execution_project_id": PHASE_ID,
        "classification": receipt["classification"],
        "causal_update": receipt["causal_update"],
        "root_cause_claim_strength": receipt["root_cause_claim_strength"],
        "profile_hash_before": receipt["profile_hash_before"],
        "profile_hash_after": receipt["profile_hash_after"],
        "profile_bytes_changed": receipt["profile_bytes_changed"],
        "content_recovery": "NO_DIFF_REQUIRED_STABLE_BYTES" if not receipt["profile_bytes_changed"] else "REDACTED_DIFF_RECOVERED",
        "changed_paths": receipt["changed_paths"],
        "unauthorized_writes": receipt["unauthorized_writes"],
        "d_consumed": True,
        "d_product_invocations": 1,
        "d_retries": 0,
        "dsh_invoked": True,
        "codex_invoked": receipt["codex_child_spawned"],
        "additional_canary_authorized": False,
        "additional_canary_recommended": False,
        "historical_pr158_reclassified": False,
        "historical_pr160_reclassified": False,
        "historical_pr161_reclassified": False,
        "raw_profile_before_deleted": receipt["raw_profile_before_deleted"],
        "raw_profile_after_deleted": receipt["raw_profile_after_deleted"],
        "secrets_recorded": False,
        "qnty_agent_eval": "NO_MATCH",
        "scientific_execution": False,
        "qnty_runtime_authority": "NONE",
        "trading_authority": "NONE",
        "capital_authority": "NONE",
        "active_project_after_closure": "NONE",
    }
    closure["next_action"] = "Stop. Do not invoke DSH/Codex again or authorize another live exposure."
    write_json(ARTIFACT_DIR / "closure.json", closure)
    return closure


def main(argv: list[str]) -> int:
    if argv == ["request-equivalence"]:
        write_json(ARTIFACT_DIR / "request_equivalence.json", request_equivalence())
        return 0
    if argv == ["prelive-gates"]:
        print(json.dumps(prelive_gates(), indent=2, sort_keys=True))
        return 0
    if argv == ["freeze"]:
        print(json.dumps(create_prelive_freeze(), indent=2, sort_keys=True))
        return 0
    if argv == ["run-live"]:
        receipt = run_live()
        close_phase(receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    raise SystemExit("usage: request-equivalence | prelive-gates | freeze | run-live")


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
