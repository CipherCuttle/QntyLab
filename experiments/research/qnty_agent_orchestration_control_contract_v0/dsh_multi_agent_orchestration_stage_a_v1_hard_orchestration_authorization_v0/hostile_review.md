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

## Review verdict

`PASS_NO_CRITICAL_OR_HIGH_FINDINGS`

No repair or targeted rereview is authorized or required. This phase remains
offline-only and does not authorize Stage B or a live V1 episode.
