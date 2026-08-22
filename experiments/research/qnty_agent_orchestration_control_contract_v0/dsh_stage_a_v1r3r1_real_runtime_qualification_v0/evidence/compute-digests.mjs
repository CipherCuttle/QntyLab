import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { sha256Canonical } from './canonical-json.mjs'

const PDIR = dirname(fileURLToPath(import.meta.url))
const manifestPath = process.env.QNTYLAB_DSH_MANIFEST || join(PDIR, 'runtime_manifest.json')
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
const fileDigest = path => createHash('sha256').update(readFileSync(path)).digest('hex')

// RUNTIME_MANIFEST_DIGEST: immutable identity only; no scratch paths/timestamps.
const runtimeIdentity = {
  phaseId: manifest.phaseId,
  sourceIdentity: manifest.sourceIdentity,
  packageManagerFingerprint: {
    declaredPackageManager: manifest.packageManagerFingerprint.declaredPackageManager,
    actualVersion: manifest.packageManagerFingerprint.actualVersion,
    executableDigest: manifest.packageManagerFingerprint.executableDigest,
  },
  lockfileDigest: manifest.lockfileDigest,
  patchDigests: manifest.patchDigests.map(p => p.digest),
  builtCliDigest: manifest.builtCliDigest,
  builtCliRelativePath: 'apps/cli/lib/bin.js',
  workspaceBundledChunkDigests: Object.fromEntries(
    Object.entries(manifest.workspaceBundledChunks).map(([relativePath, absolutePath]) => [relativePath, fileDigest(absolutePath)]),
  ),
  claudeSdkIdentity: manifest.claudeSdkIdentity,
}
const RUNTIME_MANIFEST_DIGEST = sha256Canonical(runtimeIdentity)

const executableIdentity = {
  nodeExecutableDigest: manifest.executableFingerprints.nodeExecutable,
  pythonExecutableDigest: manifest.executableFingerprints.pythonExecutable,
  codexExecutableDigest: manifest.executableFingerprints.codexExecutable,
  claudeExecutableDigest: manifest.executableFingerprints.claudeExecutable,
}
const EXECUTABLE_IDENTITY_DIGEST = sha256Canonical(executableIdentity)

const launcherDigest = fileDigest(join(PDIR, '../launcher/qntylab-launch-dsh.mjs'))
const materializerDigest = fileDigest(join(PDIR, '../materializer/qntylab-materialize-dsh-runtime.mjs'))
const materializationDriverDigest = fileDigest(join(PDIR, '../driver/run-materialize.mjs'))
const qualificationDriverDigest = fileDigest(join(PDIR, '../driver/run-via-launcher.mjs'))
const repairPatchDigest = fileDigest(join(PDIR, '../repairs/codex-executable-binding.patch'))
const overlayPatchDigest = fileDigest(join(PDIR, '../driver/qualification.patch.yml'))
const budgetGateDigest = fileDigest(join(PDIR, '../gate/qualification-budget-gate.mjs'))
const launchPolicy = {
  launcherDigest,
  materializerDigest,
  materializationDriverDigest,
  qualificationDriverDigest,
  repairPatchDigest,
  overlayPatchDigest,
  budgetGateDigest,
  parentProvider: 'openai',
  parentModel: 'gpt-5-mini',
  modelFacingTools: ['subagent_codex', 'subagent_claude_code'],
  workspaceContainmentPolicy: 'realpath-symlink-aware; --workspace must not be inside runtimeManifest.materializationRoot or any declared forbidden root',
  argvSchema: ['--runtime-manifest', '--workspace', '--dsh-home', '--profile', '--controller-state', '--node-executable', '--python-executable', '--codex-executable', '--claude-executable', '--parent-endpoint'],
  budgetPolicy: { maxParentRequestAttempts: 8, reservationBeforeAdapterIo: true },
  retryPolicy: { llmRetries: 0 },
}
const LAUNCH_POLICY_DIGEST = sha256Canonical(launchPolicy)

const QUALIFIED_LAUNCH_CONTRACT_DIGEST = sha256Canonical({
  phaseId: 'DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0',
  RUNTIME_MANIFEST_DIGEST,
  EXECUTABLE_IDENTITY_DIGEST,
  LAUNCH_POLICY_DIGEST,
})

const output = {
  RUNTIME_MANIFEST_DIGEST,
  EXECUTABLE_IDENTITY_DIGEST,
  LAUNCH_POLICY_DIGEST,
  QUALIFIED_LAUNCH_CONTRACT_DIGEST,
  components: { runtimeIdentity, executableIdentity, launchPolicy },
}
writeFileSync(join(PDIR, 'digests.json'), `${JSON.stringify(output, null, 2)}\n`, 'utf8')
console.log(JSON.stringify(output, null, 2))
