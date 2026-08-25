# Independent hostile scientific-design review

Review scope: the frozen QntySpot Ink shadow-performance preregistration,
its static validator, and focused contract tests.

Review count: exactly one.

Review method: treat the design as sealed before any market-data access and
actively search for parameter, timing, accounting, benchmark, execution,
authority, and interpretation loopholes. No market data, historical outcome,
receipt, chart, RPC, backtest, strategy test, or research-ledger mutation was
used by this review.

Reviewed preregistration digest:
`27ce60c68133f40d9496df1db6009de07957ed8a9bd68b0715cc6c54fe05d18a`

## Attack results

1. **Parameter fishing — PASS.** The artifact freezes exactly four spacing
   values, three profit targets, twelve ordered IDs, no indicators, no search
   outside the Cartesian family, no hidden expansion, and no post-DEV family
   alteration.
2. **Historical outcome leakage — PASS.** The artifact is
   `PREREGISTERED_NOT_EXECUTED`, contains no results or gas sample, and records
   zero market-data and historical-outcome reads.
3. **Candidate family too broad — PASS.** The family is a small, explicit
   three-entry ladder with fixed mechanics and exactly twelve candidates; the
   dumb grid is a baseline and not a candidate.
4. **OUTER leakage — PASS.** OUTER begins only after the selected candidate
   and its digest are frozen; the OUTER anchor is initialized from OUTER only,
   and no future information crosses the boundary.
5. **OUTER rerun loophole — PASS.** The state machine permits one evaluation,
   forbids reruns, and preserves `OUTER_CONSUMED_INVALID` after a material
   defect.
6. **Baseline favoritism — PASS.** HOLD_WETH, BUY_AND_HOLD_KRAKMASK,
   PERIODIC_DCA, DUMB_SYMMETRIC_GRID, and the selected ladder share identical
   initial wealth, executable market semantics, fees, impact, gas treatment,
   turnover, rearming, and terminal liquidation rules.
7. **Same-block lookahead — PASS.** A decision from block B can fill only at a
   strictly later block; completed same-block events cannot chain and a full
   exit cannot reenter on the same observation.
8. **Impossible fills — PASS.** A fill requires available balances, exact
   integer AMM arithmetic, impact-cap compliance, an eligible reserve state,
   and strict chronology. Failure is `NO_FILL`; partial fills are not invented.
9. **Multi-level impact understatement — PASS.** Crossed levels aggregate
   scheduled WETH input into one hypothetical AMM trade before pricing.
10. **Fee omission — PASS.** Both exact 997/1000 V2 fee semantics and explicit
    fee attribution are frozen for buys, sells, baselines, and liquidation.
11. **Gas hand-waving — PASS.** The DEV-derived receipt rule, maximum 30-point
    evenly indexed sample, exact gas formula, nearest-rank P50/P90, fallback
    grid, fallback selection value, and `ASSUMED_GAS_SELECTION_MODEL` label
    are all fixed before outcomes.
12. **Terminal inventory mark inflation — PASS.** Inventory is valued only by
    one exact full hypothetical liquidation against final eligible reserves,
    including fee, intended-size impact, and liquidation gas; frictionless
    spot marking is prohibited.
13. **Turnover understatement — PASS.** Every hypothetical acquisition and
    liquidation is included in turnover and transaction counts.
14. **Compounding/accounting ambiguity — PASS.** Balances are integer atomic
    units, reported wealth is exact rational WETH-equivalent, completed exits
    return cash to the next cycle budget, gas timing is explicit, terminal
    inventory is recorded before liquidation, and replay must reproduce all
    state and counters.
15. **Resetting/scaling capital using OUTER information — PASS.** The initial
    wealth is selected once from the first eligible DEV execution state and
    the same frozen amount is used in OUTER; OUTER resizing is forbidden.
16. **Qualification fixture as strategy evidence — PASS.** The Ink V0B
    qualification fixture is explicitly non-strategy and has no research,
    trading, or capital authorization.
17. **Candidate-selection ambiguity — PASS.** The DEV-only ranking and all
    tie-breaks are ordered and deterministic, including the one-atomic-WETH
    wealth tolerance and lexical final tie-break.
18. **Result-classification goalpost movement — PASS.** The three valid
    classifications and blocked prefix are frozen, promising requires beating
    both HOLD_WETH and DUMB_SYMMETRIC_GRID under primary costs, and no alpha
    claim is permitted.

## Findings and disposition

Critical findings: 0

High findings: 0

Medium findings: 0

Low findings: 0

Critical/High fixes required: none.

Targeted rereview: not required and not performed.

HOSTILE_REVIEW = PASS
