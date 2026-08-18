"""Frozen comparison-validity layer for SUBSCRIPTION_BACKED_STAGE_A_V1.

This module adds nothing to the frozen scorer.  Binary correctness stays
exactly ``1 = task correct`` / ``0 = task incorrect`` and no partial-credit
weight is invented.  What is added is the predeclared question the frozen V1
gate schema never asked: *was this benchmark informative at all?*

Before this amendment the primary comparator was ``treatment_correctness >=
baseline_correctness``, which ``0 >= 0`` satisfies.  An episode in which
neither arm solved the historical task could therefore reach a PASS-like
classification.  That is scientifically ambiguous: nothing about DSH
orchestration non-inferiority has been established when no compared system
produced a correct solution.

The layer is a *narrowing*.  It removes PASS reachability from the
both-arms-incorrect cell and names that cell explicitly; it does not widen any
PASS path, does not require the native baseline to be correct, and does not
change task, scorer, intervention, product, role, arm-order, or authority
bytes.

Authority: measurement interpretation only.  Nothing here grants runtime,
scientific, trading, capital, Qnty NEXT_ACTION, publication, merge, or
promotion authority, and nothing here authorizes a second episode.
"""

from __future__ import annotations

from dataclasses import dataclass

from qntylab.subscription_backed_stage_a_v1 import (
    DSH_ARM,
    EXPERIMENT_ID,
    NATIVE_ARM,
    FailClosed,
)

AMENDMENT_ID = "SUBSCRIPTION_BACKED_STAGE_A_V1_COMPARATOR_VALIDITY_REPAIR_V0"
CANONICAL_PR131_MERGE = "332bf46a5543b852197547ffd850b563039c75e5"

#: Frozen V1 outcomes, unchanged by this amendment.
CLASSIFICATION_FAIL = "STAGE_A_V1_FAIL"
CLASSIFICATION_PASS_NO_INCREMENTAL_VALUE = "STAGE_A_V1_PASS_NO_INCREMENTAL_VALUE"
CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE = "STAGE_A_V1_PASS_WITH_INCREMENTAL_VALUE"
CLASSIFICATION_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY = (
    "STAGE_A_V1_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY"
)
#: The one outcome this amendment adds.  Not PASS, not FAIL, grants no
#: authority, grants no rerun, and consumes the single authorized episode if
#: it is reached after dispatch.
CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT = (
    "STAGE_A_V1_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT"
)

PASS_CLASSIFICATIONS = frozenset(
    {CLASSIFICATION_PASS_NO_INCREMENTAL_VALUE, CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE}
)
CLASSIFICATIONS = frozenset(
    PASS_CLASSIFICATIONS
    | {
        CLASSIFICATION_FAIL,
        CLASSIFICATION_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY,
        CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT,
    }
)

#: Precedence is frozen here, before dispatch, so that no later classifier can
#: reorder it after seeing results.  Rank order is the evaluation order of
#: :func:`classify`; the first rank whose condition holds decides the episode.
PRECEDENCE = (
    "R1_AUTHORITY_FIREWALL_OR_UNSEALED_RECEIPT_FAIL_CLOSED",
    "R2_MEASURED_HARD_GATE_FAILURE",
    "R3_ENVIRONMENT_OR_PRODUCT_CAPACITY_INVALIDATION",
    "R4_MISSING_OR_MALFORMED_SCORER_EVIDENCE_FAIL_CLOSED",
    "R5_BOTH_ARMS_INCORRECT_BENCHMARK_INVALID",
    "R6_PRIMARY_NONINFERIORITY_RULES",
)

VALID_CORRECTNESS_SCORES = (0, 1)


@dataclass(frozen=True)
class ArmScorerResult:
    """One arm's post-termination evidence, as released by the frozen scorer.

    ``correctness_score`` is the frozen binary score.  ``None`` means the
    scorer produced no result for this arm and is never coerced to ``0`` --
    absence of evidence is not evidence of incorrectness.
    """

    arm_id: str
    receipt_sealed: bool
    scorer_result_present: bool
    correctness_score: int | None = None
    human_intervention_count: int | None = None
    #: Receipt-derived only (e.g. the frozen controller's rate-limit events).
    #: Capacity invalidation is never inferred from a correctness score.
    capacity_invalidation_events: tuple[str, ...] = ()
    #: Frozen intervention schema ambiguity_rule = FAIL_CLOSED.
    ambiguous_intervention_event: bool = False
    #: Hard gates that were measured and observed to fail for this arm.
    measured_hard_gate_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComparisonEvidence:
    """The complete evidence set the classifier is allowed to look at."""

    treatment: ArmScorerResult
    baseline: ArmScorerResult
    #: This amendment is effective only once canonically merged.
    comparator_validity_amendment_canonical: bool = True
    answer_key_firewall_passed: bool = True

    def arms(self) -> tuple[ArmScorerResult, ArmScorerResult]:
        return (self.treatment, self.baseline)


def _check_arm_identity(evidence: ComparisonEvidence) -> None:
    if evidence.treatment.arm_id != DSH_ARM:
        raise FailClosed(f"treatment arm identity is not {DSH_ARM}")
    if evidence.baseline.arm_id != NATIVE_ARM:
        raise FailClosed(f"baseline arm identity is not {NATIVE_ARM}")


def _is_exact_int(value: object) -> bool:
    """Reject ``bool`` and every other int-comparable stand-in.

    ``True == 1`` in Python, so a bare membership or ``isinstance`` test would
    let a boolean masquerade as a correctness score.  A score is admitted only
    when it is literally an ``int``.
    """
    return type(value) is int


