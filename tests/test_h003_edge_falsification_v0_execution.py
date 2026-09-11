from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from qntylab import h003_edge_falsification_v0_execution as execution


def test_block_shuffle_is_deterministic_and_preserves_168h_blocks_and_tail() -> None:
    held = np.r_[np.zeros(168), np.ones(168), np.tile([0.0, 1.0], 20)]
    shuffled = execution.block_shuffled_timing(held, 17011)
    np.testing.assert_array_equal(shuffled, execution.block_shuffled_timing(held, 17011))
    np.testing.assert_array_equal(shuffled[-40:], held[-40:])
    original_blocks = {held[:168].tobytes(), held[168:336].tobytes()}
    shuffled_blocks = {shuffled[:168].tobytes(), shuffled[168:336].tobytes()}
    assert shuffled_blocks == original_blocks


def test_control_costs_do_not_invent_terminal_exit() -> None:
    market = np.zeros(4)
    held = np.array([0.0, 1.0, 1.0, 1.0])
    result = execution._control_returns(market, held, 10.0)
    np.testing.assert_allclose(result, np.array([-0.001, 0.0, 0.0, 0.0]))


def test_resume_requires_canonical_ledger_membership(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    receipt = run_dir / "run_receipt.json"
    receipt.write_text('{"trial_id":"trial_test"}\n', encoding="utf-8")
    research = tmp_path / "research"
    research.mkdir()
    (research / "trial_index.json").write_text('{"schema_version":"0.1.0","trials":{}}\n', encoding="utf-8")
    row = {"trial_id": "trial_test"}
    with pytest.raises(RuntimeError, match="missing from canonical ledger"):
        execution._verify_ledger_membership(run_dir, row, research)

    digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
    (research / "trial_index.json").write_text(json.dumps({
        "schema_version": "0.1.0",
        "trials": {"trial_test": {"variant_id": "variant_00eb140f03a5f6ab40600160", "receipt_sha256": digest}},
    }) + "\n", encoding="utf-8")
    execution._verify_ledger_membership(run_dir, row, research)


def test_execution_surface_is_frozen_but_not_invoked_by_tests() -> None:
    assert callable(execution.execute_frozen_plan)
    assert callable(execution.verify_complete_receipts)
    assert callable(execution.analyze_frozen_results)
