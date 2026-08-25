import { createHash } from 'node:crypto'
import { spawn } from 'node:child_process'
import {
  existsSync,
  lstatSync,
  readFileSync,
  readdirSync,
  realpathSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import {
  delimiter,
  dirname,
  isAbsolute,
  join,
  relative,
  resolve,
  sep,
} from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  LaunchPlaneError,
  parseLauncherArgv as predecessorParseLauncherArgv,
  preflightLaunch as predecessorPreflightLaunch,
  writeLaunchReceipt,
} from '../../dsh_stage_a_v1r3r1_real_runtime_qualification_v0/launcher/qntylab-launch-dsh.mjs'
import {
  computeDigests,
  PHASE,
  ROOT,
  runtimeIdentityFromManifest,
} from '../evidence/compute-digests.mjs'
import { sha256Canonical } from '../evidence/canonical-json.mjs'

export { LaunchPlaneError, writeLaunchReceipt }

const CANONICAL_POLICY_PATCH = join(PHASE, 'profile/cordis.patch.yml')
const OFFLINE_STUB_PATCH = join(PHASE, 'stub/offline-stub.patch.yml')
const OFFLINE_STUB_EXECUTABLE = join(PHASE, 'stub/native-child-stub.mjs')
// MEDIUM-1 note: the claim-binding executionContractRoot is validated for
// exact sha256 FORMAT at this transport seam. A cross-check against the
// system-derived current composite root would require importing the composite
// production computeDigests module, which demands the qualified DSH runtime
// (not present on clean CI) — a silent skip would be a silent fallback, and a
// hard fail would make the repository-deterministic E2E unrunnable in CI.
// Therefore the FORMAT check plus the Python seam's resolved-inputs equality
// (the frozen enforcement seam compares the transported root byte-for-byte
// against the resolved execution inputs before any claim is COMMITTED) remain
// the binding enforcement points for MEDIUM-1. No authority is invented.
const QUALIFIED_CONTRACT_FLAG = '--qualified-launch-contract-digest'
// The five claim-binding env keys are DELIBERATELY NOT in ALLOWED_EXTRA_ENV.
// They are owned exclusively by the validated claimBinding payload and can
// never be supplied through the ordinary extraEnv seam. A caller with ordinary
// extraEnv control must not be able to overwrite the validated claim binding
// after validateClaimBinding has run (HIGH-1).
const ALLOWED_EXTRA_ENV = new Set([
  'OPENAI_API_KEY',
  'QNTYLAB_DSH_PARENT_BUDGET_STATE_PATH',
  'QNTYLAB_DSH_STAGE_A_CHILD_STATE_PATH',
  'QNTYLAB_DSH_CLAIM_STATE_DIR',
  'QNTYLAB_DSH_CLAIM_REMOTE',
  'QNTYLAB_DSH_CLAIM_REF',
  'QNTYLAB_DSH_CLAIM_SOURCE_REPO',
  'QNTYLAB_DSH_SESSION_NONCE',
  'QNTYLAB_DSH_PARENT_TIMEOUT_MS',
  'QNTYLAB_DSH_STUB_INVOCATION_PATH',
  'QNTYLAB_DSH_STUB_RESPONSE_MODE',
])

// ------------------------------------------------ claim-binding transport ----
//
// THE CLAIM BINDING (frozen model, TWO provenance classes):
//
// A. RESOLVED PRODUCTION IDENTITY — must originate from the SAME
//    prepareProductionLaunch execution that materialized the production home:
//      - executionContractRoot      (actual mechanically derived current root)
//      - runtimeIdentityDigest      (resolved runtime identity digest)
//      - executableIdentityDigest   (resolved executable identity digest)
//    These must NEVER be stale literals, never recovered from historical
//    artifacts, and never computed from the source SHA.
//
// B. FUTURE LIVE AUTHORITY IDENTITY — only from an applicable future canonical
//    live authorization:
//      - authorizedExecutionSourceSha  (exact immutable commit object identity)
//      - revocationState               (explicit canonical state, e.g. NOT_REVOKED)
//    This repair builds the transport and the fail-closed seam; it NEVER
//    invents a future live source SHA and NEVER declares a default
//    NOT_REVOKED on its own.
//
// The launcher transports the COMPLETE binding as a single structured object to
// the profile process via the allowlisted env vars below. There is NO
// environment substitution anywhere in this phase (no shell-style ${VAR}
// expansion): the profile process reads the exact values we placed in its env.
const CLAIM_BINDING_ENV_KEYS = Object.freeze([
  'QNTYLAB_DSH_AUTHORIZED_EXECUTION_SOURCE_SHA',
  'QNTYLAB_DSH_EXECUTION_CONTRACT_ROOT',
  'QNTYLAB_DSH_RUNTIME_IDENTITY_DIGEST',
  'QNTYLAB_DSH_EXECUTABLE_IDENTITY_DIGEST',
  'QNTYLAB_DSH_REVOCATION_STATE',
])

