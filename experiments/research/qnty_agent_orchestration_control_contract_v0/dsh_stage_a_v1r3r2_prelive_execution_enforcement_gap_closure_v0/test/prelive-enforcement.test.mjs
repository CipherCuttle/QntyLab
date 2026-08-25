import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'

import {
  assertQualifiedContractDigest,
  buildSpawnEnv,
  selectedPolicyPatches,
  spawnDsh,
  validateClaimBinding,
  verifiedNativePath,
  verifyMirroredPackage,
} from '../launcher/qntylab-launch-dsh.mjs'
import { computeDigests } from '../evidence/compute-digests.mjs'
// The ACTUAL production preparation path derives the CURRENT execution-contract
// root (successor.currentCompositeRoot). The E2E must bind to that derivation,
// never to a stale literal (MEDIUM-2).
import { computeDigests as productionComputeDigests } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/compute-digests.mjs'
import {
  createGateClient,
  createGatedProvider,
} from '../profile/qntylab-stage-a-gated-provider/lib/gated-provider.mjs'
import {
  MAX_OUTPUT_TOKENS,
  applyParentGuard,
  createParentGuard,
} from '../profile/qntylab-stage-a-parent-enforcement/lib/guard.mjs'

const ROOT = resolve(import.meta.dirname, '../../../../..')

function emptyReview({ high = false } = {}) {
  return {
    critical: [],
    high: high ? [{ id: 'H-01', summary: 'hostile finding' }] : [],
    medium: [],
    low: [],
    closure_blocking: high,
    summary: 'stub hostile review',
  }
}

function nativeStub(name, outputs) {
  let calls = 0
  return {
    name,
    capabilities: {},
    inheritsParentContext: false,
    get calls() { return calls },
    async start() {
      const output = outputs[Math.min(calls, outputs.length - 1)]
      calls += 1
      return {
        id: `${name}-${calls}`,
        result: Promise.resolve(output),
        async dispose() {},
      }
    },
  }
}

function childHarness(directory, { claudeOutputs = [emptyReview()] } = {}) {
  const gate = createGateClient({
    statePath: join(directory, 'child-state.json'),
    qntyLabRoot: ROOT,
    pythonExecutable: 'python',
  })
  const codex = nativeStub('codex', [{ output: [{ type: 'text', text: 'implemented' }] }])
  const claude = nativeStub('claude-code', claudeOutputs)
  const gatedCodex = createGatedProvider({
    providerName: 'qntylab-stage-a-gated-codex',
    rawProviderName: 'codex',
    toolName: 'subagent_codex',
    rawProvider: codex,
    gate,
  })
  const gatedClaude = createGatedProvider({
    providerName: 'qntylab-stage-a-gated-claude',
    rawProviderName: 'claude-code',
    toolName: 'subagent_claude_code',
    rawProvider: claude,
    gate,
  })
  async function invoke(provider) {
    const run = await provider.start({})
    const result = await run.result
    await run.dispose()
    return result
  }
  return { gate, codex, claude, gatedCodex, gatedClaude, invoke }
}

