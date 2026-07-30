# R1 procurement plan (outcome-blind)

## PLAN

Verify the frozen qualification and Sprint-v2 identity; prove the test gate; map the minimum Bybit corpus; then stop before purchase, full data download, or any R1 calculation.

## Qualification and test gate

- `R1_DATA_QUALIFICATION.md` and its three data contracts were preserved unchanged.
- Sprint-v2 SHA-256 is `01868090cb77068e8524da67976121152a62034c7fa4ea4c9993366bcce4844d`, matching the scientific lock. No result contents were inspected.
- Collection: **40 tests**.
- Owned full-suite supervisor: PID/PGID `3479139`; durable exit receipt `0`; log result: **40 passed in 36.28s**. The earlier unverified run lost its wrapper sentinel after pytest completed; there was no remaining pytest/Python child and no test or multiprocessing defect. No test fix was made.

## R1 minimum data requirements

| Data type | Classification | R1 use | Access |
| --- | --- | --- | --- |
| Trades | REQUIRED | Causal daily close; sum `price * amount` as daily quote volume; gaps | Normalized CSV |
| Derivative ticker | REQUIRED | `funding_rate`, `funding_timestamp`, funding-state corroboration | Normalized CSV |
| Instrument info/status | REQUIRED | Instrument instance, listing/status/delivery, reuse and terminal evidence | Raw replay only |
| Official Bybit instruments/funding history | USEFUL_CORROBORATOR | Field semantics and conflict checks; current inventory cannot be projected backward | Public API/docs |
| Coin Metrics / Kaiko | USEFUL_CORROBORATOR | Only Grade C/X terminal/reuse disputes | Narrow quote if needed |
| Aggregated trades, OHLCV, books, quotes, liquidations, OI, index and mark | NOT_REQUIRED | Frozen R1 semantics do not require them | Do not buy |

## Normalized CSV sufficiency and raw replay requirement

| Need | Decision | Evidence / constraint |
| --- | --- | --- |
| Price | NORMALIZED CSV SUFFICIENT | Trade `price` with timestamp |
| Quote volume | NORMALIZED CSV SUFFICIENT | Trade `price` and `amount` |
| Funding | NORMALIZED CSV SUFFICIENT, conditional settlement rule | `derivative_ticker.funding_rate` and `funding_timestamp`; use final value before timestamp, never `predicted_funding_rate` |
| Instrument identity | RAW REPLAY REQUIRED | CSV catalog omits `instrument_info` |
| Listing, delisting, status transition, symbol reuse | RAW REPLAY REQUIRED | historical `instrument_info` is the documented captured raw channel; field completeness remains a pre-purchase gate |
| Gaps | NORMALIZED CSV SUFFICIENT for data gaps; RAW REPLAY REQUIRED for disconnect attribution | disconnect events are excluded from CSV |
| Terminal exit | CORROBORATING SOURCE REQUIRED for Grade A; otherwise frozen Grade C fail-closed policy | no inferred last-price exit |

