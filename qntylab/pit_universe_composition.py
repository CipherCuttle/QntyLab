"""PIT Universe Composition Fixture V0 (artificial closed-world fixture only).

One question only: given an EXPLICITLY SUPPLIED candidate roster, an evidence
snapshot, a half-open historical interval and an ``as_of``, can every exact
candidate be deterministically partitioned into ADMITTED / REJECTED /
UNRESOLVED without inventing evidence, lifecycle semantics, candidate
completeness or future knowledge?

Layer position -- this is layer 2b, and only 2b:

    1.  EVIDENCE CLAIMS          qntylab.evidence_claim_split      (frozen)
    2.  PIT RESEARCH ADMISSION   qntylab.pit_research_admission    (frozen)
    2b. PIT UNIVERSE COMPOSITION this module
    3.  DATA / OUTCOME USABILITY not implemented, unreachable from here

This module owns no evidence semantics and no admission semantics. It is a
deterministic fold of the frozen policy over an explicit candidate list, plus
the identity/digest bookkeeping needed to say exactly WHICH roster, WHICH
evidence slice, WHICH policy and WHICH builder produced a given partition.

What it must never do, and structurally cannot:

    * discover candidates            -- the roster is an input, never derived
    * infer roster completeness      -- the only completeness it computes is
                                        ``roster_partition_complete``, scoped
                                        to the supplied roster (see below)
    * create evidence propositions   -- it constructs no Proposition and no
                                        EvidenceRecord (AST-asserted)
    * upgrade UNKNOWN evidence       -- establishment is the predecessor's
    * override admission decisions   -- the policy's outcome is recorded
                                        verbatim; UNRESOLVED stays UNRESOLVED
    * infer lifecycle continuity     -- no cross-candidate, cross-episode or
                                        cross-interval reasoning exists
    * inspect future outcomes        -- no channel: the whole input is a
                                        roster, a snapshot, and a query
    * inspect data availability      -- likewise no channel

CRITICAL SCOPE LIMIT, restated because it is the whole point:

    PIT-correct filtering of a survivorship-biased candidate roster is still
    survivorship-biased.

``CLOSED_WORLD_BY_CONSTRUCTION`` means only "for this artificial fixture, this
enumerated set is the complete input universe". It does NOT mean these were the
instruments that existed historically, and it does NOT mean the roster
represents any venue at any time. Historical candidate discovery belongs to a
later phase (PIT Candidate Roster / Discovery Provenance V0) and is absent
here.

Point-in-time handling. The snapshot's identity is the digest of its
``as_of``-ELIGIBLE slice (``available_time <= as_of``), not of every record the
caller happened to hand over. Future-known records are therefore invisible to
the artifact -- they change no digest, no decision and no telemetry -- for the
same reason the predecessor refuses a ``FUTURE_KNOWN_EVIDENCE_EXCLUDED`` reason
code: a historical artifact that counted future evidence would make future
knowledge observable. Only the eligible slice is passed to the policy, which
applies its own identical cutoff again; this layer narrows, never widens.

Failure surface. ``UNRESOLVED`` is a valid policy output and normal content of
a healthy artifact. Structural contract violations -- duplicate exact candidate
identity, malformed query, unsupported contract version, policy or snapshot
identity mismatch -- raise ``InvalidUniverseBuild`` and emit NO artifact, not
even a partial one. The two must never be conflated.

No coverage target exists. ``resolution_rate`` is descriptive telemetry with no
pass/fail threshold; an artifact that is 90% UNRESOLVED can be entirely
correct, and is evidence about upstream evidence coverage, never a reason to
weaken the admission policy.

See ``docs/forensics/PIT_UNIVERSE_COMPOSITION_V0_CONTRACT.md``. Artificial
fixture only: no network, no filesystem, no clock, no randomness, no database,
no Qnty / QntyPolicyGate coupling.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable

from qntylab.evidence_claim_split import (
    EvidenceRecord,
    _require_identity,
    _require_non_empty,
    _require_timestamp,
    evidence_payload,
)
from qntylab.market_observation import InstrumentIdentity
from qntylab.pit_research_admission import (
    ADMIT,
    AdmissionDecision,
    AdmissionRequest,
    DECISIONS,
    POLICY_CONTRACT_DIGEST,
    POLICY_ID,
    POLICY_VERSION,
    REASON_CODES,
    REJECT,
    UNRESOLVED,
    decision_digest,
    decision_payload,
    evaluate,
)


# --- Builder identity --------------------------------------------------------

BUILDER_ID = "qntylab.pit_universe_composition"
BUILDER_VERSION = "v0"

ARTIFACT_TYPE = "PIT_UNIVERSE_COMPOSITION_ARTIFACT"
ARTIFACT_VERSION = "v0"


# --- Frozen roster provenance vocabulary -------------------------------------

ARTIFICIAL_FIXTURE = "ARTIFICIAL_FIXTURE"

# Exactly one member in V0. A real venue-derived roster is a different phase
# with a different provenance story, and must not be smuggled in by relabelling
# this one.
SOURCE_KINDS = frozenset({ARTIFICIAL_FIXTURE})

CLOSED_WORLD_BY_CONSTRUCTION = "CLOSED_WORLD_BY_CONSTRUCTION"

COMPLETENESS_CLAIMS = frozenset({CLOSED_WORLD_BY_CONSTRUCTION})

COMPLETENESS_CLAIM_MEANINGS = {
    CLOSED_WORLD_BY_CONSTRUCTION: (
        "For this artificial fixture, the enumerated candidate set is the complete "
        "input universe. This is NOT a claim that these were all instruments that "
        "existed historically, and NOT a claim that this roster represents any "
        "venue at any time."
    ),
}

# Emitted verbatim into every artifact. The artifact must carry its own scope
# limit, because an artifact outlives the conversation that produced it.
PARTITION_COMPLETENESS_SCOPE = (
    "roster_partition_complete is scoped to the supplied CandidateRosterV0 only: "
    "every candidate in that roster appears in exactly one partition. It is NOT a "
    "claim of historical market-universe completeness, and PIT-correct filtering "
    "of a survivorship-biased roster remains survivorship-biased."
)

SUPPORTED_ROSTER_VERSIONS = frozenset({"v0"})
SUPPORTED_SNAPSHOT_VERSIONS = frozenset({"v0"})


# --- Failure surface (structural contract failures, never policy outcomes) ---


class InvalidUniverseBuild(ValueError):
    """A structural contract failure. Never a per-candidate policy outcome.

    Deliberately an exception rather than an artifact state: if a malformed
    roster or query could produce an artifact, a build failure would be
    readable as "these candidates were rejected", which is exactly the
    conflation this layer must prevent. No partial artifact is ever emitted.
    """


class InvalidCandidateRoster(InvalidUniverseBuild):
    """The candidate roster is malformed as input."""


class DuplicateCandidateIdentity(InvalidCandidateRoster):
    """The roster lists one exact canonical identity more than once.

    Fails closed rather than silently deduplicating: a duplicate is evidence of
    a defect in whatever generated the roster, and swallowing it would hide
    that defect behind a plausible-looking universe.
    """


class InvalidEvidenceSnapshot(InvalidUniverseBuild):
    """The evidence snapshot is malformed, or does not bind this query."""


class InvalidUniverseQuery(InvalidUniverseBuild):
    """The historical query is malformed or non-PIT."""


class PolicyIdentityMismatch(InvalidUniverseBuild):
    """The admission policy is not the exact one the caller expected."""


class InvalidUniverseArtifact(InvalidUniverseBuild):
    """An artifact object is not exactly the frozen V0 artifact type."""


def _canonical_json(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _identity_payload(identity: InstrumentIdentity) -> dict:
    # Predecessor's exact-type gate: an InstrumentIdentity subclass carrying
    # extra distinguishing fields would flatten to this payload and let two
    # different candidates share one canonical key.
    _require_identity(identity)
    return {
        "symbol": identity.symbol,
        "market": identity.market,
        "contract_type": identity.contract_type,
        "instrument_instance_id": identity.instrument_instance_id,
    }


def _identity_key(identity: InstrumentIdentity) -> str:
    """Canonical total order over exact identities. Order is never semantic."""
    return _canonical_json(_identity_payload(identity))


# --- Candidate roster --------------------------------------------------------


@dataclass(frozen=True)
class CandidateRosterV0:
    """An EXPLICIT, externally supplied candidate list. Never derived here.

    ``completeness_claim`` is a claim about the fixture's input set, not about
    history; see ``COMPLETENESS_CLAIM_MEANINGS``. Candidate order is not
    semantic: the roster is canonicalised before use and two rosters differing
    only in order are the same roster.
    """
    roster_id: str
    roster_version: str
    scope: str
    source_kind: str
    completeness_claim: str
    candidates: tuple[InstrumentIdentity, ...]

    def __post_init__(self) -> None:
        try:
            _require_non_empty(self.roster_id, "roster_id")
            _require_non_empty(self.roster_version, "roster_version")
            _require_non_empty(self.scope, "scope")
        except ValueError as exc:
            raise InvalidCandidateRoster(str(exc)) from None
        if self.roster_version not in SUPPORTED_ROSTER_VERSIONS:
            raise InvalidCandidateRoster(
                f"roster_version: unsupported contract version: {self.roster_version!r}"
            )
        if self.source_kind not in SOURCE_KINDS:
            raise InvalidCandidateRoster(f"source_kind: unsupported: {self.source_kind!r}")
        if self.completeness_claim not in COMPLETENESS_CLAIMS:
            raise InvalidCandidateRoster(
                f"completeness_claim: unsupported: {self.completeness_claim!r}"
            )
        if type(self.candidates) is not tuple:
            # A list is mutable and a generator is single-consumption; either
            # would make roster identity depend on when it was read.
            raise InvalidCandidateRoster(
                f"candidates: expected exactly tuple, got {type(self.candidates).__name__}"
            )
        if not self.candidates:
            raise InvalidCandidateRoster("candidates: roster must not be empty")
        seen: set[str] = set()
        for candidate in self.candidates:
            try:
                key = _identity_key(candidate)
            except ValueError as exc:
                raise InvalidCandidateRoster(str(exc)) from None
            if key in seen:
                raise DuplicateCandidateIdentity(
                    f"candidates: duplicate exact canonical identity: {key}"
                )
            seen.add(key)


def canonical_candidates(roster: CandidateRosterV0) -> tuple[InstrumentIdentity, ...]:
    """The roster's candidates in frozen canonical order."""
    _require_roster(roster)
    return tuple(sorted(roster.candidates, key=_identity_key))


