# PIT Universe Composition Fixture V0 — Contract

Project lineage name: **PIT Universe Fixture V0**. Semantic role: **PIT Universe Composition Fixture V0**.

Question answered by this phase, and only this question:

> Given an **explicitly supplied** candidate roster, an evidence snapshot, `[start, end)` and `as_of`, can QntyLab deterministically partition every exact candidate into `ADMITTED` / `REJECTED` / `UNRESOLVED` without inventing evidence, lifecycle semantics, candidate-completeness claims or future knowledge?

Artificial closed-world fixture only. No candidate discovery, no Binance query, no `STATE_SNAPSHOT_V0`, no Router / Jigsaw / Qnty / QntyPolicyGate integration, no backtest.

Implemented by `qntylab/pit_universe_composition.py`. Predecessors `qntylab/pit_research_admission.py` (commit `5f6a744`) and `qntylab/evidence_claim_split.py` (commit `81b3345`) are **unmodified**.

## Layer Separation

| Layer | Question | Owner |
| --- | --- | --- |
| 1. Evidence claims | what do we know, from what, when? | `evidence_claim_split.py` (frozen) |
| 2. PIT research admission | may this exact instrument enter this calculation? | `pit_research_admission.py` (frozen) |
| **2b. PIT universe composition** | **how does that answer partition an explicit candidate roster?** | **this phase** |
| 3. Data / outcome usability | can features, labels, prices, funding be computed? | not implemented, not consulted |

This module owns no evidence semantics and no admission semantics. It is a deterministic fold of the frozen policy over an explicit candidate list, plus the identity bookkeeping needed to say exactly which roster, evidence slice, policy and builder produced a partition.

Structurally impossible here, and asserted by test: discovering candidates; inferring roster completeness; constructing an evidence proposition or `EvidenceRecord`; calling `assess` / `is_established`; upgrading `UNKNOWN`; overriding an admission decision; inferring lifecycle continuity; reading future outcomes; reading data availability.

## The Scope Limit That Defines This Phase

> **PIT-correct filtering of a survivorship-biased candidate roster is still survivorship-biased.**

`CLOSED_WORLD_BY_CONSTRUCTION` means **only**:

> For this artificial fixture, this explicitly enumerated candidate set is the complete input universe.

It does **not** mean "these were all instruments that existed historically", and does **not** mean "this roster represents Binance at time T". Those claims belong to the later **PIT Candidate Roster / Discovery Provenance V0** phase and are absent here. Every artifact carries this limit in its own `partition_completeness_scope` field, because an artifact outlives the conversation that produced it.

## CandidateRosterV0

Explicit, externally supplied, never derived.

| Field | Rule |
| --- | --- |
| `roster_id`, `scope` | non-empty, unpadded strings; both are load-bearing in the roster digest |
| `roster_version` | must be `v0` (`SUPPORTED_ROSTER_VERSIONS`); anything else is an unsupported contract version |
| `source_kind` | frozen to exactly `ARTIFICIAL_FIXTURE` |
| `completeness_claim` | frozen to exactly `CLOSED_WORLD_BY_CONSTRUCTION` |
| `candidates` | non-empty `tuple` of exact `InstrumentIdentity` (no subclasses, no list, no generator) |

Identity is the predecessor's `InstrumentIdentity`, unchanged: `symbol`, `market`, `contract_type`, `instrument_instance_id`, all four participating in equality. No second identity model exists. A delisted-then-relisted ticker is two candidates, not one.

**Duplicate exact canonical identity → `DuplicateCandidateIdentity`, no artifact.** Deliberately not deduplicated: a duplicate is evidence of a defect in whatever generated the roster, and swallowing it would hide that defect behind a plausible-looking universe.

Candidate order is **not semantic**. Canonical order is ascending canonical identity JSON; `roster_digest` is order-insensitive.

An **empty roster is refused**. A zero-candidate universe has an undefined resolution rate and would assert a vacuously "complete" partition; the caller must state a real candidate set.

## EvidenceSnapshotV0

A wrapper, not a second evidence framework: the records are the predecessor's `EvidenceRecord` values, unchanged and uninterpreted.

