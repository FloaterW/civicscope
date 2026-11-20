/** Read-only, paced verification of an exact frontend/backend release. */
import fs from 'node:fs/promises';
import fsSync from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { externalMapUrl, classifyErrors, verifyClassifierOffline } from './release-smoke-diagnostics.mjs';
import { parseOptions, matchesRelease, classifyApiTarget, isOptionalTelemetryScript } from './release-smoke-options.mjs';

const config = parseOptions(process.argv.slice(2));
if (config.mode === 'help') {
  console.log(`CivicScope read-only release smoke
  npm run smoke:release -- --run --base=https://FRONTEND --api=https://BACKEND \
    --expected-frontend-sha=FULL_SHA --expected-backend-sha=FULL_SHA
  npm run smoke:release -- --check
Optional: --output=DIR --wait-for-release-seconds=1200
Public traffic is paced at least 3500ms apart. --pace-ms=0 is local-only.
No synthetic data, mutation requests, dependency installs, or browser downloads.
Use a new output directory per run. See docs/release-verification.md.`);
  process.exit(0);
}
if (config.mode === 'check') {
  console.log(JSON.stringify({ offline: true, classifierCasesPassed: verifyClassifierOffline() }));
  process.exit(0);
}
const directory = path.dirname(fileURLToPath(import.meta.url));
const requireProject = createRequire(path.join(directory, '../package.json'));
const playwright = requireProject('playwright');
const { expect } = requireProject('@playwright/test');
const engineName = 'chromium';
const engine = playwright[engineName];
assert(fsSync.existsSync(engine.executablePath()), 'Install the lock-matched Chromium browser first: npx playwright install chromium');
const { base, api } = config;
const output = path.resolve(config.output ?? path.join(directory, '../../output/release-smoke', new Date().toISOString().replace(/[:.]/g, '-')));
assert(!fsSync.existsSync(path.join(output, 'results.json')), 'Refusing to overwrite prior evidence; use a fresh output directory');
const results = { started: new Date().toISOString(), expectedFrontendSha: config.frontendSha, expectedBackendSha: config.backendSha, base: base.origin, api: api.origin,
  browser: engineName, output, checks: [], apiRequests: [], apiResponses: [], browserRequests: [],
  pageErrors: [], console: [], requestFailures: [], httpErrors: [], blockedWrites: [], unexpectedApiOrigins: [],
  screenshots: [], excludedTelemetryScripts: [], note: 'Requests paced; not a performance benchmark. Optional Vercel telemetry is disabled in this browser; dashboard responses are never mocked.' };
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let queue = Promise.resolve();
let lastStart = 0;
const inFlightRequests = new Set();
const expectedAbortReasons = new WeakMap();
const requestMetadata = new WeakMap();
let nextRequestId = 0;
let documentId = 0;
let browser;
let context;
let page;
let apiContext;
function isApiUrl(raw) {
  return classifyApiTarget(raw, config) !== 'other';
}
async function pace(url, channel, requestId) {
  const slot = queue.then(async () => {
    await delay(Math.max(0, config.paceMs - (Date.now() - lastStart)));
    lastStart = Date.now();
    results.apiRequests.push({ at: new Date(lastStart).toISOString(), ms: lastStart, url, channel,
      ...(requestId === undefined ? {} : { requestId }) });
  });
  queue = slot.catch(() => {});
  await slot;
}
async function checkpoint(name, action) {
  const start = Date.now();
  try {
    const details = await action();
    results.checks.push({ name, passed: true, elapsedMs: Date.now() - start, details });
    console.log(`PASS ${name}`);
    return details;
  } catch (error) {
    results.checks.push({ name, passed: false, elapsedMs: Date.now() - start, error: String(error.stack || error) });
    console.error(`FAIL ${name}: ${error.message}`);
    throw error;
  }
}
async function apiGet(params) {
  const url = new URL('/api/map-data', api);
  url.search = new URLSearchParams({ detail: 'display', ...params }).toString();
  await pace(url.href, 'direct-get');
  const response = await apiContext.get(url.href, { timeout: 90000, maxRetries: 0, maxRedirects: 0 });
  results.apiResponses.push({ at: new Date().toISOString(), channel: 'direct-get', url: url.href, status: response.status() });
  assert.equal(response.status(), 200, `Map API returned ${response.status()}`);
  return response.json();
}
function validateConstruction(payload, metric, year, status) {
  assert.equal(payload.metadata.metric, metric);
  assert.equal(payload.metadata.year, year);
  assert.equal(payload.metadata.cmhc_year, year);
  assert.equal(payload.metadata.data_quality.metric_status, status);
  assert.equal(payload.metadata.metric_catalog[metric].data_quality.metric_status, status);
  assert.match(payload.metadata.source, /Starts & Completions Survey/);
  const sourceField = metric === 'housing_starts_total' ? 'starts_source' : 'completions_source';
  const sources = {};
  assert.equal(payload.features.length, 1334);
  for (const { properties } of payload.features) {
    const cmhc = properties.cmhc_metrics;
    assert.equal(properties.value, cmhc?.[metric] ?? null);
    if (cmhc?.[metric] != null) {
      const source = cmhc[sourceField];
      assert(['official', 'estimated_parent', 'estimated'].includes(source), `Unknown count source: ${source}`);
      sources[source] = (sources[source] || 0) + 1;
    }
  }
  assert(sources.estimated > 0, 'Expected municipality allocation fallback');
  if (status === 'estimated') assert.equal(sources.official || 0, 0);
  else assert(sources.official > 0, 'Expected official observations in mixed year');
  return { metric, year, status, sources, label: payload.metadata.data_quality.label };
}
async function capture(name) {
  await page.evaluate(() => document.fonts.ready);
  const mapPanel = page.getByTestId('map-panel');
  await mapPanel.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, `${name}-viewport.png`), fullPage: false });
  await mapPanel.screenshot({ path: path.join(output, `${name}-map.png`) });
  await fs.writeFile(path.join(output, `${name}.yml`), await page.locator('body').ariaSnapshot());
  results.screenshots.push(`${name}-viewport.png`, `${name}-map.png`);
}
async function mapReady(metric, year, label, geography = 'census_tract') {
  const map = page.getByTestId('civic-map');
  await expect(map).toHaveAttribute('data-metric', metric, { timeout: 90000 });
  await expect(map).toHaveAttribute('data-geography-type', geography);
  await expect(map).toHaveAttribute('data-feature-count', geography === 'census_tract' ? '1334' : '25');
  await expect(map).toHaveAttribute('aria-busy', 'false', { timeout: 90000 });
  await expect(page.getByLabel('CMHC data year', { exact: true })).toHaveValue(String(year));
  await expect(page.getByTestId('map-panel')).toContainText(`CMHC ${year}`, { timeout: 90000 });
  await expect(page.getByTestId('map-panel').getByTestId('data-quality-badge')).toHaveText(label, { timeout: 90000 });
  await expect(page.getByTestId('detail-panel').getByTestId('data-quality-badge')).toHaveText(label);
  await page.evaluate(() => document.fonts.ready);
}
async function compactLayout(name) {
  await page.setViewportSize({ width: 320, height: 844 });
  await page.evaluate(() => document.fonts.ready);
  const layout = await page.evaluate(() => ({
    viewport: innerWidth, documentWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    badges: [...document.querySelectorAll('[data-testid="data-quality-badge"]')].map(badge => {
      const icon = badge.querySelector('svg');
      const bounds = badge.getBoundingClientRect();
      const iconBounds = icon?.getBoundingClientRect();
      return { text: badge.textContent, x: bounds.x, right: bounds.right,
        iconWidth: iconBounds?.width, iconHeight: iconBounds?.height,
        iconFlexShrink: icon ? getComputedStyle(icon).flexShrink : null };
    })
  }));
  assert.equal(layout.viewport, 320);
  assert(layout.documentWidth <= layout.clientWidth + 1, `Horizontal overflow: ${JSON.stringify(layout)}`);
  assert(layout.badges.length >= 2, 'Expected map and detail provenance badges');
  for (const badge of layout.badges) {
    assert(badge.iconWidth >= 13.5 && badge.iconHeight >= 13.5, `Collapsed badge icon: ${JSON.stringify(badge)}`);
    assert.equal(badge.iconFlexShrink, '0');
    assert(badge.x >= -1 && badge.right <= 321, `Badge exceeds viewport: ${JSON.stringify(badge)}`);
  }
  await capture(name);
  return layout;
}
function markSuperseded(reason, predicate = () => true) {
  for (const request of inFlightRequests) {
    if (['GET', 'HEAD', 'OPTIONS'].includes(request.method()) && predicate(request)) {
      expectedAbortReasons.set(request, reason);
    }
  }
}
function markDataSuperseded(reason) {
  markSuperseded(`superseded:${reason}`, request => isApiUrl(request.url()) &&
    /^\/api\/(?:map-data|summary|compare|geographies)(?:\/|$)/.test(new URL(request.url()).pathname));
}
async function instrument() {
  page.on('request', request => {
    inFlightRequests.add(request);
    const target = classifyApiTarget(request.url(), config);
    if (target.startsWith('unexpected-')) {
      const url = new URL(request.url());
      results.unexpectedApiOrigins.push({ origin: url.origin, path: url.pathname, reason: target });
    }
    if (request.isNavigationRequest() && request.frame() === page.mainFrame()) documentId += 1;
    if (isApiUrl(request.url())) {
      const createdMs = Date.now();
      const metadata = { id: ++nextRequestId, documentId, createdMs, createdAt: new Date(createdMs).toISOString(),
        url: request.url(), method: request.method(), pageUrl: page.url() };
      requestMetadata.set(request, metadata);
      results.browserRequests.push(metadata);
    }
  });
  page.on('requestfinished', request => {
    const metadata = requestMetadata.get(request);
    if (metadata) { metadata.finishedMs = Date.now(); metadata.finishedAt = new Date(metadata.finishedMs).toISOString(); }
    inFlightRequests.delete(request);
  });
  await context.route('**/*', async route => {
    const request = route.request();
    if (isOptionalTelemetryScript(request.url(), base, request.method())) {
      results.excludedTelemetryScripts.push(new URL(request.url()).pathname);
      return route.fulfill({ status: 200, contentType: 'application/javascript', body: '/* Telemetry excluded from read-only release verification. */' });
    }
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      results.blockedWrites.push({ url: request.url(), method: request.method() });
      return route.abort('blockedbyclient');
    }
    const target = classifyApiTarget(request.url(), config);
    if (target.startsWith('unexpected-')) return route.abort('blockedbyclient');
    if (target === 'other') return route.continue();
    await pace(request.url(), 'browser', requestMetadata.get(request)?.id);
    try { await route.continue(); }
    catch (error) { const ms = Date.now(); results.requestFailures.push({ at: new Date(ms).toISOString(), ms,
      requestId: requestMetadata.get(request)?.id, url: request.url(), method: request.method(), phase: 'route-continue',
      error: String(error), expectedAbortReason: expectedAbortReasons.get(request) }); }
  });
  page.on('pageerror', error => results.pageErrors.push(String(error.stack || error)));
  page.on('console', message => {
    if (['error', 'warning'].includes(message.type())) results.console.push({ type: message.type(), text: message.text().slice(0,2500), location: message.location() });
  });
  page.on('requestfailed', request => {
    const ms = Date.now();
    const metadata = requestMetadata.get(request);
    if (metadata) { metadata.failedMs = ms; metadata.failedAt = new Date(ms).toISOString(); }
    results.requestFailures.push({ at: new Date(ms).toISOString(), ms, requestId: metadata?.id,
      url: request.url(), method: request.method(), failure: request.failure(),
      expectedAbortReason: expectedAbortReasons.get(request) });
    inFlightRequests.delete(request);
  });
  page.on('response', response => {
    const url = response.url();
    const at = new Date().toISOString();
    const metadata = requestMetadata.get(response.request());
    if (metadata) { metadata.status = response.status(); metadata.responseAt = at; }
    if (isApiUrl(url)) results.apiResponses.push({ at, requestId: metadata?.id, channel: 'browser', url, status: response.status() });
    if (response.status() >= 400) results.httpErrors.push({ url, status: response.status(), application: [api.origin, base.origin].includes(new URL(url).origin) });
  });
}

