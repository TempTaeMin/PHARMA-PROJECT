import { useState, useEffect, useCallback } from 'react';
import { LayoutDashboard, Star, Building2, Activity, Settings, Bell, Menu } from 'lucide-react';
import { notificationApi } from './api/client';
import Dashboard from './pages/Dashboard';
import MyDoctors from './pages/MyDoctors';
import BrowseDoctors from './pages/BrowseDoctors';
import CrawlStatus from './pages/CrawlStatus';
import NotificationPanel from './components/NotificationPanel';

const NAV = [
  { id: 'dashboard', label: '대시보드', icon: LayoutDashboard },
  { id: 'my-doctors', label: '내 교수', icon: Star },
  { id: 'browse', label: '교수 탐색', icon: Building2 },
  { id: 'crawl', label: '크롤링', icon: Activity },
];

export default function App() {
  const [page, setPage] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);

  const loadNotifs = useCallback(async () => {
    try {
      const r = await notificationApi.list(30);
      setNotifications(r.notifications || []);
    } catch (e) { /* offline */ }
  }, []);

  useEffect(() => { loadNotifs(); }, []);

  const unread = notifications.filter(n => !n.read).length;
  const navTo = (p) => { setPage(p); setSidebarOpen(false); };

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg-0)' }}>
      {sidebarOpen && <div onClick={() => setSidebarOpen(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 39 }} />}

      <aside style={{ width: 220, minWidth: 220, background: 'var(--bg-1)', borderRight: '1px solid var(--bd-s)', display: 'flex', flexDirection: 'column', padding: '16px 10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', marginBottom: 24 }}>
          <div style={{ width: 28, height: 28, borderRadius: 7, background: 'linear-gradient(135deg,#7C6AF0,#5B8DEF)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 }}>💊</div>
          <h1 style={{ fontFamily: 'Outfit', fontSize: 15, fontWeight: 700, letterSpacing: '-.03em', background: 'linear-gradient(135deg,#F0F0F2,#9898A0)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>PharmScheduler</h1>
        </div>
        <nav style={{ display: 'flex', flexDirection: 'column', gap: 1, flex: 1 }}>
          {NAV.map(n => {
            const Icon = n.icon;
            const on = page === n.id;
            return (
              <button key={n.id} onClick={() => navTo(n.id)} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 10px', borderRadius: 7, fontSize: 13, fontWeight: on ? 500 : 450, color: on ? 'var(--t1)' : 'var(--t3)', background: on ? 'var(--bg-3)' : 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', width: '100%', textAlign: 'left' }}>
                <Icon size={17} style={{ opacity: on ? 1 : .6 }} /> {n.label}
              </button>
            );
          })}
        </nav>
        <div style={{ borderTop: '1px solid var(--bd-s)', paddingTop: 8 }}>
          <button style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 10px', borderRadius: 7, fontSize: 13, color: 'var(--t3)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', width: '100%' }}>
            <Settings size={17} style={{ opacity: .6 }} /> 설정
          </button>
        </div>
      </aside>

      <main style={{ flex: 1, overflow: 'auto' }}>
        <header style={{ position: 'sticky', top: 0, zIndex: 10, background: 'rgba(8,8,10,.88)', backdropFilter: 'blur(16px)', borderBottom: '1px solid var(--bd-s)', padding: '14px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 style={{ fontFamily: 'Outfit', fontSize: 17, fontWeight: 600, letterSpacing: '-.02em' }}>
            {NAV.find(n => n.id === page)?.label || '대시보드'}
          </h2>
          <button onClick={() => { setNotifOpen(true); loadNotifs(); }} style={{ width: 32, height: 32, borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--t3)', position: 'relative' }}>
            <Bell size={15} />
            {unread > 0 && <span style={{ position: 'absolute', top: 5, right: 5, width: 6, height: 6, borderRadius: '50%', background: 'var(--rd)', border: '2px solid var(--bg-2)' }} />}
          </button>
        </header>
        <div style={{ padding: '20px 24px' }}>
          {page === 'dashboard' && <Dashboard onNavigate={navTo} />}
          {page === 'my-doctors' && <MyDoctors />}
          {page === 'browse' && <BrowseDoctors onNavigate={navTo} />}
          {page === 'crawl' && <CrawlStatus />}
        </div>
      </main>

      <NotificationPanel open={notifOpen} onClose={() => setNotifOpen(false)} notifications={notifications} onRefresh={loadNotifs} />
    </div>
  );
}
