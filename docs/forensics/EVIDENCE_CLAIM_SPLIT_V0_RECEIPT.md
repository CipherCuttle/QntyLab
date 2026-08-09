# Evidence Claim Split V0 — Receipt

Verdict: `EVIDENCE_CLAIM_SPLIT_V0_PASS`.

Phase objective: prove that QntyLab can represent what different evidence types establish without one evidence proposition silently manufacturing another (Evidence Non-Escalation Contract). Artificial fixture phase; no final interval-eligibility policy decided.

## Source Identity

| Field | Value |
| --- | --- |
| root | `/home/swirky/DevHub/repos/QntyLab` |
| branch | `master` |
| starting HEAD | `1cfa2d5e35a1aee73a5efa557637dabfdf6d13fc` |
| pre-existing WIP | 3 modified `data/manifests/*.json`; untracked `data/manifests/*.json`, `.playwright-mcp/`, `experiments/results/`, `experiments/runs/`, `logs/` — left untouched |
| network research attempts | `0` |

Added files (all additive; no existing file modified):

| Path | SHA-256 |
| --- | --- |
| `qntylab/evidence_claim_split.py` | `305876cdc7b9acc35aae8dac2f6eab9d5964350378407706db67e0ff94b52839` |
| `tests/test_evidence_claim_split_v0.py` | `31c712f5572316f6ae77a00d4e86cf866b6cd6fea44a6009c2eded2d00fbbd9a` |

Hashes are of the files as committed; recompute with `sha256sum`.

## Contract Semantics

See `docs/forensics/EVIDENCE_CLAIM_SPLIT_V0_CONTRACT.md`.

Summary: proposition domain (three distinct frozen dataclass types) is kept orthogonal to epistemic status (`ESTABLISHED` / `UNKNOWN`). `UNKNOWN` is not a peer proposition. No negative status exists, so absence of evidence cannot render as a false or ineligible claim. Support requires exact proposition equality plus `available_time <= as_of`; there is no derivation step in the evaluator.

## Artificial Fixture Identity

Fixture: `BASE_EVIDENCE` in `tests/test_evidence_claim_split_v0.py` — one launch boundary, two point observations bracketing a suspension gap, one delist boundary, all for instrument instance `binance|BTCUSDT|perpetual|usd-m|2024-01-01T00:00:00Z`. Every value is synthetic.

```
fixture_digest(BASE_EVIDENCE) = d5dd35267c49c7c3e317b5b8d4fe8a563ddf1289b21481735a44ddd48f2a5c05
```

Canonical-JSON, order-insensitive, domain-tagged, identity-sensitive.

## Falsifiers Executed

| ID | Falsifier | Result |
| --- | --- | --- |
| F1 | suspension gap between 11:00 and 13:00 observations | PASS — 12:00 `UNKNOWN`, interval 11→13 `UNKNOWN`, zero supporting keys |
| F2 | delist → relist instance separation | PASS — no inheritance in either direction |
| F3 | launch boundary before first observation | PASS — no synthetic observation, no interval, no LAUNCH→DELIST cross-establishment |
| F4 | missing observation/archive evidence | PASS — `UNKNOWN`, never negative; siblings unmoved under every single-record removal |
| F5 | wrong contract variant (spot ↔ perpetual) | PASS — both directions |
| F6 | generic `BTC` asset evidence | PASS — binds no instrument instance |
| F7 | future-known evidence / anti-lookahead | PASS — inadmissible below `available_time`; inclusive one-second boundary verified |
| F8 | no evidence at all | PASS — every proposition `UNKNOWN` |

## Test Results

```
python -m pytest tests/test_evidence_claim_split_v0.py -q
31 passed
```

Full suite: `831 passed, 2 failed, 11 errors`. All failures/errors are pre-existing and confined to `tests/test_curated_breadth_summary.py` and `tests/test_holdout_data_audit.py`, caused by untracked `experiments/runs/` WIP tripping a screen-evidence integrity block. They do not import and are not affected by this phase's additive modules.

`git diff --check`: clean.

## Hostile Review

One independent hostile pass, executed as runnable attack probes rather than reading alone. Review question: can any supported input path cause evidence for one proposition, instrument instance, or causal time to silently establish a stronger or different proposition?

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| H-1 | HIGH | Subtype widening. `isinstance`-based acceptance and dispatch allowed a proposition or identity **subclass** carrying extra distinguishing fields to be accepted by `assess`, serialised as its base domain, and digested identically to a different proposition — two distinct fixtures collapsed onto one `fixture_digest`, while the subclass query silently read `UNKNOWN` instead of failing loudly. Confirmed by probe. | FIXED |
| H-2 | MEDIUM | Future-effective evidence (`effective_time > as_of`, already available) is admissible. Judged correct, not a defect: the proposition names its own effective time and establishes nothing about any earlier instant, and V0 exposes no "state now" query. | ACCEPTED, documented as an explicit non-claim, covered by a regression test |
| H-3 | LOW | `__post_init__` validation is bypassable via `pickle` / `object.__setattr__`. Reaching that state requires first constructing a valid record; not a supported input path. | NOT REPAIRED |

Cross-domain equality, empty-evidence handling, string-timestamp chronology, and `supporting_source_keys` leakage were probed and found sound.

### C/H Fixes

H-1 only: proposition, identity and evidence-record admission now dispatch on **exact type** (`type(x) is …` / exact-type set membership) at every entry point — `assess`, `EvidenceRecord.__post_init__`, `proposition_payload`, and therefore `evidence_payload` and `fixture_digest`. Widening raises `ValueError`. Three regression tests added.

### Targeted Re-Review

One re-review, scoped to the H-1 fix. Re-ran the original attack probes: every entry point refuses widened propositions, identities and records; the digest path is unreachable with a widened proposition; legitimate `ESTABLISHED` / `UNKNOWN` paths and the 64-hex digest are unchanged; no new status member was introduced. `PASS`.

## Explicit Non-Claims

* No final interval-eligibility policy — only exact-proposition matching. No coverage, containment, subsumption, interpolation or gap bridging.
* No delist/relist continuity semantics.
* No lifecycle authority, no authentication, no second authentication path. `qntylab/lifecycle.py`, `qntylab/market_observation.py`, `qntylab/binance_um_archive.py`, Qnty, QntyPolicyGate and THT0 unmodified; no lifecycle symbol imported (asserted by AST test).
* No tradability, eligibility, universe, strategy, backtest or profitability claim.
* No network access, no Binance query, no source discovery, no real lifecycle evidence, no PIT universe.
* Not a Router / Jigsaw / State Snapshot feature; `UNKNOWN` is not exposed to any consumer.

## Phase Success Criteria

All met: boundary and observation propositions remain distinct; neither establishes interval eligibility; `UNKNOWN` is not a peer evidence claim; absence never becomes negative evidence; effective and available time are distinct; historical `as_of` excludes future-known evidence; exact instrument identity preserved, with spot/perpetual and delist/relist cross-binding blocked; the artificial suspension gap remains unresolved; no external evidence authentication added; no final interval-eligibility policy implemented; no network or data acquisition; no production lifecycle semantics changed; deterministic tests pass; `git diff --check` clean.

Next phase if accepted: Interval Eligibility Policy V0 (not started here).
