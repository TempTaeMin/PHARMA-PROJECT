import { useEffect, useMemo, useState } from 'react';
import { Calendar as CalendarIcon, X } from 'lucide-react';
import { doctorApi } from '../api/client';
import { isClosedScheduleStatus, isKoreanPublicHoliday, isOpenOnKoreanPublicHoliday } from '../utils/koreanHolidays';
import ScheduleCalendar from './ScheduleCalendar';

/**
 * 의사 선택 후 방문 날짜를 정하는 캘린더 모달.
 *
 * - initialDate: 일정확인에서 선택했던 날짜 (기본값)
 * - 사용자가 캘린더에서 다른 날짜로 변경 가능
 * - 캘린더는 의료진 상세의 진료시간표(ScheduleCalendar) 와 동일한 표시 방식
 *   (오전/오후 뱃지, 휴진 뱃지, 월간 네비)
 * - 확인 시 onConfirm(dateStr) → 다음 단계 (진료시간표 참고 팝업) 진입
 */
export default function SelectVisitDate({ open, doctor, initialDate, onBack, onConfirm }) {
  const [selected, setSelected] = useState(initialDate || todayStr());
  const [details, setDetails] = useState(null); // doctorApi.get 결과
  const [loading, setLoading] = useState(false);

  // 모달이 열릴 때마다 초기화
  useEffect(() => {
    if (!open) return;
    setSelected(initialDate || todayStr());
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
      if (ds.status && !isClosedScheduleStatus(ds.status)) {
        if (!isKoreanPublicHoliday(ds.schedule_date) || isOpenOnKoreanPublicHoliday(ds.status)) {
          cur.hasOpen = true;
          cur.allClosed = false;
        }
      }
      m[ds.schedule_date] = cur;
    });
    return m;
  }, [details]);

  if (!open || !doctor) return null;

  const selDow = (() => {
    const d = new Date(selected + 'T00:00:00');
    return (d.getDay() + 6) % 7;
  })();
  const selectedHasSchedule = activeDows.has(selDow);
  const selectedOverride = dateStatusMap[selected];
  const selectedHoliday = isKoreanPublicHoliday(selected);
  const selectedClosed = selectedOverride?.allClosed && !selectedOverride?.hasOpen;
  const selectedAvailableByWeekly = selectedHasSchedule && !selectedHoliday;

  const initialMonth = selected ? selected.slice(0, 7) : undefined;

  const calSchedules = (details?.schedules || []).map(s => ({
    day_of_week: s.day_of_week ?? s.day,
    time_slot: s.time_slot ?? s.slot,
    is_active: s.is_active,
  }));
  const calDateSchedules = details?.date_schedules || [];

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

        {/* 캘린더 — 의료진 상세 진료시간표와 동일한 컴포넌트 */}
        <div style={{ padding: '0 20px 8px' }}>
          {loading && (
            <div style={{
              fontSize: 11, color: 'var(--t3)', marginBottom: 8, textAlign: 'center',
            }}>진료시간표를 불러오는 중…</div>
          )}
          <ScheduleCalendar
            key={initialDate || 'today'}
            compact
            schedules={calSchedules}
            dateSchedules={calDateSchedules}
            selected={selected}
            onSelect={setSelected}
            initialMonth={initialMonth}
          />
        </div>

        {/* 선택 안내 */}
        <div style={{
          margin: '12px 20px 16px', padding: 12, borderRadius: 10,
          background: selectedClosed || (selectedHoliday && !selectedOverride?.hasOpen) ? '#fee2e2'
                     : (!selectedAvailableByWeekly && !selectedOverride?.hasOpen ? '#fef3c7' : 'var(--ac-d)'),
          border: `1px solid ${selectedClosed ? '#fca5a5'
                              : selectedHoliday && !selectedOverride?.hasOpen ? '#fca5a5'
                              : (!selectedAvailableByWeekly && !selectedOverride?.hasOpen ? '#fcd34d' : 'var(--ac)')}`,
          color: selectedClosed ? '#7f1d1d'
               : selectedHoliday && !selectedOverride?.hasOpen ? '#7f1d1d'
               : (!selectedAvailableByWeekly && !selectedOverride?.hasOpen ? '#78350f' : 'var(--ac)'),
        }}>
          <div style={{ fontSize: 13, fontWeight: 700 }}>
            {formatLong(selected)}
          </div>
          <div style={{ fontSize: 11, marginTop: 3, opacity: .9 }}>
            {selectedClosed || (selectedHoliday && !selectedOverride?.hasOpen)
              ? '이 날은 휴진입니다. 다른 날짜를 선택하거나 강행할 수 있어요.'
              : selectedOverride?.hasOpen
                ? '이 날 특이일정이 있습니다. 진료시간표 참고에서 확인하세요.'
                : selectedAvailableByWeekly
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
