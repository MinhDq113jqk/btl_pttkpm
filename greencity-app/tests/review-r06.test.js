import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ApiError, createApiClient } from '../src/services/apiClient.js';

const reportId = '11111111-1111-4111-8111-111111111111';
const sourceId = '22222222-2222-4222-8222-222222222222';
const reportsCode = readFileSync(new URL('../src/components/SadReportsPanel.jsx', import.meta.url), 'utf8');
const linkedSources = [...reportsCode.match(/const linkedSources = new Set\(\[([^\]]+)\]/)[1].matchAll(/'([^']+)'/g)].map(match => match[1]);
const response = (payload, status = 200) => new Response(JSON.stringify(payload), {
  status, headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': 'R06-CORRELATION' },
});

test('FE-43.04 every report source opens both snapshot and live source paths', async t => {
  assert.equal(linkedSources.length, 19);
  for (const source of linkedSources) await t.test(source, async () => {
    const calls = [];
    const payload = { source, current: { id: sourceId }, links: [] };
    const client = createApiClient({ baseUrl: '/api/v1', fetchImpl: async (url, options) => {
      calls.push({ url, options }); return response(payload);
    } });
    for (const path of [`/control/reports/${reportId}/sources/${source}/${sourceId}`, `/sources/${source}/${sourceId}`]) {
      assert.deepEqual(await client.portalGet(path), payload);
      assert.equal(calls.at(-1).url, `/api/v1/portal${path}`);
      assert.equal(calls.at(-1).options.method, 'GET');
    }
    assert.equal(calls.length, 2);
  });
});

test('FE-43.04 invalid source paths are rejected before fetch', async () => {
  let calls = 0;
  const client = createApiClient({ fetchImpl: async () => { calls++; return response({}); } });
  for (const path of ['https://outside.test/sources/payments', '/sources/../payments', '/sources/./payments', '/sources/%2e%2e/payments', '/sources/payments?token=x', '/sources/payments#x', '/sources\\payments', '/sources/payments x', 'sources/payments', '/sources/PAYMENTS']) {
    await assert.rejects(client.portalGet(path), { name: 'TypeError', message: 'Invalid portal path' });
  }
  assert.equal(calls, 0);
});

test('FE-43.04 underscore paths retain query encoding, signal and session headers', async () => {
  const calls = []; const controller = new AbortController();
  const client = createApiClient({ baseUrl: '/api/v1', correlationIdFactory: () => 'R06-REQUEST', fetchImpl: async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith('/auth/login')) return response({ access_token: 'synthetic-r06-session' });
    if (url.endsWith('/auth/me')) return response({ account_id: sourceId, tenant_id: reportId, username: 'synthetic.r06', full_name: 'Người kiểm tra R06', roles: ['director'], active_site_id: reportId, allowed_sites: [{ id: reportId, code: 'R06', name: 'GreenCity R06' }] });
    return response({ current: { id: sourceId }, links: [] });
  } });
  await client.authenticate('synthetic.r06', 'synthetic-password-only');
  await client.portalGet('/sources/billing_invoices/' + sourceId, { unit_id: sourceId, keyword: 'căn 101 & phí', empty: '', unset: undefined }, { signal: controller.signal });
  const last = calls.at(-1); const url = new URL(last.url, 'http://local.test');
  assert.equal(url.searchParams.get('keyword'), 'căn 101 & phí');
  assert.equal(url.searchParams.get('unit_id'), sourceId);
  assert.equal(url.searchParams.has('empty'), false);
  assert.equal(url.searchParams.has('unset'), false);
  assert.equal(last.options.signal, controller.signal);
  assert.equal(last.options.headers.Authorization, 'Bearer synthetic-r06-session');
  assert.equal(last.options.headers['X-Correlation-ID'], 'R06-REQUEST');
});

test('FE-43.04 source API errors retain their server code and correlation', async t => {
  for (const status of [403, 404, 409, 500]) await t.test(String(status), async () => {
    const client = createApiClient({ fetchImpl: async () => response({ error: { code: 'ERR-SOURCE-' + status, message: 'Không mở được nguồn.', correlation_id: 'R06-SOURCE' } }, status) });
    await assert.rejects(client.portalGet('/sources/billing_invoices/' + sourceId), error => error instanceof ApiError && error.status === status && error.code === 'ERR-SOURCE-' + status && error.correlationId === 'R06-SOURCE');
  });
});
