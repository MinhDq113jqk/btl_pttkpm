import test from 'node:test';
import assert from 'node:assert/strict';
import { serializeFields } from '../src/data/operationalForms.js';

test('operation quantities preserve decimal text and arrays carry selected references', () => {
  const schema = { properties: { quantity: { anyOf: [{ type: 'number' }, { type: 'string' }] }, meter_ids: { type: 'array' }, starts_at: { type: 'string', format: 'date-time' }, building_id: { type: 'string' }, expected_version: { type: 'integer' } }, required: ['quantity', 'meter_ids', 'starts_at'] };
  const result = serializeFields(schema, { quantity: '12345.6789', meter_ids: ['meter-a', 'meter-b'], starts_at: '2026-10-10T09:00', building_id: 'untrusted-form-value', expected_version: 99 });
  assert.equal(result.quantity, '12345.6789');
  assert.deepEqual(result.meter_ids, ['meter-a', 'meter-b']);
  assert.equal(new Date(result.starts_at).getTime(), new Date('2026-10-10T09:00').getTime());
  assert.equal('building_id' in result, false); assert.equal('expected_version' in result, false);
});

test('missing required fields, invalid date and unsafe money integers fail before send', () => {
  assert.throws(() => serializeFields({ properties: { title: { type: 'string' } }, required: ['title'] }, {}), /Cần nhập/);
  assert.throws(() => serializeFields({ properties: { amount_vnd: { type: 'integer' } } }, { amount_vnd: '9007199254740992' }), /Số nguyên/);
  assert.throws(() => serializeFields({ properties: { starts_at: { type: 'string', format: 'date-time' } } }, { starts_at: 'bad date' }), /Thời gian/);
});

test('optional values are omitted and line lists normalize without raw JSON inputs', () => {
  const schema = { properties: { options: { type: 'array' }, valid_to: { anyOf: [{ type: 'string', format: 'date' }, { type: 'null' }] }, mandatory: { type: 'boolean' } } };
  assert.deepEqual(serializeFields(schema, { options: ' Một\n\n Hai ', valid_to: '', mandatory: false }), { options: ['Một', 'Hai'], mandatory: false });
});

test('structured milestone arrays resolve nested definitions and retain scope references', () => {
  const schema = { properties: { milestone_items: { type: 'array', items: { $ref: '#/$defs/Milestone' }, minItems: 1 } }, required: ['milestone_items'], $defs: { Milestone: { type: 'object', properties: { code: { type: 'string' }, amount_vnd: { type: 'integer' }, unit_id: { type: 'string' } }, required: ['code', 'amount_vnd'] } } };
  assert.deepEqual(serializeFields(schema, { milestone_items: [{ code: 'M1', amount_vnd: '123', unit_id: 'unit-a' }] }), { milestone_items: [{ code: 'M1', amount_vnd: 123, unit_id: 'unit-a' }] });
  assert.throws(() => serializeFields(schema, { milestone_items: [{}] }), /Cần nhập/);
  assert.throws(() => serializeFields(schema, { milestone_items: [] }), /Cần thêm/);
});

test('allocations reject missing targets, fractions and incomplete totals', () => {
  const schema = { properties: { amount_vnd: { type: 'integer' }, allocation: { type: 'object', default: {} } } };
  assert.deepEqual(serializeFields(schema, { amount_vnd: '100', allocation: { 'UNIT:unit-a': '60', 'BUILDING:building-a': '40' } }), { amount_vnd: 100, allocation: { 'UNIT:unit-a': 60, 'BUILDING:building-a': 40 } });
  for (const allocation of [{}, { '': 100 }, { 'UNIT:unit-a': 99 }, { 'UNIT:unit-a': 100.1 }]) assert.throws(() => serializeFields(schema, { amount_vnd: 100, allocation }), /Phân bổ/);
});
