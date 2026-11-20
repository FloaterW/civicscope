import assert from 'node:assert/strict';

const SHA = /^[0-9a-f]{40}$/i;
const allowed = new Set(['base', 'api', 'expected-frontend-sha', 'expected-backend-sha', 'output', 'pace-ms', 'wait-for-release-seconds']);
const modes = new Set(['--run', '--check', '--help']);

export function parseOptions(args) {
  const values = {};
  const flags = new Set();
  for (const arg of args) {
    if (modes.has(arg)) {
      assert(!flags.has(arg), `Duplicate option ${arg}`);
      flags.add(arg);
      continue;
    }
    const match = /^--([^=]+)=(.+)$/.exec(arg);
    assert(match && allowed.has(match[1]), 'Unknown, malformed or empty option');
    assert(!(match[1] in values), `Duplicate option --${match[1]}`);
    values[match[1]] = match[2];
  }
  assert(flags.size <= 1, 'Select exactly one mode');
  if (!flags.size || flags.has('--help')) return { mode: 'help' };
  if (flags.has('--check')) return { mode: 'check' };
  const origins = {};
  for (const name of ['base', 'api']) {
    assert(values[name], `--${name} is required`);
    let url;
    try { url = new URL(values[name]); }
    catch { throw new Error(`--${name} must be a valid origin`); }
    const local = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
    assert(url.protocol === 'https:' || (url.protocol === 'http:' && local), 'Use HTTPS, except for local test services');
    assert(!url.username && !url.password && url.pathname === '/' && !url.search && !url.hash, 'URLs must be credential-free origins');
    origins[name] = url;
  }
  for (const name of ['expected-frontend-sha', 'expected-backend-sha']) {
    assert(values[name]?.length === 40 && SHA.test(values[name]), `--${name} must be a full Git SHA`);
  }
  const paceMs = Number(values['pace-ms'] ?? 3500);
  assert(Number.isInteger(paceMs) && paceMs >= 0 && paceMs <= 60000, 'Invalid pacing interval');
  const localOnly = Object.values(origins).every(url => ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname));
  assert(localOnly || paceMs >= 3500, 'Public checks require at least 3500ms between API starts');
  const waitSeconds = Number(values['wait-for-release-seconds'] ?? 0);
  assert(Number.isInteger(waitSeconds) && waitSeconds >= 0 && waitSeconds <= 1800, 'Release wait must be 0–1800 seconds');
  return { mode: 'run', ...origins, frontendSha: values['expected-frontend-sha'].toLowerCase(),
    backendSha: values['expected-backend-sha'].toLowerCase(), output: values.output, paceMs, waitSeconds };
}

export function matchesRelease(frontend, backend, expected) {
  return frontend?.httpStatus === 200 && frontend.service === 'civicscope-frontend' && frontend.commit === expected.frontendSha &&
    backend?.httpStatus === 200 && backend.service === 'civicscope-api' && backend.commit === expected.backendSha &&
    backend.status === 'ok' && backend.database === 'ok';
}

export function classifyApiTarget(raw, { base, api }) {
  const url = new URL(raw);
  if (!url.pathname.startsWith('/api/') && url.pathname !== '/health') return 'other';
  const core = /^\/api\/(?:map-data|summary|compare|metrics|geographies|data-status|transit-routes)(?:\/|$)/.test(url.pathname);
  if (core && url.origin !== api.origin) return 'unexpected-core-origin';
  if (![base.origin, api.origin].includes(url.origin)) return 'unexpected-api-origin';
  return 'allowed';
}

export function isOptionalTelemetryScript(raw, base, method) {
  const url = new URL(raw);
  return method === 'GET' && url.origin === base.origin &&
    ['/_vercel/insights/script.js', '/_vercel/speed-insights/script.js'].includes(url.pathname);
}
