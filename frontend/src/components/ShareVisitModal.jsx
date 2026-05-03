import { useState, useEffect } from 'react';
import { Users, X } from 'lucide-react';
import RecipientPicker from './RecipientPicker.jsx';
import { visitApi } from '../api/client';

/**
 * 이미 등록된 일정의 공유 상태를 변경하는 모달.
 *
 * 모달 열리자마자 RecipientPicker 노출. 1명 이상 선택 → 'team', 0명 선택 → 'private'.
 *
 * props:
 *   open: bool
 *   visit: 현재 카드의 visit 객체 (visibility, recipient_user_ids, doctor_id, id)
 *   teamMembers: 팀원 목록
 *   currentUserId: 본인 user.id
 *   onClose: () => void
 *   onSaved: (updated) => void  — PATCH 성공 시 새 visit dict
 */
export default function ShareVisitModal({
  open, visit, teamMembers = [], currentUserId, onClose, onSaved,
}) {
  const [recipientIds, setRecipientIds] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open || !visit) return;
    setRecipientIds(Array.isArray(visit.recipient_user_ids) ? [...visit.recipient_user_ids] : []);
    setError('');
  }, [open, visit]);

  if (!open || !visit) return null;

  const willShare = recipientIds.length > 0;
  const canSave = !saving;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError('');
    try {
      const patch = {
        visibility: willShare ? 'team' : 'private',
        recipient_user_ids: willShare ? recipientIds : [],
      };
      const updated = visit.doctor_id
        ? await visitApi.update(visit.doctor_id, visit.id, patch)
        : await visitApi.updateFlat(visit.id, patch);
      onSaved?.(updated);
      onClose?.();
    } catch (e) {
      setError(e?.message || '저장 실패');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
        zIndex: 400, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16, animation: 'fadeIn .18s ease', fontFamily: 'inherit',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
    >
      <div style={{
        background: 'var(--bg-1)', borderRadius: 14,
        width: 480, maxWidth: '100%', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
        animation: 'fadeUp .2s ease',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '14px 16px', borderBottom: '1px solid var(--bd-s)',
        }}>
          <Users size={16} style={{ color: 'var(--ac)' }} />
          <div style={{ flex: 1, fontSize: 15, fontWeight: 800, color: 'var(--t1)' }}>
            공유 받을 팀원 선택
          </div>
          <button onClick={onClose} aria-label="닫기" style={{
            width: 30, height: 30, border: '1px solid var(--bd-s)', borderRadius: 7,
            background: 'var(--bg-2)', color: 'var(--t3)', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
          }}>
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: '16px', overflowY: 'auto' }}>
          <div style={{
            fontSize: 11, color: 'var(--t3)', marginBottom: 10, lineHeight: 1.5,
          }}>
            선택한 팀원만 이 일정을 봅니다. 모두 해제하면 비공개로 전환됩니다.
          </div>
          <RecipientPicker
            members={teamMembers}
            value={recipientIds}
            onChange={setRecipientIds}
            currentUserId={currentUserId}
          />

          {error && (
            <div style={{
              marginTop: 12, padding: '8px 10px', borderRadius: 8,
              background: '#fee2e2', color: '#b91c1c', fontSize: 12, fontWeight: 600,
            }}>
              {error}
            </div>
          )}
        </div>

        <div style={{
          padding: '12px 16px 16px', borderTop: '1px solid var(--bd-s)',
          display: 'flex', gap: 8,
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 16px', borderRadius: 9,
              background: 'var(--bg-2)', color: 'var(--t2)',
              border: '1px solid var(--bd-s)', cursor: 'pointer',
              fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
            }}
          >
            취소
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave}
            style={{
              flex: 1, padding: '10px 16px', borderRadius: 9,
              background: canSave ? 'var(--ac)' : 'var(--bg-2)',
              color: canSave ? '#fff' : 'var(--t3)',
              border: 'none', cursor: canSave ? 'pointer' : 'not-allowed',
              fontSize: 13, fontWeight: 800, fontFamily: 'inherit',
              boxShadow: canSave ? '0 4px 12px rgba(0,64,161,.18)' : 'none',
            }}
          >
            {saving ? '저장 중…' : (willShare ? `${recipientIds.length}명에게 공유` : '비공개로 저장')}
          </button>
        </div>
      </div>
    </div>
  );
}