| Field | Rule |
| --- | --- |
| `snapshot_id` | non-empty; load-bearing in the artifact digest |
| `snapshot_version` | must be `v0` |
| `as_of` | frozen UTC timestamp shape; **must equal `query.as_of` exactly** |
| `records` | `tuple` of exact `EvidenceRecord` (no subclasses) |

**Snapshot identity is the digest of the `as_of`-ELIGIBLE slice only** (`available_time <= as_of`), not of every record the caller handed over. A snapshot that additionally carries records knowable only after `as_of` has the *same* `eligible_evidence_digest` as one that does not. This is deliberate and load-bearing: the object being identified is "the historically eligible evidence at `as_of`", and a historical artifact must not shift when the future arrives. It is the same reasoning that made the predecessor refuse a `FUTURE_KNOWN_EVIDENCE_EXCLUDED` reason code — future-known evidence is invisible, not annotated.

Byte-identical eligible records are collapsed before digesting and before reaching the policy. A record is a value; carrying the same established fact twice conveys nothing extra, and the predecessor already deduplicates `supporting_source_keys` for exactly this reason. Records differing in **any** field, including `source_key`, are distinct corroborating evidence and are all kept.

The eligible slice is computed once and shared read-only across candidates, so this layer only ever **narrows** what the policy sees; the policy applies its own identical cutoff again. Narrowing changes no policy answer (asserted over randomised evidence subsets).

## Historical Query

`UniverseQueryV0` reuses the frozen PIT Admission time semantics exactly. No second interval convention is introduced.

```
[start, end)      half-open
start < end
end  <= as_of
```

Malformed or non-PIT query → `InvalidUniverseQuery`, **no artifact**. Never "reject every candidate": a contract violation must not be readable as a plausible empty universe.

## Composition Rule

```
for candidate in canonical(roster):
    decision = pit_research_admission.evaluate(
        AdmissionRequest(candidate, query.start, query.end, query.as_of),
        eligible_slice,
    )
```

The decision is **recorded verbatim**. There is deliberately no branch anywhere that could rewrite an outcome, for any reason.

```
PIT Admission = UNRESOLVED  →  Universe Composition = UNRESOLVED
```

Never `UNRESOLVED → probably active → ADMITTED`.

| Decision | Partition |
| --- | --- |
| `ADMIT` | `admitted` |
| `REJECT` | `rejected` |
| `UNRESOLVED` | `unresolved` |

### Exact partition invariant

```
admitted ∪ rejected ∪ unresolved = roster
admitted ∩ rejected = admitted ∩ unresolved = rejected ∩ unresolved = ∅
```

Every candidate appears exactly once. No candidate disappears because evidence was missing. Enforced twice: in the builder, **and again at canonicalisation** — an artifact violating it has no canonical form and therefore no digest (see H-1 below).

### Candidate independence

A candidate's decision depends only on that candidate and the shared eligible slice. Adding or removing an unrelated candidate `Z` leaves every other candidate's complete record byte-identical, verified by leave-one-out over every candidate, by single-candidate universes matching the full one, and over randomised roster subsets.

One honest caveat, inherited from the frozen predecessor and not a property of this layer: the `IDENTITY_MISMATCH` diagnostic reflects whether *foreign-identity evidence exists in the evidence slice*. It is a property of the **snapshot**, never of the roster — roster membership alone can never influence another candidate's decision. Adding `Z`'s evidence to the snapshot is an evidence change, not a candidate interaction.

## Artifact

`PITUniverseCompositionArtifactV0` binds:

| Group | Contents |
| --- | --- |
| type | `artifact_type` = `PIT_UNIVERSE_COMPOSITION_ARTIFACT`, `artifact_version` = `v0` |
| query | `start`, `end`, `as_of` |
| candidate roster | `roster_id`, `roster_version`, `scope`, `source_kind`, `completeness_claim`, `roster_digest` |
| evidence | `snapshot_id`, `snapshot_version`, `as_of`, `eligible_evidence_digest` |
| admission policy | `policy_id`, `policy_version`, `policy_contract_digest` |
| builder | `builder_id`, `builder_version`, `builder_contract_digest` |
| per candidate | exact identity, decision, reason codes, evidence basis, admission `decision_digest` |
| partitions | `admitted`, `rejected`, `unresolved` |
| telemetry | counts, exact-ratio resolution rate, reason-code histogram, `roster_partition_complete` |
| scope | `partition_completeness_scope` (verbatim disclaimer) |

