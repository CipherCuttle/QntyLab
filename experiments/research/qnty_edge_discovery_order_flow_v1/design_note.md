# Qnty Edge Discovery — Order Flow Prospective V1

## Purpose

This phase creates a new prospective-only scientific identity for the order-flow question. It does **not** reopen or repair `CANDIDATE_ORDER_FLOW_SIGNED_TAKER_NOTIONAL_V0`.

Historical V0 was blocked by frozen source/lifecycle coverage and was correctly graveyarded. V1 avoids denominator repair entirely: observations begin only after canonical preregistration and must be collected prospectively from the frozen first-party Binance USD-M source.

## Mechanism

For completed one-hour candle `t`, define:

```text
signed_taker_quote_imbalance_t =
    (2 * taker_buy_quote_asset_volume_t - quote_asset_volume_t)
    / quote_asset_volume_t
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

The collection window is exactly `2026-09-16T00:00:00Z` through `2027-01-13T23:00:00Z` (2880 hourly origins / 120 calendar days).

No historical V0 outcome may be used to alter this design. No backfill, replacement origins, source substitution, parameter change, symbol change, interim p-value, interim edge verdict, strategy translation, Router authority, Qnty authority, or trading authority is granted.

## Source semantics

The intended provider is Binance first-party USD-M Futures `GET /fapi/v1/klines`, interval `1h`. The contract consumes the provider's completed-candle fields for open time, open, close, close time, quote asset volume, and taker-buy quote asset volume.

The provider identifies klines by candle open time. Any later recorder must therefore bind logical origin/close semantics explicitly and must not repeat the close-time/open-time translation defect discovered in the unrelated JFPV3 R2 transport.

## Decision rule

This phase performs no scientific execution. After the 120-day collection is complete, a separately authorized terminal evaluator may run the frozen pooled model and diagnostic per-symbol slopes.

Support requires every gate in `preregistration.json`; otherwise the candidate fails or is inconclusive for integrity reasons. A supported result establishes only incremental predictive information within the frozen prospective scope. It does not itself establish a profitable executable strategy.
