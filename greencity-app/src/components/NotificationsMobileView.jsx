import React, { useState } from 'react';
import { Bell, CheckCheck, AlertTriangle, FileText, CheckCircle2, ChevronRight } from 'lucide-react';

export const NotificationsMobileView = ({ onOpenForm }) => {
  const [filter, setFilter] = useState('all');

  const notifications = [
    {
      id: 1,
      title: "Cần phê duyệt hoàn tiền căn A101",
      detail: "Hồ sơ hoàn phí thừa 3.000.000 đ kỳ 08/2026 đã được kế toán trình duyệt.",
      time: "10 phút trước",
      type: "finance",
      unread: true,
      hasAction: true
    },
    {
      id: 2,
      title: "Cảnh báo quá hạn hạng mục điện",
      detail: "Nhiệm vụ KT-2608-097 tại Văn phòng DNP đã trễ hạn 1 ngày.",
      time: "45 phút trước",
      type: "alert",
      unread: true,
      hasAction: false
    },
    {
      id: 3,
      title: "Hoàn tất bàn giao ca trực an ninh",
      detail: "Tổ trưởng an ninh phân khu B đã nộp nhật ký tuần tra ca 1.",
      time: "2 giờ trước",
      type: "security",
      unread: false,
      hasAction: false
    },
    {
      id: 4,
      title: "Cập nhật dữ liệu công nợ kỳ 09/2026",
      detail: "Billing Run hoàn tất thành công cho 320 căn hộ site Central.",
      time: "Hôm qua",
      type: "billing",
      unread: false,
      hasAction: false
    }
  ];

  return (
    <div className="p-4 space-y-4 pb-24">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Thông báo điều hành</h2>
          <p className="text-xs text-slate-400">Tin tức & nhắc việc quan trọng</p>
        </div>
        <button className="text-xs font-semibold text-emerald-700 flex items-center gap-1 hover:underline">
          <CheckCheck size={14} />
          <span>Đọc tất cả</span>
        </button>
      </div>

      {/* Notifications List */}
      <div className="space-y-2.5">
        {notifications.map((n) => (
          <div
            key={n.id}
            onClick={() => {
              if (n.hasAction) onOpenForm();
            }}
            className={`p-3.5 rounded-2xl border transition-all cursor-pointer ${
              n.unread 
                ? 'bg-white border-emerald-300 shadow-xs' 
                : 'bg-slate-50/70 border-slate-200/70'
            }`}
          >
            <div className="flex items-start gap-3">
              <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5 ${
                n.type === 'finance' ? 'bg-emerald-100 text-emerald-700' :
                n.type === 'alert' ? 'bg-rose-100 text-rose-600' : 'bg-slate-100 text-slate-600'
              }`}>
                {n.type === 'finance' && <FileText size={16} />}
                {n.type === 'alert' && <AlertTriangle size={16} />}
                {n.type !== 'finance' && n.type !== 'alert' && <Bell size={16} />}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-900 leading-tight truncate">
                    {n.title}
                  </h4>
                  <span className="text-[10px] text-slate-400 whitespace-nowrap pl-2">{n.time}</span>
                </div>
                <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                  {n.detail}
                </p>

                {n.hasAction && (
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenForm();
                    }}
                    className="mt-2 text-[11px] font-bold text-emerald-700 hover:text-emerald-800 flex items-center gap-1"
                  >
                    <span>Xem phiếu ngay</span>
                    <ChevronRight size={12} />
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
