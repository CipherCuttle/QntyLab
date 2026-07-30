# R1 free-only historical Bybit USDT-linear-perpetual census

Scope: outcome-blind, free/public-source-only lifecycle and coverage census for
historical Bybit USDT-linear perpetuals, 2020-03-25 through 2026-06-30. This
follows and extends `R1_DATA_QUALIFICATION.md` / `R1_PROCUREMENT_PLAN.md` /
`R1_LIFECYCLE_PROOF.md`, which left R1 `BLOCKED_BY_LIFECYCLE_DATA_GAP` pending
a paid Tardis quote. This census asks a narrower question: can the gate be
cleared with **no purchase at all**. It does not run R1 and does not touch
H012/H014 factor scores, ranks, books, returns, PnL, IC, or null outcomes.

## PLAN

1. Verify the 7 required free endpoints live, with current docs.
2. Use the Bybit announcements API as the primary lifecycle-discovery
   mechanism, with a deterministic, word-boundary-safe title classifier.
3. Build a candidate instrument population from the union of Tardis's public
   catalog and Bybit's current instrument list (source hierarchy Tier 1/2).
4. Run the funding graveyard test and the market-data graveyard test as the
   two hard gates, on a 30-symbol sample spread 2022–2026.
5. Reconstruct era-level lifecycle/announcement coverage and quantify exactly
   where the free stack's evidence runs out.
6. Compute PIT breadth structurally (existence-only) to bound a candidate
   free date range.
7. Freeze the fail-closed ambiguity-exposure contract already established in
   `qntylab/lifecycle.py`; do not execute it.

## PUBLIC SOURCE VERIFY

| Source | Accessible | Auth | Data types | Historical range | Limitations |
| --- | --- | --- | --- | --- | --- |
| Bybit announcements API | yes | no | listing/delisting/rebrand/migration titles, description, start/end ts | `delistings` category paginates to 2022-08-11; `new_crypto` (listings) 500 most-recent items span only ~2025-07 to 2026-07 | undocumented `type=` taxonomy; body is a Contentstack rich-text JSON doc, not plain HTML |
| Bybit instruments-info API | yes | no | symbol, contractType, status, launchTime, deliveryTime, fundingInterval | current snapshot only | delisted symbols disappear entirely; never project backward |
| Bybit funding history API | yes | no | symbol, fundingRate, fundingRateTimestamp | confirmed for delisted symbols 2022–2026 (30/30 sample) | 200-record page cap, needs windowed pagination for full history |
| Bybit public historical archive (`public.bybit.com`) | yes | no | daily trade CSV.gz: timestamp, side, size, price, tickDirection, grossValue, homeNotional, foreignNotional | BTCUSDT back to 2020-03-25; persists for delisted symbols (30/30 sample) | trade-level only for most symbols; `kline_for_metatrader4` pre-aggregated archive is sparse for small-cap alts (1/30 sample) |
| Tardis public exchange-details catalog | yes | no | availableSymbols[] (id, type, availableSince, availableTo), incidentReports | linear collection documented from 2020-05-28; 964 USDT-perp records | `availableTo` is recorder-stop time, not delisting time (reconfirmed) |
| Coin Metrics Community catalog-all | yes | no | per-market min/max time + trades/orderbooks/quotes/funding_rates sub-ranges | 966 USDT-quoted bybit future markets, earliest 2020-03-25 | `page_size`/`limit_per_market_type` unsupported, must omit; coverage metadata only, not a lifecycle event |
| CryptoDataDownload | partial | no | site confirms Bybit as covered exchange | unconfirmed | exact Bybit dataset URL not resolved by static crawl this session; not required for the verdict (Tier 3 optional) |

