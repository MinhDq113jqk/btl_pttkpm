import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeSearch } from '../src/data/searchUtils.js';

test('search normalization ignores Vietnamese accents, case and surrounding spaces', () => {
  assert.equal(normalizeSearch('  ĐIỆN  '), 'dien');
  assert.equal(normalizeSearch('Máy bơm'), 'may bom');
});
