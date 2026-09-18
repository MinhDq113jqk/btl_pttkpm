// Thin UI adapter. The backend derives tenant/site/building/role from the
// authenticated session; the browser sends only the user's message.
export function requestAssistantReply({ client, question, signal }) {
  if (!client || typeof client.chatAssistant !== 'function') throw new TypeError('client.chatAssistant is required');
  return client.chatAssistant(question, { signal });
}
