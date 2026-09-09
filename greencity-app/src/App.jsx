import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Layers, Info, ShieldCheck } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { RefundFormView } from './components/RefundFormView';
import { TasksDesktopView, StatusBadge } from './components/TasksDesktopView';
import { NotificationsDesktopView } from './components/NotificationsDesktopView';
import { MediaChannelsView } from './components/MediaChannelsView';
import { UrbanAmenitiesView } from './components/UrbanAmenitiesView';
import { SearchDialog } from './components/SearchDialog';
import { Dialog } from './components/Dialog';
import { ConfirmModal } from './components/ConfirmModal';
import { Toast } from './components/Toast';
import { GreenAssistant } from './components/assistant/GreenAssistant';
import { navItems } from './data/mockData';
import { DRAFT_KEY, loadRefundDraft, saveRefundDraft } from './data/refundForm';
import { StaffLogin } from './components/staff/StaffLogin';
import { StaffDashboard, StaffAdminView, StaffReportsView } from './components/staff/StaffDashboard';
import { RefundReview } from './components/staff/RefundReview';
import { STAFF_SESSION_KEY, loadStaffSession, getAllowedNav, getScopedTasks, getScopedNotifications, canViewTab, canSubmitRefund, canApproveRefund } from './data/staffRoles';
import { requestDemoReply } from './services/greenAssistant';
import { ASSISTANT_STORAGE_KEY } from './data/assistantStore';

