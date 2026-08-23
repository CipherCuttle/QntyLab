#!/usr/bin/env node

// The only launcher boundary for the successor contract. The physical
// launcher remains the source of the pinned runtime/executable preflight; this
// module composes that result with the exact Stage-A policy and repeats the
// complete verification immediately before spawn.

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
  parseLauncherArgv as parsePhysicalLauncherArgv,
  preflightLaunch as physicalPreflightLaunch,
} from '../../dsh_runtime_materialization_and_launch_v0/launcher/qntylab-launch-dsh.mjs'
import {
  computeDigests,
  CONTRACT_PATH,
  PHASE,
  ROOT,
  STAGE_A_PHASE,
} from '../evidence/compute-digests.mjs'
import { canonicalJson, sha256Canonical } from '../evidence/canonical-json.mjs'

export { LaunchPlaneError }

const QUALIFIED_CONTRACT_FLAG = '--qualified-launch-contract-digest'
const CANONICAL_POLICY_PATCH = join(STAGE_A_PHASE, 'profile/cordis.patch.yml')
const OFFLINE_PROVIDER_OVERLAY = join(PHASE, 'stub/offline-provider-overlay.patch.yml')
const OFFLINE_STUB_EXECUTABLE = join(STAGE_A_PHASE, 'stub/native-child-stub.mjs')
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

function fail(code, message) {
  throw new LaunchPlaneError(code, message)
}

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
      else if (entry.isFile() && (all || entry.name === 'package.json' || current.includes(`${sep}lib${sep}`))) {
        output.push([relative(root, current), digestFile(current)])
      }
    }
  }
  visit(root)
  return output
}

function packageTreeDigest(root) {
  return sha256Canonical(selectedFiles(realpathSync(root)))
}

function verifyMirroredPackage(canonicalRoot, candidateRoot) {
  const canonical = selectedFiles(realpathSync(canonicalRoot), { all: true })
  const candidate = selectedFiles(realpathSync(candidateRoot), { all: true })
  if (JSON.stringify(candidate) !== JSON.stringify(canonical)) fail('BLOCK_RUNTIME_IDENTITY', `Stage-A profile package identity mismatch: ${candidateRoot}`)
}

function verifyProfileHome(args, physical, contract) {
  if (args.profile !== 'headless') fail('BLOCK_RUNTIME_IDENTITY', 'Stage-A requires the exact headless profile')
  let dshHome
  try { dshHome = realpathSync(args.dshHome) } catch { fail('BLOCK_RUNTIME_IDENTITY', `DSH_HOME is not a real directory: ${args.dshHome}`) }
  const policy = contract.components.compositeLaunchPolicy.stageAPolicy
  const profileRoot = join(dshHome, 'profiles/headless')
  for (const [name, expected] of Object.entries(policy.qualifiedDshHomeProfileDigests)) {
    const path = join(profileRoot, name)
    if (!existsSync(path) || digestFile(path) !== expected) fail('BLOCK_RUNTIME_IDENTITY', `qualified DSH_HOME profile identity mismatch: ${name}`)
  }
  const modulesRoot = join(dshHome, 'profiles/node_modules')
  const qntyRoot = join(modulesRoot, '@qntylab')
  const requiredQnty = {
    'dsh-stage-a-gated-provider': join(STAGE_A_PHASE, 'profile/qntylab-stage-a-gated-provider'),
    'dsh-stage-a-parent-enforcement': join(STAGE_A_PHASE, 'profile/qntylab-stage-a-parent-enforcement'),
  }
  const optionalQnty = { 'dsh-stage-a-stub-provider': join(STAGE_A_PHASE, 'stub/qntylab-stage-a-stub-provider') }
  if (!existsSync(qntyRoot)) fail('BLOCK_RUNTIME_IDENTITY', 'DSH_HOME is missing the Stage-A package scope')
  const actualQnty = readdirSync(qntyRoot).sort()
  const allowed = new Set([...Object.keys(requiredQnty), ...Object.keys(optionalQnty)])
  if (actualQnty.some(name => !allowed.has(name))) fail('BLOCK_RUNTIME_IDENTITY', 'DSH_HOME contains an unbound @qntylab package')
  for (const [name, canonical] of Object.entries(requiredQnty)) {
    const candidate = join(qntyRoot, name)
    if (!existsSync(candidate)) fail('BLOCK_RUNTIME_IDENTITY', `DSH_HOME is missing ${name}`)
    verifyMirroredPackage(canonical, candidate)
  }
  for (const [name, canonical] of Object.entries(optionalQnty)) {
    const candidate = join(qntyRoot, name)
    if (existsSync(candidate)) verifyMirroredPackage(canonical, candidate)
  }
  for (const [name, expected] of Object.entries(policy.qualifiedRuntimePackageTreeDigests)) {
    const path = join(modulesRoot, '@deepseek-ai', name)
    if (!existsSync(path) || !contained(physical.manifestRoot, realpathSync(path))) fail('BLOCK_RUNTIME_IDENTITY', `qualified runtime package is missing or substituted: ${name}`)
    if (packageTreeDigest(path) !== expected) fail('BLOCK_RUNTIME_IDENTITY', `qualified runtime package digest mismatch: ${name}`)
  }
}

