"""Frozen, local-only, one-shot scientific executor for JFP03.

This module is frozen by the V0R1 authorization artifact.  Importing it and
testing its pure functions never opens the real JFP03 source objects.  The
only real-input entry point is :func:`execute_once`, which verifies the
authorization and immutable V0R3 metadata, durably claims the one allowed
run, and only then opens the locally cached, hash-bound source objects.

The executor has no networking implementation and grants no downstream,
Qnty, trading, or capital authority regardless of its scientific result.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import math
import os
import platform
import subprocess
import sys
import sysconfig
import tomllib
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


PROJECT_ID = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R1_HISTORICAL_SCIENTIFIC_EXECUTION_AUTHORIZATION_V0"
EXECUTION_ID = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R1_HISTORICAL_SCIENTIFIC_EXECUTION_V0"
EXPECTED_AUTHORIZATION_BASE_SHA = "98a039b588ee960874c63dbd651ac329623194ae"
CANDIDATE_ID = "JFP03"
DESIGN_DIGEST = "a52d4999038e0be814ee8770322303fce84bed9ec8941b812748a18867633736"
SNAPSHOT_ID = "jfp-input-v0r3-24311649d541c28d068addc2fc76121d614a11f0f191581c7dd988ba0b99c69f"
SNAPSHOT_DIGEST = "24311649d541c28d068addc2fc76121d614a11f0f191581c7dd988ba0b99c69f"
QUALIFICATION_DIGEST = "420b0a4a84a57814d13393eb008affc05eb81223e06a9cf4a86c7772bc8bef5d"
SOURCE_MANIFEST_DIGEST = "b253ee51394ef90553b6d0e11195b7b5bed069a3b9a5dd1097515a7cb8637c15"
SOURCE_OBJECT_COUNT = 63
LOGICAL_WARMUP_ROWS = 721
EXECUTION_WORKSPACE_ROOT = Path("/home/swirky/DevHub/repos/QntyLab")
EXECUTION_GIT_COMMON_DIR = Path("/home/swirky/DevHub/repos/QntyLab/.git")
EXECUTION_GIT_COMMON_DIR_DEVICE = 66_307
EXECUTION_GIT_COMMON_DIR_INODE = 7_740_500
CLAIM_GIT_COMMON_RELATIVE = Path("qntylab-claims/jfp03-v0r1-historical-scientific-execution-v0.json")

FROZEN_RUNTIME_IDENTITY = {
    "python_implementation": "CPython",
    "python_version": "3.14.4",
    "platform_system": "Linux",
    "platform_release": "7.0.0-29-generic",
    "machine": "x86_64",
    "byteorder": "little",
    "libc_name": "glibc",
    "libc_version": "2.43",
    "python_compiler": "GCC 15.2.0",
    "python_build_branch": "main",
    "python_build_date": "Jun 18 2026 14:25:02",
    "python_cache_tag": "cpython-314",
    "python_soabi": "cpython-314-x86_64-linux-gnu",
    "python_platform": "linux-x86_64",
    "numpy_version": "2.3.5",
    "numpy_blas_name": "blas",
    "numpy_blas_version": "3.12.1",
    "numpy_lapack_name": "lapack",
    "numpy_lapack_version": "3.12.1",
    "numpy_config_sha256": "0783bfc9b478a6155574783e6133a27979667d89e3ad5b86385d921e68a6de67",
}

HOUR_MS = 3_600_000
FIRST_REQUIRED_CLOSE_MS = 1_575_244_800_000  # 2019-12-02T00:00:00Z
FIRST_DECISION_MS = 1_577_836_800_000  # 2020-01-01T00:00:00Z
LAST_DECISION_MS = 1_735_686_000_000  # 2024-12-31T23:00:00Z
LAST_REQUIRED_CLOSE_MS = 1_735_772_400_000  # 2025-01-01T23:00:00Z
OBSERVATION_COUNT = 43_848
HAC_LAG = 24
HAC_CRITICAL_VALUE_95 = 1.959963984540054
HOLM_FAMILY_SIZE = 3
FAMILYWISE_ALPHA = 0.05
RAW_ALPHA_GATE = FAMILYWISE_ALPHA / HOLM_FAMILY_SIZE
PARTIAL_R2_GATE = 0.001

MODULE_RELATIVE = Path("qntylab/jfp03_v0r1_historical_scientific_execution.py")
AUTHORIZATION_RELATIVE = Path(
    "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/execution/v0r1/"
    "historical_scientific_execution_authorization.json"
)
SNAPSHOT_RELATIVE = Path(
    "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/materialization/v0r3_input_snapshot.json"
)
QUALIFICATION_RELATIVE = Path(
    "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/materialization/v0r3_input_qualification.json"
)
SOURCE_MANIFEST_RELATIVE = Path(
    "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/materialization/v0r3_source_manifest.json"
)
RESULT_RELATIVE = Path(
    "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/execution/v0r1/"
    "historical_scientific_execution_result.json"
)
CACHE_RELATIVE = Path("data/archive/binance_jfp_v0")

TERMINAL_CLASSIFICATIONS = (
    "DISCOVERY_SUPPORTED_WITHIN_FROZEN_SCOPE",
    "NO_DISCOVERY_SUPPORT_FOUND",
    "BLOCKED_CANDIDATE",
    "BLOCKED_GLOBAL",
)
OUTPUT_FIELDS = (
    "candidate_id",
    "design_digest",
    "snapshot_id",
    "snapshot_digest",
    "executor_path",
    "executor_implementation_sha256",
    "executor_contract_digest",
    "runtime_identity",
    "runtime_identity_digest",
    "observation_count",
    "gamma_afi",
    "hac_standard_error",
    "test_statistic",
    "ci95_lower",
    "ci95_upper",
    "raw_p_value",
    "holm_adjusted_p_value",
    "sse_baseline",
    "sse_full",
    "partial_r2",
    "direction_pass",
    "inference_pass",
    "materiality_pass",
    "input_integrity_pass",
    "execution_integrity_pass",
    "terminal_classification",
    "sample_first_timestamp",
    "sample_last_timestamp",
    "expected_observation_count",
    "actual_observation_count",
    "missing_count",
    "duplicate_count",
    "nonfinite_count",
)


class ExecutionContractError(ValueError):
    """A frozen authorization, identity, input, or design invariant failed."""


class ExecutionAlreadyClaimed(RuntimeError):
    """The sole historical scientific execution has already been claimed."""


@dataclass(frozen=True)
class Kline:
    """The only source fields used by the frozen JFP03 design."""

    open_time_ms: int
    close_time_ms: int
    close: float
    total_quote_volume: float
    taker_buy_quote_volume: float

    @property
    def close_boundary_ms(self) -> int:
        return self.close_time_ms + 1


@dataclass(frozen=True)
class DesignRow:
    decision_time_ms: int
    har_1h: float
    har_24h: float
    har_168h: float
    har_720h: float
    afi: float
    rv24_future: float


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def object_digest(value: Mapping[str, Any], *, omitted_field: str) -> str:
    return hashlib.sha256(
        canonical_bytes({key: item for key, item in value.items() if key != omitted_field})
    ).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_identity() -> dict[str, Any]:
    build = np.__config__.CONFIG.get("Build Dependencies", {})
    blas = build.get("blas", {})
    lapack = build.get("lapack", {})
    config_digest = hashlib.sha256(
        canonical_bytes(np.__config__.CONFIG)
    ).hexdigest()
    libc_name, libc_version = platform.libc_ver()
    build_branch, build_date = platform.python_build()
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "machine": platform.machine(),
        "byteorder": sys.byteorder,
        "libc_name": libc_name,
        "libc_version": libc_version,
        "python_compiler": platform.python_compiler(),
        "python_build_branch": build_branch,
        "python_build_date": build_date,
        "python_cache_tag": sys.implementation.cache_tag,
        "python_soabi": sysconfig.get_config_var("SOABI"),
        "python_platform": sysconfig.get_platform(),
        "numpy_version": np.__version__,
        "numpy_blas_name": blas.get("name"),
        "numpy_blas_version": blas.get("version"),
        "numpy_lapack_name": lapack.get("name"),
        "numpy_lapack_version": lapack.get("version"),
        "numpy_config_sha256": config_digest,
    }


def runtime_identity_digest(identity: Mapping[str, Any] | None = None) -> str:
    return hashlib.sha256(canonical_bytes(dict(identity or runtime_identity()))).hexdigest()


def workspace_identity(root: Path) -> dict[str, Any]:
    root = root.resolve()
    commands = (
        ("--show-toplevel", "workspace_root"),
        ("--git-common-dir", "git_common_dir"),
    )
    values: dict[str, Any] = {}
    for argument, field in commands:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--path-format=absolute", argument],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode:
            raise ExecutionContractError("execution workspace is not the bound Git repository")
        values[field] = str(Path(completed.stdout.strip()).resolve())
    common = Path(values["git_common_dir"])
    try:
        common_stat = common.stat()
    except OSError as exc:
        raise ExecutionContractError("bound Git common directory is unavailable") from exc
    values["git_common_dir_device"] = common_stat.st_dev
    values["git_common_dir_inode"] = common_stat.st_ino
    return values


def _timestamp(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def canonical_schedule_ms() -> tuple[int, ...]:
    schedule = tuple(
        range(FIRST_DECISION_MS, LAST_DECISION_MS + HOUR_MS, HOUR_MS)
    )
    if len(schedule) != OBSERVATION_COUNT or schedule[-1] != LAST_DECISION_MS:
        raise AssertionError("frozen JFP03 decision schedule drift")
    return schedule


def expected_close_boundaries_ms() -> tuple[int, ...]:
    boundaries = tuple(
        range(FIRST_REQUIRED_CLOSE_MS, LAST_REQUIRED_CLOSE_MS + HOUR_MS, HOUR_MS)
    )
    if len(boundaries) != LOGICAL_WARMUP_ROWS + OBSERVATION_COUNT + 23:
        raise AssertionError("frozen JFP03 source coverage drift")
    return boundaries


def afi(total_quote_volume: float, taker_buy_quote_volume: float) -> float:
    """AFI = abs(2 * taker-buy quote share - 1), without transforms."""
    values = (total_quote_volume, taker_buy_quote_volume)
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        raise ExecutionContractError("AFI inputs must be finite")
    if total_quote_volume <= 0:
        raise ExecutionContractError("AFI total quote-volume denominator must be positive")
    result = abs(2.0 * (float(taker_buy_quote_volume) / float(total_quote_volume)) - 1.0)
    if not math.isfinite(result):
        raise ExecutionContractError("AFI must be finite")
    return result


def log_return(previous_close: float, current_close: float) -> float:
    """Return at boundary u is ln(C_u / C_(u-1h))."""
    values = (previous_close, current_close)
    if any(
        not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        for value in values
    ):
        raise ExecutionContractError("return closes must be finite and strictly positive")
    return math.log(float(current_close) / float(previous_close))


def baseline_return_boundaries_ms(decision_time_ms: int, hours: int) -> tuple[int, ...]:
    if hours not in (1, 24, 168, 720):
        raise ExecutionContractError("HAR window must be exactly 1, 24, 168, or 720 hours")
    if decision_time_ms % HOUR_MS:
        raise ExecutionContractError("decision boundary must be hour aligned")
    return tuple(decision_time_ms - offset * HOUR_MS for offset in range(hours - 1, -1, -1))


def target_return_boundaries_ms(decision_time_ms: int) -> tuple[int, ...]:
    if decision_time_ms % HOUR_MS:
        raise ExecutionContractError("decision boundary must be hour aligned")
    return tuple(decision_time_ms + offset * HOUR_MS for offset in range(1, 25))


def realized_volatility(
    returns_by_boundary: Mapping[int, float], boundaries: Sequence[int]
) -> float:
    values: list[float] = []
    for boundary in boundaries:
        if boundary not in returns_by_boundary:
            raise ExecutionContractError("required return boundary is missing")
        value = returns_by_boundary[boundary]
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ExecutionContractError("required return must be finite")
        values.append(float(value))
    result = math.sqrt(sum(value * value for value in values))
    if not math.isfinite(result):
        raise ExecutionContractError("realized volatility must be finite")
    return result


def har_features(
    decision_time_ms: int, returns_by_boundary: Mapping[int, float]
) -> tuple[float, float, float, float]:
    return tuple(
        realized_volatility(
            returns_by_boundary,
            baseline_return_boundaries_ms(decision_time_ms, hours),
        )
        for hours in (1, 24, 168, 720)
    )  # type: ignore[return-value]


def future_target(decision_time_ms: int, returns_by_boundary: Mapping[int, float]) -> float:
    boundaries = target_return_boundaries_ms(decision_time_ms)
    if set(boundaries) & set(baseline_return_boundaries_ms(decision_time_ms, 720)):
        raise AssertionError("baseline and future-target windows overlap")
    return realized_volatility(returns_by_boundary, boundaries)


def _validate_kline(row: Kline) -> None:
    if row.open_time_ms % HOUR_MS or row.close_time_ms != row.open_time_ms + HOUR_MS - 1:
        raise ExecutionContractError("kline open/close boundary semantics mismatch")
    if row.close_boundary_ms != row.open_time_ms + HOUR_MS:
        raise ExecutionContractError("logical close boundary mismatch")
    if not math.isfinite(row.close) or row.close <= 0:
        raise ExecutionContractError("kline close must be finite and strictly positive")
    afi(row.total_quote_volume, row.taker_buy_quote_volume)


def build_design_rows(klines: Sequence[Kline]) -> tuple[DesignRow, ...]:
    """Build the exact complete JFP03 sample; row dropping is prohibited."""
    expected_boundaries = expected_close_boundaries_ms()
    if len(klines) != len(expected_boundaries):
        raise ExecutionContractError("exact frozen kline cardinality required; row dropping prohibited")
    by_boundary: dict[int, Kline] = {}
    for expected, row in zip(expected_boundaries, klines, strict=True):
        _validate_kline(row)
        if row.close_boundary_ms != expected:
            raise ExecutionContractError("kline boundaries must equal the frozen ordered hourly set")
        if row.close_boundary_ms in by_boundary:
            raise ExecutionContractError("duplicate kline close boundary")
        by_boundary[row.close_boundary_ms] = row

    returns_by_boundary = {
        current: log_return(by_boundary[previous].close, by_boundary[current].close)
        for previous, current in zip(expected_boundaries[:-1], expected_boundaries[1:], strict=True)
    }
    rows: list[DesignRow] = []
    for decision in canonical_schedule_ms():
        har_1h, har_24h, har_168h, har_720h = har_features(decision, returns_by_boundary)
        row = DesignRow(
            decision_time_ms=decision,
            har_1h=har_1h,
            har_24h=har_24h,
            har_168h=har_168h,
            har_720h=har_720h,
            afi=afi(
                by_boundary[decision].total_quote_volume,
                by_boundary[decision].taker_buy_quote_volume,
            ),
            rv24_future=future_target(decision, returns_by_boundary),
        )
        if any(not math.isfinite(value) for value in asdict(row).values()):
            raise ExecutionContractError("non-finite design row; row dropping prohibited")
        rows.append(row)
    if len(rows) != OBSERVATION_COUNT or tuple(row.decision_time_ms for row in rows) != canonical_schedule_ms():
        raise ExecutionContractError("exact complete decision sample required; row dropping prohibited")
    return tuple(rows)


def partial_r2(sse_baseline: float, sse_full: float) -> float:
    if not all(math.isfinite(value) for value in (sse_baseline, sse_full)) or sse_baseline <= 0:
        raise ExecutionContractError("partial R2 requires finite SSEs and positive baseline SSE")
    result = (sse_baseline - sse_full) / sse_baseline
    if not math.isfinite(result):
        raise ExecutionContractError("partial R2 must be finite")
    return result


def support_classification(*, gamma: float, raw_p_value: float, partial_r2_value: float) -> str:
    """Apply the three exact scientific gates after integrity has passed."""
    if not all(math.isfinite(value) for value in (gamma, raw_p_value, partial_r2_value)):
        raise ExecutionContractError("support gates require finite scientific values")
    if not 0 <= raw_p_value <= 1:
        raise ExecutionContractError("raw p-value must be in [0,1]")
    adjusted = min(1.0, HOLM_FAMILY_SIZE * raw_p_value)
    if (
        gamma > 0
        and raw_p_value <= RAW_ALPHA_GATE
        and adjusted <= FAMILYWISE_ALPHA
        and partial_r2_value >= PARTIAL_R2_GATE
    ):
        return "DISCOVERY_SUPPORTED_WITHIN_FROZEN_SCOPE"
    return "NO_DISCOVERY_SUPPORT_FOUND"


def _newey_west_covariance(x: np.ndarray, residuals: np.ndarray) -> np.ndarray:
    if x.ndim != 2 or residuals.ndim != 1 or x.shape[0] != residuals.shape[0]:
        raise ExecutionContractError("HAC design/residual dimensions mismatch")
    bread = np.linalg.inv(x.T @ x)
    scores = x * residuals[:, None]
    meat = scores.T @ scores
    for lag in range(1, HAC_LAG + 1):
        weight = 1.0 - lag / (HAC_LAG + 1)
        cross = scores[lag:].T @ scores[:-lag]
        meat = meat + weight * (cross + cross.T)
    covariance = bread @ meat @ bread
    if not np.all(np.isfinite(covariance)):
        raise ExecutionContractError("HAC covariance must be finite")
    return covariance


def fit_frozen_models(rows: Sequence[DesignRow]) -> dict[str, Any]:
    """Fit the two common-sample models and fixed Bartlett HAC(24) inference."""
    if len(rows) < HAC_LAG + 7:
        raise ExecutionContractError("insufficient common sample for frozen models")
    values = np.asarray(
        [
            [
                row.har_1h,
                row.har_24h,
                row.har_168h,
                row.har_720h,
                row.afi,
                row.rv24_future,
            ]
            for row in rows
        ],
        dtype=np.float64,
    )
    if values.shape != (len(rows), 6) or not np.all(np.isfinite(values)):
        raise ExecutionContractError("complete finite common sample required; row dropping prohibited")
    y = values[:, 5]
    common = np.column_stack((np.ones(len(rows), dtype=np.float64), values[:, :5]))
    baseline_x, full_x = common[:, :5], common
    if np.linalg.matrix_rank(baseline_x) != 5 or np.linalg.matrix_rank(full_x) != 6:
        raise ExecutionContractError("full-rank frozen OLS designs required")
    baseline_beta = np.linalg.lstsq(baseline_x, y, rcond=None)[0]
    full_beta = np.linalg.lstsq(full_x, y, rcond=None)[0]
    baseline_residuals = y - baseline_x @ baseline_beta
    full_residuals = y - full_x @ full_beta
    sse_baseline = float(baseline_residuals @ baseline_residuals)
    sse_full = float(full_residuals @ full_residuals)
    covariance = _newey_west_covariance(full_x, full_residuals)
    variance = float(covariance[-1, -1])
    if not math.isfinite(variance) or variance <= 0:
        raise ExecutionContractError("gamma HAC variance must be finite and positive")
    standard_error = math.sqrt(variance)
    gamma = float(full_beta[-1])
    statistic = gamma / standard_error
    raw_p = math.erfc(abs(statistic) / math.sqrt(2.0))
    adjusted_p = min(1.0, HOLM_FAMILY_SIZE * raw_p)
    effect = partial_r2(sse_baseline, sse_full)
    direction_pass = gamma > 0
    inference_pass = raw_p <= RAW_ALPHA_GATE and adjusted_p <= FAMILYWISE_ALPHA
    materiality_pass = effect >= PARTIAL_R2_GATE
    classification = support_classification(
        gamma=gamma,
        raw_p_value=raw_p,
        partial_r2_value=effect,
    )
    return {
        "observation_count": len(rows),
        "gamma_afi": gamma,
        "hac_standard_error": standard_error,
        "test_statistic": statistic,
        "ci95_lower": gamma - HAC_CRITICAL_VALUE_95 * standard_error,
        "ci95_upper": gamma + HAC_CRITICAL_VALUE_95 * standard_error,
        "raw_p_value": raw_p,
        "holm_adjusted_p_value": adjusted_p,
        "sse_baseline": sse_baseline,
        "sse_full": sse_full,
        "partial_r2": effect,
        "direction_pass": direction_pass,
        "inference_pass": inference_pass,
        "materiality_pass": materiality_pass,
        "hac_lag": HAC_LAG,
        "hac_kernel": "BARTLETT_NEWEY_WEST",
        "hac_lag_selection": "NONE",
        "inference_reference": "ASYMPTOTIC_NORMAL_Z_TWO_SIDED",
        "common_sample_pass": baseline_x.shape[0] == full_x.shape[0] == len(rows),
        "terminal_classification": classification,
    }


def multiplicity_family(
    raw_p_jfp03: float | None, terminal_classification: str
) -> tuple[dict[str, Any], ...]:
    if raw_p_jfp03 is not None and (not math.isfinite(raw_p_jfp03) or not 0 <= raw_p_jfp03 <= 1):
        raise ExecutionContractError("JFP03 raw p-value must be null or in [0,1]")
    if terminal_classification not in TERMINAL_CLASSIFICATIONS:
        raise ExecutionContractError("JFP03 terminal classification is invalid")
    if terminal_classification in TERMINAL_CLASSIFICATIONS[:2] and raw_p_jfp03 is None:
        raise ExecutionContractError("valid JFP03 terminal science requires a raw p-value")
    if terminal_classification in TERMINAL_CLASSIFICATIONS[2:] and raw_p_jfp03 is not None:
        raise ExecutionContractError("blocked JFP03 terminal science must remain null")
    adjusted = None if raw_p_jfp03 is None else min(1.0, 3.0 * raw_p_jfp03)
    return (
        {"candidate_id": "JFP01", "status": "BLOCKED_CANDIDATE", "raw_p_value": None, "holm_adjusted_p_value": None},
        {"candidate_id": "JFP02", "status": "BLOCKED_CANDIDATE", "raw_p_value": None, "holm_adjusted_p_value": None},
        {"candidate_id": "JFP03", "status": terminal_classification, "raw_p_value": raw_p_jfp03, "holm_adjusted_p_value": adjusted},
    )


def executor_contract() -> dict[str, Any]:
    return {
        "schema_version": "jfp03-v0r1-historical-scientific-executor-contract-v1",
        "candidate_id": CANDIDATE_ID,
        "design_digest": DESIGN_DIGEST,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "qualification_digest": QUALIFICATION_DIGEST,
        "source_manifest_digest": SOURCE_MANIFEST_DIGEST,
        "source_object_count": SOURCE_OBJECT_COUNT,
        "execution_workspace": {
            "workspace_root": str(EXECUTION_WORKSPACE_ROOT),
            "git_common_dir": str(EXECUTION_GIT_COMMON_DIR),
            "git_common_dir_device": EXECUTION_GIT_COMMON_DIR_DEVICE,
            "git_common_dir_inode": EXECUTION_GIT_COMMON_DIR_INODE,
            "claim_path_relative_to_git_common_dir": CLAIM_GIT_COMMON_RELATIVE.as_posix(),
            "scope": "THIS_UNIQUE_GIT_COMMON_DIRECTORY_AND_ITS_LINKED_WORKTREES_ONLY",
        },
        "runtime_identity": FROZEN_RUNTIME_IDENTITY,
        "runtime_identity_digest": runtime_identity_digest(FROZEN_RUNTIME_IDENTITY),
        "instrument": "BINANCE_USD_M_BTCUSDT_PERPETUAL",
        "decision_schedule": {
            "first": _timestamp(FIRST_DECISION_MS),
            "last": _timestamp(LAST_DECISION_MS),
            "frequency": "1H",
            "inclusive": True,
            "observation_count": OBSERVATION_COUNT,
        },
        "feature": "AFI_t=abs(2*(taker_buy_quote_volume_t/total_quote_volume_t)-1)",
        "return": "r_u=ln(C_u/C_(u-1h)); u is UTC close boundary",
        "har_windows_hours": [1, 24, 168, 720],
        "har_aggregation": "sqrt(sum(squared hourly log returns)); no normalization",
        "target": "sqrt(sum(r_(t+1h)^2,...,r_(t+24h)^2))",
        "baseline_columns": ["intercept", "HAR_1H", "HAR_24H", "HAR_168H", "HAR_720H"],
        "full_columns": ["intercept", "HAR_1H", "HAR_24H", "HAR_168H", "HAR_720H", "AFI"],
        "estimator": "NUMPY_LINALG_LSTSQ_RCOND_NONE_OLS",
        "inference": {
            "covariance": "BARTLETT_NEWEY_WEST",
            "lag": HAC_LAG,
            "lag_selection": "NONE",
            "finite_sample_correction": "NONE",
            "reference_distribution": "ASYMPTOTIC_NORMAL_Z_TWO_SIDED",
            "ci95_critical_value": HAC_CRITICAL_VALUE_95,
        },
        "materiality": {
            "formula": "(SSE_baseline-SSE_full)/SSE_baseline",
            "gate_inclusive": PARTIAL_R2_GATE,
            "common_sample_required": True,
        },
        "multiplicity": {
            "ordered_family": ["JFP01", "JFP02", "JFP03"],
            "family_size": HOLM_FAMILY_SIZE,
            "familywise_alpha": FAMILYWISE_ALPHA,
            "jfp03_raw_alpha_gate": RAW_ALPHA_GATE,
            "jfp03_adjustment": "min(1,3*raw_p)",
            "blocked_candidate_scientific_values": None,
        },
        "terminal_classifications": list(TERMINAL_CLASSIFICATIONS),
        "output_fields": list(OUTPUT_FIELDS),
        "one_shot": {
            "runs_allowed": 1,
            "claim_before_real_source_open": True,
            "mechanism": "GIT_COMMON_DIR_O_EXCL_FILE_FSYNC_AND_PARENT_DIRECTORY_FSYNC",
            "failure_after_claim_replay_authorized": False,
        },
        "network_access": "PROHIBITED_NOT_IMPLEMENTED",
        "input_reacquisition": "PROHIBITED",
        "row_dropping": "PROHIBITED",
        "downstream_authority": "NONE",
    }


def executor_contract_digest() -> str:
    return hashlib.sha256(canonical_bytes(executor_contract())).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionContractError(f"invalid or missing frozen artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ExecutionContractError(f"frozen artifact must be a JSON object: {path}")
    return value


def _require_self_digest(value: Mapping[str, Any], field: str, expected: str) -> None:
    if value.get(field) != expected or object_digest(value, omitted_field=field) != expected:
        raise ExecutionContractError(f"{field} mismatch")


def _require_snapshot_digest(value: Mapping[str, Any]) -> None:
    body = {key: item for key, item in value.items() if key not in {"snapshot_id", "snapshot_digest"}}
    actual = hashlib.sha256(canonical_bytes(body)).hexdigest()
    if (
        value.get("snapshot_digest") != SNAPSHOT_DIGEST
        or value.get("snapshot_id") != SNAPSHOT_ID
        or actual != SNAPSHOT_DIGEST
        or value.get("snapshot_id") != f"jfp-input-v0r3-{actual}"
    ):
        raise ExecutionContractError("snapshot identity or digest mismatch")


def verify_frozen_bindings(
    root: Path,
    *,
    _workspace_identity_for_test: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify all metadata and executor bytes without opening real source objects."""
    authorization = _load_json(root / AUTHORIZATION_RELATIVE)
    _require_self_digest(authorization, "authorization_digest", authorization.get("authorization_digest", ""))
    if authorization.get("project_id") != PROJECT_ID or authorization.get("state") != "CLOSED_PASS":
        raise ExecutionContractError("authorization project/state mismatch")
    if authorization.get("expected_master") != EXPECTED_AUTHORIZATION_BASE_SHA:
        raise ExecutionContractError("authorization base SHA mismatch")
    if authorization.get("historical_scientific_execution_runs_allowed") != 1 or authorization.get("historical_scientific_execution_runs_consumed") != 0:
        raise ExecutionContractError("authorization must freeze exactly one unconsumed run")
    if authorization.get("design_digest") != DESIGN_DIGEST:
        raise ExecutionContractError("design digest mismatch")
    if authorization.get("executor_path") != MODULE_RELATIVE.as_posix():
        raise ExecutionContractError("executor path mismatch")
    if authorization.get("executor_contract_digest") != executor_contract_digest():
        raise ExecutionContractError("executor contract digest mismatch")
    actual_executor_sha = file_sha256(root / MODULE_RELATIVE)
    if authorization.get("executor_implementation_sha256") != actual_executor_sha:
        raise ExecutionContractError("executor implementation identity mismatch")
    actual_runtime = runtime_identity()
    actual_runtime_digest = runtime_identity_digest(actual_runtime)
    if actual_runtime != FROZEN_RUNTIME_IDENTITY:
        raise ExecutionContractError("frozen numerical runtime identity mismatch")
    if authorization.get("runtime_identity") != actual_runtime or authorization.get("runtime_identity_digest") != actual_runtime_digest:
        raise ExecutionContractError("authorization numerical runtime identity mismatch")
    actual_workspace = dict(_workspace_identity_for_test or workspace_identity(root))
    expected_workspace = {
        "workspace_root": str(EXECUTION_WORKSPACE_ROOT),
        "git_common_dir": str(EXECUTION_GIT_COMMON_DIR),
        "git_common_dir_device": EXECUTION_GIT_COMMON_DIR_DEVICE,
        "git_common_dir_inode": EXECUTION_GIT_COMMON_DIR_INODE,
    }
    if actual_workspace != expected_workspace:
        raise ExecutionContractError("execution workspace identity mismatch")
    if authorization.get("execution_workspace_identity") != expected_workspace:
        raise ExecutionContractError("authorization workspace identity mismatch")
    if authorization.get("claim_path_relative_to_git_common_dir") != CLAIM_GIT_COMMON_RELATIVE.as_posix():
        raise ExecutionContractError("authorization claim-path identity mismatch")

    snapshot = _load_json(root / SNAPSHOT_RELATIVE)
    _require_snapshot_digest(snapshot)
    if snapshot.get("design_digest") != DESIGN_DIGEST:
        raise ExecutionContractError("snapshot identity or design binding mismatch")
    if snapshot.get("source_manifest_digest") != SOURCE_MANIFEST_DIGEST or snapshot.get("source_object_count") != SOURCE_OBJECT_COUNT:
        raise ExecutionContractError("snapshot source binding mismatch")
    if snapshot.get("logical_warmup", {}).get("rows") != LOGICAL_WARMUP_ROWS or snapshot.get("logical_warmup", {}).get("first_har720_complete") is not True or snapshot.get("last_target_24h_complete") is not True:
        raise ExecutionContractError("snapshot coverage contract mismatch")

    qualification = _load_json(root / QUALIFICATION_RELATIVE)
    _require_self_digest(qualification, "qualification_digest", QUALIFICATION_DIGEST)
    if qualification.get("input_qualification") != "READY" or qualification.get("snapshot_id") != SNAPSHOT_ID or qualification.get("snapshot_digest") != SNAPSHOT_DIGEST:
        raise ExecutionContractError("input qualification binding mismatch")
    if qualification.get("source_object_count") != SOURCE_OBJECT_COUNT or qualification.get("logical_warmup_rows") != LOGICAL_WARMUP_ROWS or qualification.get("first_har720_complete") is not True or qualification.get("last_target_24h_complete") is not True:
        raise ExecutionContractError("input qualification coverage mismatch")

    manifest = _load_json(root / SOURCE_MANIFEST_RELATIVE)
    _require_self_digest(manifest, "source_manifest_digest", SOURCE_MANIFEST_DIGEST)
    if manifest.get("design_digest") != DESIGN_DIGEST or manifest.get("source_object_count") != SOURCE_OBJECT_COUNT or len(manifest.get("source_objects", ())) != SOURCE_OBJECT_COUNT:
        raise ExecutionContractError("source-manifest binding mismatch")

    try:
        registry = tomllib.loads((root / "docs/state/projects.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ExecutionContractError("invalid canonical project registry") from exc
    projects = {record.get("project_id"): record for record in registry.get("project", ())}
    project = projects.get(PROJECT_ID)
    if not isinstance(project, dict) or project.get("state") != "CLOSED_PASS" or project.get("authority_level") != "HISTORICAL_SCIENTIFIC_EXECUTION_AUTHORIZATION_ONLY":
        raise ExecutionContractError("canonical authorization project is not closed-pass")
    if project.get("historical_scientific_execution_runs_allowed") != 1 or project.get("historical_scientific_execution_runs_consumed") != 0 or project.get("downstream_authority") != "NONE":
        raise ExecutionContractError("canonical one-shot/downstream authority mismatch")
    if project.get("bound_execution_workspace_root") != str(EXECUTION_WORKSPACE_ROOT) or project.get("bound_git_common_dir") != str(EXECUTION_GIT_COMMON_DIR) or project.get("bound_runtime_identity_digest") != actual_runtime_digest:
        raise ExecutionContractError("canonical workspace/runtime binding mismatch")
    return {
        "authorization": authorization,
        "snapshot": snapshot,
        "qualification": qualification,
        "manifest": manifest,
        "executor_implementation_sha256": actual_executor_sha,
        "executor_contract_digest": executor_contract_digest(),
        "runtime_identity": actual_runtime,
        "runtime_identity_digest": actual_runtime_digest,
        "execution_workspace_identity": actual_workspace,
        "claim_path": Path(actual_workspace["git_common_dir"]) / CLAIM_GIT_COMMON_RELATIVE,
    }


def claim_execution(root: Path, verified: Mapping[str, Any]) -> dict[str, Any]:
    """Durably consume the one allowed run before any real source object is opened."""
    authorization = verified.get("authorization")
    if not isinstance(authorization, Mapping) or authorization.get("authorization_digest") is None:
        raise ExecutionContractError("verified authorization required before claim")
    claim_path_value = verified.get("claim_path")
    if not isinstance(claim_path_value, Path):
        raise ExecutionContractError("verified repository-wide claim path required")
    claim_path = claim_path_value
    result_path = root / RESULT_RELATIVE
    if result_path.exists():
        raise ExecutionAlreadyClaimed("a terminal execution result already exists")
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    claim = {
        "artifact_type": "JFP03_V0R1_HISTORICAL_SCIENTIFIC_EXECUTION_START",
        "schema_version": "jfp03-v0r1-historical-scientific-execution-start-v1",
        "execution_id": EXECUTION_ID,
        "candidate_id": CANDIDATE_ID,
        "authorization_digest": authorization["authorization_digest"],
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "design_digest": DESIGN_DIGEST,
        "executor_implementation_sha256": verified["executor_implementation_sha256"],
        "executor_contract_digest": verified["executor_contract_digest"],
        "historical_scientific_execution_runs_allowed": 1,
        "historical_scientific_execution_runs_consumed_before": 0,
        "historical_scientific_execution_runs_consumed_after": 1,
        "execution_workspace_identity": verified["execution_workspace_identity"],
        "runtime_identity": verified["runtime_identity"],
        "runtime_identity_digest": verified["runtime_identity_digest"],
        "claim_path_relative_to_git_common_dir": CLAIM_GIT_COMMON_RELATIVE.as_posix(),
        "claim_mechanism": "GIT_COMMON_DIR_O_EXCL_FILE_FSYNC_AND_PARENT_DIRECTORY_FSYNC",
        "replay_authorized": False,
    }
    claim["start_digest"] = object_digest(claim, omitted_field="start_digest")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(claim_path, flags, 0o644)
    except FileExistsError as exc:
        raise ExecutionAlreadyClaimed("the sole execution run is already claimed") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(canonical_bytes(claim) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        directory_descriptor = os.open(claim_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        # The exclusive claim intentionally survives every post-create failure.
        raise
    return claim


def _parse_source_row(values: Sequence[Any]) -> Kline:
    if len(values) != 12:
        raise ExecutionContractError("Binance kline source row must have exactly 12 fields")
    try:
        return Kline(
            open_time_ms=int(values[0]),
            close_time_ms=int(values[6]),
            close=float(values[4]),
            total_quote_volume=float(values[7]),
            taker_buy_quote_volume=float(values[10]),
        )
    except (TypeError, ValueError) as exc:
        raise ExecutionContractError("invalid Binance kline source value") from exc


def _json_rows(data: bytes) -> list[Kline]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionContractError("invalid JSON source object") from exc
    if not isinstance(value, list):
        raise ExecutionContractError("JSON source object must contain a row list")
    return [_parse_source_row(row) for row in value]


def _zip_rows(data: bytes, member_name: str) -> list[Kline]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if archive.namelist() != [member_name]:
                raise ExecutionContractError("monthly archive member identity mismatch")
            with archive.open(member_name) as stream:
                reader = csv.reader(io.TextIOWrapper(stream, encoding="utf-8", newline=""))
                rows = list(reader)
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        raise ExecutionContractError("invalid monthly source archive") from exc
    if rows and not rows[0][0].isdigit():
        rows = rows[1:]
    return [_parse_source_row(row) for row in rows]


def select_frozen_coverage(
    rows: Sequence[Kline], expected_boundaries: Sequence[int] | None = None
) -> tuple[Kline, ...]:
    """Select the frozen support range, rejecting gaps, duplicates, and leading extras."""
    expected = tuple(expected_boundaries or expected_close_boundaries_ms())
    if not expected or any(right - left != HOUR_MS for left, right in zip(expected, expected[1:])):
        raise ExecutionContractError("expected source coverage must be contiguous and hourly")
    selected: dict[int, Kline] = {}
    for row in rows:
        _validate_kline(row)
        boundary = row.close_boundary_ms
        if boundary < expected[0]:
            raise ExecutionContractError("source contains an unauthorized leading row")
        if boundary <= expected[-1]:
            if boundary in selected:
                raise ExecutionContractError("duplicate source row in frozen coverage")
            selected[boundary] = row
    if tuple(selected) != expected:
        raise ExecutionContractError("source rows do not equal the frozen complete coverage")
    return tuple(selected[boundary] for boundary in expected)


def load_frozen_klines(root: Path, verified: Mapping[str, Any]) -> tuple[Kline, ...]:
    """Open only hash-bound local V0R3 objects.  Must be called after claim."""
    claim_path = verified.get("claim_path")
    if not isinstance(claim_path, Path) or not claim_path.is_file():
        raise ExecutionContractError("durable execution claim required before source access")
    manifest = verified.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ExecutionContractError("verified source manifest required")
    objects = manifest.get("source_objects")
    if not isinstance(objects, list) or len(objects) != SOURCE_OBJECT_COUNT:
        raise ExecutionContractError("exact V0R3 source-object list required")
    rows: list[Kline] = []
    for index, identity in enumerate(objects):
        if not isinstance(identity, Mapping):
            raise ExecutionContractError("source identity must be an object")
        role = identity.get("source_role")
        if index == 0 and role == "PREFIX_REST_OBJECT":
            try:
                data = base64.b64decode(identity["authoritative_response_bytes_base64"], validate=True)
            except (KeyError, ValueError) as exc:
                raise ExecutionContractError("invalid embedded prefix bytes") from exc
            expected_sha = identity.get("response_sha256")
            if hashlib.sha256(data).hexdigest() != expected_sha:
                raise ExecutionContractError("embedded prefix response hash mismatch")
            part = _json_rows(data)
        elif index == 1 and role == "EXISTING_720_ROW_REST_OBJECT":
            expected_sha = identity.get("response_sha256")
            path = root / CACHE_RELATIVE / f"{expected_sha}.json"
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise ExecutionContractError("missing 720-row REST source object") from exc
            if hashlib.sha256(data).hexdigest() != expected_sha:
                raise ExecutionContractError("720-row REST source hash mismatch")
            part = _json_rows(data)
        elif role in ("ORIGINAL_MONTHLY_OBJECT", "EXISTING_2025_01_OBJECT"):
            expected_sha = identity.get("local_sha256")
            path = root / CACHE_RELATIVE / f"{expected_sha}.zip"
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise ExecutionContractError("missing monthly source object") from exc
            if hashlib.sha256(data).hexdigest() != expected_sha or identity.get("official_checksum") != expected_sha:
                raise ExecutionContractError("monthly source hash mismatch")
            names = identity.get("archive_member_names")
            if not isinstance(names, list) or len(names) != 1:
                raise ExecutionContractError("monthly archive requires one frozen member")
            part = _zip_rows(data, names[0])
        else:
            raise ExecutionContractError("unexpected source ordering or role")
        rows.extend(part)
    return select_frozen_coverage(rows)


def _result_envelope(verified: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "JFP03_V0R1_HISTORICAL_SCIENTIFIC_EXECUTION_RESULT",
        "schema_version": "jfp03-v0r1-historical-scientific-execution-result-v1",
        "execution_id": EXECUTION_ID,
        "candidate_id": CANDIDATE_ID,
        "design_digest": DESIGN_DIGEST,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "executor_path": MODULE_RELATIVE.as_posix(),
        "executor_implementation_sha256": verified["executor_implementation_sha256"],
        "executor_contract_digest": verified["executor_contract_digest"],
        "runtime_identity": verified["runtime_identity"],
        "runtime_identity_digest": verified["runtime_identity_digest"],
        "jfp01_status": "BLOCKED_CANDIDATE",
        "jfp01_scientific_values": None,
        "jfp02_status": "BLOCKED_CANDIDATE",
        "jfp02_scientific_values": None,
        "multiplicity_family_size": HOLM_FAMILY_SIZE,
        "downstream_authority": "NONE",
        "jigsaw_synthesis_authorized": False,
        "state_snapshot_authorized": False,
        "forecaster_authorized": False,
        "router_authorized": False,
        "qnty_authorized": False,
        "paper_trading_authorized": False,
        "trading_authorized": False,
        "capital_authority": "NONE",
    }


def _write_terminal_result(root: Path, result: dict[str, Any]) -> None:
    result["result_digest"] = object_digest(result, omitted_field="result_digest")
    path = root / RESULT_RELATIVE
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb", closefd=True) as stream:
        stream.write(canonical_bytes(result) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def execute_once(root: Path) -> dict[str, Any]:
    """Consume and execute the frozen real-input contract exactly once."""
    root = root.resolve()
    verified = verify_frozen_bindings(root)
    claim_execution(root, verified)
    envelope = _result_envelope(verified)
    try:
        klines = load_frozen_klines(root, verified)
        rows = build_design_rows(klines)
        statistics = fit_frozen_models(rows)
        result = {
            **envelope,
            **statistics,
            "input_integrity_pass": True,
            "execution_integrity_pass": True,
            "sample_first_timestamp": _timestamp(rows[0].decision_time_ms),
            "sample_last_timestamp": _timestamp(rows[-1].decision_time_ms),
            "expected_observation_count": OBSERVATION_COUNT,
            "actual_observation_count": len(rows),
            "missing_count": 0,
            "duplicate_count": 0,
            "nonfinite_count": 0,
            "multiplicity_family": multiplicity_family(
                statistics["raw_p_value"], statistics["terminal_classification"]
            ),
        }
    except ExecutionContractError as exc:
        result = {
            **envelope,
            **{field: None for field in OUTPUT_FIELDS if field not in envelope},
            "input_integrity_pass": False,
            "execution_integrity_pass": False,
            "terminal_classification": "BLOCKED_CANDIDATE",
            "expected_observation_count": OBSERVATION_COUNT,
            "integrity_failure": str(exc),
            "multiplicity_family": multiplicity_family(None, "BLOCKED_CANDIDATE"),
        }
    except Exception as exc:
        result = {
            **envelope,
            **{field: None for field in OUTPUT_FIELDS if field not in envelope},
            "input_integrity_pass": None,
            "execution_integrity_pass": False,
            "terminal_classification": "BLOCKED_GLOBAL",
            "expected_observation_count": OBSERVATION_COUNT,
            "global_failure_type": type(exc).__name__,
            "multiplicity_family": multiplicity_family(None, "BLOCKED_GLOBAL"),
        }
    _write_terminal_result(root, result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--confirm-one-shot",
        required=True,
        choices=("CONSUME_JFP03_HISTORICAL_SCIENTIFIC_EXECUTION",),
    )
    arguments = parser.parse_args(argv)
    result = execute_once(arguments.root)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result["terminal_classification"] in TERMINAL_CLASSIFICATIONS[:2] else 2


if __name__ == "__main__":
    sys.exit(main())
