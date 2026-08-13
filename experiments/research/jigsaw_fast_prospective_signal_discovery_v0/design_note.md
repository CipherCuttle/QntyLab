# Jigsaw Fast Prospective Signal Discovery V0

This is a bounded, outcome-blind design phase. It freezes exactly three
literature/mechanism-seeded propositions and stops before market-data
materialization, historical falsification, prospective observation, or any
capital-bearing action. The operating rule is **fast to shadow, slow to claim,
even slower to capital**. Zero survivors is a valid terminal result.

## Source forensics

- Kim and Hansen (2026), [The Quarter-Hour Effect](https://arxiv.org/abs/2607.09426), reports quarter-hour order-flow/return predictability in six Binance perpetual contracts. It is a prior for JFP01, not QntyLab evidence; the registered 8-hour BTCUSDT test is not a mechanical copy or independent replication.
- Andersen, Bollerslev, Diebold and Labys (2003), [Modeling and Forecasting Realized Volatility](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0262.00418), motivates realized-volatility measurement and forecasting context.
- Corsi (2009), [HAR-RV](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1365738), motivates the fixed persistence/HAR-style baseline for JFP03, not a claim about the flow feature.
- White (2000), [Reality Check](https://doi.org/10.1111/1468-0262.00152), Hansen (2005), [Superior Predictive Ability](https://doi.org/10.1016/j.jeconom.2004.10.001), and Harvey, Liu and Zhu (2016), [...and the Cross-Section of Expected Returns](https://doi.org/10.1093/rfs/hhv059), motivate predeclared denominators and multiplicity control. V0 uses a simple Holm family correction; it is not a strategy-selection claim.
- Ackerer, Hugonnier and Jermann (2024), [Perpetual Futures Pricing](https://www.nber.org/papers/w32936), motivates JFP02's narrow premium-to-compression mechanism proposition. It does not authorize a funding or directional trade interpretation.
- Binance's [public-data archive README](https://github.com/binance/binance-public-data/blob/master/README.md) documents USD-M futures aggTrades/klines schemas, monthly/daily archive timing, `.CHECKSUM` files, and the possibility of later archive updates. Binance's [USD-M market-data documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) exposes aggregate trades, klines, and premium-index klines as distinct endpoints. These are source semantics only; no endpoint was queried for candidate observations.

## Design decisions

The census records every externally considered horizon or feature family that
was materially discussed, while selecting one primary specification per
candidate before local outcome access. JFP01 uses first-party aggregate-trade
taker semantics (`buyer is maker` means the aggressor was the seller) and a
completed 15-minute interval. JFP02 uses premium-index history rather than
fragile historical open-interest dependencies. JFP03 uses only auditable
hourly kline quote volume and taker-buy quote volume, and tests incremental
information beyond a fixed HAR-style volatility baseline. None uses L2,
liquidations, open interest, ML, opaque toxicity, or optimization.

The three primary tests share one Holm family. HAC lags are fixed from the
registered observation cadence and outcome overlap; they are not selected from
the data. Materiality thresholds are decision hurdles, not literature-derived
constants. No secondary diagnostic can rescue a failed primary test.

## Later phase boundary

The next phase, if this preregistration is merged and separately opened, may
materialize authenticated inputs only. A later historical phase must execute
all three candidates once, in order, against frozen artifacts. Only a
deterministic admission gate may set `shadow_observation_eligible`; the gate
does not authorize deployment. A future Qnty protocol lane must independently
authorize any observer integration, and the prospective contract's authority
flags remain non-capital and discovery-only.

## Strict stop

This document and its JSON artifacts do not contain market observations,
candidate outcomes, computed features, regressions, or execution receipts.
They create no strategy, Router, State Snapshot, Qnty, trading, or capital
authority.
