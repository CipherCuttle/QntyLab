import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

function sha256(obj) {
  const text = typeof obj === 'string' ? obj : JSON.stringify(obj, Object.keys(obj).sort())
  return createHash('sha256').update(text).digest('hex')
}
function fileDigest(p) {
  return createHash('sha256').update(readFileSync(p)).digest('hex')
}

const REPO = '/home/swirky/DevHub/repos/QntyLab'
const PDIR = `${REPO}/experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_real_runtime_qualification_v0`
const SRC = '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/source'
const manifest = JSON.parse(readFileSync('/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/runtime/runtime_manifest.json', 'utf8'))

// RUNTIME_MANIFEST_DIGEST: identity-bearing fields only, no ephemeral scratch paths/timestamps.
const runtimeIdentity = {
  sourceIdentity: manifest.sourceIdentity,
  packageManagerFingerprint: manifest.packageManagerFingerprint,
  patchDigest: manifest.patchDigests.map(p => p.digest), // digest only, not the QntyLab-repo path
  builtCliDigest: manifest.builtCliDigest,
  builtCliRelativePath: 'apps/cli/lib/bin.js',
  lockfileDigest: fileDigest(`${SRC}/pnpm-lock.yaml`),
}
const RUNTIME_MANIFEST_DIGEST = sha256(runtimeIdentity)

// EXECUTABLE_IDENTITY_DIGEST: which host tools were bound, by digest (not by ephemeral absolute path).
const executableIdentity = {
  nodeExecutableDigest: manifest.executableFingerprints.nodeExecutable,
  pythonExecutableDigest: manifest.executableFingerprints.pythonExecutable,
  codexExecutableDigest: manifest.executableFingerprints.codexExecutable,
  claudeExecutableDigest: manifest.executableFingerprints.claudeExecutable,
}
const EXECUTABLE_IDENTITY_DIGEST = sha256(executableIdentity)

// LAUNCH_POLICY_DIGEST: launcher/profile/gate/tool-surface/argv/budget policy — all content, not paths.
const launcherDigest = fileDigest(`${PDIR}/launcher/qntylab-launch-dsh.mjs`)
const materializerDigest = fileDigest(`${PDIR}/materializer/qntylab-materialize-dsh-runtime.mjs`)
const repairPatchDigest = fileDigest(`${PDIR}/repairs/codex-executable-binding.patch`)
const overlayPatchDigest = fileDigest(`${PDIR}/driver/qualification.patch.yml`)
const budgetGateDigest = fileDigest(`${PDIR}/gate/qualification-budget-gate.mjs`)
const launchPolicy = {
  launcherDigest,
  materializerDigest,
  repairPatchDigest,
  overlayPatchDigest, // narrows the tool surface / selects parent provider+model
  budgetGateDigest,
  parentProvider: 'openai',
  parentModel: 'gpt-5-mini',
  modelFacingTools: ['subagent_codex', 'subagent_claude_code'].sort(),
  workspaceContainmentPolicy: 'realpath-symlink-aware; --workspace must not be inside runtimeManifest.materializationRoot or any declared forbidden root',
  argvSchema: ['--runtime-manifest', '--workspace', '--dsh-home', '--profile', '--controller-state', '--node-executable', '--python-executable', '--codex-executable', '--claude-executable', '--parent-endpoint'].sort(),
  budgetPolicy: { maxParentRequestAttempts: 8, reservationBeforeAdapterIo: true },
  retryPolicy: { llmRetries: 0 },
}
const LAUNCH_POLICY_DIGEST = sha256(launchPolicy)

const QUALIFIED_LAUNCH_CONTRACT_DIGEST = sha256({
  phaseId: 'DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0',
  RUNTIME_MANIFEST_DIGEST,
  EXECUTABLE_IDENTITY_DIGEST,
  LAUNCH_POLICY_DIGEST,
})

console.log(JSON.stringify({
  RUNTIME_MANIFEST_DIGEST,
  EXECUTABLE_IDENTITY_DIGEST,
  LAUNCH_POLICY_DIGEST,
  QUALIFIED_LAUNCH_CONTRACT_DIGEST,
  components: { runtimeIdentity, executableIdentity, launchPolicy },
}, null, 2))
