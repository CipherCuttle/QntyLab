# PIT Research Admission Policy V0 — Receipt

Project name: **Interval Eligibility Policy V0**. Semantic role: **PIT Research Admission Policy V0**.

Verdict: `PIT_RESEARCH_ADMISSION_V0_PASS`.

Phase objective: freeze the smallest defensible point-in-time research admission policy — may this exact instrument identity enter a historical calculation over `[query_start, query_end)`, using only evidence available by `as_of`? Artificial fixture only.

## Baseline and Isolation

| Field | Value |
| --- | --- |
| repo | `/home/swirky/DevHub/repos/QntyLab` (QntyLab) |
| master HEAD at start | `74b4e7c3a825732423a29bb1ac1bcadd2541dffe` |
| `origin/master` | identical to local `master` |
| `QNTYLAB_HYGIENE_V0` | `CLOSED`, not reopened |
| predecessor | Evidence Claim Split V0, `81b3345cce78076344e996c5c1908e0b2d5651ab`, `CLOSED / PASS` |
| branch | `research/pit-research-admission-v0` |
| worktree | `/home/swirky/DevHub/worktrees/QntyLab-pit-research-admission-v0` |
| parent commit | `74b4e7c3a825732423a29bb1ac1bcadd2541dffe` |
| main worktree | 187 preserved dirty paths, untouched; nothing cleaned, nothing staged from it |
| network research attempts | `0` |

Added files (all additive; no existing file modified):

| Path | SHA-256 |
| --- | --- |
| `docs/forensics/PIT_RESEARCH_ADMISSION_V0_CONTRACT.md` | `904424faae35d8d59da76c7d3765bd27e6443a14457cd8242e94766a3c3618f5` |
| `qntylab/pit_research_admission.py` | `3743adde0faa9f29906bdc52c98d9aa22b91c89b5b012aaa66e0e887f23d7036` |
| `tests/test_pit_research_admission_v0.py` | `361fff9cbf29347c89981afb4bccca52fc0c996e2bd9c63225b6898cb85a21b3` |

Hashes are of the files as committed; recompute with `sha256sum`.

## Contract

See `docs/forensics/PIT_RESEARCH_ADMISSION_V0_CONTRACT.md`. Summary of the frozen surface:

| Item | Frozen value |
| --- | --- |
| outputs | `ADMIT` / `REJECT` / `UNRESOLVED` (policy actions, never world-state claims) |
| query interval | `[query_start, query_end)` half-open |
| PIT rule | `query_start < query_end` and `query_end <= as_of` |
| invalid query | `InvalidPITQuery` raised at request construction; no decision object exists, so it can never read as `REJECT` |
| evidence admissibility | `available_time <= as_of`, applied before any other property of the dataset is observed |
| establishment gate | predecessor `evidence_claim_split.assess(...) == ESTABLISHED`; no second evidence gate |
| identity | exact `InstrumentIdentity` equality over all four fields; exact types only, no subclasses |
| ADMIT grounds | `INTERVAL_CLAIM_COVERS_QUERY`, `BOUNDARY_WINDOW_COVERS_QUERY` |
| REJECT grounds | `DELIST_AT_OR_BEFORE_QUERY_START`, `DELIST_INSIDE_QUERY`, `LAUNCH_AT_OR_AFTER_QUERY_END`, `LAUNCH_INSIDE_QUERY` |
| conflict | any admit ground ∧ any reject ground → `UNRESOLVED` + `CONFLICTING_EVIDENCE`; no precedence invented |
| default | `UNRESOLVED` + `INSUFFICIENT_EVIDENCE` |
| policy identity | `qntylab.pit_research_admission` / `v0` / contract digest `8c59865a54cb1ddeb061a3c22f6a2741e60751570bc1101cd2f43752f4709cb2` |

`POLICY_CONTRACT_DIGEST` is a SHA-256 over the canonical rule spec literal embedded in the module, so any rule change changes the digest carried by every decision.

Frozen V0 limitation, documented rather than repaired: boundary evidence alone cannot admit a still-listed instrument, because "no delist evidence exists" is absence of evidence and must not close the right edge. Such a query is `UNRESOLVED`; admitting it requires an explicit `IntervalEligibilityProposition`.

## Fixture Matrix Executed

