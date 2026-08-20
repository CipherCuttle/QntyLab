# Hostile implementation review

Scope: final C candidate, B plus explicit `thread/start.sandbox` ownership.

Checks completed:

- B remains consumed and is not rerunnable;
- B-to-C has exactly one semantic delta: `params.sandbox`, `<ABSENT>` to
  `workspace-write`;
- `sandbox` is not confused with `turn/start.sandboxPolicy`, writable roots,
  runtime roots, or capabilities;
- approvalPolicy remains `never` and DSH/Codex/prompt/task identities remain pinned;
- no API-key or pay-per-token route is available;
- the new C marker is independent and irrevocable with zero retries;
- the prior aggregate `-32600` remains represented as unknown placement rather
  than being discarded or falsely assigned to a lifecycle stage, and the live
  wrapper records every trace error with ordinal/stage when available;
- receipt classification requires actual fixture mutation for success.
- the pinned patch applies to both the tracked TypeScript source and the
  generated runtime artifact without changing any other DSH input.

Findings:

Critical: 0
High: 0
Medium: 0
Low: 0

Verdict: HOSTILE_REVIEW_PASS
