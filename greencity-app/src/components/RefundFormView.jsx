import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Save, CheckCircle2, UploadCloud, Trash2, FileText, AlertCircle } from 'lucide-react';
import { sampleRefundCase } from '../data/mockData';
import { createRefundForm, validateRefund, formatVND, paymentLabels, validateAttachment } from '../data/refundForm';

function Field({ id, label, required, error, hint, children }) {
  return <div className="form-field"><label htmlFor={id} className="field-label">{label}{required && <span aria-hidden="true"> *</span>}</label>{children}{hint && <p className="helper-text" id={`${id}-hint`}>{hint}</p>}{error && <p id={`${id}-error`} className="field-error"><AlertCircle size={14} aria-hidden="true" />{error}</p>}</div>;
}

export function RefundFormView({ onBack, onSaveDraft, onSubmitForm, initialData, onDirtyChange }) {
  const [formData, setFormData] = useState(() => initialData || createRefundForm());
  const [savedSnapshot, setSavedSnapshot] = useState(() => JSON.stringify(initialData || createRefundForm()));
  const [errors, setErrors] = useState({});
  const [uploadError, setUploadError] = useState('');
  const [saveMessage, setSaveMessage] = useState(initialData ? 'Đã khôi phục bản nháp của tab này.' : '');
  const summaryRef = useRef(null);
  const dirty = JSON.stringify(formData) !== savedSnapshot;
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);

  const update = (field, value) => {
    setFormData(previous => ({ ...previous, [field]: value }));
    setSaveMessage('');
    if (errors[field]) setErrors(previous => ({ ...previous, [field]: undefined }));
  };
  const blur = field => setErrors(previous => ({ ...previous, [field]: validateRefund(formData)[field] }));
  const inputProps = field => ({
    id: field, value: formData[field], onChange: event => update(field, event.target.value),
    onBlur: () => blur(field), 'aria-invalid': errors[field] ? true : undefined,
    'aria-describedby': [errors[field] && `${field}-error`, field === 'refundAmount' && 'refundAmount-hint'].filter(Boolean).join(' ') || undefined,
  });
  const save = () => {
    if (onSaveDraft(formData)) {
      setSavedSnapshot(JSON.stringify(formData));
      setSaveMessage('Đã lưu nội dung phiếu trong tab này. Tệp chọn thêm cần chọn lại sau khi tải lại.');
    }
  };
  const submit = event => {
    event.preventDefault();
    const nextErrors = validateRefund(formData);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      requestAnimationFrame(() => summaryRef.current?.focus());
      return;
    }
    onSubmitForm({ ...formData, refundAmount: Number(formData.refundAmount) });
  };
  const addFiles = files => {
    const added = [];
    const problems = [];
    Array.from(files).forEach(file => {
      const error = validateAttachment(file);
      if (error) problems.push(`${file.name}: ${error}`);
      else added.push({ id: crypto.randomUUID(), name: file.name, size: `${(file.size / 1024 / 1024).toFixed(2)} MB`, local: true });
    });
    setUploadError(problems.join(' '));
    if (added.length) {
      setFormData(previous => ({ ...previous, attachments: [...previous.attachments, ...added] }));
      setErrors(previous => ({ ...previous, attachments: undefined }));
    }
  };
  const invalidFields = Object.entries(errors).filter(([, value]) => value);
  const { resident, reason, financials } = sampleRefundCase;

  return <div className="desktop-page refund-page">
    <div className="page-heading"><div><p className="eyebrow">Tài chính · {sampleRefundCase.caseCode}</p><h1>Kiểm tra phiếu hoàn tiền</h1><p>Đối chiếu thông tin, lưu nháp hoặc xem lại trước khi xác nhận.</p></div><span className="subtle-badge">{dirty ? 'Có thay đổi chưa lưu' : initialData ? 'Bản nháp' : 'Hồ sơ mẫu'}</span></div>
    <form onSubmit={submit} noValidate>
      {invalidFields.length > 0 && <div ref={summaryRef} tabIndex={-1} role="alert" className="error-summary"><h2>Cần kiểm tra {invalidFields.length} mục</h2><ul>{invalidFields.map(([field, error]) => <li key={field}><a href={`#${field}`} onClick={event => { event.preventDefault(); document.getElementById(field)?.focus(); }}>{error}</a></li>)}</ul></div>}
      <div className="refund-layout">
        <div className="refund-sections">
          <section className="surface form-section"><h2>Hồ sơ & lý do hoàn tiền</h2><dl className="profile-grid"><div><dt>Cư dân</dt><dd>{resident.name}</dd></div><div><dt>Căn hộ</dt><dd>{resident.unitCode} · {resident.building}</dd></div><div><dt>Chứng từ nguồn</dt><dd>{reason.sourceDocument}</dd></div><div><dt>Phạm vi</dt><dd>GreenCity Central</dd></div></dl><p className="context-note">{reason.description}</p></section>
          <section className="surface form-section"><h2>Số tiền & ngày hạch toán</h2><div className="form-grid">
            <Field id="refundAmount" label="Số tiền hoàn (VND)" required error={errors.refundAmount} hint={`Số nguyên, tối đa ${formatVND(financials.remainingAmount)}. Không nhập dấu phân cách.`}><input {...inputProps('refundAmount')} type="text" inputMode="numeric" required /></Field>
            <Field id="postingDate" label="Ngày hạch toán" required error={errors.postingDate}><input {...inputProps('postingDate')} type="date" required /></Field>
          </div></section>
          <section className="surface form-section"><h2>Phương thức & người nhận</h2>
            <fieldset id="paymentMethod" tabIndex={-1} aria-describedby={errors.paymentMethod ? 'paymentMethod-error' : undefined}><legend className="field-label">Phương thức chi trả *</legend><div className="payment-methods">{Object.entries(paymentLabels).map(([value, label]) => <label key={value} className={formData.paymentMethod === value ? 'is-selected' : ''}><input type="radio" name="paymentMethod" value={value} checked={formData.paymentMethod === value} onChange={() => update('paymentMethod', value)} />{label}</label>)}</div>{errors.paymentMethod && <p className="field-error" id="paymentMethod-error">{errors.paymentMethod}</p>}</fieldset>
            {formData.paymentMethod === 'bank_transfer' ? <>
              <div className="form-grid">
                <Field id="bankName" label="Ngân hàng thụ hưởng" required error={errors.bankName}><input {...inputProps('bankName')} required /></Field>
                <Field id="branchName" label="Chi nhánh (tùy chọn)"><input {...inputProps('branchName')} /></Field>
                <Field id="accountHolder" label="Tên chủ tài khoản" required error={errors.accountHolder}><input {...inputProps('accountHolder')} required /></Field>
                <Field id="accountNumber" label="Số tài khoản" required error={errors.accountNumber}><input {...inputProps('accountNumber')} inputMode="numeric" required /></Field>
              </div>
              <p className="context-note">Chưa xác minh với ngân hàng. Cần đối chiếu tên và số tài khoản với chứng từ; giao diện không tự xác nhận danh tính.</p>
            </> : <p className="context-note">{formData.paymentMethod === 'cash' ? 'Khi triển khai thực tế, thủ quỹ cần lập phiếu chi và xác nhận người nhận tiền.' : 'Số tiền được đề nghị khấu trừ vào kỳ sau; không thực hiện chuyển khoản ngân hàng.'}</p>}
          </section>
          <section className="surface form-section"><h2>Chứng từ đối chiếu</h2>
            <p className="helper-text">PDF, JPG, PNG · Tối đa 10 MB/tệp. Chỉ mô phỏng đính kèm trên máy, chưa tải lên máy chủ.</p>
            <label className="upload-area" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); addFiles(e.dataTransfer.files); }}><UploadCloud size={24} aria-hidden="true" /><span>Chọn chứng từ hoặc kéo thả vào đây</span><input id="attachments" type="file" multiple accept=".pdf,.jpg,.jpeg,.png" aria-label="Chọn chứng từ" aria-invalid={errors.attachments ? true : undefined} aria-describedby="attachment-help" onChange={event => { addFiles(event.target.files); event.target.value = ''; }} /></label>
            <div id="attachment-help">{errors.attachments && <p className="field-error">{errors.attachments}</p>}{uploadError && <p className="field-error" role="alert">{uploadError}</p>}</div>
            <ul className="attachment-list">{formData.attachments.map(file => <li key={file.id}><FileText size={19} aria-hidden="true" /><div><span>{file.name}</span><small>{file.size} · {file.local ? 'Đã chọn cục bộ, chưa tải lên' : 'Chứng từ mẫu'}</small></div><button type="button" className="icon-button" aria-label={`Gỡ chứng từ ${file.name}`} title="Gỡ khỏi phiếu" onClick={() => update('attachments', formData.attachments.filter(item => item.id !== file.id))}><Trash2 size={17} aria-hidden="true" /></button></li>)}</ul>
          </section>
          <section className="surface form-section"><h2>Ghi chú nội bộ</h2><Field id="remarks" label="Ghi chú (tùy chọn)"><textarea {...inputProps('remarks')} rows={3} maxLength={500} placeholder="Bổ sung thông tin cần người kiểm tra lưu ý…" /></Field><p className="helper-text">{formData.remarks.length}/500 ký tự</p></section>
        </div>
        <aside className="refund-summary surface" aria-label="Tóm tắt phiếu"><p className="eyebrow">Đối chiếu trước khi gửi</p><h2>Tóm tắt hoàn tiền</h2><dl><div><dt>Thu thừa ban đầu</dt><dd>{formatVND(financials.originalAmount)}</dd></div><div><dt>Đã hoàn trước đây</dt><dd>{formatVND(financials.alreadyRefunded)}</dd></div><div><dt>Số dư khả dụng</dt><dd>{formatVND(financials.remainingAmount)}</dd></div></dl><div className="refund-total"><span>Đề nghị hoàn lần này</span><strong>{/^\d+$/.test(formData.refundAmount) ? formatVND(Number(formData.refundAmount)) : 'Chưa hợp lệ'}</strong></div><p>{paymentLabels[formData.paymentMethod]}</p><p className="context-note">Chế độ minh họa. Xác nhận không tạo bút toán, không chuyển tiền và không gửi dữ liệu đến ngân hàng.</p><p className="helper-text">Bản nháp chỉ lưu trong tab hiện tại. Không dùng dữ liệu tài chính thật để thử nghiệm.</p></aside>
      </div>
      <footer className="form-action-bar"><button type="button" className="button-secondary" onClick={onBack}><ArrowLeft size={17} aria-hidden="true" />Quay lại</button><p className="form-save-status" role="status">{saveMessage || (dirty ? 'Có thay đổi chưa lưu' : 'Chưa có thay đổi')}</p><div className="form-action-buttons"><button type="button" className="button-secondary" onClick={save}><Save size={17} aria-hidden="true" />Lưu bản nháp</button><button type="submit" className="button-primary"><CheckCircle2 size={17} aria-hidden="true" />Kiểm tra & xác nhận</button></div></footer>
    </form>
  </div>;
}
