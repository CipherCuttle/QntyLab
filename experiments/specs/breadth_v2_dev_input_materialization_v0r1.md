# Breadth V2 development-input materialization V0R1

V0R1 is a bounded correction phase over `BREADTH_V2_DEV_INPUT_MATERIALIZATION_V0`
(`experiments/specs/breadth_v2_dev_input_materialization_v0.md`), triggered by a
post-closure Git audit that found the committed coordinator diverged from its own
frozen contract in two places. V0R1 fixes only those two defects, regenerates
the census from the existing persistent evidence cache, and preserves V0 as
superseded historical evidence. No strategy formula, benchmark, cost, panel
membership, development window, price materialization rule, funding accounting
formula, admission clock, missingness philosophy, source family, `SEALED_T0`,
execution kernel, ledger semantics, or family gate changed.

## Defect A — funding parent overrequest

The V0 contract already stated the correct rule ("Funding sources begin no
later than `T0 - 1 hour`, and carry warmup walks authenticated settlement
events by count, never by `N * 8 hours`"), but the committed coordinator
(`qntylab/breadth_v2_dev_inputs.py`) materialized every funding parent from
`period_start - 180 days`, regardless of profile. This could — and, per the
V0-to-V0R1 transition artifact, does not in this cohort, but could in
general — falsely block a non-carry input on unrelated old-history coverage.

V0R1 fix:

- Ordinary (non-`FUNDING_CARRY`) profiles materialize funding from exactly
  `T0 - 1h` through `T1` (`funding_parent_start`, unchanged — it was already
  correct; only its caller was wired wrong).
- `FUNDING_CARRY` profiles (`funding_window_events` in `{8, 24, 72, 168}`) run
  `discover_funding_carry_start`: starting at the ordinary floor, it counts
  *authenticated, checksum-verified* archive settlement events with
  `admission_boundary <= T0`. If fewer than the registered `N` exist, it
  extends backward by exactly one more official monthly archive object,
  authenticates it, and repeats — until the count is satisfied or the next
  earlier monthly object is `SOURCE_OBJECT_ABSENT` (official history
  terminated). The stopping condition is a real event count; the
  implementation never computes `N * 8h`, `N * current_interval`, or
  `N * average_interval`.
- The discovered parent start is frozen per `(symbol, period, N)` and recorded
  in each READY record's `per_symbol_evidence_summary.funding_parent_source_start`.
  The row-level `funding_source_range` reports the widest range actually used
  across the record's symbols.
- The `180`-day envelope is removed as a scientific rule. A per-symbol prefetch
  envelope still warms the cache with the ordinary range only, purely as a
  transport optimization; it cannot affect admissibility. Additional older
  funding objects are fetched only on demand, during carry backscan, and only
  for symbols/periods that actually need them.
- Raw archive bytes remain shared and content-addressed across profiles
  (`EvidenceCache`, keyed by request URL). Parent materialization
  (`materialize_from_objects`) stays profile-specific: an ordinary parent and
  a carry parent for the same symbol/period are distinct cache entries with
  distinct normalized content, even when built from overlapping raw bytes.

## Defect B — READY/BLOCKED scientific-cell accounting

`build_census` mapped each READY market-input record (already collapsed
across both cost modes) to `1` scientific cell for `SINGLE_ASSET` and `20`
for `SYNCHRONIZED_PANEL` — undercounting by exactly the cost-mode factor.
Each record maps to both `BASELINE_EXECUTION` and `STRESS_EXECUTION`, so:

```
SINGLE_ASSET READY      -> 2 execution descriptors -> 2 scientific cells
SYNCHRONIZED_PANEL READY -> 2 execution descriptors -> 40 scientific cells
```

Fix: `ready_cells` now sums `2` (single) / `2 * len(FROZEN_PANEL_ORDER)`
(panel) per READY record. `blocked_cells = scientific_cell_count() - ready_cells`,
so `ready + blocked` always reconciles to the frozen `3360`. Mapped execution
units were already correct (`2` per record regardless of type) and are
unchanged.

## Unchanged invariants

Registered denominators (`996` / `1992` / `3360`), panel atomicity, price
clip semantics, funding admission boundary computation, missingness
philosophy (`BLOCKED` is never a zero/negative return or a deleted
registration), transport classification (`ACQUISITION_UNRESOLVED` vs
`SOURCE_OBJECT_ABSENT`), and the outcome guard (no runner, `PortfolioKernel`,
strategy function, or ledger writer call) all carry over from V0 unchanged.

## Disposition

`BREADTH_V2_DEV_INPUT_MATERIALIZATION_V0` remains `CLOSED_PASS` as a
historical record, then `SUPERSEDED_FOR_DOWNSTREAM_USE_BY_V0R1`. Its census
(`5c4cff22e43edc14a2b2214fab277f4f2f1f5bfb79f13b389e0a2ebc1e835064`) is
preserved unmutated. Downstream Breadth V2 work must use only
`BREADTH_V2_DEV_INPUT_UNIVERSE_V0R1`
(`experiments/data/breadth_v2_dev_input_universe_v0r1_compact.json`,
`campaign_input_universe_sha256 = 8fef4c02d113027630072bcbb0802e35ab31be17c835aa2ebdae4261265589fb`)
after this phase closes.
