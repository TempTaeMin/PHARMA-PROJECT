import { useState, useRef, useEffect } from 'react';
import { Users, Crown, Check, ChevronDown } from 'lucide-react';
import { teamApi } from '../api/client';
import { showError } from '../utils/dialog';

/**
 * 사이드바 팀 전환 dropdown.
 * currentUser.teams = [{id, name, role, is_active}]
 *  - 0개: 렌더 안 함
 *  - 1개: 클릭 비활성, 정보만 표시
 *  - 2개 이상: dropdown 열림, 다른 팀 선택 → 활성 팀 전환
 */
export default function TeamSwitcher({ currentUser, onSwitched }) {
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const ref = useRef(null);

  const teams = Array.isArray(currentUser?.teams) ? currentUser.teams : [];
  const activeId = currentUser?.active_team_id || currentUser?.team_id || null;
  const active = teams.find(t => t.id === activeId) || teams[0] || null;
  const multi = teams.length > 1;

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    window.addEventListener('mousedown', handler);
    return () => window.removeEventListener('mousedown', handler);
  }, [open]);

  if (teams.length === 0) return null;

  const handleSwitch = async (teamId) => {
    if (teamId === activeId) { setOpen(false); return; }
    setSwitching(true);
    try {
      await teamApi.switchActive(teamId);
      setOpen(false);
      onSwitched?.();
    } catch (e) {
      showError(e, { title: '팀 전환 실패' });
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div ref={ref} style={{ position: 'relative', margin: '4px 0 12px' }}>
      <button
        onClick={() => multi && setOpen(o => !o)}
        disabled={!multi || switching}
        style={{
          width: '100%',
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 10px', borderRadius: 9,
          background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
          fontFamily: 'inherit', cursor: multi ? 'pointer' : 'default',
          textAlign: 'left',
        }}
      >
        <Users size={14} style={{ color: 'var(--ac)', flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 9, fontWeight: 700, color: 'var(--t3)',
            letterSpacing: '.06em', textTransform: 'uppercase',
          }}>
            현재 팀
          </div>
          <div style={{
            fontSize: 12, fontWeight: 700, color: 'var(--t1)',
            display: 'flex', alignItems: 'center', gap: 4,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {active?.name || '미소속'}
            {active?.role === 'owner' && (
              <Crown size={10} style={{ color: 'var(--am)', flexShrink: 0 }} />
            )}
          </div>
        </div>
        {multi && (
          <ChevronDown
            size={12}
            style={{
              color: 'var(--t3)', flexShrink: 0,
              transform: open ? 'rotate(180deg)' : 'none',
              transition: 'transform .15s',
            }}
          />
        )}
      </button>

      {open && multi && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0,
          background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
          borderRadius: 9, boxShadow: '0 8px 24px rgba(0,0,0,.12)',
          overflow: 'hidden', zIndex: 60,
          maxHeight: 240, overflowY: 'auto',
        }}>
          {teams.map(t => {
            const isActive = t.id === activeId;
            return (
              <button
                key={t.id}
                onClick={() => handleSwitch(t.id)}
                disabled={switching}
                style={{
                  width: '100%', padding: '9px 11px',
                  display: 'flex', alignItems: 'center', gap: 6,
                  border: 'none',
                  background: isActive ? 'var(--ac-d)' : 'none',
                  color: isActive ? 'var(--ac)' : 'var(--t1)',
                  cursor: 'pointer', fontFamily: 'inherit',
                  fontSize: 12, textAlign: 'left',
                  borderBottom: '1px solid var(--bd-s)',
                }}
              >
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {t.name}
                </span>
                {t.role === 'owner' && (
                  <Crown size={10} style={{ color: 'var(--am)', flexShrink: 0 }} />
                )}
                {isActive && <Check size={11} style={{ flexShrink: 0 }} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
