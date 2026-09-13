import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, Building2, Home, LoaderCircle, RefreshCw, Search, ShieldCheck, UserRound } from 'lucide-react';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const STATUS_LABELS = {
  OCCUPIED: 'Đang sử dụng',
  VACANT: 'Đang trống',
  MAINTENANCE: 'Đang bảo trì',
};

const RELATIONSHIP_LABELS = {
  owner: 'Chủ sở hữu',
  tenant: 'Người thuê',
  family_member: 'Thành viên gia đình',
  OWNER: 'Chủ sở hữu',
  TENANT: 'Người thuê',
  RESIDENT: 'Cư dân',
};

const unitErrorCopy = error => {
  if (error?.status === 401 || error?.code === 'ERR-UNAUTHORIZED') return {
    title: 'Phiên đăng nhập đã hết hạn',
    message: 'Vui lòng đăng nhập lại để tiếp tục tra cứu căn hộ.',
  };
  if (error?.code === 'ERR-SCOPE-NOTFOUND') return {
    title: 'Không tìm thấy căn hộ trong phạm vi',
    message: 'Unit ID không tồn tại hoặc phiên hiện tại không được phép xem căn hộ này.',
  };
  if (error?.code === 'ERR-NETWORK') return {
    title: 'Mất kết nối tới máy chủ',
    message: 'Chưa thể tải hồ sơ căn hộ. Kiểm tra kết nối rồi thử lại.',
  };
  return {
    title: 'Không tải được căn hộ 360°',
    message: error?.message || 'Máy chủ chưa thể trả dữ liệu. Vui lòng thử lại.',
  };
};

const displayValue = (value, fallback = 'Ẩn theo quyền phiên') => (
  value === null || value === undefined || value === '' ? fallback : value
);

