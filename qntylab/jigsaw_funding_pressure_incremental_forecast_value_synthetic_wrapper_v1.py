"""SYNTHETIC_VALIDATION wrapper over the shared funding incremental core.

SUCCESSOR WRAPPER (phase
``FUNDING_INCREMENTAL_EXECUTOR_CORE_EXTRACTION_AND_SUCCESSOR_IMPLEMENTATION_V1``).

This wrapper accepts SYNTHETIC rows only and delegates every mathematical
step to the exactly one active shared scientific core
(``qntylab.jigsaw_funding_pressure_incremental_forecast_value_core_v1``)
through the guarded executor entrypoint.  It performs no math of its own.

Fail-closed properties:

* any execution mode other than ``SYNTHETIC_VALIDATION`` is refused with
  :class:`UnauthorizedExecutionError` before any row is validated;
* no real evidence reader, network client, claim transport or outcome
  accessor exists in this module;
* the qualification attestation is a deterministic, synthetic-only record.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from qntylab.jigsaw_funding_pressure_incremental_forecast_value_core_v1 import (
    IncrementalForecastError,
    UnauthorizedExecutionError,
)
from qntylab.jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import (
    AUTHORIZED_EXECUTION_MODES,
    EXECUTION_MODE_SYNTHETIC_VALIDATION,
    GOVERNING_PREREGISTRATION_DIGEST,
    GOVERNING_PREREGISTRATION_PROJECT_ID,
    IncrementalForecastEvaluation,
    ForecastRow,
    run_incremental_forecast_evaluation,
)

PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_SYNTHETIC_WRAPPER_V1"
WRAPPER_KIND = "SYNTHETIC_VALIDATION"

#: Deterministic qualification attestation: what this wrapper is and is not.
SYNTHETIC_QUALIFICATION_ATTESTATION = MappingProxyType(
    {
        "WRAPPER_KIND": WRAPPER_KIND,
        "SYNTHETIC_ROWS_ONLY": True,
        "REAL_ROWS_ACCEPTED": False,
        "REAL_OUTCOMES_ACCESSED": False,
        "SCIENTIFIC_EXECUTION_PERFORMED": False,
        "EVALUATION_ORIGINS_CONSUMED": 0,
        "NEW_DATA_ACQUIRED": False,
        "SCIENTIFIC_RESULT_RECORDED": False,
        "TRIAL_COMPLETION_RECORDED": False,
        "SHARED_CORE_INVOCATION_ONLY": True,
        "LOCAL_MATH_DUPLICATED": False,
        "GOVERNING_PREREGISTRATION_PROJECT_ID": GOVERNING_PREREGISTRATION_PROJECT_ID,
        "GOVERNING_PREREGISTRATION_DIGEST": GOVERNING_PREREGISTRATION_DIGEST,
        "AUTHORIZED_EXECUTION_MODES": tuple(AUTHORIZED_EXECUTION_MODES),
        "DOWNSTREAM_AUTHORITY": "NONE",
        "CAPITAL_AUTHORITY": "NONE",
    }
)


def require_synthetic_validation_mode(execution_mode: object) -> str:
    """Fail closed unless the caller asks for synthetic validation."""
    if execution_mode != EXECUTION_MODE_SYNTHETIC_VALIDATION:
        raise UnauthorizedExecutionError(
            "the SYNTHETIC_VALIDATION wrapper accepts synthetic rows only; "
            f"execution_mode must be {EXECUTION_MODE_SYNTHETIC_VALIDATION!r}, got {execution_mode!r}"
        )
    return EXECUTION_MODE_SYNTHETIC_VALIDATION


def run_synthetic_validation_evaluation(
    rows: Sequence[ForecastRow], *, execution_mode: object
) -> IncrementalForecastEvaluation:
    """Run the frozen synthetic validation through the shared core.

    Deterministic closure: the returned evaluation is exactly the guarded
    executor entrypoint's output over the shared core; no wrapper-local
    arithmetic exists that could diverge from it.
    """
    mode = require_synthetic_validation_mode(execution_mode)
    return run_incremental_forecast_evaluation(rows, execution_mode=mode)


def synthetic_qualification() -> Mapping[str, object]:
    """The deterministic synthetic-only qualification record."""
    return SYNTHETIC_QUALIFICATION_ATTESTATION


__all__ = [
    "IncrementalForecastError",
    "PROJECT_ID",
    "SYNTHETIC_QUALIFICATION_ATTESTATION",
    "WRAPPER_KIND",
    "require_synthetic_validation_mode",
    "run_synthetic_validation_evaluation",
    "synthetic_qualification",
]
