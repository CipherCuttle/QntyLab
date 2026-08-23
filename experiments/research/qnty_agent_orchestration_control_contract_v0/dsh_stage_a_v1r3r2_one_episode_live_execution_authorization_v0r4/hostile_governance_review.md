# Hostile governance review — Stage-A V1R3R2 authorization V0R4

Review type: exactly one independent, read-only hostile governance review after
the V0R4 authorization artifact, focused tests, and registry/roadmap entries
were frozen.

Reviewed candidate:

- authorization project: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_AUTHORIZATION_V0R4`
- future activation project: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4`
- episode: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4#EPISODE_1`
- qualified contract: `a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be`
- composite launch policy: `7345ab145a0c98696ce8b9e6d815f4da98092f7be680467278464fb098a51589`
- composite launcher: `6f212de0576127fea1dd2778a69c49a3b755a017a9d55f97f18b9057dc15c329`
- canonical base: `add590cac0afebd9666a3453b38ae19866b9dea5`

The review was repository-read-only. It made no file change, read no real
secret, created no claim, invoked no DSH or native child, made no provider
request, and incurred no spend.

## Adversarial checks

| Attack | Result | Evidence |
| --- | --- | --- |
| Downgrade from `a392` to `e168`, `e3b`, `c98`, or `57162` | PASS | Only `a392` is current; all four historical digests are explicitly rejected. |
| Accept the physical-runtime launcher as the composite boundary | PASS | The exact composite path/digest are required and the physical launcher alone is false. |
| Accept the historical Stage-A launcher as the composite boundary | PASS | The historical launcher alone is explicitly rejected. |
| Bypass immediate pre-spawn revalidation with a wrapper or supplied receipt | PASS | The composite binding requires one boundary and rejects bypass. |
| Substitute runtime manifest, executable, source, lockfile, or built CLI | PASS | Exact runtime, executable, source, lockfile, and built CLI identities are frozen from the canonical contract. |
| Collide with authorization, execution, episode, or claim identity | PASS | Fresh V0R4 IDs and claim paths are absent from canonical history, remote claim state, and local state at construction. |
| Reuse V0R3 authorization, activation, episode, or claim tuple | PASS | V0R3 closure is preserved as `CLOSED_BLOCKED / BLOCK_RUNTIME_IDENTITY` and every lineage is rejected. |
| Turn branch-local authorization into effective authority | PASS | Canonical merge is `add590…`; branch-local presence cannot self-authorize. |
| Collapse authorization into activation or active execution | PASS | No activation artifact exists; construction is ineffective and `ACTIVE_PROJECT` remains `NONE`. |
| Read the secret, create a claim, call a provider/model, or spend during construction | PASS | Construction counters are all zero and the secret is represented only by path and ordering policy. |
| Widen parent provider/model/route, attempts, retries, output, or spend | PASS | OpenAI `gpt-5-mini` / `llm-pi-ai`, 8 attempts, 0 retries, no continuation, 4096 output tokens, and hard `$1.00` are frozen. |
| Bypass child sequence or counts | PASS | Exact Codex→Claude→optional Codex repair→optional Claude rereview state machine, max 2 each, and no alternate/background route. |
| Escape Claude read-only policy | PASS | Only `Read`, `Glob`, and `Grep` are allowed; write/edit/bash/agent/task/MCP/delegation surfaces are denied. |
| Read secret before non-secret gates or claim | PASS | Gate order places secret read after all non-secret gates and before claim completion/provider I/O. |
| Replay after timeout, crash, or ambiguous claim state | PASS | `BLOCK_NEVER_REPLAY`, no rerun/rescue, create-only/no-overwrite claim semantics, and deletion/reset/force-update prohibition are frozen. |
| Leak Stage B, Qnty, science, trading, capital, promotion, or production authority | PASS | All downstream firewall fields are false or `NONE`; no active project is created. |

## Findings

```text
Critical = 0
High = 0
Medium = 0
Low = 0
```

No Critical or High repair was required. The targeted rereview allowance was
not used, and no review recursion is authorized.

## Review verdict

`PASS`: freeze this authorization candidate only. This review creates no
activation, effective live authority, claim, secret read, provider/model I/O,
DSH invocation, native child turn, fixture mutation, Stage-B authority, Qnty
authority, trading authority, capital authority, promotion authority,
scientific execution authority, or broader production deployment authority.
