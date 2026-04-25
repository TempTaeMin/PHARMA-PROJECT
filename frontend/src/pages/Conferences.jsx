import { useState, useMemo } from 'react';
import { Calendar, MapPin, BookOpen, ChevronRight, RefreshCw, Filter, AlertCircle, CalendarRange, GraduationCap, Pin } from 'lucide-react';
import { academicApi } from '../api/client';
import { useCachedApi } from '../hooks/useCachedApi';
import { invalidate } from '../api/cache';
import AcademicEventModal from '../components/AcademicEventModal';

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
  const [, m, d] = iso.split('-');
  return `${Number(m)}월 ${Number(d)}일`;
}

function fmtRange(start, end) {
  if (!start) return '';
  if (!end || start === end) return fmtDate(start);
  return `${fmtDate(start)} ~ ${fmtDate(end)}`;
}

const SOURCE_LABELS = {
  kma_edu: { label: 'KMA 연수', bg: '#fef3c7', c: '#92400e' },
};

function addMonthsISO(date, months) {
  const d = new Date(date);
  d.setMonth(d.getMonth() + months);
  return d.toISOString().slice(0, 10);
}

function ymdISO(date) {
  return date.toISOString().slice(0, 10);
}

// 기간 프리셋. compute(today) → { from, to } (YYYY-MM-DD 문자열)
const RANGE_PRESETS = [
  { key: 'last-1y',  label: '지난 1년',     compute: (t) => ({ from: addMonthsISO(t, -12), to: ymdISO(t) }) },
  { key: 'last-3m',  label: '지난 3개월',   compute: (t) => ({ from: addMonthsISO(t, -3),  to: ymdISO(t) }) },
  { key: 'next-3m',  label: '앞으로 3개월', compute: (t) => ({ from: ymdISO(t), to: addMonthsISO(t, 3) }) },
  { key: 'next-6m',  label: '앞으로 6개월', compute: (t) => ({ from: ymdISO(t), to: addMonthsISO(t, 6) }) },
  { key: 'custom',   label: '직접 선택',    compute: null },
];
const DEFAULT_PRESET_KEY = 'next-3m';

function defaultRange() {
  const today = new Date();
  const preset = RANGE_PRESETS.find(p => p.key === DEFAULT_PRESET_KEY);
  const { from, to } = preset.compute(today);
  return { presetKey: DEFAULT_PRESET_KEY, from, to };
}