def _require_roster(roster: CandidateRosterV0) -> None:
    if type(roster) is not CandidateRosterV0:
        raise InvalidCandidateRoster(
            f"roster: expected exactly CandidateRosterV0, got {type(roster).__name__}"
        )


def roster_payload(roster: CandidateRosterV0) -> dict:
    _require_roster(roster)
    return {
        "roster_id": roster.roster_id,
        "roster_version": roster.roster_version,
        "scope": roster.scope,
        "source_kind": roster.source_kind,
        "completeness_claim": roster.completeness_claim,
        "candidates": [_identity_payload(c) for c in canonical_candidates(roster)],
    }


def roster_digest(roster: CandidateRosterV0) -> str:
    """Order-insensitive SHA-256 identity of one candidate roster."""
    return sha256(_canonical_json(roster_payload(roster)).encode()).hexdigest()


# --- Evidence snapshot -------------------------------------------------------


@dataclass(frozen=True)
class EvidenceSnapshotV0:
    """The evidence supplied to ONE historical composition, bound to one ``as_of``.

    This is a wrapper, not a second evidence framework: the records are the
    predecessor's ``EvidenceRecord`` values, unchanged and uninterpreted.

    Snapshot identity is the digest of the ``as_of``-eligible slice only, so a
    snapshot that additionally carries records knowable only after ``as_of``
    has the SAME digest as one that does not. That is deliberate: the object
    being identified is "the historically eligible evidence at ``as_of``", and
    a historical artifact must not shift when the future arrives.
    """
    snapshot_id: str
    snapshot_version: str
    as_of: str
    records: tuple[EvidenceRecord, ...]

    def __post_init__(self) -> None:
        try:
            _require_non_empty(self.snapshot_id, "snapshot_id")
            _require_non_empty(self.snapshot_version, "snapshot_version")
            _require_timestamp(self.as_of, "as_of")
        except ValueError as exc:
            raise InvalidEvidenceSnapshot(str(exc)) from None
        if self.snapshot_version not in SUPPORTED_SNAPSHOT_VERSIONS:
            raise InvalidEvidenceSnapshot(
                f"snapshot_version: unsupported contract version: {self.snapshot_version!r}"
            )
        if type(self.records) is not tuple:
            raise InvalidEvidenceSnapshot(
                f"records: expected exactly tuple, got {type(self.records).__name__}"
            )
        for record in self.records:
            # Exact type, inherited from the predecessor: a widened record
            # subtype would serialise as the base record and could collide.
            if type(record) is not EvidenceRecord:
                raise InvalidEvidenceSnapshot(
                    f"records: expected exactly EvidenceRecord, got {type(record).__name__}"
                )


