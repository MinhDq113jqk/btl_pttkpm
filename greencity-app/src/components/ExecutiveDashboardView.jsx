import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  Coins,
  Copy,
  ExternalLink,
  History,
  Info,
  LoaderCircle,
  MapPin,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Wrench,
  WifiOff,
  X,
} from 'lucide-react';

const formatTime = value => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? '—'
    : new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(date);
};

const formatCurrencyVnd = amount => {
  if (typeof amount !== 'number') return '0 ₫';
  return new Intl.NumberFormat('vi-VN').format(amount) + ' ₫';
};

const METRIC_CONFIG = {
  sla_overdue: {
    title: 'Yêu cầu CSKH quá hạn SLA',
    shortTitle: 'Quá hạn SLA',
    description: 'Yêu cầu dịch vụ quá hạn cam kết giải quyết tại mốc cutoff.',
    icon: Clock,
    colorClass: 'metric-sla',
    unit: 'vụ',
  },
  maintenance_due: {
    title: 'Bảo trì kỹ thuật đến hạn',
    shortTitle: 'Bảo trì đến hạn',
    description: 'Kế hoạch bảo trì máy phát, cơ điện chưa hoàn thành tại cutoff.',
    icon: Wrench,
    colorClass: 'metric-maintenance',
    unit: 'hạng mục',
  },
  cleaning_rework: {
    title: 'Vệ sinh cần làm lại (Rework)',
    shortTitle: 'Vệ sinh làm lại',
    description: 'Ca vệ sinh có checklist không đạt yêu cầu (REWORK_REQUIRED).',
    icon: Sparkles,
    colorClass: 'metric-cleaning',
    unit: 'ca',
  },
  open_incidents: {
    title: 'Sự cố an ninh đang mở',
    shortTitle: 'Sự cố đang mở',
    description: 'Sự cố PCCC, an ninh chưa được đóng/giải quyết tại cutoff.',
    icon: ShieldAlert,
    colorClass: 'metric-security',
    unit: 'vụ',
  },
  ar_debt: {
    title: 'Tổng công nợ quá hạn (AR)',
    shortTitle: 'Công nợ quá hạn',
    description: 'Số dư nợ thực tế SUM(debit - credit) từ sổ cái ArLedgerEntry (INV-01).',
    icon: Coins,
    colorClass: 'metric-finance',
    unit: 'VND',
  },
};

