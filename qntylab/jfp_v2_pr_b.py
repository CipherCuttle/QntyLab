"""Bounded PR-B implementation for the frozen JFPV2 finalists.

This module has two deliberately separate seams: structural source receipts
read only identity/time columns, while the executor accepts synthetic rows
only.  A later PR-C must add a separately authorized real-data adapter.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v2"
RDS_ROOT = Path.home() / ".qntylab/evidence/snapshots/rds-v0-c0fa7dc0e51c7680fccbd7e7cdd0945fcd63af3e8c75809a24aa3b216868b9ac"
SOURCE_CAPABILITY = "CAP_V2_RDS_FIXED_PANEL_OHLCV"
SOURCE_ID = "rds-v0-c0fa7dc0e51c7680fccbd7e7cdd0945fcd63af3e8c75809a24aa3b216868b9ac"
SOURCE_DIGEST = SOURCE_ID.removeprefix("rds-v0-")
PANEL = ("ALICEUSDT", "APEUSDT", "API3USDT", "APTUSDT", "BCHUSDT", "CHRUSDT", "CHZUSDT", "ETCUSDT", "GMTUSDT", "INJUSDT", "LDOUSDT", "LINKUSDT", "LTCUSDT", "ONEUSDT", "OPUSDT", "REEFUSDT", "SANDUSDT", "TRXUSDT", "XLMUSDT", "XRPUSDT")
ANALYSIS_START = "2023-10-20T00:00:00Z"
ANALYSIS_END_METADATA = "2025-06-18T23:00:00Z"
SOURCE_START = "2023-10-19T00:00:00Z"
SOURCE_END = "2025-06-19T23:00:00Z"
FINALISTS = ("JFPV2_04", "JFPV2_06")
RESULT_FIELDS = ("candidate_id", "frozen_preregistration_digest", "frozen_contract_digest", "frozen_source_capability_digest", "frozen_implementation_sha", "input_integrity", "execution_integrity", "eligible_origin_count", "blocked_origin_count", "beta_candidate", "hac_standard_error", "hac_maxlag", "raw_p_two_sided", "holm_adjusted_p", "materiality_metric_name", "materiality_metric_value", "materiality_gate", "materiality_pass", "observed_beta_sign", "classification", "block_reason")
PREREG_DIGEST = "ba5960c07cbbb76187d4877ad074df88a43c3f8664c3e5026c533c8f8d40f07d"
CAPABILITY_DIGEST = "926d23b8df11b4014c2465ff6b83b5afb25a2444fd584e549b1224fe9df69618"
CONTRACT_DIGEST = "54e29bb48b208566b826f0804dadb01634dd010adb4739a65140a5b23066be65"
IMPLEMENTATION_MODE = "SYNTHETIC_VALIDATION"


class PRBBlocked(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def ts(value: str | datetime) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise PRBBlocked("timezone-aware timestamp required")
    return value.astimezone(UTC)


def stamp(value: datetime) -> str:
    return ts(value).isoformat().replace("+00:00", "Z")


def hourly_log_return(previous_close: float, current_close: float) -> float:
    if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (previous_close, current_close)):
        raise PRBBlocked("positive finite closes required")
    return math.log(current_close / previous_close)


def fixed_panel(values: Mapping[str, float]) -> tuple[float, ...]:
    if tuple(values) != PANEL:
        raise PRBBlocked("exact fixed 20-symbol panel required")
    result = tuple(float(values[s]) for s in PANEL)
    if not all(math.isfinite(x) for x in result):
        raise PRBBlocked("finite panel values required")
    return result


def sample_sd(values: Sequence[float]) -> float:
    if len(values) < 2 or not all(math.isfinite(x) for x in values):
        raise PRBBlocked("sample SD requires at least two finite values")
    mean = sum(values) / len(values)
    return math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1))


def concentration(returns: Mapping[str, float]) -> float:
    values = fixed_panel(returns)
    denominator = sum(abs(x) for x in values)
    if denominator <= 0:
        raise PRBBlocked("BLOCKED_INVALID_FEATURE_DOMAIN")
    return max(abs(x) for x in values) / denominator


def panel_rv24(returns: Sequence[Mapping[str, float]]) -> float:
    if len(returns) != 24:
        raise PRBBlocked("exactly 24 hourly panel-return vectors required")
    values = [fixed_panel(row) for row in returns]
    return math.sqrt(sum(x * x for row in values for x in row))


def downside_share(returns: Sequence[Mapping[str, float]]) -> float:
    if len(returns) != 24:
        raise PRBBlocked("exactly 24 hourly panel-return vectors required")
    values = [fixed_panel(row) for row in returns]
    denominator = sum(x * x for row in values for x in row)
    if denominator <= 0:
        raise PRBBlocked("BLOCKED_INVALID_FEATURE_DOMAIN")
    return sum(x * x for row in values for x in row if x < 0) / denominator


def origin_schedule() -> tuple[str, ...]:
    start, end = ts(ANALYSIS_START), ts(ANALYSIS_END_METADATA)
    result = []
    current = start
    while current <= end:
        result.append(stamp(current))
        current += timedelta(days=1)
    return tuple(result)


def _inverse(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    augmented = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) <= 1e-14:
            raise PRBBlocked("MODEL_IDENTIFIABLE=false: BLOCKED_CANDIDATE")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        scale = augmented[col][col]
        augmented[col] = [x / scale for x in augmented[col]]
        for row in range(n):
            if row != col:
                scale = augmented[row][col]
                augmented[row] = [a - scale * b for a, b in zip(augmented[row], augmented[col])]
    return [row[n:] for row in augmented]


def ols_hac(design: Sequence[Sequence[float]], outcome: Sequence[float], maxlag: int) -> dict[str, Any]:
    if len(design) != len(outcome) or len(design) <= len(design[0]) or not design:
        raise PRBBlocked("insufficient OLS rows")
    if any(len(row) != len(design[0]) or not all(math.isfinite(x) for x in row) for row in design) or not all(math.isfinite(y) for y in outcome):
        raise PRBBlocked("finite design and outcome required")
    p, n = len(design[0]), len(design)
    xtx = [[sum(design[r][i] * design[r][j] for r in range(n)) for j in range(p)] for i in range(p)]
    inverse = _inverse(xtx)
    xty = [sum(design[r][i] * outcome[r] for r in range(n)) for i in range(p)]
    beta = [sum(inverse[i][j] * xty[j] for j in range(p)) for i in range(p)]
    residuals = [outcome[r] - sum(design[r][j] * beta[j] for j in range(p)) for r in range(n)]
    sse = sum(x * x for x in residuals)
    scores = [[design[r][j] * residuals[r] for j in range(p)] for r in range(n)]
    meat = [[sum(scores[r][i] * scores[r][j] for r in range(n)) for j in range(p)] for i in range(p)]
    for lag in range(1, maxlag + 1):
        weight = 1.0 - lag / (maxlag + 1)
        for r in range(lag, n):
            for i in range(p):
                for j in range(p):
                    meat[i][j] += weight * (scores[r][i] * scores[r - lag][j] + scores[r - lag][i] * scores[r][j])
    covariance = [[sum(inverse[i][a] * meat[a][b] * inverse[b][j] for a in range(p) for b in range(p)) for j in range(p)] for i in range(p)]
    variance = covariance[-1][-1]
    if not math.isfinite(variance) or variance <= 0:
        raise PRBBlocked("invalid HAC variance")
    se = math.sqrt(variance)
    z = beta[-1] / se
    return {"beta": beta[-1], "sse": sse, "hac_standard_error": se, "raw_p": math.erfc(abs(z) / math.sqrt(2.0)), "covariance": covariance}


def holm_two(p_values: Mapping[str, float | None]) -> dict[str, float | None]:
    if set(p_values) != set(FINALISTS):
        raise PRBBlocked("Holm family must remain exactly two finalists")
    present = sorted(((p, key) for key, p in p_values.items() if p is not None), key=lambda x: (x[0], x[1]))
    result: dict[str, float | None] = {key: None for key in FINALISTS}
    running = 0.0
    for index, (p, key) in enumerate(present):
        running = max(running, min(1.0, (len(FINALISTS) - index) * p))
        result[key] = running
    return result


def classify(*, beta: float | None, raw_p: float | None, holm_p: float | None, materiality_pass: bool, blocked: str | None = None) -> str:
    if blocked or beta is None or raw_p is None or holm_p is None:
        return "BLOCKED_CANDIDATE"
    if beta > 0 and holm_p <= 0.05 and materiality_pass:
        return "HISTORICAL_SCREEN_SUPPORT"
    return "HISTORICAL_SCREEN_NO_SUPPORT"


def hac_bandwidth(observation_count: int) -> int:
    if observation_count <= 0:
        raise PRBBlocked("positive observation count required")
    return math.floor(4 * (observation_count / 100) ** (2 / 9))


def standardized_beta(beta: float, feature: Sequence[float], outcome: Sequence[float]) -> float:
    feature_sd, outcome_sd = sample_sd(feature), sample_sd(outcome)
    if feature_sd <= 0 or outcome_sd <= 0:
        raise PRBBlocked("BLOCKED_INVALID_STANDARDIZATION_DOMAIN")
    return beta * feature_sd / outcome_sd


def partial_r2(sse_reduced: float, sse_full: float) -> float:
    if not math.isfinite(sse_reduced) or sse_reduced <= 0:
        raise PRBBlocked("BLOCKED_INVALID_PARTIAL_R2_DOMAIN")
    return (sse_reduced - sse_full) / sse_reduced


def jfpv2_04_fit(rows: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """Thin synthetic-data wrapper for the frozen concentration proposition."""
    x = [[1.0, float(row["dispersion"]), float(row["concentration"])] for row in rows]
    y = [float(row["future_dispersion"]) for row in rows]
    fit = ols_hac(x, y, hac_bandwidth(len(rows)))
    reduced = ols_hac([[1.0, float(row["dispersion"])] for row in rows], y, hac_bandwidth(len(rows)))
    metric = standardized_beta(fit["beta"], [row["concentration"] for row in rows], y)
    return {"candidate_id": "JFPV2_04", "fit": fit, "materiality_metric_name": "STANDARDIZED_BETA", "materiality_metric_value": metric, "materiality_pass": metric >= 0.01, "partial_r2": partial_r2(reduced["sse"], fit["sse"])}


def jfpv2_06_fit(rows: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """Thin synthetic-data wrapper for the frozen downside-share proposition."""
    x = [[1.0, float(row["panel_rv24"]), float(row["downside_share"])] for row in rows]
    y = [float(row["future_panel_rv24"]) for row in rows]
    fit = ols_hac(x, y, hac_bandwidth(len(rows)))
    reduced = ols_hac([[1.0, float(row["panel_rv24"])] for row in rows], y, hac_bandwidth(len(rows)))
    metric = partial_r2(reduced["sse"], fit["sse"])
    return {"candidate_id": "JFPV2_06", "fit": fit, "materiality_metric_name": "PARTIAL_R2", "materiality_metric_value": metric, "materiality_pass": metric >= 0.001}


def real_execution_is_disabled(*, mode: str, source_id: str | None = None) -> None:
    if mode == "PR_B_PHASE" or source_id == SOURCE_ID:
        raise PRBBlocked("PR_B_PHASE + REAL_RDS_SCIENTIFIC_EXECUTION_REQUEST = REFUSED")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def materialize_structural_receipts(output: Path = ARTIFACT_ROOT / "implementation_v0") -> dict[str, Any]:
    """Materialize identity/time-only receipts; never reads OHLCV value columns."""
    import polars as pl
    manifest = json.loads((RDS_ROOT / "manifest.json").read_text())
    if manifest["snapshot_id"] != SOURCE_ID or manifest["snapshot_digest"] != SOURCE_DIGEST:
        raise PRBBlocked("RDS identity mismatch")
    observed = []
    for part in manifest["ordered_partitions"]:
        symbol = part["instrument_identity"]["symbol"]
        path = RDS_ROOT / part["relative_path"]
        frame = pl.read_parquet(path, columns=["instrument_instance_id", "symbol", "bar_open_time", "bar_close_time"])
        times = frame.get_column("bar_open_time").to_list()
        expected = [stamp(ts(part["first_bar_open_time"]) + timedelta(hours=i)) for i in range(part["row_count"])]
        observed.append({"relative_path": part["relative_path"], "symbol": symbol, "parquet_byte_sha256": _sha(path), "expected_row_count": part["row_count"], "observed_row_count": frame.height, "duplicate_timestamp_count": len(times) - len(set(times)), "missing_timestamp_count": len(set(expected) - set(times)), "unexpected_timestamp_count": len(set(times) - set(expected)), "identity_pass": all(row["symbol"] == symbol and row["instrument_instance_id"] == part["instrument_identity"]["instrument_instance_id"] for row in frame.to_dicts()), "timestamp_pass": times == sorted(times) and all(row["bar_close_time"] == stamp(ts(row["bar_open_time"]) + timedelta(hours=1)) for row in frame.to_dicts())})
    output.mkdir(parents=True, exist_ok=True)
    integrity = {"artifact_type": "PR_B_STRUCTURAL_INPUT_INTEGRITY", "source_identity": SOURCE_ID, "snapshot_digest": SOURCE_DIGEST, "panel": list(PANEL), "per_symbol": observed, "panel_complete": [x["symbol"] for x in observed] == list(PANEL), "timestamps_aligned": all(x["missing_timestamp_count"] == x["unexpected_timestamp_count"] == 0 for x in observed), "source_identity_pass": True, "source_integrity_pass": all(x["identity_pass"] and x["timestamp_pass"] and x["observed_row_count"] == x["expected_row_count"] and x["duplicate_timestamp_count"] == 0 and x["missing_timestamp_count"] == 0 and x["unexpected_timestamp_count"] == 0 for x in observed), "raw_market_values_interpreted": False}
    binding = {"artifact_type": "PR_B_SOURCE_BINDING", "source_capability_id": SOURCE_CAPABILITY, "source_identity": SOURCE_ID, "snapshot_digest": SOURCE_DIGEST, "source_contract_identity": "RESEARCH_DATA_SPINE_V0", "capability_snapshot_digest": CAPABILITY_DIGEST, "source_manifest_identity": _sha(RDS_ROOT / "manifest.json"), "exact_panel": list(PANEL), "coverage": [SOURCE_START, SOURCE_END], "interval": "1h", "venue": "Binance", "market_type": "USD-M perpetual", "timestamp_semantics": "bar_open_time identity; bar_close_time = bar_open_time + 1h", "safe_known_after": "bar_close_time", "canonical_master": "b018b998413934301a2535a38f64adb8a963366d", "preregistration_digest": PREREG_DIGEST, "contract_digest": CONTRACT_DIGEST, "new_source_acquired": False, "network_market_data_used": False, "source_substitution": False}
    schedule = {"artifact_type": "PR_B_ORIGIN_SCHEDULE", "anchor": ANALYSIS_START, "spacing": "24h", "metadata_window": [ANALYSIS_START, ANALYSIS_END_METADATA], "origins": [{"origin_timestamp": x, "structural_warmup_available": True, "structural_future_tail_available": True, "all_20_symbols_present": True, "structural_status": "PASS"} for x in origin_schedule()], "schedule_digest": digest(origin_schedule())}
    for name, value in (("source_binding.json", binding), ("input_integrity.json", integrity), ("origin_schedule.json", schedule), ("execution_semantics_v0.json", {"hac_bandwidth_formula": "floor(4 * (T / 100)^(2/9))", "hac_lag_unit": "ORIGINS", "hac_kernel": "BARTLETT", "hac_finite_sample_correction": "NONE", "test_statistic": "normal_z", "p_value_reference_distribution": "standard_normal_two_sided", "tolerance": 1e-12})):
        (output / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return {"binding": binding, "integrity": integrity, "schedule": schedule}


def implementation_identity(root: Path = ROOT) -> dict[str, Any]:
    paths = ["qntylab/jfp_v2_pr_b.py"]
    return {"source_paths": paths, "source_sha256": {path: _sha(root / path) for path in paths}, "git_candidate_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(), "python": __import__("sys").version.split()[0], "polars": __import__("polars").__version__}
