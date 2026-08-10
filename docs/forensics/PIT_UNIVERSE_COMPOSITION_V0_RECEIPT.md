# PIT Universe Composition Fixture V0 — Receipt

Project lineage name: **PIT Universe Fixture V0**. Semantic role: **PIT Universe Composition Fixture V0**.

Verdict: `PIT_UNIVERSE_COMPOSITION_V0_CLOSED_PASS`.

Phase objective: freeze the smallest deterministic PIT universe composition layer on top of the promoted PIT Research Admission Policy V0 — partition every exact candidate of an explicitly supplied roster into `ADMITTED` / `REJECTED` / `UNRESOLVED` without inventing evidence, lifecycle semantics, candidate-completeness claims or future knowledge. Artificial closed-world fixture only.

## Baseline and Isolation

| Field | Value |
| --- | --- |
| repo | `/home/swirky/DevHub/repos/QntyLab` (QntyLab) |
| `master` HEAD at start | `7bd01c6dbee1d851c2e561db136f87597a587808` |
| `origin/master` | identical to local `master` |
| `QNTYLAB_HYGIENE_V0` | `CLOSED`, not reopened |
| PIT Admission promotion | `CLOSED`; `5f6a74498d615272a08dde64ba7abc02f85f128e` verified an ancestor of `master` |
| predecessor (evidence) | Evidence Claim Split V0, `81b3345`, `CLOSED / PASS` |
| branch | `research/pit-universe-composition-v0` |
| worktree | `/home/swirky/DevHub/worktrees/QntyLab-pit-universe-composition-v0` |
| parent commit | `7bd01c6dbee1d851c2e561db136f87597a587808` |
| main worktree | 187 preserved dirty paths, untouched; nothing cleaned, nothing staged from it |
| suspended causal-vol worktree | untouched |
| forensic census | not re-run (read-only preflight only) |
| network research attempts | `0` |

Added files (all additive; **no existing file modified**):

| Path | SHA-256 |
| --- | --- |
| `docs/forensics/PIT_UNIVERSE_COMPOSITION_V0_CONTRACT.md` | `7a93fe258669fe4041d884dff44676597fa1eba9a54baf1beaa9de5c0814b456` |
| `qntylab/pit_universe_composition.py` | `7367e1cefc3e7b11a62cdd8e0768cc1cf2cd8fb86f485720dcbda69a21272a6b` |
| `tests/test_pit_universe_composition_v0.py` | `7d8fa4a52389ae051f45883fb258f5e9c2d73de73e1cd97f75c56781897ab318` |

Hashes are of the files as committed; recompute with `sha256sum`. This receipt is the fourth added file.

## Contract

See `docs/forensics/PIT_UNIVERSE_COMPOSITION_V0_CONTRACT.md`. Frozen surface:

| Item | Frozen value |
| --- | --- |
| inputs | `CandidateRosterV0`, `EvidenceSnapshotV0`, `UniverseQueryV0`, PIT Admission Policy V0 |
| output | `PITUniverseCompositionArtifactV0` |
| `source_kind` | exactly `ARTIFICIAL_FIXTURE` |
| `completeness_claim` | exactly `CLOSED_WORLD_BY_CONSTRUCTION` (fixture input set only) |
| duplicate candidate | `DuplicateCandidateIdentity`, no artifact; never silently deduplicated |
| candidate identity | predecessor `InstrumentIdentity`, exact type, all four fields |
| candidate order | not semantic; canonical order is ascending canonical identity JSON |
| query | `[start, end)`, `start < end`, `end <= as_of`; malformed → no artifact |
| snapshot binding | `evidence_snapshot.as_of` must equal `query.as_of` exactly |
| evidence eligibility | `available_time <= as_of`, applied before anything else is observed |
| snapshot identity | digest of the eligible slice only; future-known records are invisible |
| evidence dedup | byte-identical eligible records collapsed; any field difference kept |
| decision recording | verbatim; `UNRESOLVED` never upgraded or downgraded |
| telemetry | descriptive only; **no threshold of any kind** |
| builder identity | `qntylab.pit_universe_composition` / `v0` / contract digest below |

