# PIT Research Admission Policy V0 — Contract

Project name: **Interval Eligibility Policy V0**. Refined semantic role: **PIT Research Admission Policy V0**.

Question answered by this phase, and only this question:

> May this **exact instrument identity** enter a historical research calculation over this interval, using only evidence available by the query's `as_of`?

Artificial fixture only. No network, no Binance acquisition, no source discovery, no PIT universe construction, no Router / Jigsaw / Qnty / QntyPolicyGate integration, no backtest.

Implemented by `qntylab/pit_research_admission.py`. Predecessor `qntylab/evidence_claim_split.py` (Evidence Claim Split V0, commit `81b3345`) is **unmodified** and is the only evidence gate this layer uses.

## Layer Separation

| Layer | Question | Owner |
| --- | --- | --- |
| 1. Evidence claims | what do we know, from what evidence, when did we know it? | `evidence_claim_split.py` (frozen) |
| 2. **PIT research admission** | may this exact instrument enter this historical calculation at this `as_of`? | **this phase** |
| 3. Data / outcome usability | can features, labels, prices, funding, replay inputs actually be computed? | not implemented, not consulted |

Layer 3 inputs — missing price data, missing funding, missing future outcomes, missing experiment files, label computability, eventual delisting, future survival — have **no channel** into this module. The evaluator's only inputs are an `AdmissionRequest` and an iterable of `EvidenceRecord`.

## Fact vs Policy Decision

A policy decision is not an evidence proposition. The output vocabulary is therefore deliberately **not** `ELIGIBLE` / `INELIGIBLE` / `UNKNOWN`:

| Outcome | Meaning |
| --- | --- |
| `ADMIT` | admissible evidence plus the frozen policy rules establish positive coverage of the whole requested interval |
| `REJECT` | admissible evidence plus the frozen policy rules affirmatively establish that the requested interval must not be admitted |
| `UNRESOLVED` | insufficient, ambiguous, conflicting, wrong-identity or temporally unavailable evidence — the fail-closed default |

The decision is an *action about a research query*, never a claim about the world. This module **never constructs an `IntervalEligibilityProposition`** from its own output, and never writes back into the evidence stream: a policy decision cannot re-enter as evidence.

## Invalid Query ≠ REJECT

Contract violations raise `InvalidPITQuery` (a `ValueError` subclass) from `AdmissionRequest.__post_init__`. They never produce a decision object of any kind, so a malformed query can never be read as "the instrument was rejected from the universe".

Raising conditions:

* identity not exactly `InstrumentIdentity`, or any identity field empty/padded
* any timestamp not the frozen `YYYY-MM-DDTHH:MM:SSZ` UTC shape, or not a real instant
* `query_start >= query_end`
* `query_end > as_of` — a non-PIT (lookahead) request

## Time Model

Query interval is **half-open**: `[query_start, query_end)`.

Required of every historical admissibility query:

```
query_start < query_end
query_end  <= as_of
```

Two clocks are preserved exactly as frozen by the predecessor:

| Clock | Field | Meaning |
| --- | --- | --- |
| effective / valid | `effective_time`, `effective_start`, `effective_end` | when the claimed fact holds |
| available / known | `available_time` | when the evidence became knowable |

Timestamps are fixed-width UTC, so string comparison is chronological comparison.

## Hard PIT Rule

Evidence is filtered by `available_time <= as_of` **before anything else is observed about the dataset** — before ground detection, before identity partitioning, before diagnostics. Consequently *every* field of the returned `AdmissionDecision` (decision, reason codes, evidence basis, digest) is invariant under adding evidence that becomes available after `as_of`.

`available_time == as_of` is **admissible** (inclusive boundary, inherited unchanged from the predecessor). `available_time == as_of + 1s` (the smallest supported unit) is excluded.

### Rejected reason code: `FUTURE_KNOWN_EVIDENCE_EXCLUDED`

Deliberately **not** in the vocabulary. Emitting a code that counts or acknowledges future-known evidence would make future knowledge observable in a historical decision — the exact leak this layer exists to prevent. Future-available evidence is invisible, not annotated.

## Exact Identity Rule

An evidence record participates only if `record.proposition.identity == request.identity`, using frozen `InstrumentIdentity` equality over all four fields (`symbol`, `market`, `contract_type`, `instrument_instance_id`). Generic `BTC` asset evidence, `BTCUSDT` spot evidence, another venue's perpetual, and a later relisted instance are all different identities and bind nothing. Identity is compared by value on the exact frozen type; propositions and records are admitted by **exact type** (no subclasses), inherited from the predecessor's anti-widening rule.

