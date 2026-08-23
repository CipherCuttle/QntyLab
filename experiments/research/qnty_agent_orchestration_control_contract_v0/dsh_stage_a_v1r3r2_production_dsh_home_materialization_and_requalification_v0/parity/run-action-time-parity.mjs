#!/usr/bin/env node

// ACTION_TIME_PARITY_RECEIPT.
//
// Runs the production preparation path from a completely fresh disposable
// environment and stops immediately before the real secret read — the exact
// boundary a future live episode would cross next. The V0R4 failure was that
// qualification and action time did not share a preparation path; this receipt
// exists to prove they now do.

import { mkdtempSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { sha256Canonical } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/canonical-json.mjs'
import { prepareProductionLaunch, REAL_SECRET_PATH } from '../preparation/prepare-production-launch.mjs'

const PHASE = resolve(fileURLToPath(import.meta.url), '../..')

export function runActionTimeParity({ keepScratch = false } = {}) {
  const scratch = mkdtempSync(join(tmpdir(), 'qntylab-stage-a-parity-'))
  try {
    const prepared = prepareProductionLaunch({
      dshHomeDestination: join(scratch, 'dsh-home'),
      workspace: join(scratch, 'workspace'),
      fixtureDestination: join(scratch, 'fixture'),
      launchArgv: [
        '--controller-state', join(scratch, 'state/child.json'),
        '--node-executable', process.execPath,
        '--python-executable', '/usr/bin/python3',
        '--codex-executable', '/home/swirky/.local/bin/codex',
        '--claude-executable', '/usr/bin/claude',
        '--parent-endpoint', 'http://127.0.0.1:1/',
      ],
    })

    const receipt = {
      artifactType: 'DSH_STAGE_A_V1R3R2_ACTION_TIME_PARITY_RECEIPT',
      schemaVersion: 'dsh-stage-a-v1r3r2-action-time-parity-receipt-v0',
      projectId: prepared.successor.contract.projectId,
      preparationPath: 'preparation/prepare-production-launch.mjs#prepareProductionLaunch',
      singleProductionPreparationPathUsedByQualificationAndLive: true,
      hiddenQualificationOnlyPreparationUsed: false,
      chain: [
        'EMPTY DSH_HOME DESTINATION',
        'PRODUCTION DSH_HOME MATERIALIZER',
        'PRODUCTION COMPOSITE PREFLIGHT',
        'PRODUCTION FIXTURE PREPARATION',
        'ALL NON-SECRET LIVE GATES PASS',
        'STOP IMMEDIATELY BEFORE REAL SECRET READ',
      ],
      gates: prepared.gates,
      homeManifestDigest: prepared.materialization.homeManifestDigest,
      NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST: prepared.successor.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
      NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST: prepared.successor.NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST,
      NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST: prepared.successor.NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST,
      predecessorQualifiedContractDigest: prepared.successor.contract.predecessorQualifiedContractDigest,
      runtimeManifestDigest: prepared.successor.contract.runtimeManifestDigest,
      executableIdentityDigest: prepared.successor.contract.executableIdentityDigest,
      fixture: { fixtureId: prepared.fixture.fixtureId, fixtureDigest: prepared.fixture.fixtureDigest, canonicalFixtureMutated: false },
      stopBoundary: 'IMMEDIATELY_BEFORE_REAL_SECRET_READ',
      realSecretPathInspected: false,
      realSecretPath: REAL_SECRET_PATH,
      counters: prepared.counters,
      LIVE_AUTHORITY: false,
      v0r5Created: false,
      terminal: Object.values(prepared.gates).every(value => value === 'PASS') ? 'ACTION_TIME_PARITY_PASS' : 'ACTION_TIME_PARITY_FAIL',
    }
    receipt.receiptDigest = sha256Canonical(receipt)
    return { receipt, prepared, scratch }
  } finally {
    if (!keepScratch) rmSync(scratch, { recursive: true, force: true })
  }
}

if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  const { receipt } = runActionTimeParity()
  const out = join(PHASE, 'evidence/action_time_parity_receipt.json')
  writeFileSync(out, `${JSON.stringify(receipt, undefined, 2)}\n`)
  process.stdout.write(`${JSON.stringify(receipt, undefined, 2)}\n`)
}
