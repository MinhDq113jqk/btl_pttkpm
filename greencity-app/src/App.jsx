import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Layers, Info } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { DashboardView } from './components/DashboardView';
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
import { navItems, currentUser } from './data/mockData';
import { tasks, initialNotifications } from './data/desktopData';
import { DRAFT_KEY, loadRefundDraft, saveRefundDraft } from './data/refundForm';

const tabFromLocation = () => {
  const id = window.location.hash.replace(/^#\/?/, '');
  return navItems.some(item => item.id === id) ? id : 'overview';
};
const readDraft = () => { try { return loadRefundDraft(window.sessionStorage); } catch { return null; } };

export default function App() {
  const [currentTab, setCurrentTab] = useState(tabFromLocation);
  const [collapsed, setCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState(null);
  const [filters, setFilters] = useState({ query: '', status: 'all', department: 'all', sort: 'asc' });
  const [notifications, setNotifications] = useState(initialNotifications);
  const [draft, setDraft] = useState(readDraft);
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
  const selectTask = task => task.actionForm ? openForm() : setSelectedTask(task);
  const saveDraft = data => {
    try {
      saveRefundDraft(window.sessionStorage, data);
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
    if (submittingRef.current) return;
    submittingRef.current = true;
    setIsSubmitting(true);
    submitTimer.current = setTimeout(() => {
      let cleared = true;
      try { window.sessionStorage.removeItem(DRAFT_KEY); } catch { cleared = false; }
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
  const implemented = ['overview', 'tasks', 'notifications', 'refund-form', 'amenities', 'media'];

  return <>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); mainRef.current?.focus(); }}>Đến nội dung chính</a>
    <div className="desktop-shell">
      <Sidebar currentTab={currentTab} setCurrentTab={navigate} navItems={navItems} collapsed={collapsed} setCollapsed={setCollapsed} activeSite={currentUser.currentSite} taskCount={tasks.length} unreadCount={unreadCount} />
      <div className="desktop-content">
        <Header onSearch={() => setSearchOpen(true)} onOpenForm={openForm} onNotifications={() => navigate('notifications')} unreadCount={unreadCount} activeBreadcrumb={activeName} />
        <main id="main-content" ref={mainRef} tabIndex={-1} className="desktop-main">
          <div className="demo-notice"><Info size={16} aria-hidden="true" /><span><strong>Bản minh họa desktop.</strong> Dữ liệu mẫu; chưa kết nối máy chủ, ngân hàng hoặc kênh truyền thông.</span></div>
          {currentTab === 'overview' && <DashboardView onSelectTask={selectTask} onOpenForm={openForm} onViewAll={() => navigate('tasks')} onFilterTasks={status => { setFilters({ query: '', status, department: 'all', sort: 'asc' }); navigate('tasks'); }} />}
          {currentTab === 'tasks' && <TasksDesktopView filters={filters} onFiltersChange={setFilters} onSelectTask={selectTask} />}
          {currentTab === 'refund-form' && <RefundFormView initialData={draft} onDirtyChange={setDirty} onBack={() => navigate(returnTab.current)} onSaveDraft={saveDraft} onSubmitForm={setPendingForm} />}
          {currentTab === 'notifications' && <NotificationsDesktopView notifications={notifications} onRead={readNotification} onReadAll={() => { setNotifications(previous => previous.map(item => ({ ...item, unread: false }))); showToast('Đã đánh dấu tất cả thông báo là đã đọc.'); }} onOpen={item => { readNotification(item.id); const task = tasks.find(entry => entry.id === item.taskId); if (task) selectTask(task); }} />}
          {visited.has('amenities') && <div hidden={currentTab !== 'amenities'}><UrbanAmenitiesView onToast={showToast} /></div>}
          {visited.has('media') && <div hidden={currentTab !== 'media'}><MediaChannelsView onToast={showToast} onOpenServiceRequest={() => showToast('Chưa có kết nối tiếp nhận yêu cầu. Tin nhắn mẫu chưa được chuyển thành hồ sơ.', 'info')} /></div>}
          {!implemented.includes(currentTab) && <div className="desktop-page"><div className="page-heading"><div><p className="eyebrow">Phân hệ trong lộ trình</p><h1>{activeName}</h1></div><span className="subtle-badge">Chưa triển khai</span></div><section className="surface empty-state"><Layers size={36} aria-hidden="true" /><h2>Phân hệ chưa có chức năng xử lý</h2><p>Mục này được giữ để thể hiện phạm vi sản phẩm. Bạn có thể theo dõi công việc hiện có từ danh sách điều phối.</p><button className="button-primary" onClick={() => navigate('tasks')}>Mở Công việc & Yêu cầu</button><button className="button-text" onClick={() => navigate('overview')}>Về Tổng quan</button></section></div>}
        </main>
        <footer className="desktop-statusbar"><span>GreenCity Central · Chế độ minh họa</span><span>Ctrl K · Tìm kiếm nhanh</span></footer>
      </div>
    </div>
    <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} onNavigate={navigate} onSelectTask={selectTask} />
    <Dialog open={Boolean(selectedTask)} onClose={() => setSelectedTask(null)} title={selectedTask?.id || 'Chi tiết công việc'}>
      {selectedTask && <div className="dialog-body"><StatusBadge task={selectedTask} /><h3 className="task-detail-title">{selectedTask.title}</h3><dl className="confirmation-details"><div><dt>Vị trí</dt><dd>{selectedTask.location}</dd></div><div><dt>Bộ phận</dt><dd>{selectedTask.department}</dd></div><div><dt>Hạn xử lý</dt><dd>{selectedTask.deadline}</dd></div></dl><p className="context-note">Hồ sơ mẫu, chỉ xem thông tin. Phân công, đổi trạng thái và nhật ký thực hiện chưa được triển khai.</p></div>}
      <div className="dialog-actions"><button className="button-secondary" onClick={() => setSelectedTask(null)}>Đóng chi tiết</button></div>
    </Dialog>
    <Dialog open={Boolean(pendingNavigation)} onClose={cancelNavigation} title="Phiếu có thay đổi chưa lưu">
      <div className="dialog-body"><p>Nếu rời đi, những thay đổi sau lần lưu nháp gần nhất sẽ bị mất. Chọn Ở lại để tiếp tục hoặc lưu bản nháp trước.</p></div>
      <div className="dialog-actions"><button className="button-secondary" onClick={cancelNavigation}>Ở lại</button><button className="button-danger" onClick={() => { const target = pendingNavigation; setPendingNavigation(null); changeTab(target.id, target.fromHistory); }}>Rời đi, bỏ thay đổi</button></div>
    </Dialog>
    <ConfirmModal isOpen={Boolean(pendingForm)} onClose={() => { if (!isSubmitting) setPendingForm(null); }} onConfirm={confirmSubmit} data={pendingForm} isLoading={isSubmitting} />
    <Toast message={toast.message} type={toast.type} onClose={() => setToast(previous => ({ ...previous, message: '' }))} />
    <GreenAssistant contextKey={currentTab} />
  </>;
}
