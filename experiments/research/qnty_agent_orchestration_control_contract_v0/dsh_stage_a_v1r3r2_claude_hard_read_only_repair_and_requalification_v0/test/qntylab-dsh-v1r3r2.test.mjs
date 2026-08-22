import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import test from 'node:test'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { buildManifest } from '../materializer/qntylab-materialize-dsh-runtime.mjs'
import { parseLauncherArgv } from '../launcher/qntylab-launch-dsh.mjs'

test('phase materializer binds the fresh phase identity while reusing verified manifest construction', () => {
  const sourceRoot = mkdtempSync(join(tmpdir(), 'qntylab-dsh-v1r3r2-test-'))
  try {
    mkdirSync(join(sourceRoot, 'apps/cli/lib'), { recursive: true })
    writeFileSync(join(sourceRoot, 'apps/cli/lib/bin.js'), 'fixture')
    const rebuilt = buildManifest({
      sourceRoot,
      repository: 'deepseek-ai/deepseek-harness',
      commit: '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca',
      tree: '3bc8f89fe494a4755c188be354add4e8b1e7b188',
      expectedTag: 'dsh-v0.1.0-rc.7',
      packageManagerFingerprint: { declaredPackageManager: 'pnpm@11.7.0' },
      lockfileDigest: 'lock',
      claudeSdkIdentity: { package: '@anthropic-ai/claude-agent-sdk', version: '0.3.220' },
      patchDigests: [],
      profileDigests: {},
      launcherDigest: 'launcher',
      builtCliRelativePath: 'apps/cli/lib/bin.js',
      executableFingerprints: {},
    })
    assert.equal(rebuilt.phaseId, 'DSH_STAGE_A_V1R3R2_CLAUDE_HARD_READ_ONLY_REPAIR_AND_REQUALIFICATION_V0')
    assert.equal(rebuilt.sourceIdentity.commit, '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca')
  } finally {
    rmSync(sourceRoot, { recursive: true, force: true })
  }
})

test('phase launcher wrapper preserves the fail-closed argv parser seam', () => {
  const parsed = parseLauncherArgv([
    '--runtime-manifest', '/tmp/runtime.json',
    '--workspace', '/tmp/workspace',
    '--dsh-home', '/tmp/dsh-home',
    '--profile', 'headless',
    '--controller-state', '/tmp/controller.json',
    '--node-executable', '/usr/bin/node',
    '--python-executable', '/usr/bin/python3',
    '--codex-executable', '/usr/bin/codex',
    '--claude-executable', '/usr/bin/claude',
  ])
  assert.equal(parsed.profile, 'headless')
  assert.equal(parsed.workspace, '/tmp/workspace')
  assert.throws(
    () => parseLauncherArgv(['--unknown', 'value']),
    error => error?.code === 'BLOCK_LAUNCH_ARGV',
  )
})