def _require_snapshot(snapshot: EvidenceSnapshotV0) -> None:
    if type(snapshot) is not EvidenceSnapshotV0:
        raise InvalidEvidenceSnapshot(
            f"evidence_snapshot: expected exactly EvidenceSnapshotV0, got "
            f"{type(snapshot).__name__}"
        )


def eligible_records(snapshot: EvidenceSnapshotV0) -> tuple[EvidenceRecord, ...]:
    """The ``available_time <= as_of`` slice, deduplicated, in canonical order.

    The cutoff is applied before anything else is observed about the snapshot,
    exactly as the predecessor does, and the result is emitted in canonical
    order so no incidental input ordering can reach the policy or the digest.

    Byte-identical records are collapsed. A record is a value: carrying the
    same established fact twice conveys nothing extra, and the predecessor
    already deduplicates ``supporting_source_keys`` for exactly this reason, so
    a repeated record must not give the snapshot a different identity either.
    Records that differ in any field -- including ``source_key`` -- are
    distinct corroborating evidence and are all kept.
    """
    _require_snapshot(snapshot)
    unique: dict[str, EvidenceRecord] = {}
    for record in snapshot.records:
        if record.available_time <= snapshot.as_of:
            unique.setdefault(_canonical_json(evidence_payload(record)), record)
    return tuple(record for _, record in sorted(unique.items()))


