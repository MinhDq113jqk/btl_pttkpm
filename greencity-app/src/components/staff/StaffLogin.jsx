import React, { useEffect, useState } from 'react';
import { ArrowRight, Building2, ShieldCheck, LockKeyhole, Monitor, Info } from 'lucide-react';
import { GreenCityLogo } from '../GreenCityLogo';
import { staffAccounts, findStaffAccount } from '../../data/staffRoles';
import './staff.css';

export function StaffLogin({ onLogin, notice = '' }) {
  const [accountId, setAccountId] = useState('demo-director');
  const [help, setHelp] = useState(false);
  const account = findStaffAccount(accountId);
  useEffect(() => { document.title = 'Đăng nhập nhân viên & BQL · GreenCity'; }, []);
  return <main className="staff-login">
    <section className="staff-login-story" aria-label="GreenCity dành cho nhân viên và Ban quản lý">
      <GreenCityLogo />
      <div className="staff-story-content"><span className="staff-overline">GREENCITY / STAFF WORKSPACE</span><h1>Một không gian.<br />Đúng vai trò của bạn.</h1><p>Kết nối Ban quản lý và các đội vận hành trên cùng một ứng dụng desktop.</p>
        <div className="staff-building-scene" aria-hidden="true"><div className="scene-orbit" /><div className="scene-tower tower-a"><i /><i /><i /><i /><i /><i /></div><div className="scene-tower tower-b"><i /><i /><i /><i /><i /><i /><i /><i /></div><div className="scene-tower tower-c"><i /><i /><i /><i /></div><div className="scene-path" /><span className="scene-label"><Building2 size={15} />GreenCity Central</span></div>
        <div className="staff-story-points"><div><ShieldCheck size={19} /><span>Menu theo quyền được cấp</span></div><div><Monitor size={19} /><span>Dashboard theo công việc mỗi ngày</span></div></div>
      </div><p className="staff-story-footer">Dành cho nhân viên & Ban quản lý · Không phải cổng cư dân</p>
    </section>
    <section className="staff-login-form-side"><div className="staff-login-card">
      <div className="staff-login-badge"><Monitor size={15} aria-hidden="true" />Bản xem thử giao diện desktop</div>
      <h2>Đăng nhập không gian làm việc</h2><p className="staff-login-intro">Chọn tài khoản mẫu để trải nghiệm giao diện theo quyền. Bản này chưa kết nối xác thực.</p>
      {notice && <p role="status" className="context-note">{notice}</p>}
      <form onSubmit={event => { event.preventDefault(); onLogin(account); }}>
        <label className="field-label" htmlFor="staff-account">Tài khoản nhân viên mẫu</label>
        <select id="staff-account" value={accountId} onChange={event => setAccountId(event.target.value)}>{staffAccounts.map(item => <option value={item.accountId} key={item.accountId}>{item.label} — {item.name}</option>)}</select>
        <label className="field-label" htmlFor="staff-email">Email công việc</label><input id="staff-email" type="email" autoComplete="username" value={account.email} readOnly />
        <label className="field-label" htmlFor="staff-password">Mật khẩu</label><div className="staff-password-placeholder"><LockKeyhole size={16} aria-hidden="true" /><input id="staff-password" type="password" autoComplete="current-password" disabled placeholder="Không cần mật khẩu trong bản mẫu" /></div>
        <div className="staff-login-role" aria-live="polite"><span className="staff-role-mark">{account.initials}</span><div><strong>{account.label}</strong><p>{account.scope}</p></div></div>
        <button className="button-primary staff-login-submit" type="submit">Vào không gian mẫu<ArrowRight size={18} aria-hidden="true" /></button>
      </form>
      <button className="button-text staff-login-help" aria-expanded={help} onClick={() => setHelp(!help)}>Cần hỗ trợ đăng nhập?</button>
      {help && <p className="context-note">Khi triển khai thật, tài khoản và quyền do Admin cấp. Liên hệ quản trị viên của Ban quản lý nếu không đăng nhập được. Bản xem thử không nhận mật khẩu hoặc OTP.</p>}
      <p className="staff-login-disclaimer"><Info size={15} aria-hidden="true" />Tài khoản mẫu chỉ dùng để xem thiết kế. Trong hệ thống thật, người dùng không tự chọn quyền khi đăng nhập.</p>
    </div><p className="staff-login-copyright">GreenCity · Hệ thống quản lý vận hành khu đô thị</p></section>
  </main>;
}