## Artifact Identity (frozen fixture, 12 candidates)

| Digest | Value |
| --- | --- |
| `roster_digest` | `5e1befc0490e66a88d430e1a7a10410c7400789e91ef21bab379d70dabff5fec` |
| `eligible_evidence_digest` | `7511879959139cbbdb05f9d0708154d3ded8fe5564873c6fd8113a433c6afb7b` |
| `policy_contract_digest` | `8c59865a54cb1ddeb061a3c22f6a2741e60751570bc1101cd2f43752f4709cb2` (unchanged) |
| `builder_contract_digest` | `a80dd5a45bdd80081b737bbe1f4e23c97736a5cb229723d9ccaac161cbf7fd4b` |
| `artifact_digest` | `7de2bb5e10e4bdba21dd0b5eb77e0b5e779a51434a4966b4f7f7c4b7c3d61c47` |

## Resolution Telemetry — Descriptive, No Threshold

| Metric | Value |
| --- | --- |
| `candidate_count` | 12 |
| `admit_count` | 3 |
| `reject_count` | 3 |
| `unresolved_count` | 6 |
| `resolution_rate` | 0.5 |
| threshold | **NONE** |

Reason-code histogram: `BOUNDARY_WINDOW_COVERS_QUERY` 2, `CONFLICTING_EVIDENCE` 1, `DELIST_AT_OR_BEFORE_QUERY_START` 1, `DELIST_INSIDE_QUERY` 1, `IDENTITY_MISMATCH` 5, `INSUFFICIENT_EVIDENCE` 5, `INTERVAL_CLAIM_COVERS_QUERY` 2, `LAUNCH_AT_OR_AFTER_QUERY_END` 1, `LAUNCH_INSIDE_QUERY` 1, `NO_EXACT_IDENTITY_EVIDENCE` 3, `POINT_OBSERVATION_INSUFFICIENT_FOR_INTERVAL` 1.

Candidate counts were chosen to exercise semantics, never to hit a rate. The 50% resolution rate is a description of this fixture, not a target and not a grade.

## Artificial Fixture

12 heterogeneous candidates in one closed-world roster, covering: clear `ADMIT` via explicit interval claim; clear `ADMIT` via both boundary edges; `REJECT` via delist ≤ start; `REJECT` via launch inside; `UNRESOLVED` from no evidence; from identity mismatch (spot evidence for a perp candidate); from observation-only evidence; from conflicting evidence; from future-known evidence; from `UNKNOWN` / insufficient evidence (launch with no delist); plus a delist/relist pair of episodes (`ADMIT` for the first instance, `REJECT` for the second).

## Fixture Matrix Executed

| ID | Fixture | Result |
| --- | --- | --- |
| U1 | all candidates partition exactly once | PASS — union equals roster, pairwise disjoint, also over 40 random subsets |
| U2 | candidate order permutation | PASS — byte-identical payload and digest; all 24 permutations of a 4-candidate roster give one digest |
| U3 | evidence order permutation | PASS — byte-identical; duplicated records collapse; distinct corroborating sources kept |
| U4 | duplicate exact candidate identity | PASS — `DuplicateCandidateIdentity`, no artifact; equal-valued distinct objects also caught; different instance of the same ticker is not a duplicate |
| U5 | add unrelated candidate Z | PASS — roster-only and roster+evidence variants; every other candidate byte-identical; leave-one-out over all 12 |
| U6 | remove unrelated candidate Z | PASS — remaining decisions byte-identical |
| U7 | future-known evidence added | PASS — every one of the 64 subsets of 6 future records leaves the artifact digest unchanged; `available_time == as_of` eligible, `+1s` excluded |
| U8 | different future outcomes | PASS — two worlds, one artifact digest; input surface has no outcome channel |
| U9 | policy returns `UNRESOLVED` | PASS — recorded verbatim; an all-`UNRESOLVED` universe is a valid artifact |
| U10 | no evidence for a candidate | PASS — present as `UNRESOLVED` with `NO_EXACT_IDENTITY_EVIDENCE`; empty snapshot leaves all 12 present |
| U11 | one candidate `REJECT` | PASS — no effect on others; single-candidate universes match the full one |
| U12 | malformed query | PASS — `InvalidUniverseQuery` over 6 shapes, no artifact; `end == as_of` valid |
| U13 | policy identity/digest mismatch | PASS — fails closed on id, version and digest |
| U14 | snapshot identity/digest mismatch | PASS — fails closed; `as_of` must bind the query; 6 malformed-snapshot shapes refused |
| U15 | roster digest mismatch | PASS — fails closed; 8 malformed-roster shapes refused |
| U16 | same semantic inputs | PASS — exact canonical serialisation and digest repeat; 64-hex |
| U17 | same candidates, different provenance | PASS — partitions identical, artifact digest differs (roster_id, scope, snapshot_id) |
| U18 | same claims, different `as_of` | PASS — artifact identity differs; exactly the one candidate whose evidence became knowable between cutoffs changes |
| U19 | missing hypothetical price/funding/outcome data | PASS — not representable in any input type (`TypeError` on every such kwarg); nearest representable proxy moves nobody |
| U20 | composition vs independent per-candidate admission | PASS — decisions and `decision_digest`s equal for all 12; also equal against the raw un-narrowed snapshot |

