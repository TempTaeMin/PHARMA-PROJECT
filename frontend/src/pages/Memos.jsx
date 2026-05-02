import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Search, Filter, Sparkles, FileText, X, Calendar, Settings, ChevronLeft, ClipboardList, CalendarDays } from 'lucide-react';
import { dashboardApi, memoApi, memoTemplateApi, reportApi } from '../api/client';
import { invalidate } from '../api/cache';
import MemoEditor from '../components/MemoEditor';
import MemoDetail from '../components/MemoDetail';
import TemplateSettings from '../components/TemplateSettings';
import ReportGenerator from '../components/ReportGenerator';
import ReportDetail from '../components/ReportDetail';

const MEMO_TYPE_LABEL = { visit: '방문', meeting: '회의록', note: '노트' };
const MEMO_TYPE_COLORS = {
  visit: { bg: '#e0f2fe', c: '#0369a1' },
  meeting: { bg: '#f3e8ff', c: '#7e22ce' },
  note: { bg: '#f3f4f6', c: '#6b7280' },
};

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}

function todayYMD() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function ymdMinusDays(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const DEFAULT_FROM = ymdMinusDays(7);
const DEFAULT_TO = todayYMD();

function summaryOneLine(memo) {
  const raw = memo.ai_summary;
  if (raw && typeof raw === 'object' && raw.summary) {
    const pref = raw.summary['결과'] || raw.summary['논의내용'] || raw.summary['요약'];
    if (pref && String(pref).trim()) return String(pref);
    const first = Object.values(raw.summary).find(v => v && String(v).trim());
    if (first) return String(first);
  }
  if (memo.raw_memo) {
    return memo.raw_memo.slice(0, 100).replace(/\s+/g, ' ');
  }
  return '';
}

/**
 * 메모/회의록 메뉴 — 목록 + 필터/검색 + 상세 전환 (내부 state).
 * `initialFilters`: 외부에서 진입 시 사전 적용(`{ doctor_id }`).
 */
export default function Memos({ initialFilters = {}, onNavigate }) {
  const [memos, setMemos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [hospitals, setHospitals] = useState([]);

  // 필터
  // 외부에서 doctor_id 와 함께 진입한 경우 (예: 의료진 상세 → 메모 전체보기) 기본 기간 필터를 풀어
  // 해당 교수의 모든 기록을 보여주고, 사용자가 필요하면 기간을 직접 설정.
  const enteredWithDoctor = !!initialFilters.doctor_id;
  const [q, setQ] = useState('');
  const [doctorFilter, setDoctorFilter] = useState(initialFilters.doctor_id || null);
  const [hospitalFilter, setHospitalFilter] = useState(null);
  const [typeFilter, setTypeFilter] = useState(null);
  const [fromDate, setFromDate] = useState(enteredWithDoctor ? '' : DEFAULT_FROM);
  const [toDate, setToDate] = useState(enteredWithDoctor ? '' : DEFAULT_TO);
  const [showFilters, setShowFilters] = useState(true);
  const [templateSettingsOpen, setTemplateSettingsOpen] = useState(false);

  // 뷰 상태
  const [view, setView] = useState('memos'); // 'memos' | 'reports'
  const [selected, setSelected] = useState(null); // 상세 표시
  const [editorOpen, setEditorOpen] = useState(false);
  const [editTarget, setEditTarget] = useState(null);

  // 보고서 관련 상태
  const [reports, setReports] = useState([]);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [selectedMemoIds, setSelectedMemoIds] = useState(() => new Set());
  const [reportGenOpen, setReportGenOpen] = useState(false);
  const [reportGenMode, setReportGenMode] = useState('daily'); // 'daily' | 'daily-from-memos' | 'weekly'
  const [reportGenPresetIds, setReportGenPresetIds] = useState(null);
  const [openedReport, setOpenedReport] = useState(null);

  const reloadTemplates = useCallback(async () => {
    try {
      const ts = await memoTemplateApi.list();
      setTemplates(ts || []);
      invalidate('memo-templates');
    } catch (e) {
      console.warn('템플릿 로드 실패:', e);
    }
  }, []);

  // ─ 초기 로드: templates + doctors (from dashboard summary) ─
  useEffect(() => {
    (async () => {
      try {
        const [ts, dash] = await Promise.all([
          memoTemplateApi.list().catch(() => []),
          dashboardApi.summary().catch(() => ({ doctors: [] })),
        ]);
        setTemplates(ts || []);
        const docs = dash.doctors || [];
        setDoctors(docs);
        // 병원 dedupe
        const hmap = {};
        docs.forEach(d => {
          if (d.hospital_name) hmap[d.hospital_name] = true;
        });
        setHospitals(Object.keys(hmap).sort());
      } catch (e) {
        console.warn('초기 데이터 로드 실패:', e);
      }
    })();
  }, []);

  // ─ 보고서 목록 로드 ─
  const loadReports = useCallback(async () => {
    setReportsLoading(true);
    try {
      const list = await reportApi.list({});
      setReports(list || []);
    } catch (e) {
      console.warn('보고서 로드 실패:', e);
      setReports([]);
    } finally {
      setReportsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view === 'reports') loadReports();
  }, [view, loadReports]);

  // ─ 목록 로드 ─
  const loadMemos = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (doctorFilter) params.doctor_id = doctorFilter;
      if (typeFilter) params.memo_type = typeFilter;
      if (q.trim()) params.q = q.trim();
      if (fromDate) params.from = fromDate;
      if (toDate) params.to = toDate;
      // hospital_id 필터 필요시 doctors에서 hospital → id 매핑 필요. 일단 client-side로 필터.
      const list = await memoApi.list(params);
      const filtered = hospitalFilter
        ? list.filter(m => m.hospital_name === hospitalFilter)
        : list;
      setMemos(filtered);
    } catch (e) {
      console.error(e);
      setMemos([]);
    } finally {
      setLoading(false);
    }
  }, [doctorFilter, typeFilter, q, fromDate, toDate, hospitalFilter]);

  useEffect(() => { loadMemos(); }, [loadMemos]);

  // ─ 교수 검색 입력 ─
  const [docQ, setDocQ] = useState('');
  const filteredDocs = useMemo(() => {
    const query = docQ.trim();
    if (!query) return doctors.slice(0, 15);
    return doctors
      .filter(d =>
        (d.name || '').includes(query) ||
        (d.department || '').includes(query) ||
        (d.hospital_name || '').includes(query)
      )
      .slice(0, 15);
  }, [doctors, docQ]);

  const selectedDoctor = doctors.find(d => d.id === doctorFilter) || null;
  const dateChanged = fromDate !== DEFAULT_FROM || toDate !== DEFAULT_TO;
  const anyFilter =
    doctorFilter || hospitalFilter || typeFilter || dateChanged || q.trim();

  const clearFilters = () => {
    setDoctorFilter(null);
    setHospitalFilter(null);
    setTypeFilter(null);
    setFromDate(DEFAULT_FROM);
    setToDate(DEFAULT_TO);
    setQ('');
    setDocQ('');
  };

  // ─ 액션: 저장 후 리스트 갱신 + 상세 진입 ─
  const handleSaved = (saved) => {
    if (!saved) return;
    loadMemos();
    // 현재 상세 보고 있었다면 업데이트 반영
    if (selected?.id === saved.id) setSelected(saved);
  };

  const handleMemoChanged = (updated) => {
    if (updated === null) {
      // 삭제
      setSelected(null);
      loadMemos();
      return;
    }
    setSelected(updated);
    setMemos(prev => prev.map(m => (m.id === updated.id ? updated : m)));
  };

  // ─ 상세 뷰 ─
  if (selected) {
    return (
      <>
        <MemoDetail
          memo={selected}
          onBack={() => setSelected(null)}
          onEdit={(m) => { setEditTarget(m); setEditorOpen(true); }}
          onChanged={handleMemoChanged}
        />
        <MemoEditor
          open={editorOpen}
          memo={editTarget}
          doctors={doctors}
          templates={templates}
          onClose={() => { setEditorOpen(false); setEditTarget(null); }}
          onSaved={handleSaved}
        />
      </>
    );
  }

  // ─ 목록 뷰 ─
  return (
    <div>
      {/* 상단 액션 바 + 필터 패널 (스크롤 시 고정) */}
      <div style={{
        position: 'sticky', top: 56, zIndex: 5,
        background: 'var(--bg-0)',
        margin: '-8px -4px 0',
        padding: '8px 4px 4px',
      }}>
      {enteredWithDoctor && onNavigate && (
        <button
          onClick={() => onNavigate('my-doctors', { doctorId: initialFilters.doctor_id })}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '6px 10px', marginBottom: 10, borderRadius: 8,
            background: 'var(--bg-1)', color: 'var(--t2)',
            border: '1px solid var(--bd-s)',
            fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
          }}
        >
          <ChevronLeft size={14} /> 의료진 상세로 돌아가기
        </button>
      )}

      {/* 메모 / 보고서 탭 */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
        <button onClick={() => setView('memos')} style={tabPillStyle(view === 'memos')}>
          <FileText size={13} /> 메모
        </button>
        <button onClick={() => setView('reports')} style={tabPillStyle(view === 'reports')}>
          <ClipboardList size={13} /> 보고서
        </button>
      </div>

      {view === 'memos' && (<>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', gap: 7,
          background: 'var(--bg-1)', border: '1px solid var(--bd)', borderRadius: 9,
          padding: '9px 12px', maxWidth: 420,
        }}>
          <Search size={14} style={{ color: 'var(--t3)' }} />
          <input
            placeholder="제목·원본·AI 정리 검색"
            value={q}
            onChange={e => setQ(e.target.value)}
            style={{
              border: 'none', background: 'none', outline: 'none',
              color: 'var(--t1)', fontSize: 13, width: '100%', fontFamily: 'inherit',
            }}
          />
        </div>
        <button
          onClick={() => setShowFilters(v => !v)}
          style={{
            padding: '9px 12px', borderRadius: 9,
            background: showFilters || anyFilter ? 'var(--ac-d)' : 'var(--bg-1)',
            color: showFilters || anyFilter ? 'var(--ac)' : 'var(--t3)',
            border: `1px solid ${showFilters || anyFilter ? 'var(--ac)' : 'var(--bd-s)'}`,
            fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
          }}
        >
          <Filter size={13} /> 필터
          {anyFilter && <span style={{
            background: 'var(--ac)', color: '#fff', borderRadius: 10,
            padding: '1px 6px', fontSize: 10,
          }}>ON</span>}
        </button>
        <button
          onClick={() => setTemplateSettingsOpen(true)}
          title="템플릿 관리"
          style={{
            padding: '9px 12px', borderRadius: 9,
            background: 'var(--bg-1)', color: 'var(--t3)',
            border: '1px solid var(--bd-s)',
            fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
          }}
        >
          <Settings size={13} /> 템플릿
        </button>
        <button
          onClick={() => { setEditTarget(null); setEditorOpen(true); }}
          style={{
            padding: '9px 14px', borderRadius: 9,
            background: 'var(--ac)', color: '#fff', border: 'none',
            fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
          }}
        >
          <Plus size={13} /> 새 메모
        </button>
      </div>

      {/* 필터 패널 */}
      {showFilters && (
        <div style={{
          padding: '14px 16px', borderRadius: 12,
          background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
          marginBottom: 12,
        }}>
          {/* 교수 */}
          <FilterRow label="교수">
            {selectedDoctor ? (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '5px 10px', borderRadius: 7,
                background: 'var(--ac-d)', color: 'var(--ac)',
                fontSize: 12, fontWeight: 700, width: 'fit-content',
              }}>
                {selectedDoctor.name} · {selectedDoctor.hospital_name}
                <button onClick={() => setDoctorFilter(null)} style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--ac)', padding: 0, display: 'flex',
                }}><X size={12} /></button>
              </div>
            ) : (
              <div>
                <input
                  placeholder="교수명 검색…"
                  value={docQ}
                  onChange={e => setDocQ(e.target.value)}
                  style={{
                    width: '100%', maxWidth: 280, padding: '7px 10px', borderRadius: 7,
                    background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
                    fontSize: 12, outline: 'none', color: 'var(--t1)', fontFamily: 'inherit',
                  }}
                />
                {docQ && (
                  <div style={{
                    marginTop: 6, maxHeight: 140, overflowY: 'auto',
                    border: '1px solid var(--bd-s)', borderRadius: 7,
                    background: 'var(--bg-1)', maxWidth: 280,
                  }}>
                    {filteredDocs.length === 0 ? (
                      <div style={{ padding: 10, textAlign: 'center', fontSize: 11, color: 'var(--t3)' }}>결과 없음</div>
                    ) : filteredDocs.map(d => (
                      <button
                        key={d.id}
                        onClick={() => { setDoctorFilter(d.id); setDocQ(''); }}
                        style={{
                          display: 'block', width: '100%', textAlign: 'left',
                          padding: '7px 10px', background: 'none', border: 'none',
                          borderBottom: '1px solid var(--bd-s)', cursor: 'pointer',
                          fontFamily: 'inherit',
                        }}
                      >
                        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--t1)' }}>{d.name}</div>
                        <div style={{ fontSize: 10, color: 'var(--t3)' }}>{d.hospital_name} · {d.department}</div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </FilterRow>

          {/* 병원 */}
          <FilterRow label="병원">
            <select
              value={hospitalFilter || ''}
              onChange={e => setHospitalFilter(e.target.value || null)}
              style={selectStyle}
            >
              <option value="">(전체)</option>
              {hospitals.map(h => <option key={h} value={h}>{h}</option>)}
            </select>
          </FilterRow>

          {/* 유형 */}
          <FilterRow label="유형">
            <div style={{ display: 'flex', gap: 5 }}>
              <ChipBtn active={!typeFilter} onClick={() => setTypeFilter(null)}>전체</ChipBtn>
              {Object.entries(MEMO_TYPE_LABEL).map(([k, v]) => (
                <ChipBtn key={k} active={typeFilter === k} onClick={() => setTypeFilter(k)}>{v}</ChipBtn>
              ))}
            </div>
          </FilterRow>

          {/* 기간 */}
          <FilterRow label="기간">
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} style={selectStyle} />
              <span style={{ fontSize: 12, color: 'var(--t3)' }}>~</span>
              <input type="date" value={toDate} onChange={e => setToDate(e.target.value)} style={selectStyle} />
            </div>
          </FilterRow>

          {anyFilter && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
              <button
                onClick={clearFilters}
                style={{
                  padding: '6px 11px', borderRadius: 7,
                  background: 'var(--bg-2)', color: 'var(--t2)',
                  border: '1px solid var(--bd-s)', fontSize: 11, fontWeight: 600,
                  cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                필터 초기화
              </button>
            </div>
          )}
        </div>
      )}
      </>)}

      {/* ── 보고서 탭 액션바 ── */}
      {view === 'reports' && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          <button
            onClick={() => { setReportGenMode('daily'); setReportGenPresetIds(null); setReportGenOpen(true); }}
            style={{
              padding: '9px 14px', borderRadius: 9,
              background: 'var(--ac)', color: '#fff', border: 'none',
              fontSize: 12, fontWeight: 700, fontFamily: 'inherit', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            <Plus size={13} /> 일일 보고서
          </button>
          <button
            onClick={() => { setReportGenMode('weekly'); setReportGenPresetIds(null); setReportGenOpen(true); }}
            style={{
              padding: '9px 14px', borderRadius: 9,
              background: 'var(--bg-1)', color: 'var(--ac)', border: '1px solid var(--ac)',
              fontSize: 12, fontWeight: 700, fontFamily: 'inherit', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            <CalendarDays size={13} /> 주간 보고서
          </button>
        </div>
      )}
      </div>

      {/* 카운트 */}
      {view === 'memos' && (
        <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 8 }}>
          {loading ? '불러오는 중…' : `${memos.length}건`}
        </div>
      )}

      {/* 메모 목록 */}
      {view === 'memos' && (
        loading && !memos.length ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--t3)', fontSize: 13 }}>
            로딩 중…
          </div>
        ) : memos.length === 0 ? (
          <div style={{
            padding: '60px 20px', textAlign: 'center',
            background: 'var(--bg-1)', border: '1px dashed var(--bd-s)',
            borderRadius: 14, color: 'var(--t3)', fontSize: 13,
          }}>
            {anyFilter ? '조건에 맞는 메모가 없습니다.' : '아직 메모가 없습니다.'}
            <div style={{ fontSize: 11, marginTop: 6 }}>
              상단 "새 메모" 버튼으로 작성해보세요.
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingBottom: selectedMemoIds.size > 0 ? 80 : 0 }}>
            {memos.map(m => (
              <MemoCard
                key={m.id}
                memo={m}
                onClick={() => setSelected(m)}
                checked={selectedMemoIds.has(m.id)}
                onToggleCheck={() => {
                  setSelectedMemoIds(prev => {
                    const next = new Set(prev);
                    if (next.has(m.id)) next.delete(m.id);
                    else next.add(m.id);
                    return next;
                  });
                }}
              />
            ))}
          </div>
        )
      )}

      {/* 보고서 목록 */}
      {view === 'reports' && (
        reportsLoading && !reports.length ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--t3)', fontSize: 13 }}>
            로딩 중…
          </div>
        ) : reports.length === 0 ? (
          <div style={{
            padding: '60px 20px', textAlign: 'center',
            background: 'var(--bg-1)', border: '1px dashed var(--bd-s)',
            borderRadius: 14, color: 'var(--t3)', fontSize: 13,
          }}>
            아직 작성된 보고서가 없습니다.
            <div style={{ fontSize: 11, marginTop: 6 }}>
              위의 "일일 보고서" 또는 "주간 보고서" 버튼으로 시작하세요.
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {reports.map(r => (
              <ReportCard key={r.id} report={r} onClick={() => setOpenedReport(r)} />
            ))}
          </div>
        )
      )}

      {/* ── floating 액션바 (메모 선택 시) ── */}
      {view === 'memos' && selectedMemoIds.size > 0 && (
        <div style={{
          position: 'fixed', bottom: 18, left: '50%', transform: 'translateX(-50%)',
          width: 'min(560px, calc(100% - 32px))', zIndex: 60,
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 14px', borderRadius: 12,
          background: 'var(--t1)', color: '#fff',
          boxShadow: '0 10px 30px rgba(0,0,0,.25)',
          animation: 'fadeUp .2s ease',
        }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>{selectedMemoIds.size}개 선택됨</span>
          <div style={{ flex: 1 }} />
          <button
            onClick={() => {
              setReportGenMode('daily-from-memos');
              setReportGenPresetIds(Array.from(selectedMemoIds));
              setReportGenOpen(true);
            }}
            style={{
              padding: '8px 14px', borderRadius: 8,
              background: 'var(--ac)', color: '#fff', border: 'none',
              fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            <Sparkles size={13} /> 일일 보고서로 만들기
          </button>
          <button
            onClick={() => setSelectedMemoIds(new Set())}
            style={{
              padding: '8px 12px', borderRadius: 8,
              background: 'transparent', color: '#fff',
              border: '1px solid rgba(255,255,255,.3)',
              fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >해제</button>
        </div>
      )}

      {/* 작성/편집 모달 */}
      <MemoEditor
        open={editorOpen}
        memo={editTarget}
        doctors={doctors}
        templates={templates}
        onClose={() => { setEditorOpen(false); setEditTarget(null); }}
        onSaved={handleSaved}
      />

      {/* 템플릿 관리 모달 */}
      <TemplateSettings
        open={templateSettingsOpen}
        onClose={() => setTemplateSettingsOpen(false)}
        onChanged={reloadTemplates}
      />

      {/* 보고서 생성 모달 */}
      <ReportGenerator
        open={reportGenOpen}
        mode={reportGenMode}
        presetMemoIds={reportGenPresetIds}
        onClose={() => { setReportGenOpen(false); setReportGenPresetIds(null); }}
        onCreated={() => { loadReports(); }}
        onOpenReport={(r) => {
          setReportGenOpen(false);
          setReportGenPresetIds(null);
          setSelectedMemoIds(new Set());
          setView('reports');
          setOpenedReport(r);
        }}
      />

      {/* 보고서 상세 모달 */}
      <ReportDetail
        open={!!openedReport}
        report={openedReport}
        onClose={() => setOpenedReport(null)}
        onChanged={(updated) => {
          if (updated === null) {
            setOpenedReport(null);
            loadReports();
          } else {
            setOpenedReport(updated);
            loadReports();
          }
        }}
      />
    </div>
  );
}

function tabPillStyle(active) {
  return {
    padding: '8px 14px', borderRadius: 9,
    background: active ? 'var(--ac)' : 'var(--bg-1)',
    color: active ? '#fff' : 'var(--t3)',
    border: `1px solid ${active ? 'var(--ac)' : 'var(--bd-s)'}`,
    fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
    cursor: 'pointer',
    display: 'flex', alignItems: 'center', gap: 5,
  };
}

function ReportCard({ report, onClick }) {
  const typeLabel = report.report_type === 'weekly' ? '주간' : '일일';
  const typeColor = report.report_type === 'weekly'
    ? { bg: '#fef3c7', c: '#b45309' }
    : { bg: '#e0f2fe', c: '#0369a1' };
  const periodLabel = report.period_start === report.period_end
    ? report.period_start
    : `${report.period_start} ~ ${report.period_end}`;
  const summary = report.ai_summary && typeof report.ai_summary === 'object' && report.ai_summary.summary;
  const preview = summary
    ? (summary['핵심 활동'] || Object.values(summary).find(v => v && String(v).trim()) || '')
    : '';
  const sourceCount = (report.source_memo_ids || []).length || (report.source_report_ids || []).length;

  return (
    <div
      onClick={onClick}
      style={{
        padding: '14px 16px', borderRadius: 12,
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
        cursor: 'pointer', transition: 'all .12s',
        scrollSnapAlign: 'start', scrollMarginTop: 60,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6, gap: 8 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{
            padding: '2px 7px', borderRadius: 5,
            background: typeColor.bg, color: typeColor.c,
            fontSize: 9, fontWeight: 800, fontFamily: 'Manrope', letterSpacing: '.05em',
          }}>{typeLabel}</span>
          <span style={{ fontSize: 11, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>{periodLabel}</span>
        </div>
        {sourceCount > 0 && (
          <span style={{ fontSize: 10, color: 'var(--t3)' }}>
            {report.report_type === 'weekly' && report.source_report_ids ? `보고서 ${sourceCount}건` : `메모 ${sourceCount}건`}
          </span>
        )}
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)', marginBottom: 4, lineHeight: 1.35 }}>
        {report.title || `${typeLabel} 보고서`}
      </div>
      {preview && (
        <div style={{
          fontSize: 12, color: 'var(--t2)', lineHeight: 1.5,
          overflow: 'hidden', textOverflow: 'ellipsis',
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
        }}>{String(preview)}</div>
      )}
    </div>
  );
}

function MemoCard({ memo, onClick, checked, onToggleCheck }) {
  const typeTheme = MEMO_TYPE_COLORS[memo.memo_type] || MEMO_TYPE_COLORS.note;
  const hasAi = !!(memo.ai_summary && (
    (typeof memo.ai_summary === 'object' && memo.ai_summary.summary) ||
    (typeof memo.ai_summary === 'string' && memo.ai_summary.trim())
  ));
  return (
    <div
      onClick={onClick}
      style={{
        padding: '14px 16px', borderRadius: 12,
        background: checked ? 'var(--ac-d)' : 'var(--bg-1)',
        border: `1px solid ${checked ? 'var(--ac)' : 'var(--bd-s)'}`,
        cursor: 'pointer', transition: 'all .12s',
        scrollSnapAlign: 'start',
        scrollMarginTop: 60,
        display: 'flex', gap: 12, alignItems: 'flex-start',
      }}
    >
      {onToggleCheck && (
        <input
          type="checkbox"
          checked={!!checked}
          onChange={onToggleCheck}
          onClick={(e) => e.stopPropagation()}
          style={{ marginTop: 4, accentColor: 'var(--ac)', flexShrink: 0, cursor: 'pointer' }}
          aria-label="보고서로 선택"
        />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{
            padding: '2px 7px', borderRadius: 5,
            background: typeTheme.bg, color: typeTheme.c,
            fontSize: 9, fontWeight: 800, fontFamily: 'Manrope', letterSpacing: '.05em',
          }}>
            {MEMO_TYPE_LABEL[memo.memo_type] || 'NOTE'}
          </span>
          {hasAi && (
            <span style={{
              padding: '2px 7px', borderRadius: 5,
              background: 'var(--ac-d)', color: 'var(--ac)',
              fontSize: 9, fontWeight: 800, fontFamily: 'Manrope',
              display: 'flex', alignItems: 'center', gap: 3,
            }}>
              <Sparkles size={9} /> AI
            </span>
          )}
        </div>
        <span style={{ fontSize: 11, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>
          {formatDate(memo.visit_date || memo.created_at)}
        </span>
      </div>
      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)', marginBottom: 4, lineHeight: 1.35 }}>
        {memo.title || (memo.doctor_name ? `${memo.doctor_name} 교수 메모` : '(제목 없음)')}
      </div>
      {(memo.doctor_name || memo.hospital_name) && (
        <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 6 }}>
          {memo.doctor_name && <>{memo.doctor_name}</>}
          {memo.hospital_name && <> · {memo.hospital_name}</>}
          {memo.department && <> · {memo.department}</>}
        </div>
      )}
      <div style={{
        fontSize: 12, color: 'var(--t2)', lineHeight: 1.5,
        overflow: 'hidden', textOverflow: 'ellipsis',
        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
      }}>
        {summaryOneLine(memo) || <span style={{ color: 'var(--t3)', fontStyle: 'italic' }}>내용 없음</span>}
      </div>
      </div>
    </div>
  );
}

function FilterRow({ label, children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 10 }}>
      <div style={{ minWidth: 50, fontSize: 11, fontWeight: 700, color: 'var(--t3)', paddingTop: 7 }}>
        {label}
      </div>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}

function ChipBtn({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: '6px 12px', borderRadius: 6,
      background: active ? 'var(--ac-d)' : 'var(--bg-2)',
      color: active ? 'var(--ac)' : 'var(--t3)',
      border: `1px solid ${active ? 'var(--ac)' : 'var(--bd-s)'}`,
      fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
    }}>
      {children}
    </button>
  );
}

const selectStyle = {
  padding: '7px 10px', borderRadius: 7,
  background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
  fontSize: 12, color: 'var(--t1)', fontFamily: 'inherit',
  outline: 'none',
};
