import { useMemo, useState } from 'react';
import { ArrowLeft, Calendar, Check, MapPin } from 'lucide-react';

// 30분 단위 슬롯 정의
const MORNING_SLOTS = ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30'];
const AFTERNOON_SLOTS = ['13:00', '13:30', '14:00', '14:30', '15:00', '15:30', '16:00', '16:30', '17:00', '17:30'];

const GRADE_CHIP = {
  A: { bg: '#ffdad6', c: '#ba1a1a' },
  B: { bg: '#fef3c7', c: '#b45309' },
  C: { bg: '#dae2ff', c: '#0056d2' },
};

/**
 * 시간 선택 풀스크린.
 * 교수 진료시간(doctor.schedules) 기반으로 30분 단위 슬롯을 활성/비활성화.
 * 사전 메모 textarea 포함.
 */
export default function SelectMeetingTime({
  open, doctor, initialDate, todayStr, onBack, onConfirm,
}) {
  const [dateStr, setDateStr] = useState(initialDate || todayStr);
  const [dateEdit, setDateEdit] = useState(false);
  const [selectedTime, setSelectedTime] = useState(null);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  // 선택한 날짜의 요일 → 교수가 오전/오후 진료하는지
  const availability = useMemo(() => {
    if (!doctor || !dateStr) return { morningActive: false, afternoonActive: false };
    const d = new Date(dateStr + 'T00:00:00');
    const dow = (d.getDay() + 6) % 7; // 0=월 ~ 6=일

    // 해당 날짜 override 우선
    const overrides = (doctor.date_schedules || []).filter(ds => ds.schedule_date === dateStr);
    const slotsFromOverride = overrides
      .filter(ov => ov.status !== '휴진' && ov.status !== '')
      .map(ov => ov.time_slot);

    if (overrides.length > 0) {
      // override가 있으면 override만 인정 (휴진이 포함되면 해당 슬롯 비활성)
      const closed = new Set(overrides.filter(ov => ov.status === '휴진').map(ov => ov.time_slot));
      return {
        morningActive: slotsFromOverride.includes('morning') && !closed.has('morning'),
        afternoonActive: slotsFromOverride.includes('afternoon') && !closed.has('afternoon'),
        overridden: true,
      };
    }

    const weekly = (doctor.schedules || []).filter(s => s.day_of_week === dow);
    return {
      morningActive: weekly.some(s => s.time_slot === 'morning'),
      afternoonActive: weekly.some(s => s.time_slot === 'afternoon'),
      overridden: false,
    };
  }, [doctor, dateStr]);

  // 슬롯 비활성(과거 시각) 계산
  const pastCheck = (time) => {
    if (dateStr !== todayStr) return false;
    const now = new Date();
    const [h, m] = time.split(':').map(Number);
    const slotMin = h * 60 + m;
    const nowMin = now.getHours() * 60 + now.getMinutes();
    return slotMin < nowMin;
  };

  if (!open || !doctor) return null;

  const dateObj = new Date(dateStr + 'T00:00:00');
  const dowLabel = ['일', '월', '화', '수', '목', '금', '토'][dateObj.getDay()];

  const handleConfirm = async () => {
    if (!selectedTime) return;
    setSaving(true);
    try {
      await onConfirm({
        doctor,
        dateStr,
        timeHHMM: selectedTime,
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
      position: 'fixed', inset: 0, background: 'var(--bg-0)',
      zIndex: 360, display: 'flex', flexDirection: 'column',
      animation: 'fadeIn .18s ease',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '16px 16px 12px',
        background: 'var(--bg-1)', borderBottom: '1px solid var(--bd-s)',
        flexShrink: 0,
      }}>
        <button onClick={onBack} style={iconBtn}>
          <ArrowLeft size={20} />
        </button>
        <div style={{
          flex: 1, fontFamily: 'Manrope', fontSize: 18, fontWeight: 800,
          color: 'var(--t1)',
        }}>
          시간 선택
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 140px' }}>
        {/* 교수 카드 */}
        <div style={{
          padding: '14px 16px', borderRadius: 14,
          background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
          marginBottom: 16,
        }}>
          <div style={{
            fontSize: 10, fontWeight: 700, color: 'var(--t3)', letterSpacing: '.05em',
            marginBottom: 4,
          }}>
            선택된 의료진
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--t1)' }}>
              {doctor.name} 교수
            </div>
            {doctor.visit_grade && (
              <span style={{
                padding: '2px 7px', borderRadius: 5,
                fontSize: 9, fontWeight: 700, fontFamily: "'JetBrains Mono'",
                ...(GRADE_CHIP[doctor.visit_grade] || {}),
              }}>{doctor.visit_grade}</span>
            )}
          </div>
          <div style={{ fontSize: 12, color: 'var(--t3)' }}>
            {doctor.hospital_name} · {doctor.department}
            {location && <> · <MapPin size={10} style={{ display: 'inline', verticalAlign: -1 }}/> {location}</>}
          </div>
        </div>

        {/* 날짜 */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: 12,
        }}>
          <div>
            <div style={{
              fontSize: 11, fontWeight: 700, color: 'var(--t3)', letterSpacing: '.05em',
              marginBottom: 3,
            }}>
              예약 희망일
            </div>
            <div style={{ fontSize: 17, fontWeight: 800, color: 'var(--t1)' }}>
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
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            <Calendar size={13} />
            날짜 변경
          </button>
        </div>
        {dateEdit && (
          <input
            type="date"
            value={dateStr}
            onChange={e => { setDateStr(e.target.value); setSelectedTime(null); }}
            style={{
              width: '100%', padding: '11px 13px', borderRadius: 10,
              border: '1px solid var(--bd)', background: 'var(--bg-1)',
              fontSize: 14, fontFamily: 'inherit', color: 'var(--t1)',
              marginBottom: 14,
            }}
          />
        )}

        {/* 오전 슬롯 */}
        <SlotSection
          icon="☀"
          label="오전"
          slots={MORNING_SLOTS}
          active={availability.morningActive}
          selected={selectedTime}
          onSelect={setSelectedTime}
          pastCheck={pastCheck}
        />

        {/* 오후 슬롯 */}
        <SlotSection
          icon="🌤"
          label="오후"
          slots={AFTERNOON_SLOTS}
          active={availability.afternoonActive}
          selected={selectedTime}
          onSelect={setSelectedTime}
          pastCheck={pastCheck}
        />

        {availability.overridden && (
          <div style={{
            marginTop: 6, padding: '9px 12px', borderRadius: 8,
            background: '#fef3c7', color: '#78350f', fontSize: 11,
            border: '1px solid #fcd34d',
          }}>
            ⚠ 이 날짜는 교수 일정 변경이 있습니다. 진료 가능한 시간대만 활성화됐어요.
          </div>
        )}

        {/* 사전 메모 */}
        <div style={{ marginTop: 20 }}>
          <div style={{
            fontSize: 11, fontWeight: 700, color: 'var(--t3)', letterSpacing: '.05em',
            marginBottom: 6,
          }}>
            사전 메모 (선택)
          </div>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={3}
            placeholder="방문 전 준비사항, 언급할 제품/포인트 등"
            style={{
              width: '100%', padding: '11px 13px', borderRadius: 10,
              border: '1px solid var(--bd)', background: 'var(--bg-1)',
              fontSize: 13, fontFamily: 'inherit', color: 'var(--t1)',
              outline: 'none', resize: 'vertical', boxSizing: 'border-box',
            }}
          />
        </div>
      </div>

      {/* 하단 고정 완료 버튼 */}
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0,
        padding: '14px 16px 20px',
        background: 'var(--bg-1)',
        borderTop: '1px solid var(--bd-s)',
        display: 'flex', justifyContent: 'center',
      }}>
        <button
          onClick={handleConfirm}
          disabled={!selectedTime || saving}
          style={{
            width: '100%', maxWidth: 520, padding: '15px 20px', borderRadius: 12,
            background: selectedTime ? 'var(--ac)' : 'var(--bg-h)',
            color: '#fff', border: 'none',
            fontSize: 15, fontWeight: 800, fontFamily: 'inherit',
            cursor: selectedTime ? 'pointer' : 'not-allowed',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            opacity: saving ? .7 : 1,
          }}
        >
          <Check size={18} />
          {saving ? '저장 중…' : selectedTime ? `${selectedTime} 으로 완료` : '시간을 선택하세요'}
        </button>
      </div>
    </div>
  );
}

