# ADR 0005: QntyLab North-Star Market-Intelligence Architecture

**Status:** `CURRENT_GLOBAL_SCIENTIFIC_NORTH_STAR_NO_IMPLEMENTATION_AUTHORIZATION`

## Context

QntyLab is an evidence-producing exploratory research laboratory. It accumulates
bounded, falsifiable, provenance-linked knowledge about market behavior. It is
not an AI trading bot, a monolithic trading system, or an authority for trading
or external effects.

This ADR establishes the current scientific north star so that repository state
can be interpreted without relying on older, broader wording. It is a
north-star architecture, not authorization to implement every layer described
here. Current implementation status must be established independently from Git
and from the contract governing each project. ADR 0007 holds the current global
architecture and cross-repository role boundary; this ADR remains current for
the scientific and research-design north star inside that boundary.

The primary objective is not to maximize governance, artifact count, predictive
fit, or architectural sophistication. It is to maximize the rate at which
QntyLab can discover and falsify credible economic edge while preserving enough
research integrity that survivors can later earn much stronger confirmation.

A useful optimization target for the Discovery Lane is therefore not raw idea
count or nominal information gain alone, but **expected decision-changing
information per bounded research cost**. Research cost includes researcher time,
data acquisition and qualification burden, implementation complexity, search
budget consumed, and the risk that a more complex experiment creates additional
degrees of freedom without answering a more valuable question.

The intended direction is:

