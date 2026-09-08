import React from 'react';
import { LayoutDashboard, Receipt, CheckSquare, Building2, Wrench, Sparkles, ShieldCheck, Users, BadgePercent, BarChart3, Bell, Settings, Globe, Store, PanelLeftClose, PanelLeftOpen, Building } from 'lucide-react';
import { GreenCityLogo } from './GreenCityLogo';
import { currentUser } from '../data/mockData';

const icons = { LayoutDashboard, Receipt, CheckSquare, Building2, Wrench, Sparkles, ShieldCheck, Users, BadgePercent, BarChart3, Bell, Settings, Globe, Store };
const groups = [
  { label: 'Không gian làm việc', ids: ['overview', 'tasks', 'notifications', 'refund-form'] },
  { label: 'Vận hành khu đô thị', ids: ['technical', 'cleaning', 'security', 'projects', 'amenities', 'residents', 'finance', 'media'] },
  { label: 'Quản trị', ids: ['reports', 'settings'] },
];
export const Sidebar = ({ currentTab, setCurrentTab, navItems, collapsed, setCollapsed, activeSite, taskCount, unreadCount }) => (
  <aside className={`desktop-sidebar ${collapsed ? 'is-collapsed' : ''}`} aria-label="Thanh bên GreenCity">
    <div className="sidebar-brand"><GreenCityLogo collapsed={collapsed} /></div>
    <div className="sidebar-site" title={`${activeSite} · Dữ liệu mẫu`}><Building size={18} aria-hidden="true" /><div className="sidebar-copy"><strong>{activeSite}</strong><span>Dữ liệu minh họa · 1 khu đô thị</span></div></div>
    <nav className="sidebar-navigation" aria-label="Điều hướng chính">
      {groups.map(group => <div className="nav-group" key={group.label}>
        <p className="nav-group-label sidebar-copy">{group.label}</p>
        {group.ids.map(id => {
          const item = navItems.find(entry => entry.id === id);
          const Icon = icons[item.icon];
          const count = id === 'tasks' ? taskCount : id === 'notifications' ? unreadCount : null;
          const ready = ['overview', 'tasks', 'notifications', 'refund-form', 'amenities', 'media'].includes(id);
          return <button key={id} type="button" onClick={() => setCurrentTab(id)} aria-current={currentTab === id ? 'page' : undefined}
            aria-label={item.label} title={`${item.label}${ready ? '' : ' · Chưa triển khai'}`} className={`nav-item ${currentTab === id ? 'is-active' : ''}`}>
            <Icon size={19} aria-hidden="true" /><span className="sidebar-copy nav-label">{item.label}</span>
            {count > 0 && <span className="nav-count sidebar-copy">{count}</span>}
            {!ready && <span className="nav-planned sidebar-copy" aria-label="Chưa triển khai">—</span>}
          </button>;
        })}
      </div>)}
    </nav>
    <div className="sidebar-footer">
      <div className="sidebar-user"><span className="user-avatar">{currentUser.avatarText}</span><div className="sidebar-copy"><strong>{currentUser.name}</strong><span>{currentUser.role} · Tài khoản mẫu</span></div></div>
      <button type="button" className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Mở rộng thanh bên' : 'Thu gọn thanh bên'} aria-expanded={!collapsed}>
        {collapsed ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}<span className="sidebar-copy">Thu gọn thanh bên</span>
      </button>
    </div>
  </aside>
);
