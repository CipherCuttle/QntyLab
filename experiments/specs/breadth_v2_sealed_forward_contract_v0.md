# Breadth V2 sealed forward contract V0

`BREADTH_V2_SEALED_FORWARD_CONTRACT_V0`. This phase does not create a new
strategy, a new data platform, or a new ledger. It freezes the identity of
the sealed forward observation (`qntylab/breadth_v2_sealed.py`, already
built) and adds the one missing mechanic: a reusable, pure gate that refuses
sealed forward adjudication before the frozen horizon has elapsed. It then
binds that gate, and the frozen identity, to the already-existing Breadth V2
machinery by reference -- no other frozen semantics are duplicated or
redefined here.

## What already existed (reused exactly, not redesigned)

- `qntylab/breadth_v2_sealed.py` / `experiments/results/breadth_v2_sealed_forward_observation_v0.json`
  -- `BREADTH_V2_SEALED_FORWARD_OBSERVATION_V0`: `SEALED_T0`, the 2,160-hour
  minimum, the two advancing families, their exact registered variant IDs,
  cost modes, benchmarks, and source contracts. Unchanged by this phase.
- `qntylab/breadth_v2_input_bundle.py` (`BREADTH_V2_INPUT_BUNDLE_V0`) --
  strict, fail-closed input construction. `InputBundleBlocked` is the
  existing missingness/gap vocabulary (`BLOCKED_PRICE_COVERAGE`, etc.); the
  sealed forward window reuses this exact fail-closed behavior. No new gap
  rule is introduced.
- `qntylab/breadth_v2_runner.py` (`BREADTH_V2_RUNNER_LEDGER_INTEGRATION_V0`)
  -- the two-stage `prepare_breadth_v2_evaluation` / `record_breadth_v2_evaluation`
  API and the existing append-only `TRIAL_COMPLETED` ledger seam. The sealed
  forward evaluation, once mature, is recorded through this exact path --
  no new receipt or ledger schema is introduced.
- `qntylab/breadth_v2_execution.py` (`evaluation_input_bundle_sha256`,
  `BREADTH_V2_PORTFOLIO_KERNEL_V0`) -- the forward input bundle is identified
  the same way any registered Breadth V2 input bundle is identified: by its
  own content hash. No separate forward-specific identity scheme is created.
- The verified USD-M 1h kline materializer (`2167a3b`, already on `master`)
  -- forward price/funding source ingestion reuses this general materializer.
  No Breadth-V2-specific data platform is added.

## What this phase adds

- `qntylab.breadth_v2_sealed.SealedAdjudicationNotAuthorized` and
  `enforce_sealed_adjudication_authorized(as_of)`: a pure, additive gate.
  It raises unless the frozen minimum horizon has elapsed as of `as_of`; it
  never computes, inspects, or returns any economic quantity. It does not
  change `SEALED_T0`, the horizon, the families, the variants, or
  `contract_digest` -- it is purely additive to the existing module.
- This document, binding the above pieces together and stating the
  remaining required-content items that had no natural home in the JSON
  identity artifact.

This phase does **not** wire the gate into `breadth_v2_runner.py`. Doing so
would require registering a forward evaluation period/window as a first
execution against real, still-accumulating data -- that is prospective
execution work, out of scope for this contract-freezing phase (see
"Out of scope" in the phase brief). The gate is frozen and available for
whichever later, explicitly-scoped phase performs that wiring.

## Permitted pre-horizon materialization

Before `sealed_adjudication_authorized` is `True`, only these are permitted,
and only using already-frozen, unmodified machinery:

- ingesting and provenance-binding forward hourly price/funding source data
  (`BINANCE_USDM_PERPETUAL_1H_OHLCV`, `BINANCE_USDM_FUNDING_SETTLEMENT_MATERIALIZER_V0`);
  the general materializer already produces these hourly, independent of
  Breadth V2;
- constructing `BREADTH_V2_INPUT_BUNDLE_V0` bundles over the accumulating
  forward window and observing their `READY` / `InputBundleBlocked` status;
- computing and recording `evaluation_input_bundle_sha256` identities for
  those bundles.

None of the above computes a strategy return, a benchmark comparison, or any
PnL. `qntylab.breadth_v2_runner.record_breadth_v2_evaluation` -- the only
code path that produces a scientific outcome -- MUST NOT be called for the
sealed forward window until `enforce_sealed_adjudication_authorized` does
not raise.

## Prohibited before the horizon completes

Unchanged from the phase brief's outcome-peeking rule: no family PASS/FAIL,
no development-vs-forward comparison, no variant ranking by forward return,
no coordinate/gate/endpoint change, no asset dropping or replacement, no
cost/benchmark redesign. `SealedAdjudicationNotAuthorized` is the mechanical
backstop for the first of these (nothing can be recorded as complete before
maturity); the rest remain process discipline, as they were before this
phase.

## No-retuning rule

`ELIGIBLE_VARIANT_IDS` in `qntylab/breadth_v2_sealed.py` are exactly the
already-registered Breadth V2 candidate IDs for the two PASS families (four
each, all four -- not a best-of selection). Nothing in this phase, or any
future accumulation code that reuses this contract, may add, remove, or
substitute a variant ID, change a parameter, or introduce a new coordinate.

## Advancement / blocked states

`observation_status` (`SEALED_OBSERVATION_ACTIVE` / `SEALED_OBSERVATION_MATURE`,
per `build_contract`) is the frozen vocabulary; `SEALED_OBSERVATION_ACTIVE`
is this contract's `SEALED_FORWARD_ACCUMULATING` state from the phase brief
-- same state, no renaming of already-frozen code. There is no
`SEALED_OBSERVATION_BLOCKED` contract state: a blocked *input bundle* is
already representable via `InputBundleBlocked` from
`BREADTH_V2_INPUT_BUNDLE_V0` without needing a new top-level contract state,
and a genuinely new class of blocker discovered during real accumulation is
a later, narrowly-scoped decision, not one this phase can anticipate.

## Relationship to prospective shadow

This contract governs sealed forward *observation* only. It grants no
authority to begin prospective shadow execution, paper trading, live
trading, router integration, or any Qnty mutation. Reaching
`SEALED_OBSERVATION_MATURE` and a subsequent sealed adjudication is a
prerequisite for a later, separately-scoped prospective shadow phase; it is
not that phase and does not authorize it.

## No Qnty / trading authority

This phase, and the contract it freezes, grant no Qnty integration
authority, no router authority, and no trading authority of any kind
(paper or live). `qntylab.breadth_v2_sealed` and this document make no
calls into, and reference no interfaces of, any Qnty or execution-venue
system.

## Synthetic-only / no real accumulation performed by this phase

This phase adds no scheduler, no cron, and no live data pull. It freezes
the gate and the reuse contract only. Real forward accumulation -- actually
calling the existing materializer and input-bundle machinery against live
data over the next 90 days -- is deliberately left to whatever process
already runs the general 1h kline materializer; that process needs no
change from this phase to keep accumulating.
