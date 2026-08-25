#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { existsSync, lstatSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { sha256Canonical } from './canonical-json.mjs'

export const PHASE = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const ROOT = resolve(PHASE, '../../../..')
export const PHYSICAL_PHASE = resolve(ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_runtime_materialization_and_launch_v0')
export const STAGE_A_PHASE = resolve(ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0')
export const MANIFEST_DEFAULT = join(PHYSICAL_PHASE, 'evidence/runtime_manifest.json')
export const CONTRACT_PATH = join(PHASE, 'evidence/contract.json')
// CURRENT-generation evidence must NEVER be written to the historical
// contract.json / digests.json paths (immutable a392 lineage). The CLI main
// block below writes current-generation evidence to an explicit NEW
// reconciliation path so historical evidence stays byte-for-byte immutable.
export const RECONCILIATION_PHASE = resolve(ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_execution_contract_reconciliation_v0')
export const CURRENT_CONTRACT_PATH = join(RECONCILIATION_PHASE, 'evidence/current_contract.json')
export const CURRENT_DIGESTS_PATH = join(RECONCILIATION_PHASE, 'evidence/current_digests.json')
export const PREDECESSOR_QUALIFIED_CONTRACT = 'e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82'
export const PROJECT_ID = 'DSH_STAGE_A_V1R3R2_COMPOSITE_LIVE_LAUNCHER_INTEGRATION_AND_REQUALIFICATION_V0'

const EXPECTED_SOURCE = {
  repository: 'deepseek-ai/deepseek-harness',
  commit: '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca',
  tree: '3bc8f89fe494a4755c188be354add4e8b1e7b188',
  tag: 'dsh-v0.1.0-rc.7',
}
const EXPECTED_PATCHES = [
  'f89bf5833956f3c4202ca88a9285e39658976b29605fc1b63b7c62ebdd07fcb3',
  '2b8277bf13e077651046e2527dc7aa092c3c9669cedc61eac1f742d9364a17e3',
]
const EXPECTED_LOCKFILE = 'f517dc3978d57531cda747df62a2abdde1df5b9f25415fcf1fc5d51f8b7547ea'
const EXPECTED_BUILT_CLI = 'c0226687bb20f45c603ec6fe50f3de16d1c3510c3a803304ec575ef9bc366c62'
const EXPECTED_EXECUTABLES = {
  nodeExecutableDigest: '1bec56ef7cfa9a76f3e0b7c0a87f220eb73f23102b9c0b4c7529a3f7c3ce7c31',
  pythonExecutableDigest: 'b8d8288faefdd300201f43fcf00f6f539a27218eeed3a3dff5ab10b9c4c99700',
  codexExecutableDigest: 'ac2cfed85fb647d61e0150b8548102b330e4799d9d81ad5d354de701edf6b074',
  claudeExecutableDigest: '98226474f802e3094d6a86c5ade8883c16206d0fcb5c400b7401c800063e99d7',
}

/**
 * Explicit dependency manifest for the Stage-A execution-contract DAG.
 *
 * Each node lists every downstream node that consumes its output, so the
 * reverse-transitive closure of any changed leaf is the complete set of nodes
 * that MUST be invalidated and re-derived. This manifest exists to make the
 * real reverse-transitive closure explicit and mechanically provable. It does
 * NOT artificially reduce invalidation: a leaf change reaches every downstream
 * node, exactly as the real content-addressed DAG requires.
 */
export const DEPENDENCY_MANIFEST = Object.freeze({
  projectId: 'DSH_STAGE_A_V1R3R2_COMPOSITE_LIVE_LAUNCHER_INTEGRATION_AND_REQUALIFICATION_V0',
  nodes: Object.freeze({
    'qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py': Object.freeze({ downstream: Object.freeze(['stageAFileDigests']) }),
    stageAFileDigests: Object.freeze({ downstream: Object.freeze(['stageAPolicy']) }),
    stageAPolicy: Object.freeze({ downstream: Object.freeze(['compositeLaunchPolicy']) }),
    compositeLaunchPolicy: Object.freeze({ downstream: Object.freeze(['computeDigests', 'compositeContract']) }),
    computeDigests: Object.freeze({ downstream: Object.freeze(['compositeContract']) }),
    compositeContract: Object.freeze({ downstream: Object.freeze(['successorContract']) }),
    successorContract: Object.freeze({ downstream: Object.freeze(['prepareProductionLaunch']) }),
    prepareProductionLaunch: Object.freeze({ downstream: Object.freeze(['V0R6_EXECUTION_EVIDENCE']) }),
  }),
})

/**
 * The real reverse-transitive closure over {@link DEPENDENCY_MANIFEST}.
 * Returns every downstream node that must be invalidated when `changedLeaf`
 * changes. Mechanically provable: it walks only the explicit manifest edges.
 */
export function reverseTransitiveClosure(changedLeaf) {
  const nodes = DEPENDENCY_MANIFEST.nodes
  if (!(changedLeaf in nodes)) return []
  const closed = new Set()
  const queue = [...nodes[changedLeaf].downstream]
  while (queue.length > 0) {
    const node = queue.shift()
    if (closed.has(node)) continue
    closed.add(node)
    if (nodes[node]) for (const downstream of nodes[node].downstream) queue.push(downstream)
  }
  return [...closed]
}

const fileDigest = path => createHash('sha256').update(readFileSync(path)).digest('hex')

function requireFile(path, label) {
  if (!existsSync(path) || !lstatSync(path).isFile()) throw new Error(`missing ${label}: ${path}`)
  return path
}

function selectedFiles(root) {
  const output = []
  function visit(path) {
    for (const entry of readdirSync(path, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.name === 'node_modules') continue
      const current = join(path, entry.name)
      if (entry.isSymbolicLink()) throw new Error(`identity tree contains a symlink: ${current}`)
      if (entry.isDirectory()) visit(current)
      else if (entry.isFile() && (entry.name === 'package.json' || current.includes('/lib/'))) {
        output.push([relative(root, current), fileDigest(current)])
      }
    }
  }
  visit(root)
  return output
}

function packageTreeDigest(root) {
  return sha256Canonical(selectedFiles(resolve(root)))
}

function assertManifest(manifest) {
  if (JSON.stringify(manifest.sourceIdentity) !== JSON.stringify(EXPECTED_SOURCE)) throw new Error('current DSH source identity is not the pinned source')
  if (manifest.sourceRemote !== 'https://github.com/deepseek-ai/deepseek-harness.git') throw new Error('current DSH source remote drifted')
  if (manifest.lockfileDigest !== EXPECTED_LOCKFILE) throw new Error('current DSH lockfile identity drifted')
  if (manifest.patchDigests.map(item => item.digest).join('|') !== EXPECTED_PATCHES.join('|')) throw new Error('current governed DSH patch identity drifted')
  if (manifest.builtCliDigest !== EXPECTED_BUILT_CLI) throw new Error('current built CLI identity drifted')
  for (const [key, expected] of Object.entries({
    nodeExecutable: EXPECTED_EXECUTABLES.nodeExecutableDigest,
    pythonExecutable: EXPECTED_EXECUTABLES.pythonExecutableDigest,
    codexExecutable: EXPECTED_EXECUTABLES.codexExecutableDigest,
    claudeExecutable: EXPECTED_EXECUTABLES.claudeExecutableDigest,
  })) {
    if (manifest.executableFingerprints?.[key] !== expected) throw new Error(`current ${key} identity drifted`)
  }
  requireFile(manifest.builtCliAbsolutePath, 'built CLI')
  for (const [label, path] of Object.entries(manifest.workspaceBundledChunks ?? {})) requireFile(path, `runtime chunk ${label}`)
  if (fileDigest(manifest.builtCliAbsolutePath) !== manifest.builtCliDigest) throw new Error('built CLI bytes drifted from manifest')
}

export function runtimeIdentityFromManifest(manifest) {
  assertManifest(manifest)
  return {
    phaseId: manifest.phaseId,
    sourceIdentity: manifest.sourceIdentity,
    packageManagerFingerprint: {
      declaredPackageManager: manifest.packageManagerFingerprint.declaredPackageManager,
      actualVersion: manifest.packageManagerFingerprint.actualVersion,
      executableDigest: manifest.packageManagerFingerprint.executableDigest,
    },
    lockfileDigest: manifest.lockfileDigest,
    patchDigests: manifest.patchDigests.map(item => item.digest),
    builtCliDigest: manifest.builtCliDigest,
    builtCliRelativePath: manifest.buildIdentity.entrypointRelativePath,
    workspaceBundledChunkDigests: Object.fromEntries(
      Object.entries(manifest.workspaceBundledChunks).sort(([left], [right]) => left.localeCompare(right)).map(([path, absolute]) => [path, fileDigest(absolute)]),
    ),
    claudeSdkIdentity: manifest.claudeSdkIdentity,
    buildCommand: manifest.buildIdentity.command,
  }
}

export function executableIdentityFromManifest(manifest) {
  return {
    nodeExecutableDigest: manifest.executableFingerprints.nodeExecutable,
    pythonExecutableDigest: manifest.executableFingerprints.pythonExecutable,
    codexExecutableDigest: manifest.executableFingerprints.codexExecutable,
    claudeExecutableDigest: manifest.executableFingerprints.claudeExecutable,
  }
}

const parentPolicy = {
  provider: 'openai',
  model: 'gpt-5-mini',
  route: 'llm-pi-ai',
  agentLoopOnly: true,
  auxiliaryRoutesDenied: true,
  maximumLogicalRequests: 8,
  maximumOutputTokens: 4096,
  providerInternalRetries: 0,
  automaticContinuation: false,
  authorizedSpendCapUsd: '1.00',
  priceScheduleId: 'openai-gpt-5-mini-2026-08-22-4x-authorization-reserve-v0',
  inputUsdPerMillion: '0.25',
  outputUsdPerMillion: '2.00',
  priceUncertaintyMultiplier: '4',
  nonTextModalitiesDenied: true,
  reservationBeforeAdapterIo: true,
}

const childPolicy = {
  modelFacingTools: ['subagent_codex', 'subagent_claude_code'],
  exactOrder: ['codex_initial', 'claude_review', 'codex_repair_if_critical_high', 'claude_rereview_if_repaired'],
  codexMaximum: 2,
  claudeMaximum: 2,
  durableReservationBeforeRawProviderStart: true,
  crashAfterReservationFailsClosed: true,
  genericAlternateAndBackgroundRoutesDenied: true,
  rawExecutableResolutionRestrictedToPreflightedPath: true,
}

const claudePolicy = {
  allowedTools: ['Read', 'Glob', 'Grep'],
  tools: ['Read', 'Glob', 'Grep'],
  disallowedTools: ['Write', 'Edit', 'Bash', 'Agent', 'Task', 'mcp__*', 'AskUserQuestion', 'delegation'],
  permissionMode: 'dontAsk',
  settingSources: [],
  strictMcpConfig: true,
  mcpServers: {},
  agents: {},
  plugins: [],
  persistence: false,
  writeAllowed: false,
  editAllowed: false,
  bashAllowed: false,
  agentAllowed: false,
  taskAllowed: false,
  mcpAllowed: false,
  delegationAllowed: false,
  askUserQuestionAllowed: false,
}

const claimPolicy = {
  createOnlyRemoteGitRef: true,
  durableIntentBeforeRemotePush: true,
  exclusiveLocalReceipt: true,
  partialAmbiguousOrRestartStateBlocksReplay: true,
  compensationDeletionForbidden: true,
}

const secretPolicy = {
  parentCredentialViaExactExtraEnvSeam: true,
  gateSubprocessEnvironmentAllowlisted: true,
  nativeChildCredentialScrubReliesOnBoundDshRuntime: true,
  qntyLabRootDerivedByLauncher: true,
  realSecretPathNeverUsedByOfflineQualification: true,
}

const workspacePolicy = {
  realpathSymlinkAware: true,
  workspaceMustBeOutsideQntyLabRoot: true,
  workspaceMustBeOutsideRuntimeRoot: true,
  workspaceMustBeDisposable: true,
  noQntyLabOrQntyMutation: true,
}

const profileFiles = ['cordis.patch.yml', 'cordis.yml', 'package.json', 'pnpm-workspace.yaml']
const runtimePackagePaths = {
  'dsh-llm': 'packages/llm/llm',
  'dsh-llm-pi-ai': 'packages/llm/llm-pi-ai',
  'dsh-subagent-claude-code': 'packages/subagent/subagent-claude-code',
  'dsh-subagent-codex': 'packages/subagent/subagent-codex',
  'dsh-subprocess': 'packages/subprocess/subprocess',
  'dsh-tool-subagent': 'packages/subagent/tool-subagent',
}

function profileIdentity(profileHome) {
  const profileRoot = resolve(profileHome, 'profiles/headless')
  return Object.fromEntries(profileFiles.map(name => [name, fileDigest(requireFile(join(profileRoot, name), `qualified DSH_HOME ${name}`))]))
}

function stageAFileDigests() {
  const paths = [
    'qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py',
    relative(ROOT, join(STAGE_A_PHASE, 'evidence/canonical-json.mjs')),
    relative(ROOT, join(STAGE_A_PHASE, 'evidence/compute-digests.mjs')),
    relative(ROOT, join(STAGE_A_PHASE, 'launcher/qntylab-launch-dsh.mjs')),
    relative(ROOT, join(STAGE_A_PHASE, 'profile/cordis.patch.yml')),
    relative(ROOT, join(STAGE_A_PHASE, 'profile/qntylab-stage-a-gated-provider/package.json')),
    relative(ROOT, join(STAGE_A_PHASE, 'profile/qntylab-stage-a-gated-provider/lib/index.js')),
    relative(ROOT, join(STAGE_A_PHASE, 'profile/qntylab-stage-a-gated-provider/lib/gated-provider.mjs')),
    relative(ROOT, join(STAGE_A_PHASE, 'profile/qntylab-stage-a-parent-enforcement/package.json')),
    relative(ROOT, join(STAGE_A_PHASE, 'profile/qntylab-stage-a-parent-enforcement/lib/index.js')),
    relative(ROOT, join(STAGE_A_PHASE, 'profile/qntylab-stage-a-parent-enforcement/lib/guard.mjs')),
    relative(ROOT, join(STAGE_A_PHASE, 'stub/offline-stub.patch.yml')),
    relative(ROOT, join(STAGE_A_PHASE, 'stub/native-child-stub.mjs')),
    relative(ROOT, join(STAGE_A_PHASE, 'stub/qntylab-stage-a-stub-provider/package.json')),
    relative(ROOT, join(STAGE_A_PHASE, 'stub/qntylab-stage-a-stub-provider/lib/index.js')),
    relative(ROOT, join(PHASE, 'stub/offline-provider-overlay.patch.yml')),
  ]
  const digests = Object.fromEntries(paths.sort().map(path => [path, fileDigest(requireFile(join(ROOT, path), `Stage-A artifact ${path}`))]))
  // NOTE: the dependency manifest is intentionally NOT a key in the produced
  // digest map. `verifyPolicyBytes` in the composite launcher treats every key
  // as a file path, and the manifest is an explicit DAG representation, not a
  // file leaf in the identity bytes. It is exposed on the computeDigests()
  // result as `dependencyClosure` instead, keeping the reverse-transitive
  // invalidation mechanically provable without altering the derived digests.
  return digests
}

function verifyOverlayComposition() {
  const canonical = readFileSync(join(STAGE_A_PHASE, 'profile/cordis.patch.yml'), 'utf8')
  const overlay = readFileSync(join(PHASE, 'stub/offline-provider-overlay.patch.yml'), 'utf8')
  for (const token of [
    'qntylab-stage-a-gated-codex',
    'qntylab-stage-a-gated-claude',
    'qntylab-stage-a-parent-enforcement',
    'enableRunInBackground: false',
    'maxRetries: 0',
    'maxTokens: 4096',
  ]) {
    if (!canonical.includes(token)) throw new Error(`canonical Stage-A policy is missing ${token}`)
  }
  for (const token of ['subagent-codex', 'subagent-claude-code', 'qntylab-offline-raw-codex', 'qntylab-offline-raw-claude', '@qntylab/dsh-stage-a-stub-provider']) {
    if (!overlay.includes(token)) throw new Error(`offline overlay is missing ${token}`)
  }
  if (overlay.includes('qntylab-stage-a-parent-enforcement') || overlay.includes('tool-subagent-control')) throw new Error('offline overlay attempts to replace Stage-A control policy')
  return {
    mode: 'canonical-policy-then-additive-provider-overlay',
    canonicalPolicyActive: true,
    changedIds: ['subagent-codex', 'subagent-claude-code'],
  }
}

function stageAPolicy(profileHome, manifest) {
  const productionFileDigests = stageAFileDigests()
  const overlayComposition = verifyOverlayComposition()
  const runtimeRoot = resolve(manifest.materializationRoot)
  const qualifiedRuntimePackageTreeDigests = Object.fromEntries(
    Object.entries(runtimePackagePaths).map(([name, path]) => [name, packageTreeDigest(join(runtimeRoot, path))]),
  )
  return {
    schemaVersion: 'dsh-stage-a-v1r3r2-composite-launch-policy-v0',
    projectId: PROJECT_ID,
    predecessorQualifiedContractDigest: PREDECESSOR_QUALIFIED_CONTRACT,
    productionFileDigests,
    canonicalPolicy: {
      path: relative(ROOT, join(STAGE_A_PHASE, 'profile/cordis.patch.yml')),
      digest: productionFileDigests[relative(ROOT, join(STAGE_A_PHASE, 'profile/cordis.patch.yml'))],
    },
    offlineProviderOverlay: {
      path: relative(ROOT, join(PHASE, 'stub/offline-provider-overlay.patch.yml')),
      digest: productionFileDigests[relative(ROOT, join(PHASE, 'stub/offline-provider-overlay.patch.yml'))],
      composition: overlayComposition,
    },
    qualifiedDshHomeProfileDigests: profileIdentity(profileHome),
    qualifiedRuntimePackageTreeDigests,
    parentPolicy,
    childPolicy,
    claimPolicy,
    secretPolicy,
    claudePolicy,
    workspacePolicy,
    orderingPolicy: [
      'canonical-authority',
      'activation',
      'qualified-contract',
      'physical-runtime-and-executable',
      'workspace',
      'budget-and-child-controls',
      'non-secret-gates',
      'real-secret-read',
      'claim-creation',
      'first-potentially-paid-provider-dispatch',
    ],
    alternateRoutes: {
      providers: [],
      models: [],
      childTools: ['subagent_codex', 'subagent_claude_code'],
      backgroundDelegation: false,
    },
  }
}

export function computeDigests({ manifestPath = process.env.QNTYLAB_DSH_MANIFEST || MANIFEST_DEFAULT, profileHome = process.env.QNTYLAB_QUALIFIED_DSH_HOME || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home' } = {}) {
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  const runtimeIdentity = runtimeIdentityFromManifest(manifest)
  const executableIdentity = executableIdentityFromManifest(manifest)
  if (sha256Canonical(executableIdentity) !== 'ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9') throw new Error('current executable identity digest is not qualified')
  const runtimeManifestDigest = sha256Canonical(runtimeIdentity)
  const executableIdentityDigest = sha256Canonical(executableIdentity)
  const physicalLauncherPath = join(PHYSICAL_PHASE, 'launcher/qntylab-launch-dsh.mjs')
  const materializerPath = join(PHYSICAL_PHASE, 'materializer/qntylab-materialize-dsh-runtime.mjs')
  const physicalBinding = {
    sourceRemote: manifest.sourceRemote,
    sourceIdentity: manifest.sourceIdentity,
    runtimeManifestDigest,
    executableIdentityDigest,
    lockfileDigest: manifest.lockfileDigest,
    builtCliDigest: manifest.builtCliDigest,
    physicalLauncher: {
      path: relative(ROOT, physicalLauncherPath),
      digest: fileDigest(requireFile(physicalLauncherPath, 'physical launcher')),
    },
    materializer: {
      path: relative(ROOT, materializerPath),
      version: manifest.materializerIdentity.version,
      digest: fileDigest(requireFile(materializerPath, 'physical materializer')),
    },
    governedPatchDigests: manifest.patchDigests.map(item => item.digest),
    builtCliRelativePath: manifest.buildIdentity.entrypointRelativePath,
  }
  if (manifest.launcherIdentity.digest !== physicalBinding.physicalLauncher.digest) throw new Error('manifest does not bind the current physical launcher bytes')
  const stageA = stageAPolicy(profileHome, manifest)
  const compositeLauncherPath = join(PHASE, 'launcher/qntylab-launch-dsh.mjs')
  const compositeLaunchPolicy = {
    schemaVersion: 'dsh-stage-a-v1r3r2-composite-launch-policy-envelope-v0',
    projectId: PROJECT_ID,
    predecessorQualifiedContractDigest: PREDECESSOR_QUALIFIED_CONTRACT,
    physicalRuntimeBinding: physicalBinding,
    stageAPolicy: stageA,
    compositeLauncher: {
      path: relative(ROOT, compositeLauncherPath),
      digest: fileDigest(requireFile(compositeLauncherPath, 'composite launcher')),
    },
    immediatePreSpawnRevalidation: {
      physicalManifest: true,
      executableIdentity: true,
      dshHomeProfile: true,
      stageAPolicyBytes: true,
      contractArtifact: true,
      suppliedPreflightReceiptRejectedUnlessMatching: true,
    },
    offlineQualification: {
      loopbackParentOnly: true,
      fakeSentinelCredentialOnly: true,
      canonicalStageAPolicyRemainsActive: true,
      additiveProviderOverlayOnly: true,
      realSecretPathForbidden: '~/.secrets/openai_api_key_stage_a',
      publicProviderRequests: 0,
      realModelCalls: 0,
      realChildTurns: 0,
      spendUsd: 0,
    },
    workspacePolicy: workspacePolicy,
    secretClaimOrdering: secretPolicy,
    parentPolicy,
    childPolicy,
    claudePolicy,
    claimPolicy,
  }
  const compositeLaunchPolicyDigest = sha256Canonical(compositeLaunchPolicy)
  const qualifiedContract = {
    projectId: PROJECT_ID,
    predecessorQualifiedContractDigest: PREDECESSOR_QUALIFIED_CONTRACT,
    RUNTIME_MANIFEST_DIGEST: runtimeManifestDigest,
    EXECUTABLE_IDENTITY_DIGEST: executableIdentityDigest,
    COMPOSITE_LAUNCH_POLICY_DIGEST: compositeLaunchPolicyDigest,
    PHYSICAL_RUNTIME_BYTES_CHANGED: false,
    DSH_SOURCE_BYTES_CHANGED: false,
    GOVERNED_DSH_PATCHES_CHANGED: false,
    COMPOSITE_LAUNCH_POLICY_CHANGED: true,
  }
  const contract = {
    artifactType: 'DSH_STAGE_A_V1R3R2_COMPOSITE_QUALIFIED_LAUNCH_CONTRACT',
    schemaVersion: 'dsh-stage-a-v1r3r2-composite-launch-contract-v0',
    projectId: PROJECT_ID,
    predecessor: {
      qualifiedContractDigest: PREDECESSOR_QUALIFIED_CONTRACT,
      historicalContractPreserved: true,
      historicalContractPath: 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_launch_contract_requalification_v0/evidence/contract.json',
    },
    components: { runtimeIdentity, executableIdentity, compositeLaunchPolicy },
    digests: {
      RUNTIME_MANIFEST_DIGEST: runtimeManifestDigest,
      EXECUTABLE_IDENTITY_DIGEST: executableIdentityDigest,
      COMPOSITE_LAUNCH_POLICY_DIGEST: compositeLaunchPolicyDigest,
    },
    qualifiedContract,
    qualifiedContractDigest: sha256Canonical(qualifiedContract),
  }
  const rootChangedLeaf = 'qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py'
  const dependencyClosure = {
    manifestDigest: sha256Canonical(DEPENDENCY_MANIFEST),
    rootChangedLeaf,
    reverseTransitiveClosure: reverseTransitiveClosure(rootChangedLeaf),
    invalidationModel: 'complete_reverse_transitive_closure_over_real_dag',
  }
  return {
    contract,
    runtimeManifestDigest,
    executableIdentityDigest,
    compositeLaunchPolicyDigest,
    NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST: contract.qualifiedContractDigest,
    predecessorQualifiedContractDigest: PREDECESSOR_QUALIFIED_CONTRACT,
    sourceIdentity: manifest.sourceIdentity,
    profileHome,
    manifestPath,
    dependencyClosure,
  }
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])
if (isMain) {
  const result = computeDigests()
  const replicaManifest = process.env.QNTYLAB_DSH_REPLICA_MANIFEST
  const replica = replicaManifest
    ? computeDigests({ manifestPath: replicaManifest, profileHome: process.env.QNTYLAB_DSH_REPLICA_DSH_HOME || result.profileHome })
    : result
  const output = {
    artifactType: 'DSH_STAGE_A_V1R3R2_COMPOSITE_IDENTITY_DIGESTS',
    schemaVersion: 'dsh-stage-a-v1r3r2-composite-identity-digests-v0',
    ...result,
    reproducibility: {
      sourceIdentityMatch: JSON.stringify(result.sourceIdentity) === JSON.stringify(replica.sourceIdentity),
      runtimeManifestDigestMatch: result.runtimeManifestDigest === replica.runtimeManifestDigest,
      executableIdentityDigestMatch: result.executableIdentityDigest === replica.executableIdentityDigest,
      compositeLaunchPolicyDigestMatch: result.compositeLaunchPolicyDigest === replica.compositeLaunchPolicyDigest,
      qualifiedContractDigestMatch: result.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST === replica.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
    },
  }
  const { mkdirSync, writeFileSync } = await import('node:fs')
  // CURRENT-generation evidence is written ONLY to the explicit new
  // reconciliation path. The historical contract.json / digests.json (a392
  // lineage) are immutable and are never overwritten by this CLI.
  mkdirSync(dirname(CURRENT_CONTRACT_PATH), { recursive: true })
  writeFileSync(CURRENT_CONTRACT_PATH, `${JSON.stringify(result.contract, null, 2)}\n`)
  writeFileSync(CURRENT_DIGESTS_PATH, `${JSON.stringify(output, null, 2)}\n`)
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`)
}
