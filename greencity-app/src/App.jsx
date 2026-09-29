import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Info, ShieldCheck } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { TasksDesktopView } from './components/TasksDesktopView';
import { Unit360View } from './components/Unit360View';
import { NotificationsDesktopView } from './components/NotificationsDesktopView';
import { SearchDialog } from './components/SearchDialog';
import { Dialog } from './components/Dialog';
import { Toast } from './components/Toast';
import { GreenAssistant } from './components/assistant/GreenAssistant';
import { SessionDashboard } from './components/staff/SessionDashboard';
import { ExecutiveDashboardView } from './components/ExecutiveDashboardView';
import { StaffLogin } from './components/staff/StaffLogin';
import { PasswordChange } from './components/staff/PasswordChange';
import { CreateServiceRequestForm } from './components/staff/CreateServiceRequestForm';
import { CleaningDesktopView } from './components/CleaningDesktopView';
import { SecurityDesktopView } from './components/SecurityDesktopView';
import { ParcelDeskView } from './components/ParcelDeskView';
import { BillingDesktopView } from './components/BillingDesktopView';
import { ResidentPortalView } from './components/ResidentPortalView';
import { navItems } from './data/navigation';
import { ASSISTANT_STORAGE_KEY, clearAssistantHistoryForAccount } from './data/assistantStore';
import { canViewTab, createAuthenticatedAccount, getAllowedNav, getStaffTabFromHash } from './data/authSession';
import { mapServiceRequest } from './data/serviceRequestView';
import { createApiClient } from './services/apiClient';
import { requestAssistantReply } from './services/greenAssistant';

const WorkOrderWorkspace = React.lazy(() => import('./components/WorkOrderWorkspace').then(module => ({ default: module.WorkOrderWorkspace })));
const ImportRunsView = React.lazy(() => import('./components/ImportRunsView').then(module => ({ default: module.ImportRunsView })));
const MaintenanceDesktopView = React.lazy(() => import('./components/MaintenanceDesktopView').then(module => ({ default: module.MaintenanceDesktopView })));

const tabFromLocation = () => getStaffTabFromHash(window.location.hash);

const loginErrorView = error => ({
  message: error?.code === 'ERR-NETWORK'
    ? 'Không thể kết nối backend. Kiểm tra cấu hình API và kết nối mạng rồi thử lại.'
    : error?.message || 'Không thể hoàn tất đăng nhập.',
  correlationId: error?.correlationId || '',
});

const siteSwitchErrorView = error => ({
  message: error?.code === 'ERR-SCOPE-NOTFOUND'
    ? 'Site này không còn nằm trong phạm vi phiên hiện tại.'
    : error?.code === 'ERR-NETWORK'
      ? 'Không thể đổi site vì mất kết nối. Phạm vi cũ vẫn được giữ.'
      : error?.message || 'Không thể đổi site làm việc.',
  correlationId: error?.correlationId || '',
});

