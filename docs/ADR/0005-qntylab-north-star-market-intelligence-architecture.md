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

The primary objective is not to maximize governance, artifact count, predictive
fit, or architectural sophistication. It is to maximize the rate at which
QntyLab can discover and falsify credible economic edge while preserving enough
research integrity that survivors can later earn much stronger confirmation.

The intended direction is:

```text
QntyLab
→ mechanism-first hypotheses
→ cheap, high-throughput discovery and falsification
→ trial ledger + Jigsaw skeptical evidence
→ net economic-utility and robustness tests
→ ECONOMIC SURVIVOR GATE
→ sealed / prospective confirmation for earned survivors
→ immutable promotion candidate
→ optional State Snapshot / Forecaster / Router composition
→ Qnty
```

The architecture therefore has two epistemic speeds: fast discovery and brutal
confirmation. Confirmation-grade rigor is expensive and should be concentrated
on candidates that first earn it rather than imposed indiscriminately on the
entire search process.

## Decision

### Economic edge is the target claim

A predictive statistic is not the terminal research objective. A candidate
becomes economically interesting only if information available at decision time
can improve a decision after realistic costs, funding, spread/slippage,
turnover, risk, and other relevant implementation frictions.

Accordingly:

```text
prediction != edge
statistical support != tradeability
tradeability != Qnty authority
```

Forecasting, volatility estimation, regime classification, or other predictive
work may be valuable as decision inputs, but must not be described as edge until
incremental net economic utility has been demonstrated under the relevant
contract.

### Two-speed research architecture

QntyLab separates exploratory discovery from confirmatory evidence production.

The **Discovery Lane** is optimized for information throughput. It may use
point-in-time historical data, broad but bounded candidate families, cheap
falsification, walk-forward evaluation, perturbation tests, simple benchmark
comparisons, and automatically recorded trial identities. It may iterate
quickly. Discovery results are exploratory evidence only and cannot directly
create promotion, Router, Qnty, paper, shadow, live, or capital authority.

The **Confirmation Lane** is reserved for candidates that survive an explicit
survivor gate. It may use preregistration, frozen implementations, sealed outer
temporal evaluation, prospective collection, immutable persistence, hostile
review, external evaluation where applicable, and other expensive controls.
Confirmation must remain hard to game, but its cost must be paid only after a
candidate has demonstrated enough economic promise to justify it.

Existing long-horizon prospective experiments remain valid evidence programs.
They must not, however, become a global bottleneck that prevents parallel cheap
falsification and candidate discovery.

### Mechanism-first search and simple opponents

Candidate generation should prefer hypotheses with an identifiable economic
mechanism, constraint, transfer, behavioral source, institutional feature, or
other reason that an effect could persist. Mechanism quality changes the prior;
it does not substitute for evidence.

Every complex candidate must face the simplest credible opponent first. Examples
include naive carry or funding rules, simple trend or momentum rules, static
ensembles, equal-weight alternatives, and `FLAT` / `ABSTAIN` where appropriate.
Additional complexity is justified only by reproducible incremental out-of-
sample economic utility.

### Search itself is part of the evidence problem

Human, scripted, and LLM-assisted candidate generation all create researcher
degrees of freedom. Testing many lookbacks, universes, modifiers, interaction
rules, prompts, generated hypotheses, or strategy variants constitutes search
even when the final survivor is later preregistered cleanly.

QntyLab must therefore preserve family-level trial history and treat broad
candidate search as a multiple-comparison / overfitting risk. A clean final
experiment must not erase the exploratory path that selected it.

### Jigsaw is durable, skeptical evidence

Jigsaw accumulates small falsifiable evidence pieces rather than reducing
research knowledge to `PASS`, `FAIL`, `SURVIVOR`, or `GRAVEYARD`. Pieces may
describe a signal effect, condition dependence, failure mode, cost boundary,
regime effect, event response, strategy interaction, or abstention condition.
An unsuccessful experiment may still produce useful bounded evidence. A Jigsaw
piece states only what its evidence earned.

During the discovery-heavy stage of QntyLab, Jigsaw is primarily a durable
knowledge store and evidence memory, not an automatic decision brain. Jigsaw
composition must not manufacture strength that individual evidence pieces did
not earn.

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

