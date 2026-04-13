import { useMemo, useCallback } from 'react';
import { dashboardApi, visitApi } from '../api/client';
import { useCachedApi } from './useCachedApi';
import { invalidate } from '../api/cache';

const SLOT_ORDER = { morning: 0, afternoon: 1, evening: 2 };
const GRADE_CYCLE_DAYS = { A: 7, B: 14, C: 30 };
const GRADE_MONTHLY_TARGET = { A: 4, B: 2, C: 1 };

function ymd(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function daysBetween(a, b) {
  return Math.floor((a.getTime() - b.getTime()) / (1000 * 60 * 60 * 24));
}

/**
 * 월간 캘린더용 데이터 + 파생 집계 + 액션을 묶은 공용 훅.
 * Dashboard / Schedule 양쪽에서 사용.
 */
export function useMonthCalendar(year, month) {
  const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;

  const { data: dashData, loading: dashLoading, refresh: refreshDash } =
    useCachedApi('dashboard', dashboardApi.summary, { ttlKey: 'doctors' });

  const { data: monthVisits, refresh: refreshVisits } = useCachedApi(
    `my-visits:${monthKey}`,
    () => dashboardApi.myVisits(year, month + 1),
    { ttlKey: 'doctors', deps: [monthKey] },
  );

  const doctors = dashData?.doctors || [];
  const visits = monthVisits || [];
  const today = new Date();

  const visitsByDate = useMemo(() => {
    const map = {};
    visits.forEach(v => {
      const date = (v.visit_date || '').slice(0, 10);
      if (!date) return;
      (map[date] ||= []).push(v);
    });
    return map;
  }, [visits]);

  const doctorsByDate = useMemo(() => {
    const map = {};
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = ymd(year, month, d);
      const dow = (new Date(year, month, d).getDay() + 6) % 7;
      const items = [];
      doctors.forEach(doc => {
        const overrides = (doc.date_schedules || []).filter(ds => ds.schedule_date === dateStr);
        if (overrides.length > 0) {
          overrides.forEach(ov => {
            if (ov.status === '휴진') return;
            items.push({ doctor: doc, slot: ov.time_slot, location: ov.location });
          });
        } else {
          (doc.schedules || []).filter(s => s.day_of_week === dow).forEach(s => {
            items.push({ doctor: doc, slot: s.time_slot, location: s.location });
          });
        }
      });
      const uniq = new Map();
      items.forEach(it => {
        const cur = uniq.get(it.doctor.id);
        if (!cur) {
          uniq.set(it.doctor.id, { doctor: it.doctor, slots: [it.slot], location: it.location });
        } else if (!cur.slots.includes(it.slot)) {
          cur.slots.push(it.slot);
        }
      });
      map[dateStr] = Array.from(uniq.values()).sort((a, b) =>
        (SLOT_ORDER[a.slots[0]] ?? 9) - (SLOT_ORDER[b.slots[0]] ?? 9)
      );
    }
    return map;
  }, [doctors, year, month]);

  const overdueDoctors = useMemo(() => {
    const result = [];
    doctors.forEach(doc => {
      const cycle = GRADE_CYCLE_DAYS[doc.visit_grade];
      if (!cycle) return;
      const last = doc.last_visit_date ? new Date(doc.last_visit_date) : null;
      const daysSince = last ? daysBetween(today, last) : Infinity;
      if (daysSince >= cycle) {
        result.push({ doctor: doc, daysSince: last ? daysSince : null });
      }
    });
    return result;
  }, [doctors]);

  const overdueSet = useMemo(
    () => new Set(overdueDoctors.map(o => o.doctor.id)),
    [overdueDoctors]
  );

  const monthStats = useMemo(() => {
    let completed = 0, planned = 0;
    visits.forEach(v => {
      if (v.status === '예정') planned++;
      else if (['성공', '부재', '거절'].includes(v.status)) completed++;
    });
    const succeeded = visits.filter(v => v.status === '성공').length;
    const target = doctors.reduce((acc, d) => acc + (GRADE_MONTHLY_TARGET[d.visit_grade] || 0), 0);
    return { completed, planned, succeeded, target, overdueCount: overdueDoctors.length };
  }, [visits, doctors, overdueDoctors]);

  const refresh = useCallback(() => {
    invalidate('my-visits');
    invalidate('dashboard');
    refreshDash();
    refreshVisits();
  }, [refreshDash, refreshVisits]);

  const addPlanned = useCallback(async (doctorId, dateStr, slot = 'morning', opts = {}) => {
    const { timeHHMM, notes } = opts;
    const time = timeHHMM
      ? `${timeHHMM}:00`
      : slot === 'afternoon' ? '13:00:00'
      : slot === 'evening'   ? '18:00:00'
      :                        '09:00:00';
    const dt = new Date(`${dateStr}T${time}`).toISOString();
    const payload = { doctor_id: doctorId, visit_date: dt, status: '예정' };
    if (notes) payload.notes = notes;
    await visitApi.create(doctorId, payload);
    refresh();
  }, [refresh]);

  const updateVisit = useCallback(async (visit, patch) => {
    await visitApi.update(visit.doctor_id, visit.id, patch);
    refresh();
  }, [refresh]);

  const cancelPlanned = useCallback(async (visit) => {
    await visitApi.remove(visit.doctor_id, visit.id);
    refresh();
  }, [refresh]);

  return {
    doctors,
    visits,
    visitsByDate,
    doctorsByDate,
    overdueSet,
    overdueDoctors,
    monthStats,
    loading: dashLoading && !dashData,
    refresh,
    actions: { addPlanned, updateVisit, cancelPlanned },
  };
}

export { ymd, SLOT_ORDER, GRADE_CYCLE_DAYS, GRADE_MONTHLY_TARGET };
