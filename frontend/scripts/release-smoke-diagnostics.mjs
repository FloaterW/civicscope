import assert from 'node:assert/strict';

function externalMapUrl(raw) {
  try {
    const host = new URL(raw).hostname;
    return host === 'openfreemap.org' || host.endsWith('.openfreemap.org');
  } catch { return false; }
}
function abortText(text) {
  return /^(?:net::)?ERR_ABORTED$|^NS_BINDING_ABORTED$|^Load request cancelled\.?$/i.test(text.trim());
}
function knownAbortReason(reason) {
  return typeof reason === 'string' && /^(?:navigation:|superseded:|cleanup:owned-browser-close$)/.test(reason);
}
function selectionSupersession(failure, events) {
  // Only explain the observed initial URL-selection hydration sequence. A
  // repeated URL, matching endpoint, or ERR_ABORTED alone is not sufficient.
  try {
    if (!abortText(failure.failure?.errorText ?? failure.error ?? '') || failure.method !== 'GET') return null;
    const requests = events.browserRequests ?? [];
    const initial = requests.find(item => item.id === failure.requestId);
    if (!initial || initial.method !== 'GET' || !Number.isFinite(failure.ms) ||
      !Number.isFinite(initial.createdMs) || failure.ms < initial.createdMs ||
      !Number.isInteger(initial.documentId) || initial.documentId < 1) return null;
    const source = new URL(initial.url);
    if (![events.api, events.base].filter(Boolean).some(origin => new URL(origin).origin === source.origin)) return null;
    if (!['/api/summary', '/api/compare'].includes(source.pathname)) return null;
    const documentUrl = new URL(initial.pageUrl);
    const geoid = documentUrl.searchParams.get('geoid');
    if (!geoid || documentUrl.searchParams.get('level') !== source.searchParams.get('type') ||
      documentUrl.searchParams.get('year') !== source.searchParams.get('year')) return null;
    const signature = url => JSON.stringify([...url.searchParams].filter(([key]) => key !== 'ids').sort());
    const replacement = requests.find(item => item.id > initial.id && item.documentId === initial.documentId &&
      item.method === 'GET' && new URL(item.url).origin === source.origin && new URL(item.url).pathname === source.pathname);
    if (!replacement || !Number.isFinite(replacement.createdMs) || replacement.createdMs < initial.createdMs ||
      Math.abs(replacement.createdMs - failure.ms) > 1000) return null;
    const target = new URL(replacement.url);
    if (signature(source) !== signature(target) || new URL(replacement.pageUrl).searchParams.get('geoid') !== geoid) return null;
    const explicitReplacementAbort = events.requestFailures.find(item => item.requestId === replacement.id &&
      knownAbortReason(item.expectedAbortReason) && abortText(item.failure?.errorText ?? item.error ?? ''));
    const completed = Number.isFinite(replacement.finishedMs) && replacement.finishedMs >= replacement.createdMs &&
      replacement.status >= 200 && replacement.status < 300;
    if (!completed && !explicitReplacementAbort) return null;
    const beforeIds = (source.searchParams.get('ids') ?? '').split(',').filter(Boolean);
    const afterIds = (target.searchParams.get('ids') ?? '').split(',').filter(Boolean);
    let pairedSummary;
    if (source.pathname === '/api/summary') {
      if (beforeIds.length !== 0 || afterIds.length !== 1 || afterIds[0] !== geoid) return null;
    } else {
      const expectedIds = [geoid, ...beforeIds.filter(id => id !== geoid)];
      if (JSON.stringify(afterIds) !== JSON.stringify(expectedIds)) return null;
      // Toronto is already first in the default comparison cohort, so selecting
      // it restarts an identical URL via a new comparisonIds array. Require the
      // paired summary's no-IDs -> selected-ID transition, not just a retry.
      pairedSummary = events.requestFailures.filter(item => new URL(item.url).pathname === '/api/summary')
        .map(item => selectionSupersession(item, events)).find(proof => proof &&
          proof.documentId === initial.documentId && proof.geoid === geoid &&
          signature(new URL(proof.initialUrl)) === signature(source) &&
          new URL(proof.initialUrl).origin === source.origin &&
          Math.abs(proof.initialCreatedMs - initial.createdMs) <= 1000 &&
          Math.abs(proof.replacementCreatedMs - replacement.createdMs) <= 1000);
      if (!pairedSummary) return null;
    }
    return { kind: 'url-selection-hydration', geoid, documentId: initial.documentId,
      initialRequestId: initial.id, replacementRequestId: replacement.id,
      initialUrl: initial.url, replacementUrl: replacement.url,
      initialCreatedMs: initial.createdMs, replacementCreatedMs: replacement.createdMs,
      replacementOutcome: completed ? 'completed-2xx' : explicitReplacementAbort.expectedAbortReason,
      ...(pairedSummary ? { pairedSummaryRequestId: pairedSummary.initialRequestId } : {}) };
  } catch { return null; }
}
function classifyErrors(events) {
  const analysis = { unexplainedConsoleErrors: [], unexplainedRequestFailures: [],
    externalMapConsole: [], externalMapRequests: [], expectedAborts: [], selectionSupersessions: [],
    warnings: [], applicationHttpErrors: events.httpErrors.filter(item => item.application),
    externalMapHttpErrors: events.httpErrors.filter(item => !item.application && externalMapUrl(item.url)),
    otherHttpErrors: events.httpErrors.filter(item => !item.application && !externalMapUrl(item.url)) };
  for (const failure of events.requestFailures) {
    const text = failure.failure?.errorText ?? failure.error ?? '';
    const reason = failure.expectedAbortReason;
    const knownReason = knownAbortReason(reason);
    const closedQueuedRoute = failure.phase === 'route-continue' &&
      /Target (?:page, context or browser|page, context|page|context|browser) has been closed|Target closed/.test(text);
    const selection = !knownReason ? selectionSupersession(failure, events) : null;
    if (knownReason && (abortText(text) || closedQueuedRoute)) analysis.expectedAborts.push(failure);
    else if (selection) {
      analysis.expectedAborts.push(failure);
      analysis.selectionSupersessions.push(selection);
    }
    else if (externalMapUrl(failure.url)) analysis.externalMapRequests.push(failure);
    else analysis.unexplainedRequestFailures.push(failure);
  }
  for (const message of events.console) {
    // Never hide a React/hydration exception merely because it mentions a tile URL.
    if (/hydration|hydrating|hydrated|Minified React error|react\.dev\/errors|uncaught|unhandled (?:promise|rejection)/i.test(message.text)) {
      analysis.unexplainedConsoleErrors.push(message);
      continue;
    }
    const explicitUrls = [message.location?.url, ...(message.text.match(/https?:\/\/[^\s<>"'`)]+/g) ?? [])].filter(Boolean);
    const hasMapUrl = explicitUrls.some(externalMapUrl);
    const networkFailure = /Failed to (?:load|fetch)|AJAXError|NetworkError|net::ERR_|NS_BINDING_ABORTED|Load request cancelled|HTTP (?:error )?[45]\d\d/i.test(message.text);
    if (hasMapUrl && networkFailure) { analysis.externalMapConsole.push(message); continue; }
    const correlatedAbort = /ERR_ABORTED|NS_BINDING_ABORTED|Load request cancelled/i.test(message.text) &&
      analysis.expectedAborts.some(failure => explicitUrls.includes(failure.url));
    if (correlatedAbort) continue;
    if (message.type === 'error') analysis.unexplainedConsoleErrors.push(message);
    else analysis.warnings.push(message);
  }
  analysis.blockingCount = analysis.unexplainedConsoleErrors.length + analysis.unexplainedRequestFailures.length +
    analysis.applicationHttpErrors.length + analysis.otherHttpErrors.length + events.pageErrors.length +
    events.blockedWrites.length + events.apiResponses.filter(item => item.status >= 400).length +
    (events.closeError ? 1 : 0) + (events.apiDisposeError ? 1 : 0) + (events.unexpectedApiOrigins?.length ?? 0);
  return analysis;
}
function verifyClassifierOffline() {
  const empty = () => ({ api: 'https://civicscope.onrender.com', base: 'https://civicscope-gold.vercel.app',
    httpErrors: [], requestFailures: [], console: [], pageErrors: [], blockedWrites: [], apiResponses: [], browserRequests: [] });
  const error = text => ({ type: 'error', text, location: { url: 'https://civicscope-gold.vercel.app/_next/app.js' } });
  const cases = [
    [{ ...empty(), console: [error('Hydration failed: the initial UI does not match')] }, 1],
    [{ ...empty(), console: [error('Unexpected application failure')] }, 1],
    [{ ...empty(), console: [error('Failed to fetch https://tiles.openfreemap.org/planet/0/0/0.pbf')] }, 0],
    [{ ...empty(), console: [error('Hydration failed after Failed to fetch https://tiles.openfreemap.org/0.pbf')] }, 1],
    [{ ...empty(), console: [error('Failed to fetch')] }, 1],
    [{ ...empty(), requestFailures: [{ url: 'https://civicscope.onrender.com/api/map-data', failure: { errorText: 'net::ERR_FAILED' }, expectedAbortReason: 'navigation:test' }] }, 1],
    [{ ...empty(), requestFailures: [{ url: 'https://civicscope.onrender.com/api/map-data', failure: { errorText: 'net::ERR_ABORTED' } }] }, 1],
    [{ ...empty(), requestFailures: [{ url: 'https://civicscope.onrender.com/api/map-data', failure: { errorText: 'net::ERR_ABORTED' }, expectedAbortReason: 'superseded:data-year:2024' }] }, 0],
    [{ ...empty(), requestFailures: [{ url: 'https://tiles.openfreemap.org/0.pbf', failure: { errorText: 'net::ERR_FAILED' } }] }, 0],
    [{ ...empty(), requestFailures: [{ url: 'https://unknown.example/0.pbf', failure: { errorText: 'net::ERR_FAILED' } }] }, 1]
  ];
  const hydration = (level = 'census_tract', geoid = '5350400.16', year = '2025') => {
    const events = empty();
    const defaults = level === 'municipality' ? ['3520005', '3521005', '3521010', '3519036', '3519028'] : [];
    const pageUrl = `${events.base}/?level=${level}&year=${year}&geoid=${geoid}`;
    const make = (id, endpoint, ids, createdMs, completed = false) => ({ id, documentId: 1, createdMs,
      method: 'GET', pageUrl,
      url: `${events.api}/api/${endpoint}?type=${level}&year=${year}&data_revision=test${ids.length ? `&ids=${ids.join(',')}` : ''}`,
      ...(completed ? { status: 200, finishedMs: 1040 } : {}) });
    events.browserRequests = [make(1, 'summary', [], 1000), make(2, 'compare', defaults, 1001),
      make(3, 'summary', [geoid], 1010, true), make(4, 'compare', [geoid, ...defaults.filter(id => id !== geoid)], 1011, true)];
    events.requestFailures = events.browserRequests.slice(0, 2).map(request => ({ requestId: request.id,
      url: request.url, method: 'GET', ms: 1012, failure: { errorText: 'net::ERR_ABORTED' } }));
    return events;
  };
  const changed = action => { const events = hydration(); action(events); return events; };
  cases.push(
    [hydration(), 0],
    [hydration('municipality', '3520005', '2018'), 0],
    [changed(events => { events.requestFailures = events.requestFailures.slice(1); }), 1],
    [changed(events => { events.requestFailures[0].failure.errorText = 'net::ERR_FAILED'; }), 2],
    [changed(events => { events.browserRequests[2].status = 500; }), 2],
    [changed(events => { delete events.browserRequests[2].finishedMs; }), 2],
    [changed(events => { events.browserRequests[2].documentId = 2; }), 2],
    [changed(events => { events.browserRequests[2].createdMs = 5000; }), 2],
    [changed(events => { events.requestFailures.forEach(failure => { failure.ms = 61000; }); }), 2],
    [changed(events => { events.browserRequests[2].createdMs = NaN; }), 2],
    [changed(events => { events.browserRequests[2].finishedMs = 900; }), 2],
    [changed(events => { events.browserRequests[2].url = events.browserRequests[2].url.replace('year=2025', 'year=2024'); }), 2],
    [changed(events => { events.browserRequests[2].url = events.browserRequests[2].url.replace('ids=5350400.16', 'ids=another'); }), 2],
    [changed(events => { events.browserRequests[0].pageUrl = `${events.base}/?level=census_tract&year=2025`; }), 2],
    [changed(events => { events.api = 'https://another.example'; }), 2],
    [changed(events => {
      delete events.browserRequests[2].finishedMs;
      events.requestFailures.push({ requestId: 3, url: events.browserRequests[2].url, method: 'GET', ms: 1020,
        failure: { errorText: 'net::ERR_ABORTED' }, expectedAbortReason: 'superseded:data-year:2024' });
    }), 0]
  );
  const unpairedToronto = hydration('municipality', '3520005', '2018');
  unpairedToronto.requestFailures = unpairedToronto.requestFailures.slice(1);
  cases.push([unpairedToronto, 1]);
  for (const [events, blocking] of cases) {
    const raw = JSON.stringify(events);
    assert.equal(classifyErrors(events).blockingCount, blocking);
    assert.equal(JSON.stringify(events), raw, 'Classification must not mutate raw events');
  }
  return cases.length;
}

export { externalMapUrl, classifyErrors, verifyClassifierOffline };
