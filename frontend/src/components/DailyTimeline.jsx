import { Clock, MapPin, CheckCircle, XCircle, AlertTriangle, Plus, Trash2 } from 'lucide-react';

const SLOT_LABEL = { morning: '오전', afternoon: '오후', evening: '야간' };
const SLOT_RANGES = {
  morning: { label: '오전', range: '09:00 – 12:00', sort: 0 },
  afternoon: { label: '오후', range: '13:00 – 17:00', sort: 1 },
  evening: { label: '야간', range: '18:00 – 21:00', sort: 2 },
};

const GC = {
  A: { c: '#ba1a1a', bg: '#ffdad6' },
  B: { c: '#b45309', bg: '#fef3c7' },
  C: { c: '#0056d2', bg: '#dae2ff' },
};
const STATUS_COLOR = {
  성공: { c: '#166534', bg: '#dcfce7' },
  부재: { c: '#6b7280', bg: '#f3f4f6' },
  거절: { c: '#b91c1c', bg: '#fee2e2' },
  예정: { c: '#0369a1', bg: '#e0f2fe' },
};

function hourOf(visitDate) {
  if (!visitDate) return -1;
  const d = new Date(visitDate);
  return d.getHours();
}
function slotOfVisit(visit) {
  const h = hourOf(visit.visit_date);
  if (h < 0) return 'morning';
  if (h < 12) return 'morning';
  if (h < 18) return 'afternoon';
  return 'evening';
}

/**
 * 당일 데일리 타임라인.
 * - 오전/오후/야간 섹션 분할
 * - 각 섹션에 진료 교수 카드 + 방문 기록 카드 렌더
 */