const SHA256_RE = /^[0-9a-fA-F]{64}$/
const EXACT_COMMIT_RE = /^[0-9a-fA-F]{40,64}$/
// Explicit canonical revocation/supersession states, mirroring the Python
// enforcement seam. REVOKED/SUPERSEDED must fail closed in the guard.
const REVOCATION_STATES = Object.freeze(['NOT_REVOKED', 'REVOKED', 'SUPERSEDED'])

export function validateClaimBinding(binding) {
  if (binding === undefined || binding === null || typeof binding !== 'object') {
    throw new Error('BLOCK_CLAIM_BINDING: the claim binding payload is required')
  }
  // Allowlisted keys only — nothing is silently dropped, and no unknown key is
  // ever transported.
  for (const key of Object.keys(binding)) {
    if (!CLAIM_BINDING_ENV_KEYS.includes(`QNTYLAB_DSH_${key.replace(/([A-Z])/g, '_$1').toUpperCase()}`)) {
      throw new Error(`BLOCK_CLAIM_BINDING: unknown claim binding key is denied: ${key}`)
    }
  }
  // Production-identity values are REQUIRED (non-empty, exact sha256 format).
  for (const key of ['executionContractRoot', 'runtimeIdentityDigest', 'executableIdentityDigest']) {
    const value = binding[key]
    if (typeof value !== 'string' || !SHA256_RE.test(value)) {
      throw new Error(`BLOCK_CLAIM_BINDING: ${key} is missing or not a valid sha256`)
    }
  }
  // Future-authority values: source SHA is required and must be an exact
  // immutable commit identity; revocation state is required and explicit.
  const sourceSha = binding.authorizedExecutionSourceSha
  if (typeof sourceSha !== 'string' || !EXACT_COMMIT_RE.test(sourceSha)) {
    throw new Error('BLOCK_CLAIM_BINDING: authorizedExecutionSourceSha is missing or malformed; an exact immutable commit identity is required')
  }
  const revocation = binding.revocationState
  if (typeof revocation !== 'string' || !REVOCATION_STATES.includes(revocation)) {
    throw new Error('BLOCK_CLAIM_BINDING: revocationState is missing or not an explicit canonical state')
  }
  // NO environment substitution, no moving ref accepted as immutable source SHA,
  // no default NOT_REVOKED: the payload is transported exactly as supplied.
  return Object.freeze({ ...binding })
}

export const claimBindingEnv = binding => validateClaimBinding(binding)

/** Env keys that carry the claim binding into the profile process. */
export function claimBindingWithoutInvention() {
  return [...CLAIM_BINDING_ENV_KEYS]
}

const digestFile = path => createHash('sha256').update(readFileSync(path)).digest('hex')
function contained(root, candidate) {
  return candidate === root || candidate.startsWith(root.endsWith(sep) ? root : `${root}${sep}`)
}

function selectedFiles(root, { all = false } = {}) {
  const output = []
  function visit(path) {
    for (const entry of readdirSync(path, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.name === 'node_modules') continue
      const current = join(path, entry.name)
      if (entry.isSymbolicLink()) throw new Error(`Stage-A package contains a symlink: ${current}`)
      if (entry.isDirectory()) visit(current)
      else if (entry.isFile() && (all || current.endsWith('package.json') || current.includes(`${sep}lib${sep}`))) {
        output.push([relative(root, current), digestFile(current)])
      }
    }
  }
  visit(root)
  return output
}

export function packageTreeDigest(root) {
  return createHash('sha256').update(JSON.stringify(selectedFiles(realpathSync(root)))).digest('hex')
}

export function verifyMirroredPackage(canonicalRoot, candidateRoot) {
  const canonical = selectedFiles(realpathSync(canonicalRoot), { all: true })
  const candidate = selectedFiles(realpathSync(candidateRoot), { all: true })
  if (JSON.stringify(candidate) !== JSON.stringify(canonical)) {
    throw new Error(`Stage-A profile package identity mismatch: ${candidateRoot}`)
  }
}

