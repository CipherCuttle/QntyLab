# QntyLab Perpetual-Futures Structure Sprint v1

**EXPLORATORY ONLY · NON_AUTHORITATIVE · NO SCIENTIFIC VALIDATION · NO HOLDOUT · NO PAPER/LIVE AUTHORITY · NO TRADING EXECUTION**

## PLAN

Test a small, preregistered set of perp-native signals on BTCUSDT, ETHUSDT, and SOLUSDT 1h USD-M perpetuals, with 10 bps per absolute position change as the primary screen. Sprint v0 price-rule families were not rerun or retuned.

## LITERATURE

Literature is a prior, not validation. Ackerer, Hugonnier, and Jermann explain funding as the price-anchoring mechanism for perpetuals; He, Manela, Ross, and von Wachter model the spot-perp gap and funding transfer; Chi et al. find basis important in a different, cross-sectional futures setting. Those motivate testing premium and funding, not copying their strategies. Funding-rate dynamics are also reported as forecastable in a recent BTC/Bybit study, while current order-flow work motivates a narrow causal flow screen rather than a model search.

## DATA SOURCES

- Binance public-data monthly USD-M archives: `klines`, `premiumIndexKlines`, and `fundingRate`.
- Binance kline schema supplies OHLCV, quote volume, trade count, and taker-buy base/quote volumes.
- Funding is an actual settled event from the archive; it is never synthesized from premium.

## DATASET

| Symbol | Perp 1h rows | Funding events | Range | Source gaps |
|---|---:|---:|---|---:|
| BTCUSDT | 47,976 | 6,021 | 2021-01-01 to 2026-06-30 | 5 |
| ETHUSDT | 47,976 | 6,021 | 2021-01-01 to 2026-06-30 | 5 |
| SOLUSDT | 47,880 | 6,096 | 2021-01-01 to 2026-06-30 | 6 |

Each manifest records source, market, type, timeframe, range, row count, retrieval timestamp, gap list, and SHA-256 for the raw perp and funding files. Timestamps are strictly increasing; duplicate events, non-finite values, invalid OHLC, invalid taker/total-volume relationships, and extreme funding values are rejected.

## ALIGNMENT CONTRACT

- A feature observed in hourly bar *t* can first produce the *t+1* return.
- A settled funding event is placed in its containing hour and then delayed one bar; it cannot explain any return before its event time.
- Premium is the close of Binance's `premiumIndexKlines`, not a spot/perp or mark/index substitute.
- OFI is `2 * taker_buy_quote_volume / quote_volume - 1`; a zero-quote-volume hour is neutral, not infinite.
- No return is bridged across a source gap.

## PERP PNL CONTRACT

For every return interval, `net = position * close_return - transition_fee - position * settled_funding_rate`. Thus positive funding debits a long and credits a short. Price PnL, funding cashflow, and fees are reported separately. A long-to-short flip has two units of turnover and therefore two fee units.

## SPRINT V1 PREREGISTRATION

`experiments/specs/sprint_v1_perp.json` fixes 17 variants: H007 (4), H008 (3), H009 (4), and H010 (6), across three assets for 51 runs. The primary classification requires positive 10 bps net, two positive thirds, support on two assets, and a result better than an extra-bar-delay control. No H011 grid was authorized unless a prior family survived.

## H007 FUNDING EXTREMES

12 runs. One BTC-only positive result existed: 168h / 2.0 z-score / 24h hold netted +21.21% at 10 bps, but ETH and SOL were negative, its late third was -34.25%, and the extra-delay control was higher (+47.61%). **KILL.**

## H008 FUNDING-CONDITIONED MOMENTUM

9 runs. No run was positive after 10 bps; the neutral-funding filter did not rescue fixed 168h momentum. **KILL.**

## H009 PREMIUM / BASIS

12 runs. No run was positive after 10 bps. The strategy is particularly turnover-sensitive, so contemporaneous-looking premium behavior did not turn into a viable lagged gross-to-net result. **KILL.**

## H010 TAKER FLOW

18 runs. Two asset-specific positives failed the gates: ETH 6h reversal was +0.25% but had only one positive third; SOL 24h reversal was +5.19% but only in the early third and had no second-asset confirmation. **KILL.**

## OPTIONAL H011

Not run. No H007–H010 family passed the preregistered survivor gate.

## RUN MATRIX

4 H007 + 3 H008 + 4 H009 + 6 H010 variants × BTC/ETH/SOL = **51** fixed runs. No per-asset parameter tuning or ML was used.

## RESULTS

