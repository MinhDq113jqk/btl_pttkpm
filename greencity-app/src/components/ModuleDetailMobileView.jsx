import React from 'react';
import { ArrowLeft, ChevronRight, CheckCircle2, AlertCircle, FileSpreadsheet, Plus } from 'lucide-react';

export const ModuleDetailMobileView = ({ module, onBack, onOpenForm }) => {
  if (!module) return null;
  const Icon = module.icon;

  return (
    <div className="p-4 space-y-4 pb-24">
      {/* Header with Back Button */}
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="w-8 h-8 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-50 transition-colors"
        >
          <ArrowLeft size={16} />
        </button>
        <div>
          <h2 className="text-base font-bold text-slate-900 leading-tight">
            {module.label}
          </h2>
          <p className="text-[11px] text-slate-400">{module.subtext}</p>
        </div>
      </div>

      {/* Module Overview Card */}
      <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-xs space-y-3">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${module.color}`}>
            <Icon size={20} />
          </div>
          <div>
            <span className="text-[10px] uppercase font-bold text-slate-400">Trạng thái vận hành</span>
            <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>{module.badge}</span>
            </div>
          </div>
        </div>

        <p className="text-xs text-slate-500 leading-relaxed pt-1 border-t border-slate-100">
          Phân hệ {module.label} đã được thiết lập theo quy chuẩn Data Scope (`ARC-03`) và phân quyền người dùng (`PRM-*`) tại site GreenCity Central.
        </p>
      </div>

      {/* Quick Actions */}
      <div className="space-y-2">
        <h3 className="text-xs font-bold text-slate-700">Tác vụ nhanh</h3>
        <div className="grid grid-cols-2 gap-2.5">
          <button 
            onClick={onOpenForm}
            className="p-3 bg-white rounded-xl border border-slate-200 hover:border-emerald-500 text-left text-xs font-semibold text-slate-800 flex items-center justify-between"
          >
            <span>Tạo phiếu mới</span>
            <Plus size={14} className="text-emerald-600" />
          </button>
          <button 
            className="p-3 bg-white rounded-xl border border-slate-200 text-left text-xs font-semibold text-slate-800 flex items-center justify-between"
          >
            <span>Xuất báo cáo</span>
            <FileSpreadsheet size={14} className="text-blue-600" />
          </button>
        </div>
      </div>

      {/* Checklist / Recent Log placeholder */}
      <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-2xs space-y-2.5">
        <h3 className="text-xs font-bold text-slate-800">Nhật ký hoạt động gần nhất</h3>
        <div className="space-y-2 text-xs">
          <div className="p-2.5 rounded-xl bg-slate-50 flex items-center justify-between">
            <span className="text-slate-600">Đồng bộ lịch tuần tra / kiểm tra</span>
            <span className="text-[10px] text-emerald-600 font-bold">Hoàn tất</span>
          </div>
          <div className="p-2.5 rounded-xl bg-slate-50 flex items-center justify-between">
            <span className="text-slate-600">Kiểm tra chỉ số an toàn vận hành</span>
            <span className="text-[10px] text-emerald-600 font-bold">100% Đạt</span>
          </div>
        </div>
      </div>
    </div>
  );
};
