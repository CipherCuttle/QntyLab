# DSH Stage-A V1R3R2 V0R4 activation hostile review

Review type: exactly one independent hostile review of the frozen activation
candidate and focused tests.

Scope: authorization substitution, canonical-byte binding, activation
projection, composite launcher binding, runtime identity, claim ordering,
secret boundary, budget enforcement, child policy, workspace containment,
timeout/replay, and downstream authority escalation.

| Attack | Result | Evidence |
| --- | --- | --- |
| Authorization artifact substitution | PASS | Activation binds the V0R4 authorization project, path, canonical merge, SHA-256, and Git blob identity. |
| Authorization digest not checked | PASS | `project_context` recomputes canonical authorization bytes and the V0R4 test asserts the exact digest. |
| Branch-local activation becomes effective | PASS | Candidate projection is `active_project = None`; synthetic candidate projection is ineffective. |
| More than one effective active project | PASS | Registry has one ACTIVE candidate row; synthetic canonical projection returns exactly V0R4. |
| a392 downgrade to e168 | PASS | a392 is the only authorized digest; e168 is rejected as historical. |
| Physical launcher substitution | PASS | Physical launcher path is explicitly distinct and the composite path/digest are exact. |
| Historical Stage-A launcher substitution | PASS | Historical policy launcher path is explicitly distinct and rejected. |
| Composite launcher path/digest bypass | PASS | Exact composite path and SHA-256 are bound and tested. |
| Forged preflight receipt | PASS | Immediate/pre-spawn validation is part of the frozen gate order; no caller-selected wrapper is authorized. |
| Action-time wrapper bypass | PASS | Composite launcher binding requires the single qualified boundary and immediate revalidation. |
| Runtime identity drift | PASS | Pinned source commit/tree/tag and runtime manifest digest are registry-parity bound. |
| Executable identity drift | PASS | Exact executable identity digest is bound to the composite contract and registry. |
| Stale V0R3 claim reuse | PASS | V0R3 project, episode, and claim namespace are rejected; V0R3 closure remains CLOSED_BLOCKED. |
| Fresh claim collision | PASS | Remote claim, local state directory, lock, intent, and receipt are absent at construction. |
| Claim created during activation | PASS | Construction receipt records zero claims and the claim contract forbids construction-time creation. |
| Real secret accessed during activation | PASS | Secret metadata only; activation receipt records zero real secret reads. |
| Secret read before non-secret gates | PASS | Secret read follows all non-secret gates in the explicit order. |
| Claim before secret | PASS | Secret binding precedes durable intent and create-only claim steps. |
| Provider before complete claim | PASS | Complete claim precedes first potentially paid parent dispatch. |
| Spend-cap widening | PASS | Parent is capped at eight logical attempts and USD 1.00 with attempt 9 denied. |
| Alternate model/provider | PASS | Alternate provider and model substitution are false; auxiliary routes are empty. |
| Child count widening | PASS | Codex and Claude maxima are both two with no background delegation. |
| Claude permission escape | PASS | Claude is restricted to Read/Glob/Grep with denied write, shell, agent, task, MCP, and delegation surfaces. |
| Codex workspace escape | PASS | Codex writes are limited to the fresh disposable Stage-A fixture workspace. |
| Timeout/replay escape | PASS | Timeout, crash, and unknown claim state are BLOCK_NEVER_REPLAY with no rerun. |
| Stage B/Qnty/science/trading/capital escalation | PASS | All downstream authority firewall fields are closed. |
| Historical closure mutation | PASS | V0R3 remains CLOSED_BLOCKED with BLOCK_RUNTIME_IDENTITY and no rerun authority. |

Review counts: Critical 0, High 0, Medium 0, Low 0.

Targeted rereview: not used; no Critical/High repair was required.

Verdict: PASS.

## Targeted rereview after Critical/High repair

The only repair added canonical-merge byte verification for the V0R4
authorization and a regression test that mutates local authorization bytes.
The targeted rereview re-ran that hostile substitution path, canonical
authorization SHA-256 binding, and branch-local projection.

Result: PASS. Critical 0, High 0, Medium 0, Low 0. No further review is
authorized or performed.
