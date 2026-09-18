import test from 'node:test';
import assert from 'node:assert/strict';
import { ASSISTANT_STORAGE_KEY, assistantReducer, createAssistantState, createConversation, loadAssistantHistory, persistAssistantHistory, restoreAssistantState, shouldSendOnEnter } from '../src/data/assistantStore.js';
import { requestAssistantReply } from '../src/services/greenAssistant.js';

const fresh = () => createAssistantState(createConversation('one', 1000));
const user = { id: 'u1', role: 'user', text: 'Công việc quá hạn', status: 'complete', createdAt: 1001 };
const reply = { id: 'a1', role: 'assistant', text: '', status: 'pending', replyTo: 'u1', attempt: 1, createdAt: 1001 };
const sent = () => assistantReducer(fresh(), { type: 'send', conversationId: 'one', user, assistant: reply, now: 1001 });

test('new chat does not create duplicate empty conversations', () => {
  const initial = fresh();
  assert.equal(assistantReducer(initial, { type: 'new', conversation: createConversation('two') }), initial);
});
test('send creates distinct user/pending assistant messages and clears draft', () => {
  const state = sent();
  assert.equal(state.conversations[0].messages.length, 2);
  assert.equal(state.conversations[0].title, user.text);
  assert.equal(state.conversations[0].draft, '');
  assert.equal(state.conversations[0].messages[1].status, 'pending');
});
test('another send is ignored while this conversation is pending', () => {
  const state = assistantReducer(sent(), { type: 'send', conversationId: 'one', user, assistant: reply, now: 1002 });
  assert.equal(state.conversations[0].messages.length, 2);
});
test('new conversation retains old messages and draft', () => {
  const drafted = assistantReducer(sent(), { type: 'draft', conversationId: 'one', text: 'Bản nháp cần giữ' });
  const state = assistantReducer(drafted, { type: 'new', conversation: createConversation('two', 2000) });
  assert.equal(state.activeId, 'two');
  assert.equal(state.conversations.length, 2);
  assert.equal(state.conversations[1].draft, 'Bản nháp cần giữ');
  assert.equal(state.conversations[1].messages.length, 2);
});
test('late response updates only its original conversation', () => {
  const state = assistantReducer(sent(), { type: 'new', conversation: createConversation('two', 2000) });
  const resolved = assistantReducer(state, { type: 'resolve', conversationId: 'one', messageId: 'a1', text: 'Câu trả lời', now: 2001 });
  assert.equal(resolved.activeId, 'two');
  assert.equal(resolved.conversations[0].messages.length, 0);
  assert.equal(resolved.conversations[1].messages[1].text, 'Câu trả lời');
});
test('retry replaces failed reply state without duplicating question', () => {
  let state = assistantReducer(sent(), { type: 'reject', conversationId: 'one', messageId: 'a1', error: 'Lỗi mẫu', now: 1002 });
  state = assistantReducer(state, { type: 'retry', conversationId: 'one', messageId: 'a1', now: 1003 });
  assert.equal(state.conversations[0].messages.length, 2);
  assert.equal(state.conversations[0].messages[1].attempt, 2);
  assert.equal(state.conversations[0].messages[1].status, 'pending');
  state = assistantReducer(state, { type: 'resolve', conversationId: 'one', messageId: 'a1', text: 'Đã trả lời', now: 1004 });
  assert.equal(state.conversations[0].messages[1].status, 'complete');
});
test('reload converts in-flight replies to recoverable errors', () => {
  const state = restoreAssistantState(JSON.stringify(sent()));
  assert.equal(state.conversations[0].messages[1].status, 'error');
  assert.match(state.conversations[0].messages[1].error, /gián đoạn/);
});
test('storage round trip preserves conversations and drafts', () => {
  const map = new Map();
  const storage = { getItem: key => map.get(key), setItem: (key, value) => map.set(key, value) };
  const state = assistantReducer(fresh(), { type: 'draft', conversationId: 'one', text: 'Nháp nhiều\ndòng' });
  persistAssistantHistory(storage, state);
  assert.deepEqual(loadAssistantHistory(storage), state);
  assert.ok(map.has(ASSISTANT_STORAGE_KEY));
});
test('malformed history is rejected, not silently overwritten', () => {
  for (const raw of ['{', 'null', '{}', '{"version":1,"conversations":[]}', JSON.stringify({ ...fresh(), activeId: 'missing' })]) assert.throws(() => restoreAssistantState(raw));
  const bad = sent();
  bad.conversations[0].messages[1].replyTo = 'missing';
  assert.throws(() => restoreAssistantState(JSON.stringify(bad)));
});
test('storage read/write failures propagate for visible recovery feedback', () => {
  assert.throws(() => loadAssistantHistory({ getItem() { throw new Error('blocked'); } }));
  assert.throws(() => persistAssistantHistory({ setItem() { throw new Error('quota'); } }, fresh()));
});
test('out-of-range dates in saved history do not reach the renderer', () => {
  const state = sent();
  state.conversations[0].messages[0].createdAt = 1e30;
  assert.throws(() => restoreAssistantState(JSON.stringify(state)));
});
test('Enter sends, Shift+Enter and composing Enter do not', () => {
  assert.equal(shouldSendOnEnter({ key: 'Enter' }), true);
  for (const modifiers of [{ shiftKey: true }, { isComposing: true }, { keyCode: 229 }, { ctrlKey: true }, { altKey: true }, { metaKey: true }]) assert.equal(shouldSendOnEnter({ key: 'Enter', ...modifiers }), false);
  assert.equal(shouldSendOnEnter({ key: 'a' }), false);
});
test('assistant adapter sends only the question and AbortSignal to the authenticated client', async () => {
  const controller = new AbortController();
  const calls = [];
  const client = {
    chatAssistant(message, options) {
      calls.push({ message, options });
      return Promise.resolve('Câu trả lời từ backend');
    },
  };

  const result = await requestAssistantReply({
    client,
    question: '  Xin chào  ',
    signal: controller.signal,
    tenant_id: 'must-not-be-forwarded',
    role: 'admin',
  });

  assert.equal(result, 'Câu trả lời từ backend');
  assert.deepEqual(calls, [{ message: '  Xin chào  ', options: { signal: controller.signal } }]);
});
