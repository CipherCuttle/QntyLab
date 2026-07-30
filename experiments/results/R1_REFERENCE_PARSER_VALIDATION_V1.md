# R1 reference-parser validation — v1 (Gap 2)

## Scope

Independently validates that raw Bybit trade objects can be transformed into
the frozen `DailyMarketEvidenceV1` contract without relying on the existing
`daily_primitive` candidate's semantic implementation. Outcome embargo intact
throughout: no factor value, rank, weight, return, PnL, IC, or Sharpe was
computed or inspected.

## Terminology

There is no production parser in this repository. The only pre-existing
transform (`daily_primitive` in `qntylab/r1_retention_candidate.py`) has zero
callers anywhere in the codebase and its own module docstring disclaims
frozen status ("candidate, not frozen"). Per explicit instruction for this
task, neither implementation is called "production" or "reference" in a
privileged sense:

- **Parser A** — the independent, contract-derived implementation built for
  this task (`qntylab/r1_reference_parser.py`).
- **Parser B** — the pre-existing `daily_primitive` candidate.

## Input contract verification

All four frozen artifact SHA-256 values and their combined hash, as claimed
in `experiments/results/R1_INPUT_CONTRACT_CLOSURE_V1.md`, were independently
recomputed and matched exactly. Checkpoint commits `81b8a67`/`8a76f78` and the
checkpoint manifest's SHA-256 (`80ed752c...`) were verified against actual
git history and file bytes, not inferred from the task brief.

## Sequencing (independence)

Parser A was designed and implemented from the frozen contract artifacts
alone, with a 21/21-passing test suite, before `r1_retention_candidate.py`
was opened for this task. Its implementation SHA at that point
(`5cc2c3080e331d366ece1dbeb4a5d18c4a631cc54552618c7bbdc0c6d487e6de`) is
recorded in `experiments/data/r1_reference_parser_validation_v1.json`. A
small Phase-10 helper was appended after unblinding; it does not touch trade
parsing.

**Caveat, disclosed rather than hidden:** an earlier read-only Phase-1 audit
(dispatched to establish whether a production parser exists at all) surfaced
high-level facts about `daily_primitive`'s algorithm before Parser A's design.
Full code-blindness was therefore not achieved, though no code was shared or
copied. The specific divergences found below (not the agreements) are the
meaningful evidence of independence.

## Real validation corpus

Five real, gzip-compressed Bybit trade objects already present in
`.r1_input_cache/sha256/` (retrieved by an earlier, separate task; no new
network acquisition performed this pass, since the actual raw trade archive
is a licensed Tardis vendor product per `r1_ingest_contract.json` and no API
credential is present in this repository) were used:

| Object | Date | Schema | Rows | Bytes (gz) |
|---|---|---|---|---|
| BTCUSDT | 2020-03-25 | bybit_trade_v1 | 2,693 | 121,118 |
| UNIUSDT | 2021-11-30 | bybit_trade_v1 | 12,757 | 558,477 |
| ANCUSDT | 2022-03-15 | bybit_trade_v1 | 67,019 | 1,784,626 |
| FTTUSDT | 2022-11-13 (FTX collapse week) | bybit_trade_v1 | 112,618 | 4,184,174 |
| 1000000CHEEMSUSDT | 2026-05-28 | bybit_trade_v1_rpi | 535 | 21,756 |

Selection rationale is recorded in `experiments/data/r1_reference_validation_corpus_v1.json`,
written before any Parser A/B comparison was run. Known gaps (not covered by
real data this pass): 2023–2025 eras; MONUSDT/FHEUSDT/SANDUSDT-vicinity
objects named in the original task brief; a real symbol-reuse case (out of
scope for a single-day trade parser).

Synthetic adversarial fixtures (15 categories: out-of-order rows, exact and
conflicting duplicates, timestamp ties, UTC boundaries, empty/single-trade
days, malformed decimal/timestamp, unknown/missing/reordered columns, future
cutoff, gzip corruption, truncated CSV) are generated inline in
`tests/test_r1_reference_parser.py`.

## Cross-validation results

