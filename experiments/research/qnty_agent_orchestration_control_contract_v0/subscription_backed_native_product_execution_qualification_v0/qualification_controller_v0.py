#!/usr/bin/env python3
"""Execute the one authorized native subscription-product qualification batch."""

from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[4]
PHASE_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PHASE_ROOT) not in sys.path:
    sys.path.insert(0, str(PHASE_ROOT))

from claude_reviewer_driver_v0 import run_role as run_claude_driver  # noqa: E402
from native_codex_role_driver_v0 import run_role as run_codex_driver  # noqa: E402
from qntylab.subscription_backed_native_product_execution_qualification_v0 import (  # noqa: E402
    API_KEY_NAMES,
    FIXTURE_BEFORE_BYTES,
    FIXTURE_NAME,
    FIXTURE_TARGET_BYTES,
    PROJECT_ID,
    QualificationError,
    api_key_gate,
    api_key_presence,
    canonical_json,
    fixture_observation,
    executable_sha256,
    git_metadata_snapshot,
    git_changed_paths,
    git_diff_bytes,
    overall_qualification_pass,
    qntylab_snapshot,
    read_json_file,
    render_evidence_prompt,
    require_hashes,
    sha256_bytes,
    sha256_file,
    snapshot_digest,
    utc_now,
    validate_role_receipt,
    workspace_identity,
    workspace_snapshot,
    write_exclusive_json,
)

ROLE_FILENAMES = {
    "BUILDER": ("builder_started.json", "builder_receipt.json"),
    "INDEPENDENT_REVIEWER": ("reviewer_started.json", "reviewer_receipt.json"),
    "VERIFIER": ("verifier_started.json", "verifier_receipt.json"),
}
PHASE_REL = "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0"
REQUIRED_HASH_PATHS = {
    "qntylab/__init__.py",
    "qntylab/subscription_backed_product_execution_plumbing_v0.py",
    "qntylab/subscription_backed_codex_app_server_write_path_diagnostic_v0.py",
    "qntylab/subscription_backed_native_product_execution_qualification_v0.py",
    f"{PHASE_REL}/native_codex_role_driver_v0.py",
    f"{PHASE_REL}/claude_reviewer_driver_v0.py",
    f"{PHASE_REL}/qualification_controller_v0.py",
    f"{PHASE_REL}/run_qualification_batch_v0.py",
    f"{PHASE_REL}/qualification_contract.json",
    f"{PHASE_REL}/prompts/builder.txt",
    f"{PHASE_REL}/prompts/reviewer.txt",
    f"{PHASE_REL}/prompts/verifier.txt",
}
REQUIRED_BINARY_PATHS = {"/home/swirky/.local/bin/codex", "/usr/bin/claude"}


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=root, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise QualificationError(f"git preflight failed: {' '.join(args)}")
    return completed.stdout.strip()