export default function App() {
  const [account, setAccount] = useState(null);
  const [sessionNotice, setSessionNotice] = useState('');
  const [loginError, setLoginError] = useState(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [isSwitchingSite, setIsSwitchingSite] = useState(false);
  const [siteSwitchError, setSiteSwitchError] = useState(null);
  const [passwordChangeError, setPasswordChangeError] = useState(null);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [workspaceReset, setWorkspaceReset] = useState(0);
  const clientRef = useRef(null);
  const accountRef = useRef(account);
  accountRef.current = account;

  const clearAccountAssistantHistory = () => {
    try {
      clearAssistantHistoryForAccount(window.localStorage, accountRef.current?.accountId);
      return true;
    } catch {
      return false;
    }
  };

  if (!clientRef.current) {
    clientRef.current = createApiClient({
      onUnauthorized: error => {
        const historyCleared = clearAccountAssistantHistory();
        setAccount(null);
        setLoginError(null);
        setSiteSwitchError(null);
        setSessionNotice(`Phiên đã hết hạn. Vui lòng đăng nhập lại.${historyCleared ? '' : ' Không xóa được lịch sử trợ lý; hãy xóa dữ liệu website trong cài đặt trình duyệt.'}${error.correlationId ? ` Mã đối chiếu: ${error.correlationId}` : ''}`);
      },
    });
  }

  const login = async ({ username, password }) => {
    setIsLoggingIn(true);
    setLoginError(null);
    setSessionNotice('');
    try {
      const user = await clientRef.current.authenticate(username, password);
      setAccount(createAuthenticatedAccount(user));
      setSiteSwitchError(null);
      setPasswordChangeError(null);
      setWorkspaceReset(0);
    } catch (error) {
      setLoginError(loginErrorView(error));
    } finally {
      setIsLoggingIn(false);
    }
  };

  const logout = async () => {
    const historyCleared = clearAccountAssistantHistory();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    let sessionRevoked = false;
    try {
      sessionRevoked = await clientRef.current.logoutCurrentSession({ signal: controller.signal });
    } finally {
      clearTimeout(timeout);
    }
    window.history.replaceState(null, '', '#/overview');
    setLoginError(null);
    setSiteSwitchError(null);
    setSessionNotice(`Đã đăng xuất.${sessionRevoked ? ' Phiên đã được thu hồi trên máy chủ.' : ' Máy chủ chưa xác nhận thu hồi phiên; hãy đăng xuất lại khi có kết nối.'}${historyCleared ? '' : ' Không xóa được lịch sử trợ lý; hãy xóa dữ liệu website trong cài đặt trình duyệt.'}`);
    setAccount(null);
  };

  const changePassword = async ({ currentPassword, newPassword }) => {
    setIsChangingPassword(true);
    setPasswordChangeError(null);
    try {
      await clientRef.current.changePassword(currentPassword, newPassword);
      const historyCleared = clearAccountAssistantHistory();
      window.history.replaceState(null, '', '#/overview');
      setLoginError(null);
      setAccount(null);
      setSessionNotice(`Mật khẩu đã được đổi. Hãy đăng nhập lại bằng mật khẩu mới.${historyCleared ? '' : ' Không xóa được lịch sử trợ lý; hãy xóa dữ liệu website trong cài đặt trình duyệt.'}`);
    } catch (error) {
      setPasswordChangeError({
        message: error?.message || 'Không thể đổi mật khẩu. Hãy thử lại.',
        correlationId: error?.correlationId || '',
      });
    } finally {
      setIsChangingPassword(false);
    }
  };

  const switchSite = async siteId => {
    if (!account || !siteId || siteId === account.activeSiteId || isSwitchingSite) return;
    setIsSwitchingSite(true);
    setSiteSwitchError(null);
    try {
      const user = await clientRef.current.switchSite(siteId);
      setAccount(createAuthenticatedAccount(user));
    } catch (error) {
      if (error?.name !== 'AbortError') {
        setSiteSwitchError(siteSwitchErrorView(error));
        // Requests from the previous revision were discarded; remount to reload the retained site.
        setWorkspaceReset(value => value + 1);
      }
    } finally {
      setIsSwitchingSite(false);
    }
  };

  if (!account) return <StaffLogin onLogin={login} notice={sessionNotice} error={loginError} isLoading={isLoggingIn} />;
  if (account.mustChangePassword) return <PasswordChange username={account.username} onChangePassword={changePassword}
    onLogout={logout} error={passwordChangeError} isLoading={isChangingPassword} />;
  if (account.isResident) return <ResidentPortalView account={account} client={clientRef.current}
    onLogout={logout} onSwitchSite={switchSite} isSwitchingSite={isSwitchingSite} siteSwitchError={siteSwitchError} />;
  return <StaffWorkspace key={`${account.workspaceKey}:${workspaceReset}`} account={account} client={clientRef.current}
    onLogout={logout} onSwitchSite={switchSite} isSwitchingSite={isSwitchingSite} siteSwitchError={siteSwitchError} />;
}

function StaffWorkspace({ account, client, onLogout, onSwitchSite, isSwitchingSite, siteSwitchError }) {
  const availableNav = useMemo(() => getAllowedNav(account), [account]);
  const [currentTab, setCurrentTab] = useState(tabFromLocation);
  const [collapsed, setCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState(null);
  const [filters, setFilters] = useState({ query: '', status: 'all', sort: 'asc' });
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [retryKey, setRetryKey] = useState(0);
  const [requestState, setRequestState] = useState({ items: [], total: 0, loading: account.canViewServiceRequests, error: null });
  const [unreadCount, setUnreadCount] = useState(0);
  const [dashboardAsOf, setDashboardAsOf] = useState(() => new Date().toISOString());
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [toast, setToast] = useState({ message: '', type: 'success', id: 0 });
  const [createRequestOpen, setCreateRequestOpen] = useState(false);
  const mainRef = useRef(null);
  const positions = useRef({});

  const tasks = requestState.items;
  const showToast = useCallback((message, type = 'success') => setToast({ message, type, id: Date.now() }), []);
  const assistantReply = useCallback(args => requestAssistantReply({ client, ...args }), [client]);

  useEffect(() => {
    if (!account.canViewServiceRequests) {
      setRequestState({ items: [], total: 0, loading: false, error: null });
      return undefined;
    }
    const controller = new AbortController();
    setRequestState(previous => ({ ...previous, loading: true, error: null }));
    client.listServiceRequests({
      status: filters.status === 'all' ? undefined : filters.status,
      page,
      page_size: pageSize,
      signal: controller.signal,
    }).then(result => {
      setRequestState({ items: result.items.map(item => mapServiceRequest(item)), total: result.total, loading: false, error: null });
    }).catch(error => {
      if (error?.name !== 'AbortError') setRequestState(previous => ({ ...previous, loading: false, error }));
    });
    return () => controller.abort();
  }, [account.canViewServiceRequests, client, filters.status, page, retryKey]);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = setTimeout(() => setToast(previous => ({ ...previous, message: '' })), 5000);
    return () => clearTimeout(timer);
  }, [toast.id, toast.message]);

  useEffect(() => {
    if (!client?.listNotifications) return undefined;
    const controller = new AbortController();
    client.listNotifications({
      includeRead: false,
      asOf: account.canViewExecutiveDashboard ? dashboardAsOf : undefined,
      signal: controller.signal,
    })
      .then(result => {
        setUnreadCount(result.items.length);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [client, account.workspaceKey, account.canViewExecutiveDashboard, dashboardAsOf]);

  const changeTab = useCallback(id => {
    const nextTab = getStaffTabFromHash(`#/${id}`);
    if (nextTab === currentTab) {
      if (window.location.hash !== `#/${nextTab}`) window.history.replaceState(null, '', `#/${nextTab}`);
      return;
    }
    positions.current[currentTab] = mainRef.current?.scrollTop || 0;
    window.history.pushState(null, '', `#/${nextTab}`);
    setCurrentTab(nextTab);
  }, [currentTab]);

  useEffect(() => {
    if (window.location.hash !== `#/${currentTab}`) window.history.replaceState(null, '', `#/${currentTab}`);
    document.title = `${navItems.find(item => item.id === currentTab)?.label || 'Tổng quan'} · GreenCity`;
    mainRef.current?.focus({ preventScroll: true });
    if (mainRef.current) mainRef.current.scrollTop = positions.current[currentTab] || 0;
  }, [currentTab]);

  useEffect(() => {
    const onLocationChange = () => {
      const nextTab = tabFromLocation();
      if (window.location.hash !== `#/${nextTab}`) window.history.replaceState(null, '', `#/${nextTab}`);
      setCurrentTab(nextTab);
    };
    const onKeyDown = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('popstate', onLocationChange);
    window.addEventListener('hashchange', onLocationChange);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('popstate', onLocationChange);
      window.removeEventListener('hashchange', onLocationChange);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const updateFilters = next => {
    if (next.status !== filters.status) setPage(1);
    setFilters(next);
  };
  const filterFromDashboard = status => {
    setPage(1);
    setFilters({ query: '', status, sort: 'asc' });
    changeTab('tasks');
  };
  const handleServiceRequestCreated = created => {
    setCreateRequestOpen(false);
    setPage(1);
    setFilters(previous => ({ ...previous, status: 'all' }));
    setRetryKey(value => value + 1);
    showToast(`Đã tạo yêu cầu ${created.code}.`);
  };
  const activeName = navItems.find(item => item.id === currentTab)?.label || 'Tổng quan';
  const allowed = canViewTab(account, currentTab);
  const scopeNotice = currentTab === 'cleaning'
    ? 'Ca, checklist và quyền thao tác vệ sinh đều do backend quyết định theo phiên hiện tại.'
      : currentTab === 'security'
        ? 'Ca trực, tuần tra, ngoại lệ và quyền thao tác an ninh đều do backend quyết định theo phiên hiện tại.'
      : currentTab === 'parcels'
        ? 'Bưu phẩm, PIN và quyền bàn giao đều do backend quyết định theo phiên hiện tại; PIN không được lưu ở frontend.'
      : currentTab === 'finance'
        ? 'Biểu phí, kỳ, Billing Run và hóa đơn đều do backend quyết định theo phiên hiện tại; giao diện không tự tính tiền.'
      : 'CSKH có thể tạo yêu cầu bằng lựa chọn máy chủ cấp; danh tính, danh sách và Unit 360° tiếp tục dùng cùng phiên thật.';

  return <>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); mainRef.current?.focus(); }}>Đến nội dung chính</a>
    <div className="desktop-shell">
      <Sidebar currentTab={currentTab} setCurrentTab={changeTab} navItems={availableNav} collapsed={collapsed} setCollapsed={setCollapsed}
        activeSite={account.site} activeSiteId={account.activeSiteId} allowedSites={account.allowedSites}
        onSwitchSite={onSwitchSite} isSwitchingSite={isSwitchingSite} siteSwitchError={siteSwitchError}
        taskCount={requestState.total} unreadCount={unreadCount} account={account} onLogout={() => setLogoutOpen(true)} />
      <div className="desktop-content">
        <Header onSearch={() => setSearchOpen(true)} onNotifications={() => changeTab('notifications')} unreadCount={unreadCount} activeBreadcrumb={allowed ? activeName : 'Ngoài phạm vi'} roleLabel={account.label} />
        <main id="main-content" ref={mainRef} tabIndex={-1} className="desktop-main">
          <div className="demo-notice"><Info size={16} aria-hidden="true" /><span><strong>Phiên và phạm vi do backend quyết định.</strong> {scopeNotice}</span></div>
          {allowed ? <>
            {currentTab === 'overview' && (account.canViewExecutiveDashboard
              ? <ExecutiveDashboardView account={account} client={client} onToast={showToast} onNavigate={changeTab}
                initialAsOf={dashboardAsOf} onAsOfChange={setDashboardAsOf} />
              : <SessionDashboard account={account} items={tasks} total={requestState.total} loading={requestState.loading} error={requestState.error} onRetry={() => setRetryKey(value => value + 1)} onNavigate={changeTab} onSelectTask={setSelectedTask} onFilterTasks={filterFromDashboard} />)}
            {currentTab === 'tasks' && <TasksDesktopView tasks={tasks} scopeLabel={account.scope} filters={filters} onFiltersChange={updateFilters} onSelectTask={setSelectedTask} loading={requestState.loading} error={requestState.error} onRetry={() => setRetryKey(value => value + 1)} pagination={{ page, pageSize, total: requestState.total }} onPageChange={setPage} canCreate={account.canCreateServiceRequests} onCreate={() => setCreateRequestOpen(true)} />}
            {currentTab === 'maintenance' && <React.Suspense fallback={<div className="desktop-page" role="status">Đang mở không gian bảo trì…</div>}><MaintenanceDesktopView account={account} client={client} /></React.Suspense>}
            {currentTab === 'cleaning' && <CleaningDesktopView account={account} client={client} onToast={showToast} />}
            {currentTab === 'security' && <SecurityDesktopView account={account} client={client} onToast={showToast} />}
            {currentTab === 'parcels' && <ParcelDeskView account={account} client={client} onToast={showToast} />}
            {currentTab === 'finance' && <BillingDesktopView account={account} client={client} onToast={showToast} />}
            {currentTab === 'imports' && <React.Suspense fallback={<div className="desktop-page" role="status">Đang mở màn nhập dữ liệu…</div>}><ImportRunsView account={account} client={client} /></React.Suspense>}
            {currentTab === 'residents' && <Unit360View client={client} scopeLabel={account.scope} />}
            {currentTab === 'notifications' && <NotificationsDesktopView account={account} client={client} onToast={showToast} onUnreadChange={setUnreadCount}
              asOf={account.canViewExecutiveDashboard ? dashboardAsOf : undefined} onOpen={item => {
              const taskId = item.taskId || item.template_snapshot?.task_id;
              if (taskId) {
                const matched = tasks.find(t => t.id === taskId || t.recordId === taskId);
                if (matched) setSelectedTask(matched);
              }
            }} />}
          </> : <div className="desktop-page"><section className="surface empty-state"><ShieldCheck size={38} aria-hidden="true" /><h1>Không có quyền xem phân hệ này</h1><p>Menu của phiên chỉ gồm các bề mặt được suy ra từ vai trò mà <code>/auth/me</code> trả về. Frontend không thể tự mở rộng phạm vi.</p><button className="button-primary" onClick={() => changeTab('overview')}>Về không gian của tôi</button></section></div>}
        </main>
        <footer className="desktop-statusbar"><span>{account.scope} · Phiên xác thực</span><span>Ctrl K · Tìm trong trang dữ liệu hiện tại</span></footer>
      </div>
    </div>
    <SearchDialog navItems={availableNav} tasks={tasks} open={searchOpen} onClose={() => setSearchOpen(false)} onNavigate={changeTab} onSelectTask={setSelectedTask} />
    <Dialog open={Boolean(selectedTask)} onClose={() => setSelectedTask(null)} title={selectedTask?.id || 'Chi tiết yêu cầu'}>
      {selectedTask && <React.Suspense fallback={<div className="dialog-body" role="status">Đang tải hồ sơ công việc…</div>}><WorkOrderWorkspace account={account} client={client} selectedTask={selectedTask} /></React.Suspense>}
      <div className="dialog-actions"><button className="button-secondary" onClick={() => setSelectedTask(null)}>Đóng chi tiết</button></div>
    </Dialog>
    <Dialog open={logoutOpen} onClose={() => setLogoutOpen(false)} title="Đăng xuất GreenCity?"><div className="dialog-body"><p>Token chỉ tồn tại trong bộ nhớ của phiên hiện tại. Khi đăng xuất, ứng dụng sẽ thử xóa lịch sử trợ lý của tài khoản trên thiết bị này.</p></div><div className="dialog-actions"><button className="button-secondary" onClick={() => setLogoutOpen(false)}>Ở lại</button><button className="button-danger" onClick={onLogout}>Đăng xuất</button></div></Dialog>
    <Dialog open={createRequestOpen} onClose={() => setCreateRequestOpen(false)} title="Tạo yêu cầu dịch vụ" busy={false} wide initialFocusId="service-request-building">
      {createRequestOpen && <CreateServiceRequestForm client={client} onCreated={handleServiceRequestCreated} onClose={() => setCreateRequestOpen(false)} />}
    </Dialog>
    <Toast message={toast.message} type={toast.type} onClose={() => setToast(previous => ({ ...previous, message: '' }))} />
    <GreenAssistant accountId={account.accountId} contextKey={currentTab} historyKey={`${ASSISTANT_STORAGE_KEY}:${account.workspaceKey}`} requestReply={assistantReply} suggestions={['Xem công việc quá hạn', 'Hướng dẫn xem thông báo']} />
  </>;
}
