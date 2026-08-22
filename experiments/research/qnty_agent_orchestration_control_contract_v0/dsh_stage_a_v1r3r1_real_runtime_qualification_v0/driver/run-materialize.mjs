#!/usr/bin/env node
// V1R3R1 decisive materialization driver.
//
// The source root must be a fresh, pristine checkout of the exact pinned DSH
// commit. This driver owns the complete materialization graph: identity
// verification -> canonical patch application -> offline frozen install ->
// full build:lib -> manifest emission. No prior session state is accepted.
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'
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
const SOURCE_ROOT = process.env.QNTYLAB_DSH_SOURCE_ROOT || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/source'
const MANIFEST_PATH = process.env.QNTYLAB_DSH_MANIFEST || join(PDIR, 'evidence/runtime_manifest.json')
const PATCH_PATH = join(PDIR, 'repairs/codex-executable-binding.patch')
const LAUNCHER_PATH = join(PDIR, 'launcher/qntylab-launch-dsh.mjs')
const OVERLAY_PATH = join(PDIR, 'driver/qualification.patch.yml')

function sha256(buf) {
  return createHash('sha256').update(buf).digest('hex')
}

function assertPristineSource(sourceRoot) {
  const result = spawnSync('git', ['-C', sourceRoot, 'status', '--porcelain'], { encoding: 'utf8' })
  if (result.status !== 0 || result.stdout.trim() !== '') {
    throw new Error(`SOURCE_NOT_FRESH_PRISTINE: ${sourceRoot}`)
  }
}

assertPristineSource(SOURCE_ROOT)
const result = {}

result.sourceIdentity = verifySourceIdentity(SOURCE_ROOT, {
  expectedRepository: 'deepseek-ai/deepseek-harness',
  expectedCommit: '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca',
  expectedTree: '3bc8f89fe494a4755c188be354add4e8b1e7b188',
  expectedTag: 'dsh-v0.1.0-rc.7',
})
console.log('sourceIdentity OK', result.sourceIdentity)

result.patchDigests = applyCanonicalPatches(SOURCE_ROOT, [PATCH_PATH])
console.log('patch applied by canonical materializer', result.patchDigests)

result.packageManagerFingerprint = installOffline(SOURCE_ROOT)
console.log('offline frozen install OK', result.packageManagerFingerprint)

result.build = buildRuntime(SOURCE_ROOT)
console.log('canonical build OK', result.build)

const lockfilePath = join(SOURCE_ROOT, 'pnpm-lock.yaml')
const claudeSdkIdentity = installedPackageIdentity(SOURCE_ROOT, '@anthropic-ai/claude-agent-sdk')
const executables = {
  nodeExecutable: fingerprintExecutable(process.execPath),
  pythonExecutable: fingerprintExecutable('/usr/bin/python3'),
  codexExecutable: fingerprintExecutable('/home/swirky/.local/bin/codex'),
  claudeExecutable: fingerprintExecutable('/usr/bin/claude'),
}
const overlayDigest = sha256(readFileSync(OVERLAY_PATH))
const manifest = buildManifest({
  sourceRoot: SOURCE_ROOT,
  repository: result.sourceIdentity.repository,
  commit: result.sourceIdentity.commit,
  tree: result.sourceIdentity.tree,
  expectedTag: result.sourceIdentity.tag,
  packageManagerFingerprint: result.packageManagerFingerprint,
  lockfileDigest: sha256(readFileSync(lockfilePath)),
  claudeSdkIdentity,
  patchDigests: result.patchDigests,
  profileDigests: { qualificationOverlay: overlayDigest },
  launcherDigest: sha256(readFileSync(LAUNCHER_PATH)),
  builtCliRelativePath: 'apps/cli/lib/bin.js',
  workspaceBundledChunkRelativePaths: [
    'apps/cli/lib/profile-boot-DG5t9aNs.js',
    'apps/cli/lib/plugin-9h8shc4d.js',
  ],
  executableFingerprints: {
    nodeExecutable: executables.nodeExecutable.digest,
    pythonExecutable: executables.pythonExecutable.digest,
    codexExecutable: executables.codexExecutable.digest,
    claudeExecutable: executables.claudeExecutable.digest,
  },
})
const manifestTextDigest = writeManifest(MANIFEST_PATH, manifest)
console.log('manifest written to', MANIFEST_PATH)
console.log('manifestTextDigest', manifestTextDigest)
console.log(JSON.stringify(manifest, null, 2))