const tabFromLocation = () => {
  const id = window.location.hash.replace(/^#\/?/, '');
  return navItems.some(item => item.id === id) ? id : 'overview';
};
const readDraft = key => { try { return loadRefundDraft(window.sessionStorage, key); } catch { return null; } };

export default function App() {
  const [account, setAccount] = useState(() => { try { return loadStaffSession(window.sessionStorage); } catch { return null; } });
  const [sessionNotice, setSessionNotice] = useState('');
  const login = selected => {
    if (!selected) return;
    try { window.sessionStorage.setItem(STAFF_SESSION_KEY, JSON.stringify({ accountId: selected.accountId })); setSessionNotice(''); }
    catch { setSessionNotice('Không lưu được phiên mẫu trong tab. Tải lại ứng dụng sẽ trở về màn đăng nhập.'); }
    setAccount(selected);
  };
  const logout = () => {
    try { window.sessionStorage.removeItem(STAFF_SESSION_KEY); setSessionNotice('Đã kết thúc phiên mẫu. Chọn tài khoản để tiếp tục.'); }
    catch { setSessionNotice('Đã rời giao diện nhưng không xóa được phiên mẫu đã lưu. Hãy kiểm tra quyền lưu trữ của trình duyệt.'); }
    window.history.replaceState(null, '', '#/overview');
    setAccount(null);
  };
  if (!account) return <StaffLogin onLogin={login} notice={sessionNotice} />;
  return <StaffWorkspace key={account.accountId} account={account} onLogout={logout} sessionNotice={sessionNotice} />;
}

function StaffWorkspace({ account, onLogout, sessionNotice }) {
  const tasks = useMemo(() => getScopedTasks(account), [account]);
  const availableNav = useMemo(() => getAllowedNav(account), [account]);
  const draftKey = `${DRAFT_KEY}:${account.accountId}`;
  const assistantReply = useCallback(args => requestDemoReply({ ...args, visibleTasks: tasks, allowedTabs: account.menu, roleLabel: account.label }), [tasks, account]);
  const [currentTab, setCurrentTab] = useState(tabFromLocation);
  const [collapsed, setCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState(null);
  const [filters, setFilters] = useState({ query: '', status: 'all', department: 'all', sort: 'asc' });
  const [notifications, setNotifications] = useState(() => getScopedNotifications(account));
  const [draft, setDraft] = useState(() => readDraft(draftKey));
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState(null);
  const [pendingForm, setPendingForm] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [toast, setToast] = useState({ message: '', type: 'success', id: 0 });
  const [visited, setVisited] = useState(() => new Set([tabFromLocation()]));
  const returnTab = useRef('overview');
  const mainRef = useRef(null);
  const positions = useRef({});
  const submitTimer = useRef(null);
  const submittingRef = useRef(false);

  const showToast = useCallback((message, type = 'success') => setToast({ message, type, id: Date.now() }), []);
  useEffect(() => {
    if (!toast.message) return;
    const timer = setTimeout(() => setToast(previous => ({ ...previous, message: '' })), 5000);
    return () => clearTimeout(timer);
  }, [toast.id, toast.message]);
  useEffect(() => () => clearTimeout(submitTimer.current), []);

  const changeTab = useCallback((id, fromHistory = false) => {
    if (id === currentTab) return;
    positions.current[currentTab] = mainRef.current?.scrollTop || 0;
    if (id === 'refund-form') returnTab.current = currentTab;
    if (!fromHistory) window.history.pushState(null, '', `#/${id}`);
    setCurrentTab(id);
    setVisited(previous => new Set([...previous, id]));
    setDirty(false);
  }, [currentTab]);

  const navigate = useCallback((id, fromHistory = false) => {
    if (id === currentTab) return;
    if (currentTab === 'refund-form' && dirty) {
      setPendingNavigation({ id, fromHistory });
      return;
    }
    changeTab(id, fromHistory);
  }, [currentTab, dirty, changeTab]);

  useEffect(() => {
    document.title = `${navItems.find(item => item.id === currentTab)?.label || 'Tổng quan'} · GreenCity`;
    mainRef.current?.focus({ preventScroll: true });
    if (mainRef.current) mainRef.current.scrollTop = positions.current[currentTab] || 0;
  }, [currentTab]);
  useEffect(() => {
    const onPopState = () => navigate(tabFromLocation(), true);
    const onKeyDown = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        if (document.querySelector('dialog[open]')) return;
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('popstate', onPopState);
    window.addEventListener('keydown', onKeyDown);
    return () => { window.removeEventListener('popstate', onPopState); window.removeEventListener('keydown', onKeyDown); };
  }, [navigate]);
  useEffect(() => {
    if (!dirty) return;
    const warn = event => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const openForm = () => navigate('refund-form');
  const selectTask = task => {
    if (!tasks.some(item => item.id === task.id)) return;
    if (task.actionForm && canViewTab(account, 'refund-form')) openForm();
    else setSelectedTask(task);
  };
  const saveDraft = data => {
    if (!canSubmitRefund(account)) return false;
    try {
      saveRefundDraft(window.sessionStorage, data, draftKey);
      setDraft(data);
      setDirty(false);
      showToast('Đã lưu bản nháp trong tab này, chưa lưu lên máy chủ.', 'info');
      return true;
    } catch {
      showToast('Không lưu được bản nháp. Trình duyệt đang chặn lưu trữ hoặc đã hết dung lượng. Giữ phiếu mở và thử lại.', 'warning');
      return false;
    }
  };
  const confirmSubmit = () => {
    if (!canSubmitRefund(account) && !canApproveRefund(account)) return;
    if (submittingRef.current) return;
    submittingRef.current = true;
    setIsSubmitting(true);
    submitTimer.current = setTimeout(() => {
      let cleared = true;
      try { if (canSubmitRefund(account)) window.sessionStorage.removeItem(draftKey); } catch { cleared = false; }
      setIsSubmitting(false);
      submittingRef.current = false;
      setPendingForm(null);
      setDraft(null);
      setDirty(false);
      changeTab(returnTab.current);
      showToast(cleared ? 'Đã hoàn tất mô phỏng. Chưa gửi lệnh chuyển tiền hoặc tạo bút toán.' : 'Đã hoàn tất mô phỏng nhưng không xóa được bản nháp cũ trong tab. Không có giao dịch thật.', cleared ? 'success' : 'warning');
    }, 650);
  };
  const cancelNavigation = () => {
    if (pendingNavigation?.fromHistory) window.history.replaceState(null, '', `#/${currentTab}`);
    setPendingNavigation(null);
  };
  const readNotification = id => setNotifications(previous => previous.map(item => item.id === id ? { ...item, unread: false } : item));
  const unreadCount = notifications.filter(item => item.unread).length;
  const activeName = navItems.find(item => item.id === currentTab)?.label || 'Tổng quan';
  const implemented = ['overview', 'tasks', 'notifications', 'refund-form', 'amenities', 'media', 'settings', 'reports', 'technical', 'cleaning', 'security'];
  const allowed = canViewTab(account, currentTab);
  const department = { technical: 'Kỹ thuật', cleaning: 'Vệ sinh', security: 'An ninh' }[currentTab];

  return <>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); mainRef.current?.focus(); }}>Đến nội dung chính</a>
    <div className="desktop-shell">
      <Sidebar currentTab={currentTab} setCurrentTab={navigate} navItems={availableNav} collapsed={collapsed} setCollapsed={setCollapsed} activeSite={account.site} taskCount={tasks.length} unreadCount={unreadCount} account={account} onLogout={() => setLogoutOpen(true)} />
      <div className="desktop-content">
        <Header onSearch={() => setSearchOpen(true)} onOpenForm={currentTab === 'overview' ? undefined : () => navigate(account.primary)} primaryLabel={account.primaryLabel} roleLabel={account.label} onNotifications={() => navigate('notifications')} unreadCount={unreadCount} activeBreadcrumb={allowed ? activeName : 'Ngoài phạm vi'} />
        <main id="main-content" ref={mainRef} tabIndex={-1} className="desktop-main">
          <div className="demo-notice"><Info size={16} aria-hidden="true" /><span><strong>Bản minh họa desktop.</strong> Dữ liệu mẫu; chưa kết nối máy chủ, ngân hàng hoặc kênh truyền thông.</span></div>
          {sessionNotice && <p className="context-note" role="status">{sessionNotice}</p>}
          {allowed ? <>
          {currentTab === 'overview' && <StaffDashboard account={account} items={tasks} onNavigate={navigate} onSelectTask={selectTask} onFilterTasks={status => { setFilters({ query: '', status, department: 'all', sort: 'asc' }); navigate('tasks'); }} />}
          {currentTab === 'tasks' && <TasksDesktopView tasks={tasks} scopeLabel={account.scope} filters={filters} onFiltersChange={setFilters} onSelectTask={selectTask} />}
          {department && <TasksDesktopView tasks={tasks.filter(task => task.department === department)} title={activeName} scopeLabel={account.scope} filters={filters} onFiltersChange={setFilters} onSelectTask={selectTask} />}
          {currentTab === 'settings' && <StaffAdminView />}
          {currentTab === 'reports' && <StaffReportsView account={account} items={tasks} />}
          {currentTab === 'refund-form' && (canSubmitRefund(account) ? <RefundFormView initialData={draft} onDirtyChange={setDirty} onBack={() => navigate(returnTab.current)} onSaveDraft={saveDraft} onSubmitForm={setPendingForm} /> : <RefundReview account={account} onBack={() => navigate(returnTab.current)} onApprove={setPendingForm} />)}
          {currentTab === 'notifications' && <NotificationsDesktopView notifications={notifications} onRead={readNotification} onReadAll={() => { setNotifications(previous => previous.map(item => ({ ...item, unread: false }))); showToast('Đã đánh dấu tất cả thông báo là đã đọc.'); }} onOpen={item => { readNotification(item.id); const task = tasks.find(entry => entry.id === item.taskId); if (task) selectTask(task); }} />}
          {canViewTab(account, 'amenities') && visited.has('amenities') && <div hidden={currentTab !== 'amenities'}><UrbanAmenitiesView onToast={showToast} /></div>}
          {canViewTab(account, 'media') && visited.has('media') && <div hidden={currentTab !== 'media'}><MediaChannelsView onToast={showToast} onOpenServiceRequest={() => showToast('Chưa có kết nối tiếp nhận yêu cầu. Tin nhắn mẫu chưa được chuyển thành hồ sơ.', 'info')} /></div>}
          {!implemented.includes(currentTab) && <div className="desktop-page"><div className="page-heading"><div><p className="eyebrow">Phân hệ trong lộ trình</p><h1>{activeName}</h1></div><span className="subtle-badge">Chưa triển khai</span></div><section className="surface empty-state"><Layers size={36} aria-hidden="true" /><h2>Phân hệ chưa có chức năng xử lý</h2><p>Mục này được giữ để thể hiện phạm vi sản phẩm. Bạn có thể theo dõi công việc hiện có từ danh sách điều phối.</p><button className="button-primary" onClick={() => navigate('tasks')}>Mở Công việc & Yêu cầu</button><button className="button-text" onClick={() => navigate('overview')}>Về Tổng quan</button></section></div>}
          </> : <div className="desktop-page"><section className="surface empty-state"><ShieldCheck size={38} aria-hidden="true" /><h1>Không có quyền xem phân hệ này</h1><p>Tài khoản {account.label} không được cấp mục này trong bản giao diện. Hãy chọn một mục trong menu hoặc liên hệ Admin khi có hệ thống thật.</p><button className="button-primary" onClick={() => navigate('overview')}>Về không gian của tôi</button></section></div>}
        </main>
        <footer className="desktop-statusbar"><span>{account.scope} · Phiên mẫu</span><span>Ctrl K · Tìm trong phạm vi</span></footer>
      </div>
    </div>
    <SearchDialog navItems={availableNav} tasks={tasks} open={searchOpen} onClose={() => setSearchOpen(false)} onNavigate={navigate} onSelectTask={selectTask} />
    <Dialog open={Boolean(selectedTask)} onClose={() => setSelectedTask(null)} title={selectedTask?.id || 'Chi tiết công việc'}>
      {selectedTask && <div className="dialog-body"><StatusBadge task={selectedTask} /><h3 className="task-detail-title">{selectedTask.title}</h3><dl className="confirmation-details"><div><dt>Vị trí</dt><dd>{selectedTask.location}</dd></div><div><dt>Bộ phận</dt><dd>{selectedTask.department}</dd></div><div><dt>Hạn xử lý</dt><dd>{selectedTask.deadline}</dd></div></dl><p className="context-note">Hồ sơ mẫu, chỉ xem thông tin. Phân công, đổi trạng thái và nhật ký thực hiện chưa được triển khai.</p></div>}
      <div className="dialog-actions"><button className="button-secondary" onClick={() => setSelectedTask(null)}>Đóng chi tiết</button></div>
    </Dialog>
    <Dialog open={Boolean(pendingNavigation)} onClose={cancelNavigation} title="Phiếu có thay đổi chưa lưu">
      <div className="dialog-body"><p>Nếu rời đi, những thay đổi sau lần lưu nháp gần nhất sẽ bị mất. Chọn Ở lại để tiếp tục hoặc lưu bản nháp trước.</p></div>
      <div className="dialog-actions"><button className="button-secondary" onClick={cancelNavigation}>Ở lại</button><button className="button-danger" onClick={() => { const target = pendingNavigation; setPendingNavigation(null); changeTab(target.id, target.fromHistory); }}>Rời đi, bỏ thay đổi</button></div>
    </Dialog>
    <Dialog open={logoutOpen} onClose={() => setLogoutOpen(false)} title="Đăng xuất tài khoản mẫu?"><div className="dialog-body"><p>{dirty ? 'Phiếu có thay đổi chưa lưu. Chọn Ở lại để lưu nháp trước khi đăng xuất.' : 'Nháp hoàn tiền đã lưu và lịch sử trợ lý vẫn thuộc tài khoản này. Nội dung chưa lưu tại các màn khác có thể mất khi kết thúc phiên.'}</p></div><div className="dialog-actions"><button className="button-secondary" onClick={() => setLogoutOpen(false)}>Ở lại</button><button className="button-danger" onClick={onLogout}>Đăng xuất</button></div></Dialog>
    <ConfirmModal isOpen={Boolean(pendingForm)} onClose={() => { if (!isSubmitting) setPendingForm(null); }} onConfirm={confirmSubmit} data={pendingForm} isLoading={isSubmitting} actionLabel={canSubmitRefund(account) ? 'Trình duyệt mô phỏng' : 'Phê duyệt mô phỏng'} />
    <Toast message={toast.message} type={toast.type} onClose={() => setToast(previous => ({ ...previous, message: '' }))} />
    <GreenAssistant contextKey={currentTab} historyKey={`${ASSISTANT_STORAGE_KEY}:${account.accountId}`} requestReply={assistantReply} suggestions={canViewTab(account, 'refund-form') ? ['Xem công việc quá hạn', 'Hướng dẫn kiểm tra phiếu hoàn tiền'] : ['Xem công việc quá hạn', 'Hướng dẫn xem thông báo']} />
  </>;
}
