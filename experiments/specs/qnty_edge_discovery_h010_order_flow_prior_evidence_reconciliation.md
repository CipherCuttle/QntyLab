# H010 Order-Flow Prior-Evidence Reconciliation

## PLAN

This is a read-only forensic reconciliation of canonical Git-tracked evidence.
It is allowed to inspect H010 outcomes, but performs no new scientific
execution, rerun, optimization, candidate proposal, ledger mutation, Jigsaw
mutation, or downstream authority change.

Sources inspected included the H010 specification, implementation, tests,
manifests, result matrix, report, Git lineage, research ledger streams and
generated state, and the later JFP01/JFP03 order-flow-related artifacts.

## RECONCILIATION

H010 is prior exploratory evidence, not untouched territory. It tested a narrow
hourly Binance USD-M perpetual taker-flow strategy family and completed 18
asset-by-variant rows. All six predeclared H010 coordinates were killed by the
fixed sprint gate. The broader proposition that signed aggressive flow can
contain economically useful, strictly pre-decision information was not fully
answered because H010 used a normalized rolling OFI, a simplified fixed-fee
execution model, no sealed holdout, and no venue-specific taker-friction
model.

The proposed modern V0 is therefore materially related but not substantively
identical. It must not be registered as pristine discovery, and it must not be
silently treated as a replication of H010.

## H010_LINEAGE

### Canonical H010 identity

| Field | Reconciled value |
|---|---|
| Family ID | `H010_taker_flow` |
| Candidate ID | None in the current append-only research ledger |
| Variant IDs | None; six inline JSON coordinates in `sprint_v1_perp.json` |
| Strategy ID/version | None; implementation is `qntylab/perp.py` without a strategy-version identity |
| Trial IDs/receipts | None; the legacy result JSON and CSV are not ledger `TRIAL_COMPLETED` receipts |
| Decision event | None in `experiments/research/decisions.jsonl` |
| Fixed variants | `lookback ∈ {1,6,24}`, `threshold = 0.15`, `direction ∈ {+1,-1}` |
| Symbols | `BTCUSDT`, `ETHUSDT`, `SOLUSDT` USD-M perpetuals |
| Bar interval | 1 hour |
| Material Git lineage | `5bfb2bd87abca874aedb6c80d427bc1116077848` (`feat: add perpetual futures exploratory sprint`, 2026-07-28) |

The H010 artifacts were introduced together with the sprint specification,
implementation, manifests, results, report, and tests in commit `5bfb2bd`.
There is no repository evidence of a later H010 reopen, replication event,
candidate event, or renamed H010 ledger descendant.

### Related but distinct later candidates

The later frozen Jigsaw census contains related flow propositions, but no
canonical identity link to `H010_taker_flow`:

- `JFP01` tests quarter-hour boundary order imbalance against an immediately
  preceding generic-flow control and an 8-hour BTCUSDT return. It is an
  association test, not the H010 hourly strategy, and has no local completed
  scientific result.
- `JFP03` tests absolute hourly taker-flow imbalance (`AFI`) for incremental
  24-hour realized-volatility value beyond a HAR-style baseline. Its result is
  `BLOCKED_CANDIDATE` before observations, features, targets, regressions, or
  p-values because `AFI total quote-volume denominator must be positive`.
  It is not directional return evidence and not an H010 replication.

The current ledger context contains no H010, JFP01, or JFP03 candidate/trial
rows. The JFP artifacts are separate research records outside the legacy
strategy ledger.

## H010_MECHANISM

The frozen H010 proposition was:

> Taker-buy quote-volume imbalance forecasts continuation or reversal at the
> next bar.

The stated economic story was that aggressive flow can reflect information or
temporary pressure; both directional interpretations were predeclared. H010
therefore covered a short-term continuation/reversal trading interpretation,
not merely a descriptive order-flow measurement.

## FEATURE_SEMANTICS

The input was Binance USD-M 1-hour kline data, not raw trades or order-book
events. The relevant source fields were:

- `quote_volume`;
- `taker_buy_quote_volume`; and
- the kline timestamp used for causal alignment.

The implementation computes:

```text
OFI_t = 2 * taker_buy_quote_volume_t / quote_volume_t - 1
flow_t = trailing_mean(OFI_t, lookback)
```

Zero quote volume is assigned a neutral buy share of `0.5`, hence `OFI = 0`.
For each variant, `abs(flow_t) >= 0.15` activates a position with sign
`direction * sign(flow_t)`. `direction = +1` is continuation and `direction =
-1` is reversal. The six lookback/direction combinations were fixed before
the reported results.

