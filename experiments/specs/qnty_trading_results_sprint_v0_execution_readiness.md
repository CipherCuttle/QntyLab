# QNTY_TRADING_RESULTS_SPRINT_V0_EXECUTION_READINESS

Status: `FROZEN_FOR_POST_MATURITY_ADJUDICATION_ONLY`.

This phase prepares the deterministic execution boundary for the three
candidates selected in the canonical selection artifact. It does not access,
compute, summarize, rank, or record sealed-forward economic outcomes.

## PLAN

1. Reconcile canonical master, project context, research ledger, and the
   selection freeze.
2. Audit the existing Breadth V2 input, runner, kernel, path, and maturity
   machinery.
3. Add only the missing exact three-candidate readiness/reduction seam.
4. Test with synthetic fixtures, conduct one hostile review, repair only
   Critical/High issues, freeze source identities, verify closure, and stop.

## RECONCILIATION

Canonical remote master is `e27bb15caac8d66530530690b9aa423e6e4fd641`, the
merged PR #107 commit. The local tree was clean and identical to that master
tree after fetching the missing object. The selection artifact remains the
authority for candidates and contract. Its byte SHA-256 is
`91c3ccd147b6fe5e19e0851834ea601dc90acf0d60f5c942aca13de4d37d5e11`.

The truthful Breadth V2 interpretation is unchanged:

- generated ledger variants remain `SCREENING` because the development
  campaign did not append family decision events;
- the separate committed development decision artifact records family-level
  `PASS` for `MOVING_AVERAGE_TREND` and `PRICE_BREAKOUT`;
- that family decision is selection evidence, not exact-variant validation or
  unseen forward confirmation.

No JH01, JFPV3, Qnty, source repository, paper/live, or capital state was
opened or mutated.

## CANONICAL_RESEARCH_STATE

The required project-context and research-ledger bootstrap commands were run
against canonical master:

- `python -m qntylab.project_context`: clean repository, ADR-0005/0006
  authority map, exploratory research state, no conflicting active project;
- `python -m qntylab.research_ledger context`: 59 variants, 1,874 trials,
  no active survivors, and the expected historical warnings/graveyards;
- `python -m qntylab.research_ledger doctor`: `ledger ok`.

The readiness implementation consumes no ledger events and appends none.

## CANDIDATE_CENSUS

The exact frozen set is:

| Candidate | Variant | Mechanism | Prior selection evidence |
|---|---|---|---|
| `CANDIDATE_BREADTH_V2_MA_24_96` | `variant_2584eb63c90a1aa65da2e006` | delayed smoothed trend participation | family stress excess `0.09569786257049016`; variant stress excess `0.19577230236403648`; variant stress net `-0.10140228714858432` |
| `CANDIDATE_BREADTH_V2_BREAKOUT_72` | `variant_ac4a45549606e2d83bad89a9` | event-triggered directional persistence | family stress excess `0.21747593957349115`; variant stress excess `0.2789698277495456`; variant stress net `-0.01820476176307521` |
| `CANDIDATE_BREADTH_V2_BREAKOUT_168` | `variant_057bf9fb96021b54541a31cc` | event-triggered directional persistence | family stress excess `0.21747593957349115`; variant stress excess `0.2434221289855831`; variant stress net `-0.053752460527037735` |

All three use the fixed 20-symbol panel, hourly bars, exact registered
parameters, and the existing single-asset runner path.

## THREE-CANDIDATE_SELECTION

Selection is inherited unchanged from the canonical selection artifact. It
maximizes information gain using two surviving mechanisms, preserves an
adjacent breakout pair for preregistered local sensitivity context, and does
not add coordinates, retune, or search.

## REJECTED-ALTERNATIVE RATIONALE

The five non-surviving families were not reopened: the canonical family
decision artifact records them as failed, and the ledger correctly retains
their generated variants as screening/graveyard history rather than silently
promoting them. Other variants within the two surviving families were not
added because the selection freeze already fixed the three-candidate count and
the subsequent contract forbids forward-outcome-driven substitution. Funding
carry and cross-sectional alternatives were additionally excluded from this
execution seam because they are not among the frozen exact candidates.

## FROZEN ECONOMIC-EVALUATION CONTRACT

The implementation consumes the selection artifact contract verbatim:

