import React from 'react';
import { Search, Bell, ArrowUpRight } from 'lucide-react';

export const Header = ({ onSearch, onOpenForm, onNotifications, unreadCount, activeBreadcrumb, primaryLabel = 'Mở phiếu hoàn tiền', roleLabel }) => (
  <header className="desktop-header">
    <div className="header-context"><span>Không gian điều hành</span><strong>{activeBreadcrumb}</strong></div>
    <button type="button" onClick={onSearch} className="search-trigger" aria-keyshortcuts="Control+k" aria-label="Tìm kiếm công việc và phân hệ">
      <Search size={18} aria-hidden="true" /><span>Tìm công việc, phân hệ…</span><kbd>Ctrl K</kbd>
    </button>
    <div className="header-actions">
      {roleLabel && <span className="staff-header-role">{roleLabel}</span>}
      <button type="button" className="icon-button notification-trigger" onClick={onNotifications} aria-label={`Thông báo, ${unreadCount} chưa đọc`} title="Mở thông báo">
        <Bell size={20} aria-hidden="true" />{unreadCount > 0 && <span className="notification-count" aria-hidden="true">{unreadCount}</span>}
      </button>
      {onOpenForm && <button type="button" className="button-primary" onClick={onOpenForm}><ArrowUpRight size={17} aria-hidden="true" /><span>{primaryLabel}</span></button>}
    </div>
  </header>
);
