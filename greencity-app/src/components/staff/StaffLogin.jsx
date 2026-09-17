import React, { useEffect, useState } from 'react';
import { AlertCircle, ArrowRight, Building2, ShieldCheck, LockKeyhole, LoaderCircle, Monitor, Info } from 'lucide-react';
import { GreenCityLogo } from '../GreenCityLogo';
import './staff.css';

export function StaffLogin({ onLogin, notice = '', error = null, isLoading = false }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [help, setHelp] = useState(false);
  useEffect(() => { document.title = 'Đăng nhập nhân viên & BQL · GreenCity'; }, []);

  const submit = event => {
    event.preventDefault();
    if (!username.trim() || !password || isLoading) return;
    onLogin({ username: username.trim(), password });
  };

  return <main className="staff-login">
    <section className="staff-login-story" aria-label="GreenCity dành cho người dùng đã được cấp quyền">
      <GreenCityLogo />
      <div className="staff-story-content"><span className="staff-overline">GREENCITY / SECURE WORKSPACE</span><h1>Một không gian.<br />Đúng vai trò của bạn.</h1><p>Kết nối cư dân, Ban quản lý và các đội vận hành trên cùng một ứng dụng.</p>
        <div className="staff-building-scene" aria-hidden="true"><div className="scene-orbit" /><div className="scene-tower tower-a"><i /><i /><i /><i /><i /><i /></div><div className="scene-tower tower-b"><i /><i /><i /><i /><i /><i /><i /><i /></div><div className="scene-tower tower-c"><i /><i /><i /><i /></div><div className="scene-path" /><span className="scene-label"><Building2 size={15} />GreenCity Central</span></div>
        <div className="staff-story-points"><div><ShieldCheck size={19} /><span>Menu theo quyền máy chủ cấp</span></div><div><Monitor size={19} /><span>Yêu cầu dịch vụ đúng phạm vi dữ liệu</span></div></div>
      </div><p className="staff-story-footer">Dành cho cư dân, nhân viên & Ban quản lý · Vai trò do máy chủ xác minh</p>
    </section>
    <section className="staff-login-form-side"><div className="staff-login-card">
      <div className="staff-login-badge"><Monitor size={15} aria-hidden="true" />Phiên xác thực GreenCity</div>
      <h2>Đăng nhập GreenCity</h2><p className="staff-login-intro">Nhập tài khoản đã được cấp. Vai trò và phạm vi hiển thị được lấy từ máy chủ sau khi xác thực.</p>
      {notice && <p role="status" className="context-note">{notice}</p>}
      {error && <div role="alert" className="staff-login-error"><AlertCircle size={18} aria-hidden="true" /><div><strong>Không thể đăng nhập</strong><p>{error.message}</p>{error.correlationId && <small>Mã đối chiếu: {error.correlationId}</small>}</div></div>}
      <form onSubmit={submit} aria-busy={isLoading}>
        <label className="field-label" htmlFor="staff-username">Tên đăng nhập</label>
        <input id="staff-username" name="username" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} disabled={isLoading} required autoFocus />
        <label className="field-label" htmlFor="staff-password">Mật khẩu</label>
        <div className="staff-password-input"><LockKeyhole size={16} aria-hidden="true" /><input id="staff-password" name="password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} disabled={isLoading} required /></div>
        <button className="button-primary staff-login-submit" type="submit" disabled={isLoading || !username.trim() || !password}>
          <span>{isLoading ? 'Đang xác minh…' : 'Đăng nhập'}</span>{isLoading ? <LoaderCircle className="request-spinner" size={18} aria-hidden="true" /> : <ArrowRight size={18} aria-hidden="true" />}
        </button>
      </form>
      <button type="button" className="button-text staff-login-help" aria-expanded={help} onClick={() => setHelp(!help)}>Cần hỗ trợ đăng nhập?</button>
      {help && <p className="context-note">Tài khoản và quyền do Admin cấp. Liên hệ quản trị viên của Ban quản lý nếu không đăng nhập được. Không gửi mật khẩu hoặc mã phiên qua kênh hỗ trợ.</p>}
      <p className="staff-login-disclaimer"><Info size={15} aria-hidden="true" />Bạn không thể chọn hoặc thay đổi vai trò tại màn hình này. Mọi quyền hiển thị lấy từ <code>/auth/me</code>.</p>
    </div><p className="staff-login-copyright">GreenCity · Hệ thống quản lý vận hành khu đô thị</p></section>
  </main>;
}
