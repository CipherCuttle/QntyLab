"""Outcome-blind pre-execution integrity reconciliation for the frozen
funding-pressure incremental forecast-value executor.

This module is a *verifier*.  It computes no forecast, reads no real
evaluation outcome, consumes no evaluation origin, acquires no data and
touches no network.  Everything it asserts is derived from Git object
identities, file hashes, frozen JSON artifacts, module constants, and
deterministic synthetic fixtures supplied by the caller.

It discharges three preconditions that the frozen implementation review left
open, and which any future one-shot scientific execution authorization must
be able to cite by exact identity:

* **Historical producer identity.**  The funding provenance baseline is
  authenticated against the immutable Git blobs of its own frozen ancestors,
  never against whatever the shared materializer happens to be at HEAD.
  See :func:`qntylab.jigsaw_funding_pressure_provenance_v0.verify_historical_materializer_identity`.

* **Panel binding (hostile review M-02).**  The exact 20-member ordered panel
  is proven identical across the preregistration, the frozen source binding,
  the V2 executor and the provenance module, bound to the frozen
  preregistration digest.

* **Numerical runtime contract (hostile review M-01).**  The frozen executor
  reaches its frozen synthetic identity under one explicit, literal Decimal
  context, regardless of the ambient interpreter context or its traps.  The
  frozen algorithm is NOT modified; the runtime is pinned instead.

Nothing here grants execution authority.  ``reconcile`` returns a receipt
describing what was authenticated; it never returns, implies, or creates
permission to run the 244-origin evaluation.
"""
from __future__ import annotations

import decimal
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from decimal import Context, ROUND_HALF_EVEN, localcontext
from pathlib import Path

from qntylab import jigsaw_funding_pressure_execution_v2 as v2
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as executor
from qntylab import jigsaw_funding_pressure_provenance_v0 as provenance

# ==========================================================================
# SECTION 0 -- identity and authority boundary
# ==========================================================================

PHASE_ID = "FUNDING_INCREMENTAL_PRE_EXECUTION_INTEGRITY_RECONCILIATION_V0"
PROJECT_ID = "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_PRE_EXECUTION_INTEGRITY_V0"
AUTHORITY_LEVEL = "OUTCOME_BLIND_PRE_EXECUTION_INTEGRITY_VERIFICATION_ONLY"

SCIENTIFIC_EXECUTION_AUTHORIZED = False
REAL_EVALUATION_OUTCOME_ACCESS_AUTHORIZED = False
DATA_ACQUISITION_AUTHORIZED = False
DOWNSTREAM_AUTHORITY = "NONE"
ROUTER_AUTHORITY = "NONE"
QNTY_AUTHORITY = "NONE"
TRADING_AUTHORITY = "NONE"
CAPITAL_AUTHORITY = "NONE"

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_RELATIVE_PATH = (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0"
)
EXPERIMENT = ROOT / EXPERIMENT_RELATIVE_PATH
IMPLEMENTATION = EXPERIMENT / "implementation_v0"

# ==========================================================================
# SECTION 1 -- the exact immutable identities a future authorization must cite
# ==========================================================================

#: The governing preregistration contract digest.  Every binding below is
#: anchored to this value; nothing in this module is allowed to reach a PASS
#: while the preregistration is anything other than this exact artifact.
FROZEN_PREREGISTRATION_DIGEST = (
    "d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef"
)
FROZEN_PREREGISTRATION_FILE_SHA256 = (
    "42b96afae80e55611bcd9786169050520525fbc5534b9f94c72ed867380ba9cf"
)
FROZEN_PREREGISTRATION_STATUS = "PREREGISTERED_NOT_EXECUTED"

FROZEN_EXECUTOR_RELATIVE_PATH = (
    "qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
)
FROZEN_EXECUTOR_SHA256 = (
    "b894d4d9316bed6f8c4f7171b32692aff7b1f0eb32abd686a33fdb38425a7490"
)
FROZEN_EXECUTOR_TEST_RELATIVE_PATH = (
    "tests/test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py"
)
FROZEN_EXECUTOR_TEST_SHA256 = (
    "7de2bd14b2997b5aee9f8820b54a1819b8423da5b55d362a8ab7b0bb95bb6d30"
)
FROZEN_V2_SHA256 = "d603e747952d31d1fa87df463b9c739bc495a4e94597c2be0f93c02c678fbbc6"
FROZEN_FOUNDATION_V0_SHA256 = (
    "834964137e4f2b77ab12a1d454f8ba8da9d71330e0806d00d1d2e26f113c980c"
)

