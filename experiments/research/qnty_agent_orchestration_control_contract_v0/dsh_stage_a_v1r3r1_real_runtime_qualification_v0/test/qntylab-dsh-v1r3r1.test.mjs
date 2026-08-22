// Offline, no-network node:test coverage for DSH_STAGE_A_V1R3_LAUNCH_PLANE_QUALIFICATION_V0.
// Run: node --test qntylab-dsh-v1r3.test.mjs
//
// These tests exercise the launcher/materializer/mock contract logic
// directly against synthetic fixtures. They do not clone or build the real
// pinned DSH commit (no network access / no offline pnpm store in this
// environment) — see PHASE.md "Known residual scope".

import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync, chmodSync, symlinkSync, unlinkSync, realpathSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  LaunchPlaneError,
  parseLauncherArgv,
  preflightLaunch,
  spawnDsh,
} from '../launcher/qntylab-launch-dsh.mjs'
import {
  MaterializationError,
  verifySourceIdentity,
  applyCanonicalPatches,
  fingerprintExecutable,
  buildManifest,
  writeManifest,
} from '../materializer/qntylab-materialize-dsh-runtime.mjs'
import { createQualificationMock } from '../mock/qualification-openai-mock.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))

function sha256(buf) {
  return createHash('sha256').update(buf).digest('hex')
}

function scratchDir(label) {
  return mkdtempSync(join(tmpdir(), `qntylab-v1r3-${label}-`))
}

// --- fixture builder: a fake "materialized runtime" the launcher can preflight ---

function buildFakeRuntime() {
  const root = scratchDir('runtime')
  mkdirSync(join(root, 'apps/cli/lib'), { recursive: true })
  mkdirSync(join(root, 'apps/cli/lib/chunks'), { recursive: true })

  const cliPath = join(root, 'apps/cli/lib/bin.js')
  writeFileSync(
    cliPath,
    "process.stdout.write(JSON.stringify({cwd: process.cwd(), argv: process.argv.slice(2)}));\n",
  )
  const chunkPath = join(root, 'apps/cli/lib/chunks/chunk-a.js')
  writeFileSync(chunkPath, '// chunk\n')

  // Fake executables: real files with distinguishable content so fingerprint
  // mismatch is easy to construct. We use process.execPath (real node) as the
  // "node executable" so spawnDsh can genuinely run the fake CLI script.
  const nodeExecutable = process.execPath
  const pythonExecutable = join(root, 'bin/fake-python')
  const codexExecutable = join(root, 'bin/fake-codex')
  const claudeExecutable = join(root, 'bin/fake-claude')
  mkdirSync(join(root, 'bin'), { recursive: true })
  for (const [p, content] of [
    [pythonExecutable, '#!/bin/sh\necho fake-python\n'],
    [codexExecutable, '#!/bin/sh\necho fake-codex\n'],
    [claudeExecutable, '#!/bin/sh\necho fake-claude\n'],
  ]) {
    writeFileSync(p, content)
    chmodSync(p, 0o755)
  }

  const fingerprints = {
    nodeExecutable: fingerprintExecutable(nodeExecutable),
    pythonExecutable: fingerprintExecutable(pythonExecutable),
    codexExecutable: fingerprintExecutable(codexExecutable),
    claudeExecutable: fingerprintExecutable(claudeExecutable),
  }

  const manifest = buildManifest({
    sourceRoot: root,
    commit: 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
    expectedTag: 'dsh-v0.1.0-rc.7',
    packageManagerFingerprint: { packageManager: 'pnpm@9.0.0' },
    patchDigests: [],
    profileDigests: {},
    launcherDigest: sha256('launcher'),
    builtCliRelativePath: 'apps/cli/lib/bin.js',
    workspaceBundledChunkRelativePaths: ['apps/cli/lib/chunks/chunk-a.js'],
    executableFingerprints: {
      nodeExecutable: fingerprints.nodeExecutable.digest,
      pythonExecutable: fingerprints.pythonExecutable.digest,
      codexExecutable: fingerprints.codexExecutable.digest,
      claudeExecutable: fingerprints.claudeExecutable.digest,
    },
  })

  const manifestPath = join(root, 'runtime_manifest.json')
  writeManifest(manifestPath, manifest)

  return { root, manifestPath, nodeExecutable, pythonExecutable, codexExecutable, claudeExecutable, cliPath }
}

