import { useState, useRef, useEffect } from 'react';
import { BookOpen, X } from 'lucide-react';
import { academicApi } from '../api/client';
import { invalidate } from '../api/cache';

function formatKoreanDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const dow = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${dow})`;
}

export default function AcademicEventCreateModal({ open, initialDate, onClose, onCreated }) {
  const [startDate, setStartDate] = useState(initialDate);
  const [endDate, setEndDate] = useState('');
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [organizerName, setOrganizerName] = useState('');
  const [url, setUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const startRef = useRef(null);
  const endRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setStartDate(initialDate);
    setEndDate('');
    setName('');
    setLocation('');
    setOrganizerName('');
    setUrl('');
    setError('');
  }, [open, initialDate]);

  if (!open) return null;

  const handleSubmit = async () => {
    if (submitting) return;
    if (!name.trim()) {
      setError('학회명을 입력하세요');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const created = await academicApi.create({
        name: name.trim(),
        start_date: startDate,
        end_date: endDate || null,
        location: location.trim() || null,
        organizer_name: organizerName.trim() || null,
        url: url.trim() || null,
      });
      // Schedule 페이지의 수동 학회 월 캐시 + Conferences 목록 캐시 무효화
      const ym = startDate.slice(0, 7);
      invalidate(`academic-month-manual:${ym}`);
      invalidate('academic');
      onCreated?.(created);
      onClose?.();
    } catch (e) {
      setError(e.message || '저장 실패');
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
      {/* 상단바 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '14px 16px', borderBottom: '1px solid var(--bd-s)',
        flexShrink: 0,
      }}>
        <BookOpen size={16} style={{ color: '#7c3aed' }} />
        <div style={{
          flex: 1, fontSize: 16, fontWeight: 800,
          color: 'var(--t1)', letterSpacing: '-.01em',
        }}>
          학회 일정 추가
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
        <SectionLabel>학회명 *</SectionLabel>
        <FieldBox>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            placeholder="예: 대한내과학회 춘계학술대회"
            style={textInput}
          />
        </FieldBox>

        <SectionLabel>시작일 *</SectionLabel>
        <FieldBox onClick={() => startRef.current?.showPicker?.() ?? startRef.current?.click()} clickable>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--t1)' }}>
            {formatKoreanDate(startDate)}
          </div>
          <input
            ref={startRef}
            type="date"
            value={startDate}
            onChange={(e) => e.target.value && setStartDate(e.target.value)}
            style={hiddenDateInput}
          />
        </FieldBox>

        <SectionLabel>종료일 (선택)</SectionLabel>
        <FieldBox onClick={() => endRef.current?.showPicker?.() ?? endRef.current?.click()} clickable>
          <div style={{ fontSize: 15, fontWeight: endDate ? 700 : 500, color: endDate ? 'var(--t1)' : 'var(--t3)' }}>
            {endDate ? formatKoreanDate(endDate) : '당일 행사이면 비워두세요'}
          </div>
          <input
            ref={endRef}
            type="date"
            value={endDate}
            min={startDate}
            onChange={(e) => setEndDate(e.target.value)}
            style={hiddenDateInput}
          />
        </FieldBox>

        <SectionLabel>장소 (선택)</SectionLabel>
        <FieldBox>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            maxLength={300}
            placeholder="예: 코엑스 그랜드볼룸"
            style={textInput}
          />
        </FieldBox>

        <SectionLabel>주최 (선택)</SectionLabel>
        <FieldBox>
          <input
            value={organizerName}
            onChange={(e) => setOrganizerName(e.target.value)}
            maxLength={300}
            placeholder="예: 대한내과학회"
            style={textInput}
          />
        </FieldBox>

        <SectionLabel>URL (선택)</SectionLabel>
        <FieldBox>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            maxLength={500}
            placeholder="https://..."
            style={textInput}
          />
        </FieldBox>

        {error && (
          <div style={{
            marginTop: 4, padding: '10px 12px', borderRadius: 10,
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
          {submitting ? '등록 중…' : '학회 일정 등록'}
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