| ID | Fixture | Result |
| --- | --- | --- |
| F1 | exact instrument, launch ≤ start and delist ≥ end known by `as_of` | PASS — `ADMIT` / `BOUNDARY_WINDOW_COVERS_QUERY`; covering interval claim also `ADMIT` |
| F2 | same effective evidence, available only after `as_of` | PASS — `UNRESOLVED`, byte-identical to the no-evidence decision |
| F3 | no relevant evidence | PASS — `UNRESOLVED` + `NO_EXACT_IDENTITY_EVIDENCE`, empty basis |
| F4 | generic `BTC` / spot / relisted-instance evidence | PASS — `UNRESOLVED` + `IDENTITY_MISMATCH`; foreign exclusion evidence cannot reject either |
| F5 | exact-instrument exclusion evidence | PASS — `REJECT` for delist ≤ start, launch ≥ end, and boundaries strictly inside |
| F6 | exact-time observation inside a wider query | PASS — `UNRESOLVED`; observations bracketing the query do not bridge it; observation never rejects |
| F7 | 18 `UNKNOWN`-producing records (foreign identity, wrong domain, future-known) | PASS — `UNRESOLVED`, never `REJECT`, empty basis |
| F8 | `query_end > as_of`, plus empty/inverted/malformed/invalid-instant requests | PASS — `InvalidPITQuery`, never a decision; `query_end == as_of` valid |
| F9 | interval claim vs delist inside; two launches | PASS — `UNRESOLVED` + `CONFLICTING_EVIDENCE`; no resolution by recency or order |
| F10 | all 24 permutations of a 4-record set; duplicated records | PASS — identical decision, reasons, basis, digest |
| F11 | 5 base sets × 6 shapes of future-available evidence | PASS — every field byte-identical; brute-force probe found 0 leaks over all future-evidence subsets |
| F12 | post-query observation density / eventual-delist surrogates differ | PASS — decision and digest unchanged; evaluator signature has no outcome channel |
| F13 | boundaries exactly at `query_start` / `query_end` | PASS — launch@start opens, launch@end rejects, delist@start rejects, delist@end closes the window; observation@start inside, observation@end outside |
| F14 | `available_time == as_of` | PASS — admissible |
| F15 | `available_time == as_of + 1s`; one edge future-available | PASS — excluded; no half-admission |
| F16 | delist/relist episodes | PASS — each episode admits only its own window; relist does not repair the earlier gap; later episode cannot admit an earlier interval; spanning queries never `ADMIT` |

## Test Results

```
python -m pytest tests/test_pit_research_admission_v0.py -q          66 passed
python -m pytest tests/test_evidence_claim_split_v0.py -q            31 passed   (predecessor regression)
python -m pytest tests/test_market_observation.py tests/test_lifecycle.py -q     50 passed   (neighbours)
```

Full suite, run once: `894 passed, 41 failed, 32 errors`. Classified **unrelated**: re-running the identical suite with the two phase files removed gives `828 passed, 41 failed, 32 errors` — the same failure set, differing only by this phase's 66 passing tests. All failures are pre-existing, data-dependent tests (`data/raw`, manifests, `experiments/runs/` are gitignored and absent in a fresh worktree) in `test_materialize_halt_normalized_holdout`, `test_r1_source_structure_recognition_amendment_v1`, `test_curated_breadth_*`, `test_holdout_data_audit`, `test_focused_trend_*`, `test_lab`, `test_binance_spot_halt_normalization_v1`, `test_r1_*_repair_v1`, `test_r1_daily_market_materializer`. None import this phase's modules. No repair campaign started; no market experiment rerun.

`git diff --check`: clean.

## Hostile Review