function baseLauncherArgs(rt, workspace) {
  return {
    runtimeManifest: rt.manifestPath,
    workspace,
    dshHome: join(workspace, '..', 'dsh-home'),
    profile: 'headless', // a bare DSH profile name, resolved under --dsh-home (real pinned CLI contract; see launcher's V1R3R1 correction comment)
    controllerState: join(workspace, '..', 'controller.json'),
    nodeExecutable: rt.nodeExecutable,
    pythonExecutable: rt.pythonExecutable,
    codexExecutable: rt.codexExecutable,
    claudeExecutable: rt.claudeExecutable,
  }
}

test('parseLauncherArgv rejects unrecognized flags and dangling values', () => {
  assert.throws(() => parseLauncherArgv(['--bogus', 'x']), LaunchPlaneError)
  assert.throws(() => parseLauncherArgv(['--workspace']), LaunchPlaneError)
})

test('preflightLaunch: happy path resolves manifest, fingerprints, and cli identity', () => {
  const rt = buildFakeRuntime()
  const workspace = scratchDir('workspace')
  const args = baseLauncherArgs(rt, workspace)
  const result = preflightLaunch(args)
  assert.equal(result.manifestRoot, realpathSync(rt.root))
  assert.equal(result.cliDigest, sha256(Buffer.from(
    "process.stdout.write(JSON.stringify({cwd: process.cwd(), argv: process.argv.slice(2)}));\n",
  )))
})

test('preflightLaunch: FAIL_WORKSPACE_ISOLATION when --workspace is inside a forbidden root', () => {
  const rt = buildFakeRuntime()
  const forbiddenRoot = scratchDir('qntylab-root')
  const workspace = join(forbiddenRoot, 'nested', 'fixture')
  mkdirSync(workspace, { recursive: true })
  const args = baseLauncherArgs(rt, workspace)
  assert.throws(
    () => preflightLaunch(args, { forbiddenRoots: [forbiddenRoot] }),
    err => err instanceof LaunchPlaneError && err.code === 'FAIL_WORKSPACE_ISOLATION',
  )
})

test('preflightLaunch: FAIL_WORKSPACE_ISOLATION when --workspace is symlink-equivalent to a forbidden root', () => {
  const rt = buildFakeRuntime()
  const forbiddenRoot = scratchDir('qntylab-root-2')
  const linkParent = scratchDir('link-parent')
  const symlinkedWorkspace = join(linkParent, 'alias')
  symlinkSync(forbiddenRoot, symlinkedWorkspace)
  const args = baseLauncherArgs(rt, symlinkedWorkspace)
  assert.throws(
    () => preflightLaunch(args, { forbiddenRoots: [forbiddenRoot] }),
    err => err instanceof LaunchPlaneError && err.code === 'FAIL_WORKSPACE_ISOLATION',
  )
})

test('preflightLaunch: --workspace inside the materialization root is always rejected', () => {
  const rt = buildFakeRuntime()
  const workspace = join(rt.root, 'nested-workspace')
  mkdirSync(workspace, { recursive: true })
  const args = baseLauncherArgs(rt, workspace)
  assert.throws(
    () => preflightLaunch(args),
    err => err instanceof LaunchPlaneError && err.code === 'FAIL_WORKSPACE_ISOLATION',
  )
})

test('preflightLaunch: BLOCK_EXECUTABLE_IDENTITY on fingerprint mismatch (altered/decoy binary)', () => {
  const rt = buildFakeRuntime()
  const workspace = scratchDir('workspace')
  // Mutate the recorded python executable after manifest creation, simulating
  // a decoy/altered binary at the same absolute path.
  writeFileSync(rt.pythonExecutable, '#!/bin/sh\necho decoy\n')
  const args = baseLauncherArgs(rt, workspace)
  assert.throws(
    () => preflightLaunch(args),
    err => err instanceof LaunchPlaneError && err.code === 'BLOCK_EXECUTABLE_IDENTITY',
  )
})

