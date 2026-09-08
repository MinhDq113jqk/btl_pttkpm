import React from 'react';
import { CheckCircle2 } from 'lucide-react';
import { Dialog } from './Dialog';
import { formatVND, paymentLabels } from '../data/refundForm';
import { sampleRefundCase } from '../data/mockData';

export const ConfirmModal = ({ isOpen, onClose, onConfirm, data, isLoading }) => (
  <Dialog open={isOpen} onClose={onClose} busy={isLoading} title="Xác nhận phiếu hoàn tiền mẫu">
    <div className="dialog-body">
      <p className="context-note">Đây là mô phỏng giao diện. Không tạo bút toán, không chuyển tiền và không gửi dữ liệu đến ngân hàng.</p>
      <dl className="confirmation-details">
        <div><dt>Mã hồ sơ</dt><dd>{sampleRefundCase.caseCode}</dd></div>
        <div><dt>Cư dân / Căn hộ</dt><dd>{sampleRefundCase.resident.name} · {sampleRefundCase.resident.unitCode}</dd></div>
        <div><dt>Phương thức</dt><dd>{paymentLabels[data?.paymentMethod]}</dd></div>
        <div><dt>Ngày hạch toán</dt><dd>{data?.postingDate?.split('-').reverse().join('/')}</dd></div>
        {data?.paymentMethod === 'bank_transfer' && <><div><dt>Ngân hàng</dt><dd>{data.bankName}</dd></div><div><dt>Người nhận</dt><dd>{data.accountHolder}</dd></div><div><dt>Số tài khoản</dt><dd>{data.accountNumber}</dd></div></>}
        <div><dt>Chứng từ</dt><dd>{data?.attachments?.length || 0} tệp minh họa</dd></div>
        <div className="confirmation-amount"><dt>Số tiền đề nghị</dt><dd>{formatVND(data?.refundAmount ?? 0)}</dd></div>
      </dl>
    </div>
    <div className="dialog-actions">
      <button type="button" className="button-secondary" disabled={isLoading} onClick={onClose}>Quay lại kiểm tra</button>
      <button type="button" className="button-primary" disabled={isLoading} onClick={onConfirm}><CheckCircle2 size={17} aria-hidden="true" />{isLoading ? 'Đang xử lý mô phỏng…' : 'Xác nhận mô phỏng'}</button>
    </div>
  </Dialog>
);