One independent hostile pass, executed as runnable attack probes against the exact contract + diff. Attack question: can this policy use evidence for one proposition, identity, time, or future outcome to silently admit/reject a stronger or different historical interval?

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| H-1 | HIGH | Subtype widening in the decision-identity layer. `_basis_payload` accepted any `EvidenceBasisEntry` subclass and serialised it as the base entry, so two decisions whose bases differed only in a subclass's extra distinguishing field produced the **same** `decision_digest`. Confirmed by probe (`A1: digests equal → True`). Same widening class as the predecessor's H-1. | FIXED |
| H-2 | MEDIUM | `INTERVAL_CLAIM_COVERS_QUERY` reads a wider eligibility claim as covering a sub-interval, which the predecessor's `assess` deliberately does not do. Judged correct, not a defect: it is entailment *within* one proposition domain, applied at the policy layer to an admission **action**. The module never asserts the sub-interval proposition as `ESTABLISHED` and never writes it back as evidence (AST-asserted). | ACCEPTED, documented as a frozen rule |
| H-3 | LOW | The module namespace re-exports the predecessor's proposition class names (imported for exact-type dispatch), so a caller could construct propositions "via" this module. No behavioural consequence: an AST test proves none is ever called here, and the predecessor's own constructors are the same objects. | NOT REPAIRED |

Probed and found sound: future-knowledge leakage (brute force over all future-evidence subsets × 5 base sets — 0 changes to any decision field); effective-vs-available-time confusion; generic-asset and widened-identity escalation (refused at proposition construction and at request construction); observation→interval escalation; absence→rejection (brute force over all boundary-free evidence sets — 0 rejections); `UNKNOWN`→`FALSE`; conflict ordering and recency; half-open boundary off-by-one; forged basis roles; generator-input single-consumption; reason-code vocabulary closure, sorting and dedup over an exhaustive 8-record subset sweep (0 violations, and no `ADMIT` ever carried a reject-ground code).

### C/H Fixes

H-1 only: `_basis_payload` now admits exactly `EvidenceBasisEntry` (`type(entry) is …`) and raises `ValueError` on any subclass. Three regression tests added (widened basis entry, widened decision type, forged role).

Also applied while building, not a review finding: `_established` deduplicates the predecessor's `supporting_source_keys` before they enter the basis, so an evidence set that repeats one identical record cannot produce a different canonical decision. The predecessor's `Assessment` is unchanged.

### Targeted Re-Review

One re-review, scoped to the H-1 fix. Re-ran the full probe battery: A1 now refuses widened basis entries; A2–A10 unchanged (forged role refused, widened identity refused at both entry points, 0 absence-driven rejections, 0 future-evidence leaks, conflict still `UNRESOLVED`, boundary behaviour unchanged, 0 vocabulary violations), digest still 64-hex, no new decision or reason-code member introduced. `PASS`.

## Predecessor and Coupling

* `qntylab/evidence_claim_split.py` — **unmodified**. Its `ESTABLISHED`/`UNKNOWN` vocabulary, `BOUNDARY_KINDS`, exact-match `assess` semantics and non-escalation guarantees are unchanged and re-asserted by a test in this phase. The Evidence Claim Split receipt was not rewritten.
* `qntylab/lifecycle.py`, `qntylab/market_observation.py`, `qntylab/binance_um_archive.py` — unmodified. No lifecycle redesign.
* Qnty coupling: **NONE**. QntyPolicyGate coupling: **NONE**. Router / Jigsaw / PIT Universe Fixture / `STATE_SNAPSHOT_V0`: not started.
* Network dependency: **NONE**. AST test forbids `os`, `sys`, `pathlib`, `socket`, `urllib`, `requests`, `httpx`, `subprocess`, `sqlite3`, `random`, `time`, `datetime`, `qnty`, `qntypolicygate`; the only `qntylab` imports are `evidence_claim_split` and `market_observation`.

## Success Criteria

All met: fact vs policy decision explicit; `ADMIT`/`REJECT`/`UNRESOLVED` frozen; invalid query distinct from `REJECT`; `[start,end)` frozen; `end <= as_of` enforced; future-known evidence cannot leak backward (whole decision, not just the outcome); exact instrument identity enforced; absence of evidence never becomes negative evidence; exact-time observation cannot prove an interval; missing experiment/price/funding data has no channel into admission; future outcome and survival cannot drive admission; conflicts fail closed deterministically; input ordering cannot change output; policy identity and digest deterministic; predecessor semantically unchanged; fixture matrix F1–F16 passes; no network, no live data, no Qnty coupling.

## Bounded Stop

Phase closed. Not started here: PIT Universe Fixture V0, `STATE_SNAPSHOT_V0`, Reactive Jigsaw, Router, live Binance acquisition, real historical universe construction, backtesting.

Next phase if accepted: **PIT Universe Fixture V0** (not authorized in this task).
