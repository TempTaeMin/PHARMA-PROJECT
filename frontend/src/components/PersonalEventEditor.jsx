import { useState, useRef, useEffect } from 'react';
import { ChevronUp, ChevronDown, X } from 'lucide-react';

function formatKoreanDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const dow = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${dow})`;
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

export default function PersonalEventEditor({ open, initialDate, onClose, onSubmit }) {
  const [dateStr, setDateStr] = useState(initialDate);
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const dateInputRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setDateStr(initialDate);
    setHour(9);
    setMinute(0);
    setTitle('');
    setNotes('');
  }, [open, initialDate]);

  if (!open) return null;

  const bumpHour = (d) => setHour((h) => (h + 24 + d) % 24);
  const bumpMinute = (d) => setMinute((m) => (m + 60 + d * 5) % 60);

  const handleSubmit = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await onSubmit?.({
        dateStr,
        timeHHMM: `${pad2(hour)}:${pad2(minute)}`,
        title: title.trim() || '내 일정',
        notes: notes.trim() || null,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
        zIndex: 320, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16, animation: 'fadeIn .18s ease', fontFamily: 'inherit',
      }}
    >
      <div style={{
        background: 'var(--bg-1)', borderRadius: 14,
        width: 560, maxWidth: '100%', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
        animation: 'fadeUp .2s ease',
      }}>
      {/* ── 상단바 ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '14px 16px', borderBottom: '1px solid var(--bd-s)',
        flexShrink: 0,
      }}>
        <div style={{
          flex: 1, fontSize: 16, fontWeight: 800,
          color: 'var(--t1)', letterSpacing: '-.01em',
        }}>
          개인 일정 설정
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

      {/* ── 본문 ── */}
      <div style={{
        flex: 1, overflowY: 'auto', padding: '18px 16px 20px',
      }}>
        {/* 일정 */}
        <SectionLabel>일정</SectionLabel>
        <div
          onClick={() => dateInputRef.current?.showPicker?.() ?? dateInputRef.current?.click()}
          style={{
            padding: '18px 18px', borderRadius: 14,
            background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
            cursor: 'pointer', marginBottom: 18, position: 'relative',
          }}
        >
          <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 4 }}>날짜</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--t1)' }}>
            {formatKoreanDate(dateStr)}
          </div>
          <input
            ref={dateInputRef}
            type="date"
            value={dateStr}
            onChange={(e) => e.target.value && setDateStr(e.target.value)}
            style={{
              position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer',
              border: 'none', fontFamily: 'inherit',
            }}
          />
        </div>

        {/* 시간 설정 */}
        <SectionLabel>시간 설정</SectionLabel>
        <div style={{
          padding: '18px 16px', borderRadius: 14,
          background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
          marginBottom: 18,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 14, position: 'relative',
        }}>
          <Stepper value={hour} onUp={() => bumpHour(1)} onDown={() => bumpHour(-1)} />
          <div style={{
            fontSize: 40, fontWeight: 800, color: 'var(--t1)',
            lineHeight: 1, padding: '0 4px',
          }}>:</div>
          <Stepper value={minute} onUp={() => bumpMinute(1)} onDown={() => bumpMinute(-1)} />
          <div style={{
            position: 'absolute', right: 14, top: 14,
            padding: '3px 8px', borderRadius: 6,
            background: 'var(--ac-d)', color: 'var(--ac)',
            fontSize: 10, fontWeight: 800, letterSpacing: '.04em',
          }}>
            24H
          </div>
        </div>

        {/* 일정 제목 */}
        <SectionLabel>일정 제목</SectionLabel>
        <div style={{
          padding: '12px 14px', borderRadius: 14,
          background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
          marginBottom: 18,
        }}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={100}
            placeholder="내 일정"
            style={{
              width: '100%', border: 'none', outline: 'none',
              background: 'transparent', color: 'var(--t1)',
              fontFamily: 'inherit', fontSize: 15, fontWeight: 700,
            }}
          />
        </div>

        {/* 일정 메모 */}
        <SectionLabel>일정 메모</SectionLabel>
        <div style={{
          padding: '14px 14px 10px', borderRadius: 14,
          background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
        }}>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={500}
            placeholder="일정에 대한 메모를 입력하세요"
            rows={5}
            style={{
              width: '100%', border: 'none', outline: 'none', resize: 'none',
              background: 'transparent', color: 'var(--t1)',
              fontFamily: 'inherit', fontSize: 14, lineHeight: 1.5,
            }}
          />
          <div style={{
            textAlign: 'right', fontSize: 11, color: 'var(--t3)', marginTop: 4,
          }}>
            {notes.length}/500
          </div>
        </div>
      </div>

      {/* ── 하단 CTA ── */}
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
          {submitting ? '등록 중…' : '일정 등록 완료'}
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

function Stepper({ value, onUp, onDown }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
    }}>
      <IconBtn onClick={onUp} ariaLabel="증가"><ChevronUp size={18} /></IconBtn>
      <div style={{
        fontSize: 40, fontWeight: 800, color: 'var(--t1)',
        minWidth: 62, textAlign: 'center', lineHeight: 1,
        fontVariantNumeric: 'tabular-nums',
      }}>
        {pad2(value)}
      </div>
      <IconBtn onClick={onDown} ariaLabel="감소"><ChevronDown size={18} /></IconBtn>
    </div>
  );
}

function IconBtn({ onClick, ariaLabel, children }) {
  return (
    <button
      onClick={onClick}
      aria-label={ariaLabel}
      style={{
        width: 34, height: 28, border: '1px solid var(--bd-s)', borderRadius: 8,
        background: 'var(--bg-2)', color: 'var(--t2)', cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 0, fontFamily: 'inherit',
      }}
    >
      {children}
    </button>
  );
}
