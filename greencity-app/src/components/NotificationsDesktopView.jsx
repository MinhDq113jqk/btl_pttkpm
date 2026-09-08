import React, { useState } from 'react';
import { Bell, CheckCheck, Check } from 'lucide-react';

export function NotificationsDesktopView({ notifications, onRead, onReadAll, onOpen }) {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const unread = notifications.filter(item => item.unread).length;
  const visible = notifications.filter(item => !unreadOnly || item.unread);
  return <div className="desktop-page">
    <div className="page-heading"><div><p className="eyebrow">Hộp thư điều hành</p><h1>Thông báo</h1><p role="status">{unread} thông báo chưa đọc · Trạng thái giữ trong phiên làm việc.</p></div><button className="button-secondary" onClick={onReadAll} disabled={unread === 0}><CheckCheck size={18} aria-hidden="true" />Đánh dấu tất cả đã đọc</button></div>
    <section className="surface"><div className="status-filters"><button aria-pressed={!unreadOnly} className={!unreadOnly ? 'is-selected' : ''} onClick={() => setUnreadOnly(false)}>Tất cả <span>{notifications.length}</span></button><button aria-pressed={unreadOnly} className={unreadOnly ? 'is-selected' : ''} onClick={() => setUnreadOnly(true)}>Chưa đọc <span>{unread}</span></button></div>
      {visible.map(item => <article key={item.id} className={`notification-row ${item.unread ? 'is-unread' : ''}`}><div className="notification-symbol"><Bell size={20} aria-hidden="true" /></div><div className="notification-content"><div className="notification-title"><h2>{item.title}</h2><span>{item.time}</span></div><p>{item.detail}</p><div className="notification-controls">{item.taskId && <button className="button-text" onClick={() => onOpen(item)}>Mở hồ sơ liên quan</button>}{item.unread ? <button className="button-text" onClick={() => onRead(item.id)}><Check size={15} aria-hidden="true" />Đánh dấu đã đọc</button> : <span className="helper-text">Đã đọc</span>}</div></div></article>)}
      {visible.length === 0 && <div className="empty-state"><CheckCheck size={32} aria-hidden="true" /><h2>Bạn đã đọc hết thông báo</h2><p>Các thông báo vẫn có trong mục Tất cả.</p><button className="button-secondary" onClick={() => setUnreadOnly(false)}>Xem tất cả thông báo</button></div>}
    </section>
  </div>;
}
