# V0R5 hostile governance review

Review target: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R5`

Review mode: exactly one independent hostile governance review after the
authorization artifact, registry row, roadmap entry, and focused tests were
frozen. This review does not invoke DSH, a provider, a model, Codex, Claude,
the real secret, or a claim mechanism.

Verdict: PASS

Critical findings: 0
High findings: 0
Medium findings: 0
Low findings: 0
Targeted rereview: not used

| # | Hostile attack | Evidence checked | Result |
|---:|---|---|---|
| 1 | A branch-local V0R5 artifact self-executes | Canonicalization requires exact canonical presence; no activation artifact is created; focused test rejects the artifact from canonical `f2a3e7a` history | PASS |
| 2 | Historical `a392` contract is accepted as final | Successor binding authorizes only `50bd…`; `a392…` is explicitly historical/rejected | PASS |
| 3 | Caller bypasses the production materializer | Successor contract and authorization bind the materializer as the only production DSH_HOME authority | PASS |
| 4 | Caller supplies arbitrary persistent DSH_HOME | Fresh empty destination is required; caller-selected persistent DSH_HOME is false | PASS |
| 5 | Ambient scratch home re-enters as authority | Ambient path is forbidden and fallback/repair/backfill are false | PASS |
| 6 | Materializer or home-manifest identity is omitted | Materializer, schema, production home, whole-home identity, and recomputed materializer digest are bound | PASS |
| 7 | Runtime or executable identity drifts | Pinned repository/commit/tree/tag, lockfile, runtime manifest, executable, launcher, and policy digests are frozen | PASS |
| 8 | V0R4 claim namespace is reused | Fresh V0R5 remote/local tuple differs and the V0R4 ref is rejected | PASS |
| 9 | V0R4 episode is replayed or reopened | V0R4 is closed/immutable, unclaimed, unconsumed, non-rerunnable, and non-reopenable | PASS |
| 10 | Secret is read before non-secret gates | Secret reads are zero; ordering places secret injection after all non-secret gates | PASS |
| 11 | Claim is created before secret/gates | Claim is absent during authorization; ordering is secret, then create-only claim, then DSH | PASS |
| 12 | Partial/ambiguous claim is retried | Ambiguous state is `BLOCK_NEVER_REPLAY`; deletion/reset/force-update are forbidden | PASS |
| 13 | Parent request/spend limits expand | Parent is fixed at 8 requests, 0 retries, no continuation, 4096 output tokens, $1.00 hard cap | PASS |
| 14 | Codex/Claude turn limits expand | Each child controller is capped at 2 turns | PASS |
| 15 | Claude gains write/delegation capability | Claude is limited to Read/Glob/Grep with write, shell, agent, task, MCP, question, and delegation denial | PASS |
| 16 | Fixture scope expands | Exact `STAGE_A_BOUNDED_RETRY_V0` digest and disposable mutable-target-only policy are bound | PASS |
| 17 | Authorization creates activation/live authority | Firewall and registry both set activation/effective/live authority false; active project is NONE | PASS |
| 18 | V0R5 is created during authorization | `v0r5_created`, activation, claim, execution, and all construction receipts are false/zero | PASS |
| 19 | Stage B/Qnty/scientific/trading authority leaks | Stage B, scientific, trading, capital, promotion, production, and Qnty authority are explicitly denied | PASS |
| 20 | Successor contract substitution is undetected | Contract path/hash/digest and all required identities are recomputed by focused tests | PASS |

No repair was required. The review is closed without a rereview loop.
