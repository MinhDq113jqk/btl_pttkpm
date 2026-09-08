import React, { useState } from 'react';
import { 
  CheckSquare, 
  Clock, 
  AlertTriangle, 
  Filter, 
  Search, 
  ArrowRight, 
  ChevronRight,
  Plus
} from 'lucide-react';
import { dashboardData } from '../data/mockData';

export const TasksMobileView = ({ onOpenForm }) => {
  const [filter, setFilter] = useState('all');

  const tasks = [
    ...dashboardData.urgentTasks,
    {
      id: "VS-2608-042",
      title: "Kiểm tra checklist vệ sinh sảnh chính tòa A1",
      location: "Grand Park A - Tầng 1",
      status: "Đang xử lý",
      statusColor: "blue",
      deadline: "Hôm nay, 17:30"
    },
    {
      id: "AN-2608-019",
      title: "Bàn giao nhật ký tuần tra ca chiều phân khu B",
      location: "Chốt an ninh số 3",
      status: "Chờ duyệt",
      statusColor: "amber",
      deadline: "Hôm nay, 18:00"
    },
    {
      id: "KT-2608-088",
      title: "Bảo dưỡng định kỳ máy bơm tăng áp tầng hầm",
      location: "Phòng kỹ thuật B2",
      status: "Đang xử lý",
      statusColor: "blue",
      deadline: "Ngày mai, 11:00"
    }
  ];

  const filteredTasks = tasks.filter(t => {
    if (filter === 'in_progress') return t.status === 'Đang xử lý';
    if (filter === 'pending') return t.status === 'Chờ duyệt';
    if (filter === 'overdue') return t.status === 'Quá hạn';
    return true;
  });

  return (
    <div className="p-4 space-y-4 pb-24">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Công việc & Yêu cầu</h2>
          <p className="text-xs text-slate-400">12 công việc trong ca trực hôm nay</p>
        </div>
        <span className="px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold">
          12 việc
        </span>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar text-xs">
        <button
          onClick={() => setFilter('all')}
          className={`px-3 py-1.5 rounded-xl font-semibold whitespace-nowrap transition-all ${
            filter === 'all' 
              ? 'bg-slate-900 text-white shadow-xs' 
              : 'bg-white text-slate-600 border border-slate-200'
          }`}
        >
          Tất cả (6)
        </button>
        <button
          onClick={() => setFilter('in_progress')}
          className={`px-3 py-1.5 rounded-xl font-semibold whitespace-nowrap transition-all ${
            filter === 'in_progress' 
              ? 'bg-blue-600 text-white shadow-xs' 
              : 'bg-white text-blue-700 border border-blue-200'
          }`}
        >
          Đang xử lý (3)
        </button>
        <button
          onClick={() => setFilter('pending')}
          className={`px-3 py-1.5 rounded-xl font-semibold whitespace-nowrap transition-all ${
            filter === 'pending' 
              ? 'bg-amber-600 text-white shadow-xs' 
              : 'bg-white text-amber-700 border border-amber-200'
          }`}
        >
          Chờ duyệt (2)
        </button>
        <button
          onClick={() => setFilter('overdue')}
          className={`px-3 py-1.5 rounded-xl font-semibold whitespace-nowrap transition-all ${
            filter === 'overdue' 
              ? 'bg-rose-600 text-white shadow-xs' 
              : 'bg-white text-rose-700 border border-rose-200'
          }`}
        >
          Quá hạn (1)
        </button>
      </div>

      {/* Task List */}
      <div className="space-y-2.5">
        {filteredTasks.map((task) => {
          const statusStyles = {
            blue: 'bg-blue-50 text-blue-700 border-blue-200',
            amber: 'bg-amber-50 text-amber-700 border-amber-200',
            rose: 'bg-rose-50 text-rose-700 border-rose-200'
          }[task.statusColor];

          return (
            <div 
              key={task.id}
              onClick={() => {
                if (task.actionForm) onOpenForm();
              }}
              className="bg-white rounded-2xl p-3.5 border border-slate-200/80 shadow-2xs hover:border-slate-300 transition-all cursor-pointer active:scale-99"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs font-bold text-slate-700">
                  {task.id}
                </span>
                <span className={`text-[10px] px-2 py-0.5 rounded-md font-bold border ${statusStyles}`}>
                  {task.status}
                </span>
              </div>

              <h3 className="text-xs font-bold text-slate-900 leading-snug">
                {task.title}
              </h3>

              <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                <span className="truncate max-w-[170px]">{task.location}</span>
                <span className={`font-semibold ${task.statusColor === 'rose' ? 'text-rose-600' : 'text-slate-600'}`}>
                  {task.deadline}
                </span>
              </div>

              {task.actionForm && (
                <div className="mt-2.5 px-3 py-1.5 rounded-xl bg-emerald-50 text-emerald-800 text-[11px] font-bold flex items-center justify-between">
                  <span>Mở biểu mẫu phê duyệt hoàn tiền</span>
                  <ChevronRight size={14} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
