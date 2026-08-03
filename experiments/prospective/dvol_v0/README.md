# Deribit DVOL prospective forecast V0

**Current phase:** `PHASE_0_PROTOCOL_FROZEN`

## Purpose and non-claim boundary

This is a probationary prospective forecasting experiment. It asks whether the
Deribit volatility-index close contains prospective information about the next
seven complete UTC days of realized BTC and ETH volatility beyond trailing
30-day realized volatility alone.

It is not a strategy, an edge or profitability claim, a candidate nomination,
QNTY validation, or paper, shadow, or live authorization.

Prospective observations are used so that the hypothesis, timing, predictors,
outcome, comparison, and stopping rules are frozen before their eligible future
outcomes accumulate.

## Source contract

The sole declared source is the Deribit public market-data API. The protocol
uses `public/get_volatility_index_data` for BTC and ETH volatility-index
candles, and the same official public API's
`public/get_tradingview_chart_data` for declared BTC-PERPETUAL and
ETH-PERPETUAL hourly closes used only to measure the frozen realized-volatility
predictor and outcome. Public methods require no authentication.

Official documentation, retrieved `2026-08-03`:

- [Volatility-index historical data](https://docs.deribit.com/api-reference/market-data/public-get_volatility_index_data)
- [TradingView chart data](https://docs.deribit.com/api-reference/market-data/public-get_tradingview_chart_data)
- [Authentication](https://docs.deribit.com/articles/authentication)
- [Rate limits](https://docs.deribit.com/articles/rate-limits)

The volatility-index method documents BTC and ETH currency identifiers,
millisecond start/end parameters, and resolutions including one second. Its
candle row is timestamp, open, high, low, close. A non-null continuation or a
rate-limit error is invalid: V0 will not paginate or retry inside its primary
window.

## Frozen design

- Assets: `BTC`, `ETH`.
- Primary observation: every Monday at `00:05 UTC`, only within
  `00:00:00`–`00:10:00 UTC` inclusive.
- Predictor: the formation-time Deribit volatility-index close.
- Benchmark: trailing 30-day realized volatility alone.
- Outcome: annualized realized volatility from hourly perpetual closes over
  the next complete seven UTC days.
- Primary comparison: equally asset-weighted pooled mean absolute forecast
  error in percent points. The frozen DVOL forecast is its source close; the
  benchmark forecast is trailing realized volatility. Neither has fitted
  hyperparameters.
- Minimum: 104 complete primary weeks for each asset (208 asset-weeks total).
  No primary conclusion is allowed before that. At 156 complete weeks per
  asset, V0 must stop and be reassessed rather than continuing indefinitely.

The exact timestamp, return, annualization, missing-bar, raw-byte,
normalization, amendment, and terminal rules are in
[`protocol.json`](protocol.json). A week with missing BTC or ETH data,
malformed/non-finite data, a protocol/hash mismatch, an outside-tolerance
capture, ambiguous source timing, raw-response loss, normalization/hash
mismatch, or an incomplete future outcome is not imputed or silently dropped:
it blocks V0.

Material amendments before the first eligible primary observation require a
new version and preservation of this protocol. After that observation, changes
to the assets, source, timing, predictors, benchmark, outcome, horizon,
primary comparison, missing-data policy, or stopping rules create a new
experiment identity; V0 is never rewritten in place.

The only terminal classifications are `KILLED`, `BLOCKED`, and
`RETAIN_FOR_SEPARATELY_REGISTERED_FOLLOWUP`. Retention is only exploratory and
does not authorize a candidate, a strategy, or QNTY work.

## Verify the frozen protocol

```bash
cd experiments/prospective/dvol_v0
sha256sum -c protocol.sha256
```

## Explicitly deferred implementation

No capture code exists. No network request was made. No observation was
recorded. No analysis was executed. No QNTY integration occurred.

The following is proposed future command shape only:

```bash
python -m qntylab.prospective_deribit_dvol capture-once \
  --protocol experiments/prospective/dvol_v0/protocol.json \
  --output-root /home/swirky/DevHub/data/QntyLab/dvol_v0
```

**NOT IMPLEMENTED OR AUTHORIZED BY THIS PR**
