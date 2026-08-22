# Hostile review — DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0

One independent hostile pass over the real qualification evidence in this
directory (`PHASE.md`, `qualification.json`, `evidence/`), run after that
evidence existed, per the phase's bounded-completion policy.

## Checklist

- **Source actually pinned?** Yes. `git rev-parse HEAD` = the exact pinned
  commit; `git rev-parse HEAD^{tree}` = the exact pinned tree; `git tag
  --points-at HEAD` includes the exact pinned tag; working tree clean at
  checkout time. Verified via real `git`, not a trust label.
- **Dependency store/lockfile drift?** None. `pnpm fetch --frozen-lockfile`
  then `pnpm install --offline --frozen-lockfile`, both against the same
  dedicated store; the lockfile was never written to; its digest is recorded
  in `evidence/runtime_manifest.json` / `evidence/digests.json`.
- **Build output really from the same runtime root?** Yes. `builtCliDigest`
  in the manifest is computed by hashing the real file at
  `<materializationRoot>/apps/cli/lib/bin.js` at manifest-build time, not
  borrowed from elsewhere (this is the exact V1R2 failure mode #176's
  materializer was built to prevent, and this run exercised that code path
  for real for the first time).
- **Codex patch actually compiled?** Yes. `packages/subagent/subagent-codex`
  built cleanly after the patch; its own 32-test suite passes;
  `packages/subagent/subagent-codex/lib/index.js` was read directly and
  shows `resolveExecutable("codex", this.config.env, request.signal)`
  feeding `codexAppServerArgv(spec.executable)`, which places the resolved
  value at `argv[0]`.
- **Actual spawn absolute?** Proven by static inspection of the compiled
  output, not by a live OS-level spawn trace — **this phase does not, and
  per its own boundary must not, ever actually invoke
  `subagent_codex`/`subagent_claude_code`** (`CODEX_ACTUAL_TASK_CALLS =
  CLAUDE_ACTUAL_TASK_CALLS = 0` is a hard requirement, and the mock's one
  response is plain-text with no tool call). Flagging this distinction
  explicitly rather than implying a live spawn was traced: the evidence is
  "the compiled code path pins an absolute resolved path into argv before
  spawn," not "a spawned process was observed with that argv0."
- **Caller cwd leaks?** No. The same preflight+spawn path was run from three
  different caller cwds (QntyLab repo root, the DSH source root, an
  unrelated scratch directory); `preflightResult.workspaceReal` and the
  spawned child's actual `cwd` were identical in all three, and the
  decisive parent-mock run's session header (see below) confirms it for the
  real boot.
- **Session cwd actually proven?** Yes, from real state, not argv inference:
  the written session's own JSONL header line was decompressed and read
  directly — `"cwd":"/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/
  workspace/run1"` — and the session directory name itself independently
  encodes the same path.
- **Full-profile path genuinely traversed?** Yes: canonical launcher → real
  materialized runtime → built CLI → real `headless` profile composition
  (Cordis plugin tree, including the two native subagent providers) → real
  Agent/session creation → a real `llm-pi-ai` `openai-completions` HTTP
  request → the loopback mock → a clean `turn/end` settlement → exit 0. This
  is not a `--help`/`--dump-config` smoke test; it is the actual `dsh
  --profile headless "<task>"` boot path a live episode would use.
- **Local mock genuinely used by llm-pi-ai?** Yes — the captured request
  body was inspected directly: `model: "gpt-5-mini"`, `tools:
  ["subagent_claude_code", "subagent_codex"]`, and the mock's own SSE
  response was what produced the stdout text the process printed.
- **Second hidden request?** Two were found and eliminated during this
  phase, not silently worked around: a session-title-generation request
  (disabled `session-title-llm`) and a broader default tool surface than the
  spec's exact two tools (disabled every other default model-facing tool
  row, including `plan-mode`'s `exit_plan_mode`). The decisive run now shows
  exactly one wire request.
- **External network leakage?** **Evidence level, stated honestly**: no
  network namespace or firewall isolation was applied — this environment's
  qualification ran under configuration-plus-observation evidence only,
  exactly as PHASE.md/qualification.json describe. The `openai` route's
  `baseURL` was explicitly overridden to the loopback mock's own ephemeral
  `127.0.0.1` address, the credential was a fake, obviously-non-functional
  string, and the mock's request log shows exactly one request, from the DSH
  process, to itself. This is real but bounded evidence: it does not
  constitute a cryptographic or kernel-level guarantee that no other
  outbound connection was attempted or could have succeeded, only that the
  one configured route pointed at loopback and the one request observed
  came through it. **MEDIUM** — recorded as a named evidence-level limit,
  not silently overclaimed as stronger isolation.
- **Real secret accidentally read?** No. `~/.secrets/openai_api_key_stage_a`
  was never referenced by any command in this phase; the credential used was
  the literal string `sk-qualification-only-fake-not-real`, set directly in
  the qualification driver's own spawned-child environment.
- **Digest omits a critical immutable identity?** No known omission: source
  commit/tree/tag, lockfile digest, repair-patch digest, built-CLI digest,
  all four executable digests, launcher/materializer/overlay/budget-gate
  digests, parent provider/model, exact tool-surface list, workspace
  containment policy description, argv schema, and budget/retry policy are
  all digest inputs (see `evidence/compute-digests.mjs`).
- **Digest includes ephemeral paths incorrectly?** No — `materializationRoot`,
  `materializedAtUtc`, and every absolute scratch path were deliberately
  excluded from every digest's input; only the relative `builtCliRelativePath`
  (`apps/cli/lib/bin.js`) and content digests are hashed.
- **False `CLOSED_PASS`?** Not found — every required acceptance item in
  `qualification.json` has real, inspectable evidence behind it as described
  above and in `PHASE.md`.
- **Accidental live/Stage-B authority?** No — nothing in this phase's
  artifacts authorizes Stage B, a live episode, or grants any authority
  beyond `DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0` itself; closure
  sets `ACTIVE_PROJECTS = NONE` with no successor project.

## Additional finding (procedural, not in the checklist template)

- **`~/.dsh` touched outside the authorized scratch root.** One intermediate
  diagnostic command in this phase omitted `DSH_HOME` and landed against the
  operator's real, pre-existing `~/.dsh` profile home instead of the scratch
  root. Its effects were idempotent (a symlink-farm refresh and a templated
  root-file rewrite DSH performs on every ordinary boot) plus two symlinks
  this phase's own driver added there for the two subagent packages, which
  were identified and removed immediately upon discovery, before any further
  qualification work. No session, credential, or settings data under
  `~/.dsh` was created, altered, or deleted. **MEDIUM** — a real boundary
  slip, self-caught and remediated within the same phase, documented here
  and in `PHASE.md` rather than omitted. Every subsequent command in this
  phase explicitly sets `DSH_HOME` to the scratch root.

## Outcome

No **Critical** or **High** finding. Two **Medium** findings, both already
addressed: the network-isolation evidence-level limit is stated honestly
rather than overclaimed (no code/process change applicable — it is an
environment capability limit), and the `~/.dsh` boundary slip was corrected
immediately. Per the bounded-completion policy, no targeted rereview is
required (no Critical/High fix was made that would need one).
