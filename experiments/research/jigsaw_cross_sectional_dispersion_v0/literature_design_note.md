# JIGSAW_CROSS_SECTIONAL_DISPERSION_V0 — literature and design note

Phase: `JIGSAW_CROSS_SECTIONAL_DISPERSION_PREREGISTRATION_V0` (design only; no economic execution).

## Bounded literature pass

Claims are classified explicitly. Nothing here is imported into QntyLab as evidence; the QntyLab
proposition (`experiments/research/jigsaw_cross_sectional_dispersion_v0/preregistration.json`) stands
or falls on its own preregistered, later-executed measurement.

1. **Zhang & Makgolo (2026), "Cross-Sectional Dispersion and the State Dependence of Cryptocurrency
   Momentum," SSRN working paper 6648082.**
   - SOURCE-SUPPORTED FACT: the paper reports that cross-sectional return dispersion across coins
     predicts momentum breakdowns, and that in extreme dispersion regimes momentum weakens sharply.
   - SOURCE-SUPPORTED FACT: the paper reports a dispersion-scaled strategy improved a Sharpe ratio
     from 0.63 to 0.80 and cut max drawdown from -42.5% to -17.1% (a strategy-construction result, not
     a QntyLab result).
   - INFERENCE: this suggests HIGH dispersion -> WEAKER momentum as the plausible sign.
   - UNRESOLVED: exact universe, dispersion statistic, momentum construction, and horizon used in the
     original paper were not independently verified here (SSRN abstract page returned HTTP 403 to the
     read-only fetch tool). Nothing from this paper's magnitude, cell definition, or backtest is copied
     into this preregistration; it is used only as the hypothesis-seed for direction.
   - HYPOTHESIS SEED, not QntyLab evidence, not validated mechanism, not replication, not authority.

2. **Daniel & Moskowitz (2016), "Momentum Crashes," Journal of Financial Economics 122, 221-247
   (NBER w20439 lineage).**
   - SOURCE-SUPPORTED FACT: momentum strategies exhibit infrequent, partly forecastable crash
     episodes concentrated in "panic" states following market declines and during high volatility;
     the low ex-ante expected return in panic states is consistent with a conditionally high premium
     on the option-like payoff of past losers.
   - INFERENCE: high cross-sectional dispersion is mechanistically adjacent to the panic/high-volatility
     states this paper identifies as momentum-crash-prone, giving a candidate causal story (not proof)
     for why dispersion could condition cross-sectional momentum specifically, independent of the 2026
     working paper's own claim.
   - DESIGN PROPOSAL: use this only to justify that a directional hypothesis is mechanistically
     reasonable to freeze now, not to import any parameter or threshold.

3. **White (2000), "A Reality Check for Data Snooping," Econometrica 68(5), 1097-1126.**
   - SOURCE-SUPPORTED FACT: repeated inference over the same data without accounting for the search
     inflates the chance a "best" result is spurious; a benchmark-comparison procedure is needed when
     many specifications are tried.
   - DESIGN PROPOSAL: this is why the FAMILY-FIRST design here fixes all 4 CSMOM lookback variants and
     a single dispersion recipe *before* any outcome, with an explicit 3-of-4 consistency rule rather
     than a "pick whichever variant/threshold looks best" search.

4. **Harvey, Liu & Zhu (2016), ". . . and the Cross-Section of Expected Returns," Review of Financial
   Studies 29(1), 5-68.**
   - SOURCE-SUPPORTED FACT: given the scale of factor mining in the literature, a newly proposed factor
     should be held to a materially higher significance bar than conventional thresholds; the paper
     argues much of the published cross-section literature likely reflects data mining.
   - DESIGN PROPOSAL: reinforces `NUMBER_OF_PRIMARY_STATE_HYPOTHESES = 1` and the ban on post-hoc
     threshold/horizon search in this preregistration; this phase does not attempt a t-stat hurdle
     calibration, but explicitly documents the multiplicity that does exist (4 variants, 2 cost modes,
     1 temporal split) so a later execution phase cannot silently expand it.

5. **Bailey, Borwein, López de Prado & Zhu (2015), "The Probability of Backtest Overfitting," and
   related CSCV literature.**
   - SOURCE-SUPPORTED FACT: the best in-sample result among many trialled configurations systematically
     overstates out-of-sample performance; PBO/CSCV estimates the probability of this overfitting.
   - DESIGN PROPOSAL: this phase does not register a PBO diagnostic (Breadth V2's own Section 10 already
     restricts the diagnostic stack to Hansen SPA and Deflated Sharpe Ratio for strategy-level work, and
     this is a measurement-only Jigsaw piece, not a strategy screen); instead the discipline is applied
     structurally, by freezing the variant set and consistency rule before any outcome is computed, so
     there is no "best in-sample cell" to select from in the first place.