- **Real objects:** 5 compared, 5 exact-match on `trade_count`, 0
  disagreements on close/open/high/low/base_volume/quote_turnover (within
  1e-9/1e-6 float tolerance against Parser A's Decimal-string values). Parser
  B raised zero anomalies on any real object.
- **Synthetic adversarial cases:** 23 run, 21 agree, **2 confirmed
  disagreements**:
  1. *Exact duplicate differing only in `side`* — Parser B's fingerprint
     includes `side`; the frozen contract's duplicate definition and the
     information-loss ledger (`side`: `INTENTIONALLY_DISCARDED`) do not.
     Non-blocking: numeric output still agreed in the tested case.
  2. *Genuinely conflicting duplicate (same trade id, different price),
     row order reversed* — **blocking**. `r1_source_precedence_freeze.json:conflict_rule`
     requires fail-closed handling. Parser A excludes both rows
     deterministically regardless of row order. Parser B silently retains
     whichever row it iterates to first, so its `close` value depends on raw
     row order (100 vs. 999 in the tested fixture) — contradicting both the
     conflict_rule and Parser B's own docstring claim of full determinism
     under reordering.

Full detail and exact test references: `experiments/data/r1_reference_parser_validation_v1.json`,
`tests/test_r1_parser_a_vs_b_cross_validation.py`.

**Precision-semantics note:** Parser B computes price/size/close/quote_turnover
as Python `float`; the frozen contract requires source-string precision
preservation and explicitly forbids float64 for `quote_turnover`. No object in
this bounded corpus was large/precise enough to expose a visible rounding
divergence, so this is a design non-conformance found by inspection, not (yet)
a numeric disagreement.

## RPI closure

Classification: **UNRESOLVED** (unchanged from the frozen information-loss
ledger). Structurally confirmed to not affect canonical trade identity,
price, size, quote turnover, event ordering, or duplicate semantics; retained
verbatim as a diagnostic, never dropped. This task's real corpus incidentally
surfaced a **second** real RPI-schema object (`1000000CHEEMSUSDT` 2026-05-28,
constant RPI=`0` across all 535 rows) beyond the single 2026-06-30 DOLOUSDT
observation the frozen registry cites — reported as a registry-documentation
undercount finding, not corrected in place (editing a frozen artifact is out
of scope absent an actual contradiction). Semantic resolution still requires
an authoritative Bybit source that does not exist in this repository; no
meaning was invented.

## Derivable notional fields (homeNotional/foreignNotional/grossValue)

Independently re-tested (different 5 objects than the original 5-object
pilot behind the frozen ledger's claim) across both known schema variants,
~195,622 total rows: **zero reconstruction errors** for
`homeNotional == size`, `foreignNotional == size*price`,
`grossValue == foreignNotional * 1e8`. This corroborates and extends, but
does not globalize beyond, the already-checked objects — 2023–2025-era
objects remain untested.

## Schema registry validation

Both known variants (`bybit_trade_v1`, `bybit_trade_v1_rpi`) are recognized
by column-name set (order-independent), matching real objects and a
reordered-header synthetic fixture. An unknown column set is quarantined
(no best-effort parse, all rows rejected, no record produced, raw retention
required) per policy.

## Source mutation contract

Implemented and tested as a fixture-based state check
(`qntylab.r1_reference_parser.check_source_mutation`): a mismatched
freshly-retrieved SHA-256 against a recorded one is reported as
`SOURCE_MUTATION` without ever overwriting the recorded value. No live
mutation occurred or was required to occur.

## Determinism

Verified: identical raw bytes parsed twice yield byte-identical canonical
output; the same logical rows in different file order yield identical
derived fields (excluding `source_object_sha256`, which correctly differs
because the underlying raw bytes differ).

## Required-acquisition hash provenance (`required_acquisition_sha256`)

Audited independently. The target hash
(`d9d8875592a2a19672372b88fa46aadcec36b7f6b58df5af17028e6bca1dc16b`) is the
value BOM v3 (`r1_population_raw_acquisition_bom_v3.json`) self-declares in
its own `required_acquisition_sha256` field. It does **not** match the
canonical SHA-256 of any of: every top-level field (9), every field inside
`required_acquisition` (9), the 894-entry `streams` list as a whole, any
individual stream entry (894 checked), the whole document, or the whole
document with the self-referential field excluded. **Not reproduced** →
this sub-finding is `BLOCKED_BY_PREOUTCOME_PROVENANCE`. This independently
confirms and extends (rather than merely repeats) the prior checkpoint's
`known_dangling_reference` flag. No fake file was created to force
resolution; the reference remains recorded, not repaired.

## Raw deletion firewall

`RAW_DELETION_AUTHORIZED = false`, unchanged. Verified no deletion call
exists in any new file.

## Outcome embargo

Verified intact: no H012/H014 value, factor score, rank, weight, forward
return, PnL, IC, Sharpe, weekly/null/replication outcome was computed,
inspected, or referenced. Sprint-v2 result content was not opened.

## Verdict basis

The frozen contract is independently implementable (Parser A, 28/28 tests
passing) and Parser B conforms to it on every real object and 21 of 23
adversarial cases. However, one adversarial case — conflicting duplicates —
exposes a confirmed, contract-traceable disagreement in Parser B (order-
dependent, non-fail-closed), and this task explicitly must not paper over
that by picking a winner or by calling either implementation "production."

**Verdict: `BLOCKED_BY_REFERENCE_VALIDATION`**

The contract is implementable and Parser A is independently cross-validated
against real and adversarial data; Parser B does not fully conform to the
frozen contract (conflicting-duplicate handling; float64 precision by
design). Production promotion of either implementation remains a separate,
future task. `RAW_DELETION_AUTHORIZED` remains `false`.
