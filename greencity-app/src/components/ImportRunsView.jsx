import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Download, FileSpreadsheet, RefreshCw, Upload } from 'lucide-react';
import './ImportRunsView.css';

const IMPORT_FIELDS = [
  ['unit_number', 'Số căn'],
  ['floor', 'Tầng'],
  ['area_m2', 'Diện tích (m²)'],
  ['status', 'Trạng thái'],
];

const errorMessage = error => error?.message || 'Máy chủ chưa thể xử lý yêu cầu. Hãy thử lại.';

function parseCsvHeader(line) {
  const values = [];
  let current = '';
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"' && quoted && line[index + 1] === '"') {
      current += '"';
      index += 1;
    } else if (character === '"') quoted = !quoted;
    else if (character === ',' && !quoted) {
      values.push(current.trim());
      current = '';
    } else current += character;
  }
  if (quoted) throw new Error('Hàng tiêu đề CSV có dấu ngoặc kép chưa khép.');
  values.push(current.trim());
  const headers = values.map((value, index) => index === 0 ? value.replace(/^\uFEFF/, '') : value);
  if (!headers.length || headers.some(value => !value) || new Set(headers).size !== headers.length) {
    throw new Error('Hàng tiêu đề CSV phải có tên cột không rỗng và không trùng.');
  }
  return headers;
}