export function ExecutiveDashboardView({ account, client, onToast, onNavigate }) {
  const isApiMode = Boolean(client?.getDashboard && client?.hasSession?.());
  const [asOf, setAsOf] = useState(() => new Date().toISOString());
  const [customAsOf, setCustomAsOf] = useState('');
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isOffline, setIsOffline] = useState(typeof navigator !== 'undefined' && !navigator.onLine);

  // Drill-down states
  const [drillDownOpen, setDrillDownOpen] = useState(false);
  const [activeMetric, setActiveMetric] = useState(null);
  const [drillDownData, setDrillDownData] = useState(null);
  const [drillDownLoading, setDrillDownLoading] = useState(false);
  const [drillDownError, setDrillDownError] = useState(null);

  // Audit timeline states
  const [auditOpen, setAuditOpen] = useState(false);
  const [auditCorrelationId, setAuditCorrelationId] = useState('');
  const [auditResource, setAuditResource] = useState(null);
  const [auditEvents, setAuditEvents] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState(null);

  const errorRef = useRef(null);
  const drillDownDialogRef = useRef(null);
  const auditDialogRef = useRef(null);
  const lastActiveElementRef = useRef(null);
  const auditLastActiveElementRef = useRef(null);
  const dashboardRequestRef = useRef(0);
  const auditSearchId = useId();

  const loadDashboard = useCallback(async cutoffToUse => {
    const requestId = dashboardRequestRef.current + 1;
    dashboardRequestRef.current = requestId;
    setLoading(true);
    setError(null);
    try {
      if (!isApiMode) {
        throw new Error('Chế độ API chưa sẵn sàng hoặc phiên đăng nhập không tồn tại.');
      }
      const data = await client.getDashboard({ asOf: cutoffToUse });
      if (requestId !== dashboardRequestRef.current) return;
      setDashboard(data);
      setIsOffline(false);
    } catch (err) {
      if (requestId !== dashboardRequestRef.current) return;
      // RULE: Do NOT silently fallback to mock data when in API mode!
      setError({
        message: err?.code === 'ERR-NETWORK'
          ? 'Mất kết nối tới máy chủ. Vui lòng kiểm tra đường truyền và thử lại.'
          : err?.message || 'Không thể tải dữ liệu điều hành từ máy chủ.',
        correlationId: err?.correlationId || '',
        code: err?.code || 'ERR-FETCH',
      });
      setDashboard(null);
      if (err?.code === 'ERR-NETWORK') setIsOffline(true);
    } finally {
      if (requestId === dashboardRequestRef.current) setLoading(false);
    }
  }, [client, isApiMode]);

  useEffect(() => {
    loadDashboard(asOf);
  }, [asOf, loadDashboard]);

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
    if (error) {
      errorRef.current?.focus();
    }
  }, [error]);

  // Handle Quick Presets
  const setNowAsOf = () => {
    const nowIso = new Date().toISOString();
    setAsOf(nowIso);
    setCustomAsOf('');
  };

  const setStartOfDayAsOf = () => {
    const now = new Date();
    now.setUTCHours(0, 0, 0, 0);
    const startIso = now.toISOString();
    setAsOf(startIso);
    setCustomAsOf('');
  };

  const handleApplyCustomAsOf = e => {
    e.preventDefault();
    if (!customAsOf.trim()) return;
    const parsed = new Date(customAsOf);
    if (Number.isNaN(parsed.valueOf())) {
      onToast?.('Định dạng thời gian không hợp lệ. Vui lòng thử lại.');
      return;
    }
    const isoString = parsed.toISOString();
    setAsOf(isoString);
  };

  // Open Drill-Down
  const handleOpenDrillDown = async metricKey => {
    lastActiveElementRef.current = document.activeElement;
    setActiveMetric(metricKey);
    setDrillDownOpen(true);
    setDrillDownLoading(true);
    setDrillDownError(null);
    setDrillDownData(null);
    try {
      const response = await client.getDashboardDrillDown(metricKey, { asOf });
      setDrillDownData(response);
    } catch (err) {
      setDrillDownError({
        message: err?.message || 'Không thể tải chi tiết bản ghi nguồn.',
        correlationId: err?.correlationId || '',
      });
    } finally {
      setDrillDownLoading(false);
    }
  };

  const handleCloseDrillDown = () => {
    setDrillDownOpen(false);
    setActiveMetric(null);
    setDrillDownData(null);
    lastActiveElementRef.current?.focus();
  };

  // Open Audit Timeline
  const handleOpenAudit = async ({ correlationId = '', resourceType, resourceId } = {}) => {
    auditLastActiveElementRef.current = document.activeElement;
    setAuditCorrelationId(correlationId || '');
    setAuditResource(resourceId ? { resourceType, resourceId } : null);
    setAuditOpen(true);
    setAuditLoading(true);
    setAuditError(null);
    setAuditEvents([]);
    try {
      const response = await client.listAuditEvents({
        correlationId: correlationId || undefined,
        resourceType,
        resourceId,
        asOf,
        limit: 50,
      });
      setAuditEvents(response.items || []);
    } catch (err) {
      setAuditError({
        message: err?.message || 'Không thể tải sự kiện kiểm toán.',
        correlationId: err?.correlationId || '',
      });
    } finally {
      setAuditLoading(false);
    }
  };

  const handleCloseAudit = () => {
    setAuditOpen(false);
    setAuditEvents([]);
    auditLastActiveElementRef.current?.focus();
  };

  useEffect(() => {
    if (drillDownOpen) drillDownDialogRef.current?.focus();
  }, [drillDownOpen]);

  useEffect(() => {
    if (auditOpen) auditDialogRef.current?.focus();
  }, [auditOpen]);

  // Keyboard accessibility: ESC to close modals
  useEffect(() => {
    const handleKeyDown = e => {
      if (e.key === 'Escape') {
        if (auditOpen) {
          handleCloseAudit();
        } else if (drillDownOpen) {
          handleCloseDrillDown();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [auditOpen, drillDownOpen]);

  return (
    <div className="desktop-page executive-dashboard">
      {/* Scope & Control Toolbar */}
      <section className="surface executive-scope-banner" aria-label="Phạm vi điều hành và mốc thời gian">
        <div className="scope-info-group">
          <div className="scope-icon-wrap">
            <Activity size={24} aria-hidden="true" />
          </div>
          <div>
            <span className="scope-eyebrow">BẢNG ĐIỀU HÀNH TỔNG HỢP CAP-BI (R5)</span>
            <h1 className="scope-site-title">{account.site}</h1>
            <p className="scope-desc">
              Theo dõi 5 chỉ số hiệu năng (KPI) cốt lõi tại mốc thời gian chốt sổ. Đối soát chính xác 100% từng bản ghi nguồn (AC-25).
            </p>
          </div>
        </div>

        <div className="cutoff-toolbar">
          <div className="cutoff-indicator">
            <Calendar size={16} aria-hidden="true" />
            <span>Mốc cutoff: <strong>{formatTime(asOf)}</strong></span>
            <span className="cutoff-iso-badge" title={asOf}>UTC</span>
          </div>

          <div className="cutoff-actions">
            <button
              type="button"
              className="button-secondary btn-sm"
              onClick={setNowAsOf}
              disabled={loading}
              title="Cập nhật mốc cutoff về thời điểm hiện tại"
            >
              Hiện tại
            </button>
            <button
              type="button"
              className="button-secondary btn-sm"
              onClick={setStartOfDayAsOf}
              disabled={loading}
              title="Lấy mốc 00:00:00 UTC đầu ngày"
            >
              Đầu ngày UTC
            </button>
            <button
              type="button"
              className="button-primary btn-sm"
              onClick={() => loadDashboard(asOf)}
              disabled={loading}
              title="Tải lại dữ liệu theo mốc cutoff hiện tại"
            >
              <RefreshCw size={14} className={loading ? 'request-spinner' : ''} aria-hidden="true" />
              Làm mới
            </button>
          </div>
        </div>
      </section>

      {isOffline && (
        <div className="surface request-state request-error" role="alert">
          <WifiOff size={24} aria-hidden="true" />
          <div>
            <strong>Đang ngoại tuyến</strong>
            <p>Không thể xác nhận KPI mới từ máy chủ. Dữ liệu cũ không được hiển thị như một snapshot hiện tại.</p>
          </div>
          <button type="button" className="button-secondary" onClick={() => loadDashboard(asOf)} disabled={loading}>
            <RefreshCw size={14} aria-hidden="true" />
            Kiểm tra lại
          </button>
        </div>
      )}

      {/* Error state: RULE: NO SILENT FALLBACK TO MOCK */}
      {error && (
        <div ref={errorRef} className="surface request-state request-error" role="alert" tabIndex={-1}>
          <AlertCircle size={28} aria-hidden="true" />
          <div className="error-body">
            <strong>Không thể tải bảng điều hành KPI</strong>
            <p>{error.message}</p>
            {error.correlationId && (
              <span className="helper-text">Mã đối chiếu: <code>{error.correlationId}</code></span>
            )}
          </div>
          <button type="button" className="button-secondary" onClick={() => loadDashboard(asOf)}>
            <RefreshCw size={14} aria-hidden="true" />
            Thử lại
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && !error && (
        <div className="surface request-state request-loading" role="status" aria-busy="true">
          <LoaderCircle size={28} className="request-spinner" aria-hidden="true" />
          <span>Đang tính toán các chỉ số KPI theo mốc cutoff {formatTime(asOf)}…</span>
        </div>
      )}

      {/* 5 KPI Metric Cards (AC-25) */}
      {!loading && !error && dashboard && (
        <section className="kpi-grid" aria-label="5 Chỉ số điều hành cốt lõi">
          {Object.entries(METRIC_CONFIG).map(([key, config]) => {
            const Icon = config.icon;
            const isDebt = key === 'ar_debt';
            const rawValue = isDebt
              ? (dashboard.ar_debt_vnd || 0)
              : key === 'open_incidents'
                ? (dashboard.open_incident_count || 0)
                : (dashboard[`${key}_count`] || 0);
            const displayValue = isDebt ? formatCurrencyVnd(rawValue) : rawValue;
            const isWarning = rawValue > 0;

            return (
              <button
                type="button"
                key={key}
                className={`kpi-card surface ${config.colorClass} ${isWarning ? 'is-alert' : 'is-clear'}`}
                onClick={() => handleOpenDrillDown(key)}
                aria-haspopup="dialog"
                aria-label={`${config.title}: ${displayValue}. Nhấn để xem bản ghi nguồn.`}
              >
                <div className="kpi-card-header">
                  <div className="kpi-icon-box">
                    <Icon size={20} aria-hidden="true" />
                  </div>
                  <span className={`kpi-status-tag ${isWarning ? 'status-rose' : 'status-emerald'}`}>
                    {isWarning ? 'Cần chú ý' : 'Đạt chuẩn'}
                  </span>
                </div>

                <div className="kpi-value-wrap">
                  <span className="kpi-number">{displayValue}</span>
                  {!isDebt && <span className="kpi-unit">{config.unit}</span>}
                </div>

                <h2 className="kpi-title">{config.title}</h2>
                <p className="kpi-desc">{config.description}</p>

                <div className="kpi-footer">
                  <span className="kpi-link-text">
                    Đối soát bản ghi nguồn
                    <ArrowRight size={14} aria-hidden="true" />
                  </span>
                </div>
              </button>
            );
          })}
        </section>
      )}

      {/* Quick Navigation Footer */}
      <div className="dashboard-quick-footer surface">
        <div className="audit-entry-callout">
          <History size={20} aria-hidden="true" />
          <div>
            <strong>Truy vết sự kiện kiểm toán (Audit Explorer)</strong>
            <p>Tra cứu nguồn gốc, dòng thời gian và actor thay đổi dữ liệu theo Correlation ID.</p>
          </div>
        </div>
        <button
          type="button"
          className="button-secondary"
          onClick={() => handleOpenAudit()}
        >
          <Search size={14} aria-hidden="true" />
          Mở Audit Explorer
        </button>
      </div>

      {/* Drill-down Dialog Modal */}
      {drillDownOpen && (
        <div
          className="dialog-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="drilldown-title"
          onClick={e => { if (e.target === e.currentTarget) handleCloseDrillDown(); }}
        >
          <div ref={drillDownDialogRef} className="surface drilldown-dialog" tabIndex={-1}>
            <div className="drilldown-header">
              <div>
                <span className="dialog-eyebrow">ĐỐI SOÁT BẢN GHI NGUỒN (AC-25)</span>
                <h2 id="drilldown-title">
                  {METRIC_CONFIG[activeMetric]?.title || 'Chi tiết bản ghi'}
                </h2>
                <p className="dialog-cutoff-note">
                  Dữ liệu được trích xuất chính xác theo mốc cutoff <strong>{formatTime(asOf)}</strong>.
                </p>
              </div>
              <button
                type="button"
                className="button-text dialog-close-btn"
                onClick={handleCloseDrillDown}
                aria-label="Đóng bảng chi tiết"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>

            <div className="drilldown-content">
              {drillDownLoading && (
                <div className="request-state request-loading" role="status" aria-busy="true">
                  <LoaderCircle size={24} className="request-spinner" aria-hidden="true" />
                  <span>Đang tải các bản ghi nguồn cấu thành chỉ số…</span>
                </div>
              )}

              {drillDownError && (
                <div className="surface request-state request-error" role="alert">
                  <AlertCircle size={24} aria-hidden="true" />
                  <div>
                    <strong>Lỗi tải bản ghi đối soát</strong>
                    <p>{drillDownError.message}</p>
                    {drillDownError.correlationId && (
                      <span className="helper-text">Mã đối chiếu: {drillDownError.correlationId}</span>
                    )}
                  </div>
                </div>
              )}

              {!drillDownLoading && !drillDownError && drillDownData && (
                <>
                  <div className="drilldown-summary-strip">
                    <span>Tổng số bản ghi đối soát: <strong>{drillDownData.items.length}</strong></span>
                    {activeMetric === 'ar_debt' && (
                      <span>
                        Tổng công nợ cộng gộp:{' '}
                        <strong>
                          {formatCurrencyVnd(drillDownData.items.reduce((acc, cur) => acc + (cur.amount_vnd || 0), 0))}
                        </strong>
                      </span>
                    )}
                  </div>

                  <div className="table-wrapper">
                    <table className="data-table drilldown-table">
                      <thead>
                        <tr>
                          <th>Mã tham chiếu</th>
                          <th>Tiêu đề / Nội dung</th>
                          <th>Loại tài nguyên</th>
                          <th>Trạng thái</th>
                          <th>Thời điểm mốc</th>
                          {activeMetric === 'ar_debt' && <th>Số nợ (VND)</th>}
                          <th>Hành động</th>
                        </tr>
                      </thead>
                      <tbody>
                        {drillDownData.items.map(item => (
                          <tr key={`${item.resource_type}-${item.resource_id}`}>
                            <td>
                              <strong>{item.reference}</strong>
                            </td>
                            <td>
                              <span>{item.title}</span>
                            </td>
                            <td>
                              <span className="resource-pill">{item.resource_type}</span>
                            </td>
                            <td>
                              <span className="status-badge status-blue">
                                {item.status || '—'}
                              </span>
                            </td>
                            <td>
                              <span>{formatTime(item.occurred_at)}</span>
                            </td>
                            {activeMetric === 'ar_debt' && (
                              <td>
                                <strong className="debt-amount">
                                  {formatCurrencyVnd(item.amount_vnd || 0)}
                                </strong>
                              </td>
                            )}
                            <td>
                              <button
                                type="button"
                                className="button-text btn-xs"
                                onClick={() => handleOpenAudit({
                                  resourceType: item.resource_type,
                                  resourceId: item.resource_id,
                                })}
                                aria-label="Xem lịch sử thay đổi của tài nguyên này"
                                title="Xem lịch sử thay đổi của tài nguyên này"
                              >
                                <History size={13} aria-hidden="true" />
                                Audit
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    {drillDownData.items.length === 0 && (
                      <div className="empty-state">
                        <CheckCircle2 size={36} className="text-emerald" aria-hidden="true" />
                        <h3>Không có bản ghi tồn đọng</h3>
                        <p>Toàn bộ mục trong danh mục này đều đạt chuẩn tại mốc cutoff {formatTime(asOf)}.</p>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>

            <div className="drilldown-footer">
              <span className="helper-text">Nhấn Esc hoặc bấm nút Đóng để quay lại Dashboard</span>
              <button type="button" className="button-secondary" onClick={handleCloseDrillDown}>
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Audit Explorer Dialog Modal */}
      {auditOpen && (
        <div
          className="dialog-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="audit-title"
          onClick={e => { if (e.target === e.currentTarget) handleCloseAudit(); }}
        >
          <div ref={auditDialogRef} className="surface audit-dialog" tabIndex={-1}>
            <div className="audit-header">
              <div>
                <span className="dialog-eyebrow">DÒNG THỜI GIAN & ĐỐI SOÁT GIAO DỊCH</span>
                <h2 id="audit-title">Nhật ký kiểm toán (Audit Explorer)</h2>
                <p className="dialog-cutoff-note">
                  Truy vết minh bạch từng thay đổi và lệnh nghiệp vụ theo chuẩn bảo mật SEC-04.
                </p>
              </div>
              <button
                type="button"
                className="button-text dialog-close-btn"
                onClick={handleCloseAudit}
                aria-label="Đóng cửa sổ kiểm toán"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>

            <div className="audit-filter-bar">
              <div className="search-input-wrap">
                <Search size={16} aria-hidden="true" />
                <label className="sr-only" htmlFor={auditSearchId}>Lọc Audit Explorer theo Correlation ID</label>
                <input
                  id={auditSearchId}
                  type="text"
                  placeholder="Lọc theo Correlation ID (UUID)…"
                  value={auditCorrelationId}
                  onChange={e => setAuditCorrelationId(e.target.value)}
                  className="input-search"
                />
              </div>
              <button
                type="button"
                className="button-primary btn-sm"
                onClick={() => handleOpenAudit({ correlationId: auditCorrelationId.trim() })}
                disabled={auditLoading}
              >
                Tìm kiếm
              </button>
            </div>

            {auditResource && (
              <p className="helper-text">
                Đang truy vết tài nguyên: <code>{auditResource.resourceType}</code> · <code>{auditResource.resourceId}</code>
              </p>
            )}

            <div className="audit-content">
              {auditLoading && (
                <div className="request-state request-loading" role="status" aria-busy="true">
                  <LoaderCircle size={24} className="request-spinner" aria-hidden="true" />
                  <span>Đang tải chuỗi sự kiện kiểm toán…</span>
                </div>
              )}

              {auditError && (
                <div className="surface request-state request-error" role="alert">
                  <AlertCircle size={24} aria-hidden="true" />
                  <div>
                    <strong>Không thể tải sự kiện audit</strong>
                    <p>{auditError.message}</p>
                    {auditError.correlationId && (
                      <span className="helper-text">Mã đối chiếu: {auditError.correlationId}</span>
                    )}
                  </div>
                </div>
              )}

              {!auditLoading && !auditError && (
                <div className="audit-timeline-stream">
                  {auditEvents.map(event => (
                    <div key={event.id} className="audit-timeline-card">
                      <div className="timeline-badge-column">
                        <span className="timeline-dot" />
                        <span className="timeline-line" />
                      </div>
                      <div className="timeline-card-content surface">
                        <div className="timeline-card-head">
                          <div className="timeline-action-group">
                            <strong className="timeline-event-type">{event.event_type}</strong>
                            <span className="timeline-action-tag">{event.action}</span>
                          </div>
                          <span className="timeline-time">{formatTime(event.created_at)}</span>
                        </div>

                        <div className="timeline-meta-row">
                          <span>Tài nguyên: <code>{event.resource_type}</code></span>
                          <span>ID: <code>{event.resource_id?.slice?.(0, 8)}…</code></span>
                          {event.actor_account_id && (
                            <span>Actor: <code>{event.actor_account_id?.slice?.(0, 8)}…</code></span>
                          )}
                        </div>

                        <div className="timeline-corr-row">
                          <span className="corr-label">Correlation ID:</span>
                          <code>{event.correlation_id}</code>
                          <button
                            type="button"
                            className="button-text btn-copy"
                            onClick={() => {
                              navigator.clipboard?.writeText?.(event.correlation_id);
                              onToast?.('Đã sao chép Correlation ID.');
                            }}
                            title="Sao chép Correlation ID"
                          >
                            <Copy size={12} aria-hidden="true" />
                          </button>
                        </div>

                        {event.reason && (
                          <div className="timeline-reason">
                            <span>Lý do: {event.reason}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}

                  {auditEvents.length === 0 && (
                    <div className="empty-state">
                      <History size={36} aria-hidden="true" />
                      <h3>Không tìm thấy sự kiện kiểm toán</h3>
                      <p>Chưa có sự kiện nào phù hợp với bộ lọc Correlation ID hiện tại.</p>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="audit-footer">
              <span className="helper-text">Nhấn Esc hoặc bấm nút Đóng để quay lại</span>
              <button type="button" className="button-secondary" onClick={handleCloseAudit}>
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