The feature is a normalized imbalance ratio in `[-1,1]`, not signed quote
notional. It is not a cross-sectional score, volume-surprise feature, order
book measure, raw aggressor-event imbalance, or maker/taker fee classifier.
There is no explicit warm-up contract for the convolution: the implementation
uses a full-lookback denominator with zero-padding behavior at the beginning
of the series. This is a fixed implementation detail, not evidence of a
post-outcome rescue, but it makes the early-window semantics less explicit.

The code applies a one-bar causal shift: a completed bar-t feature first
affects the next bar. The focused test verifies that a flow shock at index 12
does not activate position index 12 and activates index 13. Direct feature to
next-return lookahead was therefore addressed under the sprint's bar
convention.

Residual timing ambiguity remains: the source rows are hourly kline records,
while the report describes the signal as passing through `close[t]` and the
position as effective on the next bar. H010 does not preserve a trade-level
SAFE-KNOWN-AFTER timestamp or a sub-bar latency/fill receipt. The feature also
summarizes trades occurring during the same completed bar whose close is the
decision boundary, so it can encode that bar's contemporaneous price pressure
even though it does not overlap the subsequent close-to-close return.

## TARGET_AND_EXECUTION_SEMANTICS

H010 evaluated executable-style strategy PnL, not a regression or a benchmark
excess measurement:

```text
return_t = close[t+1] / close[t] - 1
net_t = position_t * return_t - fee_t + funding_cashflow_t
```

The position is `-1`, `0`, or `+1`, held/rebalanced hourly. A threshold breach
sets the directional position; sub-threshold flow is flat. A sign flip has two
units of turnover and two fee units. There is no cross-sectional portfolio
weighting, classification target, or long-only restriction.

The result is a next-hour close-to-close trading proposition with a one-bar
feature shift. It is not a test of an immediately subsequent return from raw
sub-hour aggressive flow, and it is not a prospective prediction artifact.

## ECONOMIC_REALISM

**Classification: `PARTIAL`.**

Included:

- 5, 10, and 20 bps fixed fee stress;
- funding cashflow, separately reported from price PnL;
- explicit turnover and trade-count accounting;
- two-unit fee charging on long/short flips; and
- no-return-across-gap handling.

Not included or not evidenced:

- spread or slippage separate from the fixed fee;
- venue-specific taker fee tiers or historical maker/taker fees;
- fill price, latency, queue position, or market-impact modeling;
- liquidation, margin, leverage, or account-equity semantics; and
- a conservative taker-friction contract tied to the actual signal/execution
  timestamp.

Funding was included, but its event-to-bar mapping follows the sprint's
containing-hour convention and is not an exchange execution receipt. The
fixed bps fee should not be described as a full historical taker-cost model.

## SEARCH_DENOMINATOR

The H010 denominator is explicit but narrow:

- 6 predeclared variants: 3 lookbacks × 2 directions;
- 3 assets, producing 18 completed asset-by-variant rows;
- 3 fee levels (5/10/20 bps) for each row; and
- 1 extra-one-bar-delay diagnostic for each row.

The whole sibling sprint denominator was 17 variants × 3 assets = 51 fixed
asset-variant runs: H007=4, H008=3, H009=4, H010=6. H010 was not selected
after seeing its own outcomes; the six coordinates were present in the frozen
specification. However, there is no ledger identity, per-run input digest,
trial receipt, or canonical record of manual/LLM ideas considered outside the
fixed sprint. The denominator is therefore preserved for the recorded sprint,
not for every possible historical order-flow thought.

The manifests bind the intended data identity to Binance public USD-M
klines/premium/funding archives. They describe BTC and ETH as 47,976 hourly
rows from 2021-01-01 through 2026-06-30 and SOL as 47,880 rows over the same
declared interval, with documented gaps. The legacy result artifacts do not
carry ledger-style per-trial input hashes or immutable execution receipts.

## HISTORICAL_RESULTS

The canonical H010 result matrix contains 18 rows. At the primary 10 bps
cost, only two rows were positive:

| Asset | Direction | Lookback | Net return | Temporal result | 5/10/20 bps net |
|---|---:|---:|---:|---|---|
| ETHUSDT | reversal (`-1`) | 6h | +0.2498% | middle negative, late positive; only 1 positive third | +0.7525% / +0.2498% / -0.7488% |
| SOLUSDT | reversal (`-1`) | 24h | +5.1872% | early positive, middle and late zero; only 1 positive third | +6.4590% / +5.1872% / +2.6871% |

All BTC rows were non-positive or inactive at 10 bps. All other ETH and SOL
rows were non-positive at 10 bps. The two positive rows had no second-asset
support for their exact parameter coordinate, so `cross_asset_support = 0`.
The extra-delay controls were lower than the real-alignment rows for these two
cases (`-0.9424%` for ETH 6h reversal and `+4.2554%` for SOL 24h reversal),
but this did not cure their temporal breadth or cross-asset failures.

