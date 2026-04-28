import { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

/**
 * 의사 진료 시간표 캘린더 — schedules(주간 정규) + dateSchedules(특정 날짜 override) 통합 표시.
 *
 * 우선순위(useMonthCalendar 와 동일):
 *  1) 그 날짜의 dateSchedule 이 있으면 → 그것을 사용 (status='휴진' 이면 비어있는 셀)
 *  2) 없으면 그 요일의 schedules (day_of_week 매칭)
 *  3) 둘 다 없으면 비어있는 셀
 */
export default function ScheduleCalendar({ schedules = [], dateSchedules = [], compact = false }) {
  const hasAny = (schedules?.length || 0) > 0 || (dateSchedules?.length || 0) > 0;

  const [view, setView] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });

  const dateMap = useMemo(() => {
    const m = {};
    (dateSchedules || []).forEach(ds => {
      if (!ds?.schedule_date) return;
      (m[ds.schedule_date] ||= []).push(ds);
    });
    return m;
  }, [dateSchedules]);

  const dowMap = useMemo(() => {
    const m = {};
    (schedules || []).forEach(s => {
      if (s?.day_of_week === undefined || s?.day_of_week === null) return;
      (m[s.day_of_week] ||= []).push(s);
    });
    return m;
  }, [schedules]);

  const monthsAvailable = useMemo(() => {
    const set = new Set();
    (dateSchedules || []).forEach(ds => {
      if (ds?.schedule_date) set.add(ds.schedule_date.slice(0, 7));
    });
    return Array.from(set).sort();
  }, [dateSchedules]);

  if (!hasAny) return null;

  const { year, month } = view;
  const firstDay = new Date(year, month, 1);
  const startDow = (firstDay.getDay() + 6) % 7; // 월=0 ~ 일=6
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const monthStr = `${year}-${String(month + 1).padStart(2, '0')}`;

  const prevMonth = () => setView(v => v.month === 0 ? { year: v.year - 1, month: 11 } : { ...v, month: v.month - 1 });
  const nextMonth = () => setView(v => v.month === 11 ? { year: v.year + 1, month: 0 } : { ...v, month: v.month + 1 });

  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push({ empty: true, key: `e-${i}` });
  for (let d = 1; d <= daysInMonth; d++) cells.push({ d, key: `d-${d}` });
  while (cells.length % 7 !== 0) cells.push({ empty: true, key: `t-${cells.length}` });

  // dateSchedule.day_of_week 가 있으면 그 형식 사용. DB 컨벤션에서는 0=월~6=일.
  const slotsForDate = (d) => {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const overrides = dateMap[dateStr];
    if (overrides && overrides.length > 0) {
      // 휴진 entry 가 있으면 그날은 비어있는 것으로 간주
      const hasRest = overrides.some(o => o.status === '휴진');
      if (hasRest) return { am: false, pm: false, isOverride: true, isClosed: true, dateStr };
      const am = overrides.some(o => o.time_slot === 'morning');
      const pm = overrides.some(o => o.time_slot === 'afternoon');
      return { am, pm, isOverride: true, dateStr };
    }
    const dow = (startDow + d - 1) % 7;
    const regular = dowMap[dow] || [];
    return {
      am: regular.some(s => s.time_slot === 'morning'),
      pm: regular.some(s => s.time_slot === 'afternoon'),
      isOverride: false,
      dateStr,
    };
  };

  return (
    <div>
      {/* Section head — 월 이동 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{
          padding: '2px 7px', borderRadius: 5,
          fontSize: 9, fontWeight: 800, letterSpacing: '.05em',
          background: 'var(--bg-2)', color: 'var(--t3)',
          fontFamily: 'Manrope',
        }}>MONTHLY</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button onClick={prevMonth} style={btnStyle}><ChevronLeft size={14} /></button>
          <div style={{
            fontFamily: 'Manrope', fontSize: 14, fontWeight: 800,
            color: 'var(--t1)', padding: '0 6px', minWidth: 70, textAlign: 'center',
          }}>{year}.{String(month + 1).padStart(2, '0')}</div>
          <button onClick={nextMonth} style={btnStyle}><ChevronRight size={14} /></button>
        </div>
      </div>

      {/* 월 탭 — dateSchedules 가용 월만 */}
      {monthsAvailable.length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
          {monthsAvailable.map(m => {
            const active = m === monthStr;
            return (
              <button
                key={m}
                onClick={() => setView({ year: parseInt(m.slice(0, 4)), month: parseInt(m.slice(5, 7)) - 1 })}
                style={{
                  padding: '5px 12px', borderRadius: 7,
                  background: active ? 'var(--ac-d)' : 'var(--bg-1)',
                  border: `1px solid ${active ? 'var(--ac)' : 'var(--bd-s)'}`,
                  color: active ? 'var(--ac)' : 'var(--t3)',
                  fontSize: 12, fontWeight: active ? 700 : 600,
                  cursor: 'pointer', fontFamily: 'Manrope',
                }}
              >{m.slice(5)}월</button>
            );
          })}
        </div>
      )}

      {/* 요일 헤더 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4, marginBottom: 6 }}>
        {DOW_LABELS.map((label, i) => (
          <div
            key={label}
            style={{
              textAlign: 'center', fontSize: 11, fontWeight: 700,
              color: i === 5 ? 'var(--bl)' : i === 6 ? 'var(--rd)' : 'var(--t3)',
              letterSpacing: '.05em', padding: '6px 0',
            }}
          >{label}</div>
        ))}
      </div>

      {/* 캘린더 그리드 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4 }}>
        {cells.map((c, idx) => {
          if (c.empty) {
            return (
              <div
                key={c.key}
                style={{
                  aspectRatio: '1 / 1', borderRadius: 10,
                  background: 'transparent', border: '1px dashed transparent',
                }}
              />
            );
          }
          const dow = idx % 7;
          const { am, pm, isClosed, dateStr } = slotsForDate(c.d);
          const isToday = dateStr === todayStr;
          const isWeekend = dow === 5 || dow === 6;
          const dayColor = dow === 5 ? 'var(--bl)' : dow === 6 ? 'var(--rd)' : 'var(--t1)';

          const amLabel = compact ? 'AM' : '오전';
          const pmLabel = compact ? 'PM' : '오후';
          const badgeFont = compact ? 9 : 10;
          const badgePad = compact ? '2px 0' : '3px 0';
          const dateFont = compact ? 12 : 14;
          const badgeRowDir = compact ? 'row' : 'column';

          return (
            <div
              key={c.key}
              style={{
                aspectRatio: '1 / 1', borderRadius: 10,
                border: `${isToday ? 2 : 1}px solid ${isToday ? 'var(--ac)' : 'var(--bd-s)'}`,
                background: 'var(--bg-1)',
                padding: compact ? '5px 4px 6px' : '8px 8px 10px',
                display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
                gap: compact ? 3 : 6,
                minHeight: 0,
              }}
            >
              <span style={{
                fontFamily: 'Manrope', fontWeight: 700, fontSize: dateFont,
                color: isToday ? 'var(--ac)' : (isWeekend ? dayColor : 'var(--t1)'),
                lineHeight: 1,
                textAlign: compact ? 'center' : 'left',
              }}>{c.d}</span>
              <div style={{ display: 'flex', flexDirection: badgeRowDir, gap: compact ? 2 : 3 }}>
                {am && (
                  <span style={{
                    flex: compact ? 1 : 'none',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    padding: badgePad, borderRadius: 4,
                    fontSize: badgeFont, fontWeight: 800, letterSpacing: '.02em', lineHeight: 1.1,
                    fontFamily: 'Manrope', minWidth: 0,
                    background: 'var(--ac-d)', color: 'var(--ac)',
                  }}>{amLabel}</span>
                )}
                {pm && (
                  <span style={{
                    flex: compact ? 1 : 'none',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    padding: badgePad, borderRadius: 4,
                    fontSize: badgeFont, fontWeight: 800, letterSpacing: '.02em', lineHeight: 1.1,
                    fontFamily: 'Manrope', minWidth: 0,
                    background: '#fff5cc', color: '#92670a',
                  }}>{pmLabel}</span>
                )}
                {isClosed && (
                  <span style={{
                    flex: compact ? 1 : 'none',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    padding: badgePad, borderRadius: 4,
                    fontSize: badgeFont, fontWeight: 700, lineHeight: 1.1,
                    fontFamily: 'Manrope', minWidth: 0,
                    background: 'var(--bg-2)', color: 'var(--t3)',
                  }}>휴진</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 범례 */}
      <div style={{ display: 'flex', gap: 10, marginTop: 14, alignItems: 'center' }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', padding: '4px 8px', borderRadius: 6,
          fontFamily: 'Manrope', fontSize: 11, fontWeight: 800,
          background: 'var(--ac-d)', color: 'var(--ac)',
        }}>{compact ? 'AM' : '오전'}</span>
        <span style={{
          display: 'inline-flex', alignItems: 'center', padding: '4px 8px', borderRadius: 6,
          fontFamily: 'Manrope', fontSize: 11, fontWeight: 800,
          background: '#fff5cc', color: '#92670a',
        }}>{compact ? 'PM' : '오후'}</span>
      </div>
    </div>
  );
}

const DOW_LABELS = ['월', '화', '수', '목', '금', '토', '일'];
const btnStyle = {
  width: 28, height: 28, borderRadius: 8,
  background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
  color: 'var(--t3)', cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};
