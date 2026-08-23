#!/usr/bin/env node

// Regenerates every evidence artifact for this phase from live bytes.

import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { sha256Canonical } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/canonical-json.mjs'
import { materializeStageADshHome, ROOT } from '../materializer/qntylab-materialize-stage-a-dsh-home.mjs'
import { computeSuccessorContract } from '../contract/successor-contract.mjs'
import { runActionTimeParity } from '../parity/run-action-time-parity.mjs'
import { runProductionQualification } from '../qualification/run-production-qualification.mjs'

const PHASE = resolve(fileURLToPath(import.meta.url), '../..')
const EVIDENCE = join(PHASE, 'evidence')
const write = (name, value) => writeFileSync(join(EVIDENCE, name), `${JSON.stringify(value, undefined, 2)}\n`)

// ---- two independent materializations ---------------------------------------
const homes = []
for (const label of ['A', 'B']) {
  const scratch = mkdtempSync(join(tmpdir(), `qntylab-evidence-${label}-`))
  const result = materializeStageADshHome({ destination: join(scratch, 'dsh-home') })
  homes.push({ label, scratch, result })
}
const [homeA, homeB] = homes

const determinism = {
  artifactType: 'DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_DETERMINISM_RECEIPT',
  schemaVersion: 'dsh-stage-a-v1r3r2-production-dsh-home-determinism-receipt-v0',
  HOME_A_DIGEST: homeA.result.homeManifestDigest,
  HOME_B_DIGEST: homeB.result.homeManifestDigest,
  identical: homeA.result.homeManifestDigest === homeB.result.homeManifestDigest,
  profileFileDigestsEqual: sha256Canonical(homeA.result.manifest.objects.filter(o => o.type === 'file'))
    === sha256Canonical(homeB.result.manifest.objects.filter(o => o.type === 'file')),
  packageInventoryEqual: sha256Canonical(homeA.result.manifest.packageInventory) === sha256Canonical(homeB.result.manifest.packageInventory),
  symlinkIdentitiesEqual: sha256Canonical(homeA.result.manifest.objects.filter(o => o.type === 'symlink'))
    === sha256Canonical(homeB.result.manifest.objects.filter(o => o.type === 'symlink')),
  qntylabPackageDigestsEqual: sha256Canonical(homeA.result.manifest.objects.filter(o => o.type === 'package-tree'))
    === sha256Canonical(homeB.result.manifest.objects.filter(o => o.type === 'package-tree')),
  packageCount: homeA.result.manifest.packageInventory.length,
  objectCount: homeA.result.manifest.objects.length,
  terminal: homeA.result.homeManifestDigest === homeB.result.homeManifestDigest
    ? 'DETERMINISTIC' : 'BLOCK_MATERIALIZATION_NONDETERMINISM',
}
write('determinism.json', determinism)
if (determinism.terminal !== 'DETERMINISTIC') throw new Error('BLOCK_MATERIALIZATION_NONDETERMINISM')

// The canonical DSH_HOME manifest, with per-run residue removed.
write('dsh_home_manifest.json', homeA.result.identityBody)

// ---- successor contract ------------------------------------------------------
const successor = computeSuccessorContract({
  homeManifest: homeA.result.identityBody,
  profileHome: homeA.result.destination,
})
write('successor_contract.json', {
  artifactType: 'DSH_STAGE_A_V1R3R2_PRODUCTION_QUALIFIED_LAUNCH_CONTRACT',
  NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST: successor.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
  NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST: successor.NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST,
  NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST: successor.NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST,
  contract: successor.contract,
})
for (const home of homes) rmSync(home.scratch, { recursive: true, force: true })

// ---- action-time parity ------------------------------------------------------
const { receipt: parity } = runActionTimeParity()
write('action_time_parity_receipt.json', parity)
if (parity.terminal !== 'ACTION_TIME_PARITY_PASS') throw new Error('ACTION_TIME_PARITY_FAIL')

