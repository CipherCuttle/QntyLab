import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { sha256Canonical } from './canonical-json.mjs'

export const PHASE = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const ROOT = resolve(PHASE, '../../../..')
const PREDECESSOR = resolve(
  PHASE,
  '../dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/evidence/digests.json',
)
const fileDigest = path => createHash('sha256').update(readFileSync(path)).digest('hex')

export function runtimeIdentityFromManifest(manifest) {
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
    builtCliRelativePath: 'apps/cli/lib/bin.js',
    workspaceBundledChunkDigests: Object.fromEntries(
      Object.entries(manifest.workspaceBundledChunks).map(([path, absolute]) => [path, fileDigest(absolute)]),
    ),
    claudeSdkIdentity: manifest.claudeSdkIdentity,
  }
}

export function computeDigests() {
  const old = JSON.parse(readFileSync(PREDECESSOR, 'utf8'))
  if (sha256Canonical(old.components.runtimeIdentity) !== old.RUNTIME_MANIFEST_DIGEST) {
    throw new Error('predecessor runtime identity digest is internally inconsistent')
  }
  if (sha256Canonical(old.components.executableIdentity) !== old.EXECUTABLE_IDENTITY_DIGEST) {
    throw new Error('predecessor executable identity digest is internally inconsistent')
  }
  const productionPaths = [
    'qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py',
    relative(ROOT, join(PHASE, 'evidence/canonical-json.mjs')),
    relative(ROOT, join(PHASE, 'evidence/compute-digests.mjs')),
    relative(ROOT, join(PHASE, 'launcher/qntylab-launch-dsh.mjs')),
    relative(ROOT, join(PHASE, 'profile/cordis.patch.yml')),
    relative(ROOT, join(PHASE, 'profile/qntylab-stage-a-gated-provider/package.json')),
    relative(ROOT, join(PHASE, 'profile/qntylab-stage-a-gated-provider/lib/index.js')),
    relative(ROOT, join(PHASE, 'profile/qntylab-stage-a-gated-provider/lib/gated-provider.mjs')),
    relative(ROOT, join(PHASE, 'profile/qntylab-stage-a-parent-enforcement/package.json')),
    relative(ROOT, join(PHASE, 'profile/qntylab-stage-a-parent-enforcement/lib/index.js')),
    relative(ROOT, join(PHASE, 'profile/qntylab-stage-a-parent-enforcement/lib/guard.mjs')),
    relative(ROOT, join(PHASE, 'stub/offline-stub.patch.yml')),
    relative(ROOT, join(PHASE, 'stub/native-child-stub.mjs')),
    relative(ROOT, join(PHASE, 'stub/qntylab-stage-a-stub-provider/package.json')),
    relative(ROOT, join(PHASE, 'stub/qntylab-stage-a-stub-provider/lib/index.js')),
  ]
  const productionFileDigests = Object.fromEntries(
    productionPaths.sort().map(path => [path, fileDigest(join(ROOT, path))]),
  )
  const launchPolicy = {
    schemaVersion: 'dsh-stage-a-v1r3r2-prelive-repaired-launch-policy-v0',
    projectId: 'DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_V0',
    predecessorQualifiedLaunchContractDigest: old.QUALIFIED_LAUNCH_CONTRACT_DIGEST,
    productionFileDigests,
    qualifiedDshHomeProfileDigests: {
      'cordis.patch.yml': 'ef189a8c27db6d63930aa3046a3040482e952eafcb7487c644d508e8d461f027',
      'cordis.yml': 'c300dcf2ebc5f02062d6591268d29d3db6fe45e0cb138f5467276fe2ba06076e',
      'package.json': '563c0b6082748a6e93daad51514f01335c51fc9c44f5f88253383f18ac2557b5',
      'pnpm-workspace.yaml': 'ae7c5b68e2f157528e62885804e69e88583897b775e03c86fcbe52feaf498aba',
    },
    qualifiedRuntimePackageTreeDigests: {
      'dsh-llm': '81007276be7e45762a5c4d84ea1c743476b318ceedc6a561d44007ccb1b8cfc3',
      'dsh-llm-pi-ai': '083b6a1ae017ba27b38ed46509fae23c5f16d599caca758b5862d1a56c89e04f',
      'dsh-subagent-claude-code': 'd2df76cc6e7c7e865ad7d439fb4c1833e968e27b009d6caa8567c586e1094db4',
      'dsh-subagent-codex': '668240ad6efea07c08127bb872f2f3e57ace09295f02fd9e52ed67d6dbe7ac9a',
      'dsh-subprocess': '7e07e7d6acf593426e0e8cf10ac1704630446b8a24e6ef8534bd65cf9764caf2',
      'dsh-tool-subagent': 'bfa1cb63c10b8065dc2c30c560ad89c4f24291faee5a2edc444af814be437e13',
    },
    parentPolicy: {
      provider: 'openai',
      model: 'gpt-5-mini',
      agentLoopOnly: true,
      auxiliaryRoutesDenied: true,
      maximumLogicalRequests: 8,
      maximumOutputTokens: 4096,
      maximumInputTokenUpperBound: 123904,
      providerInternalRetries: 0,
      authorizedSpendCapUsd: '1.00',
      priceScheduleId: 'openai-gpt-5-mini-2026-08-22-4x-authorization-reserve-v0',
      inputUsdPerMillion: '0.25',
      outputUsdPerMillion: '2.00',
      priceUncertaintyMultiplier: '4',
      nonTextModalitiesDenied: true,
      reservationBeforeAdapterIo: true,
    },
    childPolicy: {
      exactOrder: ['codex_initial', 'claude_review', 'codex_repair_if_critical_high', 'claude_rereview_if_repaired'],
      codexMaximum: 2,
      claudeMaximum: 2,
      durableReservationBeforeRawProviderStart: true,
      crashAfterReservationFailsClosed: true,
      genericAlternateAndBackgroundRoutesDenied: true,
      rawExecutableResolutionRestrictedToPreflightedPath: true,
    },
    claimPolicy: {
      createOnlyRemoteGitRef: true,
      durableIntentBeforeRemotePush: true,
      exclusiveLocalReceipt: true,
      partialAmbiguousOrRestartStateBlocksReplay: true,
      compensationDeletionForbidden: true,
    },
    secretPolicy: {
      parentCredentialViaExactExtraEnvSeam: true,
      gateSubprocessEnvironmentAllowlisted: true,
      nativeChildCredentialScrubReliesOnBoundDshRuntime: true,
      qntyLabRootDerivedByLauncher: true,
    },
  }
  const NEW_RUNTIME_MANIFEST_DIGEST = old.RUNTIME_MANIFEST_DIGEST
  const NEW_EXECUTABLE_IDENTITY_DIGEST = old.EXECUTABLE_IDENTITY_DIGEST
  const NEW_LAUNCH_POLICY_DIGEST = sha256Canonical(launchPolicy)
  const qualifiedLaunchContract = {
    projectId: launchPolicy.projectId,
    NEW_RUNTIME_MANIFEST_DIGEST,
    NEW_EXECUTABLE_IDENTITY_DIGEST,
    NEW_LAUNCH_POLICY_DIGEST,
  }
  return {
    artifact_type: 'DSH_STAGE_A_V1R3R2_PRELIVE_REPAIRED_IDENTITY',
    schema_version: 'dsh-stage-a-v1r3r2-prelive-repaired-identity-v0',
    project_id: launchPolicy.projectId,
    RUNTIME_BYTES_CHANGED: false,
    LAUNCH_POLICY_CHANGED: true,
    QUALIFIED_IDENTITY_COVERED_BYTES_CHANGED: true,
    OLD_QUALIFIED_DIGEST: old.QUALIFIED_LAUNCH_CONTRACT_DIGEST,
    OLD_QUALIFIED_DIGEST_STILL_VALID: false,
    NEW_RUNTIME_MANIFEST_DIGEST,
    NEW_EXECUTABLE_IDENTITY_DIGEST,
    NEW_LAUNCH_POLICY_DIGEST,
    NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST: sha256Canonical(qualifiedLaunchContract),
    components: {
      runtimeIdentity: old.components.runtimeIdentity,
      executableIdentity: old.components.executableIdentity,
      launchPolicy,
      qualifiedLaunchContract,
    },
  }
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])
if (isMain) process.stdout.write(`${JSON.stringify(computeDigests(), null, 2)}\n`)
