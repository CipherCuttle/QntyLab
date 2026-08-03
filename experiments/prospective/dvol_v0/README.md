# Deribit DVOL prospective forecast V0

**Current phase:** `PHASE_0_PROTOCOL_FROZEN_SOURCE_CONTRACT_RESOLVED_NO_IMPLEMENTATION_AUTHORIZATION`

## Purpose and selected design

This is a bounded prospective forecast horse race, not a strategy or a claim of
edge, causality, tradability, profitability, QNTY validation, or paper/shadow/live
authority. It asks: “Does a timestamped Deribit DVOL observation produce lower
forecast error than trailing Binance Spot realized volatility for future Binance
Spot realized volatility?”

The selected architecture is `DERIBIT_DVOL_PLUS_BINANCE_SPOT_KLINES`:

- Deribit public WebSocket DVOL notifications:
  `deribit_volatility_index.btc_usd` and
  `deribit_volatility_index.eth_usd`.
- Binance Spot public REST closed klines: `BTCUSDT` and `ETHUSDT`, interval `1h`,
  endpoint `/api/v3/klines`.

The cross-venue measurement is intentional and must remain explicit: a Deribit
options-implied predictor is compared with realized volatility measured from
Binance Spot closes. It is not generic “BTC realized volatility.”

## Frozen timing and metric

For each scheduled Monday, the target is `00:05:00 UTC`; an accepted DVOL
notification must have both source and UTC receipt timestamps in
`[00:05:00.000, 00:10:00.000] UTC`. The formation completion is the later
accepted receipt timestamp (source timestamps remain separately retained). The earliest outcome boundary is
`01:00 UTC`; its first return is `01:00 -> 02:00 UTC`, so it begins strictly after
formation. The outcome has 169 Binance boundary closes and 168 one-hour log
returns. The trailing benchmark ends at the closed `00:00 UTC` boundary and has
721 boundary closes and 720 returns. Binance REST has no closed-candle boolean:
eligibility is instead fixed by each tuple's open/close timestamps and a
60-second post-final-close retrieval safety delay.

DVOL is a 30-day forward-looking annualized implied-volatility expectation in
percentage points. The outcome and benchmark are annualized realized volatility
over, respectively, 168 and 720 hourly returns. Numeric units are made comparable
by annualization and percentage-point conversion, but the 30-day DVOL economic
horizon and seven-day outcome measurement horizon are not identical. V0 tests
forecast error only, not unbiasedness. A complete week is paired: BTC and ETH
must both succeed for the same scheduled Monday; the primary comparison uses the
same 104 paired Mondays for both assets. Calculations are unrounded, strict, and
have no practical margin; any retained result remains exploratory.

## Source basis (retrieved 2026-08-03)

- [Deribit DVOL subscription](https://docs.deribit.com/subscriptions/market-data/deribit_volatility_indexindex_name)
- [Deribit price-index subscription](https://docs.deribit.com/subscriptions/market-data/deribit_price_indexindex_name) (audited and rejected as the realized-volatility source)
- [Deribit notifications and public subscriptions](https://docs.deribit.com/articles/notifications)
- [Deribit public time](https://docs.deribit.com/api-reference/supporting/public-get_time)
- [Deribit authentication](https://docs.deribit.com/articles/authentication)
- [Deribit DVOL explanation](https://insights.deribit.com/industry/demystifying-dvol-futures/)
- [Binance Spot klines](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market)
- [Binance Spot REST conventions](https://developers.binance.com/en/docs/products/spot/rest-api)

## Non-authority boundary

No capture code exists. No API or WebSocket request was made, no market data was
retrieved, no observation was recorded, and no analysis was run. The protocol
forbids historical primary-observation backfill: a missed Deribit formation may
not be replaced. It distinguishes allowed bounded formation-lookback and
outcome-finalization retrieval from forbidden primary-observation backfill.

All exact source, timestamp, raw-byte retention, retry, missing-data, terminal,
amendment, and authority rules are in [`protocol.json`](protocol.json). Verify it
with `sha256sum -c protocol.sha256` from this directory.
