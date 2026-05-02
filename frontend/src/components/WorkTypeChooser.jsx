import { Calendar, Megaphone, ChevronRight } from 'lucide-react';

/**
 * 업무 일정 서브 선택 바텀시트:
 *  - event         : 기존 개인 일정 (시간 포함)
 *  - announcement  : 업무공지 (제목 + 내용, 팀 공유 예정)
 */
export default function WorkTypeChooser({ open, onClose, onSelect }) {
  if (!open) return null;

  const items = [
    {
      key: 'event',
      label: '일정 등록',
      sub: '연차, 반차, 내부 회의, 보고',
      icon: Calendar,
    },
    {
      key: 'announcement',
      label: '공지 등록',
      sub: '업무 공지사항 기록 (팀 공유 예정)',
      icon: Megaphone,
    },
  ];

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)',
        zIndex: 305, display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
        animation: 'fadeIn .18s ease',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-1)',
          borderTopLeftRadius: 22, borderTopRightRadius: 22,
          padding: '14px 18px 26px',
          width: '100%', maxWidth: 520,
          boxShadow: '0 -8px 30px rgba(0,0,0,.18)',
          animation: 'slideUpSheet .25s cubic-bezier(.2,.9,.2,1.04)',
        }}
      >
        <div style={{
          width: 40, height: 4, borderRadius: 999,
          background: 'var(--bg-h)', margin: '0 auto 14px',
        }} />

        <div style={{
          fontFamily: 'Manrope', fontSize: 19, fontWeight: 800, color: 'var(--t1)',
          letterSpacing: '-.01em',
        }}>
          업무 일정
        </div>
        <div style={{
          fontSize: 12, color: 'var(--t3)', marginTop: 4, marginBottom: 16,
        }}>
          등록할 업무 유형을 선택하세요
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(it => {
            const Icon = it.icon;
            return (
              <button
                key={it.key}
                onClick={() => onSelect?.(it.key)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 14,
                  padding: '14px 16px', borderRadius: 14,
                  background: 'var(--bg-1)',
                  border: '1px solid var(--bd)',
                  cursor: 'pointer',
                  textAlign: 'left', fontFamily: 'inherit',
                  transition: 'background .15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--ac-d)'; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-1)'; }}
              >
                <div style={{
                  width: 42, height: 42, borderRadius: 10,
                  background: 'var(--ac)', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <Icon size={20} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)' }}>
                    {it.label}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>{it.sub}</div>
                </div>
                <ChevronRight size={18} style={{ color: 'var(--t3)' }} />
              </button>
            );
          })}
        </div>

        <button
          onClick={onClose}
          style={{
            marginTop: 14, width: '100%', padding: '13px 14px', borderRadius: 12,
            background: 'var(--bg-2)', color: 'var(--t2)',
            border: '1px solid var(--bd-s)',
            fontSize: 13, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
          }}
        >
          취소
        </button>
      </div>
    </div>
  );
}
