import { useEffect, useState } from 'react';
import { X, Info, AlertCircle, Clock, GraduationCap, Calendar, Edit3 } from 'lucide-react';
import { academicApi } from '../api/client';

const DOW_LABELS = ['월', '화', '수', '목', '금', '토', '일'];
const FULL_DOW_LABELS = ['월', '화', '수', '목', '금', '토', '일'];
const SLOT_LABELS = { morning: '오전', afternoon: '오후', evening: '야간' };

/**
 * 교수 진료시간표 힌트 팝업.
 * 교수 선택 후 "이 교수의 진료시간을 참고하세요" 를 보여주고
 * [확인하고 시간 선택] 으로 다음 단계(SelectMeetingTime)로 진입.
 */
export default function DoctorScheduleHintPopup({ open, doctor, selectedDate, onClose, onConfirm }) {
  const [conferences, setConferences] = useState([]);

  // 선택 날짜 기준 해당 주(월~일)의 교수 참여 학회 로드
  useEffect(() => {
    if (!open || !doctor?.id || !selectedDate) {
      setConferences([]);
      return;
    }
    const { start, end } = weekRangeFor(selectedDate);
    let cancelled = false;
    academicApi.eventsForDoctor(doctor.id, start, end)
      .then(list => { if (!cancelled) setConferences(Array.isArray(list) ? list : []); })
      .catch(() => { if (!cancelled) setConferences([]); });
    return () => { cancelled = true; };
  }, [open, doctor?.id, selectedDate]);

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
  const lecturerConferences = conferences.filter(c => c.matched_as === 'lecturer');
  const departmentConferences = conferences.filter(c => c.matched_as === 'department');

  // 선택 날짜 기반 진료 여부 판단 (0=월 ~ 6=일)
  const selDow = selectedDate
    ? (new Date(selectedDate + 'T00:00:00').getDay() + 6) % 7
    : null;
  const hasScheduleOnSelDow = selDow != null &&
    Object.keys(matrix[selDow] || {}).length > 0;
  const overridesOnSelDate = (doctor.date_schedules || [])
    .filter(ds => ds.schedule_date === selectedDate);
  const hasOpenOverride = overridesOnSelDate.some(ov => ov.status && ov.status !== '휴진');
  const hasClosedOverride = overridesOnSelDate.length > 0 &&
    overridesOnSelDate.every(ov => ov.status === '휴진');
  const showNoClinicWarning = !!selectedDate && (
    hasClosedOverride ||
    (overridesOnSelDate.length === 0 && !hasScheduleOnSelDow)
  );

  return (
    <div
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

        {/* 선택한 방문일 */}
        {selectedDate && (
          <div style={{
            marginTop: 10, padding: '12px 14px', borderRadius: 12,
            background: showNoClinicWarning ? '#fef3c7' : 'var(--ac-d)',
            border: `1px solid ${showNoClinicWarning ? '#fcd34d' : 'var(--ac)'}`,
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: 9,
              background: showNoClinicWarning ? '#fde68a' : 'var(--bg-1)',
              color: showNoClinicWarning ? '#78350f' : 'var(--ac)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <Calendar size={17} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '.04em',
                color: showNoClinicWarning ? '#92400e' : 'var(--ac)',
                textTransform: 'uppercase', marginBottom: 2,
              }}>
                선택한 방문일
              </div>
              <div style={{
                fontFamily: 'Manrope', fontSize: 15, fontWeight: 800,
                color: showNoClinicWarning ? '#78350f' : 'var(--t1)',
              }}>
                {formatSelDateLong(selectedDate)}
              </div>
            </div>
            <button onClick={onClose} style={{
              flexShrink: 0,
              padding: '7px 11px', borderRadius: 8,
              background: 'var(--bg-1)',
              border: `1px solid ${showNoClinicWarning ? '#fcd34d' : 'var(--ac)'}`,
              color: showNoClinicWarning ? '#92400e' : 'var(--ac)',
              fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
              display: 'inline-flex', alignItems: 'center', gap: 4,
            }}>
              <Edit3 size={11} /> 변경
            </button>
          </div>
        )}

        {/* 선택 날짜 진료 없음 경고 */}
        {showNoClinicWarning && (
          <div style={{
            marginTop: 14, padding: '12px 14px', borderRadius: 10,
            background: '#fee2e2', border: '1px solid #fca5a5',
            display: 'flex', gap: 10, alignItems: 'flex-start',
          }}>
            <AlertCircle size={16} style={{ color: '#b91c1c', flexShrink: 0, marginTop: 1 }} />
            <div style={{ flex: 1, fontSize: 12, color: '#7f1d1d', lineHeight: 1.55 }}>
              <div style={{ fontWeight: 800, marginBottom: 3, fontFamily: 'Manrope' }}>
                {formatSelDateShort(selectedDate)} ({DOW_LABELS[selDow]}) 진료 없음
              </div>
              <div style={{ opacity: .9 }}>
                이 날은 해당 교수의 정규 진료일이 아닙니다.
                다른 루트로 일정이 잡혔다면 그대로 진행해도 됩니다.
              </div>
            </div>
          </div>
        )}

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
                  {DOW_LABELS.map((d, dowIdx) => {
                    const isSel = dowIdx === selDow;
                    return (
                      <th key={d} style={{
                        ...thStyle,
                        background: isSel
                          ? (showNoClinicWarning ? '#fee2e2' : 'var(--ac-d)')
                          : thStyle.background,
                        color: isSel
                          ? (showNoClinicWarning ? '#b91c1c' : 'var(--ac)')
                          : thStyle.color,
                        outline: isSel ? '2px solid' : 'none',
                        outlineColor: isSel
                          ? (showNoClinicWarning ? '#fca5a5' : 'var(--ac)')
                          : 'transparent',
                        outlineOffset: -2,
                      }}>{d}</th>
                    );
                  })}
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
                      const isSel = dowIdx === selDow;
                      const selBg = showNoClinicWarning ? '#fee2e2' : 'var(--ac-d)';
                      return (
                        <td key={dowIdx} style={{
                          ...tdStyle,
                          background: cell
                            ? (isSel ? 'var(--ac)' : 'var(--ac-d)')
                            : (isSel ? selBg : 'var(--bg-1)'),
                          color: cell
                            ? (isSel ? '#fff' : 'var(--ac)')
                            : (isSel && showNoClinicWarning ? '#b91c1c' : 'var(--t3)'),
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

        {/* 이번 주 관련 학회 */}
        {conferences.length > 0 && (
          <div style={{
            marginTop: 14, padding: '12px 14px', borderRadius: 10,
            background: 'var(--ac-d)', border: '1px solid var(--ac)',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
              color: 'var(--ac)', fontSize: 12, fontWeight: 800, fontFamily: 'Manrope',
            }}>
              <GraduationCap size={14} />
              이번 주 교수 관련 학회
            </div>
            {lecturerConferences.length > 0 && (
              <ConferenceGroup
                title={`강사 참여 ${lecturerConferences.length}건`}
                tone="strong"
                events={lecturerConferences}
                limit={3}
              />
            )}
            {departmentConferences.length > 0 && (
              <ConferenceGroup
                title={`진료과 관련 ${departmentConferences.length}건`}
                tone="muted"
                events={departmentConferences}
                limit={lecturerConferences.length > 0 ? 3 : 4}
              />
            )}
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

function ConferenceGroup({ title, tone, events, limit }) {
  const visible = events.slice(0, limit);
  const strong = tone === 'strong';
  return (
    <div style={{ marginTop: strong ? 0 : 10 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        margin: strong ? '0 0 5px' : '0 0 5px',
        fontSize: 10, fontWeight: 800,
        color: strong ? 'var(--ac)' : 'var(--t3)',
        letterSpacing: '.02em',
      }}>
        <span style={{
          width: 6, height: 6, borderRadius: '50%',
          background: strong ? 'var(--ac)' : 'var(--t3)',
          opacity: strong ? 1 : .65,
        }} />
        {title}
      </div>
      {visible.map(c => (
        <div key={`${tone}-${c.id}`} style={{
          fontSize: 11, color: 'var(--t1)', lineHeight: 1.55,
          display: 'flex', gap: 6, alignItems: 'baseline',
          padding: '2px 0',
        }}>
          <span style={{
            fontFamily: "'JetBrains Mono'", color: strong ? 'var(--ac)' : 'var(--t3)',
            flexShrink: 0, minWidth: 34,
          }}>
            {formatMD(c.start_date)}
          </span>
          <span style={{ flex: 1 }}>
            {c.name}
          </span>
          <span style={{
            flexShrink: 0, fontSize: 10, fontWeight: 800,
            color: strong ? 'var(--ac)' : 'var(--t3)',
          }}>
            {strong ? '강사' : '진료과'}
          </span>
        </div>
      ))}
      {events.length > limit && (
        <div style={{
          fontSize: 10, color: 'var(--t3)',
          marginTop: 2, opacity: .8,
          paddingLeft: 40,
        }}>
          외 {events.length - limit}건
        </div>
      )}
    </div>
  );
}

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

function formatSelDateShort(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr + 'T00:00:00');
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

function formatSelDateLong(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr + 'T00:00:00');
  // 0=일 ~ 6=토
  const dow = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${dow})`;
}

function formatMD(dateStr) {
  if (!dateStr) return '';
  const s = String(dateStr).slice(0, 10);
  const parts = s.split('-');
  if (parts.length !== 3) return s;
  return `${Number(parts[1])}/${Number(parts[2])}`;
}

function weekRangeFor(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const dow = (d.getDay() + 6) % 7; // 0=월 ~ 6=일
  const mon = new Date(d);
  mon.setDate(d.getDate() - dow);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  const ymd = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
  return { start: ymd(mon), end: ymd(sun) };
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
