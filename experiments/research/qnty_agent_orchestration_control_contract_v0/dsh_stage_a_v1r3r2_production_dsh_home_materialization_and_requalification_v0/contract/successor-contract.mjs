#!/usr/bin/env node

// The successor qualified launch contract.
//
// The predecessor contract a392f82e… described a launch plane whose DSH_HOME was
// an ambient, unverified precondition. Once the production DSH_HOME materializer
// joins the trusted computing base, a392 is no longer the complete final live
// contract: it is preserved as the bound predecessor, and this successor binds
// the materializer, the DSH_HOME manifest schema, and the complete production
// package graph in addition to everything a392 covered.
//
// This contract grants LIVE_AUTHORITY = false. A separate, later, Git-backed
// V0R5 authorization remains mandatory before any live episode.

import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { canonicalJson, sha256Canonical } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/canonical-json.mjs'
import { computeDigests } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/compute-digests.mjs'
import {
  DEFAULT_RUNTIME_MANIFEST,
  DSH_HOME_MANIFEST_SCHEMA_VERSION,
  MaterializationError,
  ROOT,
} from '../materializer/qntylab-materialize-stage-a-dsh-home.mjs'

const PHASE = resolve(fileURLToPath(import.meta.url), '../..')

export const PROJECT_ID = 'DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AND_REQUALIFICATION_V0'
export const SUCCESSOR_CONTRACT_SCHEMA_VERSION = 'qntylab-stage-a-v1r3r2-production-qualified-launch-contract-v0'

/** The historical predecessor. Preserved, bound, and explicitly superseded. */
export const PREDECESSOR_QUALIFIED_CONTRACT_DIGEST = 'a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be'

/**
 * The historical composite digest that `computeDigests()` produced at the time
 * the a392 successor was generated. a392 is only valid as a HISTORICAL input
 * identity; it must never be compared against a CURRENT recomputation.
 */
export const HISTORICAL_COMPOSITE_CONTRACT_DIGEST = PREDECESSOR_QUALIFIED_CONTRACT_DIGEST

/**
 * The historical successor contract digest (50bd7762...). Preserved and
 * immutable. It is the digest of the historical successor_contract.json and is
 * verified against historical inputs only, never recomputed-as-current.
 */
export const HISTORICAL_SUCCESSOR_CONTRACT_DIGEST = '50bd776263d05e9f2fe3e026c5e8904a12fa257a1667d11c1e22ef32376c24de'

export const MATERIALIZER_RELATIVE_PATH = relative(ROOT, join(PHASE, 'materializer/qntylab-materialize-stage-a-dsh-home.mjs'))
export const COMPOSITE_LAUNCHER_RELATIVE_PATH = 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/launcher/qntylab-launch-dsh.mjs'
// DSH_STAGE_A_V1R3R2_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION_V0: the
// composite launcher now transports the five claim-binding values (HIGH-2), so
// its bytes changed. This expected digest is the NEW post-correction digest;
// the historical 6f212de0… launcher bytes are preserved in the immutable
// historical artifacts and authorization records.
export const EXPECTED_COMPOSITE_LAUNCHER_DIGEST = 'bf0baf30cc5b6ca9206c0bf4ea6357cfc37fc60b11ddf1ee06e8a9f8b252634c'

/** The governing authorization these implementation bytes are bound to. */
export const GOVERNING_AUTHORIZATION = Object.freeze({
  projectId: 'DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AND_ACTION_TIME_PARITY_AUTHORIZATION_V0',
  artifactPath: 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_action_time_parity_authorization_v0/authorization.json',
  artifactSha256: 'e0a056b5b8905736ab174fa46407166ab8f1357ef1f6e082e69a3f51f265c221',
  artifactGitBlobSha1: 'b2294649e2b66046b1ce8160722626800efdd4e8',
  canonicalMaster: '838b6e03608e4c2bc686a4f571dfbb340a333ddb',
})