Only 3 of 51 asset–variant runs were net positive at 10 bps; none passed the full classification. Detailed rows are in `sprint_v1_perp_results.json` and the compact matrix is in `sprint_v1_perp_summary.csv`.

## TEMPORAL ROBUSTNESS

The BTC H007 candidate was positive in early and middle thirds but negative in late. ETH H010 reversal was flat/negative/positive across early/middle/late; SOL H010 reversal was positive only in early. These are kills, not partial confirmations.

## CROSS-ASSET ROBUSTNESS

No parameter set had two supported assets. The H007 BTC positive did not transfer; the two H010 positives were unrelated asset/parameter cases.

## COST STRESS

The BTC H007 candidate changed from +62.25% at 5 bps to +21.21% at 10 bps and -32.39% at 20 bps. ETH H010 6h reversal changed from +0.75% to +0.25% to -0.75%. These results reinforce, rather than weaken, their kills.

## FUNDING ATTRIBUTION

For the BTC H007 candidate: price PnL +99.93%, funding cashflow +8.28%, and fees -58.30%, yielding +21.21% net. Funding was not double-counted; this did not survive the robustness gates.

## GAP SENSITIVITY

Returns touching each documented gap are zeroed. A survivor-only exclusion rerun is not applicable because there are no survivors.

## NULL / LAG CONTROL

Every run has an extra-one-bar-delay diagnostic. The BTC H007 positive was weaker than its delayed control. The SOL H010 positive remained early-third-only. Neither is a temporal-alignment survivor.

## RED TEAM

Lookahead, funding timestamp, premium definition, same-bar flow, cost, carry double-counting, gaps, single-asset behavior, calendar concentration, and an extra delay were all addressed in code/tests or the reported control. The remaining candidates fail before any claim about alpha is warranted.

## KILLS

H007, H008, H009, and H010 are killed for this fixed first-pass matrix. H011 is deferred, not inferred negative.

## SURVIVORS

None.

## RANKING

| Rank | Hypothesis | Assets supported | 10bps net | Temporal | Parameter | Control | Verdict |
|---:|---|---:|---|---|---|---|---|
| 1 | H007 funding extremes | 0 | BTC-only +21.21% best | late negative | isolated | delayed better | KILL |
| 2 | H010 taker-flow reversal | 0 | SOL-only +5.19% best | early-only | isolated | insufficient | KILL |
| 3 | H009 premium reversion | 0 | no positive run | failed | none | failed | KILL |
| 4 | H008 funding-conditioned momentum | 0 | no positive run | failed | none | failed | KILL |

## CODE CHANGES

Added the narrow futures archive loader, funding-event loader, premium/OFI feature path, causal position generation, perp PnL attribution, fixed Sprint v1 runner, manifests, and results receipts. Sprint v0 logic was left intact.

## TESTS

`python -m pytest -q` → **10 passed**. Coverage includes funding sign and event timing, premium/OFI one-bar lag, no return across a gap, long/short PnL, fees, long-short transition, deterministic output, and safe final-third splitting.

## FILES / RECEIPTS

- `data/manifests/*-perp-1h.json`
- `experiments/specs/sprint_v1_perp.json`
- `experiments/results/sprint_v1_perp_results.json`
- `experiments/results/sprint_v1_perp_summary.csv`

## COMMIT

Recorded with the implementation and receipts for this standalone QntyLab sprint.

## WHAT WE LEARNED

These raw perp-native variables did not yield a cross-asset, temporally robust, cost-resilient first-pass signal under strict causal alignment. The apparent BTC funding candidate is especially fragile to a one-bar delay and cost stress.

## NEXT EXPERIMENT

Do not broaden the universe or add H011. If the work is resumed, first audit the archive gap pattern and define one independently motivated, lower-turnover premium/funding feature before a new versioned preregistration.

## VERDICT

QNTYLAB_PERP_SPRINT_ALL_KILLED

## Sources

- Binance public-data archive README: https://github.com/binance/binance-public-data/blob/master/README.md
- Binance derivatives documentation: https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/Introduction
- Ackerer, Hugonnier, Jermann, *Perpetual Futures Pricing*: https://arxiv.org/abs/2310.11771
- He, Manela, Ross, von Wachter, *Fundamentals of Perpetual Futures*: https://arxiv.org/abs/2212.06888
- Chi et al., *An empirical investigation on risk factors in cryptocurrency futures*: https://onlinelibrary.wiley.com/doi/abs/10.1002/fut.22425
- Inan, *Predictability of Funding Rates*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5576424
- Liu et al., *Order flow and cryptocurrency returns*: https://www.sciencedirect.com/science/article/pii/S1386418126000029
