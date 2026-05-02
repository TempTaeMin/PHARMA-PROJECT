import { useState, useRef, useEffect } from 'react';
import { Megaphone, X } from 'lucide-react';

function formatKoreanDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const dow = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${dow})`;
}

export default function WorkAnnouncementEditor({ open, initialDate, onClose, onSubmit }) {
  const [dateStr, setDateStr] = useState(initialDate);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const dateRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setDateStr(initialDate);
    setTitle('');
    setContent('');
    setError('');
  }, [open, initialDate]);

  if (!open) return null;

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
    setSubmitting(true);
    setError('');
    try {
      await onSubmit?.({
        dateStr,
        title: title.trim(),
        content: content.trim(),
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
        <SectionLabel>공지 날짜</SectionLabel>
        <FieldBox
          onClick={() => dateRef.current?.showPicker?.() ?? dateRef.current?.click()}
          clickable
        >
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--t1)' }}>
            {formatKoreanDate(dateStr)}
          </div>
          <input
            ref={dateRef}
            type="date"
            value={dateStr}
            onChange={(e) => e.target.value && setDateStr(e.target.value)}
            style={hiddenDateInput}
          />
        </FieldBox>

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

        <div style={{
          marginTop: 4, padding: '10px 12px', borderRadius: 10,
          background: 'var(--bg-2)', color: 'var(--t3)',
          fontSize: 11, fontWeight: 500, lineHeight: 1.5,
        }}>
          팀원 공유 기능은 추후 추가될 예정입니다. 현재는 본인 일정에만 기록됩니다.
        </div>

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
          disabled={submitting}
          style={{
            width: '100%', height: 48, border: 'none', borderRadius: 12,
            background: 'var(--ac)', color: '#fff',
            fontSize: 14, fontWeight: 800, letterSpacing: '-.01em',
            cursor: submitting ? 'wait' : 'pointer', fontFamily: 'inherit',
            boxShadow: '0 6px 18px rgba(0,64,161,.22)',
            opacity: submitting ? 0.7 : 1,
          }}
        >
          {submitting ? '등록 중…' : '공지 등록'}
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

function FieldBox({ children, onClick, clickable }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: '14px 16px', borderRadius: 14,
        background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
        marginBottom: 16, position: 'relative',
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
