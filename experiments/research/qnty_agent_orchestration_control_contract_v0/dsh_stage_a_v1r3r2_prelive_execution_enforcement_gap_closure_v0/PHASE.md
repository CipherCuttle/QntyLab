# DSH Stage-A V1R3R2 prelive execution-enforcement gap closure V0

Project: `DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_V0`.

This is the single offline implementation phase authorized by the canonical
`DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_AUTHORIZATION_V0`.
It does not activate Stage-A, execute a real episode, read a real credential,
create a real claim, contact an external model/provider, or authorize spend.

## Repair

The smallest phase-local repair adds:

- a durable exact-order Codex/Claude state machine in front of raw provider
  start;
- a global pre-adapter parent gate with eight-attempt, 4096-output-token,
  zero-provider-retry, text-only, and conservative authorized-spend controls;
- a create-only Git claim with durable intent and fail-closed partial-state
  interpretation;
- a fixed Stage-A policy patch and allowlisted launcher environment;
- a live-equivalent offline profile harness that uses the actual materialized
  DSH runtime/profile structure, loopback parent mock, actual DSH subprocess
  seam, native child stubs, disposable state, and a fake credential sentinel.

The spend scope is exactly
`PARENT_OPENAI_AUTHORIZED_SPEND_USD_UNDER_FROZEN_SCHEDULE <= 1.00`. It is not
total multi-model cash spend. Each reservation includes a conservative text
input-token upper bound, the full 4096 output-token allowance, and a 4x
uncertainty factor over the frozen 2026-08-22 GPT-5 mini rates ($0.25/M input,
$2/M output). Non-text modalities fail closed. The price source is the
[official OpenAI GPT-5 mini model page](https://developers.openai.com/api/docs/models/gpt-5-mini).
Any future authorization must revalidate the frozen schedule before use.

## Decisive evidence

`qualification.json` records the one bounded fresh requalification. It ran 12
full-profile cases. Success, 429, 500, timeout, and connection failure each
made one reserved logical request and exactly one loopback wire request. The
ninth request and the first request exceeding the remaining authorized-spend
budget were denied before the adapter seam. The malicious child sequences
were rejected before the native stub with separately recorded attempted and
native invocation counts. Parent sentinel receipt was positive while child and
recursive persisted/captured leakage counts were zero.

`tests/test_dsh_stage_a_v1r3r2_prelive_enforcement.py` separately covers the
claim failure matrix with disposable local and bare Git state, including
concurrency, both asymmetric shapes, ambiguous outcome, and crash/restart.

The pinned DSH runtime and executable bytes did not change. The launch policy
and identity-covered enforcement bytes did, so the old qualified digest is
stale. `evidence/digests.json` binds every repaired production enforcement
file and issues the replacement contract. PR #189 is consequently
`SUPERSEDED_NOT_MERGEABLE`; this phase does not modify, close, merge, or
otherwise mutate it.
