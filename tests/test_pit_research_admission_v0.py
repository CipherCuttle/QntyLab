"""PIT Research Admission Policy V0 -- frozen fixture matrix F1..F16.

Every value here is synthetic. No network, no filesystem, no clock, no real
lifecycle evidence. Contract:
``docs/forensics/PIT_RESEARCH_ADMISSION_V0_CONTRACT.md``.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import itertools
from pathlib import Path

import pytest

from qntylab.evidence_claim_split import (
    BoundaryProposition,
    DELIST,
    EvidenceRecord,
    IntervalEligibilityProposition,
    LAUNCH,
    PointObservationProposition,
)
from qntylab.market_observation import InstrumentIdentity
from qntylab import pit_research_admission as pit
from qntylab.pit_research_admission import (
    ADMIT,
    AdmissionRequest,
    InvalidPITQuery,
    REJECT,
    UNRESOLVED,
    decision_digest,
    evaluate,
)


# --- Synthetic identities ----------------------------------------------------

PERP = InstrumentIdentity(
    symbol="BTCUSDT",
    market="binance-usd-m",
    contract_type="perpetual",
    instrument_instance_id="binance|BTCUSDT|perpetual|usd-m|2024-01-01T00:00:00Z",
)

# Same ticker, later lifecycle episode: a different instrument instance.
PERP_RELISTED = InstrumentIdentity(
    symbol="BTCUSDT",
    market="binance-usd-m",
    contract_type="perpetual",
    instrument_instance_id="binance|BTCUSDT|perpetual|usd-m|2025-06-01T00:00:00Z",
)

SPOT = InstrumentIdentity(
    symbol="BTCUSDT",
    market="binance-spot",
    contract_type="spot",
    instrument_instance_id="binance|BTCUSDT|spot|2019-09-08T00:00:00Z",
)

GENERIC_BTC = InstrumentIdentity(
    symbol="BTC",
    market="generic-asset",
    contract_type="asset",
    instrument_instance_id="asset|BTC",
)

AS_OF = "2025-01-01T00:00:00Z"
QUERY_START = "2024-03-01T00:00:00Z"
QUERY_END = "2024-04-01T00:00:00Z"


def request(identity=PERP, start=QUERY_START, end=QUERY_END, as_of=AS_OF) -> AdmissionRequest:
    return AdmissionRequest(identity=identity, query_start=start, query_end=end, as_of=as_of)


def launch(identity=PERP, effective="2024-01-01T00:00:00Z", available="2024-01-01T00:00:00Z", key="launch"):
    return EvidenceRecord(
        proposition=BoundaryProposition(identity=identity, kind=LAUNCH, effective_time=effective),
        available_time=available,
        source_key=key,
    )


def delist(identity=PERP, effective="2024-09-01T00:00:00Z", available="2024-09-01T00:00:00Z", key="delist"):
    return EvidenceRecord(
        proposition=BoundaryProposition(identity=identity, kind=DELIST, effective_time=effective),
        available_time=available,
        source_key=key,
    )


def observation(identity=PERP, effective="2024-03-15T00:00:00Z", available="2024-03-15T00:00:00Z", key="obs"):
    return EvidenceRecord(
        proposition=PointObservationProposition(identity=identity, effective_time=effective),
        available_time=available,
        source_key=key,
    )


def interval(
    identity=PERP,
    start="2024-01-01T00:00:00Z",
    end="2024-09-01T00:00:00Z",
    available="2024-09-01T00:00:00Z",
    key="interval",
):
    return EvidenceRecord(
        proposition=IntervalEligibilityProposition(
            identity=identity, effective_start=start, effective_end=end
        ),
        available_time=available,
        source_key=key,
    )


# Launch before the query and delist after it: the frozen positive-coverage
# fixture used as the F1 baseline.
BRACKETING_EVIDENCE = (launch(), delist())


# --- F1: sufficient positive boundary evidence -> ADMIT ----------------------


def test_f1_bracketing_boundary_evidence_admits():
    decision = evaluate(request(), BRACKETING_EVIDENCE)
    assert decision.decision == ADMIT
    assert decision.reason_codes == (pit.BOUNDARY_WINDOW_COVERS_QUERY,)
    assert {entry.role for entry in decision.evidence_basis} == {pit.ADMIT_GROUND}
    assert sorted(
        key for entry in decision.evidence_basis for key in entry.supporting_source_keys
    ) == ["delist", "launch"]


def test_f1_interval_claim_covering_query_admits():
    decision = evaluate(request(), (interval(),))
    assert decision.decision == ADMIT
    assert decision.reason_codes == (pit.INTERVAL_CLAIM_COVERS_QUERY,)


def test_interval_claim_not_covering_query_does_not_admit():
    # Claim stops inside the query: no coverage, and no escalation to a wider
    # eligibility fact.
    narrow = interval(start="2024-03-01T00:00:00Z", end="2024-03-20T00:00:00Z")
    decision = evaluate(request(), (narrow,))
    assert decision.decision == UNRESOLVED
    assert pit.INSUFFICIENT_EVIDENCE in decision.reason_codes


def test_launch_without_delist_is_unresolved_not_admit():
    # Frozen V0 limitation: "no delist evidence exists" is absence of evidence
    # and must not close the right edge.
    decision = evaluate(request(), (launch(),))
    assert decision.decision == UNRESOLVED
    assert pit.INSUFFICIENT_EVIDENCE in decision.reason_codes
    assert decision.evidence_basis == ()


# --- F2: same effective evidence, available only after as_of -> UNRESOLVED ---


def test_f2_future_available_evidence_does_not_admit():
    future = (
        launch(available="2025-02-01T00:00:00Z"),
        delist(available="2025-02-01T00:00:00Z"),
    )
    decision = evaluate(request(), future)
    assert decision.decision == UNRESOLVED
    # Not merely "unresolved": the future evidence is invisible, so the answer
    # is indistinguishable from having no evidence at all.
    assert decision.reason_codes == evaluate(request(), ()).reason_codes
    assert decision_digest(decision) == decision_digest(evaluate(request(), ()))


# --- F3: no relevant evidence -> UNRESOLVED ----------------------------------


def test_f3_no_evidence_is_unresolved():
    decision = evaluate(request(), ())
    assert decision.decision == UNRESOLVED
    assert decision.reason_codes == (pit.INSUFFICIENT_EVIDENCE, pit.NO_EXACT_IDENTITY_EVIDENCE)
    assert decision.evidence_basis == ()


# --- F4: generic / wrong identity -> UNRESOLVED ------------------------------


@pytest.mark.parametrize("other", [GENERIC_BTC, SPOT, PERP_RELISTED])
def test_f4_foreign_identity_evidence_binds_nothing(other):
    evidence = (launch(identity=other), delist(identity=other))
    decision = evaluate(request(), evidence)
    assert decision.decision == UNRESOLVED
    assert pit.IDENTITY_MISMATCH in decision.reason_codes
    assert pit.NO_EXACT_IDENTITY_EVIDENCE in decision.reason_codes
    assert decision.evidence_basis == ()


def test_f4_generic_evidence_cannot_reject_either():
    # Wrong-identity exclusion evidence must not reject the exact instrument.
    decision = evaluate(request(), (delist(identity=GENERIC_BTC, effective="2024-01-15T00:00:00Z"),))
    assert decision.decision == UNRESOLVED


# --- F5: affirmative exclusion -> REJECT -------------------------------------


def test_f5_delist_before_query_start_rejects():
    decision = evaluate(request(), (launch(), delist(effective="2024-02-01T00:00:00Z")))
    assert decision.decision == REJECT
    assert decision.reason_codes == (pit.DELIST_AT_OR_BEFORE_QUERY_START,)
    assert {entry.role for entry in decision.evidence_basis} == {pit.REJECT_GROUND}


def test_f5_launch_after_query_end_rejects():
    decision = evaluate(request(), (launch(effective="2024-05-01T00:00:00Z"),))
    assert decision.decision == REJECT
    assert decision.reason_codes == (pit.LAUNCH_AT_OR_AFTER_QUERY_END,)


@pytest.mark.parametrize(
    "record,code",
    [
        (delist(effective="2024-03-15T00:00:00Z"), pit.DELIST_INSIDE_QUERY),
        (launch(effective="2024-03-15T00:00:00Z"), pit.LAUNCH_INSIDE_QUERY),
    ],
)
def test_f5_boundary_inside_query_rejects_whole_interval(record, code):
    # Whole-interval semantics: V0 never truncates or repairs a query.
    decision = evaluate(request(), (record,))
    assert decision.decision == REJECT
    assert code in decision.reason_codes


# --- F6: point observation inside a wider query -> UNRESOLVED ----------------


def test_f6_point_observation_does_not_prove_interval():
    decision = evaluate(request(), (observation(),))
    assert decision.decision == UNRESOLVED
    assert pit.POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL in decision.reason_codes
    assert decision.evidence_basis == ()


def test_f6_observations_bracketing_the_query_do_not_prove_it():
    # Not even observations on both sides bridge the interval.
    evidence = (
        observation(effective="2024-02-25T00:00:00Z", key="obs-before"),
        observation(effective="2024-04-05T00:00:00Z", key="obs-after"),
    )
    decision = evaluate(request(), evidence)
    assert decision.decision == UNRESOLVED
    assert pit.POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL not in decision.reason_codes


def test_f6_observation_never_rejects():
    decision = evaluate(request(), (observation(),) * 1)
    assert decision.decision != REJECT


# --- F7: UNKNOWN-producing evidence only -> UNRESOLVED, never REJECT ---------


def test_f7_unknown_evidence_never_aggregates_into_reject():
    # A pile of evidence that establishes nothing about this query: wrong
    # identity, wrong domain, and future-known variants of the real boundaries.
    evidence = tuple(
        itertools.chain(
            (launch(identity=other, key=f"foreign-launch-{i}") for i, other in enumerate((SPOT, GENERIC_BTC, PERP_RELISTED))),
            (delist(identity=other, key=f"foreign-delist-{i}") for i, other in enumerate((SPOT, GENERIC_BTC, PERP_RELISTED))),
            (observation(effective=f"2024-03-{day:02d}T00:00:00Z", key=f"obs-{day}") for day in range(2, 12)),
            (launch(available="2025-06-01T00:00:00Z", key="future-launch"),),
            (delist(effective="2024-02-01T00:00:00Z", available="2025-06-01T00:00:00Z", key="future-delist"),),
        )
    )
    decision = evaluate(request(), evidence)
    assert decision.decision == UNRESOLVED
    assert decision.decision != REJECT
    assert pit.INSUFFICIENT_EVIDENCE in decision.reason_codes
    assert decision.evidence_basis == ()


# --- F8: query_end > as_of -> invalid query, not REJECT ----------------------


def test_f8_non_pit_query_raises_and_is_not_a_decision():
    with pytest.raises(InvalidPITQuery) as excinfo:
        request(end="2025-02-01T00:00:00Z")
    assert "non-PIT query" in str(excinfo.value)


def test_f8_invalid_query_type_is_not_reject():
    assert issubclass(InvalidPITQuery, ValueError)
    # An invalid query yields no decision object at all, so it cannot be read
    # as a universe rejection.
    assert REJECT not in {InvalidPITQuery.__name__}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start": "2024-04-01T00:00:00Z", "end": "2024-04-01T00:00:00Z"},  # empty
        {"start": "2024-05-01T00:00:00Z", "end": "2024-04-01T00:00:00Z"},  # inverted
        {"start": "2024-03-01"},  # malformed shape
        {"as_of": "2025-02-31T00:00:00Z"},  # not a real instant
    ],
)
def test_f8_malformed_requests_raise(kwargs):
    with pytest.raises(InvalidPITQuery):
        request(**kwargs)


def test_f8_malformed_identity_raises():
    with pytest.raises(InvalidPITQuery):
        request(identity=InstrumentIdentity("BTCUSDT", "binance-usd-m", "perpetual", " "))


def test_f8_end_equal_to_as_of_is_a_valid_pit_query():
    decision = evaluate(request(end=AS_OF), BRACKETING_EVIDENCE)
    assert decision.decision in {ADMIT, REJECT, UNRESOLVED}


# --- F9: conflicting established evidence -> UNRESOLVED ----------------------


def test_f9_conflicting_evidence_fails_closed():
    # An eligibility claim covering the query AND a delist inside it.
    evidence = (interval(), delist(effective="2024-03-15T00:00:00Z", key="conflicting-delist"))
    decision = evaluate(request(), evidence)
    assert decision.decision == UNRESOLVED
    assert pit.CONFLICTING_EVIDENCE in decision.reason_codes
    assert pit.INTERVAL_CLAIM_COVERS_QUERY in decision.reason_codes
    assert pit.DELIST_INSIDE_QUERY in decision.reason_codes


def test_f9_conflict_does_not_resolve_by_recency_or_order():
    older = interval(key="older-claim")
    newer = delist(effective="2024-03-15T00:00:00Z", available="2024-12-31T00:00:00Z", key="newer-delist")
    forward = evaluate(request(), (older, newer))
    backward = evaluate(request(), (newer, older))
    assert forward.decision == backward.decision == UNRESOLVED
    assert decision_digest(forward) == decision_digest(backward)


def test_f9_two_launches_conflict():
    evidence = (launch(), launch(effective="2024-03-15T00:00:00Z", key="second-launch"), delist())
    decision = evaluate(request(), evidence)
    assert decision.decision == UNRESOLVED
    assert pit.CONFLICTING_EVIDENCE in decision.reason_codes


# --- F10: input order independence -------------------------------------------


def test_f10_all_permutations_are_identical():
    evidence = (launch(), delist(), observation(), interval(identity=SPOT, key="foreign-interval"))
    reference = evaluate(request(), evidence)
    reference_digest = decision_digest(reference)
    for permutation in itertools.permutations(evidence):
        decision = evaluate(request(), permutation)
        assert decision.decision == reference.decision
        assert decision.reason_codes == reference.reason_codes
        assert decision.evidence_basis == reference.evidence_basis
        assert decision_digest(decision) == reference_digest


def test_f10_duplicate_evidence_does_not_change_the_decision():
    once = evaluate(request(), BRACKETING_EVIDENCE)
    twice = evaluate(request(), BRACKETING_EVIDENCE + BRACKETING_EVIDENCE)
    assert decision_digest(once) == decision_digest(twice)


# --- F11: metamorphic PIT invariant ------------------------------------------


@pytest.mark.parametrize(
    "base",
    [
        (),
        BRACKETING_EVIDENCE,
        (observation(),),
        (interval(),),
        (delist(effective="2024-02-01T00:00:00Z"),),
    ],
)
def test_f11_future_evidence_cannot_change_a_historical_decision(base):
    before = evaluate(request(), base)
    future_growth = (
        # Every shape of future-known evidence, including ones that would flip
        # the decision if they leaked backward.
        launch(effective="2023-01-01T00:00:00Z", available="2025-03-01T00:00:00Z", key="f-launch"),
        delist(effective="2024-02-01T00:00:00Z", available="2025-03-01T00:00:00Z", key="f-delist"),
        delist(effective="2026-01-01T00:00:00Z", available="2025-03-01T00:00:00Z", key="f-delist-late"),
        interval(available="2025-03-01T00:00:00Z", key="f-interval"),
        observation(available="2025-03-01T00:00:00Z", key="f-obs"),
        launch(identity=PERP_RELISTED, available="2025-03-01T00:00:00Z", key="f-relist"),
    )
    after = evaluate(request(), base + future_growth)
    assert after.decision == before.decision
    assert after.reason_codes == before.reason_codes
    assert after.evidence_basis == before.evidence_basis
    assert decision_digest(after) == decision_digest(before)


# --- F12: outcome blindness ---------------------------------------------------


def test_f12_future_outcome_and_data_usability_cannot_change_admission():
    # Two worlds identical in lifecycle evidence up to the query, differing only
    # in what happens (or is computable) after query_end: dense post-query
    # observations and an eventual delist in one, nothing in the other.
    survives = BRACKETING_EVIDENCE + tuple(
        observation(effective=f"2024-1{month}-01T00:00:00Z", available=f"2024-1{month}-01T00:00:00Z", key=f"post-obs-{month}")
        for month in range(0, 3)
    )
    dies = BRACKETING_EVIDENCE
    a = evaluate(request(), survives)
    b = evaluate(request(), dies)
    assert a.decision == b.decision == ADMIT
    assert a.reason_codes == b.reason_codes
    assert decision_digest(a) == decision_digest(b)


def test_f12_evaluator_has_no_outcome_channel():
    parameters = list(inspect.signature(evaluate).parameters)
    assert parameters == ["request", "evidence"]
    fields = {f for f in AdmissionRequest.__dataclass_fields__}
    assert fields == {"identity", "query_start", "query_end", "as_of"}


# --- F13: half-open boundary behaviour ---------------------------------------


def test_f13_launch_exactly_at_query_start_opens_the_window():
    decision = evaluate(request(), (launch(effective=QUERY_START), delist()))
    assert decision.decision == ADMIT


def test_f13_launch_exactly_at_query_end_rejects():
    decision = evaluate(request(), (launch(effective=QUERY_END),))
    assert decision.decision == REJECT
    assert decision.reason_codes == (pit.LAUNCH_AT_OR_AFTER_QUERY_END,)


def test_f13_delist_exactly_at_query_start_rejects():
    decision = evaluate(request(), (launch(), delist(effective=QUERY_START)))
    assert decision.decision == REJECT
    assert decision.reason_codes == (pit.DELIST_AT_OR_BEFORE_QUERY_START,)


def test_f13_delist_exactly_at_query_end_closes_the_window():
    decision = evaluate(request(), (launch(), delist(effective=QUERY_END)))
    assert decision.decision == ADMIT
    assert decision.reason_codes == (pit.BOUNDARY_WINDOW_COVERS_QUERY,)


def test_f13_observation_at_query_end_is_outside_the_half_open_query():
    decision = evaluate(request(), (observation(effective=QUERY_END),))
    assert pit.POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL not in decision.reason_codes


def test_f13_observation_at_query_start_is_inside_the_half_open_query():
    decision = evaluate(request(), (observation(effective=QUERY_START),))
    assert pit.POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL in decision.reason_codes


# --- F14 / F15: availability boundary ----------------------------------------


def test_f14_available_time_equal_to_as_of_is_admissible():
    evidence = (launch(available=AS_OF), delist(available=AS_OF))
    assert evaluate(request(), evidence).decision == ADMIT


def test_f15_available_time_one_second_after_as_of_is_excluded():
    just_after = "2025-01-01T00:00:01Z"
    evidence = (launch(available=just_after), delist(available=just_after))
    decision = evaluate(request(), evidence)
    assert decision.decision == UNRESOLVED
    assert decision.reason_codes == (pit.INSUFFICIENT_EVIDENCE, pit.NO_EXACT_IDENTITY_EVIDENCE)


def test_f15_one_edge_available_after_as_of_does_not_half_admit():
    evidence = (launch(available=AS_OF), delist(available="2025-01-01T00:00:01Z"))
    decision = evaluate(request(), evidence)
    assert decision.decision == UNRESOLVED
    assert decision.evidence_basis == ()


# --- F16: delist / relist episodes -------------------------------------------


EPISODE_EVIDENCE = (
    launch(identity=PERP, effective="2024-01-01T00:00:00Z", key="a-launch"),
    delist(identity=PERP, effective="2024-06-01T00:00:00Z", key="a-delist"),
    launch(identity=PERP_RELISTED, effective="2024-08-01T00:00:00Z", key="b-launch"),
    delist(identity=PERP_RELISTED, effective="2024-11-01T00:00:00Z", key="b-delist"),
)


def test_f16_each_episode_admits_only_its_own_window():
    inside_a = evaluate(request(identity=PERP), EPISODE_EVIDENCE)
    assert inside_a.decision == ADMIT
    inside_b = evaluate(
        request(identity=PERP_RELISTED, start="2024-09-01T00:00:00Z", end="2024-10-01T00:00:00Z"),
        EPISODE_EVIDENCE,
    )
    assert inside_b.decision == ADMIT


def test_f16_relist_does_not_repair_the_earlier_gap():
    gap = request(identity=PERP, start="2024-06-15T00:00:00Z", end="2024-07-15T00:00:00Z")
    decision = evaluate(gap, EPISODE_EVIDENCE)
    assert decision.decision == REJECT
    assert pit.DELIST_AT_OR_BEFORE_QUERY_START in decision.reason_codes
    assert pit.BOUNDARY_WINDOW_COVERS_QUERY not in decision.reason_codes


def test_f16_later_episode_cannot_admit_earlier_interval():
    early = request(identity=PERP_RELISTED, start="2024-03-01T00:00:00Z", end="2024-04-01T00:00:00Z")
    decision = evaluate(early, EPISODE_EVIDENCE)
    assert decision.decision == REJECT
    assert pit.LAUNCH_AT_OR_AFTER_QUERY_END in decision.reason_codes


def test_f16_query_spanning_both_episodes_never_admits():
    for identity in (PERP, PERP_RELISTED):
        spanning = request(identity=identity, start="2024-03-01T00:00:00Z", end="2024-10-01T00:00:00Z")
        assert evaluate(spanning, EPISODE_EVIDENCE).decision != ADMIT


# --- Determinism, policy identity, closed vocabulary -------------------------


def test_policy_identity_is_carried_and_stable():
    decision = evaluate(request(), BRACKETING_EVIDENCE)
    assert decision.policy_id == "qntylab.pit_research_admission"
    assert decision.policy_version == "v0"
    assert len(decision.policy_contract_digest) == 64
    assert decision.policy_contract_digest == pit.POLICY_CONTRACT_DIGEST


def test_digest_is_sensitive_to_every_decision_component():
    base = evaluate(request(), BRACKETING_EVIDENCE)
    variants = [
        evaluate(request(identity=PERP_RELISTED), BRACKETING_EVIDENCE),
        evaluate(request(start="2024-03-02T00:00:00Z"), BRACKETING_EVIDENCE),
        evaluate(request(end="2024-03-20T00:00:00Z"), BRACKETING_EVIDENCE),
        evaluate(request(as_of="2024-12-01T00:00:00Z"), BRACKETING_EVIDENCE),
        evaluate(request(), (interval(),)),
        evaluate(request(), ()),
    ]
    digests = {decision_digest(v) for v in variants} | {decision_digest(base)}
    assert len(digests) == len(variants) + 1


def test_digest_is_repeatable():
    a = decision_digest(evaluate(request(), BRACKETING_EVIDENCE))
    b = decision_digest(evaluate(request(), BRACKETING_EVIDENCE))
    assert a == b and len(a) == 64


def test_reason_codes_are_closed_sorted_and_deduplicated():
    for evidence in (
        (),
        BRACKETING_EVIDENCE,
        (observation(), launch(identity=SPOT)),
        (interval(), delist(effective="2024-03-15T00:00:00Z")),
        EPISODE_EVIDENCE,
    ):
        decision = evaluate(request(), evidence)
        codes = decision.reason_codes
        assert set(codes) <= pit.REASON_CODES
        assert list(codes) == sorted(set(codes))


def test_decision_vocabulary_is_exactly_three_members():
    assert pit.DECISIONS == {"ADMIT", "REJECT", "UNRESOLVED"}
    assert "ELIGIBLE" not in pit.DECISIONS and "INELIGIBLE" not in pit.DECISIONS


def test_no_future_known_evidence_reason_code_exists():
    # Deliberate: annotating excluded future evidence would make future
    # knowledge observable in a historical decision.
    assert not any("FUTURE" in code for code in pit.REASON_CODES)


def test_evidence_records_must_be_exact_type():
    class Widened(EvidenceRecord):
        pass

    widened = Widened(
        proposition=BoundaryProposition(identity=PERP, kind=LAUNCH, effective_time="2024-01-01T00:00:00Z"),
        available_time="2024-01-01T00:00:00Z",
        source_key="widened",
    )
    with pytest.raises(ValueError):
        evaluate(request(), (widened,))


def test_widened_evidence_basis_entry_cannot_collide_in_the_digest():
    # Regression for hostile finding H-1: a subclass carrying extra
    # distinguishing fields must not serialise as the base entry.
    @dataclasses.dataclass(frozen=True)
    class WidenedEntry(pit.EvidenceBasisEntry):
        distinguishing: str = "x"

    base = evaluate(request(), BRACKETING_EVIDENCE)
    entry = base.evidence_basis[0]
    for extra in ("alpha", "beta"):
        widened = WidenedEntry(entry.role, entry.proposition, entry.supporting_source_keys, extra)
        decision = pit.AdmissionDecision(
            request=base.request,
            decision=base.decision,
            reason_codes=base.reason_codes,
            evidence_basis=(widened,),
            policy_id=base.policy_id,
            policy_version=base.policy_version,
            policy_contract_digest=base.policy_contract_digest,
        )
        with pytest.raises(ValueError):
            decision_digest(decision)


def test_widened_decision_type_is_refused():
    class WidenedDecision(pit.AdmissionDecision):
        pass

    base = evaluate(request(), BRACKETING_EVIDENCE)
    widened = WidenedDecision(
        base.request, base.decision, base.reason_codes, base.evidence_basis,
        base.policy_id, base.policy_version, base.policy_contract_digest,
    )
    with pytest.raises(ValueError):
        decision_digest(widened)


def test_forged_basis_role_is_refused():
    base = evaluate(request(), BRACKETING_EVIDENCE)
    entry = base.evidence_basis[0]
    forged = pit.EvidenceBasisEntry("ADMIT_GROUND_TOTALLY", entry.proposition, entry.supporting_source_keys)
    decision = pit.AdmissionDecision(
        base.request, base.decision, base.reason_codes, (forged,),
        base.policy_id, base.policy_version, base.policy_contract_digest,
    )
    with pytest.raises(ValueError):
        decision_digest(decision)


def test_widened_request_type_is_refused():
    class WidenedRequest(AdmissionRequest):
        pass

    with pytest.raises(InvalidPITQuery):
        evaluate(WidenedRequest(PERP, QUERY_START, QUERY_END, AS_OF), ())


# --- Structural guarantees ----------------------------------------------------

MODULE_PATH = Path(pit.__file__)
MODULE_AST = ast.parse(MODULE_PATH.read_text())


def _imported_modules() -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(MODULE_AST):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def test_no_network_filesystem_clock_or_qnty_imports():
    forbidden = {
        "os", "sys", "pathlib", "glob", "shutil", "socket", "urllib", "urllib.request",
        "requests", "httpx", "http", "http.client", "subprocess", "sqlite3", "random",
        "time", "datetime", "qnty", "qntypolicygate",
    }
    imported = _imported_modules()
    assert not {m for m in imported if m.split(".")[0].lower() in forbidden}, imported


def test_only_frozen_qntylab_surfaces_are_imported():
    qntylab_imports = {m for m in _imported_modules() if m.startswith("qntylab")}
    assert qntylab_imports == {"qntylab.evidence_claim_split", "qntylab.market_observation"}


def test_policy_never_manufactures_an_evidence_proposition():
    # The escalation this phase must not commit: turning a policy decision into
    # a stronger Evidence Claim Split proposition and feeding it back.
    manufactured = {
        "BoundaryProposition",
        "PointObservationProposition",
        "IntervalEligibilityProposition",
        "EvidenceRecord",
        "Assessment",
    }
    called = {
        node.func.id
        for node in ast.walk(MODULE_AST)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not (called & manufactured)


def test_predecessor_module_is_unmodified_by_this_phase():
    import qntylab.evidence_claim_split as ecs

    assert ecs.EPISTEMIC_STATUSES == {"ESTABLISHED", "UNKNOWN"}
    assert ecs.BOUNDARY_KINDS == {"LAUNCH", "DELIST"}
    # No negative epistemic status was introduced anywhere for this phase.
    assert not any(
        status in ecs.EPISTEMIC_STATUSES for status in ("FALSE", "REFUTED", "INELIGIBLE", "REJECT")
    )
