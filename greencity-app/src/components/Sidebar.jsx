import React from 'react';
import { LayoutDashboard, Receipt, CheckSquare, Building2, Wrench, Sparkles, ShieldCheck, Users, BadgePercent, BarChart3, Bell, Settings, Globe, Store, PanelLeftClose, PanelLeftOpen, Building, LogOut } from 'lucide-react';
import { GreenCityLogo } from './GreenCityLogo';

const icons = { LayoutDashboard, Receipt, CheckSquare, Building2, Wrench, Sparkles, ShieldCheck, Users, BadgePercent, BarChart3, Bell, Settings, Globe, Store };
const groups = [
  { label: 'Không gian làm việc', ids: ['overview', 'tasks', 'notifications', 'refund-form'] },
  { label: 'Vận hành khu đô thị', ids: ['technical', 'cleaning', 'security', 'projects', 'amenities', 'residents', 'finance', 'media'] },
  { label: 'Quản trị', ids: ['reports', 'settings'] },
];
export const Sidebar = ({ currentTab, setCurrentTab, navItems, collapsed, setCollapsed, activeSite, activeSiteId,
  allowedSites = [], onSwitchSite, isSwitchingSite = false, siteSwitchError, taskCount, unreadCount, account, onLogout }) => (
  <aside className={`desktop-sidebar ${collapsed ? 'is-collapsed' : ''}`} aria-label="Thanh bên GreenCity">
    <div className="sidebar-brand"><GreenCityLogo collapsed={collapsed} /></div>
    <div className="sidebar-site" title={`${activeSite} · Phạm vi phiên hiện tại`}><Building size={18} aria-hidden="true" />
      <div className="sidebar-copy sidebar-site-control">
        <label htmlFor="active-site-select">Site đang hoạt động</label>
        <select id="active-site-select" value={activeSiteId || ''} disabled={isSwitchingSite || allowedSites.length < 2}
          aria-describedby={siteSwitchError ? 'active-site-error' : undefined}
          onChange={event => onSwitchSite?.(event.target.value)}>
          {allowedSites.length === 0 && <option value="">Chưa có site</option>}
          {allowedSites.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}
        </select>
        <span>{isSwitchingSite ? 'Đang xác minh phạm vi…' : 'Phạm vi do máy chủ cấp'}</span>
        {siteSwitchError && <small id="active-site-error" role="alert">{siteSwitchError.message}{siteSwitchError.correlationId ? ` · ${siteSwitchError.correlationId}` : ''}</small>}
      </div>
    </div>
    <nav className="sidebar-navigation" aria-label="Điều hướng chính">
      {groups.filter(group => group.ids.some(id => navItems.some(item => item.id === id))).map(group => <div className="nav-group" key={group.label}>
        <p className="nav-group-label sidebar-copy">{group.label}</p>
        {group.ids.map(id => {
          const item = navItems.find(entry => entry.id === id);
          if (!item) return null;
          const Icon = icons[item.icon];
          const count = id === 'tasks' ? taskCount : id === 'notifications' ? unreadCount : null;
          const ready = ['overview', 'tasks', 'notifications', 'residents', 'refund-form', 'amenities', 'media', 'settings', 'reports', 'technical', 'cleaning', 'security'].includes(id);
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
      <div className="sidebar-user"><span className="user-avatar">{account.initials}</span><div className="sidebar-copy"><strong>{account.name}</strong><span>{account.label} · Phiên xác thực</span></div></div>
      {onLogout && <button className="sidebar-toggle staff-logout" onClick={onLogout} aria-label="Đăng xuất" title="Đăng xuất"><LogOut size={18} aria-hidden="true" /><span className="sidebar-copy">Đăng xuất</span></button>}
      <button type="button" className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Mở rộng thanh bên' : 'Thu gọn thanh bên'} aria-expanded={!collapsed}>
        {collapsed ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}<span className="sidebar-copy">Thu gọn thanh bên</span>
      </button>
    </div>
  </aside>
);
