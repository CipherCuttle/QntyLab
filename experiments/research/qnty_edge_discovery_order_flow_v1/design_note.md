# Qnty Edge Discovery — Order Flow Prospective V1

## Purpose

This phase creates a new prospective-only scientific identity for the order-flow question. It does **not** reopen or repair `CANDIDATE_ORDER_FLOW_SIGNED_TAKER_NOTIONAL_V0`.

Historical V0 was blocked by frozen source/lifecycle coverage and was correctly graveyarded. V1 avoids denominator repair entirely: observations begin only after canonical preregistration and must be collected prospectively from the frozen first-party Binance USD-M source.

## Mechanism

For the completed one-hour candle ending at logical close boundary `C`, define:

```text
signed_taker_quote_imbalance_C =
    (2 * taker_buy_quote_asset_volume_C - quote_asset_volume_C)
    / quote_asset_volume_C
```

The value is positive when aggressive buyer quote notional dominates and negative when aggressive seller quote notional dominates.

The primary question is whether this completed-hour pressure contains incremental information for the immediately following completed-hour return after controlling for current one-hour return, trailing 24-hour return, and trailing 24-hour realized volatility.

## Why this is distinct

- H003 asks about directional trend/risk state over multi-day moving-average horizons.
- JH01 asks about persistence of realized volatility.
- JFPV3 asks whether downside variance share improves future-volatility prediction.
- Order Flow V1 asks whether contemporaneous aggressive buy/sell pressure predicts the next hourly return.

The feature family, horizon, and outcome are therefore structurally different from the active trend and volatility lanes.

## Prospective firewall

The frozen panel is `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT` on Binance USD-M perpetual futures.

The evaluated collection window is exactly `2026-09-16T00:00:00Z` through `2027-01-13T23:00:00Z` (2880 hourly origins / 120 calendar days).

A source/control-only prospective warmup precedes it. The exact warmup logical-close grid is `2026-09-15T00:00:00Z` through `2026-09-15T23:00:00Z`, 24 completed bars. Warmup observations are not candidate origins, have no outcome labels, and may not be evaluated or used to alter the model. They exist only so the first frozen origin can compute `r24` and `rv24` without historical backfill.

The final origin at `2027-01-13T23:00:00Z` owns exactly one outcome candle `[2027-01-13T23:00:00Z, 2027-01-14T00:00:00Z)`. Its completed outcome is therefore collected through logical close `2027-01-14T00:00:00Z`. This one-candle terminal tail is **outcome-only**: it creates no additional origin and does not extend the 2880-origin schedule.

No historical V0 outcome may be used to alter this design. No backfill, replacement origins, source substitution, parameter change, symbol change, interim p-value, interim edge verdict, strategy translation, Router authority, Qnty authority, or trading authority is granted. If warmup history is missing, the origin schedule does not move: affected origins remain invalid until the exact prospectively collected 24-return history exists.

## Source semantics

The intended provider is Binance first-party USD-M Futures `GET /fapi/v1/klines`, interval `1h`. The contract consumes the provider's completed-candle fields for open time, open, close, provider close time, quote asset volume, and taker-buy quote asset volume.

Binance identifies a kline by **open time**. Our scientific clock is the exact hourly **logical close boundary**. Therefore:

```text
provider open_time = logical close boundary - 1 hour
provider close_time = logical close boundary - 1 millisecond
logical close boundary = provider open_time + 1 hour
```

For an inclusive logical close range `[A, B]`, the provider query must request kline open times `[A-1h, B-1h]`. The provider `close_time` field is a completion/integrity check; it is not copied as the scientific origin timestamp.

This binding is frozen specifically so a later recorder cannot repeat the close-time/open-time translation defect discovered in the unrelated JFPV3 R2 transport.

## Control timing

At origin `C`, the source/feature candle is the completed hour `[C-1h, C)`. `r24` compares the close at `C` with the close exactly 24 hourly bars earlier. `rv24` uses the 24 completed close-to-close returns ending at `C`.

Thus the first evaluated origin, `2026-09-16T00:00:00Z`, requires hourly logical-close observations from `2026-09-15T00:00:00Z` through `2026-09-16T00:00:00Z` inclusive: 24 prospectively collected warmup closes plus the first evaluated source-candle close, giving 25 closes and exactly 24 completed close-to-close returns.

For origin `C`, the outcome candle is `[C, C+1h)`: provider open time `C`, logical close boundary `C+1h`. Its outcome cannot exist until that provider candle is complete.

## Frozen panel inference

The primary coefficient comes from pooled OLS with the three frozen controls and symbol fixed effects. BTCUSDT is the reference category.

A generic row-based HAC is **not** allowed. Five symbols can share the same hourly origin and therefore share market-wide shocks. After pooled OLS, coefficient-score contributions are summed across all valid symbols at each logical origin to form exactly one score vector per clock hour. Newey-West/Bartlett long-run covariance is then computed across those hourly score vectors with lag 24 and no finite-sample correction. Thus `24` always means **24 hours**, never 24 stacked panel rows, while contemporaneous dependence among symbols is admitted within each hourly cluster.

Per-symbol slopes are diagnostics only: each symbol uses the same feature and three controls, and only the slope sign is used. No hidden per-symbol significance threshold exists.

The concentration guard uses Frisch-Waugh-Lovell residuals of both the feature and outcome after projecting each on the same nuisance matrix (controls + symbol fixed effects). Each symbol contributes the absolute residualized feature/outcome cross-product; no symbol may exceed 35% of the total. A zero total fails support rather than creating a divide-by-zero escape hatch.

## Decision rule

This phase performs no market-data access and no scientific execution. After the 120-day evaluated collection plus the single final outcome tail are complete, a separately authorized terminal evaluator may run the frozen pooled model and diagnostic per-symbol slopes.

Support requires every gate in `preregistration.json`; otherwise the candidate fails or is inconclusive for integrity reasons. A supported result establishes only incremental predictive information within the frozen prospective scope. It does not itself establish a profitable executable strategy.