## Frozen Admission Rules

All grounds require the ground proposition to be `ESTABLISHED` under the predecessor's `assess(evidence, proposition, as_of=as_of)` — this module contains no second evidence gate and no derivation step of its own.

### ADMIT grounds (positive coverage of the whole interval)

| Code | Rule |
| --- | --- |
| `INTERVAL_CLAIM_COVERS_QUERY` | an established `IntervalEligibilityProposition` for the exact identity with `effective_start <= query_start` and `effective_end >= query_end` |
| `BOUNDARY_WINDOW_COVERS_QUERY` | an established `LAUNCH` boundary with `effective_time <= query_start` **and** an established `DELIST` boundary with `effective_time >= query_end`, both for the exact identity |

`INTERVAL_CLAIM_COVERS_QUERY` is entailment *within* one proposition domain: a claim of eligibility over a wider interval entails eligibility over a sub-interval. It is not a domain escalation, and it is the only place a claim is read as covering more than its exact endpoints.

`BOUNDARY_WINDOW_COVERS_QUERY` requires **both** edges to be positively established. An unterminated instrument (launch known, no delist) is therefore `UNRESOLVED`, not `ADMIT`.

> **Frozen V0 limitation.** Boundary evidence alone cannot admit a still-listed instrument, because "no delist evidence exists" is absence of evidence and must not close the right edge. Admitting such an interval requires an explicit `IntervalEligibilityProposition`. This is fail-closed by construction and is documented rather than repaired.

### REJECT grounds (affirmative exclusion)

| Code | Rule |
| --- | --- |
| `DELIST_AT_OR_BEFORE_QUERY_START` | established `DELIST` with `effective_time <= query_start` — the whole interval lies after termination |
| `DELIST_INSIDE_QUERY` | established `DELIST` with `query_start < effective_time < query_end` |
| `LAUNCH_AT_OR_AFTER_QUERY_END` | established `LAUNCH` with `effective_time >= query_end` — the whole interval lies before existence |
| `LAUNCH_INSIDE_QUERY` | established `LAUNCH` with `query_start < effective_time < query_end` |

Admission is **whole-interval, all-or-nothing**. V0 never truncates a query, never returns a partial interval, and never proposes a repaired interval. A boundary strictly inside the query affirmatively establishes that part of the requested interval is outside the instrument's existence, so the interval *as requested* must not be admitted.

### Half-open boundary behaviour (frozen)

| Boundary | Position | Effect |
| --- | --- | --- |
| `LAUNCH` at exactly `query_start` | inside coverage | opens the window; no reject |
| `LAUNCH` at exactly `query_end` | outside a half-open query | `LAUNCH_AT_OR_AFTER_QUERY_END` → reject ground |
| `DELIST` at exactly `query_start` | interval is empty of existence | `DELIST_AT_OR_BEFORE_QUERY_START` → reject ground |
| `DELIST` at exactly `query_end` | closes the window at the exclusive edge | satisfies the right edge of `BOUNDARY_WINDOW_COVERS_QUERY`; no reject |

### Resolution

Grounds are computed as **sets**, so input order is irrelevant.

```
admit grounds ∧ reject grounds  ->  UNRESOLVED + CONFLICTING_EVIDENCE (+ every firing ground code)
admit grounds only              ->  ADMIT
reject grounds only             ->  REJECT
neither                         ->  UNRESOLVED + INSUFFICIENT_EVIDENCE (+ diagnostics)
```

No precedence rule is invented. Two established, usable, mutually incompatible claims never resolve by first-seen, last-seen, newest-effective, or fixture convenience; they fail closed to `UNRESOLVED`.

### Diagnostic codes (only with `INSUFFICIENT_EVIDENCE`)

| Code | Condition |
| --- | --- |
| `NO_EXACT_IDENTITY_EVIDENCE` | zero admissible records carry the request identity |
| `IDENTITY_MISMATCH` | at least one admissible record carries a *different* identity |
| `POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL` | at least one admissible exact-identity observation lies in `[query_start, query_end)` |

All three are computed from admissible evidence only, so they cannot leak future knowledge.

## Non-Escalation Invariants Preserved