### Survivor gate and economic robustness

A candidate should not receive expensive confirmation or substantial downstream
infrastructure merely because it has an attractive in-sample statistic or a
nominally significant historical test.

Before confirmation-grade investment, the candidate should survive the bounded
checks relevant to its family, including as applicable:

- comparison against a simple economic baseline;
- realistic costs, funding, turnover, spread/slippage, and execution assumptions;
- out-of-sample or walk-forward degradation;
- parameter and timing perturbation;
- concentration in individual assets, periods, or exceptional events;
- family-level search / multiplicity risk; and
- an explicit statement of what observation would kill the mechanism.

The gate need not be identical for every experiment, but it must test economic
credibility rather than merely statistical detectability.

### State Snapshot and Reactive Jigsaw are downstream composition

Validated and frozen Jigsaw pieces may later contribute to a frozen market-state
representation. Reactive Jigsaw may activate already validated pieces and may
use state novelty or change detection. It does not invent patterns live and
should prefer `ABSTAIN` when the current state is unsupported or novel.

State machinery is downstream composition, not a rescue mechanism for weak
base signals. It should be deferred until enough independently useful evidence
exists to make conditional composition scientifically and economically
meaningful.

### Forecaster and Router are separate downstream roles

The Forecaster estimates narrow conditional outcomes. The Router estimates
expected utility and chooses among already-tested strategy sleeves or
`ABSTAIN` / `FLAT`. The Router may generalize for its decision problem, while
Jigsaw remains skeptical. Router authority never flows backward to rewrite
Jigsaw evidence, and Router usefulness does not turn weak evidence into
stronger scientific evidence.

A Router must not be used to rescue a collection of weak strategies by adding
state definitions, interactions, or conditional switching until the resulting
complexity happens to fit history. Router complexity must earn reproducible
incremental net utility against a simpler static or abstaining baseline. Until
that condition is plausible, Router development is lower priority than edge
discovery and falsification throughput.

### Research feedback is a first-class system metric

QntyLab should optimize not only correctness of individual experiments but also
the speed of epistemic correction. A useful control metric is the amount of
decision-changing evidence produced per researcher-hour or per bounded research
cycle.

Fast negative results are valuable. The architecture should make it cheap to
kill weak mechanisms early and expensive to confirm only the survivors.
Governance that does not materially improve claim validity, authority safety,
or downstream trust must not become an end in itself.

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

### Terminal falsification of the proprietary-edge thesis

QntyLab must permit the conclusion that no proprietary edge has yet been found.
If broad but bounded searches across economically distinct mechanism families
cannot produce candidates that beat simple credible baselines after realistic
frictions, out-of-sample degradation, robustness perturbations, and appropriate
confirmation, the response must not be to rescue the search with an increasingly
complex Router, state machine, feature stack, or model.

The correct conclusion in that state is:

```text
research / execution infrastructure may be sound
but proprietary trading edge is not established
```

That conclusion is a valid successful research outcome and should redirect work
toward new mechanisms or terminate the trading thesis rather than silently
escalating complexity.

## Relationship to ADR 0001

ADR 0001 remains authoritative for the `QntyLab Probationary Prospective
Observatory / DVOL V0` design it governs, including its project-specific source,
timing, retention, and authority constraints. It is not deleted or rewritten.

To the extent ADR 0001 contains broader statements about QntyLab's global role
that conflict with this ADR, this ADR supersedes those broader global-role
statements. Project-specific restrictions in ADR 0001 remain intact.

## Non-goals and current status

This ADR does not implement a Discovery Lane, confirmation system, Jigsaw, State
Snapshot, Reactive Jigsaw, a Forecaster, a Router, a strategy sleeve, a
promotion pipeline, or Qnty integration. It does not authorize historical
execution, paper or live activity, trading, external effects, or a shared
control plane. It does not replace project-specific preregistrations, execution
contracts, research results, or other immutable historical artifacts.

The Funding Pressure → Future RV24 experiment remains a bounded exploratory
predictive proposition. Even a positive `HIGH_MINUS_LOW_MEAN_RV24` result does
not by itself establish causality, a trading edge, strategy-family authority,
Router feature authority, or Qnty authority.