Each candidate record retains the **whole** `AdmissionDecision`, and its canonical payload is produced by the predecessor's own `decision_payload`, so reason codes and evidence basis cannot be lost or paraphrased on the way into the artifact.

`BUILDER_CONTRACT_DIGEST` is a SHA-256 over the canonical rule spec literal embedded in the module: any rule change changes the digest carried by every artifact. `artifact_digest` is a SHA-256 over the canonical payload. Every field probed above is load-bearing; incidental ordering is not.

## Resolution Telemetry — Descriptive Only

```
resolution_rate = (admit_count + reject_count) / candidate_count
```

Serialised as an exact integer numerator/denominator so digests cannot depend on float formatting.

### NO COVERAGE TARGET

**There is no pass/fail threshold for admit rate, reject rate, unresolved rate or resolution rate.** An artifact that is 90% `UNRESOLVED` may be a completely correct PASS. The builder never reads `resolution_rate`, so it structurally cannot branch on it. If real data later produces high `UNRESOLVED` rates, that is evidence about upstream evidence and roster coverage — **never** a reason to weaken PIT Admission.

### Completeness non-escalation

The only completeness this layer computes is `roster_partition_complete`, which means exactly: every candidate in the supplied roster appears in exactly one partition. There is no `universe_complete` field and no market-completeness claim of any kind.

## Failure Surface

`UNRESOLVED` is a **valid policy output** and normal content of a healthy artifact. It shares no channel with build failure.

| Structural failure | Exception |
| --- | --- |
| malformed roster, unsupported version, bad source kind / completeness claim, empty roster, non-identity candidate | `InvalidCandidateRoster` |
| duplicate exact candidate identity | `DuplicateCandidateIdentity` |
| malformed snapshot, `as_of` not bound to the query, snapshot digest mismatch | `InvalidEvidenceSnapshot` |
| malformed or non-PIT query | `InvalidUniverseQuery` |
| policy id / version / contract digest mismatch | `PolicyIdentityMismatch` |
| widened subtype or partition-invariant violation at canonicalisation | `InvalidUniverseArtifact` |

All subclass `InvalidUniverseBuild(ValueError)`. **Atomic formation:** every structural check runs before the artifact is constructed, and the module holds no mutable state, so a failed build leaves no partial universe behind.

## Subtype Widening

Exact-type dispatch at every semantic boundary, inherited from the two predecessors' H-1 findings: `CandidateRosterV0`, `EvidenceSnapshotV0`, `UniverseQueryV0`, `UniverseCandidateRecordV0`, `ResolutionTelemetryV0`, `RosterRefV0`, `EvidenceSnapshotRefV0`, `PITUniverseCompositionArtifactV0`, plus `InstrumentIdentity`, `EvidenceRecord`, `AdmissionDecision` and `EvidenceBasisEntry` via the predecessors. A subclass carrying extra distinguishing fields is refused loudly rather than flattened into a base payload that two different objects could share.

## Isolation

No network, no filesystem, no clock, no randomness, no database, no `Qnty`, no `QntyPolicyGate`. AST-asserted: the only imports are `qntylab.evidence_claim_split`, `qntylab.market_observation`, `qntylab.pit_research_admission`, plus `dataclasses`, `hashlib`, `json`, `typing`.

## Explicit Non-Claims

* No historical candidate discovery, and no claim of historical market-universe completeness.
* No lifecycle semantics, no continuity across episodes, no relist repair.
* No `STATE_SNAPSHOT_V0`, no state-now query.
* No data/outcome usability judgement: missing candles, funding, experiment files, lookback or labels cannot move a candidate between partitions, because they have no input channel.
* The frozen V0 admission limitation stands unweakened: **no delist evidence ≠ evidence of continued listing**. A launch without a delist stays `UNRESOLVED`, even though admitting it would raise universe coverage.
