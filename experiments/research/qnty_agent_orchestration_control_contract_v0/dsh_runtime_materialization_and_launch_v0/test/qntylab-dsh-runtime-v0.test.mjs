import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { createHash } from 'node:crypto'
import {
  PHASE_ID,
  SOURCE_REMOTE,
  SOURCE_COMMIT,
  SOURCE_TREE,
  SOURCE_TAG,
  PINNED_PNPM,
  materializePinnedSource,
} from '../materializer/qntylab-materialize-dsh-runtime.mjs'
import { verifyPhaseManifest } from '../launcher/qntylab-launch-dsh.mjs'

const PHASE_DIR = fileURLToPath(new URL('../', import.meta.url))
const LAUNCHER = fileURLToPath(new URL('../launcher/qntylab-launch-dsh.mjs', import.meta.url))
const sha256 = value => createHash('sha256').update(value).digest('hex')

function manifestFixture(path) {
  return {
    phaseId: PHASE_ID,
    sourceRemote: SOURCE_REMOTE,
    sourceIdentity: { repository: 'deepseek-ai/deepseek-harness', commit: SOURCE_COMMIT, tree: SOURCE_TREE, tag: SOURCE_TAG },
    sourceReceipt: { checkoutClean: true },
    packageManagerFingerprint: {
      declaredPackageManager: `pnpm@${PINNED_PNPM}`,
      actualVersion: PINNED_PNPM,
      executableDigest: '3655bc798f300951f2070fee411b337d626b0c3ae80c2d24c46ccac4595d4bf9',
      invocation: ['corepack', `pnpm@${PINNED_PNPM}`],
    },
    lockfileDigest: 'f517dc3978d57531cda747df62a2abdde1df5b9f25415fcf1fc5d51f8b7547ea',
    patchDigests: [
      { digest: 'f89bf5833956f3c4202ca88a9285e39658976b29605fc1b63b7c62ebdd07fcb3' },
      { digest: '2b8277bf13e077651046e2527dc7aa092c3c9669cedc61eac1f742d9364a17e3' },
    ],
    buildIdentity: { buildScript: 'build:lib', command: `corepack pnpm@${PINNED_PNPM} run build:lib`, entrypointRelativePath: 'apps/cli/lib/bin.js', entrypointDigest: 'c0226687bb20f45c603ec6fe50f3de16d1c3510c3a803304ec575ef9bc366c62' },
    builtCliDigest: 'c0226687bb20f45c603ec6fe50f3de16d1c3510c3a803304ec575ef9bc366c62',
    launcherIdentity: { digest: sha256(readFileSync(LAUNCHER)) },
    executableFingerprints: {
      nodeExecutable: '1bec56ef7cfa9a76f3e0b7c0a87f220eb73f23102b9c0b4c7529a3f7c3ce7c31',
      pythonExecutable: 'b8d8288faefdd300201f43fcf00f6f539a27218eeed3a3dff5ab10b9c4c99700',
      codexExecutable: 'ac2cfed85fb647d61e0150b8548102b330e4799d9d81ad5d354de701edf6b074',
      claudeExecutable: '98226474f802e3094d6a86c5ade8883c16206d0fcb5c400b7401c800063e99d7',
    },
    materializationRoot: '/var/tmp/qntylab-dsh-runtime-v0-retry2/source',
    manifestPath: path,
  }
}

test('phase pins the public source, tree, tag, and exact pnpm contract', () => {
  assert.equal(SOURCE_REMOTE, 'https://github.com/deepseek-ai/deepseek-harness.git')
  assert.equal(SOURCE_COMMIT, '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca')
  assert.equal(SOURCE_TREE, '3bc8f89fe494a4755c188be354add4e8b1e7b188')
  assert.equal(SOURCE_TAG, 'dsh-v0.1.0-rc.7')
  assert.equal(PINNED_PNPM, '11.7.0')
})

