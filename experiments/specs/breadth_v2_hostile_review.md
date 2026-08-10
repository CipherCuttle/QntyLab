# Breadth V2 hostile review

Review ID: `QNTYLAB_BREADTH_V2_HOSTILE_REVIEW_20260810`  
Reviewed artifact: `experiments/specs/breadth_v2_preregistration.md`  
Review date: `2026-08-10`  
Disposition: `REGISTRATION_ACCEPTED_EXECUTION_BLOCKED_UNTIL_DEPENDENCIES_CLOSE`

## Checks

- **Mechanism duplication:** pass. The catalog keeps the existing price-overlay families as comparators and adds cross-sectional momentum, cross-sectional reversal, and funding carry. Volatility targeting is explicitly a risk transformation, not an eighth alpha claim.
- **Outcome leakage:** pass. The panel is inherited from a historical identity freeze; current listing, liquidity, V2 outcomes, and missingness cannot alter membership. The later outcome-exposure receipt is disclosed and prevents any pristine-OOS claim.
- **Panel integrity:** pass. The exact 20 symbols and historical cohort digest are recorded. No dynamic top-N selection, backfill, or survivorship filter is allowed.
- **Period integrity:** pass. `DEV_2022`, `DEV_2024`, and `DEV_2025` are fixed before execution. 2023 and 2026 are not relabeled as fresh historical holdouts.
- **Funding accounting:** pass as a design; execution blocked. The contract requires realized event-time settlement accounting and fail-closed source gaps. `BINANCE_USDM_FUNDING_SETTLEMENT_MATERIALIZER_V0` is not implemented by this task.
- **Benchmark semantics:** pass. Timing overlays use buy-and-hold; long/short relative-value families use flat; volatility targeting uses its unscaled parent.
- **Cost completeness:** pass. Both registered modes include the same realized funding cash flow plus their frozen fee/slippage assumptions.
- **Multiplicity arithmetic:** pass after correction. `4+4+4+4+4+4+4 = 28` and `28 × 20 × 3 × 2 = 3,360`; the registration records that denominator.
- **Family gate integrity:** pass conditionally. Neighbour support, temporal breadth, asset breadth, concentration, and accounting integrity are fixed before outcomes and do not reduce to one magic scalar.
- **Tier-C containment:** pass. No order book, liquidation reconstruction, tick warehouse, options, social/news, router, ML, or portfolio optimizer is registered.

## Execution blockers

The registration is internally consistent, but execution remains blocked until the Tier B funding materializer and all required candidate proposal events are present and independently verified. This review authorizes neither data acquisition nor strategy execution.
