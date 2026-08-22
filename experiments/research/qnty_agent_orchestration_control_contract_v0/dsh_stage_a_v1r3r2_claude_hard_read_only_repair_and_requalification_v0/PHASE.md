# DSH Stage-A V1R3R2 Claude hard read-only repair and requalification

Project: `DSH_STAGE_A_V1R3R2_CLAUDE_HARD_READ_ONLY_REPAIR_AND_REQUALIFICATION_V0`.

This phase repairs exactly the prelive `BLOCK_CHILD_INFRA` found in PR #180:
the pinned Claude adapter did not enforce the frozen Stage-A hard read-only
policy. The pinned source identity remains
`deepseek-ai/deepseek-harness@99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`,
tree `3bc8f89fe494a4755c188be354add4e8b1e7b188`, tag `dsh-v0.1.0-rc.7`.

The canonical materializer applies both committed repairs to a fresh pristine
checkout: the predecessor Codex absolute-executable binding patch and this
phase's Claude policy patch. It then runs the exact offline frozen install and
full `pnpm run build:lib`. The Claude patch sets the SDK 0.3.220 `tools` and
`allowedTools` arrays exactly to `Read`, `Glob`, `Grep`, denies mutation,
execution, delegation, MCP, and `AskUserQuestion`, disables filesystem
settings and persistence, and binds the supplied cwd and executable.

Qualification is $0 only: the real built CLI, headless profile, Cordis,
Session, qualification budget gate, `llm-pi-ai` parent route, and loopback
OpenAI-compatible mock are exercised. The mock returns one assistant
completion with no tool call. No secret is read, no real Claude/Codex model
turn occurs, no live claim is created, and no Stage-A episode is executed.

The V1R3R1 digest remains historical predecessor-only. Its authorization is
explicitly incompatible with this runtime; a new Git-backed one-episode
authorization is required only after this repair PR is canonically merged.
