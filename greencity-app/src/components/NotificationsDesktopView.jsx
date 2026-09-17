import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Bell,
  Check,
  CheckCheck,
  CheckCircle2,
  Clock,
  ExternalLink,
  Inbox,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Send,
  WifiOff,
} from 'lucide-react';

const commandKey = prefix => `${prefix}-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;

const formatTime = value => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? '—'
    : new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(date);
};

const errorCopy = error => {
  if (error?.code === 'ERR-NETWORK') {
    return 'Không thể kết nối máy chủ hoặc mất mạng. Thao tác thử lại giữ nguyên mã chống trùng lặp.';
  }
  if (error?.code === 'ERR-SCOPE-NOTFOUND') {
    return 'Bản ghi không còn thuộc phạm vi phiên hiện tại hoặc không tìm thấy.';
  }
  if (error?.code === 'ERR-FORBIDDEN') {
    return 'Tài khoản không có quyền thao tác trên hàng đợi outbox của site.';
  }
  return error?.message || 'Máy chủ chưa thể xử lý yêu cầu này.';
};

function DeliveryBadge({ status }) {
  if (status === 'PENDING') {
    return (
      <span className="status-badge status-amber" title="Đang xếp hàng chờ worker gửi">
        <Clock size={12} aria-hidden="true" />
        <span>Chờ gửi</span>
      </span>
    );
  }
  if (status === 'PROCESSING') {
    return (
      <span className="status-badge status-blue" title="Đang trong tiến trình giao nhận">
        <LoaderCircle size={12} className="request-spinner" aria-hidden="true" />
        <span>Đang gửi</span>
      </span>
    );
  }
  if (status === 'PUBLISHED') {
    return (
      <span className="status-badge status-emerald" title="Đã gửi thành công qua kênh">
        <CheckCircle2 size={12} aria-hidden="true" />
        <span>Đã gửi</span>
      </span>
    );
  }
  if (status === 'RETRY_SCHEDULED') {
    return (
      <span className="status-badge status-amber" title="Lỗi gửi; đang lên lịch thử lại theo exponential backoff">
        <RotateCcw size={12} aria-hidden="true" />
        <span>Chờ gửi lại</span>
      </span>
    );
  }
  if (status === 'DEAD_LETTER') {
    return (
      <span className="status-badge status-rose" title="Quá số lần retry tối đa; đã chuyển vào dead-letter">
        <AlertTriangle size={12} aria-hidden="true" />
        <span>Thất bại</span>
      </span>
    );
  }
  return <span className="status-badge status-blue">{status || 'Không rõ'}</span>;
}

const EMPTY_NOTIFICATIONS = [];

export function NotificationsDesktopView({
  account,
  client,
  onToast,
  onUnreadChange,
  notifications: fallbackNotifications = EMPTY_NOTIFICATIONS,
  onRead: fallbackOnRead,
  onReadAll: fallbackOnReadAll,
  onOpen,
}) {
  const isApiMode = Boolean(client?.listNotifications);
  const canManageOutbox = Boolean(account?.canManageOutbox);

  const [activeTab, setActiveTab] = useState('inbox');
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [deliveryFilter, setDeliveryFilter] = useState('all');
  const [outboxStatusFilter, setOutboxStatusFilter] = useState('all');

  const [notifications, setNotifications] = useState(fallbackNotifications);
  const [outboxEvents, setOutboxEvents] = useState([]);
  const [loading, setLoading] = useState(isApiMode);
  const [error, setError] = useState(null);
  const [outboxError, setOutboxError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [busy, setBusy] = useState({});
  const [isOffline, setIsOffline] = useState(typeof navigator !== 'undefined' && !navigator.onLine);

  const errorRef = useRef(null);
  const intentsRef = useRef(new Map());
  const onUnreadChangeRef = useRef(onUnreadChange);
  const inboxPanelId = useId();
  const outboxPanelId = useId();

  useEffect(() => {
    onUnreadChangeRef.current = onUnreadChange;
  }, [onUnreadChange]);

  const intentFor = useCallback((name, payload) => {
    const fingerprint = JSON.stringify(payload);
    const existing = intentsRef.current.get(name);
    if (existing?.fingerprint === fingerprint) return existing;
    const next = { fingerprint, idempotencyKey: commandKey(`notification-${name}`) };
    intentsRef.current.set(name, next);
    return next;
  }, []);

  const clearIntent = useCallback(name => intentsRef.current.delete(name), []);

  useEffect(() => {
    const onOnline = () => setIsOffline(false);
    const onOffline = () => setIsOffline(true);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  useEffect(() => {
    if (actionError || error) errorRef.current?.focus();
  }, [actionError, error]);

  const loadData = useCallback(async signal => {
    if (!isApiMode) {
      setNotifications(fallbackNotifications);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const notifResult = await client.listNotifications({ includeRead: true, signal });
      setNotifications(notifResult.items);
      onUnreadChangeRef.current?.(notifResult.items.filter(item => !item.read_at).length);
      if (canManageOutbox && client.listOutboxEvents) {
        try {
          const outboxResult = await client.listOutboxEvents({ limit: 50, signal });
          setOutboxEvents(outboxResult.items);
          setOutboxError(null);
        } catch (outboxErr) {
          if (outboxErr?.name === 'AbortError') throw outboxErr;
          setOutboxError(outboxErr);
          if (outboxErr?.code === 'ERR-NETWORK') setIsOffline(true);
        }
      } else {
        setOutboxEvents([]);
        setOutboxError(null);
      }
    } catch (err) {
      if (err?.name !== 'AbortError') {
        setError(err);
        if (err?.code === 'ERR-NETWORK') setIsOffline(true);
      }
    } finally {
      setLoading(false);
    }
  }, [canManageOutbox, client, fallbackNotifications, isApiMode]);

  useEffect(() => {
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  const handleMarkRead = async notification => {
    const key = `read:${notification.id}`;
    setBusy(previous => ({ ...previous, [key]: true }));
    setActionError(null);
    try {
      if (isApiMode) {
        const updated = await client.markNotificationRead(notification.id);
        setNotifications(previous => previous.map(item => (item.id === notification.id ? updated : item)));
        const nextUnread = notifications.filter(item => item.id !== notification.id && !item.read_at).length;
        onUnreadChange?.(nextUnread);
      } else if (fallbackOnRead) {
        fallbackOnRead(notification.id);
        setNotifications(previous => previous.map(item => (item.id === notification.id ? { ...item, unread: false } : item)));
      }
      onToast?.('Đã đánh dấu thông báo là đã đọc.');
    } catch (err) {
      if (err?.name !== 'AbortError') {
        setActionError({
          title: 'Chưa thể đánh dấu đã đọc',
          message: errorCopy(err),
          correlationId: err?.correlationId || '',
        });
        if (err?.code === 'ERR-NETWORK') setIsOffline(true);
      }
    } finally {
      setBusy(previous => ({ ...previous, [key]: false }));
    }
  };

  const handleMarkAllRead = async () => {
    const unreadList = notifications.filter(item => (item.read_at === null || item.unread));
    if (!unreadList.length) return;
    setBusy(previous => ({ ...previous, markAll: true }));
    setActionError(null);
    let count = 0;
    try {
      if (isApiMode) {
        for (const item of unreadList) {
          await client.markNotificationRead(item.id);
          count += 1;
        }
        await loadData();
      } else if (fallbackOnReadAll) {
        fallbackOnReadAll();
        setNotifications(previous => previous.map(item => ({ ...item, unread: false })));
        count = unreadList.length;
      }
      onToast?.(`Đã đánh dấu ${count} thông báo là đã đọc.`);
      onUnreadChange?.(0);
    } catch (err) {
      if (err?.name !== 'AbortError') {
        setActionError({
          title: 'Chưa thể hoàn tất đánh dấu tất cả đã đọc',
          message: errorCopy(err),
          correlationId: err?.correlationId || '',
        });
        if (err?.code === 'ERR-NETWORK') setIsOffline(true);
      }
      if (isApiMode) loadData().catch(() => {});
    } finally {
      setBusy(previous => ({ ...previous, markAll: false }));
    }
  };

  const handleRetryOutboxEvent = async event => {
    const key = `retry:${event.id}`;
    const intent = intentFor(key, { event_id: event.id });
    setBusy(previous => ({ ...previous, [key]: true }));
    setActionError(null);
    try {
      const updated = await client.retryOutboxEvent(event.id, {
        idempotencyKey: intent.idempotencyKey,
      });
      clearIntent(key);
      setIsOffline(false);
      setOutboxEvents(previous => previous.map(item => (item.id === event.id ? updated : item)));
      onToast?.(`Đã gửi yêu cầu retry cho sự kiện ${event.event_type}.`);
    } catch (err) {
      if (err?.name !== 'AbortError') {
        setActionError({
          title: 'Thử lại gửi outbox chưa thành công',
          message: `${errorCopy(err)} (Mã chống trùng lặp được giữ nguyên cho lần nhấn kế tiếp)`,
          correlationId: err?.correlationId || '',
        });
        if (err?.code === 'ERR-NETWORK') setIsOffline(true);
      }
    } finally {
      setBusy(previous => ({ ...previous, [key]: false }));
    }
  };

  const unreadCount = useMemo(
    () => notifications.filter(item => (item.read_at === null || item.unread)).length,
    [notifications],
  );

  const failedOutboxCount = useMemo(
    () => outboxEvents.filter(item => ['RETRY_SCHEDULED', 'DEAD_LETTER'].includes(item.delivery_status)).length,
    [outboxEvents],
  );

  const visibleNotifications = useMemo(() => {
    return notifications.filter(item => {
      const isUnread = item.read_at === null || item.unread;
      if (unreadOnly && !isUnread) return false;
      if (deliveryFilter === 'queued') return ['PENDING', 'PROCESSING'].includes(item.delivery_status);
      if (deliveryFilter === 'sent') return item.delivery_status === 'PUBLISHED';
      if (deliveryFilter === 'failed') return ['RETRY_SCHEDULED', 'DEAD_LETTER'].includes(item.delivery_status);
      return true;
    });
  }, [deliveryFilter, notifications, unreadOnly]);

  const visibleOutboxEvents = useMemo(() => {
    return outboxEvents.filter(item => {
      if (outboxStatusFilter === 'queued') return ['PENDING', 'PROCESSING'].includes(item.delivery_status);
      if (outboxStatusFilter === 'sent') return item.delivery_status === 'PUBLISHED';
      if (outboxStatusFilter === 'failed') return ['RETRY_SCHEDULED', 'DEAD_LETTER'].includes(item.delivery_status);
      return true;
    });
  }, [outboxEvents, outboxStatusFilter]);

  return (
    <div className="desktop-page notifications-page">
      {isOffline && (
        <div className="notification-offline-banner" role="alert" aria-live="assertive">
          <WifiOff size={18} aria-hidden="true" />
          <div>
            <strong>Mất kết nối tới máy chủ (Ngoại tuyến)</strong>
            <p>
              Hệ thống không thể gửi yêu cầu mới. Thao tác thử lại được bảo vệ bằng Idempotency-Key để chống trùng lặp bản ghi khi kết nối trở lại.
            </p>
          </div>
          <button
            type="button"
            className="button-secondary"
            onClick={() => loadData()}
            disabled={loading}
          >
            <RefreshCw size={14} aria-hidden="true" />
            Kiểm tra kết nối
          </button>
        </div>
      )}

      <div className="page-heading">
        <div>
          <p className="eyebrow">Hộp thư & Điều hành thông báo</p>
          <h1>Thông báo</h1>
          <p role="status">
            {unreadCount} thông báo chưa đọc · Trạng thái giao nhận được đồng bộ trực tiếp từ backend R5.
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="button-secondary"
            onClick={() => loadData()}
            disabled={loading}
            title="Tải lại dữ liệu thông báo từ máy chủ"
          >
            <RefreshCw size={16} className={loading ? 'request-spinner' : ''} aria-hidden="true" />
            Làm mới
          </button>
          {activeTab === 'inbox' && (
            <button
              type="button"
              className="button-secondary"
              onClick={handleMarkAllRead}
              disabled={unreadCount === 0 || busy.markAll || loading}
            >
              <CheckCheck size={18} aria-hidden="true" />
              {busy.markAll ? 'Đang cập nhật…' : 'Đánh dấu tất cả đã đọc'}
            </button>
          )}
        </div>
      </div>

      {actionError && (
        <div ref={errorRef} className="surface error-summary-banner" role="alert" tabIndex={-1}>
          <AlertCircle size={20} aria-hidden="true" />
          <div className="error-summary-content">
            <strong>{actionError.title}</strong>
            <p>{actionError.message}</p>
            {actionError.correlationId && (
              <span className="helper-text">Mã đối chiếu: {actionError.correlationId}</span>
            )}
          </div>
          <button
            type="button"
            className="button-text"
            onClick={() => setActionError(null)}
            aria-label="Đóng thông báo lỗi"
          >
            Đóng
          </button>
        </div>
      )}

      {canManageOutbox && (
        <div className="notification-tabs-bar" role="tablist" aria-label="Phân hệ thông báo">
          <button
            type="button"
            role="tab"
            id="notification-inbox-tab"
            aria-controls={inboxPanelId}
            aria-selected={activeTab === 'inbox'}
            className={`tab-button ${activeTab === 'inbox' ? 'is-active' : ''}`}
            onClick={() => setActiveTab('inbox')}
          >
            <Inbox size={16} aria-hidden="true" />
            <span>Hộp thư của tôi</span>
            {unreadCount > 0 && <span className="tab-badge">{unreadCount}</span>}
          </button>
          <button
            type="button"
            role="tab"
            id="notification-outbox-tab"
            aria-controls={outboxPanelId}
            aria-selected={activeTab === 'outbox'}
            className={`tab-button ${activeTab === 'outbox' ? 'is-active' : ''}`}
            onClick={() => setActiveTab('outbox')}
          >
            <Send size={16} aria-hidden="true" />
            <span>Hàng đợi Outbox & Kênh gửi</span>
            {failedOutboxCount > 0 && (
              <span className="tab-badge tab-badge-rose">{failedOutboxCount} lỗi</span>
            )}
          </button>
        </div>
      )}

      {loading && (
        <div className="surface request-state request-loading" role="status" aria-busy="true">
          <LoaderCircle className="request-spinner" size={24} aria-hidden="true" />
          <span>Đang tải dữ liệu thông báo từ máy chủ…</span>
        </div>
      )}

      {error && !loading && (
        <div className="surface request-state request-error" role="alert">
          <AlertCircle size={24} aria-hidden="true" />
          <div>
            <strong>Không thể tải thông báo</strong>
            <p>{errorCopy(error)}</p>
            {error?.correlationId && (
              <span className="helper-text">Mã đối chiếu: {error.correlationId}</span>
            )}
          </div>
          <button type="button" className="button-secondary" onClick={() => loadData()}>
            <RefreshCw size={16} aria-hidden="true" />
            Thử lại
          </button>
        </div>
      )}

      {!loading && !error && activeTab === 'inbox' && (
        <section id={inboxPanelId} className="surface" role="tabpanel" aria-labelledby="notification-inbox-tab" aria-label="Danh sách thông báo">
          <div className="status-filters">
            <div className="filter-group">
              <button
                type="button"
                aria-pressed={!unreadOnly}
                className={!unreadOnly ? 'is-selected' : ''}
                onClick={() => setUnreadOnly(false)}
              >
                Tất cả <span>{notifications.length}</span>
              </button>
              <button
                type="button"
                aria-pressed={unreadOnly}
                className={unreadOnly ? 'is-selected' : ''}
                onClick={() => setUnreadOnly(true)}
              >
                Chưa đọc <span>{unreadCount}</span>
              </button>
            </div>
            <div className="filter-group delivery-status-filter">
              <span className="filter-label">Kênh gửi:</span>
              <button
                type="button"
                className={`filter-chip ${deliveryFilter === 'all' ? 'is-active' : ''}`}
                onClick={() => setDeliveryFilter('all')}
              >
                Tất cả
              </button>
              <button
                type="button"
                className={`filter-chip ${deliveryFilter === 'queued' ? 'is-active' : ''}`}
                onClick={() => setDeliveryFilter('queued')}
              >
                Chờ gửi
              </button>
              <button
                type="button"
                className={`filter-chip ${deliveryFilter === 'sent' ? 'is-active' : ''}`}
                onClick={() => setDeliveryFilter('sent')}
              >
                Đã gửi
              </button>
              <button
                type="button"
                className={`filter-chip ${deliveryFilter === 'failed' ? 'is-active' : ''}`}
                onClick={() => setDeliveryFilter('failed')}
              >
                Lỗi kênh
              </button>
            </div>
          </div>

          <div className="notification-list">
            {visibleNotifications.map(item => {
              const isUnread = item.read_at === null || item.unread;
              const title = item.template_snapshot?.title || item.template_code || item.title || 'Thông báo hệ thống';
              const detail = item.template_snapshot?.detail || item.template_snapshot?.message || item.detail || 'Chi tiết thông báo từ hệ thống.';
              const taskId = item.template_snapshot?.task_id || item.taskId;
              const isBusy = busy[`read:${item.id}`];

              return (
                <article
                  key={item.id}
                  className={`notification-row ${isUnread ? 'is-unread' : ''}`}
                >
                  <div className="notification-symbol">
                    <Bell size={20} aria-hidden="true" />
                  </div>
                  <div className="notification-content">
                    <div className="notification-title">
                      <div className="notification-header-line">
                        <h2>{title}</h2>
                        {item.delivery_status && <DeliveryBadge status={item.delivery_status} />}
                      </div>
                      <span className="notification-time">{formatTime(item.created_at || item.time)}</span>
                    </div>
                    <p>{detail}</p>
                    {item.last_error && (
                      <div className="notification-error-box">
                        <AlertTriangle size={14} aria-hidden="true" />
                        <span>Lỗi giao nhận: {item.last_error}</span>
                      </div>
                    )}
                    <div className="notification-controls">
                      {taskId && onOpen && (
                        <button
                          type="button"
                          className="button-text"
                          onClick={() => onOpen(item)}
                        >
                          <ExternalLink size={14} aria-hidden="true" />
                          Mở hồ sơ liên quan
                        </button>
                      )}
                      {isUnread ? (
                        <button
                          type="button"
                          className="button-text"
                          onClick={() => handleMarkRead(item)}
                          disabled={isBusy}
                        >
                          <Check size={15} aria-hidden="true" />
                          {isBusy ? 'Đang cập nhật…' : 'Đánh dấu đã đọc'}
                        </button>
                      ) : (
                        <span className="helper-text">Đã đọc ({formatTime(item.read_at)})</span>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}

            {visibleNotifications.length === 0 && (
              <div className="empty-state">
                {unreadOnly ? (
                  <>
                    <CheckCheck size={36} aria-hidden="true" />
                    <h2>Bạn đã đọc hết thông báo</h2>
                    <p>Không có thông báo chưa đọc nào trong hộp thư phiên hiện tại.</p>
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => setUnreadOnly(false)}
                    >
                      Xem tất cả thông báo
                    </button>
                  </>
                ) : (
                  <>
                    <Inbox size={36} aria-hidden="true" />
                    <h2>Hộp thư trống</h2>
                    <p>Chưa có thông báo nào được ghi nhận cho tài khoản trong site này.</p>
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => loadData()}
                    >
                      <RefreshCw size={16} aria-hidden="true" />
                      Tải lại
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {!loading && !error && activeTab === 'outbox' && canManageOutbox && (
        <section id={outboxPanelId} className="surface outbox-panel" role="tabpanel" aria-labelledby="notification-outbox-tab" aria-label="Hàng đợi Outbox & Kênh gửi">
          <header className="outbox-header">
            <div>
              <h2>Hàng đợi Outbox & Kênh gửi</h2>
              <p>
                Transactional Outbox theo AC-22. Lỗi giao nhận kênh ngoài không làm rollback giao dịch gốc; thử lại thủ công giữ nguyên Idempotency-Key (AC-36).
              </p>
            </div>
            <div className="filter-group">
              <button
                type="button"
                className={`filter-chip ${outboxStatusFilter === 'all' ? 'is-active' : ''}`}
                onClick={() => setOutboxStatusFilter('all')}
              >
                Tất cả ({outboxEvents.length})
              </button>
              <button
                type="button"
                className={`filter-chip ${outboxStatusFilter === 'queued' ? 'is-active' : ''}`}
                onClick={() => setOutboxStatusFilter('queued')}
              >
                Chờ gửi
              </button>
              <button
                type="button"
                className={`filter-chip ${outboxStatusFilter === 'sent' ? 'is-active' : ''}`}
                onClick={() => setOutboxStatusFilter('sent')}
              >
                Đã gửi
              </button>
              <button
                type="button"
                className={`filter-chip ${outboxStatusFilter === 'failed' ? 'is-active' : ''}`}
                onClick={() => setOutboxStatusFilter('failed')}
              >
                Thất bại / Dead-letter ({failedOutboxCount})
              </button>
            </div>
          </header>

          {outboxError ? (
            <div className="surface request-state request-error" role="alert" tabIndex={-1}>
              <AlertCircle size={24} aria-hidden="true" />
              <div>
                <strong>Không thể tải hàng đợi outbox</strong>
                <p>{errorCopy(outboxError)}</p>
                {outboxError?.correlationId && <span className="helper-text">Mã đối chiếu: {outboxError.correlationId}</span>}
              </div>
              <button type="button" className="button-secondary" onClick={() => loadData()}>
                <RefreshCw size={16} aria-hidden="true" />
                Thử lại
              </button>
            </div>
          ) : (
          <div className="billing-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Sự kiện / Tài nguyên</th>
                  <th>Trạng thái</th>
                  <th>Lần thử</th>
                  <th>Thời gian thử kế tiếp</th>
                  <th>Lỗi gần nhất</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {visibleOutboxEvents.map(event => {
                  const isRetryable = ['RETRY_SCHEDULED', 'DEAD_LETTER'].includes(event.delivery_status);
                  const isRetrying = busy[`retry:${event.id}`];

                  return (
                    <tr key={event.id}>
                      <td>
                        <strong>{event.event_type}</strong>
                        <div className="billing-line">
                          {event.resource_type} · ID: {event.resource_id?.slice?.(0, 8)}…
                        </div>
                        <div className="helper-text" title={`Correlation ID: ${event.correlation_id}`}>
                          Corr: {event.correlation_id?.slice?.(0, 8)}…
                        </div>
                      </td>
                      <td>
                        <DeliveryBadge status={event.delivery_status} />
                      </td>
                      <td>
                        <span>{event.attempt_count} / 3</span>
                      </td>
                      <td>
                        <span>{formatTime(event.next_attempt_at)}</span>
                      </td>
                      <td>
                        {event.last_error ? (
                          <span className="outbox-error-text" title={event.last_error}>
                            <AlertTriangle size={13} aria-hidden="true" />
                            {event.last_error}
                          </span>
                        ) : (
                          <span className="helper-text">—</span>
                        )}
                      </td>
                      <td>
                        {isRetryable ? (
                          <button
                            type="button"
                            className="button-secondary"
                            disabled={isRetrying}
                            onClick={() => handleRetryOutboxEvent(event)}
                            title="Thử lại giao nhận outbox với Idempotency-Key"
                          >
                            <RotateCcw
                              size={14}
                              className={isRetrying ? 'request-spinner' : ''}
                              aria-hidden="true"
                            />
                            {isRetrying ? 'Đang thử lại…' : 'Thử lại gửi'}
                          </button>
                        ) : (
                          <span className="helper-text">
                            {event.delivery_status === 'PUBLISHED' ? 'Đã hoàn tất' : 'Đang xử lý'}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {visibleOutboxEvents.length === 0 && (
              <div className="empty-state">
                <Send size={36} aria-hidden="true" />
                <h2>Không có sự kiện outbox</h2>
                <p>Không tìm thấy sự kiện nào trong hàng đợi outbox phù hợp với bộ lọc hiện tại.</p>
              </div>
            )}
          </div>
          )}
        </section>
      )}
    </div>
  );
}
