# Pons S0 Model Screen V1 — QntyLab Contract

## Status

**EXPLORATORY ONLY / EDGE_UNPROVEN / NO PROMOTION AUTHORITY**

This is PR-B of the compressed S0 plan.

SENTRY remains the point-in-time evidence authority. QntyLab consumes the
content-addressed S0 export and asks one narrow question:

> Do the frozen pre-decision features contain out-of-sample information about
> the already-established canonical 24h executable outcome?

This phase cannot trade, sign, broadcast, alter SENTRY policy, or promote a
model.

## Frozen denominator

Exactly four variants are registered:

1. `PONS_S0_C0` — BUY_EVERY_EXECUTABLE_CONTROL_R1
2. `PONS_S0_C1` — FAST_VET_R1_CAPACITY_GATE
3. `PONS_S0_M1_LOGISTIC` — fixed L2 logistic regression
4. `PONS_S0_M2_HIST_GRADIENT_BOOSTING` — fixed histogram gradient boosting

There is no hyperparameter search and no automatic winner selection.

The denominator is frozen in:

`experiments/specs/pons_s0_model_screen_v1.json`

## Target

Primary development target:

`24h / 86,400,000 ms`

Model universe:

`C0_MECHANICALLY_ADMISSIBLE_WITH_RESOLVED_24H_OUTCOME`

A launch whose frozen `BUY_EVERY_EXECUTABLE_CONTROL_R1` action is
`WOULD_SKIP` is retained in coverage diagnostics but is **not** a model
training or test row. M1/M2 may therefore select only among launches that have
already passed the minimum frozen bidirectional mechanical gate. A learned
model cannot override mechanical admissibility.

This reuses SENTRY's existing canonical 24h creator/outcome evaluation rather
than opening a horizon-selection search.

Positive class:

`NORMAL_WIN`

Negative classes:

- `NORMAL_LOSS`
- `CATASTROPHIC_LOSS`
- `EXIT_FAILURE`
- `LIQUIDITY_COLLAPSE`

Missing, UNVERIFIED or unknown classifications remain unresolved and lower
coverage. They are not coerced into either class.

## Input boundary

QntyLab accepts only:

- `PONS_S0_EXPORT_MANIFEST_V1`
- `PONS_S0_FEATURE_PACKET_V1`
- `PONS_S0_OUTCOME_PACKET_V1`

The loader revalidates:

- raw feature/outcome stream SHA-256;
- manifest digest and manifest identity;
- every feature/outcome packet evidence digest;
- packet identity;
- stream packet-digest order;
- chain/protocol/mode boundaries;
- outcome-to-feature bindings;
- `INDEPENDENT_PROBE_CAPACITY_NOT_SEQUENTIAL`;
- shadow execution-persona parity remains explicitly
  `SHADOW_RECIPIENT_BOUND_LIVE_WALLET_UNVERIFIED`.

Future outcome packets are never feature inputs.

## Feature surface

The model receives only the fixed numeric feature vector declared in
`FEATURE_NAMES`.

It deliberately excludes:

- token address;
- creator address as a categorical ID;
- token name/symbol;
- policy decision outputs;
- target outcome data;
- social/web data;
- any model-generated feature.

The initial surface is mechanical + point-in-time creator history:

- decision delay;
- creator-history counts and adverse rate;
- fee / creator-tax / snipe-tax terms;
- tracked-quote / graduation ratio;
- sellable / token-reserve ratio;
- quote-reserve scale;
- contiguous probe-capacity rung count;
- same-state reverse recovery at each frozen notional rung.

## Chronological evaluation

Random cross-validation is forbidden.

The runner uses expanding chronological folds with a harder label-availability
condition:

> every training outcome must satisfy
> `training.outcome.observedBlock < first_test.feature.decisionBlock`

This is a chain-block embargo. It does not compare SENTRY's local capture clock
against outcome block timestamps.

Frozen defaults:

- minimum embargoed training rows: 30
- test rows per fold: 10
- maximum folds: 3
- decision threshold: 0.5

