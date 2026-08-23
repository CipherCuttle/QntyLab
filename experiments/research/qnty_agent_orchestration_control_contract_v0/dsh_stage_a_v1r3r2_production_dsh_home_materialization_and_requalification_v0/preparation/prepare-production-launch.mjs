#!/usr/bin/env node

// The single production preparation path.
//
// Action-time parity is the primary acceptance gate of this phase: the sequence
// that a future live episode would execute and the sequence qualification
// executes must be the SAME code, not two implementations that agree by
// inspection. Every caller — offline qualification, the parity receipt, and any
// future V0R5 live episode — enters here.
//
// The path deliberately stops immediately before the real secret read. Reading
// the operator secret is the caller's step, past this boundary, and is not
// authorized in this phase.

import { createHash } from 'node:crypto'
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { preflightLaunch, parseLauncherArgv } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/launcher/qntylab-launch-dsh.mjs'
import {
  DEFAULT_RUNTIME_MANIFEST,
  MaterializationError,
  ROOT,
  materializeStageADshHome,
  verifyHomeManifest,
} from '../materializer/qntylab-materialize-stage-a-dsh-home.mjs'
import { FIXTURE, computeFixtureIdentity, computeSuccessorContract } from '../contract/successor-contract.mjs'

const PHASE = resolve(fileURLToPath(import.meta.url), '../..')
export const SUCCESSOR_CONTRACT_ARTIFACT = join(PHASE, 'evidence/successor_contract.json')

/** The real Stage-A secret. This module never reads it; the path stops before it. */
export const REAL_SECRET_PATH = `${process.env.HOME ?? '/home/swirky'}/.secrets/openai_api_key_stage_a`

const failWith = (code, message) => { throw new MaterializationError(code, message) }
const digestFile = path => createHash('sha256').update(readFileSync(path)).digest('hex')

/**
 * Prepare a fresh disposable Stage-A fixture copy. The canonical Git-tracked
 * fixture is never mutated; only the disposable copy is writable.
 */
export function prepareProductionFixture(destination, { qntyLabRoot = ROOT } = {}) {
  if (existsSync(destination) && readdirSync(destination).length > 0) {
    failWith('BLOCK_FIXTURE_IDENTITY', `fixture destination is not empty: ${destination}`)
  }
  const canonicalRoot = join(qntyLabRoot, FIXTURE.fixtureRoot)
  const before = computeFixtureIdentity(qntyLabRoot)
  mkdirSync(destination, { recursive: true })
  for (const file of FIXTURE.files) {
    const target = join(destination, file)
    mkdirSync(join(target, '..'), { recursive: true })
    cpSync(join(canonicalRoot, file), target)
  }
  const copyDigests = Object.fromEntries(FIXTURE.files.map(file => [`fixture/${file}`, digestFile(join(destination, file))]))
  const copyDigest = createHash('sha256').update(JSON.stringify(copyDigests, Object.keys(copyDigests).sort())).digest('hex')
  if (copyDigest !== before.fixtureDigest) failWith('BLOCK_FIXTURE_IDENTITY', 'disposable fixture copy does not match the canonical fixture identity')
  const after = computeFixtureIdentity(qntyLabRoot)
  if (after.fixtureDigest !== before.fixtureDigest) failWith('BLOCK_FIXTURE_IDENTITY', 'canonical fixture was mutated during preparation')
  return {
    fixtureId: FIXTURE.fixtureId,
    disposableCopy: destination,
    fixtureDigest: copyDigest,
    canonicalFixtureDigest: after.fixtureDigest,
    canonicalFixtureMutated: false,
    mutablePaths: [...FIXTURE.mutablePaths],
    immutablePaths: [...FIXTURE.immutablePaths],
  }
}

/**
 * The production preparation sequence. Returns a receipt covering every
 * non-secret gate, plus the launcher arguments and preflight result a caller
 * would hand to `spawnDsh`.
 *
 * @param dshHomeDestination  fresh, empty, disposable DSH_HOME destination.
 * @param workspace           disposable workspace (outside QntyLab and the runtime root).
 * @param fixtureDestination  fresh destination for the disposable fixture copy.
 * @param launchArgv          the remaining composite launcher argv.
 */
