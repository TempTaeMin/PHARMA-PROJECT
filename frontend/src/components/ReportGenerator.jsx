import { useEffect, useMemo, useState } from 'react';
import { X, Sparkles, RefreshCw, FileText, Calendar, Check, LayoutTemplate } from 'lucide-react';
import { memoApi, reportApi, memoTemplateApi } from '../api/client';

/**
 * 일일/주간 보고서 생성 모달.
 * - mode='daily-from-memos': 미리 선택한 memo_ids 로 바로 생성 진입
 * - mode='daily': 날짜 선택 → 그 날 메모 자동 로드 → 체크박스 선택
 * - mode='weekly': 기간 선택 + 방식(메모 직접 / 일일 보고서 합치기) 라디오
 */
export default function ReportGenerator({
  open,
  mode = 'daily',
  presetDate = null,
  presetMemoIds = null,
  onClose,
  onCreated,
  onOpenReport,
}) {
  const [date, setDate] = useState(presetDate || todayYMD());
  const [weekStart, setWeekStart] = useState(monday(presetDate || todayYMD()));
  const [weekEnd, setWeekEnd] = useState(sunday(presetDate || todayYMD()));
  const [weeklyMode, setWeeklyMode] = useState('memos'); // 'memos' | 'reports'

  const [memos, setMemos] = useState([]);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());

  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState(null);  // null = 기본 (템플릿 없음)
  const [templateAutoApplied, setTemplateAutoApplied] = useState(false);

  // 모달 열릴 때 초기화
  useEffect(() => {
    if (!open) return;
    setDate(presetDate || todayYMD());
    setWeekStart(monday(presetDate || todayYMD()));
    setWeekEnd(sunday(presetDate || todayYMD()));
    setWeeklyMode('memos');
    setError(null);
    setResult(null);
    setTemplateId(null);
    setTemplateAutoApplied(false);
    if (mode === 'daily-from-memos' && presetMemoIds && presetMemoIds.length > 0) {
      setSelectedIds(new Set(presetMemoIds));
    } else {
      setSelectedIds(new Set());
    }
  }, [open, mode, presetDate, presetMemoIds]);

  // 보고서 템플릿 목록 로드 (모달 열릴 때 1회)
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await memoTemplateApi.list({ scope: 'report' });
        if (cancelled) return;
        setTemplates(list || []);
      } catch (e) {
        // 템플릿 로드 실패는 치명적이지 않음 (그냥 기본으로 진행)
        if (!cancelled) setTemplates([]);
      }
    })();
    return () => { cancelled = true; };
  }, [open]);

  // 현재 모드(일일/주간)에 맞는 default_report_type 템플릿 자동 추천
  // (사용자가 한 번이라도 직접 선택했으면 덮어쓰지 않음)
  useEffect(() => {
    if (!open || templateAutoApplied) return;
    if (templates.length === 0) return;
    const wantType = mode === 'weekly' ? 'weekly' : 'daily';
    const preferred = templates.find(t => t.default_report_type === wantType);
    if (preferred) {
      setTemplateId(preferred.id);
      setTemplateAutoApplied(true);
    }
  }, [open, templates, mode, templateAutoApplied]);

  // 데이터 로드
  useEffect(() => {
    if (!open) return;
    if (result) return; // 이미 생성 완료 상태면 재로드 안 함
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        if (mode === 'weekly' && weeklyMode === 'reports') {
          const list = await reportApi.list({ from: weekStart, to: weekEnd, type: 'daily' });
          if (!cancelled) {
            setReports(list || []);
            setSelectedIds(new Set((list || []).map(r => r.id)));
          }
        } else {
          // 일일 또는 주간-메모 직접 모드
          const from = mode === 'weekly' ? weekStart : date;
          const to = mode === 'weekly' ? weekEnd : date;
          const list = await memoApi.list({ from, to });
          if (!cancelled) {
            setMemos(list || []);
            // daily-from-memos 모드면 presetMemoIds 유지, 아니면 전체 선택
            if (mode === 'daily-from-memos' && presetMemoIds && presetMemoIds.length > 0) {
              setSelectedIds(new Set(presetMemoIds));
            } else {
              setSelectedIds(new Set((list || []).map(m => m.id)));
            }
          }
        }
      } catch (e) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, mode, date, weekStart, weekEnd, weeklyMode, presetMemoIds, result]);

  if (!open) return null;

  const isWeekly = mode === 'weekly';
  const useReports = isWeekly && weeklyMode === 'reports';
  const items = useReports ? reports : memos;
  const selectedCount = selectedIds.size;

  const toggle = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const selectAll = () => setSelectedIds(new Set(items.map(it => it.id)));
  const selectNone = () => setSelectedIds(new Set());

  const handleGenerate = async () => {
    if (selectedCount === 0) {
      setError('최소 1개 이상을 선택하세요.');
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const ids = Array.from(selectedIds);
      const payload = {
        report_type: isWeekly ? 'weekly' : 'daily',
        period_start: isWeekly ? weekStart : date,
        period_end: isWeekly ? weekEnd : date,
        memo_ids: useReports ? null : ids,
        report_ids: useReports ? ids : null,
        template_id: templateId || null,
      };
      const r = await reportApi.create(payload);
      setResult(r);
      onCreated?.(r);
    } catch (e) {
      setError(e.message || '보고서 생성 실패');
    } finally {
      setGenerating(false);
    }
  };

  const headerLabel = isWeekly ? '주간 보고서 만들기' : '일일 보고서 만들기';

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 380,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16, animation: 'fadeIn .18s ease',
    }}>
      <div style={{
        background: 'var(--bg-1)', borderRadius: 14,
        width: 640, maxWidth: '100%', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
        animation: 'fadeUp .2s ease',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 16px', borderBottom: '1px solid var(--bd-s)',
          flexShrink: 0,
        }}>
          <FileText size={18} style={{ color: 'var(--ac)' }} />
          <div style={{ flex: 1, fontFamily: 'Manrope', fontSize: 16, fontWeight: 800, color: 'var(--t1)' }}>
            {headerLabel}
          </div>
          <button onClick={onClose} aria-label="닫기" style={iconCloseBtn}>
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px' }}>
          {result ? (
            <ResultView result={result} onOpenReport={onOpenReport} />
          ) : (
            <>
              {/* 기간/방식 선택 */}
              {isWeekly ? (
                <>
                  <SectionLabel>기간</SectionLabel>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14 }}>
                    <input type="date" value={weekStart} onChange={e => setWeekStart(e.target.value)} style={dateInput} />
                    <span style={{ color: 'var(--t3)', fontSize: 12 }}>~</span>
                    <input type="date" value={weekEnd} onChange={e => setWeekEnd(e.target.value)} style={dateInput} />
                    <button
                      onClick={() => { const t = todayYMD(); setWeekStart(monday(t)); setWeekEnd(sunday(t)); }}
                      style={miniBtn}
                    >이번 주</button>
                  </div>

                  <SectionLabel>방식</SectionLabel>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
                    <RadioRow
                      checked={weeklyMode === 'memos'}
                      onChange={() => setWeeklyMode('memos')}
                      label="메모에서 직접 종합"
                      desc="이 기간의 모든 메모를 모아 AI 가 한 번에 정리합니다."
                    />
                    <RadioRow
                      checked={weeklyMode === 'reports'}
                      onChange={() => setWeeklyMode('reports')}
                      label="일일 보고서들 합치기"
                      desc="이 기간에 이미 만든 일일 보고서들을 합쳐 주간 종합으로 만듭니다."
                    />
                  </div>
                </>
              ) : (
                <>
                  <SectionLabel>날짜</SectionLabel>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14 }}>
                    <input type="date" value={date} onChange={e => setDate(e.target.value)} style={dateInput} />
                    <button onClick={() => setDate(todayYMD())} style={miniBtn}>오늘</button>
                  </div>
                </>
              )}

              {/* 보고서 템플릿 (선택) */}
              <SectionLabel>보고서 양식</SectionLabel>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 14 }}>
                <LayoutTemplate size={14} style={{ color: 'var(--t3)', flexShrink: 0 }} />
                <select
                  value={templateId || ''}
                  onChange={(e) => {
                    setTemplateId(e.target.value ? Number(e.target.value) : null);
                    setTemplateAutoApplied(true);
                  }}
                  style={{
                    flex: 1, padding: '7px 10px', borderRadius: 7,
                    background: 'var(--bg-2)', border: '1px solid var(--bd)',
                    fontSize: 12, color: 'var(--t1)', fontFamily: 'inherit', outline: 'none',
                  }}
                >
                  <option value="">기본 양식 ({isWeekly ? '주간 표준' : '일일 표준'})</option>
                  {templates.map(t => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                      {t.default_report_type ? ` · ${t.default_report_type === 'weekly' ? '주간' : '일일'} 추천` : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* 항목 선택 */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <SectionLabel>{useReports ? '일일 보고서' : '메모'} ({selectedCount}/{items.length})</SectionLabel>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button onClick={selectAll} style={miniBtn}>전체 선택</button>
                  <button onClick={selectNone} style={miniBtn}>해제</button>
                </div>
              </div>

              {loading ? (
                <div style={{ textAlign: 'center', padding: 30, color: 'var(--t3)', fontSize: 12 }}>불러오는 중…</div>
              ) : items.length === 0 ? (
                <div style={{
                  padding: 30, textAlign: 'center', borderRadius: 10,
                  background: 'var(--bg-2)', border: '1px dashed var(--bd-s)',
                  color: 'var(--t3)', fontSize: 12,
                }}>
                  {useReports ? '이 기간에 만든 일일 보고서가 없습니다.' : '이 기간에 작성된 메모가 없습니다.'}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
                  {items.map(it => (
                    <ItemRow
                      key={it.id}
                      item={it}
                      isReport={useReports}
                      checked={selectedIds.has(it.id)}
                      onToggle={() => toggle(it.id)}
                    />
                  ))}
                </div>
              )}

              {error && (
                <div style={{
                  padding: '10px 12px', borderRadius: 8,
                  background: '#fee2e2', color: '#b91c1c',
                  fontSize: 12, marginTop: 6,
                }}>{error}</div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 16px 16px', borderTop: '1px solid var(--bd-s)', flexShrink: 0,
          display: 'flex', gap: 8, justifyContent: 'flex-end',
        }}>
          {result ? (
            <>
              <button onClick={onClose} style={btnGhost}>닫기</button>
              <button onClick={() => onOpenReport?.(result)} style={btnPrimary}>
                <FileText size={14} /> 보고서 보기
              </button>
            </>
          ) : (
            <>
              <button onClick={onClose} style={btnGhost}>취소</button>
              <button
                onClick={handleGenerate}
                disabled={generating || selectedCount === 0}
                style={{ ...btnPrimary, opacity: (generating || selectedCount === 0) ? .5 : 1, cursor: (generating || selectedCount === 0) ? 'not-allowed' : 'pointer' }}
              >
                {generating ? <><RefreshCw size={14} style={{ animation: 'spin .8s linear infinite' }} /> 생성 중…</> : <><Sparkles size={14} /> AI 보고서 생성</>}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ItemRow({ item, isReport, checked, onToggle }) {
  const title = isReport
    ? (item.title || `${item.report_type} 보고서`)
    : (item.title || (item.doctor_name ? `${item.doctor_name} 방문` : '제목 없음'));
  const sub = isReport
    ? `${item.period_start}${item.period_end !== item.period_start ? ` ~ ${item.period_end}` : ''}`
    : `${formatDate(item.visit_date)}${item.hospital_name ? ` · ${item.hospital_name}` : ''}${item.department ? ` · ${item.department}` : ''}`;
  const preview = isReport
    ? aiPreview(item.ai_summary)
    : aiPreview(item.ai_summary) || (item.raw_memo || '').slice(0, 90);

  return (
    <label style={{
      display: 'flex', alignItems: 'flex-start', gap: 10,
      padding: '10px 12px', borderRadius: 9,
      background: checked ? 'var(--ac-d)' : 'var(--bg-2)',
      border: `1px solid ${checked ? 'var(--ac)' : 'var(--bd-s)'}`,
      cursor: 'pointer', transition: 'background .12s, border-color .12s',
    }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        style={{ marginTop: 3, accentColor: 'var(--ac)', flexShrink: 0 }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)', marginBottom: 2 }}>{title}</div>
        <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 4 }}>{sub}</div>
        {preview && (
          <div style={{
            fontSize: 11, color: 'var(--t2)', lineHeight: 1.4,
            overflow: 'hidden', textOverflow: 'ellipsis',
            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
          }}>{preview}</div>
        )}
      </div>
    </label>
  );
}

function RadioRow({ checked, onChange, label, desc }) {
  return (
    <label style={{
      display: 'flex', alignItems: 'flex-start', gap: 10,
      padding: '10px 12px', borderRadius: 9,
      background: checked ? 'var(--ac-d)' : 'var(--bg-2)',
      border: `1px solid ${checked ? 'var(--ac)' : 'var(--bd-s)'}`,
      cursor: 'pointer',
    }}>
      <input type="radio" checked={checked} onChange={onChange} style={{ marginTop: 3, accentColor: 'var(--ac)', flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>{label}</div>
        <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>{desc}</div>
      </div>
    </label>
  );
}

function ResultView({ result, onOpenReport }) {
  const summary = (result.ai_summary && typeof result.ai_summary === 'object' && result.ai_summary.summary) || {};
  return (
    <div>
      <div style={{
        padding: '10px 12px', borderRadius: 8, marginBottom: 12,
        background: 'var(--gn-d)', border: '1px solid var(--gn)',
        color: 'var(--gn)', fontSize: 12, fontWeight: 700,
        display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <Check size={14} /> 보고서 생성 완료
      </div>
      {result.title && (
        <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--t1)', marginBottom: 10 }}>{result.title}</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {Object.entries(summary).filter(([, v]) => v && String(v).trim()).map(([k, v]) => (
          <div key={k} style={{
            padding: '10px 12px', borderRadius: 8,
            background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
          }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--t3)', marginBottom: 4 }}>{k}</div>
            <div style={{ fontSize: 12, color: 'var(--t1)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{String(v)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Helpers ───
function todayYMD() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function monday(ymd) {
  const d = new Date(ymd + 'T00:00:00');
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function sunday(ymd) {
  const d = new Date(monday(ymd) + 'T00:00:00');
  d.setDate(d.getDate() + 6);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}

function aiPreview(ai) {
  if (!ai) return null;
  let obj = ai;
  if (typeof ai === 'string') {
    try { obj = JSON.parse(ai); } catch { return ai.slice(0, 100); }
  }
  if (typeof obj !== 'object') return null;
  const s = obj.summary || obj;
  if (typeof s !== 'object') return String(s).slice(0, 100);
  const pref = s['결과'] || s['논의내용'] || s['핵심 활동'] || s['요약'];
  if (pref && String(pref).trim()) return String(pref);
  const first = Object.values(s).find(v => v && String(v).trim());
  return first ? String(first) : null;
}

const dateInput = {
  padding: '7px 10px', borderRadius: 7,
  background: 'var(--bg-2)', border: '1px solid var(--bd)',
  fontSize: 12, color: 'var(--t1)', fontFamily: 'inherit', outline: 'none',
};
const miniBtn = {
  padding: '6px 10px', borderRadius: 7,
  background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
  fontSize: 11, fontWeight: 600, color: 'var(--t2)',
  cursor: 'pointer', fontFamily: 'inherit',
};
const btnGhost = {
  padding: '9px 16px', borderRadius: 8, background: 'var(--bg-2)',
  color: 'var(--t2)', border: '1px solid var(--bd)',
  fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
};
const btnPrimary = {
  padding: '9px 16px', borderRadius: 8, background: 'var(--ac)',
  color: '#fff', border: 'none',
  fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
  display: 'flex', alignItems: 'center', gap: 5,
};
const iconCloseBtn = {
  width: 30, height: 30, border: '1px solid var(--bd-s)', borderRadius: 7,
  background: 'var(--bg-2)', color: 'var(--t3)', cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
};

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 800, color: 'var(--t3)',
      letterSpacing: '.04em', marginBottom: 6,
    }}>{children}</div>
  );
}