def eligible_evidence_digest(snapshot: EvidenceSnapshotV0) -> str:
    """SHA-256 over the eligible slice: order-insensitive, future-blind."""
    rows = [evidence_payload(record) for record in eligible_records(snapshot)]
    return sha256(_canonical_json(rows).encode()).hexdigest()


# --- Historical query --------------------------------------------------------


@dataclass(frozen=True)
class UniverseQueryV0:
    """``[start, end)`` at one ``as_of``. Same time semantics as the policy.

    No second interval convention is introduced at the universe layer; these
    three fields are handed to each ``AdmissionRequest`` unchanged.
    """
    start: str
    end: str
    as_of: str

    def __post_init__(self) -> None:
        try:
            _require_timestamp(self.start, "start")
            _require_timestamp(self.end, "end")
            _require_timestamp(self.as_of, "as_of")
        except ValueError as exc:
            raise InvalidUniverseQuery(str(exc)) from None
        if not self.start < self.end:
            raise InvalidUniverseQuery(
                f"query interval: start must precede end: {self.start!r} .. {self.end!r}"
            )
        if self.end > self.as_of:
            # Refuse the question. Rejecting every candidate instead would turn
            # a contract violation into a plausible-looking empty universe.
            raise InvalidUniverseQuery(
                f"non-PIT query: end must not exceed as_of: {self.end!r} > {self.as_of!r}"
            )


def _require_query(query: UniverseQueryV0) -> None:
    if type(query) is not UniverseQueryV0:
        raise InvalidUniverseQuery(
            f"query: expected exactly UniverseQueryV0, got {type(query).__name__}"
        )


def query_payload(query: UniverseQueryV0) -> dict:
    _require_query(query)
    return {"start": query.start, "end": query.end, "as_of": query.as_of}


# --- Artifact components -----------------------------------------------------


@dataclass(frozen=True)
class RosterRefV0:
    """Roster provenance as recorded in the artifact."""
    roster_id: str
    roster_version: str
    scope: str
    source_kind: str
    completeness_claim: str
    roster_digest: str


@dataclass(frozen=True)
class EvidenceSnapshotRefV0:
    """Evidence-slice provenance as recorded in the artifact."""
    snapshot_id: str
    snapshot_version: str
    as_of: str
    eligible_evidence_digest: str


@dataclass(frozen=True)
class UniverseCandidateRecordV0:
    """One candidate's recorded policy decision. Never a reinterpretation.

    The whole ``AdmissionDecision`` is retained, so reason codes and evidence
    basis cannot be lost or paraphrased on the way into the artifact; the
    canonical payload is produced by the predecessor's own serialiser.
    """
    identity: InstrumentIdentity
    admission_decision: AdmissionDecision


@dataclass(frozen=True)
class ResolutionTelemetryV0:
    """Descriptive counts only. No threshold, no pass/fail, no target.

    ``resolution_rate`` is ``(admit_count + reject_count) / candidate_count``.
    It is serialised as an exact integer ratio so artifact digests cannot
    depend on float formatting.
    """
    candidate_count: int
    admit_count: int
    reject_count: int
    unresolved_count: int
    reason_code_histogram: tuple[tuple[str, int], ...]
    roster_partition_complete: bool

    @property
    def resolution_rate(self) -> float:
        return (self.admit_count + self.reject_count) / self.candidate_count


@dataclass(frozen=True)
class PITUniverseCompositionArtifactV0:
    """The frozen deterministic output of one universe composition."""
    artifact_type: str
    artifact_version: str
    query: UniverseQueryV0
    candidate_roster: RosterRefV0
    evidence: EvidenceSnapshotRefV0
    policy_id: str
    policy_version: str
    policy_contract_digest: str
    builder_id: str
    builder_version: str
    builder_contract_digest: str
    candidate_records: tuple[UniverseCandidateRecordV0, ...]
    admitted: tuple[InstrumentIdentity, ...]
    rejected: tuple[InstrumentIdentity, ...]
    unresolved: tuple[InstrumentIdentity, ...]
    telemetry: ResolutionTelemetryV0
    partition_completeness_scope: str


