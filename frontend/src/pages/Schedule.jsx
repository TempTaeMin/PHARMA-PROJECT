import { useMemo, useState } from 'react';
import {
  ChevronLeft, ChevronRight, CalendarDays, Plus, CheckCircle, XCircle,
  AlertTriangle, Clock, MapPin, BookOpen, Trash2, X,
} from 'lucide-react';
import { academicApi } from '../api/client';
import { useCachedApi } from '../hooks/useCachedApi';
import { useMonthCalendar } from '../hooks/useMonthCalendar';

const DOW_KO = ['월', '화', '수', '목', '금', '토', '일'];
const SLOT_LABEL = { morning: '오전', afternoon: '오후', evening: '야간' };
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

function ymd(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

export default function Schedule() {
  const now = new Date();
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [selected, setSelected] = useState(now.toISOString().slice(0, 10));
  const [completing, setCompleting] = useState(null); // visit object
  const [completeStatus, setCompleteStatus] = useState('');
  const [completeProduct, setCompleteProduct] = useState('');
  const [completeNotes, setCompleteNotes] = useState('');

  const { year, month } = view;
  const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;

  const {
    doctors, visits, visitsByDate, doctorsByDate,
    overdueSet, overdueDoctors, monthStats,
    loading, actions,
  } = useMonthCalendar(year, month);

  const { data: monthEvents } = useCachedApi(
    `academic-month:${monthKey}`,
    () => academicApi.list({ start_from: ymd(year, month, 1), start_to: ymd(year, month, 31), limit: 500 }),
    { ttlKey: 'academic', deps: [monthKey] },
  );
  const events = monthEvents || [];
  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);

  const prevMonth = () => setView(v => v.month === 0 ? { year: v.year - 1, month: 11 } : { ...v, month: v.month - 1 });
  const nextMonth = () => setView(v => v.month === 11 ? { year: v.year + 1, month: 0 } : { ...v, month: v.month + 1 });
  const goToday = () => {
    const t = new Date();
    setView({ year: t.getFullYear(), month: t.getMonth() });
    setSelected(t.toISOString().slice(0, 10));
  };

  const eventsByDate = useMemo(() => {
    const map = {};
    events.forEach(e => {
      if (!e.start_date) return;
      (map[e.start_date] ||= []).push(e);
    });
    return map;
  }, [events]);

  // 선택일
  const selectedDate = selected ? new Date(selected + 'T00:00:00') : null;
  const selectedVisits = (visitsByDate[selected] || []).slice().sort((a, b) => (a.visit_date || '').localeCompare(b.visit_date || ''));
  const selectedDoctors = doctorsByDate[selected] || [];
  const selectedEvents = eventsByDate[selected] || [];
  const visitedDoctorIds = new Set(selectedVisits.map(v => v.doctor_id));

  // 그 날 진료 교수 목록을 overdue 우선으로 정렬
  const rankedDoctors = selectedDoctors.slice().sort((a, b) => {
    const ao = overdueSet.has(a.doctor.id) ? 0 : 1;
    const bo = overdueSet.has(b.doctor.id) ? 0 : 1;
    if (ao !== bo) return ao - bo;
    return a.doctor.name.localeCompare(b.doctor.name);
  });

  // ───── 액션 ─────
  async function addPlanned(doctorId) {
    try {
      await actions.addPlanned(doctorId, selected, 'morning');
    } catch (e) { alert('추가 실패: ' + e.message); }
  }

  function openComplete(visit) {
    setCompleting(visit);
    setCompleteStatus('');
    setCompleteProduct(visit.product || '');
    setCompleteNotes(visit.notes || '');
  }

  async function submitComplete() {
    if (!completeStatus || !completing) return;
    try {
      await actions.updateVisit(completing, {
        status: completeStatus,
        product: completeProduct || null,
        notes: completeNotes || null,
      });
      setCompleting(null);
    } catch (e) { alert('저장 실패: ' + e.message); }
  }

  async function cancelPlanned(visit) {
    if (!confirm(`${visit.doctor_name} 예정을 취소하시겠습니까?`)) return;
    try {
      await actions.cancelPlanned(visit);
    } catch (e) { alert('취소 실패: ' + e.message); }
  }

  return (
    <div style={{ maxWidth: 1180, margin: '0 auto' }}>
      {/* ── Month Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontFamily: 'Manrope', fontSize: 22, fontWeight: 700, letterSpacing: '-.02em' }}>월간 방문 일정</div>
          <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 4 }}>내 교수 {doctors.length}명 · 이번 달 계획과 실적</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button onClick={prevMonth} style={navBtn}><ChevronLeft size={16} /></button>
          <div style={{ minWidth: 130, textAlign: 'center', fontFamily: 'Manrope', fontSize: 16, fontWeight: 700 }}>
            {year}년 {month + 1}월
          </div>
          <button onClick={nextMonth} style={navBtn}><ChevronRight size={16} /></button>
          <button onClick={goToday} style={{ ...navBtn, width: 'auto', padding: '0 12px', fontSize: 12, fontWeight: 600 }}>오늘</button>
        </div>
      </div>

      {/* ── Stat Cards ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
        <StatCard label="완료" value={monthStats.completed} accent="#166534" bg="#dcfce7" />
        <StatCard label="예정" value={monthStats.planned} accent="#0369a1" bg="#e0f2fe" />
        <StatCard
          label="달성률"
          value={monthStats.target > 0 ? `${Math.round((monthStats.succeeded / monthStats.target) * 100)}%` : '—'}
          sub={`${monthStats.succeeded} / ${monthStats.target}`}
          accent="#7c3aed" bg="#ede9fe"
        />
        <StatCard
          label="미방문"
          value={monthStats.overdueCount}
          accent="#b91c1c" bg="#fee2e2"
          sub={monthStats.overdueCount > 0 ? '주기 초과' : '양호'}
        />
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)' }}>로딩 중…</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16, alignItems: 'start' }}>
          {/* ── Calendar ── */}
          <Calendar
            year={year}
            month={month}
            todayStr={todayStr}
            selected={selected}
            setSelected={setSelected}
            visitsByDate={visitsByDate}
            eventsByDate={eventsByDate}
            doctorsByDate={doctorsByDate}
            overdueSet={overdueSet}
          />

          {/* ── Side Panel ── */}
          <div style={{ position: 'sticky', top: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <SidePanel
              selectedDate={selectedDate}
              visits={selectedVisits}
              doctors={rankedDoctors}
              events={selectedEvents}
              visitedDoctorIds={visitedDoctorIds}
              overdueSet={overdueSet}
              overdueDoctors={overdueDoctors}
              onAddPlanned={addPlanned}
              onComplete={openComplete}
              onCancel={cancelPlanned}
            />
          </div>
        </div>
      )}

      {/* ── Complete Modal ── */}
      {completing && (
        <div
          onClick={() => setCompleting(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{ background: 'var(--bg-1)', borderRadius: 14, padding: 22, width: 420, maxWidth: '90%', animation: 'fadeUp .2s ease' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <div style={{ fontFamily: 'Manrope', fontSize: 16, fontWeight: 700 }}>방문 완료 처리</div>
              <button onClick={() => setCompleting(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--t3)' }}><X size={16} /></button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--t3)', marginBottom: 14 }}>{completing.doctor_name} · {completing.department}</div>
            <label style={labelS}>결과</label>
            <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
              {['성공', '부재', '거절'].map(s => (
                <button key={s} onClick={() => setCompleteStatus(s)} style={{
                  flex: 1, padding: 10, borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 600,
                  fontFamily: 'inherit',
                  background: completeStatus === s ? 'var(--ac-d)' : 'var(--bg-2)',
                  color: completeStatus === s ? 'var(--ac)' : 'var(--t3)',
                  border: `1px solid ${completeStatus === s ? 'var(--ac)' : 'var(--bd-s)'}`,
                }}>{s}</button>
              ))}
            </div>
            <label style={labelS}>디테일링 제품</label>
            <input
              value={completeProduct}
              onChange={e => setCompleteProduct(e.target.value)}
              placeholder="예: 관절주사A"
              style={inputS}
            />
            <label style={labelS}>메모</label>
            <textarea
              value={completeNotes}
              onChange={e => setCompleteNotes(e.target.value)}
              rows={3}
              placeholder="핵심 대화 내용"
              style={{ ...inputS, resize: 'vertical' }}
            />
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14 }}>
              <button onClick={() => setCompleting(null)} style={btnGhost}>취소</button>
              <button onClick={submitComplete} disabled={!completeStatus} style={{ ...btnPrimary, opacity: completeStatus ? 1 : .5 }}>
                저장
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ───── Sub-components ─────

function StatCard({ label, value, sub, accent, bg }) {
  return (
    <div style={{ padding: 14, borderRadius: 12, background: bg, border: `1px solid ${bg}` }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: accent, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 800, color: accent, fontFamily: 'Manrope' }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: accent, opacity: .75, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function Calendar({ year, month, todayStr, selected, setSelected, visitsByDate, eventsByDate, doctorsByDate, overdueSet }) {
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDow = (new Date(year, month, 1).getDay() + 6) % 7;
  const cells = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  return (
    <div style={{ background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 16, padding: 12 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4, marginBottom: 6 }}>
        {DOW_KO.map((d, i) => (
          <div key={d} style={{
            padding: '6px 0', textAlign: 'center', fontSize: 11, fontWeight: 700,
            color: i === 6 ? 'var(--rd)' : i === 5 ? 'var(--bl)' : 'var(--t3)',
          }}>{d}</div>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4 }}>
        {cells.map((day, i) => {
          if (day === null) return <div key={`e${i}`} />;
          const dateStr = ymd(year, month, day);
          const visits = visitsByDate[dateStr] || [];
          const events = eventsByDate[dateStr] || [];
          const doctorsHere = doctorsByDate[dateStr] || [];
          const hasOverdue = doctorsHere.some(x => overdueSet.has(x.doctor.id));
          const completed = visits.filter(v => ['성공', '부재', '거절'].includes(v.status)).length;
          const succeeded = visits.filter(v => v.status === '성공').length;
          const planned = visits.filter(v => v.status === '예정').length;
          const isToday = dateStr === todayStr;
          const isSelected = dateStr === selected;
          const dow = (firstDow + day - 1) % 7;
          const isWeekend = dow >= 5;

          return (
            <button
              key={day}
              onClick={() => setSelected(dateStr)}
              style={{
                minHeight: 86, padding: 7, border: 'none', cursor: 'pointer',
                borderRadius: 10, fontFamily: 'inherit', textAlign: 'left',
                background: isSelected ? 'var(--ac)' : isToday ? 'var(--ac-d)' : 'var(--bg-2)',
                color: isSelected ? '#fff' : 'var(--t1)',
                outline: isToday && !isSelected ? '1px solid var(--ac)' : 'none',
                borderLeft: hasOverdue && !isSelected ? '3px solid #dc2626' : undefined,
                opacity: isWeekend && !isSelected && !isToday ? .65 : 1,
                display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
                transition: 'transform .1s, background .15s',
              }}
              onMouseEnter={e => { if (!isSelected) e.currentTarget.style.transform = 'translateY(-1px)'; }}
              onMouseLeave={e => { e.currentTarget.style.transform = 'none'; }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{
                  fontSize: 13, fontWeight: isToday || isSelected ? 700 : 500,
                  color: isSelected ? '#fff' : isToday ? 'var(--ac)' : dow === 6 ? 'var(--rd)' : dow === 5 ? 'var(--bl)' : 'var(--t1)',
                }}>{day}</span>
                {events.length > 0 && (
                  <span style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: isSelected ? '#fff' : '#a855f7',
                  }} title={`학회 ${events.length}건`} />
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {succeeded > 0 && (
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 3,
                    fontSize: 9, fontWeight: 700,
                    color: isSelected ? '#fff' : '#166534',
                  }}>
                    <CheckCircle size={9} /> {succeeded}
                  </span>
                )}
                {completed - succeeded > 0 && (
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 3,
                    fontSize: 9, fontWeight: 600,
                    color: isSelected ? 'rgba(255,255,255,.85)' : 'var(--t3)',
                  }}>
                    <XCircle size={9} /> {completed - succeeded}
                  </span>
                )}
                {planned > 0 && (
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 3,
                    fontSize: 9, fontWeight: 700,
                    color: isSelected ? '#fff' : '#0369a1',
                  }}>
                    <Clock size={9} /> {planned} 예정
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SidePanel({
  selectedDate, visits, doctors, events,
  visitedDoctorIds, overdueSet, overdueDoctors,
  onAddPlanned, onComplete, onCancel,
}) {
  if (!selectedDate) {
    return (
      <div style={panelBox}>
        <div style={{ textAlign: 'center', padding: 30, color: 'var(--t3)', fontSize: 12 }}>날짜를 선택하세요</div>
      </div>
    );
  }

  const dow = (selectedDate.getDay() + 6) % 7;

  return (
    <>
      {/* 헤더 */}
      <div style={panelBox}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <CalendarDays size={16} style={{ color: 'var(--ac)' }} />
          <div style={{ fontFamily: 'Manrope', fontSize: 15, fontWeight: 700 }}>
            {selectedDate.getMonth() + 1}월 {selectedDate.getDate()}일 ({DOW_KO[dow]})
          </div>
        </div>
      </div>

      {/* 방문 기록 */}
      <div style={panelBox}>
        <SectionTitle>방문 기록 {visits.length > 0 && <span style={count}>{visits.length}</span>}</SectionTitle>
        {visits.length === 0 ? (
          <Empty text="기록 없음" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {visits.map(v => (
              <VisitItem key={v.id} visit={v} onComplete={onComplete} onCancel={onCancel} />
            ))}
          </div>
        )}
      </div>

      {/* 그 날 진료하는 내 교수 */}
      <div style={panelBox}>
        <SectionTitle>
          진료 중인 내 교수 {doctors.length > 0 && <span style={count}>{doctors.length}</span>}
        </SectionTitle>
        {doctors.length === 0 ? (
          <Empty text="이 날 진료 교수가 없습니다" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 340, overflowY: 'auto' }}>
            {doctors.map(({ doctor, slots, location }) => {
              const already = visitedDoctorIds.has(doctor.id);
              const isOverdue = overdueSet.has(doctor.id);
              const overdueInfo = overdueDoctors.find(o => o.doctor.id === doctor.id);
              const gc = GC[doctor.visit_grade] || GC.B;
              return (
                <div key={doctor.id} style={{
                  padding: 10, borderRadius: 9, background: 'var(--bg-2)',
                  border: `1px solid ${isOverdue ? '#fecaca' : 'var(--bd-s)'}`,
                  opacity: already ? .5 : 1,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>{doctor.name}</div>
                      <span style={{
                        padding: '1px 5px', borderRadius: 4, fontSize: 9, fontWeight: 700,
                        fontFamily: "'JetBrains Mono'", background: gc.bg, color: gc.c,
                      }}>{doctor.visit_grade}</span>
                    </div>
                    {!already && (
                      <button
                        onClick={() => onAddPlanned(doctor.id)}
                        style={addBtn}
                        title="예정 추가"
                      ><Plus size={12} /></button>
                    )}
                    {already && <span style={{ fontSize: 10, color: 'var(--t3)' }}>기록됨</span>}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 4 }}>
                    {doctor.hospital_name} · {doctor.department}
                  </div>
                  <div style={{ display: 'flex', gap: 8, fontSize: 10, color: 'var(--t3)', flexWrap: 'wrap' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <Clock size={10} /> {slots.map(s => SLOT_LABEL[s] || s).join(', ')}
                    </span>
                    {location && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                        <MapPin size={10} /> {location}
                      </span>
                    )}
                  </div>
                  {isOverdue && (
                    <div style={{
                      marginTop: 5, display: 'inline-flex', alignItems: 'center', gap: 3,
                      padding: '2px 6px', borderRadius: 4,
                      fontSize: 9, fontWeight: 700, background: '#fee2e2', color: '#b91c1c',
                    }}>
                      <AlertTriangle size={9} />
                      {overdueInfo?.daysSince != null
                        ? `${overdueInfo.daysSince}일 미방문`
                        : '방문 이력 없음'}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 학회 */}
      {events.length > 0 && (
        <div style={panelBox}>
          <SectionTitle>학회 일정 <span style={count}>{events.length}</span></SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {events.map(e => (
              <div key={e.id} style={{
                padding: 10, borderRadius: 9, background: '#faf5ff',
                border: '1px solid #e9d5ff',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3 }}>
                  <BookOpen size={10} style={{ color: '#7c3aed' }} />
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--t1)' }}>{e.name}</div>
                </div>
                {e.organizer_name && (
                  <div style={{ fontSize: 10, color: 'var(--t3)' }}>{e.organizer_name}</div>
                )}
                {e.location && (
                  <div style={{ fontSize: 10, color: 'var(--t3)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 3 }}>
                    <MapPin size={9} /> {e.location}
                  </div>
                )}
                {e.url && (
                  <a href={e.url} target="_blank" rel="noopener noreferrer" style={{
                    display: 'inline-block', marginTop: 5, fontSize: 10, color: '#7c3aed', textDecoration: 'none',
                  }}>자세히 보기 →</a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function VisitItem({ visit, onComplete, onCancel }) {
  const color = STATUS_COLOR[visit.status] || STATUS_COLOR.예정;
  const isPlanned = visit.status === '예정';
  return (
    <div style={{
      padding: 10, borderRadius: 9, background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>{visit.doctor_name}</div>
        <span style={{
          padding: '2px 7px', borderRadius: 4, fontSize: 9, fontWeight: 700,
          background: color.bg, color: color.c,
        }}>{visit.status}</span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: isPlanned ? 6 : 0 }}>
        {visit.hospital_name} · {visit.department}
      </div>
      {visit.product && (
        <div style={{ fontSize: 11, color: 'var(--ac)', marginTop: 3 }}>{visit.product}</div>
      )}
      {visit.notes && (
        <div style={{ fontSize: 11, color: 'var(--t2)', marginTop: 3, lineHeight: 1.4 }}>{visit.notes}</div>
      )}
      {isPlanned && (
        <div style={{ display: 'flex', gap: 5, marginTop: 7 }}>
          <button onClick={() => onComplete(visit)} style={{
            flex: 1, padding: '5px 10px', borderRadius: 6, background: 'var(--ac)',
            color: '#fff', border: 'none', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
          }}>완료하기</button>
          <button onClick={() => onCancel(visit)} style={{
            padding: '5px 9px', borderRadius: 6, background: 'var(--bg-1)',
            color: 'var(--rd)', border: '1px solid var(--bd-s)',
            fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center',
          }}><Trash2 size={11} /></button>
        </div>
      )}
    </div>
  );
}

function SectionTitle({ children }) {
  return (
    <div style={{ fontFamily: 'Manrope', fontSize: 12, fontWeight: 700, color: 'var(--t2)', marginBottom: 10, letterSpacing: '.02em' }}>
      {children}
    </div>
  );
}

function Empty({ text }) {
  return <div style={{ padding: '16px 0', textAlign: 'center', color: 'var(--t3)', fontSize: 11 }}>{text}</div>;
}

// ───── Styles ─────
const navBtn = {
  width: 32, height: 32, borderRadius: 8,
  background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer', color: 'var(--t2)', fontFamily: 'inherit',
};
const panelBox = {
  background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 14, padding: 14,
};
const count = {
  padding: '1px 6px', borderRadius: 8, fontSize: 10, fontWeight: 700,
  background: 'var(--bg-2)', color: 'var(--t3)', fontFamily: "'JetBrains Mono'",
};
const addBtn = {
  width: 24, height: 24, borderRadius: 6, background: 'var(--ac)', color: '#fff',
  border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
};
const labelS = {
  display: 'block', fontSize: 11, color: 'var(--t3)', fontWeight: 600, marginBottom: 5,
};
const inputS = {
  width: '100%', padding: '9px 11px', borderRadius: 7, background: 'var(--bg-2)',
  border: '1px solid var(--bd)', color: 'var(--t1)', fontSize: 12, outline: 'none',
  fontFamily: 'inherit', marginBottom: 12, boxSizing: 'border-box',
};
const btnGhost = {
  padding: '8px 16px', borderRadius: 7, background: 'var(--bg-2)', color: 'var(--t2)',
  border: '1px solid var(--bd)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
};
const btnPrimary = {
  padding: '8px 16px', borderRadius: 7, background: 'var(--ac)', color: '#fff',
  border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
};