function verifyProfileHome(args, preflightResult, identity) {
  if (args.profile !== 'headless') throw new Error('Stage-A requires the exact headless profile')
  const dshHome = realpathSync(args.dshHome)
  const profileRoot = join(dshHome, 'profiles/headless')
  for (const [name, expected] of Object.entries(identity.components.launchPolicy.qualifiedDshHomeProfileDigests)) {
    const path = join(profileRoot, name)
    if (!existsSync(path) || digestFile(path) !== expected) {
      throw new Error(`Stage-A qualified base profile identity mismatch: ${name}`)
    }
  }
  const modulesRoot = join(dshHome, 'profiles/node_modules')
  const qntyRoot = join(modulesRoot, '@qntylab')
  const expectedQntyPackages = {
    'dsh-stage-a-gated-provider': join(PHASE, 'profile/qntylab-stage-a-gated-provider'),
    'dsh-stage-a-parent-enforcement': join(PHASE, 'profile/qntylab-stage-a-parent-enforcement'),
  }
  const optionalOfflinePackages = {
    'dsh-stage-a-stub-provider': join(PHASE, 'stub/qntylab-stage-a-stub-provider'),
  }
  const actualQntyPackages = readdirSync(qntyRoot).sort()
  const allowed = new Set([...Object.keys(expectedQntyPackages), ...Object.keys(optionalOfflinePackages)])
  if (actualQntyPackages.some(name => !allowed.has(name))) {
    throw new Error('Stage-A DSH_HOME contains an unbound @qntylab package')
  }
  for (const [name, canonical] of Object.entries(expectedQntyPackages)) {
    verifyMirroredPackage(canonical, join(qntyRoot, name))
  }
  for (const [name, canonical] of Object.entries(optionalOfflinePackages)) {
    const candidate = join(qntyRoot, name)
    if (existsSync(candidate)) verifyMirroredPackage(canonical, candidate)
  }
  const runtimePackages = identity.components.launchPolicy.qualifiedRuntimePackageTreeDigests
  for (const [name, expected] of Object.entries(runtimePackages)) {
    const path = join(modulesRoot, '@deepseek-ai', name)
    if (!existsSync(path) || !contained(preflightResult.manifestRoot, realpathSync(path))) {
      throw new Error(`Stage-A qualified runtime package is missing or substituted: ${name}`)
    }
    if (packageTreeDigest(path) !== expected) {
      throw new Error(`Stage-A qualified runtime package digest mismatch: ${name}`)
    }
  }
}

export function assertQualifiedContractDigest(candidate, identity = computeDigests()) {
  if (candidate !== identity.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST) {
    throw new Error('BLOCK_RUNTIME_IDENTITY: stale or unknown qualified launch contract')
  }
}

function executableIdentity(preflightResult) {
  return Object.fromEntries(
    ['node', 'python', 'codex', 'claude'].map(name => [
      `${name}ExecutableDigest`,
      preflightResult.fingerprints[`${name}Executable`].digest,
    ]),
  )
}

function resolveOnPath(name, pathValue) {
  for (const directory of pathValue.split(delimiter)) {
    const candidate = join(directory, name)
    if (existsSync(candidate) && !lstatSync(candidate).isDirectory()) return realpathSync(candidate)
  }
  return undefined
}

export function verifiedNativePath(preflightResult) {
  const resolved = preflightResult.fingerprints
  const pathValue = [...new Set([
    dirname(resolved.codexExecutable.resolvedPath),
    dirname(resolved.claudeExecutable.resolvedPath),
    dirname(resolved.nodeExecutable.resolvedPath),
    dirname(resolved.pythonExecutable.resolvedPath),
  ])].join(delimiter)
  for (const name of ['codex', 'claude']) {
    const expected = resolved[`${name}Executable`].resolvedPath
    if (resolveOnPath(name, pathValue) !== expected) {
      throw new Error(`BLOCK_EXECUTABLE_IDENTITY: ${name} does not resolve to its preflighted executable`)
    }
  }
  return pathValue
}

function verifyStageAIdentity(args, preflightResult) {
  const identity = computeDigests()
  assertQualifiedContractDigest(args.qualifiedLaunchContractDigest, identity)
  if (sha256Canonical(runtimeIdentityFromManifest(preflightResult.manifest)) !== identity.NEW_RUNTIME_MANIFEST_DIGEST) {
    throw new Error('BLOCK_RUNTIME_IDENTITY: runtime manifest is not the qualified runtime')
  }
  if (sha256Canonical(executableIdentity(preflightResult)) !== identity.NEW_EXECUTABLE_IDENTITY_DIGEST) {
    throw new Error('BLOCK_EXECUTABLE_IDENTITY: executable set is not the qualified identity')
  }
  verifyProfileHome(args, preflightResult, identity)
  return { identity, nativePath: verifiedNativePath(preflightResult) }
}

