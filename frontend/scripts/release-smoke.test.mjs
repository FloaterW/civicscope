import assert from 'node:assert/strict';
import { test } from 'node:test';
import { classifyErrors, verifyClassifierOffline } from './release-smoke-diagnostics.mjs';
import { parseOptions, matchesRelease, classifyApiTarget, isOptionalTelemetryScript } from './release-smoke-options.mjs';

const sha = 'a'.repeat(40);
const args = ['--run', '--base=https://web.example', '--api=https://api.example',
  `--expected-frontend-sha=${sha}`, `--expected-backend-sha=${sha}`];

test('running requires explicit origins and full expected identities', () => {
  assert.equal(parseOptions([]).mode, 'help');
  assert.equal(parseOptions(['--check']).mode, 'check');
  assert.throws(() => parseOptions(['--run']));
  assert.throws(() => parseOptions(args.filter(value => !value.startsWith('--expected-backend-sha='))));
  assert.throws(() => parseOptions([...args.slice(0, -1), '--expected-backend-sha=main']));
  assert.throws(() => parseOptions([...args.slice(0, -1), `--expected-backend-sha=${sha}\n`]));
  const parsed = parseOptions(args);
  assert.equal(parsed.frontendSha, sha);
  assert.equal(parsed.base.origin, 'https://web.example');
});

for (const origin of ['https://user:secret@example.test', 'https://example.test/api',
  'https://example.test/?token=private', 'https://example.test/#private', 'http://public.example', 'file:///tmp']) {
  test(`rejects non-origin or nonsecure target ${new URL(origin).protocol}`, () => {
    assert.throws(() => parseOptions(args.map(value => value.startsWith('--base=') ? `--base=${origin}` : value)));
  });
}

test('public pacing cannot be disabled; fast checks require two loopback origins', () => {
  assert.throws(() => parseOptions([...args, '--pace-ms=0']));
  assert.throws(() => parseOptions([...args.map(value => value.startsWith('--base=') ? '--base=http://127.0.0.1:3101' : value), '--pace-ms=0']));
  const local = args.map(value => value.startsWith('--base=') ? '--base=http://127.0.0.1:3101' : value.startsWith('--api=') ? '--api=http://localhost:8000' : value);
  assert.equal(parseOptions([...local, '--pace-ms=0']).paceMs, 0);
  assert.throws(() => parseOptions([...local, '--pace-ms=-1']));
});

test('options are bounded and reject ambiguity', () => {
  for (const bad of ['--unknown=true', '--output=', '--wait-for-release-seconds=1801', '--wait-for-release-seconds=NaN', '--pace-ms=3.5', '--base=https://other.example', '--check']) {
    assert.throws(() => parseOptions([...args, bad]), bad.split('=')[0]);
  }
});

test('a healthy old backend or frontend never satisfies release verification', () => {
  const frontend = { httpStatus: 200, service: 'civicscope-frontend', commit: sha };
  const backend = { httpStatus: 200, service: 'civicscope-api', commit: sha, status: 'ok', database: 'ok' };
  const expected = { frontendSha: sha, backendSha: sha };
  assert.equal(matchesRelease(frontend, backend, expected), true);
  for (const change of [{ commit: null }, { commit: 'b'.repeat(40) }, { status: 'degraded' }, { database: 'unavailable' }, { service: 'another-service' }, { httpStatus: 503 }]) {
    assert.equal(matchesRelease(frontend, { ...backend, ...change }, expected), false);
  }
  assert.equal(matchesRelease({ ...frontend, commit: 'b'.repeat(40) }, backend, expected), false);
  assert.equal(matchesRelease({ ...frontend, httpStatus: 302 }, backend, expected), false);
});

test('27 cancellation and error counterexamples remain strict and nonmutating', () => {
  assert.equal(verifyClassifierOffline(), 27);
});

test('application HTTP errors, page exceptions and attempted writes all fail', () => {
  const events = { base: 'https://web.example', api: 'https://api.example', console: [], requestFailures: [],
    httpErrors: [{ application: true, status: 500, url: 'https://api.example/api/summary' }],
    pageErrors: ['Uncaught application exception'], blockedWrites: [{ method: 'POST', url: 'https://api.example/api/data' }],
    apiResponses: [], browserRequests: [] };
  assert.equal(classifyErrors(events).blockingCount, 3);
  assert.equal(classifyErrors({ ...events, unexpectedApiOrigins: [{ origin: 'https://old.example' }] }).blockingCount, 4);
});

test('malformed URLs and option errors never echo credentials', () => {
  const secret = 'SENTINEL_PRIVATE';
  for (const value of [`--base=https://user:${secret}@[bad`, `--${secret}`]) {
    const input = value.startsWith('--base=') ? args.map(arg => arg.startsWith('--base=') ? value : arg) : [...args, value];
    assert.throws(() => parseOptions(input), error => !String(error.stack).includes(secret) && !JSON.stringify(error).includes(secret));
  }
});

test('browser API traffic must use the verified API origin, including redirected targets', () => {
  const options = parseOptions(args);
  assert.equal(classifyApiTarget('https://api.example/api/map-data', options), 'allowed');
  assert.equal(classifyApiTarget('https://web.example/api/trreb', options), 'allowed');
  assert.equal(classifyApiTarget('https://web.example/api/release', options), 'allowed');
  assert.equal(classifyApiTarget('https://web.example/api/summary', options), 'unexpected-core-origin');
  assert.equal(classifyApiTarget('https://old.example/api/map-data', options), 'unexpected-core-origin');
  assert.equal(classifyApiTarget('https://old.example/api/trreb', options), 'unexpected-api-origin');
  assert.equal(classifyApiTarget('https://old.example/health', options), 'unexpected-api-origin');
  assert.equal(classifyApiTarget('https://tiles.example/style.json', options), 'other');
});

test('only two same-origin telemetry scripts are excluded from read-only verification', () => {
  const base = new URL('https://web.example');
  for (const path of ['/_vercel/insights/script.js', '/_vercel/speed-insights/script.js']) {
    assert.equal(isOptionalTelemetryScript(new URL(path, base).href, base, 'GET'), true);
    assert.equal(isOptionalTelemetryScript(new URL(path, base).href, base, 'POST'), false);
    assert.equal(isOptionalTelemetryScript(new URL(path, 'https://other.example').href, base, 'GET'), false);
  }
  for (const path of ['/api/client-errors', '/api/trreb', '/_next/application.js', '/_vercel/insights/event']) {
    assert.equal(isOptionalTelemetryScript(new URL(path, base).href, base, 'GET'), false);
  }
});
