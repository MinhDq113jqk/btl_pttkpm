import React, { useEffect, useLayoutEffect, useReducer, useRef, useState } from 'react';
import { ArrowDown, ArrowLeft, ArrowUp, Check, ChevronDown, Copy, History, Info, LoaderCircle, MessageCircle, Plus, RotateCcw, ShieldCheck, AlertCircle } from 'lucide-react';
import { GreenPet } from './GreenPet';
import { ASSISTANT_STORAGE_KEY, MAX_QUESTION_LENGTH, assistantReducer, createAssistantState, createConversation, loadAssistantHistory, persistAssistantHistory, shouldSendOnEnter } from '../../data/assistantStore';
import { requestAssistantReply } from '../../services/greenAssistant';
import './green-assistant.css';

const formatTime = time => new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit' }).format(time);
const formatDate = time => new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(time);

function formatAssistantError(error, timedOut) {
  if (timedOut) return 'Hệ thống xử lý quá lâu. Câu hỏi đã được giữ lại; chọn Gửi lại để thử tiếp.';
  if (error?.name === 'AbortError') return 'Yêu cầu đã bị hủy. Câu hỏi vẫn được giữ lại; chọn Gửi lại để thử tiếp.';
  const messages = {
    'ERR-NETWORK': 'Không thể kết nối Green Assistant. Kiểm tra mạng rồi thử lại.',
    'ERR-UNAUTHORIZED': 'Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.',
    'ERR-GEMINI-UNAVAILABLE': 'Green Assistant tạm thời không khả dụng.',
    'ERR-INVALID-RESPONSE': 'Backend trả về phản hồi không hợp lệ.',
  };
  const base = messages[error?.code]
    || (error?.name === 'ApiError' && typeof error.message === 'string' && error.message.trim()
      ? error.message.trim()
      : 'Chưa nhận được câu trả lời từ hệ thống.');
  const correlation = error?.correlationId ? ` Mã đối chiếu: ${error.correlationId}.` : '';
  return `${base} Câu hỏi vẫn được giữ lại; chọn Gửi lại để thử tiếp.${correlation}`;
}

function initializeHistory(historyKey) {
  try { return { state: loadAssistantHistory(window.localStorage, historyKey), canPersist: true, error: '' }; }
  catch {
    return { state: createAssistantState(), canPersist: false, error: 'Không đọc được lịch sử đã lưu. Cuộc trò chuyện hiện chỉ giữ trong phiên này; dữ liệu cũ không bị ghi đè.' };
  }
}

