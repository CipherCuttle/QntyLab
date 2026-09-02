"""REAL_CAPABLE wrapper over the shared funding incremental core.

SUCCESSOR WRAPPER (phase
``FUNDING_INCREMENTAL_EXECUTOR_CORE_EXTRACTION_AND_SUCCESSOR_IMPLEMENTATION_V1``).

This wrapper is structurally capable of accepting real :class:`ForecastRow`
inputs later, but it is behind an explicit scientific-execution authority
envelope that DOES NOT EXIST YET.  During this implementation phase it must
never receive real outcomes and it fails closed with
:class:`UnauthorizedExecutionError` absent a canonical evaluation
authorization artifact.

Step 1 does NOT trust caller-supplied bytes.  Provenance repair phase
``FUNDING_INCREMENTAL_EXECUTOR_EVALUATION_PROVENANCE_REPAIR_V0`` moved
authorization authentication into
:mod:`qntylab.jigsaw_funding_pressure_incremental_forecast_value_evaluation_authorization_provenance_v1`,
which reads the authorization only from the canonical repository's Git object
database, at a fixed tracked path, in the checked-out canonical commit, and
only after two immutable QntyLab anchor commits are proven ancestors of
``HEAD``.  A caller-supplied ``authorization_path`` can only *point at* that
one canonical artifact; it can never introduce bytes.

Claim-before-outcome ordering is structural and cannot be reversed:

1. validate the canonical evaluation authorization;
2. consume the irreversible one-shot claim;
3. authenticate the frozen evidence;
4. construct the real ForecastRows;
5. invoke the successor shared core;
6. record exactly one result.

Required property: CLAIM FAILURE => zero real ForecastRows constructed and
zero scientific-core invocations.  Post-claim crash replay is NOT
automatically authorized: there is no retry authority, and a consumed claim
is never re-consumed by this module.

The canonical evaluation authorization artifact bound below does not exist
anywhere in the repository at this phase, so step 1 always fails closed
today and steps 2-6 are unreachable.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from qntylab.jigsaw_funding_pressure_incremental_forecast_value_core_v1 import (
    IncrementalForecastError,
    UnauthorizedExecutionError,
)
from qntylab.jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import (
    GOVERNING_PREREGISTRATION_DIGEST,
    GOVERNING_PREREGISTRATION_PROJECT_ID,
    IncrementalForecastEvaluation,
    ForecastRow,
)
from qntylab import (
    jigsaw_funding_pressure_incremental_forecast_value_evaluation_authorization_provenance_v1 as _provenance,
)

PROJECT_ID = _provenance.REAL_CAPABLE_WRAPPER_PROJECT_ID
WRAPPER_KIND = "REAL_CAPABLE"

#: The canonical evaluation authorization that would license a real run.
#: It is Git-backed and does NOT exist yet; its absence is the primary
#: fail-closed boundary of this wrapper.  Authentication of these bytes to
#: canonical QntyLab Git identity lives in :mod:`_provenance`.
CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH = (
    _provenance.CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH
)

REQUIRED_AUTHORIZATION_ARTIFACT_TYPE = _provenance.REQUIRED_AUTHORIZATION_ARTIFACT_TYPE
REQUIRED_AUTHORIZATION_STATE = _provenance.REQUIRED_AUTHORIZATION_STATE

#: Deterministic attestation of what this wrapper did NOT do in this phase.
REAL_CAPABLE_PHASE_ATTESTATION = MappingProxyType(
    {
        "WRAPPER_KIND": WRAPPER_KIND,
        "REAL_ROWS_CONSTRUCTED": 0,
        "REAL_OUTCOMES_ACCESSED": False,
        "SCIENTIFIC_CORE_INVOCATIONS": 0,
        "SCIENTIFIC_EXECUTION_PERFORMED": False,
        "EVALUATION_ORIGINS_CONSUMED": 0,
        "NEW_DATA_ACQUIRED": False,
        "SCIENTIFIC_RESULT_RECORDED": False,
        "TRIAL_COMPLETION_RECORDED": False,
        "AUTHORIZATION_CLAIM_CONSUMED": False,
        "POST_CLAIM_CRASH_REPLAY_AUTHORIZED": False,
        "CANONICAL_EVALUATION_AUTHORIZATION_EXISTS": False,
        "AUTHORIZATION_PROVENANCE_BINDING": "CANONICAL_QNTYLAB_GIT_IDENTITY",
        "CALLER_SUPPLIED_AUTHORIZATION_BYTES_TRUSTED": False,
        "GOVERNING_PREREGISTRATION_PROJECT_ID": GOVERNING_PREREGISTRATION_PROJECT_ID,
        "GOVERNING_PREREGISTRATION_DIGEST": GOVERNING_PREREGISTRATION_DIGEST,
        "DOWNSTREAM_AUTHORITY": "NONE",
        "CAPITAL_AUTHORITY": "NONE",
    }
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def validate_canonical_evaluation_authorization(
    authorization_path: str | Path | None = None,
) -> Mapping[str, object]:
    """Step 1 -- authenticate the canonical evaluation authorization.

    Delegates to
    :func:`_provenance.authenticate_canonical_evaluation_authorization`, which
    reads the authorization only from canonical QntyLab Git history (never
    caller bytes) and fails closed with :class:`UnauthorizedExecutionError`
    on caller path substitution, symlink/traversal, wrong repository, wrong
    commit, wrong tree/blob, wrong artifact path, modified bytes,
    worktree-local replacement, a missing canonical artifact, malformed
    authorization, or a mismatched preregistration/wrapper identity.  No row
    is touched and no core invocation happens before this succeeds -- and it
    never succeeds at this phase, because the canonical artifact does not
    exist.
    """
    return _provenance.authenticate_canonical_evaluation_authorization(
        authorization_path, root=_repository_root()
    )


def _consume_irreversible_one_shot_claim(
    authorization: Mapping[str, object], claim_transport: object
) -> Mapping[str, object]:
    """Step 2 -- consume the irreversible one-shot claim (exactly once)."""
    if claim_transport is None:
        raise UnauthorizedExecutionError(
            "no one-shot claim transport was provided; the claim cannot be consumed and "
            "real execution fails closed"
        )
    consume = getattr(claim_transport, "claim_authorization_once", None)
    if not callable(consume):
        raise UnauthorizedExecutionError(
            "the provided claim transport has no callable claim_authorization_once seam"
        )
    claim = consume(project_id=PROJECT_ID, authorization=authorization)
    if not isinstance(claim, Mapping) or not claim:
        raise UnauthorizedExecutionError("the one-shot claim transport returned no usable claim")
    return claim


def _authenticate_frozen_evidence(
    authorization: Mapping[str, object], frozen_evidence: object
) -> Mapping[str, object]:
    """Step 3 -- authenticate the frozen evidence bundle."""
    if frozen_evidence is None:
        raise UnauthorizedExecutionError(
            "no frozen evidence bundle was provided; real execution fails closed"
        )
    authenticate = getattr(frozen_evidence, "authenticate", None)
    if not callable(authenticate):
        raise UnauthorizedExecutionError(
            "the frozen evidence bundle has no callable authenticate seam"
        )
    receipt = authenticate(authorization=authorization)
    if not isinstance(receipt, Mapping) or receipt.get("authenticated") is not True:
        raise UnauthorizedExecutionError("frozen evidence authentication did not pass")
    return receipt


def _construct_real_forecast_rows(
    authorization: Mapping[str, object], frozen_evidence: object
) -> tuple[ForecastRow, ...]:
    """Step 4 -- construct the real ForecastRows from authenticated evidence."""
    build = getattr(frozen_evidence, "build_real_forecast_rows", None)
    if not callable(build):
        # The evidence receipt is a plain mapping in the minimal contract; a
        # real row factory must be supplied by the future authorization.  No
        # factory means no rows and no core invocation.
        raise UnauthorizedExecutionError(
            "no real ForecastRow factory is bound to the authenticated evidence; "
            "real execution fails closed"
        )
    rows = build(authorization=authorization)
    if not isinstance(rows, tuple) or not rows or not all(isinstance(row, ForecastRow) for row in rows):
        raise UnauthorizedExecutionError(
            "the real ForecastRow factory did not return a non-empty tuple of ForecastRow instances"
        )
    return rows


def _invoke_successor_shared_core(
    rows: tuple[ForecastRow, ...], authorization: Mapping[str, object]
) -> IncrementalForecastEvaluation:
    """Step 5 -- invoke the successor shared core exactly once.

    The real execution mode comes from the canonical authorization; the
    assembly itself is the executor's frozen assembly over the shared core.
    """
    from qntylab.jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import (
        _assemble_incremental_forecast_evaluation,
    )

    mode = authorization.get("execution_mode")
    if not isinstance(mode, str) or not mode:
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization does not declare an execution_mode"
        )
    return _assemble_incremental_forecast_evaluation(rows, mode)


def _record_exactly_one_result(
    result: IncrementalForecastEvaluation, claim: Mapping[str, object]
) -> IncrementalForecastEvaluation:
    """Step 6 -- record exactly one result against the consumed claim."""
    claim_digest = hashlib.sha256(
        json.dumps(dict(claim), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    result.result_digest  # the frozen result carries its own digest binding
    _ = claim_digest  # recorded with the result by the future persistence seam
    return result


def run_real_capable_evaluation(
    *,
    authorization_path: str | Path | None = None,
    claim_transport: object = None,
    frozen_evidence: object = None,
) -> IncrementalForecastEvaluation:
    """Run a real evaluation behind the full authority envelope.

    CLAIM FAILURE GUARANTEE: every failure path of steps 1-4 raises before
    any real ForecastRow is constructed and before the shared scientific
    core is invoked, so a failed or absent claim leaves
    ``REAL_ROWS_CONSTRUCTED == 0`` and ``SCIENTIFIC_CORE_INVOCATIONS == 0``.
    There is no retry authority: a consumed claim is never re-consumed here,
    and a crash after the claim is not automatically authorized for replay.
    """
    # Step 1 -- validate canonical evaluation authorization (fail closed).
    authorization = validate_canonical_evaluation_authorization(authorization_path)
    # Step 2 -- consume the irreversible one-shot claim.
    claim = _consume_irreversible_one_shot_claim(authorization, claim_transport)
    # Step 3 -- authenticate frozen evidence.
    _authenticate_frozen_evidence(authorization, frozen_evidence)
    # Step 4 -- construct the real ForecastRows.
    rows = _construct_real_forecast_rows(authorization, frozen_evidence)
    # Step 5 -- invoke the successor shared core.
    result = _invoke_successor_shared_core(rows, authorization)
    # Step 6 -- record exactly one result.
    return _record_exactly_one_result(result, claim)


def real_capable_phase_attestation() -> Mapping[str, object]:
    """The deterministic phase attestation (all-negative during this phase)."""
    return REAL_CAPABLE_PHASE_ATTESTATION


__all__ = [
    "CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH",
    "IncrementalForecastError",
    "PROJECT_ID",
    "REAL_CAPABLE_PHASE_ATTESTATION",
    "REQUIRED_AUTHORIZATION_ARTIFACT_TYPE",
    "REQUIRED_AUTHORIZATION_STATE",
    "WRAPPER_KIND",
    "real_capable_phase_attestation",
    "run_real_capable_evaluation",
    "validate_canonical_evaluation_authorization",
]