No more than the required ~5 core sources were used; the phase cap of ~8 was not needed.

## Distinct new proposition

The existing `JIGSAW_TREND_CONDITION_DEPENDENCE_V0` piece measured `MARKET_DRAWDOWN_30D`,
`MARKET_RV_7D`, and `MARKET_CORR_7D` conditioning a fixed H003 MA 24/96 long/flat process on
BTC/ETH/SOL. This proposition is distinct on every axis:
- different state (`CROSS_SECTIONAL_DISPERSION`, not reused as a competing hypothesis here — the old
  three states are used only for a descriptive redundancy check, never as alternate primary states);
- different measurement process (`CROSS_SECTIONAL_MOMENTUM`, a relative-value long/short process on the
  20-asset Breadth V2 panel, not a single-asset long/flat trend overlay on BTC/ETH/SOL);
- different panel (20 Breadth V2 assets, none of which are BTC/ETH/SOL);
- different development sample (`DEV_2024` only, versus the H003 piece's longest-common-contiguous
  BTC/ETH/SOL path).
No prior committed QntyLab experiment tests `CROSS_SECTIONAL_DISPERSION` (the only prior "dispersion"
hits in the repository are `sprint_v2_execute.py`'s unrelated weekly-anchor robustness spread
`max(values) - min(values)`, not a market-state variable).

## Measurement-family fit: why CROSS_SECTIONAL_MOMENTUM survives read-only scrutiny

`CROSS_SECTIONAL_MOMENTUM` is the primary candidate per the phase brief because dispersion has a
direct conceptual relation to its ranking opportunity set. Before freezing it, the following was
verified read-only against the committed Breadth V2 corpus:

- It is a **registered, frozen family** with exactly 4 registered lookback variants (24/72/168/336h;
  `CANDIDATE_BREADTH_V2_CSMOM_24/72/168/336` in `experiments/research/candidates.jsonl`), a frozen
  20-asset panel, frozen tail fraction (20%) and gross exposure (2.0), and a frozen benchmark (FLAT).
  Nothing about its target-weight computation (`qntylab.breadth_v2_strategies.cross_sectional_weights`)
  needs to change to serve as a measurement process here.
- Its Breadth V2 family status is `FAIL` (`final_frozen_family_status: "FAIL"` in
  `BREADTH_V2_DEVELOPMENT_DECISION_V0.json`), and it is explicitly excluded from the sealed
  observation stream (`breadth_v2_sealed.EXCLUDED_DEVELOPMENT_FAIL_FAMILIES`). Per the phase brief, a
  failed strategy family may still serve as a fixed measurement process for Jigsaw research; this does
  not reopen it for strategy advancement, and it has zero interaction with the sealed cohort.
- **Discovered constraint, not selected for convenience:** the whole-panel missing-member rule
  (`breadth_v2_execution_contract_v0.md`: "Missing panel members block the whole panel") means
  `DEV_2022` and `DEV_2025` have **zero** usable CSMOM cells (16 of 24 planned cells blocked; only the
  8 `DEV_2024` cells — 4 variants x 2 cost modes — have receipts under
  `experiments/research/breadth_v2_receipts/`). This is an honest, verified limitation carried into the
  design: `DEVELOPMENT_SAMPLE = DEV_2024` only, and cross-window temporal-stability robustness is
  correspondingly weaker than the prior Jigsaw piece's 3-year BTC/ETH/SOL sample. This was discovered
  by inspection, not chosen to reach a nicer result — it was true before any outcome was computed.

## Variant-selection problem: FAMILY-FIRST chosen over single-frozen-coordinate

FAMILY-FIRST is used (all 4 registered CSMOM lookbacks, pooled under a predeclared 3-of-4 directional
consistency rule) rather than SINGLE-FROZEN-MEASUREMENT, because:
- only 4 coordinates exist (not a large search space);
- all 4 already have usable `DEV_2024` receipts, so nothing needs to be newly computed to include them;
- a family-level claim is more useful Jigsaw evidence than a single-lookback claim, and the phase
  brief prefers FAMILY-FIRST when expressible without inventing new strategy semantics — here it is,
  because the one frozen dispersion recipe is deliberately decoupled from any one CSMOM lookback (see
  `dispersion_recipe.rejected_alternatives_recorded_not_tested` in the preregistration).

## Threshold justification (non-performance-based, frozen before outcomes)

