import { useState, useMemo } from 'react';
import { Calendar, MapPin, BookOpen, ExternalLink, RefreshCw, Filter, AlertCircle } from 'lucide-react';
import { academicApi } from '../api/client';
import { useCachedApi } from '../hooks/useCachedApi';

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
  return `${Number(m)}월 ${Number(d)}일`;
}

function fmtRange(start, end) {
  if (!start) return '';
  if (!end || start === end) return fmtDate(start);
  return `${fmtDate(start)} ~ ${fmtDate(end)}`;
}

const SOURCE_LABELS = {
  healthmedia: { label: '메디칼허브', bg: '#e0f2fe', c: '#0369a1' },
  kma_edu: { label: 'KMA 연수', bg: '#fef3c7', c: '#92400e' },
};

export default function Conferences() {
  const [tab, setTab] = useState('upcoming'); // upcoming | all | unclassified
  const [deptFilter, setDeptFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState(''); // '' | 'healthmedia' | 'kma_edu'
  const [syncStatus, setSyncStatus] = useState(null);

  const srcKey = sourceFilter || 'all';
  const srcParam = sourceFilter || undefined;

  const {
    data: upcomingRaw, loading: upLoading, refresh: refreshUpcoming,
  } = useCachedApi(
    `academic-upcoming:${srcKey}`,
    () => academicApi.upcoming(null, 3, srcParam),
    { ttlKey: 'academic' },
  );

  const {
    data: allRaw, loading: allLoading, refresh: refreshAll,
  } = useCachedApi(
    `academic-all:${srcKey}`,
    () => academicApi.list({ limit: 1000, ...(srcParam ? { source: srcParam } : {}) }),
    { ttlKey: 'academic' },
  );

  const {
    data: unclassifiedRaw, loading: unLoading, refresh: refreshUnclassified,
  } = useCachedApi('academic-unclassified', () => academicApi.unclassified(), { ttlKey: 'academic' });

  const sourceRaw = tab === 'upcoming' ? upcomingRaw : tab === 'unclassified' ? unclassifiedRaw : allRaw;
  const loading = tab === 'upcoming' ? upLoading : tab === 'unclassified' ? unLoading : allLoading;
  const events = Array.isArray(sourceRaw) ? sourceRaw : [];

  // 진료과 옵션 — 현재 노출된 이벤트에서 추출
  const deptOptions = useMemo(() => {
    const set = new Set();
    events.forEach(e => (e.departments || []).forEach(d => set.add(d)));
    return Array.from(set).sort();
  }, [events]);

  const filtered = useMemo(() => {
    if (!deptFilter) return events;
    return events.filter(e => (e.departments || []).includes(deptFilter));
  }, [events, deptFilter]);

  async function handleSync() {
    setSyncStatus('syncing');
    try {
      await academicApi.sync();
      setSyncStatus('dispatched');
      setTimeout(() => {
        refreshUpcoming();
        refreshAll();
        refreshUnclassified();
        setSyncStatus(null);
      }, 2000);
    } catch (err) {
      setSyncStatus('error');
      setTimeout(() => setSyncStatus(null), 3000);
    }
  }

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      {/* ── 헤더 ── */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 20, gap: 16, flexWrap: 'wrap',
      }}>
        <div>
          <div style={{ fontFamily: 'Manrope', fontSize: 22, fontWeight: 700, letterSpacing: '-.02em' }}>학회 일정</div>
          <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 4 }}>
            교수 방문 일정을 참고할 때 활용하세요 · 매월 1일 자동 갱신
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

      {/* ── 탭 + 필터 ── */}
      <div style={{
        display: 'flex', gap: 4, marginBottom: 16, padding: 4,
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 10,
        width: 'fit-content',
      }}>
        {[
          { id: 'upcoming', label: '다가오는 일정' },
          { id: 'all', label: '전체' },
          { id: 'unclassified', label: '미분류' },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '7px 14px', borderRadius: 7, border: 'none',
            background: tab === t.id ? 'var(--ac-d)' : 'transparent',
            color: tab === t.id ? 'var(--ac)' : 'var(--t3)',
            fontWeight: tab === t.id ? 600 : 500, fontSize: 12,
            fontFamily: 'inherit', cursor: 'pointer',
          }}>{t.label}</button>
        ))}
      </div>

      {/* ── 소스 토글 ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
        {[
          { id: '', label: '전체 소스' },
          { id: 'healthmedia', label: '메디칼허브' },
          { id: 'kma_edu', label: 'KMA 연수' },
        ].map(s => (
          <button
            key={s.id || 'all'}
            onClick={() => setSourceFilter(s.id)}
            style={{
              padding: '5px 11px', borderRadius: 20,
              background: sourceFilter === s.id ? 'var(--ac)' : 'var(--bg-1)',
              color: sourceFilter === s.id ? '#fff' : 'var(--t2)',
              border: '1px solid ' + (sourceFilter === s.id ? 'var(--ac)' : 'var(--bd-s)'),
              fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >{s.label}</button>
        ))}
      </div>

      {deptOptions.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
          <Filter size={14} style={{ color: 'var(--t3)' }} />
          <button
            onClick={() => setDeptFilter('')}
            style={{
              padding: '5px 11px', borderRadius: 20,
              background: !deptFilter ? 'var(--ac)' : 'var(--bg-1)',
              color: !deptFilter ? '#fff' : 'var(--t2)',
              border: '1px solid ' + (!deptFilter ? 'var(--ac)' : 'var(--bd-s)'),
              fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >전체</button>
          {deptOptions.map(d => (
            <button
              key={d}
              onClick={() => setDeptFilter(d === deptFilter ? '' : d)}
              style={{
                padding: '5px 11px', borderRadius: 20,
                background: deptFilter === d ? 'var(--ac)' : 'var(--bg-1)',
                color: deptFilter === d ? '#fff' : 'var(--t2)',
                border: '1px solid ' + (deptFilter === d ? 'var(--ac)' : 'var(--bd-s)'),
                fontSize: 11, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
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
          {tab === 'upcoming' ? '다가오는 학회 일정이 없습니다' : tab === 'unclassified' ? '미분류 이벤트가 없습니다' : '데이터가 없습니다'}
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 10 }}>
          {filtered.map((e, i) => (
            <article key={e.id} style={{
              background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 12,
              padding: 16, display: 'flex', gap: 14,
              animation: `fadeUp .25s ease ${i * .03}s both`,
            }}>
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
              </div>

              {e.url && (
                <a href={e.url} target="_blank" rel="noopener noreferrer" style={{
                  flexShrink: 0, alignSelf: 'flex-start',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  width: 32, height: 32, borderRadius: 8,
                  background: 'var(--bg-2)', color: 'var(--t3)',
                  textDecoration: 'none',
                }}>
                  <ExternalLink size={14} />
                </a>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