- fixed 20-symbol universe from `BREADTH_V2_DEV_INPUT_UNIVERSE_V0R1`;
- one-hour bars; after-close decision at `t`, target applied to `t -> t+1`;
- no walk-forward refit, tuning, interpolation, or forward fill;
- B&H primary benchmark with cash secondary policy;
- baseline 10 bps fee / 0 bps slippage and stress 10 bps fee / 10 bps
  slippage;
- realized event-time funding against the prior position, with unsupported,
  missing, or incomplete funding fail-closed;
- kernel-owned pre-cost-equity one-way turnover, fees, slippage, funding,
  price PnL, and terminal liquidation;
- calendar-window regime decomposition only;
- fixed parameter-neighbor IDs are retained as selection context only; no
  neighbor execution or new search is authorized.

The forward plan is 3 candidates × 20 assets × 2 cost modes = 120 execution
cells per the existing machinery. Each candidate receives its own causal
warmup/input-bundle identity because the three exact parameters require
different history lengths.

The output preserves candidate, asset, forward-window, and cost-mode rows,
including net/gross return, benchmark excess, turnover, trade count,
exposure, fee, slippage, funding, price PnL, drawdown, and the aggregate
volatility/sharpe-like diagnostics produced from the same kernel paths.

Hard gates are integrity, positive stressed aggregate excess, non-negative
forward stressed excess, at least 10 positive assets, maximum positive-asset
share no greater than 35%, and cost retention of at least 50% of positive
baseline advantage. Complete data emits `PROMOTE` or `KILL`; `ITERATE` is
reserved for a separately preregistered future contract and is not inferred
from incomplete evidence here.

## LOOKAHEAD / SELECTION-BIAS ANALYSIS

The three variants were selected with visible historical development results.
Those results are copied into each future record as explicitly labeled
`selection_evidence_context`; they are not recomputed and never count as
unseen confirmation. The forward window is disjoint from the selection
windows and is blocked by the committed clock gate until
`2026-11-08T19:00:00Z` with 2,160 complete hours. Parameters, universe,
benchmark, costs, funding treatment, and regime labels cannot change after
forward outcomes are available. The local-neighbor list is context only; no
post-outcome neighbor comparison is performed by this phase.

## CHANGESET

- Added `qntylab/qnty_trading_results_sprint_v0_execution.py`.
- Added the frozen readiness manifest JSON with candidate-freeze digest,
  implementation source hashes, input/output schema, exact plan, and
  commands.
- Added synthetic-only tests for identity, maturity, coverage, reducer gates,
  non-finite metrics, and no-network/no-ledger-append behavior.
- Existing Breadth V2 runner, kernel, sealed contract, ledger, JH01, JFPV3,
  and Qnty files were not modified.

## TESTS

Focused readiness tests are synthetic and never load real forward outcomes.
They cover exact 120-cell plan construction, universe/2160-hour identity,
missing-source candidate KILL preservation, cost/breadth/concentration gates,
non-finite integrity KILL, pre-maturity access ordering, and forbidden
network/ledger-append paths.

## HOSTILE REVIEW

One independent hostile review pass was completed against the seam:

| Check | Result |
|---|---|
| maturity gate precedes forward bundle access | Pass |
| exact freeze digest and three IDs enforced | Pass |
| altered universe, boundary grid, bundle digest, or warmup rejected | Pass |
| missing source preserved as affected-candidate KILL | Pass |
| 20 assets × 2 costs denominator retained | Pass |
| non-finite/funding/input failures fail closed | Pass |
| no network, Qnty mutation, or ledger append path | Pass |
| existing runner/kernel reused | Pass |
| no QntyAgentEval construction | Pass |

No Critical or High finding remained after review; no targeted re-review was
required.

## QNTYAGENTEVAL_APPLICABILITY

The canonical selection-phase lookup remains `NO_MATCH`. Per instruction, no
new evaluator was built. The later execution phase must use this readiness
seam plus the existing Breadth V2 runner/kernel contract.

## VERIFY

Before any future outcome access, verify the readiness manifest’s source hashes
and candidate-freeze SHA on the immutable readiness commit. At runtime, call
`enforce_sealed_adjudication_authorized(as_of)` first, then invoke the exact
`adjudicate` entry point. This phase performed no adjudication and wrote no
economic result records.

## VERDICT

`QNTY_TRADING_RESULTS_SPRINT_V0_EXECUTION_READINESS_FROZEN_READY_FOR_POST_MATURITY_ADJUDICATION`

This phase is closed. Do not execute, summarize, or rank the three candidates
until the frozen maturity boundary.
