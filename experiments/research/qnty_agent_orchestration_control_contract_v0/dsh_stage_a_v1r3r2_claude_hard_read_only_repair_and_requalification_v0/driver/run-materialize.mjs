#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import {
  verifySourceIdentity,
  applyCanonicalPatches,
  installOffline,
  buildRuntime,
  fingerprintExecutable,
  installedPackageIdentity,
  buildManifest,
  writeManifest,
} from '../materializer/qntylab-materialize-dsh-runtime.mjs'

const PDIR = fileURLToPath(new URL('../', import.meta.url))
const PREDECESSOR = join(PDIR, '../dsh_stage_a_v1r3r1_real_runtime_qualification_v0')
const SOURCE_ROOT = process.env.QNTYLAB_DSH_SOURCE_ROOT || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r2-claude-repair/source'
const MANIFEST_PATH = process.env.QNTYLAB_DSH_MANIFEST || join(PDIR, 'evidence/runtime_manifest.json')
const PATCH_PATH = join(PDIR, 'repairs/claude-hard-read-only.patch')
const CODEX_PATCH_PATH = join(PREDECESSOR, 'repairs/codex-executable-binding.patch')
const LAUNCHER_PATH = join(PDIR, 'launcher/qntylab-launch-dsh.mjs')
const OVERLAY_PATH = join(PDIR, 'driver/qualification.patch.yml')

function sha256(value) { return createHash('sha256').update(value).digest('hex') }
function assertPristineSource(sourceRoot) {
  const result = spawnSync('git', ['-C', sourceRoot, 'status', '--porcelain'], { encoding: 'utf8' })
  if (result.status !== 0 || result.stdout.trim() !== '') throw new Error(`SOURCE_NOT_FRESH_PRISTINE: ${sourceRoot}`)
}
function builtChunks(sourceRoot) {
  const lib = join(sourceRoot, 'apps/cli/lib')
  return readdirSync(lib).filter(name => /^(profile-boot|plugin)-.*\.js$/.test(name)).map(name => join('apps/cli/lib', name))
}

assertPristineSource(SOURCE_ROOT)
const sourceIdentity = verifySourceIdentity(SOURCE_ROOT, {
  expectedRepository: 'deepseek-ai/deepseek-harness',
  expectedCommit: '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca',
  expectedTree: '3bc8f89fe494a4755c188be354add4e8b1e7b188',
  expectedTag: 'dsh-v0.1.0-rc.7',
})
console.log('sourceIdentity OK', sourceIdentity)
const patchDigests = applyCanonicalPatches(SOURCE_ROOT, [CODEX_PATCH_PATH, PATCH_PATH])
console.log('both repairs applied by canonical materializer', patchDigests)
const packageManagerFingerprint = installOffline(SOURCE_ROOT)
console.log('offline frozen install OK', packageManagerFingerprint)
const build = buildRuntime(SOURCE_ROOT, { buildScript: 'build:lib' })
console.log('canonical full build OK', build)

const lockfilePath = join(SOURCE_ROOT, 'pnpm-lock.yaml')
const claudeSdkIdentity = installedPackageIdentity(SOURCE_ROOT, '@anthropic-ai/claude-agent-sdk')
const manifest = buildManifest({
  sourceRoot: SOURCE_ROOT,
  repository: sourceIdentity.repository,
  commit: sourceIdentity.commit,
  tree: sourceIdentity.tree,
  expectedTag: sourceIdentity.tag,
  packageManagerFingerprint,
  lockfileDigest: sha256(readFileSync(lockfilePath)),
  claudeSdkIdentity,
  patchDigests,
  profileDigests: { qualificationOverlay: sha256(readFileSync(OVERLAY_PATH)) },
  launcherDigest: sha256(readFileSync(LAUNCHER_PATH)),
  builtCliRelativePath: 'apps/cli/lib/bin.js',
  workspaceBundledChunkRelativePaths: builtChunks(SOURCE_ROOT),
  executableFingerprints: {
    nodeExecutable: fingerprintExecutable(process.execPath).digest,
    pythonExecutable: fingerprintExecutable('/usr/bin/python3').digest,
    codexExecutable: fingerprintExecutable('/home/swirky/.local/bin/codex').digest,
    claudeExecutable: fingerprintExecutable('/usr/bin/claude').digest,
  },
})
if (!existsSync(manifest.builtCliAbsolutePath)) throw new Error('BUILT_CLI_MISSING')
const manifestTextDigest = writeManifest(MANIFEST_PATH, manifest)
console.log(JSON.stringify({ manifestPath: MANIFEST_PATH, manifestTextDigest, manifest }, null, 2))