## Test Results

```
python -m pytest tests/test_pit_universe_composition_v0.py -q      109 passed   (new)
python -m pytest tests/test_pit_research_admission_v0.py -q         66 passed   (predecessor regression)
python -m pytest tests/test_evidence_claim_split_v0.py -q           31 passed   (predecessor regression)
python -m pytest tests/test_market_observation.py tests/test_lifecycle.py -q    53 passed   (neighbours)
```

Full suite, run once: `1003 passed, 41 failed, 32 errors`. Classified **unrelated and pre-existing**: the PIT Admission receipt recorded `894 passed, 41 failed, 32 errors` at the parent commit, so the failure and error sets are numerically identical and this phase contributes only its 109 passing tests. The failures are the known data-dependent tests (`data/raw`, manifests and `experiments/runs/` are gitignored and absent in a fresh worktree). None import this phase's module. No repair campaign started; no scientific experiment rerun.

`git diff --check`: clean.

## Hostile Review

One independent hostile pass, executed as runnable attack probes against the exact contract and diff. Attack question: *can this composition layer silently create stronger knowledge than its candidate roster, evidence snapshot or PIT Admission decisions actually establish?*

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| H-1 | HIGH | **The exact-partition invariant was enforced only inside the builder.** `artifact_payload` / `artifact_digest` accepted any artifact object and canonicalised it, so an artifact reaching the serialiser from anywhere else could claim a stronger universe than its own recorded decisions establish and still mint a well-formed digest. Confirmed by probe: moving every `UNRESOLVED` candidate into `admitted` (`A17`) was accepted; a candidate present in two partitions (`A17b`) was accepted; emptying all three partitions (`A17c`) was accepted. This is precisely `UNRESOLVED` upgrading plus partition-integrity loss, surviving into the artifact's authoritative identity. | **FIXED** |
| M-1 | MEDIUM | Two snapshots differing only in records with `available_time > as_of` share one `eligible_evidence_digest`, so the artifact cannot distinguish "only eligible evidence existed" from "more existed, later". | ACCEPTED — this *is* the future-blindness requirement (U7), and the same reasoning that made the predecessor refuse a `FUTURE_KNOWN_EVIDENCE_EXCLUDED` code. Documented in the contract. |
| M-2 | MEDIUM | An empty roster is refused rather than producing an empty universe. | ACCEPTED — a zero-candidate universe has an undefined resolution rate and would assert a vacuously complete partition. Documented. |
| L-1 | LOW | The module namespace re-exports predecessor names imported for exact-type dispatch, so a caller could reach them "via" this module. No behavioural consequence; AST tests prove no proposition or record is ever constructed here. | NOT REPAIRED |