# --- Frozen builder spec (what BUILDER_CONTRACT_DIGEST commits to) -----------
#
# A literal statement of every frozen composition rule. Changing a rule changes
# the digest carried by every artifact, so a historical partition can be traced
# to the exact builder that produced it. Not a registry; holds no state.

_BUILDER_SPEC = {
    "builder_id": BUILDER_ID,
    "builder_version": BUILDER_VERSION,
    "artifact_type": ARTIFACT_TYPE,
    "artifact_version": ARTIFACT_VERSION,
    "inputs": ["CandidateRosterV0", "EvidenceSnapshotV0", "UniverseQueryV0", "PITResearchAdmissionPolicyV0"],
    "candidate_source": "explicitly supplied roster only; no discovery, no derivation, no inference",
    "roster_versions": sorted(SUPPORTED_ROSTER_VERSIONS),
    "snapshot_versions": sorted(SUPPORTED_SNAPSHOT_VERSIONS),
    "source_kinds": sorted(SOURCE_KINDS),
    "completeness_claims": sorted(COMPLETENESS_CLAIMS),
    "duplicate_candidate": "duplicate exact canonical identity -> DuplicateCandidateIdentity; never deduplicated",
    "candidate_order": "not semantic; canonical order is ascending canonical identity JSON",
    "query_interval": "[start, end)",
    "pit_rule": "start < end and end <= as_of",
    "snapshot_binding": "evidence_snapshot.as_of must equal query.as_of exactly",
    "evidence_eligibility": "available_time <= as_of, applied before anything else is observed",
    "evidence_dedup": "byte-identical eligible records are collapsed; records differing in any field are all kept",
    "snapshot_identity": "digest of the as_of-eligible slice only; future-known records are invisible",
    "composition": "decision = pit_research_admission.evaluate(AdmissionRequest(candidate, start, end, as_of), eligible_slice) per candidate, independently",
    "decision_recording": "verbatim; UNRESOLVED is recorded as UNRESOLVED and never upgraded, downgraded or reinterpreted",
    "partition": "ADMIT->admitted, REJECT->rejected, UNRESOLVED->unresolved; exactly one partition per candidate; union equals the roster",
    "partition_enforcement": "the exact-partition invariant and telemetry consistency are re-checked at canonicalisation, so a violating artifact has no canonical form and no digest",
    "policy_binding": "policy id, version and contract digest must match the expected values and every decision's own values",
    "atomicity": "all structural validation precedes artifact construction; a failed build emits no artifact",
    "telemetry": "descriptive only; no admit/reject/unresolved/resolution-rate threshold exists",
    "resolution_rate": "(admit_count + reject_count) / candidate_count",
    "partition_completeness_scope": PARTITION_COMPLETENESS_SCOPE,
    "non_escalation": [
        "creates no evidence proposition and no evidence record",
        "creates no candidate-completeness claim beyond roster_partition_complete",
        "has no data-usability, outcome, price, funding, label or survival input channel",
        "performs no cross-candidate reasoning: a candidate's decision depends only on itself",
    ],
}

BUILDER_CONTRACT_DIGEST = sha256(_canonical_json(_BUILDER_SPEC).encode()).hexdigest()


# --- Canonical serialisation / artifact identity -----------------------------


def candidate_record_payload(record: UniverseCandidateRecordV0) -> dict:
    # Exact type, not isinstance: a subclass carrying extra distinguishing
    # fields would serialise as the base record, letting two semantically
    # different universes share one artifact_digest. Same widening class as the
    # predecessor's H-1.
    if type(record) is not UniverseCandidateRecordV0:
        raise InvalidUniverseArtifact(
            f"candidate_records: expected exactly UniverseCandidateRecordV0, got "
            f"{type(record).__name__}"
        )
    # decision_payload enforces exact AdmissionDecision and exact basis entries.
    payload = decision_payload(record.admission_decision)
    if record.identity != record.admission_decision.request.identity:
        raise InvalidUniverseArtifact(
            "candidate_records: record identity does not match its admission decision"
        )
    return {
        "identity": _identity_payload(record.identity),
        "decision": payload["decision"],
        "reason_codes": payload["reason_codes"],
        "evidence_basis": payload["evidence_basis"],
        "admission_decision_digest": decision_digest(record.admission_decision),
    }


