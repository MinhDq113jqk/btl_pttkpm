import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, LoaderCircle, RefreshCw } from 'lucide-react';

const EMPTY_OPTIONS = { buildings: [], categories: [], units: [] };
const PRIORITIES = [
  ['LOW', 'Thấp'], ['MEDIUM', 'Trung bình'], ['HIGH', 'Cao'], ['URGENT', 'Khẩn cấp'],
];

const makeIdempotencyKey = () => globalThis.crypto?.randomUUID?.()
  || `service-request-${Date.now()}-${Math.random().toString(16).slice(2)}`;

const errorView = error => {
  if (error?.code === 'ERR-SCOPE-NOTFOUND') return {
    title: 'Không thể dùng phạm vi đã chọn',
    message: 'Tòa nhà hoặc dữ liệu liên quan không còn thuộc phạm vi phiên hiện tại. Hãy đóng biểu mẫu và mở lại để tải phạm vi mới.',
  };
  if (error?.code === 'ERR-NETWORK') return {
    title: 'Mất kết nối tới máy chủ',
    message: 'Yêu cầu chưa được gửi. Kiểm tra mạng rồi thử lại; lần thử lại giữ nguyên mã chống tạo trùng.',
  };
  return { title: 'Chưa thể tạo yêu cầu', message: error?.message || 'Máy chủ chưa thể xử lý yêu cầu này.' };
};

