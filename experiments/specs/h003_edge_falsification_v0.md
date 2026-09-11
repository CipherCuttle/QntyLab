# H003 EDGE FALSIFICATION V0

Status: `REGISTERED_NOT_EXECUTED`

This phase asks a deliberately narrower question than the historical H003 promotion work:

> Does the exact frozen `H003_moving_average` 48/192 long-flat rule contain a **defensive / risk-timing edge** after realistic costs, or is its apparent benefit explained by simply spending less time exposed to SOL?

It does **not** reopen the historical claim that H003 should beat buy-and-hold on total return.

## Prior evidence stays negative

The exact variant is:

- candidate: `CANDIDATE_H003_MA_48_192_LONG_FLAT`
- variant: `variant_00eb140f03a5f6ab40600160`
- strategy: `H003_moving_average`
- parameters: `fast=48`, `slow=192`, `mode=long_flat`

It was previously retained after breadth screening, then failed the preregistered 2023 untouched-holdout continuation gate and was graveyarded by decision event:

`event_3206c7b09c089b274ca027a5`

That result is immutable evidence. In the SOL 2023 baseline cell, buy-and-hold returned about `9.1822` while H003 returned about `4.2507` net, for approximately `-4.9315` excess return versus buy-and-hold. H003 maximum drawdown was approximately `-0.3511`.

V0 may therefore test a different proposition — whether H003 improves risk-adjusted or drawdown-adjusted utility — but it may not relabel the old excess-return failure as success.

## Why this is a legitimate reopen question

The material change is the **objective**, not the parameters.

The previous gate tested continuation / excess-return performance versus buy-and-hold. V0 tests whether timing information exists after controlling for the most obvious alternative explanation: reduced SOL exposure.

A positive result requires more than a smaller drawdown. H003 must beat exposure-matched timing controls on preregistered risk metrics. Otherwise the result is merely "hold SOL less often," not evidence that the moving-average timing rule adds information.

## Frozen V0 scope

V0 tests **one strategy variant only**. There is no MA parameter grid and no replacement-winner selection.

Primary market:

- `SOLUSDT`
- Binance Spot
- `1h`

Canonical frozen input identity:

- path: `data/raw/SOLUSDT-1h.csv`
- manifest: `data/manifests/SOLUSDT-1h.json`
- SHA-256: `64bdb27a31003b0de25f3802affa8b412143a50bc8a5b76a399924626b01174a`
- rows: `49,831`
- interval: `2021-01-01T00:00:00Z` through `2026-09-08T20:00:00Z`

If those exact CSV bytes cannot be established, the run is `EXTERNAL_RECONSTRUCTION`; it cannot be silently promoted to canonical evidence.

## Historical blocks

Results are reported separately for:

1. 2021
2. 2022
3. 2023 — explicitly marked **known prior holdout**, not new OOS evidence
4. 2024
5. 2025
6. 2026 through the frozen endpoint

The roughly two days after the September 8 data freeze are insufficient for a new forward claim. Fresh forward evidence requires at least `2160` completed hourly observations (90 days) under unchanged parameters and gates.

## Costs

Four preregistered accounting views are permitted:

- zero-cost — diagnostic only
- baseline — 10 bps fee, 0 bps slippage
- stress — 10 bps fee, 10 bps slippage
- severe stress — 10 bps fee, 20 bps slippage

No cost mode may be added after result inspection.

## Primary metrics

- annualized Sharpe
- maximum drawdown
- Calmar ratio
- net return
- exposure fraction
- turnover
- trade count

A positive absolute return is insufficient.

## Benchmarks and falsification controls

The exact H003 result is compared against:

- SOL buy-and-hold
- cash
- exposure-matched random timing
- block-shuffled H003 timing
- the exact H003 signal delayed by 24 hours

The exposure-matched control is essential. Random controls must approximately match H003's long exposure fraction and sample contiguous holding-run lengths from H003's empirical holding-run distribution in the evaluated block.

The ten fixed seeds are frozen in the machine-readable preregistration before any V0 result is produced.

## Verdict gates

`DEFENSIVE_EDGE_CANDIDATE` requires **all** preregistered gates, including:

- complete-sample baseline Sharpe > buy-and-hold Sharpe
- complete-sample baseline Calmar > buy-and-hold Calmar
- less severe maximum drawdown than buy-and-hold
- positive Sharpe and Calmar under stress costs
- H003 beats the median exposure-matched random-timing control on both Sharpe and Calmar in at least 4 of 6 historical blocks
- the prior 2023 excess-return failure remains reported as a failure

`FALSIFIED` is mandatory if an integrity gate fails, if complete-sample baseline Sharpe or Calmar fails to beat buy-and-hold, if stress Sharpe/Calmar is non-positive, or if H003 fails to beat exposure-matched controls broadly enough under the frozen rule.

Anything between those states is `FRAGILE_OR_UNPROVEN`.

## Statistical boundary

This is intentionally a **single-strategy V0**. We do not add a 25-cell MA neighborhood now because doing so would immediately enlarge the multiple-testing surface and require 24 additional canonical candidate proposals.

If and only if V0 survives, a new V1 may preregister a bounded local MA surface and use White Reality Check / Hansen SPA / Deflated Sharpe / PBO diagnostics as appropriate. V0 itself cannot select another MA pair.

## Governance / execution preconditions

Before any result-producing run:

1. Run `python -m qntylab.project_context brief` and obey the canonical authority map.
2. Run `python -m qntylab.research_ledger context` and `doctor`.
3. Append a canonical `CANDIDATE_REOPENED` event for `variant_00eb140f03a5f6ab40600160` referencing `event_3206c7b09c089b274ca027a5`.
4. The reopen reason must say the old excess-return failure remains intact and the material change is limited to this preregistered defensive-risk objective.
5. Execute official strategy evidence only through `qntylab.strategy_test`.
6. Freeze any additional analysis implementation and tests before reading V0 result outputs.
7. Run one independent hostile review before interpreting the verdict.

The current PR is registration-only. It grants no execution authority by itself.

## Authority boundary

This phase is QntyLab exploratory research only.

It grants **no**:

- Qnty acceptance
- QntySpot policy authority
- capital authority
- signing
- submission
- live trading
- paper trading
- scientific validation

## Literature basis

The design deliberately follows the anti-data-snooping / anti-overfitting direction of:

- White (2000), *A Reality Check for Data Snooping*, Econometrica. DOI `10.1111/1468-0262.00152`.
- Hansen (2005), *A Test for Superior Predictive Ability*, Journal of Business & Economic Statistics. DOI `10.1198/073500105000000063`.
- Bailey & Lopez de Prado (2014), *The Deflated Sharpe Ratio*, Journal of Portfolio Management. DOI `10.3905/jpm.2014.40.5.094`.
- Bailey, Borwein, Lopez de Prado & Zhu (2017), *The Probability of Backtest Overfitting*, Journal of Computational Finance.
- Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum*, Journal of Financial Economics. DOI `10.1016/j.jfineco.2011.11.003`.

The trend literature supplies a non-zero prior that persistent directional effects can exist. It does not validate this exact hourly SOL rule. The anti-overfitting literature determines the experiment design.
