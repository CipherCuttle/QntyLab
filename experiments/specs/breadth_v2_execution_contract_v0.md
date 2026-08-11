# Breadth V2 execution contract V0

This is an exploratory, synthetic-fixture-only execution contract. It does
not acquire data, calculate Breadth V2 outcomes, or confer trading authority.

All seven frozen families emit target weights into one `PortfolioKernel`.
The kernel alone owns quantities, price PnL, realized event-time funding,
turnover, fees, slippage, equity, entry, rebalances, terminal liquidation,
and additive asset contributions. Targets use `PRE_COST_EQUITY`.

At boundary `t`, the prior position is marked, funding events at `t` settle
against that prior position, the bar and events become known, the strategy
computes a target, and the kernel rebalances. An event at `t` can affect the
next target but cannot be paid by a position opened because of it. Final
marking and funding settlement precede zero-target liquidation and terminal
costs.

Funding is an explicit event (`symbol`, `funding_time`, `funding_rate`,
`mark_price`, `rate_type`, source/coverage identity). Unsupported rate types
and coverage gaps fail closed; events are never forward-filled.

The fixed 20-asset panel ranks with `FROZEN_PANEL_ORDER`; ties are stable and
diagnostic ranking is not outcome-sensitive. Missing panel members block the
whole panel. The three panel families are 72 synchronized portfolio units,
each producing 20 contribution cells. Thus execution units are
`1,920 + 72 = 1,992`, while the registered scientific denominator remains
`1,920 + (72 × 20) = 3,360`.

`BREADTH_V2_INPUT_BUNDLE_V0` and `BREADTH_V2_EVALUATION_ID_V0` are canonical
SHA-256 identities. They are defined for future prospective use and are not
wired into the research ledger in this phase. `sealed_t0` is the first
complete UTC hour strictly after the prerequisite-closing merge commit.

All verification in this phase uses artificial deterministic fixtures only.
