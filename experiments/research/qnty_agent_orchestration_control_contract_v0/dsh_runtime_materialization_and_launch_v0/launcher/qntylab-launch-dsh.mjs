#!/usr/bin/env node

// Phase-D manifest gate over the already-qualified V1R3 launcher. The
// predecessor launcher remains the process-spawn implementation; this gate
// adds the phase's immutable source/lockfile/patch/build bindings before that
// implementation is allowed to run.

import { createHash } from 'node:crypto'
import { existsSync, readFileSync, realpathSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { isAbsolute, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

import {
  parseLauncherArgv,
  preflightLaunch as predecessorPreflightLaunch,
  spawnDsh as predecessorSpawnDsh,
  LaunchPlaneError,
} from '../../dsh_stage_a_v1r3r1_real_runtime_qualification_v0/launcher/qntylab-launch-dsh.mjs'
import {
  SOURCE_REMOTE,
  SOURCE_REPOSITORY,
  SOURCE_COMMIT,
  SOURCE_TREE,
  SOURCE_TAG,
  PINNED_PNPM,
  PHASE_ID,
  verifySourceIdentity,
} from '../materializer/qntylab-materialize-dsh-runtime.mjs'

const EXPECTED_LOCKFILE_DIGEST = 'f517dc3978d57531cda747df62a2abdde1df5b9f25415fcf1fc5d51f8b7547ea'
const EXPECTED_PATCH_DIGESTS = [
  'f89bf5833956f3c4202ca88a9285e39658976b29605fc1b63b7c62ebdd07fcb3',
  '2b8277bf13e077651046e2527dc7aa092c3c9669cedc61eac1f742d9364a17e3',
]
const EXPECTED_BUILD_CLI_DIGEST = 'c0226687bb20f45c603ec6fe50f3de16d1c3510c3a803304ec575ef9bc366c62'
const EXPECTED_EXECUTABLE_FINGERPRINTS = {
  nodeExecutable: '1bec56ef7cfa9a76f3e0b7c0a87f220eb73f23102b9c0b4c7529a3f7c3ce7c31',
  pythonExecutable: 'b8d8288faefdd300201f43fcf00f6f539a27218eeed3a3dff5ab10b9c4c99700',
  codexExecutable: 'ac2cfed85fb647d61e0150b8548102b330e4799d9d81ad5d354de701edf6b074',
  claudeExecutable: '98226474f802e3094d6a86c5ade8883c16206d0fcb5c400b7401c800063e99d7',
}
const EXPECTED_PATCHED_PATHS = [
  'packages/subagent/subagent-codex/src/index.ts',
  'packages/subagent/subagent-codex/src/run.ts',
  'packages/subagent/subagent-codex/tests/subagent-codex.spec.ts',
  'packages/subagent/subagent-claude-code/src/run.ts',
  'packages/subagent/subagent-claude-code/tests/subagent-claude-code.spec.ts',
]

function sha256File(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function fail(message) {
  throw new LaunchPlaneError('BLOCK_RUNTIME_IDENTITY', message)
}

export function verifyPhaseManifest(manifestPath) {
  if (!isAbsolute(manifestPath) || !existsSync(manifestPath)) fail(`manifest must be an existing absolute file: ${manifestPath}`)
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  if (manifest.phaseId !== PHASE_ID) fail(`unexpected manifest phase: ${manifest.phaseId}`)
  if (manifest.sourceRemote !== SOURCE_REMOTE) fail(`unexpected source remote: ${manifest.sourceRemote}`)
  if (manifest.sourceIdentity?.repository !== SOURCE_REPOSITORY) fail('unexpected source repository')
  if (manifest.sourceIdentity?.commit !== SOURCE_COMMIT) fail('unexpected source commit')
  if (manifest.sourceIdentity?.tree !== SOURCE_TREE) fail('unexpected source tree')
  if (manifest.sourceIdentity?.tag !== SOURCE_TAG) fail('unexpected source tag')
  if (manifest.sourceReceipt?.checkoutClean !== true) fail('source checkout is not recorded clean')
  if (manifest.packageManagerFingerprint?.declaredPackageManager !== `pnpm@${PINNED_PNPM}`) fail('wrong declared package manager')
  if (manifest.packageManagerFingerprint?.actualVersion !== PINNED_PNPM) fail('wrong pnpm executable version')
  if (manifest.packageManagerFingerprint?.executableDigest !== '3655bc798f300951f2070fee411b337d626b0c3ae80c2d24c46ccac4595d4bf9') fail('wrong corepack executable identity')
  if (JSON.stringify(manifest.packageManagerFingerprint?.invocation) !== JSON.stringify(['corepack', `pnpm@${PINNED_PNPM}`])) fail('wrong package-manager invocation')
  if (manifest.lockfileDigest !== EXPECTED_LOCKFILE_DIGEST) fail('wrong lockfile digest')
  const patchDigests = (manifest.patchDigests || []).map(patch => patch.digest)
  if (patchDigests.length !== EXPECTED_PATCH_DIGESTS.length || patchDigests.some((digest, index) => digest !== EXPECTED_PATCH_DIGESTS[index])) {
    fail('wrong governed patch identity')
  }
  if (manifest.buildIdentity?.buildScript !== 'build:lib') fail('wrong build script')
  if (manifest.buildIdentity?.command !== `corepack pnpm@${PINNED_PNPM} run build:lib`) fail('wrong build command')
  if (manifest.buildIdentity?.entrypointRelativePath !== 'apps/cli/lib/bin.js') fail('wrong built entrypoint')
  if (!manifest.buildIdentity?.entrypointDigest || manifest.buildIdentity.entrypointDigest !== manifest.builtCliDigest) fail('entrypoint digest is absent or inconsistent')
  if (manifest.builtCliDigest !== EXPECTED_BUILD_CLI_DIGEST) fail('built entrypoint digest is not qualified')
  for (const [key, digest] of Object.entries(EXPECTED_EXECUTABLE_FINGERPRINTS)) {
    if (manifest.executableFingerprints?.[key] !== digest) fail(`unqualified executable identity: ${key}`)
  }
  const sourceRoot = realpathSync(manifest.materializationRoot)
  const gitIdentity = verifySourceIdentity(sourceRoot, {
    expectedRepository: SOURCE_REPOSITORY,
    expectedCommit: SOURCE_COMMIT,
    expectedTree: SOURCE_TREE,
    expectedTag: SOURCE_TAG,
  })
  if (gitIdentity.commit !== SOURCE_COMMIT || gitIdentity.tree !== SOURCE_TREE) fail('checked-out source identity drift')
  const status = spawnSync('git', ['-C', sourceRoot, 'status', '--porcelain'], { encoding: 'utf8' })
  if (status.status !== 0 || status.stdout.split('\n').filter(line => line.startsWith('??')).length > 0) fail('source has unexpected untracked files')
  const changed = spawnSync('git', ['-C', sourceRoot, 'diff', '--name-only'], { encoding: 'utf8' }).stdout.trim().split('\n').filter(Boolean).sort()
  if (JSON.stringify(changed) !== JSON.stringify([...EXPECTED_PATCHED_PATHS].sort())) fail('source diff does not match governed repairs')
  const launcherPath = fileURLToPath(import.meta.url)
  if (manifest.launcherIdentity?.digest !== sha256File(launcherPath)) fail('launcher identity mismatch')
  if (manifest.manifestPath && resolve(manifest.manifestPath) !== resolve(manifestPath)) fail('manifest path binding mismatch')
  return manifest
}

export function preflightLaunch(args, options = {}) {
  verifyPhaseManifest(args.runtimeManifest)
  return predecessorPreflightLaunch(args, options)
}

export function spawnDsh(args, preflightResult, options = {}) {
  return predecessorSpawnDsh(args, preflightResult, options)
}

export { parseLauncherArgv, LaunchPlaneError }

async function main() {
  try {
    const args = parseLauncherArgv(process.argv.slice(2))
    const preflight = preflightLaunch(args, { forbiddenRoots: (process.env.QNTYLAB_LAUNCH_FORBIDDEN_ROOTS || '').split(':').filter(Boolean) })
    const child = spawnDsh(args, preflight)
    child.on('exit', code => { process.exitCode = code ?? 1 })
  } catch (error) {
    if (error instanceof LaunchPlaneError) {
      process.stderr.write(`${error.code}: ${error.message}\n`)
      process.exitCode = 1
      return
    }
    throw error
  }
}

if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`)
  process.exitCode = 1
})
