import React from 'react';
import { 
  Folder, 
  Wrench, 
  Sparkles, 
  ShieldCheck, 
  Users, 
  Building2, 
  BarChart3, 
  Settings, 
  X, 
  Bot, 
  ChevronRight,
  FolderOpen,
  ArrowUpRight,
  Globe,
  Store
} from 'lucide-react';

const otherModules = [
  {
    id: "amenities",
    label: "Tiện ích & Thương mại",
    subtext: "Bệnh viện, Trường, Bãi xe, Shophouse",
    icon: Store,
    color: "bg-amber-50 text-amber-700 border-amber-200/60",
    badge: "Mới",
    isAmenities: true
  },
  {
    id: "media",
    label: "Website & Fanpage",
    subtext: "Quản trị Facebook & Cổng tin tức",
    icon: Globe,
    color: "bg-emerald-50 text-emerald-700 border-emerald-200/60",
    badge: "Meta & Web",
    isMedia: true
  },
  {
    id: "technical",
    label: "Kỹ thuật & Bảo trì",
    subtext: "Lịch kiểm tra, checklist vật tư",
    icon: Wrench,
    color: "bg-blue-50 text-blue-600 border-blue-200/60",
    badge: "5 lịch đến hạn"
  },
  {
    id: "cleaning",
    label: "Vệ sinh môi trường",
    subtext: "Ca trực, tuyến quét & checklist",
    icon: Sparkles,
    color: "bg-teal-50 text-teal-600 border-teal-200/60",
    badge: "Ca sáng"
  },
  {
    id: "security",
    label: "An ninh & Tuần tra",
    subtext: "Nhật ký ca, sự cố, khách ra vào",
    icon: ShieldCheck,
    color: "bg-emerald-50 text-emerald-600 border-emerald-200/60",
    badge: "Bình thường"
  },
  {
    id: "residents",
    label: "Khách hàng & Cư dân",
    subtext: "Hồ sơ căn hộ, hợp đồng, chủ hộ",
    icon: Users,
    color: "bg-indigo-50 text-indigo-600 border-indigo-200/60",
    badge: "320 căn"
  },
  {
    id: "projects",
    label: "Dự án & Hạng mục",
    subtext: "Mặt bằng, phân khu Grand Park",
    icon: Building2,
    color: "bg-amber-50 text-amber-600 border-amber-200/60",
    badge: "Site A"
  },
  {
    id: "reports",
    label: "Báo cáo điều hành",
    subtext: "Chỉ số KPI, doanh thu & công nợ",
    icon: BarChart3,
    color: "bg-rose-50 text-rose-600 border-rose-200/60",
    badge: "Tháng 8"
  },
  {
    id: "ai_assistant",
    label: "Trợ lý AI Nghiệp vụ",
    subtext: "Tra cứu quy trình & biểu mẫu BQL",
    icon: Bot,
    color: "bg-purple-50 text-purple-600 border-purple-200/60",
    badge: "AI-R1"
  },
  {
    id: "settings",
    label: "Quản trị hệ thống",
    subtext: "Phân quyền, cấu hình site & audit",
    icon: Settings,
    color: "bg-slate-100 text-slate-700 border-slate-200/60",
    badge: "Admin"
  }
];

export const MobileFolderModal = ({ isOpen, onClose, onSelectModule }) => {
  if (!isOpen) return null;

  return (
    <div className="absolute inset-0 z-50 flex flex-col justify-end bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-200">
      {/* Click outside to close */}
      <div className="flex-1" onClick={onClose} />

      {/* Drawer Container (Sheet styled as an interactive Smart Folder) */}
      <div 
        className="bg-white rounded-t-[32px] shadow-2xl border-t border-slate-200 max-h-[85vh] flex flex-col overflow-hidden animate-in slide-in-from-bottom-6 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Handle pill */}
        <div className="w-12 h-1.5 bg-slate-300 rounded-full mx-auto mt-3 mb-1" />

        {/* Folder Header */}
        <div className="px-6 py-3 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-50 text-emerald-700 flex items-center justify-center">
              <FolderOpen size={20} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 leading-tight">
                Menu Mở rộng • Thêm Phân hệ
              </h3>
              <p className="text-[11px] text-slate-400">
                Toàn bộ các phân hệ mở rộng theo Roadmap Master Baseline v2.0
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-500 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Folder Content: 2-column Grid of App Modules */}
        <div className="p-4 sm:p-6 overflow-y-auto space-y-3">
          <div className="grid grid-cols-2 gap-3">
            {otherModules.map((module) => {
              const Icon = module.icon;
              return (
                <button
                  key={module.id}
                  onClick={() => {
                    onSelectModule(module);
                    onClose();
                  }}
                  className="flex flex-col text-left p-3.5 rounded-2xl bg-slate-50/80 hover:bg-emerald-50/40 border border-slate-200/80 hover:border-emerald-300 transition-all group relative cursor-pointer active:scale-98"
                >
                  <div className="flex items-center justify-between w-full mb-2.5">
                    <div className={`w-8 h-8 rounded-xl flex items-center justify-center border ${module.color}`}>
                      <Icon size={17} />
                    </div>
                    <span className="text-[10px] font-semibold text-slate-500 bg-white px-1.5 py-0.5 rounded-md border border-slate-200/60 shadow-2xs">
                      {module.badge}
                    </span>
                  </div>

                  <h4 className="text-xs font-bold text-slate-800 group-hover:text-emerald-800 transition-colors leading-snug">
                    {module.label}
                  </h4>
                  <p className="text-[10px] text-slate-400 line-clamp-1 mt-0.5">
                    {module.subtext}
                  </p>

                  <div className="mt-2 pt-2 border-t border-slate-200/50 flex items-center justify-between text-[10px] font-medium text-slate-400 group-hover:text-emerald-700">
                    <span>Mở phân hệ</span>
                    <ArrowUpRight size={12} className="group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                  </div>
                </button>
              );
            })}
          </div>

          {/* Quick Tip inside Folder */}
          <div className="p-3 rounded-xl bg-emerald-50/70 border border-emerald-200/70 flex items-center gap-2.5 text-[11px] text-emerald-900">
            <Folder size={16} className="text-emerald-600 flex-shrink-0" />
            <span>
              Mục "Thêm" này gom gọn các phân hệ phụ trợ giúp thanh tác vụ bên dưới luôn thông thoáng và dễ thao tác trên điện thoại.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
