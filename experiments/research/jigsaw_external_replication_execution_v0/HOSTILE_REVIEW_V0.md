# Hostile Review — Frozen External Replication Final Execution V0

Scope, as frozen: contract identity, aggregation identity, future leakage, H003
timing, state calculation, missingness, XLM handling, costs, asset breadth, LOO,
tail trim, bootstrap, result interpretation.  Acquisition was **not** reopened;
no input was altered; no network call was made.

## Attacks and findings

| Attack | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| Contract identity drift | `request_digest`, `cohort_digest`, `piece_contract_digest`, materialization commit `6c0a8ad`, and adapter commit `2167a3b` are asserted in code and matched before any science ran.  Cohort membership and order equal the 20 frozen members. | None | Closed |
| Unauthenticated bytes entering the estimand | All 22 `INPUT_READY` normalized CSVs were re-hashed and matched their committed manifest `normalized_sha256`.  Execution aborts on any mismatch. | None | Closed |
| Aggregation / estimand substitution | Recovered unambiguously from the committed V0 implementation: `materialize()` builds one row per decision whose `utilities` are the **mean across assets** of per-asset 24h net utility, and `analyze()` computes `primary` from `rows`, not `asset_rows`.  The V0 report states it in words: "assets are not treated as independent rows."  Replication preserves the same unit of analysis over the frozen cohort. | None | Closed |
| Reimplementation drift | Drawdown, PIT percentile, bins, H003 positions, net utility, `_contrast`, and `_bootstrap` are **imported** from the frozen discovery module (sha256 `a2d9fd81…0fa3`) and `qntylab/strategies.py` (sha256 `a641abf9…03b8`), not rewritten. | None | Closed |
| Future leakage in state | Drawdown at `t` uses `max(index[t-719 … t])`; the PIT percentile uses `values[i-365 … i]` inclusive-trailing only; `day_index` is strictly monotone.  No decision reads any bar after `t`. | None | Closed |
| Future leakage in outcome | Utility at `t` reads `close[t … t+24]` and `position[t … t+24]` only.  Positions are `_causal`-shifted, so `position[i]` encodes the signal known at `i-1`. | None | Closed |
| H003 timing / warm-up | First decision `2025-01-01T00:00Z` is source index **96** for every cohort member (start `2024-12-28T00:00Z`), exactly the frozen derivation.  `position[:96]` is identically zero and is never consumed; `MEASUREMENT_STRATEGY_PATH_MISSING` count is 0 because no decision falls in the warm-up. | None | Closed |
| State-panel contract mismatch | State panel is the frozen BTC/ETH/SOL 22,583-hour path, 0 gaps, `2023-12-03T01:00Z`→`2026-06-30T23:00Z`.  First 720h-inclusive drawdown is `2024-01-02T00:00Z`; the 365th subsequent daily observation is `2025-01-01T00:00Z` — the frozen decision-window start, reproduced rather than assumed. | None | Closed |
| One-hour boundary reading of the 720h window | The frozen request derives availability at index 719; the V0 discovery guard was `i >= 720`.  Re-running under the V0 guard gives first decision `2025-01-02`, N=544, stress H-L `+0.0479%` (vs `+0.0438%`), 2025 `-0.0383%`, 2026H1 `+0.1870%`, top-five retention `-251.0%`, same-direction assets 9.  Every conclusion is invariant. | Low | Documented, no change |
| Missingness manufacturing the contrast | 10,920 opportunities, 10,920 telemetry rows, all `(date, symbol)` keys unique, terminal counts sum exactly.  Missingness is 546 XLM rows (uniform across bins, in proportion to bin frequency: 144 HIGH / 211 LOW / 191 MID) plus 19 rows on the single date `2026-06-30` whose `t+24h` close lies past the frozen end.  No bin is differentially depleted, so missingness cannot create the HIGH-vs-LOW difference; handling was not altered in response to this finding. | None | Closed |
| XLM reconstruction / substitution | `XLMUSDT` is `INPUT_PARTIAL` with 0 normalized rows.  A **stale 812 KB `XLMUSDT-perp-1h.csv` exists on disk from an earlier partial pass and does not match any committed digest.**  `load_member()` refuses to open it because the manifest readiness gate precedes the read; the file's hash is recorded as non-matching and never used.  XLM stays a frozen member, receives 546 `SOURCE_DATA_MISSING` terminal states, is `INSUFFICIENT_DATA`, and is excluded from the LOO set and from the breadth denominator. | None | Closed |
| Costs | `COST_MODES` is imported from the frozen V0 module: BASELINE 10/0 bps, STRESS 10/10 bps.  Not redefined. | None | Closed |
| REEFUSDT degeneracy | REEF is `INPUT_READY` (13,200 rows, 0 gaps) but **95.6% of its hourly log-returns are exactly zero** (price 0.00082–0.001244, tick-quantised) — an effectively dead instrument.  Declaring it `POST_DELIST_OR_OTHER_DECLARED_UNUSABLE` now would be post-freeze, outcome-dependent mutation; it was declared usable at freeze and is retained unchanged.  Note it is an `OPPOSITE_DIRECTION` member, so removing it would *strengthen* the replication — retaining it is the conservative choice.  Its LOO run is included and retains sign. | Informational | Reported, no change |
| Leave-one-asset-out gaming | 19 runs, one per usable asset, each recomputing the **primary equal-weight daily aggregation** over the remaining 18.  Range `+0.0197%` … `+0.0728%`; 19/19 retain sign, 0 reverse.  XLM is not run.  (V0's own LOO pooled per-asset rows; the prompt mandates primary-aggregation LOO, which preserves the estimand — the difference is recorded, not hidden.) | None | Closed |
| Tail trim | Exactly the frozen V0 concept: drop the five largest utilities among HIGH∪LOW rows, no top-10, no alternate trim.  Result is decisive against the mean contrast — the spread inverts from `+0.0438%` to `-0.1246%` (retention `-284.5%`), so 5 of 354 conditioning observations carry the entire positive mean. | None | Closed (adverse) |
| Bootstrap | `_bootstrap` imported verbatim: 7-day blocks, 1,000 resamples, seed 271828, no IID t-test.  Stress 95% interval `[-0.4311%, +0.4905%]` around a `+0.0438%` point — `SIGN_UNCERTAIN`. | None | Closed |
| Preview contamination | Committed preview was `stress ≈ +0.0115%`; the authoritative computation returns `+0.0438%`.  Nothing was tuned toward the preview, and no attempt was made to reproduce it. | None | Closed |
| **Result interpretation** | **The pre-execution `classify_magnitude` mapped any spread below 25% of the discovery reference to `NEAR_ZERO`, and `NEAR_ZERO` routed directly to `DRAWDOWN_PIECE_FAILED_EXTERNAL_REPLICATION`.  At 18.5% of discovery the observed `+0.0438%/day` was therefore labelled "near zero" by a ratio band, not by economics — while being 4.4× the negligible-epsilon scale the contract itself names (`+1 bp/day`).  A second defect: the fallback branch contained `not criteria["magnitude_not_trivial"] is False`, which parses as `not (True is False)` and is unconditionally true, so the branch could never discriminate.  Together these let an invented ratio threshold, rather than the evidence, choose between FAIL and MIXED.** | **High** | **Fixed; single targeted re-review run** |

## Targeted fix and re-review

Only the defective classification and disposition logic was changed:

1. `NEAR_ZERO` is now an absolute-scale judgement (`|spread| < 1 bp/day`, the
   epsilon scale the contract names), and the ratio bands only separate
   non-negligible effects.  `+0.0438%/day` classifies as
   `SMALLER_BUT_MEANINGFUL` (18.5% of discovery).
2. The unreachable boolean branch was replaced by an explicit
   `materially_contradicted` test.  `FAIL` is now reserved for vanishing,
   reversal, or absence of credible breadth on **both** frozen primary
   contrasts.  `HIGH_MINUS_LOW_POSITIVE_RATE` is the second frozen primary
   contrast and it replicates broadly (19/19 usable assets positive, 2/2
   temporal blocks positive, `+13.02 pp` stress), so material contradiction
   cannot be asserted.

No input, cost, threshold, bin, lookback, horizon, cohort, or aggregation rule
was touched.  Every measured quantity is bit-identical across the re-run; only
the label and disposition changed:

- stress H-L mean `+0.0438%` → unchanged
- stress H-L positive rate `+13.02 pp` → unchanged
- asset breadth 9 / 9 / 1 / 1 → unchanged
- top-five retention `-284.5%` → unchanged
- bootstrap `[-0.4311%, +0.4905%]` → unchanged
- `DRAWDOWN_PIECE_FAILED_EXTERNAL_REPLICATION` → `DRAWDOWN_PIECE_REPLICATION_WEAK_OR_MIXED`

The revised disposition is **not** a rescue: `WEAK_OR_MIXED` forbids promotion,
forbids the Router, earns no probe, and returns the research budget to
independent Jigsaw discovery.  It differs from `FAIL` only in declining to
close the proposition as contradicted while a co-primary contrast replicates
19/19 across assets and 2/2 across temporal blocks.

A bad scientific result was not treated as a defect: the adverse tail-trim,
negative-2025, and 9-versus-9 breadth findings were left exactly as computed.

Verdict: `PASS_AFTER_ONE_TARGETED_FIX` — no remaining Critical or High finding.
