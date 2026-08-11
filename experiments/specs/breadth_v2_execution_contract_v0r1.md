# Breadth V2 execution contract V0R1

This is an append-only amendment to `BREADTH_V2_EXECUTION_CONTRACT_V0`.
It applies only the canonical correction adjudicated by
`BREADTH_V2_FUNDING_BLOCKER_ADJUDICATION_V0`.

## Amendment authority

- Superseded artifact: `BREADTH_V2_EXECUTION_CONTRACT_V0`
- Reason: `EXECUTION_CONTRACT_OVERCONSTRAINED`
- Authority: `BREADTH_V2_FUNDING_BLOCKER_ADJUDICATION_V0`
- Claim boundary: `NORMALIZED_RESEARCH_PORTFOLIO_ECONOMICS`
- Explicit disclaimer: `NOT_BINANCE_ACCOUNT_EXACT_REPLICATION`

## Normalized funding accounting

```text
FUNDING_ACCOUNTING_MODE = NORMALIZED_HELD_NOTIONAL_X_REALIZED_RATE_V1
funding_cashflow = -held_notional_at_settlement × realized_funding_rate
```

At funding boundary `t`, `held_notional_at_settlement[symbol]` is defined
deterministically by the portfolio kernel:

1. The position from the previous rebalance arrives at `t`.
2. That position is marked using QntyLab's admitted evaluation close at `t`.
3. Before any target generated at `t` is applied,
   `held_notional_at_settlement = existing_quantity × admitted_evaluation_price`.
4. Funding settles as `-held_notional_at_settlement × realized_funding_rate`.
5. Only afterward may the event/bar information influence target generation
   and rebalance.

The admitted evaluation price is QntyLab's normalized research
representation. It is not claimed to equal Binance's historical associated
settlement `markPrice`. No mark-price reconstruction, nearest mark-price
candle, 1m open/close substitution, spot-price substitution, or index-price
substitution is permitted.

## Funding event fields

Economic accounting requires `symbol`, `funding_time`, `funding_rate`,
`source`, and `coverage`. `funding_rate` must be finite; positive and negative
realized rates are valid. `mark_price` is optional diagnostic/provenance
metadata, must not enter normalized cashflow, and malformed non-finite values
are rejected. A missing mark price does not block a complete normalized event.

`rate_type` is retained when present but is not required for this frozen crypto
proposition. Historical absence is represented as absent; `Regular` is
accepted; `Special` is explicitly unsupported and fails closed. No synthetic
rate type is invented.

Coverage other than `COMPLETE` remains fail-closed. Exact settlement timestamp,
exact realized funding rate, event-time chronology, source provenance,
coverage/gap behavior, determinism, and portfolio contribution reconciliation
remain frozen. A funding event can influence only the next target, and a
position opened because of an event cannot receive or pay that same event.

## Unchanged execution contract

`TARGET_WEIGHT_BASIS = PRE_COST_EQUITY`, price PnL, turnover, entry and
rebalance costs, terminal liquidation, fee/slippage accounting, asset
contributions, and portfolio reconciliation are unchanged. The
`BREADTH_V2_INPUT_BUNDLE_V0` and `BREADTH_V2_EVALUATION_ID_V0` identities are
not redesigned. Causal funding economic content binds symbol,
funding-time, funding-rate, and admission/coverage semantics; optional
`mark_price` and `rate_type` metadata cannot silently change the formula.

The fixed panel, seven families, 28 variants, 20-asset panel, three
development windows, two cost modes, `EXECUTION_UNITS = 1992`, and
`REGISTERED_SCIENTIFIC_CELLS = 3360` remain unchanged. This amendment uses
artificial deterministic fixtures only and authorizes no materializer, data
acquisition, strategy execution, outcome access, or ledger integration.
