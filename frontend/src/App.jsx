import { useState, useEffect, useCallback, useRef } from 'react';
import { LayoutDashboard, Star, Building2, BookOpen, Settings, Bell, Menu, CalendarDays, FileText, LogOut, User as UserIcon, Users, MessageSquarePlus, Inbox } from 'lucide-react';
import { authApi, notificationApi, setUnauthorizedHandler, teamApi, feedbackApi } from './api/client';
import Dashboard from './pages/Dashboard';
import MyDoctors from './pages/MyDoctors';
import BrowseDoctors from './pages/BrowseDoctors';
import Conferences from './pages/Conferences';
import Schedule from './pages/Schedule';
import Memos from './pages/Memos';
import Team from './pages/Team';
import SettingsPage from './pages/Settings';
import AdminFeedback from './pages/AdminFeedback';
import Login from './pages/Login';
import NotificationPanel from './components/NotificationPanel';
import DialogHost from './components/Dialog';
import FeedbackModal from './components/FeedbackModal';
import PwaInstallHint from './components/PwaInstallHint';
import ChangelogModal from './components/ChangelogModal';

const NAV = [
  { id: 'dashboard', label: '내 일정', icon: LayoutDashboard },
  { id: 'schedule', label: '전체 일정', icon: CalendarDays },
  { id: 'my-doctors', label: '내 의료진', icon: Star },
  { id: 'memos', label: '메모·회의록', icon: FileText },
  { id: 'browse', label: '의료진 검색', icon: Building2 },
  { id: 'conferences', label: '학회 일정', icon: BookOpen },
  { id: 'team', label: '팀 관리', icon: Users },
];

const PAGE_IDS = [...NAV.map(n => n.id), 'settings', 'admin-feedback'];

// admin 가드 — 백엔드 ADMIN_EMAILS env 와 동기화 필요. 프론트는 UI 분기만, 보안은 백엔드 의존.
const ADMIN_EMAILS = ['namgiggo1@gmail.com'];
const isAdminEmail = (email) => !!email && ADMIN_EMAILS.includes(email.toLowerCase());

// URL 의 첫 path segment 로 초기 페이지 결정 — 직접 URL 입력 / 새로고침 / 뒤로가기 대응.
function pageFromPath() {
  if (typeof window === 'undefined') return 'dashboard';
  const seg = window.location.pathname.replace(/^\/+/, '').split('/')[0];
  return PAGE_IDS.includes(seg) ? seg : 'dashboard';
}

function pathForPage(p) {
  return p === 'dashboard' ? '/' : `/${p}`;
}

