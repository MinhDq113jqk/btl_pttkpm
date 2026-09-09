import React, { useState } from 'react';
import { Search, ArrowUpRight } from 'lucide-react';
import { Dialog } from './Dialog';
import { navItems as defaultNav } from '../data/mockData';
import { tasks as defaultTasks, normalizeSearch } from '../data/desktopData';

export function SearchDialog({ open, onClose, onNavigate, onSelectTask, navItems = defaultNav, tasks = defaultTasks }) {
  const [query, setQuery] = useState('');
  const normalized = normalizeSearch(query);
  const modules = navItems.filter(item => normalizeSearch(item.label).includes(normalized));
  const results = normalized ? tasks.filter(task => normalizeSearch(`${task.id} ${task.title} ${task.location}`).includes(normalized)) : [];
  const activate = action => { onClose(); setQuery(''); action(); };
  return <Dialog open={open} onClose={onClose} title="Tìm kiếm nhanh" wide initialFocusId="global-search">
    <div className="dialog-body search-dialog">
      <label htmlFor="global-search" className="field-label">Tìm theo mã, tên công việc hoặc phân hệ</label>
      <div className="search-field"><Search size={18} aria-hidden="true" /><input id="global-search" autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder="Ví dụ: máy bơm, A101, kỹ thuật…" /></div>
      <p className="helper-text" role="status">{modules.length + results.length} kết quả · Tab để chọn, Enter để mở, Esc để đóng.</p>
      {modules.length + results.length === 0 && <div className="empty-state"><Search size={28} aria-hidden="true" /><h3>Không tìm thấy kết quả</h3><p>Thử tên ngắn hơn hoặc mã công việc. Có thể tìm không dấu.</p><button className="button-secondary" onClick={() => setQuery('')}>Xóa tìm kiếm</button></div>}
      {results.length > 0 && <section><h3 className="search-section-title">Công việc</h3>{results.map(task => <button className="search-result" key={task.id} onClick={() => activate(() => onSelectTask(task))}><div><strong>{task.title}</strong><span>{task.id} · {task.location}</span></div><ArrowUpRight size={17} aria-hidden="true" /></button>)}</section>}
      {modules.length > 0 && <section><h3 className="search-section-title">Phân hệ</h3>{modules.map(item => <button className="search-result" key={item.id} onClick={() => activate(() => onNavigate(item.id))}><strong>{item.label}</strong><ArrowUpRight size={17} aria-hidden="true" /></button>)}</section>}
    </div>
  </Dialog>;
}