async function verifyRelease(waitSeconds) {
  const deadline = Date.now() + waitSeconds * 1000;
  results.releaseObservations ??= [];
  while (true) {
    const observed = { at: new Date().toISOString() };
    for (const [service, origin, endpoint] of [['frontend', base, '/api/release'], ['backend', api, '/health']]) {
      const url = new URL(endpoint, origin);
      await pace(url.href, 'release-identity');
      try {
        const response = await apiContext.get(url.href, { timeout: 75000, maxRetries: 0, maxRedirects: 0, headers: { 'Cache-Control': 'no-cache' } });
        const data = response.status() === 200 ? await response.json() : null;
        observed[service] = { httpStatus: response.status(), service: data?.service,
          commit: /^[a-f0-9]{40}$/.test(data?.commit ?? '') ? data.commit : null,
          status: data?.status, database: data?.database };
      } catch (error) { observed[service] = { error: error.name }; }
    }
    results.releaseObservations.push(observed);
    if (matchesRelease(observed.frontend, observed.backend, config)) return observed;
    if (Date.now() >= deadline) throw new Error('Expected frontend/backend release is not healthy and ready; see releaseObservations');
    await delay(Math.min(15000, deadline - Date.now()));
  }
}

async function main() {
  await fs.mkdir(output, { recursive: true });
  apiContext = await playwright.request.newContext();
  await checkpoint('Both services serve the expected healthy release', () => verifyRelease(config.waitSeconds));
  for (const [metric, year, status] of [
    ['housing_starts_total', 2025, 'estimated'],
    ['housing_starts_total', 2024, 'mixed'],
    ['housing_completions', 2025, 'estimated']
  ]) await checkpoint(`API tract ${metric} ${year} ${status}`, async () =>
    validateConstruction(await apiGet({ metric, year: String(year), type: 'census_tract' }), metric, year, status));
  for (const [metric, year, survey] of [
    ['housing_completions', 2018, 'CMHC Starts & Completions Survey'],
    ['unabsorbed_units', 2025, 'CMHC Market Absorption Survey'],
    ['rental_universe', 2025, 'CMHC Rental Market Survey']
  ]) await checkpoint(`API municipality ${metric} ${year} source`, async () => {
    const payload = await apiGet({ metric, year: String(year), type: 'municipality' });
    assert.equal(payload.metadata.year, year);
    assert.equal(payload.metadata.data_quality.label, survey);
    assert.equal(payload.metadata.data_quality.metric_status, 'official');
    assert(payload.metadata.source.startsWith(`${survey} data `));
    assert.equal(payload.metadata.metric_catalog[metric].data_quality.label, survey);
    assert.equal(payload.features.length, 25);
    return { metric, year, source: payload.metadata.source };
  });
  browser = await engine.launch({ headless: true });
  context = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'light', serviceWorkers: 'block' });
  page = await context.newPage();
  page.setDefaultTimeout(90000);
  await instrument();
  const estimated = 'CMHC (estimated tract allocation)';
  const mixed = 'CMHC tract values (official + estimated)';
  await checkpoint('UI tract starts 2025 estimated', async () => {
    await page.goto(`${base.origin}/?level=census_tract&metric=housing_starts_total&year=2025&geoid=5350400.16`, { waitUntil: 'domcontentloaded' });
    await mapReady('housing_starts_total', 2025, estimated);
    await expect(page.getByTestId('map-panel').getByTestId('data-quality-badge').locator('svg')).toHaveClass(/lucide-triangle-alert/);
    await capture('tract-starts-2025-estimated');
  });
  await checkpoint('UI tract starts 2024 mixed and 320px layout', async () => {
    markDataSuperseded('data-year:2024');
    await page.getByLabel('CMHC data year', { exact: true }).selectOption('2024');
    await mapReady('housing_starts_total', 2024, mixed);
    return compactLayout('tract-starts-2024-mixed-320');
  });
  await checkpoint('UI tract completions 2025 estimated', async () => {
    markDataSuperseded('metric:housing-completions');
    await page.getByLabel('Map metric', { exact: true }).selectOption('housing_completions');
    markDataSuperseded('data-year:2025');
    await page.getByLabel('CMHC data year', { exact: true }).selectOption('2025');
    await mapReady('housing_completions', 2025, estimated);
    return compactLayout('tract-completions-2025-estimated-320');
  });
  await checkpoint('UI municipal 2018 completions SCSS badge', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    markSuperseded('navigation:municipality-completions-2018');
    await page.goto(`${base.origin}/?level=municipality&metric=housing_completions&year=2018&geoid=3520005`, { waitUntil: 'domcontentloaded' });
    await mapReady('housing_completions', 2018, 'CMHC Starts & Completions Survey', 'municipality');
    await capture('municipality-completions-2018-scss');
  });
  await checkpoint('UI real transit availability and Select/Clear all', async () => {
    const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/transit-routes');
    await page.getByRole('button', { name: 'Transit', exact: true }).click();
    const response = await responsePromise;
    assert.equal(response.status(), 200);
    const routes = await response.json();
    const present = [...new Set(routes.features.map(feature => feature.properties.transit_category))];
    assert(present.length > 0);
    results.transitCategories = present;
    await expect(page.getByTestId('civic-map')).toHaveAttribute('data-transit-status', 'loaded');
    const labels = { ttc_subway: 'Subway', ttc_other: 'Bus / Streetcar', go_transit: 'GO Transit', miway: 'MiWay', durham_rt: 'Durham RT', brampton: 'Brampton Transit' };
    for (const [key, label] of Object.entries(labels)) {
      const available = present.includes(key);
      const checkbox = page.getByRole('checkbox', { name: available ? label : `${label} Not in snapshot`, exact: true });
      if (available) { await expect(checkbox).toBeEnabled(); await expect(checkbox).toBeChecked(); }
      else { await expect(checkbox).toBeDisabled(); await expect(checkbox).not.toBeChecked(); }
    }
    await page.getByRole('button', { name: 'Clear all', exact: true }).click();
    await expect(page.getByTestId('civic-map')).toHaveAttribute('data-transit-visible', 'false');
    await page.getByRole('button', { name: 'Select all', exact: true }).click();
    await expect(page.getByTestId('civic-map')).toHaveAttribute('data-transit-visible', 'true');
    if (!present.includes('brampton')) await expect(page.getByRole('checkbox', { name: /Brampton Transit/ })).not.toBeChecked();
    const chosen = page.getByRole('checkbox', { name: labels[present[0]], exact: true });
    await chosen.focus();
    await chosen.press('Space');
    await expect(chosen).not.toBeChecked();
    results.transitPreferenceBefore = await page.locator('#transit-layer-panel input[type="checkbox"]').evaluateAll(inputs => inputs.map(input => ({ label: input.parentElement.textContent.trim(), checked: input.checked, disabled: input.disabled })));
    await page.locator('#transit-layer-panel').screenshot({ path: path.join(output, 'transit-real-availability.png') });
    results.screenshots.push('transit-real-availability.png');
    return { presentCategories: present, toggledOff: present[0] };
  });
  await checkpoint('UI theme/year preserve transit choice and 320px badge icons', async () => {
    markSuperseded('superseded:map-theme:dark', request => externalMapUrl(request.url()));
    await page.getByRole('button', { name: 'Dark theme', exact: true }).click();
    await expect(page.locator('html')).toHaveClass(/dark/);
    await expect(page.getByTestId('map-canvas-host')).toHaveAttribute('data-map-theme', 'dark');
    markDataSuperseded('data-year:2025');
    await page.getByLabel('CMHC data year', { exact: true }).selectOption('2025');
    await mapReady('housing_completions', 2025, 'CMHC Starts & Completions Survey', 'municipality');
    const after = await page.locator('#transit-layer-panel input[type="checkbox"]').evaluateAll(inputs => inputs.map(input => ({ label: input.parentElement.textContent.trim(), checked: input.checked, disabled: input.disabled })));
    assert.deepEqual(after, results.transitPreferenceBefore);
    if (!results.transitCategories.includes('brampton')) await expect(page.getByRole('checkbox', { name: /Brampton Transit/ })).toBeDisabled();
    const layout = await compactLayout('municipality-scss-transit-dark-320');
    await page.locator('#transit-layer-panel').screenshot({ path: path.join(output, 'transit-dark-320.png') });
    results.screenshots.push('transit-dark-320.png');
    return { transitPreferences: after, layout };
  });
  await checkpoint('UI search Escape reopens with ArrowDown and preserves refreshed selection', async () => {
    const map = page.getByTestId('civic-map');
    const panel = page.getByTestId('detail-panel');
    const search = page.getByTestId('geography-search');
    const isOakvilleSearch = raw => {
      const url = new URL(raw);
      return isApiUrl(raw) && url.pathname === '/api/geographies' &&
        url.searchParams.get('search') === 'Oakville' && url.searchParams.get('type') === 'municipality';
    };
    await expect(map).toHaveAttribute('data-geography-type', 'municipality');
    await expect(map).toHaveAttribute('data-selected-geoid', '3520005');
    await expect(panel).toContainText('Toronto');
    markSuperseded('superseded:search-query:Oakville', request => isApiUrl(request.url()) &&
      new URL(request.url()).pathname === '/api/geographies');
    await search.fill('Oakville');
    const oakville = page.getByRole('listbox').getByRole('option').filter({ hasText: '3524001' });
    await expect(oakville).toBeVisible({ timeout: 90000 });
    markSuperseded('superseded:search-escape:Oakville', request => isOakvilleSearch(request.url()));
    await search.press('Escape');
    await expect(search).toBeFocused();
    await expect(search).toHaveValue('Oakville');
    await expect(search).toHaveAttribute('aria-expanded', 'false');
    await expect(search).not.toHaveAttribute('aria-activedescendant');
    await search.press('Enter');
    await expect(page.getByRole('listbox')).toBeHidden();
    await expect(map).toHaveAttribute('data-selected-geoid', '3520005');

    const [refresh] = await Promise.all([
      page.waitForResponse(response => response.request().method() === 'GET' &&
        isOakvilleSearch(response.url()), { timeout: 90000 }),
      (async () => {
        await search.press('ArrowDown');
        await expect(oakville).toBeVisible({ timeout: 90000 });
        await expect(search).toBeFocused();
        await expect(search).toHaveAttribute('aria-activedescendant', 'search-option-3524001');
      })()
    ]);
    assert.equal(refresh.status(), 200, 'Reopened search refresh failed');
    assert.equal(await refresh.finished(), null, 'Reopened search response did not finish successfully');
    const refreshed = await refresh.json();
    assert(refreshed.items.some(item => item.geoid === '3524001'), 'Refreshed search omitted Oakville');
    // Wait for the real paced response and the following DOM frames, not a
    // fixed delay that could finish before the production refresh arrives.
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(search).toHaveAttribute('aria-expanded', 'true');
    await expect(search).toHaveAttribute('aria-activedescendant', 'search-option-3524001');
    await expect(oakville).toHaveAttribute('aria-selected', 'true');
    await search.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'search-keyboard-reopened.png'), fullPage: false });
    await fs.writeFile(path.join(output, 'search-keyboard-reopened.yml'), await page.locator('body').ariaSnapshot());
    results.screenshots.push('search-keyboard-reopened.png');

    markDataSuperseded('search-selection:Oakville');
    await search.press('Enter');
    await expect(map).toHaveAttribute('data-selected-geoid', '3524001', { timeout: 90000 });
    await expect(panel).toContainText('Oakville', { timeout: 90000 });
    await expect(search).toHaveValue('Oakville');
    await expect(search).toBeFocused();
    await expect(page.getByRole('listbox')).toBeHidden();
    await expect(page).toHaveURL(/geoid=3524001/);
    await capture('search-keyboard-selected-oakville');
    return { initialGeoid: '3520005', selectedGeoid: '3524001', query: 'Oakville',
      refresh: { url: refresh.url(), status: refresh.status(), resultCount: refreshed.items.length },
      highlightAfterRefresh: 'search-option-3524001' };
  });
  await checkpoint('UI comparison keyboard dismissal and repeated pointer exits', async () => {
    const panel = page.getByTestId('comparison-panel');
    await expect(panel.locator('tbody tr').filter({ hasText: 'Oakville' })).toHaveCount(1, { timeout: 90000 });
    const chart = panel.getByRole('application', { name: /comparison chart/ });
    const tooltip = panel.locator('.recharts-tooltip-wrapper');
    const rows = panel.locator('tbody tr');
    const first = await rows.nth(0).locator('td').first().innerText();
    const second = await rows.nth(1).locator('td').first().innerText();
    await chart.scrollIntoViewIfNeeded();
    await chart.focus();
    await expect(tooltip).toBeVisible({ timeout: 90000 });
    await expect(tooltip).toContainText(first);
    await chart.press('ArrowRight');
    await expect(tooltip).toContainText(second);
    await expect(tooltip.getByRole('status')).toHaveAttribute('aria-live', 'polite');
    await chart.press('Escape');
    await expect(tooltip).toBeHidden();
    await chart.press('Tab');
    await expect(chart).not.toBeFocused();
    for (let attempt = 0; attempt < 3; attempt++) {
      await panel.locator('.recharts-bar-rectangle').first().hover();
      await expect(tooltip).toBeVisible();
      await expect(tooltip).toContainText(first);
      await expect(tooltip.getByRole('status')).toHaveCount(0);
      await page.mouse.move(0, 0);
      await expect(tooltip).toBeHidden();
    }
    await panel.screenshot({ path: path.join(output, 'comparison-pointer-exit.png') });
    results.screenshots.push('comparison-pointer-exit.png');
    return { firstArea: first, secondArea: second, pointerExits: 3,
      note: 'Real keyboard/pointer interactions; deterministic delayed-frame race is tested locally and in CI.' };
  });
  await checkpoint('Desktop topics preserve map height and keyboard panel scroll', async () => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const panel = page.getByTestId('detail-panel');
    const map = page.getByTestId('map-panel');
    const scroll = page.getByTestId('detail-panel-scroll');
    const before = await map.boundingBox();
    assert(before && before.height > 300);
    const heights = [];
    for (const topic of ['census', 'population', 'stock', 'rental', 'construction', 'sources']) {
      const section = panel.locator(`details[data-topic="${topic}"]`);
      await expect(section).toHaveCount(1);
      if (!await section.evaluate(el => el.open)) await section.locator('summary').click();
      const after = await map.boundingBox();
      assert(Math.abs(after.height - before.height) < 1, `Map height changed when opening ${topic}`);
      assert(Math.abs((await panel.boundingBox()).height - before.height) < 1);
      heights.push({ topic, mapHeight: after.height });
    }
    assert.equal(heights.length, 6);
    assert(await scroll.evaluate(el => el.scrollHeight > el.clientHeight));
    await scroll.focus();
    await page.keyboard.press('End');
    await expect.poll(() => scroll.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    await expect(panel.getByRole('button', { name: 'Export geography data as CSV' })).toBeVisible();
    const downloadPromise = page.waitForEvent('download');
    await panel.getByRole('button', { name: 'Export geography data as CSV' }).click();
    const download = await downloadPromise;
    await download.saveAs(path.join(output, 'oakville-geography.csv'));
    const csv = await fs.readFile(path.join(output, 'oakville-geography.csv'), 'utf8');
    assert.equal(download.suggestedFilename(), 'civicscope-3524001.csv');
    assert(csv.includes('"Metric","Value","Period","Source","Method","Status"'));
    assert(csv.includes('"Housing completions","3543","Calendar year 2025","CMHC Starts & Completions Survey — municipality","Published value","official"'));
    assert(csv.includes('"Availability rate","","October 2025 survey"'), 'Missing values must remain empty');
    await scroll.evaluate(el => { el.scrollTop = 0; });
    await page.getByTestId('map-panel').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'desktop-expanded-topics.png'), fullPage: false });
    results.screenshots.push('desktop-expanded-topics.png');
    return { heights, exportFilename: download.suggestedFilename(), csvBytes: Buffer.byteLength(csv) };
  });
  await checkpoint('Live TRREB archive historical periods, reload and mobile layout', async () => {
    markSuperseded('navigation:trreb-history');
    await page.goto(`${base.origin}/?level=municipality&metric=population&geoid=3520005&resale_year=2025&resale_open=1`, { waitUntil: 'domcontentloaded' });
    const section = page.locator('details[data-topic="resale"]');
    // The global request queue intentionally adds 3.5 seconds per API call.
    // Wait for actual selected geography and archive readiness, not DOMContentLoaded.
    await expect(page.getByTestId('civic-map')).toHaveAttribute('data-selected-geoid', '3520005', { timeout: 90000 });
    await expect(section).toContainText('January–December 2025', { timeout: 90000 });
    await expect(section.locator('dl')).toHaveAttribute('aria-busy', 'false', { timeout: 90000 });
    await expect(section).toContainText('$855,000');
    await expect(section).toContainText('23,196');
    await expect(section).toContainText('Archived 2020–2025 reports; not current market quotes.');
    markDataSuperseded('resale-year:2020');
    await page.getByLabel('Report year', { exact: true }).selectOption('2020');
    await expect(section).toContainText('January–December 2020', { timeout: 90000 });
    await expect(section.locator('dl')).toHaveAttribute('aria-busy', 'false', { timeout: 90000 });
    await expect(section.getByRole('status')).not.toContainText('unavailable');
    markDataSuperseded('resale-month:January');
    await page.getByLabel('Reporting period', { exact: true }).selectOption('1');
    await expect(section).toContainText('January 2020', { timeout: 90000 });
    await expect(section.locator('dl')).toHaveAttribute('aria-busy', 'false', { timeout: 90000 });
    await expect(section).toContainText('$725,000');
    await expect(section).toContainText('1,603');
    await expect(section.getByRole('link', { name: /Market Watch/ })).toHaveAttribute('href', 'https://trreb.ca/wp-content/files/market-stats/market-watch/mw2001.pdf');
    markSuperseded('navigation:trreb-reload');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(section).toContainText('January 2020', { timeout: 90000 });
    await expect(section.locator('dl')).toHaveAttribute('aria-busy', 'false', { timeout: 90000 });
    await expect(section).toContainText('$725,000');
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await section.scrollIntoViewIfNeeded();
      await expect(section.getByText('$725,000', { exact: true })).toBeVisible();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
      await page.screenshot({ path: path.join(output, `trreb-${width}.png`), fullPage: false });
      results.screenshots.push(`trreb-${width}.png`);
    }
    // Archive completion precedes the queued summary/comparison responses after
    // reload. Preserve proof of those replacements before closing our browser.
    await expect.poll(() => results.browserRequests.filter(item => {
      const url = new URL(item.url);
      return item.documentId === documentId && ['/api/summary', '/api/compare'].includes(url.pathname) &&
        (url.searchParams.get('ids') ?? '').split(',')[0] === '3520005' &&
        item.status === 200 && Number.isFinite(item.finishedMs);
    }).length, { timeout: 90000 }).toBe(2);
    return { geography: 'Toronto', annual2025: { median: 855000, sales: 23196 }, january2020: { median: 725000, sales: 1603 }, widths: [390, 320] };
  });
  await checkpoint('Browser data came from the verified API origin', async () => {
    assert.equal(results.unexpectedApiOrigins.length, 0, 'Browser used an unverified API origin');
    const endpoints = ['/api/map-data', '/api/summary', '/api/compare'];
    for (const endpoint of endpoints) {
      assert(results.apiResponses.some(item => item.channel === 'browser' && item.status === 200 &&
        new URL(item.url).origin === api.origin && new URL(item.url).pathname === endpoint), `No verified browser response for ${endpoint}`);
    }
    return { origin: api.origin, endpoints };
  });
  await checkpoint('Release identity remains unchanged after browser checks', () => verifyRelease(0));
}
main().catch(async error => {
  results.fatal = String(error.stack || error);
  process.exitCode = 1;
  console.error(results.fatal);
  if (page && !page.isClosed()) {
    try { await page.screenshot({ path: path.join(output, 'failure-viewport.png') }); results.screenshots.push('failure-viewport.png'); }
    catch (captureError) { results.failureScreenshotError = String(captureError); }
  }
}).finally(async () => {
  markSuperseded('cleanup:owned-browser-close');
  if (browser) await browser.close().catch(error => { results.closeError = String(error); });
  if (apiContext) await apiContext.dispose().catch(error => { results.apiDisposeError = String(error); });
  await queue;
  // Include late request/console events from browser shutdown in the final gate.
  await delay(0);
  results.errorAnalysis = classifyErrors(results);
  results.checks.push({ name: 'No unexplained application/network errors after cleanup',
    passed: results.errorAnalysis.blockingCount === 0, details: { blockingCount: results.errorAnalysis.blockingCount } });
  if (results.errorAnalysis.blockingCount > 0) process.exitCode = 1;
  const starts = results.apiRequests.map(request => request.ms);
  results.maxRequestsInRollingMinute = starts.reduce((maximum, at) => Math.max(maximum, starts.filter(other => other >= at && other < at + 60000).length), 0);
  results.finished = new Date().toISOString();
  results.passed = !results.fatal && results.checks.every(check => check.passed);
  await fs.mkdir(output, { recursive: true });
  await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify({ passed: results.passed, checks: results.checks.length, apiAttempts: starts.length,
    peakRequestsPerMinute: results.maxRequestsInRollingMinute, evidence: path.join(output, 'results.json') }, null, 2));
});
