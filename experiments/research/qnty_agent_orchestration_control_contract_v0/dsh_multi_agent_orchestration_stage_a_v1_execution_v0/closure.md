# DSH Stage-A V1 execution V0 closure

Terminal outcome: `STAGE_A_V1_BLOCK_PARENT_INFRA`.

The disposable pinned DSH build failed during profile boot before session
materialization and before any parent-model request. The exact loader failure
was `dsh: plugin tree failed: loader fibers failed`. The causal errors were
that `qntylab-gated-provider` attempted to load before the raw `codex` and
`claude-code` providers were registered.

Consequently the parent request count was zero, both exact child-call counts
were zero, no fixture test or review ran, and observed spend was `$0.00`.
The canonical V1 controller, gated provider, profile patch, authorization
record, repaired provider materializer, pinned source, and frozen fixture were
not changed. No rescue run was performed. The disposable fixture hashes are
identical before and after the blocked boot.

The authority checkpoint remains `IMPLEMENT_REQUIRED` with no consumed child
budget; the project registry is closed blocked so this authorization cannot be
replayed. The secret gate was checked without printing or hashing the value:
the file was present, nonempty, and mode `0600`; the value was not committed or
persisted in execution artifacts. Native Codex and Claude authentication
remained on the normal host HOME, but neither child was reached.
