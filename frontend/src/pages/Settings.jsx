import { useState, useEffect } from 'react';
import { User as UserIcon, Save } from 'lucide-react';
import { authApi } from '../api/client';

/**
 * 사용자 설정 — 현재는 프로필(이름) 편집만. 향후 다른 항목도 여기 모음.
 */
export default function Settings({ currentUser, onUpdated }) {
  const [name, setName] = useState(currentUser?.name || '');
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setName(currentUser?.name || '');
  }, [currentUser?.name]);

  const trimmed = name.trim();
  const dirty = trimmed !== (currentUser?.name || '').trim();
  const canSave = dirty && trimmed.length > 0 && !saving;

  const onSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError('');
    try {
      const updated = await authApi.updateMe({ name: trimmed });
      onUpdated?.(updated);
      setSavedAt(new Date());
    } catch (e) {
      setError(e?.message || '저장 실패');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      <div style={{
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 14,
        padding: 20, marginBottom: 16,
      }}>
        <div style={{
          fontSize: 12, fontWeight: 700, color: 'var(--t2)', marginBottom: 14,
          letterSpacing: '.02em',
        }}>
          프로필
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
          {currentUser?.picture ? (
            <img
              src={currentUser.picture}
              alt=""
              referrerPolicy="no-referrer"
              style={{ width: 56, height: 56, borderRadius: '50%', objectFit: 'cover' }}
            />
          ) : (
            <div style={{
              width: 56, height: 56, borderRadius: '50%',
              background: 'var(--ac-d)', color: 'var(--ac)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <UserIcon size={26} />
            </div>
          )}
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12, color: 'var(--t3)', marginBottom: 2 }}>이메일</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)', wordBreak: 'break-all' }}>
              {currentUser?.email || '-'}
            </div>
          </div>
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={{
            display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--t2)',
            marginBottom: 6,
          }}>
            이름
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={50}
            placeholder="팀에 표시될 이름"
            style={{
              width: '100%', padding: '10px 12px', borderRadius: 10,
              border: '1px solid var(--bd-s)', background: 'var(--bg-2)',
              fontSize: 14, fontWeight: 600, color: 'var(--t1)', fontFamily: 'inherit',
              outline: 'none',
            }}
          />
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--t3)' }}>
            기본값은 Google 계정의 이름이지만, 직접 변경할 수 있습니다.
          </div>
        </div>

        {error && (
          <div style={{
            marginBottom: 12, padding: '8px 10px', borderRadius: 8,
            background: '#fee2e2', color: '#b91c1c', fontSize: 12, fontWeight: 600,
          }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={onSave}
            disabled={!canSave}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '9px 16px', border: 'none', borderRadius: 9,
              background: canSave ? 'var(--ac)' : 'var(--bg-2)',
              color: canSave ? '#fff' : 'var(--t3)',
              fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
              cursor: canSave ? 'pointer' : 'not-allowed',
              boxShadow: canSave ? '0 4px 12px rgba(0,64,161,.18)' : 'none',
            }}
          >
            <Save size={14} /> {saving ? '저장 중…' : '저장'}
          </button>
          {savedAt && !dirty && (
            <span style={{ fontSize: 11, color: 'var(--t3)' }}>
              저장됨 ({savedAt.getHours().toString().padStart(2, '0')}:{savedAt.getMinutes().toString().padStart(2, '0')})
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
