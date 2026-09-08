import test from 'node:test';
import assert from 'node:assert/strict';
import { tasks, filterTasks, normalizeSearch } from '../src/data/desktopData.js';
import { createRefundForm, validateRefund, validateAttachment, loadRefundDraft, saveRefundDraft, DRAFT_KEY } from '../src/data/refundForm.js';

test('task counts are consistent across all statuses', () => {
  assert.equal(tasks.length, 7);
  assert.deepEqual(['Đang xử lý', 'Chờ duyệt', 'Quá hạn'].map(status => filterTasks(tasks, '', status, 'all').length), [3, 3, 1]);
});
test('accent insensitive search and combined filters', () => {
  assert.equal(normalizeSearch('ĐIỆN'), 'dien');
  assert.equal(filterTasks(tasks, 'may bom', 'all', 'Kỹ thuật').length, 1);
  assert.equal(filterTasks(tasks, 'may bom', 'Quá hạn', 'all').length, 0);
});
test('default form has a valid ISO date and no errors', () => {
  const form = createRefundForm();
  assert.equal(form.postingDate, '2026-09-04');
  assert.deepEqual(validateRefund(form), {});
});
for (const amount of ['0', '-1', '1.5', '1e3', 'abc', '', '3000001', '9007199254740992']) {
  test(`rejects invalid refund amount: ${amount || 'empty'}`, () => {
    assert.ok(validateRefund({ ...createRefundForm(), refundAmount: amount }).refundAmount);
  });
}
test('rejects missing and invalid dates', () => {
  for (const postingDate of ['', '2026/09/04', '2026-02-31', '2026-13-01']) assert.ok(validateRefund({ ...createRefundForm(), postingDate }).postingDate);
});
test('requires bank fields only for bank transfer', () => {
  const data = { ...createRefundForm(), bankName: ' ', accountHolder: '', accountNumber: 'abc' };
  assert.equal(Object.keys(validateRefund(data)).length, 3);
  for (const paymentMethod of ['cash', 'credit_offset']) assert.deepEqual(validateRefund({ ...data, paymentMethod }), {});
  assert.ok(validateRefund({ ...data, paymentMethod: 'unknown' }).paymentMethod);
});
test('requires evidence', () => assert.ok(validateRefund({ ...createRefundForm(), attachments: [] }).attachments));
test('attachments reject oversized, empty, disguised and unsupported files', () => {
  assert.equal(validateAttachment({ name: 'proof.pdf', type: 'application/pdf', size: 1024 }), '');
  for (const file of [{ name: 'a.exe', type: '', size: 3 }, { name: 'a.pdf', type: 'text/html', size: 3 }, { name: 'a.png', type: 'image/png', size: 0 }, { name: 'a.pdf', size: 10485761 }]) assert.ok(validateAttachment(file));
});
test('draft round trip stores fields and fixture IDs, not chosen file contents', () => {
  const store = new Map();
  const storage = { getItem: key => store.get(key), setItem: (key, value) => store.set(key, value) };
  const data = { ...createRefundForm(), remarks: 'Test draft', refundAmount: '1200000' };
  data.attachments.push({ id: 'local', name: 'chosen.png', local: true });
  saveRefundDraft(storage, data);
  assert.equal(loadRefundDraft(storage).remarks, 'Test draft');
  assert.equal(loadRefundDraft(storage).refundAmount, '1200000');
  assert.equal(loadRefundDraft(storage).attachments.length, 2);
  assert.ok(!storage.getItem(DRAFT_KEY).includes('chosen.png'));
});
test('corrupt or blocked storage does not crash draft loading', () => {
  for (const value of ['{', 'null', '{"version":1,"data":{}}', '{"version":2,"data":{}}']) assert.equal(loadRefundDraft({ getItem: () => value }), null);
  assert.equal(loadRefundDraft({ getItem: () => { throw new Error('blocked'); } }), null);
});