- `FAMILY_CONSISTENCY_MINIMUM_VARIANTS = 3` of 4: chosen to require a clear majority without demanding
  unanimity, mirroring the precedent already set by the prior Jigsaw piece's own robustness rule
  (`temporal_support >= 2` of the non-2024 years, `non_missing_assets >= 2` of 3 assets — i.e. "more
  than half, not all"). Applied to 4 coordinates, the nearest majority-plus analog is 3 of 4 (75%).
  This was fixed from that existing precedent, not tuned against any dispersion outcome.
- `DISTINCTNESS_ABS_CORRELATION_KILL_THRESHOLD = 0.90`: a conventional near-collinearity cutoff,
  deliberately stricter (higher bar to kill) than the more common 0.7-0.8 multicollinearity screens
  used elsewhere in applied finance, so a new state is not discarded on merely moderate correlation
  with an existing one.

## Ten-stack design review (one bounded pass)

1. **Socratic** — Yes, one genuinely new question: does a cross-sectional dispersion state condition
   the already-failed CSMOM family's utility, independent of the three states already tested against a
   different measurement process on a different panel.
2. **Popperian** — Killed by: pooled STRESS contrast not negative, or <3/4 variants consistent, or
   sign flip under cost/tail/temporal-half attacks, or |correlation| >= 0.90 with an existing state.
   Each is frozen in `kill_defer_criteria` before any outcome exists.
3. **Bayesian** — Prior update: the H003 drawdown piece's own external replication came back
   `EXTERNAL_REPLICATION_MIXED` / `PREDICTIVE_PIECE_REMAINS_WEAK`. That lowers the prior probability
   that any single new Jigsaw condition-dependence piece will replicate cleanly; this design does not
   relax any threshold to compensate, and treats a `PREDICTIVE_PIECE_CANDIDATE` outcome (if earned) as
   provisional in the same way the drawdown piece turned out to be.
4. **Causal/mechanistic** — Dispersion is a plausible mechanism variable (divergence of opinion /
   idiosyncratic-versus-common movement, per the Daniel & Moskowitz panic-state logic), not merely
   another stress-magnitude proxy like RV; it is tested for redundancy against RV/drawdown/corr
   descriptively, not assumed distinct.
5. **Systems** — State evidence (this Jigsaw piece) is architecturally separate from strategy
   authority: `promotion_eligible=false`, `router_authority="NONE"`, no gate or sleeve is created, and
   the underlying CSMOM family status (`FAIL`) is unchanged.
6. **Cybernetic** — A `KILLED`/kill-criterion outcome removes this state from further Jigsaw search
   (it is not silently retried with a different threshold); it reduces future architecture rather than
   triggering a rescue re-review, matching the phase's "medium/low does not restart" rule but scoped to
   genuine kill conditions.
7. **Hegelian/separation** — Measurement (`MEASUREMENT_STRATEGY_UTILITY` of a fixed, unmodified CSMOM
   process) is kept fully separate from intervention (no gate, no Router semantics, no transition-cost
   claim for a hypothetical gate).
8. **MDL** — One state, one dispersion recipe, one decision grid, one already-frozen panel, one
   already-frozen measurement family (reused, not reimplemented) is the minimum-description experiment
   that can answer the question; no additional state, horizon, or universe was introduced.
9. **DOE/multiplicity** — All degrees of freedom are frozen and counted in `multiplicity` above:
   1 primary state hypothesis, 4 pooled (not selected) variants, 1 primary cost mode (STRESS) with
   BASELINE as secondary, 1 temporal split (H1/H2 2024) as a labelled-weaker substitute.
10. **Adversarial** — Survivorship: panel membership is frozen by the pre-existing Breadth V2
    source-conditioned freeze, unaffected by this experiment. Tails: five-best/five-worst removal is
    preregistered. Missingness: whole-panel fail-closed by construction, checked as an integrity
    assertion. Time concentration: H1/H2 2024 split and explicit acknowledgement that cross-window
    stability cannot be tested. Costs: BASELINE/STRESS sign-preservation required. Variant choice:
    3-of-4 consistency rule fixed before outcomes, no best-variant selection. Leakage: dispersion and
    percentile normalization use only trailing/contemporaneous-at-t information, proven by synthetic
    tests in `tests/test_jigsaw_cross_sectional_dispersion_v0.py`.

## External evaluator check

One bounded, read-only repository search for `QntyAgentEval` / `qnty_agent_eval` / `QNTY_AGENT_EVAL`
found no matches anywhere in the repository. Result: **NO_MATCH**. Per policy this does not block
closure and no new evaluator was built.
