import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { sha256Canonical } from './canonical-json.mjs'

const PDIR = fileURLToPath(new URL('../', import.meta.url))
const manifest = JSON.parse(readFileSync(join(PDIR, 'evidence/runtime_manifest.json'), 'utf8'))
const fileDigest = path => createHash('sha256').update(readFileSync(path)).digest('hex')
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
  workspaceBundledChunkDigests: Object.fromEntries(Object.entries(manifest.workspaceBundledChunks).map(([path, absolute]) => [path, fileDigest(absolute)])),
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
const digest = relative => fileDigest(join(PDIR, relative))
const claudePolicy = {
  allowedTools: ['Read', 'Glob', 'Grep'],
  writeAllowed: false,
  editAllowed: false,
  bashAllowed: false,
  agentAllowed: false,
  taskAllowed: false,
  mcpAllowed: false,
  delegationAllowed: false,
  askUserQuestionAllowed: false,
  tools: ['Read', 'Glob', 'Grep'],
  disallowedTools: ['Write', 'Edit', 'Bash', 'Agent', 'Task', 'mcp__*', 'AskUserQuestion'],
  permissionMode: 'dontAsk',
  settingSources: [],
  strictMcpConfig: true,
  persistence: false,
}
const launchPolicy = {
  launcherDigest: digest('launcher/qntylab-launch-dsh.mjs'),
  predecessorLauncherDigest: digest('../dsh_stage_a_v1r3r1_real_runtime_qualification_v0/launcher/qntylab-launch-dsh.mjs'),
  materializerDigest: digest('materializer/qntylab-materialize-dsh-runtime.mjs'),
  materializationDriverDigest: digest('driver/run-materialize.mjs'),
  qualificationDriverDigest: digest('driver/run-via-launcher.mjs'),
  codexRepairDigest: manifest.patchDigests[0].digest,
  claudeRepairDigest: manifest.patchDigests[1].digest,
  overlayPatchDigest: digest('driver/qualification.patch.yml'),
  budgetGateDigest: digest('gate/qualification-budget-gate.mjs'),
  parentProvider: 'openai',
  parentModel: 'gpt-5-mini',
  modelFacingTools: ['subagent_codex', 'subagent_claude_code'],
  claudeSdkIdentity: manifest.claudeSdkIdentity,
  claudePolicy,
  workspaceContainmentPolicy: 'realpath-symlink-aware; workspace must not be inside runtime root or forbidden roots',
  budgetPolicy: { maxParentRequestAttempts: 8, reservationBeforeAdapterIo: true },
  retryPolicy: { llmRetries: 0, providerRetry: 0, automaticContinuation: false },
}
const LAUNCH_POLICY_DIGEST = sha256Canonical(launchPolicy)
const QUALIFIED_LAUNCH_CONTRACT_DIGEST = sha256Canonical({
  phaseId: manifest.phaseId,
  RUNTIME_MANIFEST_DIGEST,
  EXECUTABLE_IDENTITY_DIGEST,
  LAUNCH_POLICY_DIGEST,
})
const output = { RUNTIME_MANIFEST_DIGEST, EXECUTABLE_IDENTITY_DIGEST, LAUNCH_POLICY_DIGEST, QUALIFIED_LAUNCH_CONTRACT_DIGEST, components: { runtimeIdentity, executableIdentity, launchPolicy } }
writeFileSync(join(PDIR, 'evidence/digests.json'), `${JSON.stringify(output, null, 2)}\n`)
console.log(JSON.stringify(output, null, 2))