export function prepareProductionLaunch({
  dshHomeDestination,
  workspace,
  fixtureDestination,
  launchArgv,
  runtimeManifestPath = DEFAULT_RUNTIME_MANIFEST,
  qntyLabRoot = ROOT,
} = {}) {
  const gates = {}

  // 1. EMPTY DSH_HOME DESTINATION -> PRODUCTION DSH_HOME MATERIALIZER
  const materialization = materializeStageADshHome({
    destination: dshHomeDestination,
    runtimeManifestPath,
    qntyLabRoot,
  })
  gates.MATERIALIZER = 'PASS'

  // 2. DSH_HOME identity, recomputed from disk
  const verified = verifyHomeManifest(materialization.destination)
  if (verified.homeManifestDigest !== materialization.homeManifestDigest) {
    failWith('BLOCK_HOME_MANIFEST', 'materialized home digest is unstable')
  }
  gates.DSH_HOME_IDENTITY = 'PASS'

  // 3. SUCCESSOR CONTRACT, computed against the freshly materialized home
  const successor = computeSuccessorContract({
    homeManifest: materialization.identityBody,
    profileHome: materialization.destination,
    runtimeManifestPath,
    qntyLabRoot,
  })
  if (successor.contract.LIVE_AUTHORITY !== false) failWith('BLOCK_SUCCESSOR_CONTRACT', 'successor contract must not grant live authority')
  // The frozen artifact is mandatory, not opportunistic: it is the binding that
  // detects a substituted materializer or home identity, so its absence must
  // fail closed rather than silently disable the check.
  if (!existsSync(SUCCESSOR_CONTRACT_ARTIFACT)) {
    failWith('BLOCK_SUCCESSOR_CONTRACT', `frozen successor contract artifact is missing: ${SUCCESSOR_CONTRACT_ARTIFACT}`)
  }
  const frozen = JSON.parse(readFileSync(SUCCESSOR_CONTRACT_ARTIFACT, 'utf8'))
  if (frozen.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST !== successor.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST) {
    failWith('BLOCK_SUCCESSOR_CONTRACT', 'frozen successor contract artifact does not match recomputed component bytes')
  }
  gates.SUCCESSOR_CONTRACT = 'PASS'
  gates.RUNTIME_IDENTITY = successor.predecessorComposite.runtimeManifestDigest === '0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3' ? 'PASS' : 'FAIL'
  gates.EXECUTABLE_IDENTITY = successor.predecessorComposite.executableIdentityDigest === 'ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9' ? 'PASS' : 'FAIL'
  if (gates.RUNTIME_IDENTITY !== 'PASS') failWith('BLOCK_RUNTIME_IDENTITY', 'pinned runtime identity is not the frozen identity')
  if (gates.EXECUTABLE_IDENTITY !== 'PASS') failWith('BLOCK_EXECUTABLE_IDENTITY', 'executable identity is not the frozen identity')

  // 4. DISPOSABLE WORKSPACE. Created here, inside the single production
  //    preparation path, so no caller — qualification or live — has to create a
  //    prerequisite of its own outside the shared path.
  if (existsSync(workspace)) {
    if (!statSync(workspace).isDirectory()) failWith('BLOCK_WORKSPACE', `workspace exists and is not a directory: ${workspace}`)
    if (readdirSync(workspace).length > 0) failWith('BLOCK_WORKSPACE', `workspace is not a fresh disposable directory: ${workspace}`)
  }
  mkdirSync(workspace, { recursive: true })

  // 5. PRODUCTION COMPOSITE PREFLIGHT — the exact qualified launcher boundary
  const args = parseLauncherArgv([
    '--qualified-launch-contract-digest', successor.predecessorComposite.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
    '--runtime-manifest', runtimeManifestPath,
    '--workspace', workspace,
    '--dsh-home', materialization.destination,
    '--profile', 'headless',
    ...launchArgv,
  ])
  const preflight = preflightLaunch(args, { forbiddenRoots: [qntyLabRoot] })
  gates.COMPOSITE_PREFLIGHT = 'PASS'

  // 6. WORKSPACE CONTAINMENT
  const workspaceReal = preflight.workspaceReal
  const runtimeRoot = materialization.runtimeRoot
  const inside = (root, candidate) => candidate === root || candidate.startsWith(`${root}/`)
  if (inside(realpathSync(qntyLabRoot), workspaceReal)) failWith('BLOCK_WORKSPACE', 'workspace is inside QntyLab')
  if (inside(runtimeRoot, workspaceReal)) failWith('BLOCK_WORKSPACE', 'workspace is inside the pinned runtime root')
  gates.WORKSPACE_CONTAINMENT = 'PASS'

  // 7. PRODUCTION FIXTURE PREPARATION
  const fixture = prepareProductionFixture(fixtureDestination, { qntyLabRoot })
  gates.FIXTURE_IDENTITY = 'PASS'

  // 8. STOP. The next operation a live episode would perform is the real secret
  //    read. That boundary is not crossed here.
  gates.ALL_NON_SECRET_GATES = Object.values(gates).every(value => value === 'PASS') ? 'PASS' : 'FAIL'

  return {
    gates,
    args,
    preflight,
    materialization,
    successor,
    fixture,
    workspaceReal,
    stoppedBefore: 'REAL_SECRET_READ',
    realSecretPathNotRead: REAL_SECRET_PATH,
    counters: {
      REAL_SECRET_READS: 0,
      CLAIMS_CREATED: 0,
      PUBLIC_PROVIDER_REQUESTS: 0,
      REAL_MODEL_CALLS: 0,
      REAL_CODEX_TURNS: 0,
      REAL_CLAUDE_TURNS: 0,
      SPEND_USD: 0,
    },
  }
}
