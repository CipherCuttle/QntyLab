"""One-shot real-data adapter for the frozen JFPV2 PR-B implementation."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from qntylab import jfp_v2_pr_b as prb

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v2/historical_execution_v0"
SNAPSHOT = prb.RDS_ROOT
EXPECTED_MASTER = "258d225a68903790451f8aa10706af8f309d7fce"
IMPLEMENTATION_COMMIT = "5084df5f6aa3f469f2f2844972745703849abe30"
IMPLEMENTATION_SOURCE_DIGEST = "379f9655bfb9b007da839656c99ffd34f6e72116f0ab82d0a639949742788118"
SCHEDULE_DIGEST = "73859b2ece7a81a1d9f4a24dfb996b21c4427f1b1449d31553541eef66c2d040"
EXECUTION_SEMANTICS_DIGEST = "f3c50c7fd8d34efdaff37582cfd733c00c14c4aeb065c6ad138eb8d00ac174c6"
PREEXECUTION_SCHEMA = {
    "candidate_result_fields": list(prb.RESULT_FIELDS),
    "artifacts": ["execution_authority.json", "execution_manifest.json", "candidate_results.json", "family_result.json", "execution_receipt.json", "hostile_review.md", "closure.json"],
    "scientific_execution_count": 1,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def verify_implementation_identity() -> None:
    source = ROOT / "qntylab/jfp_v2_pr_b.py"
    if sha(source) != IMPLEMENTATION_SOURCE_DIGEST:
        raise RuntimeError("frozen implementation source digest mismatch")
    recorded = subprocess.check_output(["git", "show", f"{IMPLEMENTATION_COMMIT}:qntylab/jfp_v2_pr_b.py"], cwd=ROOT)
    if hashlib.sha256(recorded).hexdigest() != IMPLEMENTATION_SOURCE_DIGEST:
        raise RuntimeError("frozen implementation commit identity mismatch")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def frozen_paths() -> dict[str, Path]:
    base = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v2"
    return {
        "preregistration": base / "preregistration.json",
        "contract": base / "contract_compile.json",
        "capability": base / "data_capabilities.json",
        "schedule": base / "implementation_v0/origin_schedule.json",
        "semantics": base / "implementation_v0/execution_semantics_v0.json",
    }


def verify_frozen_inputs() -> dict[str, Any]:
    paths = frozen_paths()
    expected = {
        "preregistration": prb.PREREG_DIGEST,
        "contract": prb.CONTRACT_DIGEST,
        "capability": prb.CAPABILITY_DIGEST,
        "schedule": sha(paths["schedule"]),
        "semantics": sha(paths["semantics"]),
    }
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"missing frozen artifact: {path}")
        if name in ("preregistration", "contract", "capability") and sha(path) != expected[name]:
            raise RuntimeError(f"frozen {name} digest mismatch")
    schedule = load_json(paths["schedule"])
    if schedule["schedule_digest"] != SCHEDULE_DIGEST or len(schedule["origins"]) != 608:
        raise RuntimeError("origin schedule identity mismatch")
    if expected["semantics"] != EXECUTION_SEMANTICS_DIGEST:
        raise RuntimeError("execution semantics identity mismatch")
    return {"paths": {k: str(v.relative_to(ROOT)) for k, v in paths.items()}, "digests": expected, "schedule_digest": schedule["schedule_digest"], "origin_count": len(schedule["origins"])}


def freeze_authority() -> dict[str, Any]:
    frozen = verify_frozen_inputs()
    authority = {
        "artifact_type": "JFPV2_PR_C_ONE_SHOT_EXECUTION_AUTHORITY",
        "phase": "FAST_LANE_V2_PR_C",
        "execution_start_master": EXPECTED_MASTER,
        "local_start_head": git_head(),
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "implementation_source_digest": IMPLEMENTATION_SOURCE_DIGEST,
        "preregistration_digest": prb.PREREG_DIGEST,
        "contract_digest": prb.CONTRACT_DIGEST,
        "source_capability_digest": prb.CAPABILITY_DIGEST,
        "source_snapshot_id": prb.SOURCE_ID,
        "source_snapshot_digest": prb.SOURCE_DIGEST,
        "origin_schedule_digest": SCHEDULE_DIGEST,
        "execution_semantics_digest": EXECUTION_SEMANTICS_DIGEST,
        "finalists": list(prb.FINALISTS),
        "family_size": 2,
        "real_execution_count_authorized": 1,
        "network_market_data_used": False,
        "source_substitution": False,
        "alternate_specification": False,
        "output_schema": PREEXECUTION_SCHEMA,
        "frozen_at_utc": now(),
        "frozen_inputs": frozen,
    }
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_ROOT / "execution_authority.json").write_text(json.dumps(authority, indent=2, sort_keys=True) + "\n")
    return authority


def validate_source() -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    manifest = load_json(SNAPSHOT / "manifest.json")
    if manifest["snapshot_id"] != prb.SOURCE_ID or manifest["snapshot_digest"] != prb.SOURCE_DIGEST:
        raise RuntimeError("source snapshot identity mismatch")
    if [p["instrument_identity"]["symbol"] for p in manifest["ordered_partitions"]] != list(prb.PANEL):
        raise RuntimeError("exact panel identity mismatch")
    prices: dict[str, dict[str, float]] = {}
    checks = []
    for part in manifest["ordered_partitions"]:
        symbol = part["instrument_identity"]["symbol"]
        path = SNAPSHOT / part["relative_path"]
        if sha(path) != part["parquet_byte_sha256"]:
            raise RuntimeError(f"partition byte digest mismatch: {symbol}")
        frame = pl.read_parquet(path, columns=["instrument_instance_id", "symbol", "bar_open_time", "bar_close_time", "close"])
        rows = frame.to_dicts()
        if frame.height != part["row_count"] or any(row["symbol"] != symbol or row["instrument_instance_id"] != part["instrument_identity"]["instrument_instance_id"] for row in rows):
            raise RuntimeError(f"partition structural integrity mismatch: {symbol}")
        timestamps = [row["bar_open_time"] for row in rows]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise RuntimeError(f"partition timestamp integrity mismatch: {symbol}")
        prices[symbol] = {row["bar_open_time"]: float(row["close"]) for row in rows}
        checks.append({"symbol": symbol, "row_count": frame.height, "byte_sha256": sha(path), "identity_pass": True, "timestamp_pass": True})
    return {"source_identity": prb.SOURCE_ID, "source_snapshot_digest": prb.SOURCE_DIGEST, "panel": list(prb.PANEL), "partition_checks": checks, "panel_size": len(checks), "source_binding_pass": True, "source_integrity_pass": True, "network_market_data_used": False, "source_substitution": False}, prices


def close(prices: dict[str, dict[str, float]], symbol: str, at: datetime) -> float:
    key = at.isoformat().replace("+00:00", "Z")
    return prices[symbol][key]


def return_vector(prices: dict[str, dict[str, float]], at: datetime) -> dict[str, float]:
    previous = at - timedelta(hours=1)
    return {symbol: prb.hourly_log_return(close(prices, symbol, previous), close(prices, symbol, at)) for symbol in prb.PANEL}


def build_rows(prices: dict[str, dict[str, float]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows04, rows06 = [], []
    blocked = []
    for origin in prb.origin_schedule():
        t = datetime.fromisoformat(origin.replace("Z", "+00:00")).astimezone(UTC)
        try:
            current = return_vector(prices, t)
            prior24 = [return_vector(prices, t - timedelta(hours=23 - i)) for i in range(24)]
            future24 = [return_vector(prices, t + timedelta(hours=1 + i)) for i in range(24)]
            rows04.append({"dispersion": prb.sample_sd(tuple(current.values())), "concentration": prb.concentration(current), "future_dispersion": prb.sample_sd(tuple(return_vector(prices, t + timedelta(hours=24)).values()))})
            rows06.append({"panel_rv24": prb.panel_rv24(prior24), "downside_share": prb.downside_share(prior24), "future_panel_rv24": prb.panel_rv24(future24)})
        except (KeyError, prb.PRBBlocked) as exc:
            blocked.append({"origin_timestamp": origin, "block_reason": str(exc)})
    if blocked:
        raise RuntimeError(f"required origin blocked: {blocked[0]}")
    return rows04, rows06


def candidate_result(candidate: str, fit: dict[str, Any], integrity: dict[str, Any], count: int) -> dict[str, Any]:
    f = fit["fit"]
    return {"candidate_id": candidate, "frozen_preregistration_digest": prb.PREREG_DIGEST, "frozen_contract_digest": prb.CONTRACT_DIGEST, "frozen_source_capability_digest": prb.CAPABILITY_DIGEST, "frozen_implementation_sha": IMPLEMENTATION_COMMIT, "input_integrity": integrity, "execution_integrity": {"implementation_source_digest": IMPLEMENTATION_SOURCE_DIGEST, "execution_semantics_digest": EXECUTION_SEMANTICS_DIGEST, "origin_schedule_digest": SCHEDULE_DIGEST}, "eligible_origin_count": count, "blocked_origin_count": 0, "beta_candidate": f["beta"], "hac_standard_error": f["hac_standard_error"], "hac_maxlag": prb.hac_bandwidth(count), "raw_p_two_sided": f["raw_p"], "holm_adjusted_p": None, "materiality_metric_name": fit["materiality_metric_name"], "materiality_metric_value": fit["materiality_metric_value"], "materiality_gate": 0.01 if candidate == "JFPV2_04" else 0.001, "materiality_pass": fit["materiality_pass"], "observed_beta_sign": "POSITIVE" if f["beta"] > 0 else "NEGATIVE" if f["beta"] < 0 else "ZERO", "classification": None, "block_reason": None}


def execute() -> dict[str, Any]:
    authority_path = ARTIFACT_ROOT / "execution_authority.json"
    if not authority_path.is_file():
        raise RuntimeError("pre-execution authority artifact is missing")
    authority = load_json(authority_path)
    if authority["execution_start_master"] != EXPECTED_MASTER or authority["real_execution_count_authorized"] != 1 or authority["alternate_specification"]:
        raise RuntimeError("execution authority mismatch")
    verify_implementation_identity()
    integrity, prices = validate_source()
    rows04, rows06 = build_rows(prices)
    count = len(rows04)
    if count != 608 or len(rows06) != count:
        raise RuntimeError("eligible origin count mismatch")
    results = [candidate_result("JFPV2_04", prb.jfpv2_04_fit(rows04), integrity, count), candidate_result("JFPV2_06", prb.jfpv2_06_fit(rows06), integrity, count)]
    holm = prb.holm_two({r["candidate_id"]: r["raw_p_two_sided"] for r in results})
    for result in results:
        result["holm_adjusted_p"] = holm[result["candidate_id"]]
        result["classification"] = prb.classify(beta=result["beta_candidate"], raw_p=result["raw_p_two_sided"], holm_p=result["holm_adjusted_p"], materiality_pass=result["materiality_pass"])
    result_digest = digest(results)
    manifest = {"artifact_type": "JFPV2_PR_C_EXECUTION_MANIFEST", "authority_digest": sha(authority_path), "execution_start_master": EXPECTED_MASTER, "source_snapshot_id": prb.SOURCE_ID, "source_snapshot_digest": prb.SOURCE_DIGEST, "origin_schedule_digest": SCHEDULE_DIGEST, "implementation_sha": IMPLEMENTATION_COMMIT, "execution_semantics_digest": EXECUTION_SEMANTICS_DIGEST, "eligible_origin_count": count, "blocked_origin_count": 0, "network_market_data_used": False, "source_substitution": False, "execution_timestamp_utc": now(), "runtime": {"python": platform.python_version(), "polars": pl.__version__}}
    (ARTIFACT_ROOT / "execution_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (ARTIFACT_ROOT / "candidate_results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    family = {"artifact_type": "JFPV2_PR_C_FAMILY_RESULT", "family_size": 2, "support_candidates": [r["candidate_id"] for r in results if r["classification"] == "HISTORICAL_SCREEN_SUPPORT"], "no_support_candidates": [r["candidate_id"] for r in results if r["classification"] == "HISTORICAL_SCREEN_NO_SUPPORT"], "blocked_candidates": [r["candidate_id"] for r in results if r["classification"] == "BLOCKED_CANDIDATE"], "family_verdict": "FAST_LANE_HISTORICAL_SURVIVOR" if any(r["classification"] == "HISTORICAL_SCREEN_SUPPORT" for r in results) else "NO_HISTORICAL_SUPPORT", "authority_boundary": "measurement_only_no_promotion_authority", "result_digest": result_digest}
    (ARTIFACT_ROOT / "family_result.json").write_text(json.dumps(family, indent=2, sort_keys=True) + "\n")
    receipt = {"artifact_type": "JFPV2_PR_C_EXECUTION_RECEIPT", "real_historical_execution_performed": True, "real_historical_execution_lineages": 1, "deterministic_execution_digest": result_digest, "result_digest": sha(ARTIFACT_ROOT / "candidate_results.json"), "determinism_claim": "exact frozen computation; no alternate specification"}
    (ARTIFACT_ROOT / "execution_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return {"manifest": manifest, "results": results, "family": family, "receipt": receipt}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "execute"))
    args = parser.parse_args()
    print(json.dumps(freeze_authority() if args.command == "freeze" else execute(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
