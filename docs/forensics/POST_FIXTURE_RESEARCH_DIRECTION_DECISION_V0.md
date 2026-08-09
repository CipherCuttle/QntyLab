# Executive Verdict

`CLOSE_AS_INFRASTRUCTURE_ONLY`. The verified QNTY feature proves a bounded, hypothetical funding-transfer calculation for one authentic public event and a synthetic quantity. It does not add a predictive observation, a research dataset, or a new economic signal. QntyLab's earlier funding-extremes and funding-conditioned-momentum screens were already killed under causal alignment and cost stress; the currently retained worktree also lacks the registered raw perpetual and funding inputs needed to identify a fresh question. No candidate, trial, or decision is created.

# Scope

Decision ID: `DECIDE_POST_FIXTURE_RESEARCH_DIRECTION_V0`. This is a documentation-only research-direction decision. It does not register a candidate, append a trial or research decision, run a backtest, alter QNTY, merge, cherry-pick, push, or create execution, margin, liquidation, or capital infrastructure.

# Repository Identities

QntyLab decision worktree: `/home/swirky/DevHub/worktrees/QntyLab-post-fixture-direction-v0`, branch `research/post-fixture-direction-v0`, starting HEAD `a7e6c6f9b49dffeff1419ad592ceb518b0b9a5f9`.

Read-only QNTY integration worktree: `/home/swirky/DevHub/worktrees/Qnty-public-economic-fixture-v0`, branch `feat/public-economic-fixture-v0-integration`, HEAD `1b5e3793f69f79487f3cf325e561b548598d9aa6`.

# Verified QNTY Capability

Classification: `VERIFIED_ACCOUNTING_PRIMITIVE`, not `VERIFIED_RESEARCH_SIGNAL` and not `VERIFIED_STRATEGY_COMPONENT`. The chain is `6d3d33e` (fixture), `252b463` (verification hardening), `b9a3722` (worktree-safe source resolution), and `1b5e379` (integration receipt). The integration receipt reports base `7493 passed, 0 failed, 1 skipped` and integrated `7554 passed, 0 failed, 1 skipped`, with claim scope `HYPOTHETICAL_PUBLIC_FUNDING_ECONOMIC_RECONSTRUCTION_ONLY`.

The primitive deterministically applies Decimal funding arithmetic to an authentic public event and a synthetic signed position. A correct transfer formula is an accounting identity conditional on its inputs; it is not evidence that funding predicts returns or that a trade is viable.

# Evidence Chain

Established: official public finalized-event identity, public rate/time/mark-price source integrity, signed-quantity arithmetic, sign and dimensional rules, deterministic receipts, and repair of the hostile review's verification-metadata blocker.

Refuted: arithmetic-sign, dimensional, raw-hash, selected-event-hash, duplicate-identity, and receipt-verification-metadata attacks within the fixture contract. The fresh hostile rereview reports 25 metadata mutations rejected and independent arithmetic/identity oracle passes.

Unknown or out of scope: account settlement, wallet rounding, position ownership, execution, spot hedge, historical product eligibility, margin, liquidation, ADL, profitability, alpha, causal effect, and strategy validity. Authentic evidence is the Binance public finalized event and its archive/checksum chain. The signed position quantity and all resulting economic transfers are synthetic/paper accounting.

The earlier settlement-evidence audit was closed because authentic account receipt, matched signed position, product identity, and precision evidence were absent. The public-event fixture changed only the bounded public-accounting premise, not those missing research or trading premises.

# Existing QntyLab Research State

The append-only streams contain 19 candidate proposals, 22 decisions, and 378 completed trials. There are no funding-family candidate or trial events in the current research ledger; however, the retained `SPRINT_V1_PERP_REPORT.md` and `sprint_v1_perp_results.json` contain prior funding research: `H007_funding_extremes` and `H008_funding_conditioned_momentum`. Both are repeatedly `KILL`ed. The report states that the apparent BTC H007 result did not survive robustness gates and that the perp-native variables did not yield a cross-asset, temporally robust, cost-resilient signal.

The strategy registry retains non-funding price strategy families. The older perp runner contains H007/H008 logic, causal one-bar delay, fee treatment, and gap handling, but its raw perp/funding files are not retained in this worktree. The protected 2023 spot holdout is not available for a clean result: each asset has a registered missing bar at `2023-03-24T13:00:00Z`, with `REJECT` gap policy. No protected funding holdout is available.

# Data-Capability Inventory

