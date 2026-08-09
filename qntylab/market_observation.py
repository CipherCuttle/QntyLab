"""Authenticated point-in-time market observation, orthogonal to lifecycle state.

Model B (parallel point evidence): a market observation is a claim that a
matching trade was authenticated in a capture at an exact timestamp for an
exact instrument identity. It is evidence about what was seen in a capture,
never a lifecycle transition. It MUST NOT be written into the lifecycle
``EvidenceEvent`` stream, and it MUST NOT influence ``state_at()`` /
``eligible_at()`` in either direction (no bridging a suspension, no
retroactive change to an already-computed state, no reviving a terminated
instance).

CMS (capture management / provenance) is required only to establish capture
*boundaries* (what a capture covers and its integrity) -- never to promote an
observation into a lifecycle claim. This module has no CMS, no network, and
no archive downloader; captures are supplied in-memory by the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


# Finite result vocabulary. Deliberately not a bool: a market observation
# result must never be confused with a lifecycle TRADABLE/NOT_TRADABLE claim.
OBSERVED = "OBSERVED"
NOT_OBSERVED_IN_CAPTURE = "NOT_OBSERVED_IN_CAPTURE"  # capture examined, no exact match -- NOT a NOT_TRADABLE claim
UNKNOWN = "UNKNOWN"
INVALID = "INVALID"

RESULTS = frozenset({OBSERVED, NOT_OBSERVED_IN_CAPTURE, UNKNOWN, INVALID})

# Structural conventions frozen by this fixture. Deliberately minimal: this is
# not a general validation library, just the smallest structural gate needed
# to keep malformed/forged evidence from reading as genuine.
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _non_empty(value: str) -> bool:
    return isinstance(value, str) and value.strip() != "" and value == value.strip()


def _valid_identity(identity: InstrumentIdentity) -> bool:
    return (
        isinstance(identity, InstrumentIdentity)
        and _non_empty(identity.symbol)
        and _non_empty(identity.market)
        and _non_empty(identity.contract_type)
        and _non_empty(identity.instrument_instance_id)
    )


def _valid_timestamp(at: str) -> bool:
    # Syntax (frozen YYYY-MM-DDTHH:MM:SSZ shape) AND calendar/clock validity
    # both must hold. The regex alone accepts calendar-impossible strings
    # like "2026-02-31T12:00:00Z"; strptime rejects those while still
    # requiring the exact two-digit fields the regex enforces (it will not
    # silently accept "2026-1-1..." because the regex boundary runs first).
    if not isinstance(at, str) or not _TIMESTAMP_RE.match(at):
        return False
    try:
        datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _valid_source_key(source_key: str) -> bool:
    return _non_empty(source_key)


def _valid_hash(value: str) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.match(value))


@dataclass(frozen=True)
class InstrumentIdentity:
    """Exact identity an observation or query is scoped to.

    Reuses lifecycle's instrument-instance semantics: identity is not the
    ticker string alone. Two rows with the same ``symbol`` but different
    ``instrument_instance_id`` (e.g. a delisted-then-relisted ticker) are
    different instruments and never satisfy each other's queries.
    """
    symbol: str
    market: str
    contract_type: str
    instrument_instance_id: str


@dataclass(frozen=True)
class MarketObservation:
    """One authenticated trade observation inside a capture.

    This is deliberately not an ``EvidenceEvent``: it carries no lifecycle
    ``claim`` and is never appended to a lifecycle event stream.

    ``source_key`` / ``local_content_sha256`` are this observation's own
    provenance claim -- where it says it came from. ``observed_at`` binds
    this against the capture's frozen provenance before trusting it; an
    observation whose provenance disagrees with the capture it is found in
    is conflicting evidence, not genuine evidence.
    """
    identity: InstrumentIdentity
    timestamp: str
    source_key: str
    local_content_sha256: str


@dataclass(frozen=True)
class Capture:
    """An examined, integrity-checked set of observations for one identity.

    ``source_key`` / ``local_content_sha256`` are the capture's own frozen
    provenance: the exact source artifact this capture was built from. Any
    observation admitted as evidence for this capture must carry matching
    provenance -- otherwise it is an injected/foreign observation, not
    evidence this capture actually contains.

    ``valid`` models capture/identity/integrity validity (section 4/9 of the
    fixture spec). An invalid or absent capture never becomes a lifecycle
    claim; it only ever yields INVALID or UNKNOWN observation results.
    """
    identity: InstrumentIdentity
    observations: tuple[MarketObservation, ...]
    source_key: str
    local_content_sha256: str
    valid: bool = True


def _valid_capture(capture: Capture) -> bool:
    """Capture-level structural/provenance validity, independent of any query."""
    return (
        capture.valid
        and _valid_identity(capture.identity)
        and _valid_source_key(capture.source_key)
        and _valid_hash(capture.local_content_sha256)
    )


def _valid_observation_for_capture(observation: MarketObservation, capture: Capture) -> bool:
    """One stored observation's structural validity AND provenance binding to
    ``capture``. Deliberately identity/timestamp-agnostic: whether a row is
    genuine evidence must not depend on whether it happens to be the row a
    caller is looking for."""
    if (
        not _valid_identity(observation.identity)
        or not _valid_timestamp(observation.timestamp)
        or not _valid_source_key(observation.source_key)
        or not _valid_hash(observation.local_content_sha256)
    ):
        return False

    # Provenance binding: every stored observation must belong to this exact
    # capture. A foreign observation injected into this capture's tuple (e.g.
    # carrying another capture's source_key/hash) is conflicting evidence,
    # even if it is irrelevant to the current lookup.
    return (
        observation.source_key == capture.source_key
        and observation.local_content_sha256 == capture.local_content_sha256
    )


def observed_at(capture: Capture | None, identity: InstrumentIdentity, at: str) -> str:
    """Exact-timestamp, exact-identity observation lookup. No temporal tolerance.

    Returns one of OBSERVED / NOT_OBSERVED_IN_CAPTURE / UNKNOWN / INVALID.
    This function only reads ``capture``; it never constructs an
    ``EvidenceEvent`` and never touches a lifecycle event stream.

    Every stored observation in the capture is validated -- structurally and
    for provenance binding -- before any lookup is attempted, regardless of
    whether that observation matches the query. A capture's validity must
    never depend on which timestamp happens to be queried.
    """
    if capture is None:
        return UNKNOWN

    # 1. Capture structure/provenance must itself be well-formed before it
    # can be trusted to answer anything.
    if not _valid_capture(capture):
        return INVALID

    # 2. Every stored observation must be structurally valid AND
    # provenance-bound to this capture -- unconditionally, not just the ones
    # that happen to match the query's identity/timestamp. A malformed or
    # foreign row anywhere in the capture makes the whole capture untrusted
    # evidence.
    for observation in capture.observations:
        if not _valid_observation_for_capture(observation, capture):
            return INVALID

    # 3. Query identity/timestamp must be structurally valid evidence, not
    # just absent from the capture.
    if not _valid_identity(identity) or not _valid_timestamp(at):
        return INVALID

    if capture.identity != identity:
        # Wrong market / wrong instrument instance: an otherwise valid
        # capture for a different identity must never satisfy this query.
        return INVALID

    # 4. Exact observation lookup: every remaining candidate is already
    # known-valid and provenance-bound, so this is a pure identity/timestamp
    # match.
    for observation in capture.observations:
        if observation.identity == identity and observation.timestamp == at:
            return OBSERVED

    return NOT_OBSERVED_IN_CAPTURE


def observations_by_identity(observations: Iterable[MarketObservation], identity: InstrumentIdentity) -> tuple[MarketObservation, ...]:
    """Convenience filter; still identity-exact, still no lifecycle side effect."""
    return tuple(observation for observation in observations if observation.identity == identity)