export default function App() {
  const [page, setPage] = useState(pageFromPath);
  const [pageProps, setPageProps] = useState({});
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [invitations, setInvitations] = useState([]);  // 받은 팀 초대 (pending)
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' && window.innerWidth <= 768
  );
  // ─── 인증 상태 ───
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef(null);
  const [showFeedback, setShowFeedback] = useState(false);
  const [adminFeedbackUnread, setAdminFeedbackUnread] = useState(0);
  const [teamMembers, setTeamMembers] = useState([]);

  const reloadTeam = useCallback(async () => {
    try {
      const t = await teamApi.me();
      setTeamMembers(Array.isArray(t?.members) ? t.members : []);
    } catch {
      setTeamMembers([]);
    }
  }, []);

  useEffect(() => {
    if (currentUser) reloadTeam();
    else setTeamMembers([]);
  }, [currentUser, reloadTeam]);

  // 401 응답 시 자동 로그아웃
  useEffect(() => {
    setUnauthorizedHandler(() => setCurrentUser(null));
  }, []);

  // 첫 마운트 + 페이지 복귀 시 /auth/me 확인
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await authApi.me();
        if (!cancelled) setCurrentUser(me);
      } catch {
        if (!cancelled) setCurrentUser(null);
      } finally {
        if (!cancelled) setAuthChecking(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // 프로필 드롭다운 외부 클릭 닫기
  useEffect(() => {
    if (!profileOpen) return;
    const handler = (e) => {
      if (profileRef.current && !profileRef.current.contains(e.target)) {
        setProfileOpen(false);
      }
    };
    window.addEventListener('mousedown', handler);
    return () => window.removeEventListener('mousedown', handler);
  }, [profileOpen]);

  const loadNotifs = useCallback(async () => {
    if (!currentUser) return;
    try {
      const r = await notificationApi.list(30);
      setNotifications(r.notifications || []);
    } catch (e) { /* offline */ }
    try {
      const inv = await teamApi.myInvitations();
      setInvitations(Array.isArray(inv) ? inv : []);
    } catch (e) { setInvitations([]); }
  }, [currentUser]);

  useEffect(() => { loadNotifs(); }, [loadNotifs]);

  // 30초마다 받은 초대 폴링 (실시간 WebSocket 보강)
  useEffect(() => {
    if (!currentUser) return;
    const t = setInterval(() => { loadNotifs(); }, 30000);
    return () => clearInterval(t);
  }, [currentUser, loadNotifs]);

  // admin: 사이드바 뱃지용 미처리 피드백 카운트 (60초 폴링)
  useEffect(() => {
    if (!isAdminEmail(currentUser?.email)) {
      setAdminFeedbackUnread(0);
      return;
    }
    let cancelled = false;
    const fetchSummary = async () => {
      try {
        const s = await feedbackApi.summary();
        if (!cancelled) setAdminFeedbackUnread(s.unread_count || 0);
      } catch { /* ignore */ }
    };
    fetchSummary();
    const t = setInterval(fetchSummary, 60000);
    return () => { cancelled = true; clearInterval(t); };
  }, [currentUser]);

  const handleLogout = async () => {
    try { await authApi.logout(); } catch { /* ignore */ }
    setCurrentUser(null);
    setProfileOpen(false);
  };

  const unread = notifications.filter(n => !n.read).length;

  // 페이지 이동 — history.pushState 동기화로 모바일 뒤로가기 정상 동작.
  const navTo = useCallback((p, props = {}) => {
    if (typeof window !== 'undefined') {
      window.history.pushState({ page: p, props }, '', pathForPage(p));
    }
    setPage(p);
    setPageProps(props);
    setSidebarOpen(false);
    setNotifOpen(false);
  }, []);

  // 첫 마운트 시 현재 page 를 history.state 에 박아둠 (popstate 시 fallback 용).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const st = window.history.state;
    if (!st || st.page === undefined) {
      window.history.replaceState({ page, props: pageProps }, '', pathForPage(page));
    }
    // 첫 마운트만
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 시스템 뒤로가기/앞으로가기 — state 에서 page 복원, 없으면 URL 에서 다시 읽음.
  useEffect(() => {
    const onPopState = (e) => {
      const st = e.state;
      if (st && PAGE_IDS.includes(st.page)) {
        setPage(st.page);
        setPageProps(st.props || {});
      } else {
        setPage(pageFromPath());
        setPageProps({});
      }
      setSidebarOpen(false);
      setNotifOpen(false);
      setProfileOpen(false);
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const sidebarVisible = !isMobile || sidebarOpen;

  // 인증 상태에 따른 분기
  if (authChecking) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: 'var(--t3)', fontSize: 13, background: 'var(--bg-0)',
      }}>
        로딩 중…
        <DialogHost />
      </div>
    );
  }
  if (!currentUser) {
    return (
      <>
        <Login />
        <DialogHost />
      </>
    );
  }

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg-0)' }}>
      {isMobile && sidebarOpen && <div onClick={() => setSidebarOpen(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 39 }} />}

      <aside style={{
        width: 220, minWidth: 220,
        background: 'var(--bg-1)',
        borderRight: '1px solid var(--bd-s)',
        display: 'flex', flexDirection: 'column', padding: '16px 10px',
        ...(isMobile ? {
          position: 'fixed', top: 0, bottom: 0, left: 0, zIndex: 40,
          transform: sidebarOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform .22s ease',
          boxShadow: sidebarOpen ? '0 10px 36px rgba(0,0,0,.22)' : 'none',
        } : {}),
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', marginBottom: 24 }}>
          <div style={{ width: 28, height: 28, borderRadius: 7, background: 'linear-gradient(135deg,#0040a1,#0056d2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#fff' }}>💊</div>
          <h1 style={{ fontFamily: 'Manrope', fontSize: 15, fontWeight: 800, letterSpacing: '-.03em', color: 'var(--ac)' }}>MediSync</h1>
        </div>
        <nav style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
          {NAV.map(n => {
            const Icon = n.icon;
            const on = page === n.id;
            return (
              <button key={n.id} onClick={() => navTo(n.id)} style={{
                display: 'flex', alignItems: 'center', gap: 9, padding: '9px 12px', borderRadius: 10,
                fontSize: 13, fontWeight: on ? 600 : 450,
                color: on ? 'var(--ac)' : 'var(--t3)',
                background: on ? 'var(--ac-d)' : 'none',
                border: 'none', cursor: 'pointer', fontFamily: 'inherit', width: '100%', textAlign: 'left',
                transition: 'all .15s',
              }}>
                <Icon size={17} style={{ opacity: on ? 1 : .5 }} /> {n.label}
              </button>
            );
          })}
        </nav>
        <div style={{ borderTop: '1px solid var(--bd-s)', paddingTop: 8 }}>
          {isAdminEmail(currentUser?.email) && (
            <button onClick={() => navTo('admin-feedback')} style={{
              display: 'flex', alignItems: 'center', gap: 9, padding: '9px 12px', borderRadius: 10,
              fontSize: 13, fontWeight: page === 'admin-feedback' ? 600 : 450,
              color: page === 'admin-feedback' ? 'var(--ac)' : 'var(--t3)',
              background: page === 'admin-feedback' ? 'var(--ac-d)' : 'none',
              border: 'none', cursor: 'pointer', fontFamily: 'inherit', width: '100%', textAlign: 'left',
              marginBottom: 4,
            }}>
              <Inbox size={17} style={{ opacity: page === 'admin-feedback' ? 1 : .5 }} />
              <span style={{ flex: 1 }}>피드백 관리</span>
              {adminFeedbackUnread > 0 && (
                <span style={{
                  minWidth: 18, height: 18, padding: '0 5px', borderRadius: 9,
                  background: 'var(--rd)', color: '#fff',
                  fontSize: 10, fontWeight: 700, fontFamily: "'JetBrains Mono'",
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {adminFeedbackUnread > 99 ? '99+' : adminFeedbackUnread}
                </span>
              )}
            </button>
          )}
          <button onClick={() => navTo('settings')} style={{
            display: 'flex', alignItems: 'center', gap: 9, padding: '9px 12px', borderRadius: 10,
            fontSize: 13, fontWeight: page === 'settings' ? 600 : 450,
            color: page === 'settings' ? 'var(--ac)' : 'var(--t3)',
            background: page === 'settings' ? 'var(--ac-d)' : 'none',
            border: 'none', cursor: 'pointer', fontFamily: 'inherit', width: '100%', textAlign: 'left',
          }}>
            <Settings size={17} style={{ opacity: page === 'settings' ? 1 : .5 }} /> 설정
          </button>
        </div>
      </aside>

      <main style={{
        flex: 1, overflow: 'auto', minWidth: 0,
        // scroll-snap-type 제거: 카드들에 scrollSnapAlign:start 가 박혀있어
        // 페이지 첫 진입 시 첫 카드로 스냅 정렬되며 살짝 아래로 내려가는 현상이 있었음.
        // scrollPaddingTop 은 Schedule 의 scrollIntoView 가 sticky 헤더에 가리지 않도록 유지.
        scrollPaddingTop: 56,
      }}>
        <header style={{
          position: 'sticky', top: 0, zIndex: 10,
          background: 'rgba(248,249,250,.85)', backdropFilter: 'blur(16px)',
          borderBottom: '1px solid var(--bd-s)',
          padding: isMobile ? '12px 14px' : '14px 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            {isMobile && (
              <button onClick={() => setSidebarOpen(true)} style={{
                width: 34, height: 34, borderRadius: 10, background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--t2)',
                flexShrink: 0,
              }}>
                <Menu size={16} />
              </button>
            )}
            <h2 style={{ fontFamily: 'Manrope', fontSize: 17, fontWeight: 700, letterSpacing: '-.02em', color: 'var(--t1)' }}>
              {NAV.find(n => n.id === page)?.label || '내 일정'}
            </h2>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <button onClick={() => { setNotifOpen(true); loadNotifs(); }} style={{
              width: 34, height: 34, borderRadius: 10, background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--t3)', position: 'relative',
              flexShrink: 0,
            }}>
              <Bell size={15} />
              {(unread > 0 || invitations.length > 0) && <span style={{ position: 'absolute', top: 6, right: 6, width: 6, height: 6, borderRadius: '50%', background: 'var(--rd)', border: '2px solid var(--bg-1)' }} />}
            </button>

            {/* 프로필 드롭다운 */}
            <div ref={profileRef} style={{ position: 'relative' }}>
              <button onClick={() => setProfileOpen(o => !o)} style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px 4px 4px', borderRadius: 18,
                background: 'var(--bg-2)', border: '1px solid var(--bd-s)', cursor: 'pointer',
                fontFamily: 'inherit',
              }}>
                {currentUser.picture ? (
                  <img src={currentUser.picture} alt="" referrerPolicy="no-referrer" style={{
                    width: 26, height: 26, borderRadius: '50%', objectFit: 'cover', flexShrink: 0,
                  }} />
                ) : (
                  <div style={{
                    width: 26, height: 26, borderRadius: '50%', background: 'var(--ac-d)', color: 'var(--ac)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>
                    <UserIcon size={14} />
                  </div>
                )}
                {!isMobile && (
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--t2)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {currentUser.name || currentUser.email}
                  </span>
                )}
              </button>
              {profileOpen && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 6px)', right: 0, minWidth: 200,
                  background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 10,
                  boxShadow: '0 6px 24px rgba(0,0,0,.12)', overflow: 'hidden', zIndex: 50,
                }}>
                  <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--bd-s)' }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--t1)' }}>
                      {currentUser.name || '이름 없음'}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>
                      {currentUser.email}
                    </div>
                  </div>
                  <button
                    onClick={() => { setProfileOpen(false); setShowFeedback(true); }}
                    style={{
                      width: '100%', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 8,
                      border: 'none', borderBottom: '1px solid var(--bd-s)',
                      background: 'none', cursor: 'pointer', fontFamily: 'inherit',
                      fontSize: 12, color: 'var(--t2)', textAlign: 'left',
                    }}
                  >
                    <MessageSquarePlus size={13} /> 피드백 보내기
                  </button>
                  <button onClick={handleLogout} style={{
                    width: '100%', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 8,
                    border: 'none', background: 'none', cursor: 'pointer', fontFamily: 'inherit',
                    fontSize: 12, color: 'var(--t2)', textAlign: 'left',
                  }}>
                    <LogOut size={13} /> 로그아웃
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <div style={{ padding: isMobile ? '12px 10px' : '20px 24px' }}>
          {page === 'dashboard' && <Dashboard onNavigate={navTo} currentUser={currentUser} teamMembers={teamMembers} />}
          {page === 'schedule' && <Schedule onNavigate={navTo} currentUser={currentUser} />}
          {page === 'my-doctors' && <MyDoctors onNavigate={navTo} initialDoctorId={pageProps.doctorId} currentUser={currentUser} teamMembers={teamMembers} />}
          {page === 'memos' && <Memos initialFilters={pageProps.filters || {}} onNavigate={navTo} />}
          {page === 'browse' && <BrowseDoctors onNavigate={navTo} />}
          {page === 'conferences' && <Conferences onNavigate={navTo} mode={pageProps.mode} currentUser={currentUser} />}
          {page === 'team' && <Team currentUser={currentUser} onTeamChanged={async () => {
            try { const me = await authApi.me(); setCurrentUser(me); } catch { /* ignore */ }
            reloadTeam();
          }} />}
          {page === 'settings' && <SettingsPage currentUser={currentUser} onUpdated={setCurrentUser} />}
          {page === 'admin-feedback' && isAdminEmail(currentUser?.email) && (
            <AdminFeedback onSummaryChange={setAdminFeedbackUnread} />
          )}
        </div>
      </main>

      <NotificationPanel
        open={notifOpen}
        onClose={() => setNotifOpen(false)}
        notifications={notifications}
        invitations={invitations}
        onRefresh={loadNotifs}
        onNavigate={navTo}
        onTeamChanged={async () => {
          try { const me = await authApi.me(); setCurrentUser(me); } catch { /* ignore */ }
        }}
      />
      <FeedbackModal open={showFeedback} onClose={() => setShowFeedback(false)} />
      <PwaInstallHint />
      <ChangelogModal />
      <DialogHost />
    </div>
  );
}
