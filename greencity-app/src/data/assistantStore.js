export const ASSISTANT_STORAGE_KEY = 'greencity.assistant.v1';
export const MAX_QUESTION_LENGTH = 2000;

export function createConversation(id = crypto.randomUUID(), now = Date.now()) {
  return { id, title: 'Cuộc trò chuyện mới', createdAt: now, updatedAt: now, draft: '', messages: [] };
}

export function createAssistantState(conversation = createConversation()) {
  return { version: 1, activeId: conversation.id, conversations: [conversation] };
}

export function assistantReducer(state, action) {
  if (action.type === 'new') {
    const active = state.conversations.find(item => item.id === state.activeId);
    if (!active.messages.length && !active.draft.trim()) return state;
    return { ...state, activeId: action.conversation.id, conversations: [action.conversation, ...state.conversations] };
  }
  if (action.type === 'select') {
    return state.conversations.some(item => item.id === action.id) ? { ...state, activeId: action.id } : state;
  }
  return {
    ...state,
    conversations: state.conversations.map(conversation => {
      if (conversation.id !== action.conversationId) return conversation;
      if (action.type === 'draft') return { ...conversation, draft: action.text };
      if (action.type === 'send') {
        if (conversation.messages.some(message => message.status === 'pending')) return conversation;
        return {
          ...conversation, draft: '', updatedAt: action.now,
          title: conversation.messages.length ? conversation.title : action.user.text.slice(0, 64),
          messages: [...conversation.messages, action.user, action.assistant],
        };
      }
      if (action.type === 'retry') {
        if (conversation.messages.some(message => message.status === 'pending')) return conversation;
        return { ...conversation, updatedAt: action.now, messages: conversation.messages.map(message =>
          message.id === action.messageId && message.status === 'error'
            ? { ...message, status: 'pending', error: '', attempt: message.attempt + 1 }
            : message) };
      }
      if (action.type === 'resolve' || action.type === 'reject') {
        return { ...conversation, updatedAt: action.now, messages: conversation.messages.map(message =>
          message.id === action.messageId && message.status === 'pending'
            ? { ...message, status: action.type === 'resolve' ? 'complete' : 'error', text: action.text || '', error: action.error || '' }
            : message) };
      }
      return conversation;
    }),
  };
}

export function restoreAssistantState(raw) {
  const state = JSON.parse(raw);
  const text = value => typeof value === 'string';
  const validTime = value => Number.isFinite(value) && !Number.isNaN(new Date(value).getTime());
  if (state?.version !== 1 || !Array.isArray(state.conversations) || !state.conversations.length) throw new Error('Invalid chat history');
  const ids = new Set();
  for (const conversation of state.conversations) {
    if (!text(conversation.id) || ids.has(conversation.id) || !text(conversation.title) || !text(conversation.draft) || !validTime(conversation.createdAt) || !validTime(conversation.updatedAt) || !Array.isArray(conversation.messages)) throw new Error('Invalid conversation');
    ids.add(conversation.id);
    const messageIds = new Set();
    for (const message of conversation.messages) {
      if (!text(message.id) || messageIds.has(message.id) || !text(message.text) || !validTime(message.createdAt) || !['user', 'assistant'].includes(message.role) || !['complete', 'pending', 'error'].includes(message.status)) throw new Error('Invalid message');
      if (message.role === 'assistant' && (!text(message.replyTo) || !Number.isInteger(message.attempt) || message.attempt < 1)) throw new Error('Invalid reply');
      if (message.role === 'user' && message.status !== 'complete') throw new Error('Invalid user message');
      if (message.error !== undefined && !text(message.error)) throw new Error('Invalid message error');
      messageIds.add(message.id);
    }
    for (const message of conversation.messages) {
      if (message.role === 'assistant' && !conversation.messages.some(item => item.id === message.replyTo && item.role === 'user')) throw new Error('Missing question');
    }
  }
  if (!ids.has(state.activeId)) throw new Error('Missing active conversation');
  return {
    version: 1, activeId: state.activeId,
    conversations: state.conversations.map(conversation => ({
      ...conversation,
      messages: conversation.messages.map(message => message.status === 'pending'
        ? { ...message, status: 'error', error: 'Lần trả lời trước bị gián đoạn khi đóng hoặc tải lại ứng dụng. Chọn Gửi lại để tiếp tục.' }
        : message),
    })),
  };
}

export function loadAssistantHistory(storage) {
  const raw = storage.getItem(ASSISTANT_STORAGE_KEY);
  return raw ? restoreAssistantState(raw) : createAssistantState();
}

export function persistAssistantHistory(storage, state) {
  storage.setItem(ASSISTANT_STORAGE_KEY, JSON.stringify(state));
}

export function shouldSendOnEnter(event) {
  return event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey && !event.isComposing && event.keyCode !== 229;
}