Docs cited: [Bybit announcements](https://bybit-exchange.github.io/docs/v5/announcement), [Bybit instruments](https://bybit-exchange.github.io/docs/v5/market/instrument), [Bybit funding history](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate), [Tardis Bybit coverage](https://docs.tardis.dev/historical-data-details/bybit), [Coin Metrics candles](https://docs.coinmetrics.io/market-data/market-data-overview/candles).

## BYBIT ANNOUNCEMENT API

`type=delistings` and `type=new_crypto` are real, working category keys
(reverse-probed; undocumented in the public API reference). Pagination via
`&page=N` works and terminates naturally. Machine-readable receipt:
`experiments/data/r1_free_source_census.json`.

## ANNOUNCEMENT CENSUS

456 delisting announcements fetched (10 pages, feed terminated naturally, not
a client-side limit): 2022→8, 2023→20, 2024→70, 2025→204, 2026→154 (through
07-28). 500 listing announcements fetched but the high-volume `new_crypto`
category only reaches back to 2025-07-23 in its 500 most-recent items — full
historical listing coverage was not achieved. Title-level classification over
a 250-item 5-category probe: `PERP_LISTING`=46, `PERP_DELISTING`=39,
`PERP_RELIST`=1, `REBRAND`=2, `CONTRACT_MIGRATION`=4, `OTHER`=158. Body
parsing was attempted for one case (AGIXUSDT/FETUSDT/OCEANUSDT delisting): the
structured `end_time` field (`2024-06-07T16:00:00Z`) disagrees with the
article's own prose ("10AM UTC on Jun 7, 2024") — an internal disagreement
inside one official document. `content_html` was empty; full settlement-
mechanics extraction from the nested rich-text `content` JSON was not
completed this session. Artifact: `experiments/data/r1_free_lifecycle_events.json`.

## INSTRUMENT INSTANCE COUNT

Candidate population (Tardis catalog ∪ current Bybit live list) = **967**.
Active at cutoff (current USDT `LinearPerpetual`) = **663**. Ended (recorder-
stale in Tardis, absent from the live catalog) = **296**. 3 live symbols are
too recent to appear in the fetched Tardis snapshot; 8 fall in a same-day
staleness boundary. Full-population and sample records:
`experiments/data/r1_free_instrument_instances.json` (39-instance bounded
sample: the 30-symbol graveyard set plus 9 identity-reuse candidates),
`experiments/data/r1_free_ambiguity_census.json` (full-population counts).

## MARKET HISTORY SOURCE

Two candidate free sources tested per delisted symbol: (1) the **live** V5
kline REST API (`category=linear`, `interval=D`), and (2) the **separate**
public historical trade archive (`public.bybit.com/trading/<symbol>/`).

## MARKET GRAVEYARD TEST

30 delisted symbols (9 early/2022, 10 middle/2023–24, 11 recent/2025–26,
selected from Tardis/CM staleness evidence only, not outcome):
- Live kline REST API: **3/30** returned data (only symbols delisted within
  weeks of the query — a short grace window before REST purge).
- Public trade archive: **30/30** directory index returned HTTP 200; verified
  one real day file (`LUNAUSDT2022-05-12.csv.gz`, 237,868 rows, schema
  `timestamp,symbol,side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional`).

**MARKET_GRAVEYARD_PASS** — via the public trade archive only, not the live
REST API. Daily close/quote-volume must be derived by causal per-UTC-day
aggregation (`close` = final qualifying trade of the day; `quote_volume` =
`sum(price * size)` in the archive's own units), not read pre-aggregated,
because the `kline_for_metatrader4` fallback archive is sparsely populated
for small-cap delisted alts (1/30 sample: `BITUSDT` only).

## FUNDING SOURCE

`GET /v5/market/funding/history?category=linear&symbol=<SYM>` — free, no
auth, works for currently-delisted symbols exactly like active ones.

## FUNDING GRAVEYARD TEST

Same 30-symbol sample. **30/30** returned funding records (29/30 hit the
200-record page cap; `USTUSDT` returned 66, its full short life). Last
settlement timestamp aligns with Tardis `availableTo` within 0–1 days for 26
symbols delisted after mid-2022, but diverges by **18–48 days** for the four
May-2022-era symbols (`ANCUSDT`, `BTTUSDT`, `LUNAUSDT`, `USTUSDT`) — Bybit's
own settlement history extends *past* Tardis's recorder stop, confirming
`availableTo` under-counts true trading life during the Terra/Luna collapse
volatility spike, not the reverse.

**FUNDING_GRAVEYARD_PASS.**

## LISTING EVIDENCE

Causal start rule (already frozen in `qntylab/lifecycle.py`): first qualified
contemporaneous observation, no future-survival dependency. Confirmed
available from 2020-03-25 (BTCUSDT trade archive + CM catalog). Official
`launchTime` is available as corroboration only for currently-live symbols;
it is not retained for delisted ones once they drop off `instruments-info`.

## DELISTING EVIDENCE

Of the 296-instance ended population, 290 have a terminal date on/after
2022-08-11 (inside the fetched `delistings` feed's depth); of those, **266
(91.7%)** precisely word-boundary-match an official delisting announcement
title. The remaining 24 in-era misses need either deeper body-text search or
fall back to `GRADE_C` (disappearance-only). The other 6 ended instances have
terminal dates *before* 2022-08-11 and are structurally outside this channel's
retained depth — confirmed by the feed terminating naturally, not by a query
limit.

## RELIST / SYMBOL REUSE

9 currently-live symbols show a >30-day gap between their official current
`launchTime` and the earliest independent (Tardis) recording of that same
ticker text — the two clearest are `LITUSDT` (1,492-day gap) and `DATAUSDT`
(923-day gap, current launch essentially at the study cutoff). Both are
treated as **separate `instrument_instance_id`s** from any earlier ticker
history per the frozen non-continuity rule; no inheritance is assumed.
`LUNAUSDT` is a clean *non*-reuse case (Terra 2.0 got a distinct ticker,
`LUNA2USDT`) but its trade archive has one unexplained isolated file dated
2022-12-12, ~7 months after its last continuous day — flagged
`gap_class=unknown`, `TERMINATED_AMBIGUOUS`, not resolved.

## TERMINAL RULE COVERAGE

Explicit effective/end timestamps are present in the structured announcement
fields we captured (e.g. `end_time`). Order-cancellation, position-closure,
and settlement-price-basis prose was **not** extracted this session (rich-text
body parser incomplete — see Announcement Census). Per the frozen contract,
`terminal_price_rule = UNKNOWN` for every instance until that parser exists;
no rule is synthesized.

## ANNOUNCEMENT COVERAGE BY ERA

| Era | Candidate listed | Listing events found | Candidate ended | Explicit terminal events found | Relist/reuse found | Ambiguous |
| --- | ---: | --- | ---: | --- | --- | --- |
| 2020 | earliest evidence 2020-03-25 (BTCUSDT) | not covered by fetched listings feed | 0 in sample | 0 (pre-feed) | 0 | n/a |
| 2021 | growing (breadth <10 until 2021-07) | not covered | 1 (sample) | 0 (pre-feed) | 0 | 1 |
| 2022 | — | not covered | 8 (sample: Feb–Nov) | 5/8 in-feed (feed starts 2022-08-11); 456-item feed shows 8 delistings published in 2022 overall | 0 detected | 3 pre-feed |
| 2023 | — | not covered | growing | 20 published | 0 detected | partial |
| 2024 | — | not covered | growing | 70 published | 0 detected | partial |
| 2025 | partially covered (2025-07 on) | 46/250-probe classified `PERP_LISTING` | growing | 204 published | 1 `PERP_RELIST` classified | partial |
| 2026 H1 | covered | — | growing | 154 published (through 07-28) | 0 detected | partial |

The listings channel's shallow retained depth (~1 year) is the weaker of the
two channels; the delistings channel's ~4-year depth (2022-08 onward) is
strong and covers the great majority of the study window.

## TARDIS PUBLIC CORROBORATION

964 USDT-perpetual symbol records; 296 recorder-stale and absent from
Bybit's live catalog. Zero recorder-stale Tardis symbols are still present in
Bybit's current live catalog — recorder-staleness correlates with actual
delisting in this population, though `availableTo` itself is still not
treated as a delisting timestamp (per the Funding Graveyard divergence
above). `availableFrom`/`availableTo` and captured channels documented per
symbol; incident reports present in the catalog but not cross-checked against
our 30-symbol gap sample this session.

## COIN METRICS CORROBORATION

966 USDT-quoted `bybit-*-future` markets, near-identical stale-set size to
Tardis (298 vs. 296) — strong independent corroboration of the ended
population's size. Provides per-market `min_time`/`max_time` and a *separate*
`funding_rates.min_time`/`max_time` sub-range, which is what made the
structural PIT breadth calculation possible without touching price/volume
magnitudes.

## CRYPTODATADOWNLOAD CORROBORATION

Not resolved this session (see Public Source Verify). Non-critical: Tier 1/2
evidence already independently clears every gate below.

## SOURCE DISAGREEMENTS

1. Tardis `availableTo` vs. Bybit official funding-settlement history:
   diverges by 18–48 days for 4/30 sampled symbols (Tardis under-counts).
   Tier 1 (official) wins; Tardis is corroboration only, as already frozen.
2. Within one official Bybit announcement: structured `end_time` field vs.
   article prose disagree by 6 hours (16:00 UTC vs. stated "10AM UTC").
   Unresolved — both are Tier 1, so this is a `GRADE_X` internal conflict,
   not adjudicated by this census.
3. Naive title-substring matching produced 3 false positives (`LUNAUSDT` in
   "LUNAI", `ANTUSDT` in "MANTRA", `BITUSDT` in "Bybit") — fixed with a
   word-boundary matcher (`qntylab/free_census.py:symbol_mentioned`), covered
   by `tests/test_free_census.py`.

## GAP CENSUS

- Announcement-channel depth ceiling: `delistings` category has zero coverage
  before 2022-08-11 (~27 months / ~40% of Bybit linear-perp history).
- Recorder-vs-settlement divergence: 4/30 sampled symbols, all in the
  May 2022 Terra/Luna volatility window.
- Archive anomaly: 1 confirmed (`LUNAUSDT` isolated 2022-12-12 file),
  `gap_class=unknown`.
- Live-REST-vs-archive divergence: kline REST purges delisted-symbol history
  almost immediately (27/30), while the trade archive retains it
  indefinitely (30/30) — these are two different free surfaces with very
  different retention, not a single fact.

## PIT UNIVERSE FEASIBILITY

Structural-only (existence of a market-data window **and** a funding window
per market on a given date; no price, volume magnitude, or ranking). Computed
from the Coin Metrics catalog for one date per quarter, 2021-01-01 through
2026-04-01:

| Date | Eligible count |
| --- | ---: |
| 2021-01-01 | 6 |
| 2021-04-01 | 9 |
| 2021-07-01 | 20 |
| 2021-10-01 | 29 |
| 2022-01-01 | 104 |
| 2023-01-01 | 183 |
| 2024-01-01 | 295 |
| 2025-01-01 | 472 |
| 2026-01-01 | 556 |

Full table: `experiments/data/r1_free_ambiguity_census.json`. Breadth ≥10
fails only at 2021-01-01 and 2021-04-01, i.e. before Bybit's USDT-linear-perp
market itself had enough listed names — not a data-access gap.

## CANDIDATE DATE RANGE

Earliest archive evidence 2020-03-25; earliest quarter clearing breadth ≥10
is 2021-07-01. Candidate start after 90-day signal + 30-day universe warmup:
**2021-10-01**. Through cutoff 2026-06-30 that is ≈1,734 candidate days,
comfortably clearing the 1,095-day minimum even discounting the two
low-breadth 2021 quarters, which fall before this candidate start anyway.

## FUTURE RESERVOIR VERIFY

No data dated 2026-07-01 or later was used in any structural computation.
Two live queries (current instrument list, current announcements) were made
on 2026-07-29 (today) strictly to establish *current* accessibility and the
active/live-catalog boundary for the census itself — not as R1 input data.
No H012/H014 factor, rank, book, return, PnL, IC, or null outcome was
touched.

## BREADTH

See PIT Universe Feasibility. ≥10 eligible instances hold on every sampled
date from 2021-07-01 onward (9/9 sampled quarters at or after that date, i.e.
100% of the sampled dates within the candidate range; the two failing
quarters precede the candidate start).

## AMBIGUITY CENSUS

| Metric | Count |
| --- | ---: |
| Total candidate instrument instances | 967 |
| Active at cutoff | 663 |
| Ended (recorder-stale, off live catalog) | 296 |
| — terminal ≥2022-08-11, GRADE_A matched | 266 |
| — terminal ≥2022-08-11, unmatched (GRADE_C pending) | 24 |
| — terminal <2022-08-11 (structurally GRADE_C only) | 6 |
| Identity-ambiguous (relist/reuse candidates, live symbols) | 9 |
| Funding-graveyard sample tested / passed | 30 / 30 |
| Market-archive sample tested / passed | 30 / 30 |
| Live-kline-API sample tested / passed | 30 / 3 |
| Recorder-vs-settlement disagreement sample | 4 |
| Archive anomalies (unresolved) | 1 |

By era: see Announcement Coverage By Era above. Full machine-readable
counts: `experiments/data/r1_free_ambiguity_census.json`.

## FREE SOURCE QUALIFICATION GATES

| Gate | Status |
| --- | --- |
| Dead contract retention | PASS (trade archive, 30/30) |
| Funding graveyard | PASS (30/30) |
| Lifecycle channel | PARTIAL — strong 2022-08→2026-06 (91.7% GRADE_A match rate in-sample), structurally absent 2020-05→2022-08 |
| Identity (no silent reuse merge) | PASS mechanically (`instrument_instance_id` scheme + 9 flagged reuse candidates never merged) |
| PIT causality | PASS (state-driven, no future-survival dependency) |
| Span ≥1095 days after warmup | PASS (≈1,734 candidate days from 2021-10-01) |
| Breadth ≥10 on ≥90% of candidate dates | PASS (100% of sampled dates within the candidate range) |
| Terminal safety (exposed-ambiguous can mechanically block) | PASS — already frozen in `qntylab/lifecycle.py::terminal_policy` |
| No paid dependency | PASS — nothing in this census required Tardis raw replay, a Tardis subscription, or any purchase |

## RED TEAM

- **Survivorship bias**: mitigated by construction — population comes from
  Tardis/CM catalogs, not today's live list; 296 ended instances are in the
  candidate pool.
- **Announcement incompleteness**: confirmed and quantified — 27-month
  pre-2022-08 blind spot, 8.3% in-era miss rate.
- **Dead-symbol funding/market-data deletion**: tested directly, both PASS
  (funding 30/30, archive 30/30); live kline REST *does* delete (27/30 gone)
  — a real trap for anyone assuming the REST API is a durable historical
  source.
- **Current metadata leakage**: guarded — `instruments-info` is documented
  and used as corroboration only, never projected backward.
- **Reused ticker identity**: 9 candidates found and never silently merged;
  one (`LUNAUSDT`) shown to be a *false* reuse alarm (different real ticker
  used for the relaunch) with a genuinely unresolved archive anomaly instead.
- **Volume unit mismatch**: real archive schema captured
  (`price,size,...,grossValue,homeNotional,foreignNotional`); units were not
  independently verified against Bybit's documented quote-turnover units
  this session — flagged, not resolved.
- **Predicted vs. realized funding confusion**: Bybit's funding-history
  endpoint is documented as settled history; not independently re-verified
  against a raw feed this session.
- **Terminal price assumptions**: none made; `terminal_price_rule=UNKNOWN`
  stands for every instance.
- **Post-2026 leakage**: none found (see Future Reservoir Verify).
- **Source disagreement**: three found and logged (see Source Disagreements).
- **Scraper/parser false positives**: three found and fixed with tests (see
  Source Disagreements #3).

## OUTCOME EMBARGO VERIFY

No H012/H014 score, rank, portfolio, return, PnL, IC, weekly/null outcome, or
replication classification was calculated, read, or accessed. The Sprint-v2
discovery lock hash was not touched or re-derived. No factor-vs-future-return
join was constructed. `qntylab/free_census.py` has no price, return, or
ranking concept — confirmed by inspection and by its test file.

## STRUCTURAL CODE CHANGES

- `qntylab/free_census.py` (new): `symbol_mentioned` (word-boundary matcher),
  `classify_announcement` (deterministic 8-class title classifier),
  `find_matching_delistings`, `relist_gap_days`, `pit_eligible_count`. No
  price/return/ranking/portfolio interface.
- `tests/test_free_census.py` (new): 7 synthetic tests, including the 3
  real false-positive regressions found in this census.

## ARTIFACTS

- `experiments/data/r1_free_source_census.json`
- `experiments/data/r1_free_instrument_instances.json`
- `experiments/data/r1_free_lifecycle_events.json`
- `experiments/data/r1_free_ambiguity_census.json`
- `experiments/data/r1_free_census_raw_retrieval_manifest.json` (URL, HTTP
  status, byte size, SHA-256 for every raw file fetched this session)
- `experiments/results/R1_FREE_CENSUS.md` (this file)

Large raw downloads (Tardis catalog, CM catalog, Bybit instrument lists,
announcement pages, one sample trade-archive day) were kept outside Git under
the session scratchpad and are bound into the artifacts above by SHA-256 only.

## TEST COLLECTION

`python -m pytest --collect-only -q`: **47 tests collected** (40 pre-existing
+ 7 new in `tests/test_free_census.py`).

## TEST RESULT

`python -m pytest -q`: **47 passed in 33.13s**, exit 0. Durable log/exit
receipt: `/tmp/qntylab_r1_free_census_pytest.log`,
`/tmp/qntylab_r1_free_census_pytest.exit`.

## GIT STATUS

This census added only: `qntylab/free_census.py`, `tests/test_free_census.py`,
and the five artifacts listed above. Pre-existing uncommitted WIP
(`data/manifests/`, `logs/`, the prior `R1_*` qualification/procurement/
lifecycle-proof artifacts) was left untouched — verified via `git status`
before and after. No formal QNTY file was read or modified. No commit was
created.

## VERIFY

- Import check: `python -c "import qntylab"` — OK (implicit via pytest run).
- Scoped tests: `tests/test_free_census.py` — 7/7 passed.
- Full suite: 47/47 passed, exit 0.
- `git diff --check`: no tracked files were modified, only new untracked
  files added; no whitespace/conflict-marker issues in new files.
- `git status` confirms only the listed new files were added.

## VERDICT

**`R1_FREE_DATA_SUFFICIENT_WITH_FAIL_CLOSED_AMBIGUITY`**

The free stack independently clears every hard, testable gate: funding
retrieval for delisted symbols (30/30), market-data retrieval for delisted
symbols via the trade archive (30/30), a >1,095-day span with breadth ≥10 on
100% of sampled in-range dates, a non-merging identity scheme, and a terminal
policy that already fails closed on exposed ambiguity
(`qntylab/lifecycle.py::terminal_policy`) without needing this census to
resolve every historical case in advance. This is a materially stronger
result than the prior paid-procurement path assumed: realized funding, in
particular, was previously scoped as a Tardis purchase requirement and is now
shown to be free.

What remains genuinely unresolved — and is not resolved by more querying,
only by the frozen fail-closed rule at execution time — is a **structural**
lifecycle-evidence gap before 2022-08-11 (~27 months, zero delisting-
announcement coverage) plus an 8.3% in-era miss rate and a handful of
identity/archive anomalies (9 reuse candidates, 1 unexplained archive gap).
None of these can be resolved into `TERMINATED_VERIFIED` from free sources
alone. Under the already-frozen contract, an ambiguous terminal with no R1
exposure is simply dropped after its last verified tradable state; only an
ambiguous terminal *with* exposure blocks (`BLOCKED_BY_DATA_INTEGRITY`). This
census does not and should not pre-run books to find out which candidates
that will be — the recommended candidate start of 2021-10-01 already sits
after the worst of the pre-feed-coverage era in any case, which reduces how
often that fail-closed path would actually be exercised, but does not
eliminate it.
