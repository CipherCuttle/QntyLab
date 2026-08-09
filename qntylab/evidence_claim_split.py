"""Evidence Claim Split V0 -- evidence non-escalation contract (artificial fixture).

One question only: can QntyLab represent what different evidence types actually
establish, without letting one evidence proposition silently manufacture
another?

Two axes are kept structurally separate and must never be collapsed:

    PROPOSITION DOMAIN   what is claimed
      - lifecycle boundary            (BoundaryProposition)
      - exact-time market observation (PointObservationProposition)
      - interval eligibility          (IntervalEligibilityProposition)

    EPISTEMIC STATUS     how well it is known
      - ESTABLISHED
      - UNKNOWN

``UNKNOWN`` is deliberately NOT a peer member of the proposition domain, and
there is deliberately NO negative status: absence of evidence can only ever
render as ``UNKNOWN``, never as a false/ineligible/not-tradable claim. That
vocabulary makes "absence of evidence became negative evidence" structurally
unrepresentable rather than merely untested.

Authority boundary: this module NEVER authenticates evidence. An
``EvidenceRecord`` is an artificial fact standing for evidence whose authority
was already established elsewhere. There is no ``authenticated=True`` switch,
no second lifecycle-authentication path, and nothing here writes to or reads
from the lifecycle ``EvidenceEvent`` stream. It only answers what may be
inferred AFTER evidence is already established.

Temporal model: two times, no temporal database.

    effective_time   when the claimed fact holds (valid time)
    available_time   when the evidence became knowable (available time)

A query carries an ``as_of`` causal cutoff; evidence with
``available_time > as_of`` is inadmissible for that query, even when its
``effective_time`` is in the past. This is the anti-lookahead rule.

Explicit non-claims for V0:

    * No final interval-eligibility policy. Interval eligibility is established
      only by an exactly-matching interval-eligibility proposition already in
      evidence. No coverage, containment, subsumption, interpolation, gap
      bridging, or derivation from boundaries/observations is implemented.
    * No continuity semantics across delist/relist. Distinct
      ``instrument_instance_id`` values are distinct instruments, full stop.
    * No temporal tolerance on observations. Exact effective_time only.
    * No present-state claim. Evidence whose ``effective_time`` is later than
      ``as_of`` (an announced future boundary, say) is admissible once its
      ``available_time`` has passed, because the proposition names its own
      effective time and asserting it establishes nothing about any earlier
      instant. Callers must not read a future-effective proposition as current
      state; V0 offers no "state now" query that could do so.
    * No subtype widening. Proposition and identity types are matched by exact
      type, so no subclass can be flattened into a broader domain payload.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Iterable, Union

from qntylab.market_observation import InstrumentIdentity


# --- Epistemic status (NOT a proposition) -----------------------------------

ESTABLISHED = "ESTABLISHED"
UNKNOWN = "UNKNOWN"

# Exactly two members. There is intentionally no REFUTED / FALSE / INELIGIBLE:
# V0 consumes only positive established facts, so no input path can produce a
# negative claim from missing evidence.
EPISTEMIC_STATUSES = frozenset({ESTABLISHED, UNKNOWN})


# --- Lifecycle boundary kinds -----------------------------------------------

LAUNCH = "LAUNCH"
DELIST = "DELIST"
BOUNDARY_KINDS = frozenset({LAUNCH, DELIST})


_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _require_timestamp(value: str, field: str) -> None:
    """Frozen ``YYYY-MM-DDTHH:MM:SSZ`` UTC shape, calendar-valid.

    The fixed-width UTC shape is what makes plain string comparison a correct
    chronological comparison everywhere else in this module.
    """
    if not isinstance(value, str) or not _TIMESTAMP_RE.match(value):
        raise ValueError(f"{field}: malformed timestamp: {value!r}")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError(f"{field}: not a real UTC instant: {value!r}") from None


def _require_non_empty(value: str, field: str) -> None:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise ValueError(f"{field}: must be a non-empty, unpadded string: {value!r}")


def _require_identity(identity: InstrumentIdentity) -> None:
    """Exact instrument-instance identity, reusing the lifecycle/observation type.

    Identity is never the ticker alone: symbol, market, contract_type and
    instrument_instance_id must all be present and all participate in equality.

    Exact type, not ``isinstance``: an ``InstrumentIdentity`` subclass carrying
    extra distinguishing fields would be flattened by ``_identity_payload`` and
    could collide with a different identity in the fixture digest. Widening is
    refused loudly.
    """
    if type(identity) is not InstrumentIdentity:
        raise ValueError(f"identity: expected exactly InstrumentIdentity, got {type(identity).__name__}")
    _require_non_empty(identity.symbol, "identity.symbol")
    _require_non_empty(identity.market, "identity.market")
    _require_non_empty(identity.contract_type, "identity.contract_type")
    _require_non_empty(identity.instrument_instance_id, "identity.instrument_instance_id")


# --- Proposition domain ------------------------------------------------------
#
# Three distinct types, not three members of one enum. Dataclass equality is
# type-sensitive, so a boundary proposition can never compare equal to an
# observation proposition even with identical field values -- that is the
# mechanism enforcing non-escalation between domains.


@dataclass(frozen=True)
class BoundaryProposition:
    """A lifecycle boundary of ``kind`` occurred for this exact instance at
    ``effective_time``.

    Establishes nothing about tradability before, after, or across that
    instant, and nothing about any interval.
    """
    identity: InstrumentIdentity
    kind: str
    effective_time: str

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        if self.kind not in BOUNDARY_KINDS:
            raise ValueError(f"kind: unknown lifecycle boundary kind: {self.kind!r}")
        _require_timestamp(self.effective_time, "effective_time")


@dataclass(frozen=True)
class PointObservationProposition:
    """This exact instrument instance was observed at this exact instant.

    Establishes nothing about any other instant, and nothing about any
    interval -- not even an interval whose endpoints are both observed.
    """
    identity: InstrumentIdentity
    effective_time: str

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        _require_timestamp(self.effective_time, "effective_time")


@dataclass(frozen=True)
class IntervalEligibilityProposition:
    """This exact instance was interval-eligible over ``[start, end]``.

    Represented only far enough to prove that boundary and observation
    evidence do not establish it. V0 implements no policy that derives this
    from anything else.
    """
    identity: InstrumentIdentity
    effective_start: str
    effective_end: str

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        _require_timestamp(self.effective_start, "effective_start")
        _require_timestamp(self.effective_end, "effective_end")
        if not self.effective_start < self.effective_end:
            raise ValueError(
                f"interval: effective_start must precede effective_end: "
                f"{self.effective_start!r} .. {self.effective_end!r}"
            )


Proposition = Union[
    BoundaryProposition,
    PointObservationProposition,
    IntervalEligibilityProposition,
]

_PROPOSITION_TYPES = frozenset({
    BoundaryProposition,
    PointObservationProposition,
    IntervalEligibilityProposition,
})


def _require_proposition(proposition: Proposition) -> None:
    """Admit exactly the three proposition types -- no subclasses.

    Subtype widening is a real escalation path: a subclass carrying extra
    distinguishing fields would serialise (and therefore digest) as its base
    domain, letting two different propositions share one fixture identity,
    while silently never matching in ``assess``. Refuse it at the door.
    """
    if type(proposition) not in _PROPOSITION_TYPES:
        raise ValueError(
            f"proposition: unsupported proposition type: {type(proposition).__name__}"
        )


# --- Evidence ----------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceRecord:
    """An already-established proposition, plus when it became knowable.

    This module does not authenticate: constructing a record asserts nothing
    about authority, it only carries an artificial fact whose authority was
    established by some other, unchanged system. ``source_key`` is provenance
    labelling for the receipt, never an authority grant.
    """
    proposition: Proposition
    available_time: str
    source_key: str

    def __post_init__(self) -> None:
        _require_proposition(self.proposition)
        _require_timestamp(self.available_time, "available_time")
        _require_non_empty(self.source_key, "source_key")


@dataclass(frozen=True)
class Assessment:
    """What is known about ONE proposition at ONE causal cutoff.

    ``status`` is an epistemic status, never a proposition. The assessed
    proposition is echoed back so a caller cannot lose track of which claim
    the status belongs to.
    """
    proposition: Proposition
    status: str
    as_of: str
    supporting_source_keys: tuple[str, ...]


def assess(evidence: Iterable[EvidenceRecord], proposition: Proposition, *, as_of: str) -> Assessment:
    """Assess exactly ``proposition`` against ``evidence`` at causal cutoff ``as_of``.

    A record supports the query only when all three hold:

      1. ``record.proposition == proposition`` -- exact structural equality,
         which is type-sensitive (domain), identity-sensitive (exact
         instrument instance), and effective-time-sensitive (exact instant or
         exact interval endpoints). No cross-domain, cross-instance,
         cross-variant, or near-in-time match exists.
      2. ``record.available_time <= as_of`` -- anti-lookahead.
      3. nothing else. There is no derivation, inference, bridging, or
         interpolation step anywhere in this function.

    Anything unsupported is ``UNKNOWN``. Malformed queries raise rather than
    silently reading as an evidence statement.
    """
    _require_proposition(proposition)
    _require_timestamp(as_of, "as_of")

    supporting: list[str] = []
    for record in evidence:
        if type(record) is not EvidenceRecord:
            raise ValueError(f"evidence: expected exactly EvidenceRecord, got {type(record).__name__}")
        if record.available_time > as_of:
            # Known only later than the query's causal cutoff: inadmissible
            # here regardless of how far in the past its effective_time is.
            continue
        if record.proposition == proposition:
            supporting.append(record.source_key)

    status = ESTABLISHED if supporting else UNKNOWN
    return Assessment(
        proposition=proposition,
        status=status,
        as_of=as_of,
        supporting_source_keys=tuple(sorted(supporting)),
    )


def is_established(assessment: Assessment) -> bool:
    """Strict, fail-closed read of an assessment. UNKNOWN is not eligible."""
    return assessment.status == ESTABLISHED


# --- Canonical serialisation / fixture identity ------------------------------


def _identity_payload(identity: InstrumentIdentity) -> dict:
    return {
        "symbol": identity.symbol,
        "market": identity.market,
        "contract_type": identity.contract_type,
        "instrument_instance_id": identity.instrument_instance_id,
    }


def proposition_payload(proposition: Proposition) -> dict:
    """Canonical dict for one proposition, tagged with its domain.

    ``proposition_domain`` is emitted so the split survives serialisation: two
    propositions of different domains can never round-trip into each other.
    Dispatch is on exact type, so no subtype can be flattened into a domain
    payload that omits its distinguishing fields.
    """
    _require_proposition(proposition)
    if type(proposition) is BoundaryProposition:
        return {
            "proposition_domain": "LIFECYCLE_BOUNDARY",
            "identity": _identity_payload(proposition.identity),
            "kind": proposition.kind,
            "effective_time": proposition.effective_time,
        }
    if type(proposition) is PointObservationProposition:
        return {
            "proposition_domain": "POINT_MARKET_OBSERVATION",
            "identity": _identity_payload(proposition.identity),
            "effective_time": proposition.effective_time,
        }
    if type(proposition) is IntervalEligibilityProposition:
        return {
            "proposition_domain": "INTERVAL_ELIGIBILITY",
            "identity": _identity_payload(proposition.identity),
            "effective_start": proposition.effective_start,
            "effective_end": proposition.effective_end,
        }
    raise ValueError(f"proposition: unsupported proposition type: {type(proposition).__name__}")


def evidence_payload(record: EvidenceRecord) -> dict:
    return {
        "proposition": proposition_payload(record.proposition),
        "available_time": record.available_time,
        "source_key": record.source_key,
    }


def fixture_digest(evidence: Iterable[EvidenceRecord]) -> str:
    """Deterministic SHA-256 identity for an evidence fixture, order-insensitive."""
    rows = [evidence_payload(record) for record in evidence]
    canonical = json.dumps(
        sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":"))),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(canonical.encode()).hexdigest()
