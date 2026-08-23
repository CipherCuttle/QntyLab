# Independent hostile governance review — Stage-A V1R3R2 V0R3 activation

Review scope: the exact V0R3 activation candidate, its authorization artifact,
the project-context execution-authority projection, the registry row, and the
focused V0R3 tests. This review is limited to governance construction; no
secret, claim, runtime, provider, child, fixture, or spend path was invoked.

| Attack | Result |
| --- | --- |
| Branch-local activation becomes effective | PASS — projection requires clean checkout at `origin/master`; candidate is ineffective. |
| Wrong authorization, byte drift, Git blob drift | PASS — V0R3 authorization ID, raw SHA-256, and Git blob SHA are bound and fail closed. |
| e168 or launch-policy substitution | PASS — both exact digests and canonical artifact SHA-256 values are bound. |
| V0/V0R1/V0R2/V0R2R1, PR #189, or historical claim resurrection | PASS — all historical identities and claim refs are rejected. |
| Claim creation, secret read, provider/model call during activation | PASS — absence preflight and zero construction/activity receipts are required. |
| More than one project or episode; activation consumes episode | PASS — one ACTIVE row, one V0R3 episode, unclaimed/unconsumed, no second episode or rerun. |
| Parent or child budget widening | PASS — OpenAI/gpt-5-mini/llm-pi-ai, 8 attempts, zero provider retries, 4096 output tokens, USD 1.00 hard cap, and exact child machine are bound. |
| Claude write escape or Codex repository write escape | PASS — Claude is Read/Glob/Grep only; Codex is limited to the disposable fixture workspace. |
| Workspace containment or canonical fixture mutation | PASS — fresh disposable workspace/home/copy and realpath containment are required; fixture digest and immutable paths are bound. |
| Timeout/replay escape | PASS — 1800 seconds, no rerun, and BLOCK_NEVER_REPLAY are bound. |
| Stage B/Qnty/scientific/trading/capital/promotion leakage | PASS — authority firewall remains closed. |

Critical findings: 0
High findings: 0
Medium findings: 0
Low findings: 0

Verdict: PASS. No targeted rereview is required.
