# Evidence Claim Split V0 — Contract

Conceptual objective: **Evidence Non-Escalation Contract**.

Question answered by this phase, and only this question:

> Can QntyLab represent what different evidence types actually establish without allowing one evidence proposition to silently manufacture another?

Artificial fixture only. No network, no Binance acquisition, no source discovery, no PIT universe, no Router / Jigsaw / Qnty / QntyPolicyGate integration.

## Two Axes, Never Collapsed

`qntylab/evidence_claim_split.py` keeps two axes structurally separate.

| Axis | Members | Representation |
| --- | --- | --- |
| Proposition domain (what is claimed) | lifecycle boundary; exact-time market observation; interval eligibility | three distinct frozen dataclasses: `BoundaryProposition`, `PointObservationProposition`, `IntervalEligibilityProposition` |
| Epistemic status (how well it is known) | `ESTABLISHED`, `UNKNOWN` | a two-member string vocabulary on `Assessment.status` |

`UNKNOWN` is not a peer member of the proposition domain. There is deliberately **no negative status** (`FALSE` / `REFUTED` / `INELIGIBLE` / `NOT_TRADABLE`), which makes "absence of evidence became negative evidence" structurally unrepresentable rather than merely untested.

Non-escalation across domains is enforced by dataclass equality, which is type-sensitive: a `BoundaryProposition` can never compare equal to a `PointObservationProposition` even with identical field values.

## Evidence and Assessment

```
EvidenceRecord(proposition, available_time, source_key)
assess(evidence, proposition, *, as_of) -> Assessment(proposition, status, as_of, supporting_source_keys)
```

A record supports a query iff **both** hold, with no derivation step anywhere:

1. `record.proposition == proposition` — exact structural equality. Type-sensitive (domain), identity-sensitive (exact instrument instance), effective-time-sensitive (exact instant, or exact interval endpoints).
2. `record.available_time <= as_of` — anti-lookahead admissibility.

Anything unsupported is `UNKNOWN`. Malformed queries and malformed evidence raise `ValueError` rather than silently reading as an evidence statement.

## Temporal Model

Two times, no temporal database:

| Field | Meaning |
| --- | --- |
| `effective_time` / `effective_start` / `effective_end` | when the claimed fact holds (valid time) |
| `available_time` | when the evidence became knowable (available time) |

Query cutoff is `as_of`. Evidence with `available_time > as_of` is inadmissible for that query regardless of how far in the past its `effective_time` is. Timestamps are the frozen fixed-width UTC shape `YYYY-MM-DDTHH:MM:SSZ`, calendar-validated, so string comparison is chronological comparison.

## Exact Instrument Identity

Identity reuses `qntylab.market_observation.InstrumentIdentity` (`symbol`, `market`, `contract_type`, `instrument_instance_id`), all four participating in equality. `BTC` ≠ `BTCUSDT spot` ≠ `BTCUSDT usd-m perpetual` ≠ a later relisted `BTCUSDT` perpetual instance. Proposition and identity types are matched by **exact type**, so no subclass can be widened into a broader domain payload.

## Authority Boundary

This module never authenticates evidence. An `EvidenceRecord` is an artificial fact standing for evidence whose authority was established elsewhere. There is no caller-controlled `authenticated=True` switch, no `grade` / `verified` / `trusted` field, and no second lifecycle-authentication path. The module imports nothing from `qntylab.lifecycle`; the only `qntylab` import is the shared identity type. Both properties are asserted by AST-level tests.

`qntylab/lifecycle.py`, `qntylab/market_observation.py`, `qntylab/binance_um_archive.py`, Qnty, QntyPolicyGate and THT0 are unmodified. V0 is built beside the existing state machine, not on top of it.

## Explicit Non-Claims

* **No final interval-eligibility policy.** Interval eligibility is established only by an exactly-matching interval-eligibility proposition already in evidence. No coverage, containment, subsumption, interpolation, gap bridging, or derivation from boundaries/observations is implemented. Deciding that policy is the next phase.
* **No continuity semantics across delist/relist.** Distinct `instrument_instance_id` values are distinct instruments; nothing inherits.
* **No temporal tolerance.** Observations match at the exact instant only.
* **No present-state claim.** Evidence whose `effective_time` is later than `as_of` (an announced future boundary) is admissible once its `available_time` has passed, because the proposition names its own effective time and establishes nothing about any earlier instant. V0 exposes no "state now" query that could misread it.
* Not a lifecycle authority, not a tradability claim, not a research candidate, not a universe.

## Frozen Falsifier Matrix

| ID | Fixture | Required outcome |
| --- | --- | --- |
| F1 | observations at 11:00 and 13:00, query 12:00 | 12:00 `UNKNOWN`; interval 11→13 `UNKNOWN` |
| F2 | instance A evidence, instance B query (relist) | `UNKNOWN`, both directions |
| F3 | launch boundary 08:00 established | no observation at 08:00/09:00; no interval established |
| F4 | one evidence record removed | that proposition `UNKNOWN`, never negative; siblings unmoved |
| F5 | `BTCUSDT` spot ↔ `BTCUSDT` usd-m perpetual | `UNKNOWN`, both directions |
| F6 | generic `BTC` asset evidence | binds no instrument instance |
| F7 | `effective_time <= as_of < available_time` | inadmissible; admissible only from `available_time` onward |
| F8 | no evidence at all | every proposition `UNKNOWN`, no implicit negative |

## Central Success Example

```
launch boundary:        ESTABLISHED
observation @ 11:00:    ESTABLISHED
observation @ 13:00:    ESTABLISHED

observation @ 12:00:    UNKNOWN
interval 11:00→13:00:   UNKNOWN
```

The gap is not filled merely because observations exist on both sides.
