from __future__ import annotations

import json
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"expected one patch anchor in {path}, got {text.count(old)}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_verdict() -> None:
    path = Path("qntylab/h003_edge_falsification_v0.py")
    replace_once(
        path,
        'required = ("baseline", "stress", "buy_and_hold", "block_random_wins_sharpe", "block_random_wins_calmar", "prior_2023_failure_preserved")\n',
        'required = ("baseline", "stress", "buy_and_hold", "block_random_wins_sharpe", "block_random_wins_calmar", "prior_2023_failure_preserved", "controls_complete")\n',
    )
    replace_once(
        path,
        '    baseline, stress, buyhold = summary["baseline"], summary["stress"], summary["buy_and_hold"]\n',
        '    if summary["prior_2023_failure_preserved"] is not True or summary["controls_complete"] is not True:\n        return "BLOCKED_BY_INPUT_OR_INTEGRITY"\n    baseline, stress, buyhold = summary["baseline"], summary["stress"], summary["buy_and_hold"]\n',
    )


def patch_execution() -> None:
    path = Path("qntylab/h003_edge_falsification_v0_execution.py")
    text = path.read_text(encoding="utf-8")
    helper = '''\n\ndef _verify_ledger_membership(run_dir: Path, row: dict[str, Any], research_root: Path) -> None:\n    index_path = research_root / "trial_index.json"\n    if not index_path.is_file():\n        raise FileNotFoundError(f"missing canonical trial index: {index_path}")\n    index = _read_json(index_path)\n    record = index.get("trials", {}).get(row["trial_id"])\n    if not isinstance(record, dict):\n        raise RuntimeError(f"H003 trial missing from canonical ledger: {row['trial_id']}")\n    if record.get("variant_id") != "variant_00eb140f03a5f6ab40600160":\n        raise RuntimeError(f"H003 ledger variant mismatch: {row['trial_id']}")\n    receipt_path = run_dir / "run_receipt.json"\n    if record.get("receipt_sha256") != strategy_test.sha256_path(receipt_path):\n        raise RuntimeError(f"H003 ledger receipt hash mismatch: {row['trial_id']}")\n'''
    anchor = '\n\ndef verify_complete_receipts(workspace: Path) -> dict[str, dict[str, Any]]:\n'
    if helper.strip() not in text:
        text = text.replace(anchor, helper + '\n\ndef verify_complete_receipts(workspace: Path, *, research_root: Path | None = None) -> dict[str, dict[str, Any]]:\n', 1)
    else:
        raise SystemExit("ledger helper already present unexpectedly")
    text = text.replace(
        '    runs = workspace / "runs"\n    verified: dict[str, dict[str, Any]] = {}\n',
        '    runs = workspace / "runs"\n    ledger_root = research_root or strategy_test.RESEARCH_ROOT\n    verified: dict[str, dict[str, Any]] = {}\n',
        1,
    )
    text = text.replace(
        '        receipt, metrics = _verify_one_receipt(run_dir, row)\n        verified[row["trial_id"]] = {"receipt": receipt, "metrics": metrics, "run_dir": str(run_dir)}\n',
        '        receipt, metrics = _verify_one_receipt(run_dir, row)\n        _verify_ledger_membership(run_dir, row, ledger_root)\n        verified[row["trial_id"]] = {"receipt": receipt, "metrics": metrics, "run_dir": str(run_dir)}\n',
        1,
    )
    text = text.replace(
        '    plan = h003.compile_plan()\n    runs = workspace / "runs"\n',
        '    plan = h003.compile_plan()\n    ledger_root = research_root or strategy_test.RESEARCH_ROOT\n    runs = workspace / "runs"\n',
        1,
    )
    text = text.replace(
        '        if run_dir.exists():\n            _verify_one_receipt(run_dir, row)\n            skipped.append(row["trial_id"])\n',
        '        if run_dir.exists():\n            _verify_one_receipt(run_dir, row)\n            _verify_ledger_membership(run_dir, row, ledger_root)\n            skipped.append(row["trial_id"])\n',
        1,
    )
    text = text.replace(
        '    verified = verify_complete_receipts(workspace)\n',
        '    verified = verify_complete_receipts(workspace, research_root=ledger_root)\n',
        1,
    )
    text = text.replace(
        '    verified = verify_complete_receipts(workspace)\n    plan = h003.compile_plan()\n',
        '    verified = verify_complete_receipts(workspace)\n    plan = h003.compile_plan()\n',
        1,
    )
    text = text.replace(
        '    random_wins_sharpe = 0\n    random_wins_calmar = 0\n',
        '    random_wins_sharpe = 0\n    random_wins_calmar = 0\n    controls_complete = True\n',
        1,
    )
    text = text.replace(
        '        base = block_metrics["baseline"]\n',
        '        if random_median_sharpe is None or random_median_calmar is None:\n            controls_complete = False\n        base = block_metrics["baseline"]\n',
        1,
    )
    text = text.replace(
        '        "prior_2023_failure_preserved": prior_preserved,\n    }\n',
        '        "prior_2023_failure_preserved": prior_preserved,\n        "controls_complete": controls_complete,\n    }\n',
        1,
    )
    text = text.replace(
        '        "trial_count": 44,\n        "prior_2023_failure_preserved": prior_preserved,\n',
        '        "trial_count": 44,\n        "repository_commit": strategy_test._repository_commit(),\n        "implementation_sha256": {\n            "compiler": strategy_test.sha256_path(Path(h003.__file__)),\n            "executor_analyzer": strategy_test.sha256_path(Path(__file__)),\n            "authorization": strategy_test.sha256_path(h003.AUTHORIZATION_PATH),\n            "analysis_contract": strategy_test.sha256_path(h003.ANALYSIS_CONTRACT_PATH),\n            "preregistration": strategy_test.sha256_path(h003.PREREG_PATH),\n        },\n        "prior_2023_failure_preserved": prior_preserved,\n',
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_contract() -> None:
    path = Path("experiments/specs/h003_edge_falsification_v0_analysis_contract.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    value["control_contract_boundary_costs"] = {
        "owned_interval_transition_rule": "For controls defined on reporting-owned return intervals, charge each transition between consecutive reconstructed held states on the preceding owned return, matching QntyLab backtest alignment.",
        "terminal_boundary_rule": "Do not invent a liquidation or exit after the final owned return solely because a reporting block, contiguous segment, or analysis slice ends. This gives controls no extra terminal cost and is conservative against H003.",
        "genuine_gap_rule": "Never charge or infer a transition across a genuine unnormalized gap. Each admitted 2021 contiguous segment constructs controls independently before chronological return concatenation.",
    }
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def patch_tests() -> None:
    path = Path("tests/test_h003_edge_falsification_v0_runner.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '        "prior_2023_failure_preserved": True,\n    }\n',
        '        "prior_2023_failure_preserved": True,\n        "controls_complete": True,\n    }\n',
        1,
    )
    text += '''\n\ndef test_verdict_blocks_on_control_or_prior_evidence_integrity() -> None:\n    summary = {\n        "baseline": {"annualized_sharpe": 1.0, "calmar_ratio": 1.0, "maximum_drawdown": -0.1},\n        "stress": {"annualized_sharpe": 0.5, "calmar_ratio": 0.5},\n        "buy_and_hold": {"annualized_sharpe": 0.2, "calmar_ratio": 0.2, "maximum_drawdown": -0.5},\n        "block_random_wins_sharpe": 6,\n        "block_random_wins_calmar": 6,\n        "prior_2023_failure_preserved": True,\n        "controls_complete": False,\n    }\n    assert h003.verdict(summary) == "BLOCKED_BY_INPUT_OR_INTEGRITY"\n    summary["controls_complete"] = True\n    summary["prior_2023_failure_preserved"] = False\n    assert h003.verdict(summary) == "BLOCKED_BY_INPUT_OR_INTEGRITY"\n\n\ndef test_control_boundary_cost_contract_is_frozen() -> None:\n    contract = json.loads(h003.ANALYSIS_CONTRACT_PATH.read_text(encoding="utf-8"))\n    boundary = contract["control_contract_boundary_costs"]\n    assert "Do not invent a liquidation or exit" in boundary["terminal_boundary_rule"]\n    assert "Never charge or infer a transition across a genuine unnormalized gap" in boundary["genuine_gap_rule"]\n'''
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_verdict()
    patch_execution()
    patch_contract()
    patch_tests()
