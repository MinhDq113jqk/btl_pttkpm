import React from 'react';

export const GreenCityLogo = ({ collapsed = false, className = "" }) => {
  return (
    <div className={`flex items-center gap-3 select-none ${className}`}>
      {/* Brand Icon: Smart Urban Building + Green Sprout Leaf */}
      <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center shadow-md shadow-emerald-500/20 text-white flex-shrink-0 group">
        <svg 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2" 
          strokeLinecap="round" 
          strokeLinejoin="round" 
          className="w-6 h-6"
        >
          {/* Smart Modern Urban Towers */}
          <path d="M4 21V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v16" stroke="currentColor" strokeWidth="1.8" />
          <path d="M12 11h6a2 2 0 0 1 2 2v8" stroke="currentColor" strokeWidth="1.8" />
          {/* Windows / Tech Grid */}
          <line x1="8" y1="7" x2="8.01" y2="7" strokeWidth="2.5" />
          <line x1="8" y1="11" x2="8.01" y2="11" strokeWidth="2.5" />
          <line x1="8" y1="15" x2="8.01" y2="15" strokeWidth="2.5" />
          <line x1="16" y1="15" x2="16.01" y2="15" strokeWidth="2.5" />
          {/* Green Leaf Accent - Eco Architecture */}
          <path 
            d="M17 3c0 4-4 5-4 5s1-3 4-5z" 
            fill="#a7f3d0" 
            stroke="#10b981" 
            strokeWidth="1.2" 
          />
        </svg>
        <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-400 rounded-full border-2 border-white ring-1 ring-emerald-600/30"></div>
      </div>

      {!collapsed && (
        <div className="flex flex-col">
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-lg tracking-tight text-slate-900 leading-none">
              Green<span className="text-emerald-600">City</span>
            </span>
            <span className="text-[10px] uppercase font-semibold tracking-wider px-1.5 py-0.5 rounded bg-emerald-100/70 text-emerald-800 leading-none">
              Urban
            </span>
          </div>
          <span className="text-[11px] text-slate-500 font-medium tracking-normal mt-0.5 leading-tight">
            Quản trị Vận hành Đô thị
          </span>
        </div>
      )}
    </div>
  );
};
