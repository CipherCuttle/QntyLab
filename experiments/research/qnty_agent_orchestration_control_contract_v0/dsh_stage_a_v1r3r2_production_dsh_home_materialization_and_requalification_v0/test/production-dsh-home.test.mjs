#!/usr/bin/env node --test

// The twenty required negative controls, plus the positive path and the
// determinism gate. Every control is a real executed test against real
// materialized bytes: none of them asserts that a string appears in an
// authorization artifact.
//
// No test mutates the pinned DSH runtime, the ambient scratch roots, or any
// canonical Git-tracked source. Controls that need a damaged input build a
// disposable copy and damage that.

import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync,
  realpathSync, rmSync, symlinkSync, unlinkSync, writeFileSync,
} from 'node:fs'
import { tmpdir, homedir } from 'node:os'
import { join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  DSH_HOME_MANIFEST_FILENAME,
  MaterializationError,
  ROOT,
  STAGE_A_PHASE,
  applyQualificationOverlay,
  deriveHeadlessProfileBytes,
  materializeStageADshHome,
  readRuntimeIdentity,
  resolveDestination,
  verifyHomeManifest,
  verifyMaterializedHome,
} from '../materializer/qntylab-materialize-stage-a-dsh-home.mjs'
import {
  COMPOSITE_LAUNCHER_RELATIVE_PATH,
  FIXTURE,
  MATERIALIZER_RELATIVE_PATH,
  computeSuccessorContract,
} from '../contract/successor-contract.mjs'
import { prepareProductionLaunch } from '../preparation/prepare-production-launch.mjs'
import { parseLauncherArgv, preflightLaunch } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/launcher/qntylab-launch-dsh.mjs'
import { sha256Canonical } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/canonical-json.mjs'

const PHASE = resolve(fileURLToPath(import.meta.url), '../..')
const AMBIENT_SCRATCH_DSH_HOME = '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home'

const scratches = []
function scratchDir(label) {
  const dir = mkdtempSync(join(tmpdir(), `qntylab-neg-${label}-`))
  scratches.push(dir)
  return dir
}
function freshHome(label) {
  const scratch = scratchDir(label)
  const destination = join(scratch, 'dsh-home')
  const result = materializeStageADshHome({ destination })
  return { scratch, home: destination, result }
}
function expectBlocked(fn, codePattern) {
  let error
  try { fn() } catch (caught) { error = caught }
  assert.ok(error !== undefined, 'expected the operation to fail closed, but it succeeded')
  assert.ok(error instanceof MaterializationError || error.code !== undefined,
    `expected a coded failure, got: ${error?.message}`)
  if (codePattern !== undefined) {
    assert.match(error.code ?? '', codePattern, `unexpected failure code ${error.code}: ${error.message}`)
  }
  return error
}
process.on('exit', () => { for (const dir of scratches) rmSync(dir, { recursive: true, force: true }) })

// --------------------------------------------------------------- positive ---

