# Deribit DVOL prospective forecast V0

**Current phase:** `PHASE_0_PROTOCOL_FROZEN_SOURCE_CONTRACT_BLOCKED`

## Purpose and non-claim boundary

This is a probationary prospective forecast horse race. It asks whether the raw
Deribit volatility-index close has lower prospective forecast error than the
trailing-30-day-realized-volatility benchmark for the next 168 complete hourly
intervals of BTC and ETH realized volatility. It does not test incremental
information conditional on trailing realized volatility.

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
millisecond start/end parameters, resolutions including one second, a row of
timestamp/open/high/low/close, and continuation. The chart method documents
`BTC-PERPETUAL` and minute resolution `60`, `result.status`, `result.ticks`,
and OHLC arrays. Public methods require no authentication; rate limiting can
return `too_many_requests`.

However, those official pages do not state whether either method's timestamp is
the opening or closing boundary of a candle, provide a candle-completeness
indicator, define the DVOL close's unit/annualization, or state its economic
horizon. These are `UNRESOLVED_OFFICIAL_SOURCE_CONTRACT_FACTS`. Therefore this
protocol is deliberately non-executable: no Phase 1 authorization, network
access, capture implementation, observation, outcome retrieval, or analysis is
permitted until a separately reviewed authoritative source contract resolves
them.

## Frozen design

- Assets: `BTC`, `ETH`.
- Proposed primary observation receipt window: Monday `00:00:00`–`00:10:00 UTC`.
- Proposed common source-data cutoff: Monday `00:00:00 UTC`, fixed before any
  of the four formation requests; actual request start/completion and receipt
  times must be retained separately. This is unusable until candle-boundary
  semantics are resolved.
- Predictor: the formation-time Deribit volatility-index close.
- Benchmark: trailing 30-day realized volatility alone.
- Outcome: annualized realized volatility from 168 strictly future hourly
  perpetual-close intervals, beginning only at the first eligible boundary
  after formation and ending 168 hours later.
- Primary comparison: equally asset-weighted pooled mean absolute forecast
  error in percent points. The frozen DVOL forecast is its source close; the
  benchmark forecast is trailing realized volatility. Neither has fitted
  hyperparameters.
- Minimum: 104 complete primary weeks for each asset (208 asset-weeks total),
  a transparent two-calendar-year descriptive target rather than a power or
  significance calculation. No primary conclusion is allowed before that.
  The 156-scheduled-week upper bound is a three-year operational stop: if the
  minimum is not reached by then, V0 is `BLOCKED`.

The exact timestamp, return, annualization, missing-bar, raw-byte,
normalization, amendment, retry, and terminal rules are in
[`protocol.json`](protocol.json). Every scheduled week, attempt, raw response,
and error must be retained. A transport or local operational failure is a
predeclared skipped week, never a silently omitted or replacement observation;
source-data, timing, integrity, or outcome invalidity blocks V0.

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

No command shape is specified because implementation is not authorized and the
official source-contract gaps remain unresolved.
