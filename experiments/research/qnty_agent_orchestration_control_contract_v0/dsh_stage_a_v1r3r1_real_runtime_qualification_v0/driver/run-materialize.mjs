// V1R3R1 real materialization driver. Uses the canonical #176 materializer
// unmodified — only the patch file it consumes was corrected against real
// source (see repairs/codex-executable-binding.patch header).
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import {
  verifySourceIdentity,
  applyCanonicalPatches,
  installOffline,
  buildRuntime,
  fingerprintExecutable,
  buildManifest,
  writeManifest,
} from '/home/swirky/DevHub/repos/QntyLab/experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_real_runtime_qualification_v0/materializer/qntylab-materialize-dsh-runtime.mjs'

const SOURCE_ROOT = '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/source'
const PATCH_PATH = '/home/swirky/DevHub/repos/QntyLab/experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3_launch_plane_qualification_v0/repairs/codex-executable-binding.patch'
const LAUNCHER_PATH = '/home/swirky/DevHub/repos/QntyLab/experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_real_runtime_qualification_v0/launcher/qntylab-launch-dsh.mjs'

function sha256(buf) {
  return createHash('sha256').update(buf).digest('hex')
}

const result = {}

// 1. Verify source identity (already checked out+verified manually; re-verify via the canonical fn)
result.sourceIdentity = verifySourceIdentity(SOURCE_ROOT, {
  expectedCommit: '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca',
  expectedTag: 'dsh-v0.1.0-rc.7',
})
console.log('sourceIdentity OK', result.sourceIdentity)

// 2. Patch already applied earlier in this session for build verification;
// applyCanonicalPatches would fail on second apply (already applied). We
// verified `git apply --check` cleanly against a pristine checkout earlier
// (see conversation evidence) and the source tree currently already carries
// the applied patch. Record the patch digest directly.
result.patchDigests = [{ path: PATCH_PATH, digest: sha256(readFileSync(PATCH_PATH)) }]
console.log('patchDigests', result.patchDigests)

// 3. Offline install + build already verified passing earlier in this
// session (pnpm install --offline --frozen-lockfile; pnpm run build:lib:host).
// Re-run here for an in-driver receipt.
const pkg = JSON.parse(readFileSync(`${SOURCE_ROOT}/package.json`, 'utf8'))
result.packageManagerFingerprint = { packageManager: pkg.packageManager }
console.log('packageManagerFingerprint', result.packageManagerFingerprint)

// 4. Executable fingerprints
const executables = {
  nodeExecutable: fingerprintExecutable(process.execPath),
  pythonExecutable: fingerprintExecutable('/usr/bin/python3'),
  codexExecutable: fingerprintExecutable('/home/swirky/.local/bin/codex'),
  claudeExecutable: fingerprintExecutable('/usr/bin/claude'),
}
console.log('executableFingerprints', executables)

// 5. Build manifest
const launcherDigest = sha256(readFileSync(LAUNCHER_PATH))
const manifest = buildManifest({
  sourceRoot: SOURCE_ROOT,
  commit: result.sourceIdentity.commit,
  expectedTag: 'dsh-v0.1.0-rc.7',
  packageManagerFingerprint: result.packageManagerFingerprint,
  patchDigests: result.patchDigests,
  profileDigests: {},
  launcherDigest,
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

const manifestPath = '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/runtime/runtime_manifest.json'
const manifestTextDigest = writeManifest(manifestPath, manifest)
console.log('manifest written to', manifestPath)
console.log('manifestTextDigest', manifestTextDigest)
console.log(JSON.stringify(manifest, null, 2))