Tardis documents normalized CSV types as trades, books, quotes, derivative ticker and liquidations, and directs fields without a normalized equivalent to raw replay. Its Bybit page documents linear coverage from 2020-05-28 and captured `instrument_info`. [Tardis CSV documentation](https://docs.tardis.dev/downloadable-csv-files), [Tardis Bybit coverage](https://docs.tardis.dev/historical-data-details/bybit)

## Funding and lifecycle contracts

The funding source is `derivative_ticker`: the documented `funding_timestamp` is the next funding event and `funding_rate` is the value applied when final immediately before that timestamp; `predicted_funding_rate` is explicitly excluded. Bybit independently documents historical `fundingRate` and `fundingRateTimestamp`, and current instrument records expose `fundingInterval`. [Tardis schema](https://docs.tardis.dev/downloadable-csv-files), [Bybit funding history](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate), [Bybit instruments](https://bybit-exchange.github.io/docs/v5/market/instrument)

| Lifecycle claim | Primary source | Corroborator | Fail-closed action |
| --- | --- | --- | --- |
| First tradable / confirmed existence | Timestamped raw `instrument_info` plus observed trade | official timestamped event | not tradable before observed evidence |
| Temporary disappearance | explicit raw status/disconnect or CSV gap | vendor incident record | `TEMPORARILY_UNOBSERVABLE` |
| Confirmed termination | raw delivery/status event | official Bybit event or narrow vendor record | frozen settlement only when evidence is Grade A/B |
| Ambiguous termination | last observed raw/CSV event | none sufficient by itself | remove if unexposed; block if exposed |
| Symbol reuse | changed `symbolId`/new first observation in raw info | independent record | create a new instance unless continuity is proven |

## Product, access, cost, and date range

`MINIMUM_TARDIS_PRODUCT=Professional subscription + Perpetuals plan + yearly billing (or an equivalent one-off quote that includes CSV, raw replay, and metadata API).`

Academic and Solo permit CSV only. Professional and Business add raw replay, Tardis Machine, and the metadata API; Business adds support/key capacity but is not needed. Yearly Professional access is documented as four years, while this request must include 2020-05-28 through 2026-06-30. That requires a specifically quoted historical configuration/one-off entitlement; current public pages expose a **$300 minimum order** but no fixed price for this exact configuration. Thus exact price is `PRICE_NOT_PUBLIC`, verified 2026-07-29. [Tardis subscriptions](https://docs.tardis.dev/faq/billing-and-subscriptions), [Tardis pricing/order form](https://tardis.dev/)

- Raw acquisition: `2020-05-28T00:00:00Z` through `2026-06-30T23:59:59Z`.
- Earliest evaluable date after 90 calendar days of available warm-up: `2020-08-26T00:00:00Z`.
- The future reservoir beginning `2026-07-01T00:00:00Z` is excluded from every manifest filter.

## Free sample measurements and storage estimate

Free first-of-month files were measured only for bytes, rows, and schema, never for outcomes.

| Feed / date / BTCUSDT | Compressed | Uncompressed | Rows |
| --- | ---: | ---: | ---: |
| trades, 2020-06-01 | 0.91 MB | 2.75 MB | 27,362 |
| trades, 2021-05-01 | 2.08 MB | 6.41 MB | 62,807 |
| trades, 2023-06-01 | 22.50 MB | 77.08 MB | 749,352 |
| trades, 2026-06-01 | 63.12 MB | 237.94 MB | 2,307,089 |
| derivative ticker, 2020-06-01 | 2.76 MB | 21.49 MB | 197,947 |
| derivative ticker, 2021-05-01 | 6.09 MB | 47.35 MB | 414,072 |
| derivative ticker, 2023-06-01 | 1.44 MB | 12.72 MB | 117,751 |
| derivative ticker, 2024-01-01 | 1.55 MB | 13.10 MB | 119,591 |

These BTC-only samples demonstrate volatility, not a complete-universe forecast. Until a paid manifest returns exact symbol-day inventory, the following is a deliberately broad operational scenario for roughly 2,225 days: low (100 average active symbols / quiet samples) **0.5 TB compressed**, central (250 / median-to-active samples) **about 14 TB**, high (500 / high-activity samples) **about 77 TB**. Uncompressed working space is approximately 3–8.8× those sizes; retain derived daily products separately at roughly 1–10 GB. Pure transfer times for compressed data are respectively ~11 h / 13 d / 71 d at 100 Mbps, ~2 h / 2.6 d / 14 d at 500 Mbps, and ~1 h / 1.3 d / 7 d at 1 Gbps.

## Procurement decision

| Component | Needed? | Source | Access product | Date range | Estimated size | Cost | Why |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| Price / volume | Yes | Tardis trades | Professional Perpetuals CSV | 2020-05-28–2026-06-30 | included in 0.5–77 TB scenario | PRICE_NOT_PUBLIC | daily close and quote volume |
| Funding | Yes | Tardis derivative ticker | same CSV | same | included | PRICE_NOT_PUBLIC | realized-funding reconstruction |
| Lifecycle / status | Yes, gate-bound | Tardis raw `instrument_info` | Professional raw replay | same | materially smaller than trades; quote required | PRICE_NOT_PUBLIC | PIT identity and fail-closed terminals |
| Corroboration | Conditional | official Bybit; then narrow Coin Metrics/Kaiko only for disputes | public / narrow quote | disputed events only | negligible | no purchase initially | resolve Grade C/X only |

## Cheapest defensible procurement

```text
CHEAPEST_DEFENSIBLE_PROCUREMENT

Tardis:
  product: Professional + Perpetuals, yearly/one-off historical configuration
  billing: quote required; exact configuration must reach 2020-05-28
  verified price: PRICE_NOT_PUBLIC (public minimum order: USD 300, verified 2026-07-29)
  required feeds: trades, derivative_ticker CSV; instrument_info raw replay only
  required date range: 2020-05-28 through 2026-06-30 UTC
  estimated download: 0.5 TB low / 14 TB central / 77 TB high, pending exact manifest

Coin Metrics:
  required? no
  reason: narrow optional corroborator for terminal/reuse disputes only

Kaiko:
  required? no
  reason: narrow optional corroborator for terminal/reuse disputes only

Total known cost: USD 0 before purchase; vendor public minimum order USD 300
Unknown quoted cost: exact Professional Perpetuals historical configuration
Expected local storage: provision 2x high-side compressed estimate plus working headroom, or obtain manifest and revise before purchase
```

## Kill switches, ingest, retention, outcome embargo

Do **not** purchase if: the quote cannot reach 2020-05-28; historical raw Bybit-linear `instrument_info` cannot demonstrate timestamped lifecycle fields; funding observations cannot be bound to settlement time without predicted values; reuse cannot be separated; or the actual manifest makes storage/bandwidth disproportionate. No full paid data was downloaded.

The ingest contract is in `experiments/data/r1_ingest_contract.json`: partial `.part` objects, bounded/resumable downloads, gzip and SHA-256 validation, atomic promotion, a canonical source root, then only outcome-blind lifecycle/daily/funding/PIT structural materialization. Raw licensed data stays outside Git at `/var/lib/qntylab/licensed/tardis/bybit-r1-v1`, with two independently controlled encrypted copies subject to license terms. No R1 scores, ranks, weights, books, returns, PnL, IC, weekly/null results, or replication calculations were made or exposed.

## Artifacts, commits, and verdict

Created: `experiments/data/r1_procurement_bom.json`, `experiments/data/r1_tardis_product_mapping.json`, `experiments/data/r1_ingest_contract.json`, and this plan. No formal QNTY file was modified. No commit was created; pre-existing QntyLab WIP remains untouched.

**VERDICT: BLOCKED_BY_LIFECYCLE_DATA_GAP.** Test integrity is green and the cheapest product route is identified, but purchase is not justified until Tardis proves historical linear `instrument_info` field coverage sufficient for the frozen lifecycle/terminal/reuse contract.
