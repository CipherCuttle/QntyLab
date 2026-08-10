# BREADTH_V2_FUNDING_BLOCKER_ADJUDICATION_V0

Status: `DECIDED`  
Verdict: `EXECUTION_CONTRACT_OVERCONSTRAINED`  
Date: 2026-08-10  
Canonical base: `de44100e59b532d8232c9146b780895641403c39`

This is one bounded adjudication phase. It does not acquire the Breadth V2
campaign dataset, run any of the 28 candidates, calculate PnL or family
metrics, or authorize a funding materializer. The prior negative forensic
result remains first-class evidence and is not reinterpreted as a successful
source recovery.

## FACTS

- The reviewed forensic commit `05b3ea1b84786a82979fa632dc2616eaa7c26af9`
  was promoted unchanged through evidence-only PR #15 and merged to remote
  `master` as `de44100e…`. The forensic conclusion remains `BLOCKED` for the
  exact historical associated mark field.
- The protected primary worktree was not changed. This artifact was created
  in a detached scratch worktree from the merged canonical master.
- The preregistration freezes realized settlement timestamps and funding rates,
  source identity/checksum/provenance, and fail-closed coverage/gap handling.
  It does not state that historical exchange-account replication, or a
  `markPrice` field, is part of the scientific proposition.
- The later execution contract and its implementation explicitly require
  `mark_price` and compute `-quantity × mark_price × funding_rate`.
- No strategy outcome, return, ranking, or candidate-selection evidence was
  accessed in this phase.

## CONTRACT LINEAGE AUDIT

| Requirement | First artifact introducing it | Role | Frozen relative to candidate registration | Adjudication |
|---|---|---|---|---|
| Settlement timestamp | `breadth_v2_preregistration.md` §6 | Scientific chronology and event-time eligibility | Before registration | `SCIENTIFICALLY_NECESSARY`; retain exact event time |
| Realized funding rate | `breadth_v2_preregistration.md` §6 | Settlement economics | Before registration | `SCIENTIFICALLY_NECESSARY`; retain exact rate |
| Source URL/archive identity and checksum | `breadth_v2_preregistration.md` §6 | Evidence identity and reproducibility | Before registration | `PROVENANCE_REQUIRED`; retain archive checksum and REST retrieval digest as distinct claims |
| Coverage/gap state | `breadth_v2_preregistration.md` §6 and §8 | Fail-closed admission | Before registration | `SCIENTIFICALLY/IMPLEMENTATION NECESSARY`; retain, never zero-fill |
| Exact associated `markPrice` | `breadth_v2_execution_contract_v0.md`; implementation commit `16d9507` | Exchange-account valuation choice | After candidate registration | Not required by the original normalized proposition; overconstraint for this phase |
| `rateType` | `breadth_v2_execution_contract_v0.md`; implementation commit `16d9507` | Event validation/classification | After candidate registration | `PROVENANCE/DIAGNOSTIC`; not required for the frozen crypto accounting when the realized stream is otherwise complete |
| Funding interval metadata | The forensic source contract and archive schema; not a preregistration input | Coverage/provenance diagnostic | After registration | Not needed for realized accounting or an N-settlement lookback; useful only for diagnostics/gap interpretation |

The preregistration's “realized settlement economics” means that a position
open at an observed settlement receives the observed realized rate. It freezes
the event stream and missingness rules, but does not freeze an exchange-ledger
quantity/mark reconstruction. The execution contract added that stronger
ledger representation after candidate registration.

## QUESTION A — FUNDING CASHFLOW

**SOURCE-SUPPORTED FACT.** Binance's official funding-rate documentation
defines `fundingRate`, `fundingTime`, and `markPrice`, calling the latter the
“mark price associated with a particular funding fee charge.” It does not
define the `markPrice` field as a mark-price-kline open or close, nor does the
funding-history page specify a historical account-replication formula beyond
the rate being associated with the funding charge.