export function verifyPolicyBytes(contract, { canonicalPolicyPath = CANONICAL_POLICY_PATCH, offlineProviderOverlayPath = OFFLINE_PROVIDER_OVERLAY } = {}) {
  const policy = contract.components.compositeLaunchPolicy.stageAPolicy
  for (const [path, expected] of Object.entries(policy.productionFileDigests)) {
    const absolute = resolve(ROOT, path)
    if (!existsSync(absolute) || digestFile(absolute) !== expected) fail('BLOCK_RUNTIME_IDENTITY', `Stage-A policy artifact drifted: ${path}`)
  }
  const canonical = readFileSync(canonicalPolicyPath, 'utf8')
  const overlay = readFileSync(offlineProviderOverlayPath, 'utf8')
  if (digestFile(canonicalPolicyPath) !== policy.canonicalPolicy.digest) fail('BLOCK_RUNTIME_IDENTITY', 'canonical Stage-A policy bytes drifted')
  if (digestFile(offlineProviderOverlayPath) !== policy.offlineProviderOverlay.digest) fail('BLOCK_RUNTIME_IDENTITY', 'offline provider overlay bytes drifted')
  for (const token of ['qntylab-stage-a-gated-codex', 'qntylab-stage-a-gated-claude', 'qntylab-stage-a-parent-enforcement', 'enableRunInBackground: false', 'maxRetries: 0', 'maxTokens: 4096']) {
    if (!canonical.includes(token)) fail('BLOCK_RUNTIME_IDENTITY', `canonical Stage-A policy token missing: ${token}`)
  }
  for (const token of ['subagent-codex', 'subagent-claude-code', 'qntylab-offline-raw-codex', 'qntylab-offline-raw-claude', '@qntylab/dsh-stage-a-stub-provider']) {
    if (!overlay.includes(token)) fail('BLOCK_RUNTIME_IDENTITY', `offline provider overlay token missing: ${token}`)
  }
  if (overlay.includes('qntylab-stage-a-parent-enforcement') || overlay.includes('tool-subagent-control')) fail('BLOCK_RUNTIME_IDENTITY', 'offline overlay replaces canonical Stage-A controls')
  return { canonicalPolicyDigest: digestFile(canonicalPolicyPath), offlineProviderOverlayDigest: digestFile(offlineProviderOverlayPath), canonicalStageAPolicyActive: true }
}

export function verifyContractArtifact(manifestPath, dshHome) {
  let contract
  try { contract = JSON.parse(readFileSync(CONTRACT_PATH, 'utf8')) } catch (error) { fail('BLOCK_RUNTIME_IDENTITY', `qualified composite contract is unreadable: ${error.message}`) }
  let computed
  try { computed = computeDigests({ manifestPath, profileHome: dshHome }) } catch (error) { fail('BLOCK_RUNTIME_IDENTITY', `qualified composite identity cannot be recomputed: ${error.message}`) }
  if (canonicalJson(contract) !== canonicalJson(computed.contract)) fail('BLOCK_RUNTIME_IDENTITY', 'qualified composite contract artifact does not match current component bytes')
  if (sha256Canonical(contract.qualifiedContract) !== contract.qualifiedContractDigest) fail('BLOCK_RUNTIME_IDENTITY', 'qualified composite contract digest is internally inconsistent')
  return { contract, computed }
}

