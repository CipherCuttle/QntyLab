# R1 lifecycle-data proof audit

Scope: historical Bybit USDT-linear perpetual lifecycle reconstruction, 2020-05-28 through 2026-06-30. This is exploratory, outcome-blind, and does not execute R1.

## PLAN

1. Confirm the vendor's raw-channel and coverage claims from current primary documentation and public interfaces.
2. Separate positive observed lifecycle evidence from disappearance inference.
3. Probe public catalog retention and normalized historical access for ended-recording candidates.
4. Freeze only a fail-closed lifecycle rule; escalate unknown raw-schema/terminal facts to the vendor.

## CURRENT BLOCKER

The public record proves raw-channel availability and retained historical discovery evidence, but does not prove the historical payload fields, every-symbol subscription continuity, replayability of dead symbols under paid access, or an explicit terminal transition for every candidate. The blocker is evidence semantics, not procurement price or strategy performance.

## TARDIS RAW INSTRUMENT_INFO AVAILABILITY

**CONFIRMED:** Tardis's current Bybit details page lists `instrument_info` among captured real-time channels and documents raw replay as exchange-native messages paired with a local timestamp. The public exchange-details response also currently lists `instrument_info` for `bybit`.

**PARTIALLY_CONFIRMED:** an unauthenticated one-minute data-feeds request using `channel=instrument_info` returned HTTP 200 with Tardis slice headers, but this audit did not accept that as proof of paid historical replay semantics or a sample payload for a dead symbol.

**UNCONFIRMED:** returned disconnect markers; continuous subscription for each new linear symbol; dead-symbol replay after delisting.

## TARDIS BYBIT LINEAR COVERAGE

Tardis documents linear derivative collection from 2020-05-28. The public catalog is a discovery index, not an exchange lifecycle ledger: at retrieval it contained 964 USDT perpetual records, with 290 `availableTo` values no later than the cutoff. `availableTo` is recorder availability, not a delisting time.

## HISTORICAL INSTRUMENT_INFO SCHEMA

No complete primary archived field schema for USDT-linear legacy `instrument_info` was recovered in this audit. The official legacy connector proves `instrument_info.100ms.<symbol>` subscription naming, but not an exhaustive payload field set. Therefore no status, launch, delivery, delist, or symbol-id field is assumed for 2020-2023.

| Period | Channel/topic | Relevant fields proven here | Lifecycle information available? |
| --- | --- | --- | --- |
| 2020-05-28–2022 | `instrument_info.100ms.<symbol>` | Subscription topic only | Not proven |
| 2023 to 2023-10-16 | legacy `instrument_info.100ms.<symbol>` | Topic only; ticker changes do not prove this payload's schema | Partially confirmed channel, not lifecycle fields |
| 2023-10-17 onward | V5 `tickers.<symbol>` and V5 instruments REST | REST documents `symbol`, `symbolId`, `contractType`, `status`, `launchTime`, `deliveryTime`, `fundingInterval` | Current/post-hoc metadata only; historical replay mapping not proven |

Bybit announced legacy V1/V2 public REST/WebSocket shutdown on 2023-10-16. Do not project V5 REST fields backward into legacy raw messages.

## VERSIONED BYBIT CHANNEL ANALYSIS

The old `instrument_info` topic and V5 instruments REST are distinct evidence surfaces. V5 can corroborate a current metadata schema; it cannot retrospectively establish what a 2020–2023 raw event said. A purchased sample for a known ended symbol is required before parsing rules are frozen.

## PUBLIC HISTORICAL SYMBOL CATALOG

The public endpoint structurally exposes `id`, `type`, `availableSince`, and for ended recordings `availableTo`; it also exposes channels and incidents. It is sufficient to find candidates and recording intervals. It is insufficient to assert exchange launch, suspension, delisting, terminal timestamp, or settlement.

## GRAVEYARD PROBES

Ten catalog-ended candidates were selected without any outcome information: `10000000AIDOGEUSDT`, `1000000CHEEMSUSDT`, `1000000PEIPEIUSDT`, `1000000VINUUSDT`, `10000COQUSDT`, `10000ELONUSDT`, `10000LADYSUSDT`, `10000NFTUSDT`, `10000STARLUSDT`, and `1000BEERUSDT`.

For each, the public first-of-month `trades` and `derivative_ticker` CSV URL during its recorded interval returned HTTP 200. Thus dead/ended-recording candidates retain positive historical normalized evidence. For every row, raw `instrument_info` addressability and official delisting evidence remain unproven; recorder-end and disappearance are not official termination proof.

## START-OF-LIFE EVIDENCE

Use a causal start rule: create an instance at its first qualified contemporaneous instrument observation; mark it eligible only after a valid market-data observation and the frozen warmup. This has no future-survival dependency. An official launch event or historical `launchTime` can improve provenance, but is not required to call the first *observed* lifetime.

## END-OF-LIFE EVIDENCE

Candidate A, an explicit historical status/delivery transition, is sufficient if the historical schema/sample and timestamp are preserved. Candidate B, a timestamped official Bybit delisting announcement, is sufficient for its named symbol. Candidate C, Tardis `availableTo`, is not sufficient. Candidate D, permanent post-last-observation disappearance, is not sufficient; it is only an ambiguity trigger.

