import { useMemo, useState } from 'react';
import {
  ChevronLeft, ChevronRight, X, BookOpen,
  Briefcase, GraduationCap, Trash2, CheckCircle, ListFilter, Pin,
} from 'lucide-react';
import { academicApi } from '../api/client';
import { invalidate } from '../api/cache';
import { useCachedApi } from '../hooks/useCachedApi';
import { useMonthCalendar } from '../hooks/useMonthCalendar';
import VisitDetailModal from '../components/VisitDetailModal';
import AcademicEventDetailModal from '../components/AcademicEventDetailModal';

const DOW_KO = ['일', '월', '화', '수', '목', '금', '토'];
const STATUS_THEME = {
  성공: { label: '완료', c: '#166534', bg: '#dcfce7' },
  부재: { label: '부재', c: '#6b7280', bg: '#f3f4f6' },
  거절: { label: '거절', c: '#b91c1c', bg: '#fee2e2' },
  예정: { label: '예정', c: '#0369a1', bg: '#e0f2fe' },
};

function ymd(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function hhmm(dt) {
  if (!dt) return '';
  const s = String(dt);
  const m = s.match(/T(\d{2}):(\d{2})/);
  if (!m) return '';
  return `${m[1]}:${m[2]}`;
}

function buildWeeks(year, month, daysInMonth) {
  // 주: 월요일 시작. 월 내에서 해당 주가 차지하는 [start, end] 일 반환.
  const weeks = [];
  let cursor = 1;
  while (cursor <= daysInMonth) {
    // 이 날짜의 주 시작(월요일) 찾기 — 1일 이전으로는 넘어가지 않음
    const dowMon0 = (new Date(year, month, cursor).getDay() + 6) % 7; // 0=월..6=일
    const start = Math.max(1, cursor - dowMon0);
    // 주 끝(일요일)
    const end = Math.min(daysInMonth, start + 6);
    weeks.push({ start, end });
    cursor = end + 1;
  }
  return weeks;
}

export default function Schedule({ onNavigate }) {
  const now = new Date();
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() });
  const [completing, setCompleting] = useState(null);
  const [completeStatus, setCompleteStatus] = useState('');
  const [completeProduct, setCompleteProduct] = useState('');
  const [completeNotes, setCompleteNotes] = useState('');
  const [filter, setFilter] = useState({ visit: true, personal: true, academic: true });
  const [onlyWithEvents, setOnlyWithEvents] = useState(false);
  const [detailVisit, setDetailVisit] = useState(null);
  const [detailEvent, setDetailEvent] = useState(null);

  const { year, month } = view;
  const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const { visitsByDate, loading, actions } = useMonthCalendar(year, month);

  // Schedule 은 "내 일정" 페이지 — 수동 추가(source='manual') + 핀(is_pinned)된 KMA 학회 합집합.
  // 전체 학회 브라우징은 Conferences 페이지(#/conferences) 쪽에서.
  const { data: monthEvents } = useCachedApi(
    `academic-my-schedule:${monthKey}`,
    () => academicApi.mySchedule({
      start_date: ymd(year, month, 1),
      end_date: ymd(year, month, daysInMonth),
    }),
    { ttlKey: 'academic', deps: [monthKey] },
  );
  const events = monthEvents || [];
  const todayStr = now.toISOString().slice(0, 10);
  const today = new Date(todayStr + 'T00:00:00');
  const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

  const prevMonth = () => setView(v => v.month === 0 ? { year: v.year - 1, month: 11 } : { ...v, month: v.month - 1 });
  const nextMonth = () => setView(v => v.month === 11 ? { year: v.year + 1, month: 0 } : { ...v, month: v.month + 1 });
  const goToday = () => {
    const t = new Date();
    setView({ year: t.getFullYear(), month: t.getMonth() });
    setTimeout(() => {
      const el = document.getElementById(`day-${t.getDate()}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 50);
  };

  const eventsByDate = useMemo(() => {
    const map = {};
    events.forEach(e => {
      if (!e.start_date) return;
      (map[e.start_date] ||= []).push(e);
    });
    return map;
  }, [events]);

  const weeks = useMemo(() => buildWeeks(year, month, daysInMonth), [year, month, daysInMonth]);

  // 다음 예정(오늘 이후 첫 예정) 식별 — 현재 월에서만
  const nextUpVisitId = useMemo(() => {
    if (!isCurrentMonth) return null;
    const todayDay = today.getDate();
    for (let d = todayDay; d <= daysInMonth; d++) {
      const list = (visitsByDate[ymd(year, month, d)] || [])
        .filter(v => v.status === '예정')
        .sort((a, b) => (a.visit_date || '').localeCompare(b.visit_date || ''));
      if (list.length) return list[0].id;
    }
    return null;
  }, [isCurrentMonth, visitsByDate, year, month, daysInMonth, today]);

  // ─── 완료 처리 모달 ───
  function openComplete(visit) {
    setCompleting(visit);
    setCompleteStatus('');
    setCompleteProduct(visit.product || '');
    setCompleteNotes(visit.post_notes || '');
  }

  async function submitComplete() {
    if (!completeStatus || !completing) return;
    try {
      await actions.updateVisit(completing, {
        status: completeStatus,
        product: completeProduct || null,
        post_notes: completeNotes || null,
      });
      setCompleting(null);
    } catch (e) { alert('저장 실패: ' + e.message); }
  }

  async function cancelPlanned(visit) {
    if (!confirm(`${visit.doctor_name || visit.title || '이 일정'} 을(를) 취소하시겠습니까?`)) return;
    try {
      await actions.cancelPlanned(visit);
    } catch (e) { alert('취소 실패: ' + e.message); }
  }

  // 주 스트립 스크롤 = 앵커 점프
  const scrollToDay = (d) => {
    const el = document.getElementById(`day-${d}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div style={{ maxWidth: 980, margin: '0 auto' }}>
      {/* ── Sticky: 뒤로가기 + 월 헤더 + 필터 + 주 스트립 (스크롤 시 상단 고정) ── */}
      <div style={{
        position: 'sticky', top: 56, zIndex: 5,
        background: 'var(--bg-0)', paddingTop: 6, paddingBottom: 10,
        marginBottom: 8,
      }}>
        {/* ── Back link ── */}
        <button
          onClick={() => onNavigate?.('dashboard')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '4px 8px 4px 4px', marginBottom: 8,
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--t2)', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
          }}
        >
          <ChevronLeft size={16} /> 내 일정
        </button>

        {/* ── Month Header ── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 14, flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontFamily: 'Manrope', fontSize: 28, fontWeight: 800, letterSpacing: '-.025em', lineHeight: 1 }}>
              {year}년 {month + 1}월
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button onClick={prevMonth} style={navBtn}><ChevronLeft size={16} /></button>
            <button onClick={goToday} style={{ ...navBtn, width: 'auto', padding: '0 12px', fontSize: 12, fontWeight: 600 }}>오늘</button>
            <button onClick={nextMonth} style={navBtn}><ChevronRight size={16} /></button>
          </div>
        </div>

        {/* ── Filter Bar ── */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          <FilterChip
            active={filter.visit}
            onClick={() => setFilter(f => ({ ...f, visit: !f.visit }))}
            icon={GraduationCap}
            label="내 의료진 방문"
            activeColor="#0369a1"
          />
          <FilterChip
            active={filter.personal}
            onClick={() => setFilter(f => ({ ...f, personal: !f.personal }))}
            icon={Briefcase}
            label="업무 일정"
            activeColor="#0040a1"
          />
          <FilterChip
            active={filter.academic}
            onClick={() => setFilter(f => ({ ...f, academic: !f.academic }))}
            icon={BookOpen}
            label="학회 일정"
            activeColor="#7c3aed"
          />
          <FilterChip
            active={onlyWithEvents}
            onClick={() => setOnlyWithEvents(v => !v)}
            icon={ListFilter}
            label="일정 있는 날만"
            activeColor="#0f766e"
          />
        </div>

        {/* ── Week Strip ── */}
        <div style={{
          display: 'flex', gap: 4, padding: 8,
          background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
          borderRadius: 12, overflowX: 'auto',
        }}>
          {weeks.map((w, i) => {
            const isCurrent = isCurrentMonth && today.getDate() >= w.start && today.getDate() <= w.end;
            return (
              <button
                key={i}
                onClick={() => scrollToDay(w.start)}
                style={{
                  flex: 1, minWidth: 80, padding: '10px 12px', borderRadius: 9,
                  background: isCurrent ? 'var(--ac)' : 'transparent',
                  color: isCurrent ? '#fff' : 'var(--t2)',
                  border: 'none', cursor: 'pointer',
                  display: 'flex', flexDirection: 'column', gap: 2,
                  fontFamily: 'inherit', textAlign: 'left',
                  transition: 'background .15s',
                }}
              >
                <div style={{
                  fontSize: 10, fontWeight: 700,
                  opacity: isCurrent ? .85 : .55,
                  letterSpacing: '.05em',
                }}>WEEK {i + 1}</div>
                <div style={{ fontFamily: 'Manrope', fontSize: 13, fontWeight: 700 }}>
                  {w.start}{w.start !== w.end ? ` – ${w.end}` : ''}일
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Agenda ── */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)' }}>로딩 중…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {Array.from({ length: daysInMonth }, (_, i) => i + 1).map((d) => (
            <DayRow
              key={d}
              year={year}
              month={month}
              day={d}
              isToday={isCurrentMonth && d === today.getDate()}
              visits={(visitsByDate[ymd(year, month, d)] || [])
                .slice().sort((a, b) => (a.visit_date || '').localeCompare(b.visit_date || ''))}
              events={eventsByDate[ymd(year, month, d)] || []}
              filter={filter}
              nextUpVisitId={nextUpVisitId}
              onComplete={openComplete}
              onCancel={cancelPlanned}
              onOpenVisitDetail={setDetailVisit}
              onOpenEventDetail={setDetailEvent}
              onlyWithEvents={onlyWithEvents}
            />
          ))}
        </div>
      )}

      {/* ── Complete Modal (기존 유지) ── */}
      {completing && (
        <div
          onClick={() => setCompleting(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{ background: 'var(--bg-1)', borderRadius: 14, padding: 22, width: 420, maxWidth: '90%' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <div style={{ fontFamily: 'Manrope', fontSize: 16, fontWeight: 700 }}>방문 완료 처리</div>
              <button onClick={() => setCompleting(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--t3)' }}><X size={16} /></button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--t3)', marginBottom: 14 }}>
              {completing.doctor_name} · {completing.department}
            </div>
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
            <label style={labelS}>결과 메모</label>
            <textarea
              value={completeNotes}
              onChange={e => setCompleteNotes(e.target.value)}
              rows={3}
              placeholder="핵심 대화 내용 (사전 메모는 보존됩니다)"
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

      {/* ── 상세 모달: 교수 방문 + 업무 (VisitLog 공용) ── */}
      <VisitDetailModal
        open={!!detailVisit}
        visit={detailVisit}
        onClose={() => setDetailVisit(null)}
        onSave={async (visit, patch) => { await actions.updateVisit(visit, patch); }}
        onCancelPlanned={async (visit) => {
          await actions.cancelPlanned(visit);
          setDetailVisit(null);
        }}
        onComplete={(visit) => { setDetailVisit(null); openComplete(visit); }}
      />

      {/* ── 상세 모달: 학회 ── */}
      <AcademicEventDetailModal
        open={!!detailEvent}
        event={detailEvent}
        onClose={() => setDetailEvent(null)}
        onDelete={async (ev) => {
          if (ev.source === 'manual') {
            await academicApi.delete(ev.id);
          } else {
            await academicApi.unpin(ev.id);
          }
          invalidate(`academic-my-schedule:${monthKey}`);
          invalidate('academic');
          setDetailEvent(null);
        }}
      />
    </div>
  );
}

// ─────── DayRow ───────
function DayRow({ year, month, day, isToday, visits, events, filter, nextUpVisitId, onComplete, onCancel, onOpenVisitDetail, onOpenEventDetail, onlyWithEvents }) {
  const dow = new Date(year, month, day).getDay(); // 0=일..6=토
  const isWeekend = dow === 0 || dow === 6;
  const dowColor = dow === 0 ? 'var(--rd)' : dow === 6 ? 'var(--bl)' : 'var(--t3)';
  const isMonday = dow === 1;

  // 필터 적용
  const shownEvents = filter.academic ? events : [];
  const shownVisits = visits.filter(v => {
    if (v.doctor_id) return filter.visit;
    return filter.personal; // 개인/업무 일정 (doctor_id 없음)
  });
  const hasContent = shownVisits.length > 0 || shownEvents.length > 0;
  const dim = isWeekend && !hasContent;

  // "일정 있는 날만" 토글 — 빈 날은 렌더 생략
  if (onlyWithEvents && !hasContent) return null;

  return (
    <>
      {isMonday && day !== 1 && (
        <div style={{ height: 1, background: 'var(--bd-s)', margin: '8px 0' }} />
      )}
      <div
        id={`day-${day}`}
        style={{
          display: 'grid', gridTemplateColumns: '110px 1fr', gap: 16,
          padding: '14px 0', minHeight: hasContent ? 'auto' : 64,
          background: isToday
            ? 'linear-gradient(90deg, var(--ac-d) 0%, var(--ac-d) 100px, transparent 100px)'
            : 'transparent',
          opacity: dim ? 0.55 : 1,
          borderRadius: 10,
        }}
      >
        {/* LEFT */}
        <div style={{
          paddingLeft: isToday ? 12 : 0,
          display: 'flex', flexDirection: 'column', gap: 2,
        }}>
          <div style={{
            fontSize: 10, fontWeight: 800, letterSpacing: '.1em',
            color: isToday ? 'var(--ac)' : dowColor,
          }}>
            {DOW_KO[dow]}요일
          </div>
          <div style={{
            fontFamily: 'Manrope', fontSize: 34, fontWeight: 800,
            lineHeight: 1, letterSpacing: '-.02em',
            color: isToday ? 'var(--ac)' : isWeekend ? dowColor : 'var(--t1)',
          }}>
            {day}
          </div>
          {isToday && (
            <div style={{
              fontSize: 10, fontWeight: 700, color: 'var(--ac)',
              marginTop: 4, letterSpacing: '.05em',
            }}>TODAY</div>
          )}
          {shownVisits.length > 0 && (
            <div style={{
              fontSize: 11, color: 'var(--t3)', marginTop: 6, fontWeight: 500,
            }}>
              {summarize(shownVisits)}
            </div>
          )}
        </div>

        {/* RIGHT */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingRight: 4, minWidth: 0 }}>
          {shownEvents.map(e => (
            <EventCard key={e.id} event={e} onOpen={onOpenEventDetail} />
          ))}
          {shownVisits.map(v => (
            v.doctor_id
              ? <VisitCard
                  key={v.id}
                  visit={v}
                  isNext={nextUpVisitId === v.id}
                  onComplete={onComplete}
                  onCancel={onCancel}
                  onOpen={onOpenVisitDetail}
                />
              : <PersonalCard
                  key={v.id}
                  visit={v}
                  onCancel={onCancel}
                  onOpen={onOpenVisitDetail}
                />
          ))}
          {!hasContent && (
            <div style={{ padding: '10px 0', fontSize: 12, color: 'var(--t3)', fontStyle: 'italic' }}>—</div>
          )}
        </div>
      </div>
    </>
  );
}

// ─────── Cards ───────
function VisitCard({ visit, isNext, onComplete, onCancel, onOpen }) {
  const theme = STATUS_THEME[visit.status] || STATUS_THEME.예정;
  const isPlanned = visit.status === '예정';
  const borderCol = isNext ? '#0284c7' : 'var(--bd-s)';
  const shadow = isNext ? '0 4px 14px #0284c722' : 'none';
  const time = hhmm(visit.visit_date);

  return (
    <div
      onClick={() => onOpen?.(visit)}
      style={{
        padding: '10px 12px', borderRadius: 10,
        background: 'var(--bg-1)', border: `1px solid ${borderCol}`,
        boxShadow: shadow, cursor: 'pointer',
        display: 'flex', alignItems: 'flex-start', gap: 12,
      }}
    >
      <div style={{
        fontFamily: "'JetBrains Mono', monospace", fontSize: 11, fontWeight: 700,
        color: isNext ? '#0369a1' : 'var(--t3)',
        minWidth: 42, paddingTop: 2,
      }}>{time}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>{visit.doctor_name}</div>
          <span style={{
            padding: '1px 6px', borderRadius: 4,
            fontSize: 9, fontWeight: 800, letterSpacing: '.05em', fontFamily: 'Manrope',
            background: isNext ? '#0369a1' : theme.bg,
            color: isNext ? '#fff' : theme.c,
          }}>
            {isNext ? 'NEXT UP' : theme.label}
          </span>
          {visit.product && (
            <span style={{ fontSize: 10, color: theme.c, fontWeight: 600 }}>{visit.product}</span>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--t3)' }}>
          {visit.hospital_name}{visit.department ? ` · ${visit.department}` : ''}
        </div>
        {(() => {
          const aiDiscussion = visit.ai_summary?.summary?.['논의내용'];
          const display = (aiDiscussion && String(aiDiscussion).trim()) || visit.notes;
          if (!display) return null;
          return (
            <div style={{
              fontSize: 11, color: 'var(--t2)', marginTop: 5, lineHeight: 1.45,
              padding: '6px 8px', background: 'var(--bg-2)', borderRadius: 6,
            }}>
              {aiDiscussion && (
                <span style={{
                  display: 'inline-block', marginRight: 5, padding: '1px 5px',
                  borderRadius: 3, fontSize: 9, fontWeight: 800,
                  background: 'var(--ac-d)', color: 'var(--ac)',
                  verticalAlign: 'middle',
                }}>AI</span>
              )}
              {display}
            </div>
          );
        })()}
        {isPlanned && (
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <button onClick={(e) => { e.stopPropagation(); onComplete(visit); }} style={{
              padding: '5px 10px', borderRadius: 6, background: 'var(--ac)',
              color: '#fff', border: 'none', fontSize: 11, fontWeight: 700,
              cursor: 'pointer', fontFamily: 'inherit',
              display: 'inline-flex', alignItems: 'center', gap: 4,
            }}>
              <CheckCircle size={11} /> 완료
            </button>
            <button onClick={(e) => { e.stopPropagation(); onCancel(visit); }} style={{
              padding: '5px 9px', borderRadius: 6, background: 'var(--bg-1)',
              color: 'var(--rd)', border: '1px solid var(--bd-s)',
              fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
              display: 'inline-flex', alignItems: 'center',
            }}><Trash2 size={11} /></button>
          </div>
        )}
      </div>
    </div>
  );
}

function PersonalCard({ visit, onCancel, onOpen }) {
  const isAnnouncement = visit.category === 'announcement';
  const time = hhmm(visit.visit_date);
  const isPlanned = visit.status === '예정';
  const badgeLabel = isAnnouncement ? '공지' : '업무';
  const badgeBg = isAnnouncement ? '#fef3c7' : 'var(--ac-d)';
  const badgeColor = isAnnouncement ? '#b45309' : 'var(--ac)';
  const borderCol = isAnnouncement ? '#fde68a' : 'var(--bd-s)';
  const bgCol = isAnnouncement ? '#fffbeb' : 'var(--bg-1)';
  return (
    <div
      onClick={() => onOpen?.(visit)}
      style={{
        padding: '10px 12px', borderRadius: 10,
        background: bgCol, border: `1px solid ${borderCol}`,
        cursor: 'pointer',
        display: 'flex', alignItems: 'flex-start', gap: 12,
      }}
    >
      <div style={{
        fontFamily: "'JetBrains Mono', monospace", fontSize: 11, fontWeight: 700,
        color: 'var(--t3)', minWidth: 42, paddingTop: 2,
      }}>{isAnnouncement ? '공지' : time}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>
            {visit.title || (isAnnouncement ? '업무공지' : '업무 일정')}
          </div>
          <span style={{
            padding: '1px 6px', borderRadius: 4,
            fontSize: 9, fontWeight: 800, letterSpacing: '.05em', fontFamily: 'Manrope',
            background: badgeBg, color: badgeColor,
          }}>{badgeLabel}</span>
        </div>
        {visit.notes && (
          <div style={{ fontSize: 11, color: 'var(--t2)', marginTop: 3, lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>
            {visit.notes}
          </div>
        )}
        {isPlanned && (
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <button onClick={(e) => { e.stopPropagation(); onCancel(visit); }} style={{
              padding: '4px 8px', borderRadius: 6, background: 'var(--bg-1)',
              color: 'var(--rd)', border: '1px solid var(--bd-s)',
              fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
              display: 'inline-flex', alignItems: 'center', gap: 4,
            }}><Trash2 size={10} /> 삭제</button>
          </div>
        )}
      </div>
    </div>
  );
}

function EventCard({ event, onOpen }) {
  const matchedCount = event.matched_doctor_count || 0;
  const isPinnedKma = event.source === 'kma_edu' && event.is_pinned;
  return (
    <div
      onClick={() => onOpen?.(event)}
      style={{
        padding: '10px 12px', borderRadius: 10,
        background: '#faf5ff', border: '1px solid #e9d5ff',
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', gap: 10,
      }}
    >
      <BookOpen size={14} style={{ color: '#7c3aed', flexShrink: 0 }} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--t1)' }}>{event.name}</div>
          {matchedCount > 0 && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 3,
              padding: '1px 6px', borderRadius: 10, fontSize: 9, fontWeight: 800,
              background: '#e0e7ff', color: '#3730a3',
              letterSpacing: '.02em', fontFamily: 'Manrope',
            }}>
              <GraduationCap size={9} /> 내 의료진 {matchedCount}명
            </span>
          )}
        </div>
        {(event.location || event.organizer_name) && (
          <div style={{ fontSize: 10, color: 'var(--t3)', marginTop: 2 }}>
            {[event.organizer_name, event.location].filter(Boolean).join(' · ')}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 4, flexShrink: 0, alignItems: 'center' }}>
        {isPinnedKma && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 2,
            padding: '2px 6px', borderRadius: 4, fontSize: 9, fontWeight: 800,
            background: '#fef3c7', color: '#b45309',
            letterSpacing: '.05em', fontFamily: 'Manrope',
          }}>
            <Pin size={9} /> 연수교육
          </span>
        )}
        <span style={{
          padding: '2px 7px', borderRadius: 4, fontSize: 9, fontWeight: 800,
          background: '#ede9fe', color: '#7c3aed',
          letterSpacing: '.05em', fontFamily: 'Manrope',
        }}>학회</span>
      </div>
    </div>
  );
}

// ─────── Helpers ───────
function summarize(visits) {
  const done = visits.filter(v => v.status === '성공').length;
  const planned = visits.filter(v => v.status === '예정').length;
  const issues = visits.filter(v => v.status === '부재' || v.status === '거절').length;
  const bits = [];
  if (done) bits.push(`완료 ${done}`);
  if (planned) bits.push(`예정 ${planned}`);
  if (issues) bits.push(`이슈 ${issues}`);
  return bits.join(' · ') || '';
}

function FilterChip({ active, onClick, icon: Icon, label, activeColor }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '7px 12px', borderRadius: 20,
        border: `1px solid ${active ? activeColor : 'var(--bd-s)'}`,
        background: active ? activeColor : 'var(--bg-1)',
        color: active ? '#fff' : 'var(--t3)',
        fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
        transition: 'all .15s',
      }}
    >
      <Icon size={13} />
      {label}
    </button>
  );
}

// ─────── Styles ───────
const navBtn = {
  width: 34, height: 34, borderRadius: 9,
  background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer', color: 'var(--t2)', fontFamily: 'inherit',
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
