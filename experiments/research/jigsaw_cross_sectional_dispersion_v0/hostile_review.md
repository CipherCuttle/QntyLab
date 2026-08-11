# Hostile review — Jigsaw Cross-Sectional Dispersion V0 (preregistration)

Reviewed independently, against the frozen preregistration and contract module, before any
economic execution exists.

- **Utility compounding convention (CRITICAL, FIXED):** the initial draft's decision-grid
  compatibility note re-binned the frozen hourly CSMOM equity path into daily blocks by *summing*
  hourly net returns. This is inconsistent with the already-frozen Jigsaw utility convention
  (`qntylab.jigsaw_trend_condition_dependence_v0._utility` uses `prod(1+r)-1`, i.e. geometric
  compounding) and would understate compounding, silently changing the measurement definition from
  what the rest of QntyLab's Jigsaw work uses. **Fixed**: `preregistration.json`
  `decision_grid.compatibility_note` now specifies `equity(t+24h)/equity(t) - 1` compounding,
  explicitly bound to the existing `_utility` convention.
- **Arbitrary-looking thresholds (MEDIUM, addressed):** `FAMILY_CONSISTENCY_MINIMUM_VARIANTS = 3`
  of 4 and `DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD = 0.90` had no stated justification in the
  first draft, which is a data-snooping surface if left unexplained (a threshold could later be
  defended post-hoc as "whatever made the result pass"). **Addressed**: both are now justified in
  `literature_design_note.md` against precedent already set by the prior Jigsaw piece's own
  majority-not-unanimity robustness rule, and against a conventional near-collinearity cutoff,
  respectively — fixed from precedent, not tuned against any dispersion outcome (none exists yet).
- **Future leakage:** no Critical/High finding. `cross_sectional_dispersion` takes only
  already-computed period returns as input and performs no time lookups itself;
  `dispersion_percentile_and_bin` delegates byte-for-byte to the already-frozen, already-tested
  `historical_percentile`/`state_bin` functions. Proven by synthetic tests.
- **Missing-member / partial-panel contamination:** no Critical/High finding.
  `cross_sectional_dispersion` raises on any panel deviation (missing, extra, or non-finite member),
  mirroring CSMOM's own whole-panel blocking rule exactly; no partial-panel computation path exists.
- **Best-variant selection / silent search:** no Critical/High finding. `family_consistency` is
  proven order-invariant and never returns or privileges a "best" variant; the module contains no
  `argmax`, no `materialize`/`analyze`/`run`/`main`, and no outcome-selected path (enforced by test).
- **Sample-boundary honesty:** no Critical/High finding, but flagged as a real scientific weakness
  the preregistration does not hide: `DEVELOPMENT_SAMPLE` is `DEV_2024` only, because CSMOM's own
  Breadth V2 execution has zero usable cells in `DEV_2022`/`DEV_2025` (whole-panel blocking,
  verified against `experiments/research/breadth_v2_receipts/*.json`). Cross-window temporal
  stability is therefore explicitly marked `BLOCKED_AT_CROSS_WINDOW_LEVEL` with a labelled-weaker
  H1/H2 2024 substitute, rather than silently omitted or disguised as full 3-window replication.
- **Sealed-cohort contamination:** no Critical/High finding. `DEV_2024` ends 2024-12-31T23:00:00Z,
  well before `SEALED_T0` (2026-08-10T19:00:00Z); `CROSS_SECTIONAL_MOMENTUM` is independently already
  excluded from Breadth V2's sealed observation stream
  (`breadth_v2_sealed.EXCLUDED_DEVELOPMENT_FAIL_FAMILIES`). `is_pre_sealed_t0` is proven correct at
  the exact boundary by synthetic test.
- **Router / Qnty authority creep:** no Critical/High finding. `router_authority`, `promotion_eligible`,
  and `pit_universe_claim` are frozen to `"NONE"` / `False` / `"NONE"` and asserted by test; no gate,
  sleeve, or transition-cost claim is introduced anywhere in the module or preregistration.
- **Multiplicity disclosure:** no Critical/High finding. All degrees of freedom (1 state, 4 variants
  assessed via `consistent_count`, 2 cost modes with 1 primary, 1 temporal split) are enumerated in
  `preregistration.json.multiplicity`, matching `NUMBER_OF_PRIMARY_STATE_HYPOTHESES = 1` proven by
  test.

## Targeted re-review

Required and performed separately: the CRITICAL compounding-definition finding above requires
exactly one targeted re-review under the bounded workflow regardless of the fix's
documentation/specification nature. See `targeted_re_review.md` for that review, which also covers
three further contract issues (primary-cost-mode authority, the undefined "pooled" family statistic,
and the funding/input identity contradiction) surfaced by subsequent direct review evidence and
repaired in this same preregistration-closure pass.

Outcome of this hostile-review pass on its own: `NO_UNRESOLVED_CRITICAL_OR_HIGH_FINDINGS` conditional
on the required targeted re-review passing (it does; see `targeted_re_review.md`).
