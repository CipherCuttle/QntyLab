# Breadth V2 runner/ledger integration V0

This is a synthetic-only plumbing phase. It wires the already-frozen Breadth
V2 pieces into one deterministic runner and the existing append-only research
ledger. It does not acquire data, execute a real campaign, or calculate a real
strategy outcome.

## What this phase adds

- `qntylab/breadth_v2_runner.py` -- the runner. Resolves a registered
  candidate by `variant_id`, accepts only a `READY` result of
  `build_breadth_v2_input_bundle(...)`, validates the registered period and
  cost mode, computes `BREADTH_V2_EVALUATION_ID_V0`, executes the candidate
  and its subordinate benchmark on the same `PortfolioKernel`, builds the
  Breadth V2 path, assembles a deterministic receipt, and appends exactly one
  `TRIAL_COMPLETED` event to the existing append-only ledger.
- `qntylab/breadth_v2_path.py` -- `BREADTH_V2_PATH_V0`: a purely observational
  serialization of `ExecutionResult.boundary_path`. It does not recompute
  portfolio accounting; it only serializes and reconciles what
  `PortfolioKernel.execute` already produced.
- An observational-only trace seam added to
  `qntylab/breadth_v2_execution.PortfolioKernel.execute`
  (`ExecutionResult.boundary_path`). No accounting arithmetic changed.
- Small, additive optional fields on the existing `TRIAL_COMPLETED` schema in
  `qntylab/research_ledger.py` (see "Ledger seam" below). Historical V1/V2
  trials are unaffected; the 378 historical trial identities are unchanged.

## Two distinct identities

- `trial_id` continues to use the existing `compute_trial_id_v2(...)`
  contract, unmodified. It remains the backward-compatible append-only ledger
  key.
- `breadth_v2_evaluation_id` is computed from the frozen
  `breadth_v2_evaluation_id(...)` helper in `qntylab/breadth_v2_execution.py`.
  It is the authoritative Breadth V2 scientific execution identity. Both
  appear on the receipt and on the completed trial event.

## Execution units and scientific cells

- `SINGLE_ASSET`: `TIME_SERIES_MOMENTUM`, `MOVING_AVERAGE_TREND`,
  `PRICE_BREAKOUT`, `VOLATILITY_TARGETING`. `execution_unit_id` is the exact
  asset symbol. `4 families x 4 variants x 20 assets x 3 periods x 2 costs =
  1,920` units, each producing one scientific cell (`SINGLE_ASSET_EVALUATION`).
- `SYNCHRONIZED_PANEL`: `CROSS_SECTIONAL_MOMENTUM`, `CROSS_SECTIONAL_REVERSAL`,
  `FUNDING_CARRY`. `execution_unit_id` is the frozen sentinel
  `BREADTH_V2_FIXED_PANEL_20`, never an exchange symbol. `3 families x 4
  variants x 3 periods x 2 costs = 72` units, each producing 20 contribution
  cells (`PORTFOLIO_ASSET_CONTRIBUTION`), one per frozen panel member.
- Total: `1,992` execution units, `1,920 + 72*20 = 3,360` scientific cells.
  `enumerate_registered_execution_plan()` proves this with no data access.

## Benchmark economics

The benchmark runs on the exact same frozen price/funding evidence, event
clock, fee model, slippage model and terminal liquidation as the candidate,
via the same `PortfolioKernel`. `BUY_AND_HOLD` is implemented as a genuine
single entry with zero turnover thereafter (a stateful target function that
tracks its own implied quantity from the same per-boundary price and pre-cost
equity the kernel already supplies), not as an hourly rebalance to weight 1.
`FLAT` is zero exposure throughout. `UNSCALED_MA_24_96` reuses the frozen
24/96 `MOVING_AVERAGE_TREND` target function against the candidate's own
admitted price series. The benchmark never creates a second `TRIAL_COMPLETED`
event; it is subordinate evidence on the one candidate execution unit.

## Ledger seam

`TRIAL_OPTIONAL_KEYS` in `qntylab/research_ledger.py` gains seven optional
fields: `breadth_v2_evaluation_id`, `evaluation_input_bundle_sha256`,
`execution_contract_digest`, `execution_unit_type`, `execution_unit_id`,
`scientific_cell_count`, `cell_semantics`. They are optional for every
historical and non-Breadth-V2 trial. When
`registered_screen_id == "QNTYLAB_BREADTH_V2_20260810"` they become mandatory,
and `breadth_v2_evaluation_id` is recomputed from the ledger event's own
fields and required to match exactly -- the ledger never trusts a
receipt-declared evaluation identity without recomputation.

`COMPACT_METRIC_KEYS` gains two optional keys, `benchmark_net_return` and
`excess_return_vs_benchmark`, so relative-value and volatility-targeting
benchmarks are not forced into the historical `buy_and_hold_return` field.

## Two-stage API

- `prepare_breadth_v2_evaluation(...)`: pure except for reading frozen
  repo/ledger state. Validates the candidate, the input bundle, the period
  and cost mode; computes identities; executes the candidate and benchmark;
  builds and reconciles the path; assembles the deterministic receipt and the
  proposed `TRIAL_COMPLETED` event. Writes nothing.
- `record_breadth_v2_evaluation(...)`: stores the receipt and both paths
  content-addressed under the ledger root, appends the canonical event, and
  runs the existing `doctor()` check.

A blocked input bundle (`status != READY`) short-circuits `prepare_...` before
any `PortfolioKernel` execution and returns a bounded blocked result with no
trial event.

## Synthetic-only scope

This phase never touches `experiments/research/trials/*` on canonical
`master`; integration tests copy the canonical ledger into a temporary
fixture root and append synthetic Breadth V2 trials there only. All prices
and funding events used by the tests are closed-form deterministic fixtures
(see `tests/_breadth_v2_fixtures.py`), not real market data. No real Breadth
V2 campaign is executed by this phase.