Binance's official Academy explanation states that the final funding rate is
applied to each trader's **position value** to determine the funding payment.
That establishes rate × position-value accounting, but does not authoritatively
identify position value with `quantity × fundingRate.markPrice` for all
historical rows. Therefore the identity cannot be silently assumed.

Sources:

- [Binance USDⓈ-M funding-rate history](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)
- [Binance mark-price kline API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data)
- [Binance Academy funding-rate explanation](https://academy.binance.com/ky-KG/articles/what-are-funding-rates-in-crypto-markets)

This leaves two distinct contracts:

1. `EXCHANGE_ACCOUNT_REPLICATION`: exact historical position quantity times
   the exchange's associated settlement mark. This requires the missing mark
   for R1.
2. `NORMALIZED_RESEARCH_PORTFOLIO_ECONOMICS`: the deterministic signed
   held/target notional in QntyLab's portfolio state times the realized rate.
   This is the registered research representation and does not claim to
   reproduce an historical Binance account ledger.

## QUESTION B — MEANING OF `fundingRate.markPrice`

Classification: `ASSOCIATED_OBSERVATION`, not proven to be an independently
recoverable historical accounting input from mark-price klines.

The official wording supports that the field is associated with the charge.
It does not establish that a 1-minute open, close, high, low, or any other
kline observation is the same state used for the charge. The prior forensic
result therefore correctly remains blocked for exact exchange-account
replication.

## QUESTION C — OFFICIAL MARK-KLINE COMPARISON

This was a bounded semantic probe only. Events were selected before inspecting
the corresponding kline values: the first three REST events with populated
`markPrice` for each of BTCUSDT, BCHUSDT, ALICEUSDT, OPUSDT, and APTUSDT in
January 2024 and January 2025. The event's minute bucket was compared with the
official `/fapi/v1/markPriceKlines` 1-minute row; no unverified finer interval
was assumed.

| Candidate reconstruction | Result |
|---|---|
| 1m open | 25/30 exact decimal numeric matches; 5 mismatches; maximum absolute difference `0.00053932` |
| 1m close | 0/30 exact matches; maximum absolute difference `45.03824823` |
| Finer official granularity | Not used; no required authenticated finer object and semantics were established |
| 2022 ground truth | Not available: the sampled official REST events for the frozen panel had empty `markPrice`, so no marked event could be compared |

Classification: `NUMERICALLY_EQUAL_IN_SAMPLE_BUT_NOT_CONTRACTUALLY_GUARANTEED`
for the 1m-open matches, and `MISMATCH` for 1m close. Sample equality is not
source equivalence. Binance's kline documentation identifies these as bars
uniquely identified by open time; it does not identify the open as the
funding-charge mark.

The result cannot change the verdict to `SOURCE_RESOLVED_EXACTLY`.

## QUESTION D — REPRESENTATION AUDIT

Let `N_t` be QntyLab's deterministic signed held notional at a settlement
event, and let `r_t` be the realized funding rate in the admitted event
stream. The normalized research cashflow is:

```text
F_t = -N_t × r_t
```

This is exact for the frozen normalized representation because the state
variable being carried is notional exposure. No separate historical base
quantity or exchange settlement mark is needed to multiply that state by the
realized rate. If instead `N_t` is defined as `quantity × Binance settlement
mark`, the calculation becomes R1 and the missing mark returns; that is
exchange-account replication, not the registered normalized proposition.

Synthetic arithmetic confirms the distinction without strategy data. For an
artificial held notional of `10,000 USDT` and realized rate `0.0008`, R2 gives
`-8.00 USDT`. R1 gives the same result only when its quantity is defined as
`10,000 / settlement_mark`; it does not require materializing that quantity
when the research state already stores `10,000 USDT` as held notional. Using a
different reconstructed mark changes R1, but does not change R2.

R1: highest exchange-account fidelity, unavailable for the historical gap.  
R2: `SCIENTIFICALLY FAITHFUL BUT NOT BINANCE-ACCOUNT EXACT` for the frozen
QntyLab normalized portfolio state.  
R3: `APPROXIMATION`, not an exact substitute; 1m-open sample equality does not
authorize it.

This is a representation correction, not a change to family definition,
signal, parameters, benchmarks, panel, windows, costs, denominator, or family
advancement rules. It changes the execution/accounting representation and the
strength of the provenance claim only.

## QUESTION E — RATE TYPE

Binance documents `Regular` as normal funding and `Special` as additional
funding generated by stock dividends. A bounded REST census over all 20 frozen
crypto panel symbols found:

- 2022: 18,498 rows, 0 `Special`, all 18,498 with empty `markPrice`.
- 2024: 23,288 rows, 0 `Special`, 0 empty `markPrice`.
- 2025-01 through 2025-09: 16,742 rows, 0 `Special`.

This does not prove that no future or unobserved historical row can be
`Special`; it establishes no observed `Special` event in the relevant bounded
crypto periods. The realized funding stream and its fail-closed event
validation remain required. Missing type metadata would prevent richer
classification, but for this frozen crypto proposition it does not prevent
accounting of a complete realized transfer stream.

Classification: `NOT_REQUIRED_FOR_FROZEN_CRYPTO_PROPOSITION`, while retaining
the field when available as `PROVENANCE_DESIRABLE` and failing closed on a
conflicting or unsupported event type.

## QUESTION F — FUNDING INTERVAL METADATA

Actual returned settlement timestamps are sufficient for realized accounting
and for a lookback defined as the last N settlement events. The bounded REST
data showed approximately eight-hour spacing in 2022, and both eight-hour and
four-hour spacing in 2024; this is evidence against a historical fixed
eight-hour assumption. `funding_interval_hours` is therefore:

- not required for realized accounting;
- not required for an N-settlement-event carry lookback;
- useful for coverage/gap diagnostics and provenance;
- not a license to infer missing events from a nominal schedule.

## PROPOSED FOLLOW-UP (NOT APPLIED HERE)

Because the later execution contract is the overconstrained artifact, the
next phase should review an append-only:

```text
BREADTH_V2_EXECUTION_CONTRACT_V0R1
```

It should supersede the exact `mark_price` requirement for normalized research
accounting, freeze `F_t = -N_t × r_t`, retain exact event chronology, realized
rates, source identity/checksum/provenance, fail-closed coverage, deterministic
accounting, and explicitly disclaim Binance-account-exact replication. That
amendment and any materializer implementation are outside this bounded phase.

## ONE HOSTILE CHECK

| Check | Result |
|---|---|
| Sample equality mistaken for source equivalence | No; sample is labelled empirical only |
| Scientific proposition changed merely to unblock | No; normalized notional accounting is separated from exchange-ledger replication |
| Normalized accounting confused with Binance account replication | No; R1 and R2 are explicitly separated |
| Kline open/close assumed to equal funding mark | No; open mismatches exist and no source identity was found |
| `rateType` retroactively invented | No; field retained when available; no historical absence is filled |
| 8-hour interval silently assumed | No; actual timestamps govern and 4h observations were found |
| Fail-closed gaps weakened | No; gaps remain blocking and are never zero-filled |
| Strategy outcomes accessed | No |
| Panel/windows/costs/denominator altered | No; 20 assets, registered windows, costs, and 3,360 denominator remain frozen |
| Convenience determined source contract | No; official REST/archive evidence and provenance classes determine it |

No Critical or High correction was required. The single hostile review is
complete.

## VERDICT

`EXECUTION_CONTRACT_OVERCONSTRAINED`

The original scientific proposition requires exact settlement chronology,
realized rates, provenance, and fail-closed coverage. The later requirement
for an exact historical associated `markPrice` is necessary for exchange-ledger
replication but is not necessary for the registered normalized notional
representation. Official mark-price history cannot be promoted to exact
settlement-mark identity from the bounded evidence. No funding materializer is
authorized until the proposed V0r1 amendment is separately reviewed and
promoted.
