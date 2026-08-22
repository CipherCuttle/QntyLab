# Hostile governance review — Stage-A V1R3R2 authorization V0R3

Review type: exactly one independent, read-only hostile governance review after
the authorization artifact and focused tests were frozen.

Reviewed candidate:

- authorization project: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R3`
- future activation project: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3`
- episode: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R3#EPISODE_1`
- qualified contract: `e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82`
- canonical base: `52ae5fe3a7df10a7b35d04789d6c0ce509e74b04`
- review input: staged authorization, canonical `e168` contract, fresh focused tests, and the staged registry row

The review was repository-read-only. It made no file change, read no real
secret, created no claim, invoked no DSH or native child, made no provider
request, and incurred no spend.

## Adversarial checks

| Attack | Result | Evidence |
| --- | --- | --- |
| Stale `e3b` or `c98` contract accepted as current | PASS | Both digests, plus the predecessor `5716` digest, are explicitly rejected; only `e168` is bound. |
| Prior V0/V0R1/V0R2/V0R2R1 authorization or activation substitutes | PASS | All historical authorization, activation, episode, and claim identities are listed as rejected; the fresh tuple is V0R3. |
| Fresh identity collision or second episode | PASS | Authorization, execution, episode, and claim ref are a new V0R3 tuple with `episode_count=1` and no second episode. |
| Branch-local authorization becomes effective | PASS | Canonical base and merge are bound to `52ae…`; branch-local presence cannot authorize activation or execution. |
| Authorization implicitly creates activation | PASS | No activation artifact exists; activation creation is a separate phase and the projection remains inactive. |
| Secret read, claim, provider/model call, child turn, or spend during construction | PASS | All construction counters are zero and the secret is represented only by source path and gate policy. |
| Budget ceiling or retry/continuation bypass | PASS | Parent is fixed to OpenAI `gpt-5-mini`, route `llm-pi-ai`, 8 attempts, 0 provider retries, no continuation, 4096 output tokens, and hard `$1.00` cap. |
| Child count or sequence bypass | PASS | Codex and Claude maxima are both 2; reservation and invalid-transition gates are required. |
| Claude write/Bash/MCP/delegation escape | PASS | Claude is hard read-only with only `Read`, `Glob`, and `Grep`; denied classes and empty MCP/plugin/agent settings are frozen. |
| Secret gate occurs after non-secret gates and before claim | PASS | The action-time order places secret availability/read after all identity/firewall gates and before create-only claim and provider I/O. |
| Claim overwrite/replay or timeout rerun | PASS | Create-only remote ref, durable intent, exclusive receipt, no force update/delete/reset, `BLOCK_NEVER_REPLAY`, and no rerun are frozen. |
| Runtime or launcher substitution | PASS | Exact e168-bound source commit/tree/tag, lockfile, patches, entrypoint, manifest, executable, launcher, materializer, and launch-policy identities are recorded. |
| PR #189 substitutes for authority | PASS | PR #189 is recorded noncanonical and `SUPERSEDED_NOT_MERGEABLE`; substitution is false for authorization, execution, claim, and digest. |
| Stage B/Qnty/scientific/trading/capital/promotion leakage | PASS | All downstream authority fields are false or `NONE`; `ACTIVE_PROJECT` remains `NONE`. |

## Findings

```text
Critical = 0
High = 0
Medium = 0
Low = 0
```

No Critical or High repair was required. The targeted rereview allowance was
not used, and no review recursion is authorized.

## Review disposition

`PASS`: freeze this authorization candidate only. This review creates no
activation, effective live authority, claim, secret read, provider/model I/O,
DSH invocation, native child turn, fixture mutation, Stage-B authority, Qnty
authority, trading authority, capital authority, promotion authority,
scientific execution authority, or broader production deployment authority.
