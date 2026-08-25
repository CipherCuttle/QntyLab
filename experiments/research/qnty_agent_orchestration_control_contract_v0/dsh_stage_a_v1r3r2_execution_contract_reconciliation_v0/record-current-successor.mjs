#!/usr/bin/env node

// Records the CURRENT-generation successor contract at a NEW path, leaving the
// historical successor_contract.json (sha256 9bb1f217…) byte-identical.
//
// The current successor derives mechanically from CURRENT resolved canonical
// inputs (current composite root), never from a historical digest. Deriving it
// twice must produce identical bytes; the receipt proves that.

import { createHash } from 'node:crypto'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { SUCCESSOR_CONTRACT_ARTIFACT as CURRENT_SUCCESSOR_ARTIFACT } from '../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/preparation/prepare-production-launch.mjs'
import { materializeStageADshHome } from '../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/materializer/qntylab-materialize-stage-a-dsh-home.mjs'
import { computeSuccessorContract } from '../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/contract/successor-contract.mjs'

// The current-generation artifact must live at EXACTLY the path the production
// preparation path references (a NEW path — the historical successor_contract.json
// is never overwritten).
const OUT = CURRENT_SUCCESSOR_ARTIFACT
// The determinism receipt must live beside the current-generation successor
// artifact, inside the CANONICAL production evidence dir (never in this phase's
// own local evidence/ subdir, which was the accidental-typo placement).
const PHASE_OUT = new URL('../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/evidence/', import.meta.url)

function derive() {
  const scratch = mkdtempSync(join(tmpdir(), 'qntylab-recon-record-'))
  try {
    const result = materializeStageADshHome({ destination: join(scratch, 'dsh-home') })
    const successor = computeSuccessorContract({
      homeManifest: result.identityBody,
      profileHome: result.destination,
    })
    return {
      artifactType: 'DSH_STAGE_A_V1R3R2_CURRENT_GENERATION_SUCCESSOR_CONTRACT_RECONCILIATION_V0',
      schemaVersion: 'dsh-stage-a-v1r3r2-reconciliation-v0-successor-v0',
      NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST: successor.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
      CURRENT_COMPOSITE_ROOT: successor.currentCompositeRoot,
      NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST: successor.NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST,
      NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST: successor.NEW_DSH_HOME_MANIFEST_SCHEMA_DIGEST,
      historicalSuccessorContractDigestPreserved: '9bb1f217b9de60b92841ababf6075ccf46c1080f1416f5e5e29fd496a08b143e',
      contract: successor.contract,
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true })
  }
}

const first = derive()
const second = derive()
const receipt = {
  ...first,
  determinism: {
    derivedTwice: true,
    identical: JSON.stringify(first) === JSON.stringify(second),
    compositeRootIdentical: first.CURRENT_COMPOSITE_ROOT === second.CURRENT_COMPOSITE_ROOT,
    successorDigestIdentical: first.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST === second.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
  },
  sha256: createHash('sha256').update(JSON.stringify(first, null, 2)).digest('hex'),
}
if (receipt.determinism.identical !== true) throw new Error('BLOCK_NONDETERMINISM: current successor derivation is not reproducible')
mkdirSync(PHASE_OUT, { recursive: true })
writeFileSync(new URL('./determinism_reconciliation_v0.json', PHASE_OUT), `${JSON.stringify({
  artifactType: 'DSH_STAGE_A_V1R3R2_CURRENT_SUCCESSOR_DETERMINISM_RECEIPT',
  derivedTwice: true,
  identical: receipt.determinism.identical,
  CURRENT_COMPOSITE_ROOT: first.CURRENT_COMPOSITE_ROOT,
  NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST: first.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
}, null, 2)}\n`)
mkdirSync(dirname(OUT), { recursive: true })
writeFileSync(OUT, `${JSON.stringify(receipt, null, 2)}\n`)
process.stdout.write(`CURRENT_COMPOSITE_ROOT=${first.CURRENT_COMPOSITE_ROOT}\n`)
process.stdout.write(`NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST=${first.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST}\n`)
process.stdout.write(`sha256=${receipt.sha256}\n`)