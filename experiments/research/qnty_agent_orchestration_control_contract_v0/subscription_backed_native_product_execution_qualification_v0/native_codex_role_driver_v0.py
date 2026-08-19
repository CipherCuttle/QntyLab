#!/usr/bin/env python3
"""Committed/hash-bound native Codex app-server role driver."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qntylab.subscription_backed_native_product_execution_qualification_v0 import (  # noqa: E402
    QualificationError,
    run_codex_role,
)


def run_role(
    *,
    role: str,
    workspace: Path,
    qntylab_root: Path,
    prompt: bytes,
    workspace_identity: str,
    prompt_template_sha256: str,
    driver_sha256: str,
    started_marker_sha256: str,
    binary_sha256: str,
    timeouts: Mapping[str, Any],
) -> dict:
    return run_codex_role(
        role=role,
        workspace=workspace,
        qntylab_root=qntylab_root,
        prompt=prompt,
        workspace_id=workspace_identity,
        template_sha=prompt_template_sha256,
        driver_sha=driver_sha256,
        marker_sha=started_marker_sha256,
        binary_sha256=binary_sha256,
        timeouts=timeouts,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=("BUILDER", "VERIFIER"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--qntylab-root", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--workspace-identity", required=True)
    parser.add_argument("--prompt-template-sha256", required=True)
    parser.add_argument("--driver-sha256", required=True)
    parser.add_argument("--started-marker-sha256", required=True)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument("--timeouts-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        timeouts = json.loads(args.timeouts_json)
        receipt = run_role(
            role=args.role,
            workspace=args.workspace,
            qntylab_root=args.qntylab_root,
            prompt=args.prompt_file.read_bytes(),
            workspace_identity=args.workspace_identity,
            prompt_template_sha256=args.prompt_template_sha256,
            driver_sha256=args.driver_sha256,
            started_marker_sha256=args.started_marker_sha256,
            binary_sha256=args.binary_sha256,
            timeouts=timeouts,
        )
    except (OSError, QualificationError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "error_class": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["machine_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