#: Frozen implementation artifacts, addressed by raw file SHA-256 exactly as
#: ``implementation_v0/closure.json`` declares them.
FROZEN_SOURCE_BINDING_SHA256 = (
    "9961d086b4c029f52d7840f1abfe200c0d37c6ff7368b81a14b067ae237db7ba"
)
FROZEN_IMPLEMENTATION_MANIFEST_SHA256 = (
    "748c74c2cf039dab287a4b336f0443180202cc3545d1100d6ddc9532887b5fd3"
)
FROZEN_ORIGIN_SCHEDULE_SHA256 = (
    "220eda6dc41b66820d6e1de31ed4023dcd11ec75ee713ea9d8fa9d1e74233d3a"
)
FROZEN_EXECUTION_SEMANTICS_SHA256 = (
    "66000949a064fb913b2a61bcf716304ff324bb58e56602471a726fcbb1a7ccc4"
)
FROZEN_IMPLEMENTATION_AUTHORITY_SHA256 = (
    "ec4862896d7065ee5957f2fc3fbb8abce30ccd1cdee7cae2046a801d5032c296"
)
FROZEN_SYNTHETIC_VALIDATION_SHA256 = (
    "a882cfecc07bc6fc3bbb3d3f6a693e557918dac4d8795e7bc0d155c82d7011aa"
)

#: The commit the implementation freeze reviewed and froze.
FROZEN_IMPLEMENTATION_SHA = "f6f12994d65c3dfeaf7839de560e58ad99547c62"

#: The frozen synthetic identity of the executor, from
#: ``implementation_v0/synthetic_validation.json``.  The numerical runtime
#: preflight reproduces exactly this and nothing else.
FROZEN_SYNTHETIC_RESULT_DIGEST = (
    "sha256:1fca55ebdbe5c4d5b835cb65f87930755d231449c924eae912b522bd04b53ea2"
)

#: Exactly 244 evaluation origins, from ``implementation_v0/origin_schedule.json``.
FROZEN_EVALUATION_ORIGIN_COUNT = 244
FROZEN_FORECAST_ROW_ORIGIN_COUNT = 609
FROZEN_PANEL_SIZE = 20

_ARTIFACT_SHA256 = {
    "implementation_v0/source_binding.json": FROZEN_SOURCE_BINDING_SHA256,
    "implementation_v0/implementation_manifest.json": FROZEN_IMPLEMENTATION_MANIFEST_SHA256,
    "implementation_v0/origin_schedule.json": FROZEN_ORIGIN_SCHEDULE_SHA256,
    "implementation_v0/execution_semantics_v0.json": FROZEN_EXECUTION_SEMANTICS_SHA256,
    "implementation_v0/implementation_authority.json": FROZEN_IMPLEMENTATION_AUTHORITY_SHA256,
    "implementation_v0/synthetic_validation.json": FROZEN_SYNTHETIC_VALIDATION_SHA256,
    "preregistration.json": FROZEN_PREREGISTRATION_FILE_SHA256,
}

_SOURCE_SHA256 = {
    FROZEN_EXECUTOR_RELATIVE_PATH: FROZEN_EXECUTOR_SHA256,
    FROZEN_EXECUTOR_TEST_RELATIVE_PATH: FROZEN_EXECUTOR_TEST_SHA256,
    "qntylab/jigsaw_funding_pressure_execution_v2.py": FROZEN_V2_SHA256,
    "qntylab/jigsaw_funding_pressure_execution_foundation_v0.py": FROZEN_FOUNDATION_V0_SHA256,
}


class PreExecutionIntegrityError(Exception):
    """Every failure in this module is fail-closed and of this family."""


class HistoricalProvenanceError(PreExecutionIntegrityError):
    pass


class PanelBindingError(PreExecutionIntegrityError):
    pass


class ImplementationIdentityError(PreExecutionIntegrityError):
    pass