export function CreateServiceRequestForm({ client, onCreated, onClose }) {
  const [buildingId, setBuildingId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [unitId, setUnitId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('MEDIUM');
  const [options, setOptions] = useState(EMPTY_OPTIONS);
  const [optionsState, setOptionsState] = useState({ loading: true, error: null, retry: 0 });
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const errorSummaryRef = useRef(null);
  const intentRef = useRef(null);
  const submittingRef = useRef(false);
  const submitControllerRef = useRef(null);
  const mountedRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      submitControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setOptionsState(previous => ({ ...previous, loading: true, error: null }));
    client.getServiceRequestFormOptions({ buildingId: buildingId || undefined, signal: controller.signal })
      .then(result => {
        setOptions(result);
        setOptionsState(previous => ({ ...previous, loading: false, error: null }));
      })
      .catch(error => {
        if (error?.name !== 'AbortError') {
          setOptions(EMPTY_OPTIONS);
          setOptionsState(previous => ({ ...previous, loading: false, error }));
        }
      });
    return () => controller.abort();
  }, [buildingId, client, optionsState.retry]);

  useEffect(() => {
    if (Object.keys(fieldErrors).length || submitError) errorSummaryRef.current?.focus();
  }, [fieldErrors, submitError]);

  const selectBuilding = event => {
    setBuildingId(event.target.value);
    setCategoryId('');
    setUnitId('');
    setFieldErrors(previous => ({ ...previous, buildingId: undefined, categoryId: undefined, unitId: undefined }));
    setSubmitError(null);
  };
  const validate = () => {
    const errors = {};
    if (!buildingId) errors.buildingId = 'Chọn tòa nhà trong phạm vi được cấp.';
    if (!categoryId) errors.categoryId = 'Chọn loại yêu cầu.';
    if (title.trim().length < 3) errors.title = 'Tiêu đề cần ít nhất 3 ký tự.';
    if (description.trim().length < 3) errors.description = 'Mô tả cần ít nhất 3 ký tự.';
    return errors;
  };
  const submit = async event => {
    event?.preventDefault();
    if (submittingRef.current) return;
    const errors = validate();
    setFieldErrors(errors);
    setSubmitError(null);
    if (Object.keys(errors).length) return;
    const values = {
      category_id: categoryId,
      building_id: buildingId,
      unit_id: unitId || null,
      title: title.trim(),
      description: description.trim(),
      priority,
    };
    const fingerprint = JSON.stringify(values);
    if (!intentRef.current || intentRef.current.fingerprint !== fingerprint) {
      intentRef.current = { fingerprint, idempotencyKey: makeIdempotencyKey() };
    }
    const controller = new AbortController();
    submittingRef.current = true;
    submitControllerRef.current = controller;
    setSubmitting(true);
    try {
      const created = await client.createServiceRequest(values, {
        idempotencyKey: intentRef.current.idempotencyKey,
        signal: controller.signal,
      });
      intentRef.current = null;
      onCreated(created);
    } catch (error) {
      if (error?.name !== 'AbortError') setSubmitError(error);
    } finally {
      if (submitControllerRef.current === controller) {
        submitControllerRef.current = null;
        submittingRef.current = false;
      }
      if (mountedRef.current) setSubmitting(false);
    }
  };
  const errors = Object.entries(fieldErrors).filter(([, message]) => message);
  const shownError = submitError ? errorView(submitError) : null;
  const describe = name => fieldErrors[name] ? `${name}-error` : undefined;

  return <form className="dialog-body service-request-form" onSubmit={submit} noValidate>
    {(errors.length > 0 || shownError) && <div className="error-summary" tabIndex={-1} role="alert" ref={errorSummaryRef}>
      <h3>{shownError?.title || 'Kiểm tra lại biểu mẫu'}</h3>
      {shownError ? <><p>{shownError.message}</p>{submitError?.correlationId && <small>Mã đối chiếu: {submitError.correlationId}</small>}</> : <ul>{errors.map(([name, message]) => <li key={name}><a href={`#service-request-${name}`}>{message}</a></li>)}</ul>}
    </div>}

    {optionsState.loading && <div className="request-state request-loading" role="status"><LoaderCircle className="request-spinner" size={20} aria-hidden="true" /><span>Đang tải lựa chọn theo phạm vi…</span></div>}
    {optionsState.error && <div className="request-state request-error" role="alert"><AlertCircle size={22} aria-hidden="true" /><div><strong>{errorView(optionsState.error).title}</strong><p>{errorView(optionsState.error).message}</p>{optionsState.error.correlationId && <small>Mã đối chiếu: {optionsState.error.correlationId}</small>}</div><button className="button-secondary" type="button" onClick={() => setOptionsState(previous => ({ ...previous, retry: previous.retry + 1 }))}><RefreshCw size={16} aria-hidden="true" />Thử lại</button></div>}

    {!optionsState.loading && !optionsState.error && <>
      {options.buildings.length === 0 ? <div className="empty-state compact-empty"><h3>Không có tòa nhà trong phạm vi tạo yêu cầu</h3><p>Phiên CSKH hiện tại chưa có grant tòa nhà phù hợp. Liên hệ quản trị viên để được cấp quyền.</p></div> : <>
        <p className="context-note">Tòa nhà, loại yêu cầu và căn hộ đều do máy chủ trả về theo phiên hiện tại. Các trường có dấu <span aria-hidden="true">*</span> là bắt buộc.</p>
        <div className="form-grid">
          <div className="form-field"><label className="field-label" htmlFor="service-request-building">Tòa nhà <span aria-hidden="true">*</span></label><select id="service-request-building" value={buildingId} onChange={selectBuilding} aria-invalid={Boolean(fieldErrors.buildingId)} aria-describedby={describe('buildingId')} disabled={submitting}><option value="">Chọn tòa nhà</option>{options.buildings.map(building => <option key={building.id} value={building.id}>{building.code} · {building.name}</option>)}</select>{fieldErrors.buildingId && <p className="field-error" id="buildingId-error">{fieldErrors.buildingId}</p>}</div>
          <div className="form-field"><label className="field-label" htmlFor="service-request-category">Loại yêu cầu <span aria-hidden="true">*</span></label><select id="service-request-category" value={categoryId} onChange={event => { setCategoryId(event.target.value); setFieldErrors(previous => ({ ...previous, categoryId: undefined })); }} aria-invalid={Boolean(fieldErrors.categoryId)} aria-describedby={describe('categoryId')} disabled={submitting || !buildingId}><option value="">{buildingId ? 'Chọn loại yêu cầu' : 'Chọn tòa nhà trước'}</option>{options.categories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select>{fieldErrors.categoryId && <p className="field-error" id="categoryId-error">{fieldErrors.categoryId}</p>}</div>
          <div className="form-field"><label className="field-label" htmlFor="service-request-unit">Căn hộ <span className="optional-label">(không bắt buộc)</span></label><select id="service-request-unit" value={unitId} onChange={event => setUnitId(event.target.value)} disabled={submitting || !buildingId}><option value="">Khu vực chung</option>{options.units.map(unit => <option key={unit.id} value={unit.id}>{unit.unit_number}</option>)}</select></div>
          <div className="form-field"><label className="field-label" htmlFor="service-request-priority">Ưu tiên</label><select id="service-request-priority" value={priority} onChange={event => setPriority(event.target.value)} disabled={submitting}>{PRIORITIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        </div>
        <div className="form-field"><label className="field-label" htmlFor="service-request-title">Tiêu đề <span aria-hidden="true">*</span></label><input id="service-request-title" value={title} onChange={event => { setTitle(event.target.value); setFieldErrors(previous => ({ ...previous, title: undefined })); }} aria-invalid={Boolean(fieldErrors.title)} aria-describedby={describe('title')} disabled={submitting} maxLength={200} />{fieldErrors.title && <p className="field-error" id="title-error">{fieldErrors.title}</p>}</div>
        <div className="form-field"><label className="field-label" htmlFor="service-request-description">Mô tả <span aria-hidden="true">*</span></label><textarea id="service-request-description" value={description} onChange={event => { setDescription(event.target.value); setFieldErrors(previous => ({ ...previous, description: undefined })); }} aria-invalid={Boolean(fieldErrors.description)} aria-describedby={describe('description')} disabled={submitting} maxLength={4000} />{fieldErrors.description && <p className="field-error" id="description-error">{fieldErrors.description}</p>}</div>
      </>}
    </>}

    <div className="dialog-actions service-request-actions"><button className="button-secondary" type="button" onClick={onClose} disabled={submitting}>Hủy</button><button className="button-primary" type="submit" disabled={submitting || optionsState.loading || Boolean(optionsState.error) || options.buildings.length === 0}>{submitting ? <><LoaderCircle className="request-spinner" size={16} aria-hidden="true" />Đang tạo…</> : 'Tạo yêu cầu'}</button></div>
  </form>;
}