* `BOUNDARY ≠ OBSERVATION ≠ INTERVAL ADMISSION FACT` — the three predecessor proposition types stay distinct; `PointObservationProposition` is **never** an admission ground, in either direction. An observation inside the query is at most a diagnostic string.
* `ABSENCE OF EVIDENCE ≠ NEGATIVE EVIDENCE` — every `REJECT` requires an established boundary proposition. There is no path from an empty or partial evidence set to `REJECT`.
* `UNKNOWN ≠ FALSE`, `UNKNOWN ≠ REJECT` — a proposition that assesses `UNKNOWN` contributes nothing, in any quantity. Aggregating `UNKNOWN` never yields `REJECT`.
* `ESTABLISHED EXACT-TIME OBSERVATION ≠ ESTABLISHED CONTINUOUS INTERVAL EXISTENCE` — no interpolation, no gap bridging, no bracketing rule.
* Boundary evidence reaches a decision only through the two explicitly frozen rules above.
* The policy derives an *action*. It never manufactures a stronger Evidence Claim Split proposition and feeds it back as evidence.

## Relist / Episode Safety

Lifecycle episodes are separated by `instrument_instance_id`, reusing the frozen identity model. A later episode's `LAUNCH` cannot admit an earlier episode's interval and cannot repair an earlier episode's gap, because it is evidence about a different identity and is filtered out before ground detection. The gap between one instance's `DELIST` and the next instance's `LAUNCH` is `REJECT` for each instance separately (post-termination / pre-existence) and never `ADMIT` for either.

V0 adds no cross-episode continuity concept. Where the identity model cannot express a needed distinction, the outcome is `UNRESOLVED`, documented, and left to a later phase.

## Outcome Blindness

The evaluator is pure and takes no outcome channel: no returns, no price/funding availability, no delisting-later check, no label computability, no experiment directory, no PnL, no strategy state, no clock, no filesystem, no network. Two otherwise identical PIT queries produce byte-identical decisions and digests regardless of hypothetical future outcome or data-usability state. Asserted structurally by an AST import test and behaviourally by fixture F12.

## Determinism and Policy Identity

```
POLICY_ID               = "qntylab.pit_research_admission"
POLICY_VERSION          = "v0"
POLICY_CONTRACT_DIGEST  = sha256 of the frozen canonical rule spec embedded in the module
```

Every `AdmissionDecision` carries all three. `decision_digest(decision)` is a SHA-256 over canonical JSON of policy identity, request, decision, sorted reason codes and the canonically sorted evidence basis (each entry: role, source keys, predecessor `proposition_payload`, so the proposition domain tag survives serialisation).

Reason codes are a closed vocabulary, deduplicated and lexicographically sorted. Evidence basis entries are deduplicated and sorted by canonical JSON. Nothing depends on filesystem iteration order, dict insertion order, randomness, wall-clock now, or network state.

## Frozen Fixture Matrix

| ID | Fixture | Required outcome |
| --- | --- | --- |
| F1 | exact instrument, launch ≤ start and delist ≥ end known by `as_of` | `ADMIT` / `BOUNDARY_WINDOW_COVERS_QUERY` |
| F2 | same effective evidence, available only after `as_of` | `UNRESOLVED` |
| F3 | no relevant evidence | `UNRESOLVED` + `NO_EXACT_IDENTITY_EVIDENCE` |
| F4 | generic `BTC` evidence, query for exact `BTCUSDT` perpetual | `UNRESOLVED` + `IDENTITY_MISMATCH` |
| F5 | exact-instrument delist covering the query | `REJECT` |
| F6 | exact-time observation inside a wider query, no boundary coverage | `UNRESOLVED` + `POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL` |
| F7 | only `UNKNOWN`-producing evidence, in quantity | `UNRESOLVED`, never `REJECT` |
| F8 | `query_end > as_of` | `InvalidPITQuery`, not `REJECT` |
| F9 | conflicting established usable evidence | `UNRESOLVED` + `CONFLICTING_EVIDENCE` |
| F10 | evidence order permuted (all permutations) | identical decision, reasons, basis, digest |
| F11 | future evidence appended after an earlier historical query | historical decision byte-identical |
| F12 | future outcome / data-usability surrogates differ | decision and digest unchanged |
| F13 | boundaries exactly at `query_start` / `query_end` | frozen half-open behaviour above |
| F14 | `available_time == as_of` | admissible |
| F15 | `available_time == as_of + 1s` | excluded |
| F16 | delist / relist episodes | no cross-episode admission or repair |

## Explicit Non-Claims

* Not a live universe builder, market-data availability checker, outcome/survival checker, trading signal, backtest, Router feature, or Qnty integration.
* Not a replacement for, or amendment to, Evidence Claim Split V0.
* No PIT Universe Fixture, no `STATE_SNAPSHOT_V0`, no lifecycle redesign, no policy registry.
* No tradability, liquidity, profitability, or scientific-validation claim.
