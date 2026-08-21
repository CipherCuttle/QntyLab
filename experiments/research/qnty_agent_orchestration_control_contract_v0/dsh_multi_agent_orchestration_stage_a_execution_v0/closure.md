# DSH multi-agent orchestration Stage-A execution — closure

**Terminal outcome: `BLOCK_PARENT_INFRA`**

The one authorized Stage-A episode ran live under the canonical
authorization (PR #165, merge `1924bd4d4...`), after a pre-live H-04 repair
(disabled internal parent retries; commit `523b86b`) and a clean pass of all
four offline verification gates (provider identity, exact composition
allowlist, non-registry package resolution, ambient-override exclusion).

## What happened

The DSH parent (gpt-5-mini via `llm-pi-ai`/OpenAI) read the fixture task and
files (5 steps: `skill`, `glob`, `read`×3), then invoked `subagent_codex`
**three separate times** (steps 6, 7, 8) with essentially the same full
implementation prompt each time — without ever invoking
`subagent_claude_code`. The frozen contract authorizes at most two Codex
calls total, and the second is conditional on Claude reporting a
Critical/High finding from an initial review that never happened. This is a
genuine violation of the frozen call-sequence contract, confirmed by
structural (not substring) parsing of the session log's `tool/call` events.

The episode was manually terminated (clean `SIGTERM`) after the real-time
monitor's substring-based check flagged what looked like an unauthorized
`subagent_fork` call. Forensic re-analysis after the fact showed that flag
was a **false positive**: no `subagent_fork` tool/call event was ever
actually issued — the substring match came from tool-catalog metadata
embedded in streaming/request data, not an invocation (`subagent_fork` is a
real, always-mounted tool from `dsh-base`'s own default composition, so its
name legitimately appears in every request's tool schema regardless of
whether it's called). This is recorded honestly rather than quietly
smoothed over. It doesn't change the outcome: the independently-confirmed
Codex call-budget violation above means the episode was already outside its
authorized contract when it was terminated, so termination — for the real
reason, if not quite the one first cited — was correct.

## Why `BLOCK_PARENT_INFRA` and not something else

- Not `FAIL_IMPLEMENTATION`: no implementation was ever completed to
  evaluate. `retry.py` is byte-identical to the frozen stub
  (`f82a84088b76...`) — none of the three Codex delegations returned before
  termination.
- Not `BLOCK_COST`: every cost control held. 8/8 steps used (at, not over,
  the ceiling), 0 retry events (confirming the H-04 fix), and real spend
  was approximately **$0.0066** of the $1.00 authority — far under even the
  $0.865536 conservative bound.
- Not `BLOCK_AUTH` or `BLOCK_CHILD_INFRA`: the secret-file gate passed,
  native Codex/Claude Code were both present and versioned, and the
  workspace boundary was never violated.
- It is a parent-process/orchestration-composition fault: the parent itself
  did not follow its own frozen delegation sequence.

## Budgets consumed

```text
Episode number:            1 of 1 authorized
Parent steps:               8 of 8
Parent retry events:        0
Codex calls observed:       3 (budget: 1 initial + ≤1 conditional repair = 2 max)
Claude calls observed:      0 (budget: 1 initial + ≤1 conditional rereview)
Estimated spend:            ~$0.0066 of $1.00
Fixture mutated:             No
```

## What this does and does not mean

This Stage-A episode did not demonstrate that the pinned/repaired DSH build
can coordinate the intended bounded Codex→Claude workflow — it demonstrated
that, at minimum, the parent model's adherence to a purely prompt-level
call-sequence instruction (as opposed to a framework-enforced one) cannot be
assumed. No second episode is authorized under this closure; no Stage B
follows from it. This result carries no scientific, trading, promotion, or
capital authority, and answers only the narrow operational question the
authorization asked: whether this exact composition could run the frozen
workflow end-to-end. It could not, on this one attempt.

## Evidence

A temporary OpenAI credential had already appeared in pre-execution chat
before this episode began; Stage-A execution did not reproduce, print, or
persist its value anywhere (see `secret_handling` in
`execution_evidence.json`), but that prior exposure itself is not undone by
this closure.

Full structured evidence: `execution_evidence.json` in this directory. The
raw session JSONL log is intentionally not committed (per the authorization's
prohibition on committing raw transcripts); every figure above is derived
from it and cross-checked in `execution_evidence.json`.