```text
QntyLab
→ mechanism-first hypotheses
→ outcome-blind data qualification + bounded search budget
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

### Discovery Integrity Kernel

Fast discovery is not permission for untracked adaptive backtesting. The
Discovery Lane has a deliberately small integrity kernel that is cheap enough to
apply broadly and strong enough to prevent the most common forms of self-created
edge.

Before scientific outcome access for a bounded mechanism family, freeze at the
appropriate level:

- the economic mechanism and the simplest executable expression capable of
  falsifying it;
- the simplest credible opponent or abstaining baseline;
- the finite family/search budget, including meaningful variants, horizons,
  universes, transformations, and conditional branches that may be explored;
- the causal decision/execution timing convention;
- the relevant execution-friction model; and
- a cheap failure condition stating what observation is sufficient to kill the
  frozen proposition rather than rescue-tune it.

Every material interaction with historical scientific outcomes consumes
research budget. Human exploration, scripted sweeps, LLM-generated variants,
manual parameter changes, alternate horizons, alternate universes, alternate
benchmarks, abandoned variants, and informal "quick checks" are part of the
search denominator when they can influence what is tested next. A clean final
candidate must not erase this adaptive path.

Discovery integrity is therefore primarily enforced by **preserving the search,
freezing the bounded question before outcome access, and making failures die**,
not by applying confirmation-grade ceremony to every exploratory idea.

### Outcome-blind data qualification

Data feasibility must be separated from scientific outcome evaluation.
Outcome-blind qualification may inspect only facts needed to determine whether a
mechanism can be tested honestly, such as:

- source and venue identity;
- instrument and contract identity;
- available fields and interval/granularity;
- historical coverage and missingness;
- timestamp units and timestamp semantics;
- point-in-time / publication-time semantics;
- source revision and replacement policy;
- immutable source snapshots or digests where available; and
- the existence of execution-relevant fields required by the proposed
  mechanism.

It must not inspect returns, candidate PnL, outcome direction, feature/outcome
relationships, correlations, regressions, rankings, charts selected for their
scientific result, or any other information that could adapt the mechanism or
search budget to the answer.

For event mechanisms, the relevant point-in-time boundary is the **first
publicly actionable information time**, not merely the later effective-event
time. For high-frequency or cross-venue mechanisms, timestamp synchronization
and observation granularity must be capable of resolving the claimed lead/lag
or dislocation; a bar-level backtest must not manufacture a sub-bar execution
advantage. If data timing uncertainty is of the same order as the hypothesized
edge, the experiment is not qualified to make that claim.

Outcome-blind data qualification is an evidence-integrity boundary, not generic
infrastructure authority. New data plumbing should be built only when a concrete
mechanism cannot be falsified with already-qualified data and the expected
information gain justifies the bounded cost.

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

Prefer the lowest-description-length expression that can falsify the mechanism.
Interaction rules, regime definitions, model complexity, feature stacks, and
parameter breadth must earn their additional degrees of freedom through a
separate information-bearing question rather than being added until history
fits.

### Search itself is part of the evidence problem

Human, scripted, and LLM-assisted candidate generation all create researcher
degrees of freedom. Testing many lookbacks, universes, modifiers, interaction
rules, prompts, generated hypotheses, or strategy variants constitutes search
even when the final survivor is later preregistered cleanly.

QntyLab must therefore preserve family-level trial history and treat broad
candidate search as a multiple-comparison / overfitting risk. A clean final
experiment must not erase the exploratory path that selected it.

Selection-bias and multiplicity controls should be **family-appropriate**, not a
single mandatory statistical framework. Depending on the actual experiment,
relevant tools may include benchmark-relative multiple-model tests,
family-level false-discovery control, probability-of-backtest-overfitting
analysis, deflated performance statistics, or a simpler finite family gate when
that is sufficient. The method must match the search that actually occurred;
the architecture does not authorize building a generic statistical bureaucracy
in advance of a concrete need.

### Conservative execution semantics

A historical edge claim must use information that was available at the decision
time and an execution model appropriate to the mechanism's horizon and market
microstructure.

As applicable, economic evaluation must account for fees, spread/slippage,
funding, turnover, latency, borrow or margin constraints, market impact,
exchange outages, and fill/queue uncertainty. Missing execution information must
not be replaced with favorable assumptions. Maker fills, queue priority,
sub-bar timing, or cross-venue synchronization must not be treated as free or
certain when the data cannot support them.

Risk-transfer or premium mechanisms must be tested as executable risk-bearing
policies rather than promoted from a raw statistical spread. For example, a
premium between two measured quantities is not itself net economic edge unless
the relevant hedge, rebalance, financing, tail, and implementation costs are
represented by the frozen contract.

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
credibility rather than merely statistical detectability. A plausible economic
story may improve a mechanism's priority for testing; it must not weaken the
survivor threshold or convert an exploratory result into stronger evidence.

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
decision-changing evidence produced per bounded research cost, not merely per
backtest or per candidate. Cost includes researcher time, data qualification,
implementation complexity, and search budget consumed.

Fast negative results are valuable. The architecture should make it cheap to
kill weak mechanisms early and expensive to confirm only the survivors.
Mechanisms requiring substantial new data or execution infrastructure must earn
that burden through higher expected decision value; intellectual novelty alone
is insufficient. Governance that does not materially improve claim validity,
authority safety, or downstream trust must not become an end in itself.

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

## Methodological grounding

The Discovery Integrity Kernel reflects established problems and controls in
quantitative research rather than a project-specific aesthetic. Relevant
methodological lineages include:

- White's Reality Check for data snooping and Hansen's Superior Predictive
  Ability framework for multiple-model benchmark comparison;
- Harvey, Liu, and Zhu on multiple testing and false discoveries in the
  cross-section of expected returns;
- Bailey and coauthors on probability of backtest overfitting and deflated
  performance statistics after strategy search;
- Novy-Marx and Velikov on turnover and transaction costs materially changing
  apparent anomaly profitability; and
- standard event-study methodology on event timing, anticipation, and
  contamination.

These references motivate the invariants; they do not prescribe one universal
test for every QntyLab experiment. Project-specific search structure, data,
horizon, and economic claim determine the appropriate bounded controls.

## Relationship to ADR 0001

ADR 0001 remains authoritative for the `QntyLab Probationary Prospective
Observatory / DVOL V0` design it governs, including its project-specific source,
timing, retention, and authority constraints. It is not deleted or rewritten.

To the extent ADR 0001 contains broader statements about QntyLab's global role
that conflict with this ADR, this ADR supersedes those broader global-role
statements. Project-specific restrictions in ADR 0001 remain intact.

## Relationship to ADR 0006

ADR 0006 remains the companion research-design philosophy. Its principles such
as preserving the denominator, separating exploration from confirmation,
outcome-blind data-capability compile, simple-first research, prospective
prediction-first evidence, and failure-as-information remain aligned with this
North Star. ADR 0005 defines the architecture and durable strategic invariants;
ADR 0006 provides the broader epistemic philosophy inside those boundaries.

## Relationship to ADR 0007

ADR 0007 is the current global architecture (`GLOBAL_ARCHITECTURE`) and holds
the cross-repository role boundary, `QNTY_HANDOFF` and downstream-acceptance
semantics, the shared identity vocabulary, Context Spine ownership, context
source precedence, and the Architecture Relevance Gate. This ADR is superseded
on exactly those points and must not be read as an independent authority over
them.

This ADR remains current as the QntyLab scientific north star
(`GLOBAL_SCIENTIFIC_NORTH_STAR`). Its research integrity, discovery-integrity,
outcome-blind qualification, evidence non-escalation, survivor-gate, promotion
boundary, and no-implementation-authority constraints remain in force and are
not weakened by ADR 0007. Being current here confers no implementation,
execution, paper, shadow, live, or capital authority.

## Non-goals and current status

This ADR does not implement a Discovery Lane, data-qualification framework,
multiple-testing framework, confirmation system, Jigsaw, State Snapshot,
Reactive Jigsaw, a Forecaster, a Router, a strategy sleeve, a promotion
pipeline, or Qnty integration. It does not authorize market-data acquisition,
historical execution, paper or live activity, trading, external effects, or a
shared control plane. It does not replace project-specific preregistrations,
execution contracts, research results, or other immutable historical artifacts.

The Funding Pressure → Future RV24 experiment remains a bounded exploratory
predictive proposition. Even a positive `HIGH_MINUS_LOW_MEAN_RV24` result does
not by itself establish causality, a trading edge, strategy-family authority,
Router feature authority, or Qnty authority.

## Operational Alignment Contract

This section encodes operating policy only. It grants no execution, live,
trading, capital, promotion, or implementation authority.

**Optimization target.** The single optimization target for QntyLab work is
expected decision-changing information per bounded research cost. Architecture
completeness, governance sophistication, artifact count, agent count,
orchestration capability, runtime elegance, speculative hardening, and similar
quantities are not optimization targets and do not justify phases by
themselves.

**Mandatory phase questions.** Every non-trivial phase must concretely answer,
before it starts:

1. `WHAT_UNCERTAINTY_DOES_THIS_REDUCE?`
2. `WHAT_DECISION_CHANGES_IF_POSITIVE?`
3. `WHAT_DECISION_CHANGES_IF_NEGATIVE?`
4. `WHAT_IS_THE_CHEAPEST_VALID_TEST?`
5. `WHAT_STOPS_THIS_LINEAGE?`

If any of these cannot be answered concretely, the phase must not be started.

**Infrastructure foreign-key rule.** Any infrastructure, governance, or runtime
repair phase must identify, all referring to a currently selected scientific
question:

- `BLOCKED_SCIENTIFIC_QUESTION`
- `BLOCKING_FAILURE`
- `WHY_THE_FAILURE_PREVENTS_THE_QUESTION`
- `MINIMUM_REPAIR`
- `CHEAPER_ALTERNATIVE_CONSIDERED`
- `DECISION_UNLOCKED_BY_REPAIR`
- `STOP_AFTER`

If no named blocked scientific question exists, no infrastructure phase may be
started. Insufficient reasons include: cleaner architecture, future flexibility,
robustness in principle, nicer provenance, broader orchestration, more agent
capability, generic hardening, possible future use, fixing DSH because it is
broken, and reducing technical debt without a current scientific dependency.

**North Star drift.** `NORTH_STAR_DRIFT = TRUE` when more than 3 of the last 10
completed phases are infrastructure/governance-only without directly
unblocking a named selected scientific question. While true, initiating
infrastructure work stops; work returns to the cheapest information-bearing
experiment.

**Infrastructure loop.** `INFRA_LOOP = TRUE` when two consecutive phases attack
substantially the same infrastructure blocker without a new market/scientific
observation. Default dispositions are `SIMPLER_PATH`, `DEFER`, or `KILL`. A
third attempt requires explicit new Git-backed authority plus proof that no
cheaper scientific route exists.

**Router/State entry discipline.** Entry into Router or State work requires all
of: at least 3 economically useful surviving mechanism/sleeve families, a
credible FLAT/ABSTAIN baseline, at least 1 genuinely prospective evidence
stream, and an actual conditional-composition question not answerable by
evaluating the sleeves directly. Until then, `ROUTER = DEFERRED` and
`STATE = DEFERRED`.

**DSH Stage-A disposition.** `DSH_STAGE_A_DISPOSITION = MAINTENANCE_ONLY`. DSH
is no longer a roadmap destination. No new DSH authorization, repair,
qualification, activation, execution, hardening, generalization, or
orchestration project may be started merely because DSH itself is imperfect. A
future DSH phase requires a named selected scientific question mechanically
blocked by a concrete DSH defect AND no materially cheaper valid route.
`NO_AUTOMATIC_V0R8 = true`.

**Failure and negative evidence.** FAILURE IS INFORMATION. Failed frozen
hypotheses are not auto-rescued; blocked implementations are not auto-repaired;
broken tools are not auto-fixed. First ask whether the selected scientific
question can proceed through a simpler valid route.

**Complexity rule.** Simple baseline first. Complexity must earn itself through
incremental information. Router and State cannot rescue weak signals.
