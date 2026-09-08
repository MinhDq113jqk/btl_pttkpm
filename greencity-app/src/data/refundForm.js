import { sampleRefundCase } from './mockData.js';

export const DRAFT_KEY = 'greencity.refund-draft.v1';
export const paymentLabels = { bank_transfer: 'Chuyển khoản ngân hàng', credit_offset: 'Khấu trừ kỳ sau', cash: 'Tiền mặt tại quầy' };
export const formatVND = value => new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(value);
export function createRefundForm() {
  return {
    refundAmount: String(sampleRefundCase.financials.currentRefundAmount),
    postingDate: sampleRefundCase.financials.postingDate.replaceAll('/', '-'),
    paymentMethod: 'bank_transfer',
    ...sampleRefundCase.beneficiaryAccount,
    remarks: '',
    attachments: [...sampleRefundCase.attachments],
  };
}

export function validateRefund(data) {
  const errors = {};
  const amount = Number(data.refundAmount);
  if (!/^\d+$/.test(String(data.refundAmount)) || !Number.isSafeInteger(amount) || amount <= 0) errors.refundAmount = 'Nhập số tiền nguyên lớn hơn 0, không dùng dấu âm hoặc phần thập phân.';
  else if (amount > sampleRefundCase.financials.remainingAmount) errors.refundAmount = `Số tiền không được vượt số dư ${formatVND(sampleRefundCase.financials.remainingAmount)}.`;
  const date = new Date(`${data.postingDate}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(data.postingDate) || Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== data.postingDate) errors.postingDate = 'Chọn ngày hạch toán hợp lệ.';
  if (!Object.hasOwn(paymentLabels, data.paymentMethod)) errors.paymentMethod = 'Chọn phương thức chi trả.';
  if (data.paymentMethod === 'bank_transfer') {
    if (!data.bankName.trim()) errors.bankName = 'Nhập tên ngân hàng thụ hưởng.';
    if (!data.accountHolder.trim()) errors.accountHolder = 'Nhập tên chủ tài khoản.';
    if (!/^\d+$/.test(data.accountNumber.trim())) errors.accountNumber = 'Nhập số tài khoản bằng chữ số, không có khoảng trắng ở giữa.';
  }
  if (!data.attachments.length) errors.attachments = 'Đính kèm ít nhất một chứng từ để tiếp tục mô phỏng.';
  return errors;
}

export function loadRefundDraft(storage) {
  try {
    const saved = JSON.parse(storage.getItem(DRAFT_KEY));
    if (!saved || saved.version !== 1 || !saved.data) return null;
    const defaults = createRefundForm();
    const keys = ['refundAmount', 'postingDate', 'paymentMethod', 'bankName', 'branchName', 'accountHolder', 'accountNumber', 'remarks'];
    if (!keys.every(key => typeof saved.data[key] === 'string')) return null;
    if (!Object.hasOwn(paymentLabels, saved.data.paymentMethod)) return null;
    return { ...defaults, ...Object.fromEntries(keys.map(key => [key, saved.data[key]])), attachments: Array.isArray(saved.data.attachmentIds) ? defaults.attachments.filter(file => saved.data.attachmentIds.includes(file.id)) : defaults.attachments };
  } catch { return null; }
}

export function saveRefundDraft(storage, data) {
  const { attachments, ...fields } = data;
  storage.setItem(DRAFT_KEY, JSON.stringify({ version: 1, data: { ...fields, attachmentIds: attachments.filter(file => !file.local).map(file => file.id) } }));
}

export function validateAttachment(file) {
  if (!/\.(pdf|jpe?g|png)$/i.test(file.name) || (file.type && !['application/pdf', 'image/jpeg', 'image/png'].includes(file.type))) return 'Chỉ nhận tệp PDF, JPG hoặc PNG.';
  if (file.size === 0 || file.size > 10 * 1024 * 1024) return 'Chọn tệp có dữ liệu và không lớn hơn 10 MB.';
  return '';
}
