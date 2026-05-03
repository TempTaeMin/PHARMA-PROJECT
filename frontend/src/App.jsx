import { useState, useEffect, useCallback, useRef } from 'react';
import { LayoutDashboard, Star, Building2, BookOpen, Settings, Bell, Menu, CalendarDays, FileText, LogOut, User as UserIcon, Users } from 'lucide-react';
import { authApi, notificationApi, setUnauthorizedHandler, teamApi } from './api/client';
import Dashboard from './pages/Dashboard';
import MyDoctors from './pages/MyDoctors';
import BrowseDoctors from './pages/BrowseDoctors';
import Conferences from './pages/Conferences';
import Schedule from './pages/Schedule';
import Memos from './pages/Memos';
import Team from './pages/Team';
import SettingsPage from './pages/Settings';
import Login from './pages/Login';
import NotificationPanel from './components/NotificationPanel';

const NAV = [
  { id: 'dashboard', label: '내 일정', icon: LayoutDashboard },
  { id: 'schedule', label: '전체 일정', icon: CalendarDays },
  { id: 'my-doctors', label: '내 의료진', icon: Star },
  { id: 'memos', label: '메모·회의록', icon: FileText },
  { id: 'browse', label: '의료진 검색', icon: Building2 },
  { id: 'conferences', label: '학회 일정', icon: BookOpen },
  { id: 'team', label: '팀 관리', icon: Users },
];

export default function App() {
  const [page, setPage] = useState('dashboard');
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

  const handleLogout = async () => {
    try { await authApi.logout(); } catch { /* ignore */ }
    setCurrentUser(null);
    setProfileOpen(false);
  };

  const unread = notifications.filter(n => !n.read).length;
  const navTo = (p, props = {}) => {
    setPage(p);
    setPageProps(props);
    setSidebarOpen(false);
  };

  const sidebarVisible = !isMobile || sidebarOpen;

  // 인증 상태에 따른 분기
  if (authChecking) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: 'var(--t3)', fontSize: 13, background: 'var(--bg-0)',
      }}>로딩 중…</div>
    );
  }
  if (!currentUser) {
    return <Login />;
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
    </div>
  );
}