export function GreenAssistant({ contextKey, requestReply = requestAssistantReply, historyKey = ASSISTANT_STORAGE_KEY, suggestions = ['Xem công việc quá hạn', 'Hướng dẫn kiểm tra phiếu hoàn tiền'] }) {
  const [initial] = useState(() => initializeHistory(historyKey));
  const [state, dispatch] = useReducer(assistantReducer, initial.state);
  const [open, setOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [storageError, setStorageError] = useState(initial.error);
  const [inputError, setInputError] = useState('');
  const [copyState, setCopyState] = useState(null);
  const [unseen, setUnseen] = useState(false);
  const [closedReply, setClosedReply] = useState(false);
  const [bottomOffset, setBottomOffset] = useState(40);
  const rootRef = useRef(null);
  const launcherRef = useRef(null);
  const inputRef = useRef(null);
  const historyTitleRef = useRef(null);
  const messagesRef = useRef(null);
  const requests = useRef(new Map());
  const canPersist = useRef(initial.canPersist);
  const mounted = useRef(true);
  const openRef = useRef(open);
  const stickToBottom = useRef(true);
  const forceScroll = useRef(false);
  const copyTimer = useRef(null);
  const copyAttempt = useRef(0);
  const composing = useRef(false);
  openRef.current = open;

  const conversation = state.conversations.find(item => item.id === state.activeId);
  const pending = conversation.messages.some(message => message.status === 'pending');
  const readyToSend = conversation.draft.trim().length > 0 && !pending;

  const saveHistory = () => {
    if (!canPersist.current) return;
    try { persistAssistantHistory(window.localStorage, state, historyKey); setStorageError(''); }
    catch { setStorageError('Không lưu được lịch sử trên máy. Nội dung vẫn còn trong phiên này; đừng tải lại trước khi lưu thành công.'); }
  };
  useEffect(() => {
    if (!canPersist.current) return;
    try { persistAssistantHistory(window.localStorage, state, historyKey); setStorageError(''); }
    catch { setStorageError('Không lưu được lịch sử trên máy. Nội dung vẫn còn trong phiên này; đừng tải lại trước khi lưu thành công.'); }
  }, [state, historyKey]);

  useEffect(() => {
    mounted.current = true;
    const otherWindowChanged = event => {
      if (event.key !== historyKey && event.key !== null) return;
      canPersist.current = false;
      setStorageError('Lịch sử đã thay đổi ở cửa sổ khác. Phiên này tạm ngừng lưu để tránh ghi đè; hãy giữ cửa sổ mở nếu còn nội dung cần lưu.');
    };
    window.addEventListener('storage', otherWindowChanged);
    return () => {
      mounted.current = false;
      for (const request of requests.current.values()) request.controller.abort();
      clearTimeout(copyTimer.current);
      window.removeEventListener('storage', otherWindowChanged);
    };
  }, [historyKey]);

  // The pet must not sit on existing submit controls as forms scroll into view.
  useEffect(() => {
    const main = document.querySelector('main');
    const measure = () => {
      const bounds = main.getBoundingClientRect();
      const controls = [...main.querySelectorAll(open ? '.form-action-bar' : '.form-action-bar, form button[type="submit"]')];
      const offsets = controls.map(control => control.getBoundingClientRect())
        .filter(rect => rect.width && rect.top >= bounds.top && rect.top < bounds.bottom)
        .map(rect => window.innerHeight - rect.top + 12);
      setBottomOffset(Math.min(window.innerHeight - 110, Math.max(40, ...offsets)));
    };
    measure();
    const observer = new MutationObserver(measure);
    observer.observe(main, { childList: true, subtree: true });
    main.addEventListener('scroll', measure, { passive: true });
    window.addEventListener('resize', measure);
    return () => { observer.disconnect(); main.removeEventListener('scroll', measure); window.removeEventListener('resize', measure); };
  }, [contextKey, open]);

  useEffect(() => {
    if (!open) return;
    setClosedReply(false);
    if (showHistory) historyTitleRef.current?.focus();
    else inputRef.current?.focus({ preventScroll: true });
  }, [open, showHistory, state.activeId]);

  useEffect(() => {
    if (!open) return;
    const revealFocusedControl = event => {
      if (rootRef.current?.contains(event.target) || document.querySelector('dialog[open]')) return;
      if (!event.target.matches('button, input, select, textarea, a[href], [tabindex="0"]')) return;
      const target = event.target.getBoundingClientRect();
      const panel = rootRef.current.getBoundingClientRect();
      if (target.right > panel.left && target.left < panel.right && target.bottom > panel.top && target.top < panel.bottom) setOpen(false);
    };
    document.addEventListener('focusin', revealFocusedControl);
    return () => document.removeEventListener('focusin', revealFocusedControl);
  }, [open]);

  useLayoutEffect(() => {
    if (!open || showHistory) return;
    stickToBottom.current = true;
    forceScroll.current = true;
    messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    setUnseen(false);
    setInputError('');
    setCopyState(null);
  }, [open, showHistory, state.activeId]);

  useLayoutEffect(() => {
    const list = messagesRef.current;
    if (!list || !open || showHistory) return;
    if (forceScroll.current || stickToBottom.current) {
      list.scrollTop = list.scrollHeight;
      forceScroll.current = false;
      setUnseen(false);
    } else setUnseen(true);
  }, [conversation.messages, open, showHistory]);

  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
  }, [conversation.draft, open, showHistory]);

  const close = () => {
    setOpen(false);
    requestAnimationFrame(() => launcherRef.current?.focus({ preventScroll: true }));
  };

  const runRequest = async (conversationId, message, question, context) => {
    const controller = new AbortController();
    const request = { controller, conversationId, timedOut: false };
    requests.current.set(message.id, request);
    const timeout = setTimeout(() => { request.timedOut = true; controller.abort(); }, 15000);
    try {
      const answer = await requestReply({ question, messages: context, attempt: message.attempt, signal: controller.signal });
      if (controller.signal.aborted || !mounted.current) return;
      if (typeof answer !== 'string' || !answer.trim()) throw new Error('Hệ thống chưa trả về nội dung. Chọn Gửi lại để thử lại câu hỏi này.');
      dispatch({ type: 'resolve', conversationId, messageId: message.id, text: answer, now: Date.now() });
      if (!openRef.current) setClosedReply(true);
    } catch (error) {
      if (!mounted.current || (controller.signal.aborted && !request.timedOut)) return;
      const errorText = formatAssistantError(error, request.timedOut);
      dispatch({ type: 'reject', conversationId, messageId: message.id, error: errorText, now: Date.now() });
      if (!openRef.current) setClosedReply(true);
    } finally {
      clearTimeout(timeout);
      requests.current.delete(message.id);
    }
  };

  const isRequestRunning = () => [...requests.current.values()].some(request => request.conversationId === conversation.id);
  const send = (text = conversation.draft) => {
    const question = text.trim();
    if (!question || pending || isRequestRunning()) return;
    if (question.length > MAX_QUESTION_LENGTH) { setInputError(`Câu hỏi quá dài. Vui lòng rút gọn còn tối đa ${MAX_QUESTION_LENGTH} ký tự.`); return; }
    const now = Date.now();
    const user = { id: crypto.randomUUID(), role: 'user', text: question, status: 'complete', createdAt: now };
    const assistant = { id: crypto.randomUUID(), role: 'assistant', text: '', status: 'pending', replyTo: user.id, attempt: 1, createdAt: now };
    forceScroll.current = true;
    setInputError('');
    dispatch({ type: 'send', conversationId: conversation.id, user, assistant, now });
    void runRequest(conversation.id, assistant, question, [...conversation.messages, user]);
    inputRef.current?.focus({ preventScroll: true });
  };
  const retry = message => {
    if (pending || isRequestRunning()) return;
    const original = conversation.messages.find(item => item.id === message.replyTo);
    if (!original) return;
    forceScroll.current = true;
    dispatch({ type: 'retry', conversationId: conversation.id, messageId: message.id, now: Date.now() });
    void runRequest(conversation.id, { ...message, attempt: message.attempt + 1 }, original.text, conversation.messages.slice(0, conversation.messages.indexOf(original) + 1));
  };
  const copy = async message => {
    const attempt = ++copyAttempt.current;
    clearTimeout(copyTimer.current);
    try {
      await navigator.clipboard.writeText(message.text);
      if (!mounted.current || attempt !== copyAttempt.current) return;
      setCopyState({ id: message.id, success: true });
      copyTimer.current = setTimeout(() => setCopyState(null), 2200);
    } catch {
      if (mounted.current && attempt === copyAttempt.current) setCopyState({ id: message.id, success: false });
    }
  };
  const scrollToLatest = () => {
    messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    stickToBottom.current = true;
    setUnseen(false);
  };
  const newConversation = () => {
    dispatch({ type: 'new', conversation: createConversation() });
    setShowHistory(false);
    inputRef.current?.focus();
  };

  return <div ref={rootRef} className={`green-assistant ${open ? 'is-open' : ''}`} style={{ '--assistant-bottom': `${bottomOffset}px` }}>
    <button ref={launcherRef} hidden={open} className="assistant-launcher" onClick={() => setOpen(true)} aria-label={`Mở Green Assistant${closedReply ? ', có phản hồi mới' : ''}`} aria-expanded={open} aria-controls="green-assistant-panel">
      <span className="assistant-launcher-label">{closedReply ? 'Có phản hồi mới' : 'Green Assistant'}</span>
      <GreenPet thinking={state.conversations.some(item => item.messages.some(message => message.status === 'pending'))} />
      {closedReply && <span className="assistant-unread-dot" aria-hidden="true" />}
    </button>

    {open && <section id="green-assistant-panel" className="assistant-panel" role="dialog" aria-modal="false" aria-labelledby="assistant-title" onKeyDown={event => {
      if (event.key === 'Escape' && !composing.current) { event.stopPropagation(); if (showHistory) setShowHistory(false); else close(); }
    }}>
      <header className="assistant-header">
        <div className="assistant-avatar"><GreenPet thinking={pending} /></div>
        <div className="assistant-heading"><h2 id="assistant-title">Green Assistant</h2><p>Trợ lý hỗ trợ GreenCity</p></div>
        <div className="assistant-header-actions">
          <button className="icon-button" aria-label="Lịch sử trò chuyện" title="Lịch sử trò chuyện" aria-expanded={showHistory} aria-controls="assistant-history" onClick={() => setShowHistory(!showHistory)}><History size={18} aria-hidden="true" /></button>
          <button className="icon-button" aria-label="Tạo cuộc trò chuyện mới" title="Tạo cuộc trò chuyện mới" onClick={newConversation}><Plus size={20} aria-hidden="true" /></button>
          <button className="icon-button" aria-label="Thu gọn Green Assistant" title="Thu gọn (Esc)" onClick={close}><ChevronDown size={20} aria-hidden="true" /></button>
        </div>
      </header>

      {storageError && <div className="assistant-storage-error" role="alert"><AlertCircle size={16} aria-hidden="true" /><div>{storageError}{canPersist.current && <button onClick={saveHistory}>Thử lưu lại lịch sử</button>}</div></div>}

      {showHistory ? <div className="assistant-history" id="assistant-history">
        <div className="assistant-history-heading"><button className="icon-button" aria-label="Quay lại trò chuyện" onClick={() => setShowHistory(false)}><ArrowLeft size={18} aria-hidden="true" /></button><h3 ref={historyTitleRef} tabIndex={-1}>Lịch sử trò chuyện</h3></div>
        <p className="assistant-history-note">Các cuộc trò chuyện được giữ riêng. Tạo mới không xóa lịch sử.</p>
        <div className="assistant-history-list">{[...state.conversations].sort((a, b) => b.updatedAt - a.updatedAt).map(item => <button key={item.id} className={`assistant-history-item ${state.activeId === item.id ? 'is-active' : ''}`} aria-current={state.activeId === item.id ? 'true' : undefined} onClick={() => { dispatch({ type: 'select', id: item.id }); setShowHistory(false); }}>
          <MessageCircle size={18} aria-hidden="true" /><span><strong>{item.messages.length ? item.title : item.draft || 'Cuộc trò chuyện mới'}</strong><small>{formatDate(item.updatedAt)} · {item.messages.filter(message => message.role === 'user').length} câu hỏi{item.draft ? ' · Có nháp' : ''}</small></span>{item.messages.some(message => message.status === 'pending') && <LoaderCircle size={16} className="assistant-spinner" aria-label="Đang xử lý" />}
        </button>)}</div>
      </div> : <>
        <div className="assistant-conversation-label"><span>{conversation.messages.length ? conversation.title : 'Cuộc trò chuyện mới'}</span><span className="assistant-demo-badge">Backend</span></div>
        <div className="assistant-log-wrap">
          <div ref={messagesRef} className="assistant-messages" role="log" aria-label="Nội dung trò chuyện" aria-live="polite" aria-relevant="additions text" aria-busy={pending} tabIndex={0} onScroll={event => {
            const list = event.currentTarget;
            stickToBottom.current = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
            if (stickToBottom.current) setUnseen(false);
          }}>
            {conversation.messages.length === 0 && <div className="assistant-welcome"><GreenPet /><p className="assistant-welcome-kicker">MỘT NGƯỜI BẠN NHỎ, LUÔN Ở ĐÂY</p><h3>Mình có thể giúp gì cho bạn?</h3><p>Hỏi mình cách sử dụng GreenCity.<br />Bắt đầu bằng một câu hỏi bên dưới nhé.</p><div className="assistant-suggestions">{suggestions.map(question => <button key={question} onClick={() => send(question)}>{question}<ArrowUp size={15} aria-hidden="true" /></button>)}</div></div>}
            {conversation.messages.map(message => <article key={message.id} className={`assistant-message assistant-message-${message.role} is-${message.status}`} aria-label={message.role === 'user' ? 'Tin nhắn của bạn' : 'Tin nhắn Green Assistant'}>
              <div className="assistant-message-meta"><span>{message.role === 'user' ? 'Bạn' : 'Green Assistant'}</span><time dateTime={new Date(message.createdAt).toISOString()}>{formatTime(message.createdAt)}</time></div>
              {message.status === 'pending' ? <div className="assistant-message-bubble assistant-typing" aria-hidden="true"><span /><span /><span /></div>
                : message.status === 'error' ? <div className="assistant-message-error" role="alert"><strong><AlertCircle size={16} aria-hidden="true" />Chưa thể trả lời câu hỏi này</strong><p>{message.error}</p><button onClick={() => retry(message)} disabled={pending}><RotateCcw size={15} aria-hidden="true" />Gửi lại câu hỏi</button></div>
                  : <div className="assistant-message-bubble">{message.text}</div>}
              {message.role === 'assistant' && message.status === 'complete' && <div className="assistant-copy-row"><button onClick={() => copy(message)} aria-label="Sao chép câu trả lời">{copyState?.id === message.id && copyState.success ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}{copyState?.id === message.id && copyState.success ? 'Đã sao chép' : 'Sao chép'}</button>{copyState?.id === message.id && !copyState.success && <p role="status">Không sao chép được. Bạn có thể bôi đen câu trả lời và nhấn Ctrl+C.</p>}</div>}
            </article>)}
          </div>
          {unseen && <button className="assistant-latest" onClick={scrollToLatest}><ArrowDown size={15} aria-hidden="true" />Tin nhắn mới nhất</button>}
        </div>
        <form className="assistant-composer" onSubmit={event => { event.preventDefault(); send(); }}>
          <div className="assistant-processing" role="status" aria-live="polite">{pending && <><LoaderCircle size={14} className="assistant-spinner" aria-hidden="true" /><span>Green Assistant đang trả lời...</span></>}</div>
          <label htmlFor="assistant-question" className="sr-only">Nhập tin nhắn cho Green Assistant</label>
          <div className="assistant-input-wrap"><textarea ref={inputRef} id="assistant-question" rows={2} placeholder={pending ? 'Bạn có thể soạn trước câu hỏi tiếp theo…' : 'Nhập câu hỏi của bạn…'} value={conversation.draft} aria-describedby={`assistant-keyboard-hint${inputError ? ' assistant-input-error' : ''}`} aria-invalid={inputError ? true : undefined}
            onChange={event => { dispatch({ type: 'draft', conversationId: conversation.id, text: event.target.value }); setInputError(''); }}
            onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
            onKeyDown={event => { if (!composing.current && shouldSendOnEnter(event.nativeEvent)) { event.preventDefault(); send(); } }} />
            <button className="assistant-send" type="submit" disabled={!readyToSend} aria-label={pending ? 'Đang xử lý câu hỏi' : 'Gửi tin nhắn'} title={pending ? 'Đang xử lý, bạn vẫn có thể soạn câu hỏi tiếp theo' : 'Gửi tin nhắn (Enter)'}>{pending ? <LoaderCircle size={19} className="assistant-spinner" aria-hidden="true" /> : <ArrowUp size={20} aria-hidden="true" />}</button>
          </div>
          {inputError && <p className="assistant-input-error" id="assistant-input-error" role="alert">{inputError}</p>}
          <div className="assistant-input-hint"><span id="assistant-keyboard-hint">Enter để gửi · Shift + Enter xuống dòng</span>{conversation.draft.length > 1600 && <span>{conversation.draft.length}/{MAX_QUESTION_LENGTH}</span>}</div>
        </form>
      </>}
      <details className="assistant-privacy"><summary><ShieldCheck size={13} aria-hidden="true" />{storageError ? 'Lịch sử chưa được lưu' : 'Lịch sử lưu trên máy này'}<Info size={13} aria-hidden="true" /></summary><p>Câu hỏi được gửi qua backend đã đăng nhập; API key không nằm trong trình duyệt. Lịch sử chỉ lưu trên máy này và chưa đồng bộ tài khoản. Không nhập mật khẩu, OTP hay dữ liệu cư dân thật. Xóa dữ liệu trình duyệt sẽ mất lịch sử.</p></details>
    </section>}
  </div>;
}