class NumericalRuntimeError(PreExecutionIntegrityError):
    pass


class OutcomeFirewallError(PreExecutionIntegrityError):
    pass


# ==========================================================================
# SECTION 2 -- (M-01) the explicit scientific numerical runtime contract
# ==========================================================================

#: The one Decimal context under which the frozen executor may be run.
#:
#: Built from literals rather than copied from ``decimal.DefaultContext``,
#: which is process-global mutable state that an importer could have changed
#: before this module was loaded.  ``prec`` and ``rounding`` here govern only
#: the executor's few ambient-context operations -- notably the M-01 precision
#: guard at ``standard_normal_upper_tail`` -- because every contract-visible
#: quantity is computed in exact rational arithmetic or inside an explicit
#: ``localcontext`` the executor sets for itself.
SCIENTIFIC_RUNTIME_CONTEXT = Context(
    prec=28,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow],
)

SCIENTIFIC_RUNTIME_CONTRACT = {
    "context_identity": "DECIMAL_PREC_28_ROUND_HALF_EVEN_DEFAULT_TRAPS_LITERAL",
    "prec": 28,
    "rounding": "ROUND_HALF_EVEN",
    "Emin": -999999,
    "Emax": 999999,
    "capitals": 1,
    "clamp": 0,
    "traps": ["InvalidOperation", "DivisionByZero", "Overflow"],
    "constructed_from": "MODULE_LITERALS_NOT_DECIMAL_DEFAULTCONTEXT",
    "rationale": (
        "The frozen executor computes every contract-visible quantity in exact "
        "rational arithmetic or inside an explicit localcontext. Its only "
        "ambient-context arithmetic is the M-01 precision guard, which sizes "
        "working precision on top of a fixed 30-digit margin. Pinning the "
        "ambient context makes the guard's size, and any ambient trap "
        "behaviour, an input of the frozen runtime rather than of the caller."
    ),
    "algorithm_modified": False,
    "frozen_executor_sha256": FROZEN_EXECUTOR_SHA256,
}


@contextmanager
def scientific_runtime():
    """Enter the frozen scientific numerical runtime contract.

    Any future authorized execution of the frozen executor MUST run inside
    this context manager.  It neutralizes hostile ambient Decimal state --
    reduced precision, alternative rounding, and nuisance traps such as
    ``Inexact`` or ``Rounded`` that would otherwise raise inside the M-01
    guard -- without altering a single line of the frozen algorithm.
    """
    with localcontext(SCIENTIFIC_RUNTIME_CONTEXT):
        yield


# ==========================================================================
# SECTION 3 -- helpers
# ==========================================================================


