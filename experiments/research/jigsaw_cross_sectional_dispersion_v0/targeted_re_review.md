# Targeted re-review — Jigsaw Cross-Sectional Dispersion V0 (preregistration closure)

Scope: exactly the five items below. This is not a second broad hostile review; no new surface was
solicited beyond the direct review evidence that identified these four contract issues (plus the
originally outstanding re-review obligation for the compounding fix).

## a) Original CRITICAL compounding fix

`hostile_review.md`'s CRITICAL finding (initial draft summed hourly returns into daily blocks,
contradicting the frozen `qntylab.jigsaw_trend_condition_dependence_v0._utility` `prod(1+r)-1`
convention) was fixed in the same closure pass that recorded it, but no separate targeted re-review
had been performed — the fix's documentation/specification nature is not an exception to that
requirement.

Re-verified now: `preregistration.json` `decision_grid.compatibility_note` specifies
`equity(t+24h)/equity(t) - 1` geometric compounding of the hourly net-of-cost equity ratio, explicitly
bound to the existing `_utility` convention, and cross-references this file. No code in
`qntylab/jigsaw_cross_sectional_dispersion_v0.py` implements the aggregation itself (no
`materialize`/`run`), so there is no executable path that could silently regress to additive summation
before the execution phase; the specification is the only artifact to check, and it is internally
consistent. **Result: CONFIRMED FIXED, no Critical/High remains.**

## b) Primary-cost consistency

Direct review found `PRIMARY_COST_MODE = BASELINE_EXECUTION` in the module/spec contradicting
`primary_hypothesis`/`multiplicity`, which treated STRESS as primary.

Canonical authority reconciled (not preference, not observed results):
- `experiments/specs/breadth_v2_preregistration.md` Section 8, items 2 and 4: family advancement
  gates on "positive **stressed** benchmark excess" and retaining "**stressed** net-return advantage" —
  STRESS is the binding cost mode in the one existing frozen family-level advancement authority that
  covers `CROSS_SECTIONAL_MOMENTUM` itself.
- `qntylab/jigsaw_trend_condition_dependence_v0.py` `analyze()`: eligibility is anchored on
  `stress = primary[state]["STRESS"][...]`, with `same_sign(baseline)` checked only as an additional
  requirement on top of a non-`None` STRESS value — the prior Jigsaw piece's own precedent is
  STRESS-primary, BASELINE-secondary.

Both authorities agree; there is no conflicting frozen authority favoring BASELINE. Fixed:
`PRIMARY_COST_MODE = "STRESS_EXECUTION"`, `SECONDARY_COST_MODE = "BASELINE_EXECUTION"` in
`qntylab/jigsaw_cross_sectional_dispersion_v0.py`; `preregistration.json` `cost_contract` now states
the mode and its authority citation explicitly; `robustness_contract.cost_robustness` and all
`kill_defer_criteria` referencing cost were rewritten to test BASELINE as a secondary check against
the STRESS-based verdict, never the reverse. Verified by
`test_primary_cost_mode_matches_frozen_breadth_v2_and_jigsaw_authority`. **Result: CONFIRMED FIXED,
contract and module now agree, resolved from existing authority only.**

## c) Family primary-statistic determinism

Direct review found "pooled family-first HIGH_MINUS_LOW_MEAN_UTILITY" used repeatedly in
`preregistration.json` without a defined implementation, while the module only ever defined the
symmetric 3-of-4 sign-consistency count.

Fixed using the minimum-authority solution specified in the review: the primary family statistic is
now explicitly and solely `consistent_count` (count of the 4 registered variants whose STRESS
`HIGH_MINUS_LOW_MEAN_UTILITY` has the preregistered negative sign; threshold `>= 3`), computed only by
`qntylab.jigsaw_cross_sectional_dispersion_v0.family_consistency()`. A new
`preregistration.json.primary_family_statistic` block states this definition, the threshold, and an
explicit `no_pooled_scalar` disclaimer correcting the prior draft language. Every remaining
"pooled ... contrast" phrase in `variant_treatment`, `multiplicity`, `robustness_contract`, and
`kill_defer_criteria` was rewritten in terms of `consistent_count` (per-cost-mode, per-half,
per-trimmed-sample) rather than an undefined scalar. No economic averaging/ensemble across variants
was introduced — none is required by any existing frozen authority for a measurement-only Jigsaw
piece. **Result: CONFIRMED FIXED, "pooled" is no longer implementation-defined; the module already
computed the correct minimum-authority statistic, only the specification prose was wrong.**

## d) Funding/input identity

Direct review found `candidate_proposal.json` declaring `funding_boundary_mode: NOT_APPLICABLE` and
OHLCV-only required data, while `preregistration.json` requires realized Binance USD-M funding,
fail-closed on gaps.

Reconciled by binding to the exact pre-existing value, not inventing a new mode: `CROSS_SECTIONAL_MOMENTUM`
is Breadth V2 Tier A (OHLCV-only *decision input*, per Section 5), but the frozen `PortfolioKernel`
still charges/pays realized funding settlements for any open perpetual position regardless of tier
(Section 6/7), and the four registered `CANDIDATE_BREADTH_V2_CSMOM_*` events in
`experiments/research/candidates.jsonl` already carry
`funding_boundary_mode: REALIZED_FUNDING_SETTLEMENTS_REQUIRED` — verified directly against the ledger
by `test_funding_boundary_mode_matches_the_registered_csmom_variants` (asserts all 4 match). Fixed:
`candidate_proposal.json` now carries the identical value, `required_data` names the funding
requirement explicitly, `qntylab/jigsaw_cross_sectional_dispersion_v0.py` gained a
`FUNDING_BOUNDARY_MODE` constant bound to the same string and included in `contract_payload()`, and
`BLOCKED_BY_MEASUREMENT_PROCESS_IDENTITY` now also fails closed on a funding-mode mismatch at
execution time. Because this changed the event's identity payload, the ledger `variant_id` was
recomputed deterministically (`compute_variant_id`) rather than hand-edited, and the candidate was
re-proposed with a fresh `event_id` into a clean ledger reconstructed from the pre-registration
parent commit (this branch is unmerged, so no accepted history was rewritten). Verified by
`test_candidate_proposal_funding_and_input_identity_is_consistent` and
`test_candidate_proposal_variant_id_is_the_deterministic_ledger_hash`. **Result: CONFIRMED FIXED.**

## e) Contract-digest coherence

`contract_digest()` recomputed after (b)–(d): `d2227ac387852a23d5fb2b09d8656ba7678f460cffc2478afaa1ea5b7d882182`
(previously `b9aaea55e55483074dce0a4f49873257a46c222116e37361c440b0903a6be6ad`, which is now stale and
must not be cited as current anywhere). `contract_payload()` includes `primary_cost_mode`,
`secondary_cost_mode`, and `funding_boundary_mode`, so any future drift in these three values changes
the digest and is caught by `test_contract_digest_is_deterministic`; `preregistration.json` continues
to bind by function reference (`qntylab.jigsaw_cross_sectional_dispersion_v0.contract_digest()`)
rather than a hardcoded value, so the specification cannot silently diverge from the module. No other
file in the repository hardcodes the old digest (checked by direct search). **Result: CONFIRMED
COHERENT.**

## Verdict

No Critical/High finding remains open across (a)–(e). `NO_CRITICAL_OR_HIGH_FINDINGS`. No further
re-review is triggered.
