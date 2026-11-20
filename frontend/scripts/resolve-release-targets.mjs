/** Resolve exact deployed identities only when Git proves service equivalence. */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SHA = /^[0-9a-f]{40}$/;
export const SERVICES = Object.freeze({
  frontend: Object.freeze({
    url: 'https://civicscope-gold.vercel.app/api/release',
    service: 'civicscope-frontend',
    paths: ['frontend', '.gitattributes', '.gitmodules', 'vercel.json', 'package.json', 'package-lock.json',
      'npm-shrinkwrap.json', '.npmrc', '.node-version', '.nvmrc', 'pnpm-workspace.yaml',
      'pnpm-lock.yaml', 'yarn.lock', 'turbo.json'],
  }),
  backend: Object.freeze({
    url: 'https://civicscope.onrender.com/health',
    service: 'civicscope-api',
    paths: ['backend', 'render.yaml', '.gitattributes', '.gitmodules'],
  }),
});

export function gitCommand(args, cwd) {
  const result = spawnSync('git', args, {
    cwd, encoding: 'utf8', timeout: 30000, windowsHide: true,
    env: { ...process.env, GIT_NO_REPLACE_OBJECTS: '1' },
  });
  return result.error ? -1 : result.status;
}

export async function observeIdentity(name, request = fetch) {
  assert(Object.hasOwn(SERVICES, name), 'Unknown release service');
  const service = SERVICES[name];
  try {
    const response = await request(service.url, {
      method: 'GET', redirect: 'error', credentials: 'omit', cache: 'no-store',
      signal: AbortSignal.timeout(75000), headers: { 'Cache-Control': 'no-cache' },
    });
    if (response.status !== 200) {
      await response.body?.cancel();
      return { valid: false, httpStatus: response.status, reason: 'identity-http-error' };
    }
    const reader = response.body?.getReader();
    assert(reader, 'Missing identity body');
    let body = '';
    let size = 0;
    const decoder = new TextDecoder();
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        assert(size <= 16384, 'Identity response is too large');
        body += decoder.decode(value, { stream: true });
      }
      body += decoder.decode();
    } finally {
      await reader.cancel();
    }
    const payload = JSON.parse(body);
    const commit = typeof payload?.commit === 'string' && payload.commit.length === 40 && SHA.test(payload.commit) ? payload.commit : null;
    const valid = Boolean(commit && payload.service === service.service &&
      (name !== 'backend' || (payload.status === 'ok' && payload.database === 'ok')));
    return { valid, httpStatus: 200, commit, reason: valid ? 'observed-healthy-identity' : 'invalid-identity' };
  } catch {
    // Do not retain raw bodies, URLs from redirects, or network exception text.
    return { valid: false, reason: 'identity-unavailable' };
  }
}

export function resolveTarget(name, observation, targetSha, git = gitCommand, cwd = process.cwd()) {
  assert(Object.hasOwn(SERVICES, name), 'Unknown release service');
  assert(SHA.test(targetSha) && targetSha.length === 40, 'Expected a full target Git SHA');
  assert.equal(git(['cat-file', '-e', `${targetSha}^{commit}`], cwd), 0, 'Target commit is unavailable');
  const result = { service: name, targetSha, observedSha: observation?.commit ?? null,
    expectedSha: targetSha, comparedPaths: [...SERVICES[name].paths],
    reason: 'identity-not-verified', ancestor: false, unchangedServiceTree: false };
  if (!observation?.valid || !SHA.test(observation.commit ?? '') || observation.commit.length !== 40) return result;
  const observed = observation.commit;
  if (observed === targetSha) return { ...result, reason: 'current-main', ancestor: true, unchangedServiceTree: true };
  if (git(['cat-file', '-e', `${observed}^{commit}`], cwd) !== 0) return { ...result, reason: 'observed-commit-unavailable' };
  const ancestor = git(['merge-base', '--is-ancestor', observed, targetSha], cwd);
  if (ancestor !== 0) return { ...result, reason: ancestor === 1 ? 'not-an-ancestor' : 'git-verification-failed' };
  const diff = git(['diff', '--quiet', '--no-ext-diff', '--no-textconv', '--ignore-submodules=none', observed, targetSha,
    '--', ...SERVICES[name].paths.map(value => `:(top,literal)${value}`)], cwd);
  if (diff !== 0) return { ...result, ancestor: true, reason: diff === 1 ? 'service-tree-changed' : 'git-verification-failed' };
  return { ...result, expectedSha: observed, reason: 'equivalent-service-tree', ancestor: true, unchangedServiceTree: true };
}

export async function main(args) {
  assert(args.length === 2, 'Provide --target-sha=SHA and --output=DIR');
  const options = {};
  for (const arg of args) {
    const match = /^--(target-sha|output)=(.+)$/.exec(arg);
    assert(match && !Object.hasOwn(options, match[1]), 'Invalid or duplicate resolver option');
    options[match[1]] = match[2];
  }
  assert(SHA.test(options['target-sha'] ?? '') && options['target-sha'].length === 40, 'Expected a full target Git SHA');
  assert(options.output, 'Output directory is required');
  const output = path.resolve(options.output);
  await fs.mkdir(output, { recursive: true });
  const evidence = { targetSha: options['target-sha'], observedAt: new Date().toISOString(), services: {} };
  for (const name of Object.keys(SERVICES)) {
    const observation = await observeIdentity(name);
    evidence.services[name] = { observation, ...resolveTarget(name, observation, evidence.targetSha) };
    // Keep public preflight requests and the next smoke request at least 3.5s apart.
    await new Promise(resolve => setTimeout(resolve, 3500));
  }
  await fs.writeFile(path.join(output, 'release-targets.json'), JSON.stringify(evidence, null, 2) + '\n', { flag: 'wx' });
  if (process.env.GITHUB_OUTPUT) {
    await fs.appendFile(process.env.GITHUB_OUTPUT, Object.entries(evidence.services)
      .map(([name, value]) => `${name}_sha=${value.expectedSha}\n`).join(''));
  }
  const summary = ['Resolved exact service release targets:', ...Object.entries(evidence.services)
    .map(([name, value]) => `- ${name}: ${value.expectedSha} (${value.reason}; target main ${value.targetSha}; compared ${value.comparedPaths.join(', ')})`)].join('\n');
  if (process.env.GITHUB_STEP_SUMMARY) await fs.appendFile(process.env.GITHUB_STEP_SUMMARY, summary + '\n');
  console.log(summary);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main(process.argv.slice(2));
}
