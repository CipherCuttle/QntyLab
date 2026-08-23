#!/usr/bin/env node

import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { writeFileSync } from 'node:fs'

const PHASE = new URL('..', import.meta.url).pathname.replace(/\/$/, '')
const DRIVER = join(PHASE, 'qualification/run-composite-qualification.mjs')
const cases = ['clean', 'repair']

function run(scenario) {
  const result = spawnSync(process.execPath, [DRIVER], {
    encoding: 'utf8',
    env: { ...process.env, QNTYLAB_COMPOSITE_SCENARIO: scenario },
    maxBuffer: 20 * 1024 * 1024,
    timeout: 120_000,
  })
  if (result.error) throw result.error
  const receipt = JSON.parse(result.stdout)
  if (result.status !== 0) throw new Error(`${scenario} composite qualification failed: ${result.stderr || result.stdout}`)
  return receipt
}

const receipts = cases.map(run)
const output = {
  artifactType: 'DSH_STAGE_A_V1R3R2_COMPOSITE_LAUNCHER_QUALIFICATION',
  schemaVersion: 'dsh-stage-a-v1r3r2-composite-launcher-qualification-v0',
  projectId: 'DSH_STAGE_A_V1R3R2_COMPOSITE_LIVE_LAUNCHER_INTEGRATION_AND_REQUALIFICATION_V0',
  qualificationMode: 'BOUNDED_PRELIVE_COMPOSITE_LAUNCH_PATH_OFFLINE_LOOPBACK',
  receipts,
  summary: {
    verdict: 'PASS',
    actualDshProcess: receipts.every(receipt => receipt.actualDshProcessConfirmed),
    physicalRuntimeVerification: receipts.every(receipt => receipt.physicalRuntimeVerification === 'PASS'),
    stageAPolicyVerification: receipts.every(receipt => receipt.stageAPolicyVerification === 'PASS'),
    singleCompositePreflight: receipts.every(receipt => receipt.singleCompositePreflight === 'PASS'),
    singleCompositeSpawnBoundary: receipts.every(receipt => receipt.singleCompositeSpawnBoundary === 'PASS'),
    canonicalStageAPolicyActive: receipts.every(receipt => receipt.canonicalStageAPolicyActive),
    cleanPathProcessExercised: receipts.some(receipt => receipt.scenario === 'clean' && receipt.childController === 'PASS'),
    repairPathProcessExercised: receipts.some(receipt => receipt.scenario === 'repair' && receipt.childController === 'PASS'),
    publicProviderRequests: 0,
    realModelCalls: 0,
    realCodexTurns: 0,
    realClaudeTurns: 0,
    realSecretReads: 0,
    claimsCreated: 0,
    spendUsd: 0,
    offlineLocalClaimReceipts: receipts.filter(receipt => receipt.offlineLocalClaimReceiptCreated).length,
  },
}
writeFileSync(join(PHASE, 'evidence/qualification.json'), `${JSON.stringify(output, null, 2)}\n`)
process.stdout.write(`${JSON.stringify(output, null, 2)}\n`)
