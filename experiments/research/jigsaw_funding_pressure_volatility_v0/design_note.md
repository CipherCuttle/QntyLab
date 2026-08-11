# JIGSAW FUNDING PRESSURE → VOLATILITY V0

Status: `PREREGISTERED_NOT_EXECUTED` / `DESIGN_ONLY`.

## Reconciliation verdict

- `origin/master` reconciles to `16081045175abf30cdf33d983618b2e58cc46b79`.
- The primary worktree contains unrelated modified manifests, research-ledger edits, and untracked run/data artifacts; none were overwritten or adopted.
- Canonical master contains certified BTCUSDT, ETHUSDT, and SOLUSDT funding manifests. The frozen 20-member Jigsaw/Breadth panel does not yet have canonical certified funding coverage. Local untracked manifests are WIP and are not evidence.
- Prior overlap exists with killed H007 funding extremes and H008 funding-conditioned momentum, but neither tests a market-wide forward-volatility outcome. Basis/premium research is not equivalent and is excluded.

## Source and cadence contract

Funding uses the existing Binance USD-M materializer: publisher-checksummed monthly archive as causal source, exact REST rate/time reconciliation as coverage witness, and exact event timestamps. The `funding_interval_hours` field is descriptive; no 8-hour schedule is assumed. Binance's funding mechanism supports the sign convention, but interval changes make an event-time contract mandatory.

## Design decision

The single state is the cross-sectional median of the absolute value of each frozen panel member's latest known, no-more-than-24-hour-old realized settlement rate at daily 00:00Z. This is one absolute-pressure recipe. It does not also test signed funding, mean funding, dispersion, acceleration, or shock.

The single outcome is unannualized realized volatility of the equal-weight 20-member market return over the following non-overlapping 24 hourly intervals. The sole contrast is HIGH minus LOW mean RV24, with the direction frozen positive.

## Safety decision

`SAFE_TO_PREREGISTER: YES_WITH_EXECUTION_BLOCKER`.

Funding rate itself is defensible as a perpetual-contract state variable. The literature only motivates the question; it does not establish the QntyLab effect. Execution is blocked until a fresh, append-only materialization certifies 20/20 point-in-time funding and OHLCV coverage under the exact contract and until the sealed Breadth boundary is respected.

No outcome, statistical result, strategy family, Router feature, or trading authority is created.

## Bounded repair record

- F1 repaired by freezing fraction-scale ECDF semantics with rational tertile thresholds: LOW `<= 1/3`, MID `> 1/3 and < 2/3`, HIGH `>= 2/3`; `<=` tie semantics are inherited explicitly.
- F2/F3 repaired by binding the exact-20 materialization identities and provenance aggregates in `materialization_index.json`, then covering its canonical digest from the preregistration contract digest.
- F4 duplicate funding-timestamp tie semantics remains deferred; this pass found no evidence that it falsifies or prevents a required invariant.