def telemetry_payload(telemetry: ResolutionTelemetryV0) -> dict:
    if type(telemetry) is not ResolutionTelemetryV0:
        raise InvalidUniverseArtifact(
            f"telemetry: expected exactly ResolutionTelemetryV0, got {type(telemetry).__name__}"
        )
    return {
        "candidate_count": telemetry.candidate_count,
        "admit_count": telemetry.admit_count,
        "reject_count": telemetry.reject_count,
        "unresolved_count": telemetry.unresolved_count,
        # Exact ratio, not a float: digest stability must not depend on float
        # repr. Threshold: none, by contract.
        "resolution_rate_numerator": telemetry.admit_count + telemetry.reject_count,
        "resolution_rate_denominator": telemetry.candidate_count,
        "reason_code_histogram": [
            {"reason_code": code, "count": count}
            for code, count in telemetry.reason_code_histogram
        ],
        "roster_partition_complete": telemetry.roster_partition_complete,
    }


def _require_exact_partition(
    artifact: PITUniverseCompositionArtifactV0,
    records: list[dict],
) -> None:
    """The exact-partition invariant, enforced at the canonicalisation boundary.

    ``compose_pit_universe`` cannot produce a violating artifact, but that is
    not sufficient: an artifact outlives its builder, and any artifact object
    reaching this serialiser from elsewhere would otherwise be digested as
    authoritative. Without this gate, moving every ``UNRESOLVED`` candidate
    into ``admitted`` yields a well-formed payload and a well-formed digest --
    a universe claiming knowledge its own recorded decisions do not establish.

    Required, exactly:

        admitted u rejected u unresolved == the recorded candidate identities
        the three partitions are pairwise disjoint
        each candidate's partition equals its recorded policy decision
        telemetry counts equal the partition sizes
    """
    by_decision: dict[str, set[str]] = {ADMIT: set(), REJECT: set(), UNRESOLVED: set()}
    for row in records:
        by_decision[row["decision"]].add(_canonical_json(row["identity"]))

    partitions = {
        ADMIT: [_identity_key(i) for i in artifact.admitted],
        REJECT: [_identity_key(i) for i in artifact.rejected],
        UNRESOLVED: [_identity_key(i) for i in artifact.unresolved],
    }
    for outcome, keys in partitions.items():
        if len(keys) != len(set(keys)):
            raise InvalidUniverseArtifact(
                f"partitions: duplicate identity inside the {outcome} partition"
            )
        if set(keys) != by_decision[outcome]:
            raise InvalidUniverseArtifact(
                f"partitions: {outcome} membership does not equal the candidates whose "
                f"recorded decision is {outcome}"
            )

    all_keys = [k for keys in partitions.values() for k in keys]
    if len(all_keys) != len(set(all_keys)):  # pragma: no cover - implied above
        raise InvalidUniverseArtifact("partitions: a candidate appears in more than one partition")
    recorded = [_canonical_json(row["identity"]) for row in records]
    if len(recorded) != len(set(recorded)):
        raise InvalidUniverseArtifact("candidate_records: duplicate exact candidate identity")
    if set(all_keys) != set(recorded):  # pragma: no cover - implied above
        raise InvalidUniverseArtifact("partitions: union does not equal the candidate roster")

    telemetry = artifact.telemetry
    if type(telemetry) is not ResolutionTelemetryV0:
        raise InvalidUniverseArtifact(
            f"telemetry: expected exactly ResolutionTelemetryV0, got {type(telemetry).__name__}"
        )
    expected = (
        len(recorded),
        len(partitions[ADMIT]),
        len(partitions[REJECT]),
        len(partitions[UNRESOLVED]),
    )
    actual = (
        telemetry.candidate_count,
        telemetry.admit_count,
        telemetry.reject_count,
        telemetry.unresolved_count,
    )
    if actual != expected:
        raise InvalidUniverseArtifact(
            f"telemetry: counts {actual} do not describe the partition {expected}"
        )
    if telemetry.roster_partition_complete is not True:
        # The only completeness this layer can compute is this one, and an
        # artifact that partitioned every candidate cannot deny it.
        raise InvalidUniverseArtifact(
            "telemetry: roster_partition_complete must be True for a formed artifact"
        )
    histogram: dict[str, int] = {}
    for row in records:
        for code in row["reason_codes"]:
            histogram[code] = histogram.get(code, 0) + 1
    if tuple(sorted(histogram.items())) != tuple(telemetry.reason_code_histogram):
        raise InvalidUniverseArtifact(
            "telemetry: reason_code_histogram does not describe the recorded decisions"
        )


