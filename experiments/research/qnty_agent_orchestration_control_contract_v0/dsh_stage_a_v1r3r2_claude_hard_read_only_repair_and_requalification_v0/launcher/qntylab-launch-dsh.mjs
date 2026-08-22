// V1R3R2 reuses the predecessor's verified launch-plane implementation.
// The wrapper is phase-local so the new launch contract binds this exact
// reuse edge as well as the underlying launcher bytes.
export {
  LaunchPlaneError,
  parseLauncherArgv,
  preflightLaunch,
  spawnDsh,
  writeLaunchReceipt,
} from '../../dsh_stage_a_v1r3r1_real_runtime_qualification_v0/launcher/qntylab-launch-dsh.mjs'
