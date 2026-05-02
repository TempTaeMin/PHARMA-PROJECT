import { useMemo, useState, useEffect } from 'react';
import { Calendar, Check, ChevronUp, ChevronDown, MapPin, X } from 'lucide-react';

const GRADE_CHIP = {
  A: { bg: '#ffdad6', c: '#ba1a1a' },
  B: { bg: '#fef3c7', c: '#b45309' },
  C: { bg: '#dae2ff', c: '#0056d2' },
};

const DOW_LABELS = ['일', '월', '화', '수', '목', '금', '토'];
const SLOT_LABELS = { morning: '오전', afternoon: '오후', evening: '야간' };
const MINUTE_STEP = 10;

/**
 * 시간 선택 풀스크린.
 * 시/분 스피너 타임피커 (24H). 진료시간이 아닌 시각도 자유롭게 선택 가능.
 * 해당 요일 정규 진료시간이 있으면 참고용 힌트로만 표시.
 */
export default function SelectMeetingTime({
  open, doctor, initialDate, todayStr, onBack, onConfirm,
}) {
  const [dateStr, setDateStr] = useState(initialDate || todayStr);
  const [dateEdit, setDateEdit] = useState(false);
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDateStr(initialDate || todayStr);
    setDateEdit(false);
    setHour(9);
    setMinute(0);
    setNotes('');
  }, [open, initialDate, todayStr]);

  // 참고용 — 해당 요일 정규 진료시간
  const scheduleHint = useMemo(() => {
    if (!doctor || !dateStr) return null;
    const d = new Date(dateStr + 'T00:00:00');
    const dow = (d.getDay() + 6) % 7; // 0=월

    const overrides = (doctor.date_schedules || []).filter(ds => ds.schedule_date === dateStr);
    if (overrides.length > 0) {
      const openOv = overrides.filter(ov => ov.status && ov.status !== '휴진');
      if (openOv.length === 0) return { closed: true };
      return {
        entries: openOv.map(ov => ({
          slot: SLOT_LABELS[ov.time_slot] || '',
          range: '',
          status: ov.status,
        })),
        overridden: true,
      };
    }

    const weekly = (doctor.schedules || []).filter(s => s.day_of_week === dow);
    if (weekly.length === 0) return null;
    return {
      entries: weekly.map(s => ({
        slot: SLOT_LABELS[s.time_slot] || '',
        range: formatRange(s.start_time, s.end_time),
      })),
    };
  }, [doctor, dateStr]);

  if (!open || !doctor) return null;

  const dateObj = new Date(dateStr + 'T00:00:00');
  const dowLabel = DOW_LABELS[dateObj.getDay()];

  const incH = () => setHour((hour + 1) % 24);
  const decH = () => setHour((hour + 23) % 24);
  const incM = () => setMinute((minute + MINUTE_STEP) % 60);
  const decM = () => setMinute((minute - MINUTE_STEP + 60) % 60);

  const timeHHMM = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;

  const handleConfirm = async () => {
    setSaving(true);
    try {
      await onConfirm({
        doctor,
        dateStr,
        timeHHMM,
        notes: notes.trim() || null,
      });
    } catch (e) {
      alert('저장 실패: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const location = doctor.schedules?.find(s => s.location)?.location || '';

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
      zIndex: 360, display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16, animation: 'fadeIn .18s ease',
    }}>
      <div style={{
        background: 'var(--bg-1)', borderRadius: 14,
        width: 560, maxWidth: '100%', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
        animation: 'fadeUp .2s ease',
      }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '14px 16px',
        borderBottom: '1px solid var(--bd-s)',
        flexShrink: 0,
      }}>
        <div style={{
          flex: 1, fontFamily: 'Manrope', fontSize: 16, fontWeight: 800,
          color: 'var(--t1)',
        }}>
          일정 상세 설정
        </div>
        <button onClick={onBack} aria-label="닫기" style={{
          width: 30, height: 30, border: '1px solid var(--bd-s)', borderRadius: 7,
          background: 'var(--bg-2)', color: 'var(--t3)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
        }}>
          <X size={14} />
        </button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 16px' }}>
        {/* 의료진 정보 */}
        <SectionLabel>의료진 정보</SectionLabel>
        <div style={{
          padding: '18px 16px', borderRadius: 14,
          background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
          marginBottom: 18, textAlign: 'center',
        }}>
          <div style={{
            fontSize: 10, fontWeight: 700, color: 'var(--ac)', letterSpacing: '.05em',
            marginBottom: 6,
          }}>
            선택된 의료진
          </div>
          <div style={{
            fontFamily: 'Manrope', fontSize: 22, fontWeight: 800,
            color: 'var(--t1)', marginBottom: 8,
          }}>
            {doctor.name} 교수
          </div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            justifyContent: 'center', flexWrap: 'wrap',
          }}>
            {doctor.department && (
              <span style={{
                padding: '4px 10px', borderRadius: 14,
                background: 'var(--bg-2)', color: 'var(--t2)',
                fontSize: 11, fontWeight: 700,
              }}>{doctor.department}</span>
            )}
            <span style={{ fontSize: 12, color: 'var(--t3)' }}>
              {doctor.hospital_name}
            </span>
          </div>
          {location && (
            <div style={{
              marginTop: 6, fontSize: 11, color: 'var(--t3)',
              display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center',
            }}>
              <MapPin size={10} /> {location}
            </div>
          )}
        </div>

        {/* 방문 일정 */}
        <SectionLabel>방문 일정</SectionLabel>
        <div style={{
          padding: '14px 16px', borderRadius: 14,
          background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
          marginBottom: 18,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Calendar size={18} style={{ color: 'var(--ac)' }} />
            <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--t1)' }}>
              {dateObj.getFullYear()}년 {dateObj.getMonth() + 1}월 {dateObj.getDate()}일 ({dowLabel})
            </div>
          </div>
          <button
            onClick={() => setDateEdit(v => !v)}
            style={{
              padding: '8px 12px', borderRadius: 9,
              background: 'var(--bg-2)', color: 'var(--ac)',
              border: '1px solid var(--bd-s)',
              fontSize: 12, fontWeight: 700, cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            날짜 변경
          </button>
        </div>
        {dateEdit && (
          <input
            type="date"
            value={dateStr}
            onChange={e => setDateStr(e.target.value)}
            style={{
              width: '100%', padding: '11px 13px', borderRadius: 10,
              border: '1px solid var(--bd)', background: 'var(--bg-2)',
              fontSize: 14, fontFamily: 'inherit', color: 'var(--t1)',
              marginTop: -12, marginBottom: 18, boxSizing: 'border-box',
            }}
          />
        )}

        {/* 시간 설정 */}
        <SectionLabel>시간 설정</SectionLabel>
        <div style={{
          padding: '22px 16px 20px', borderRadius: 14,
          background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
          marginBottom: scheduleHint ? 10 : 18,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 14,
            justifyContent: 'center',
          }}>
            <SpinnerCol value={hour} onInc={incH} onDec={decH} />
            <div style={{
              fontFamily: 'Manrope', fontSize: 38, fontWeight: 800,
              color: 'var(--t2)', lineHeight: 1, paddingBottom: 4,
            }}>:</div>
            <SpinnerCol value={minute} onInc={incM} onDec={decM} />
            <span style={{
              marginLeft: 10, padding: '4px 9px', borderRadius: 6,
              background: 'var(--ac-d)', color: 'var(--ac)',
              fontSize: 10, fontWeight: 800, fontFamily: 'Manrope',
              letterSpacing: '.04em',
            }}>24H</span>
          </div>
        </div>

        {/* 진료시간 힌트 */}
        {scheduleHint && (
          scheduleHint.closed ? (
            <div style={{
              marginBottom: 18, padding: '10px 12px', borderRadius: 10,
              background: '#fee2e2', border: '1px solid #fca5a5',
              fontSize: 11, color: '#7f1d1d',
            }}>
              ⚠ 이 날은 해당 교수의 정규 진료가 없습니다. 자유롭게 시간을 선택할 수 있습니다.
            </div>
          ) : scheduleHint.entries && scheduleHint.entries.length > 0 ? (
            <div style={{
              marginBottom: 18, padding: '10px 12px', borderRadius: 10,
              background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
              fontSize: 11, color: 'var(--t2)', lineHeight: 1.5,
            }}>
              <span style={{ fontWeight: 800, color: 'var(--t3)', marginRight: 6 }}>
                {scheduleHint.overridden ? '이 날짜 진료' : '정규 진료'}
              </span>
              {scheduleHint.entries.map((e, i) => (
                <span key={i} style={{ marginRight: 10 }}>
                  {e.slot}{e.range ? ` ${e.range}` : ''}{e.status ? ` (${e.status})` : ''}
                </span>
              ))}
            </div>
          ) : null
        )}

        {/* 방문 사전 메모 */}
        <SectionLabel>방문 사전 메모</SectionLabel>
        <textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          rows={4}
          maxLength={500}
          placeholder="미팅 목적이나 준비사항을 입력하세요..."
          style={{
            width: '100%', padding: '13px 14px', borderRadius: 14,
            border: '1px solid var(--bd-s)', background: 'var(--bg-2)',
            fontSize: 13, fontFamily: 'inherit', color: 'var(--t1)',
            outline: 'none', resize: 'vertical', boxSizing: 'border-box',
            lineHeight: 1.5,
          }}
        />
        <div style={{
          marginTop: 4, fontSize: 10, color: 'var(--t3)', textAlign: 'right',
        }}>
          {notes.length} / 500
        </div>
      </div>

      {/* 하단 완료 버튼 */}
      <div style={{
        padding: '12px 16px 16px',
        borderTop: '1px solid var(--bd-s)',
        flexShrink: 0,
      }}>
        <button
          onClick={handleConfirm}
          disabled={saving}
          style={{
            width: '100%', padding: '13px 20px', borderRadius: 12,
            background: 'var(--ac)',
            color: '#fff', border: 'none',
            fontSize: 14, fontWeight: 800, fontFamily: 'inherit',
            cursor: saving ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            opacity: saving ? .7 : 1,
          }}
        >
          {saving ? '저장 중…' : (
            <>
              일정 등록 완료
              <Check size={18} />
            </>
          )}
        </button>
      </div>
      </div>
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 800, color: 'var(--t3)',
      letterSpacing: '.04em', marginBottom: 8, marginLeft: 2,
    }}>
      {children}
    </div>
  );
}

function SpinnerCol({ value, onInc, onDec }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
    }}>
      <button onClick={onInc} style={spinBtn} aria-label="증가">
        <ChevronUp size={22} />
      </button>
      <div style={{
        fontFamily: 'Manrope', fontSize: 46, fontWeight: 800,
        color: 'var(--t1)', minWidth: 76, textAlign: 'center',
        lineHeight: 1.1,
        fontVariantNumeric: 'tabular-nums',
      }}>
        {String(value).padStart(2, '0')}
      </div>
      <button onClick={onDec} style={spinBtn} aria-label="감소">
        <ChevronDown size={22} />
      </button>
    </div>
  );
}

function formatRange(start, end) {
  if (!start && !end) return '';
  const s = (start || '').slice(0, 5);
  const e = (end || '').slice(0, 5);
  if (s && e) return `${s}-${e}`;
  return s || e || '';
}

const spinBtn = {
  width: 44, height: 32, borderRadius: 8,
  background: 'transparent', border: 'none',
  cursor: 'pointer', color: 'var(--t3)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};
