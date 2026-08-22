import assert from 'node:assert/strict'
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'

import {
  assertQualifiedContractDigest,
  selectedPolicyPatches,
  spawnDsh,
  verifiedNativePath,
  verifyMirroredPackage,
} from '../launcher/qntylab-launch-dsh.mjs'
import { computeDigests } from '../evidence/compute-digests.mjs'
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

function parentConfig(directory) {
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
  return {
    budgetStatePath: join(directory, 'parent-budget.json'),
    claimStateDir: join(directory, 'claim-state'),
    claimRemote: remote,
    claimRef: 'refs/heads/qntylab-claims/offline-test-parent-guard',
    claimSourceRepo: source,
    sessionNonce: 'offline-session-nonce',
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
