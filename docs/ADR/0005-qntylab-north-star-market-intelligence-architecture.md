# ADR 0005: QntyLab North-Star Market-Intelligence Architecture

**Status:** `CURRENT_GLOBAL_ARCHITECTURE_NORTH_STAR_NO_IMPLEMENTATION_AUTHORIZATION`

## Context

QntyLab is an evidence-producing exploratory research laboratory. It accumulates
bounded, falsifiable, provenance-linked knowledge about market behavior. It is
not an AI trading bot, a monolithic trading system, or an authority for trading
or external effects.

This ADR establishes the current global architecture so that repository state
can be interpreted without relying on older, broader wording. It is a
north-star architecture, not authorization to implement every layer described
here. Current implementation status must be established independently from Git
and from the contract governing each project.

The intended direction is:

```text
QntyLab
→ research experiments
→ Jigsaw durable market knowledge
→ frozen market observers / State Snapshot
→ Reactive Jigsaw
→ Forecaster
→ Router
→ strategy sleeve or ABSTAIN / FLAT
→ immutable promotion artifact
→ Qnty
```

## Decision

### Jigsaw is durable, skeptical evidence

Jigsaw accumulates small falsifiable evidence pieces rather than reducing
research knowledge to `PASS`, `FAIL`, `SURVIVOR`, or `GRAVEYARD`. Pieces may
describe a signal effect, condition dependence, failure mode, cost boundary,
regime effect, event response, strategy interaction, or abstention condition.
An unsuccessful experiment may still produce useful bounded evidence. A Jigsaw
piece states only what its evidence earned.

### Evidence Non-Escalation

The global claim-scope invariant is:

```text
Evidence supporting proposition X
must not silently manufacture
a stronger or different proposition Y.
```

In particular, predictive association is not causality; positive historical
contrast is not a trading edge; a Jigsaw evidence piece is not Router feature
authority; a Router feature is not strategy promotion; and strategy promotion
is not Qnty execution authority. Evidence may move downstream only through
explicit scope and authority.

### State Snapshot and Reactive Jigsaw

Validated and frozen Jigsaw pieces may later contribute to a frozen market-state
representation. Reactive Jigsaw may activate already validated pieces and may
use state novelty or change detection. It does not invent patterns live and
should prefer `ABSTAIN` when the current state is unsupported or novel. These
are intended downstream boundaries; this ADR authorizes no implementation.

### Forecaster and Router are separate downstream roles

The Forecaster estimates narrow conditional outcomes. The Router estimates
expected utility and chooses among already-tested strategy sleeves or
`ABSTAIN` / `FLAT`. The Router may generalize for its decision problem, while
Jigsaw remains skeptical. Router authority never flows backward to rewrite
Jigsaw evidence, and Router usefulness does not turn weak evidence into
stronger scientific evidence.

### QntyLab and Qnty remain separate

QntyLab may own exploratory responsibilities such as hypothesis registration,
deterministic experiment and trial identity, evidence and provenance
collection, Jigsaw accumulation, market-state research, candidate generation,
bounded follow-ups, and immutable promotion artifacts.

Qnty remains separate and may own canonical replay and accounting, execution
realism, protected evidence where applicable, downstream promotion acceptance,
paper/shadow/live authority, and actual trading or external-effect authority
when separately authorized. The repositories must not be merged conceptually
or technically. No shared mutable control plane is authorized. Cross-repository
handoff must be explicit and immutable.

If architecture references `QntyPolicyGate`, it remains a separate authority
boundary for external effects. This ADR does not absorb it or grant any new
policy or execution authority.

### Promotion boundary and bounded evaluation

Any transition from exploratory evidence toward downstream use requires an
explicit immutable artifact or contract. A QntyLab result does not
automatically become strategy, Router, Qnty, paper, shadow, or live authority.

QntyLab remains exploratory and non-authoritative. An individual preregistered
research design may contain a sealed holdout, temporal outer evaluation,
prospective shadow, or similar evidence boundary. That boundary belongs only to
that research contract and does not itself grant Qnty authority; no holdout is
required for every QntyLab experiment.

## Relationship to ADR 0001

ADR 0001 remains authoritative for the `QntyLab Probationary Prospective
Observatory / DVOL V0` design it governs, including its project-specific source,
timing, retention, and authority constraints. It is not deleted or rewritten.

To the extent ADR 0001 contains broader statements about QntyLab's global role
that conflict with this ADR, this ADR supersedes those broader global-role
statements. Project-specific restrictions in ADR 0001 remain intact.

## Non-goals and current status

This ADR does not implement Jigsaw, State Snapshot, Reactive Jigsaw, a
Forecaster, a Router, a strategy sleeve, a promotion pipeline, or Qnty
integration. It does not authorize historical execution, paper or live
activity, trading, external effects, or a shared control plane. It does not
replace project-specific preregistrations, execution contracts, research
results, or other immutable historical artifacts.

The Funding Pressure → Future RV24 experiment remains a bounded exploratory
predictive proposition. Even a positive `HIGH_MINUS_LOW_MEAN_RV24` result does
not by itself establish causality, a trading edge, strategy-family authority,
Router feature authority, or Qnty authority.

