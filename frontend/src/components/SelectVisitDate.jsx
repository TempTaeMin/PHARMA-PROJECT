import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, X } from 'lucide-react';
import { doctorApi } from '../api/client';

const DAY_LABELS = ['월', '화', '수', '목', '금', '토', '일'];

/**
 * 의사 선택 후 방문 날짜를 정하는 캘린더 모달.
 *
 * - initialDate: 일정확인에서 선택했던 날짜 (기본값)
 * - 사용자가 캘린더에서 다른 날짜로 변경 가능
 * - 진료 가능 요일은 작은 점 표시 (doctor.schedules)
 * - 날짜별 특이일정(휴진/대진)은 색상으로 구분 (doctor.date_schedules)
 * - 확인 시 onConfirm(dateStr) → 다음 단계 (진료시간표 참고 팝업) 진입
 */
export default function SelectVisitDate({ open, doctor, initialDate, onBack, onConfirm }) {
  const [selected, setSelected] = useState(initialDate || todayStr());
  const [view, setView] = useState(() => {
    const d = new Date((initialDate || todayStr()) + 'T00:00:00');
    return { year: d.getFullYear(), month: d.getMonth() };
  });
  const [details, setDetails] = useState(null); // doctorApi.get 결과
  const [loading, setLoading] = useState(false);

  // 모달이 열릴 때마다 초기화
  useEffect(() => {
    if (!open) return;
    const init = initialDate || todayStr();
    setSelected(init);
    const d = new Date(init + 'T00:00:00');
    setView({ year: d.getFullYear(), month: d.getMonth() });
  }, [open, initialDate]);

  // 의사 schedules / date_schedules 가 props 에 없으면 fetch
  useEffect(() => {
    if (!open || !doctor?.id) { setDetails(null); return; }
    if (Array.isArray(doctor.schedules)) {
      setDetails(doctor);
      return;
    }
    let cancelled = false;
    setLoading(true);
    doctorApi.get(doctor.id)
      .then(d => { if (!cancelled) setDetails(d); })
      .catch(() => { if (!cancelled) setDetails(doctor); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, doctor]);

  const activeDows = useMemo(() => {
    const set = new Set();
    (details?.schedules || []).forEach(s => {
      if (s.is_active === false) return;
      if (typeof s.day_of_week === 'number') set.add(s.day_of_week);
    });
    return set;
  }, [details]);

  const dateStatusMap = useMemo(() => {
    const m = {};
    (details?.date_schedules || []).forEach(ds => {
      if (!ds.schedule_date) return;
      const cur = m[ds.schedule_date] || { allClosed: true, hasOpen: false };
      if (ds.status && ds.status !== '휴진') { cur.hasOpen = true; cur.allClosed = false; }
      m[ds.schedule_date] = cur;
    });
    return m;
  }, [details]);

  if (!open || !doctor) return null;

  const { year, month } = view;
  const firstDow = (new Date(year, month, 1).getDay() + 6) % 7; // 0=월
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = todayStr();

  const cells = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const prevMonth = () => setView(v => v.month === 0 ? { year: v.year - 1, month: 11 } : { ...v, month: v.month - 1 });
  const nextMonth = () => setView(v => v.month === 11 ? { year: v.year + 1, month: 0 } : { ...v, month: v.month + 1 });

  const selDow = (() => {
    const d = new Date(selected + 'T00:00:00');
    return (d.getDay() + 6) % 7;
  })();
  const selectedHasSchedule = activeDows.has(selDow);
  const selectedOverride = dateStatusMap[selected];
  const selectedClosed = selectedOverride?.allClosed && !selectedOverride?.hasOpen;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
      zIndex: 350, display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 20, animation: 'fadeIn .18s ease',
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: 'var(--bg-1)', borderRadius: 18,
        width: 460, maxWidth: '95%', maxHeight: '92vh', overflowY: 'auto',
        animation: 'fadeUp .22s ease',
      }}>
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: '18px 20px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'var(--ac-d)', color: 'var(--ac)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <CalendarIcon size={18} />
            </div>
            <div>
              <div style={{ fontFamily: 'Manrope', fontSize: 16, fontWeight: 800 }}>방문 날짜 선택</div>
              <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>
                {doctor.name} · {doctor.hospital_name || details?.hospital_name || ''} · {doctor.department || details?.department || ''}
              </div>
            </div>
          </div>
          <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--t3)' }}>
            <X size={18} />
          </button>
        </div>

        {/* 월 네비 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px 8px' }}>
          <button onClick={prevMonth} style={navBtn}><ChevronLeft size={16} /></button>
          <div style={{ fontFamily: 'Outfit', fontSize: 17, fontWeight: 700 }}>
            {year}.{String(month + 1).padStart(2, '0')}
          </div>
          <button onClick={nextMonth} style={navBtn}><ChevronRight size={16} /></button>
        </div>

        {/* 캘린더 그리드 */}
        <div style={{ padding: '0 20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2 }}>
            {DAY_LABELS.map(d => (
              <div key={d} style={{
                padding: '6px 0', textAlign: 'center', fontSize: 11, fontWeight: 600,
                color: d === '토' ? 'var(--bl)' : d === '일' ? 'var(--rd)' : 'var(--t3)',
              }}>{d}</div>
            ))}
            {cells.map((day, i) => {
              if (day == null) return <div key={`e${i}`} />;
              const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
              const isSel = dateStr === selected;
              const isToday = dateStr === today;
              const cellDow = (firstDow + day - 1) % 7;
              const hasSchedule = activeDows.has(cellDow);
              const override = dateStatusMap[dateStr];
              const isClosed = override?.allClosed && !override?.hasOpen;
              const isSpecial = override?.hasOpen;
              return (
                <button
                  key={day}
                  onClick={() => setSelected(dateStr)}
                  style={{
                    position: 'relative',
                    aspectRatio: '1 / 1',
                    minHeight: 44,
                    padding: 4,
                    borderRadius: 9,
                    border: isSel ? '2px solid var(--ac)' : isToday ? '1px dashed var(--ac)' : '1px solid var(--bd-s)',
                    background: isSel ? 'var(--ac)' : 'var(--bg-1)',
                    color: isSel ? '#fff' : (cellDow === 6 ? 'var(--rd)' : cellDow === 5 ? 'var(--bl)' : 'var(--t1)'),
                    cursor: 'pointer', fontFamily: "'JetBrains Mono'",
                    fontSize: 13, fontWeight: isSel || isToday ? 700 : 500,
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    transition: 'background .12s, border .12s',
                  }}
                  title={isClosed ? '휴진' : isSpecial ? '특이일정' : hasSchedule ? '진료가능' : '진료없음'}
                >
                  <span>{day}</span>
                  <span style={{
                    marginTop: 3, width: 5, height: 5, borderRadius: '50%',
                    background: isClosed
                      ? (isSel ? '#fff' : 'var(--rd)')
                      : isSpecial
                        ? (isSel ? '#fff' : 'var(--am)')
                        : hasSchedule
                          ? (isSel ? '#fff' : 'var(--ac)')
                          : 'transparent',
                    opacity: isSel ? .9 : 1,
                  }} />
                </button>
              );
            })}
          </div>
        </div>

        {/* 범례 */}
        <div style={{
          display: 'flex', gap: 12, padding: '12px 20px',
          fontSize: 11, color: 'var(--t3)', flexWrap: 'wrap',
        }}>
          <Legend color="var(--ac)" label="진료 가능" />
          <Legend color="var(--am)" label="특이일정" />
          <Legend color="var(--rd)" label="휴진" />
        </div>

        {/* 선택 안내 */}
        <div style={{
          margin: '0 20px 16px', padding: 12, borderRadius: 10,
          background: selectedClosed ? '#fee2e2'
                     : (!selectedHasSchedule && !selectedOverride?.hasOpen ? '#fef3c7' : 'var(--ac-d)'),
          border: `1px solid ${selectedClosed ? '#fca5a5'
                              : (!selectedHasSchedule && !selectedOverride?.hasOpen ? '#fcd34d' : 'var(--ac)')}`,
          color: selectedClosed ? '#7f1d1d'
               : (!selectedHasSchedule && !selectedOverride?.hasOpen ? '#78350f' : 'var(--ac)'),
        }}>
          <div style={{ fontSize: 13, fontWeight: 700 }}>
            {formatLong(selected)}
          </div>
          <div style={{ fontSize: 11, marginTop: 3, opacity: .9 }}>
            {selectedClosed
              ? '이 날은 휴진입니다. 다른 날짜를 선택하거나 강행할 수 있어요.'
              : selectedOverride?.hasOpen
                ? '이 날 특이일정이 있습니다. 진료시간표 참고에서 확인하세요.'
                : selectedHasSchedule
                  ? '교수의 정규 진료요일입니다.'
                  : '교수의 정규 진료요일이 아닙니다. 비정기 방문이라면 그대로 진행하세요.'}
          </div>
        </div>

        {/* 액션 */}
        <div style={{ display: 'flex', gap: 8, padding: '0 20px 18px' }}>
          <button onClick={onBack} style={cancelBtn}>이전</button>
          <button onClick={() => onConfirm?.(selected)} style={confirmBtn} disabled={loading}>
            다음 (진료시간표 확인)
          </button>
        </div>
      </div>
    </div>
  );
}

function Legend({ color, label }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
      {label}
    </span>
  );
}

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function formatLong(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr + 'T00:00:00');
  const dow = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${dow})`;
}

const navBtn = {
  width: 32, height: 32, borderRadius: 9,
  background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer', color: 'var(--t2)',
};
const cancelBtn = {
  flex: '0 0 auto', padding: '12px 18px', borderRadius: 10,
  background: 'var(--bg-2)', color: 'var(--t2)', border: '1px solid var(--bd-s)',
  cursor: 'pointer', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
};
const confirmBtn = {
  flex: 1, padding: '12px 18px', borderRadius: 10,
  background: 'var(--ac)', color: '#fff', border: 'none',
  cursor: 'pointer', fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
};
