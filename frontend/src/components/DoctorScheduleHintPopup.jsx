import { X, Info, AlertCircle, Clock } from 'lucide-react';

const DOW_LABELS = ['월', '화', '수', '목', '금', '토', '일'];
const SLOT_LABELS = { morning: '오전', afternoon: '오후', evening: '야간' };

/**
 * 교수 진료시간표 힌트 팝업.
 * 교수 선택 후 "이 교수의 진료시간을 참고하세요" 를 보여주고
 * [확인하고 시간 선택] 으로 다음 단계(SelectMeetingTime)로 진입.
 */
export default function DoctorScheduleHintPopup({ open, doctor, onClose, onConfirm }) {
  if (!open || !doctor) return null;

  // 요일 × 시간대 매트릭스 구성
  const matrix = buildMatrix(doctor.schedules || []);
  const recentOverrides = (doctor.date_schedules || []).filter(ds => {
    if (!ds.schedule_date) return false;
    const d = new Date(ds.schedule_date + 'T00:00:00');
    const today = new Date();
    const diff = (d.getTime() - today.getTime()) / (1000 * 60 * 60 * 24);
    return diff >= -1 && diff <= 14;
  });

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
        zIndex: 400, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20, animation: 'fadeIn .18s ease',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-1)', borderRadius: 18,
          padding: '22px 22px 20px', width: 460, maxWidth: '95%',
          maxHeight: '90vh', overflowY: 'auto',
          animation: 'fadeUp .22s ease',
        }}
      >
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'var(--ac-d)', color: 'var(--ac)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Info size={18} />
            </div>
            <div>
              <div style={{ fontFamily: 'Manrope', fontSize: 16, fontWeight: 800 }}>
                진료 시간표 참고
              </div>
              <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>
                방문 시간을 정하기 전에 확인해주세요
              </div>
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--t3)',
          }}><X size={18} /></button>
        </div>

        {/* 교수 정보 */}
        <div style={{
          marginTop: 16, padding: 14, borderRadius: 12,
          background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
        }}>
          <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--t1)' }}>
            {doctor.name} 교수
          </div>
          <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 3 }}>
            {doctor.hospital_name} · {doctor.department}
            {doctor.position ? ` · ${doctor.position}` : ''}
          </div>
        </div>

        {/* 매트릭스 */}
        <div style={{ marginTop: 16 }}>
          <div style={{
            fontSize: 11, fontWeight: 700, color: 'var(--t3)', marginBottom: 6,
            letterSpacing: '.04em',
          }}>
            주간 진료 시간
          </div>
          {hasAnySchedule(matrix) ? (
            <table style={{
              width: '100%', borderCollapse: 'separate', borderSpacing: 0,
              fontSize: 11, tableLayout: 'fixed',
            }}>
              <thead>
                <tr>
                  <th style={thStyle}></th>
                  {DOW_LABELS.map(d => (
                    <th key={d} style={thStyle}>{d}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {['morning', 'afternoon', 'evening'].map(slot => (
                  <tr key={slot}>
                    <td style={{
                      ...tdStyle, fontWeight: 700, color: 'var(--t2)',
                      background: 'var(--bg-2)',
                    }}>
                      {SLOT_LABELS[slot]}
                    </td>
                    {DOW_LABELS.map((_, dowIdx) => {
                      const cell = matrix[dowIdx]?.[slot];
                      return (
                        <td key={dowIdx} style={{
                          ...tdStyle,
                          background: cell ? 'var(--ac-d)' : 'var(--bg-1)',
                          color: cell ? 'var(--ac)' : 'var(--t3)',
                          fontWeight: cell ? 700 : 400,
                          fontFamily: cell ? "'JetBrains Mono'" : 'inherit',
                        }}>
                          {cell ? (cell.time || '○') : '-'}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{
              padding: '20px 14px', textAlign: 'center',
              fontSize: 12, color: 'var(--t3)',
              background: 'var(--bg-2)', borderRadius: 10,
              border: '1px dashed var(--bd-s)',
            }}>
              등록된 진료 시간표가 없습니다.
            </div>
          )}
        </div>

        {/* 최근 override 경고 */}
        {recentOverrides.length > 0 && (
          <div style={{
            marginTop: 14, padding: '10px 12px', borderRadius: 10,
            background: '#fef3c7', border: '1px solid #fcd34d',
            display: 'flex', gap: 8,
          }}>
            <AlertCircle size={14} style={{ color: '#b45309', flexShrink: 0, marginTop: 1 }} />
            <div style={{ flex: 1, fontSize: 11, color: '#78350f' }}>
              <div style={{ fontWeight: 700, marginBottom: 3 }}>최근 일정 변경</div>
              {recentOverrides.slice(0, 3).map((ov, i) => (
                <div key={i} style={{ lineHeight: 1.5 }}>
                  {formatOverride(ov)}
                </div>
              ))}
              {recentOverrides.length > 3 && (
                <div style={{ opacity: .7, marginTop: 2 }}>외 {recentOverrides.length - 3}건</div>
              )}
            </div>
          </div>
        )}

        {/* 공통 위치 캡션 */}
        {doctor.schedules?.[0]?.location && (
          <div style={{
            marginTop: 10, fontSize: 11, color: 'var(--t3)',
            display: 'flex', alignItems: 'center', gap: 4,
          }}>
            <Clock size={11} />
            주 진료실: {doctor.schedules[0].location}
          </div>
        )}

        {/* 액션 버튼 */}
        <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
          <button onClick={onClose} style={{
            flex: '0 0 auto', padding: '12px 18px', borderRadius: 10,
            background: 'var(--bg-2)', color: 'var(--t2)',
            border: '1px solid var(--bd-s)', cursor: 'pointer',
            fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
          }}>취소</button>
          <button onClick={onConfirm} style={{
            flex: 1, padding: '12px 18px', borderRadius: 10,
            background: 'var(--ac)', color: '#fff', border: 'none',
            cursor: 'pointer', fontSize: 13, fontWeight: 700,
            fontFamily: 'inherit',
          }}>확인하고 시간 선택</button>
        </div>
      </div>
    </div>
  );
}

// ──── Helpers ────

/**
 * DB의 day_of_week는 이미 0=월 ~ 6=일 기준 (kbsmc_crawler 등 참고).
 * 참고: useMonthCalendar.js:53 에서 `(getDay() + 6) % 7`로 계산 → 0=월, 6=일.
 */
function buildMatrix(schedules) {
  const m = Array.from({ length: 7 }, () => ({}));
  schedules.forEach(s => {
    const dow = s.day_of_week;
    if (dow == null || dow < 0 || dow > 6) return;
    const slot = s.time_slot || 'morning';
    const time = formatRange(s.start_time, s.end_time);
    m[dow][slot] = { time, location: s.location };
  });
  return m;
}

function formatRange(start, end) {
  if (!start && !end) return '';
  const s = (start || '').slice(0, 5);
  const e = (end || '').slice(0, 5);
  if (s && e) return `${s}-${e}`;
  return s || e || '';
}

function hasAnySchedule(matrix) {
  return matrix.some(dow => Object.keys(dow).length > 0);
}

function formatOverride(ov) {
  const date = (ov.schedule_date || '').slice(5).replace('-', '월 ') + '일';
  const slot = SLOT_LABELS[ov.time_slot] || '';
  const status = ov.status || '';
  return `${date} ${slot} ${status}`.trim();
}

const thStyle = {
  padding: '6px 4px', fontSize: 10,
  background: 'var(--bg-2)', color: 'var(--t3)', fontWeight: 700,
  border: '1px solid var(--bd-s)',
};
const tdStyle = {
  padding: '7px 2px', textAlign: 'center',
  border: '1px solid var(--bd-s)',
  fontSize: 10,
};