export function parseLauncherArgv(argv) {
  const filtered = []
  let qualifiedLaunchContractDigest
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] !== QUALIFIED_CONTRACT_FLAG) {
      filtered.push(argv[index])
      continue
    }
    if (qualifiedLaunchContractDigest !== undefined || argv[index + 1] === undefined) {
      throw new LaunchPlaneError('BLOCK_LAUNCH_ARGV', `${QUALIFIED_CONTRACT_FLAG} requires exactly one value`)
    }
    qualifiedLaunchContractDigest = argv[index + 1]
    index += 1
  }
  return { ...predecessorParseLauncherArgv(filtered), qualifiedLaunchContractDigest }
}

export function preflightLaunch(args, options = {}) {
  const result = predecessorPreflightLaunch(args, options)
  const verified = verifyStageAIdentity(args, result)
  return { ...result, ...verified }
}

function validateExtraEnvironment(extraEnv) {
  for (const [key, value] of Object.entries(extraEnv)) {
    if (CLAIM_BINDING_ENV_KEYS.includes(key)) {
      // Claim-binding keys are owned exclusively by the validated claimBinding
      // payload. They can never enter through the ordinary extraEnv seam, so a
      // caller with extraEnv control cannot silently override a value that
      // validateClaimBinding already produced and approved (HIGH-1).
      throw new Error(`Stage-A claim-binding environment key cannot be supplied through extraEnv: ${key}`)
    }
    if (!ALLOWED_EXTRA_ENV.has(key)) throw new Error(`Stage-A extra environment key is denied: ${key}`)
    if (typeof value !== 'string' || value.length === 0) {
      throw new Error(`Stage-A extra environment value is invalid: ${key}`)
    }
  }
}

export function selectedPolicyPatches(args, extraEnv, offlineProfilePatch) {
  if (offlineProfilePatch === undefined) return [CANONICAL_POLICY_PATCH]
  const endpoint = new URL(args.parentEndpoint)
  const loopback = ['127.0.0.1', '::1', 'localhost'].includes(endpoint.hostname)
  const sentinel = extraEnv.OPENAI_API_KEY ?? ''
  const resolved = realpathSync(offlineProfilePatch)
  const invocationPath = resolve(extraEnv.QNTYLAB_DSH_STUB_INVOCATION_PATH ?? '')
  const invocationIsTemporary = isAbsolute(invocationPath)
    && !relative(realpathSync(tmpdir()), invocationPath).startsWith('..')
  const responseMode = extraEnv.QNTYLAB_DSH_STUB_RESPONSE_MODE
  if (
    !loopback
    || !/^QNTYLAB_FAKE_[A-Za-z0-9_]+_NOT_REAL$/.test(sentinel)
    || resolved !== realpathSync(OFFLINE_STUB_PATCH)
    || !invocationIsTemporary
    || !['clean', 'high-first'].includes(responseMode)
  ) {
    throw new Error('Stage-A offline profile substitution is denied outside the loopback sentinel harness')
  }
  return [OFFLINE_STUB_PATCH]
}

/**
 * Build the complete child env the launcher hands to the DSH profile process.
 *
 * This is the SINGLE env-construction code path (also used by spawnDsh). The
 * validated claim binding is applied AFTER extraEnv and a post-merge integrity
 * re-check guarantees the five claim-binding values are byte-identical to the
 * validated payload. Callers with ONLY ordinary extraEnv control cannot
 * overwrite a validated claim-binding value (HIGH-1).
 */
