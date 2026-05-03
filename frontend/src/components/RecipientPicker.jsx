import { useMemo } from 'react';
import { Check } from 'lucide-react';

/**
 * 팀원 멀티셀렉트. visibility='team' 일정의 수신자를 고른다.
 *
 * props:
 *   members: [{ user_id, name, email, picture, role }]
 *   value: number[]  // 선택된 user_id 목록
 *   onChange: (ids: number[]) => void
 *   currentUserId: number  // 본인은 옵션에서 제외
 *   disabled?: boolean
 */
export default function RecipientPicker({
  members = [],
  value = [],
  onChange,
  currentUserId,
  disabled = false,
}) {
  const candidates = useMemo(
    () => members.filter((m) => m.user_id !== currentUserId),
    [members, currentUserId]
  );
  const selected = useMemo(() => new Set(value), [value]);
  const allSelected = candidates.length > 0 && candidates.every((m) => selected.has(m.user_id));
  const someSelected = candidates.some((m) => selected.has(m.user_id));

  if (candidates.length === 0) {
    return (
      <div style={{
        padding: '12px 14px', borderRadius: 12,
        background: 'var(--bg-2)', border: '1px dashed var(--bd-s)',
        fontSize: 12, color: 'var(--t3)',
      }}>
        같은 팀에 다른 멤버가 없어 공유할 동료가 없습니다. 팀원을 초대한 뒤 선택할 수 있어요.
      </div>
    );
  }

  const toggle = (id) => {
    if (disabled) return;
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange?.(Array.from(next));
  };

  const toggleAll = () => {
    if (disabled) return;
    if (allSelected) onChange?.([]);
    else onChange?.(candidates.map((m) => m.user_id));
  };

  return (
    <div style={{
      borderRadius: 12, background: 'var(--bg-2)',
      border: '1px solid var(--bd-s)', overflow: 'hidden',
      opacity: disabled ? 0.55 : 1,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 12px', borderBottom: '1px solid var(--bd-s)',
        fontSize: 12, color: 'var(--t2)',
      }}>
        <span>
          공유 받는 팀원
          {someSelected && (
            <span style={{ marginLeft: 8, color: 'var(--ac)', fontWeight: 700 }}>
              {selected.size}명
            </span>
          )}
        </span>
        <button
          type="button"
          onClick={toggleAll}
          disabled={disabled}
          style={{
            border: '1px solid var(--bd-s)', borderRadius: 6,
            background: 'var(--bg-1)', color: 'var(--t2)',
            padding: '4px 8px', fontSize: 11, fontWeight: 700,
            cursor: disabled ? 'default' : 'pointer', fontFamily: 'inherit',
          }}
        >
          {allSelected ? '모두 해제' : '모두 선택'}
        </button>
      </div>
      <div style={{ maxHeight: 200, overflowY: 'auto' }}>
        {candidates.map((m) => {
          const checked = selected.has(m.user_id);
          return (
            <button
              key={m.user_id}
              type="button"
              onClick={() => toggle(m.user_id)}
              disabled={disabled}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px', border: 'none', background: 'transparent',
                cursor: disabled ? 'default' : 'pointer',
                borderBottom: '1px solid var(--bd-s)',
                fontFamily: 'inherit', textAlign: 'left',
              }}
            >
              <span style={{
                width: 18, height: 18, borderRadius: 5,
                border: `1px solid ${checked ? 'var(--ac)' : 'var(--bd-s)'}`,
                background: checked ? 'var(--ac)' : 'transparent',
                color: '#fff', display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                {checked && <Check size={12} strokeWidth={3} />}
              </span>
              {m.picture ? (
                <img
                  src={m.picture}
                  alt=""
                  style={{ width: 24, height: 24, borderRadius: '50%', objectFit: 'cover', flexShrink: 0 }}
                />
              ) : (
                <span style={{
                  width: 24, height: 24, borderRadius: '50%',
                  background: 'var(--bg-3, var(--bg-1))',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 11, fontWeight: 700, color: 'var(--t2)', flexShrink: 0,
                }}>
                  {(m.name || m.email || '?').slice(0, 1)}
                </span>
              )}
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>
                  {m.name || m.email}
                </span>
                {m.role === 'owner' && (
                  <span style={{
                    marginLeft: 6, fontSize: 10, color: 'var(--ac)', fontWeight: 700,
                  }}>
                    팀장
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
