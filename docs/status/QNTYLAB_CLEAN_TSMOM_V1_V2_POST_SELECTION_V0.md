# QNTYLAB_CLEAN_TSMOM_V1_V2_POST_SELECTION_EVALUATION_V0

Status: `CLEAN_TSMOM_SOURCE_PANEL_BLOCKED`

## Identity and lineage

- QntyLab base: `e7dde95c487716107857e253b63635df7ee85ce5`
- Contract commit: `175b4a621936a79ffc44c299d9f21fc53fffd053`
- Historical V1: head `128e01ab4ad97b5b92c4c6c623dff83b79aed0c2`, tree `4327db920d67ef61c3670a265ce0acfbe412fa2d`
- Historical V2: head `6c2872fa4487d5d0c063717d7482c93fd7131255`, tree `20b7bcf3bfafdf9e8631f322b4d11dbbd5f755ed`
- `HISTORICAL_PARITY_NOT_CLAIMED`; `HISTORICAL_RESULTS_NON_AUTHORITATIVE`; `CLEAN_RECONSTRUCTION_REQUIRED`

## Frozen contract

Universe order: `BTCUSDT, ETHUSDT, XRPUSDT, LINKUSDT, DOTUSDT, BNBUSDT, ADAUSDT, MATICUSDT, SOLUSDT, AVAXUSDT`.

Source: public Binance USD-M monthly 1h klines/premium-index archives and settled funding-rate archives. Bars are exact consecutive 8h UTC aggregates. Warmup is `2026-03-01T00:00:00Z`; primary evaluation is `2026-04-23T00:00:00Z` through `2026-08-01T00:00:00Z` exclusive; tail is `2026-06-19T00:00:00Z` through the same end. Signal is causal 20-bar long/flat momentum. V1 is active signal divided by 10. V2 uses 90-return trailing inverse volatility with target active-count/10 and gross cap 1.0. Base costs are 5 bps fee plus 2.5 bps slippage; stress is 10 plus 5 bps. Initial capital is USD 10,000.

## Source-panel gate

The archive fetch was bounded to the frozen symbols and dates. For BTC, ETH, XRP, LINK, DOT, BNB and ADA, the validated raw perp panel contained 3,648 1h rows and the same source gap: `2026-06-28T23:00:00Z -> 2026-06-30T00:00:00Z`. SOL's inherited archive also reports that gap. MATIC produced funding data but no valid perp/premium rows and failed closed with `zero rows`. AVAX was not fetched after the MATIC failure because the common-panel gate had already failed.

Observed completed-source hashes are retained in ignored local manifests under `data/manifests/`; raw data is not committed. Representative perp hashes: BTC `2b05c05e13dd59492cc6958875513b4a4f38d26b985dee59e4f0f141c124e451`, ETH `39185c4a52c278630823bf974cfef607e19168362c651c90beb6dbadc9fac842`, XRP `cc5b03f8332e8455274632ad252f39d1d36a91a4e1f43f46562bcfb3f29f461c`, LINK `7b8105d26985910304cde244a413545cd53be3592a45ff7a3a2912538a32a06f`, DOT `43090caa29c97157ad27c03fc961b4d2d8ae8ad7af58f99ad918864908c0d4a8`, BNB `d94635a82da3a880e352d77d9abc5245f96a58baf4b64c2f3a0c47ece286604b`, ADA `2c532be1ee366ecfba0642e6ba8204a38a7bab17245996f298899ec118ea488b`.

Result: `SOURCE_PANEL_INCOMPLETE`. No panel was built, no strategy/control run was executed, no package classification was assigned, and no performance result is reported. This is an integrity block, not a negative trading result.

## Verification and boundaries

- Pre-contract market-data network attempts: `0`.
- Offline focused tests: `5 passed`.
- Compileall and JSON syntax checks: passed.
- Ledger registration: `LEDGER_REGISTRATION_NOT_APPLICABLE`; existing per-symbol ledger schema was not altered.
- No Qnty files, QNTY runtime, DVOL files, paper/shadow/live services, credentials, or order endpoints were used.
- Raw market data remains ignored and uncommitted.

This post-selection evaluation cannot prove persistent edge even if the source gate is later repaired. It cannot authorize tuning, another evaluation window, paper/shadow/live trading, deployment, QNTY integration, or DVOL modification.
