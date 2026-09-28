import React, { useState } from 'react';
import { AlertCircle, ArrowRight, Info, LockKeyhole, LoaderCircle, Monitor, ShieldCheck } from 'lucide-react';
import { GreenCityLogo } from '../GreenCityLogo';
import './staff.css';

export function PasswordChange({ username, onChangePassword, onLogout, error = null, isLoading = false }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [formError, setFormError] = useState('');

  const submit = event => {
    event.preventDefault();
    setFormError('');
    if (newPassword.length < 12) {
      setFormError('Mật khẩu mới cần có ít nhất 12 ký tự.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setFormError('Hai lần nhập mật khẩu mới chưa khớp.');
      return;
    }
    void onChangePassword({ currentPassword, newPassword });
  };

  const visibleError = formError ? { message: formError } : error;

  return <main className="staff-login password-change-page">
    <section className="staff-login-story" aria-label="Bảo vệ tài khoản GreenCity">
      <GreenCityLogo />
      <div className="staff-story-content">
        <span className="staff-overline">GREENCITY / ACCOUNT SECURITY</span>
        <h1>Bảo vệ tài khoản<br />trước khi tiếp tục.</h1>
        <p>Mật khẩu cấp ban đầu chỉ dùng để mở phiên đầu tiên. Hãy đổi mật khẩu để vào không gian làm việc.</p>
        <div className="password-change-callout"><ShieldCheck size={20} aria-hidden="true" /><span><strong>Phiên giới hạn</strong><small>Chỉ đổi mật khẩu hoặc đăng xuất cho đến khi hoàn tất.</small></span></div>
      </div>
      <p className="staff-story-footer">Quyền và phạm vi tiếp tục được xác minh bởi máy chủ.</p>
    </section>
    <section className="staff-login-form-side">
      <div className="staff-login-card">
        <div className="staff-login-badge"><Monitor size={15} aria-hidden="true" />Bảo mật tài khoản</div>
        <h2>Đổi mật khẩu</h2>
        <p className="staff-login-intro">Tài khoản <strong>{username}</strong> cần mật khẩu riêng trước khi mở GreenCity.</p>
        {visibleError && <div role="alert" className="staff-login-error"><AlertCircle size={18} aria-hidden="true" /><div><strong>Chưa đổi được mật khẩu</strong><p>{visibleError.message}</p>{visibleError.correlationId && <small>Mã đối chiếu: {visibleError.correlationId}</small>}</div></div>}
        <form onSubmit={submit} aria-busy={isLoading}>
          <label className="field-label" htmlFor="current-password">Mật khẩu hiện tại</label>
          <div className="staff-password-input"><LockKeyhole size={16} aria-hidden="true" /><input id="current-password" name="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} disabled={isLoading} required /></div>
          <label className="field-label" htmlFor="new-password">Mật khẩu mới</label>
          <div className="staff-password-input"><LockKeyhole size={16} aria-hidden="true" /><input id="new-password" name="new-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} value={newPassword} onChange={event => setNewPassword(event.target.value)} disabled={isLoading} required /></div>
          <p className="password-change-hint">Dùng ít nhất 12 ký tự và không dùng lại mật khẩu hiện tại.</p>
          <label className="field-label" htmlFor="confirm-password">Nhập lại mật khẩu mới</label>
          <div className="staff-password-input"><LockKeyhole size={16} aria-hidden="true" /><input id="confirm-password" name="confirm-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} disabled={isLoading} required /></div>
          <button className="button-primary staff-login-submit" type="submit" disabled={isLoading || !currentPassword || !newPassword || !confirmPassword}>
            <span>{isLoading ? 'Đang cập nhật…' : 'Đổi mật khẩu'}</span>{isLoading ? <LoaderCircle className="request-spinner" size={18} aria-hidden="true" /> : <ArrowRight size={18} aria-hidden="true" />}
          </button>
        </form>
        <button type="button" className="button-text staff-login-help" onClick={onLogout}>Đăng xuất</button>
        <p className="staff-login-disclaimer"><Info size={15} aria-hidden="true" />Sau khi đổi mật khẩu, phiên hiện tại sẽ kết thúc và bạn cần đăng nhập lại.</p>
      </div>
      <p className="staff-login-copyright">GreenCity · Hệ thống quản lý vận hành khu đô thị</p>
    </section>
  </main>;
}