def file_sha256(relative_path: str, root: Path = ROOT) -> str:
    path = root / relative_path
    if not path.is_file():
        raise ImplementationIdentityError(f"required file is absent: {relative_path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(relative_path: str, root: Path = ROOT) -> dict:
    return json.loads((root / relative_path).read_text(encoding="utf-8"))


def _canonical_digest(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _without(payload: Mapping[str, object], key: str) -> dict:
    result = dict(payload)
    result.pop(key, None)
    return result


# ==========================================================================
# SECTION 4 -- historical provenance reconciliation
# ==========================================================================


def verify_historical_provenance(root: Path = ROOT) -> dict:
    """Authenticate the historical funding producer identity, fail-closed.

    Delegates the identity proof to the provenance module so there is exactly
    one implementation of it, then re-asserts here that the proof was made
    against immutable Git anchors and that the frozen baseline bytes were not
    rewritten to accommodate the current worktree.
    """
    baseline = provenance._load("provenance_baseline_v0.json")
    provenance.verify_self_digest(baseline, "provenance_baseline_digest")

    materializers = provenance.verify_historical_materializer_identity(baseline, root)
    if not materializers:
        raise HistoricalProvenanceError("no materializer identity was authenticated")

    laundered = []
    for entry in materializers:
        relative_path = entry["relative_path"]
        frozen = entry["file_sha256"]
        current = file_sha256(relative_path, root)
        if not entry["anchors"]:
            raise HistoricalProvenanceError(
                f"materializer {relative_path} was authenticated against no anchor"
            )
        # The frozen record must still say what history says, not what HEAD
        # says.  If they happen to coincide that is fine; what must never
        # happen is the frozen value having been *replaced* by the current one.
        for anchor in entry["anchors"]:
            historical = provenance.historical_materializer_digest(anchor, relative_path, root)
            if historical != frozen:
                raise HistoricalProvenanceError(
                    f"frozen materializer digest for {relative_path} does not match "
                    f"the historical blob at {anchor}"
                )
        laundered.append(
            {
                "relative_path": relative_path,
                "frozen_historical_sha256": frozen,
                "current_worktree_sha256": current,
                "diverged_from_current_worktree": current != frozen,
                "authenticated_against": list(entry["anchors"]),
            }
        )
    return {
        "historical_materializer_identity_authenticated": True,
        "current_materializer_laundered_into_history": False,
        "authentication_source": "IMMUTABLE_GIT_BLOB_AT_FROZEN_BASELINE_ANCESTORS",
        "frozen_baseline_digest": baseline["provenance_baseline_digest"],
        "frozen_baseline_mutated": False,
        "materializers": laundered,
    }


# ==========================================================================
# SECTION 5 -- (M-02) exact panel binding
# ==========================================================================


def verify_panel_binding(root: Path = ROOT) -> dict:
    """Prove the exact 20-member ordered panel is one object, four ways.

    Equality is list equality on ``str``: exact members, exact order, no
    substitution, no extra, no omission.  The whole check is refused unless
    the preregistration it reads is the frozen digest-bound artifact.
    """
    prereg_relative = f"{EXPERIMENT_RELATIVE_PATH}/preregistration.json"
    prereg = _load_json(prereg_relative, root)

    declared = prereg.get("preregistration_digest")
    recomputed = _canonical_digest(_without(prereg, "preregistration_digest"))
    if declared != FROZEN_PREREGISTRATION_DIGEST:
        raise PanelBindingError(
            f"preregistration declares digest {declared}, "
            f"frozen contract requires {FROZEN_PREREGISTRATION_DIGEST}"
        )
    if recomputed != FROZEN_PREREGISTRATION_DIGEST:
        raise PanelBindingError(
            f"preregistration content digest is {recomputed}, "
            f"frozen contract requires {FROZEN_PREREGISTRATION_DIGEST}"
        )
    if prereg.get("status") != FROZEN_PREREGISTRATION_STATUS:
        raise PanelBindingError(
            f"preregistration status is {prereg.get('status')!r}, "
            f"expected {FROZEN_PREREGISTRATION_STATUS!r}"
        )

    source_binding = _load_json(
        f"{EXPERIMENT_RELATIVE_PATH}/implementation_v0/source_binding.json", root
    )

    panels = {
        "preregistration.feature_contract.panel": list(prereg["feature_contract"]["panel"]),
        "implementation_v0.source_binding.exact_panel": list(source_binding["exact_panel"]),
        "jigsaw_funding_pressure_execution_v2.PANEL": list(v2.PANEL),
        "jigsaw_funding_pressure_provenance_v0.PANEL": list(provenance.PANEL),
    }

    reference_name = "preregistration.feature_contract.panel"
    reference = panels[reference_name]

    if len(reference) != FROZEN_PANEL_SIZE:
        raise PanelBindingError(
            f"panel has {len(reference)} members, frozen contract requires {FROZEN_PANEL_SIZE}"
        )
    if len(set(reference)) != FROZEN_PANEL_SIZE:
        raise PanelBindingError("panel contains a duplicate member")
    if not all(isinstance(symbol, str) and symbol for symbol in reference):
        raise PanelBindingError("panel contains a non-string or empty member")

    for name, panel in panels.items():
        if panel != reference:
            missing = [s for s in reference if s not in panel]
            extra = [s for s in panel if s not in reference]
            if missing or extra:
                raise PanelBindingError(
                    f"panel substitution between {reference_name} and {name}: "
                    f"missing={missing} extra={extra}"
                )
            raise PanelBindingError(
                f"panel order mismatch between {reference_name} and {name}: "
                f"{panel} != {reference}"
            )

    return {
        "panel_binding_established": True,
        "bound_to_preregistration_digest": FROZEN_PREREGISTRATION_DIGEST,
        "panel_member_count": FROZEN_PANEL_SIZE,
        "compared_sources": sorted(panels),
        "exact_ordered_panel": list(reference),
        "panel_substitution": False,
        "panel_order_mismatch": False,
        "panel_extras": 0,
        "panel_omissions": 0,
        "m02_discharged": True,
    }


# ==========================================================================
# SECTION 6 -- exact implementation identity precondition
# ==========================================================================


def verify_implementation_identity(root: Path = ROOT) -> dict:
    """Bind every artifact a future authorization must name, by exact digest.

    A future execution authorization may not refer to "current code"; it must
    cite these immutable values.  Any drift here fails closed.
    """
    source_digests = {}
    for relative_path, expected in sorted(_SOURCE_SHA256.items()):
        actual = file_sha256(relative_path, root)
        if actual != expected:
            raise ImplementationIdentityError(
                f"source identity drift: {relative_path} is {actual}, frozen identity is {expected}"
            )
        source_digests[relative_path] = actual

    artifact_digests = {}
    for relative_path, expected in sorted(_ARTIFACT_SHA256.items()):
        actual = file_sha256(f"{EXPERIMENT_RELATIVE_PATH}/{relative_path}", root)
        if actual != expected:
            raise ImplementationIdentityError(
                f"artifact identity drift: {relative_path} is {actual}, frozen identity is {expected}"
            )
        artifact_digests[relative_path] = actual

    closure = _load_json(
        f"{EXPERIMENT_RELATIVE_PATH}/implementation_v0/closure.json", root
    )
    for field, expected in [
        ("governing_preregistration_digest", FROZEN_PREREGISTRATION_DIGEST),
        ("source_binding_digest", FROZEN_SOURCE_BINDING_SHA256),
        ("implementation_manifest_digest", FROZEN_IMPLEMENTATION_MANIFEST_SHA256),
        ("origin_schedule_digest", FROZEN_ORIGIN_SCHEDULE_SHA256),
        ("execution_semantics_digest", FROZEN_EXECUTION_SEMANTICS_SHA256),
        ("authority_artifact_digest", FROZEN_IMPLEMENTATION_AUTHORITY_SHA256),
        ("synthetic_validation_digest", FROZEN_SYNTHETIC_VALIDATION_SHA256),
        ("final_implementation_sha", FROZEN_IMPLEMENTATION_SHA),
    ]:
        if closure.get(field) != expected:
            raise ImplementationIdentityError(
                f"closure.{field} is {closure.get(field)!r}, frozen identity is {expected!r}"
            )
    if closure.get("state") != "CLOSED_PASS":
        raise ImplementationIdentityError(
            f"implementation phase state is {closure.get('state')!r}, expected 'CLOSED_PASS'"
        )
    if closure.get("real_scientific_execution_performed") is not False:
        raise ImplementationIdentityError("implementation closure claims real scientific execution")

    source_binding = _load_json(
        f"{EXPERIMENT_RELATIVE_PATH}/implementation_v0/source_binding.json", root
    )
    if source_binding["governing_preregistration_contract_digest"] != FROZEN_PREREGISTRATION_DIGEST:
        raise ImplementationIdentityError("source binding names a different preregistration contract")
    if source_binding["governing_preregistration_file_sha256"] != FROZEN_PREREGISTRATION_FILE_SHA256:
        raise ImplementationIdentityError("source binding names different preregistration bytes")
    for relative_path, expected in source_binding["implementation_source_sha256"].items():
        if source_digests.get(relative_path) != expected:
            raise ImplementationIdentityError(
                f"source binding disagrees with the worktree for {relative_path}"
            )
    for relative_path, expected in source_binding["reused_canonical_source_sha256"].items():
        if source_digests.get(relative_path) != expected:
            raise ImplementationIdentityError(
                f"source binding disagrees with the worktree for reused {relative_path}"
            )

    schedule = _load_json(
        f"{EXPERIMENT_RELATIVE_PATH}/implementation_v0/origin_schedule.json", root
    )
    if schedule["evaluation_origin_count"] != FROZEN_EVALUATION_ORIGIN_COUNT:
        raise ImplementationIdentityError(
            f"origin schedule declares {schedule['evaluation_origin_count']} evaluation origins, "
            f"frozen contract requires {FROZEN_EVALUATION_ORIGIN_COUNT}"
        )
    if schedule["forecast_row_origin_count"] != FROZEN_FORECAST_ROW_ORIGIN_COUNT:
        raise ImplementationIdentityError("origin schedule declares a different forecast row count")

    # The executor's own declared identity must agree with the frozen record.
    identity = executor.implementation_identity()
    if identity["implementation_source_sha256"] != FROZEN_EXECUTOR_SHA256:
        raise ImplementationIdentityError("executor self-reported identity does not match the frozen digest")
    if identity["governing_preregistration_digest"] != FROZEN_PREREGISTRATION_DIGEST:
        raise ImplementationIdentityError("executor names a different governing preregistration")
    if list(identity["execution_modes"]) != ["SYNTHETIC_VALIDATION"]:
        raise ImplementationIdentityError(
            f"executor advertises execution modes {identity['execution_modes']!r}"
        )

    return {
        "implementation_identity_bound": True,
        "frozen_implementation_sha": FROZEN_IMPLEMENTATION_SHA,
        "governing_preregistration_digest": FROZEN_PREREGISTRATION_DIGEST,
        "executor_sha256": FROZEN_EXECUTOR_SHA256,
        "executor_test_sha256": FROZEN_EXECUTOR_TEST_SHA256,
        "v2_sha256": FROZEN_V2_SHA256,
        "foundation_v0_sha256": FROZEN_FOUNDATION_V0_SHA256,
        "source_binding_sha256": FROZEN_SOURCE_BINDING_SHA256,
        "implementation_manifest_sha256": FROZEN_IMPLEMENTATION_MANIFEST_SHA256,
        "origin_schedule_sha256": FROZEN_ORIGIN_SCHEDULE_SHA256,
        "execution_semantics_sha256": FROZEN_EXECUTION_SEMANTICS_SHA256,
        "implementation_authority_sha256": FROZEN_IMPLEMENTATION_AUTHORITY_SHA256,
        "synthetic_validation_sha256": FROZEN_SYNTHETIC_VALIDATION_SHA256,
        "evaluation_origin_count": FROZEN_EVALUATION_ORIGIN_COUNT,
        "source_digests": source_digests,
        "artifact_digests": artifact_digests,
    }


# ==========================================================================
# SECTION 7 -- (M-01) synthetic numerical runtime preflight
# ==========================================================================

#: Ambient Decimal contexts the preflight runs the executor under.  Each is a
#: hostile caller state the frozen runtime contract must absorb.
def hostile_ambient_contexts() -> list[tuple[str, Context]]:
    contexts: list[tuple[str, Context]] = []
    for prec in (1, 2, 7, 300):
        for rounding in (
            decimal.ROUND_UP,
            decimal.ROUND_FLOOR,
            decimal.ROUND_CEILING,
            decimal.ROUND_05UP,
        ):
            contexts.append((f"prec={prec},rounding={rounding}", Context(prec=prec, rounding=rounding)))
    for trap in (
        decimal.Inexact,
        decimal.Rounded,
        decimal.Subnormal,
        decimal.Clamped,
        decimal.Underflow,
        decimal.FloatOperation,
    ):
        context = Context(prec=9, rounding=decimal.ROUND_UP)
        context.traps[trap] = True
        contexts.append((f"prec=9,trap={trap.__name__}", context))
    squeezed = Context(prec=9, Emin=-5, Emax=5, rounding=decimal.ROUND_UP)
    contexts.append(("prec=9,Emin=-5,Emax=5", squeezed))
    everything = Context(prec=1, rounding=decimal.ROUND_UP)
    for trap in (decimal.Inexact, decimal.Rounded, decimal.Subnormal, decimal.Clamped, decimal.Underflow):
        everything.traps[trap] = True
    contexts.append(("prec=1,all-nuisance-traps", everything))
    return contexts


def run_synthetic_runtime_preflight(
    synthetic_rows_factory: Callable[[], Sequence[object]],
    root: Path = ROOT,
) -> dict:
    """Prove the frozen executor reaches its frozen synthetic identity.

    ``synthetic_rows_factory`` must return deterministic SYNTHETIC forecast
    rows.  This function never loads, and has no way to load, real frozen
    evidence: the executor's only evaluation entrypoint refuses any execution
    mode other than ``SYNTHETIC_VALIDATION``, and no evidence loader is
    referenced here.

    The preflight asserts three things:

    1. Under the frozen runtime contract, the synthetic result digest equals
       the frozen ``synthetic_run_1_digest``, and is stable on replay.
    2. Under every hostile ambient context, the frozen runtime contract still
       yields exactly that digest.
    3. The digest is never *silently different* under any ambient context --
       divergence is a fail-closed defect, whereas an exception raised outside
       the contract is merely fail-closed behaviour and is recorded as such.
    """
    rows = synthetic_rows_factory()

    with scientific_runtime():
        first = executor.run_incremental_forecast_evaluation(
            rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
        ).result_digest
        second = executor.run_incremental_forecast_evaluation(
            rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
        ).result_digest

    if first != second:
        raise NumericalRuntimeError(
            f"frozen runtime contract is not replay-stable: {first} != {second}"
        )
    if first != FROZEN_SYNTHETIC_RESULT_DIGEST:
        raise NumericalRuntimeError(
            f"frozen synthetic identity not reproduced: got {first}, "
            f"frozen identity is {FROZEN_SYNTHETIC_RESULT_DIGEST}"
        )

    under_contract = []
    without_contract = []
    for name, ambient in hostile_ambient_contexts():
        with localcontext(ambient):
            with scientific_runtime():
                digest = executor.run_incremental_forecast_evaluation(
                    rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
                ).result_digest
        if digest != FROZEN_SYNTHETIC_RESULT_DIGEST:
            raise NumericalRuntimeError(
                f"frozen runtime contract failed to absorb ambient context {name}: got {digest}"
            )
        under_contract.append(name)

        # Outside the contract, record -- but do not require -- the behaviour.
        # A different digest would be a genuine reproducibility defect; an
        # exception is fail-closed and acceptable.
        try:
            with localcontext(ambient):
                bare = executor.run_incremental_forecast_evaluation(
                    rows, execution_mode=executor.EXECUTION_MODE_SYNTHETIC_VALIDATION
                ).result_digest
            outcome = "IDENTICAL" if bare == FROZEN_SYNTHETIC_RESULT_DIGEST else "DIVERGED"
        except Exception as exc:  # noqa: BLE001 - classification, not control flow
            outcome = f"FAILED_CLOSED:{type(exc).__name__}"
        if outcome == "DIVERGED":
            raise NumericalRuntimeError(
                f"ambient context {name} silently changed the synthetic result digest"
            )
        without_contract.append({"ambient_context": name, "outcome": outcome})

    return {
        "synthetic_runtime_preflight": "PASS",
        "mode": "SYNTHETIC_VALIDATION",
        "frozen_synthetic_result_digest": FROZEN_SYNTHETIC_RESULT_DIGEST,
        "replay_stable": True,
        "runtime_contract": dict(SCIENTIFIC_RUNTIME_CONTRACT),
        "hostile_ambient_contexts_tested": len(under_contract),
        "hostile_ambient_contexts_absorbed": len(under_contract),
        "silent_divergences": 0,
        "unwrapped_behaviour": without_contract,
        "m01_discharged": True,
        "frozen_algorithm_modified": False,
        "real_outcome_accessed": False,
        "evaluation_origins_consumed": 0,
    }


# ==========================================================================
# SECTION 8 -- outcome firewall
# ==========================================================================

#: Names the executor must never expose to this phase, and which no code path
#: here calls.  Checked structurally so the attestation is not merely prose.
_FORBIDDEN_REAL_EVIDENCE_ENTRYPOINTS = (
    "load_verified_frozen_evidence",
    "execute_authorized_frozen_experiment_v2",
    "claim_authorization_once",
    "compute_frozen_experiment",
    "build_receipt_provenance",
)


def verify_outcome_firewall() -> dict:
    """Assert this phase cannot reach a real evaluation outcome."""
    module_source = Path(__file__).read_bytes().decode("utf-8")
    for name in _FORBIDDEN_REAL_EVIDENCE_ENTRYPOINTS:
        # The tuple literal above is the only place these names may appear.
        occurrences = module_source.count(name)
        if occurrences > 1:
            raise OutcomeFirewallError(
                f"this module references the real-evidence entrypoint {name!r}"
            )
    if executor.AUTHORIZED_EXECUTION_MODES != (executor.EXECUTION_MODE_SYNTHETIC_VALIDATION,):
        raise OutcomeFirewallError(
            "the frozen executor advertises an execution mode beyond SYNTHETIC_VALIDATION"
        )
    for attribute, expected in [
        ("DOWNSTREAM_AUTHORITY", "NONE"),
        ("CAPITAL_AUTHORITY", "NONE"),
    ]:
        value = getattr(executor, attribute, None)
        if value != expected:
            raise OutcomeFirewallError(f"executor.{attribute} is {value!r}, expected {expected!r}")
    return {
        "real_scientific_execution_performed": False,
        "real_evaluation_outcome_access_performed": False,
        "evaluation_origins_consumed": 0,
        "real_forecasts_computed": 0,
        "real_clark_west_computed": False,
        "real_mse_computed": False,
        "real_p_value_computed": False,
        "scientific_result_created": False,
        "scientific_result_persisted": False,
        "data_acquisition_performed": False,
        "network_access_performed": False,
        "frozen_evidence_mutated": False,
        "preregistration_mutated": False,
        "order_flow_modified": False,
        "jh01_modified": False,
        "authorized_execution_modes": list(executor.AUTHORIZED_EXECUTION_MODES),
    }


# ==========================================================================
# SECTION 9 -- orchestration
# ==========================================================================


def reconcile(
    synthetic_rows_factory: Callable[[], Sequence[object]] | None = None,
    root: Path = ROOT,
) -> dict:
    """Run the whole outcome-blind reconciliation and return its receipt.

    The receipt records what was authenticated.  It is explicitly NOT an
    execution authorization: ``scientific_execution_authorized`` is a frozen
    ``False`` and ``next_action`` says what a separate phase must still do.
    """
    firewall = verify_outcome_firewall()
    historical = verify_historical_provenance(root)
    panel = verify_panel_binding(root)
    identity = verify_implementation_identity(root)
    preflight = (
        run_synthetic_runtime_preflight(synthetic_rows_factory, root)
        if synthetic_rows_factory is not None
        else {"synthetic_runtime_preflight": "NOT_RUN"}
    )

    return {
        "artifact_type": "FUNDING_INCREMENTAL_PRE_EXECUTION_INTEGRITY_RECONCILIATION",
        "phase_id": PHASE_ID,
        "project_id": PROJECT_ID,
        "authority_level": AUTHORITY_LEVEL,
        "historical_provenance": historical,
        "panel_binding": panel,
        "implementation_identity": identity,
        "numerical_runtime_preflight": preflight,
        "outcome_firewall": firewall,
        "scientific_execution_authorized": SCIENTIFIC_EXECUTION_AUTHORIZED,
        "real_evaluation_outcome_access_authorized": REAL_EVALUATION_OUTCOME_ACCESS_AUTHORIZED,
        "data_acquisition_authorized": DATA_ACQUISITION_AUTHORIZED,
        "downstream_authority": DOWNSTREAM_AUTHORITY,
        "router_authority": ROUTER_AUTHORITY,
        "qnty_authority": QNTY_AUTHORITY,
        "trading_authority": TRADING_AUTHORITY,
        "capital_authority": CAPITAL_AUTHORITY,
        "next_action": (
            "Separately create an exact one-shot scientific execution authorization bound "
            "to the frozen preregistration digest "
            f"{FROZEN_PREREGISTRATION_DIGEST}, the frozen executor "
            f"{FROZEN_EXECUTOR_SHA256}, the authenticated historical evidence identity, the "
            f"exact {FROZEN_PANEL_SIZE}-member ordered panel, the "
            f"{FROZEN_EVALUATION_ORIGIN_COUNT}-origin schedule, and the frozen numerical "
            "runtime contract. This reconciliation does not create, imply, or contain that "
            "authorization."
        ),
    }


if __name__ == "__main__":  # pragma: no cover - manual, outcome-blind inspection
    print(json.dumps(reconcile(), indent=2, sort_keys=True))
