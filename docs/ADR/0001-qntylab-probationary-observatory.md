# ADR 0001: QntyLab Probationary Prospective Observatory

**Status:** `ACCEPTED_FOR_BOUNDED_V0_PROTOCOL_ONLY`

This decision accepts a bounded design-only protocol. It does not authorize capture
implementation, network access, an observation, analysis, or a strategy test.

## Context

QntyLab must not become a second QNTY, a historical strategy-tournament engine,
an autonomous multi-agent research platform, a formal validator, or a trading
system. Historical-search throughput increases false-discovery risk: many flexible
searches can make retrospective coincidences look persuasive.

The probationary lane is deliberately narrower. It asks whether QntyLab can create
genuinely new, timestamped information under a frozen hypothesis, and can preserve
a negative result rather than manufacture a candidate.

## Decision

Freeze the following responsibility boundary.

| Repository | Frozen role |
| --- | --- |
| QntyLab | prospective public-market observation; point-in-time provenance; data-feasibility research; hypothesis preregistration; negative-result memory; bounded exploratory closure |
| QNTY | independent confirmation; protected evidence; canonical accounting; formal scientific classification; paper/shadow/live authority |

The V0 forecasting question is:

> Does the Deribit volatility index contain incremental prospective information about future realized BTC and ETH volatility beyond trailing realized volatility alone?

It is not a trading or profitability hypothesis.

For V0, QntyLab may eventually retrieve one declared public source, preserve exact
raw responses, normalize only declared fields, produce timestamped hash-bound
observations, calculate the preregistered forecast comparison after the minimum
prospective sample exists, and terminate as killed, blocked, or retained for a
separately registered follow-up.

V0 forbids: historical strategy tournaments; return optimization; trading signals;
position generation; PnL or edge ranking; paper/shadow/live execution; QNTY
control-state mutation; QNTY holdout access; QNTY verdict-feedback tuning; a
multi-agent framework; a knowledge graph; a feature store; a generic observatory
platform; a generic candidate-pack framework; and historical options backfill.

Authority is one way: QntyLab may later propose. QNTY may independently confirm.
QntyLab may not use iterative QNTY verdict feedback to tune the same hypothesis
family.

No generic permanent capability may be promoted until at least three completed
independent prospective experiments have required it. V0 remains experiment-specific.

## Probation success criteria

1. It introduces a genuinely new observable.
2. It freezes the hypothesis before eligible outcomes accumulate.
3. It makes observation timing and raw-byte identity independently auditable.
4. It does not duplicate QNTY validation, accounting, custody, or authority.
5. It can honestly terminate without producing a candidate.
6. It requires no prior chat transcript to understand or reproduce.
7. It keeps generic infrastructure smaller than experiment-specific work.

## Repository-level kill criteria

- `K1` Generic infrastructure exceeds experiment-specific code.
- `K2` QNTY accounting or validation logic is duplicated.
- `K3` The hypothesis changes after eligible outcomes exist.
- `K4` Observation timestamps or raw responses cannot be verified.
- `K5` Historical strategy tournaments are added.
- `K6` QNTY feedback is used for adaptive tuning.
- `K7` A general agent framework is introduced prematurely.
- `K8` A permanent abstraction is promoted before three completed uses.
- `K9` The experiment cannot terminate as killed or blocked.
- `K10` A bounded QNTY exploratory worktree would be materially simpler.

## Consequences

The separately frozen V0 protocol is the only Phase 0 experiment surface. A
separately authorized next task may implement only one experiment-specific capture
module. This ADR does not authorize that implementation.