The report also records severe turnover sensitivity for the 1-hour variants:
BTC continuation lookback 1 lost approximately 99.94% net at 10 bps with
7,640 turnover units; ETH and SOL lookback-1 variants similarly lost almost
all capital under the fixed accounting. The 24-hour reversal result on SOL is
the best H010 row but is concentrated in the early third and one asset.

Evidence class:

- **In-sample/development:** the full historical matrix and chronological
  thirds are exploratory historical evidence;
- **Temporal robustness:** early/middle/late split diagnostics, not a sealed
  holdout or independent out-of-sample confirmation;
- **Cost stress:** fixed 5/10/20 bps sensitivity;
- **Prospective:** none; and
- **Formal inference:** none; no p-values or confidence intervals were part of
  H010.

## CANONICAL_DECISION_STATE

The sprint report's family verdict is `KILL` for H010 in this fixed first-pass
matrix, with no survivors. This is a report-level legacy judgment, not a
current ledger `DECISION_RECORDED` event.

Primary classification:

`EXACT_VARIANT_FALSIFIED_FAMILY_OPEN`

What is killed:

- all six predeclared H010 coordinates as tested on BTCUSDT, ETHUSDT, and
  SOLUSDT under the sprint's fixed economic contract;
- the claim that this fixed hourly normalized-OFI strategy family cleared the
  sprint's positive-net, temporal-breadth, cross-asset, and delay-control
  gate; and
- any interpretation of the two isolated positive rows as a survivor.

What remains open:

- other order-flow constructions, timing granularities, and economic
  mechanisms;
- the proposed strictly pre-decision lagged signed-flow proposition; and
- a separately authorized follow-up with a materially specified friction and
  evidence contract.

What was never tested by H010:

- raw signed aggressive quote notional rather than normalized OFI;
- sub-hour or trade-event flow observed strictly before decision time;
- explicit spread/slippage and venue-appropriate taker friction;
- a sealed outer holdout or prospective prediction-first confirmation; and
- incremental information beyond a frozen simpler return baseline.

## WHAT_H010_PROVES

H010 proves only that the recorded fixed hourly normalized-OFI strategy matrix
was tested causally under its stated bar convention, that its exact
coordinates did not pass the exploratory survivor gate, and that two isolated
asset/coordinate positives appeared but lacked breadth and robustness.

It also proves that order flow was not an untouched QntyLab mechanism family at
the time of the later proposed V0.

## WHAT_H010_DOES_NOT_PROVE

H010 does not prove that all taker flow, all aggressive order flow, all signed
notional features, all assets, or all horizons are economically useless. It
does not establish causality, a durable trading edge, a robust net utility
after actual taker execution friction, prospective evidence, or any Qnty,
Router, State Snapshot, paper, live, or capital authority.

## RED_TEAM_FINDINGS

| Question | Finding | Severity |
|---|---|---|
| Same-bar leakage | One-bar shift and a focused test address direct feature-to-next-return leakage. Close-boundary/sub-bar SAFE-KNOWN-AFTER is not preserved. | Medium |
| Feature/target overlap | Target starts after the feature bar; however the feature summarizes the same bar's internal trades and may encode its contemporaneous move. | Medium |
| Mechanical price content | No OHLC return is directly used in OFI, but taker flow is mechanically co-produced with the bar's price path; no orthogonal control was run. | Medium |
| Maker/taker interpretation | Kline `taker_buy_quote_volume` gives a buy-aggressor convention. No raw trade-level semantic audit or venue fee mapping exists. | High |
| Asset-selection hindsight | BTC/ETH/SOL and no per-asset tuning were fixed in the spec; broader asset-selection provenance is not recorded. | Medium |
| Parameter-selection hindsight | Six coordinates were frozen and preserved; no post-result tuning evidence was found. The best coordinates remain search-selected within that six-member family. | Medium |
| Missing denominator | The sprint denominator is explicit; manual/LLM search outside it and ledger identities are absent. | High |
| Cost understatement | Fixed fees include no explicit spread/slippage/impact or historical taker tiers. | High |
| Funding omission | Funding is included and separately reported; exact event-time versus bar-time semantics remain a contract weakness. | Medium |
| Turnover understatement | Position changes and flips are charged explicitly. Realized execution impact remains unmodeled. | Medium |
| Unrealistic execution price | Close-to-close accounting is not a taker fill or latency model. | High |
| Survivorship bias | Only three selected symbols were tested; no broad historical universe census was part of H010. | Medium |
| Multiple testing | The fixed 18-row denominator is visible, but no formal inference or multiplicity correction was applied. | High |
| Regime/event concentration | The positive SOL row is early-third-only; no event/regime decomposition or holdout exists. | High |
| Microstructure/autocorrelation | The one-hour horizon can reflect transient microstructure or bar autocorrelation; the extra-delay control is not a full microstructure null. | High |