def artifact_payload(artifact: PITUniverseCompositionArtifactV0) -> dict:
    """Canonical dict for one universe artifact.

    Fail-closed: an artifact that violates the exact-partition invariant, or
    whose telemetry does not describe its own records, has no canonical form
    and therefore no digest.
    """
    if type(artifact) is not PITUniverseCompositionArtifactV0:
        raise InvalidUniverseArtifact(
            f"artifact: expected exactly PITUniverseCompositionArtifactV0, got "
            f"{type(artifact).__name__}"
        )
    roster_ref = artifact.candidate_roster
    if type(roster_ref) is not RosterRefV0:
        raise InvalidUniverseArtifact(
            f"candidate_roster: expected exactly RosterRefV0, got {type(roster_ref).__name__}"
        )
    evidence_ref = artifact.evidence
    if type(evidence_ref) is not EvidenceSnapshotRefV0:
        raise InvalidUniverseArtifact(
            f"evidence: expected exactly EvidenceSnapshotRefV0, got {type(evidence_ref).__name__}"
        )
    records = [candidate_record_payload(r) for r in artifact.candidate_records]
    _require_exact_partition(artifact, records)
    return {
        "artifact_type": artifact.artifact_type,
        "artifact_version": artifact.artifact_version,
        "query": query_payload(artifact.query),
        "candidate_roster": {
            "roster_id": roster_ref.roster_id,
            "roster_version": roster_ref.roster_version,
            "scope": roster_ref.scope,
            "source_kind": roster_ref.source_kind,
            "completeness_claim": roster_ref.completeness_claim,
            "roster_digest": roster_ref.roster_digest,
        },
        "evidence": {
            "snapshot_id": evidence_ref.snapshot_id,
            "snapshot_version": evidence_ref.snapshot_version,
            "as_of": evidence_ref.as_of,
            "eligible_evidence_digest": evidence_ref.eligible_evidence_digest,
        },
        "admission_policy": {
            "policy_id": artifact.policy_id,
            "policy_version": artifact.policy_version,
            "policy_contract_digest": artifact.policy_contract_digest,
        },
        "builder": {
            "builder_id": artifact.builder_id,
            "builder_version": artifact.builder_version,
            "builder_contract_digest": artifact.builder_contract_digest,
        },
        "candidate_records": records,
        "partitions": {
            "admitted": [_identity_payload(i) for i in artifact.admitted],
            "rejected": [_identity_payload(i) for i in artifact.rejected],
            "unresolved": [_identity_payload(i) for i in artifact.unresolved],
        },
        "telemetry": telemetry_payload(artifact.telemetry),
        "partition_completeness_scope": artifact.partition_completeness_scope,
    }


def artifact_digest(artifact: PITUniverseCompositionArtifactV0) -> str:
    """Deterministic SHA-256 identity for one universe composition artifact."""
    return sha256(_canonical_json(artifact_payload(artifact)).encode()).hexdigest()


# --- Composition -------------------------------------------------------------