test('preflightLaunch: missing required flag raises BLOCK_LAUNCH_ARGV', () => {
  const rt = buildFakeRuntime()
  const workspace = scratchDir('workspace')
  const args = baseLauncherArgs(rt, workspace)
  delete args.dshHome
  assert.throws(
    () => preflightLaunch(args),
    err => err instanceof LaunchPlaneError && err.code === 'BLOCK_LAUNCH_ARGV',
  )
})

test('preflightLaunch: BLOCK_RUNTIME_IDENTITY when manifest chunk resolves outside materialization root', () => {
  const rt = buildFakeRuntime()
  const workspace = scratchDir('workspace')
  const outside = scratchDir('outside-chunk')
  const outsideChunk = join(outside, 'chunk-b.js')
  writeFileSync(outsideChunk, '// escaped chunk\n')
  const manifestText = JSON.parse(execFileSync('cat', [rt.manifestPath], { encoding: 'utf8' }))
  manifestText.workspaceBundledChunks['escaped'] = outsideChunk
  writeFileSync(rt.manifestPath, `${JSON.stringify(manifestText, null, 2)}\n`)
  const args = baseLauncherArgs(rt, workspace)
  assert.throws(
    () => preflightLaunch(args),
    err => err instanceof LaunchPlaneError && err.code === 'BLOCK_RUNTIME_IDENTITY',
  )
})

test('preflightLaunch: FAIL_WORKSPACE_ISOLATION when workspace leaf does not exist yet but an ancestor is symlinked into a forbidden root (regression for hostile-review Critical #1)', () => {
  const rt = buildFakeRuntime()
  const forbiddenRoot = scratchDir('qntylab-root-3')
  const linkParent = scratchDir('link-parent-2')
  const aliasedAncestor = join(linkParent, 'alias')
  symlinkSync(forbiddenRoot, aliasedAncestor)
  // The leaf itself is never created — this is the documented common case
  // ("--workspace ... need not exist yet"), and is exactly the case a
  // lexical-only resolve() would get wrong.
  const workspace = join(aliasedAncestor, 'disposable-fixture-not-yet-created')
  const args = baseLauncherArgs(rt, workspace)
  assert.throws(
    () => preflightLaunch(args, { forbiddenRoots: [forbiddenRoot] }),
    err => err instanceof LaunchPlaneError && err.code === 'FAIL_WORKSPACE_ISOLATION',
  )
})

test('preflightLaunch: BLOCK_RUNTIME_IDENTITY when manifest omits builtCliDigest (regression for hostile-review High #4)', () => {
  const rt = buildFakeRuntime()
  const workspace = scratchDir('workspace')
  const manifest = JSON.parse(execFileSync('cat', [rt.manifestPath], { encoding: 'utf8' }))
  delete manifest.builtCliDigest
  writeFileSync(rt.manifestPath, `${JSON.stringify(manifest, null, 2)}\n`)
  const args = baseLauncherArgs(rt, workspace)
  assert.throws(
    () => preflightLaunch(args),
    err => err instanceof LaunchPlaneError && err.code === 'BLOCK_RUNTIME_IDENTITY',
  )
})

