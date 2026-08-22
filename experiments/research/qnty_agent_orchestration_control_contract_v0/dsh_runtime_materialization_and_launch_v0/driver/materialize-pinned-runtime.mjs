#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'

import {
  PHASE_ID,
  SOURCE_COMMIT,
  SOURCE_TREE,
  SOURCE_TAG,
  materializePinnedSource,
  applyCanonicalPatches,
  installPinnedOffline,
  buildPinnedRuntime,
  buildPhaseManifest,
  writeManifest,
  writeReceipt,
} from '../materializer/qntylab-materialize-dsh-runtime.mjs'

const PHASE_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const REPO_ROOT = resolve(PHASE_DIR, '../../../..')
const PREVIOUS_CODEX_PATCH = join(REPO_ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_real_runtime_qualification_v0/repairs/codex-executable-binding.patch')
const PREVIOUS_CLAUDE_PATCH = join(REPO_ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/repairs/claude-hard-read-only.patch')
const QUALIFICATION_OVERLAY = join(REPO_ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/driver/qualification.patch.yml')
const LAUNCHER = join(PHASE_DIR, 'launcher/qntylab-launch-dsh.mjs')
const RUNTIME_ROOT = process.env.QNTYLAB_DSH_RUNTIME_ROOT || '/var/tmp/qntylab-dsh-runtime-v0'
const MANIFEST_PATH = process.env.QNTYLAB_DSH_MANIFEST || join(PHASE_DIR, 'evidence/runtime_manifest.json')
const RECEIPT_PATH = process.env.QNTYLAB_DSH_RECEIPT || join(PHASE_DIR, 'evidence/materialization_receipt.json')

function sha256File(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

const sourceReceipt = materializePinnedSource({ runtimeRoot: RUNTIME_ROOT })
if (sourceReceipt.sourceCommit !== SOURCE_COMMIT || sourceReceipt.sourceTree !== SOURCE_TREE || sourceReceipt.sourceTag !== SOURCE_TAG) {
  throw new Error('BLOCK_SOURCE: pinned source identity was not reproduced')
}
writeReceipt(RECEIPT_PATH, { phaseId: PHASE_ID, ...sourceReceipt, receiptPath: resolve(RECEIPT_PATH) })

const patchDigests = applyCanonicalPatches(sourceReceipt.sourceRoot, [PREVIOUS_CODEX_PATCH, PREVIOUS_CLAUDE_PATCH])
const packageManagerFingerprint = installPinnedOffline(sourceReceipt.sourceRoot, {
  corepackExecutable: process.env.QNTYLAB_COREPACK || 'corepack',
})
const build = buildPinnedRuntime(sourceReceipt.sourceRoot, {
  corepackExecutable: process.env.QNTYLAB_COREPACK || 'corepack',
  buildScript: 'build:lib',
})
const manifest = buildPhaseManifest({
  sourceRoot: sourceReceipt.sourceRoot,
  sourceReceipt,
  patchDigests,
  packageManagerFingerprint,
  buildIdentity: { ...build, commandDigest: sha256File(resolve(PHASE_DIR, 'driver/materialize-pinned-runtime.mjs')) },
  lockfileDigest: sha256File(join(sourceReceipt.sourceRoot, 'pnpm-lock.yaml')),
  launcherPath: LAUNCHER,
  overlayPath: QUALIFICATION_OVERLAY,
  executablePaths: {
    nodeExecutable: process.execPath,
    pythonExecutable: process.env.QNTYLAB_PYTHON || '/usr/bin/python3',
    codexExecutable: process.env.QNTYLAB_CODEX_EXECUTABLE || '/home/swirky/.local/bin/codex',
    claudeExecutable: process.env.QNTYLAB_CLAUDE_EXECUTABLE || '/usr/bin/claude',
  },
  manifestPath: MANIFEST_PATH,
})
const manifestTextDigest = writeManifest(MANIFEST_PATH, manifest)
writeReceipt(RECEIPT_PATH, {
  phaseId: PHASE_ID,
  ...sourceReceipt,
  patchDigests,
  packageManagerFingerprint,
  build,
  lockfileDigest: manifest.lockfileDigest,
  manifestPath: resolve(MANIFEST_PATH),
  manifestTextDigest,
})
console.log(JSON.stringify({ phaseId: PHASE_ID, sourceReceipt, patchDigests, packageManagerFingerprint, build, manifestPath: MANIFEST_PATH, manifestTextDigest }, null, 2))
