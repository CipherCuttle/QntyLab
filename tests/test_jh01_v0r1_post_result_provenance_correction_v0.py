from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V0R1_ROOT = ROOT / "experiments/research/jh01_rv_persistence_temporal_replication_v0/v0r1"
FROZEN_EXECUTOR_SHA = "758e02718ce82bebeae3e63d17ecc6e3d4a9a23a"
FROZEN_RESULT_SHA = "939f47d8c24abf5e84a1071550eaab463647182e"
EXECUTOR_PATH = "qntylab/jh01_rv_persistence_temporal_replication_execution_v0r1.py"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(value: dict[str, object]) -> str:
    payload = {key: item for key, item in value.items() if key != "provenance_correction_digest"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()


def _git_show(revision: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{revision}:{path}"], cwd=ROOT, check=True, capture_output=True).stdout


def test_v0r1_provenance_correction_is_deterministic_and_preserves_frozen_history() -> None:
    v0_started = _read_json(ROOT / "experiments/research/jh01_rv_persistence_temporal_replication_v0/execution_started.json")
    request_path = V0R1_ROOT / "execution_request.json"
    start_path = V0R1_ROOT / "execution_started.json"
    result_path = V0R1_ROOT / "execution_result.json"
    request, started, result = (_read_json(path) for path in (request_path, start_path, result_path))
    correction = _read_json(V0R1_ROOT / "provenance_correction.json")

    canonical = v0_started["execution_started_digest"]
    recorded = result["prior_execution_started_digest"]
    assert isinstance(canonical, str) and re.fullmatch(r"[0-9a-f]{64}", canonical)
    assert recorded == request["prior_execution_started_digest"] == "9c8b00ad68c1e1ba389512c94a4e24fae75c038fcc9e0144f285"
    assert correction["canonical_value"] == canonical
    assert correction["recorded_value"] == recorded
    assert correction["target_execution_result_digest"] == result["execution_result_digest"] == "3dba3a0f0700a768e981dcecfe5793532bcd4bc1db7dc4dbcd9e4806a722c5c1"
    assert correction["target_execution_request_digest"] == request["execution_request_digest"]
    assert correction["provenance_correction_digest"] == _digest(correction)
    assert all(correction[field] is False for field in ("scientific_computation_affected", "scientific_values_changed", "scientific_classification_changed", "real_sample_rerun", "frozen_executor_changed", "frozen_request_changed", "frozen_start_changed", "frozen_result_changed"))
    assert _git_show(FROZEN_RESULT_SHA, "experiments/research/jh01_rv_persistence_temporal_replication_v0/v0r1/execution_request.json") == request_path.read_bytes()
    assert _git_show(FROZEN_RESULT_SHA, "experiments/research/jh01_rv_persistence_temporal_replication_v0/v0r1/execution_started.json") == start_path.read_bytes()
    assert _git_show(FROZEN_RESULT_SHA, "experiments/research/jh01_rv_persistence_temporal_replication_v0/v0r1/execution_result.json") == result_path.read_bytes()


def test_frozen_executor_records_the_stale_value_only_as_request_result_provenance() -> None:
    source_path = ROOT / EXECUTOR_PATH
    source = _git_show(FROZEN_EXECUTOR_SHA, EXECUTOR_PATH).decode("utf-8")
    assert source_path.read_bytes() == source.encode("utf-8")
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    references = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "PRIOR_EXECUTION_STARTED_DIGEST"]
    assert len(references) == 3
    assert isinstance(parents[references[0]], ast.Assign)
    assert all(isinstance(parents[node], ast.Dict) for node in references[1:])
    assert {parents[node].lineno for node in references[1:]} == {351, 410}
