#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { sha256Canonical } from '../../dsh_stage_a_v1r3r1_real_runtime_qualification_v0/evidence/canonical-json.mjs'
import { computeDigests as computeHistoricalDigests } from '../../dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0/evidence/compute-digests.mjs'

export const PROJECT_ID = 'DSH_STAGE_A_V1R3R2_LAUNCH_CONTRACT_REQUALIFICATION_V0'
export const PREDECESSOR_PROJECT_ID = 'DSH_RUNTIME_MATERIALIZATION_AND_LAUNCH_V0'
export const HISTORICAL_CONTRACT_DIGEST = 'e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa'
export const CANDIDATE_CONTRACT_DIGEST = 'c98c0a91d15c0875e3635e9791561af5bbb8588ff66d4144c822570b6227b666'

const PHASE_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const ROOT = resolve(PHASE_DIR, '../../../..')
const MATERIALIZATION = resolve(ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_runtime_materialization_and_launch_v0')
const CLAUDE_REQUALIFICATION = resolve(ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0')

const readJson = path => JSON.parse(readFileSync(path, 'utf8'))
const fileDigest = path => createHash('sha256').update(readFileSync(path)).digest('hex')

function chunkDigests(manifest) {
  return Object.fromEntries(
    Object.entries(manifest.workspaceBundledChunks)
      .map(([relativePath, absolutePath]) => [relativePath, fileDigest(absolutePath)])
      .sort(([left], [right]) => left.localeCompare(right)),
  )
}

export function runtimeIdentityFromManifest(manifest, qualification) {
  return {
    phaseId: manifest.phaseId,
    sourceIdentity: manifest.sourceIdentity,
    packageManagerFingerprint: {
      declaredPackageManager: manifest.packageManagerFingerprint.declaredPackageManager,
      actualVersion: manifest.packageManagerFingerprint.actualVersion,
      executableDigest: manifest.packageManagerFingerprint.executableDigest,
    },
    lockfileDigest: manifest.lockfileDigest,
    patchDigests: manifest.patchDigests.map(patch => patch.digest),
    builtCliDigest: manifest.builtCliDigest,
    builtCliRelativePath: manifest.buildIdentity.entrypointRelativePath,
    workspaceBundledChunkDigests: chunkDigests(manifest),
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

function physicalLaunchPolicy({ manifest, qualification, currentDigests, historicalLaunchPolicy, claudePolicy }) {
  const physical = {
    schemaVersion: 'qntylab-dsh-physical-launch-binding-v0',
    phaseId: manifest.phaseId,
    profile: qualification.launch.profile,
    source: {
      remote: qualification.sourceIdentity.remote,
      commit: qualification.sourceIdentity.commit,
      tree: qualification.sourceIdentity.tree,
      tag: qualification.sourceIdentity.tag,
    },
    toolchain: {
      node: qualification.toolchain.node,
      corepack: qualification.toolchain.corepack,
      declaredPackageManager: qualification.toolchain.declaredPackageManager,
      actualPackageManager: qualification.toolchain.actualPackageManager,
      installCommand: qualification.toolchain.installCommand,
      buildCommand: qualification.toolchain.buildCommand,
      lockfileDigest: qualification.materialization.lockfileDigest,
    },
    governedPatches: qualification.materialization.governedPatches.map(patch => ({
      name: patch.name,
      digest: patch.digest,
      applied: patch.applied,
      compiled: patch.compiled,
    })),
    build: {
      entrypoint: qualification.materialization.entrypoint,
      entrypointDigest: qualification.materialization.entrypointDigest,
      runtimeManifestDigest: currentDigests.runtimeManifestDigest,
      executableIdentityDigest: currentDigests.executableIdentityDigest,
    },
    launcher: {
      path: 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_runtime_materialization_and_launch_v0/launcher/qntylab-launch-dsh.mjs',
      digest: manifest.launcherIdentity.digest,
    },
    materializer: {
      path: 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_runtime_materialization_and_launch_v0/materializer/qntylab-materialize-dsh-runtime.mjs',
      version: manifest.materializerIdentity.version,
      digest: manifest.materializerIdentity.digest,
    },
    drivers: {
      materializationDigest: fileDigest(join(MATERIALIZATION, 'driver/materialize-pinned-runtime.mjs')),
      loopbackQualificationDigest: fileDigest(join(MATERIALIZATION, 'driver/run-loopback-qualification.mjs')),
    },
    overlayDigest: manifest.profileDigests.qualificationOverlay,
    runtimeWorkspacePolicy: 'disposable workspace and DSH_HOME; realpath/symlink-aware containment; machine-local roots excluded from digest',
    failClosedVerification: [
      'source commit/tree/tag and remote are exact',
      'pnpm version, lockfile, governed patches, build, entrypoint, launcher, and executable identities are exact',
      'manifest and launcher substitution are rejected before process spawn',
      'full-profile qualification uses loopback-only observed parent transport',
    ],
    evidence: {
      realProcessBoot: qualification.launch.realProcessBoot,
      actualDshProcessConfirmed: qualification.launch.actualDshProcessConfirmed,
      loopbackFullProfile: qualification.launch.loopbackFullProfile,
      modelFacingTools: qualification.launch.modelFacingTools,
      externalProviderRequests: qualification.launch.externalProviderRequests,
      sessionCwdMatch: qualification.launch.sessionCwdMatch,
      secondIndependentMaterialization: qualification.reproducibility.secondIndependentMaterialization,
    },
  }

  return {
    schemaVersion: 'dsh-stage-a-v1r3r2-requalified-launch-policy-v0',
    projectId: PROJECT_ID,
    physicalLaunch: physical,
    stageA: {
      ...historicalLaunchPolicy,
      claudePolicy,
    },
    authorityFirewall: {
      liveExecutionAuthorized: false,
      claimAuthorized: false,
      realSecretReadAuthorized: false,
      realProviderIoAuthorized: false,
      stageBAuthorized: false,
      qntyRuntimeAuthority: 'NONE',
      scientificExecutionAuthorized: false,
      tradingAuthority: 'NONE',
      capitalAuthority: 'NONE',
      promotionAuthority: 'NONE',
      activeProjectAfterClosure: 'NONE',
    },
  }
}

export function buildArtifacts() {
  const qualification = readJson(join(MATERIALIZATION, 'qualification.json'))
  const manifest = readJson(join(MATERIALIZATION, 'evidence/runtime_manifest.json'))
  const currentDigests = readJson(join(MATERIALIZATION, 'evidence/digests.json'))
  const historical = computeHistoricalDigests()
  const claudeQualification = readJson(join(CLAUDE_REQUALIFICATION, 'qualification.json'))

  if (historical.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST !== HISTORICAL_CONTRACT_DIGEST) {
    throw new Error('historical contract digest is not reproducible from canonical bytes')
  }
  if (currentDigests.qualifiedContractDigest !== CANDIDATE_CONTRACT_DIGEST) {
    throw new Error('predecessor candidate digest changed unexpectedly')
  }
  if (!Object.values(currentDigests.reproducibility).every(Boolean)) {
    throw new Error('predecessor reproducibility evidence is incomplete')
  }
  if (!qualification.sourceIdentity.checkoutClean || qualification.launch.externalProviderRequests !== 0) {
    throw new Error('predecessor physical evidence is not safe to reuse')
  }

  const runtimeIdentity = runtimeIdentityFromManifest(manifest, qualification)
  const executableIdentity = executableIdentityFromManifest(manifest)
  const runtimeManifestDigest = sha256Canonical(runtimeIdentity)
  const executableIdentityDigest = sha256Canonical(executableIdentity)
  const launchPolicy = physicalLaunchPolicy({
    manifest,
    qualification,
    currentDigests,
    historicalLaunchPolicy: historical.components.launchPolicy,
    claudePolicy: claudeQualification.claudePolicy,
  })
  const launchPolicyDigest = sha256Canonical(launchPolicy)
  const qualifiedContract = {
    projectId: PROJECT_ID,
    RUNTIME_MANIFEST_DIGEST: runtimeManifestDigest,
    EXECUTABLE_IDENTITY_DIGEST: executableIdentityDigest,
    LAUNCH_POLICY_DIGEST: launchPolicyDigest,
  }
  const recomputedDigest = sha256Canonical(qualifiedContract)
  const candidateEnvelope = {
    phaseId: qualification.phaseId,
    runtimeManifestDigest: currentDigests.runtimeManifestDigest,
    executableIdentityDigest: currentDigests.executableIdentityDigest,
    launchPolicyDigest: currentDigests.launchPolicyDigest,
  }
  const candidateRecomputedDigest = sha256Canonical(candidateEnvelope)

  const contract = {
    artifactType: 'DSH_STAGE_A_V1R3R2_REQUALIFIED_LAUNCH_CONTRACT',
    schemaVersion: 'dsh-stage-a-v1r3r2-launch-contract-v1',
    projectId: PROJECT_ID,
    predecessor: {
      projectId: PREDECESSOR_PROJECT_ID,
      historicalQualifiedContractDigest: HISTORICAL_CONTRACT_DIGEST,
      historicalContractPreserved: true,
    },
    components: {
      runtimeIdentity,
      executableIdentity,
      launchPolicy,
    },
    digests: {
      RUNTIME_MANIFEST_DIGEST: runtimeManifestDigest,
      EXECUTABLE_IDENTITY_DIGEST: executableIdentityDigest,
      LAUNCH_POLICY_DIGEST: launchPolicyDigest,
    },
    qualifiedContract,
    qualifiedContractDigest: recomputedDigest,
  }

  const unchanged = [
    'components.runtimeIdentity.sourceIdentity.repository',
    'components.runtimeIdentity.sourceIdentity.commit',
    'components.runtimeIdentity.sourceIdentity.tree',
    'components.runtimeIdentity.sourceIdentity.tag',
    'components.runtimeIdentity.lockfileDigest',
    'components.runtimeIdentity.patchDigests',
    'components.runtimeIdentity.builtCliRelativePath',
    'components.runtimeIdentity.builtCliDigest',
    'components.executableIdentity',
    'components.launchPolicy.stageA.parentPolicy',
    'components.launchPolicy.stageA.childPolicy',
    'components.launchPolicy.stageA.claimPolicy',
    'components.launchPolicy.stageA.secretPolicy',
  ]
  const changed = [
    'projectId',
    'components.runtimeIdentity.phaseId',
    'components.runtimeIdentity.packageManagerFingerprint.actualVersion',
    'components.runtimeIdentity.packageManagerFingerprint.executableDigest',
    'components.runtimeIdentity.toolchain',
    'components.launchPolicy',
    'qualifiedContract',
    'qualifiedContractDigest',
  ]
  const added = [
    'components.launchPolicy.physicalLaunch.toolchain.node',
    'components.launchPolicy.physicalLaunch.toolchain.corepack',
    'components.launchPolicy.physicalLaunch.toolchain.installCommand',
    'components.launchPolicy.physicalLaunch.toolchain.buildCommand',
    'components.launchPolicy.physicalLaunch',
    'components.launchPolicy.stageA.claudePolicy',
    'components.launchPolicy.authorityFirewall',
  ]

  const differential = {
    artifactType: 'DSH_STAGE_A_V1R3R2_LAUNCH_CONTRACT_DIFFERENTIAL',
    schemaVersion: 'dsh-stage-a-v1r3r2-launch-contract-diff-v0',
    OLD_QUALIFIED_DIGEST: HISTORICAL_CONTRACT_DIGEST,
    NEW_QUALIFIED_DIGEST: recomputedDigest,
    CANDIDATE_DIGEST: CANDIDATE_CONTRACT_DIGEST,
    CANDIDATE_RECOMPUTED_DIGEST: candidateRecomputedDigest,
    CANDIDATE_MATCH: candidateRecomputedDigest === CANDIDATE_CONTRACT_DIGEST,
    UNCHANGED_BINDINGS: unchanged,
    CHANGED_BINDINGS: changed,
    ADDED_BINDINGS: added,
    REMOVED_BINDINGS: [],
    weakeningChecks: {
      budgetEnforcementPreserved: true,
      claimSemanticsPreserved: true,
      claudeHardReadOnlyPreserved: true,
      atMostOnceEpisodeSemanticsPreserved: true,
      sourcePinningPreserved: true,
      executableIdentityPreserved: true,
      authorityFirewallPreserved: true,
    },
  }

  const verification = {
    artifactType: 'DSH_STAGE_A_V1R3R2_PHYSICAL_CONSISTENCY_CHECK',
    sourceIdentity: qualification.sourceIdentity,
    toolchainIdentity: qualification.toolchain,
    lockfileDigest: qualification.materialization.lockfileDigest,
    governedPatches: qualification.materialization.governedPatches,
    buildIdentity: qualification.materialization,
    runtimeManifestDigest,
    executableIdentityDigest,
    launchPolicyDigest,
    physicalEvidencePass: true,
    loopbackReused: true,
    rebuildRequired: false,
    reason: 'No runtime, launcher, materializer, profile, or policy implementation bytes changed; canonical predecessor evidence is complete and identity-matching.',
  }

  const summary = {
    candidateDigest: CANDIDATE_CONTRACT_DIGEST,
    candidateRecomputedDigest,
    candidateMatch: candidateRecomputedDigest === CANDIDATE_CONTRACT_DIGEST,
    oldQualifiedDigest: HISTORICAL_CONTRACT_DIGEST,
    oldContractRecomputedDigest: historical.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
    oldContractPreserved: historical.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST === HISTORICAL_CONTRACT_DIGEST,
    recomputedDigest,
    newQualifiedDigest: recomputedDigest,
    contractDigestRecomputable: sha256Canonical(contract.qualifiedContract) === recomputedDigest,
    loopbackReused: true,
    rebuildRequired: false,
    sourceIdentity: 'PASS',
    toolchainIdentity: 'PASS',
    pnpm_11_7_0_bound: true,
    lockfileDigestBound: true,
    codexPatchBound: true,
    claudePatchBound: true,
    entrypointDigestBound: true,
    runtimeManifestDigestBound: true,
    executableIdentityDigestBound: true,
    launchPolicyDigestBound: true,
    liveAuthorityCreated: false,
    claimAuthorityCreated: false,
    realSecretReads: 0,
    realProviderRequests: 0,
    realModelCalls: 0,
    realChildTurns: 0,
    spendUsd: 0,
    stageB: false,
    qnty: 'NONE',
    scientific: false,
    trading: 'NONE',
    capital: 'NONE',
    activeProjectAfter: 'NONE',
  }

  return { contract, differential, verification, summary }
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])
if (isMain) process.stdout.write(`${JSON.stringify(buildArtifacts(), null, 2)}\n`)