export default function Conferences({ onNavigate }) {
  const [tab, setTab] = useState('matched'); // matched | upcoming | all | unclassified
  const [deptFilter, setDeptFilter] = useState('');
  const [range, setRange] = useState(defaultRange);
  const [syncStatus, setSyncStatus] = useState(null);
  const [selectedEvent, setSelectedEvent] = useState(null);

  const {
    data: rangeRaw, loading: rangeLoading, refresh: refreshRange,
  } = useCachedApi(
    `academic-range:${range.from}:${range.to}`,
    () => academicApi.list({ limit: 1000, start_from: range.from, start_to: range.to }),
    { ttlKey: 'academic', deps: [range.from, range.to] },
  );

  const {
    data: unclassifiedRaw, loading: unLoading, refresh: refreshUnclassified,
  } = useCachedApi('academic-unclassified', () => academicApi.unclassified(), { ttlKey: 'academic' });

  const sourceRaw = tab === 'unclassified' ? unclassifiedRaw : rangeRaw;
  const loading = tab === 'unclassified' ? unLoading : rangeLoading;
  const events = Array.isArray(sourceRaw) ? sourceRaw : [];

  // 히어로 요약 — 현재 선택 기간 기준
  const heroStats = useMemo(() => {
    const base = Array.isArray(rangeRaw) ? rangeRaw : [];
    const matched = base.filter(e => (e.matched_doctor_count || 0) > 0).length;
    return { total: base.length, matched };
  }, [rangeRaw]);

  const presetLabel = useMemo(() => {
    const p = RANGE_PRESETS.find(x => x.key === range.presetKey);
    return p ? p.label : '지정 기간';
  }, [range.presetKey]);

  const selectPreset = (key) => {
    if (key === 'custom') {
      setRange(prev => ({ ...prev, presetKey: 'custom' }));
      return;
    }
    const preset = RANGE_PRESETS.find(p => p.key === key);
    const { from, to } = preset.compute(new Date());
    setRange({ presetKey: key, from, to });
  };

  // 탭별 필터
  const tabFiltered = useMemo(() => {
    if (tab === 'matched') {
      return events.filter(e => (e.matched_doctor_count || 0) > 0);
    }
    return events;
  }, [events, tab]);

  // 진료과 옵션 — 현재 탭 노출 이벤트에서 추출
  const deptOptions = useMemo(() => {
    const set = new Set();
    tabFiltered.forEach(e => (e.departments || []).forEach(d => set.add(d)));
    return Array.from(set).sort();
  }, [tabFiltered]);

  const filtered = useMemo(() => {
    if (!deptFilter) return tabFiltered;
    return tabFiltered.filter(e => (e.departments || []).includes(deptFilter));
  }, [tabFiltered, deptFilter]);

  async function handleSync() {
    setSyncStatus('syncing');
    try {
      await academicApi.sync();
      setSyncStatus('dispatched');
      setTimeout(() => {
        invalidate('academic');
        refreshRange();
        refreshUnclassified();
        setSyncStatus(null);
      }, 2000);
    } catch {
      setSyncStatus('error');
      setTimeout(() => setSyncStatus(null), 3000);
    }
  }

  function handleEventUpdated() {
    invalidate('academic');
    refreshRange();
    refreshUnclassified();
  }

  const TABS = [
    { id: 'matched', label: '내 교수 참여' },
    { id: 'upcoming', label: '다가오는 일정' },
    { id: 'all', label: '전체' },
    { id: 'unclassified', label: '미분류' },
  ];

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <style>{`
        .dept-chip-row::-webkit-scrollbar { display: none; }
        .dept-chip-row { -ms-overflow-style: none; scrollbar-width: none; }
      `}</style>

      {/* ── 헤더 ── */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 16, gap: 16, flexWrap: 'wrap',
      }}>
        <div>
          <div style={{ fontFamily: 'Manrope', fontSize: 22, fontWeight: 700, letterSpacing: '-.02em' }}>학회 일정</div>
          <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 4 }}>
            내 교수가 강사로 참여하는 학회를 우선으로 · 매월 1일 자동 갱신
          </div>
        </div>
        <button onClick={handleSync} disabled={syncStatus === 'syncing'} style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '8px 14px', borderRadius: 10,
          background: syncStatus === 'error' ? '#fee2e2' : 'var(--bg-1)',
          border: '1px solid var(--bd-s)', cursor: 'pointer',
          fontSize: 12, fontWeight: 600, color: 'var(--t1)', fontFamily: 'inherit',
        }}>
          <RefreshCw size={13} style={{ animation: syncStatus === 'syncing' ? 'spin 1s linear infinite' : 'none' }} />
          {syncStatus === 'syncing' ? '동기화 중…' : syncStatus === 'dispatched' ? '동기화 요청됨' : syncStatus === 'error' ? '실패' : '동기화'}
        </button>
      </div>

      {/* ── 히어로 요약 ── */}
      <div style={{
        background: 'linear-gradient(135deg, var(--ac-d), #eef2ff)',
        border: '1px solid var(--ac)',
        borderRadius: 14, padding: '16px 20px', marginBottom: 16,
        display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <GraduationCap size={28} style={{ color: 'var(--ac)' }} />
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--ac)', letterSpacing: '.08em' }}>
            {presetLabel}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 24, flex: 1, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 10, color: 'var(--t3)', fontWeight: 600 }}>전체 학회</div>
            <div style={{ fontFamily: 'Manrope', fontSize: 26, fontWeight: 800, color: 'var(--t1)', lineHeight: 1.1 }}>
              {heroStats.total}<span style={{ fontSize: 13, marginLeft: 2 }}>개</span>
            </div>
          </div>
          <div>
            <div style={{ fontSize: 10, color: 'var(--t3)', fontWeight: 600 }}>내 교수 강사 참여</div>
            <div style={{ fontFamily: 'Manrope', fontSize: 26, fontWeight: 800, color: 'var(--ac)', lineHeight: 1.1 }}>
              {heroStats.matched}<span style={{ fontSize: 13, marginLeft: 2 }}>개</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── 탭 + 기간 필터 ── */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 14, gap: 12, flexWrap: 'wrap',
      }}>
        <div style={{
          display: 'flex', gap: 4, padding: 4,
          background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 10,
          overflowX: 'auto', maxWidth: '100%',
        }} className="dept-chip-row">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding: '7px 14px', borderRadius: 7, border: 'none',
              background: tab === t.id ? 'var(--ac-d)' : 'transparent',
              color: tab === t.id ? 'var(--ac)' : 'var(--t3)',
              fontWeight: tab === t.id ? 700 : 500, fontSize: 12,
              fontFamily: 'inherit', cursor: 'pointer', whiteSpace: 'nowrap',
              flexShrink: 0,
            }}>{t.label}</button>
          ))}
        </div>

        {tab !== 'unclassified' && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: 4,
            background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 10,
            flexWrap: 'wrap',
          }}>
            <CalendarRange size={13} style={{ color: 'var(--t3)', marginLeft: 6 }} />
            {RANGE_PRESETS.map(p => (
              <button key={p.key} onClick={() => selectPreset(p.key)} style={{
                padding: '6px 12px', borderRadius: 7, border: 'none',
                background: range.presetKey === p.key ? 'var(--ac-d)' : 'transparent',
                color: range.presetKey === p.key ? 'var(--ac)' : 'var(--t3)',
                fontWeight: range.presetKey === p.key ? 600 : 500, fontSize: 12,
                fontFamily: 'inherit', cursor: 'pointer', whiteSpace: 'nowrap',
              }}>{p.label}</button>
            ))}
            {range.presetKey === 'custom' && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 4,
                marginLeft: 4, paddingLeft: 8, borderLeft: '1px solid var(--bd-s)',
              }}>
                <input type="date" value={range.from}
                  onChange={e => setRange(prev => ({ ...prev, from: e.target.value }))}
                  style={dateInputStyle} />
                <span style={{ color: 'var(--t3)', fontSize: 11 }}>~</span>
                <input type="date" value={range.to}
                  onChange={e => setRange(prev => ({ ...prev, to: e.target.value }))}
                  style={dateInputStyle} />
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── 진료과 필터 (모바일 가로 스크롤) ── */}
      {deptOptions.length > 0 && (
        <div
          className="dept-chip-row"
          style={{
            display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16,
            overflowX: 'auto', flexWrap: 'nowrap',
            scrollSnapType: 'x proximity',
            padding: '2px 2px 6px',
            WebkitOverflowScrolling: 'touch',
          }}
        >
          <div style={{
            flexShrink: 0, display: 'flex', alignItems: 'center', gap: 4,
            padding: '10px 8px', color: 'var(--t3)',
          }}>
            <Filter size={14} />
          </div>
          <button
            onClick={() => setDeptFilter('')}
            style={{
              flexShrink: 0, scrollSnapAlign: 'start',
              padding: '10px 16px', borderRadius: 22,
              background: !deptFilter ? 'var(--ac)' : 'var(--bg-1)',
              color: !deptFilter ? '#fff' : 'var(--t2)',
              border: '1px solid ' + (!deptFilter ? 'var(--ac)' : 'var(--bd-s)'),
              fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
              whiteSpace: 'nowrap', minHeight: 40,
            }}
          >전체</button>
          {deptOptions.map(d => (
            <button
              key={d}
              onClick={() => setDeptFilter(d === deptFilter ? '' : d)}
              style={{
                flexShrink: 0, scrollSnapAlign: 'start',
                padding: '10px 16px', borderRadius: 22,
                background: deptFilter === d ? 'var(--ac)' : 'var(--bg-1)',
                color: deptFilter === d ? '#fff' : 'var(--t2)',
                border: '1px solid ' + (deptFilter === d ? 'var(--ac)' : 'var(--bd-s)'),
                fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                whiteSpace: 'nowrap', minHeight: 40,
              }}
            >{d}</button>
          ))}
        </div>
      )}

      {/* ── 이벤트 목록 ── */}
      {loading && !sourceRaw ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)' }}>로딩 중…</div>
      ) : filtered.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 60, color: 'var(--t3)',
          background: 'var(--bg-1)', borderRadius: 12, border: '1px solid var(--bd-s)',
        }}>
          {tab === 'matched' ? '내 교수가 강사로 참여하는 학회가 없습니다'
            : tab === 'upcoming' ? '다가오는 학회 일정이 없습니다'
            : tab === 'unclassified' ? '미분류 이벤트가 없습니다'
            : '데이터가 없습니다'}
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 10 }}>
          {filtered.map((e, i) => {
            const matchedCount = e.matched_doctor_count || 0;
            const matchedNames = Array.isArray(e.matched_doctor_names) ? e.matched_doctor_names : [];
            const preview = matchedNames.slice(0, 3).join(' · ');
            const extra = matchedNames.length > 3 ? ` +${matchedNames.length - 3}명` : '';
            return (
              <article
                key={e.id}
                onClick={() => setSelectedEvent(e)}
                style={{
                  background: 'var(--bg-1)',
                  border: '1px solid ' + (matchedCount > 0 ? 'var(--ac)' : 'var(--bd-s)'),
                  borderRadius: 12, padding: 16, display: 'flex', gap: 14, cursor: 'pointer',
                  animation: `fadeUp .25s ease ${i * .03}s both`,
                  transition: 'border-color .15s, transform .15s',
                }}
                onMouseEnter={ev => ev.currentTarget.style.borderColor = 'var(--ac)'}
                onMouseLeave={ev => ev.currentTarget.style.borderColor = matchedCount > 0 ? 'var(--ac)' : 'var(--bd-s)'}
              >
                <div style={{
                  flexShrink: 0, width: 60, textAlign: 'center',
                  padding: '8px 4px', borderRadius: 10,
                  background: 'var(--ac-d)', color: 'var(--ac)',
                }}>
                  <div style={{ fontSize: 10, fontWeight: 600, opacity: .8 }}>
                    {e.start_date ? e.start_date.slice(5, 7) + '월' : ''}
                  </div>
                  <div style={{ fontFamily: 'Outfit', fontSize: 22, fontWeight: 700, lineHeight: 1 }}>
                    {e.start_date ? Number(e.start_date.slice(8, 10)) : '-'}
                  </div>
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--t1)', lineHeight: 1.4 }}>
                      {e.name}
                    </div>
                    {SOURCE_LABELS[e.source] && (
                      <span style={{
                        padding: '2px 7px', borderRadius: 10, fontSize: 9, fontWeight: 700,
                        background: SOURCE_LABELS[e.source].bg, color: SOURCE_LABELS[e.source].c,
                        letterSpacing: '.02em',
                      }}>{SOURCE_LABELS[e.source].label}</span>
                    )}
                    {matchedCount > 0 && (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 3,
                        padding: '2px 8px', borderRadius: 10,
                        fontSize: 10, fontWeight: 800,
                        background: 'var(--ac)', color: '#fff',
                        letterSpacing: '.02em',
                      }}>
                        <GraduationCap size={10} /> 내 교수 {matchedCount}명
                      </span>
                    )}
                    {e.is_pinned && (
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: 3,
                        padding: '2px 7px', borderRadius: 10,
                        fontSize: 9, fontWeight: 800,
                        background: '#fef3c7', color: '#b45309',
                        letterSpacing: '.02em',
                      }}>
                        <Pin size={9} /> 내 일정 등록됨
                      </span>
                    )}
                  </div>
                  {e.organizer_name && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--t2)', marginBottom: 3 }}>
                      <BookOpen size={11} /> {e.organizer_name}
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: 'var(--t3)', flexWrap: 'wrap' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Calendar size={11} /> {fmtRange(e.start_date, e.end_date)}
                    </span>
                    {e.location && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <MapPin size={11} /> {e.location}
                      </span>
                    )}
                  </div>

                  {(e.departments && e.departments.length > 0) ? (
                    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 8 }}>
                      {e.departments.map(d => {
                        const col = deptColor(d);
                        return (
                          <span key={d} style={{
                            padding: '3px 8px', borderRadius: 12, fontSize: 10, fontWeight: 600,
                            background: col.bg, color: col.c,
                          }}>{d}</span>
                        );
                      })}
                    </div>
                  ) : e.classification_status === 'unclassified' ? (
                    <div style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      marginTop: 8, padding: '3px 8px', borderRadius: 12,
                      fontSize: 10, fontWeight: 500, color: 'var(--t3)',
                      background: 'var(--bg-2)',
                    }}>
                      <AlertCircle size={10} /> 미분류
                    </div>
                  ) : null}

                  {matchedCount > 0 && preview && (
                    <div style={{
                      marginTop: 8, padding: '6px 10px', borderRadius: 8,
                      background: 'var(--ac-d)',
                      fontSize: 11, color: 'var(--ac)', fontWeight: 600,
                      display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
                    }}>
                      <GraduationCap size={11} />
                      <span>강사: {preview}{extra}</span>
                    </div>
                  )}
                </div>

                <div style={{
                  flexShrink: 0, alignSelf: 'center',
                  color: 'var(--t3)',
                }}>
                  <ChevronRight size={16} />
                </div>
              </article>
            );
          })}
        </div>
      )}

      <AcademicEventModal
        open={!!selectedEvent}
        event={selectedEvent}
        onClose={() => setSelectedEvent(null)}
        onNavigateDoctor={(doctorId) => {
          setSelectedEvent(null);
          if (onNavigate) onNavigate('my-doctors', { doctorId });
        }}
        onUpdated={handleEventUpdated}
      />
    </div>
  );
}

const dateInputStyle = {
  padding: '5px 8px', borderRadius: 6,
  background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
  color: 'var(--t1)', fontSize: 11, fontFamily: "'JetBrains Mono'",
  outline: 'none',
};
