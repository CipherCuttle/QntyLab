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

## Phase 1A offline capture core

**Current implementation phase:** `PHASE_1A_OFFLINE_CAPTURE_CORE_UNDER_REVIEW`

The frozen protocol and hash remain unchanged. An offline fixture replay is
available; its artifacts are not observations. Live Deribit or Binance access
remains unauthorized: no scheduled Monday has been captured, outcome retrieval
and analysis do not exist, and there is no QNTY integration. Live transport
requires a new reviewed task.

```bash
python -m qntylab.prospective_deribit_dvol replay-fixture \
  --protocol experiments/prospective/dvol_v0/protocol.json \
  --sidecar experiments/prospective/dvol_v0/protocol.sha256 \
  --scheduled-monday YYYY-MM-DD \
  --deribit-events tests/fixtures/dvol_v0/valid_deribit_session.jsonl \
  --binance-btc-response /tmp/BTCUSDT.json \
  --binance-eth-response /tmp/ETHUSDT.json \
  --output-root /tmp/dvol-v0-replay \
  --repository-commit 0123456789abcdef0123456789abcdef01234567
```

The replay accepts only byte-exact fixture input. Deribit payloads are represented
as `payload_base64`, so escaped Unicode, backslashes, embedded newlines, and JSON
whitespace are not reconstructed from a host JSON string. It has no HTTP adapter,
WebSocket transport, `requests` import, live command, scheduler, outcome
retrieval, forecast-error calculation, or QNTY integration. Fixture outputs are
explicitly non-scientific and cannot be primary observations. Live-source timing,
notification cadence, clock skew, and Binance response behavior remain untested.

## Phase 1B non-primary live source smoke

**Current implementation phase:** `NON_PRIMARY_SMOKE_BLOCKED`

An isolated, one-time smoke command is implemented for independent review. Raw
smoke data stays outside Git under `/tmp`; no primary observation was created,
no week was added to the 104-week sample, no outcome was retrieved, no realized
volatility was computed, and no forecast comparison was performed. Scheduled
collection remains unauthorized and another independent review is required.

## Phase 1B evidence-retention repair

**Repair status:** `PHASE_1B_EVIDENCE_RETENTION_REPAIR_UNDER_REVIEW`

The first smoke remains `NON_PRIMARY_SMOKE_BLOCKED / DERIBIT_ACK_MISMATCH`.
Its offending acknowledgement payload was not retained, so the exact mismatch
remains unresolved and the first receipt is unchanged. Future source payloads
are retained before classification, with strict structural diagnostics; Deribit
and each Binance source are independently probed. No rerun has occurred, no new
network access is authorized, and scheduled collection remains unauthorized.

The repaired implementation uses one absolute 90-second post-subscription
monotonic deadline; retains but does not count pre-acknowledgement notifications;
stops later probes on clock regression; retains available non-200 Binance bodies;
binds artifacts directly to protocol, commit, mode, aggregate, and source
verdicts; and publishes only to a non-existing output root.
