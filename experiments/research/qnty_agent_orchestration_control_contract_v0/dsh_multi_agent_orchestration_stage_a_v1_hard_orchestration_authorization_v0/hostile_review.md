# Hostile offline review — DSH Stage-A V1 hard orchestration

Review mode: one independent, offline pass over the staged implementation
diff. No DSH, OpenAI, Codex, Claude, market-data, or subprocess call occurred.

## Findings

- Critical: 0
- High: 0
- Medium: 0
- Low: 0

## Adversarial checks

- Exact `subagent_codex` / `subagent_claude_code` admission is state-bound;
  generic names, `subagent_fork`, and aliases fail before the provider callable.
- Initial and repair budgets are separate, consumed before invocation, and
  cannot be replenished by restart, duplicate completion, timeout, or failure.
- Interprocess file locking plus atomic JSON replacement serializes concurrent
  reservations and preserves a running child across restart.
- Claude repair authority requires strict machine-readable review data with
  closure-blocking Critical/High findings; malformed data blocks child infra.
- Initial tests are driver-owned and always precede the one initial review;
  rereview requires real repair completion plus driver-owned retest completion.
- Event counting parses only exact `type=tool/call` objects; catalog, schema,
  reasoning, prompt, and stream text do not count as invocations.
- The wrapper invokes the provider callable only after a persisted grant and
  records provider exceptions/timeouts without retry.
- The frozen `STAGE_A_BOUNDED_RETRY_V0` fixture remains unchanged; upstream DSH
  and all live execution paths remain untouched.

## Targeted closure rereview — exactly one pass

This independent rereview was limited to the authorized closure repairs H-01,
H-02, and M-01. It did not broaden into a general review and made no DSH,
OpenAI, Codex, Claude, market-data, or live subprocess call.

- H-01: PASS. The frozen V1 profile binds each model-facing delegation tool to
  a QntyLab-gated provider. The wrapper implements the pinned DSH
  `SubagentProvider.start(request)` seam and obtains the persisted grant before
  calling the raw provider. Static route proof and the Node seam test pass.
- H-02: PASS. `claude_rereview` now checks the latest driver-owned retest first;
  a failed retest always closes `FAIL_IMPLEMENTATION`, including when the
  rereview is clean. Four adversarial state-machine cases pass.
- M-01: PASS. The authorization artifact and canonical project state now
  explicitly record one later V1 execution/closure phase, one draft closure PR,
  stop-after-PR, no second episode, and no Stage B/scientific/trading/capital
  authority.

## Review verdict

Critical: 0
High: 0

`PASS_TARGETED_CLOSURE_REREVIEW`

The V1 authorization remains offline-only and does not authorize Stage B or a
live V1 episode in this phase.
