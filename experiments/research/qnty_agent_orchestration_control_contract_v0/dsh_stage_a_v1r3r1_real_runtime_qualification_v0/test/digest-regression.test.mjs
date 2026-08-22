import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { sha256Canonical } from '../evidence/canonical-json.mjs'
import { buildManifest } from '../materializer/qntylab-materialize-dsh-runtime.mjs'

const baseRuntime = () => ({
  sourceIdentity: {
    repository: 'deepseek-ai/deepseek-harness',
    commit: '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca',
    tree: '3bc8f89fe494a4755c188be354add4e8b1e7b188',
    tag: 'dsh-v0.1.0-rc.7',
  },
  packageManagerFingerprint: {
    declaredPackageManager: 'pnpm@11.7.0',
    actualVersion: '11.7.0',
    executableDigest: 'pnpm-digest',
  },
})

const basePolicy = () => ({
  budgetPolicy: { maxParentRequestAttempts: 8, reservationBeforeAdapterIo: true },
  retryPolicy: { llmRetries: 0 },
})

test('recursive canonicalization binds nested source and package-manager identity', () => {
  for (const field of ['commit', 'tree', 'tag']) {
    const changed = baseRuntime()
    changed.sourceIdentity[field] += '-changed'
    assert.notEqual(sha256Canonical(baseRuntime()), sha256Canonical(changed), field)
  }
  const changedPackageManager = baseRuntime()
  changedPackageManager.packageManagerFingerprint.actualVersion = '11.8.0'
  assert.notEqual(sha256Canonical(baseRuntime()), sha256Canonical(changedPackageManager))
})

test('recursive canonicalization binds nested budget and retry policy', () => {
  for (const [section, field, value] of [
    ['budgetPolicy', 'maxParentRequestAttempts', 9],
    ['budgetPolicy', 'reservationBeforeAdapterIo', false],
    ['retryPolicy', 'llmRetries', 1],
  ]) {
    const baseline = basePolicy()
    const changed = basePolicy()
    changed[section][field] = value
    assert.notEqual(sha256Canonical(baseline), sha256Canonical(changed), `${section}.${field}`)
  }
})

test('recursive canonicalization ignores object insertion order and preserves arrays', () => {
  const first = { z: { b: 2, a: 1 }, array: ['one', { d: 4, c: 3 }], a: true }
  const second = { a: true, array: ['one', { c: 3, d: 4 }], z: { a: 1, b: 2 } }
  assert.equal(sha256Canonical(first), sha256Canonical(second))
  assert.notEqual(sha256Canonical(first), sha256Canonical({ ...first, array: ['two', { d: 4, c: 3 }] }))
})

test('qualified contract digest changes when any component digest changes', () => {
  const components = {
    RUNTIME_MANIFEST_DIGEST: 'runtime',
    EXECUTABLE_IDENTITY_DIGEST: 'executables',
    LAUNCH_POLICY_DIGEST: 'policy',
  }
  const baseline = sha256Canonical({ phaseId: 'DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0', ...components })
  for (const key of Object.keys(components)) {
    const changed = { ...components, [key]: `${components[key]}-changed` }
    assert.notEqual(baseline, sha256Canonical({ phaseId: 'DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0', ...changed }), key)
  }
})

test('runtime manifest binds phase, tree, lockfile, pnpm identity, and Claude SDK identity', () => {
  const root = mkdtempSync(join(tmpdir(), 'qntylab-manifest-'))
  mkdirSync(join(root, 'apps/cli/lib/chunks'), { recursive: true })
  writeFileSync(join(root, 'apps/cli/lib/bin.js'), 'cli\n')
  writeFileSync(join(root, 'apps/cli/lib/chunks/full-build.js'), 'full\n')
  const manifest = buildManifest({
    sourceRoot: root,
    repository: 'deepseek-ai/deepseek-harness',
    commit: 'commit',
    tree: 'tree',
    expectedTag: 'dsh-v0.1.0-rc.7',
    packageManagerFingerprint: {
      declaredPackageManager: 'pnpm@11.7.0',
      actualVersion: '11.22.0',
      executablePath: '/usr/bin/pnpm',
      executableDigest: 'pnpm-digest',
    },
    lockfileDigest: 'lock-digest',
    claudeSdkIdentity: { package: '@anthropic-ai/claude-agent-sdk', version: '0.3.220', packageJsonDigest: 'claude-digest' },
    patchDigests: [],
    profileDigests: {},
    launcherDigest: 'launcher-digest',
    builtCliRelativePath: 'apps/cli/lib/bin.js',
    workspaceBundledChunkRelativePaths: ['apps/cli/lib/chunks/full-build.js'],
    executableFingerprints: {},
  })
  assert.equal(manifest.phaseId, 'DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0')
  assert.deepEqual(manifest.sourceIdentity, {
    repository: 'deepseek-ai/deepseek-harness', commit: 'commit', tree: 'tree', tag: 'dsh-v0.1.0-rc.7',
  })
  assert.equal(manifest.lockfileDigest, 'lock-digest')
  assert.equal(manifest.packageManagerFingerprint.actualVersion, '11.22.0')
  assert.equal(manifest.claudeSdkIdentity.version, '0.3.220')
})