export default function DailyTimeline({
  dateStr,
  doctors = [],        // [{doctor, slots, location}]
  visits = [],         // visit_log[]
  overdueSet = new Set(),
  overdueDoctors = [],
  onQuickPlan,         // (doctorId, dateStr, slot)
  onComplete,          // (visit)
  onCancel,            // (visit)
}) {
  const visitedDoctorIds = new Set(visits.map(v => v.doctor_id));

  const sections = ['morning', 'afternoon', 'evening'].map(slot => {
    const sectionDoctors = doctors.filter(d => d.slots.includes(slot));
    const sectionVisits = visits.filter(v => slotOfVisit(v) === slot);
    return { slot, doctors: sectionDoctors, visits: sectionVisits };
  }).filter(s => s.doctors.length > 0 || s.visits.length > 0);

  const dateObj = dateStr ? new Date(dateStr + 'T00:00:00') : null;
  const dow = dateObj ? ['일', '월', '화', '수', '목', '금', '토'][dateObj.getDay()] : '';
  const totalDoctors = doctors.length;
  const plannedCount = visits.filter(v => v.status === '예정').length;
  const completedCount = visits.filter(v => v.status !== '예정').length;

  return (
    <div>
      {/* 날짜 헤더 */}
      <div style={{
        display: 'flex', alignItems: 'baseline', gap: 12, padding: '8px 4px 16px',
      }}>
        <div style={{
          fontFamily: 'Manrope', fontSize: 32, fontWeight: 800, color: 'var(--t1)', lineHeight: 1,
        }}>{dateObj?.getDate()}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)' }}>{dow}요일</div>
          <div style={{ fontSize: 11, color: 'var(--t3)' }}>
            {totalDoctors > 0 && <span>교수 {totalDoctors}명 · </span>}
            {plannedCount > 0 && <span style={{ color: '#0369a1' }}>예정 {plannedCount}건</span>}
            {plannedCount > 0 && completedCount > 0 && <span> · </span>}
            {completedCount > 0 && <span style={{ color: '#166534' }}>완료 {completedCount}건</span>}
            {totalDoctors === 0 && plannedCount === 0 && completedCount === 0 && <span>일정 없음</span>}
          </div>
        </div>
      </div>

      {/* 타임라인 */}
      {sections.length === 0 ? (
        <div style={{
          padding: '50px 20px', textAlign: 'center',
          color: 'var(--t3)', fontSize: 13,
          background: 'var(--bg-1)', borderRadius: 14, border: '1px dashed var(--bd-s)',
        }}>
          이 날은 일정이 없습니다.
          <div style={{ fontSize: 11, marginTop: 6, color: 'var(--t3)' }}>아래 + 버튼으로 방문 예정을 추가하세요.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {sections.map(sec => (
            <Section
              key={sec.slot}
              slot={sec.slot}
              doctors={sec.doctors}
              visits={sec.visits}
              visitedDoctorIds={visitedDoctorIds}
              overdueSet={overdueSet}
              overdueDoctors={overdueDoctors}
              dateStr={dateStr}
              onQuickPlan={onQuickPlan}
              onComplete={onComplete}
              onCancel={onCancel}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Section({ slot, doctors, visits, visitedDoctorIds, overdueSet, overdueDoctors, dateStr, onQuickPlan, onComplete, onCancel }) {
  const meta = SLOT_RANGES[slot];
  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, padding: '0 2px',
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: slot === 'morning' ? '#f59e0b' : slot === 'afternoon' ? '#3b82f6' : '#7c3aed',
        }} />
        <div style={{ fontFamily: 'Manrope', fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>{meta.label}</div>
        <div style={{ fontSize: 11, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>{meta.range}</div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingLeft: 16, borderLeft: '2px solid var(--bg-h)' }}>
        {/* 방문 기록 카드 먼저 */}
        {visits.map(v => (
          <VisitCard key={v.id} visit={v} onComplete={onComplete} onCancel={onCancel} />
        ))}

        {/* 진료 교수 카드 */}
        {doctors.map(({ doctor, slots, location }) => {
          const already = visitedDoctorIds.has(doctor.id);
          if (already) return null; // 이미 방문 기록이 있으면 숨김 (중복 방지)
          const isOverdue = overdueSet.has(doctor.id);
          const overdueInfo = overdueDoctors.find(o => o.doctor.id === doctor.id);
          const gc = GC[doctor.visit_grade] || GC.B;
          return (
            <div key={doctor.id} style={{
              padding: '10px 12px', borderRadius: 10,
              background: 'var(--bg-1)',
              border: `1px solid ${isOverdue ? '#fecaca' : 'var(--bd-s)'}`,
              display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>{doctor.name}</div>
                  {doctor.visit_grade && (
                    <span style={{
                      padding: '1px 5px', borderRadius: 4, fontSize: 9, fontWeight: 700,
                      fontFamily: "'JetBrains Mono'", background: gc.bg, color: gc.c,
                    }}>{doctor.visit_grade}</span>
                  )}
                  {isOverdue && (
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: 2,
                      padding: '1px 5px', borderRadius: 4,
                      fontSize: 9, fontWeight: 700, background: '#fee2e2', color: '#b91c1c',
                    }}>
                      <AlertTriangle size={9} />
                      {overdueInfo?.daysSince != null ? `${overdueInfo.daysSince}일` : '미방문'}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: 'var(--t3)' }}>
                  {doctor.hospital_name} · {doctor.department}
                  {location && <> · <MapPin size={9} style={{ display: 'inline', verticalAlign: -1 }} /> {location}</>}
                </div>
              </div>
              <button
                onClick={() => onQuickPlan?.(doctor.id, dateStr, slot)}
                title="방문 예정 추가"
                style={{
                  width: 28, height: 28, borderRadius: 7,
                  background: 'var(--ac)', color: '#fff', border: 'none',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}
              ><Plus size={14} /></button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VisitCard({ visit, onComplete, onCancel }) {
  const color = STATUS_COLOR[visit.status] || STATUS_COLOR.예정;
  const isPlanned = visit.status === '예정';
  return (
    <div style={{
      padding: '10px 12px', borderRadius: 10,
      background: color.bg,
      border: `1px solid ${color.bg}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {visit.status === '성공' ? <CheckCircle size={12} style={{ color: color.c }} /> :
           visit.status === '예정' ? <Clock size={12} style={{ color: color.c }} /> :
           <XCircle size={12} style={{ color: color.c }} />}
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>{visit.doctor_name}</div>
          <span style={{
            padding: '1px 6px', borderRadius: 4, fontSize: 9, fontWeight: 700,
            background: '#fff', color: color.c,
          }}>{visit.status}</span>
        </div>
      </div>
      <div style={{ fontSize: 11, color: 'var(--t2)' }}>
        {visit.hospital_name} · {visit.department}
      </div>
      {visit.product && (
        <div style={{ fontSize: 11, color: color.c, marginTop: 3, fontWeight: 600 }}>{visit.product}</div>
      )}
      {visit.notes && (
        <div style={{ fontSize: 11, color: 'var(--t2)', marginTop: 3, lineHeight: 1.4 }}>{visit.notes}</div>
      )}
      {isPlanned && (
        <div style={{ display: 'flex', gap: 5, marginTop: 8 }}>
          <button onClick={() => onComplete?.(visit)} style={{
            flex: 1, padding: '6px 10px', borderRadius: 6,
            background: 'var(--ac)', color: '#fff', border: 'none',
            fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
          }}>완료 처리</button>
          <button onClick={() => onCancel?.(visit)} style={{
            padding: '6px 8px', borderRadius: 6,
            background: '#fff', color: 'var(--rd)', border: '1px solid var(--bd-s)',
            cursor: 'pointer', display: 'flex', alignItems: 'center',
          }}><Trash2 size={11} /></button>
        </div>
      )}
    </div>
  );
}
