# QntyLab Clean TSMOM EXP_V2 execution semantics R2 freeze

`experiment=EXP_V2`  
`contract_revision=EXECUTION_SEMANTICS_R2`

## Scope and provenance

R1 repaired source discovery and authentication. R2 repairs execution and evaluation semantics discovered before the first real EXP_V2 producer run.

No corrected EXP_V2 metrics existed or were inspected before the R2 freeze. R2 does not claim that its newly explicit metric, benchmark or classification rules were historically preregistered in EXP_V1. They are prospective EXP_V2 rules frozen before the corrected run.

The prior V2 and V2R1 directories, producer, verifier, binding and external source bundle are immutable inputs. R2 is additive and synthetic-only during this freeze.

## Timeline semantics

For completed 8-hour closes `T_t`, a signal using `close[T_t]` creates target `w_t` only after that close. Funding at exactly `T_t` belongs to the preceding interval and uses the previous carried weight. The transaction to `w_t` is charged at `T_t`; price PnL and funding for `T_t < event <= T_(t+1)` use `w_t`.

Symbolically, if `close[T_0]=100` and `close[T_1]=110`, a target computed at `T_0` contributes `w_0 * (110/100-1)` at `T_1`, never to the return ending at `T_0`. The first scored interval is `(2026-04-23T00:00:00Z, 2026-04-23T08:00:00Z]`; the last is `(2026-07-31T16:00:00Z, 2026-08-01T00:00:00Z]` when the completed panel contains those closes.

## Windows and evaluation

Warmup starts `2026-03-01T00:00:00Z`. Decisions satisfy `evaluation_start <= T_t < evaluation_end`, with evaluation start `2026-04-23T00:00:00Z` and exclusive decision end `2026-08-01T00:00:00Z`. No warmup return, funding, cost or equity movement is scored. Initial capital is USD 10,000, previous weight is zero, entry cost is charged at evaluation start, and final liquidation is charged once after settlement at evaluation end. The diagnostic tail is independently rebased over scored intervals with starts at or after `2026-06-19T00:00:00Z` and ends at or before `2026-08-01T00:00:00Z`.

## Metrics, benchmarks and classification

Metrics use scored normalized equity and population standard deviation. The field is explicitly `naive_annualized_sharpe`, using `sqrt(1095)` and zero when volatility is zero. Flat, static equal-notional buy-and-hold perpetual, and rebalanced equal-weight always-long are separate benchmark outputs.

Classification is a prospective EXP_V2 policy, not recovered EXP_V1 history. It uses only base/stress return, naive Sharpe and drawdown fields specified by the R2 classification contract; turnover, funding totals and benchmarks are reported but are not hidden gates.

## Freeze guard

The R2 producer and independent verifier reject non-synthetic roots. Only `--help` may be invoked against the real configuration during this freeze.

Recorded counters: `market_data_network_attempts_during_r2_freeze=0`, `real_strategy_evaluation_attempts_during_r2_freeze=0`, `corrected_metrics_observed=0`, `source_bundle_byte_changes=0`, `original_v2_file_changes=0`, `original_v2r1_file_changes=0`.