/** The Stage-A bounded-retry fixture, bound by its frozen identity. */
export const FIXTURE = Object.freeze({
  fixtureId: 'STAGE_A_BOUNDED_RETRY_V0',
  fixtureRoot: 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_authorization_v0/fixture',
  expectedFixtureDigest: '397ed055f2fb5cd14fd4c0b54fc21994c688f6cf56f07fb073d4e3257cd47552',
  digestBasis: 'sha256 of canonical JSON of {"fixture/<relative path>": sha256}',
  files: Object.freeze(['TASK.md', 'retry.py', 'tests/test_retry.py']),
  mutablePaths: Object.freeze(['retry.py']),
  immutablePaths: Object.freeze(['TASK.md', 'tests/test_retry.py']),
  freshDisposableCopyRequired: true,
  canonicalFixtureMutationAllowed: false,
})

const digestFile = path => createHash('sha256').update(readFileSync(path)).digest('hex')

const failWith = (code, message) => { throw new MaterializationError(code, message) }

/** Recompute the canonical fixture identity from Git-tracked bytes. */
export function computeFixtureIdentity(qntyLabRoot = ROOT) {
  const root = join(qntyLabRoot, FIXTURE.fixtureRoot)
  const digests = {}
  for (const file of FIXTURE.files) {
    const path = join(root, file)
    if (!existsSync(path)) failWith('BLOCK_FIXTURE_IDENTITY', `canonical fixture file missing: ${file}`)
    digests[`fixture/${file}`] = digestFile(path)
  }
  const fixtureDigest = createHash('sha256')
    .update(JSON.stringify(digests, Object.keys(digests).sort()))
    .digest('hex')
  if (fixtureDigest !== FIXTURE.expectedFixtureDigest) {
    failWith('BLOCK_FIXTURE_IDENTITY', `canonical Stage-A fixture drifted: ${fixtureDigest}`)
  }
  return { fixtureId: FIXTURE.fixtureId, fixtureRoot: FIXTURE.fixtureRoot, fixtureDigest, initialFileDigestsSha256: digests }
}

/** The schema of the DSH_HOME manifest, bound by digest so substitution is detectable. */
export const DSH_HOME_MANIFEST_SCHEMA = Object.freeze({
  schemaVersion: DSH_HOME_MANIFEST_SCHEMA_VERSION,
  identityFields: Object.freeze([
    'artifactType', 'schemaVersion', 'classification', 'provenance',
    'packageInventory', 'objects', 'productionStubProviderPresent', 'nondeterministicResidue',
  ]),
  excludedFromIdentity: Object.freeze([
    'homeManifestDigest', 'materializedAtUtc', 'destinationAbsolutePath', 'materializationRootAbsolutePath',
  ]),
  objectFields: Object.freeze({
    file: Object.freeze(['path', 'type', 'digest', 'byteLength', 'canonicalSource', 'classification']),
    symlink: Object.freeze([
      'path', 'type', 'packageName', 'declaredName', 'version',
      'targetRelativeToRuntimeRoot', 'targetRealpathRelativeToRuntimeRoot',
      'containment', 'packageJsonDigest', 'canonicalSource', 'classification',
    ]),
    'package-tree': Object.freeze([
      'path', 'type', 'packageName', 'declaredName', 'version',
      'packageTreeDigest', 'wholeTreeDigest', 'fileCount',
      'canonicalSource', 'canonicalSourcePath', 'classification',
    ]),
  }),
  digestAlgorithm: 'sha256-over-canonical-json',
})

export const DSH_HOME_MANIFEST_SCHEMA_DIGEST = sha256Canonical(DSH_HOME_MANIFEST_SCHEMA)

/**
 * Compute the successor qualified launch contract.
 * @param homeManifest - the identity body of a PRODUCTION DSH_HOME manifest.
 */
