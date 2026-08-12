"""One-shot executor for the frozen JH01 temporal replication.

The module is intentionally local-only.  Its scientific builder accepts
synthetic panels for Stage A; :func:`execute_once` is the sole real-input path
and creates an exclusive start sentinel before transforming any closes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import jh01_rv_persistence_temporal_replication_input_materialization_v0 as materialization
from . import jh01_rv_persistence_temporal_replication_prereg_v0 as prereg


PHASE_ID = "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_EXECUTION_V0"
EXECUTION_AUTHORIZATION_BASE_SHA = "56ec5640afa6bcbbe3857c9598068446166f0772"
PREREGISTRATION_DIGEST = "46f923023b4b696307da2b9d6fc4c8db9d04b40b012de35e0bf738cc03c4be57"
INPUT_QUALIFICATION_DIGEST = "8f82db32ce0f453f6f67e5cd4b421e0848752b7f24a9b39f05ec979fe9382593"
SNAPSHOT_ID = "jh01-rv-temporal-input-v0-ce0e0d1945eb5d6096cc8c24933e0ec19bb8a882c4cce526cb01ff4487b11efa"
SNAPSHOT_DIGEST = "ce0e0d1945eb5d6096cc8c24933e0ec19bb8a882c4cce526cb01ff4487b11efa"
UNIVERSE = prereg.UNIVERSE
UNIVERSE_DIGEST = "e6d1447ff2be57f81eaf943b62218ce9a7b9a6f5bf2d25f9be255cb3f2040cd8"
FIRST_DECISION = prereg.FIRST_DECISION
LAST_DECISION = prereg.LAST_DECISION
OBSERVATION_COUNT = 365
HAC_LAG = 5
HAC_CRITICAL_VALUE_95 = 1.959963984540054
ARTIFACT_RELATIVE = Path("experiments/research/jh01_rv_persistence_temporal_replication_v0")
RAW_RELATIVE = Path("data/raw/jh01_rv_persistence_temporal_replication_v0")
MODULE_RELATIVE = Path("qntylab/jh01_rv_persistence_temporal_replication_execution_v0.py")


class ExecutionContractError(ValueError):
    """A frozen identity, input, or mathematical invariant has failed."""


class ExecutionAlreadyStartedError(RuntimeError):
    """A prior real-science attempt makes any automatic retry impermissible."""


@dataclass(frozen=True)
class BarClose:
    bar_open_time: datetime
    close: float
    safe_known_after: datetime


@dataclass(frozen=True)
class DesignRow:
    decision_time: datetime
    rv24_prior: float
    rv24_future: float


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Mapping[str, Any], *, omitted_field: str) -> str:
    return hashlib.sha256(canonical_bytes({key: item for key, item in value.items() if key != omitted_field})).hexdigest()


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ExecutionContractError("timezone-aware UTC timestamp required")
    result = value.astimezone(UTC)
    if result.minute or result.second or result.microsecond:
        raise ExecutionContractError("hour-aligned timestamp required")
    return result


def _stamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_schedule() -> tuple[datetime, ...]:
    first, last = _utc(FIRST_DECISION), _utc(LAST_DECISION)
    schedule = tuple(first + timedelta(days=index) for index in range(OBSERVATION_COUNT))
    if schedule[-1] != last or math.floor(4 * (len(schedule) / 100) ** (2 / 9)) != HAC_LAG:
        raise AssertionError("frozen JH01 schedule/HAC contract drift")
    return schedule


def asset_log_return(previous_close: float, current_close: float) -> float:
    if not all(isinstance(item, (int, float)) and math.isfinite(item) and item > 0 for item in (previous_close, current_close)):
        raise ExecutionContractError("positive finite closes required")
    return math.log(float(current_close) / float(previous_close))


def market_hourly_return(asset_returns: Mapping[str, float]) -> float:
    if tuple(asset_returns) != UNIVERSE:
        raise ExecutionContractError("market return requires the exact ordered 20-symbol universe")
    values = tuple(asset_returns[symbol] for symbol in UNIVERSE)
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        raise ExecutionContractError("finite asset log returns required")
    return sum(values) / len(UNIVERSE)


def market_rv24(hourly_market_returns: Sequence[float]) -> float:
    if len(hourly_market_returns) != 24 or any(not math.isfinite(value) for value in hourly_market_returns):
        raise ExecutionContractError("RV24 requires exactly 24 finite hourly market returns")
    return math.sqrt(sum(value * value for value in hourly_market_returns))


def _validate_panel(bars_by_symbol: Mapping[str, Sequence[BarClose]]) -> dict[str, dict[datetime, BarClose]]:
    if tuple(bars_by_symbol) != UNIVERSE:
        raise ExecutionContractError("exact ordered 20-symbol panel required")
    expected = tuple(materialization.expected_timestamps())
    result: dict[str, dict[datetime, BarClose]] = {}
    for symbol in UNIVERSE:
        rows = bars_by_symbol[symbol]
        if len(rows) != len(expected):
            raise ExecutionContractError("each panel member requires exactly 8785 bars")
        mapping: dict[datetime, BarClose] = {}
        stamps: list[str] = []
        for row in rows:
            opened, known = _utc(row.bar_open_time), _utc(row.safe_known_after)
            if not isinstance(row.close, (int, float)) or not math.isfinite(row.close) or row.close <= 0:
                raise ExecutionContractError("positive finite close required")
            if known != opened + timedelta(hours=1):
                raise ExecutionContractError("bar-open to close-boundary semantics mismatch")
            if opened in mapping:
                raise ExecutionContractError("duplicate bar open")
            mapping[opened] = row
            stamps.append(_stamp(opened))
        if tuple(stamps) != expected:
            raise ExecutionContractError("raw timestamps must equal the frozen ordered hourly set")
        result[symbol] = mapping
    return result


def rv24_windows_at_decision(*, decision: datetime, market_returns: Mapping[datetime, float], bars: Mapping[str, Mapping[datetime, BarClose]]) -> tuple[tuple[datetime, ...], tuple[datetime, ...]]:
    """Validate the frozen no-leakage RV24 boundaries for one decision time."""
    decision = _utc(decision)
    prior_boundaries = tuple(decision - timedelta(hours=offset) for offset in range(23, -1, -1))
    future_boundaries = tuple(decision + timedelta(hours=offset) for offset in range(1, 25))
    if len(prior_boundaries) != 24 or len(future_boundaries) != 24 or set(prior_boundaries) & set(future_boundaries):
        raise ExecutionContractError("exact non-overlapping 24-return windows required")
    if any(boundary not in market_returns or not math.isfinite(market_returns[boundary]) for boundary in (*prior_boundaries, *future_boundaries)):
        raise ExecutionContractError("required feature/outcome return coverage missing")
    if tuple(bars) != UNIVERSE:
        raise ExecutionContractError("exact ordered 20-symbol panel required")
    if any(bars[symbol][boundary - timedelta(hours=1)].safe_known_after > decision for symbol in UNIVERSE for boundary in prior_boundaries):
        raise ExecutionContractError("feature includes a close not safely known at decision time")
    if any(boundary <= decision for boundary in future_boundaries):
        raise ExecutionContractError("future outcome leakage")
    return prior_boundaries, future_boundaries


def build_design_rows(bars_by_symbol: Mapping[str, Sequence[BarClose]]) -> tuple[DesignRow, ...]:
    """Build exact JH01 rows from a validated (usually synthetic) bar panel."""
    bars = _validate_panel(bars_by_symbol)
    opens = tuple(_utc(materialization.expected_timestamps()[0]) + timedelta(hours=index) for index in range(8785))
    market_returns: dict[datetime, float] = {}
    for previous_open, current_open in zip(opens, opens[1:], strict=True):
        boundary = current_open + timedelta(hours=1)
        market_returns[boundary] = market_hourly_return({
            symbol: asset_log_return(bars[symbol][previous_open].close, bars[symbol][current_open].close)
            for symbol in UNIVERSE
        })
    rows: list[DesignRow] = []
    for decision in canonical_schedule():
        prior_boundaries, future_boundaries = rv24_windows_at_decision(decision=decision, market_returns=market_returns, bars=bars)
        rows.append(DesignRow(decision, market_rv24([market_returns[item] for item in prior_boundaries]), market_rv24([market_returns[item] for item in future_boundaries])))
    if len(rows) != OBSERVATION_COUNT or tuple(row.decision_time for row in rows) != canonical_schedule():
        raise ExecutionContractError("exactly 365 scheduled design rows required")
    if any(not math.isfinite(value) for row in rows for value in (row.rv24_prior, row.rv24_future)):
        raise ExecutionContractError("non-finite design value")
    return tuple(rows)


def _invert_2x2(matrix: tuple[tuple[float, float], tuple[float, float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    (a, b), (c, d) = matrix
    determinant = a * d - b * c
    if not math.isfinite(determinant) or determinant <= 0:
        raise ExecutionContractError("singular OLS design")
    return ((d / determinant, -b / determinant), (-c / determinant, a / determinant))


def ols_hac5(x: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    """The single frozen OLS-with-intercept/Bartlett-HAC(5) estimator."""
    if len(x) != OBSERVATION_COUNT or len(y) != OBSERVATION_COUNT:
        raise ExecutionContractError("OLS requires exactly 365 observations")
    if any(not math.isfinite(value) for value in (*x, *y)):
        raise ExecutionContractError("finite design values required")
    n = len(x)
    mean_x, mean_y = sum(x) / n, sum(y) / n
    sxx = sum((value - mean_x) ** 2 for value in x)
    if not math.isfinite(sxx) or sxx <= 0:
        raise ExecutionContractError("degenerate feature")
    beta = sum((left - mean_x) * (right - mean_y) for left, right in zip(x, y, strict=True)) / sxx
    alpha = mean_y - beta * mean_x
    residuals = [right - alpha - beta * left for left, right in zip(x, y, strict=True)]
    inverse = _invert_2x2(((float(n), sum(x)), (sum(x), sum(value * value for value in x))))
    scores = [(residual, feature * residual) for feature, residual in zip(x, residuals, strict=True)]
    meat = [[0.0, 0.0], [0.0, 0.0]]
    for score in scores:
        for row in range(2):
            for column in range(2):
                meat[row][column] += score[row] * score[column]
    for lag in range(1, HAC_LAG + 1):
        weight = 1.0 - lag / (HAC_LAG + 1)
        for current in range(lag, n):
            now, earlier = scores[current], scores[current - lag]
            for row in range(2):
                for column in range(2):
                    meat[row][column] += weight * (now[row] * earlier[column] + earlier[row] * now[column])
    middle = [[sum(inverse[row][k] * meat[k][column] for k in range(2)) for column in range(2)] for row in range(2)]
    covariance = [[sum(middle[row][k] * inverse[column][k] for k in range(2)) for column in range(2)] for row in range(2)]
    variance = covariance[1][1]
    if not math.isfinite(variance) or variance <= 0:
        raise ExecutionContractError("HAC beta variance must be finite and positive")
    standard_error = math.sqrt(variance)
    interval = (beta - HAC_CRITICAL_VALUE_95 * standard_error, beta + HAC_CRITICAL_VALUE_95 * standard_error)
    raw_p = math.erfc(abs(beta / standard_error) / math.sqrt(2.0))
    return {"alpha": alpha, "beta": beta, "hac_standard_error": standard_error, "confidence_interval_95": list(interval), "raw_p_value_two_sided": raw_p, "hac_lag": HAC_LAG, "hac_covariance": "BARTLETT_NEWEY_WEST"}


def classify(*, beta: float, confidence_interval_95: Sequence[float], raw_p_value_two_sided: float) -> str:
    if len(confidence_interval_95) != 2 or not all(math.isfinite(value) for value in (beta, *confidence_interval_95, raw_p_value_two_sided)):
        raise ExecutionContractError("finite statistical result required")
    low, high = confidence_interval_95
    if beta > 0 and low > 0 and raw_p_value_two_sided <= 0.05:
        return "REPLICATED_WITHIN_FROZEN_TEMPORAL_SCOPE"
    if beta < 0 and high < 0 and raw_p_value_two_sided <= 0.05:
        return "OPPOSITE_DIRECTION_WITHIN_FROZEN_TEMPORAL_SCOPE"
    return "INCONCLUSIVE"


def design_rows_digest(rows: Sequence[DesignRow]) -> str:
    if len(rows) != OBSERVATION_COUNT:
        raise ExecutionContractError("design digest requires exactly 365 rows")
    return hashlib.sha256(canonical_bytes([{"decision_timestamp": _stamp(row.decision_time), "rv24_prior": row.rv24_prior, "rv24_future": row.rv24_future} for row in rows])).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionContractError(f"invalid frozen artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ExecutionContractError("frozen artifact must be an object")
    return value


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=root, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode:
        raise ExecutionContractError(f"git identity verification failed: {' '.join(args)}")
    return completed.stdout.strip()


def _verify_implementation_identity(root: Path, frozen_implementation_sha: str) -> dict[str, str]:
    if len(frozen_implementation_sha) != 40 or any(character not in "0123456789abcdef" for character in frozen_implementation_sha):
        raise ExecutionContractError("frozen implementation SHA must be lowercase 40-character Git SHA")
    actual_head = _run_git(root, "rev-parse", "HEAD")
    if _run_git(root, "merge-base", "--is-ancestor", EXECUTION_AUTHORIZATION_BASE_SHA, actual_head) is not None:
        pass
    if subprocess.run(["git", "merge-base", "--is-ancestor", frozen_implementation_sha, actual_head], cwd=root).returncode:
        raise ExecutionContractError("frozen implementation is not an ancestor of actual execution HEAD")
    current_bytes = (root / MODULE_RELATIVE).read_bytes()
    frozen_bytes = subprocess.run(["git", "show", f"{frozen_implementation_sha}:{MODULE_RELATIVE.as_posix()}"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).stdout
    if not frozen_bytes or frozen_bytes != current_bytes:
        raise ExecutionContractError("executor source differs from frozen implementation bytes")
    return {"actual_execution_git_head": actual_head, "frozen_execution_implementation_sha": frozen_implementation_sha, "implementation_source_blob_sha256": hashlib.sha256(current_bytes).hexdigest(), "implementation_source_git_blob": _run_git(root, "rev-parse", f"HEAD:{MODULE_RELATIVE.as_posix()}")}


def _preflight(root: Path, frozen_implementation_sha: str) -> tuple[dict[str, Any], dict[str, str], dict[str, tuple[BarClose, ...]]]:
    preregistration = prereg.load_preregistration(root)
    prereg.validate(preregistration)
    if preregistration.get("preregistration_digest") != PREREGISTRATION_DIGEST:
        raise ExecutionContractError("preregistration digest mismatch")
    artifact_root = root / ARTIFACT_RELATIVE
    qualification = _load_json(artifact_root / "materialization/input_qualification.json")
    manifest = _load_json(artifact_root / "materialization/per_symbol_manifest.json")
    snapshot = _load_json(artifact_root / "materialization/snapshot_manifest.json")
    if qualification.get("input_qualification_digest") != INPUT_QUALIFICATION_DIGEST or qualification.get("qualification_status") != "INPUT_READY" or qualification.get("input_ready") is not True:
        raise ExecutionContractError("input qualification contract mismatch")
    if snapshot.get("snapshot_id") != SNAPSHOT_ID or snapshot.get("snapshot_digest") != SNAPSHOT_DIGEST:
        raise ExecutionContractError("snapshot identity mismatch")
    if tuple(qualification.get("ordered_universe", ())) != UNIVERSE or qualification.get("universe_digest") != UNIVERSE_DIGEST or tuple(record.get("symbol") for record in manifest.get("per_symbol", ())) != UNIVERSE:
        raise ExecutionContractError("ordered universe mismatch")
    expected_records = {record["symbol"]: record for record in manifest["per_symbol"]}
    panel: dict[str, tuple[BarClose, ...]] = {}
    for symbol in UNIVERSE:
        path = root / RAW_RELATIVE / f"{symbol}-perp-1h.csv"
        if not path.is_file():
            raise ExecutionContractError(f"missing frozen raw file: {symbol}")
        if _file_digest(path) != expected_records[symbol].get("accepted_raw_content_sha256"):
            raise ExecutionContractError(f"accepted raw-content hash mismatch: {symbol}")
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["timestamp", "open", "high", "low", "close", "volume"]:
                raise ExecutionContractError("raw schema mismatch")
            rows: list[BarClose] = []
            for record in reader:
                try:
                    opened, close = _utc(record["timestamp"]), float(record["close"])
                    prices = tuple(float(record[field]) for field in ("open", "high", "low", "close"))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ExecutionContractError("invalid raw price/timestamp") from exc
                if not all(math.isfinite(value) and value > 0 for value in prices):
                    raise ExecutionContractError("non-finite/non-positive raw OHLC")
                rows.append(BarClose(opened, close, opened + timedelta(hours=1)))
        panel[symbol] = tuple(rows)
    # _validate_panel asserts exact timestamps, duplicates, monotonicity, coverage, and cardinality.
    _validate_panel(panel)
    identities = _verify_implementation_identity(root, frozen_implementation_sha)
    request = {
        "artifact_type": "JH01_TEMPORAL_REPLICATION_EXECUTION_REQUEST_V0",
        "phase_id": PHASE_ID,
        "execution_authorization_base_sha": EXECUTION_AUTHORIZATION_BASE_SHA,
        **identities,
        "preregistration_digest": PREREGISTRATION_DIGEST,
        "input_qualification_digest": INPUT_QUALIFICATION_DIGEST,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "ordered_universe": list(UNIVERSE),
        "universe_digest": UNIVERSE_DIGEST,
        "observation_count": OBSERVATION_COUNT,
        "hac_lag": HAC_LAG,
        "network_used": False,
        "input_reacquired": False,
    }
    request["execution_request_digest"] = digest(request, omitted_field="execution_request_digest")
    return request, identities, panel


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    data = canonical_bytes(value) + b"\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise ExecutionAlreadyStartedError(f"immutable artifact already exists: {path.name}") from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def execute_once(root: Path, *, frozen_implementation_sha: str) -> dict[str, Any]:
    """Authenticate local raw bytes and run the scientific contract exactly once."""
    root = Path(root).resolve()
    artifact_root = root / ARTIFACT_RELATIVE
    result_path, started_path, request_path = (artifact_root / "execution_result.json", artifact_root / "execution_started.json", artifact_root / "execution_request.json")
    if result_path.exists():
        raise ExecutionAlreadyStartedError("execution_result already exists; real-sample rerun prohibited")
    if started_path.exists():
        raise ExecutionAlreadyStartedError("EXECUTION_INTERRUPTED_AFTER_REAL_OUTCOME_ACCESS")
    request, identities, panel = _preflight(root, frozen_implementation_sha)
    _write_new_json(request_path, request)
    started = {"artifact_type": "JH01_TEMPORAL_REPLICATION_EXECUTION_STARTED_V0", "execution_request_digest": request["execution_request_digest"], "execution_count": 1, "real_science_authorized_now": True}
    started["execution_started_digest"] = digest(started, omitted_field="execution_started_digest")
    _write_new_json(started_path, started)
    rows = build_design_rows(panel)
    statistic = ols_hac5([row.rv24_prior for row in rows], [row.rv24_future for row in rows])
    classification = classify(beta=statistic["beta"], confidence_interval_95=statistic["confidence_interval_95"], raw_p_value_two_sided=statistic["raw_p_value_two_sided"])
    result: dict[str, Any] = {
        "artifact_type": "JH01_TEMPORAL_REPLICATION_EXECUTION_RESULT_V0",
        "phase_id": PHASE_ID,
        "experiment_id": prereg.EXPERIMENT_ID,
        "source_piece_id": "JH01_RV_PERSISTENCE",
        "replication_type": "TEMPORAL_EMPIRICAL_REPLICATION",
        "execution_request_digest": request["execution_request_digest"],
        "execution_started_digest": started["execution_started_digest"],
        "execution_count": 1,
        "network_used": False,
        "input_reacquired": False,
        "execution_authorization_base_sha": EXECUTION_AUTHORIZATION_BASE_SHA,
        **identities,
        "preregistration_digest": PREREGISTRATION_DIGEST,
        "input_qualification_digest": INPUT_QUALIFICATION_DIGEST,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "ordered_universe": list(UNIVERSE),
        "universe_digest": UNIVERSE_DIGEST,
        "first_decision": FIRST_DECISION,
        "last_decision": LAST_DECISION,
        "observation_count": OBSERVATION_COUNT,
        "design_rows_digest": design_rows_digest(rows),
        "return_semantics": "LOG_CLOSE_RETURN_AT_BAR_CLOSE_BOUNDARY",
        "feature_semantics": "RV24_PRIOR_INCLUSIVE_T_MINUS_23H_TO_T",
        "outcome_semantics": "RV24_FUTURE_T_PLUS_1H_TO_T_PLUS_24H",
        "model": "RV24_future = alpha + beta * RV24_prior + epsilon",
        "estimator": "OLS_WITH_INTERCEPT",
        **statistic,
        "multiplicity_adjustment": "NONE_SINGLE_CONFIRMATORY_PROPOSITION",
        "classification": classification,
        "scientific_authority": "TEMPORAL_REPLICATION_RESULT_ONLY",
        "prohibited_downstream_authority": {"causal": "NONE", "strategy": "NONE", "state_snapshot": "NONE", "router": "NONE", "qnty": "NONE", "trading": "NONE", "promotion": "NONE"},
    }
    result["execution_result_digest"] = digest(result, omitted_field="execution_result_digest")
    _write_new_json(result_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the one authorized local JH01 temporal replication.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--frozen-implementation-sha", required=True)
    arguments = parser.parse_args()
    result = execute_once(arguments.root, frozen_implementation_sha=arguments.frozen_implementation_sha)
    print(json.dumps({"classification": result["classification"], "execution_result_digest": result["execution_result_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
