// Thin UI adapter. The backend derives tenant/site/building/role from the
// authenticated session; the browser sends only the user's message.
export function requestAssistantReply({ client, question, signal }) {
  if (typeof client?.supportAssistant === 'function') return client.supportAssistant({ mode: 'SEARCH', query: question }, { signal, idempotencyKey: `assistant-${crypto.randomUUID()}` }).then(row => row.messages.at(-1).reply);
  if (!client || typeof client.chatAssistant !== 'function') throw new TypeError('client.chatAssistant is required');
  return client.chatAssistant(question, { signal });
}