test('launcher accepts only the exact phase manifest identity', () => {
  if (!existsSync('/var/tmp/qntylab-dsh-runtime-v0-retry2/source/.git')) return
  const root = mkdtempSync(join(tmpdir(), 'qntylab-dsh-manifest-'))
  const path = join(root, 'runtime_manifest.json')
  const fixture = manifestFixture(path)
  writeFileSync(path, JSON.stringify(fixture))
  assert.deepEqual(verifyPhaseManifest(path).sourceIdentity, fixture.sourceIdentity)
  for (const [field, value] of [
    ['sourceRemote', 'https://example.invalid/floating.git'],
    ['lockfileDigest', 'wrong'],
  ]) {
    const mutated = { ...fixture, [field]: value }
    writeFileSync(path, JSON.stringify(mutated))
    assert.throws(() => verifyPhaseManifest(path), error => error?.code === 'BLOCK_RUNTIME_IDENTITY')
  }
  for (const [index, value] of [['commit', 'wrong'], ['tree', 'wrong'], ['tag', 'latest']]) {
    const mutated = { ...fixture, sourceIdentity: { ...fixture.sourceIdentity, [index]: value } }
    writeFileSync(path, JSON.stringify(mutated))
    assert.throws(() => verifyPhaseManifest(path), error => error?.code === 'BLOCK_RUNTIME_IDENTITY')
  }
  const patchMutation = { ...fixture, patchDigests: [{ digest: 'wrong' }, fixture.patchDigests[1]] }
  writeFileSync(path, JSON.stringify(patchMutation))
  assert.throws(() => verifyPhaseManifest(path), error => error?.code === 'BLOCK_RUNTIME_IDENTITY')
})

test('launcher rejects stale/missing build and launcher identity', () => {
  const root = mkdtempSync(join(tmpdir(), 'qntylab-dsh-manifest-'))
  const path = join(root, 'runtime_manifest.json')
  const fixture = manifestFixture(path)
  for (const mutation of [
    { ...fixture, buildIdentity: { ...fixture.buildIdentity, buildScript: 'build' } },
    { ...fixture, buildIdentity: { ...fixture.buildIdentity, entrypointRelativePath: 'apps/cli/src/bin.ts' } },
    { ...fixture, launcherIdentity: { digest: 'wrong' } },
    { ...fixture, manifestPath: join(root, 'other.json') },
  ]) {
    writeFileSync(path, JSON.stringify(mutation))
    assert.throws(() => verifyPhaseManifest(path), error => error?.code === 'BLOCK_RUNTIME_IDENTITY')
  }
})

test('materializer refuses a non-empty or dirty target before source acquisition', () => {
  const root = mkdtempSync(join(tmpdir(), 'qntylab-dsh-materializer-'))
  writeFileSync(join(root, 'do-not-overwrite'), 'user data')
  assert.throws(() => materializePinnedSource({ runtimeRoot: root }), error => error?.code === 'BLOCK_SOURCE')
})

test('materializer and qualification driver are source-controlled and fail closed', () => {
  const materializer = readFileSync(fileURLToPath(new URL('../materializer/qntylab-materialize-dsh-runtime.mjs', import.meta.url)), 'utf8')
  const driver = readFileSync(fileURLToPath(new URL('../driver/materialize-pinned-runtime.mjs', import.meta.url)), 'utf8')
  const loopback = readFileSync(fileURLToPath(new URL('../driver/run-loopback-qualification.mjs', import.meta.url)), 'utf8')
  assert.match(materializer, /clone.*--no-checkout.*--no-tags/s)
  assert.match(materializer, /fetch.*--tags.*sourceCommit/s)
  assert.match(materializer, /install.*--offline.*--frozen-lockfile/s)
  assert.match(materializer, /pnpm@\$\{PINNED_PNPM\}/)
  assert.doesNotMatch(driver, /npx\s+@deepseek-ai\/dsh/)
  assert.match(loopback, /127\.0\.0\.1/)
  assert.match(loopback, /QNTYLAB_QUAL_OPENAI_API_KEY.*loopback-fake-only/)
  assert.doesNotMatch(loopback, /OPENAI_API_KEY.*process\.env/)
})

test('governed historical repairs remain the exact bytes used by the phase', () => {
  const repoRoot = fileURLToPath(new URL('../../../../../', import.meta.url))
  const codex = join(repoRoot, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_real_runtime_qualification_v0/repairs/codex-executable-binding.patch')
  const claude = join(repoRoot, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/repairs/claude-hard-read-only.patch')
  assert.match(readFileSync(codex, 'utf8'), /resolveExecutable\(/)
  assert.match(readFileSync(claude, 'utf8'), /CLAUDE_ALLOWED_TOOLS/)
})