export function verifyCompositeLauncherBytes(contract, launcherPath = fileURLToPath(import.meta.url)) {
  const expected = contract.components.compositeLaunchPolicy.compositeLauncher.digest
  if (digestFile(launcherPath) !== expected) fail('BLOCK_RUNTIME_IDENTITY', 'composite launcher bytes are not the qualified launcher')
  return true
}

function executableIdentity(physical) {
  return Object.fromEntries(['node', 'python', 'codex', 'claude'].map(name => [`${name}ExecutableDigest`, physical.fingerprints[`${name}Executable`].digest]))
}

function verifyCompositeIdentity(args, physical) {
  const { contract, computed } = verifyContractArtifact(args.runtimeManifest, args.dshHome)
  if (args.qualifiedLaunchContractDigest !== computed.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST) fail('BLOCK_RUNTIME_IDENTITY', 'stale or unknown qualified composite launch contract')
  if (sha256Canonical(computed.contract.components.runtimeIdentity) !== computed.runtimeManifestDigest) fail('BLOCK_RUNTIME_IDENTITY', 'runtime identity digest is internally inconsistent')
  if (sha256Canonical(computed.contract.components.executableIdentity) !== computed.executableIdentityDigest) fail('BLOCK_EXECUTABLE_IDENTITY', 'executable identity digest is internally inconsistent')
  if (sha256Canonical(executableIdentity(physical)) !== computed.executableIdentityDigest) fail('BLOCK_EXECUTABLE_IDENTITY', 'action-time executable identity is not the qualified identity')
  if (sha256Canonical(computed.contract.components.compositeLaunchPolicy) !== computed.compositeLaunchPolicyDigest) fail('BLOCK_RUNTIME_IDENTITY', 'composite launch policy digest is internally inconsistent')
  const compositeLauncher = computed.contract.components.compositeLaunchPolicy.compositeLauncher
  if (compositeLauncher.path !== relative(ROOT, fileURLToPath(import.meta.url))) fail('BLOCK_RUNTIME_IDENTITY', 'composite launcher path is not the qualified launcher')
  verifyCompositeLauncherBytes(contract)
  const policyBytes = verifyPolicyBytes(contract)
  verifyProfileHome(args, physical, contract)
  return { contract, computed, policyBytes }
}

export function parseLauncherArgv(argv) {
  const filtered = []
  let qualifiedLaunchContractDigest
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] !== QUALIFIED_CONTRACT_FLAG) {
      filtered.push(argv[index])
      continue
    }
    if (qualifiedLaunchContractDigest !== undefined || argv[index + 1] === undefined) fail('BLOCK_LAUNCH_ARGV', `${QUALIFIED_CONTRACT_FLAG} requires exactly one value`)
    qualifiedLaunchContractDigest = argv[index + 1]
    index += 1
  }
  if (qualifiedLaunchContractDigest === undefined) fail('BLOCK_LAUNCH_ARGV', `${QUALIFIED_CONTRACT_FLAG} is required`)
  return { ...parsePhysicalLauncherArgv(filtered), qualifiedLaunchContractDigest }
}

export function preflightLaunch(args, options = {}) {
  const physical = physicalPreflightLaunch(args, options)
  const composite = verifyCompositeIdentity(args, physical)
  return { ...physical, ...composite, nativePath: verifiedNativePath(physical) }
}

function resolveOnPath(name, pathValue) {
  for (const directory of pathValue.split(delimiter)) {
    const candidate = join(directory, name)
    if (existsSync(candidate) && !lstatSync(candidate).isDirectory()) return realpathSync(candidate)
  }
  return undefined
}

export function verifiedNativePath(physical) {
  const pathValue = [...new Set(['codex', 'claude', 'node', 'python'].map(name => dirname(physical.fingerprints[`${name}Executable`].resolvedPath)))].join(delimiter)
  for (const name of ['codex', 'claude']) {
    const expected = physical.fingerprints[`${name}Executable`].resolvedPath
    if (resolveOnPath(name, pathValue) !== expected) fail('BLOCK_EXECUTABLE_IDENTITY', `${name} no longer resolves to its preflighted executable`)
  }
  return pathValue
}

function validateExtraEnvironment(extraEnv) {
  for (const [key, value] of Object.entries(extraEnv)) {
    if (!ALLOWED_EXTRA_ENV.has(key)) throw new Error(`Stage-A extra environment key is denied: ${key}`)
    if (typeof value !== 'string' || value.length === 0) throw new Error(`Stage-A extra environment value is invalid: ${key}`)
  }
}

