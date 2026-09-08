import React from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export const Toast = ({ message, type = 'success', onClose }) => {
  if (!message) return null;

  const bgStyles = {
    success: 'bg-emerald-800 text-white border-emerald-700 shadow-emerald-900/20',
    info: 'bg-slate-900 text-white border-slate-800 shadow-slate-950/20',
    warning: 'bg-amber-800 text-white border-amber-700 shadow-amber-900/20'
  };

  const icons = {
    success: <CheckCircle2 size={18} className="text-emerald-300 flex-shrink-0" />,
    info: <Info size={18} className="text-sky-300 flex-shrink-0" />,
    warning: <AlertCircle size={18} className="text-amber-200 flex-shrink-0" />
  };

  return (
    <div className="app-toast" role="status" aria-live="polite" aria-atomic="true">
      <div className={`flex items-center gap-3 px-4 py-3 rounded-2xl shadow-xl border text-xs font-medium ${bgStyles[type]}`}>
        {icons[type]}
        <span>{message}</span>
        <button 
          aria-label="Đóng thông báo"
          onClick={onClose}
          className="ml-2 p-1 rounded-lg hover:bg-white/20 transition-colors text-white/80 hover:text-white"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
};
