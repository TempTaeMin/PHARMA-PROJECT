import { useEffect, useState } from 'react';
import { X, Calendar, MapPin, BookOpen, Users, Hash, Tag, ExternalLink, Presentation } from 'lucide-react';
import { academicApi } from '../api/client';

const GRADE_COLORS = {
  A: { bg: '#fee2e2', c: '#b91c1c' },
  B: { bg: '#ffedd5', c: '#c2410c' },
  C: { bg: '#dbeafe', c: '#1d4ed8' },
};

const SOURCE_LABELS = {
  kma_edu: { label: 'KMA 연수', bg: '#fef3c7', c: '#92400e' },
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

export default function AcademicEventModal({ open, event, onClose, onNavigateDoctor }) {
  const [enriched, setEnriched] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !event?.id) {
      setEnriched(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    academicApi.getById(event.id)
      .then(data => { if (!cancelled) setEnriched(data); })
      .catch(err => { if (!cancelled) console.error('[AcademicEventModal] fetch failed', err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, event?.id]);

  if (!open || !event) return null;

  const ev = enriched || event;
  const allLectures = Array.isArray(ev.lectures) ? ev.lectures : [];
  const lectures = allLectures.filter(L => !!L.matched_doctor_id);
  const hasAnyLectures = allLectures.length > 0;
  const externalLink = ev.detail_url_external || ev.url;
  const src = SOURCE_LABELS[ev.source];

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
          padding: '22px 24px 20px', width: 560, maxWidth: '100%',
          maxHeight: '92vh', overflowY: 'auto',
          animation: 'fadeUp .22s ease',
        }}
      >
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {src && (
              <span style={{
                display: 'inline-block', marginBottom: 8,
                padding: '3px 8px', borderRadius: 5,
                fontSize: 10, fontWeight: 800, letterSpacing: '.05em',
                background: src.bg, color: src.c, fontFamily: 'Manrope',
              }}>
                {src.label}
              </span>
            )}
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
            <Row icon={<MapPin size={13} />} label="장소">
              {ev.location}
            </Row>
          )}
          {ev.region && (
            <Row icon={<MapPin size={13} />} label="지역">
              {ev.region}
            </Row>
          )}
          {ev.organizer_name && (
            <Row icon={<BookOpen size={13} />} label="주최">
              {ev.organizer_name}
            </Row>
          )}
          {ev.sub_organizer && (
            <Row icon={<Users size={13} />} label="주관">
              {ev.sub_organizer}
            </Row>
          )}
          {ev.kma_category && (
            <Row icon={<Tag size={13} />} label="분야">
              {ev.kma_category}
            </Row>
          )}
          {ev.event_code && (
            <Row icon={<Hash size={13} />} label="교육코드">
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                {ev.event_code}
              </span>
            </Row>
          )}
        </div>

        {/* 강사진 — 내 교수 매칭된 강사만 */}
        {(loading || hasAnyLectures) && (
          <div style={{ marginTop: 18 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10,
            }}>
              <Presentation size={14} style={{ color: 'var(--t3)' }} />
              <span style={{
                fontSize: 12, fontWeight: 800, color: 'var(--t2)', letterSpacing: '.02em',
              }}>내 교수 강사진</span>
              {lectures.length > 0 && (
                <span style={{
                  fontSize: 10, color: 'var(--t3)', fontFamily: 'Outfit',
                }}>{lectures.length}</span>
              )}
            </div>

            {loading && allLectures.length === 0 ? (
              <div style={{
                fontSize: 12, color: 'var(--t3)', padding: '12px 0',
              }}>강의 일정 불러오는 중…</div>
            ) : lectures.length === 0 ? (
              <div style={{
                fontSize: 12, color: 'var(--t3)', padding: '12px 14px',
                background: 'var(--bg-2)', borderRadius: 8, border: '1px solid var(--bd-s)',
              }}>내 교수로 등록된 강사가 없습니다</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {lectures.map((L, i) => {
                  const matched = !!L.matched_doctor_id;
                  const grade = L.matched_doctor_grade;
                  const gcol = GRADE_COLORS[grade];
                  return (
                    <div
                      key={i}
                      onClick={matched ? () => onNavigateDoctor && onNavigateDoctor(L.matched_doctor_id) : undefined}
                      style={{
                        padding: '10px 12px', borderRadius: 10,
                        background: matched ? 'var(--ac-d)' : 'var(--bg-2)',
                        border: '1px solid ' + (matched ? 'var(--ac)' : 'var(--bd-s)'),
                        cursor: matched ? 'pointer' : 'default',
                        transition: 'transform .12s',
                      }}
                      onMouseEnter={matched ? e => e.currentTarget.style.transform = 'translateY(-1px)' : undefined}
                      onMouseLeave={matched ? e => e.currentTarget.style.transform = 'translateY(0)' : undefined}
                    >
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap',
                      }}>
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
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
                        fontSize: 11, color: 'var(--t2)',
                      }}>
                        <span style={{ fontWeight: 700, color: matched ? 'var(--ac)' : 'var(--t1)' }}>
                          {L.lecturer}
                        </span>
                        {L.affiliation && (
                          <span style={{ color: 'var(--t3)' }}>· {L.affiliation}</span>
                        )}
                        {matched && gcol && (
                          <span style={{
                            padding: '2px 7px', borderRadius: 10, fontSize: 9, fontWeight: 800,
                            background: gcol.bg, color: gcol.c, letterSpacing: '.02em',
                            fontFamily: 'Manrope', marginLeft: 'auto',
                          }}>
                            내 교수 · {grade}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* 외부 링크 — 맨 아래 */}
        {externalLink && (
          <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--bd-s)' }}>
            <a
              href={externalLink}
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
              <ExternalLink size={13} /> 원본 사이트에서 자세히 보기
            </a>
            <div style={{
              fontSize: 10, color: 'var(--t3)', textAlign: 'center',
              marginTop: 6, wordBreak: 'break-all',
            }}>
              {externalLink}
            </div>
          </div>
        )}
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
