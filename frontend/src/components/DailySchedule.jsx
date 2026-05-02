import { useMemo, useState } from 'react';
import { CheckCircle, Trash2, ChevronLeft, ChevronRight, RotateCcw, BookOpen, MapPin, Megaphone } from 'lucide-react';

const DOW_KO = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];
const DOW_SHORT = ['일', '월', '화', '수', '목', '금', '토'];

const STATUS_THEME = {
  성공: { label: 'COMPLETED', c: '#166534', bg: '#dcfce7', accent: '#16a34a' },
  부재: { label: 'MISSED',    c: '#6b7280', bg: '#f3f4f6', accent: '#9ca3af' },
  거절: { label: 'DECLINED',  c: '#b91c1c', bg: '#fee2e2', accent: '#ef4444' },
  예정: { label: 'UPCOMING',  c: '#0369a1', bg: '#e0f2fe', accent: '#0284c7' },
};

function ymd(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function startOfWeek(dateStr) {
  // 월요일 기준 (MON=0)
  const d = new Date(dateStr + 'T00:00:00');
  const day = d.getDay(); // 0(일) ~ 6(토)
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d;
}

function addDays(dateStr, delta) {
  const d = new Date(dateStr + 'T00:00:00');
  d.setDate(d.getDate() + delta);
  return ymd(d.getFullYear(), d.getMonth(), d.getDate());
}

function diffDays(a, b) {
  const da = new Date(a + 'T00:00:00');
  const db = new Date(b + 'T00:00:00');
  return Math.round((da - db) / 86400000);
}

function hhmm(visitDate) {
  if (!visitDate) return '';
  const d = new Date(visitDate);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/**
 * Daily Schedule — 오늘(또는 선택한 날짜)의 일정표를 hh:mm 세로 타임라인으로 표시.
 * 상단에 큰 날짜 타이틀 + 주간 스트립.
 */
export default function DailySchedule({
  dateStr,
  todayStr,
  visits = [],            // VisitLog[]
  events = [],            // AcademicEvent[] — 해당 날짜에 진행되는 학회/심포지엄
  onSelectDate,
  onComplete,
  onCancel,
  onOpenDetail,           // 카드 본문 클릭 → 상세 모달
  onOpenAcademic,         // 학회 카드 클릭 → 학회 상세 모달
  onOpenMonth,            // "전체 일정 확인" 버튼
}) {
  const dateObj = dateStr ? new Date(dateStr + 'T00:00:00') : new Date();

  // ─ 주간 스트립: 7일 롤링 윈도우. 화살표로 하루씩 이동. ─
  const initialStart = () => {
    const s = startOfWeek(dateStr);
    return ymd(s.getFullYear(), s.getMonth(), s.getDate());
  };
  const [stripStart, setStripStart] = useState(initialStart);
  const [prevDateStr, setPrevDateStr] = useState(dateStr);

  // dateStr이 외부에서 바뀌어 현재 윈도우 밖이 된 경우에만 재정렬
  // (화살표 이동으로는 절대 자동 재정렬 하지 않음)
  if (dateStr !== prevDateStr) {
    setPrevDateStr(dateStr);
    const delta = diffDays(dateStr, stripStart);
    if (delta < 0 || delta > 6) {
      const s = startOfWeek(dateStr);
      setStripStart(ymd(s.getFullYear(), s.getMonth(), s.getDate()));
    }
  }

  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(stripStart, i)),
    [stripStart]
  );

  const shiftStrip = (delta) => setStripStart(s => addDays(s, delta));

  // ─ 공지사항은 학회처럼 상단 고정. 타임라인에서는 제외 ─
  const announcements = useMemo(
    () => visits.filter(v => v.category === 'announcement'),
    [visits]
  );
  const timelineVisits = useMemo(
    () => visits.filter(v => v.category !== 'announcement'),
    [visits]
  );

  // ─ 타임라인 항목(공지 제외 visits)을 시각 순 정렬 ─
  const items = useMemo(() => {
    return timelineVisits.map(v => ({
      id: `v-${v.id}`,
      time: hhmm(v.visit_date) || '09:00',
      minutes: v.visit_date
        ? new Date(v.visit_date).getHours() * 60 + new Date(v.visit_date).getMinutes()
        : 0,
      visit: v,
    })).sort((a, b) => a.minutes - b.minutes);
  }, [timelineVisits]);

  // ─ NEXT UP: 지금 시각 이후 첫 예정 visit ─
  const nextUpId = useMemo(() => {
    if (dateStr !== todayStr) return null;
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const candidates = items.filter(it =>
      it.visit.status === '예정' && it.minutes >= nowMin
    );
    return candidates[0]?.id || null;
  }, [items, dateStr, todayStr]);

  const count = items.length + events.length + announcements.length;
  const completedCount = timelineVisits.filter(v => v.status === '성공').length;
  const plannedCount = timelineVisits.filter(v => v.status === '예정').length;

  return (
    <div>
      {/* ── 상단 고정 영역: 날짜 타이틀 + 주간 스트립 + 통계 bar ── */}
      <div style={{
        position: 'sticky', top: 56, zIndex: 5,
        background: 'var(--bg-0)',
        margin: '0 -6px',
        padding: '0 6px',
      }}>
      {/* ── 날짜 타이틀 헤더 ── */}
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        padding: '12px 4px 14px', gap: 12,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: 'Manrope', fontSize: 30, fontWeight: 800,
            color: 'var(--t1)', lineHeight: 1, letterSpacing: '-.02em',
          }}>
            {DOW_KO[dateObj.getDay()]}
          </div>
          <div style={{
            fontSize: 12, color: 'var(--t3)', fontWeight: 600,
            marginTop: 6, letterSpacing: '.04em',
          }}>
            {dateObj.getFullYear()}. {dateObj.getMonth() + 1}. {dateObj.getDate()}
            {count > 0 && <> · 일정 {count}건</>}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {dateStr !== todayStr && (
            <button
              onClick={() => onSelectDate?.(todayStr)}
              aria-label="오늘로 이동"
              title="오늘로 이동"
              style={{
                width: 28, height: 28, borderRadius: '50%',
                background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
                color: 'var(--t3)', cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'color .15s, border-color .15s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.color = 'var(--ac)';
                e.currentTarget.style.borderColor = 'var(--ac)';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.color = 'var(--t3)';
                e.currentTarget.style.borderColor = 'var(--bd-s)';
              }}
            >
              <RotateCcw size={13} />
            </button>
          )}
          <button
            onClick={onOpenMonth}
            style={{
              padding: '9px 14px', borderRadius: 10,
              background: 'var(--ac-d)', color: 'var(--ac)',
              border: '1px solid var(--ac)',
              fontSize: 12, fontWeight: 700, cursor: 'pointer',
              fontFamily: 'inherit', whiteSpace: 'nowrap',
              display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            📅 전체 일정
          </button>
        </div>
      </div>

      {/* ── 주간 스트립 (7일 롤링 윈도우 + 좌우 이동) ── */}
      <div style={{
        display: 'flex', alignItems: 'stretch', gap: 6, padding: '2px 2px 14px',
      }}>
        <button
          onClick={() => shiftStrip(-1)}
          aria-label="하루 이전"
          style={{
            width: 30, borderRadius: 10,
            background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
            color: 'var(--t3)', cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <ChevronLeft size={16} />
        </button>
        <div style={{
          flex: 1, display: 'flex', gap: 6, overflowX: 'auto',
        }}>
        {weekDays.map(d => {
          const obj = new Date(d + 'T00:00:00');
          const isSelected = d === dateStr;
          const isToday = d === todayStr;
          const dow = obj.getDay(); // 0=일, 6=토
          const weekendColor = dow === 0 ? 'var(--rd)' : dow === 6 ? 'var(--bl)' : null;
          const textColor = isSelected ? '#fff' : (weekendColor || 'var(--t1)');
          return (
            <button
              key={d}
              onClick={() => onSelectDate?.(d)}
              style={{
                flex: 1, minWidth: 48, padding: '10px 4px',
                borderRadius: 12, cursor: 'pointer',
                fontFamily: 'inherit',
                background: isSelected ? 'var(--ac)' : 'var(--bg-1)',
                color: textColor,
                border: `1px solid ${isSelected ? 'var(--ac)' : 'var(--bd-s)'}`,
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                transition: 'background .15s',
              }}
            >
              <span style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '.05em',
                opacity: isSelected ? .85 : .6,
              }}>
                {DOW_SHORT[obj.getDay()]}
              </span>
              <span style={{
                fontFamily: 'Manrope', fontSize: 18, fontWeight: 800, lineHeight: 1,
              }}>
                {obj.getDate()}
              </span>
              {isToday && !isSelected && (
                <span style={{
                  width: 4, height: 4, borderRadius: '50%',
                  background: 'var(--ac)', marginTop: 1,
                }} />
              )}
            </button>
          );
        })}
        </div>
        <button
          onClick={() => shiftStrip(1)}
          aria-label="하루 이후"
          style={{
            width: 30, borderRadius: 10,
            background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
            color: 'var(--t3)', cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {/* ── 통계 bar ── */}
      {(plannedCount > 0 || completedCount > 0) && (
        <div style={{
          display: 'flex', gap: 8, padding: '0 2px 12px',
          fontSize: 11, color: 'var(--t3)',
        }}>
          {completedCount > 0 && (
            <span style={{
              padding: '4px 9px', borderRadius: 6,
              background: '#dcfce7', color: '#166534', fontWeight: 700,
            }}>
              완료 {completedCount}
            </span>
          )}
          {plannedCount > 0 && (
            <span style={{
              padding: '4px 9px', borderRadius: 6,
              background: '#e0f2fe', color: '#0369a1', fontWeight: 700,
            }}>
              예정 {plannedCount}
            </span>
          )}
          {events.length > 0 && (
            <span style={{
              padding: '4px 9px', borderRadius: 6,
              background: '#ede9fe', color: '#7c3aed', fontWeight: 700,
            }}>
              학회 {events.length}
            </span>
          )}
        </div>
      )}
      </div>

      {/* ── 업무공지 섹션 ── */}
      {announcements.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
          {announcements.map(an => (
            <button
              key={an.id}
              onClick={() => onOpenDetail?.(an)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px', borderRadius: 10,
                background: '#fffbeb',
                border: '1px solid #fde68a',
                cursor: 'pointer', fontFamily: 'inherit',
                textAlign: 'left',
                transition: 'transform .12s, box-shadow .12s',
                scrollSnapAlign: 'start',
                scrollMarginTop: 180,
              }}
              onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = '0 4px 10px rgba(245,158,11,.15)'; }}
              onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = 'none'; }}
            >
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: '#fef3c7', color: '#b45309',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <Megaphone size={15} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2,
                }}>
                  <span style={{
                    padding: '1px 6px', borderRadius: 4,
                    fontSize: 9, fontWeight: 800, letterSpacing: '.05em',
                    background: '#fef3c7', color: '#b45309',
                    fontFamily: 'Manrope', flexShrink: 0,
                  }}>공지</span>
                  <span style={{
                    fontSize: 13, fontWeight: 700, color: 'var(--t1)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {an.title || '업무공지'}
                  </span>
                </div>
                {an.notes && (
                  <div style={{
                    fontSize: 11, color: 'var(--t3)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {an.notes}
                  </div>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* ── 학회 섹션 ── */}
      {events.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
          {events.map(ev => (
            <button
              key={ev.id}
              onClick={() => onOpenAcademic?.(ev)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px', borderRadius: 10,
                background: '#faf5ff',
                border: '1px solid #e9d5ff',
                cursor: 'pointer', fontFamily: 'inherit',
                textAlign: 'left',
                transition: 'transform .12s, box-shadow .12s',
                scrollSnapAlign: 'start',
                scrollMarginTop: 180,
              }}
              onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = '0 4px 10px rgba(124,58,237,.12)'; }}
              onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = 'none'; }}
            >
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: '#ede9fe', color: '#7c3aed',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <BookOpen size={15} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2,
                }}>
                  <span style={{
                    padding: '1px 6px', borderRadius: 4,
                    fontSize: 9, fontWeight: 800, letterSpacing: '.05em',
                    background: '#ede9fe', color: '#7c3aed',
                    fontFamily: 'Manrope', flexShrink: 0,
                  }}>학회</span>
                  <span style={{
                    fontSize: 13, fontWeight: 700, color: 'var(--t1)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {ev.name}
                  </span>
                </div>
                {(ev.location || ev.organizer_name) && (
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    fontSize: 11, color: 'var(--t3)',
                  }}>
                    {ev.location && <MapPin size={10} />}
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {ev.location || ev.organizer_name}
                    </span>
                  </div>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* ── 세로 타임라인 ── */}
      {items.length === 0 && events.length === 0 && announcements.length === 0 ? (
        <div style={{
          padding: '60px 20px', textAlign: 'center',
          color: 'var(--t3)', fontSize: 13,
          background: 'var(--bg-1)', borderRadius: 14,
          border: '1px dashed var(--bd-s)',
        }}>
          이 날은 일정이 없습니다.
          <div style={{ fontSize: 11, marginTop: 6 }}>아래 + 버튼으로 일정을 추가하세요.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {items.map(item => (
            <TimelineRow
              key={item.id}
              item={item}
              isNextUp={item.id === nextUpId}
              onComplete={onComplete}
              onCancel={onCancel}
              onOpenDetail={onOpenDetail}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function TimelineRow({ item, isNextUp, onComplete, onCancel, onOpenDetail }) {
  const theme = STATUS_THEME[item.visit.status] || STATUS_THEME.예정;
  const accent = isNextUp ? '#0369a1' : theme.accent;

  return (
    <div style={{
      display: 'flex', gap: 12, alignItems: 'stretch', minHeight: 76,
      scrollSnapAlign: 'start',
      scrollMarginTop: 180,
    }}>
      {/* 좌측 시각 + 점 */}
      <div style={{
        width: 48, display: 'flex', flexDirection: 'column',
        alignItems: 'center', paddingTop: 14,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11, fontWeight: 700, color: 'var(--t2)',
          marginBottom: 4,
        }}>
          {item.time}
        </div>
        <div style={{
          width: 14, height: 14, borderRadius: '50%',
          background: '#fff',
          border: `3px solid ${accent}`,
          flexShrink: 0,
          boxShadow: isNextUp ? `0 0 0 4px ${accent}22` : 'none',
        }} />
        <div style={{
          flex: 1, width: 2, background: 'var(--bg-h)', marginTop: 4,
        }} />
      </div>

      {/* 우측 카드 */}
      <div style={{ flex: 1, paddingBottom: 10 }}>
        <VisitCard
          visit={item.visit}
          theme={theme}
          isNextUp={isNextUp}
          onComplete={onComplete}
          onCancel={onCancel}
          onOpenDetail={onOpenDetail}
        />
      </div>
    </div>
  );
}

function VisitCard({ visit, theme, isNextUp, onComplete, onCancel, onOpenDetail }) {
  const isPlanned = visit.status === '예정';
  const isAnnouncement = visit.category === 'announcement';
  const isPersonal = visit.category === 'personal' || (!visit.doctor_name && !isAnnouncement);
  const cardBorder = isAnnouncement
    ? '#fde68a'
    : (isNextUp ? theme.accent : 'var(--bd-s)');
  const cardBg = isAnnouncement ? '#fffbeb' : 'var(--bg-1)';
  const badgeLabel = isAnnouncement
    ? 'NOTICE'
    : (isPersonal ? '업무' : (isNextUp ? 'NEXT UP' : theme.label));
  const badgeBg = isAnnouncement
    ? '#fef3c7'
    : (isPersonal ? 'var(--ac-d)' : (isNextUp ? '#0369a1' : theme.bg));
  const badgeColor = isAnnouncement
    ? '#b45309'
    : (isPersonal ? 'var(--ac)' : (isNextUp ? '#fff' : theme.c));
  return (
    <div
      onClick={() => onOpenDetail?.(visit)}
      style={{
        padding: '12px 14px', borderRadius: 12,
        background: cardBg,
        border: `1px solid ${cardBorder}`,
        boxShadow: isNextUp ? `0 4px 14px ${theme.accent}22` : '0 1px 4px rgba(0,0,0,.03)',
        cursor: 'pointer',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span style={{
          padding: '2px 7px', borderRadius: 5,
          fontSize: 9, fontWeight: 800, letterSpacing: '.05em',
          background: badgeBg,
          color: badgeColor,
          fontFamily: "'Manrope'",
        }}>
          {badgeLabel}
        </span>
        {!isPersonal && !isAnnouncement && isNextUp && <span style={{ fontSize: 10, color: '#b91c1c', fontWeight: 700 }}>곧 시작</span>}
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--t1)', marginBottom: 3 }}>
        {isAnnouncement
          ? (visit.title || '업무공지')
          : (isPersonal ? (visit.title || '내 일정') : visit.doctor_name)}
      </div>
      {!isPersonal && (
        <div style={{ fontSize: 11, color: 'var(--t3)' }}>
          {visit.hospital_name} · {visit.department}
        </div>
      )}
      {visit.product && (
        <div style={{
          display: 'inline-block', marginTop: 6,
          fontSize: 11, color: theme.c, fontWeight: 700,
        }}>
          🏷 {visit.product}
        </div>
      )}
      {(() => {
        const aiDiscussion = visit.ai_summary?.summary?.['논의내용'];
        const display = (aiDiscussion && String(aiDiscussion).trim()) || visit.notes;
        if (!display) return null;
        return (
          <div style={{
            fontSize: 11, color: 'var(--t2)', marginTop: 4, lineHeight: 1.45,
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
      {isPlanned && !isPersonal && !isAnnouncement && (
        <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
          <button
            onClick={(e) => { e.stopPropagation(); onComplete?.(visit); }}
            style={{
              flex: 1, padding: '8px 10px', borderRadius: 8,
              background: 'var(--ac)', color: '#fff', border: 'none',
              fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
            }}
          >
            <CheckCircle size={13} />
            방문결과메모
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onCancel?.(visit); }}
            style={{
              padding: '8px 10px', borderRadius: 8,
              background: 'var(--bg-2)', color: 'var(--rd)',
              border: '1px solid var(--bd-s)', cursor: 'pointer',
            }}
          >
            <Trash2 size={12} />
          </button>
        </div>
      )}
    </div>
  );
}

