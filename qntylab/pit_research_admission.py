"""PIT Research Admission Policy V0 (project name: Interval Eligibility Policy V0).

One question only: may this EXACT instrument identity enter a historical
research calculation over ``[query_start, query_end)``, using only evidence
available by the query's ``as_of``?

This is layer 2 of three, and only layer 2:

    1. EVIDENCE CLAIMS          what do we know, from what, and when?
                                -> qntylab.evidence_claim_split (frozen, unmodified)
    2. PIT RESEARCH ADMISSION   may this instrument enter this calculation?
                                -> this module
    3. DATA / OUTCOME USABILITY can features/labels/prices/funding be computed?
                                -> not implemented, and unreachable from here

Layer 3 has no channel into this module: the evaluator's entire input is one
``AdmissionRequest`` plus ``EvidenceRecord`` objects. Missing price data,
missing funding, missing experiment files, label computability, eventual
delisting, future survival and strategy outcomes therefore cannot become
lifecycle/admission evidence.

A policy decision is NOT an evidence proposition. The output vocabulary is
deliberately ``ADMIT``/``REJECT``/``UNRESOLVED`` rather than
eligible/ineligible/unknown, and this module never constructs an
``IntervalEligibilityProposition`` from its own conclusion: a decision cannot
re-enter as evidence.

Fail-closed by construction:

    * malformed / non-PIT requests raise ``InvalidPITQuery`` and never produce
      a decision object, so an invalid query can never read as ``REJECT``;
    * every ``REJECT`` requires an ESTABLISHED boundary proposition, so absence
      of evidence has no path to a negative outcome;
    * conflicting established evidence resolves to ``UNRESOLVED``, never by
      first-seen / last-seen / newest-effective / convenience;
    * anything else unproven is ``UNRESOLVED``.

Hard PIT rule: evidence is filtered by ``available_time <= as_of`` BEFORE any
other property of the dataset is observed -- before ground detection, identity
partitioning and diagnostics alike. Every field of the returned decision
(outcome, reason codes, evidence basis, digest) is therefore invariant under
adding evidence that becomes available after ``as_of``. There is deliberately
no ``FUTURE_KNOWN_EVIDENCE_EXCLUDED`` reason code: a code that acknowledged
future-known evidence would make future knowledge observable in a historical
decision, which is the exact leak this layer exists to prevent.

See ``docs/forensics/PIT_RESEARCH_ADMISSION_V0_CONTRACT.md`` for the frozen
contract. Artificial fixture only: no network, no filesystem, no clock, no
Qnty / QntyPolicyGate / Router / Jigsaw coupling, no backtest.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable

from qntylab.evidence_claim_split import (
    BoundaryProposition,
    DELIST,
    EvidenceRecord,
    IntervalEligibilityProposition,
    LAUNCH,
    PointObservationProposition,
    Proposition,
    _require_identity,
    _require_timestamp,
    assess,
    is_established,
    proposition_payload,
)
from qntylab.market_observation import InstrumentIdentity


# --- Policy identity ---------------------------------------------------------

POLICY_ID = "qntylab.pit_research_admission"
POLICY_VERSION = "v0"


# --- Decision vocabulary (policy actions, NOT world-state claims) ------------

ADMIT = "ADMIT"
REJECT = "REJECT"
UNRESOLVED = "UNRESOLVED"

DECISIONS = frozenset({ADMIT, REJECT, UNRESOLVED})


# --- Reason codes (small closed vocabulary) ----------------------------------

# ADMIT grounds
INTERVAL_CLAIM_COVERS_QUERY = "INTERVAL_CLAIM_COVERS_QUERY"
BOUNDARY_WINDOW_COVERS_QUERY = "BOUNDARY_WINDOW_COVERS_QUERY"

# REJECT grounds
DELIST_AT_OR_BEFORE_QUERY_START = "DELIST_AT_OR_BEFORE_QUERY_START"
DELIST_INSIDE_QUERY = "DELIST_INSIDE_QUERY"
LAUNCH_AT_OR_AFTER_QUERY_END = "LAUNCH_AT_OR_AFTER_QUERY_END"
LAUNCH_INSIDE_QUERY = "LAUNCH_INSIDE_QUERY"

# UNRESOLVED reasons
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
NO_EXACT_IDENTITY_EVIDENCE = "NO_EXACT_IDENTITY_EVIDENCE"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL = "POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL"

ADMIT_GROUND_CODES = frozenset({
    INTERVAL_CLAIM_COVERS_QUERY,
    BOUNDARY_WINDOW_COVERS_QUERY,
})

REJECT_GROUND_CODES = frozenset({
    DELIST_AT_OR_BEFORE_QUERY_START,
    DELIST_INSIDE_QUERY,
    LAUNCH_AT_OR_AFTER_QUERY_END,
    LAUNCH_INSIDE_QUERY,
})

REASON_CODES = frozenset(
    ADMIT_GROUND_CODES
    | REJECT_GROUND_CODES
    | {
        CONFLICTING_EVIDENCE,
        INSUFFICIENT_EVIDENCE,
        NO_EXACT_IDENTITY_EVIDENCE,
        IDENTITY_MISMATCH,
        POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL,
    }
)

# Roles an evidence-basis entry can play. A basis entry records which frozen
# rule consumed the proposition; it is never itself a claim.
ADMIT_GROUND = "ADMIT_GROUND"
REJECT_GROUND = "REJECT_GROUND"
BASIS_ROLES = frozenset({ADMIT_GROUND, REJECT_GROUND})


# --- Frozen rule spec (the thing POLICY_CONTRACT_DIGEST commits to) ----------
#
# A literal, canonical statement of every frozen rule. Changing any rule changes
# POLICY_CONTRACT_DIGEST, so a historical decision can be traced to the exact
# policy that produced it. This is not a policy registry and holds no state.

_RULE_SPEC = {
    "policy_id": POLICY_ID,
    "policy_version": POLICY_VERSION,
    "query_interval": "[query_start, query_end)",
    "pit_rule": "query_end <= as_of",
    "evidence_admissibility": "available_time <= as_of",
    "identity_rule": "proposition.identity == request.identity (exact InstrumentIdentity equality, all four fields)",
    "establishment_gate": "evidence_claim_split.assess(...) status == ESTABLISHED",
    "admit_grounds": [
        {
            "code": INTERVAL_CLAIM_COVERS_QUERY,
            "rule": "IntervalEligibilityProposition with effective_start <= query_start and effective_end >= query_end",
        },
        {
            "code": BOUNDARY_WINDOW_COVERS_QUERY,
            "rule": "LAUNCH with effective_time <= query_start AND DELIST with effective_time >= query_end",
        },
    ],
    "reject_grounds": [
        {"code": DELIST_AT_OR_BEFORE_QUERY_START, "rule": "DELIST with effective_time <= query_start"},
        {"code": DELIST_INSIDE_QUERY, "rule": "DELIST with query_start < effective_time < query_end"},
        {"code": LAUNCH_AT_OR_AFTER_QUERY_END, "rule": "LAUNCH with effective_time >= query_end"},
        {"code": LAUNCH_INSIDE_QUERY, "rule": "LAUNCH with query_start < effective_time < query_end"},
    ],
    "observation_rule": "PointObservationProposition is never an admission ground in either direction",
    "resolution": {
        "admit_and_reject": "UNRESOLVED + CONFLICTING_EVIDENCE",
        "admit_only": ADMIT,
        "reject_only": REJECT,
        "neither": "UNRESOLVED + INSUFFICIENT_EVIDENCE",
    },
    "whole_interval": "admission is all-or-nothing; no truncation, no partial interval, no repaired interval",
    "invalid_query": "InvalidPITQuery raised at request construction; never a decision",
    "absence_rule": "absence of evidence never produces REJECT",
    "feedback_rule": "no decision is ever converted into an evidence proposition",
}


def _canonical_json(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


POLICY_CONTRACT_DIGEST = sha256(_canonical_json(_RULE_SPEC).encode()).hexdigest()


# --- Request -----------------------------------------------------------------


class InvalidPITQuery(ValueError):
    """A malformed or non-point-in-time request.

    Deliberately an exception and not a decision outcome: ``query_end > as_of``
    means "invalid PIT query", never "this instrument was rejected from the
    universe". Request-validation failure and policy outcome share no channel.
    """


@dataclass(frozen=True)
class AdmissionRequest:
    """One historical research-admission question about one exact instrument.

    Validation is fail-closed and happens at construction, so no downstream
    code can hold a malformed request.
    """
    identity: InstrumentIdentity
    query_start: str
    query_end: str
    as_of: str

    def __post_init__(self) -> None:
        try:
            _require_identity(self.identity)
            _require_timestamp(self.query_start, "query_start")
            _require_timestamp(self.query_end, "query_end")
            _require_timestamp(self.as_of, "as_of")
        except ValueError as exc:
            raise InvalidPITQuery(str(exc)) from None
        if not self.query_start < self.query_end:
            raise InvalidPITQuery(
                f"query interval: query_start must precede query_end: "
                f"{self.query_start!r} .. {self.query_end!r}"
            )
        if self.query_end > self.as_of:
            # Not a rejection: a request to use knowledge the query claims not
            # to have. The only safe response is to refuse the question.
            raise InvalidPITQuery(
                f"non-PIT query: query_end must not exceed as_of: "
                f"{self.query_end!r} > {self.as_of!r}"
            )


# --- Decision ----------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceBasisEntry:
    """Exactly which established proposition the policy consumed, and how.

    ``supporting_source_keys`` comes from the predecessor assessment, so the
    basis names real evidence rather than the policy's own reasoning.
    """
    role: str
    proposition: Proposition
    supporting_source_keys: tuple[str, ...]


@dataclass(frozen=True)
class AdmissionDecision:
    """A policy action about one historical query. Never an evidence claim."""
    request: AdmissionRequest
    decision: str
    reason_codes: tuple[str, ...]
    evidence_basis: tuple[EvidenceBasisEntry, ...]
    policy_id: str
    policy_version: str
    policy_contract_digest: str


# --- Evaluation --------------------------------------------------------------


def _admissible_records(evidence: Iterable[EvidenceRecord], as_of: str) -> tuple[EvidenceRecord, ...]:
    """Apply the hard PIT cutoff first, before observing anything else.

    Nothing downstream -- grounds, identity partitioning, diagnostics, digest --
    sees a record that was not knowable by ``as_of``. That ordering is what
    makes the whole decision invariant under future evidence, rather than only
    its outcome.
    """
    admissible: list[EvidenceRecord] = []
    for record in evidence:
        if type(record) is not EvidenceRecord:
            raise ValueError(f"evidence: expected exactly EvidenceRecord, got {type(record).__name__}")
        if record.available_time <= as_of:
            admissible.append(record)
    return tuple(admissible)


def _established(
    admissible: tuple[EvidenceRecord, ...],
    proposition: Proposition,
    as_of: str,
) -> tuple[str, ...] | None:
    """Predecessor gate. Returns supporting source keys, or ``None`` if UNKNOWN.

    The single establishment path in this module: Evidence Claim Split decides
    what is established, this module only decides what to do about it. An
    UNKNOWN proposition contributes nothing, in any quantity -- it is never
    negative evidence.
    """
    assessment = assess(admissible, proposition, as_of=as_of)
    if not is_established(assessment):
        return None
    # Deduplicated: the basis names which sources support the ground, so an
    # evidence set that repeats one identical record must not produce a
    # different canonical decision. The predecessor assessment is left as-is.
    return tuple(sorted(set(assessment.supporting_source_keys)))


def evaluate(request: AdmissionRequest, evidence: Iterable[EvidenceRecord]) -> AdmissionDecision:
    """Decide whether ``request.identity`` may enter a calculation over the query.

    Pure and deterministic: no clock, no filesystem, no network, no outcome
    channel. Grounds are collected as sets, so input order cannot change the
    decision, reason codes, evidence basis or digest.
    """
    if type(request) is not AdmissionRequest:
        raise InvalidPITQuery(f"request: expected exactly AdmissionRequest, got {type(request).__name__}")

    as_of = request.as_of
    start = request.query_start
    end = request.query_end

    admissible = _admissible_records(evidence, as_of)

    exact: list[Proposition] = []
    foreign_identity_seen = False
    for record in admissible:
        if record.proposition.identity == request.identity:
            exact.append(record.proposition)
        else:
            # Generic-asset, wrong-venue, wrong-contract-type and relisted-
            # instance evidence all land here and bind nothing.
            foreign_identity_seen = True

    launches = {
        p for p in exact
        if type(p) is BoundaryProposition and p.kind == LAUNCH
    }
    delists = {
        p for p in exact
        if type(p) is BoundaryProposition and p.kind == DELIST
    }
    intervals = {p for p in exact if type(p) is IntervalEligibilityProposition}
    observations = {p for p in exact if type(p) is PointObservationProposition}

    admit_codes: set[str] = set()
    reject_codes: set[str] = set()
    basis: set[EvidenceBasisEntry] = set()

    def _ground(role: str, code: str, propositions: Iterable[Proposition]) -> bool:
        """Record a firing ground, but only for established propositions."""
        fired = False
        for proposition in sorted(propositions, key=lambda p: _canonical_json(proposition_payload(p))):
            keys = _established(admissible, proposition, as_of)
            if keys is None:
                continue
            fired = True
            basis.add(EvidenceBasisEntry(role=role, proposition=proposition, supporting_source_keys=keys))
        if fired:
            (admit_codes if role == ADMIT_GROUND else reject_codes).add(code)
        return fired

    # ADMIT ground 1: an eligibility claim that already covers the whole query.
    # Entailment inside one proposition domain (wider interval -> sub-interval),
    # never a cross-domain escalation.
    _ground(
        ADMIT_GROUND,
        INTERVAL_CLAIM_COVERS_QUERY,
        [p for p in intervals if p.effective_start <= start and p.effective_end >= end],
    )

    # ADMIT ground 2: both edges positively established. A launch alone does not
    # admit: "no delist evidence" is absence of evidence and must not close the
    # right edge.
    covering_launches = [p for p in launches if p.effective_time <= start]
    covering_delists = [p for p in delists if p.effective_time >= end]
    if covering_launches and covering_delists:
        left = _ground(ADMIT_GROUND, BOUNDARY_WINDOW_COVERS_QUERY, covering_launches)
        right = _ground(ADMIT_GROUND, BOUNDARY_WINDOW_COVERS_QUERY, covering_delists)
        if not (left and right):
            # One edge was UNKNOWN: the window is not established. Withdraw the
            # code and the half-basis rather than admitting on one edge.
            admit_codes.discard(BOUNDARY_WINDOW_COVERS_QUERY)
            basis = {
                entry for entry in basis
                if not (entry.role == ADMIT_GROUND and type(entry.proposition) is BoundaryProposition)
            }

    # REJECT grounds: each requires an established boundary. Whole-interval
    # semantics -- a boundary strictly inside the query establishes that part of
    # the requested interval is outside the instrument's existence, so the
    # interval as requested must not be admitted. V0 never truncates.
    _ground(REJECT_GROUND, DELIST_AT_OR_BEFORE_QUERY_START, [p for p in delists if p.effective_time <= start])
    _ground(REJECT_GROUND, DELIST_INSIDE_QUERY, [p for p in delists if start < p.effective_time < end])
    _ground(REJECT_GROUND, LAUNCH_AT_OR_AFTER_QUERY_END, [p for p in launches if p.effective_time >= end])
    _ground(REJECT_GROUND, LAUNCH_INSIDE_QUERY, [p for p in launches if start < p.effective_time < end])

    if admit_codes and reject_codes:
        # No precedence model exists, and inventing one here would let whichever
        # claim is convenient win. Fail closed.
        decision = UNRESOLVED
        codes = {CONFLICTING_EVIDENCE} | admit_codes | reject_codes
    elif admit_codes:
        decision = ADMIT
        codes = set(admit_codes)
    elif reject_codes:
        decision = REJECT
        codes = set(reject_codes)
    else:
        decision = UNRESOLVED
        codes = {INSUFFICIENT_EVIDENCE}
        if not exact:
            codes.add(NO_EXACT_IDENTITY_EVIDENCE)
        if foreign_identity_seen:
            codes.add(IDENTITY_MISMATCH)
        if any(start <= p.effective_time < end for p in observations):
            # An exact-time observation inside the interval is a diagnostic
            # only: it never establishes continuous interval existence.
            codes.add(POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL)
        basis = set()

    unknown_codes = codes - REASON_CODES
    if unknown_codes:  # pragma: no cover - defensive; vocabulary is closed
        raise AssertionError(f"reason codes outside the closed vocabulary: {sorted(unknown_codes)}")

    return AdmissionDecision(
        request=request,
        decision=decision,
        reason_codes=tuple(sorted(codes)),
        evidence_basis=tuple(
            sorted(basis, key=lambda entry: _canonical_json(_basis_payload(entry)))
        ),
        policy_id=POLICY_ID,
        policy_version=POLICY_VERSION,
        policy_contract_digest=POLICY_CONTRACT_DIGEST,
    )


# --- Canonical serialisation / decision identity -----------------------------


def _basis_payload(entry: EvidenceBasisEntry) -> dict:
    # Exact type, not isinstance: a subclass carrying extra distinguishing
    # fields would serialise as the base entry, letting two different decisions
    # share one decision_digest. Same widening class as the predecessor's H-1.
    if type(entry) is not EvidenceBasisEntry:
        raise ValueError(
            f"evidence_basis: expected exactly EvidenceBasisEntry, got {type(entry).__name__}"
        )
    if entry.role not in BASIS_ROLES:  # pragma: no cover - defensive
        raise ValueError(f"role: unsupported evidence-basis role: {entry.role!r}")
    return {
        "role": entry.role,
        # Predecessor payload: carries the proposition_domain tag, so the claim
        # split survives serialisation and two domains cannot collide.
        "proposition": proposition_payload(entry.proposition),
        "supporting_source_keys": list(entry.supporting_source_keys),
    }


def request_payload(request: AdmissionRequest) -> dict:
    if type(request) is not AdmissionRequest:
        raise InvalidPITQuery(f"request: expected exactly AdmissionRequest, got {type(request).__name__}")
    return {
        "identity": {
            "symbol": request.identity.symbol,
            "market": request.identity.market,
            "contract_type": request.identity.contract_type,
            "instrument_instance_id": request.identity.instrument_instance_id,
        },
        "query_start": request.query_start,
        "query_end": request.query_end,
        "as_of": request.as_of,
    }


def decision_payload(decision: AdmissionDecision) -> dict:
    if type(decision) is not AdmissionDecision:
        raise ValueError(f"decision: expected exactly AdmissionDecision, got {type(decision).__name__}")
    if decision.decision not in DECISIONS:  # pragma: no cover - defensive
        raise ValueError(f"decision: unsupported outcome: {decision.decision!r}")
    return {
        "policy_id": decision.policy_id,
        "policy_version": decision.policy_version,
        "policy_contract_digest": decision.policy_contract_digest,
        "request": request_payload(decision.request),
        "decision": decision.decision,
        "reason_codes": sorted(decision.reason_codes),
        "evidence_basis": sorted(
            (_basis_payload(entry) for entry in decision.evidence_basis),
            key=_canonical_json,
        ),
    }


def decision_digest(decision: AdmissionDecision) -> str:
    """Deterministic SHA-256 identity for one historical admission decision."""
    return sha256(_canonical_json(decision_payload(decision)).encode()).hexdigest()