function SlotSection({ icon, label, slots, active, selected, onSelect, pastCheck }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
      }}>
        <span style={{ fontSize: 14 }}>{icon}</span>
        <span style={{ fontSize: 13, fontWeight: 800, color: 'var(--t1)' }}>{label}</span>
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8,
      }}>
        {slots.map(time => {
          const past = pastCheck(time);
          const disabled = !active || past;
          const isSelected = selected === time;
          return (
            <button
              key={time}
              disabled={disabled}
              onClick={() => onSelect(time)}
              style={{
                padding: '12px 6px', borderRadius: 10,
                background: isSelected ? 'var(--ac)'
                  : disabled ? 'var(--bg-2)'
                  : 'var(--bg-1)',
                color: isSelected ? '#fff'
                  : disabled ? 'var(--t3)'
                  : 'var(--t1)',
                border: `1.5px solid ${isSelected ? 'var(--ac)' : disabled ? 'var(--bd-s)' : 'var(--bd-s)'}`,
                fontFamily: 'inherit', cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? .55 : 1,
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
              }}
            >
              <span style={{
                fontSize: 14, fontWeight: 800,
                fontFamily: "'JetBrains Mono'",
              }}>{time}</span>
              <span style={{
                fontSize: 9, fontWeight: 600,
                color: isSelected ? '#fff' : disabled ? 'var(--t3)' : 'var(--t3)',
                opacity: isSelected ? .9 : 1,
              }}>
                {isSelected ? '선택됨' : disabled ? (past ? '지난 시각' : '미감') : '예약가능'}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

const iconBtn = {
  width: 36, height: 36, borderRadius: 10,
  background: 'transparent', border: 'none',
  cursor: 'pointer', color: 'var(--t1)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};