These are classification findings only. This phase did not repair or rerun any
defect.

## COMPARISON_TO_PROPOSED_ORDER_FLOW_V0

Proposed question:

> Does lagged signed aggressive trade flow observed strictly before decision
> time contain economically useful information about the immediately
> subsequent return interval after conservative taker friction?

| Dimension | H010 | Proposed V0 | Same / different / unknown | Material? |
|---|---|---|---|---|
| Mechanism | Aggressive taker pressure; continuation or reversal | Lagged signed aggressive flow | Same broad mechanism; different frozen claim | Yes |
| Raw feature | Normalized `2*taker_buy_quote/quote - 1` | Signed flow, exact formula unspecified | Different/unknown | Yes |
| Sign convention | Positive buy aggressor; `direction` chooses continuation/reversal | Signed aggressive flow, exact buy/sell convention unspecified | Related/unknown | Yes |
| Normalization | Quote-volume share imbalance | Unspecified; may be signed notional | Different/unknown | Yes |
| Aggregation horizon | 1, 6, or 24 hourly OFI mean | Unspecified | Unknown | Yes |
| Prediction horizon | Immediately next 1h close-to-close return | Immediately subsequent interval, exact boundary unspecified | Related/unknown | Yes |
| Decision timing | Completed hourly bar, then one-bar causal shift | Strictly before decision time | Related; H010 lacks sub-bar safe-known proof | Yes |
| Same-bar contamination | No direct overlap with next return; same completed bar's trades are used | Intended to be strictly pre-decision | Different timing standard | Yes |
| Universe | BTC, ETH, SOL USD-M perpetuals | Unspecified | Unknown | Yes |
| Market type | Binance USD-M perpetual | Unspecified | Unknown | Yes |
| Cost model | Fixed 5/10/20 bps fee stress | Conservative taker friction | Different/unknown | Yes |
| Funding | Included in net PnL | Unspecified | Unknown | Yes |
| Turnover | Explicit position-change turnover and flip fees | Unspecified | Unknown | Yes |
| Benchmark | No flat/incremental-return benchmark; delay control and cross-asset gate | Economically useful implies a baseline, exact one unspecified | Different/unknown | Yes |
| Search budget | Six variants, 18 asset rows, fixed before results | Unspecified | Different/unknown | Yes |
| Multiplicity | Denominator preserved; no formal correction | Unspecified | Unknown | Yes |
| OOS structure | No sealed holdout; thirds are diagnostics | Unspecified | Unknown | Yes |
| Robustness | Costs, thirds, cross-asset, gap, extra delay | Conservative economic robustness intended, exact contract unspecified | Partial overlap | Yes |

## DUPLICATION_ANALYSIS

The proposed V0 is not Route A. H010 already paid for a narrow related
question—whether six normalized hourly OFI threshold rules could produce a
cross-asset, temporally broad, fixed-fee net strategy. That exact question
should not be bought again.

The proposed V0 changes at least the feature semantics, strict timing standard,
and friction claim. H010's positive rows also failed the gate, so this is not
Route C: canonical evidence does not earn a follow-up based on prior economic
promise. JFP01 and JFP03 do not change that conclusion because they are
different claims and have no completed local economic result.

## CORRECTION_TO_PRIOR_FORENSICS

The prior broad classification `UNEXPLORED_OR_MATERIALLY_UNDEREXPLORED` was:

`CORRECT_BUT_TOO_BROAD`

It was correct that the broad order-flow design space remained materially
underexplored: H010 covered one hourly kline-derived normalized feature family,
three selected assets, six coordinates, and a partial cost model. It was too
broad if read as saying QntyLab had no prior order-flow/taker-flow economic
evidence. H010's historical PnL results are now part of the search denominator
and must be disclosed in any later order-flow work.

## NARROWEST_NEXT_INFORMATION_BEARING_QUESTION

If a next phase is separately authorized, the narrowest unanswered question is:

> Does a strictly pre-decision, lagged signed taker quote-notional imbalance
> (with an explicitly frozen buy-minus-sell numerator, rather than H010's
> rolling normalized OFI) improve the immediately following 1-hour Binance
> USD-M perpetual return after explicit taker fee, spread/slippage, and
> funding treatment?

This is a material-gap follow-up question, not a clean-slate discovery claim,
and it must not be executed from this report. It would require a new immutable
candidate proposal and a new bounded denominator; it should not silently reopen
or mutate H010.

## NEXT_PHASE

No next phase is authorized by this reconciliation. If later authorized, it
should be labeled a new preregistered follow-up/replication of a materially
different feature and execution proposition, with H010, JFP01, and JFP03
included in the prior-evidence census.

## VERDICT

`H010_ORDER_FLOW_RECONCILIATION_MATERIAL_GAP_REMAINS`