test('POSITIVE: production materialization from an empty destination succeeds', () => {
  const { home, result } = freshHome('positive')
  assert.equal(result.manifest.classification, 'PRODUCTION')
  assert.equal(result.manifest.productionStubProviderPresent, false)
  assert.ok(existsSync(join(home, 'profiles/headless/cordis.yml')))
  assert.ok(existsSync(join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-gated-provider')))
  assert.ok(existsSync(join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-parent-enforcement')))
  assert.ok(!existsSync(join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-stub-provider')))
  verifyHomeManifest(home)
})

test('DETERMINISM: two independent materializations have identical identity', () => {
  const a = freshHome('det-a')
  const b = freshHome('det-b')
  assert.equal(a.result.homeManifestDigest, b.result.homeManifestDigest)
  assert.deepEqual(a.result.manifest.packageInventory, b.result.manifest.packageInventory)
  assert.deepEqual(a.result.manifest.objects, b.result.manifest.objects)
})

test('AMBIENT INDEPENDENCE: no ambient root supplies bytes or identity', () => {
  const { result } = freshHome('ambient')
  assert.equal(result.manifest.provenance.skippedDependencyEdges.loaderVisibleUnresolvedPackages, 0)
  assert.deepEqual(result.manifest.provenance.ambientRootsUsed, [])
  assert.equal(result.manifest.provenance.ambientAuthorityUsed, false)
  const serialized = JSON.stringify(result.manifest)
  for (const ambient of ['qntylab-dsh-v1r3r1-repair', 'qntylab-dsh-v1r3r2-claude-repair-source', 'qntylab-dsh-v1r3r1-repair-source-2']) {
    assert.ok(!serialized.includes(ambient), `home manifest references an ambient root: ${ambient}`)
  }
})

// ------------------------------------------------------- negative controls ---

test('NC-01 empty destination succeeds', () => {
  const scratch = scratchDir('nc01')
  const destination = join(scratch, 'dsh-home')
  const result = materializeStageADshHome({ destination })
  assert.equal(result.manifest.classification, 'PRODUCTION')
  // a second materialization into the same, now-populated destination is refused
  expectBlocked(() => materializeStageADshHome({ destination }), /BLOCK_DESTINATION/)
})

test('NC-02 missing profile source fails', () => {
  const fake = scratchDir('nc02')
  mkdirSync(join(fake, 'apps/cli/src'), { recursive: true })
  // packages/boot/app-boot/src/profile.ts is deliberately absent
  expectBlocked(() => deriveHeadlessProfileBytes(fake), /BLOCK_SOURCE_PROVENANCE/)
})

test('NC-03 modified profile byte fails', () => {
  // (a) a tampered pinned-source template yields non-canonical profile bytes
  const runtime = readRuntimeIdentity(undefined)
  const canonical = deriveHeadlessProfileBytes(runtime.runtimeRoot)
  const fake = scratchDir('nc03')
  for (const relativePath of ['apps/cli/src/profile-boot.ts', 'packages/boot/app-boot/src/profile.ts']) {
    mkdirSync(join(fake, relativePath, '..'), { recursive: true })
    cpSync(join(runtime.runtimeRoot, relativePath), join(fake, relativePath))
  }
  const target = join(fake, 'packages/boot/app-boot/src/profile.ts')
  writeFileSync(target, readFileSync(target, 'utf8').replace('nodeLinker: hoisted', 'nodeLinker: isolated'))
  const tampered = deriveHeadlessProfileBytes(fake)
  assert.notEqual(tampered.files['pnpm-workspace.yaml'], canonical.files['pnpm-workspace.yaml'])

  // (b) a tampered materialized profile byte is caught by the home manifest
  const { home } = freshHome('nc03b')
  writeFileSync(join(home, 'profiles/headless/cordis.yml'), '# tampered\n[]\n')
  expectBlocked(() => verifyHomeManifest(home), /BLOCK_HOME_MANIFEST/)
})

test('NC-04 missing gated-provider fails', () => {
  const { home, result } = freshHome('nc04')
  rmSync(join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-gated-provider'), { recursive: true, force: true })
  expectBlocked(() => verifyMaterializedHome(home, { runtimeRoot: result.runtimeRoot }), /BLOCK_PACKAGE_IDENTITY/)
  // and the materializer refuses to build one from a source tree missing it
  const partial = scratchDir('nc04b')
  cpSync(join(STAGE_A_PHASE, 'profile/qntylab-stage-a-parent-enforcement'), join(partial, 'profile/qntylab-stage-a-parent-enforcement'), { recursive: true })
  expectBlocked(() => materializeStageADshHome({
    destination: join(scratchDir('nc04c'), 'dsh-home'),
    stageAPhaseRoot: partial,
  }), /BLOCK_PACKAGE_PROVENANCE/)
})

test('NC-05 modified gated-provider fails', () => {
  const { home } = freshHome('nc05')
  const file = join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-gated-provider/lib/index.js')
  writeFileSync(file, `${readFileSync(file, 'utf8')}\n// tampered\n`)
  expectBlocked(() => verifyHomeManifest(home), /BLOCK_HOME_MANIFEST/)
})

test('NC-06 missing parent-enforcement fails', () => {
  const { home, result } = freshHome('nc06')
  rmSync(join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-parent-enforcement'), { recursive: true, force: true })
  expectBlocked(() => verifyMaterializedHome(home, { runtimeRoot: result.runtimeRoot }), /BLOCK_PACKAGE_IDENTITY/)
})

test('NC-07 modified parent-enforcement fails', () => {
  const { home } = freshHome('nc07')
  const file = join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-parent-enforcement/lib/guard.mjs')
  writeFileSync(file, `${readFileSync(file, 'utf8')}\n// tampered\n`)
  expectBlocked(() => verifyHomeManifest(home), /BLOCK_HOME_MANIFEST/)
})

test('NC-08 unexpected @qntylab package fails', () => {
  const { home, result } = freshHome('nc08')
  const intruder = join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-unbound-extra')
  mkdirSync(intruder, { recursive: true })
  writeFileSync(join(intruder, 'package.json'), '{"name":"@qntylab/dsh-stage-a-unbound-extra","version":"0.0.0"}\n')
  expectBlocked(() => verifyMaterializedHome(home, { runtimeRoot: result.runtimeRoot }), /BLOCK_PACKAGE_IDENTITY/)
})

test('NC-09 production stub-provider presence fails', () => {
  const { home, result } = freshHome('nc09')
  cpSync(join(STAGE_A_PHASE, 'stub/qntylab-stage-a-stub-provider'),
    join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-stub-provider'), { recursive: true })
  const error = expectBlocked(() => verifyMaterializedHome(home, { runtimeRoot: result.runtimeRoot }),
    /BLOCK_PRODUCTION_STUB_PROVIDER/)
  assert.match(error.message, /stub provider/i)
  // the production materializer also refuses to produce a non-production home
  expectBlocked(() => materializeStageADshHome({
    destination: join(scratchDir('nc09b'), 'dsh-home'),
    classification: 'QUALIFICATION_OVERLAY',
  }), /BLOCK_CLASSIFICATION/)
})

test('NC-10 wrong @deepseek-ai package fails', () => {
  const { home, result } = freshHome('nc10')
  const link = join(home, 'profiles/node_modules/@deepseek-ai/dsh-llm')
  unlinkSync(link)
  symlinkSync(join(result.runtimeRoot, 'packages/llm/llm-pi-ai'), link, 'junction')
  expectBlocked(() => verifyHomeManifest(home), /BLOCK_HOME_MANIFEST/)
})

test('NC-11 missing runtime package fails', () => {
  const { home, result } = freshHome('nc11')
  unlinkSync(join(home, 'profiles/node_modules/@deepseek-ai/dsh-subagent-codex'))
  expectBlocked(() => verifyMaterializedHome(home, { runtimeRoot: result.runtimeRoot }), /BLOCK_RUNTIME_IDENTITY/)
})

test('NC-12 symlink escape fails', () => {
  const { home, result } = freshHome('nc12')
  const outside = scratchDir('nc12-outside')
  mkdirSync(join(outside, 'evil'), { recursive: true })
  writeFileSync(join(outside, 'evil/package.json'), '{"name":"@deepseek-ai/dsh-subprocess","version":"9.9.9"}\n')
  const link = join(home, 'profiles/node_modules/@deepseek-ai/dsh-subprocess')
  unlinkSync(link)
  symlinkSync(join(outside, 'evil'), link, 'junction')
  expectBlocked(() => verifyMaterializedHome(home, { runtimeRoot: result.runtimeRoot }), /BLOCK_SYMLINK_CONTAINMENT/)
})

test('NC-13 destination inside QntyLab fails', () => {
  const runtimeRoot = readRuntimeIdentity(undefined).runtimeRoot
  expectBlocked(() => resolveDestination(join(ROOT, 'tmp-dsh-home'), { runtimeRoot }), /BLOCK_DESTINATION/)
  expectBlocked(() => materializeStageADshHome({ destination: join(ROOT, 'tmp-dsh-home') }), /BLOCK_DESTINATION/)
})

test('NC-14 destination inside DSH runtime fails', () => {
  const runtimeRoot = readRuntimeIdentity(undefined).runtimeRoot
  expectBlocked(() => resolveDestination(join(runtimeRoot, 'tmp-dsh-home'), { runtimeRoot }), /BLOCK_DESTINATION/)
  expectBlocked(() => materializeStageADshHome({ destination: join(runtimeRoot, 'tmp-dsh-home') }), /BLOCK_DESTINATION/)
})

test('NC-15 destination inside operator home fails', () => {
  const runtimeRoot = readRuntimeIdentity(undefined).runtimeRoot
  expectBlocked(() => resolveDestination(join(homedir(), 'tmp-dsh-home'), { runtimeRoot }), /BLOCK_DESTINATION/)
  // a symlinked parent cannot smuggle the destination into the operator home
  const scratch = scratchDir('nc15')
  symlinkSync(homedir(), join(scratch, 'sneaky'), 'junction')
  expectBlocked(() => resolveDestination(join(scratch, 'sneaky/tmp-dsh-home'), { runtimeRoot }), /BLOCK_DESTINATION/)
})

test('NC-16 stale scratch DSH_HOME cannot substitute', () => {
  if (!existsSync(AMBIENT_SCRATCH_DSH_HOME)) return // absence is itself the desired state
  const scratch = scratchDir('nc16')
  mkdirSync(join(scratch, 'workspace'), { recursive: true })
  const args = parseLauncherArgv([
    '--qualified-launch-contract-digest', 'a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be',
    '--runtime-manifest', join(ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_runtime_materialization_and_launch_v0/evidence/runtime_manifest.json'),
    '--workspace', join(scratch, 'workspace'),
    '--dsh-home', AMBIENT_SCRATCH_DSH_HOME,
    '--profile', 'headless',
    '--controller-state', join(scratch, 'child.json'),
    '--node-executable', process.execPath,
    '--python-executable', '/usr/bin/python3',
    '--codex-executable', '/home/swirky/.local/bin/codex',
    '--claude-executable', '/usr/bin/claude',
    '--parent-endpoint', 'http://127.0.0.1:1/',
  ])
  const error = expectBlocked(() => preflightLaunch(args, { forbiddenRoots: [ROOT] }), /BLOCK_RUNTIME_IDENTITY/)
  assert.match(error.message, /Stage-A package scope|package/i)
  // the ambient home is still untouched: read-only forensic reference only
  assert.ok(!existsSync(join(AMBIENT_SCRATCH_DSH_HOME, DSH_HOME_MANIFEST_FILENAME)),
    'the ambient scratch DSH_HOME must never receive a production manifest')
})

test('NC-17 caller-supplied arbitrary DSH_HOME cannot bypass the materializer', () => {
  const scratch = scratchDir('nc17')
  const handBuilt = join(scratch, 'hand-built-home')
  const source = freshHome('nc17-source')
  cpSync(source.home, handBuilt, { recursive: true, dereference: false })
  rmSync(join(handBuilt, DSH_HOME_MANIFEST_FILENAME), { force: true })
  // no manifest => no production identity
  expectBlocked(() => verifyHomeManifest(handBuilt), /BLOCK_HOME_MANIFEST/)
  // and the production path refuses to adopt a pre-populated destination
  expectBlocked(() => prepareProductionLaunch({
    dshHomeDestination: handBuilt,
    workspace: join(scratch, 'workspace'),
    fixtureDestination: join(scratch, 'fixture'),
    launchArgv: [],
  }), /BLOCK_DESTINATION/)
})

test('NC-18 materializer-byte substitution invalidates the contract', () => {
  const { result } = freshHome('nc18')
  const baseline = computeSuccessorContract({
    homeManifest: result.identityBody,
    profileHome: result.destination,
  })
  const overlay = scratchDir('nc18-overlay')
  for (const relativePath of [MATERIALIZER_RELATIVE_PATH, COMPOSITE_LAUNCHER_RELATIVE_PATH,
    ...FIXTURE.files.map(file => `${FIXTURE.fixtureRoot}/${file}`)]) {
    mkdirSync(join(overlay, relativePath, '..'), { recursive: true })
    cpSync(join(ROOT, relativePath), join(overlay, relativePath))
  }
  const substituted = join(overlay, MATERIALIZER_RELATIVE_PATH)
  writeFileSync(substituted, `${readFileSync(substituted, 'utf8')}\n// substituted materializer bytes\n`)
  const tampered = computeSuccessorContract({
    homeManifest: result.identityBody,
    profileHome: result.destination,
    qntyLabRoot: overlay,
  })
  assert.notEqual(tampered.NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST, baseline.NEW_PRODUCTION_DSH_HOME_MATERIALIZER_DIGEST)
  assert.notEqual(tampered.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, baseline.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST)
})

test('NC-19 home-manifest substitution invalidates the contract', () => {
  const { home } = freshHome('nc19')
  const manifestPath = join(home, DSH_HOME_MANIFEST_FILENAME)
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))

  // a naive edit breaks the self-consistency check
  manifest.productionStubProviderPresent = true
  writeFileSync(manifestPath, `${JSON.stringify(manifest, undefined, 2)}\n`)
  expectBlocked(() => verifyHomeManifest(home), /BLOCK_HOME_MANIFEST/)

  // a sophisticated attacker recomputes the digest so the manifest is
  // internally consistent, but the recorded objects no longer match disk
  const fresh = freshHome('nc19b')
  const path2 = join(fresh.home, DSH_HOME_MANIFEST_FILENAME)
  const m2 = JSON.parse(readFileSync(path2, 'utf8'))
  const profileObject = m2.objects.find(object => object.path === 'profiles/headless/package.json')
  profileObject.digest = 'deadbeef'.repeat(8)
  const { homeManifestDigest, materializedAtUtc, destinationAbsolutePath, materializationRootAbsolutePath, ...identityBody } = m2
  m2.homeManifestDigest = sha256Canonical(identityBody)
  writeFileSync(path2, `${JSON.stringify(m2, undefined, 2)}\n`)
  expectBlocked(() => verifyHomeManifest(fresh.home), /BLOCK_HOME_MANIFEST/)
})

test('NC-19b home-manifest root-widening forgery is rejected', () => {
  // The manifest's materialization root is outside its identity digest, so an
  // attacker can rewrite it and still produce a self-consistent digest. If the
  // verifier trusted that field it could be widened to '/' so that every
  // symlink "resolves inside the runtime root".
  const { home, result } = freshHome('nc19c')
  const outside = scratchDir('nc19c-outside')
  mkdirSync(join(outside, 'evil'), { recursive: true })
  writeFileSync(join(outside, 'evil/package.json'), '{"name":"ws","version":"9.9.9"}\n')

  const manifestPath = join(home, DSH_HOME_MANIFEST_FILENAME)
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  const victim = manifest.objects.find(object => object.path === 'profiles/node_modules/ws')
  assert.ok(victim, 'expected a ws package in the canonical graph')
  const link = join(home, victim.path)
  unlinkSync(link)
  symlinkSync(join(outside, 'evil'), link, 'junction')

  // widen the root to '/' and re-relativize every recorded target to it
  manifest.materializationRootAbsolutePath = '/'
  for (const object of manifest.objects) {
    if (object.type !== 'symlink') continue
    object.targetRealpathRelativeToRuntimeRoot = object.path === victim.path
      ? relative('/', realpathSync(link))
      : relative('/', join(result.runtimeRoot, object.targetRealpathRelativeToRuntimeRoot))
  }
  const { homeManifestDigest, materializedAtUtc, destinationAbsolutePath, materializationRootAbsolutePath, ...identityBody } = manifest
  manifest.homeManifestDigest = sha256Canonical(identityBody)
  writeFileSync(manifestPath, `${JSON.stringify(manifest, undefined, 2)}\n`)

  const error = expectBlocked(() => verifyHomeManifest(home), /BLOCK_HOME_MANIFEST/)
  assert.match(error.message, /foreign materialization root/)
})

test('NC-19c unrecorded objects added to a verified home are rejected', () => {
  for (const [label, add] of [
    ['top-level package', home => {
      const dir = join(home, 'profiles/node_modules/evil-pkg')
      mkdirSync(dir, { recursive: true })
      writeFileSync(join(dir, 'package.json'), '{"name":"evil-pkg","version":"0.0.0"}\n')
    }],
    ['scoped runtime package', home => {
      const dir = join(home, 'profiles/node_modules/@deepseek-ai/dsh-evil')
      mkdirSync(dir, { recursive: true })
      writeFileSync(join(dir, 'package.json'), '{"name":"@deepseek-ai/dsh-evil","version":"0.0.0"}\n')
    }],
    ['extra profile file', home => {
      writeFileSync(join(home, 'profiles/headless/rogue.patch.yml'), '- id: evil\n')
    }],
    ['stub provider outside the @qntylab scope', home => {
      cpSync(join(STAGE_A_PHASE, 'stub/qntylab-stage-a-stub-provider'),
        join(home, 'profiles/node_modules/dsh-stage-a-stub-provider'), { recursive: true })
    }],
  ]) {
    const { home } = freshHome('nc19d')
    add(home)
    const error = expectBlocked(() => verifyHomeManifest(home), /BLOCK_HOME_MANIFEST/)
    assert.match(error.message, /unrecorded objects/, `addition not detected: ${label}`)
  }
})

test('NC-20 qualification-only helper cannot be used as production authority', () => {
  // the production preparation path does not reach the qualification module
  for (const relativePath of [MATERIALIZER_RELATIVE_PATH, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/preparation/prepare-production-launch.mjs']) {
    // strip comments so documentation that *names* the rejected helper does not
    // count as using it; only executable code is inspected
    const code = readFileSync(join(ROOT, relativePath), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n').map(line => line.replace(/(^|\s)\/\/.*$/, '')).join('\n')
    assert.ok(!code.includes('run-composite-qualification'),
      `${relativePath} must not import the qualification-only helper`)
    assert.ok(!code.includes('prepareDisposableDshHome'),
      `${relativePath} must not use the qualification-only helper`)
    assert.ok(!code.includes('QNTYLAB_QUALIFIED_DSH_HOME'),
      `${relativePath} must not honour the ambient qualified-home override`)
    for (const ambient of ['qntylab-dsh-v1r3r1-repair', 'qntylab-dsh-v1r3r2-claude-repair-source']) {
      assert.ok(!code.split('NON_AUTHORITATIVE_AMBIENT_ROOTS')[0].includes(`scratch/${ambient}`),
        `${relativePath} must not read bytes from an ambient scratch root`)
    }
  }
  // the successor contract records the helper as a non-authority explicitly
  const { result } = freshHome('nc20')
  const successor = computeSuccessorContract({ homeManifest: result.identityBody, profileHome: result.destination })
  assert.equal(successor.contract.productionDshHomeMaterializer.qualificationOnlyHelperIsProductionAuthority, false)
  assert.equal(successor.contract.productionDshHomeMaterializer.isTheOnlyProductionDshHomeAuthority, true)
  // the stub the qualification path relies on is excluded from production identity
  assert.equal(successor.contract.productionDshHomeIdentity.productionStubProviderExcluded, true)
  assert.equal(successor.contract.productionDshHomeIdentity.stubPresenceBehavior, 'FAIL_CLOSED')
})

// ------------------------------------------- overlay stays out of production ---

test('qualification overlay is explicitly non-production and never a production identity', () => {
  const { home } = freshHome('overlay')
  const overlay = applyQualificationOverlay(home)
  assert.ok(existsSync(join(home, 'profiles/node_modules/@qntylab/dsh-stage-a-stub-provider')))
  const manifest = JSON.parse(readFileSync(join(home, DSH_HOME_MANIFEST_FILENAME), 'utf8'))
  assert.equal(manifest.classification, 'QUALIFICATION_OVERLAY')
  assert.equal(manifest.homeManifestDigest, null)
  expectBlocked(() => verifyHomeManifest(home), /BLOCK_HOME_MANIFEST/)
  expectBlocked(() => computeSuccessorContract({ homeManifest: manifest, profileHome: home }), /BLOCK_HOME_MANIFEST/)
  assert.ok(overlay.productionHomeManifestDigest)
})

test('successor contract does not grant live authority', () => {
  const { result } = freshHome('authority')
  const successor = computeSuccessorContract({ homeManifest: result.identityBody, profileHome: result.destination })
  assert.equal(successor.contract.LIVE_AUTHORITY, false)
  assert.equal(successor.contract.separateV0R5AuthorizationRequired, true)
  assert.equal(successor.contract.v0r5Created, false)
  assert.equal(successor.contract.predecessorQualifiedContractDigest,
    'a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be')
  assert.equal(successor.contract.compositeLauncher.digest,
    '6f212de0576127fea1dd2778a69c49a3b755a017a9d55f97f18b9057dc15c329')
})