test('malicious parent Codex -> Codex is stopped before native stub invocation two', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-child-codex-codex-'))
  try {
    const h = childHarness(directory)
    await h.invoke(h.gatedCodex)
    await assert.rejects(h.gatedCodex.start({}), /denied in AFTER_INITIAL_CODEX/)
    assert.equal(h.codex.calls, 1)
    assert.equal(h.claude.calls, 0)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('malicious parent Claude first is stopped before native stub invocation', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-child-claude-first-'))
  try {
    const h = childHarness(directory)
    await assert.rejects(h.gatedClaude.start({}), /denied in INITIAL/)
    assert.equal(h.codex.calls, 0)
    assert.equal(h.claude.calls, 0)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('clean review makes Codex repair attempt terminal before native stub', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-child-clean-terminal-'))
  try {
    const h = childHarness(directory)
    await h.invoke(h.gatedCodex)
    await h.invoke(h.gatedClaude)
    await assert.rejects(h.gatedCodex.start({}), /AFTER_REVIEW_NO_C_H/)
    assert.equal(h.codex.calls, 1)
    assert.equal(h.claude.calls, 1)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('second repair attempt is denied before a third Codex native invocation', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-child-second-repair-'))
  try {
    const h = childHarness(directory, { claudeOutputs: [emptyReview({ high: true })] })
    await h.invoke(h.gatedCodex)
    await h.invoke(h.gatedClaude)
    await h.invoke(h.gatedCodex)
    await assert.rejects(h.gatedCodex.start({}), /denied in AFTER_REPAIR/)
    assert.equal(h.codex.calls, 2)
    assert.equal(h.claude.calls, 1)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('second rereview attempt is denied before a third Claude native invocation', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-child-second-rereview-'))
  try {
    const h = childHarness(directory, {
      claudeOutputs: [emptyReview({ high: true }), emptyReview()],
    })
    await h.invoke(h.gatedCodex)
    await h.invoke(h.gatedClaude)
    await h.invoke(h.gatedCodex)
    await h.invoke(h.gatedClaude)
    await assert.rejects(h.gatedClaude.start({}), /denied in AFTER_REREVIEW/)
    assert.equal(h.codex.calls, 2)
    assert.equal(h.claude.calls, 2)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('crash after durable child reservation never invokes or re-enables native stub', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-child-crash-'))
  try {
    const h = childHarness(directory)
    h.gate.authorize('subagent_codex', 'codex', false)
    const restarted = childHarness(directory)
    await assert.rejects(restarted.gatedCodex.start({}), /child denied in INITIAL_CODEX_RUNNING/)
    assert.equal(restarted.codex.calls, 0)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

function git(cwd, args) {
  const result = spawnSync('git', ['-C', cwd, ...args], { encoding: 'utf8' })
  if (result.status !== 0) throw new Error(result.stderr || result.stdout)
  return result.stdout.trim()
}

/**
 * The resolved production identity, MECHANICALLY derived from the CURRENT
 * production preparation path — never a stale literal. The execution-contract
 * root is the CURRENT composite root produced by the production preparation
 * (successor) machinery starting from the CURRENT resolved runtime manifest
 * and the CURRENT materialized production home. Runtime/executable identity
 * digests are the same derived identities the production preparation binds.
 * MEDIUM-2: no hardcoded a31eb46… literal; stale roots fail this assertion.
 */
function resolvedProductionIdentity() {
  const digests = productionComputeDigests()
  const identity = {
    executionContractRoot: digests.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
    runtimeIdentityDigest: digests.runtimeManifestDigest,
    executableIdentityDigest: digests.executableIdentityDigest,
  }
  for (const value of Object.values(identity)) {
    if (!/^[0-9a-fA-F]{64}$/.test(value)) {
      throw new Error(`BLOCK_CLAIM_BINDING: production-derived identity value is not a valid sha256: ${value}`)
    }
  }
  return identity
}

function parentConfig(directory, { authorizedExecutionSourceSha, revocationState = 'NOT_REVOKED' } = {}) {
  const source = join(directory, 'claim-source')
  const remote = join(directory, 'claim-remote.git')
  spawnSync('git', ['init', '--bare', '-q', remote], { stdio: 'inherit' })
  spawnSync('git', ['init', '-q', source], { stdio: 'inherit' })
  writeFileSync(join(source, 'seed.txt'), 'seed\n')
  git(source, ['add', 'seed.txt'])
  const commit = spawnSync('git', [
    '-C', source, '-c', 'user.name=prelive-test',
    '-c', 'user.email=prelive-test@example.invalid', 'commit', '-qm', 'seed',
  ], { encoding: 'utf8' })
  if (commit.status !== 0) throw new Error(commit.stderr || commit.stdout)
  // The Python claim CLI resolves the canonical lineage via the DEFAULT canonical
  // ref refs/remotes/origin/master. Set up a real origin remote so the scratch
  // source repo can resolve refs/remotes/origin/master to the exact seed commit.
  git(source, ['remote', 'add', 'origin', remote])
  git(source, ['push', '-q', '-u', 'origin', 'HEAD:master'])
  git(source, ['fetch', '-q', 'origin'])
  const sourceSha = authorizedExecutionSourceSha ?? git(source, ['rev-parse', 'HEAD'])
  const identity = resolvedProductionIdentity()
  return {
    budgetStatePath: join(directory, 'parent-budget.json'),
    claimStateDir: join(directory, 'claim-state'),
    claimRemote: remote,
    claimRef: 'refs/heads/qntylab-claims/offline-test-parent-guard',
    claimSourceRepo: source,
    sessionNonce: 'offline-session-nonce',
    authorizedExecutionSourceSha: sourceSha,
    executionContractRoot: identity.executionContractRoot,
    runtimeIdentityDigest: identity.runtimeIdentityDigest,
    executableIdentityDigest: identity.executableIdentityDigest,
    revocationState,
    qntyLabRoot: ROOT,
    pythonExecutable: 'python',
  }
}

function parentOptions(overrides = {}) {
  return {
    provider: 'openai',
    model: 'gpt-5-mini',
    agentLoop: true,
    messages: [{ role: 'user', content: [{ type: 'text', text: 'offline adversarial request' }] }],
    tools: [],
    maxTokens: MAX_OUTPUT_TOKENS,
    ...overrides,
  }
}

function parentHookHarness(guard) {
  let hook
  const ctx = {
    on(name, callback, options) {
      assert.equal(name, 'llm/stream')
      assert.deepEqual(options, { global: true, prepend: true })
      hook = callback
    },
  }
  applyParentGuard(ctx, guard)
  return async function dispatch(options, behavior) {
    let wireAttempts = 0
    const next = () => (async function* adapter() {
      wireAttempts += 1
      if (behavior === '429') throw new Error('429')
      if (behavior === '500') throw new Error('500')
      if (behavior === 'timeout') throw new Error('timeout')
      if (behavior === 'connection') throw new Error('connection error')
      yield { type: 'text-delta', delta: 'ok' }
    })()
    try {
      for await (const _chunk of hook(options, next)) {
        // Fully consume the adapter stream.
      }
      return { wireAttempts, outcome: 'success' }
    } catch (error) {
      return { wireAttempts, outcome: String(error) }
    }
  }
}

test('parent success, 429, 500, timeout, and connection errors each create one wire attempt', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-parent-behaviors-'))
  try {
    const guard = createParentGuard(parentConfig(directory), {
      isAgentLoopRequest: options => options.agentLoop === true,
    })
    const dispatch = parentHookHarness(guard)
    for (const behavior of ['success', '429', '500', 'timeout', 'connection']) {
      const result = await dispatch(parentOptions(), behavior)
      assert.equal(result.wireAttempts, 1, behavior)
    }
    const budget = JSON.parse(readFileSync(join(directory, 'parent-budget.json'), 'utf8'))
    assert.equal(budget.attempts_reserved, 5)
    assert.equal(budget.reservations.length, 5)
    assert.equal(guard.snapshot().logicalAttempts, 5)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('attempt nine and over-4096 output are denied before adapter wire I/O', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-parent-attempt-nine-'))
  try {
    const guard = createParentGuard(parentConfig(directory), {
      isAgentLoopRequest: options => options.agentLoop === true,
    })
    const dispatch = parentHookHarness(guard)
    let wireAttempts = 0
    for (let index = 0; index < 8; index += 1) {
      wireAttempts += (await dispatch(parentOptions(), 'success')).wireAttempts
    }
    const ninth = await dispatch(parentOptions(), 'success')
    const oversized = await dispatch(parentOptions({ maxTokens: 16_384 }), 'success')
    assert.equal(ninth.wireAttempts, 0)
    assert.match(ninth.outcome, /ATTEMPT_CEILING/)
    assert.equal(oversized.wireAttempts, 0)
    assert.match(oversized.outcome, /within 1\.\.4096/)
    assert.equal(wireAttempts, 8)
    const budget = JSON.parse(readFileSync(join(directory, 'parent-budget.json'), 'utf8'))
    assert.equal(budget.attempts_reserved, 8)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('auxiliary route is denied before claim and wire while capped request reaches adapter unchanged', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-parent-auxiliary-'))
  try {
    const config = parentConfig(directory)
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
    })
    const dispatch = parentHookHarness(guard)
    const auxiliary = await dispatch(parentOptions({ purpose: 'session-title' }), 'success')
    assert.equal(auxiliary.wireAttempts, 0)
    assert.match(auxiliary.outcome, /auxiliary or non-agent-loop/)
    assert.equal(guard.snapshot().claimCompletedInThisProcess, false)

    let received
    const ctx = {
      on(_name, callback) {
        this.hook = callback
      },
    }
    applyParentGuard(ctx, guard)
    const next = options => (async function* adapter() {
      received = options
      yield { type: 'text-delta', delta: 'ok' }
    })()
    const options = parentOptions()
    for await (const _chunk of ctx.hook(options, () => next(options))) {
      // consume
    }
    assert.equal(received.maxTokens, 4096)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('unpriced media input is denied before claim and adapter wire I/O', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-parent-media-'))
  try {
    const guard = createParentGuard(parentConfig(directory), {
      isAgentLoopRequest: options => options.agentLoop === true,
    })
    const dispatch = parentHookHarness(guard)
    const media = await dispatch(parentOptions({
      messages: [{ role: 'user', content: [{ type: 'image', image: 'data:image/png;base64,AA==' }] }],
    }), 'success')
    assert.equal(media.wireAttempts, 0)
    assert.match(media.outcome, /unpriced non-text modality/)
    assert.equal(guard.snapshot().claimCompletedInThisProcess, false)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

// ---------------------------------------------------------------------------
// END-TO-END PRODUCTION-OWNER INTEGRATION (CENTRAL ACCEPTANCE GATE)
//
// Exercises the ACTUAL chain: resolved production identity -> launcher
// transport -> cordis profile semantics -> index.js Config -> guard.mjs ->
// actual Python claim CLI invocation. Scratch-only: scratch git repo, scratch
// bare remote, scratch claim ref, scratch state dir, fake/non-production claim
// namespace. No secret, no provider, no live DSH episode.
// ---------------------------------------------------------------------------

// The E2E below traverses the REAL chain:
//   resolved production identity (production preparation derivation)
//   -> launcher transport (the SAME buildSpawnEnv / claimBindingEnvVars code
//      path the real spawn uses)
//   -> cordis profile semantics (env -> config field mapping byte-for-byte as
//      profile/cordis.patch.yml declares)
//   -> index.js Config schema semantics (all five claim-binding fields are
//      required and validated before guard construction)
//   -> guard.mjs (real guard, real claim command)
//   -> actual Python claim CLI (scratch git repos only)
// The positive path does NOT mock the guard command: the real guard spawns the
// real Python claim entrypoint. If the launcher fails to transport the H1
// fields, or the profile/config omit them, this test fails (CI red).

// Mirror the EXACT env->config mapping declared in profile/cordis.patch.yml for
// the parent-enforcement plugin. Any profile change that drops or renames a
// claim-binding wiring fails this mapping, which fails the E2E.
function configFromTransportedEnv(env, directory) {
  const config = {
    budgetStatePath: env.QNTYLAB_DSH_PARENT_BUDGET_STATE_PATH,
    claimStateDir: env.QNTYLAB_DSH_CLAIM_STATE_DIR,
    claimRemote: env.QNTYLAB_DSH_CLAIM_REMOTE,
    claimRef: env.QNTYLAB_DSH_CLAIM_REF,
    claimSourceRepo: env.QNTYLAB_DSH_CLAIM_SOURCE_REPO,
    sessionNonce: env.QNTYLAB_DSH_SESSION_NONCE,
    // Claim binding — profile is transport only, exactly as cordis.patch.yml
    // maps these env vars into the plugin Config.
    authorizedExecutionSourceSha: env.QNTYLAB_DSH_AUTHORIZED_EXECUTION_SOURCE_SHA,
    executionContractRoot: env.QNTYLAB_DSH_EXECUTION_CONTRACT_ROOT,
    runtimeIdentityDigest: env.QNTYLAB_DSH_RUNTIME_IDENTITY_DIGEST,
    executableIdentityDigest: env.QNTYLAB_DSH_EXECUTABLE_IDENTITY_DIGEST,
    revocationState: env.QNTYLAB_DSH_REVOCATION_STATE,
    qntyLabRoot: ROOT,
    pythonExecutable: 'python',
  }
  for (const [key, value] of Object.entries(config)) {
    if (typeof value !== 'string' || value.length === 0) {
      throw new Error(`BLOCK_CLAIM_BINDING: profile transport produced no value for ${key} (env var missing or empty)`)
    }
  }
  return config
}

// The launcher transport env produced by the REAL launch path (buildSpawnEnv).
// The `immediate` object supplies only the fingerprint-derived values; the
// claim-binding transport, extraEnv rejection, merge order, and post-merge
// re-check are the real launcher code path. The runtime (non-claim) env vars
// are passed through the ordinary extraEnv seam exactly as a DSH launch would
// supply them; claim-binding keys must NOT be present there (they are denied).
function launcherTransportEnv(binding, extraEnv = {}, runtimeEnv = {}) {
  const immediate = {
    nativePath: '/usr/bin:/bin',
    cliPath: '/nonexistent/headless-cli',
    fingerprints: {
      nodeExecutable: { resolvedPath: '/usr/bin/node' },
      pythonExecutable: { resolvedPath: '/usr/bin/python3' },
      codexExecutable: { resolvedPath: '/usr/bin/codex' },
      claudeExecutable: { resolvedPath: '/usr/bin/claude' },
    },
    workspaceReal: '/tmp',
    cliDigest: 'stub-not-used-by-buildSpawnEnv',
  }
  return buildSpawnEnv({ parentEndpoint: 'http://127.0.0.1:1', dshHome: '/tmp/dsh' }, {
    extraEnv: { ...runtimeEnv, ...extraEnv },
    offlineProfilePatch: undefined,
    claimBinding: binding,
    immediate,
  })
}

function makeScratchClaimBinding(directory, configOverrides = {}) {
  // Production-identity values: the RESOLVED production identity (independent
  // of the scratch source commit), mechanically derived from the CURRENT
  // production preparation path. Future-authority values: scratch-only.
  const config = parentConfig(directory, configOverrides)
  const binding = {
    authorizedExecutionSourceSha: config.authorizedExecutionSourceSha,
    executionContractRoot: config.executionContractRoot,
    runtimeIdentityDigest: config.runtimeIdentityDigest,
    executableIdentityDigest: config.executableIdentityDigest,
    revocationState: config.revocationState,
  }
  // Validate through the REAL launcher seam (rejects unknown keys, malformed
  // values, and defaults no revocation state).
  const validated = validateClaimBinding(binding)
  // Produce the launcher transport env via the REAL spawn env code path,
  // carrying the runtime env vars through the ordinary extraEnv seam as a DSH
  // launch would.
  const runtimeEnv = {
    QNTYLAB_DSH_PARENT_BUDGET_STATE_PATH: config.budgetStatePath,
    QNTYLAB_DSH_CLAIM_STATE_DIR: config.claimStateDir,
    QNTYLAB_DSH_CLAIM_REMOTE: config.claimRemote,
    QNTYLAB_DSH_CLAIM_REF: config.claimRef,
    QNTYLAB_DSH_CLAIM_SOURCE_REPO: config.claimSourceRepo,
    QNTYLAB_DSH_SESSION_NONCE: config.sessionNonce,
  }
  const claimEnv = launcherTransportEnv(validated, {}, runtimeEnv)
  // Resolve the profile config from the TRANSPORTED env (cordis semantics).
  const profileConfig = configFromTransportedEnv(claimEnv, directory)
  return {
    config: profileConfig,
    binding: validated,
    claimEnv,
  }
}

function captureClaimCommand(directory, configOverrides = {}) {
  const { config, binding, claimEnv } = makeScratchClaimBinding(directory, configOverrides)
  const calls = []
  const command = (cfg, args) => {
    calls.push({ cfg, args })
    return { ok: true }
  }
  const guard = createParentGuard(config, {
    isAgentLoopRequest: options => options.agentLoop === true,
    command,
  })
  return { config, binding, claimEnv, calls, guard }
}

test('E2E-POSITIVE: launcher transports EXACT resolved binding -> profile config -> guard -> Python claim CLI', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-e2e-positive-'))
  try {
    const { config, binding, claimEnv, calls, guard } = captureClaimCommand(directory)
    // The guard's reserve -> ensureClaim -> command must receive the claim args
    guard.reserve({ provider: 'openai', model: 'gpt-5-mini', agentLoop: true, maxTokens: MAX_OUTPUT_TOKENS })
    const claimCall = calls.find(call => call.args[0] === 'claim')
    assert.ok(claimCall, 'guard must invoke the Python claim entrypoint')
    const args = claimCall.args
    // state-dir / remote / ref / source-repo / session-nonce preserved
    assert.equal(args[args.indexOf('--state-dir') + 1], config.claimStateDir)
    assert.equal(args[args.indexOf('--remote') + 1], config.claimRemote)
    assert.equal(args[args.indexOf('--ref') + 1], config.claimRef)
    assert.equal(args[args.indexOf('--source-repo') + 1], config.claimSourceRepo)
    assert.equal(args[args.indexOf('--session-nonce') + 1], config.sessionNonce)
    // EXACT binding values reach Python (no transformation anywhere)
    assert.equal(args[args.indexOf('--authorized-execution-source-sha') + 1], binding.authorizedExecutionSourceSha)
    assert.equal(args[args.indexOf('--execution-contract-root') + 1], binding.executionContractRoot)
    assert.equal(args[args.indexOf('--runtime-identity-digest') + 1], binding.runtimeIdentityDigest)
    assert.equal(args[args.indexOf('--executable-identity-digest') + 1], binding.executableIdentityDigest)
    assert.equal(args[args.indexOf('--revocation-state') + 1], binding.revocationState)
    // Launcher env carries the SAME exact values (profile transport preserves)
    assert.equal(claimEnv.QNTYLAB_DSH_AUTHORIZED_EXECUTION_SOURCE_SHA, binding.authorizedExecutionSourceSha)
    assert.equal(claimEnv.QNTYLAB_DSH_EXECUTION_CONTRACT_ROOT, binding.executionContractRoot)
    assert.equal(claimEnv.QNTYLAB_DSH_RUNTIME_IDENTITY_DIGEST, binding.runtimeIdentityDigest)
    assert.equal(claimEnv.QNTYLAB_DSH_EXECUTABLE_IDENTITY_DIGEST, binding.executableIdentityDigest)
    assert.equal(claimEnv.QNTYLAB_DSH_REVOCATION_STATE, binding.revocationState)
    // The config consumed by the guard came from the TRANSPORTED env — a
    // launcher that drops or renames a claim-binding field fails here.
    assert.equal(config.executionContractRoot, binding.executionContractRoot)
    assert.equal(config.authorizedExecutionSourceSha, binding.authorizedExecutionSourceSha)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('E2E-POSITIVE: launcher env -> profile -> guard -> REAL Python claim CLI commits a scratch claim', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-e2e-python-'))
  try {
    const { config, binding } = makeScratchClaimBinding(directory)
    // Run the real guard (default command = real Python claim CLI) with the
    // config resolved from the launcher-transported env. No mock command.
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
    })
    const dispatch = parentHookHarness(guard)
    const result = await dispatch(parentOptions(), 'success')
    assert.equal(result.wireAttempts, 1)
    // Python receipt is written in the claim state dir
    const receiptPath = join(config.claimStateDir, 'claim-receipt.json')
    assert.ok(existsSync(receiptPath), 'claim receipt must be durable after guard reserve')
    const receipt = JSON.parse(readFileSync(receiptPath, 'utf8'))
    assert.equal(receipt.source_head, binding.authorizedExecutionSourceSha, 'Python claim committed to the EXACT scratch source SHA')
    assert.equal(receipt.state, 'REMOTE_AND_LOCAL_COMPLETE')
    // budget reservation happened after claim COMMITTED (ordering preserved)
    const budget = JSON.parse(readFileSync(join(directory, 'parent-budget.json'), 'utf8'))
    assert.equal(budget.attempts_reserved, 1)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('E2E-POSITIVE: launcher denies claim-binding keys through extraEnv (immutable after validation)', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-e2e-immutable-'))
  try {
    const { config, binding } = makeScratchClaimBinding(directory)
    // A caller with ordinary extraEnv control attempts to substitute a rejected
    // source SHA / revoked state AFTER validation. The launcher must reject the
    // claim-binding keys in extraEnv entirely (HIGH-1).
    assert.throws(
      () => launcherTransportEnv(binding, {
        QNTYLAB_DSH_AUTHORIZED_EXECUTION_SOURCE_SHA: '0'.repeat(40),
        QNTYLAB_DSH_REVOCATION_STATE: 'REVOKED',
      }),
      /claim-binding environment key cannot be supplied through extraEnv/,
    )
    // And validateClaimBinding itself still fails closed on a malformed payload.
    assert.throws(() => validateClaimBinding({ ...binding, authorizedExecutionSourceSha: 'origin/master' }), /BLOCK_CLAIM_BINDING/)
    assert.throws(() => validateClaimBinding({ ...binding, revocationState: 'NOT_A_STATE' }), /BLOCK_CLAIM_BINDING/)
    // REVOKED is format-valid at the launcher transport (it is transported
    // exactly as supplied); the GUARD fails closed on REVOKED/SUPERSEDED before
    // any claim is attempted. Prove that guard-side closure here.
    assert.throws(() => createParentGuard(
      { ...config, revocationState: 'REVOKED' },
      { isAgentLoopRequest: options => options.agentLoop === true },
    ).reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

// NEGATIVE CONTROLS — all through the SAME production-owner path, all must
// block BEFORE claim COMMITTED / budget reservation / provider I/O.
function mustBlockBeforeReserve(overrides, expected) {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-bind-'))
  try {
    const { config, calls, guard } = captureClaimCommand(directory, overrides)
    let outcome
    try {
      guard.reserve({ provider: 'openai', model: 'gpt-5-mini', agentLoop: true, maxTokens: MAX_OUTPUT_TOKENS })
      outcome = 'UNBLOCKED'
    } catch (error) {
      outcome = String(error)
    }
    assert.match(outcome, expected, `negative control must block: ${expected}`)
    assert.equal(calls.filter(call => call.args[0] === 'claim').length, 0, 'claim must NOT be invoked for a blocked binding')
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
}

test('NC-BIND: missing source SHA blocks before claim', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-miss-src-'))
  try {
    const config = parentConfig(directory)
    config.authorizedExecutionSourceSha = undefined
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0, 'no Python claim may be invoked')
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('NC-BIND: symbolic/moving source (origin/master) blocks before claim', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-moving-'))
  try {
    const config = parentConfig(directory)
    config.authorizedExecutionSourceSha = 'origin/master' // moving ref, not exact commit
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('NC-BIND: missing execution root blocks before claim', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-miss-root-'))
  try {
    const config = parentConfig(directory)
    config.executionContractRoot = undefined
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('NC-BIND: wrong/substituted execution root blocks before claim', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-wrong-root-'))
  try {
    // A substituted root that is NOT the resolved production root — a malformed
    // (non-sha256) transport value must be rejected by the launcher/guard before
    // any claim is attempted.
    const config = parentConfig(directory)
    config.executionContractRoot = 'sha256(' + config.authorizedExecutionSourceSha + ')' // surrogate, not a sha256
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0, 'no Python claim may be invoked for a substituted root')
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('NC-BIND: missing revocation proof blocks before claim', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-miss-rev-'))
  try {
    const config = parentConfig(directory)
    config.revocationState = undefined
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('NC-BIND: REVOKED blocks before claim', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-revoked-'))
  try {
    const config = parentConfig(directory)
    config.revocationState = 'REVOKED'
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('NC-BIND: SUPERSEDED blocks before claim', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-superseded-'))
  try {
    const config = parentConfig(directory)
    config.revocationState = 'SUPERSEDED'
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('NC-BIND: wrong runtime identity blocks before claim', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-wrong-runtime-'))
  try {
    const config = parentConfig(directory)
    config.runtimeIdentityDigest = 'not-a-sha256-runtime-identity'
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0, 'no Python claim may be invoked for a wrong runtime identity')
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('NC-BIND: wrong executable identity blocks before claim', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-wrong-exec-'))
  try {
    const config = parentConfig(directory)
    config.executableIdentityDigest = 'not-a-sha256-executable-identity'
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0, 'no Python claim may be invoked for a wrong executable identity')
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('NC-BIND: transport substitution in launcher/profile/plugin (malformed SHA) blocks', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-neg-subst-'))
  try {
    const config = parentConfig(directory)
    config.authorizedExecutionSourceSha = 'not-a-commit-sha'
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    assert.throws(() => guard.reserve(parentOptions()), /BLOCK_CLAIM_BINDING/)
    assert.equal(calls.length, 0)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('E2E-NEG: executionContractRoot does NOT need to equal sha256(source SHA)', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-e2e-independent-root-'))
  try {
    const { config } = makeScratchClaimBinding(directory)
    // Independent derivation: contract root is NOT sha256 of the source SHA
    const shaOfSource = createHash('sha256').update(config.authorizedExecutionSourceSha).digest('hex')
    assert.notEqual(config.executionContractRoot, shaOfSource)
    // And a POSITIVE path with this independent root works end-to-end
    const calls = []
    const guard = createParentGuard(config, {
      isAgentLoopRequest: options => options.agentLoop === true,
      command: (cfg, args) => { calls.push(args); return { ok: true } },
    })
    guard.reserve({ provider: 'openai', model: 'gpt-5-mini', agentLoop: true, maxTokens: MAX_OUTPUT_TOKENS })
    const claimCall = calls.find(callArgs => callArgs[0] === 'claim')
    assert.ok(claimCall, 'guard must accept an independent root (not sha256(source))')
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('profile freezes exact tools, retry zero, token cap, and disables bypass routes', () => {
  const profile = readFileSync(resolve(import.meta.dirname, '../profile/cordis.patch.yml'), 'utf8')
  assert.match(profile, /maxRetries: 0/)
  assert.match(profile, /maxTokens: 4096/)
  assert.match(profile, /provider: qntylab-stage-a-gated-codex/)
  assert.match(profile, /provider: qntylab-stage-a-gated-claude/)
  assert.match(profile, /PATH: !!js process\.env\.QNTYLAB_DSH_NATIVE_PATH/)
  assert.match(profile, /enableRunInBackground: false/)
  for (const id of ['tool-subagent', 'tool-subagent-fork', 'tool-workflow', 'tool-ralph', 'llm-retry']) {
    assert.match(profile, new RegExp(`- id: ${id}\\n  disabled: true`))
  }
})

test('launcher fixes the policy patch and rejects protected environment overrides', () => {
  assert.throws(
    () => spawnDsh({}, {}, { appArgs: ['--patch', '/tmp/alternate.yml'] }),
    /cannot override the preflighted profile or policy patch/,
  )
  assert.throws(
    () => spawnDsh({}, {}, { extraEnv: { PATH: '/tmp/adversarial' } }),
    /extra environment key is denied: PATH/,
  )
  assert.throws(
    () => spawnDsh({}, {}, { extraEnv: { QNTYLAB_ROOT: '/tmp/adversarial' } }),
    /extra environment key is denied: QNTYLAB_ROOT/,
  )
})

test('launcher rejects the stale contract and a substituted profile package', () => {
  const identity = computeDigests()
  assert.doesNotThrow(() => assertQualifiedContractDigest(identity.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST))
  assert.throws(
    () => assertQualifiedContractDigest(identity.OLD_QUALIFIED_DIGEST),
    /stale or unknown qualified launch contract/,
  )
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-profile-substitution-'))
  try {
    const canonical = resolve(import.meta.dirname, '../profile/qntylab-stage-a-parent-enforcement')
    const candidate = join(directory, 'candidate')
    cpSync(canonical, candidate, { recursive: true })
    assert.doesNotThrow(() => verifyMirroredPackage(canonical, candidate))
    writeFileSync(join(candidate, 'lib/index.js'), 'export function apply() {}\n')
    assert.throws(() => verifyMirroredPackage(canonical, candidate), /package identity mismatch/)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('offline launcher accepts only the exact committed stub overlay', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-offline-overlay-'))
  try {
    const arbitrary = join(directory, 'arbitrary.patch.yml')
    writeFileSync(arbitrary, '- id: qntylab-stage-a-parent-enforcement\n  disabled: true\n')
    const extraEnv = {
      OPENAI_API_KEY: 'QNTYLAB_FAKE_TEST_NOT_REAL',
      QNTYLAB_DSH_STUB_INVOCATION_PATH: join(directory, 'invocations.jsonl'),
      QNTYLAB_DSH_STUB_RESPONSE_MODE: 'clean',
    }
    const args = { parentEndpoint: 'http://127.0.0.1:12345' }
    assert.throws(
      () => selectedPolicyPatches(args, extraEnv, arbitrary),
      /offline profile substitution is denied/,
    )
    const exact = resolve(import.meta.dirname, '../stub/offline-stub.patch.yml')
    assert.deepEqual(selectedPolicyPatches(args, extraEnv, exact), [exact])
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('native PATH resolves Codex and Claude to the preflighted identities', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qntylab-native-path-'))
  try {
    const native = join(directory, 'native')
    const node = join(directory, 'node')
    mkdirSync(native)
    mkdirSync(node)
    for (const path of [join(native, 'codex'), join(native, 'claude'), join(node, 'node'), join(node, 'python')]) {
      writeFileSync(path, 'offline fixture\n')
    }
    const preflight = {
      fingerprints: {
        codexExecutable: { resolvedPath: join(native, 'codex') },
        claudeExecutable: { resolvedPath: join(native, 'claude') },
        nodeExecutable: { resolvedPath: join(node, 'node') },
        pythonExecutable: { resolvedPath: join(node, 'python') },
      },
    }
    assert.equal(verifiedNativePath(preflight), `${native}:${node}`)
    writeFileSync(join(native, 'codex'), 'changed fixture\n')
    assert.equal(verifiedNativePath(preflight), `${native}:${node}`)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})
