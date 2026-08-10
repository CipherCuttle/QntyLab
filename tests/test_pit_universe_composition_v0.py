"""PIT Universe Composition Fixture V0 -- frozen fixture matrix U1..U20.

Every value here is synthetic. No network, no filesystem, no clock, no real
roster, no real lifecycle evidence. Contract:
``docs/forensics/PIT_UNIVERSE_COMPOSITION_V0_CONTRACT.md``.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import itertools
import random
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
from qntylab import pit_universe_composition as puc
from qntylab.pit_universe_composition import (
    ARTIFICIAL_FIXTURE,
    CLOSED_WORLD_BY_CONSTRUCTION,
    CandidateRosterV0,
    DuplicateCandidateIdentity,
    EvidenceSnapshotV0,
    InvalidCandidateRoster,
    InvalidEvidenceSnapshot,
    InvalidUniverseArtifact,
    InvalidUniverseBuild,
    InvalidUniverseQuery,
    PolicyIdentityMismatch,
    UniverseQueryV0,
    artifact_digest,
    artifact_payload,
    compose_pit_universe,
    eligible_evidence_digest,
    roster_digest,
)


# --- Synthetic world ---------------------------------------------------------

AS_OF = "2025-01-01T00:00:00Z"
START = "2024-03-01T00:00:00Z"
END = "2024-04-01T00:00:00Z"

QUERY = UniverseQueryV0(start=START, end=END, as_of=AS_OF)

BEFORE = "2024-01-01T00:00:00Z"
INSIDE = "2024-03-15T00:00:00Z"
AFTER = "2024-06-01T00:00:00Z"
KNOWN = "2024-07-01T00:00:00Z"          # available_time <= as_of
FUTURE_KNOWN = "2025-06-01T00:00:00Z"   # available_time  > as_of


def perp(symbol: str, instance: str = "2024-01-01T00:00:00Z") -> InstrumentIdentity:
    return InstrumentIdentity(
        symbol=symbol,
        market="binance-usd-m",
        contract_type="perpetual",
        instrument_instance_id=f"binance|{symbol}|perpetual|usd-m|{instance}",
    )


def spot(symbol: str) -> InstrumentIdentity:
    return InstrumentIdentity(
        symbol=symbol,
        market="binance-spot",
        contract_type="spot",
        instrument_instance_id=f"binance|{symbol}|spot|2019-09-08T00:00:00Z",
    )


# 12 heterogeneous candidates, chosen to exercise semantics -- never to hit a
# resolution-rate target, of which there is none.
C_ADMIT_INTERVAL = perp("AAAUSDT")        # explicit covering interval claim
C_ADMIT_BOUNDARY = perp("BBBUSDT")        # launch <= start and delist >= end
C_REJECT_DELIST = perp("CCCUSDT")         # delist <= start
C_REJECT_LAUNCH_INSIDE = perp("DDDUSDT")  # launch strictly inside the query
C_NO_EVIDENCE = perp("EEEUSDT")           # nothing at all
C_IDENTITY_MISMATCH = perp("FFFUSDT")     # only spot evidence for the ticker
C_OBSERVATION_ONLY = perp("GGGUSDT")      # point observation inside the query
C_CONFLICT = perp("HHHUSDT")              # covering interval claim + delist inside
C_FUTURE_KNOWN = perp("IIIUSDT")          # covering evidence, knowable only later
C_LAUNCH_ONLY = perp("JJJUSDT")           # launch, no delist -> right edge open
C_EPISODE_1 = perp("KKKUSDT", "2023-01-01T00:00:00Z")   # first listing episode
C_EPISODE_2 = perp("KKKUSDT", "2024-09-01T00:00:00Z")   # relisted: other instance

CANDIDATES = (
    C_ADMIT_INTERVAL,
    C_ADMIT_BOUNDARY,
    C_REJECT_DELIST,
    C_REJECT_LAUNCH_INSIDE,
    C_NO_EVIDENCE,
    C_IDENTITY_MISMATCH,
    C_OBSERVATION_ONLY,
    C_CONFLICT,
    C_FUTURE_KNOWN,
    C_LAUNCH_ONLY,
    C_EPISODE_1,
    C_EPISODE_2,
)


def launch(identity, effective=BEFORE, available=KNOWN, key=None):
    return EvidenceRecord(
        proposition=BoundaryProposition(identity=identity, kind=LAUNCH, effective_time=effective),
        available_time=available,
        source_key=key or f"launch|{identity.symbol}|{effective}",
    )


def delist(identity, effective=AFTER, available=KNOWN, key=None):
    return EvidenceRecord(
        proposition=BoundaryProposition(identity=identity, kind=DELIST, effective_time=effective),
        available_time=available,
        source_key=key or f"delist|{identity.symbol}|{effective}",
    )


def observation(identity, effective=INSIDE, available=KNOWN, key=None):
    return EvidenceRecord(
        proposition=PointObservationProposition(identity=identity, effective_time=effective),
        available_time=available,
        source_key=key or f"obs|{identity.symbol}|{effective}",
    )


def interval(identity, start=BEFORE, end=AFTER, available=KNOWN, key=None):
    return EvidenceRecord(
        proposition=IntervalEligibilityProposition(
            identity=identity, effective_start=start, effective_end=end
        ),
        available_time=available,
        source_key=key or f"interval|{identity.symbol}|{start}|{end}",
    )


BASE_RECORDS = (
    interval(C_ADMIT_INTERVAL),
    launch(C_ADMIT_BOUNDARY),
    delist(C_ADMIT_BOUNDARY),
    delist(C_REJECT_DELIST, effective="2024-02-01T00:00:00Z"),
    launch(C_REJECT_LAUNCH_INSIDE, effective=INSIDE),
    # C_NO_EVIDENCE: deliberately absent.
    launch(spot("FFFUSDT")),
    delist(spot("FFFUSDT")),
    observation(C_OBSERVATION_ONLY),
    interval(C_CONFLICT),
    delist(C_CONFLICT, effective=INSIDE, key="delist|HHHUSDT|inside"),
    launch(C_FUTURE_KNOWN, available=FUTURE_KNOWN),
    delist(C_FUTURE_KNOWN, available=FUTURE_KNOWN),
    launch(C_LAUNCH_ONLY),
    launch(C_EPISODE_1, effective="2023-02-01T00:00:00Z"),
    delist(C_EPISODE_1, effective=AFTER),
    launch(C_EPISODE_2, effective="2024-09-01T00:00:00Z"),
)


def roster(candidates=CANDIDATES, roster_id="pit-universe-fixture-v0", scope="artificial-closed-world"):
    return CandidateRosterV0(
        roster_id=roster_id,
        roster_version="v0",
        scope=scope,
        source_kind=ARTIFICIAL_FIXTURE,
        completeness_claim=CLOSED_WORLD_BY_CONSTRUCTION,
        candidates=tuple(candidates),
    )


def snapshot(records=BASE_RECORDS, snapshot_id="pit-universe-evidence-v0", as_of=AS_OF):
    return EvidenceSnapshotV0(
        snapshot_id=snapshot_id,
        snapshot_version="v0",
        as_of=as_of,
        records=tuple(records),
    )


def build(**kwargs):
    kwargs.setdefault("roster", roster())
    kwargs.setdefault("evidence_snapshot", snapshot())
    kwargs.setdefault("query", QUERY)
    return compose_pit_universe(**kwargs)


def record_for(artifact, identity):
    matches = [r for r in artifact.candidate_records if r.identity == identity]
    assert len(matches) == 1, f"expected exactly one record for {identity}"
    return matches[0]


def decision_of(artifact, identity) -> str:
    return record_for(artifact, identity).admission_decision.decision


def record_payload_for(artifact, identity) -> dict:
    return puc.candidate_record_payload(record_for(artifact, identity))


# --- Baseline semantics ------------------------------------------------------


def test_expected_decision_per_candidate():
    """The fixture really does exercise every listed semantic case."""
    artifact = build()
    assert decision_of(artifact, C_ADMIT_INTERVAL) == pit.ADMIT
    assert decision_of(artifact, C_ADMIT_BOUNDARY) == pit.ADMIT
    assert decision_of(artifact, C_REJECT_DELIST) == pit.REJECT
    assert decision_of(artifact, C_REJECT_LAUNCH_INSIDE) == pit.REJECT
    assert decision_of(artifact, C_NO_EVIDENCE) == pit.UNRESOLVED
    assert decision_of(artifact, C_IDENTITY_MISMATCH) == pit.UNRESOLVED
    assert decision_of(artifact, C_OBSERVATION_ONLY) == pit.UNRESOLVED
    assert decision_of(artifact, C_CONFLICT) == pit.UNRESOLVED
    assert decision_of(artifact, C_FUTURE_KNOWN) == pit.UNRESOLVED
    assert decision_of(artifact, C_LAUNCH_ONLY) == pit.UNRESOLVED
    assert decision_of(artifact, C_EPISODE_1) == pit.ADMIT
    assert decision_of(artifact, C_EPISODE_2) == pit.REJECT


def test_expected_reason_codes_per_case():
    artifact = build()
    assert pit.INTERVAL_CLAIM_COVERS_QUERY in record_for(artifact, C_ADMIT_INTERVAL).admission_decision.reason_codes
    assert pit.BOUNDARY_WINDOW_COVERS_QUERY in record_for(artifact, C_ADMIT_BOUNDARY).admission_decision.reason_codes
    assert pit.CONFLICTING_EVIDENCE in record_for(artifact, C_CONFLICT).admission_decision.reason_codes
    assert pit.POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL in record_for(
        artifact, C_OBSERVATION_ONLY
    ).admission_decision.reason_codes
    assert pit.NO_EXACT_IDENTITY_EVIDENCE in record_for(artifact, C_NO_EVIDENCE).admission_decision.reason_codes
    assert pit.IDENTITY_MISMATCH in record_for(artifact, C_IDENTITY_MISMATCH).admission_decision.reason_codes
    # No reason code anywhere acknowledges that future-known evidence existed.
    for record in artifact.candidate_records:
        for code in record.admission_decision.reason_codes:
            assert "FUTURE" not in code


def test_relist_episode_does_not_repair_the_other_episode():
    artifact = build()
    # Same ticker, two instances: each episode is judged on its own evidence.
    assert decision_of(artifact, C_EPISODE_1) == pit.ADMIT
    assert decision_of(artifact, C_EPISODE_2) == pit.REJECT
    assert C_EPISODE_1 in artifact.admitted
    assert C_EPISODE_2 in artifact.rejected


# --- U1: exact partition -----------------------------------------------------


def test_u1_every_candidate_appears_exactly_once():
    artifact = build()
    admitted, rejected, unresolved = set(artifact.admitted), set(artifact.rejected), set(artifact.unresolved)
    assert admitted | rejected | unresolved == set(CANDIDATES)
    assert admitted & rejected == set()
    assert admitted & unresolved == set()
    assert rejected & unresolved == set()
    assert len(artifact.admitted) + len(artifact.rejected) + len(artifact.unresolved) == len(CANDIDATES)
    assert len(artifact.candidate_records) == len(CANDIDATES)
    assert {r.identity for r in artifact.candidate_records} == set(CANDIDATES)
    assert artifact.telemetry.roster_partition_complete is True


def test_u1_partition_membership_matches_recorded_decision():
    artifact = build()
    for record in artifact.candidate_records:
        outcome = record.admission_decision.decision
        target = {
            pit.ADMIT: artifact.admitted,
            pit.REJECT: artifact.rejected,
            pit.UNRESOLVED: artifact.unresolved,
        }[outcome]
        assert record.identity in target


def test_u1_holds_over_random_candidate_subsets():
    rng = random.Random(0)  # deterministic; no reliance on process randomness
    for _ in range(40):
        size = rng.randint(1, len(CANDIDATES))
        subset = rng.sample(list(CANDIDATES), size)
        artifact = build(roster=roster(candidates=subset))
        union = set(artifact.admitted) | set(artifact.rejected) | set(artifact.unresolved)
        assert union == set(subset)
        assert len(artifact.candidate_records) == len(subset)


# --- U2: candidate permutation invariance ------------------------------------


def test_u2_candidate_permutation_produces_byte_identical_artifact():
    baseline = build()
    baseline_digest = artifact_digest(baseline)
    rng = random.Random(1)
    for _ in range(25):
        shuffled = list(CANDIDATES)
        rng.shuffle(shuffled)
        artifact = build(roster=roster(candidates=shuffled))
        assert artifact_payload(artifact) == artifact_payload(baseline)
        assert artifact_digest(artifact) == baseline_digest
        assert artifact.admitted == baseline.admitted
        assert artifact.rejected == baseline.rejected
        assert artifact.unresolved == baseline.unresolved
        assert artifact.candidate_records == baseline.candidate_records


def test_u2_roster_digest_is_order_insensitive():
    rng = random.Random(2)
    base = roster_digest(roster())
    for _ in range(20):
        shuffled = list(CANDIDATES)
        rng.shuffle(shuffled)
        assert roster_digest(roster(candidates=shuffled)) == base


def test_u2_exhaustive_permutations_of_a_small_roster():
    small = [C_ADMIT_BOUNDARY, C_REJECT_DELIST, C_NO_EVIDENCE, C_CONFLICT]
    digests = {
        artifact_digest(build(roster=roster(candidates=list(order))))
        for order in itertools.permutations(small)
    }
    assert len(digests) == 1


# --- U3: evidence order invariance -------------------------------------------


def test_u3_evidence_permutation_produces_byte_identical_artifact():
    baseline = build()
    baseline_digest = artifact_digest(baseline)
    rng = random.Random(3)
    for _ in range(25):
        shuffled = list(BASE_RECORDS)
        rng.shuffle(shuffled)
        artifact = build(evidence_snapshot=snapshot(records=shuffled))
        assert artifact_payload(artifact) == artifact_payload(baseline)
        assert artifact_digest(artifact) == baseline_digest


def test_u3_eligible_evidence_digest_is_order_insensitive():
    rng = random.Random(4)
    base = eligible_evidence_digest(snapshot())
    for _ in range(20):
        shuffled = list(BASE_RECORDS)
        rng.shuffle(shuffled)
        assert eligible_evidence_digest(snapshot(records=shuffled)) == base


def test_u3_duplicated_identical_evidence_records_change_nothing():
    baseline = build()
    duplicated = list(BASE_RECORDS) + list(BASE_RECORDS)
    artifact = build(evidence_snapshot=snapshot(records=duplicated))
    assert artifact_digest(artifact) == artifact_digest(baseline)
    assert puc.eligible_records(snapshot(records=duplicated)) == puc.eligible_records(snapshot())


def test_u3_distinct_corroborating_sources_are_all_kept():
    """Dedup collapses byte-identical records only, never distinct evidence."""
    corroborated = list(BASE_RECORDS) + [
        launch(C_ADMIT_BOUNDARY, key="second-source|launch|BBB"),
        delist(C_ADMIT_BOUNDARY, key="second-source|delist|BBB"),
    ]
    artifact = build(evidence_snapshot=snapshot(records=corroborated))
    assert len(puc.eligible_records(snapshot(records=corroborated))) == len(
        puc.eligible_records(snapshot())
    ) + 2
    keys = {
        k
        for entry in record_for(artifact, C_ADMIT_BOUNDARY).admission_decision.evidence_basis
        for k in entry.supporting_source_keys
    }
    assert "second-source|launch|BBB" in keys
    # A genuinely richer evidence basis is a different artifact.
    assert artifact_digest(artifact) != artifact_digest(build())


# --- U4: duplicate candidate identity ----------------------------------------


def test_u4_duplicate_exact_identity_fails_closed():
    with pytest.raises(DuplicateCandidateIdentity):
        roster(candidates=list(CANDIDATES) + [C_ADMIT_BOUNDARY])


def test_u4_duplicate_is_not_silently_deduplicated():
    duplicated = [C_ADMIT_BOUNDARY, C_ADMIT_BOUNDARY]
    with pytest.raises(DuplicateCandidateIdentity):
        roster(candidates=duplicated)
    # And no artifact of any kind can be reached from a duplicated roster.
    with pytest.raises(DuplicateCandidateIdentity):
        build(roster=roster(candidates=duplicated))


def test_u4_equal_valued_distinct_identity_objects_are_still_duplicates():
    twin = InstrumentIdentity(
        symbol=C_ADMIT_BOUNDARY.symbol,
        market=C_ADMIT_BOUNDARY.market,
        contract_type=C_ADMIT_BOUNDARY.contract_type,
        instrument_instance_id=C_ADMIT_BOUNDARY.instrument_instance_id,
    )
    assert twin is not C_ADMIT_BOUNDARY
    with pytest.raises(DuplicateCandidateIdentity):
        roster(candidates=[C_ADMIT_BOUNDARY, twin])


def test_u4_different_instance_of_same_ticker_is_not_a_duplicate():
    artifact = build(roster=roster(candidates=[C_EPISODE_1, C_EPISODE_2]))
    assert len(artifact.candidate_records) == 2


# --- U5 / U6 / U11: candidate independence -----------------------------------

Z = perp("ZZZUSDT")
Z_RECORDS = (launch(Z), delist(Z))


def _per_candidate_payloads(artifact, identities):
    return {puc._identity_key(i): record_payload_for(artifact, i) for i in identities}


def test_u5_adding_unrelated_candidate_to_roster_changes_nothing_else():
    baseline = build()
    extended = build(roster=roster(candidates=list(CANDIDATES) + [Z]))
    assert _per_candidate_payloads(extended, CANDIDATES) == _per_candidate_payloads(baseline, CANDIDATES)


def test_u5_adding_unrelated_candidate_with_its_own_evidence_changes_nothing_else():
    baseline = build()
    extended = build(
        roster=roster(candidates=list(CANDIDATES) + [Z]),
        evidence_snapshot=snapshot(records=list(BASE_RECORDS) + list(Z_RECORDS)),
    )
    assert _per_candidate_payloads(extended, CANDIDATES) == _per_candidate_payloads(baseline, CANDIDATES)
    assert decision_of(extended, Z) == pit.ADMIT


def test_u6_removing_unrelated_candidate_changes_nothing_else():
    extended = build(
        roster=roster(candidates=list(CANDIDATES) + [Z]),
        evidence_snapshot=snapshot(records=list(BASE_RECORDS) + list(Z_RECORDS)),
    )
    reduced = build(evidence_snapshot=snapshot(records=list(BASE_RECORDS) + list(Z_RECORDS)))
    assert _per_candidate_payloads(reduced, CANDIDATES) == _per_candidate_payloads(extended, CANDIDATES)


def test_u5_leave_one_out_over_every_candidate():
    baseline = build()
    for dropped in CANDIDATES:
        kept = [c for c in CANDIDATES if c != dropped]
        artifact = build(roster=roster(candidates=kept))
        assert _per_candidate_payloads(artifact, kept) == _per_candidate_payloads(baseline, kept)


def test_u11_a_rejected_candidate_does_not_affect_the_others():
    others = [c for c in CANDIDATES if c is not C_REJECT_DELIST]
    without = build(roster=roster(candidates=others))
    with_reject = build()
    assert _per_candidate_payloads(with_reject, others) == _per_candidate_payloads(without, others)
    assert decision_of(with_reject, C_REJECT_DELIST) == pit.REJECT


def test_u11_a_single_candidate_universe_matches_the_full_one():
    full = build()
    for candidate in CANDIDATES:
        solo = build(roster=roster(candidates=[candidate]))
        assert record_payload_for(solo, candidate) == record_payload_for(full, candidate)


# --- U7: future-knowledge invariance -----------------------------------------

FUTURE_ADDITIONS = (
    delist(C_ADMIT_INTERVAL, effective=INSIDE, available=FUTURE_KNOWN, key="future|delist|AAA"),
    launch(C_NO_EVIDENCE, effective=BEFORE, available=FUTURE_KNOWN, key="future|launch|EEE"),
    delist(C_NO_EVIDENCE, effective=AFTER, available=FUTURE_KNOWN, key="future|delist|EEE"),
    interval(C_LAUNCH_ONLY, available=FUTURE_KNOWN, key="future|interval|JJJ"),
    observation(C_ADMIT_BOUNDARY, available=FUTURE_KNOWN, key="future|obs|BBB"),
    delist(C_EPISODE_2, effective="2025-03-01T00:00:00Z", available=FUTURE_KNOWN, key="future|delist|KKK2"),
)


def test_u7_future_known_evidence_leaves_the_historical_artifact_byte_identical():
    baseline = build()
    baseline_digest = artifact_digest(baseline)
    extended = build(evidence_snapshot=snapshot(records=list(BASE_RECORDS) + list(FUTURE_ADDITIONS)))
    assert artifact_payload(extended) == artifact_payload(baseline)
    assert artifact_digest(extended) == baseline_digest


def test_u7_every_subset_of_future_evidence_is_invisible():
    baseline_digest = artifact_digest(build())
    for size in range(len(FUTURE_ADDITIONS) + 1):
        for combo in itertools.combinations(FUTURE_ADDITIONS, size):
            artifact = build(evidence_snapshot=snapshot(records=list(BASE_RECORDS) + list(combo)))
            assert artifact_digest(artifact) == baseline_digest


def test_u7_eligible_snapshot_digest_is_blind_to_future_records():
    base = eligible_evidence_digest(snapshot())
    assert eligible_evidence_digest(
        snapshot(records=list(BASE_RECORDS) + list(FUTURE_ADDITIONS))
    ) == base


def test_u7_available_time_equal_to_as_of_is_eligible():
    # Boundary inherited unchanged from the predecessor: <= as_of, not < as_of.
    edge = (launch(C_NO_EVIDENCE, available=AS_OF), delist(C_NO_EVIDENCE, available=AS_OF))
    artifact = build(evidence_snapshot=snapshot(records=list(BASE_RECORDS) + list(edge)))
    assert decision_of(artifact, C_NO_EVIDENCE) == pit.ADMIT


def test_u7_available_time_one_second_after_as_of_is_not_eligible():
    late = (
        launch(C_NO_EVIDENCE, available="2025-01-01T00:00:01Z"),
        delist(C_NO_EVIDENCE, available="2025-01-01T00:00:01Z"),
    )
    artifact = build(evidence_snapshot=snapshot(records=list(BASE_RECORDS) + list(late)))
    assert artifact_digest(artifact) == artifact_digest(build())


# --- U8: outcome blindness ---------------------------------------------------


def test_u8_two_worlds_with_different_future_outcomes_produce_one_artifact():
    # Surrogates for "what happened next": post-query observation density, an
    # eventual delist, a later relist. All future-known, all invisible.
    world_a = list(BASE_RECORDS) + [
        observation(C_ADMIT_BOUNDARY, effective="2024-09-01T00:00:00Z", available=FUTURE_KNOWN, key="wa1"),
        delist(C_LAUNCH_ONLY, effective="2024-12-01T00:00:00Z", available=FUTURE_KNOWN, key="wa2"),
    ]
    world_b = list(BASE_RECORDS) + [
        observation(C_ADMIT_BOUNDARY, effective="2024-10-01T00:00:00Z", available=FUTURE_KNOWN, key="wb1"),
        launch(perp("BBBUSDT", "2026-01-01T00:00:00Z"), effective="2026-01-01T00:00:00Z", available=FUTURE_KNOWN, key="wb2"),
    ]
    a = build(evidence_snapshot=snapshot(records=world_a))
    b = build(evidence_snapshot=snapshot(records=world_b))
    assert artifact_digest(a) == artifact_digest(b) == artifact_digest(build())


def test_u8_the_input_surface_has_no_outcome_channel():
    params = set(inspect.signature(compose_pit_universe).parameters)
    assert params == {
        "roster",
        "evidence_snapshot",
        "query",
        "expected_roster_digest",
        "expected_evidence_snapshot_digest",
        "expected_policy_id",
        "expected_policy_version",
        "expected_policy_contract_digest",
    }
    forbidden = (
        "return", "price", "pnl", "funding", "label", "outcome", "survival",
        "backtest", "candle", "execution", "fill", "slippage", "performance",
    )
    source = MODULE_PATH.read_text().lower()
    for field in itertools.chain(
        *[[f.name for f in dataclasses.fields(t)] for t in (
            puc.CandidateRosterV0,
            puc.EvidenceSnapshotV0,
            puc.UniverseQueryV0,
            puc.UniverseCandidateRecordV0,
            puc.ResolutionTelemetryV0,
            puc.PITUniverseCompositionArtifactV0,
        )]
    ):
        assert not any(word in field.lower() for word in forbidden), field
    # The words may appear in prose disclaimers, but never as an identifier.
    for word in forbidden:
        assert f"def {word}" not in source
        assert f"{word}=" not in source.replace("outcome=", "")


# --- U9 / U10: UNRESOLVED preservation ---------------------------------------


def test_u9_unresolved_is_recorded_verbatim():
    artifact = build()
    for candidate in (C_NO_EVIDENCE, C_OBSERVATION_ONLY, C_CONFLICT, C_FUTURE_KNOWN, C_LAUNCH_ONLY):
        record = record_for(artifact, candidate)
        assert record.admission_decision.decision == pit.UNRESOLVED
        assert candidate in artifact.unresolved
        assert candidate not in artifact.admitted
        assert candidate not in artifact.rejected


def test_u9_no_unresolved_candidate_is_ever_upgraded_or_downgraded():
    artifact = build()
    for record in artifact.candidate_records:
        direct = pit.evaluate(
            pit.AdmissionRequest(
                identity=record.identity, query_start=START, query_end=END, as_of=AS_OF
            ),
            puc.eligible_records(snapshot()),
        )
        assert record.admission_decision.decision == direct.decision


def test_u9_a_universe_of_only_unresolved_candidates_is_a_valid_artifact():
    only_unresolved = [C_NO_EVIDENCE, C_OBSERVATION_ONLY, C_CONFLICT, C_FUTURE_KNOWN, C_LAUNCH_ONLY]
    artifact = build(roster=roster(candidates=only_unresolved))
    assert artifact.telemetry.unresolved_count == len(only_unresolved)
    assert artifact.telemetry.resolution_rate == 0.0
    assert artifact.telemetry.roster_partition_complete is True
    assert len(artifact_digest(artifact)) == 64


def test_u10_candidate_with_no_evidence_remains_present_as_unresolved():
    artifact = build(evidence_snapshot=snapshot(records=[]))
    assert set(artifact.unresolved) == set(CANDIDATES)
    assert artifact.admitted == ()
    assert artifact.rejected == ()
    assert len(artifact.candidate_records) == len(CANDIDATES)
    # Absence of evidence is never a rejection, and never a disappearance.
    for record in artifact.candidate_records:
        assert record.admission_decision.decision == pit.UNRESOLVED
        assert pit.NO_EXACT_IDENTITY_EVIDENCE in record.admission_decision.reason_codes


# --- U12..U15: fail-closed structural inputs ---------------------------------


@pytest.mark.parametrize(
    "start,end,as_of",
    [
        (END, START, AS_OF),                                     # inverted
        (START, START, AS_OF),                                   # empty
        (START, "2025-06-01T00:00:00Z", AS_OF),                  # end > as_of
        ("2024-03-01", END, AS_OF),                              # malformed shape
        ("2024-02-30T00:00:00Z", END, AS_OF),                    # not a real instant
        (START, END, "not-a-time"),                              # malformed as_of
    ],
)
def test_u12_malformed_query_emits_no_artifact(start, end, as_of):
    with pytest.raises(InvalidUniverseQuery):
        UniverseQueryV0(start=start, end=end, as_of=as_of)


def test_u12_query_end_equal_to_as_of_is_valid():
    q = UniverseQueryV0(start=START, end=AS_OF, as_of=AS_OF)
    artifact = build(query=q)
    assert len(artifact.candidate_records) == len(CANDIDATES)


def test_u12_a_non_query_object_is_refused():
    with pytest.raises(InvalidUniverseQuery):
        build(query={"start": START, "end": END, "as_of": AS_OF})


def test_u13_policy_identity_mismatch_fails_closed():
    for kwargs in (
        {"expected_policy_id": "qntylab.some_other_policy"},
        {"expected_policy_version": "v1"},
        {"expected_policy_contract_digest": "0" * 64},
    ):
        with pytest.raises(PolicyIdentityMismatch):
            build(**kwargs)


def test_u13_matching_policy_identity_builds():
    artifact = build(
        expected_policy_id=pit.POLICY_ID,
        expected_policy_version=pit.POLICY_VERSION,
        expected_policy_contract_digest=pit.POLICY_CONTRACT_DIGEST,
    )
    assert artifact.policy_contract_digest == pit.POLICY_CONTRACT_DIGEST


def test_u14_evidence_snapshot_digest_mismatch_fails_closed():
    with pytest.raises(InvalidEvidenceSnapshot):
        build(expected_evidence_snapshot_digest="0" * 64)
    # Matching digest builds.
    artifact = build(expected_evidence_snapshot_digest=eligible_evidence_digest(snapshot()))
    assert artifact.evidence.eligible_evidence_digest == eligible_evidence_digest(snapshot())


def test_u14_snapshot_as_of_must_bind_the_query_as_of():
    other = snapshot(as_of="2024-12-01T00:00:00Z")
    with pytest.raises(InvalidEvidenceSnapshot):
        build(evidence_snapshot=other)


def test_u14_malformed_snapshot_fails_closed():
    with pytest.raises(InvalidEvidenceSnapshot):
        EvidenceSnapshotV0(snapshot_id="", snapshot_version="v0", as_of=AS_OF, records=())
    with pytest.raises(InvalidEvidenceSnapshot):
        EvidenceSnapshotV0(snapshot_id="s", snapshot_version="v9", as_of=AS_OF, records=())
    with pytest.raises(InvalidEvidenceSnapshot):
        EvidenceSnapshotV0(snapshot_id="s", snapshot_version="v0", as_of="nope", records=())
    with pytest.raises(InvalidEvidenceSnapshot):
        EvidenceSnapshotV0(snapshot_id="s", snapshot_version="v0", as_of=AS_OF, records=list(BASE_RECORDS))
    with pytest.raises(InvalidEvidenceSnapshot):
        EvidenceSnapshotV0(snapshot_id="s", snapshot_version="v0", as_of=AS_OF, records=("not-a-record",))
    with pytest.raises(InvalidEvidenceSnapshot):
        build(evidence_snapshot="not-a-snapshot")


def test_u15_roster_digest_mismatch_fails_closed():
    with pytest.raises(InvalidCandidateRoster):
        build(expected_roster_digest="0" * 64)
    artifact = build(expected_roster_digest=roster_digest(roster()))
    assert artifact.candidate_roster.roster_digest == roster_digest(roster())


def test_u15_malformed_roster_fails_closed():
    with pytest.raises(InvalidCandidateRoster):
        roster(roster_id="")
    with pytest.raises(InvalidCandidateRoster):
        CandidateRosterV0(
            roster_id="r", roster_version="v9", scope="s",
            source_kind=ARTIFICIAL_FIXTURE,
            completeness_claim=CLOSED_WORLD_BY_CONSTRUCTION, candidates=(C_NO_EVIDENCE,),
        )
    with pytest.raises(InvalidCandidateRoster):
        CandidateRosterV0(
            roster_id="r", roster_version="v0", scope="s",
            source_kind="BINANCE_LIVE",
            completeness_claim=CLOSED_WORLD_BY_CONSTRUCTION, candidates=(C_NO_EVIDENCE,),
        )
    with pytest.raises(InvalidCandidateRoster):
        CandidateRosterV0(
            roster_id="r", roster_version="v0", scope="s",
            source_kind=ARTIFICIAL_FIXTURE,
            completeness_claim="HISTORICALLY_COMPLETE", candidates=(C_NO_EVIDENCE,),
        )
    with pytest.raises(InvalidCandidateRoster):
        roster(candidates=[])
    with pytest.raises(InvalidCandidateRoster):
        CandidateRosterV0(
            roster_id="r", roster_version="v0", scope="s",
            source_kind=ARTIFICIAL_FIXTURE,
            completeness_claim=CLOSED_WORLD_BY_CONSTRUCTION, candidates=[C_NO_EVIDENCE],
        )
    with pytest.raises(InvalidCandidateRoster):
        roster(candidates=["BTCUSDT"])
    with pytest.raises(InvalidCandidateRoster):
        build(roster="not-a-roster")


def test_all_structural_failures_are_invalid_universe_build_not_unresolved():
    for exc in (
        InvalidCandidateRoster, DuplicateCandidateIdentity, InvalidEvidenceSnapshot,
        InvalidUniverseQuery, PolicyIdentityMismatch, InvalidUniverseArtifact,
    ):
        assert issubclass(exc, InvalidUniverseBuild)
    assert issubclass(InvalidUniverseBuild, ValueError)
    # BUILD_INVALID and UNRESOLVED share no channel: UNRESOLVED is a decision
    # string, build failure is an exception with no artifact.
    assert pit.UNRESOLVED not in {e.__name__ for e in (InvalidUniverseBuild,)}


def test_atomic_formation_no_partial_artifact_escapes():
    """A build that fails leaves nothing behind: no module-level state exists."""
    module_state = [
        name for name, value in vars(puc).items()
        if not name.startswith("_")
        and isinstance(value, (list, dict, set))
        and name not in {"COMPLETENESS_CLAIM_MEANINGS"}
    ]
    assert module_state == []
    with pytest.raises(InvalidUniverseBuild):
        build(expected_roster_digest="0" * 64)
    # A subsequent good build is unaffected.
    assert artifact_digest(build()) == artifact_digest(build())


# --- H-1 regression: the partition invariant survives the artifact -----------


def test_h1_unresolved_cannot_be_promoted_into_admitted_by_forgery():
    """The exact-partition invariant is enforced where digests are minted."""
    artifact = build()
    promoted = dataclasses.replace(
        artifact, admitted=artifact.admitted + artifact.unresolved, unresolved=()
    )
    with pytest.raises(InvalidUniverseArtifact):
        artifact_payload(promoted)
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(promoted)


def test_h1_candidate_in_two_partitions_is_refused():
    artifact = build()
    doubled = dataclasses.replace(artifact, rejected=artifact.rejected + artifact.admitted)
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(doubled)


def test_h1_candidate_in_no_partition_is_refused():
    artifact = build()
    for dropped in (
        dataclasses.replace(artifact, admitted=(), rejected=(), unresolved=()),
        dataclasses.replace(artifact, unresolved=artifact.unresolved[1:]),
    ):
        with pytest.raises(InvalidUniverseArtifact):
            artifact_digest(dropped)


def test_h1_partition_must_agree_with_the_recorded_decision():
    artifact = build()
    swapped = dataclasses.replace(
        artifact,
        admitted=tuple(sorted(artifact.admitted[1:] + artifact.rejected[:1], key=puc._identity_key)),
        rejected=tuple(sorted(artifact.rejected[1:] + artifact.admitted[:1], key=puc._identity_key)),
    )
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(swapped)


def test_h1_duplicate_identity_inside_one_partition_is_refused():
    artifact = build()
    dup = dataclasses.replace(artifact, admitted=artifact.admitted + artifact.admitted[:1])
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(dup)


def test_h1_duplicate_candidate_record_is_refused():
    artifact = build()
    dup = dataclasses.replace(
        artifact, candidate_records=artifact.candidate_records + artifact.candidate_records[:1]
    )
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(dup)


def test_h1_telemetry_must_describe_its_own_artifact():
    artifact = build()
    t0 = artifact.telemetry
    for forged in (
        dataclasses.replace(t0, admit_count=t0.admit_count + 1),
        dataclasses.replace(t0, candidate_count=t0.candidate_count + 1),
        dataclasses.replace(t0, unresolved_count=0),
        dataclasses.replace(t0, roster_partition_complete=False),
        dataclasses.replace(t0, reason_code_histogram=()),
    ):
        with pytest.raises(InvalidUniverseArtifact):
            artifact_digest(dataclasses.replace(artifact, telemetry=forged))


def test_h1_honest_artifacts_are_unaffected():
    for candidates in ([C_ADMIT_BOUNDARY], list(CANDIDATES), [C_NO_EVIDENCE, C_CONFLICT]):
        artifact = build(roster=roster(candidates=candidates))
        assert len(artifact_digest(artifact)) == 64


# --- U16: canonical repeatability --------------------------------------------


def test_u16_same_semantic_inputs_repeat_the_exact_serialisation_and_digest():
    first = build()
    second = build()
    assert artifact_payload(first) == artifact_payload(second)
    assert artifact_digest(first) == artifact_digest(second)
    assert len(artifact_digest(first)) == 64
    assert set(artifact_digest(first)) <= set("0123456789abcdef")


def test_u16_freshly_constructed_equal_inputs_repeat_the_digest():
    a = compose_pit_universe(
        roster=roster(candidates=list(CANDIDATES)),
        evidence_snapshot=snapshot(records=list(BASE_RECORDS)),
        query=UniverseQueryV0(start=START, end=END, as_of=AS_OF),
    )
    b = compose_pit_universe(
        roster=roster(candidates=list(reversed(CANDIDATES))),
        evidence_snapshot=snapshot(records=list(reversed(BASE_RECORDS))),
        query=UniverseQueryV0(start=START, end=END, as_of=AS_OF),
    )
    assert artifact_digest(a) == artifact_digest(b)


# --- U17: roster provenance is load-bearing ----------------------------------


def test_u17_same_candidates_different_provenance_gives_a_different_artifact():
    baseline = build()
    for changed in (
        roster(roster_id="a-different-roster"),
        roster(scope="a-different-scope"),
    ):
        artifact = build(roster=changed)
        assert set(artifact.admitted) == set(baseline.admitted)
        assert set(artifact.rejected) == set(baseline.rejected)
        assert set(artifact.unresolved) == set(baseline.unresolved)
        assert artifact_digest(artifact) != artifact_digest(baseline)


def test_u17_roster_digest_covers_provenance_not_only_membership():
    assert roster_digest(roster(roster_id="x")) != roster_digest(roster(roster_id="y"))
    assert roster_digest(roster(scope="x")) != roster_digest(roster(scope="y"))


def test_u17_evidence_snapshot_id_is_load_bearing():
    assert artifact_digest(build(evidence_snapshot=snapshot(snapshot_id="other"))) != artifact_digest(build())


# --- U18: as_of is load-bearing ----------------------------------------------


def test_u18_same_claims_different_as_of_changes_identity_and_only_licensed_decisions():
    late_available = (
        launch(C_NO_EVIDENCE, effective=BEFORE, available="2024-11-01T00:00:00Z", key="late|launch|EEE"),
        delist(C_NO_EVIDENCE, effective=AFTER, available="2024-11-01T00:00:00Z", key="late|delist|EEE"),
    )
    records = list(BASE_RECORDS) + list(late_available)
    early_as_of = "2024-10-01T00:00:00Z"

    early = compose_pit_universe(
        roster=roster(),
        evidence_snapshot=snapshot(records=records, as_of=early_as_of),
        query=UniverseQueryV0(start=START, end=END, as_of=early_as_of),
    )
    late = compose_pit_universe(
        roster=roster(),
        evidence_snapshot=snapshot(records=records, as_of=AS_OF),
        query=QUERY,
    )
    assert artifact_digest(early) != artifact_digest(late)
    # Exactly one candidate legitimately changes: the one whose evidence became
    # knowable between the two cutoffs.
    changed = {
        puc._identity_key(c)
        for c in CANDIDATES
        if decision_of(early, c) != decision_of(late, c)
    }
    assert changed == {puc._identity_key(C_NO_EVIDENCE)}
    assert decision_of(early, C_NO_EVIDENCE) == pit.UNRESOLVED
    assert decision_of(late, C_NO_EVIDENCE) == pit.ADMIT


def test_u18_query_bounds_are_load_bearing():
    baseline = artifact_digest(build())
    assert artifact_digest(build(query=UniverseQueryV0(start=BEFORE, end=END, as_of=AS_OF))) != baseline
    assert artifact_digest(build(query=UniverseQueryV0(start=START, end=INSIDE, as_of=AS_OF))) != baseline


# --- U19: data-usability independence ----------------------------------------


def test_u19_missing_price_funding_or_outcome_data_has_no_input_channel():
    for kwarg in ("price_data", "funding", "candles", "labels", "usable", "experiment_data"):
        with pytest.raises(TypeError):
            build(**{kwarg: {}})


def test_u19_data_usability_cannot_move_a_candidate_between_partitions():
    """Two worlds differing only in hypothetical data availability are one world.

    Data availability is not representable in any input type, so the strongest
    statement possible is that the entire input surface is unchanged by it --
    which is exactly the guarantee wanted.
    """
    baseline = build()
    # The nearest representable surrogate: whether an instrument was observed
    # at all inside the window (a data-availability proxy). It must not move
    # any candidate between partitions.
    with_observations = list(BASE_RECORDS) + [
        observation(C_NO_EVIDENCE, key="proxy|obs|EEE"),
        observation(C_LAUNCH_ONLY, key="proxy|obs|JJJ"),
        observation(C_REJECT_DELIST, key="proxy|obs|CCC"),
    ]
    artifact = build(evidence_snapshot=snapshot(records=with_observations))
    assert set(artifact.admitted) == set(baseline.admitted)
    assert set(artifact.rejected) == set(baseline.rejected)
    assert set(artifact.unresolved) == set(baseline.unresolved)


# --- U20: composition equals independent per-candidate admission -------------


def test_u20_composition_equals_independent_per_candidate_admission():
    artifact = build()
    slice_ = puc.eligible_records(snapshot())
    for candidate in CANDIDATES:
        expected = pit.evaluate(
            pit.AdmissionRequest(
                identity=candidate, query_start=START, query_end=END, as_of=AS_OF
            ),
            slice_,
        )
        recorded = record_for(artifact, candidate).admission_decision
        assert recorded == expected
        assert pit.decision_digest(recorded) == pit.decision_digest(expected)
        assert record_payload_for(artifact, candidate)["admission_decision_digest"] == pit.decision_digest(expected)


def test_u20_composition_equals_admission_over_the_raw_snapshot_too():
    """Narrowing to the eligible slice must not change any policy answer."""
    artifact = build()
    for candidate in CANDIDATES:
        expected = pit.evaluate(
            pit.AdmissionRequest(
                identity=candidate, query_start=START, query_end=END, as_of=AS_OF
            ),
            snapshot().records,
        )
        assert record_for(artifact, candidate).admission_decision == expected


def test_u20_reason_codes_and_evidence_basis_are_not_lost():
    artifact = build()
    for candidate in CANDIDATES:
        decision = record_for(artifact, candidate).admission_decision
        payload = record_payload_for(artifact, candidate)
        assert payload["reason_codes"] == sorted(decision.reason_codes)
        assert payload["reason_codes"]  # never empty
        assert payload["evidence_basis"] == pit.decision_payload(decision)["evidence_basis"]
    admit_record = record_for(artifact, C_ADMIT_BOUNDARY)
    assert len(admit_record.admission_decision.evidence_basis) == 2


# --- Subtype / type-widening attacks -----------------------------------------


@dataclasses.dataclass(frozen=True)
class WidenedIdentity(InstrumentIdentity):
    venue_note: str = "distinguishing"


@dataclasses.dataclass(frozen=True)
class WidenedRoster(CandidateRosterV0):
    hidden_scope: str = "distinguishing"


@dataclasses.dataclass(frozen=True)
class WidenedSnapshot(EvidenceSnapshotV0):
    hidden_slice: str = "distinguishing"


@dataclasses.dataclass(frozen=True)
class WidenedQuery(UniverseQueryV0):
    hidden_bound: str = "distinguishing"


@dataclasses.dataclass(frozen=True)
class WidenedRecord(puc.UniverseCandidateRecordV0):
    hidden_decision: str = "distinguishing"


@dataclasses.dataclass(frozen=True)
class WidenedTelemetry(puc.ResolutionTelemetryV0):
    hidden_count: int = 99


@dataclasses.dataclass(frozen=True)
class WidenedArtifact(puc.PITUniverseCompositionArtifactV0):
    hidden_universe: str = "distinguishing"


def test_widened_identity_is_refused_in_the_roster():
    widened = WidenedIdentity(
        symbol="AAAUSDT", market="binance-usd-m", contract_type="perpetual",
        instrument_instance_id="binance|AAAUSDT|perpetual|usd-m|2024-01-01T00:00:00Z",
        venue_note="A",
    )
    with pytest.raises(InvalidCandidateRoster):
        roster(candidates=[widened])


def test_widened_identities_cannot_collide_into_one_candidate():
    a = WidenedIdentity(
        symbol="X", market="m", contract_type="perpetual", instrument_instance_id="i", venue_note="A"
    )
    b = WidenedIdentity(
        symbol="X", market="m", contract_type="perpetual", instrument_instance_id="i", venue_note="B"
    )
    assert a != b
    # Refused at the door rather than flattened to the same canonical payload.
    with pytest.raises(InvalidCandidateRoster):
        roster(candidates=[a, b])


def test_widened_roster_subtype_is_refused():
    widened = WidenedRoster(
        roster_id="r", roster_version="v0", scope="s", source_kind=ARTIFICIAL_FIXTURE,
        completeness_claim=CLOSED_WORLD_BY_CONSTRUCTION, candidates=(C_NO_EVIDENCE,),
        hidden_scope="A",
    )
    with pytest.raises(InvalidCandidateRoster):
        roster_digest(widened)
    with pytest.raises(InvalidCandidateRoster):
        build(roster=widened)


def test_widened_snapshot_subtype_is_refused():
    widened = WidenedSnapshot(
        snapshot_id="s", snapshot_version="v0", as_of=AS_OF, records=BASE_RECORDS, hidden_slice="A"
    )
    with pytest.raises(InvalidEvidenceSnapshot):
        eligible_evidence_digest(widened)
    with pytest.raises(InvalidEvidenceSnapshot):
        build(evidence_snapshot=widened)


def test_widened_query_subtype_is_refused():
    widened = WidenedQuery(start=START, end=END, as_of=AS_OF, hidden_bound="A")
    with pytest.raises(InvalidUniverseQuery):
        build(query=widened)


def test_widened_candidate_record_subtype_is_refused():
    artifact = build()
    base = artifact.candidate_records[0]
    widened = WidenedRecord(
        identity=base.identity, admission_decision=base.admission_decision, hidden_decision="A"
    )
    with pytest.raises(InvalidUniverseArtifact):
        puc.candidate_record_payload(widened)
    forged = dataclasses.replace(artifact, candidate_records=(widened,) + artifact.candidate_records[1:])
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(forged)


def test_widened_telemetry_and_artifact_subtypes_are_refused():
    artifact = build()
    t = artifact.telemetry
    widened_t = WidenedTelemetry(
        candidate_count=t.candidate_count, admit_count=t.admit_count, reject_count=t.reject_count,
        unresolved_count=t.unresolved_count, reason_code_histogram=t.reason_code_histogram,
        roster_partition_complete=t.roster_partition_complete, hidden_count=1,
    )
    with pytest.raises(InvalidUniverseArtifact):
        puc.telemetry_payload(widened_t)
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(dataclasses.replace(artifact, telemetry=widened_t))

    fields = {f.name: getattr(artifact, f.name) for f in dataclasses.fields(artifact)}
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(WidenedArtifact(**fields, hidden_universe="A"))


def test_widened_admission_decision_and_basis_are_refused_by_the_predecessor():
    @dataclasses.dataclass(frozen=True)
    class WidenedDecision(pit.AdmissionDecision):
        hidden: str = "A"

    artifact = build()
    base = artifact.candidate_records[0].admission_decision
    widened = WidenedDecision(
        request=base.request, decision=base.decision, reason_codes=base.reason_codes,
        evidence_basis=base.evidence_basis, policy_id=base.policy_id,
        policy_version=base.policy_version, policy_contract_digest=base.policy_contract_digest,
        hidden="A",
    )
    with pytest.raises(ValueError):
        puc.candidate_record_payload(
            puc.UniverseCandidateRecordV0(identity=base.request.identity, admission_decision=widened)
        )


def test_candidate_record_identity_must_match_its_decision():
    artifact = build()
    base = record_for(artifact, C_ADMIT_BOUNDARY)
    mismatched = puc.UniverseCandidateRecordV0(
        identity=C_NO_EVIDENCE, admission_decision=base.admission_decision
    )
    with pytest.raises(InvalidUniverseArtifact):
        puc.candidate_record_payload(mismatched)


# --- Digest omission / collision probes --------------------------------------


LOAD_BEARING_MUTATIONS = {
    "candidate identity": lambda: build(
        roster=roster(candidates=[c for c in CANDIDATES if c is not C_NO_EVIDENCE] + [perp("QQQUSDT")])
    ),
    "roster_id": lambda: build(roster=roster(roster_id="other-roster")),
    "roster scope": lambda: build(roster=roster(scope="other-scope")),
    "as_of": lambda: compose_pit_universe(
        roster=roster(),
        evidence_snapshot=snapshot(as_of="2024-12-01T00:00:00Z"),
        query=UniverseQueryV0(start=START, end=END, as_of="2024-12-01T00:00:00Z"),
    ),
    "start": lambda: build(query=UniverseQueryV0(start=BEFORE, end=END, as_of=AS_OF)),
    "end": lambda: build(query=UniverseQueryV0(start=START, end=INSIDE, as_of=AS_OF)),
    "evidence snapshot content": lambda: build(
        evidence_snapshot=snapshot(records=list(BASE_RECORDS) + [interval(C_LAUNCH_ONLY)])
    ),
    "evidence snapshot id": lambda: build(evidence_snapshot=snapshot(snapshot_id="other-snapshot")),
}


@pytest.mark.parametrize("name", sorted(LOAD_BEARING_MUTATIONS))
def test_one_load_bearing_field_change_changes_the_artifact_digest(name):
    baseline = artifact_digest(build())
    assert artifact_digest(LOAD_BEARING_MUTATIONS[name]()) != baseline, name


def test_all_load_bearing_mutations_are_pairwise_distinct():
    digests = {name: artifact_digest(fn()) for name, fn in LOAD_BEARING_MUTATIONS.items()}
    digests["baseline"] = artifact_digest(build())
    assert len(set(digests.values())) == len(digests), digests


def _forge_record(artifact, identity, **changes):
    base = record_for(artifact, identity)
    forged_record = puc.UniverseCandidateRecordV0(
        identity=identity,
        admission_decision=dataclasses.replace(base.admission_decision, **changes),
    )
    others = tuple(r for r in artifact.candidate_records if r.identity != identity)
    return dataclasses.replace(artifact, candidate_records=(forged_record,) + others)


def test_forged_decision_or_reason_codes_are_refused_outright():
    artifact = build()
    # Rewriting the outcome contradicts the partitions; rewriting the reason
    # codes contradicts the histogram. Both lose their canonical form.
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(_forge_record(artifact, C_NO_EVIDENCE, decision=pit.ADMIT))
    with pytest.raises(InvalidUniverseArtifact):
        artifact_digest(
            _forge_record(artifact, C_NO_EVIDENCE, reason_codes=(pit.INSUFFICIENT_EVIDENCE,))
        )


def test_forged_evidence_basis_changes_the_digest():
    artifact = build()
    forged = _forge_record(artifact, C_ADMIT_BOUNDARY, evidence_basis=())
    assert artifact_digest(forged) != artifact_digest(artifact)


def test_policy_and_builder_digests_are_in_the_artifact_payload():
    payload = artifact_payload(build())
    assert payload["admission_policy"]["policy_contract_digest"] == pit.POLICY_CONTRACT_DIGEST
    assert payload["builder"]["builder_contract_digest"] == puc.BUILDER_CONTRACT_DIGEST
    assert payload["candidate_roster"]["roster_digest"] == roster_digest(roster())
    assert payload["evidence"]["eligible_evidence_digest"] == eligible_evidence_digest(snapshot())
    assert len(puc.BUILDER_CONTRACT_DIGEST) == 64


def test_builder_contract_digest_tracks_the_rule_spec():
    from hashlib import sha256
    import json

    spec = dict(puc._BUILDER_SPEC)
    recomputed = sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    assert recomputed == puc.BUILDER_CONTRACT_DIGEST
    spec["duplicate_candidate"] = "silently deduplicated"
    changed = sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    assert changed != puc.BUILDER_CONTRACT_DIGEST


def test_non_semantic_ordering_never_changes_the_digest():
    rng = random.Random(7)
    baseline = artifact_digest(build())
    for _ in range(15):
        c = list(CANDIDATES)
        e = list(BASE_RECORDS)
        rng.shuffle(c)
        rng.shuffle(e)
        assert artifact_digest(
            build(roster=roster(candidates=c), evidence_snapshot=snapshot(records=e))
        ) == baseline


# --- Telemetry: descriptive only ---------------------------------------------


def test_telemetry_counts_match_the_partitions():
    artifact = build()
    t = artifact.telemetry
    assert t.candidate_count == len(CANDIDATES)
    assert t.admit_count == len(artifact.admitted)
    assert t.reject_count == len(artifact.rejected)
    assert t.unresolved_count == len(artifact.unresolved)
    assert t.admit_count + t.reject_count + t.unresolved_count == t.candidate_count
    assert t.resolution_rate == (t.admit_count + t.reject_count) / t.candidate_count


def test_reason_code_histogram_is_complete_and_closed():
    artifact = build()
    counted = dict(artifact.telemetry.reason_code_histogram)
    expected: dict[str, int] = {}
    for record in artifact.candidate_records:
        for code in record.admission_decision.reason_codes:
            expected[code] = expected.get(code, 0) + 1
    assert counted == expected
    assert set(counted) <= pit.REASON_CODES
    assert list(artifact.telemetry.reason_code_histogram) == sorted(artifact.telemetry.reason_code_histogram)


def test_no_resolution_rate_threshold_exists_anywhere():
    # Structural, not prose: the builder never reads the rate, so it cannot
    # branch on it, and telemetry can never gate artifact formation.
    builder_source = inspect.getsource(compose_pit_universe)
    assert "resolution_rate" not in builder_source
    assert "reason_code_histogram" not in builder_source.split("telemetry = ")[0]
    for name, value in vars(puc).items():
        assert not isinstance(value, float), name

    # 0% resolution and 100% resolution are both valid PASS artifacts.
    empty_evidence = build(evidence_snapshot=snapshot(records=[]))
    assert empty_evidence.telemetry.resolution_rate == 0.0
    assert empty_evidence.telemetry.roster_partition_complete is True
    assert len(artifact_digest(empty_evidence)) == 64

    fully_resolved = build(roster=roster(candidates=[C_ADMIT_BOUNDARY, C_REJECT_DELIST]))
    assert fully_resolved.telemetry.resolution_rate == 1.0
    assert len(artifact_digest(fully_resolved)) == 64


def test_resolution_rate_is_serialised_as_an_exact_integer_ratio():
    payload = artifact_payload(build())["telemetry"]
    assert isinstance(payload["resolution_rate_numerator"], int)
    assert isinstance(payload["resolution_rate_denominator"], int)
    assert not any(isinstance(v, float) for v in payload.values())


# --- Roster-completeness non-escalation --------------------------------------


def test_no_unscoped_universe_completeness_field_exists():
    payload = artifact_payload(build())
    flat = str(payload)
    assert "universe_complete" not in flat
    assert "market_complete" not in flat
    assert payload["telemetry"]["roster_partition_complete"] is True
    assert payload["candidate_roster"]["source_kind"] == ARTIFICIAL_FIXTURE
    assert payload["candidate_roster"]["completeness_claim"] == CLOSED_WORLD_BY_CONSTRUCTION


def test_artifact_carries_its_own_scope_limit():
    artifact = build()
    scope = artifact.partition_completeness_scope
    assert "NOT a claim of historical market-universe completeness" in scope
    assert "survivorship-biased" in scope
    assert artifact_payload(artifact)["partition_completeness_scope"] == scope
    assert puc.COMPLETENESS_CLAIM_MEANINGS[CLOSED_WORLD_BY_CONSTRUCTION].startswith(
        "For this artificial fixture"
    )


def test_only_one_source_kind_and_one_completeness_claim_are_supported():
    assert puc.SOURCE_KINDS == frozenset({ARTIFICIAL_FIXTURE})
    assert puc.COMPLETENESS_CLAIMS == frozenset({CLOSED_WORLD_BY_CONSTRUCTION})


# --- Predecessor non-mutation and isolation ----------------------------------

MODULE_PATH = Path(puc.__file__)
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
        "os", "sys", "pathlib", "socket", "urllib", "urllib3", "requests", "httpx",
        "aiohttp", "websockets", "subprocess", "sqlite3", "random", "time",
        "datetime", "secrets", "uuid", "qnty", "qntypolicygate", "binance",
    }
    imported = _imported_modules()
    assert not {m for m in imported if m.split(".")[0].lower() in forbidden}, imported


def test_only_frozen_qntylab_surfaces_are_imported():
    qntylab_imports = {m for m in _imported_modules() if m.startswith("qntylab")}
    assert qntylab_imports == {
        "qntylab.evidence_claim_split",
        "qntylab.market_observation",
        "qntylab.pit_research_admission",
    }


def test_builder_never_constructs_evidence_or_propositions():
    constructed = {
        node.func.id
        for node in ast.walk(MODULE_AST)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden = {
        "EvidenceRecord", "BoundaryProposition", "PointObservationProposition",
        "IntervalEligibilityProposition", "Assessment",
    }
    assert constructed & forbidden == set()


def test_builder_never_calls_assess_or_reimplements_establishment():
    called = {
        node.func.id
        for node in ast.walk(MODULE_AST)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "assess" not in called
    assert "is_established" not in called
    # The single admission path.
    assert "evaluate" in called


def test_predecessor_admission_semantics_are_unchanged():
    assert pit.DECISIONS == frozenset({"ADMIT", "REJECT", "UNRESOLVED"})
    assert pit.POLICY_ID == "qntylab.pit_research_admission"
    assert pit.POLICY_VERSION == "v0"
    assert len(pit.REASON_CODES) == 11
    assert "FUTURE_KNOWN_EVIDENCE_EXCLUDED" not in pit.REASON_CODES


def test_predecessor_evidence_claim_split_is_unchanged():
    import qntylab.evidence_claim_split as ecs

    assert ecs.EPISTEMIC_STATUSES == frozenset({"ESTABLISHED", "UNKNOWN"})
    assert ecs.BOUNDARY_KINDS == frozenset({"LAUNCH", "DELIST"})


def test_launch_without_delist_still_does_not_admit():
    """The frozen V0 limitation is not weakened to raise universe coverage."""
    artifact = build()
    assert decision_of(artifact, C_LAUNCH_ONLY) == pit.UNRESOLVED
    assert pit.INSUFFICIENT_EVIDENCE in record_for(artifact, C_LAUNCH_ONLY).admission_decision.reason_codes


def test_composition_is_pure_over_repeated_generator_free_calls():
    digests = {artifact_digest(build()) for _ in range(5)}
    assert len(digests) == 1
