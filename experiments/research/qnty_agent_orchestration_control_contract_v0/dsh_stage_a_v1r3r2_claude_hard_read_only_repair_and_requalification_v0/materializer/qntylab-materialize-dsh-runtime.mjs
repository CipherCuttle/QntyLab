import * as predecessor from '../../dsh_stage_a_v1r3r1_real_runtime_qualification_v0/materializer/qntylab-materialize-dsh-runtime.mjs'

export const MaterializationError = predecessor.MaterializationError
export const installedPackageIdentity = predecessor.installedPackageIdentity
export const verifySourceIdentity = predecessor.verifySourceIdentity
export const applyCanonicalPatches = predecessor.applyCanonicalPatches
export const installOffline = predecessor.installOffline
export const buildRuntime = predecessor.buildRuntime
export const fingerprintExecutable = predecessor.fingerprintExecutable
export const writeManifest = predecessor.writeManifest

export function buildManifest(args) {
  return {
    ...predecessor.buildManifest(args),
    phaseId: 'DSH_STAGE_A_V1R3R2_CLAUDE_HARD_READ_ONLY_REPAIR_AND_REQUALIFICATION_V0',
  }
}
