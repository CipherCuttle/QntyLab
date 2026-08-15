# Qnty Edge Discovery Order-Flow V0 Preregistration

## PLAN

Freeze one outcome-blind material-gap follow-up to H010, validate only the
static contract, perform one hostile review, and stop. This artifact does not
authorize feature materialization, historical execution, a trial, or any
downstream authority.

## RECONCILIATION

H010 is canonical prior evidence, not untouched territory. Its six coordinates
(`lookback` 1/6/24 × continuation/reversal) produced 18 asset rows on
BTCUSDT, ETHUSDT, and SOLUSDT. All exact coordinates were killed; the two
positive isolated rows did not earn survivor status. The durable reconciliation
is [qnty_edge_discovery_h010_order_flow_prior_evidence_reconciliation.md](qnty_edge_discovery_h010_order_flow_prior_evidence_reconciliation.md).

JFP01 and JFP03 are related but distinct records. They are disclosed as
ancestry and are not identity links or evidence that H010 survived.

## FROZEN QUESTION AND MECHANISM

> Does strictly pre-decision signed aggressive taker quote-notional contain
> economically useful information about the immediately following 1-hour
> Binance USD-M perpetual return after explicit conservative taker friction?

The mechanism is persistent aggressive buying/selling as information or
directional pressure that is not fully incorporated immediately. The only
eligible direction is `CONTINUATION`. Reversal is not a V0 variant and cannot be
selected using H010's positive rows.

## FROZEN FEATURE

For target bar `[t, t+1h)`, use source bar `[t-2h, t-1h)`:

```text
sell_quote[t-2] = total_quote_volume[t-2] - taker_buy_quote_volume[t-2]
signed_notional[t-2] = taker_buy_quote_volume[t-2] - sell_quote[t-2]
scale[t] = median(total_quote_volume[t-26:t-2])
feature[t] = signed_notional[t-2] / scale[t]
position[t] = sign(feature[t])
```

The subtraction identity is admissible only if the execution-phase source
contract verifies that total quote volume is partitioned into taker-buy and
taker-sell quote notional. Unsupported semantics block the cell. The formula
is materially distinct from H010: it is raw signed notional, uses a lagged
source bar, and uses one fixed prior 24-bar median liquidity scale rather than
H010's same-bar normalized OFI rolling-mean/direction grid.

Binance’s kline schema documents total quote volume and taker-buy quote asset
volume; the partition check remains an explicit fail-closed admission rule.

## FROZEN TIMING AND ECONOMICS

The timing contract is:

```text
FEATURE_SOURCE_END < DECISION_TIME <= EXECUTION_ELIGIBLE_TIME < OUTCOME_END
t-1h source close < t target open <= t target-open execution < t+1h target end
```

No unfinished bar, same-period source, close-boundary decision, or source/target
overlap is allowed. The economic return is target-open to following-open. Entry
and exit are conservative taker executions with the declared friction; there is
no maker, queue, or free-close assumption. A direct long/short flip costs two
turnover units.

The two fixed cost modes reuse canonical QntyLab semantics:

- `BASELINE`: 10 bps fee and 0 bps slippage per one-way turnover, plus realized
  event-time funding.
- `STRESS`: 10 bps fee and 10 bps slippage per one-way turnover, plus the same
  realized event-time funding.

Funding gaps are blocking, never zero-filled. Existing `qntylab.bar_path` is
close-to-close, so an execution phase must prove compatibility or obtain a
separate authorized open-to-open adapter; this preregistration adds neither.

## FROZEN UNIVERSE AND SEARCH DENOMINATOR

The ordered Breadth V2 panel is:

`BCHUSDT, XRPUSDT, LTCUSDT, TRXUSDT, ETCUSDT, LINKUSDT, XLMUSDT, CHZUSDT, SANDUSDT, REEFUSDT, CHRUSDT, ALICEUSDT, ONEUSDT, API3USDT, GMTUSDT, APEUSDT, OPUSDT, INJUSDT, LDOUSDT, APTUSDT`

Its frozen digest is
`becdf4bd2157ebbad416526f414c3b9f647e8832753a61642d8a5d60b6620bcd`.
Coverage is metadata-only now. Missing cells remain in the denominator and
block; no asset is removed after outcomes.

The new V0 denominator is exactly one mechanism, one feature formula, one
normalization, one direction, one horizon, one universe, two cost modes, and
20 fixed assets: 40 asset-cost cells, with three fixed chronological blocks.
The two opponents are controls, not eligible rescue variants. H010’s prior
denominator remains six variants and 18 asset rows.

## FROZEN TEMPORAL DESIGN AND GATE

This is exploratory historical evidence. New V0 feature outcomes are unseen,
but market history is not pristine and this is not confirmatory evidence. The
fixed chronological blocks are `DEV_2022`, `DEV_2024`, and `DEV_2025`, reused
from the canonical Breadth V2 partition. There is no sealed holdout in this
phase.

The eligible primary opponent is `FLAT_CASH`. A diagnostic-only fixed
`PRIOR_1H_RETURN_CONTINUATION` control tests incremental utility; it cannot
become an eligible survivor.

V0 survives only if all required cells are valid; aggregate net return is
positive in both cost modes; stressed excess versus flat is positive; stressed
excess versus the fixed prior-return control is positive; at least 10/20 assets
and 2/3 temporal blocks are positive on both net and incremental excess; no
asset contributes over 35% or block over 65% of positive stressed incremental
excess; stressed incremental excess retains at least 50% of baseline excess;
and no integrity, timing, coverage, funding, or authority failure remains.

A failure kills this exact V0. It does not authorize another normalization,
direction, horizon, threshold, universe, execution model, or rescue search.

## LEDGER, EVALUATOR, AND AUTHORITY

The required ledger action is exactly one truthful
`CANDIDATE_PROPOSED` event for
`CANDIDATE_ORDER_FLOW_SIGNED_TAKER_NOTIONAL_V0`, referencing the H010
reconciliation. No `TRIAL_COMPLETED` event, H010 reopen, Jigsaw mutation, or
downstream artifact is allowed. No compatible existing `QntyAgentEval` contract
matches; do not build one.

This phase authorizes no new historical scientific execution, feature/outcome
calculation, PnL, prospective collection, sealed-forward outcome access, JH01
or JFPV3 mutation, State Snapshot, Reactive Jigsaw, Forecaster, Router, Qnty,
paper trading, live trading, or capital allocation.

## VERDICT

`QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_PREREGISTRATION_FROZEN_READY_FOR_EXECUTION_AUTHORIZATION`

The verdict means only that the question is frozen and ready for a separate
execution authorization. It is not evidence of an edge, scientific
validation, trading authority, or capital authority.
