import { useState, useRef, useEffect } from 'react';
import { Megaphone, X } from 'lucide-react';
import RecipientPicker from './RecipientPicker.jsx';

function formatKoreanDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const dow = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${dow})`;
}

export default function WorkAnnouncementEditor({
  open, initialDate, onClose, onSubmit,
  hasTeam = false, teamMembers = [], currentUserId = null,
}) {
  // 게시 기간 — 시작/종료. 디폴트는 initialDate 1일짜리.
  const [startStr, setStartStr] = useState(initialDate);
  const [endStr, setEndStr] = useState(initialDate);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [shareTeam, setShareTeam] = useState(true);  // 공지는 디폴트 ON
  const [recipientIds, setRecipientIds] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const startRef = useRef(null);
  const endRef = useRef(null);

  // 모달 열릴 때 모든 동료 자동 선택 (공지 디폴트 = 전체)
  useEffect(() => {
    if (!open) return;
    setStartStr(initialDate);
    setEndStr(initialDate);
    setTitle('');
    setContent('');
    setShareTeam(true);
    const others = (teamMembers || [])
      .filter((m) => m.user_id !== currentUserId)
      .map((m) => m.user_id);
    setRecipientIds(others);
    setError('');
  }, [open, initialDate, teamMembers, currentUserId]);

  if (!open) return null;

  const isShared = shareTeam && hasTeam;
  const canShare = !isShared || recipientIds.length > 0;

  const handleSubmit = async () => {
    if (submitting) return;
    if (!title.trim()) {
      setError('공지 제목을 입력하세요');
      return;
    }
    if (!content.trim()) {
      setError('공지 내용을 입력하세요');
      return;
    }
    if (!startStr || !endStr) {
      setError('게시 시작일과 종료일을 모두 입력하세요');
      return;
    }
    // 사용자가 시작 > 종료 로 입력하면 자동 swap
    const [start, end] = startStr <= endStr ? [startStr, endStr] : [endStr, startStr];
    if (isShared && recipientIds.length === 0) {
      setError('공유 받을 팀원을 1명 이상 선택하세요');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await onSubmit?.({
        // dateStr 은 visit_date (게시 시작일) 로 사용 — backend 가 announce_* 우선
        dateStr: start,
        announce_start_date: start,
        announce_end_date: end,
        title: title.trim(),
        content: content.trim(),
        visibility: isShared ? 'team' : 'private',
        recipient_user_ids: isShared ? recipientIds : null,
      });
    } catch (e) {
      setError(e.message || '저장 실패');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
      zIndex: 320, display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16, animation: 'fadeIn .18s ease', fontFamily: 'inherit',
    }}>
      <div style={{
        background: 'var(--bg-1)', borderRadius: 14,
        width: 560, maxWidth: '100%', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
        animation: 'fadeUp .2s ease',
      }}>
      {/* 상단바 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '14px 16px', borderBottom: '1px solid var(--bd-s)',
        flexShrink: 0,
      }}>
        <Megaphone size={16} style={{ color: 'var(--ac)' }} />
        <div style={{
          flex: 1, fontSize: 16, fontWeight: 800,
          color: 'var(--t1)', letterSpacing: '-.01em',
        }}>
          업무공지 등록
        </div>
        <button
          onClick={onClose}
          aria-label="닫기"
          style={{
            width: 30, height: 30, border: '1px solid var(--bd-s)', borderRadius: 7,
            background: 'var(--bg-2)', color: 'var(--t3)', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
          }}
        >
          <X size={14} />
        </button>
      </div>

      {/* 본문 */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '18px 16px 20px',
      }}>
        <SectionLabel>게시 기간 *</SectionLabel>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 8, alignItems: 'center', marginBottom: 16 }}>
          <FieldBox
            onClick={() => startRef.current?.showPicker?.() ?? startRef.current?.click()}
            clickable
            inline
          >
            <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 2 }}>시작</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)' }}>
              {formatKoreanDate(startStr)}
            </div>
            <input
              ref={startRef}
              type="date"
              value={startStr}
              onChange={(e) => {
                if (!e.target.value) return;
                setStartStr(e.target.value);
                // 시작 > 기존 종료면 종료도 같이 밀어서 일관성 유지
                if (e.target.value > endStr) setEndStr(e.target.value);
              }}
              style={hiddenDateInput}
            />
          </FieldBox>
          <span style={{ color: 'var(--t3)', fontSize: 13, fontWeight: 600 }}>~</span>
          <FieldBox
            onClick={() => endRef.current?.showPicker?.() ?? endRef.current?.click()}
            clickable
            inline
          >
            <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 2 }}>종료</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)' }}>
              {formatKoreanDate(endStr)}
            </div>
            <input
              ref={endRef}
              type="date"
              value={endStr}
              min={startStr}
              onChange={(e) => e.target.value && setEndStr(e.target.value)}
              style={hiddenDateInput}
            />
          </FieldBox>
        </div>

        <SectionLabel>제목 *</SectionLabel>
        <FieldBox>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={100}
            placeholder="예: 5월 월간 실적 보고 안내"
            style={textInput}
          />
        </FieldBox>

        <SectionLabel>내용 *</SectionLabel>
        <FieldBox>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            maxLength={2000}
            rows={8}
            placeholder="공지 상세 내용을 입력하세요&#10;(일시, 장소, 준비물, 참고사항 등)"
            style={{ ...textInput, resize: 'vertical', lineHeight: 1.55, minHeight: 140 }}
          />
        </FieldBox>

        {hasTeam ? (
          <>
            <div style={{
              marginTop: 4, padding: '10px 12px', borderRadius: 10,
              background: 'var(--bg-2)', color: 'var(--t2)',
              fontSize: 11, fontWeight: 500, lineHeight: 1.5,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={shareTeam}
                  onChange={(e) => setShareTeam(e.target.checked)}
                  style={{ accentColor: 'var(--ac)' }}
                />
                팀에게 공유 (선택한 팀원에게만 공지)
              </label>
            </div>
            {shareTeam && (
              <div style={{ marginTop: 10 }}>
                <RecipientPicker
                  members={teamMembers}
                  value={recipientIds}
                  onChange={setRecipientIds}
                  currentUserId={currentUserId}
                />
              </div>
            )}
          </>
        ) : (
          <div style={{
            marginTop: 4, padding: '10px 12px', borderRadius: 10,
            background: 'var(--bg-2)', color: 'var(--t3)',
            fontSize: 11, fontWeight: 500, lineHeight: 1.5,
          }}>
            팀에 속해있지 않아 본인에게만 표시됩니다. 팀 관리에서 팀을 만들어보세요.
          </div>
        )}

        {error && (
          <div style={{
            marginTop: 10, padding: '10px 12px', borderRadius: 10,
            background: '#fee2e2', color: '#b91c1c', fontSize: 12, fontWeight: 600,
          }}>
            {error}
          </div>
        )}
      </div>

      {/* 하단 CTA */}
      <div style={{
        padding: '12px 16px 16px', borderTop: '1px solid var(--bd-s)',
        flexShrink: 0,
      }}>
        <button
          onClick={handleSubmit}
          disabled={submitting || !canShare}
          style={{
            width: '100%', height: 48, border: 'none', borderRadius: 12,
            background: 'var(--ac)', color: '#fff',
            fontSize: 14, fontWeight: 800, letterSpacing: '-.01em',
            cursor: submitting || !canShare ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
            boxShadow: '0 6px 18px rgba(0,64,161,.22)',
            opacity: submitting || !canShare ? 0.6 : 1,
          }}
        >
          {submitting ? '등록 중…' : (isShared && !canShare ? '수신자 1명 이상 선택' : '공지 등록')}
        </button>
      </div>
      </div>
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 12, fontWeight: 700, color: 'var(--t2)',
      marginBottom: 8, paddingLeft: 2,
    }}>
      {children}
    </div>
  );
}

function FieldBox({ children, onClick, clickable, inline }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: inline ? '10px 12px' : '14px 16px',
        borderRadius: inline ? 10 : 14,
        background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
        marginBottom: inline ? 0 : 16, position: 'relative',
        cursor: clickable ? 'pointer' : 'text',
      }}
    >
      {children}
    </div>
  );
}

const textInput = {
  width: '100%', border: 'none', outline: 'none',
  background: 'transparent', color: 'var(--t1)',
  fontFamily: 'inherit', fontSize: 15, fontWeight: 600,
};

const hiddenDateInput = {
  position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer',
  border: 'none', fontFamily: 'inherit',
};