test('spawnDsh: executes the preflight-resolved realpath, not a post-preflight-swapped symlink target (regression for hostile-review High #2)', async () => {
  const rt = buildFakeRuntime()
  const workspace = scratchDir('workspace')

  // Point nodeExecutable at a symlink to the real node binary.
  const symlinkDir = scratchDir('node-symlink')
  const nodeSymlink = join(symlinkDir, 'node')
  symlinkSync(rt.nodeExecutable, nodeSymlink)
  const args = { ...baseLauncherArgs(rt, workspace), nodeExecutable: nodeSymlink }
  const preflightResult = preflightLaunch(args)
  assert.equal(preflightResult.fingerprints.nodeExecutable.resolvedPath, realpathSync(rt.nodeExecutable))

  // Simulate a TOCTOU swap: after preflight approved the symlink's target,
  // repoint the symlink at a different, non-approved executable.
  const decoyExecutable = join(symlinkDir, 'decoy')
  writeFileSync(decoyExecutable, '#!/bin/sh\necho decoy-ran\n')
  chmodSync(decoyExecutable, 0o755)
  unlinkSync(nodeSymlink)
  symlinkSync(decoyExecutable, nodeSymlink)

  const child = spawnDsh(args, preflightResult, { stdio: ['ignore', 'pipe', 'pipe'] })
  const out = await new Promise((resolve, reject) => {
    let buf = ''
    child.stdout.on('data', d => { buf += d })
    child.on('error', reject)
    child.on('exit', () => resolve(buf))
  })
  // Must have run the real (fingerprinted) node, executing the fake CLI
  // script and printing JSON — not "decoy-ran" from the swapped-in binary.
  const parsed = JSON.parse(out)
  assert.equal(parsed.cwd, realpathSync(workspace))
})

test('spawnDsh: propagates fingerprint-verified codex/claude executable paths into the child env', () => {
  const rt = buildFakeRuntime()
  const workspace = scratchDir('workspace')
  const args = baseLauncherArgs(rt, workspace)
  const preflightResult = preflightLaunch(args)
  assert.equal(preflightResult.fingerprints.codexExecutable.resolvedPath, realpathSync(rt.codexExecutable))
  assert.equal(preflightResult.fingerprints.claudeExecutable.resolvedPath, realpathSync(rt.claudeExecutable))
})

test('spawnDsh: caller-cwd irrelevance — identical launch produces identical child cwd from four different caller cwds', async () => {
  const rt = buildFakeRuntime()
  const workspace = scratchDir('workspace')
  const args = baseLauncherArgs(rt, workspace)
  const preflightResult = preflightLaunch(args)

  const callerCwds = [tmpdir(), rt.root, workspace, process.cwd()]
  const observedCwds = []
  for (const callerCwd of callerCwds) {
    const originalCwd = process.cwd()
    process.chdir(callerCwd)
    try {
      const child = spawnDsh(args, preflightResult, { stdio: ['ignore', 'pipe', 'pipe'] })
      const out = await new Promise((resolve, reject) => {
        let buf = ''
        child.stdout.on('data', d => { buf += d })
        child.on('error', reject)
        child.on('exit', () => resolve(buf))
      })
      observedCwds.push(JSON.parse(out).cwd)
    } finally {
      process.chdir(originalCwd)
    }
  }
  const workspaceReal = realpathSync(workspace)
  for (const cwd of observedCwds) assert.equal(cwd, workspaceReal)
  assert.equal(new Set(observedCwds).size, 1)
})

// --- materializer ---

function initGitRepo(dir) {
  execFileSync('git', ['init', '-q'], { cwd: dir })
  execFileSync('git', ['config', 'user.email', 'test@example.com'], { cwd: dir })
  execFileSync('git', ['config', 'user.name', 'Test'], { cwd: dir })
}