export function Unit360View({ client, scopeLabel = 'Phạm vi hiện tại' }) {
  const [unitId, setUnitId] = useState('');
  const [fieldError, setFieldError] = useState('');
  const [lastUnitId, setLastUnitId] = useState('');
  const [state, setState] = useState({ status: 'idle', data: null, error: null });
  const controllerRef = useRef(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const loadUnit = async id => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLastUnitId(id);
    setState({ status: 'loading', data: null, error: null });
    try {
      const data = await client.getUnit360(id, { signal: controller.signal });
      if (controllerRef.current !== controller || controller.signal.aborted) return;
      setState({ status: 'success', data, error: null });
    } catch (error) {
      if (error?.name === 'AbortError' || controller.signal.aborted || controllerRef.current !== controller) return;
      setState({ status: 'error', data: null, error });
    }
  };

  const submit = event => {
    event.preventDefault();
    const normalized = unitId.trim();
    if (!UUID_PATTERN.test(normalized)) {
      setFieldError('Unit ID phải là UUID hợp lệ, ví dụ 123e4567-e89b-42d3-a456-426614174000.');
      return;
    }
    setFieldError('');
    loadUnit(normalized);
  };

  const errorCopy = unitErrorCopy(state.error);
  const unit = state.data;

  return <div className="desktop-page unit-360-page">
    <div className="page-heading"><div><p className="eyebrow">Hồ sơ không gian</p><h1>Tra cứu Căn hộ 360°</h1><p>{scopeLabel} · Máy chủ tự áp dụng tenant, site, tòa nhà và projection theo phiên.</p></div><span className="subtle-badge">Chỉ đọc</span></div>

    <section className="surface unit-search-panel" aria-label="Tra cứu căn hộ theo Unit ID">
      <form onSubmit={submit} noValidate>
        <label className="field-label" htmlFor="unit-lookup-id">Unit ID</label>
        <div className="unit-search-row">
          <div className="search-field"><Search size={17} aria-hidden="true" /><input id="unit-lookup-id" name="unit_id" autoComplete="off" spellCheck="false" aria-describedby="unit-id-help unit-id-error" aria-invalid={Boolean(fieldError)} placeholder="Nhập UUID của căn hộ" value={unitId} onChange={event => { setUnitId(event.target.value); if (fieldError) setFieldError(''); }} /></div>
          <button className="button-primary unit-search-submit" type="submit" disabled={state.status === 'loading'}>{state.status === 'loading' ? <LoaderCircle className="request-spinner" size={17} aria-hidden="true" /> : <Search size={17} aria-hidden="true" />}Tra cứu</button>
        </div>
        <p id="unit-id-help" className="helper-text">Chỉ Unit ID được gửi lên API. Giao diện không gửi tenant, role, site hay building scope.</p>
        {fieldError && <p id="unit-id-error" className="field-error" role="alert"><AlertCircle size={15} aria-hidden="true" />{fieldError}</p>}
      </form>
    </section>

    {state.status === 'idle' && <section className="surface empty-state unit-empty-state"><Home size={34} aria-hidden="true" /><h2>Chưa có căn hộ được chọn</h2><p>Nhập Unit ID để tải hồ sơ 360° trong đúng phạm vi mà phiên hiện tại được phép xem.</p></section>}
    {state.status === 'loading' && <section className="surface request-state request-loading unit-request-state" role="status" aria-live="polite"><LoaderCircle className="request-spinner" size={20} aria-hidden="true" /><span>Đang tải căn hộ đúng phạm vi…</span></section>}
    {state.status === 'error' && <section className="surface request-state request-error unit-request-state" role="alert"><AlertCircle size={22} aria-hidden="true" /><div><strong>{errorCopy.title}</strong><p>{errorCopy.message}</p>{state.error?.correlationId && <small>Mã đối chiếu: {state.error.correlationId}</small>}</div><button className="button-secondary" type="button" onClick={() => loadUnit(lastUnitId)}><RefreshCw size={16} aria-hidden="true" />Thử lại</button></section>}

    {state.status === 'success' && unit && <div className="unit-result-grid">
      <section className="surface unit-profile" aria-labelledby="unit-profile-title">
        <div className="section-heading"><div><p className="eyebrow">{unit.site_code} · {unit.building_code}</p><h2 id="unit-profile-title">Căn {unit.unit_number}</h2><p>{unit.building_name} · {unit.site_name}</p></div><Home size={24} aria-hidden="true" /></div>
        <dl className="unit-summary-grid">
          <div><dt>Tầng</dt><dd>{unit.floor}</dd></div>
          <div><dt>Diện tích</dt><dd>{unit.area_m2 === null ? 'Ẩn theo quyền phiên' : `${unit.area_m2} m²`}</dd></div>
          <div><dt>Trạng thái</dt><dd>{displayValue(STATUS_LABELS[unit.status] || unit.status)}</dd></div>
          <div><dt>Phiên bản hồ sơ</dt><dd>{unit.version}</dd></div>
          <div><dt>Unit ID</dt><dd className="technical-value">{unit.id}</dd></div>
          <div><dt>Building ID</dt><dd className="technical-value">{unit.building_id}</dd></div>
        </dl>
        <p className="context-note"><Building2 size={16} aria-hidden="true" />Thông tin hiển thị là projection do backend quyết định cho đúng record và quyền phiên.</p>
      </section>

      <section className="surface unit-residents" aria-labelledby="unit-residents-title">
        <div className="section-heading"><div><h2 id="unit-residents-title">Cư dân liên quan</h2><p>{unit.residents_visible ? `${unit.residents.length} hồ sơ được phép hiển thị` : 'Danh sách được ẩn theo quyền phiên'}</p></div><UserRound size={22} aria-hidden="true" /></div>
        {!unit.residents_visible && <div className="unit-projection-note"><ShieldCheck size={26} aria-hidden="true" /><div><strong>Thông tin cư dân đã được ẩn</strong><p>Điều này không có nghĩa căn hộ đang trống. Backend không trả quan hệ cư dân cho vai trò hiện tại.</p></div></div>}
        {unit.residents_visible && unit.residents.length === 0 && <div className="empty-state unit-resident-empty"><UserRound size={28} aria-hidden="true" /><h3>Chưa có cư dân đang hiển thị</h3><p>Hồ sơ căn hộ hợp lệ nhưng API không trả quan hệ cư dân đang hoạt động trong projection hiện tại.</p></div>}
        {unit.residents_visible && unit.residents.length > 0 && <ul className="unit-resident-list">{unit.residents.map(resident => <li key={resident.person_id}>
          <span className="unit-resident-avatar" aria-hidden="true">{resident.full_name.trim().charAt(0).toUpperCase()}</span>
          <div><strong>{resident.full_name}</strong><span>{RELATIONSHIP_LABELS[resident.relationship_type] || resident.relationship_type}{resident.is_active ? ' · Đang hiệu lực' : ' · Hết hiệu lực'}</span><small>{resident.phone_masked} · {resident.email_masked}</small></div>
        </li>)}</ul>}
      </section>
    </div>}
  </div>;
}
