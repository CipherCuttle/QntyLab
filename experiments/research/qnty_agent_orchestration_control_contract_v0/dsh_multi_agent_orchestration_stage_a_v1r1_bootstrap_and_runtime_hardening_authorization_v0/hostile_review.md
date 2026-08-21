# Hostile offline review — DSH Stage-A V1R1

Review mode: one bounded offline pass over the V1R1 runtime-hardening
changes, with no DSH fixture, model request, Codex child, Claude child, or
network call.

## Findings

- Critical: 0
- High: 0
- Medium: 0
- Low: 0

## Adversarial coverage

- Provider-added/provider-removed listeners are installed before current
  presence is inspected; each raw-provider generation mounts and unmounts once.
- Authorization persists before raw start and the exact raw provider identity
  is re-resolved; remove/replace after authorization cannot start the raw
  provider.
- Background delegation is disabled in both model-facing tool rows.
- The parent gate admits only `openai/gpt-5-mini`, 4096 max tokens, retry 0,
  agent-loop requests, and reserves atomically before adapter dispatch; the
  ninth reservation and every unexpected route block.
- Auxiliary model routes and mutation/delegation tools are disabled; the
  built smoke exposed only the two gated child tools plus read-only inspection.
- Claude policy is pinned to `Read`, `Glob`, and `Grep`, with empty setting
  sources, no persistence, no MCP, and explicit mutation/delegation denial.
- Codex app-server startup is pinned to ephemeral threads, approval `never`,
  and `workspace-write` sandbox semantics in the exact local wire adapter.
- Raw-start, raw-result, malformed-review, gate-completion, disposal, and
  timeout outcomes settle through one terminal classification.
- The actual built DSH/Cordis profile reached `BOOT_READY=YES` with zero model
  requests and zero child spawns.

## Verdict

Critical: 0

High: 0

`PASS_OFFLINE_BOOTSTRAP_AND_RUNTIME_HARDENING`

This receipt does not authorize a live Stage-A fixture, Stage B, scientific
validation, trading authority, capital authority, or merge.
