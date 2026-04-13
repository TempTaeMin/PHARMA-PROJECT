import { useState, useEffect, useCallback } from 'react';
import { LayoutDashboard, Star, Building2, BookOpen, Settings, Bell, Menu, CalendarDays } from 'lucide-react';
import { notificationApi } from './api/client';
import Dashboard from './pages/Dashboard';
import MyDoctors from './pages/MyDoctors';
import BrowseDoctors from './pages/BrowseDoctors';
import Conferences from './pages/Conferences';
import Schedule from './pages/Schedule';
import NotificationPanel from './components/NotificationPanel';

const NAV = [
  { id: 'dashboard', label: '대시보드', icon: LayoutDashboard },
  { id: 'schedule', label: '월간 일정', icon: CalendarDays },
  { id: 'my-doctors', label: '내 교수', icon: Star },
  { id: 'browse', label: '교수 탐색', icon: Building2 },
  { id: 'conferences', label: '학회 일정', icon: BookOpen },
];

export default function App() {
  const [page, setPage] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' && window.innerWidth <= 768
  );

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const loadNotifs = useCallback(async () => {
    try {
      const r = await notificationApi.list(30);
      setNotifications(r.notifications || []);
    } catch (e) { /* offline */ }
  }, []);

  useEffect(() => { loadNotifs(); }, []);

  const unread = notifications.filter(n => !n.read).length;
  const navTo = (p) => { setPage(p); setSidebarOpen(false); };

  const sidebarVisible = !isMobile || sidebarOpen;

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
          <h1 style={{ fontFamily: 'Manrope', fontSize: 15, fontWeight: 800, letterSpacing: '-.03em', color: 'var(--ac)' }}>PharmScheduler</h1>
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
          <button style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 12px', borderRadius: 10, fontSize: 13, color: 'var(--t3)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', width: '100%' }}>
            <Settings size={17} style={{ opacity: .5 }} /> 설정
          </button>
        </div>
      </aside>

      <main style={{ flex: 1, overflow: 'auto', minWidth: 0 }}>
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
              {NAV.find(n => n.id === page)?.label || '대시보드'}
            </h2>
          </div>
          <button onClick={() => { setNotifOpen(true); loadNotifs(); }} style={{
            width: 34, height: 34, borderRadius: 10, background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--t3)', position: 'relative',
            flexShrink: 0,
          }}>
            <Bell size={15} />
            {unread > 0 && <span style={{ position: 'absolute', top: 6, right: 6, width: 6, height: 6, borderRadius: '50%', background: 'var(--rd)', border: '2px solid var(--bg-1)' }} />}
          </button>
        </header>
        <div style={{ padding: isMobile ? '12px 10px' : '20px 24px' }}>
          {page === 'dashboard' && <Dashboard onNavigate={navTo} />}
          {page === 'schedule' && <Schedule />}
          {page === 'my-doctors' && <MyDoctors />}
          {page === 'browse' && <BrowseDoctors onNavigate={navTo} />}
          {page === 'conferences' && <Conferences />}
        </div>
      </main>

      <NotificationPanel open={notifOpen} onClose={() => setNotifOpen(false)} notifications={notifications} onRefresh={loadNotifs} />
    </div>
  );
}
