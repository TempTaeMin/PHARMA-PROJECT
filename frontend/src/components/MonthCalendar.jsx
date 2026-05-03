import { useMemo } from 'react';
import { useSwipeable } from 'react-swipeable';
import { ymd } from '../hooks/useMonthCalendar';

const DOW_KO = ['일', '월', '화', '수', '목', '금', '토'];

function underlineColor(dateStr, doctorsForDate, visitsForDate, overdueSet) {
  const hasOverdue = doctorsForDate.some(x => overdueSet.has(x.doctor.id));
  if (hasOverdue) return '#dc2626';
  if (doctorsForDate.length > 0) return 'var(--ac)';
  if (visitsForDate.length > 0) return '#0040a1';
  return null;
}

/**
 * 월간/주간 토글 가능한 캘린더.
 * - 오늘: 검정 둥근 사각 배지
 * - 선택: 회색 둥근 외곽선
 * - 일정: 날짜 아래 3px 컬러 밑줄
 */
export default function MonthCalendar({
  year, month,
  selected, onSelect,
  mode = 'month',
  onModeChange,
  onPrev,
  onNext,
  todayStr,
  doctorsByDate = {},
  visitsByDate = {},
  overdueSet = new Set(),
}) {
  const swipeHandlers = useSwipeable({
    onSwipedUp: () => { if (mode === 'month') onModeChange?.('week'); },
    onSwipedDown: () => { if (mode === 'week') onModeChange?.('month'); },
    onSwipedLeft: () => onNext?.(),
    onSwipedRight: () => onPrev?.(),
    preventScrollOnSwipe: true,
    trackMouse: false,
    delta: 40,
  });

  const cells = useMemo(() => {
    if (mode === 'week') {
      const base = selected ? new Date(selected + 'T00:00:00') : new Date(year, month, 1);
      const dow = base.getDay(); // 0=일
      const sunday = new Date(base);
      sunday.setDate(sunday.getDate() - dow);
      return Array.from({ length: 7 }, (_, i) => {
        const d = new Date(sunday);
        d.setDate(d.getDate() + i);
        return {
          y: d.getFullYear(),
          m: d.getMonth(),
          day: d.getDate(),
          dateStr: ymd(d.getFullYear(), d.getMonth(), d.getDate()),
          dow: i,
          outOfMonth: d.getMonth() !== month,
        };
      });
    }
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const firstDow = new Date(year, month, 1).getDay(); // 0=일
    const list = [];
    // 이전 달 꼬리
    for (let i = 0; i < firstDow; i++) {
      const d = new Date(year, month, -(firstDow - 1 - i));
      list.push({
        y: d.getFullYear(), m: d.getMonth(), day: d.getDate(),
        dateStr: ymd(d.getFullYear(), d.getMonth(), d.getDate()),
        dow: i, outOfMonth: true,
      });
    }
    for (let d = 1; d <= daysInMonth; d++) {
      list.push({
        y: year, m: month, day: d,
        dateStr: ymd(year, month, d),
        dow: (firstDow + d - 1) % 7,
        outOfMonth: false,
      });
    }
    // 다음 달 머리 (6주 채우기)
    while (list.length < 42) {
      const last = list[list.length - 1];
      const d = new Date(last.y, last.m, last.day + 1);
      list.push({
        y: d.getFullYear(), m: d.getMonth(), day: d.getDate(),
        dateStr: ymd(d.getFullYear(), d.getMonth(), d.getDate()),
        dow: (last.dow + 1) % 7,
        outOfMonth: true,
      });
    }
    return list;
  }, [year, month, mode, selected]);

  const cellHeight = mode === 'week' ? 68 : 64;

  return (
    <div {...swipeHandlers} style={{ background: 'var(--bg-1)', borderRadius: 18, padding: '14px 10px 8px', border: '1px solid var(--bd-s)', touchAction: 'pan-y', userSelect: 'none' }}>
      {/* 요일 헤더 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', marginBottom: 6 }}>
        {DOW_KO.map((d, i) => (
          <div key={d} style={{
            padding: '8px 0', textAlign: 'center',
            fontSize: 12, fontWeight: 700, letterSpacing: '.02em',
            color: i === 0 ? '#ef4444' : i === 6 ? '#3b82f6' : 'var(--t3)',
          }}>{d}</div>
        ))}
      </div>

      {/* 날짜 그리드 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: 2,
      }}>
        {cells.map((c, i) => {
          const isToday = c.dateStr === todayStr;
          const isSelected = c.dateStr === selected;
          const doctorsHere = doctorsByDate[c.dateStr] || [];
          const visitsHere = visitsByDate[c.dateStr] || [];
          const underline = underlineColor(c.dateStr, doctorsHere, visitsHere, overdueSet);

          const dowColor = c.dow === 0 ? '#ef4444' : c.dow === 6 ? '#3b82f6' : 'var(--t1)';

          const showBadge = !c.outOfMonth && visitsHere.length > 0;
          const showUnderline = !!underline && !c.outOfMonth;
          return (
            <button
              key={i}
              onClick={() => onSelect(c.dateStr)}
              style={{
                position: 'relative',
                height: cellHeight,
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: 4,
                fontFamily: 'inherit',
                // 모든 셀이 동일한 layout — 날짜 박스 위, 점(underline) 자리는 항상 reserve
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'flex-start',
                gap: 6,
                opacity: c.outOfMonth ? 0.3 : 1,
                transition: 'transform .1s',
              }}
              onMouseEnter={e => { if (!isSelected) e.currentTarget.style.transform = 'scale(1.03)'; }}
              onMouseLeave={e => { e.currentTarget.style.transform = 'none'; }}
            >
              <div style={{
                position: 'relative',
                width: 36, height: 36,
                borderRadius: 10,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: isToday ? 'var(--t1)' : 'transparent',
                border: isSelected && !isToday ? '1.5px solid var(--bd)' : 'none',
                boxShadow: isSelected && isToday ? '0 0 0 2px var(--bd)' : 'none',
                transition: 'all .15s',
                flexShrink: 0,
              }}>
                <span style={{
                  fontSize: 15,
                  fontWeight: isToday ? 800 : 500,
                  fontFamily: 'Manrope',
                  color: isToday ? '#fff' : dowColor,
                }}>{c.day}</span>
                {/* 등록된 일정 개수 배지 (우상단) */}
                {showBadge && (
                  <span style={{
                    position: 'absolute',
                    top: -5, right: -5,
                    minWidth: 16, height: 16,
                    padding: '0 4px',
                    borderRadius: 8,
                    background: '#0040a1',
                    color: '#fff',
                    fontSize: 10,
                    fontWeight: 800,
                    fontFamily: 'Manrope',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: '0 0 0 1.5px var(--bg-1)',
                    boxSizing: 'border-box',
                    pointerEvents: 'none',
                  }}>
                    {visitsHere.length}
                  </span>
                )}
              </div>
              {/* 일정 밑줄 — 항상 자리 reserve (없으면 투명) */}
              <div style={{
                width: 22,
                height: 3,
                borderRadius: 2,
                background: showUnderline ? underline : 'transparent',
                flexShrink: 0,
              }} />
            </button>
          );
        })}
      </div>
    </div>
  );
}
