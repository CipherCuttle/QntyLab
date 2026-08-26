# DSH Stage-A V1R3R2 V0R7 one-episode live execution closure

Terminal outcome: `V0R7_EXECUTION_TERMINAL_FAILURE`.

The exact canonical activation merge was verified from Git at action time as
`1b0e936e9f1f696cd586e1cd1ea1bf3a5e1ae4c4`, with parents
`908dfed34b5f22bb99e77c146a757a8e6299064c` and
`755cb755cd7dccc547a6c39b125e7cec51cd9fbc`. All non-secret gates passed,
including fresh production DSH_HOME materialization, whole-home identity, the
pinned composite launcher bytes
(`bf0baf30cc5b6ca9206c0bf4ea6357cfc37fc60b11ddf1ee06e8a9f8b252634c`), and the
frozen fixture `STAGE_A_BOUNDED_RETRY_V0`
(`397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552`).

The single authorized DSH invocation was made through the pinned composite
launcher and exited 1 (not timed out). The profile boot crashed while importing
`@qntylab/dsh-stage-a-parent-enforcement/lib/index.js:25` with
`TypeError: z.string(...).regex is not a function` — a zod schema
incompatibility inside the frozen production implementation. This is recorded
as a production defect and was NOT repaired in this closure.

The crash preceded the guard's `ensureClaim()`: the claim was never attempted.
The remote claim ref
`refs/heads/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r7`
and the local state directory
`/var/tmp/qntylab-claims/dsh-stage-a-v1r3r2-one-episode-live-execution-v0r7/episode-1`
were absent before and after the episode. The secret was read exactly once with
parent-only extraEnv injection and was never logged, hashed, serialized, or
persisted. Provider logical requests, provider wire requests, codex turns,
claude turns, repair, and rereview were all zero; spend was USD 0.00. V0R5 and
V0R6 state and artifacts were not touched.

Closure verification: `python -m qntylab.project_context doctor --strict`,
`render`, `render --check`, `spine`, `brief`, and
`python -m qntylab.research_ledger doctor` all exited 0, and the focused DSH
Stage-A regression suite passed 38 tests across the V0R7 activation,
V0R7 authorization, execution-evidence, and prelive-enforcement test modules.

The episode is terminally closed with no retry, no second episode, no replay,
no automatic V0R8, and no runtime or contract repair. The DSH_STAGE_A
disposition recommendation is `MAINTENANCE_ONLY` pending explicit future
Git-backed authority. No Stage B, Qnty, scientific, trading, capital,
promotion, or broader production authority exists. Full structured evidence is
in `execution_evidence.json`.
