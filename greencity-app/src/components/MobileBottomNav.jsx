import React from 'react';
import { 
  LayoutDashboard, 
  CheckSquare, 
  Receipt, 
  Bell, 
  LayoutGrid,
  Folder
} from 'lucide-react';

export const MobileBottomNav = ({ 
  currentTab, 
  onSelectTab, 
  onToggleFolder,
  isFolderOpen 
}) => {
  const primaryTabs = [
    {
      id: 'overview',
      label: 'Tổng quan',
      icon: LayoutDashboard,
      badge: null
    },
    {
      id: 'tasks',
      label: 'Công việc',
      icon: CheckSquare,
      badge: 12
    },
    {
      id: 'refund-form',
      label: 'Hoàn tiền',
      icon: Receipt,
      badge: 'Mẫu'
    },
    {
      id: 'notifications',
      label: 'Thông báo',
      icon: Bell,
      badge: 4
    }
  ];

  return (
    <nav className="bg-white/95 backdrop-blur-md border-t border-slate-200/90 px-2 py-1.5 shadow-lg select-none z-30 flex-shrink-0">
      <div className="max-w-md mx-auto grid grid-cols-5 items-center gap-1">
        {/* 4 Main Core Tabs */}
        {primaryTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = currentTab === tab.id && !isFolderOpen;

          return (
            <button
              key={tab.id}
              onClick={() => onSelectTab(tab.id)}
              className={`flex flex-col items-center justify-center py-1.5 px-1 rounded-xl transition-all relative group cursor-pointer ${
                isActive 
                  ? 'text-emerald-700 font-bold' 
                  : 'text-slate-400 hover:text-slate-700 font-medium'
              }`}
            >
              {/* Active Indicator Top Pill */}
              {isActive && (
                <span className="absolute top-0 w-8 h-1 bg-emerald-600 rounded-full animate-in fade-in zoom-in duration-150" />
              )}

              <div className="relative">
                <Icon 
                  size={20} 
                  className={`transition-transform duration-150 ${
                    isActive ? 'scale-110 text-emerald-600' : 'group-hover:scale-105'
                  }`} 
                />
                {/* Badges */}
                {tab.badge !== null && (
                  <span className={`absolute -top-1 -right-2.5 text-[9px] px-1.2 py-0.2 rounded-full font-bold leading-tight ${
                    typeof tab.badge === 'string'
                      ? 'bg-amber-100 text-amber-800 border border-amber-300'
                      : 'bg-rose-500 text-white'
                  }`}>
                    {tab.badge}
                  </span>
                )}
              </div>

              <span className="text-[10px] tracking-tight mt-1 truncate max-w-full">
                {tab.label}
              </span>
            </button>
          );
        })}

        {/* 5th Tab: "Thêm" (More / Drawer containing all remaining modules) */}
        <button
          onClick={onToggleFolder}
          className={`flex flex-col items-center justify-center py-1 px-1 rounded-xl transition-all relative group cursor-pointer ${
            isFolderOpen 
              ? 'text-emerald-700 font-bold' 
              : 'text-slate-500 hover:text-slate-800 font-medium'
          }`}
        >
          {isFolderOpen && (
            <span className="absolute top-0 w-8 h-1 bg-emerald-600 rounded-full animate-in fade-in zoom-in duration-150" />
          )}

          {/* Icon with grid/more styling */}
          <div className="relative">
            <div className={`w-8 h-7 rounded-lg flex items-center justify-center border transition-all ${
              isFolderOpen 
                ? 'bg-emerald-100 border-emerald-400 text-emerald-800 shadow-xs' 
                : 'bg-slate-100 border-slate-200 text-slate-600 group-hover:bg-slate-200'
            }`}>
              <LayoutGrid size={17} className={isFolderOpen ? 'text-emerald-700' : ''} />
            </div>
            {/* Tiny indicator badge showing there are multiple items inside */}
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-white" />
          </div>

          <span className="text-[10px] tracking-tight mt-0.5 truncate max-w-full font-semibold">
            Thêm
          </span>
        </button>
      </div>
    </nav>
  );
};
