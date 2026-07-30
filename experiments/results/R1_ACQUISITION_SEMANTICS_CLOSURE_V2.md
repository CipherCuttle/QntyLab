# R1 acquisition-semantics closure v2

## VERDICT

R1_ACQUISITION_SEMANTICS_FROZEN

## PROVENANCE

- Rejected v1 candidate SHA-256: c6dd923d18c0836c837f9815d373d07877fff89ceafc08d1c8ef7647585d5c2f
- v2 candidate SHA-256: dd640a6f45881b68896ef36ee44d059d46c00bc15dc0887cde0dd9bb12cb0663

## ACQUISITION VS ASSIGNMENT

Raw source acquisition is keyed by `(venue, symbol, contract_type)` and may retain evidence through the historical cutoff.
It is not instance assignment, PIT eligibility, DailyMarket/FundingSettlement materialization, or PnL.

## FAIL-CLOSED ASSIGNMENT

Only a unique, pre-frozen determinate assignment window may admit an observation to an InstrumentInstance.
Zero windows is `UNASSIGNED`; multiple windows is `UNASSIGNED_AMBIGUOUS`. Both retain raw evidence but cannot normalize.
A source envelope may be wider than an instance window and never widens that window.

## COUNTS

- Source-native streams: 894
- Historical cutoff: 2026-06-30T23:59:59Z

## OUTCOME EMBARGO

No census, raw download, R1 execution, factor calculation, rank, return, PnL, or statistical result was produced.
