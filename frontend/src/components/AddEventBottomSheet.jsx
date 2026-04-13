import { UserCog, GraduationCap, MoreHorizontal, ChevronRight } from 'lucide-react';

/**
 * + 버튼을 누르면 아래에서 올라오는 바텀시트.
 * 3개 카테고리(개인 일정 / 교수님 미팅 / 기타) 중 선택.
 * 현재는 "교수님 미팅"만 활성.
 */
export default function AddEventBottomSheet({ open, onClose, onSelectCategory }) {
  if (!open) return null;

  const items = [
    {
      key: 'personal',
      label: '개인 일정',
      sub: '연차, 반차, 개인 약속',
      icon: UserCog,
      disabled: true,
    },
    {
      key: 'professor',
      label: '교수님 미팅',
      sub: '내 의료진 방문 일정',
      icon: GraduationCap,
      disabled: false,
    },
    {
      key: 'etc',
      label: '기타',
      sub: '보고, 내부 회의, 학회',
      icon: MoreHorizontal,
      disabled: true,
    },
  ];

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)',
        zIndex: 300, display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
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
        {/* 상단 핸들바 */}
        <div style={{
          width: 40, height: 4, borderRadius: 999,
          background: 'var(--bg-h)', margin: '0 auto 14px',
        }} />

        <div style={{
          fontFamily: 'Manrope', fontSize: 19, fontWeight: 800, color: 'var(--t1)',
          letterSpacing: '-.01em',
        }}>
          일정 추가
        </div>
        <div style={{
          fontSize: 12, color: 'var(--t3)', marginTop: 4, marginBottom: 16,
        }}>
          추가할 일정의 유형을 선택하세요
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(it => {
            const Icon = it.icon;
            return (
              <button
                key={it.key}
                disabled={it.disabled}
                onClick={() => !it.disabled && onSelectCategory?.(it.key)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 14,
                  padding: '14px 16px', borderRadius: 14,
                  background: it.disabled ? 'var(--bg-2)' : 'var(--bg-1)',
                  border: `1px solid ${it.disabled ? 'var(--bd-s)' : 'var(--bd)'}`,
                  cursor: it.disabled ? 'not-allowed' : 'pointer',
                  textAlign: 'left', fontFamily: 'inherit',
                  opacity: it.disabled ? .5 : 1,
                  transition: 'background .15s',
                }}
                onMouseEnter={e => {
                  if (!it.disabled) e.currentTarget.style.background = 'var(--ac-d)';
                }}
                onMouseLeave={e => {
                  if (!it.disabled) e.currentTarget.style.background = 'var(--bg-1)';
                }}
              >
                <div style={{
                  width: 42, height: 42, borderRadius: 10,
                  background: it.disabled ? 'var(--bg-h)' : 'var(--ac)',
                  color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <Icon size={20} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)' }}>
                    {it.label}
                    {it.disabled && (
                      <span style={{
                        marginLeft: 6, padding: '1px 6px', borderRadius: 4,
                        fontSize: 9, fontWeight: 700, background: 'var(--bg-h)',
                        color: 'var(--t3)', verticalAlign: 2,
                      }}>준비 중</span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>{it.sub}</div>
                </div>
                {!it.disabled && <ChevronRight size={18} style={{ color: 'var(--t3)' }} />}
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

      <style>{`
        @keyframes slideUpSheet {
          from { transform: translateY(100%); opacity: 0.6; }
          to   { transform: translateY(0);     opacity: 1; }
        }
      `}</style>
    </div>
  );
}
