# Hostile governance review — DSH Stage-A V1R3R2 authorization V0

Review count: exactly one independent hostile review.

Scope: authorization delta only. The review did not run DSH, read a secret, create a claim, make a model request, activate execution, or authorize Stage B.

Checks:

1. The prior V1R3R1 launch digest is explicitly superseded and `v1r3r1_authority_compatible` is false.
2. The V1R3R2 qualified contract, runtime manifest, executable identity, launch policy, Codex repair, and Claude repair digests are all bound.
3. Claude is exact Read/Glob/Grep-only with Write, Edit, Bash, Agent, Task, `mcp__*`, AskUserQuestion, and delegation denied; empty settings/MCP/agents/plugins and `dontAsk` are bound.
4. DSH identity is pinned to the exact repository, commit, tree, and tag; no moving ref or later commit is allowed.
5. The fresh V1R3R2 claim ref is create-only and construction explicitly creates no remote or local claim.
6. Exactly one initially unconsumed episode is permitted; no whole-episode retry or second episode is permitted.
7. Parent budget, retry policy, spend ceiling, child routes, child ceilings, and immutable fixture identity match the frozen Stage-A envelope.
8. Secret, DSH, model, child, claim, spend, Stage B, Qnty, trading, and capital construction counters are zero/denied.
9. Closure is `CLOSED_PASS`, implementation is complete but not authorized, and no active project remains.

Verdict: PASS.
Critical: 0
High: 0
Medium: 0
Low: 0
Targeted rereview: NOT_REQUIRED.