export function selectedPolicyPatches(args, extraEnv, offlineProviderOverlay) {
  if (offlineProviderOverlay === undefined) return [CANONICAL_POLICY_PATCH]
  const endpoint = new URL(args.parentEndpoint)
  const loopback = ['127.0.0.1', '::1', 'localhost'].includes(endpoint.hostname)
  const sentinel = extraEnv.OPENAI_API_KEY ?? ''
  const invocationPath = resolve(extraEnv.QNTYLAB_DSH_STUB_INVOCATION_PATH ?? '')
  const invocationIsTemporary = isAbsolute(invocationPath) && !relative(realpathSync(tmpdir()), invocationPath).startsWith('..')
  const resolved = realpathSync(offlineProviderOverlay)
  const responseMode = extraEnv.QNTYLAB_DSH_STUB_RESPONSE_MODE
  if (!loopback || !/^QNTYLAB_FAKE_[A-Za-z0-9_]+_NOT_REAL$/.test(sentinel) || resolved !== realpathSync(OFFLINE_PROVIDER_OVERLAY) || !invocationIsTemporary || !['clean', 'high-first'].includes(responseMode)) {
    throw new Error('Stage-A offline provider substitution is denied outside the loopback sentinel harness')
  }
  return [CANONICAL_POLICY_PATCH, OFFLINE_PROVIDER_OVERLAY]
}

/** Composite spawn boundary: policy and physical identity are revalidated here. */
export function spawnDsh(args, preflightResult, { extraEnv = {}, stdio = 'inherit', appArgs = [], offlineProviderOverlay } = {}) {
  if (!Array.isArray(appArgs) || appArgs.some(value => typeof value !== 'string')) throw new TypeError('Stage-A application arguments must be a string array')
  if (appArgs.some(value => value === '--profile' || value.startsWith('--profile=') || value === '--patch' || value.startsWith('--patch='))) throw new Error('Stage-A application arguments cannot override the preflighted profile or policy patch')
  validateExtraEnvironment(extraEnv)
  const policyPatches = selectedPolicyPatches(args, extraEnv, offlineProviderOverlay)
  const immediate = preflightLaunch(args, { forbiddenRoots: [ROOT] })
  if (preflightResult?.cliDigest !== immediate.cliDigest || preflightResult?.workspaceReal !== immediate.workspaceReal || preflightResult?.computed?.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST !== immediate.computed?.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST) throw new Error('BLOCK_RUNTIME_IDENTITY: supplied preflight receipt does not match immediate composite verification')
  const resolved = immediate.fingerprints
  const env = {
    PATH: immediate.nativePath,
    HOME: process.env.HOME ?? '',
    DSH_HOME: args.dshHome,
    QNTYLAB_ROOT: ROOT,
    QNTYLAB_PYTHON: resolved.pythonExecutable.resolvedPath,
    QNTYLAB_DSH_NATIVE_PATH: immediate.nativePath,
    ...(offlineProviderOverlay === undefined ? {} : { QNTYLAB_DSH_OFFLINE_STUB_EXECUTABLE: OFFLINE_STUB_EXECUTABLE }),
    ...extraEnv,
  }
  if (args.parentEndpoint) env.QNTYLAB_DSH_PARENT_ENDPOINT = args.parentEndpoint
  return spawn(resolved.nodeExecutable.resolvedPath, [immediate.cliPath, '--profile', args.profile, ...policyPatches.flatMap(path => ['--patch', path]), ...appArgs], { cwd: immediate.workspaceReal, env, stdio })
}

async function main() {
  try {
    const args = parseLauncherArgv(process.argv.slice(2))
    const preflight = preflightLaunch(args, { forbiddenRoots: (process.env.QNTYLAB_LAUNCH_FORBIDDEN_ROOTS || '').split(':').filter(Boolean) })
    const child = spawnDsh(args, preflight)
    child.on('exit', code => { process.exitCode = code ?? 1 })
  } catch (error) {
    if (error instanceof LaunchPlaneError) {
      process.stderr.write(`${error.code}: ${error.message}\n`)
      process.exitCode = 1
      return
    }
    throw error
  }
}

if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`)
  process.exitCode = 1
})