Probed and found sound: candidate omission (0 over 300 randomised evidence subsets); `UNRESOLVED` upgrading (0 divergences from independent per-candidate admission over the same 300); cross-candidate influence (0 over 200 randomised roster subsets); digest omission — every artifact field, every nested roster/evidence/query ref field and every telemetry field probed, 0 with an unchanged digest, and all 8 load-bearing single-field mutations pairwise distinct; eligible-slice narrowing (0 divergences vs the raw snapshot over 150 randomised sets including future records); identity-key collisions (0); subtype widening across 7 local types plus the predecessors'; policy and snapshot identity mismatch; wrong `as_of` binding; reason-code and evidence-basis loss; partial artifact formation (module holds no mutable state).

### C/H Fixes

H-1 only. `_require_exact_partition` now runs inside `artifact_payload`, the single canonicalisation chokepoint, and requires: the three partitions are pairwise disjoint and their union equals the recorded candidate identities; each candidate's partition equals its own recorded policy decision; no duplicate identity within a partition or across candidate records; telemetry counts equal the partition sizes; `roster_partition_complete` is `True`; and the reason-code histogram describes the recorded decisions. A violating artifact therefore has **no canonical form and no digest**. Seven regression tests added. `BUILDER_CONTRACT_DIGEST` changed accordingly, as designed.

Also applied while building, not a review finding: `eligible_records` collapses byte-identical records, so a repeated record cannot give the snapshot a different identity — following the predecessor's own `supporting_source_keys` dedup precedent. Records differing in any field, including `source_key`, are kept as distinct corroboration.

### Targeted Re-Review

One re-review, scoped to the H-1 fix. All five original attack shapes now refused with `InvalidUniverseArtifact` (promote-to-admitted, two-partition membership, emptied partitions, dropped candidate, lying telemetry); 0/200 honest builds refused across randomised rosters and evidence sets; digest still deterministic and 64-hex; no new decision or reason-code vocabulary member introduced; order and future-knowledge invariance re-verified after the fix. `PASS`.

## Predecessor and Coupling

* `qntylab/pit_research_admission.py` — **unmodified**. `ADMIT`/`REJECT`/`UNRESOLVED`, the 11 reason codes, `POLICY_CONTRACT_DIGEST` and the absence of `FUTURE_KNOWN_EVIDENCE_EXCLUDED` are re-asserted by tests here. The frozen limitation *no delist evidence ≠ evidence of continued listing* was **not** weakened to raise universe coverage; a launch-without-delist candidate stays `UNRESOLVED` and is asserted to do so.
* `qntylab/evidence_claim_split.py` — **unmodified**; `ESTABLISHED`/`UNKNOWN` and `BOUNDARY_KINDS` re-asserted.
* `qntylab/lifecycle.py`, `qntylab/market_observation.py` — unmodified.
* Qnty coupling: **NONE**. QntyPolicyGate coupling: **NONE**. Router / Jigsaw / `STATE_SNAPSHOT_V0` / candidate discovery: not started.
* Network dependency: **NONE**. AST test forbids `os`, `sys`, `pathlib`, `socket`, `urllib`, `requests`, `httpx`, `aiohttp`, `websockets`, `subprocess`, `sqlite3`, `random`, `time`, `datetime`, `secrets`, `uuid`, `qnty`, `qntypolicygate`, `binance`; the only `qntylab` imports are the three frozen predecessors.

## Success Criteria

All met: artificial roster completeness explicitly scoped to the fixture and carried in the artifact itself; candidate discovery absent; exact candidate identities enforced; duplicates fail closed; exact partition invariant holds and survives into the artifact; candidate independence holds; candidate and evidence ordering irrelevant; future evidence cannot rewrite a historical artifact; future outcomes cannot alter it; data usability has no channel; `UNRESOLVED` preserved exactly; the builder creates no evidence proposition and no candidate-completeness claim; malformed structural inputs form no partial artifact; the artifact binds roster, evidence, policy, builder and query identities; canonical digest deterministic; telemetry descriptive with no threshold; predecessor semantics unchanged; no network or Qnty coupling; hostile review passed after one HIGH fix and one targeted re-review.

## Bounded Stop

Phase closed, **not promoted**. Promotion is a separate bounded gate.

Not started here: PIT Candidate Roster / Discovery Provenance V0, real Binance candidate acquisition, real PIT universe construction, `STATE_SNAPSHOT_V0`, Reactive Jigsaw, Forecaster, Router / ABSTAIN.
