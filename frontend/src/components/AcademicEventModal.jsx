import { useEffect, useState } from 'react';
import { X, Calendar, MapPin, BookOpen, Users, Hash, Tag, ExternalLink, Presentation, ChevronDown, ChevronUp, Pin, Share2, Landmark, GraduationCap } from 'lucide-react';
import { academicApi } from '../api/client';

const GRADE_COLORS = {
  A: { bg: '#fee2e2', c: '#b91c1c' },
  B: { bg: '#ffedd5', c: '#c2410c' },
  C: { bg: '#dbeafe', c: '#1d4ed8' },
};

const DEPT_COLORS = [
  { bg: '#dbeafe', c: '#1e40af' },
  { bg: '#dcfce7', c: '#166534' },
  { bg: '#fef3c7', c: '#92400e' },
  { bg: '#fce7f3', c: '#9f1239' },
  { bg: '#e0e7ff', c: '#3730a3' },
  { bg: '#ccfbf1', c: '#115e59' },
];

function deptColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff;
  return DEPT_COLORS[h % DEPT_COLORS.length];
}

function fmtDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${y}년 ${Number(m)}월 ${Number(d)}일`;
}

function fmtRange(start, end) {
  if (!start) return '';
  if (!end || start === end) return fmtDate(start);
  return `${fmtDate(start)} ~ ${fmtDate(end)}`;
}

export default function AcademicEventModal({ open, event, onClose, onNavigateDoctor, onUpdated, pickMode = false, onPicked }) {
  const [enriched, setEnriched] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [pinBusy, setPinBusy] = useState(false);
  const [isPinned, setIsPinned] = useState(false);

  useEffect(() => {
    if (!open || !event?.id) {
      setEnriched(null);
      setSessionsOpen(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setIsPinned(!!event.is_pinned);
    academicApi.getById(event.id)
      .then(data => {
        if (cancelled) return;
        setEnriched(data);
        setIsPinned(!!data.is_pinned);
      })
      .catch(err => { if (!cancelled) console.error('[AcademicEventModal] fetch failed', err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, event?.id, event?.is_pinned]);

  if (!open || !event) return null;

  const ev = enriched || event;
  const allLectures = Array.isArray(ev.lectures) ? ev.lectures : [];
  const matchedLectures = allLectures.filter(L => !!L.matched_doctor_id);
  const hasAnyLectures = allLectures.length > 0;
  const isManual = ev.source === 'manual';
  const manualUrl = isManual ? (ev.url || null) : null;
  const organizerHomepage = ev.organizer_homepage || null;

  async function handleTogglePin() {
    if (pinBusy) return;
    setPinBusy(true);
    try {
      if (isPinned) {
        if (pickMode) {
          onPicked?.();
          return;
        }
        if (!window.confirm('내 일정에서 제거할까요?')) {
          setPinBusy(false);
          return;
        }
        await academicApi.unpin(ev.id);
        setIsPinned(false);
        if (onUpdated) onUpdated();
      } else {
        await academicApi.pin(ev.id);
        setIsPinned(true);
        if (onUpdated) onUpdated();
        if (pickMode) {
          onPicked?.();
          return;
        }
      }
    } catch (err) {
      console.error('[AcademicEventModal] pin toggle failed', err);
      alert('처리에 실패했습니다');
    } finally {
      setPinBusy(false);
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
        zIndex: 380, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16, animation: 'fadeIn .18s ease',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-1)', borderRadius: 18,
          padding: '22px 24px 20px', width: 600, maxWidth: '100%',
          maxHeight: '92vh', overflowY: 'auto',
          animation: 'fadeUp .22s ease',
        }}
      >
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
              {isPinned && (
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 3,
                  padding: '3px 8px', borderRadius: 5,
                  fontSize: 10, fontWeight: 800, letterSpacing: '.05em',
                  background: '#fef3c7', color: '#b45309', fontFamily: 'Manrope',
                }}>
                  <Pin size={10} /> 내 일정
                </span>
              )}
            </div>
            <div style={{
              fontFamily: 'Manrope', fontSize: 19, fontWeight: 800,
              color: 'var(--t1)', lineHeight: 1.35,
            }}>
              {ev.name}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--t3)', flexShrink: 0,
          }}><X size={20} /></button>
        </div>

        {/* 내 의료진 강사진 — 최상단 */}
        {matchedLectures.length > 0 && (
          <div style={{
            marginBottom: 16, padding: '12px 14px', borderRadius: 12,
            background: 'var(--ac-d)', border: '1px solid var(--ac)',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10,
            }}>
              <GraduationCap size={14} style={{ color: 'var(--ac)' }} />
              <span style={{
                fontSize: 12, fontWeight: 800, color: 'var(--ac)', letterSpacing: '.02em',
              }}>내 의료진 강사진 · {matchedLectures.length}명</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {matchedLectures.map((L, i) => {
                const grade = L.matched_doctor_grade;
                const gcol = GRADE_COLORS[grade];
                return (
                  <div
                    key={i}
                    onClick={() => onNavigateDoctor && onNavigateDoctor(L.matched_doctor_id)}
                    style={{
                      padding: '10px 12px', borderRadius: 10,
                      background: 'var(--bg-1)',
                      border: '1px solid var(--ac)',
                      cursor: 'pointer',
                      transition: 'transform .12s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-1px)'}
                    onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}
                  >
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap',
                    }}>
                      {L.time && (
                        <span style={{
                          fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
                          fontWeight: 700, color: 'var(--t3)',
                          background: 'var(--bg-2)', padding: '2px 6px', borderRadius: 4,
                        }}>{L.time}</span>
                      )}
                      {L.title && (
                        <span style={{
                          fontSize: 12, fontWeight: 600, color: 'var(--t1)', lineHeight: 1.35,
                        }}>{L.title}</span>
                      )}
                    </div>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
                      fontSize: 11, color: 'var(--t2)',
                    }}>
                      <span style={{ fontWeight: 700, color: 'var(--ac)' }}>{L.lecturer}</span>
                      {L.affiliation && (
                        <span style={{ color: 'var(--t3)' }}>· {L.affiliation}</span>
                      )}
                      {gcol && (
                        <span style={{
                          padding: '2px 7px', borderRadius: 10, fontSize: 9, fontWeight: 800,
                          background: gcol.bg, color: gcol.c, letterSpacing: '.02em',
                          fontFamily: 'Manrope', marginLeft: 'auto',
                        }}>내 의료진 · {grade}</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 진료과 */}
        {ev.departments && ev.departments.length > 0 && (
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 14 }}>
            {ev.departments.map(d => {
              const col = deptColor(d);
              return (
                <span key={d} style={{
                  padding: '4px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700,
                  background: col.bg, color: col.c,
                }}>{d}</span>
              );
            })}
          </div>
        )}

        {/* 정보 리스트 */}
        <div style={{
          display: 'flex', flexDirection: 'column', gap: 0,
          borderTop: '1px solid var(--bd-s)',
        }}>
          <Row icon={<Calendar size={13} />} label="일정">
            {fmtRange(ev.start_date, ev.end_date)}
          </Row>
          {ev.location && (
            <Row icon={<MapPin size={13} />} label="장소">{ev.location}</Row>
          )}
          {ev.region && (
            <Row icon={<MapPin size={13} />} label="지역">{ev.region}</Row>
          )}
          {ev.organizer_name && (
            <Row icon={<BookOpen size={13} />} label="주최">{ev.organizer_name}</Row>
          )}
          {ev.sub_organizer && (
            <Row icon={<Users size={13} />} label="주관">{ev.sub_organizer}</Row>
          )}
          {ev.kma_category && (
            <Row icon={<Tag size={13} />} label="분야">{ev.kma_category}</Row>
          )}
          {ev.event_code && (
            <Row icon={<Hash size={13} />} label="교육코드">
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                {ev.event_code}
              </span>
            </Row>
          )}
        </div>

        {/* 전체 강연 세션 — 접기/펼치기 */}
        {hasAnyLectures && (
          <div style={{ marginTop: 16 }}>
            <button
              onClick={() => setSessionsOpen(v => !v)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                width: '100%', padding: '10px 12px',
                background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
                borderRadius: 10, cursor: 'pointer',
                fontSize: 12, fontWeight: 700, color: 'var(--t2)', fontFamily: 'inherit',
              }}
            >
              <Presentation size={13} />
              전체 세션 {allLectures.length}개 보기
              <span style={{ marginLeft: 'auto' }}>
                {sessionsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </span>
            </button>
            {sessionsOpen && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 8 }}>
                {allLectures.map((L, i) => (
                  <div key={i} style={{
                    padding: '8px 10px', borderRadius: 8,
                    background: L.matched_doctor_id ? 'var(--ac-d)' : 'var(--bg-2)',
                    border: '1px solid ' + (L.matched_doctor_id ? 'var(--ac)' : 'var(--bd-s)'),
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 2 }}>
                      {L.time && (
                        <span style={{
                          fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
                          fontWeight: 700, color: 'var(--t3)',
                          background: 'var(--bg-1)', padding: '2px 6px', borderRadius: 4,
                        }}>{L.time}</span>
                      )}
                      {L.title && (
                        <span style={{
                          fontSize: 12, fontWeight: 600, color: 'var(--t1)', lineHeight: 1.35,
                        }}>{L.title}</span>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--t3)' }}>
                      <span style={{ fontWeight: 600, color: L.matched_doctor_id ? 'var(--ac)' : 'var(--t2)' }}>
                        {L.lecturer}
                      </span>
                      {L.affiliation && <span> · {L.affiliation}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {loading && allLectures.length === 0 && (
          <div style={{ marginTop: 16, fontSize: 12, color: 'var(--t3)', textAlign: 'center' }}>
            강의 일정 불러오는 중…
          </div>
        )}

        {/* 하단 액션 행 */}
        <div style={{
          marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--bd-s)',
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          {/* 내 일정에 등록 — manual 이벤트는 이미 일정에 뜨므로 숨김.
              과거 학회는 신규 등록 차단(이미 등록된 학회는 해제 가능). */}
          {!isManual && (() => {
            const todayStr = new Date().toISOString().slice(0, 10);
            const isPastEvent = !!ev.start_date && ev.start_date < todayStr;
            const blockNewPin = isPastEvent && !isPinned;
            return (
              <>
                <button
                  onClick={handleTogglePin}
                  disabled={pinBusy || blockNewPin}
                  title={blockNewPin ? '이미 종료된 학회는 새로 등록할 수 없습니다' : undefined}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                    padding: '12px 16px', borderRadius: 10,
                    cursor: pinBusy ? 'wait' : (blockNewPin ? 'not-allowed' : 'pointer'),
                    fontSize: 13, fontWeight: 800, fontFamily: 'inherit',
                    border: '1px solid ' + (
                      blockNewPin ? 'var(--bd-s)' : (isPinned ? '#b45309' : 'var(--ac)')
                    ),
                    background: blockNewPin ? 'var(--bg-2)' : (isPinned ? '#fef3c7' : 'var(--ac)'),
                    color: blockNewPin ? 'var(--t3)' : (isPinned ? '#b45309' : '#fff'),
                    opacity: pinBusy ? .6 : 1,
                  }}
                >
                  <Pin size={14} />
                  {blockNewPin
                    ? '이미 종료된 학회 (등록 불가)'
                    : isPinned
                      ? (pickMode ? '이미 내 일정에 있음 — 일정으로 돌아가기' : '내 일정 등록됨 ✓ (클릭하여 해제)')
                      : (pickMode ? '내 일정에 추가' : '내 일정에 등록')}
                </button>
                {blockNewPin && (
                  <div style={{
                    fontSize: 11, color: 'var(--t3)', textAlign: 'center', lineHeight: 1.5,
                    padding: '4px 8px',
                  }}>
                    이미 종료된 학회는 새로 등록할 수 없습니다.<br />
                    이전에 등록한 학회는 그대로 유지·해제 가능합니다.
                  </div>
                )}
              </>
            );
          })()}

          {/* manual 이벤트 — 사용자 입력 URL */}
          {manualUrl && (
            <a
              href={manualUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                padding: '11px 16px', borderRadius: 10,
                background: 'var(--ac-d)', color: 'var(--ac)',
                border: '1px solid var(--ac)', textDecoration: 'none',
                fontSize: 12, fontWeight: 800, fontFamily: 'inherit',
              }}
            >
              <ExternalLink size={13} /> 원본 링크
            </a>
          )}

          {/* 주최단체 홈페이지 — 보조 링크 */}
          {organizerHomepage && (
            <a
              href={organizerHomepage}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                padding: '9px 14px', borderRadius: 10,
                background: 'transparent', color: 'var(--t2)',
                border: '1px solid var(--bd-s)', textDecoration: 'none',
                fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
              }}
            >
              <Landmark size={12} /> {ev.organizer_name || '주최단체'} 홈페이지
            </a>
          )}

          {/* 팀 공지 — 준비 중 */}
          <button
            disabled
            title="팀 공유 준비 중"
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              padding: '9px 14px', borderRadius: 10,
              background: 'var(--bg-2)', color: 'var(--t3)',
              border: '1px dashed var(--bd-s)', cursor: 'not-allowed',
              fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
            }}
          >
            <Share2 size={12} /> 팀 공지로 공유 (준비 중)
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ icon, label, children }) {
  return (
    <div style={{
      display: 'flex', gap: 12, padding: '11px 0',
      borderBottom: '1px solid var(--bd-s)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 5,
        fontSize: 11, fontWeight: 700, color: 'var(--t3)',
        minWidth: 72, letterSpacing: '.02em',
      }}>
        {icon} {label}
      </div>
      <div style={{ flex: 1, fontSize: 13, color: 'var(--t1)', lineHeight: 1.5 }}>
        {children}
      </div>
    </div>
  );
}