def build_workspace() -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="qntylab-native-product-qualification-v0-"))
    (workspace / FIXTURE_NAME).write_bytes(FIXTURE_BEFORE_BYTES)
    commands = (
        ("init", "-q", "-b", "main"),
        ("-c", "user.name=QntyLab Qualification", "-c", "user.email=qualification@qntylab.invalid", "-c", "commit.gpgsign=false", "add", FIXTURE_NAME),
        ("-c", "user.name=QntyLab Qualification", "-c", "user.email=qualification@qntylab.invalid", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"),
    )
    for args in commands:
        _git(workspace, *args)
    if fixture_observation(workspace)["sha256"] != sha256_bytes(FIXTURE_BEFORE_BYTES):
        raise QualificationError("fresh fixture bytes do not match BEFORE")
    if git_changed_paths(workspace):
        raise QualificationError("fresh synthetic repository is not clean")
    return workspace


def validate_prelive_manifest(repo_root: Path, manifest_path: Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve(strict=True)
    manifest_path = Path(manifest_path).resolve(strict=True)
    try:
        relative = manifest_path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise QualificationError("prelive manifest is outside QntyLab") from exc
    manifest = read_json_file(manifest_path)
    required = {
        "schema_version", "project_id", "canonical_parent_master", "prelive_sha", "prelive_tree",
        "freeze_record_parent_required", "open_critical", "open_high", "hashes", "binary_hashes",
        "timeouts_seconds", "qntyagenteval", "review", "frozen_at", "fixture_hashes",
        "product_identity",
    }
    if set(manifest) != required or manifest["schema_version"] != "subscription-backed-native-product-prelive-freeze-v0":
        raise QualificationError("prelive manifest shape is invalid")
    if manifest["project_id"] != PROJECT_ID or manifest["canonical_parent_master"] != "5490d3f213bb1dc1b8fde86fe1cd464d09ddbead":
        raise QualificationError("prelive manifest project or parent binding is invalid")
    if manifest["open_critical"] != 0 or manifest["open_high"] != 0:
        raise QualificationError("prelive review has open Critical/High findings")
    if manifest["freeze_record_parent_required"] is not True:
        raise QualificationError("prelive ancestry rule is not enabled")
    head = _git(repo_root, "rev-parse", "HEAD")
    parent = _git(repo_root, "rev-parse", "HEAD^")
    if parent != manifest["prelive_sha"] or _git(repo_root, "rev-parse", f"{manifest['prelive_sha']}^{{tree}}") != manifest["prelive_tree"]:
        raise QualificationError("current freeze-record ancestry does not bind the prelive target")
    if _git(repo_root, "ls-files", "--error-unmatch", "--", relative) != relative:
        raise QualificationError("prelive manifest is not Git tracked")
    if _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise QualificationError("QntyLab worktree must be clean before the live batch")
    if head == manifest["prelive_sha"]:
        raise QualificationError("prelive manifest must be committed in a distinct freeze record")
    if set(manifest["hashes"]) != REQUIRED_HASH_PATHS:
        raise QualificationError("prelive frozen source path set is not exact")
    if set(manifest["binary_hashes"]) != REQUIRED_BINARY_PATHS:
        raise QualificationError("prelive frozen product binary path set is not exact")
    if manifest["fixture_hashes"] != {
        "before_sha256": sha256_bytes(FIXTURE_BEFORE_BYTES),
        "target_sha256": sha256_bytes(FIXTURE_TARGET_BYTES),
    }:
        raise QualificationError("prelive fixture hashes are not exact")
    require_hashes(repo_root, manifest["hashes"])
    for binary, digest in manifest["binary_hashes"].items():
        if executable_sha256(Path(binary)) != digest:
            raise QualificationError(f"frozen product binary hash mismatch: {binary}")
    if manifest["timeouts_seconds"] != {"BUILDER": 180, "INDEPENDENT_REVIEWER": 180, "VERIFIER": 180}:
        raise QualificationError("prelive role timeouts are not exact")
    if manifest["product_identity"] != {
        "codex": {
            "binary": "/home/swirky/.local/bin/codex", "version": "codex-cli 0.147.0",
            "profile_a": "/home/swirky/.codex", "profile_b": "/home/swirky/.codex-pro2",
            "authentication_mode": "CHATGPT_LOGIN", "subscription_backed": True,
        },
        "claude": {
            "binary": "/usr/bin/claude", "version": "2.1.223 (Claude Code)",
            "authentication_mode": "FIRST_PARTY_CLAUDE_AI_PRO_SUBSCRIPTION", "subscription_backed": True,
        },
    }:
        raise QualificationError("prelive product identity is not exact")
    return manifest


def _marker(
    *, live_root: Path, role: str, workspace_id: str, prompt_sha: str,
    template_sha: str, driver_sha: str, binary_sha: str, prelive_sha: str,
) -> tuple[Path, str]:
    filename = ROLE_FILENAMES[role][0]
    path = live_root / filename
    payload = {
        "schema_version": "subscription-backed-native-product-role-started-v0",
        "project_id": PROJECT_ID,
        "role": role,
        "attempt": 1,
        "workspace_identity": workspace_id,
        "prompt_sha256": prompt_sha,
        "prompt_template_sha256": template_sha,
        "driver_sha256": driver_sha,
        "binary_sha256": binary_sha,
        "prelive_sha": prelive_sha,
        "started_at": utc_now(),
    }
    digest = write_exclusive_json(path, payload)
    return path, digest


def _persist_and_validate(
    *, live_root: Path, role: str, receipt: Mapping[str, Any], workspace: Path,
    workspace_id: str, prompt: bytes, template_sha: str, driver_sha: str, marker_sha: str,
    binary_sha: str, qntylab_root: Path,
) -> dict[str, Any]:
    validated = validate_role_receipt(
        receipt, role=role, workspace=workspace, workspace_id=workspace_id,
        prompt_sha=sha256_bytes(prompt), template_sha=template_sha,
        driver_sha=driver_sha, marker_sha=marker_sha, binary_sha=binary_sha,
    )
    workspace_evidence = validated["workspace"]
    if snapshot_digest(workspace_snapshot(workspace)) != workspace_evidence["after_digest"]:
        raise QualificationError("role receipt is stale against the current workspace")
    if snapshot_digest(git_metadata_snapshot(workspace)) != workspace_evidence["git_metadata_after_digest"]:
        raise QualificationError("role receipt is stale against current Git metadata")
    if fixture_observation(workspace) != workspace_evidence["fixture_after"]:
        raise QualificationError("role receipt fixture observation is stale")
    if git_changed_paths(workspace) != workspace_evidence["git_changed_paths"]:
        raise QualificationError("role receipt Git paths are stale")
    if qntylab_snapshot(qntylab_root)["combined_sha256"] != validated["qntylab_worktree"]["after_digest"]:
        raise QualificationError("role receipt is stale against QntyLab")
    write_exclusive_json(live_root / ROLE_FILENAMES[role][1], validated)
    return validated


def _result(
    *, live_root: Path, manifest: Mapping[str, Any], workspace: Path,
    workspace_id: str, receipts: Mapping[str, Mapping[str, Any]],
    attempts: Mapping[str, int], failure_class: str,
) -> dict[str, Any]:
    try:
        require_hashes(Path(manifest["repository_root"]), manifest["hashes"])
        frozen_sources_match = all(executable_sha256(Path(binary)) == digest for binary, digest in manifest["binary_hashes"].items())
    except (KeyError, OSError, QualificationError):
        frozen_sources_match = False
    prompt_paths = {f"{PHASE_REL}/prompts/{name}.txt" for name in ("builder", "reviewer", "verifier")}
    prompts_match = frozen_sources_match and all(path in manifest["hashes"] for path in prompt_paths)
    markers_match = (live_root / "batch_started.json").is_file()
    for role, (marker_name, receipt_name) in ROLE_FILENAMES.items():
        marker_path = live_root / marker_name
        expected_attempt = attempts.get(role, 0)
        if expected_attempt == 1:
            if not marker_path.is_file() or role not in receipts or not (live_root / receipt_name).is_file():
                markers_match = False
                continue
            try:
                marker = read_json_file(marker_path)
                markers_match = markers_match and marker.get("role") == role and marker.get("attempt") == 1
                markers_match = markers_match and sha256_file(marker_path) == receipts[role].get("started_marker_sha256")
            except QualificationError:
                markers_match = False
        elif expected_attempt == 0:
            markers_match = markers_match and not marker_path.exists() and role not in receipts
        else:
            markers_match = False
    final_fixture = fixture_observation(workspace)
    final_paths = git_changed_paths(workspace)
    workspace_gate = (
        final_fixture["sha256"] == sha256_bytes(FIXTURE_TARGET_BYTES)
        and final_paths == [FIXTURE_NAME]
        and all(receipt.get("workspace_identity") == workspace_id for receipt in receipts.values())
    )
    all_role_gates = overall_qualification_pass(receipts, attempts)
    passed = all_role_gates and frozen_sources_match and prompts_match and markers_match and workspace_gate
    not_run = [role for role in ROLE_FILENAMES if attempts.get(role, 0) == 0]
    result = {
        "schema_version": "subscription-backed-native-product-qualification-result-v0",
        "project_id": PROJECT_ID,
        "prelive_sha": manifest["prelive_sha"],
        "recorded_at": utc_now(),
        "batch_attempts": 1,
        "role_attempts": {role: attempts.get(role, 0) for role in ROLE_FILENAMES},
        "role_status": {role: receipts[role]["machine_status"] if role in receipts else "NOT_RUN_BY_FAIL_CLOSED_DEPENDENCY" for role in ROLE_FILENAMES},
        "not_run_by_fail_closed_dependency": not_run,
        "workspace_identity": workspace_id,
        "final_fixture": final_fixture,
        "final_changed_paths": final_paths,
        "final_diff_sha256": sha256_bytes(git_diff_bytes(workspace)),
        "api_key_gate": "PASS" if all((receipt.get("api_key_gate") == "PASS" for receipt in receipts.values())) and api_key_gate(api_key_presence()) == "PASS" else "FAIL",
        "all_frozen_driver_hashes_match": frozen_sources_match,
        "all_prompt_hashes_match": prompts_match,
        "workspace_identity_match": workspace_gate,
        "exactly_once_gates": "PASS" if markers_match else "FAIL",
        "qualification_pass": passed,
        "failure_class": "NONE" if passed else (failure_class if failure_class != "NONE" else "RECEIPT_INTEGRITY_FAILURE"),
        "verdict": "SUBSCRIPTION_BACKED_NATIVE_PRODUCT_EXECUTION_QUALIFICATION_PASS" if passed else "NATIVE_PRODUCT_EXECUTION_QUALIFICATION_BLOCKED",
        "claim_scope": "TRIVIAL_SYNTHETIC_NATIVE_SUBSCRIPTION_PRODUCT_PLUMBING_ONLY",
        "boundaries": {
            "dsh_imported": False, "dsh_executed": False, "dsh_repaired": False,
            "stage_a_v1_rerun": False, "stage_a_v2_created": False,
            "stage_a_v2_authorized": False, "stage_a_v2_executed": False,
            "historical_stage_a_task_executed": False, "historical_answer_key_accessed": False,
            "market_data_accessed": False, "scientific_evaluation": False,
            "qnty_runtime_authorized": False, "trading_authorized": False,
            "capital_authorized": False, "api_keys_used": False, "merge_performed": False,
        },
    }
    write_exclusive_json(live_root / "result.json", result)
    return result


def execute_batch(
    *, repo_root: Path, prelive_manifest_path: Path,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve(strict=True)
    manifest = validate_prelive_manifest(repo_root, prelive_manifest_path)
    bootstrap_token = sha256_bytes(canonical_json(manifest["hashes"]))
    if os.environ.get("QNTYLAB_NATIVE_QUALIFICATION_BOOTSTRAP") != bootstrap_token:
        raise QualificationError("verified bootstrap binding is absent")
    manifest["repository_root"] = str(repo_root)
    if api_key_gate(api_key_presence()) != "PASS":
        raise QualificationError("API key gate failed before batch start")
    live_root = Path(prelive_manifest_path).parent / "live_batch_v0"
    if live_root.exists():
        raise QualificationError("live batch directory already exists; the batch is consumed")
    workspace = build_workspace()
    identity = workspace_identity(workspace)
    workspace_id = identity["identity_sha256"]
    live_root.mkdir(parents=False, exist_ok=False)
    write_exclusive_json(live_root / "workspace_identity.json", identity)
    write_exclusive_json(live_root / "batch_started.json", {
        "schema_version": "subscription-backed-native-product-batch-started-v0",
        "project_id": PROJECT_ID,
        "batch_attempt": 1,
        "workspace_identity": workspace_id,
        "prelive_sha": manifest["prelive_sha"],
        "started_at": utc_now(),
    })
    attempts = {role: 0 for role in ROLE_FILENAMES}
    receipts: dict[str, dict[str, Any]] = {}
    failure_class = "RECEIPT_INTEGRITY_FAILURE"
    hashes = manifest["hashes"]

    builder_template_path = repo_root / "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0/prompts/builder.txt"
    builder_prompt = builder_template_path.read_bytes()
    builder_template_sha = sha256_bytes(builder_prompt)
    builder_driver_rel = "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0/native_codex_role_driver_v0.py"
    builder_driver_sha = hashes[builder_driver_rel]
    codex_binary_sha = manifest["binary_hashes"]["/home/swirky/.local/bin/codex"]
    _, marker_sha = _marker(
        live_root=live_root, role="BUILDER", workspace_id=workspace_id,
        prompt_sha=sha256_bytes(builder_prompt), template_sha=builder_template_sha,
        driver_sha=builder_driver_sha, binary_sha=codex_binary_sha, prelive_sha=manifest["prelive_sha"],
    )
    attempts["BUILDER"] = 1
    try:
        raw = run_codex_driver(
            role="BUILDER", workspace=workspace, qntylab_root=repo_root, prompt=builder_prompt,
            workspace_identity=workspace_id, prompt_template_sha256=builder_template_sha,
            driver_sha256=builder_driver_sha, started_marker_sha256=marker_sha, timeout_seconds=180,
            binary_sha256=codex_binary_sha,
        )
        receipts["BUILDER"] = _persist_and_validate(
            live_root=live_root, role="BUILDER", receipt=raw, workspace=workspace,
            workspace_id=workspace_id, prompt=builder_prompt, template_sha=builder_template_sha,
            driver_sha=builder_driver_sha, marker_sha=marker_sha,
            binary_sha=codex_binary_sha, qntylab_root=repo_root,
        )
    except (OSError, QualificationError, KeyError, TypeError):
        write_exclusive_json(live_root / "builder_receipt_error.json", {"role": "BUILDER", "status": "FAIL_CLOSED", "failure_class": "RECEIPT_INTEGRITY_FAILURE", "recorded_at": utc_now()})
        return _result(live_root=live_root, manifest=manifest, workspace=workspace, workspace_id=workspace_id, receipts=receipts, attempts=attempts, failure_class="RECEIPT_INTEGRITY_FAILURE")
    if receipts["BUILDER"]["machine_status"] != "PASS":
        return _result(live_root=live_root, manifest=manifest, workspace=workspace, workspace_id=workspace_id, receipts=receipts, attempts=attempts, failure_class=receipts["BUILDER"]["failure_class"])

    reviewer_packet = {
        "schema_version": "subscription-backed-native-reviewer-evidence-v0",
        "task": {"before_hex": FIXTURE_BEFORE_BYTES.hex(), "after_hex": FIXTURE_TARGET_BYTES.hex(), "allowed_changed_paths": [FIXTURE_NAME]},
        "builder_receipt": receipts["BUILDER"],
        "git_changed_paths": git_changed_paths(workspace),
        "git_diff_hex": git_diff_bytes(workspace).hex(),
        "fixture": fixture_observation(workspace),
    }
    write_exclusive_json(live_root / "reviewer_evidence_packet.json", reviewer_packet)
    reviewer_template_path = repo_root / "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0/prompts/reviewer.txt"
    reviewer_template = reviewer_template_path.read_bytes()
    reviewer_prompt = render_evidence_prompt(reviewer_template, reviewer_packet)
    reviewer_template_sha = sha256_bytes(reviewer_template)
    reviewer_driver_rel = "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0/claude_reviewer_driver_v0.py"
    reviewer_driver_sha = hashes[reviewer_driver_rel]
    claude_binary_sha = manifest["binary_hashes"]["/usr/bin/claude"]
    _, marker_sha = _marker(
        live_root=live_root, role="INDEPENDENT_REVIEWER", workspace_id=workspace_id,
        prompt_sha=sha256_bytes(reviewer_prompt), template_sha=reviewer_template_sha,
        driver_sha=reviewer_driver_sha, binary_sha=claude_binary_sha, prelive_sha=manifest["prelive_sha"],
    )
    attempts["INDEPENDENT_REVIEWER"] = 1
    try:
        raw = run_claude_driver(
            workspace=workspace, qntylab_root=repo_root, prompt=reviewer_prompt,
            workspace_identity=workspace_id, prompt_template_sha256=reviewer_template_sha,
            driver_sha256=reviewer_driver_sha, started_marker_sha256=marker_sha, timeout_seconds=180,
            binary_sha256=claude_binary_sha,
        )
        receipts["INDEPENDENT_REVIEWER"] = _persist_and_validate(
            live_root=live_root, role="INDEPENDENT_REVIEWER", receipt=raw,
            workspace=workspace, workspace_id=workspace_id, prompt=reviewer_prompt,
            template_sha=reviewer_template_sha, driver_sha=reviewer_driver_sha, marker_sha=marker_sha,
            binary_sha=claude_binary_sha, qntylab_root=repo_root,
        )
    except (OSError, QualificationError, KeyError, TypeError):
        write_exclusive_json(live_root / "reviewer_receipt_error.json", {"role": "INDEPENDENT_REVIEWER", "status": "FAIL_CLOSED", "failure_class": "RECEIPT_INTEGRITY_FAILURE", "recorded_at": utc_now()})
        return _result(live_root=live_root, manifest=manifest, workspace=workspace, workspace_id=workspace_id, receipts=receipts, attempts=attempts, failure_class="RECEIPT_INTEGRITY_FAILURE")
    if receipts["INDEPENDENT_REVIEWER"]["machine_status"] != "PASS":
        return _result(live_root=live_root, manifest=manifest, workspace=workspace, workspace_id=workspace_id, receipts=receipts, attempts=attempts, failure_class=receipts["INDEPENDENT_REVIEWER"]["failure_class"])

    verifier_packet = {
        "schema_version": "subscription-backed-native-verifier-evidence-v0",
        "task": {"before_hex": FIXTURE_BEFORE_BYTES.hex(), "after_hex": FIXTURE_TARGET_BYTES.hex(), "allowed_changed_paths": [FIXTURE_NAME]},
        "builder_receipt": receipts["BUILDER"],
        "reviewer_receipt": receipts["INDEPENDENT_REVIEWER"],
        "git_changed_paths": git_changed_paths(workspace),
        "git_diff_hex": git_diff_bytes(workspace).hex(),
        "fixture": fixture_observation(workspace),
    }
    write_exclusive_json(live_root / "verifier_evidence_packet.json", verifier_packet)
    verifier_template_path = repo_root / "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0/prompts/verifier.txt"
    verifier_template = verifier_template_path.read_bytes()
    verifier_prompt = render_evidence_prompt(verifier_template, verifier_packet)
    verifier_template_sha = sha256_bytes(verifier_template)
    verifier_driver_sha = builder_driver_sha
    _, marker_sha = _marker(
        live_root=live_root, role="VERIFIER", workspace_id=workspace_id,
        prompt_sha=sha256_bytes(verifier_prompt), template_sha=verifier_template_sha,
        driver_sha=verifier_driver_sha, binary_sha=codex_binary_sha, prelive_sha=manifest["prelive_sha"],
    )
    attempts["VERIFIER"] = 1
    try:
        raw = run_codex_driver(
            role="VERIFIER", workspace=workspace, qntylab_root=repo_root, prompt=verifier_prompt,
            workspace_identity=workspace_id, prompt_template_sha256=verifier_template_sha,
            driver_sha256=verifier_driver_sha, started_marker_sha256=marker_sha, timeout_seconds=180,
            binary_sha256=codex_binary_sha,
        )
        receipts["VERIFIER"] = _persist_and_validate(
            live_root=live_root, role="VERIFIER", receipt=raw, workspace=workspace,
            workspace_id=workspace_id, prompt=verifier_prompt, template_sha=verifier_template_sha,
            driver_sha=verifier_driver_sha, marker_sha=marker_sha,
            binary_sha=codex_binary_sha, qntylab_root=repo_root,
        )
    except (OSError, QualificationError, KeyError, TypeError):
        write_exclusive_json(live_root / "verifier_receipt_error.json", {"role": "VERIFIER", "status": "FAIL_CLOSED", "failure_class": "RECEIPT_INTEGRITY_FAILURE", "recorded_at": utc_now()})
        return _result(live_root=live_root, manifest=manifest, workspace=workspace, workspace_id=workspace_id, receipts=receipts, attempts=attempts, failure_class="RECEIPT_INTEGRITY_FAILURE")
    failure_class = receipts["VERIFIER"]["failure_class"] if receipts["VERIFIER"]["machine_status"] != "PASS" else "NONE"
    return _result(live_root=live_root, manifest=manifest, workspace=workspace, workspace_id=workspace_id, receipts=receipts, attempts=attempts, failure_class=failure_class)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prelive-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = execute_batch(repo_root=REPO_ROOT, prelive_manifest_path=args.prelive_manifest)
    except QualificationError as exc:
        print(json.dumps({"status": "FAIL_CLOSED_BEFORE_OR_DURING_BATCH", "error_class": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["qualification_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
