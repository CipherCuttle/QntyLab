# Independent hostile implementation review — final provider-boundary closeout V0

Review count: exactly one. This review was performed after implementation and
deterministic tests, with no product process or app-server invocation.

## Attacks and disposition

- Test-only repair: PASS. The materializer reads and patches the actual pinned
  `packages/subagent/subagent-codex/src/wire.ts` provider seam and emits a
  source-controlled repaired copy.
- Wrong source accepted: PASS. Commit, tree, tag, clean tracked status,
  whole-file digest, exact `startThread` span digest, and postimage digest are
  all fail-closed gates.
- Fuzzy patching: PASS. The exact preimage span and unique two-line insertion
  are required; no context broadening or fallback exists.
- Approval/sandbox asymmetry: PASS. Both `approvalPolicy = never` and
  `sandbox = workspace-write` are emitted exactly once.
- Hidden product delta: PASS. `cwd` and `ephemeral` remain unchanged;
  initialize, turn/start, network, model, prompt, task, and text elements are
  represented as unchanged; forbidden permission fields are absent.
- Trust/Profile/CODEX_HOME mutation: PASS. The implementation only reads
  upstream source and writes a separate output root; no configuration or trust
  path is addressed.
- API-key route or live execution: PASS. The module contains no app-server or
  product launch path; tests use source fixtures and temporary output only.
- Fake desired dictionary: PASS. Tests call the materializer and parse the
  materialized provider bytes before validating the captured request shape.
- Duplicate policy/fallback: PASS. The exact method has one occurrence of each
  authorized policy field and malformed construction raises.
- Historical rewrite: PASS. B/C/D and prior authorization artifacts are read
  only and remain immutable.
- Trust uncertainty as blocker: PASS. The forensic result is conservative,
  `TRUST_TIMING_UNRECOVERABLE`, and repair proceeds as authorized.
- Closure loophole: PASS. Final outcome is a closed conservative repair;
  project state is NONE after closure and NEXT_ACTION returns to parent work
  after PR #164 merge. No #165 or further permission phase is authorized.

Critical: 0

High: 0

Targeted rereview: NOT USED. No Critical/High repair was required.

Conclusion: ACCEPTABLE FINAL CLOSEOUT IMPLEMENTATION.
