import { useMemo } from 'react';
import { CheckCircle, Clock, XCircle, MapPin, Trash2 } from 'lucide-react';

const DOW_KO = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];
const DOW_SHORT = ['일', '월', '화', '수', '목', '금', '토'];

const STATUS_THEME = {
  성공: { label: 'COMPLETED', c: '#166534', bg: '#dcfce7', accent: '#16a34a' },
  부재: { label: 'MISSED',    c: '#6b7280', bg: '#f3f4f6', accent: '#9ca3af' },
  거절: { label: 'DECLINED',  c: '#b91c1c', bg: '#fee2e2', accent: '#ef4444' },
  예정: { label: 'UPCOMING',  c: '#0369a1', bg: '#e0f2fe', accent: '#0284c7' },
};

const GC = {
  A: { c: '#ba1a1a', bg: '#ffdad6' },
  B: { c: '#b45309', bg: '#fef3c7' },
  C: { c: '#0056d2', bg: '#dae2ff' },
};

function ymd(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function startOfWeek(dateStr) {
  // 월요일 기준 (MON=0)
  const d = new Date(dateStr + 'T00:00:00');
  const day = d.getDay(); // 0(일) ~ 6(토)
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d;
}

function hhmm(visitDate) {
  if (!visitDate) return '';
  const d = new Date(visitDate);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function slotToHHMM(slot) {
  if (slot === 'afternoon') return '13:00';
  if (slot === 'evening') return '18:00';
  return '09:00';
}

function minutesFromHHMM(s) {
  if (!s) return 0;
  const [h, m] = s.split(':').map(Number);
  return h * 60 + (m || 0);
}

/**
 * Daily Schedule — 오늘(또는 선택한 날짜)의 일정표를 hh:mm 세로 타임라인으로 표시.
 * 상단에 큰 날짜 타이틀 + 주간 스트립.
 */
export default function DailySchedule({
  dateStr,
  todayStr,
  doctors = [],           // [{ doctor, slots, location }]
  visits = [],            // VisitLog[]
  onSelectDate,
  onComplete,
  onCancel,
  onOpenMonth,            // "전체 일정 확인" 버튼
}) {
  const dateObj = dateStr ? new Date(dateStr + 'T00:00:00') : new Date();

  // ─ 주간 스트립 (월~일) ─
  const weekDays = useMemo(() => {
    const start = startOfWeek(dateStr);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return ymd(d.getFullYear(), d.getMonth(), d.getDate());
    });
  }, [dateStr]);

  // ─ 타임라인 항목(visits + 예정된 교수)을 시각 순 정렬 ─
  const items = useMemo(() => {
    const visitedDoctorIds = new Set(visits.map(v => v.doctor_id));

    const visitItems = visits.map(v => ({
      kind: 'visit',
      id: `v-${v.id}`,
      time: hhmm(v.visit_date) || slotToHHMM('morning'),
      minutes: v.visit_date
        ? new Date(v.visit_date).getHours() * 60 + new Date(v.visit_date).getMinutes()
        : 0,
      visit: v,
    }));

    const doctorItems = doctors
      .filter(d => !visitedDoctorIds.has(d.doctor.id))
      .flatMap(d => d.slots.map(slot => ({
        kind: 'doctor',
        id: `d-${d.doctor.id}-${slot}`,
        time: slotToHHMM(slot),
        minutes: minutesFromHHMM(slotToHHMM(slot)),
        doctor: d.doctor,
        slot,
        location: d.location,
      })));

    return [...visitItems, ...doctorItems].sort((a, b) => a.minutes - b.minutes);
  }, [doctors, visits]);

  // ─ NEXT UP: 지금 시각 이후 첫 예정 visit ─
  const nextUpId = useMemo(() => {
    if (dateStr !== todayStr) return null;
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const candidates = items.filter(it =>
      (it.kind === 'visit' && it.visit.status === '예정' && it.minutes >= nowMin)
      || (it.kind === 'doctor' && it.minutes >= nowMin)
    );
    return candidates[0]?.id || null;
  }, [items, dateStr, todayStr]);

  const count = items.length;
  const completedCount = visits.filter(v => v.status === '성공').length;
  const plannedCount = visits.filter(v => v.status === '예정').length;

  return (
    <div>
      {/* ── 날짜 타이틀 헤더 ── */}
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        padding: '12px 4px 14px', gap: 12,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: 'Manrope', fontSize: 30, fontWeight: 800,
            color: 'var(--t1)', lineHeight: 1, letterSpacing: '-.02em',
          }}>
            {DOW_KO[dateObj.getDay()]}
          </div>
          <div style={{
            fontSize: 12, color: 'var(--t3)', fontWeight: 600,
            marginTop: 6, letterSpacing: '.04em',
          }}>
            {dateObj.getFullYear()}. {dateObj.getMonth() + 1}. {dateObj.getDate()}
            {count > 0 && <> · 일정 {count}건</>}
          </div>
        </div>

        <button
          onClick={onOpenMonth}
          style={{
            padding: '9px 14px', borderRadius: 10,
            background: 'var(--ac-d)', color: 'var(--ac)',
            border: '1px solid var(--ac)',
            fontSize: 12, fontWeight: 700, cursor: 'pointer',
            fontFamily: 'inherit', whiteSpace: 'nowrap',
            display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          📅 전체 일정
        </button>
      </div>

      {/* ── 주간 스트립 ── */}
      <div style={{
        display: 'flex', gap: 6, padding: '2px 2px 14px',
        overflowX: 'auto',
      }}>
        {weekDays.map(d => {
          const obj = new Date(d + 'T00:00:00');
          const isSelected = d === dateStr;
          const isToday = d === todayStr;
          return (
            <button
              key={d}
              onClick={() => onSelectDate?.(d)}
              style={{
                flex: 1, minWidth: 48, padding: '10px 4px',
                borderRadius: 12, cursor: 'pointer',
                fontFamily: 'inherit',
                background: isSelected ? 'var(--ac)' : 'var(--bg-1)',
                color: isSelected ? '#fff' : 'var(--t1)',
                border: `1px solid ${isSelected ? 'var(--ac)' : 'var(--bd-s)'}`,
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                transition: 'background .15s',
              }}
            >
              <span style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '.05em',
                opacity: isSelected ? .85 : .6,
              }}>
                {DOW_SHORT[obj.getDay()]}
              </span>
              <span style={{
                fontFamily: 'Manrope', fontSize: 18, fontWeight: 800, lineHeight: 1,
              }}>
                {obj.getDate()}
              </span>
              {isToday && !isSelected && (
                <span style={{
                  width: 4, height: 4, borderRadius: '50%',
                  background: 'var(--ac)', marginTop: 1,
                }} />
              )}
            </button>
          );
        })}
      </div>

      {/* ── 통계 bar ── */}
      {(plannedCount > 0 || completedCount > 0) && (
        <div style={{
          display: 'flex', gap: 8, padding: '0 2px 12px',
          fontSize: 11, color: 'var(--t3)',
        }}>
          {completedCount > 0 && (
            <span style={{
              padding: '4px 9px', borderRadius: 6,
              background: '#dcfce7', color: '#166534', fontWeight: 700,
            }}>
              완료 {completedCount}
            </span>
          )}
          {plannedCount > 0 && (
            <span style={{
              padding: '4px 9px', borderRadius: 6,
              background: '#e0f2fe', color: '#0369a1', fontWeight: 700,
            }}>
              예정 {plannedCount}
            </span>
          )}
        </div>
      )}

      {/* ── 세로 타임라인 ── */}
      {items.length === 0 ? (
        <div style={{
          padding: '60px 20px', textAlign: 'center',
          color: 'var(--t3)', fontSize: 13,
          background: 'var(--bg-1)', borderRadius: 14,
          border: '1px dashed var(--bd-s)',
        }}>
          이 날은 일정이 없습니다.
          <div style={{ fontSize: 11, marginTop: 6 }}>아래 + 버튼으로 일정을 추가하세요.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {items.map(item => (
            <TimelineRow
              key={item.id}
              item={item}
              isNextUp={item.id === nextUpId}
              onComplete={onComplete}
              onCancel={onCancel}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function TimelineRow({ item, isNextUp, onComplete, onCancel }) {
  const isVisit = item.kind === 'visit';
  const theme = isVisit ? (STATUS_THEME[item.visit.status] || STATUS_THEME.예정) : STATUS_THEME.예정;
  const accent = isNextUp ? '#0369a1' : theme.accent;

  return (
    <div style={{
      display: 'flex', gap: 12, alignItems: 'stretch', minHeight: 76,
    }}>
      {/* 좌측 시각 + 점 */}
      <div style={{
        width: 48, display: 'flex', flexDirection: 'column',
        alignItems: 'center', paddingTop: 14,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11, fontWeight: 700, color: 'var(--t2)',
          marginBottom: 4,
        }}>
          {item.time}
        </div>
        <div style={{
          width: 14, height: 14, borderRadius: '50%',
          background: '#fff',
          border: `3px solid ${accent}`,
          flexShrink: 0,
          boxShadow: isNextUp ? `0 0 0 4px ${accent}22` : 'none',
        }} />
        <div style={{
          flex: 1, width: 2, background: 'var(--bg-h)', marginTop: 4,
        }} />
      </div>

      {/* 우측 카드 */}
      <div style={{ flex: 1, paddingBottom: 10 }}>
        {isVisit
          ? <VisitCard visit={item.visit} theme={theme} isNextUp={isNextUp} onComplete={onComplete} onCancel={onCancel} />
          : <DoctorCard doctor={item.doctor} location={item.location} isNextUp={isNextUp} />}
      </div>
    </div>
  );
}

function VisitCard({ visit, theme, isNextUp, onComplete, onCancel }) {
  const isPlanned = visit.status === '예정';
  return (
    <div style={{
      padding: '12px 14px', borderRadius: 12,
      background: 'var(--bg-1)',
      border: `1px solid ${isNextUp ? theme.accent : 'var(--bd-s)'}`,
      boxShadow: isNextUp ? `0 4px 14px ${theme.accent}22` : '0 1px 4px rgba(0,0,0,.03)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{
          padding: '2px 7px', borderRadius: 5,
          fontSize: 9, fontWeight: 800, letterSpacing: '.05em',
          background: isNextUp ? '#0369a1' : theme.bg,
          color: isNextUp ? '#fff' : theme.c,
          fontFamily: "'Manrope'",
        }}>
          {isNextUp ? 'NEXT UP' : theme.label}
        </span>
        {isNextUp && <span style={{ fontSize: 10, color: '#b91c1c', fontWeight: 700 }}>곧 시작</span>}
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--t1)', marginBottom: 3 }}>
        {visit.doctor_name}
      </div>
      <div style={{ fontSize: 11, color: 'var(--t3)' }}>
        {visit.hospital_name} · {visit.department}
      </div>
      {visit.product && (
        <div style={{
          display: 'inline-block', marginTop: 6,
          fontSize: 11, color: theme.c, fontWeight: 700,
        }}>
          🏷 {visit.product}
        </div>
      )}
      {visit.notes && (
        <div style={{
          fontSize: 11, color: 'var(--t2)', marginTop: 4, lineHeight: 1.45,
          padding: '6px 8px', background: 'var(--bg-2)', borderRadius: 6,
        }}>
          {visit.notes}
        </div>
      )}
      {isPlanned && (
        <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
          <button onClick={() => onComplete?.(visit)} style={{
            flex: 1, padding: '8px 10px', borderRadius: 8,
            background: 'var(--ac)', color: '#fff', border: 'none',
            fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
          }}>
            <CheckCircle size={13} />
            Check In
          </button>
          <button onClick={() => onCancel?.(visit)} style={{
            padding: '8px 10px', borderRadius: 8,
            background: 'var(--bg-2)', color: 'var(--rd)',
            border: '1px solid var(--bd-s)', cursor: 'pointer',
          }}>
            <Trash2 size={12} />
          </button>
        </div>
      )}
    </div>
  );
}

function DoctorCard({ doctor, location, isNextUp }) {
  const gc = GC[doctor.visit_grade] || GC.B;
  return (
    <div style={{
      padding: '12px 14px', borderRadius: 12,
      background: 'var(--bg-2)',
      border: `1px dashed ${isNextUp ? 'var(--ac)' : 'var(--bd-s)'}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{
          fontSize: 9, fontWeight: 800, color: 'var(--t3)', letterSpacing: '.05em',
          fontFamily: 'Manrope',
        }}>진료 예정</span>
        {doctor.visit_grade && (
          <span style={{
            padding: '1px 5px', borderRadius: 4, fontSize: 9, fontWeight: 700,
            fontFamily: "'JetBrains Mono'", background: gc.bg, color: gc.c,
          }}>{doctor.visit_grade}</span>
        )}
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)', marginBottom: 2 }}>
        {doctor.name}
      </div>
      <div style={{ fontSize: 11, color: 'var(--t3)' }}>
        {doctor.hospital_name} · {doctor.department}
        {location && <> · <MapPin size={9} style={{ display: 'inline', verticalAlign: -1 }} /> {location}</>}
      </div>
    </div>
  );
}
