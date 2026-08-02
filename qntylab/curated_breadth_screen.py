from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .research_ledger import compute_trial_id, compute_variant_id
from .strategy_test import (
    EXPECTED_INTERVAL_1H,
    GAP_POLICY_REJECT,
    NOT_APPLICABLE,
    SCHEMA_VERSION,
    STRATEGY_VERSION,
    sha256_path,
)


def _load_spec(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("screen spec must be a JSON object")
    return value


def expand_planned_runs(spec_path: Path, *, repo_root: Path | None = None) -> list[dict[str, Any]]:
    spec = _load_spec(spec_path)
    root = repo_root or spec_path.resolve().parents[2]
    if spec["screen_id"] != "CURATED_BREADTH_SCREEN_V1":
        raise ValueError(f"unsupported screen_id: {spec['screen_id']!r}")
    if spec["status"] != "REGISTERED_NOT_EXECUTED":
        raise ValueError(f"screen status is not REGISTERED_NOT_EXECUTED: {spec['status']!r}")
    if [item["candidate_id"] for item in spec["candidate_details"]] != spec["new_candidate_ids"]:
        raise ValueError("candidate_details order must match new_candidate_ids")
    if [item["variant_id"] for item in spec["candidate_details"]] != spec["new_variant_ids"]:
        raise ValueError("candidate_details order must match new_variant_ids")

    planned: list[dict[str, Any]] = []
    for candidate in spec["candidate_details"]:
        config_base = {
            "schema_version": SCHEMA_VERSION,
            "strategy_id": candidate["strategy_id"],
            "strategy_version": STRATEGY_VERSION,
            "initial_capital": 10000,
            "funding_boundary_mode": NOT_APPLICABLE,
            "gap_policy": GAP_POLICY_REJECT,
            "expected_interval": EXPECTED_INTERVAL_1H,
            "candidate_id": candidate["candidate_id"],
            "research_intent": "SCREEN",
            "parameters": candidate["parameters"],
        }
        if compute_variant_id(config_base) != candidate["variant_id"]:
            raise ValueError(f"variant identity mismatch: {candidate['candidate_id']}")
        for symbol in spec["assets"]:
            input_path = spec["input_paths"][symbol]
            input_sha256 = sha256_path(root / input_path)
            for period_name, period in spec["periods"].items():
                for cost_mode, costs in spec["cost_modes"].items():
                    config = dict(
                        config_base,
                        input_path=input_path,
                        evaluation_start=period["start"],
                        evaluation_end=period["end"],
                        fee_bps=float(costs["fee_bps"]),
                        slippage_bps=float(costs["slippage_bps"]),
                    )
                    variant_id = compute_variant_id(config)
                    trial_id = compute_trial_id(
                        variant_id=variant_id,
                        symbol=symbol,
                        input_sha256=input_sha256,
                        evaluation_start=config["evaluation_start"],
                        evaluation_end=config["evaluation_end"],
                        fee_bps=config["fee_bps"],
                        slippage_bps=config["slippage_bps"],
                        gap_policy=config["gap_policy"],
                        expected_interval=config["expected_interval"],
                    )
                    planned.append(
                        {
                            "screen_id": spec["screen_id"],
                            "candidate_id": candidate["candidate_id"],
                            "variant_id": variant_id,
                            "symbol": symbol,
                            "period": period_name,
                            "cost_mode": cost_mode,
                            "trial_id": trial_id,
                            "config": config,
                        }
                    )
    if len(planned) != spec["expected_new_run_count"]:
        raise ValueError(f"planned run count mismatch: {len(planned)}")
    if len({run["trial_id"] for run in planned}) != len(planned):
        raise ValueError("planned trial identities are not unique")
    return planned
