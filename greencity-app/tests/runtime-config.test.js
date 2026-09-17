import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveApiBaseUrl } from '../src/services/apiClient.js';
import { resolveDevProxyTarget } from '../vite.config.js';

test('frontend API base URL keeps same-origin proxy as the safe default', () => {
  assert.equal(resolveApiBaseUrl(undefined), '/api/v1');
  assert.equal(resolveApiBaseUrl('   '), '/api/v1');
  assert.equal(resolveApiBaseUrl('https://api.example.test/api/v1/'), 'https://api.example.test/api/v1/');
});

test('Vite proxy target is configurable but restricted to http(s)', () => {
  assert.equal(resolveDevProxyTarget({}), 'http://127.0.0.1:8000');
  assert.equal(resolveDevProxyTarget({ VITE_DEV_API_PROXY_TARGET: 'http://backend.local:9000' }), 'http://backend.local:9000');
  assert.throws(
    () => resolveDevProxyTarget({ VITE_DEV_API_PROXY_TARGET: 'file:///private' }),
    /absolute http\(s\) URL/,
  );
});