def compose_pit_universe(
    *,
    roster: CandidateRosterV0,
    evidence_snapshot: EvidenceSnapshotV0,
    query: UniverseQueryV0,
    expected_roster_digest: str | None = None,
    expected_evidence_snapshot_digest: str | None = None,
    expected_policy_id: str = POLICY_ID,
    expected_policy_version: str = POLICY_VERSION,
    expected_policy_contract_digest: str = POLICY_CONTRACT_DIGEST,
) -> PITUniverseCompositionArtifactV0:
    """Partition every exact candidate in ``roster`` into ADMITTED/REJECTED/UNRESOLVED.

    Pure and deterministic: no clock, no filesystem, no network, no randomness,
    no outcome or data-usability channel. The signature is the whole input
    surface, and it contains nothing about prices, funding, labels, future
    survival or backtest results.

    All-or-nothing: every structural check runs before the artifact is
    constructed, so a failed build leaves no partial universe behind.
    """
    # --- structural validation, all before any evaluation --------------------
    _require_roster(roster)
    _require_snapshot(evidence_snapshot)
    _require_query(query)

    if evidence_snapshot.as_of != query.as_of:
        # Binding the wrong snapshot to a query would silently answer a
        # different historical question than the artifact claims.
        raise InvalidEvidenceSnapshot(
            f"evidence_snapshot.as_of must equal query.as_of: "
            f"{evidence_snapshot.as_of!r} != {query.as_of!r}"
        )

    if (
        expected_policy_id != POLICY_ID
        or expected_policy_version != POLICY_VERSION
        or expected_policy_contract_digest != POLICY_CONTRACT_DIGEST
    ):
        raise PolicyIdentityMismatch(
            f"admission policy identity mismatch: expected "
            f"{expected_policy_id!r}/{expected_policy_version!r}/"
            f"{expected_policy_contract_digest!r}, linked "
            f"{POLICY_ID!r}/{POLICY_VERSION!r}/{POLICY_CONTRACT_DIGEST!r}"
        )

    computed_roster_digest = roster_digest(roster)
    if expected_roster_digest is not None and expected_roster_digest != computed_roster_digest:
        raise InvalidCandidateRoster(
            f"roster digest mismatch: expected {expected_roster_digest!r}, got "
            f"{computed_roster_digest!r}"
        )

    computed_evidence_digest = eligible_evidence_digest(evidence_snapshot)
    if (
        expected_evidence_snapshot_digest is not None
        and expected_evidence_snapshot_digest != computed_evidence_digest
    ):
        raise InvalidEvidenceSnapshot(
            f"evidence snapshot digest mismatch: expected "
            f"{expected_evidence_snapshot_digest!r}, got {computed_evidence_digest!r}"
        )

    # --- composition ---------------------------------------------------------
    # The eligible slice is computed once and shared read-only. It is the same
    # tuple for every candidate, so no candidate can influence another's input.
    slice_ = eligible_records(evidence_snapshot)

    records: list[UniverseCandidateRecordV0] = []
    admitted: list[InstrumentIdentity] = []
    rejected: list[InstrumentIdentity] = []
    unresolved: list[InstrumentIdentity] = []
    histogram: dict[str, int] = {}

    for candidate in canonical_candidates(roster):
        request = AdmissionRequest(
            identity=candidate,
            query_start=query.start,
            query_end=query.end,
            as_of=query.as_of,
        )
        decision = evaluate(request, slice_)

        if type(decision) is not AdmissionDecision:  # pragma: no cover - defensive
            raise InvalidUniverseBuild(
                f"policy returned {type(decision).__name__}, not AdmissionDecision"
            )
        if (
            decision.policy_id != expected_policy_id
            or decision.policy_version != expected_policy_version
            or decision.policy_contract_digest != expected_policy_contract_digest
        ):  # pragma: no cover - defensive; constants checked above
            raise PolicyIdentityMismatch(
                "decision does not carry the expected admission policy identity"
            )
        if decision.decision not in DECISIONS:  # pragma: no cover - defensive
            raise InvalidUniverseBuild(f"policy returned unknown outcome: {decision.decision!r}")

        # Verbatim. There is deliberately no branch here that could rewrite an
        # UNRESOLVED into anything else, for any reason, ever.
        if decision.decision == ADMIT:
            admitted.append(candidate)
        elif decision.decision == REJECT:
            rejected.append(candidate)
        else:
            unresolved.append(candidate)

        for code in decision.reason_codes:
            if code not in REASON_CODES:  # pragma: no cover - vocabulary is closed
                raise InvalidUniverseBuild(f"reason code outside the closed vocabulary: {code!r}")
            histogram[code] = histogram.get(code, 0) + 1

        records.append(
            UniverseCandidateRecordV0(identity=candidate, admission_decision=decision)
        )

    candidate_count = len(roster.candidates)
    partitioned = len(admitted) + len(rejected) + len(unresolved)
    if partitioned != candidate_count or len(records) != candidate_count:  # pragma: no cover
        raise InvalidUniverseBuild(
            f"partition is not exact: {partitioned} decisions for {candidate_count} candidates"
        )

    telemetry = ResolutionTelemetryV0(
        candidate_count=candidate_count,
        admit_count=len(admitted),
        reject_count=len(rejected),
        unresolved_count=len(unresolved),
        reason_code_histogram=tuple(sorted(histogram.items())),
        # Scoped by name and by PARTITION_COMPLETENESS_SCOPE: relative to this
        # roster, never a claim about the historical market universe.
        roster_partition_complete=True,
    )

    return PITUniverseCompositionArtifactV0(
        artifact_type=ARTIFACT_TYPE,
        artifact_version=ARTIFACT_VERSION,
        query=query,
        candidate_roster=RosterRefV0(
            roster_id=roster.roster_id,
            roster_version=roster.roster_version,
            scope=roster.scope,
            source_kind=roster.source_kind,
            completeness_claim=roster.completeness_claim,
            roster_digest=computed_roster_digest,
        ),
        evidence=EvidenceSnapshotRefV0(
            snapshot_id=evidence_snapshot.snapshot_id,
            snapshot_version=evidence_snapshot.snapshot_version,
            as_of=evidence_snapshot.as_of,
            eligible_evidence_digest=computed_evidence_digest,
        ),
        policy_id=POLICY_ID,
        policy_version=POLICY_VERSION,
        policy_contract_digest=POLICY_CONTRACT_DIGEST,
        builder_id=BUILDER_ID,
        builder_version=BUILDER_VERSION,
        builder_contract_digest=BUILDER_CONTRACT_DIGEST,
        candidate_records=tuple(records),
        admitted=tuple(sorted(admitted, key=_identity_key)),
        rejected=tuple(sorted(rejected, key=_identity_key)),
        unresolved=tuple(sorted(unresolved, key=_identity_key)),
        telemetry=telemetry,
        partition_completeness_scope=PARTITION_COMPLETENESS_SCOPE,
    )
