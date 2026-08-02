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
    validate_normalization_provenance,
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _asset_provenance(root: Path, derived_path: str) -> dict[str, str]:
    manifest_path = Path(derived_path).with_suffix(".manifest.json")
    manifest = _load_json(root / manifest_path)
    provenance = {
        "normalization_id": manifest["normalization_id"],
        "normalization_version": manifest["normalization_version"],
        "reason_code": manifest["reason_code"],
        "derived_input_path": manifest["derived_path"],
        "derived_input_sha256": manifest["derived_sha256"],
        "derived_manifest_path": str(manifest_path),
        "derived_manifest_sha256": sha256_path(root / manifest_path),
        "source_resolution_artifact_path": manifest["source_resolution_artifact_path"],
        "source_resolution_artifact_sha256": manifest["source_resolution_artifact_sha256"],
        "authoritative_raw_path": manifest["authoritative_raw_path"],
        "authoritative_raw_sha256": manifest["authoritative_raw_sha256"],
        "normalized_timestamp": manifest["normalized_timestamp"],
    }
    validate_normalization_provenance(
        provenance=provenance,
        normalized_input=(root / derived_path).resolve(),
        input_sha256=provenance["derived_input_sha256"],
        config_path=root / "experiments/specs/focused_trend_validation_v1.json",
    )
    return provenance


def expand_planned_holdout_runs(spec_path: Path, *, repo_root: Path | None = None) -> list[dict[str, Any]]:
    spec = _load_json(spec_path)
    root = repo_root or spec_path.resolve().parents[2]
    if spec["preregistration_id"] != "PREREGISTER_FOCUSED_TREND_VALIDATION_V1":
        raise ValueError(f"unsupported preregistration_id: {spec['preregistration_id']!r}")
    if spec["status"] != "REGISTERED_NOT_EXECUTED":
        raise ValueError(f"validation status is not REGISTERED_NOT_EXECUTED: {spec['status']!r}")
    track = spec["tracks"]["A_untouched_2023_holdout"]
    period = track["period"]
    if period["id"] != "2023_UNTOUCHED_HOLDOUT":
        raise ValueError(f"unsupported holdout period: {period['id']!r}")
    variants = {item["variant_id"]: item for item in spec["variants"]}
    if set(variants) != {item["variant_id"] for item in track["planned_trials"]}:
        raise ValueError("planned trials do not match registered variants")
    provenance_by_asset = {
        asset: _asset_provenance(root, f"data/derived/focused_trend_validation_v1/{asset}-spot-1h-2023-halt-normalized.csv")
        for asset in spec["assets"]
    }

    planned: list[dict[str, Any]] = []
    for row in track["planned_trials"]:
        variant = variants[row["variant_id"]]
        costs = spec["cost_modes"][row["cost_mode"]]
        provenance = provenance_by_asset[row["asset"]]
        config = {
            "schema_version": SCHEMA_VERSION,
            "strategy_id": variant["strategy_id"],
            "strategy_version": STRATEGY_VERSION,
            "input_path": provenance["derived_input_path"],
            "evaluation_start": period["start"],
            "evaluation_end": period["end"],
            "initial_capital": 10000,
            "fee_bps": float(costs["fee_bps"]),
            "slippage_bps": float(costs["slippage_bps"]),
            "funding_boundary_mode": NOT_APPLICABLE,
            "gap_policy": GAP_POLICY_REJECT,
            "expected_interval": EXPECTED_INTERVAL_1H,
            "candidate_id": variant["candidate_id"],
            "research_intent": "FOLLOW_UP",
            "parameters": variant["parameters"],
            "normalization_provenance": provenance,
        }
        variant_id = compute_variant_id(config)
        if variant_id != row["variant_id"]:
            raise ValueError(f"variant identity mismatch: {variant['candidate_id']}")
        trial_id = compute_trial_id(
            variant_id=variant_id,
            symbol=row["asset"],
            input_sha256=provenance["derived_input_sha256"],
            evaluation_start=period["start"],
            evaluation_end=period["end"],
            fee_bps=config["fee_bps"],
            slippage_bps=config["slippage_bps"],
            gap_policy=config["gap_policy"],
            expected_interval=config["expected_interval"],
        )
        planned.append(
            {
                "preregistration_id": spec["preregistration_id"],
                "candidate_id": variant["candidate_id"],
                "variant_id": variant_id,
                "asset": row["asset"],
                "period": period["id"],
                "cost_mode": row["cost_mode"],
                "research_intent": "FOLLOW_UP",
                "trial_id": trial_id,
                "input_sha256": provenance["derived_input_sha256"],
                "config": config,
            }
        )
    if len(planned) != track["planned_trial_count"]:
        raise ValueError(f"planned run count mismatch: {len(planned)}")
    if len({run["trial_id"] for run in planned}) != len(planned):
        raise ValueError("planned trial identities are not unique")
    return planned
