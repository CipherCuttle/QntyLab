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
const QUALIFIED_CONTRACT_FLAG = '--qualified-launch-contract-digest'
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

/** Phase-local Stage-A spawn boundary with an immediate identity recheck. */
export function spawnDsh(
  args,
  preflightResult,
  { extraEnv = {}, stdio = 'inherit', appArgs = [], offlineProfilePatch } = {},
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
    ...extraEnv,
  }
  if (args.parentEndpoint) env.QNTYLAB_DSH_PARENT_ENDPOINT = args.parentEndpoint
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
