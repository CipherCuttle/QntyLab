# Qnty Trading Results Sprint V0 — Candidate Selection and Freeze

## PLAN

Reconcile canonical Git and research state, identify the truthful Breadth V2
interpretation, select exactly three still-executable exact variants, freeze
the existing economic contract for a later execution phase, perform one
hostile review, check QntyAgentEval applicability, and stop without execution.

## RECONCILIATION

The working tree was clean at commit `b5cc2cee3d76ed69e592ad90b2b43dae33c5a35e`.
The local branch has no live upstream ref; `git ls-remote` verified the
published remote refs. `project_context`, `research_ledger context`, and
`research_ledger doctor` all completed without a canonical-source conflict.

The apparent Breadth V2 contradiction has two different authorities:

- The generated ledger state is derived only from `candidates.jsonl`,
  `decisions.jsonl`, and trial streams. Breadth V2 has proposal/trial events but
  no appended family decisions, so its 28 variants correctly remain
  `SCREENING` in `state.json`.
- The committed campaign decision artifact records the separate family reducer
  outcome: `MOVING_AVERAGE_TREND=PASS` and `PRICE_BREAKOUT=PASS`; the other five
  families are `FAIL`. The campaign explicitly states that this result did not
  append ledger family decisions. `PASS` therefore means family-level
  development eligibility, not exact-variant validation or promotion.

The earlier H002/H003 follow-up variants were not selectable: later append-only
decisions graveyarded those exact variants after the 2023 untouched-holdout
continuation. Reopening them would require a valid `CANDIDATE_REOPENED` event,
which is outside this phase and was not done.

Jigsaw evidence was treated as exploratory measurement only. JH01 remains
closed as directed and was not reopened, re-reviewed, activated, or verified.

## CANONICAL_RESEARCH_STATE

- 59 candidate variants; 1,874 completed trials; no active survivors.
- Breadth V2: 28 proposals and 1,496 trial events/receipts, with 496 blocked
  execution attempts represented in the campaign decision denominator.
- Campaign denominator: 1,992 execution units and 3,360 scientific cells.
- Development decision digest:
  `5aa5a165239a893c2f6eded9c857a3bb107d7c22a807403758fe942ed43d5adb`.
- Execution contract digest:
  `547b634bb3b10bc41fd9f3d8b197aab5b0e8f766b34c90103c615dbeb532552c`.
- Input-universe digest:
  `8fef4c02d113027630072bcbb0802e35ab31be17c835aa2ebdae4261265589fb`.

## CANDIDATE_CENSUS

The 28 Breadth V2 exact variants are four each in seven families. The only
family-level PASS results are:

| Family | Stress excess | Positive assets | Positive windows | Cost retention | Neighbour pairs | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| MOVING_AVERAGE_TREND | 0.0956979 | 16/20 | 3/3 | 0.5539 | 2 | PASS |
| PRICE_BREAKOUT | 0.2174760 | 16/20 | 3/3 | 0.8768 | 3 | PASS |

The five rejected families were not selected: TSMOM failed stress aggregate,
concentration, temporal, and cost gates; both cross-sectional families failed
breadth/aggregate gates; funding carry failed stress and breadth; volatility
targeting failed cost survival. No exact variant from those families is
reopened or re-proposed.

## THREE-CANDIDATE_SELECTION

Exactly these three existing candidate events are frozen:

1. `CANDIDATE_BREADTH_V2_MA_24_96` /
   `variant_2584eb63c90a1aa65da2e006` — moving-average trend, `fast=24,
   slow=96`, long/flat.
2. `CANDIDATE_BREADTH_V2_BREAKOUT_72` /
   `variant_ac4a45549606e2d83bad89a9` — price breakout, `lookback=72`,
   long/flat.
3. `CANDIDATE_BREADTH_V2_BREAKOUT_168` /
   `variant_057bf9fb96021b54541a31cc` — price breakout, `lookback=168`,
   long/flat.

The selection keeps two mechanisms and a fixed adjacent breakout pair. Prior
stressed variant excess was 0.195772, 0.278970, and 0.243422 respectively;
each had 46 usable and 14 blocked observations in the family receipt. These
figures justify selection only. They are not unseen confirmation.

## REJECTED-ALTERNATIVE RATIONALE

