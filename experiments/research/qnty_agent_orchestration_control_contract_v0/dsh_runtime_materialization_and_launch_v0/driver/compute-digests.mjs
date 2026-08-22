#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'
import { sha256Canonical } from '../../dsh_stage_a_v1r3r1_real_runtime_qualification_v0/evidence/canonical-json.mjs'

const PHASE_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const primaryPath = process.env.QNTYLAB_DSH_MANIFEST || join(PHASE_DIR, 'evidence/runtime_manifest.json')
const replicaPath = process.env.QNTYLAB_DSH_REPLICA_MANIFEST || '/var/tmp/qntylab-dsh-runtime-v0-replica-manifest.json'
const oldDigestsPath = resolve(PHASE_DIR, '../dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/evidence/digests.json')
const primary = JSON.parse(readFileSync(primaryPath, 'utf8'))
const replica = JSON.parse(readFileSync(replicaPath, 'utf8'))
const oldDigests = JSON.parse(readFileSync(oldDigestsPath, 'utf8'))
const fileDigest = path => createHash('sha256').update(readFileSync(path)).digest('hex')

function chunkDigests(manifest) {
  return Object.fromEntries(Object.entries(manifest.workspaceBundledChunks).map(([path, absolute]) => [path, fileDigest(absolute)]))
}

function runtimeIdentity(manifest) {
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

function executableIdentity(manifest) {
  return {
    nodeExecutableDigest: manifest.executableFingerprints.nodeExecutable,
    pythonExecutableDigest: manifest.executableFingerprints.pythonExecutable,
    codexExecutableDigest: manifest.executableFingerprints.codexExecutable,
    claudeExecutableDigest: manifest.executableFingerprints.claudeExecutable,
  }
}

function launchPolicy(manifest) {
  return {
    launcherDigest: manifest.launcherIdentity.digest,
    materializerDigest: manifest.materializerIdentity.digest,
    materializationDriverDigest: fileDigest(join(PHASE_DIR, 'driver/materialize-pinned-runtime.mjs')),
    qualificationDriverDigest: fileDigest(join(PHASE_DIR, 'driver/run-loopback-qualification.mjs')),
    codexRepairDigest: manifest.patchDigests[0].digest,
    claudeRepairDigest: manifest.patchDigests[1].digest,
    overlayPatchDigest: manifest.profileDigests.qualificationOverlay,
    parentProvider: 'openai',
    parentModel: 'gpt-5-mini',
    modelFacingTools: ['subagent_codex', 'subagent_claude_code'],
    workspaceContainmentPolicy: 'realpath-symlink-aware; workspace must not be inside runtime root or forbidden roots',
    retryPolicy: { llmRetries: 0, providerRetry: 0, automaticContinuation: false },
  }
}

const primaryRuntime = runtimeIdentity(primary)
const replicaRuntime = runtimeIdentity(replica)
const primaryExecutable = executableIdentity(primary)
const replicaExecutable = executableIdentity(replica)
const primaryPolicy = launchPolicy(primary)
const runtimeManifestDigest = sha256Canonical(primaryRuntime)
const executableIdentityDigest = sha256Canonical(primaryExecutable)
const launchPolicyDigest = sha256Canonical(primaryPolicy)
const qualifiedContractDigest = sha256Canonical({ phaseId: primary.phaseId, runtimeManifestDigest, executableIdentityDigest, launchPolicyDigest })

// Compare against the old contract's exact identity-bearing fields, not its
// ephemeral paths/timestamps. A pnpm 11.7 materialization is intentionally
// not laundered into the historical contract that recorded 11.22/corepack
// shim identity.
const oldShape = {
  phaseId: oldDigests.components.runtimeIdentity.phaseId,
  sourceIdentity: primary.sourceIdentity,
  packageManagerFingerprint: {
    declaredPackageManager: primary.packageManagerFingerprint.declaredPackageManager,
    actualVersion: primary.packageManagerFingerprint.actualVersion,
    executableDigest: primary.packageManagerFingerprint.executableDigest,
  },
  lockfileDigest: primary.lockfileDigest,
  patchDigests: primary.patchDigests.map(patch => patch.digest),
  builtCliDigest: primary.builtCliDigest,
  builtCliRelativePath: primary.buildIdentity.entrypointRelativePath,
  workspaceBundledChunkDigests: chunkDigests(primary),
  claudeSdkIdentity: primary.claudeSdkIdentity,
}
const oldRuntimeIdentityMatches = sha256Canonical(oldShape) === oldDigests.RUNTIME_MANIFEST_DIGEST
const oldExecutableIdentityMatches = executableIdentityDigest === oldDigests.EXECUTABLE_IDENTITY_DIGEST
const oldLauncherIdentityMatches = primary.launcherIdentity.digest === oldDigests.components.launchPolicy.launcherDigest

const output = {
  runtimeManifestDigest,
  executableIdentityDigest,
  launchPolicyDigest,
  qualifiedContractDigest,
  primaryManifestPath: primaryPath,
  replicaManifestPath: replicaPath,
  reproducibility: {
    sourceIdentityMatch: JSON.stringify(primary.sourceIdentity) === JSON.stringify(replica.sourceIdentity),
    lockfileIdentityMatch: primary.lockfileDigest === replica.lockfileDigest,
    patchIdentityMatch: JSON.stringify(primary.patchDigests.map(p => p.digest)) === JSON.stringify(replica.patchDigests.map(p => p.digest)),
    runtimeIdentityMatch: sha256Canonical(primaryRuntime) === sha256Canonical(replicaRuntime),
    executableIdentityMatch: sha256Canonical(primaryExecutable) === sha256Canonical(replicaExecutable),
  },
  oldQualifiedContract: {
    digest: 'e3b623c58d0ce591baa9d0e07d9cf4dd802203d34a4a1b1521d29f75ca302ffa',
    runtimeIdentityMatches: oldRuntimeIdentityMatches,
    executableIdentityMatches: oldExecutableIdentityMatches,
    launcherIdentityMatches: oldLauncherIdentityMatches,
    physicallyReproduced: oldRuntimeIdentityMatches && oldExecutableIdentityMatches && oldLauncherIdentityMatches,
    requalificationRequired: !(oldRuntimeIdentityMatches && oldExecutableIdentityMatches && oldLauncherIdentityMatches),
    invalidated: false,
    reason: 'Phase-D binds exact pnpm@11.7.0 and a new acquisition/launch seam; the historical contract recorded pnpm 11.22.0 and different launch-policy bytes.',
  },
}
writeFileSync(join(PHASE_DIR, 'evidence/digests.json'), `${JSON.stringify(output, null, 2)}\n`)
console.log(JSON.stringify(output, null, 2))
