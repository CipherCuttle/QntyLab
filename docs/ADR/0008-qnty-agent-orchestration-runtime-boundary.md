# ADR 0008: Qnty Agent Orchestration Runtime Boundary

**Status:** `CURRENT_GLOBAL_COMPANION_NO_IMPLEMENTATION_AUTHORIZATION`

## Context

ADR-0007 is the current global architecture and requires an explicit ownership
and dependency decision before a new top-level component, durable schema family,
cross-repository interface, or future Git mutation boundary is introduced.
The governance-freeze phase for `QNTY_AGENT_ORCHESTRATION_CONTROL_CONTRACT_V0`
names a future private repository, `QntyAgentRuntime`, but does not create it or
authorize its implementation.

## Decision

`QntyAgentRuntime` is the intended future owner of a deterministic,
non-authoritative agent execution and routing runtime:

```text
NON_AUTHORITATIVE_AGENT_EXECUTION_AND_ROUTING_RUNTIME
```

Its future scope is limited to deterministic task admission, execution-only
task state, capability routing, workspace/process ownership, trusted
verification coordination, Git publication brokerage, and execution
provenance.

It does not own scientific truth, research state, Qnty `NEXT_ACTION`, Qnty
acceptance, QntyLab project state, QntyAgentEval state, QntyPolicyGate policy,
merge authority, trading, capital, or any other domain authority.

The dependency direction is one-way:

```text
QntyAgentRuntime
  reads/invokes QntyLab Context Spine V3, Qnty continuity, and repository
  Git/contracts
  invokes a replaceable execution substrate and bounded workers

QntyLab and Qnty do not depend on QntyAgentRuntime for canonical authority.
QntyAgentEval observes/evaluates; QntyPolicyGate evaluates Git policy.
Neither operates or controls the runtime.
```

The future canonical contract owner and path are:

```text
repository: QntyAgentRuntime
path:       docs/control/QNTY_AGENT_ORCHESTRATION_CONTROL_CONTRACT_V0.md
```

The governance authorization artifact records the complete V0 topology,
invariants, schema semantics, execution states, trust roots, capability and
credential limits, workspace/Git model, review independence, continuation
semantics, autonomy ladder, and Stage-A gates. It is the phase's authorization
surface; this ADR records only the architectural ownership boundary.

## Non-authority and implementation boundary

Repository existence is not runtime implementation authority. Exactly one later
contract-only bootstrap may create the future repository's governance surface:
`AGENTS.md`, `README.md`, the canonical control contract, four contract schemas,
deterministic schema/invariant tests, and only normal Git metadata. That phase
may not create a controller, daemon, adapter, dispatcher, scheduler, broker,
workspace manager, worker runner, or autonomous PR flow.

This phase and the later bootstrap do not authorize runtime implementation,
DeepSeek Harness implementation or integration, scientific execution, trading,
capital, shadow, live, automatic merge, or `NEXT_ACTION` authority.

No `QntyAgentRuntime` entry is added to `docs/state/ecosystem.toml` until the
repository exists with an immutable Git identity and a separate reconciliation
truthfully establishes its catalog record.

## Consequences

The control contract has one future canonical owner and cannot be duplicated in
QntyLab, Qnty, QntyAgentEval, or QntyPolicyGate. Existing repositories retain
their canonical domain authority. The future runtime may consume their bounded
contracts but cannot become a second authority plane or create a circular
dependency.

This companion ADR does not implement any runtime, change any external
repository, create a repository, or grant any operational authority. ADR-0007
remains `CURRENT_GLOBAL` and is not superseded.
