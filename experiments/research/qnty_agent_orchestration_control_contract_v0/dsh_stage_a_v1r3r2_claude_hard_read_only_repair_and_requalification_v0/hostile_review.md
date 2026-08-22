# DSH Stage-A V1R3R2 hostile review

Review count: 1
Review mode: independent hostile pass after implementation, materialization, tests, qualification, and digest generation.
Verdict: PASS

| Attack surface | Result |
| --- | --- |
| Wrong canonical base or dirty starting tree | PASS — branch was created from exact `origin/master` `ba74eb17aece6d37a21189ab0671c98282df0fed`; predecessor episode remains unclaimed/unconsumed. |
| Wrong DSH repository, commit, tree, or tag | PASS — canonical materializer verifies all four before patching. |
| Reuse of stale V1R3R1 runtime or authority | PASS — fresh detached materialization; old qualified digest is explicitly superseded and incompatible. |
| Claude write/edit/bash escape | PASS — `tools` and `allowedTools` are exactly `Read`, `Glob`, `Grep`; explicit deny list covers write, edit, bash, delegation, task, MCP, and user-dialog paths. |
| Settings or MCP reintroduction | PASS — `settingSources: []`, empty `mcpServers`, empty `agents` and `plugins`, and `strictMcpConfig: true`. |
| Permission prompt bypass ambiguity | PASS — `permissionMode: 'dontAsk'` is bound at the official query-options seam and covered by the direct test. |
| Claude policy not reaching `officialQuery()` | PASS — the 24-test Claude package suite includes an options-capture assertion at the real seam. |
| Codex repair accidentally lost | PASS — predecessor Codex patch is reused and applied first; Codex suite is 32/32. |
| Unpinned SDK or dependency drift | PASS — SDK package identity, lockfile digest, pnpm declaration, actual version, and executable digest are recorded. |
| Partial or noncanonical build | PASS — offline frozen install and full `pnpm run build:lib` both pass from the fresh source. |
| Launcher path/workspace confusion | PASS — phase wrapper reuses the verified launcher; decisive run has matching real workspace and session cwd. |
| Parent call multiplication or retry | PASS — exactly one loopback request; zero auxiliary, external, paid, and retry requests. |
| Unexpected model-facing tools or child turns | PASS — exact contract is `subagent_codex`, `subagent_claude_code`; zero child model turns and no tool-call response. |
| Secret, live Stage-A, Stage B, or spend leakage | PASS — no real secret read, zero live episodes, zero Stage B, zero spend; evidence is configuration plus observation and makes no kernel guarantee. |
| Digest substitution or mutation blindness | PASS — runtime/executable/launch/qualified digests are emitted; five policy/binding mutations change the bound launch and qualified digests. |

No Critical, High, Medium, or Low findings were found.
Targeted rereview: NOT_REQUIRED.
No live DSH launch, real model call, secret read, merge, or Stage-B action was performed.
