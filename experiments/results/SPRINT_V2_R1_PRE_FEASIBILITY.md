# Sprint v2-R1 PRE — venue feasibility gate

Status: `BLOCKED_BY_DATA_INTEGRITY`

This is an outcome-blind structural preflight. It does not contain, derive, or
report any real R1 factor, forward-return, portfolio, PnL, IC, or null outcome.

## Discovery lock

- Canonical discovery artifact:
  `experiments/results/sprint_v2_results.json`
- Verified SHA-256:
  `01868090cb77068e8524da67976121152a62034c7fa4ea4c9993366bcce4844d`
- Discovery analysis commit:
  `414867435f24b2fb0d878983aaf499a7a3ff6a2b`
- Discovery cutoff and proposed R1 end:
  `2026-06-30 UTC`
- Future temporal reservoir remains unconsumed and begins:
  `2026-07-01 UTC`
- Locked variants are exactly `R1-H012-30d`, `R1-H012-90d`,
  `R1-H014-24h`, and `R1-H014-7d`. The hierarchy would be primary
  `R1-H014-7d`, secondary `R1-H012-90d`, and the other two exploratory
  replications.

The machine-readable binding is
`experiments/data/sprint_v2_r1_origin_receipt.json`.

## Gate defined before venue selection

An eligible venue must provide, from official durable sources, all of the
following for the proposed sample, without inferring a contract's historical
state from present-day availability:

1. Daily historical OHLCV including quote turnover, and settled funding-event
   rates, for every historical eligible linear USDT perpetual.
2. A complete historical contract identity ledger that captures each linear
   USDT perpetual's first exchange existence, start of continuous trading,
   status transitions, and terminal delisting/expiry event. It must identify
   ticker reuse/relaunch as a distinct instrument identity.
3. A mechanically joinable terminal-event record with an authoritative
   last-tradable timestamp and forced-close price source. A missing archive row
   may not be silently classified as a listing, delisting, or temporary gap.
4. At least 1,095 consecutive eligible calendar days ending no later than
   2026-06-30, after the 90-day signal and 30-day volume warmups, with at least
   10 valid PIT-eligible contracts on at least 90 percent of decision dates.
   Three years is a pre-outcome engineering minimum: it admits seven weekday
   anchors and multiple market regimes while avoiding a one-year, single-regime
   replication. The breadth requirement is the frozen portfolio minimum;
   90 percent prevents a formally runnable but mostly invalid calendar.

All four conditions are mandatory. A venue that fails any condition is
`NOT_FEASIBLE`; it is not a basis for a permissive gap policy or a reduced
universe.

## Bybit — `BYBIT_NOT_FEASIBLE`

Official data sources investigated:

- [V5 Kline](https://bybit-exchange.github.io/docs/v5/market/kline): historical
  candles, including turnover for linear contracts, paginated per requested
  symbol.
- [V5 Funding History](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate):
  settled historical rates, paginated per requested symbol; it explicitly notes
  that intervals can differ by symbol.
- [V5 Instruments Info](https://bybit-exchange.github.io/docs/v5/market/instrument):
  current launched-instrument records, including `launchTime`, current status,
  `deliveryTime`, and funding interval.

The source set supports a known-symbol OHLCV/funding retrieval path, but it
does not provide a durable, complete historical snapshot/ledger of all former
linear USDT perpetuals, their status transitions, ticker reuse, or a
machine-readable authoritative delisting/forced-close record. Current
`instruments-info` cannot establish whether an absent historical ticker was
never listed, delisted, renamed, or omitted from an archive. Therefore gate
conditions 2 and 3 fail before data acquisition, and PIT universe membership,
gap classification, and forced-close mechanics cannot be frozen.

No Bybit strategy inputs or outcomes were acquired or calculated.

## Fallback — `OKX_NOT_FEASIBLE`

OKX was examined only because Bybit failed. Official sources show useful but
insufficient partial coverage:

- [Historical data](https://www.okx.com/historical-data) advertises OHLC data
  from July 2023 and funding data from March 2022.
- [V5 API guide](https://www.okx.com/docs-v5/en) documents current instrument
  `listTime`, `expTime`, and state, and states that an instrument will not be
  available when it is delisted.
- [Funding FAQ](https://www.okx.com/en-us/help/funding-fees-for-perpetual-contracts-faq)
  documents settlement-time exposure and variable 1/2/4/8-hour schedules.

The stated OHLC history alone cannot satisfy the 1,095-day common span ending
2026-06-30 after warmup (July 2023 through June 2026 is shorter). More
importantly, the public current-instrument interface removes delisted products
rather than supplying an immutable historical identity/delisting ledger.
Thus the same PIT and forced-close gate conditions fail. This is not venue
shopping; no candidate inputs or outcomes were compared.

## Consequence and stop line

No target venue has passed the predeclared structural gate. Consequently none
of the following exists: R1 date range, dataset manifest/root fingerprint,
universe ledger, replication executor, synthetic execution result, worker
invariance proof, benchmark, or freeze commit. Creating any of them would
replace an unresolvable historical-state ambiguity with an assumption.

The correct terminal verdict is `BYBIT_NOT_FEASIBLE_AND_OKX_NOT_FEASIBLE`.
Future work requires an official or independently archived, auditable
historical instrument-status and delisting dataset; it must pass this same gate
before any R1 implementation or outcome execution begins.
