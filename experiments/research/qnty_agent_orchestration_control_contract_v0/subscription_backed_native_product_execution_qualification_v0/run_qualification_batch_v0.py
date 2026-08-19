#!/usr/bin/env python3
"""Stdlib-only hash-verifying bootstrap for the one authorized live batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PHASE_REL = "experiments/research/qnty_agent_orchestration_control_contract_v0/subscription_backed_native_product_execution_qualification_v0"
MODULE_PATHS = (
    ("qntylab", "qntylab/__init__.py"),
    ("qntylab.subscription_backed_product_execution_plumbing_v0", "qntylab/subscription_backed_product_execution_plumbing_v0.py"),
    ("qntylab.subscription_backed_codex_app_server_write_path_diagnostic_v0", "qntylab/subscription_backed_codex_app_server_write_path_diagnostic_v0.py"),
    ("qntylab.subscription_backed_native_product_execution_qualification_v0", "qntylab/subscription_backed_native_product_execution_qualification_v0.py"),
    ("native_codex_role_driver_v0", f"{PHASE_REL}/native_codex_role_driver_v0.py"),
    ("claude_reviewer_driver_v0", f"{PHASE_REL}/claude_reviewer_driver_v0.py"),
    ("qualification_controller_v0", f"{PHASE_REL}/qualification_controller_v0.py"),
)
REQUIRED_HASH_PATHS = {
    *(relative for _, relative in MODULE_PATHS),
    f"{PHASE_REL}/run_qualification_batch_v0.py",
    f"{PHASE_REL}/qualification_contract.json",
    f"{PHASE_REL}/prompts/builder.txt",
    f"{PHASE_REL}/prompts/reviewer.txt",
    f"{PHASE_REL}/prompts/verifier.txt",
}
REQUIRED_BINARY_PATHS = {"/home/swirky/.local/bin/codex", "/usr/bin/claude"}


class BootstrapError(RuntimeError):
    pass


def _git(*args: str) -> str:
    completed = subprocess.run(("git", *args), cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise BootstrapError("Git bootstrap preflight failed")
    return completed.stdout.strip()


def _read_regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise BootstrapError("frozen source is not a regular non-symlink file")
    descriptor = os.open(path, os.O_RDONLY)
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _verified_sources(manifest_path: Path) -> tuple[dict, bytes, dict[str, bytes]]:
    if _git("status", "--porcelain=v1", "--untracked-files=all"):
        raise BootstrapError("QntyLab must be clean before loading execution source")
    raw = _read_regular(manifest_path)
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BootstrapError("prelive manifest is malformed") from exc
    if not isinstance(manifest, dict) or set(manifest.get("hashes", {})) != REQUIRED_HASH_PATHS:
        raise BootstrapError("prelive source hash set is not exact")
    if set(manifest.get("binary_hashes", {})) != REQUIRED_BINARY_PATHS:
        raise BootstrapError("prelive binary hash set is not exact")
    if _git("rev-parse", "HEAD^") != manifest.get("prelive_sha"):
        raise BootstrapError("freeze record does not directly descend from prelive target")
    relative_manifest = manifest_path.resolve(strict=True).relative_to(REPO_ROOT).as_posix()
    if _git("ls-files", "--error-unmatch", "--", relative_manifest) != relative_manifest:
        raise BootstrapError("prelive manifest is not tracked")
    sources: dict[str, bytes] = {}
    for relative, expected in manifest["hashes"].items():
        payload = _read_regular(REPO_ROOT / relative)
        if hashlib.sha256(payload).hexdigest() != expected:
            raise BootstrapError("frozen source digest mismatch")
        sources[relative] = payload
    for binary, expected in manifest["binary_hashes"].items():
        descriptor = os.open(binary, os.O_RDONLY)
        try:
            digest = hashlib.sha256()
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        finally:
            os.close(descriptor)
        if digest.hexdigest() != expected:
            raise BootstrapError("frozen binary digest mismatch")
    return manifest, raw, sources


def _load_exact(name: str, relative: str, payload: bytes) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__file__ = str(REPO_ROOT / relative)
    module.__package__ = name if name == "qntylab" else name.rpartition(".")[0]
    if name == "qntylab":
        module.__path__ = [str(REPO_ROOT / "qntylab")]
    sys.modules[name] = module
    exec(compile(payload, module.__file__, "exec"), module.__dict__)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prelive-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest, manifest_bytes, sources = _verified_sources(args.prelive_manifest)
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        loaded: dict[str, types.ModuleType] = {}
        for name, relative in MODULE_PATHS:
            loaded[name] = _load_exact(name, relative, sources[relative])
        controller = loaded["qualification_controller_v0"]
        os.environ["QNTYLAB_NATIVE_QUALIFICATION_BOOTSTRAP"] = hashlib.sha256(
            (json.dumps(manifest["hashes"], sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        ).hexdigest()
        result = controller.execute_batch(
            repo_root=REPO_ROOT,
            prelive_manifest_path=args.prelive_manifest,
            manifest_bytes=manifest_bytes,
            frozen_sources=sources,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["qualification_pass"] else 1
    except (BootstrapError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED_BOOTSTRAP", "error_class": type(exc).__name__}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