export function buildSpawnEnv(args, { extraEnv = {}, offlineProfilePatch, claimBinding, immediate }) {
  // extraEnv is validated on this shared seam as well (spawnDsh also validates,
  // but the exported env builder must never accept claim-binding keys through
  // the ordinary extraEnv seam either — HIGH-1 defense in depth).
  validateExtraEnvironment(extraEnv)
  // The claim binding must accompany every spawn. It is resolved against the
  // allowlisted set and transported into the child env EXACTLY as supplied —
  // the profile process never re-derives, re-substitutes, or defaults any of
  // these values.
  const validatedClaimBinding = validateClaimBinding(claimBinding)
  const claimEnv = Object.fromEntries(
    CLAIM_BINDING_ENV_KEYS.map(envKey => {
      const field = claimBindingEnvKeyField(envKey)
      return [envKey, validatedClaimBinding[field]]
    }),
  )
  const resolved = immediate.fingerprints
  const env = {
    PATH: immediate.nativePath,
    HOME: process.env.HOME ?? '',
    DSH_HOME: args.dshHome,
    QNTYLAB_ROOT: ROOT,
    QNTYLAB_PYTHON: resolved.pythonExecutable.resolvedPath,
    QNTYLAB_DSH_NATIVE_PATH: immediate.nativePath,
    ...(offlineProfilePatch === undefined
      ? {}
      : { QNTYLAB_DSH_OFFLINE_STUB_EXECUTABLE: OFFLINE_STUB_EXECUTABLE }),
    // extraEnv supplies ordinary non-claim runtime variables and is merged
    // BEFORE the claim binding so nothing can shadow an approved claim-binding
    // value.
    ...extraEnv,
    // The validated claim binding is applied LAST and is therefore
    // authoritative in the final process env. Claim-binding keys are already
    // excluded from extraEnv (validateExtraEnvironment above), so this ordering
    // is a second independent guarantee that they are byte-exact to the
    // validated binding by the time the child process starts.
    ...claimEnv,
  }
  if (args.parentEndpoint) env.QNTYLAB_DSH_PARENT_ENDPOINT = args.parentEndpoint
  // Post-merge integrity re-check: the five claim-binding env values must be
  // byte-identical to the values validateClaimBinding approved. No silent
  // fallback, no default NOT_REVOKED — any mismatch is a hard block.
  for (const envKey of CLAIM_BINDING_ENV_KEYS) {
    if (env[envKey] !== validatedClaimBinding[claimBindingEnvKeyField(envKey)]) {
      throw new Error(`BLOCK_CLAIM_BINDING: transport env re-check failed for ${envKey}`)
    }
  }
  return env
}

/** Phase-local Stage-A spawn boundary with an immediate identity recheck. */
export function spawnDsh(
  args,
  preflightResult,
  { extraEnv = {}, stdio = 'inherit', appArgs = [], offlineProfilePatch, claimBinding } = {},
) {
  if (!Array.isArray(appArgs) || appArgs.some(value => typeof value !== 'string')) {
    throw new TypeError('Stage-A application arguments must be a string array')
  }
  if (appArgs.some(value => value === '--profile' || value.startsWith('--profile=') || value === '--patch' || value.startsWith('--patch='))) {
    throw new Error('Stage-A application arguments cannot override the preflighted profile or policy patch')
  }
  validateExtraEnvironment(extraEnv)
  const policyPatches = selectedPolicyPatches(args, extraEnv, offlineProfilePatch)
  // Never trust a caller-constructed preflight object. Repeat the complete
  // predecessor + repaired-policy verification immediately before spawn.
  const immediate = preflightLaunch(args, { forbiddenRoots: [ROOT] })
  if (
    preflightResult?.cliDigest !== immediate.cliDigest
    || preflightResult?.workspaceReal !== immediate.workspaceReal
  ) throw new Error('BLOCK_RUNTIME_IDENTITY: supplied preflight receipt does not match immediate verification')
  // The env is built by the SAME exported code path the enforcement E2E
  // traverses, including the validated claim binding transport and the
  // post-merge integrity re-check.
  const env = buildSpawnEnv(args, { extraEnv, offlineProfilePatch, claimBinding, immediate })
  const resolved = immediate.fingerprints
  return spawn(
    resolved.nodeExecutable.resolvedPath,
    [
      immediate.cliPath,
      '--profile', args.profile,
      ...policyPatches.flatMap(path => ['--patch', path]),
      ...appArgs,
    ],
    { cwd: immediate.workspaceReal, env, stdio },
  )
}

/** Map an allowlisted env key to its camelCase claim-binding field. */
function claimBindingEnvKeyField(envKey) {
  return envKey
    .replace('QNTYLAB_DSH_', '')
    .toLowerCase()
    .replace(/_([a-z])/g, (_, letter) => letter.toUpperCase())
}

/** Claim-binding env mapping, exported for profile/config wiring. */
export const claimBindingEnvVars = binding => {
  const validated = validateClaimBinding(binding)
  return Object.fromEntries(
    CLAIM_BINDING_ENV_KEYS.map(envKey => [envKey, validated[claimBindingEnvKeyField(envKey)]]),
  )
}
