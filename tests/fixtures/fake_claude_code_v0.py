#!/usr/bin/env python3
"""Deterministic fake Claude Code JSON transport; never calls a product."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

scenario = os.environ.get("FAKE_CLAUDE_SCENARIO", "pass")
_ = sys.stdin.buffer.read()

if scenario == "timeout":
    time.sleep(30)
if scenario == "process_failure":
    raise SystemExit(3)
if scenario == "workspace_mutation":
    Path("reviewer-write.txt").write_bytes(b"forbidden\n")

verdict = {
    "role": "INDEPENDENT_REVIEWER",
    "verdict": "PASS",
    "builder_task_satisfied": True,
    "changed_paths_match": True,
    "fixture_match": True,
    "unauthorized_writes": [],
    "reasons": [],
}

if scenario == "fail":
    verdict.update({"verdict": "FAIL", "fixture_match": False, "reasons": ["fixture mismatch"]})
elif scenario == "wrong_role":
    verdict["role"] = "VERIFIER"
elif scenario == "missing_field":
    verdict.pop("fixture_match")
elif scenario == "false_pass":
    pass

wrapper = {"type": "result", "subtype": "success", "is_error": False, "structured_output": verdict}
payload = json.dumps(wrapper, sort_keys=True, separators=(",", ":"))
if scenario == "malformed_json":
    payload = "{bad"
elif scenario == "extra_prose":
    payload = "claimed pass\n" + payload

sys.stdout.write(payload + "\n")
