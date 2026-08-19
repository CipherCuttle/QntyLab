# Independent hostile review

Review scope: the frozen lab-only plumbing module, deterministic tests, and
the pinned external bridge. This review is independent of product output and
was completed before the live synthetic batch.

Initial review found two High fail-open risks: returned receipts did not yet
enforce the DSH parent-LLM fields, and arbitrary sandbox/approval mode strings
were accepted. Both were fixed before freeze. One targeted rereview was used,
as permitted by the qualification contract.

Targeted rereview: PASS.

- `stopReason=error`, bridge nonzero exit, missing lifecycle, and empty output
  cannot normalize to `COMPLETED`.
- A completed lifecycle with expected disposal `SIGTERM` remains successful,
  while an error lifecycle with `SIGTERM` remains an error.
- Reviewer and verifier JSON require exact keys, known severities, and
  non-contradictory terminal fields.
- Product invocations require exact cwd/scope identity, Profile A/B matching,
  `workspace-write`, and an allowed approval mode.
- Native transport requests the schema-confirmed workspace-write policy with
  the synthetic workspace as its only writable root; DSH is checked against
  the same workspace configuration.
- The real TEST runner accepts argv only, captures exit status and digests,
  and cannot report pass without executing a command.
- Credential-shaped environment variables are removed without exposing their
  values. DSH parent LLM must be `NONE` with zero requests.
- No historical task, answer key, V2 state, runtime integration, Qnty
  NEXT_ACTION, trading, or capital behavior is present in the candidate.

Open Critical: 0. Open High: 0. Medium: 0. Low: 0.