| Dataset | Class | symbols/range/frequency | fields and costs | status |
| --- | --- | --- | --- | --- |
| `data/manifests/*-perp-1h.json` | `NORMALIZED_DERIVATIVE` metadata | BTCUSDT, ETHUSDT, SOLUSDT; 2021-01-01 through 2026-06-30; 1h | describes `klines`, `premiumIndexKlines`, `fundingRate`, event counts and gaps; no rows/cost series retained | provenance is Binance public monthly archives, but manifests alone cannot identify an outcome |
| `data/manifests/*-1h.json` | `NORMALIZED_DERIVATIVE` metadata | BTCUSDT, ETHUSDT, SOLUSDT; 2021-01-01 through 2026-07-28; 1h | spot OHLC metadata and gaps; no retained raw CSV | registered 2023 holdout has a common missing evaluation bar |
| `data/derived/focused_trend_validation_v1/*` | `SYNTHETIC`/halt-normalized derivative | three spot symbols; 2023; 1h | normalized spot only; no funding or perp return series | explicitly unsuitable for funding inference |
| public event fixture | `AUTHENTIC_PUBLIC_DATA` plus `PAPER_ACCOUNTING` | one BTCUSDT event at 2026-06-01 | rate, mark price, timestamp; synthetic quantity and transfer | one event has no return panel, universe, holdout, volume, or costs |

Consequently, time-series prediction, cross-sectional prediction, event studies, persistence, reversal, extreme conditioning, and funding-versus-forward-return analysis are all unidentifiable in the current retained data. The formula fixture alone is not research data.

# Candidate Hypotheses

| ID | economic statement / null / alternative | unit, universe, horizon | cost and holdout | primary metric / kill criterion | classification |
| --- | --- | --- | --- | --- | --- |
| PF-H01 | Funding rate persists across consecutive settlements. Null: lag-one association is zero. Alternative: it is positive. | settlement event; BTC/ETH/SOL USD-M; one interval | no cost, but needs multi-event panel and untouched time holdout | holdout lag-one correlation; kill if nonpositive or unstable | `REQUIRES_NEW_DATA` |
| PF-H02 | Extreme settled funding predicts next-interval reversal. Null: conditional forward return is zero. Alternative: opposite-signed return. | event; BTC/ETH/SOL; next 8h | cost-aware diagnostic and protected holdout required | holdout mean forward return; kill if not cross-asset/cost robust | `DUPLICATES_EXISTING_RESEARCH` |
| PF-H03 | Funding sign predicts next perpetual return sign. Null: no directional association. Alternative: sign association. | event; BTC/ETH/SOL; next 8h | no tradability claim, but needs aligned perp returns and holdout | out-of-sample directional score; kill at chance or unstable | `REQUIRES_NEW_DATA` |
| PF-H04 | Funding magnitude predicts next-interval crash-tail incidence. Null: equal tail incidence. Alternative: higher incidence after extremes. | event; BTC/ETH/SOL; next 8h | needs predeclared tail and sufficient events; protected holdout | holdout tail-risk difference; kill if interval includes zero | `TOO_MANY_DEGREES_OF_FREEDOM` |

Every candidate has a null and a kill criterion. None survives; candidate count is 4 and surviving count is 0.

# Ten-Method Analysis

1. Socratic decomposition asks what new observation the fixture contributes. It contributes one settlement calculation, not repeated predictor/outcome observations.
2. Hegelian analysis: thesis—verified public economics may motivate funding research; antithesis—the result is synthetic accounting and the prior funding screen failed; synthesis—the primitive is useful infrastructure but does not justify another hypothesis.
3. Popperian falsification rejects each candidate unless it can fail on frozen, aligned out-of-sample data. The data panel and protected funding holdout are absent.
4. Causal inference separates a funding event from its causes: expected return, crowding, price movement, and funding are jointly determined. No intervention or credible identification exists.
5. Systems architecture finds a clean boundary: QNTY owns deterministic accounting; QntyLab needs independently versioned funding/return panels and holdout governance before signal work.
6. Cybernetic feedback requires observed data quality, alignment, gaps, and outcome diagnostics. One fixture gives no feedback loop; the retained 2023 holdout is blocked by the registered gap.
7. Bayesian calibration assigns low prior plausibility after H007/H008 failures and very low probability of useful learning without new data; the probability of profitable deployment is lower still.
8. Minimum-description-length reasoning favors PF-H01, but it still requires a panel. Thresholded reversal and tail hypotheses add arbitrary thresholds, horizons, and transforms.
9. Design of experiments requires predeclared universe, sample, alignment, holdout, and correction. Those cannot be honestly frozen from a single fixture or absent raw panel.
10. Adversarial testing attacks look-ahead, timestamp containment, overlapping outcomes, serial correlation, exchange-specificity, survivorship/listing selection, interval changes, mark/trade mismatch, omitted costs, liquidation selection, endogeneity, and snooping. No candidate clears these attacks on available evidence.

