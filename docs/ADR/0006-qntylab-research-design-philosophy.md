# ADR 0006: QntyLab Research Design Philosophy

**Status:** `CURRENT_GLOBAL_RESEARCH_DESIGN_PHILOSOPHY_NO_IMPLEMENTATION_AUTHORIZATION`

## Purpose

This ADR records the durable intellectual design philosophy for how QntyLab should discover, test, preserve, and hand off market knowledge. It complements ADR 0005's north-star architecture. It does not replace project-specific preregistrations, execution contracts, evidence records, or authority gates.

The core objective is not to imitate any individual investor or firm. It is to combine the strongest transferable lessons from systematic quantitative research, statistics, information theory, sequential prediction, robust inference, and scientific self-criticism into one coherent research culture.

The compact maxim is:

```text
FAST TO FALSIFY
FAST TO SHADOW
SLOW TO CLAIM
SLOWER TO CAPITAL
```

## Intellectual synthesis

### Simons — systematic curiosity and many small truths

Prefer unusual, structurally motivated problems over crowded indicator families. Seek mathematically specified predictors and modest repeatable relationships rather than one grand theory of markets. The research program persists; a failed frozen hypothesis does not.

QntyLab therefore favors accumulating many small falsifiable Jigsaw pieces over searching for a single "master strategy" or monolithic AI trading brain.

### Tukey — exploration and confirmation are different activities

Exploration is allowed and valuable when it is labeled as exploration. Once an exploratory idea is promoted into a confirmatory proposition, the feature, outcome, timing, universe, model, inference, and failure conditions must be frozen before confirmatory outcome access.

```text
EXPLORE -> FORMULATE -> FREEZE -> TEST
```

Never convert iterative exploratory tuning into apparently pristine confirmatory evidence.

### Shannon — seek incremental information, not merely correlation

A candidate becomes more interesting when it adds information beyond the simplest already-known state or benchmark.

Whenever scientifically sensible, ask:

```text
Does X contain information about Y
beyond the simplest existing state B?
```

A raw correlation may still be a valid bounded Jigsaw piece, but incremental-information tests are preferred when the relevant baseline is already known.

### Feynman — actively disclose how the result could be wrong

Scientific integrity requires recording counterevidence, alternative explanations, fragile assumptions, failed variants, relevant exclusions, and the exact limits of every result.

A positive result should always preserve:

- what could invalidate it;
- what alternative mechanisms remain possible;
- what search choices were considered;
- where the relationship fails or is unsupported;
- what the evidence does **not** establish.

Hostile review is a formal expression of this principle.

### Huber — assume the model is slightly wrong

Market models are approximations. Robustness work should test whether a supported conclusion collapses under small, scientifically legitimate perturbations or a small number of influential observations.

Robustness analysis may weaken confidence in a primary result. It must never rescue a failed frozen primary test.

### Mandelbrot — tails and regime instability are part of the system

Extreme events, heavy tails, volatility clustering, structural breaks, and regime dependence are not nuisance exceptions to be hidden by averages. Later economic evaluation should identify whether apparent value is broad-based or concentrated in rare observations, crashes, liquidation episodes, or one regime.

A tail-dependent effect can be real, but its dependence must be explicit.

### Dawid — prospective evidence requires prediction before outcome

The strongest fast-lane evidence is prequential: the exact prediction artifact exists before the corresponding outcome can be known.

A prospective observation should bind at minimum:

```text
prediction_id
contract_digest
feature/model identity
forecast_origin
prediction
prediction_timestamp
outcome_available_after
```

Prospective evidence must not be reconstructed retrospectively as "what the model would have predicted."

### Wald — future sequential stopping must be designed, not improvised

Fixed observation budgets are the default while the fast lane is young. If later generations adopt sequential stopping, support/failure thresholds must be preregistered using valid sequential decision methods. Informal optional stopping based on a live score is prohibited.

### Breiman — explanation, prediction, and decision are different roles

Keep the epistemic roles separate:

```text
JIGSAW
What bounded market relationships appear supported?

FORECASTER
What predicts a narrow future outcome out of sample?

ROUTER
Given validated state and sleeves, what action has highest expected utility?
```

Jigsaw should remain skeptical and evidence-linked. Downstream predictive or decision systems may generalize, but their usefulness cannot retroactively strengthen Jigsaw evidence.

### Thorp and Kelly — edge before economics, economics before size

Do not translate statistical significance directly into capital.

The intended order is:

```text
PREDICTIVE / STATE EVIDENCE
        ->
INCREMENTAL FORECAST VALUE
        ->
COST-AWARE ECONOMIC EDGE
        ->
PROSPECTIVE SHADOW / PAPER EVIDENCE
        ->
RISK ESTIMATION
        ->
ONLY THEN POSITION SIZING / CAPITAL AUTHORITY
```

Kelly-style sizing, or any other capital-allocation rule, belongs only after positive expectation and uncertainty are separately established. It has no role in granting scientific support to an upstream Jigsaw piece.

## Global research laws

### Law 1 — Prefer structural novelty over indicator proliferation

Prefer crypto-native or market-structural mechanisms — such as perpetual-futures anchoring, funding/premium dynamics, order flow, liquidation/deleveraging state, time-synchronized activity, dispersion, breadth, or event microstructure — over broad sweeps of generic technical indicators.

Novelty is not evidence. It is a candidate-selection preference before outcome testing.

