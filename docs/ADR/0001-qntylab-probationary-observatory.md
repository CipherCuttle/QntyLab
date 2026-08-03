# ADR 0001: QntyLab Probationary Prospective Observatory

**Status:** `FROZEN_DESIGN_ONLY_SOURCE_CONTRACT_RESOLVED_NO_IMPLEMENTATION_AUTHORIZATION`

## Context

QntyLab must not become a second QNTY, a historical strategy-tournament engine,
an autonomous research platform, a formal validator, or a trading system. This
ADR freezes a single exploratory, prospective, public-market observation design.
It authorizes neither implementation nor network access.

| Repository | Frozen role |
| --- | --- |
| QntyLab | prospective public-market observation, point-in-time provenance, hypothesis preregistration, and bounded exploratory closure |
| QNTY | independent confirmation, protected evidence, canonical accounting, formal classification, and paper/shadow/live authority |

## Decision

Select `DERIBIT_DVOL_PLUS_BINANCE_SPOT_KLINES` for DVOL V0.

The registered question is: “Does a timestamped Deribit DVOL observation produce
lower forecast error than trailing Binance Spot realized volatility for future
Binance Spot realized volatility?” It is a forecast horse race, not a claim of
causality, unbiasedness, edge, tradability, profitability, or QNTY validation.

Deribit public WebSocket notifications provide a timestamped `volatility` value
for `deribit_volatility_index.btc_usd` and `.eth_usd`. Official Deribit
publications define DVOL as 30-day forward-looking annualized implied volatility;
the documented example where DVOL 57 implies about a 3% daily move fixes the
numeric source value as annualized percentage points. Binance Spot `/api/v3/klines`
provides UTC one-hour bars with explicit open and close timestamps and a 1,000-row
limit. Therefore the 721 trailing and 169 outcome close requirements each fit one
bounded response per asset, with no pagination.

Formation requires both an in-window source timestamp and an in-window UTC
receipt timestamp; completion is the later accepted receipt, not merely the
later source time. Binance REST does not supply a closed-candle boolean, so the
protocol mechanically validates each kline's open/close timestamps and waits a
frozen 60-second safety delay after the final eligible close. Exact received
application payload/response bytes, receipt sequencing, sessions, timestamps,
and request/response metadata are the retained raw evidence boundary; this does
not overclaim WebSocket-frame or network-packet preservation.

The cross-venue choice is material: Deribit options-implied volatility forecasts
realized volatility measured from Binance Spot BTCUSDT/ETHUSDT closes. The result
must never be called generic BTC or ETH realized volatility.

`DERIBIT_ONLY_PROSPECTIVE_STREAMS` was rejected. Although its price-index and
DVOL notifications have source timestamps, it would require retaining a
continuous prospective price stream through a 30-day warm-up and every future
outcome window, deterministic boundary selection, and loss handling. That is a
larger, less bounded collector with more undocumented operational assumptions than
the closed-kline contract. It is not selected or authorized.

## Consequences and limits

The exact source identities, timing, retention, retry, terminal, unit, and
amendment rules are frozen in `experiments/prospective/dvol_v0/protocol.json`.
All authority booleans remain false. A later task would need separate authority
before any implementation, API/WebSocket request, observation, retrieval,
analysis, QNTY work, paper/shadow/live activity, or trading activity.

V0 forbids historical primary-observation backfill, source substitution,
interpolation, generic registries or platforms, candidate handoffs, QNTY control
state mutation, and copying QNTY governance machinery. A missed Deribit formation
observation cannot be recreated from any later DVOL value.

The only terminal classifications are `KILLED`, `BLOCKED`, and
`RETAIN_FOR_SEPARATELY_REGISTERED_FOLLOWUP`. This resolution permits independent
review of the docs-only design only.