export function computeSuccessorContract({
  homeManifest,
  profileHome,
  runtimeManifestPath = DEFAULT_RUNTIME_MANIFEST,
  qntyLabRoot = ROOT,
} = {}) {
  if (homeManifest === undefined) failWith('BLOCK_HOME_MANIFEST', 'a production DSH_HOME manifest is required')
  // The predecessor plane must be recomputed against the freshly materialized
  // production home, never against an ambient scratch DSH_HOME. Defaulting here
  // would reintroduce exactly the dependency this phase exists to remove.
  if (typeof profileHome !== 'string' || profileHome.length === 0) {
    failWith('BLOCK_HOME_MANIFEST', 'a materialized production DSH_HOME path is required; ambient fallback is forbidden')
  }
  if (homeManifest.classification !== 'PRODUCTION') {
    failWith('BLOCK_HOME_MANIFEST', `successor contract requires a PRODUCTION home manifest; got ${homeManifest.classification}`)
  }
  if (homeManifest.productionStubProviderPresent !== false) {
    failWith('BLOCK_PRODUCTION_STUB_PROVIDER', 'production home manifest reports a stub provider')
  }
  if (homeManifest.schemaVersion !== DSH_HOME_MANIFEST_SCHEMA_VERSION) {
    failWith('BLOCK_HOME_MANIFEST', `unexpected DSH_HOME manifest schema: ${homeManifest.schemaVersion}`)
  }

  // The current composite plane, recomputed from live bytes rather than
  // asserted. This is the CURRENT execution-contract root: it derives
  // mechanically from the CURRENT resolved canonical inputs. It is NOT compared
  // against the historical a392 digest — a392 is a historical input identity,
  // not the expected current value. Comparing current recomputation to a
  // historical digest is exactly the identity-conflation this reconciliation
  // removes.
  const composite = computeDigests({ manifestPath: runtimeManifestPath, profileHome })
  const currentCompositeRoot = composite.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST
  if (currentCompositeRoot === undefined || typeof currentCompositeRoot !== 'string' || currentCompositeRoot.length !== 64) {
    failWith('BLOCK_RUNTIME_IDENTITY', 'current composite contract root is not a valid sha256')
  }
  if (currentCompositeRoot === HISTORICAL_COMPOSITE_CONTRACT_DIGEST) {
    failWith('BLOCK_RUNTIME_IDENTITY', 'current composite contract root must not equal the historical a392 root; the current root must be mechanically re-derived')
  }

  const materializerPath = join(qntyLabRoot, MATERIALIZER_RELATIVE_PATH)
  if (!existsSync(materializerPath)) failWith('BLOCK_MATERIALIZER_IDENTITY', 'production materializer is missing')
  const materializerDigest = digestFile(materializerPath)

  const launcherPath = join(qntyLabRoot, COMPOSITE_LAUNCHER_RELATIVE_PATH)
  const compositeLauncherDigest = digestFile(launcherPath)
  if (compositeLauncherDigest !== EXPECTED_COMPOSITE_LAUNCHER_DIGEST) {
    failWith('BLOCK_RUNTIME_IDENTITY', 'composite launcher bytes changed; this phase may not modify the qualified launcher')
  }

  const policy = composite.contract.components.compositeLaunchPolicy
  const stageA = policy.stageAPolicy
  const fixture = computeFixtureIdentity(qntyLabRoot)

  const profileIdentities = Object.fromEntries(
    homeManifest.objects.filter(o => o.type === 'file')
      .map(o => [o.path.replace('profiles/headless/', ''), o.digest]),
  )
  for (const [name, expected] of Object.entries(stageA.qualifiedDshHomeProfileDigests)) {
    if (profileIdentities[name] !== expected) {
      failWith('BLOCK_PROFILE_IDENTITY', `materialized headless profile identity differs from the qualified contract: ${name}`)
    }
  }

  const stageARuntimeTreeDigests = Object.fromEntries(
    homeManifest.objects.filter(o => o.stageAContractPinned === true)
      .map(o => [o.packageName.replace('@deepseek-ai/', ''), o.packageTreeDigest]),
  )
  for (const [name, expected] of Object.entries(stageA.qualifiedRuntimePackageTreeDigests)) {
    if (stageARuntimeTreeDigests[name] !== expected) {
      failWith('BLOCK_RUNTIME_IDENTITY', `materialized runtime package tree differs from the qualified contract: ${name}`)
    }
  }

  const qntylabProductionPackages = Object.fromEntries(
    homeManifest.objects.filter(o => o.type === 'package-tree')
      .map(o => [o.packageName, {
        version: o.version,
        packageTreeDigest: o.packageTreeDigest,
        wholeTreeDigest: o.wholeTreeDigest,
        canonicalSourcePath: o.canonicalSourcePath,
      }]),
  )
  if (Object.keys(qntylabProductionPackages).some(name => name.includes('stub-provider'))) {
    failWith('BLOCK_PRODUCTION_STUB_PROVIDER', 'stub provider present in the production package set')
  }

  const productionPackageGraphIdentity = {
    packageCount: homeManifest.packageInventory.length,
    inventoryDigest: sha256Canonical(homeManifest.packageInventory),
    objectCount: homeManifest.objects.length,
    graphDerivation: 'DSH_HEAL_PROFILES_MODULE_FALLBACK_CLOSURE_PLUS_STAGE_A_CONTRACT_PINNED_WORKSPACE_PACKAGES',
    allTargetsContainedInPinnedRuntimeRoot: true,
    ambientAuthorityUsed: false,
  }

  const contractBody = {
    schemaVersion: SUCCESSOR_CONTRACT_SCHEMA_VERSION,
    projectId: PROJECT_ID,

    predecessorQualifiedContractDigest: PREDECESSOR_QUALIFIED_CONTRACT_DIGEST,
    predecessorStatus: 'PRESERVED_HISTORICALLY_SUPERSEDED_AS_THE_COMPLETE_FINAL_LIVE_CONTRACT',
    currentCompositeRoot,
    currentCompositeRootBasis: 'mechanically re-derived from current resolved canonical inputs; never compared to the historical a392 root',
    governingAuthorization: { ...GOVERNING_AUTHORIZATION },

    pinnedDshSourceIdentity: {
      repository: 'deepseek-ai/deepseek-harness',
      commit: '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca',
      tree: '3bc8f89fe494a4755c188be354add4e8b1e7b188',
      tag: 'dsh-v0.1.0-rc.7',
      lockfileDigest: homeManifest.provenance.pinnedRuntime.lockfileDigest,
      builtCliDigest: homeManifest.provenance.pinnedRuntime.builtCliDigest,
    },
    runtimeManifestDigest: composite.runtimeManifestDigest,
    runtimeManifestArtifactDigest: homeManifest.provenance.pinnedRuntime.runtimeManifestArtifactDigest,
    executableIdentityDigest: composite.executableIdentityDigest,
    compositeLaunchPolicyDigest: composite.compositeLaunchPolicyDigest,

    productionDshHomeMaterializer: {
      path: MATERIALIZER_RELATIVE_PATH,
      digest: materializerDigest,
      isTheOnlyProductionDshHomeAuthority: true,
      qualificationOnlyHelperIsProductionAuthority: false,
      qualificationOnlyHelperPath: 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/qualification/run-composite-qualification.mjs',
    },
    dshHomeManifestSchema: {
      ...DSH_HOME_MANIFEST_SCHEMA,
      schemaDigest: DSH_HOME_MANIFEST_SCHEMA_DIGEST,
    },
    productionDshHomeIdentity: {
      homeManifestDigest: sha256Canonical(homeManifest),
      headlessProfileIdentities: profileIdentities,
      packageGraph: productionPackageGraphIdentity,
      requiredDeepseekPackageTreeDigests: stageARuntimeTreeDigests,
      qntylabProductionPackages,
      productionStubProviderExcluded: true,
      excludedQualificationOnlyPackages: ['@qntylab/dsh-stage-a-stub-provider'],
      stubPresenceBehavior: 'FAIL_CLOSED',
    },

    compositeLauncher: { path: COMPOSITE_LAUNCHER_RELATIVE_PATH, digest: compositeLauncherDigest, modified: false },
    stageAPolicy: {
      canonicalPolicy: stageA.canonicalPolicy,
      productionFileDigests: stageA.productionFileDigests,
      offlineProviderOverlay: stageA.offlineProviderOverlay,
      orderingPolicy: stageA.orderingPolicy,
    },
    parentPolicy: stageA.parentPolicy,
    childController: stageA.childPolicy,
    codexBoundary: stageA.childPolicy,
    claudeBoundary: stageA.claudePolicy,
    workspaceContainment: stageA.workspacePolicy,
    claimSecretOrdering: {
      claimPolicy: stageA.claimPolicy,
      secretPolicy: stageA.secretPolicy,
      ordering: policy.secretClaimOrdering,
    },
    fixtureIdentity: fixture,

    LIVE_AUTHORITY: false,
    liveAuthorityBasis: 'This successor contract qualifies a production DSH_HOME materialization path only. It creates no live authority, no episode, and no claim.',
    separateV0R5AuthorizationRequired: true,
    v0r5Created: false,
  }

  const NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST = sha256Canonical(contractBody)
  return {
    contract: contractBody,
    NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
    currentCompositeRoot,
    NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST: materializerDigest,
    NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST: DSH_HOME_MANIFEST_SCHEMA_DIGEST,
    predecessorComposite: composite,
  }
}

