# R1 acquisition-semantics closure

## VERDICT

R1_ACQUISITION_SEMANTICS_FROZEN

## FROZEN DISTINCTION

Raw source acquisition is keyed by `(venue, symbol, contract_type)` and may retain evidence through the historical cutoff.
It is not instance assignment, PIT eligibility, DailyMarket/FundingSettlement materialization, or PnL.

## FAIL-CLOSED ASSIGNMENT

Only a unique, pre-frozen determinate assignment window may admit an observation to an InstrumentInstance.
All other in-envelope evidence is retained as `UNASSIGNED_AMBIGUOUS`; it cannot affect PIT volume/rank, funding, or PnL.

## COUNTS

- Source-native streams: 894
- Historical cutoff: 2026-06-30T23:59:59Z

## OUTCOME EMBARGO

No census, raw download, R1 execution, factor calculation, rank, return, PnL, or statistical result was produced.