- H002/H003 historical follow-ups: exact variants are graveyarded; no reopen
  event exists.
- TSMOM, cross-sectional momentum/reversal, funding carry, and volatility
  targeting: canonical family decision is `FAIL`; selecting one would spend an
  execution slot on already-falsified family evidence without new authority.
- Other MA/breakout coordinates: retained in the registered family decision
  and local-neighbor context, but excluded to keep the execution phase at
  exactly three candidates. No “best variant” family promotion is inferred.
- Jigsaw propositions and JH01: measurement-only or explicitly closed; not
  executable strategy candidates for this sprint.

## FROZEN ECONOMIC-EVALUATION CONTRACT

The machine-readable contract is
`qnty_trading_results_sprint_v0_candidate_selection.json`.

It reuses the Breadth V2 implementation and fixes:

- the fixed 20-asset V0R1 panel and 1h bars;
- separate historical selection windows `DEV_2022`, `DEV_2024`, and
  `DEV_2025`;
- an untouched sealed-forward window from `2026-08-10T19:00:00Z` through
  `2026-11-08T19:00:00Z`, with no adjudication before 2,160 complete hours;
- causal after-close decisions and next-bar execution;
- buy-and-hold primary benchmark with cash secondary;
- baseline 10 bps fees / 0 bps slippage and stress 10 bps fees / 10 bps
  slippage, plus identical realized event-time funding in both modes;
- kernel-owned turnover, fees, slippage, funding, equity, and contribution
  accounting;
- no walk-forward refit, no new parameter search, no ex-post regime labels,
  and fail-closed gaps;
- primary net return and benchmark excess, robustness metrics, regime/window
  decomposition, and fixed kill/promote/iterate thresholds.

## LOOKAHEAD / SELECTION-BIAS ANALYSIS

Selection is outcome-informed by the committed Breadth V2 development result;
that is disclosed rather than treated as pristine evidence. The future window
is disjoint, sealed, and not mature on this date. Parameters, universe,
benchmark, cost modes, and thresholds are frozen before that window is
adjudicated. No future outcome may choose a candidate, alter a parameter, drop
an asset, change a cost, or relabel a regime. Any exact duplicate historical
trial must use explicit `REPLICATION` intent under the ledger rules.

## CHANGESET

- Added the immutable three-candidate machine-readable freeze.
- Added this selection, reconciliation, and bias-analysis report.
- Added one hostile-review record and one contract-integrity test.
- Did not modify Qnty, JH01, JFPV3, the research ledger streams, strategy code,
  evaluator code, or execution receipts.

## TESTS

The test checks that the manifest has exactly three candidates, each identity
matches the canonical proposal event, all selected variants are in PASS
families, the sealed window is disjoint and correctly timed, the cost/funding
contract is unchanged, and no ledger mutation is implied.

Observed verification:

- Focused contract test: `4 passed`.
- JSON parse: `json-ok`.
- Breadth/research-ledger doctor: `ledger ok`.
- Inherited Breadth V2 subset: `75 passed, 3 failed`; the failures assert the
  stale expected canonical trial count `378` instead of the current `1874`.
- Inherited research-factory subset: `59 passed, 12 failed`; the failures are
  stale expected counts/legacy family aliases against the current canonical
  ledger. Neither subset failure touches the new files, and
  `git status -- experiments/research` remains empty.

## HOSTILE REVIEW

One independent hostile review is recorded in
`qnty_trading_results_sprint_v0_hostile_review.md`. It found no Critical or
High findings. No targeted re-review was required.

## QNTYAGENTEVAL APPLICABILITY

The bounded repository lookup found no compatible existing `QntyAgentEval`
contract. Result: `NO_MATCH`; no evaluator was built.

## VERIFY

Bootstrap verification passed before editing:

```text
python -m qntylab.project_context       # completed; no warnings
python -m qntylab.research_ledger context # completed; 59 variants / 1874 trials
python -m qntylab.research_ledger doctor  # ledger ok
```

The final verification commands and their output are recorded in the handoff
response after the implementation, test, and review checks complete.

## VERDICT

`QNTY_TRADING_RESULTS_SPRINT_V0_THREE_CANDIDATES_FROZEN_READY_FOR_EXECUTION`

This verdict authorizes neither execution now nor any Qnty/trading mutation.