If no valid fold exists, the screen fails closed as
`INSUFFICIENT_EMBARGOED_CHRONOLOGICAL_FOLDS`.

## Models

### M1 — logistic

Fixed:

- median imputation + missing indicators;
- standard scaling;
- L2 logistic regression;
- C = 1.0;
- lbfgs;
- max_iter = 1000.

### M2 — histogram gradient boosting

Fixed:

- median imputation;
- learning_rate = 0.1;
- max_iter = 100;
- max_leaf_nodes = 15;
- min_samples_leaf = 5;
- l2_regularization = 1.0;
- random_state = 0.

Both report Brier score, log loss, accuracy, balanced accuracy and ROC AUC when
defined.

Each fold also emits a **no-feature prevalence probability baseline** fitted on
that fold's embargoed training labels only. M1/M2 report Brier/log-loss
improvement versus that baseline. This is diagnostic and does not create a fifth
registered strategy variant.

These are diagnostics, not promotion gates.

## Economic diagnostics

All four variants are evaluated on the same union of out-of-sample test rows.

Rejected opportunities retain the original $1 as cash.

The receipt reports:

- trade retention;
- gross terminal capital;
- gross delta versus C0;
- adverse accepted count;
- positive-excess capture;
- verified net-cost coverage;
- net terminal capital only when every accepted trade has complete full-path
  cost evidence.

A missing net cost never silently becomes zero cost.

## Ledger reuse

PR-B does not create a new experiment database.

The runner registers the four frozen variants through the existing QntyLab
append-only candidate stream and records each completed screen through the
existing trial stream.

The committed screen spec carries the historical `preregistered_at_utc`.
Candidate ledger events do **not** copy that timestamp. They use the actual
append time from the ledger clock, so an event appended after outcomes exist
cannot masquerade as having been recorded at preregistration time.

Candidate registration occurs before the runner reads feature/outcome packet
bytes. The denominator therefore exists in the append-only trial ledger before
the model sees target data.

For irregular Pons launch events, the existing generic identity fields are used
with explicit semantics:

- input kind: `SENTRY_PONS_S0_EXPORT_V1`
- symbol: `ROBINHOOD_PONS_S0`
- bar interval: `IRREGULAR_LAUNCH_EVENTS`
- gap policy: `OUTCOME_OBSERVED_BLOCK_LT_TEST_DECISION_BLOCK`
- fee/slippage ledger identity fields: zero / not-applicable because executable
  economics are already supplied by SENTRY outcome evidence.

The full S0 metrics remain in the bound run receipt.

## No model artifact yet

A successful exploratory screen emits:

`EXPLORATORY_SCREEN_COMPLETE_NO_PROMOTION`

and:

`candidate_artifact = null`

No score ordering automatically chooses M1 or M2.

Freezing a strategy artifact is a later S0B decision and requires a separate
prospective contract.

## Synthetic tests are not evidence

`tests/test_pons_s0_screen_v1.py` uses deterministic synthetic packets solely
to verify implementation invariants.

Its model metrics are not scientific evidence, are not appended to the canonical
repository research ledger, and cannot support promotion.

## Verification

```bash
python -m pip install -r requirements-pons-s0-v1.txt pytest==9.1.1
PYTHONPATH=. python -m pytest -q tests/test_pons_s0_screen_v1.py
PYTHONPATH=. python -m qntylab.research_ledger doctor
```

## Source-origin limitation

V1 validates SENTRY packet/manifest **content integrity** and every nested
content-addressed identity it consumes. The current PR-A manifest does not carry
a cryptographically bound SENTRY repository commit or CI artifact origin.

Therefore a real scientific S0 run must preserve an external origin receipt for
the exact SENTRY materialization (repository/ref + artifact/file digest). V1
does not interpret self-consistent packet bytes as proof that they were produced
by an authorized SENTRY build.

This limitation blocks later strategy-artifact promotion until the real input
cohort has an exact origin receipt. It does not affect the synthetic
implementation qualification in this PR.