/**
 * Verify a frozen successor-contract artifact.
 *
 * Historical-vs-current aware:
 * - kind === 'HISTORICAL' verifies the preserved immutable artifact against its
 *   OWN historical record (digest 50bd7762..., predecessor a392f82e...). It is
 *   never recomputed against current bytes, because that recomputation would
 *   compare current identity to a historical digest — the exact conflation this
 *   reconciliation removes.
 * - kind === 'CURRENT' verifies a current-generation artifact (new path)
 *   against the mechanically re-derived current root.
 */
export function verifySuccessorContractArtifact(artifactPath, { homeManifest, profileHome, runtimeManifestPath = DEFAULT_RUNTIME_MANIFEST, qntyLabRoot = ROOT, kind = 'CURRENT' } = {}) {
  if (!existsSync(artifactPath)) failWith('BLOCK_SUCCESSOR_CONTRACT', `successor contract artifact missing: ${artifactPath}`)
  const artifact = JSON.parse(readFileSync(artifactPath, 'utf8'))

  if (kind === 'HISTORICAL') {
    // The historical artifact is verified against its own immutable record,
    // never against current bytes.
    if (artifact.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST !== HISTORICAL_SUCCESSOR_CONTRACT_DIGEST) {
      failWith('BLOCK_SUCCESSOR_CONTRACT', 'historical successor contract digest is not the frozen 50bd7762 record')
    }
    if (artifact.contract?.predecessorQualifiedContractDigest !== HISTORICAL_COMPOSITE_CONTRACT_DIGEST) {
      failWith('BLOCK_SUCCESSOR_CONTRACT', 'historical successor contract does not bind the historical a392 composite root')
    }
    if (artifact.contract?.LIVE_AUTHORITY !== false) {
      failWith('BLOCK_SUCCESSOR_CONTRACT', 'successor contract must not grant live authority')
    }
    return { contract: artifact.contract, NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST: artifact.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST }
  }

  const computed = computeSuccessorContract({ homeManifest, profileHome, runtimeManifestPath, qntyLabRoot })
  if (canonicalJson(artifact.contract) !== canonicalJson(computed.contract)) {
    failWith('BLOCK_SUCCESSOR_CONTRACT', 'current successor contract artifact does not match current component bytes')
  }
  if (artifact.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST !== computed.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST) {
    failWith('BLOCK_SUCCESSOR_CONTRACT', 'successor contract digest is inconsistent')
  }
  if (artifact.contract.LIVE_AUTHORITY !== false) {
    failWith('BLOCK_SUCCESSOR_CONTRACT', 'successor contract must not grant live authority')
  }
  return computed
}