function saveDownload(file) {
  const href = URL.createObjectURL(file.blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = file.filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

const formatDate = value => value ? new Date(value).toLocaleString('vi-VN') : '—';
const runStatusLabels = {
  UPLOADED: 'Đã tải lên', VALIDATING: 'Đang kiểm tra', PREVIEWED: 'Đã xem trước',
  APPLYING: 'Đang nhập', APPLIED: 'Đã nhập', FAILED: 'Thất bại',
};

export function ImportRunsView({ account, client }) {
  const [buildingCode, setBuildingCode] = useState('');
  const [mode, setMode] = useState('PARTIAL');
  const [file, setFile] = useState(null);
  const [headers, setHeaders] = useState([]);
  const [mapping, setMapping] = useState({});
  const [run, setRun] = useState(null);
  const [lookupRunId, setLookupRunId] = useState('');
  const [rows, setRows] = useState({ items: [], page: 1, page_size: 100, total: 0 });
  const [busy, setBusy] = useState('');
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');
  const actionKeys = useRef(new Map());
  const selectedMappings = Object.values(mapping);
  const mappingReady = IMPORT_FIELDS.every(([field]) => typeof mapping[field] === 'string' && mapping[field].length > 0)
    && new Set(selectedMappings).size === IMPORT_FIELDS.length;

  const getActionKey = action => {
    if (!actionKeys.current.has(action)) actionKeys.current.set(action, globalThis.crypto.randomUUID());
    return actionKeys.current.get(action);
  };

  const runAction = async (action, callback) => {
    setBusy(action);
    setError(null);
    setNotice('');
    try {
      const result = await callback();
      actionKeys.current.delete(action);
      return result;
    } catch (caught) {
      setError(caught);
      return null;
    } finally {
      setBusy('');
    }
  };

  useEffect(() => {
    if (!run?.id) return undefined;
    const controller = new AbortController();
    client.listUnitCsvImportRows(run.id, { page: rows.page, page_size: rows.page_size, signal: controller.signal })
      .then(setRows)
      .catch(caught => { if (caught?.name !== 'AbortError') setError(caught); });
    return () => controller.abort();
  }, [client, run?.id, run?.version, rows.page, rows.page_size]);

  const onFileChange = async selected => {
    setFile(selected || null);
    setRun(null);
    setLookupRunId('');
    setRows({ items: [], page: 1, page_size: 100, total: 0 });
    actionKeys.current.clear();
    setMapping({});
    setHeaders([]);
    setError(null);
    setNotice('');
    if (!selected) return;
    try {
      const firstLine = (await selected.slice(0, 64 * 1024).text()).split(/\r?\n/, 1)[0];
      const parsed = parseCsvHeader(firstLine);
      setHeaders(parsed);
      setMapping(Object.fromEntries(IMPORT_FIELDS.map(([field]) => [field, parsed.includes(field) ? field : ''])));
    } catch (caught) {
      setError(caught);
    }
  };

  const downloadTemplate = async () => {
    const result = await runAction('template', () => client.downloadUnitImportTemplate());
    if (result) saveDownload(result);
  };

  const exportUnits = async () => {
    const result = await runAction('export', () => client.exportUnitsCsv(buildingCode));
    if (result) saveDownload(result);
  };

  const upload = async () => {
    if (!file || !buildingCode.trim()) return;
    const result = await runAction('upload', () => client.uploadUnitCsvImport(file, {
      buildingCode, mode, idempotencyKey: getActionKey('upload'),
    }));
    if (result) {
      setRun(result);
      setLookupRunId(result.id);
      setRows({ items: [], page: 1, page_size: 100, total: result.total_rows });
      setNotice(`Đã tạo phiên nhập ${result.id}.`);
    }
  };

  const preview = async () => {
    if (!run || !mappingReady) return;
    const result = await runAction(`preview:${run.id}`, () => client.previewUnitCsvImport(run.id, run.version, mapping, {
      idempotencyKey: getActionKey(`preview:${run.id}`),
    }));
    if (result) {
      setRun(result);
      setRows(previous => ({ ...previous, page: 1 }));
      setNotice('Đã kiểm tra dữ liệu. Xem các dòng lỗi/cảnh báo trước khi nhập.');
    }
  };

  const apply = async () => {
    if (!run) return;
    const result = await runAction(`apply:${run.id}`, () => client.applyUnitCsvImport(run.id, run.version, {
      idempotencyKey: getActionKey(`apply:${run.id}`),
    }));
    if (result) {
      setRun(result);
      setNotice(result.status === 'APPLIED' ? `Đã nhập ${result.applied_rows} dòng.` : 'Phiên nhập đã được máy chủ xử lý.');
    }
  };

  const downloadErrors = async () => {
    if (!run) return;
    const result = await runAction('errors', () => client.downloadUnitCsvImportErrors(run.id));
    if (result) saveDownload(result);
  };

  const openRun = async () => {
    if (!lookupRunId.trim()) return;
    const result = await runAction('load-run', () => client.getUnitCsvImport(lookupRunId.trim()));
    if (result) {
      setRun(result);
      setLookupRunId(result.id);
      setRows({ items: [], page: 1, page_size: 100, total: result.total_rows });
      setNotice(`Đã tải lại trạng thái phiên ${result.id}.`);
    }
  };

  const pageCount = Math.max(1, Math.ceil(rows.total / rows.page_size));
  const progress = useMemo(() => [
    { key: 'upload', label: 'Tải CSV', done: Boolean(run) },
    { key: 'preview', label: 'Kiểm tra', done: ['PREVIEWED', 'APPLYING', 'APPLIED'].includes(run?.status) },
    { key: 'apply', label: 'Nhập dữ liệu', done: run?.status === 'APPLIED' },
  ], [run]);

  return <div className="desktop-page import-runs-page">
    <div className="page-heading">
      <div><p className="eyebrow">Dữ liệu căn hộ · {account.site}</p><h1>Nhập dữ liệu căn hộ</h1><p>Tải CSV lên, xem kết quả kiểm tra rồi mới áp dụng vào database.</p></div>
      <button className="button-secondary" type="button" onClick={downloadTemplate} disabled={Boolean(busy)}><Download size={16} aria-hidden="true" />Tải mẫu CSV</button>
    </div>

    <div className="import-progress" aria-label="Các bước nhập CSV">
      {progress.map((step, index) => <div className={`import-progress-step ${step.done ? 'is-done' : ''}`} key={step.key}>
        <span className="import-progress-number">{step.done ? '✓' : index + 1}</span><span>{step.label}</span>
      </div>)}
    </div>

    <div className="import-layout">
      <section className="surface import-panel" aria-labelledby="import-upload-heading">
        <div className="import-panel-heading"><FileSpreadsheet size={21} aria-hidden="true" /><div><h2 id="import-upload-heading">Chọn tòa nhà và tệp</h2><p>Quyền với tòa nhà được máy chủ kiểm tra từ phiên đăng nhập.</p></div></div>
        <label className="field-label" htmlFor="import-building-code">Mã tòa nhà</label>
        <input id="import-building-code" className="import-input" value={buildingCode} onChange={event => setBuildingCode(event.target.value)} maxLength={50} autoComplete="off" />
        <p className="helper-text">Nhập mã tòa trong site đang hoạt động. Không nhập tenant, site ID hoặc role.</p>
        <label className="field-label" htmlFor="unit-import-file">Tệp CSV</label>
        <input id="unit-import-file" className="import-input" type="file" accept=".csv,text/csv" onChange={event => onFileChange(event.target.files?.[0] || null)} />
        {file && <div className="import-file-summary"><strong>{file.name}</strong><span>{Math.ceil(file.size / 1024)} KB · {headers.length} cột</span></div>}
        {headers.length > 0 && <div className="import-mapping">
          <div className="import-panel-heading"><div><h3>Ánh xạ cột CSV</h3><p>Mỗi cột nguồn chỉ dùng cho một trường.</p></div></div>
          {IMPORT_FIELDS.map(([field, label]) => <label className="import-map-row" key={field}>
            <span>{label}</span><select className="import-input" aria-label={`Cột CSV cho ${label}`} value={mapping[field] || ''}
              onChange={event => setMapping(previous => ({ ...previous, [field]: event.target.value }))}>
              <option value="">Chọn cột</option>{headers.map(header => <option value={header} key={header}>{header}</option>)}
            </select>
          </label>)}
        </div>}
        <fieldset className="import-mode">
          <legend>Chính sách áp dụng</legend>
          <label><input type="radio" name="import-mode" value="PARTIAL" checked={mode === 'PARTIAL'} onChange={() => setMode('PARTIAL')} />Nhập dòng hợp lệ</label>
          <label><input type="radio" name="import-mode" value="ALL_OR_NOTHING" checked={mode === 'ALL_OR_NOTHING'} onChange={() => setMode('ALL_OR_NOTHING')} />Chỉ nhập khi toàn bộ tệp hợp lệ</label>
        </fieldset>
        <div className="import-actions">
          <button className="button-primary" type="button" onClick={upload} disabled={Boolean(busy) || !file || !buildingCode.trim()}><Upload size={16} aria-hidden="true" />Tải CSV lên</button>
          {run?.status === 'UPLOADED' && <button className="button-secondary" type="button" onClick={preview} disabled={Boolean(busy) || !mappingReady || run.source_is_quarantined}><RefreshCw size={16} aria-hidden="true" />Kiểm tra dữ liệu</button>}
          {run?.status === 'PREVIEWED' && <button className="button-primary" type="button" onClick={apply} disabled={Boolean(busy) || run.source_is_quarantined}>Áp dụng vào database</button>}
        </div>
      </section>

      <section className="surface import-panel import-run-panel" aria-labelledby="import-run-heading" aria-busy={Boolean(busy)}>
        <div className="import-panel-heading"><div><h2 id="import-run-heading">Kết quả phiên nhập</h2><p>Trạng thái và số dòng do máy chủ trả về.</p></div>{run && <span className={`import-status import-status-${run.status.toLowerCase()}`}>{runStatusLabels[run.status]}</span>}</div>
        <div className="import-run-lookup"><label className="field-label" htmlFor="import-run-id">Mã phiên nhập để xem lại</label><div><input id="import-run-id" className="import-input" value={lookupRunId} onChange={event => setLookupRunId(event.target.value)} autoComplete="off" /><button className="button-secondary" type="button" onClick={openRun} disabled={Boolean(busy) || !lookupRunId.trim()}>Mở phiên</button></div></div>
        {busy && <p className="import-inline-status" role="status">{busy === 'upload' ? 'Đang tải và lưu tệp…' : busy === 'preview' ? 'Đang kiểm tra các dòng…' : busy === 'apply' ? 'Đang áp dụng thay đổi…' : 'Đang tải tệp…'}</p>}
        {!run && !busy && <div className="import-empty"><FileSpreadsheet size={25} aria-hidden="true" /><p>Chưa có phiên nhập. Tải CSV lên để bắt đầu.</p></div>}
        {run && <>
          <p className="import-run-id"><span>Mã phiên</span><code>{run.id}</code></p>
          <dl className="import-run-summary">
            <div><dt>Chế độ</dt><dd>{run.mode === 'PARTIAL' ? 'Nhập dòng hợp lệ' : 'Tất cả hoặc không dòng nào'}</dd></div>
            <div><dt>Tệp</dt><dd>{run.source_filename}</dd></div>
            <div><dt>Dòng hợp lệ</dt><dd>{run.valid_rows}</dd></div>
            <div><dt>Cảnh báo / lỗi</dt><dd>{run.warning_rows} / {run.error_rows}</dd></div>
            <div><dt>Đã nhập</dt><dd>{run.applied_rows}</dd></div>
            <div><dt>Cập nhật</dt><dd>{formatDate(run.applied_at || run.previewed_at || run.failed_at)}</dd></div>
          </dl>
          {run.source_is_quarantined && <p className="import-alert" role="alert">Tệp bị cách ly; không thể xem trước hoặc áp dụng.</p>}
          {run.failure_code && <p className="import-alert" role="alert">Phiên nhập lỗi ({run.failure_code}). Hãy kiểm tra tệp và trạng thái từng dòng.</p>}
          {run.error_file_available && <button className="button-secondary" type="button" onClick={downloadErrors} disabled={Boolean(busy)}><Download size={16} aria-hidden="true" />Tải tệp dòng lỗi</button>}
        </>}
      </section>
    </div>

    {run && <section className="surface import-rows-panel" aria-labelledby="import-rows-heading">
      <div className="import-panel-heading"><div><h2 id="import-rows-heading">Dòng dữ liệu</h2><p>{rows.total} dòng · trang {rows.page} / {pageCount}</p></div></div>
      {rows.items.length === 0 ? <p className="import-empty">Chưa có kết quả dòng để hiển thị. Hãy chạy bước kiểm tra.</p> : <div className="table-scroll" role="region" aria-label="Kết quả từng dòng CSV" tabIndex={0}>
        <table className="import-rows-table"><thead><tr><th scope="col">Dòng</th><th scope="col">Trạng thái</th><th scope="col">Mã lỗi</th><th scope="col">Chi tiết</th></tr></thead><tbody>
          {rows.items.map(row => <tr key={row.row_number}><td>{row.row_number}</td><td><span className={`import-row-status import-row-${row.status.toLowerCase()}`}>{row.status}</span></td>
            <td>{row.issues.map(issue => issue.code).join(', ') || '—'}</td><td>{row.issues.map((issue, index) => <p key={`${issue.code}-${index}`}>{issue.column ? `${issue.column}: ` : ''}{issue.message}</p>)}</td></tr>)}
        </tbody></table>
      </div>}
      {pageCount > 1 && <div className="import-pagination"><button className="button-secondary" disabled={rows.page <= 1 || Boolean(busy)} onClick={() => setRows(previous => ({ ...previous, page: previous.page - 1 }))}>Trang trước</button><span>Trang {rows.page} / {pageCount}</span><button className="button-secondary" disabled={rows.page >= pageCount || Boolean(busy)} onClick={() => setRows(previous => ({ ...previous, page: previous.page + 1 }))}>Trang sau</button></div>}
    </section>}

    {notice && <p className="import-notice" role="status">{notice}</p>}
    {error && <div className="import-alert" role="alert"><strong>Không hoàn tất được thao tác.</strong><span>{errorMessage(error)}</span>{error.correlationId && <small>Mã đối chiếu: {error.correlationId}</small>}<button className="button-text" onClick={() => setError(null)}>Đóng</button></div>}
    <section className="surface import-export-panel" aria-label="Xuất danh sách căn hộ">
      <div><h2>Xuất danh sách căn hộ</h2><p>Tệp chỉ gồm số căn, tầng, diện tích và trạng thái trong tòa nhà được cấp quyền.</p></div>
      <button className="button-secondary" type="button" onClick={exportUnits} disabled={Boolean(busy) || !buildingCode.trim()}><Download size={16} aria-hidden="true" />Xuất CSV tòa nhà này</button>
    </section>
  </div>;
}