// ---- offline actual-DSH qualification ----------------------------------------
const qualification = {}
for (const scenario of ['clean', 'repair']) qualification[scenario] = await runProductionQualification(scenario)
write('offline_actual_dsh_qualification.json', qualification)
if (Object.values(qualification).some(r => r.terminal !== 'PRODUCTION_OFFLINE_QUALIFICATION_PASS')) {
  throw new Error('PRODUCTION_OFFLINE_QUALIFICATION_FAIL')
}

// ---- negative controls -------------------------------------------------------
const testRun = spawnSync(process.execPath, ['--test', '--test-reporter=tap', join(PHASE, 'test/production-dsh-home.test.mjs')], { encoding: 'utf8' })
const controls = [...testRun.stdout.matchAll(/^(ok|not ok) \d+ - (.+)$/gm)]
  .map(([, status, name]) => ({ name, status: status === 'ok' ? 'PASS' : 'FAIL' }))
  .filter(entry => entry.name.startsWith('NC-'))
  .sort((a, b) => a.name.localeCompare(b.name))
// The twenty required controls are NC-01..NC-20. Controls added after the
// hostile review to close its findings are recorded separately so the required
// set stays exactly the twenty the authorization enumerates.
const requiredNames = Array.from({ length: 20 }, (_, index) => `NC-${String(index + 1).padStart(2, '0')} `)
const required = controls.filter(entry => requiredNames.some(prefix => entry.name.startsWith(prefix)))
const supplementary = controls.filter(entry => !requiredNames.some(prefix => entry.name.startsWith(prefix)))
const negativeControls = {
  artifactType: 'DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_NEGATIVE_CONTROLS',
  schemaVersion: 'dsh-stage-a-v1r3r2-production-dsh-home-negative-controls-v0',
  requiredControls: 20,
  executedControls: required.length,
  passingControls: required.filter(entry => entry.status === 'PASS').length,
  controls: required,
  supplementaryControls: supplementary,
  supplementaryControlBasis: 'Added to close hostile review findings F1 (root-widening forgery) and F2 (unrecorded additions).',
  allRealExecutedTests: true,
  terminal: required.length === 20 && controls.every(entry => entry.status === 'PASS') ? '20_OF_20_PASS' : 'NEGATIVE_CONTROL_FAILURE',
}
write('negative_controls.json', negativeControls)
if (negativeControls.terminal !== '20_OF_20_PASS') throw new Error(`negative controls: ${negativeControls.terminal}`)

// ---- top-level digests -------------------------------------------------------
write('digests.json', {
  artifactType: 'DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_DIGESTS',
  PREDECESSOR_QUALIFIED_CONTRACT_DIGEST: successor.contract.predecessorQualifiedContractDigest,
  NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST: successor.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
  NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST: successor.NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST,
  NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST: successor.NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST,
  DSH_HOME_MANIFEST_DIGEST: determinism.HOME_A_DIGEST,
  RUNTIME_MANIFEST_DIGEST: successor.contract.runtimeManifestDigest,
  EXECUTABLE_IDENTITY_DIGEST: successor.contract.executableIdentityDigest,
  COMPOSITE_LAUNCHER_DIGEST: successor.contract.compositeLauncher.digest,
  FIXTURE_DIGEST: successor.contract.fixtureIdentity.fixtureDigest,
  GOVERNING_AUTHORIZATION_SHA256: successor.contract.governingAuthorization.artifactSha256,
  PHYSICAL_RUNTIME_BYTES_CHANGED: false,
  DSH_SOURCE_BYTES_CHANGED: false,
  RUNTIME_REBUILT: false,
  COMPOSITE_LAUNCHER_MODIFIED: false,
  LIVE_AUTHORITY: false,
  V0R5_CREATED: false,
})

process.stdout.write(`determinism=${determinism.terminal} parity=${parity.terminal} negativeControls=${negativeControls.terminal}\n`)
process.stdout.write(`NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST=${successor.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST}\n`)