### Law 2 — Preserve the denominator

Every bounded campaign must preserve the set of candidates, variants, horizons, benchmarks, transformations, and meaningful alternatives actually considered before freeze. Negative, inconclusive, blocked, and deferred candidates remain part of research memory.

A winning result may never erase the search that produced it.

### Law 3 — Discovery may explore; confirmation freezes

Exploration may generate hypotheses. Confirmation must freeze the claim before confirmatory outcome access. A new idea discovered after freeze belongs to a new immutable generation or project, not a rescue amendment.

### Law 4 — Prefer incremental-information questions

When a simple known baseline already explains part of the outcome, prefer testing whether a new candidate adds information beyond that baseline rather than rediscovering the baseline through a correlated proxy.

### Law 5 — Prospective means prediction-first

A valid prospective observation requires a persisted prediction before outcome availability. Machine-health monitoring may be live; scientific success should not be repeatedly surfaced in a way that encourages optional stopping or adaptive redesign.

### Law 6 — Failure is information

A clean negative result is a successful research outcome. The program should move forward rather than repeatedly modifying a failed frozen proposition until it passes.

```text
PERSIST IN THE PROGRAM.
DO NOT PERSIST IN RESCUING A FAILED FROZEN HYPOTHESIS.
```

### Law 7 — Evidence does not self-escalate

Preserve ADR 0005's global invariant:

```text
Evidence supporting proposition X
must not silently manufacture
a stronger or different proposition Y.
```

In particular:

```text
association != causality
association != incremental forecast value
forecast value != economic edge
economic edge != shadow authority
shadow success != live-capital authority
```

### Law 8 — Fast lane and slow lane coexist

QntyLab should not move at the speed of its slowest hypothesis.

**Slow lane:** strong confirmatory projects, long prospective windows, replication, or high-authority claims where the question genuinely requires them.

**Fast lane:** bounded mechanism-seeded discovery, aggressive historical falsification, then immutable zero-capital prospective observation when justified.

Fast-lane historical success may grant only eligibility for separately authorized prospective observation. It does not weaken the evidence hierarchy.

### Law 9 — Separate research truth from execution truth

QntyLab owns exploratory research, evidence scope, and Jigsaw knowledge. Qnty remains a separate downstream system for replay/accounting/execution realism and paper/shadow/live authority when independently authorized.

Cross-repository handoff must be explicit and immutable. No shared mutable control plane is implied by this philosophy.

### Law 10 — Simple first, complexity earned

Start with the smallest specification capable of falsifying the proposition. Machine learning, ensembles, adaptive routers, large feature searches, regime models, and sequential policies must earn their complexity through a distinct information-bearing question.

Do not use complexity to hide a weak proposition.

## Fast prospective lane

The preferred conceptual flow is:

```text
literature / mechanism / exploration
        ->
bounded candidate census
        ->
preregistration
        ->
first-party input qualification
        ->
one-shot historical falsification
        ->
SHADOW_OBSERVATION_ELIGIBLE only if earned
        ->
separate downstream authorization
        ->
prediction-first zero-capital prospective observation
        ->
prospective evidence incorporation
```

The system should be **fast to produce new information**, not fast to manufacture confidence.

## Anti-patterns

This philosophy rejects:

- brute-force indicator zoos whose denominator is not preserved;
- parameter, horizon, universe, subgroup, or transform rescues after seeing outcomes;
- ranking a large search and treating the best member as if it were individually preregistered;
- retrospective reconstruction of prospective predictions;
- using robustness analysis to rescue a failed primary result;
- promoting a statistically supported predictor directly into a trading strategy;
- treating shadow or paper success as proof of live profitability;
- building a monolithic "AI trading brain" that collapses Jigsaw, forecasting, routing, accounting, and authority into one model;
- copying folklore about legendary investors as if private implementation details were known facts.

## Relationship to ADR 0005

ADR 0005 remains the authoritative global north-star market-intelligence architecture. This ADR is a companion research-design philosophy describing preferred epistemic and methodological behavior inside that architecture.

If a project-specific frozen contract conflicts with a preference in this ADR, the project-specific contract governs that project unless a later explicit governance action changes it. This philosophy never grants authority to mutate a frozen historical artifact.

## Non-goals and authority

This ADR authorizes **no**:

- market-data acquisition;
- scientific execution;
- historical backtest;
- Jigsaw mutation;
- State Snapshot implementation;
- Forecaster or Router implementation;
- Qnty mutation or integration;
- paper or shadow deployment;
- live trading;
- external effects;
- strategy promotion;
- capital allocation.

It is a durable design philosophy only. All concrete work still requires the applicable Git-backed project authority, preregistration, execution contract, and repository-specific gates.

## Intellectual lineage

The philosophy is informed by publicly documented work and ideas associated with Jim Simons (systematic model-driven discovery and research culture), John Tukey (exploratory data analysis), Claude Shannon (information theory), Richard Feynman (scientific integrity), Peter Huber (robust statistics), Benoit Mandelbrot (heavy tails in price changes), A. Philip Dawid (prequential probability and statistics), Abraham Wald (sequential analysis), Leo Breiman (the two cultures of statistical modeling), Edward O. Thorp (mathematical edge and risk), and John L. Kelly Jr. (information and capital growth).

These names identify intellectual influences, not authorities whose views automatically determine any QntyLab design decision.
