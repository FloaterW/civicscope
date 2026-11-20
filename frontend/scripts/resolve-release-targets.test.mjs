import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { gitCommand, observeIdentity, resolveTarget, SERVICES } from './resolve-release-targets.mjs';

const temporaryRoot = fs.realpathSync(os.tmpdir());
const directory = fs.mkdtempSync(path.join(temporaryRoot, 'civicscope-release-targets-'));
after(() => {
  const resolved = fs.realpathSync(directory);
  assert.equal(path.dirname(resolved), temporaryRoot, 'Cleanup must stay within the intended temp directory');
  assert(path.basename(resolved).startsWith('civicscope-release-targets-'), 'Unexpected cleanup target');
  fs.rmSync(resolved, { recursive: true, force: true });
});
const git = (...args) => execFileSync('git', args, { cwd: directory, encoding: 'utf8', windowsHide: true }).trim();
git('init', '--quiet');
git('config', 'user.name', 'Release contract test');
git('config', 'user.email', 'release-test@example.invalid');
function commit(file, value) {
  const location = path.join(directory, file);
  fs.mkdirSync(path.dirname(location), { recursive: true });
  fs.writeFileSync(location, value);
  git('add', '--', file);
  git('commit', '--quiet', '-m', 'fixture');
  return git('rev-parse', 'HEAD');
}
commit('backend/app.py', 'backend v1');
commit('render.yaml', 'rootDir: backend');
const baseline = commit('frontend/app.ts', 'frontend v1');
const frontendOnly = commit('frontend/app.ts', 'frontend v2');
const backendOnly = commit('backend/app.py', 'backend v2');
const renderChanged = commit('render.yaml', 'rootDir: changed');
const rootBuildChanged = commit('package.json', '{"name":"root-build-config"}');
const attributesChanged = commit('.gitattributes', '*.py eol=lf');
const submoduleConfigChanged = commit('.gitmodules', '[submodule "external"]\npath = external\nurl = https://example.invalid/external.git\n');
git('checkout', '--quiet', '--detach', baseline);
const sibling = commit('README.md', 'side branch with equivalent backend');
git('checkout', '--quiet', '--detach', submoduleConfigChanged);
const valid = commit => ({ valid: true, httpStatus: 200, commit });
const resolve = (name, observed, target) => resolveTarget(name, observed, target, gitCommand, directory);

test('current healthy revision remains an exact current target', () => {
  const result = resolve('backend', valid(baseline), baseline);
  assert.equal(result.expectedSha, baseline);
  assert.equal(result.reason, 'current-main');
});

test('frontend-only changes permit the unchanged ancestor backend with proof', () => {
  const result = resolve('backend', valid(baseline), frontendOnly);
  assert.equal(result.expectedSha, baseline);
  assert.equal(result.reason, 'equivalent-service-tree');
  assert.equal(result.ancestor, true);
  assert.equal(result.unchangedServiceTree, true);
  assert.deepEqual(result.comparedPaths, ['backend', 'render.yaml', '.gitattributes', '.gitmodules']);
  assert.equal(resolve('frontend', valid(baseline), frontendOnly).expectedSha, frontendOnly);
});

test('backend changes require new backend but allow an equivalent frontend ancestor', () => {
  assert.equal(resolve('backend', valid(frontendOnly), backendOnly).reason, 'service-tree-changed');
  assert.equal(resolve('backend', valid(frontendOnly), backendOnly).expectedSha, backendOnly);
  assert.equal(resolve('frontend', valid(frontendOnly), backendOnly).expectedSha, frontendOnly);
});

test('deployment configuration changes invalidate backend equivalence', () => {
  assert.equal(resolve('backend', valid(backendOnly), renderChanged).expectedSha, renderChanged);
  assert.equal(resolve('backend', valid(backendOnly), renderChanged).reason, 'service-tree-changed');
});

test('a sibling commit with the same service content cannot pass as an ancestor', () => {
  const result = resolve('backend', valid(sibling), frontendOnly);
  assert.equal(result.expectedSha, frontendOnly);
  assert.equal(result.reason, 'not-an-ancestor');
});