test('verifySourceIdentity: accepts matching commit/tag, rejects mismatch', () => {
  const dir = scratchDir('src')
  initGitRepo(dir)
  writeFileSync(join(dir, 'package.json'), '{"name":"fake-dsh"}\n')
  execFileSync('git', ['add', '.'], { cwd: dir })
  execFileSync('git', ['commit', '-q', '-m', 'init'], { cwd: dir })
  execFileSync('git', ['tag', 'dsh-v0.1.0-rc.7'], { cwd: dir })
  const head = execFileSync('git', ['-C', dir, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()

  const ok = verifySourceIdentity(dir, { expectedCommit: head, expectedTag: 'dsh-v0.1.0-rc.7' })
  assert.equal(ok.commit, head)

  assert.throws(
    () => verifySourceIdentity(dir, { expectedCommit: 'f'.repeat(40) }),
    err => err instanceof MaterializationError && err.code === 'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
  )
  assert.throws(
    () => verifySourceIdentity(dir, { expectedCommit: head, expectedTag: 'wrong-tag' }),
    err => err instanceof MaterializationError && err.code === 'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
  )
})

test('applyCanonicalPatches: clean apply succeeds and fails closed on a non-applying patch', () => {
  const dir = scratchDir('src2')
  initGitRepo(dir)
  writeFileSync(join(dir, 'run.ts'), "export function f() { return 1 }\n")
  execFileSync('git', ['add', '.'], { cwd: dir })
  execFileSync('git', ['commit', '-q', '-m', 'init'], { cwd: dir })

  const patchDir = scratchDir('patches')
  const goodPatch = join(patchDir, 'good.patch')
  writeFileSync(
    goodPatch,
    [
      'diff --git a/run.ts b/run.ts',
      'index 0000000..0000000 100644',
      '--- a/run.ts',
      '+++ b/run.ts',
      '@@ -1 +1 @@',
      '-export function f() { return 1 }',
      '+export function f() { return 2 }',
      '',
    ].join('\n'),
  )
  const digests = applyCanonicalPatches(dir, [goodPatch])
  assert.equal(digests.length, 1)
  const content = execFileSync('cat', [join(dir, 'run.ts')], { encoding: 'utf8' })
  assert.match(content, /return 2/)

  const badPatch = join(patchDir, 'bad.patch')
  writeFileSync(
    badPatch,
    [
      'diff --git a/run.ts b/run.ts',
      'index 0000000..0000000 100644',
      '--- a/run.ts',
      '+++ b/run.ts',
      '@@ -1 +1 @@',
      '-export function f() { return 999 }',
      '+export function f() { return 3 }',
      '',
    ].join('\n'),
  )
  assert.throws(
    () => applyCanonicalPatches(dir, [badPatch]),
    err => err instanceof MaterializationError && err.code === 'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
  )
})

test('applyCanonicalPatches: missing patch file fails closed', () => {
  const dir = scratchDir('src3')
  initGitRepo(dir)
  writeFileSync(join(dir, 'x.txt'), 'x\n')
  execFileSync('git', ['add', '.'], { cwd: dir })
  execFileSync('git', ['commit', '-q', '-m', 'init'], { cwd: dir })
  assert.throws(
    () => applyCanonicalPatches(dir, ['/nonexistent/path.patch']),
    err => err instanceof MaterializationError,
  )
})

// --- mock server ---

test('qualification mock: exactly one deterministic completion per request, no tool call, request captured', async () => {
  const mock = createQualificationMock({ model: 'gpt-5-mini' })
  const url = await mock.listen()
  try {
    const res = await fetch(`${url}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model: 'gpt-5-mini', messages: [{ role: 'user', content: 'hi' }] }),
    })
    const body = await res.json()
    assert.equal(body.choices.length, 1)
    assert.equal(body.choices[0].message.role, 'assistant')
    assert.equal(body.choices[0].finish_reason, 'stop')
    assert.equal(mock.requests.length, 1)
    assert.equal(mock.requests[0].body.model, 'gpt-5-mini')
  } finally {
    await mock.close()
  }
})

test('qualification mock: responses-protocol shape when requested', async () => {
  const mock = createQualificationMock({ wireProtocol: 'responses' })
  const url = await mock.listen()
  try {
    const res = await fetch(`${url}/v1/responses`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model: 'gpt-5-mini', input: 'hi' }),
    })
    const body = await res.json()
    assert.equal(body.status, 'completed')
    assert.equal(body.output[0].type, 'message')
  } finally {
    await mock.close()
  }
})

test('mock server is bound to loopback only', async () => {
  const mock = createQualificationMock()
  const url = await mock.listen()
  try {
    assert.match(url, /^http:\/\/127\.0\.0\.1:\d+$/)
  } finally {
    await mock.close()
  }
})
