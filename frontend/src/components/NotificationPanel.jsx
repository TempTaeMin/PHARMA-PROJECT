import { useState } from 'react';
import { X, Bell, RefreshCw, AlertTriangle } from 'lucide-react';
import { notificationApi } from '../api/client';

export default function NotificationPanel({ open, onClose, notifications, onRefresh }) {
  const [tab, setTab] = useState('all');

  const filtered = tab === 'all' ? notifications
    : notifications.filter(n => n.type === tab);

  const unreadAll = notifications.filter(n => !n.read).length;

  const markAllRead = async () => {
    try {
      await notificationApi.markAllRead();
      onRefresh?.();
    } catch (e) { console.error(e); }
  };

  const sendTest = async () => {
    try {
      await notificationApi.test('테스트 알림: 교수 일정 변경됨');
      onRefresh?.();
    } catch (e) { console.error(e); }
  };

  const typeIcon = (type) => {
    if (type === 'schedule_change') return <RefreshCw size={12} style={{ color: 'var(--am)' }} />;
    if (type === 'visit_reminder') return <Bell size={12} style={{ color: 'var(--ac)' }} />;
    if (type === 'overdue_warning') return <AlertTriangle size={12} style={{ color: 'var(--rd)' }} />;
    return <Bell size={12} style={{ color: 'var(--t3)' }} />;
  };

  const typeLabel = (type) => {
    if (type === 'schedule_change') return { text: '스케줄 변경', color: 'var(--am)' };
    if (type === 'visit_reminder') return { text: '리마인더', color: 'var(--ac)' };
    if (type === 'overdue_warning') return { text: '미방문 경고', color: 'var(--rd)' };
    return { text: '알림', color: 'var(--t3)' };
  };

  return (
    <>
      {/* Overlay */}
      {open && <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 49, animation: 'fadeIn .15s' }} />}

      {/* Panel */}
      <div style={{
        position: 'fixed', right: 0, top: 0, bottom: 0, width: 380, maxWidth: '100vw',
        background: 'var(--bg-1)', borderLeft: '1px solid var(--bd-s)', zIndex: 50,
        transform: open ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform .25s cubic-bezier(.4,0,.2,1)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{ padding: '16px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontFamily: 'Outfit', fontSize: 16, fontWeight: 600 }}>
            알림 {unreadAll > 0 && <span style={{ fontSize: 12, color: 'var(--ac)', fontWeight: 400 }}>({unreadAll})</span>}
          </h3>
          <div style={{ display: 'flex', gap: 4 }}>
            {unreadAll > 0 && (
              <button onClick={markAllRead} style={{ padding: '5px 10px', borderRadius: 6, background: 'var(--bg-2)', border: '1px solid var(--bd-s)', color: 'var(--t3)', fontSize: 10, cursor: 'pointer', fontFamily: 'inherit' }}>모두 읽음</button>
            )}
            <button onClick={onClose} style={{ width: 30, height: 30, borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--t3)' }}>
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--bd-s)' }}>
          {[
            { id: 'all', label: '전체' },
            { id: 'schedule_change', label: '스케줄 변경' },
            { id: 'visit_reminder', label: '리마인더' },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              flex: 1, padding: '11px 0', textAlign: 'center', fontSize: 12, fontWeight: 500,
              color: tab === t.id ? 'var(--t1)' : 'var(--t3)',
              cursor: 'pointer', border: 'none', background: 'none', fontFamily: 'inherit',
              borderBottom: tab === t.id ? '2px solid var(--ac)' : '2px solid transparent',
            }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
          {filtered.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Bell size={24} style={{ color: 'var(--t3)', marginBottom: 8, opacity: .3 }} />
              <div style={{ fontSize: 13, color: 'var(--t3)' }}>알림이 없습니다</div>
            </div>
          ) : filtered.map((n, i) => {
            const label = typeLabel(n.type);
            return (
              <div key={n.id || i} style={{
                padding: 14, borderRadius: 9, marginBottom: 6,
                background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
                borderLeft: !n.read ? `3px solid ${label.color}` : '1px solid var(--bd-s)',
                opacity: n.read ? .6 : 1,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  {typeIcon(n.type)}
                  <span style={{ fontSize: 10, fontWeight: 600, color: label.color, textTransform: 'uppercase', letterSpacing: '.04em' }}>{label.text}</span>
                  <span style={{ fontSize: 10, color: 'var(--t3)', marginLeft: 'auto' }}>{n.created_at ? new Date(n.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : ''}</span>
                </div>
                <div style={{ fontSize: 13, color: 'var(--t1)', lineHeight: 1.4 }}>{n.data?.message || JSON.stringify(n.data)}</div>
              </div>
            );
          })}
        </div>

        {/* Test button (dev) */}
        <div style={{ padding: '10px 14px', borderTop: '1px solid var(--bd-s)' }}>
          <button onClick={sendTest} style={{
            width: '100%', padding: '8px', borderRadius: 7, background: 'var(--bg-2)',
            border: '1px solid var(--bd-s)', color: 'var(--t3)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
          }}>
            🧪 테스트 알림 발송 (개발용)
          </button>
        </div>
      </div>
    </>
  );
}