def _scorer_evidence_is_well_formed(arm: ArmScorerResult) -> bool:
    """True only when this arm carries a complete, in-range scorer result."""
    return (
        arm.scorer_result_present
        and _is_exact_int(arm.correctness_score)
        and arm.correctness_score in VALID_CORRECTNESS_SCORES
        and _is_exact_int(arm.human_intervention_count)
        and arm.human_intervention_count >= 0
        and not arm.ambiguous_intervention_event
    )


def comparison_valid(evidence: ComparisonEvidence) -> bool:
    """The predeclared comparison-validity predicate.

    ``COMPARISON_VALID = BOTH_ARM_SCORER_RESULTS_PRESENT AND
    BOTH_ARM_RECEIPTS_SEALED AND NO_ENVIRONMENT_OR_PRODUCT_CAPACITY_INVALIDATION
    AND (TREATMENT_CORRECTNESS == 1 OR NATIVE_BASELINE_CORRECTNESS == 1)``

    The final clause is a disjunction on purpose.  Requiring the baseline to be
    correct would invalidate the scientifically interesting cell in which DSH
    succeeds and native does not.  The invariant is AT_LEAST_ONE_ARM_CORRECT,
    never BASELINE_MUST_WIN.
    """
    arms = evidence.arms()
    if not all(arm.receipt_sealed for arm in arms):
        return False
    if any(arm.capacity_invalidation_events for arm in arms):
        return False
    if not all(_scorer_evidence_is_well_formed(arm) for arm in arms):
        return False
    return any(arm.correctness_score == 1 for arm in arms)


def classify(evidence: ComparisonEvidence) -> str:
    """Classify one V1 episode under the frozen, predeclared precedence.

    Raises :class:`FailClosed` for every fail-closed condition; returns one of
    :data:`CLASSIFICATIONS` otherwise.  A ``0``/``0`` correctness pair can
    never return a PASS classification.
    """
    _check_arm_identity(evidence)
    arms = evidence.arms()

    # R1 -- authority, firewall, and receipt sealing.  These are prerequisites
    # for the scorer being released at all, so they precede every reading of a
    # score.  An unsealed arm is fail-closed, never "incorrect = 0".
    if not evidence.comparator_validity_amendment_canonical:
        raise FailClosed(
            "comparator-validity amendment is branch-local; it cannot self-authorize "
            "a repaired interpretation before canonical merge"
        )
    if not evidence.answer_key_firewall_passed:
        raise FailClosed("answer-key firewall was not proven for this episode")
    for arm in arms:
        if not arm.receipt_sealed:
            raise FailClosed(f"receipt for {arm.arm_id} is unsealed; classification fails closed")

    # R2 -- a measured hard-gate failure is a categorical disqualification and
    # keeps the frozen "any failed hard gate makes correctness fail" rule
    # verbatim.  It is deliberately above capacity and benchmark validity: an
    # observed violation is a defect, not a non-informative episode.
    for arm in arms:
        if arm.measured_hard_gate_failures:
            return CLASSIFICATION_FAIL

    # R3 -- capacity invalidation, derived only from receipts.  It outranks the
    # comparator entirely, so one-sided throttling can never become a
    # scientific result in either direction.  It is also above R4 because a
    # capacity-invalidated arm is the one case in which an absent scorer result
    # is contract-expected rather than a scorer error; ordering it below R4
    # would make the already-frozen capacity outcome unreachable.
    if any(arm.capacity_invalidation_events for arm in arms):
        return CLASSIFICATION_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY

    # R4 -- missing or malformed scorer evidence.  Absent, out-of-range, or
    # ambiguous evidence fails closed and is never read as a 0.
    for arm in arms:
        if not _scorer_evidence_is_well_formed(arm):
            raise FailClosed(
                f"scorer evidence for {arm.arm_id} is missing, out of range, or ambiguous; "
                "missing evidence fails closed and is never treated as incorrect"
            )

    treatment_correctness = evidence.treatment.correctness_score
    baseline_correctness = evidence.baseline.correctness_score
    treatment_intervention = evidence.treatment.human_intervention_count
    baseline_intervention = evidence.baseline.human_intervention_count

    # R5 -- the repair.  Both arms scored, both arms incorrect: the benchmark
    # produced no correct solution, so the comparison carries no information
    # about orchestration non-inferiority.  Not PASS, not FAIL.
    if treatment_correctness == 0 and baseline_correctness == 0:
        return CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT

    # R6 -- the comparison is scientifically valid; apply the existing frozen
    # primary rules unchanged.
    if treatment_correctness < baseline_correctness:
        return CLASSIFICATION_FAIL
    if treatment_intervention > baseline_intervention:
        return CLASSIFICATION_FAIL
    if treatment_correctness > baseline_correctness:
        return CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE
    if treatment_intervention < baseline_intervention:
        return CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE
    return CLASSIFICATION_PASS_NO_INCREMENTAL_VALUE


__all__ = [
    "AMENDMENT_ID",
    "ArmScorerResult",
    "CANONICAL_PR131_MERGE",
    "CLASSIFICATIONS",
    "CLASSIFICATION_FAIL",
    "CLASSIFICATION_INVALID_BENCHMARK_BOTH_ARMS_INCORRECT",
    "CLASSIFICATION_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY",
    "CLASSIFICATION_PASS_NO_INCREMENTAL_VALUE",
    "CLASSIFICATION_PASS_WITH_INCREMENTAL_VALUE",
    "ComparisonEvidence",
    "EXPERIMENT_ID",
    "FailClosed",
    "PASS_CLASSIFICATIONS",
    "PRECEDENCE",
    "classify",
    "comparison_valid",
]