# Falsification Results

PF-H01 fails data-panel and holdout availability. PF-H02 duplicates previously killed H007 funding extremes and is additionally exposed to look-ahead, serial correlation, regime dependence, interval-change, return/funding endogeneity, and cost omission. PF-H03 lacks aligned retained perpetual prices and is exposed to reverse causality and mark-price/trade-price mismatch. PF-H04 introduces tail thresholds, horizon selection, rare-event instability, multiple testing, and liquidation-selection confounding. No causal, trading, or profitability claim survives.

# Causal and Predictive Boundary

Accounting identity: the fixture transfer equals signed quantity times mark price times rate under its pinned rules. Predictive association would require an out-of-sample relationship between a known-at-formation funding variable and later return. Causal effect would require identification beyond observational association. An economic mechanism is only a hypothesis about crowding; it is not established. Tradable edge additionally requires executable prices, costs, financing, position, margin, and liquidation evidence. This decision makes none of those claims.

# Bayesian Assessment

| hypothesis | prior plausibility | evidence quality | expected information gain | useful learning | actionable strategy |
| --- | --- | --- | --- | --- | --- |
| PF-H01 | LOW | VERY_LOW | LOW | LOW | VERY_LOW |
| PF-H02 | LOW | LOW (prior negative result) | VERY_LOW | VERY_LOW | VERY_LOW |
| PF-H03 | LOW | VERY_LOW | LOW | LOW | VERY_LOW |
| PF-H04 | VERY_LOW | VERY_LOW | VERY_LOW | VERY_LOW | VERY_LOW |

A clean scientific result requires a data panel and protected holdout. It is distinct from, and materially more likely than, any future profitable deployment; neither is supported here.

# Description-Length Ranking

1. PF-H01: one lag and one correlation, but infeasible without a panel.
2. PF-H03: one sign and one forward horizon, but lacks aligned outcome data.
3. PF-H02: requires extremeness threshold and reversal rule; also duplicates prior work.
4. PF-H04: tail threshold, funding threshold, horizon, and rare-event conditioning; excessive degrees of freedom.

# Best Surviving Hypothesis

`NONE`. PF-H01 is the shortest future question, not a surviving current hypothesis. It must not be registered from this decision.

# Prospective Experiment Contract

No prospective experiment is proposed because no hypothesis survives. Maximum proposed trials: `0`; maximum variants: `0`. A future PF-H01 contract would first require one immutable multi-event funding panel, aligned perpetual outcomes, a predeclared BTC/ETH/SOL universe, a separated untouched holdout, timestamp-containment rules, and autocorrelation-aware inference. It would make no causal, profitability, execution, margin, liquidation, or deployment claim.

# Stop-versus-Continue Decision

Outcome: `CLOSE_AS_INFRASTRUCTURE_ONLY`. Scientific value and novelty are LOW because the fixture changes arithmetic assurance rather than information; data readiness is VERY_LOW; implementation cost and false-discovery risk are HIGH if data infrastructure is rebuilt solely to revisit a killed family; economic relevance is unproven; opportunity cost is HIGH. Continuing would duplicate H007/H008 or require broad new data work.

# QNTY Integration Recommendation

`MERGE_AS_GENERAL_ACCOUNTING_CAPABILITY`, subject to ordinary independent integration review, not as a strategy prerequisite or evidence of alpha. The 899-line module and 61 focused tests impose maintenance cost, but deterministic public-event reconciliation is independently useful and its dedicated branch confines cross-repository provenance. This report does not merge, cherry-pick, or push it.

# Non-Claims

No claim is made about account settlement, wallet postings, real position, real trade, execution, spot hedge, capital efficiency, margin, liquidation, ADL, profitability, alpha, causal effect, strategy validity, or production readiness. No candidate/trial/decision state was changed.

# Verification

Verified decision-worktree identity, QNTY branch/head and four-commit chain, receipt test counts and claim scope, the six Markdown/JSON forensic sources, research streams, retained funding results, data manifests, holdout audit, and source locations. The validator for this report checks outcome uniqueness, report agreement, hypothesis completeness, bounded trial budget, prohibited claims, and cited-path existence.

# Final Verdict

`POST_FIXTURE_RESEARCH_DIRECTION_DECIDED` with decision `CLOSE_AS_INFRASTRUCTURE_ONLY`.

# Immediate Next Action

`ARCHIVE_PUBLIC_FUNDING_FIXTURE_BRANCH_V0`.
