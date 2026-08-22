# Hostile governance review — fresh V1R3R2 authorization V0R2

Review type: exactly one independent hostile review after the focused candidate was stable.

Reviewed candidate:

- authorization project: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R2`
- future execution project: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R2`
- canonical base: `276c1706c02bdb4fcc0d3e688c371e20fcee2065`
- review input: V0R2 authorization artifact, registry row, generated roadmap, focused V0R2 tests, project-context projection, exact remote claim-ref probe, and the frozen V1R3R2 runtime/fixture inputs
- pre-review focused result: `15 passed`
- relevant regression result: `148 passed, 1 deliberately deselected stale historical SHA assertion`

## Adversarial checks

| Attack | Result | Evidence |
| --- | --- | --- |
| V0R1 authorization can be reused accidentally | PASS | V0R2 authorization and execution IDs are fresh; both V0 and V0R1 historical IDs are explicitly rejected; `rerun_authorized=false`. |
| Historical claim identity can satisfy V0R2 | PASS | V0R2 has a distinct claim ref; both historical refs are rejected; exact `git ls-remote` probe returned absent. |
| V0R1 activation can satisfy V0R2 | PASS | V0R2 requires a separate activation identity and records `old_authorization_or_activation_satisfies=false`. |
| Authorization self-activates or branch-local bytes become effective | PASS | Canonical merge is required, branch-local authorization cannot self-authorize, no activation artifact exists, and the project-context projection has no active project. |
| Ambient `OPENAI_API_KEY` bypasses explicit binding | PASS | Ambient checking is explicitly insufficient; the frozen mechanism is `spawnDsh(..., { extraEnv: { OPENAI_API_KEY: value } })`. |
| Secret is read before non-secret gates or missing secret claims the episode | PASS | Ordered action-time sequence places the approved local read after non-secret gates and before claim; missing/unreadable/empty/binding failures block before claim. |
| Provider I/O occurs before claim | PASS | Claim creation is create-only and both remote ref plus exclusive receipt must complete before provider adapter I/O. |
| Claim ambiguity or unknown write state enables replay | PASS | Partial and unknown write states are `BLOCK_NEVER_REPLAY`; force update and deletion-based recovery are not permitted by the contract. |
| Secret leaks to Claude or artifacts | PASS | Child inheritance is false, Claude has no secret-bearing route, construction `REAL_SECRET_READ` is false, and no credential-like value is present in the serialized artifact. |
| Provider, model, or route broadens | PASS | Exact `openai` / `gpt-5-mini` / `llm-pi-ai` binding is frozen; alternate, model-substitution, auxiliary, title, and compaction routes are disabled. |
| Request, spend, or child budgets broaden | PASS | Eight parent attempts, zero retries/continuation, 4,096 tokens/request, $1.00 ceiling, and Codex/Claude ceilings of two each are frozen. |
| Claude regains write capability | PASS | Only Read/Glob/Grep are allowed; Write/Edit/Bash/Agent/Task/MCP/question/delegation are denied with strict empty settings. |
| Runtime or fixture identity drifts | PASS | The exact frozen DSH commit/tree/tag and four launch digests plus fixture ID/digest match the supplied qualified inputs; direct drift fails closed. |
| Stage B, Qnty, trading, capital, promotion, or evaluator authority leaks | PASS | All downstream firewall fields remain denied or `NONE`; evaluator is `NOT_APPLICABLE`. |
| V0R2 replays after closure or grants a second episode | PASS | Exactly one episode, no whole-episode retry, timeout never restores authority, one closure PR budget, and terminal construction receipts all remain bounded. |

## Findings

```text
Critical = 0
High = 0
Medium = 0
Low = 0
```

No Critical or High repair was required. The targeted rereview allowance was not used. No review recursion is authorized.

The broader regression also reproduced one pre-existing stale historical test assertion expecting the pre-PR-188 SHA; it was deliberately not modified because it is outside the V0R2 changeset and does not affect the V0R2 focused contract or doctor. This is recorded as a verification warning, not a hostile-review finding.

## Review disposition

`PASS`: freeze this authorization candidate only. This review creates no activation, claim, secret read, provider/model I/O, DSH invocation, fixture mutation, Stage-B authority, Qnty authority, trading authority, capital authority, promotion authority, or scientific execution authority.