test('missing, malformed, unhealthy and unknown identities require target main', () => {
  for (const observed of [null, {}, { valid: false, commit: baseline }, valid('main'), valid('a'.repeat(40) + '\n')]) {
    assert.equal(resolve('backend', observed, frontendOnly).expectedSha, frontendOnly);
  }
  const unknown = resolve('backend', valid('f'.repeat(40)), frontendOnly);
  assert.equal(unknown.expectedSha, frontendOnly);
  assert.equal(unknown.reason, 'observed-commit-unavailable');
});

test('Git errors never authorize an older target', () => {
  for (const failedCommand of ['merge-base', 'diff']) {
    const failingGit = args => args[0] === failedCommand ? 128 : gitCommand(args, directory);
    const result = resolveTarget('backend', valid(baseline), frontendOnly, failingGit, directory);
    assert.equal(result.expectedSha, frontendOnly);
    assert.equal(result.reason, 'git-verification-failed');
  }
  assert.throws(() => resolveTarget('backend', valid(baseline), frontendOnly, () => -1), /Target commit/);
  assert.throws(() => resolve('backend', valid(baseline), 'main'), /full target/);
});

test('fixed public identity requests are anonymous, bounded and forbid redirects', async () => {
  for (const name of Object.keys(SERVICES)) {
    const result = await observeIdentity(name, async (url, options) => {
      assert.equal(url, SERVICES[name].url);
      assert.equal(options.method, 'GET');
      assert.equal(options.redirect, 'error');
      assert.equal(options.credentials, 'omit');
      assert.equal(options.cache, 'no-store');
      assert(options.signal instanceof AbortSignal);
      assert.deepEqual(options.headers, { 'Cache-Control': 'no-cache' });
      return new Response(JSON.stringify({ service: SERVICES[name].service, commit: baseline, status: 'ok', database: 'ok' }));
    });
    assert.equal(result.valid, true);
    assert.equal(result.commit, baseline);
  }
  await assert.rejects(() => observeIdentity('https://other.example'), /Unknown release service/);
});

test('HTTP failures, invalid identity, redirects and oversized bodies never authorize old code', async () => {
  const responses = [
    () => new Response('', { status: 302, headers: { Location: 'https://other.example' } }),
    () => new Response('', { status: 503 }),
    () => new Response(JSON.stringify({ service: 'wrong', commit: baseline, status: 'ok', database: 'ok' })),
    () => new Response(JSON.stringify({ service: 'civicscope-api', commit: baseline, status: 'degraded', database: 'unavailable' })),
    () => new Response(JSON.stringify({ service: 'civicscope-api', commit: 'private-value', status: 'ok', database: 'ok' })),
    () => new Response('x'.repeat(16385)),
    () => { throw new Error('private network detail'); },
  ];
  for (const response of responses) {
    const observed = await observeIdentity('backend', async () => response());
    assert.equal(observed.valid, false);
    assert.equal(resolve('backend', observed, frontendOnly).expectedSha, frontendOnly);
    assert(!JSON.stringify(observed).includes('private'));
  }
});

test('frontend root build configuration changes invalidate equivalence', () => {
  const result = resolve('frontend', valid(renderChanged), rootBuildChanged);
  assert.equal(result.expectedSha, rootBuildChanged);
  assert.equal(result.reason, 'service-tree-changed');
});

test('workflow frontend working directory cannot hide service or root configuration changes', () => {
  const cwd = path.join(directory, 'frontend');
  for (const [name, observed, target] of [
    ['frontend', baseline, frontendOnly],
    ['backend', frontendOnly, backendOnly],
    ['backend', backendOnly, renderChanged],
    ['frontend', renderChanged, rootBuildChanged],
    ['frontend', rootBuildChanged, attributesChanged],
    ['backend', rootBuildChanged, attributesChanged],
    ['frontend', attributesChanged, submoduleConfigChanged],
    ['backend', attributesChanged, submoduleConfigChanged],
  ]) {
    const result = resolveTarget(name, valid(observed), target, gitCommand, cwd);
    assert.equal(result.expectedSha, target);
    assert.equal(result.reason, 'service-tree-changed');
  }
  assert.equal(resolveTarget('backend', valid(baseline), frontendOnly, gitCommand, cwd).expectedSha, baseline);
});
