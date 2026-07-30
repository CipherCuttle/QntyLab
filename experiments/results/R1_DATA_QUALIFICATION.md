# R1 historical Bybit lifecycle-data qualification

## PLAN

Assess source structure and public samples only; do not calculate any candidate outcome. The cutoff is 2026-06-30 UTC and the four locked hypothesis identities are not read or executed.

## SCIENTIFIC DATA REQUIREMENTS

The execution contract requires a point-in-time instrument instance, causally known tradability interval, daily close and quote volume, actual funding settlement records, gap state, and verified/ambiguous terminal state. A ticker alone is not an identity.

## SURVIVORSHIP LITERATURE

Ammann, Burdorf, Liebi, and Stoeckl document material cryptocurrency survivorship/delisting distortion, especially for equal-weight portfolios. This makes dead-contract retention and terminal handling load-bearing. The frozen method therefore constructs the universe from information available at each timestamp and freezes the source choice before outcomes.

Evidence links: [Ammann et al., *Survivorship and Delisting Bias in Cryptocurrency Markets*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4287573); [Tardis Bybit derivatives coverage](https://docs.tardis.dev/historical-data-details/bybit); [Tardis instrument metadata semantics](https://docs.tardis.dev/api/instruments-metadata-api); [Tardis CSV access](https://docs.tardis.dev/downloadable-csv-files/overview); [Coin Metrics candles](https://docs.coinmetrics.io/market-data/market-data-overview/candles); [Kaiko derivative contract details](https://docs.kaiko.com/rest-api/data-feeds/reference-data/advanced-tier/derivatives-contract-details); [Bybit instrument information](https://bybit-exchange.github.io/docs/v5/market/instrument).

## TARDIS DOCUMENTATION AUDIT

DOCUMENTED: Bybit linear collection begins 2020-05-28; exchange coverage exposes historical symbols, data types, availability intervals, and incident reports; first-day-of-month CSVs are public; CSV derivative ticker has funding, mark/index/last prices; raw replay is a paid Pro/Business capability. DOCUMENTED metadata says `availableTo` is recorder-stop time and can lag delisting, and warns about symbol reuse/aliases. INFERRED: historical `instrument_info` capture can support a richer lifecycle reconstruction once raw access is procured. UNVERIFIED: that capture alone supplies a complete exchange terminal ledger for every USDT-linear contract.

## TARDIS BYBIT COVERAGE

The 2026-07-29 public coverage response is 655,826 bytes, SHA-256 `b3bd…739dc`; it lists 1,761 recorded Bybit instruments and 927 with `availableTo` before the cutoff. It reports `trades`, `derivative_ticker`, and related capture types. Only records/events at or before the cutoff may enter R1.

## TARDIS DEAD-INSTRUMENT CLAIM

PROVISIONALLY SUPPORTED: the public catalog retains 927 ended recordings, including short-lived USDT perpetuals. It proves retention of historical captures, not that every `availableTo` is a delisting timestamp; all such terminal observations begin as GRADE_C.

## TARDIS ACCESS PROBE

Unauthenticated `/v1/exchanges/bybit` succeeded. Unauthenticated `/v1/instruments/bybit` returned 401. A public first-of-month dataset was reachable; no access control was bypassed.

## FREE SAMPLE RESULTS

`bybit/derivative_ticker/2024/01/01/BTCUSDT.csv.gz` downloaded at 1,545,342 bytes, SHA-256 `80e5658ea627e87bb372ca80bd0c9f424184b9582b6a551f35b0ce59ede4fffa`. Its normalized schema has `funding_timestamp` and `funding_rate`; it is format/availability evidence only, not proof that every ticker observation is a realized settlement.

## GRAVEYARD TEST

The outcome-blind catalog sample contains 30 instances: long-lived `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`; newly observed `BREVUSDT`, `FOGOUSDT`, `AAPLUSDT`, `AAOIUSDT`; ended recordings including `10000000AIDOGEUSDT`, `1000000VINUUSDT`, `10000NFTUSDT`, `1000BEERUSDT`, `1000IQ50USDT`, `1000MUMUUSDT`, `1CATUSDT`, `AGIXUSDT`, `ANCUSDT`, `ANTUSDT`, `AUDIOUSDT`, `ALPACAUSDT`, `AKROUSDT`, `LUNAUSDT`, `MATICUSDT`, `OCEANUSDT`, `PERPUSDT`, `TOMOUSDT`, `YFIIUSDT`, and `PUMPUSDT`; plus two catalogued incident/gap cases. Every sample record has trade and derivative-ticker availability in the catalog. End dates are capture ends, not asserted delistings.

## INSTRUMENT INSTANCE MODEL

`venue|symbol|contract_type|first_observed_timestamp[|symbol-id=<id>]`. A non-overlapping lifetime or different `symbolId` is a new instance. No ambiguous symbol reuse inherits predecessor history.

## LIFECYCLE EVIDENCE GRADES

GRADE_A is timestamped official lifecycle/delisting evidence. GRADE_B is qualified contemporaneous capture establishing an observed state. GRADE_C is disappearance/last observation. GRADE_X is conflict. Every fact carries event time, capture time when available, source, grade, and raw hash/identity.

## TERMINAL FAIL-CLOSED POLICY

Verified terminal plus mechanically available settlement follows a separately frozen settlement rule. Ambiguous terminal without exposure is removed after the last verified tradable state. Ambiguous terminal while exposed is `BLOCKED_BY_DATA_INTEGRITY`. Last-price exits and interpolation are forbidden.

## TRADABILITY STATE MACHINE

`UNKNOWN -> PRELAUNCH -> OBSERVED_NOT_ELIGIBLE -> TRADABLE`; a timestamped incident/suspension moves to `TEMPORARILY_UNOBSERVABLE`; terminal evidence moves to `TERMINATED_VERIFIED` or `TERMINATED_AMBIGUOUS`. The compiler uses only events no later than the queried timestamp.

## GAP SEMANTICS

Vendor incident, exchange outage, no trades, archive/API absence, suspension, delisting, and unknown disappearance remain distinct. Tardis has incident reports (including a 2026-06-08 recorder gap); unresolved material gaps are not filled and cannot be tradable.

## PIT UNIVERSE FEASIBILITY

STRUCTURALLY FEASIBLE PENDING PURCHASE: historical catalog retention includes later-dead contracts; trades permit causal daily quote-volume aggregation; the compiler makes eligibility state-driven. The paid extract must prove 30-day observations, calculate top-20 identities mechanically, and meet breadth >=10 on >=90% of candidate dates. This report intentionally does not calculate those selected identities or any factors.

## PRICE / VOLUME FEASIBILITY

Tardis trades are the preferred authoritative input: aggregate `price * size` only after contract unit/field semantics are bound per instance. Vendor candles may be a validation aid, never assumed complete for dead symbols. Check duplicates, event ordering, timestamp basis, and gaps on the purchased extract.

## FUNDING FEASIBILITY

Tardis derivative ticker publicly demonstrates timestamp/rate fields. It is provisionally sufficient only after an extractor proves realized settlement semantics and period per instance; predicted funding must be excluded. Coin Metrics may independently corroborate funding coverage but must remain a separate source.

## COIN METRICS AUDIT

CORROBORATOR. Documentation exposes market catalogs, market candles, and funding-rate availability ranges, and records Bybit futures candle support from 2021. Catalog min/max is coverage metadata, not a listing/delisting event; authenticated access is required for historical proof.

## KAIKO AUDIT

CORROBORATOR. Documentation exposes derivative contract reference fields including listing timestamp/expiry and an exchange-provided risk endpoint with funding rate and 24h volume. It requires an API key and public docs did not prove complete historical Bybit tombstone retention, so it is not selected as primary.

## OFFICIAL BYBIT EVIDENCE

The current linear instrument probe returned 767 rows, SHA-256 `17b3…69021`, with `symbolId`, status, contract type, launch/delivery time, and funding interval. Official docs state current linear defaults to Trading results, so it is corroboration only; current metadata is never projected backward. Timestamped announcements and archived official fields can upgrade individual terminal claims.

## SOURCE PRECEDENCE

Official timestamped event/delivery evidence > independent contemporaneous capture > post-hoc vendor metadata > disappearance inference. High-grade contradiction blocks rather than being resolved by judgment. Coin Metrics/Kaiko are never silently merged with Tardis.

## SOURCE DISAGREEMENTS

`availableTo` disagreement with official evidence is not reconciled into a delisting time. Preserve both receipts; classify GRADE_X when high-grade claims conflict, and block exposure across it.

## MINIMUM R1 DATA CONTRACT

Defined in `experiments/data/r1_lifecycle_contract.json`; it contains no strategy fields.

## QUALIFICATION GATES

Dead retention, identity, PIT causality, gaps, and fail-closed terminal policy provisionally pass. Span (>=1095 days after warmup) and PIT breadth require the purchased cutoff-filtered extract; price/volume and funding require semantic validation on it.

## DATE RANGE

Earliest defensible collection boundary is 2020-05-28; usable R1 start is later, once warmup and breadth gates are mechanically met. No event after 2026-06-30 may enter the R1 dataset.

## FUTURE RESERVOIR VERIFY

No July 2026+ market sample was downloaded or analysed. The public coverage response was retrieved after the cutoff but is used only as a source capability receipt; execution extraction must filter its data at the cutoff.

## ACCESS / COST MATRIX

Tardis: documented Perpetuals/Derivatives plans cover Bybit derivatives; CSV access is sufficient for trades/tickers, while raw replay/instrument capture requires Pro or Business. Historical range depends on plan/billing and pricing was not guessed. Coin Metrics and Kaiko require authenticated commercial access for the documented historical endpoints. Free first-day samples prove format and retrieval only.

## MINIMUM PROCUREMENT REQUIREMENT

Purchase only the Tardis package that grants all historical Bybit USDT-linear trades and derivative tickers through 2026-06-30, plus raw replay if CSV lacks enough timestamped instrument status evidence. Obtain Coin Metrics or Kaiko only if the required terminal/funding corroboration gate cannot be met with official evidence.

## LIFECYCLE COMPILER

`qntylab/lifecycle.py` is an outcome-blind prototype: deterministic instance identity, causal state lookup, eligibility, terminal policy, and receipt root. It has no price/PnL/ranking/factor interface.

## RECEIPTS

Machine-readable source/sample receipts and gate statuses are in `experiments/data/r1_data_source_qualification.json`; lifecycle and precedence contracts are adjacent JSON files. Large vendor data is not committed.

## RED TEAM

Unresolved attacks remain gated: vendor backfill, historical status completeness, symbol reuse, true versus recorder terminal time, predicted versus realized funding, contract-unit/quote-volume semantics, and every exposure through an ambiguous terminal. These attacks cannot be waived by apparent coverage or outcome.

## OUTCOME EMBARGO VERIFY

No H012/H014 execution, factor, ranking, portfolio, return, PnL, IC, null, candidate classification, or Sprint-v2 outcome read was performed. The discovery lock hash remains unchanged.

## ARTIFACTS

Added lifecycle compiler/tests and three compact qualification artifacts. Formal QNTY was not modified.

## TEST COLLECTION

`python -m pytest --collect-only -q` collected 40 tests.

## TEST RESULT

`tests/test_lifecycle.py`: 3 passed in 0.01s. Two requested full-suite attempts emitted 39 progress markers but the command wrapper returned no final pytest summary or exit code; no pytest process remained afterward. The full-suite result is therefore **UNVERIFIABLE**, not a pass claim. `git diff --check` exited 0.

## GIT STATUS

Pre-existing acquisition WIP remains present under `data/manifests/`, `logs/`, and Sprint-v2 artifacts. This change adds only the lifecycle module/test and the three R1 qualification artifacts. The locked Sprint-v2 result still hashes to `01868090cb77068e8524da67976121152a62034c7fa4ea4c9993366bcce4844d`.

## VERDICT

`R1_DATA_SOURCE_QUALIFIED_PENDING_PROCUREMENT`.
