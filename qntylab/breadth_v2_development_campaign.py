"""Bounded, resumable Breadth V2 development campaign orchestration.

This module owns campaign identity and progress only.  Candidate execution,
accounting, evidence writing, ledger writes, and family reduction remain in
their canonical modules.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import pickle
from pathlib import Path
from typing import Any, Mapping

from . import breadth_v2_family_decision as reducer
from . import research_ledger
from .breadth_v2_dev_inputs import run_dev_input_acquisition
from .breadth_v2_execution import INSTRUMENT_CONTRACT_ID, breadth_v2_evaluation_id
from .breadth_v2_runner import (
    COST_MODES, FROZEN_PANEL_ORDER, PANEL_EXECUTION_UNIT_ID, REGISTERED_PERIODS,
    REGISTERED_SCREEN_ID, SINGLE_ASSET, SYNCHRONIZED_PANEL,
    enumerate_registered_execution_plan, prepare_breadth_v2_evaluation,
    record_breadth_v2_evaluation, existing_breadth_v2_identities,
)
from .instrument_contract import FUNDING_INCLUDED_PROVENANCE_BOUND

CENSUS_SHA256 = "8fef4c02d113027630072bcbb0802e35ab31be17c835aa2ebdae4261265589fb"
SEALED_T0 = "2026-08-10T19:00:00Z"
CENSUS_PATH = Path("/home/swirky/DevHub/qntylab-evidence/breadth_v2_dev_inputs_v0/manifests/BREADTH_V2_DEV_INPUT_UNIVERSE_V0R1.json")
ARTIFACT_DIR = Path("experiments/results/breadth_v2_development_v0")
MANIFEST_NAME = "BREADTH_V2_DEVELOPMENT_EXECUTION_MANIFEST_V0.json"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _trial_id(variant_id: str, unit_type: str, unit_id: str, period_id: str, cost_mode: str, bundle_sha: str) -> str:
    cost = COST_MODES[cost_mode]
    return research_ledger.compute_trial_id_v2(
        variant_id=variant_id, instrument_contract_id=INSTRUMENT_CONTRACT_ID,
        symbol=unit_id, input_sha256=bundle_sha,
        evaluation_start=REGISTERED_PERIODS[period_id][0], evaluation_end=REGISTERED_PERIODS[period_id][1],
        fee_bps=cost["fee_bps"], slippage_bps=cost["slippage_bps"],
        funding_treatment=FUNDING_INCLUDED_PROVENANCE_BOUND,
        gap_policy="FAIL_CLOSED_NO_GAPS", expected_interval="1h",
    )


def load_census(path: Path = CENSUS_PATH) -> dict[str, Any]:
    census = json.loads(path.read_text(encoding="utf-8"))
    if census.get("campaign_input_universe_sha256") != CENSUS_SHA256:
        raise RuntimeError("V0R1 census digest mismatch")
    if _sha({k: v for k, v in census.items() if k != "campaign_input_universe_sha256"}) != CENSUS_SHA256:
        raise RuntimeError("V0R1 census digest does not recompute")
    expected = {"registered_input_records": 996, "ready_input_records": 748, "blocked_input_records": 248,
                "registered_execution_units": 1992, "ready_mapped_execution_units": 1496,
                "blocked_mapped_execution_units": 496, "registered_scientific_cells": 3360,
                "ready_mapped_scientific_cells": 1952, "blocked_mapped_scientific_cells": 1408}
    if any(census.get(k) != v for k, v in expected.items()):
        raise RuntimeError("V0R1 census counts mismatch")
    if census.get("sealed_t0") != SEALED_T0:
        raise RuntimeError("SEALED_T0 mismatch")
    return census


def _census_index(census: Mapping[str, Any]) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    index = {}
    for row in census["input_records"]:
        key = tuple(row[k] for k in ("family_id", "variant_id", "execution_unit_type", "execution_unit_id", "period_id"))
        if key in index:
            raise RuntimeError("duplicate V0R1 input record")
        index[key] = row
    if len(index) != 996:
        raise RuntimeError("V0R1 census input-record count mismatch")
    return index


def build_manifest(*, repo_root: Path = Path("."), census_path: Path = CENSUS_PATH) -> dict[str, Any]:
    census = load_census(census_path)
    index = _census_index(census)
    source_commit = research_commit(repo_root)
    from .breadth_v2_runner import execution_contract_digest
    descriptors = []
    for d in enumerate_registered_execution_plan():
        key = (d.family_id, d.variant_id, d.execution_unit_type, d.execution_unit_id, d.period_id)
        row = index[key]
        item = {"family_id": d.family_id, "variant_id": d.variant_id,
                "execution_unit_type": d.execution_unit_type, "execution_unit_id": d.execution_unit_id,
                "period_id": d.period_id, "cost_mode": d.cost_mode,
                "input_status": row["status"], "evaluation_input_bundle_sha256": row["evaluation_input_bundle_sha256"],
                "v0r1_blocking_reason": row.get("blocking_reason")}
        if row["status"] == "READY":
            item["breadth_v2_evaluation_id"] = breadth_v2_evaluation_id(
                registered_screen_id=REGISTERED_SCREEN_ID, variant_id=d.variant_id,
                execution_contract_digest=execution_contract_digest(repo_root), execution_unit_type=d.execution_unit_type,
                evaluation_input_bundle_sha256=row["evaluation_input_bundle_sha256"], period_id=d.period_id,
                cost_mode=d.cost_mode, fee_bps=COST_MODES[d.cost_mode]["fee_bps"],
                slippage_bps=COST_MODES[d.cost_mode]["slippage_bps"], instrument_contract_id=INSTRUMENT_CONTRACT_ID)
            item["trial_id"] = _trial_id(d.variant_id, d.execution_unit_type, d.execution_unit_id, d.period_id, d.cost_mode, row["evaluation_input_bundle_sha256"])
        descriptors.append(item)
    if len(descriptors) != 1992 or sum(x["input_status"] == "READY" for x in descriptors) != 1496:
        raise RuntimeError("campaign manifest descriptor counts mismatch")
    manifest = {"artifact_type": "BREADTH_V2_DEVELOPMENT_EXECUTION_MANIFEST_V0",
                "registered_screen_id": REGISTERED_SCREEN_ID, "canonical_source_commit": source_commit,
                "v0r1_census_sha256": CENSUS_SHA256, "family_decision_contract_digest": reducer.CONTRACT_DIGEST,
                "execution_contract_digest": execution_contract_digest(repo_root), "sealed_t0": SEALED_T0,
                "registered_execution_descriptors": descriptors}
    manifest["campaign_execution_manifest_sha256"] = _sha(manifest)
    return manifest


def research_commit(repo_root: Path) -> str:
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, capture_output=True, text=True).stdout.strip()


def write_manifest(manifest: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def materialize_bundles(*, repo_root: Path = Path("."), census_path: Path = CENSUS_PATH, bundle_dir: Path) -> dict[str, Any]:
    """Populate derived bundle cache from the authenticated persistent source cache."""
    result = run_dev_input_acquisition(evidence_root=str(CENSUS_PATH.parent.parent), candidates_path=str(repo_root / "experiments/research/candidates.jsonl"), freeze_commit="2608676b1d353446b00409c63a32b4b6a362c38e", bundle_output_dir=bundle_dir)
    return result["census"]


def _load_bundle(bundle_dir: Path, sha: str, cache: dict[str, Any]) -> dict[str, Any]:
    if sha not in cache:
        path = bundle_dir / f"{sha}.pkl.gz"
        if not path.exists():
            json_path = bundle_dir / f"{sha}.json.gz"
            if not json_path.exists():
                raise RuntimeError(f"missing READY input bundle: {sha}")
            with gzip.open(json_path, "rt", encoding="utf-8") as handle:
                cache[sha] = json.load(handle)
            return cache[sha]
        with gzip.open(path, "rb") as handle:
            cache[sha] = pickle.loads(handle.read())
    return cache[sha]


def _existing_events(root: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    history = research_ledger.load_canonical_history(root)
    events = {e["breadth_v2_evaluation_id"]: e for e in history.trials if e.get("registered_screen_id") == REGISTERED_SCREEN_ID}
    if len(events) != sum(1 for e in history.trials if e.get("registered_screen_id") == REGISTERED_SCREEN_ID):
        raise RuntimeError("duplicate existing Breadth V2 evaluation ID")
    return events, {e["breadth_v2_evaluation_id"] for e in history.trials if e.get("breadth_v2_evaluation_id")}


def execute_campaign(*, manifest: Mapping[str, Any], repo_root: Path = Path("."), bundle_dir: Path, ledger_root: Path = Path("experiments/research"), failures_path: Path | None = None) -> dict[str, Any]:
    descriptors = manifest["registered_execution_descriptors"]
    expected = {x["breadth_v2_evaluation_id"] for x in descriptors if x["input_status"] == "READY"}
    existing, all_existing = _existing_events(ledger_root)
    unexpected = all_existing - expected
    if unexpected:
        raise RuntimeError(f"unexpected Breadth V2 evaluation IDs: {sorted(unexpected)}")
    cache: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    completed = 0
    for item in descriptors:
        if item["input_status"] != "READY":
            continue
        evaluation_id = item["breadth_v2_evaluation_id"]
        if evaluation_id in existing:
            event = existing[evaluation_id]
            if any(event.get(k) != item.get(k) for k in ("breadth_v2_evaluation_id", "trial_id", "evaluation_input_bundle_sha256", "execution_unit_type", "execution_unit_id", "period_id", "cost_mode")):
                raise RuntimeError(f"existing evaluation does not match manifest: {evaluation_id}")
            completed += 1
            continue
        try:
            prepared = prepare_breadth_v2_evaluation(
                variant_id=item["variant_id"], execution_unit_type=item["execution_unit_type"], execution_unit_id=item["execution_unit_id"],
                period_id=item["period_id"], cost_mode=item["cost_mode"], input_bundle=_load_bundle(bundle_dir, item["evaluation_input_bundle_sha256"], cache),
                candidates_path=str(repo_root / "experiments/research/candidates.jsonl"), repo_root=repo_root, ledger_root=ledger_root)
            event = record_breadth_v2_evaluation(prepared, root=ledger_root)
            if event["breadth_v2_evaluation_id"] != evaluation_id or event["trial_id"] != item["trial_id"]:
                raise RuntimeError("recorded identity does not match manifest")
            existing[evaluation_id] = event
            completed += 1
        except Exception as exc:  # preserve an explicit integrity failure and continue independent work
            failure = {"evaluation_id": evaluation_id, "descriptor": item, "error_type": type(exc).__name__, "error": str(exc)}
            failures.append(failure)
            if failures_path:
                failures_path.parent.mkdir(parents=True, exist_ok=True)
                with failures_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(failure, sort_keys=True) + "\n")
    return {"attempted": 1496, "completed": completed, "unexpected_integrity_blocked": len(failures), "failures": failures}