## TERMINAL PRICE EVIDENCE

No terminal price is inferred from the last ticker/trade. If an instrument is unexposed, remove it after frozen causal confirmation. If an instrument is exposed and lacks an explicit, admissible termination execution/settlement fact, return `BLOCKED_BY_DATA_INTEGRITY`. Forced close and invented last-price settlement are prohibited.

## SYMBOL REUSE

Ticker text is not permanent identity. The identifier is `venue|symbol|contract_type|first_observed`, augmented by a historically observed `symbolId` and contract attributes. A discontinuity or ambiguity creates a new instance; continuity is never presumed.

## PIT CAUSALITY

All state changes use evidence timestamped no later than the evaluation time. Catalog metadata can discover a candidate but must not be projected backward. Silence is `TEMPORARILY_UNOBSERVABLE`/unknown, never tradable and never a termination fact.

## FAIL-CLOSED MODEL

An instrument is eligible only while positively observed as tradable. On disappearance with no exposure, remove only after a frozen causal confirmation rule. On disappearance while exposed, require explicit lifecycle/settlement evidence or block. This is survivorship-resistant because it does not use later survival to admit earlier observations, and it does not silently manufacture terminal PnL.

## DO WE NEED EXPLICIT DELISTING FOR EVERY SYMBOL?

No—provided the above exposure-sensitive rule is enforced mechanically. We need explicit terminal evidence for every *exposed ambiguous terminal*, not an announcement for every historical symbol. This narrows the causal requirement without weakening it: absence cannot contribute a favourable exit or an unobserved holding period.

## SOURCE PRECEDENCE

1. Timestamped official Bybit lifecycle/delivery event.
2. Qualified contemporaneous raw capture with local timestamp.
3. Independent contemporaneous historical capture.
4. Tardis post-hoc metadata.
5. Last-observation inference.

High-grade disagreement blocks. Cross-vendor data corroborates only; it is never silently merged into a lifecycle event.

## UNRESOLVED FACTS

- Exact historical legacy `instrument_info` schemas for the 2020–2023 linear periods.
- Whether paid replay includes ended symbols and all relevant subscription/gap markers.
- Whether historical raw messages contain explicit status/delivery/delist transitions.
- Stable historical identifier and reuse rules across lifecycle discontinuities.
- Tardis's precise `availableTo` semantics.

## EXACT TARDIS QUESTIONS

The machine-readable eight-question set is [r1_vendor_questions.json](../data/r1_vendor_questions.json). Each asks for a YES/NO answer, endpoint/product detail, or a minimal sample—not a general description.

## VENDOR MESSAGE

> We are conducting an academic/research backtest of Bybit USDT-linear perpetuals from 2020-05-28 through 2026-06-30. Before procurement, we need to establish a point-in-time, survivorship-resistant universe; we do not need order books. Does your paid raw replay retain historical `instrument_info` (or the version-equivalent lifecycle feed) for symbols that later delisted? Please confirm the correct product/access method and provide one minimal raw example for a known delisted USDT-linear perpetual, including local capture time and any status/delivery/delist fields. Please also confirm historical channel coverage, symbol discovery/subscription behavior, disconnect/gap markers, `availableTo` semantics, and how reused/relisted symbols should be identified. This request is for lifecycle evidence only; no purchase or bulk download is being requested.

## DECISION TREE

```text
explicit historical status/delivery or official event for every exposed terminal
  + versioned raw schema and dead-symbol replay proven
    -> LIFECYCLE_DATA_PUBLICLY_PROVEN
vendor supplies the missing replay/schema/sample facts
    -> LIFECYCLE_DATA_PENDING_VENDOR_CONFIRMATION (current)
raw channel lacks terminal facts but independent official ledger can bind each exposed terminal
    -> LIFECYCLE_REQUIRES_MULTISOURCE_RECONSTRUCTION
neither path can fail closed
    -> LIFECYCLE_PATH_REJECTED
```

## OUTCOME EMBARGO VERIFY

No H012/H014 score, rank, portfolio, return, PnL, IC, weekly/null outcome, replication run, or future-reservoir data was calculated or accessed. No Tardis purchase, subscription, or full-history download was attempted.

## ARTIFACTS

- `experiments/data/r1_lifecycle_evidence_audit.json`
- `experiments/data/r1_vendor_questions.json`
- `experiments/results/R1_LIFECYCLE_PROOF.md`

## TEST RESULT

`python -m pytest --collect-only -q`: 40 tests collected (exit 0).

`python -m pytest -q`: 40 passed in 42.58s, exit 0. The foreground-owned final log and explicit exit receipt are `/tmp/qntylab-r1-lifecycle-final-pytest.log` and `/tmp/qntylab-r1-lifecycle-final-pytest.exit`.

## GIT STATUS

Pre-existing QntyLab manifest and lifecycle WIP was preserved. This audit adds only the three artifacts above.

## VERDICT

`LIFECYCLE_DATA_PENDING_VENDOR_CONFIRMATION`
