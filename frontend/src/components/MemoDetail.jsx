import { useMemo, useRef, useState, useEffect } from 'react';
import {
  ArrowLeft, Copy, FileDown, Edit3, Trash2, RefreshCw, Sparkles, FileText,
} from 'lucide-react';
import { memoApi } from '../api/client';

const MEMO_TYPE_LABEL = { visit: '방문', meeting: '회의록', note: '노트' };

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * 메모 상세 뷰 (Memos 페이지 내부 state 전환용).
 * - 탭: 원본 / AI 정리
 * - 액션: 복사, PDF, 편집, 삭제, 다시 정리
 */
export default function MemoDetail({
  memo,
  onBack,
  onEdit,
  onChanged,   // memo 데이터가 바뀌었을 때 (summarize 재실행, 삭제 후)
}) {
  const [tab, setTab] = useState('raw');
  const [busy, setBusy] = useState(false);
  const [copyMsg, setCopyMsg] = useState(null);
  const [err, setErr] = useState(null);
  const printRef = useRef(null);

  const hasAi = useMemo(() => {
    if (!memo?.ai_summary) return false;
    if (typeof memo.ai_summary === 'string') return memo.ai_summary.trim().length > 0;
    return !!(memo.ai_summary.title || memo.ai_summary.summary);
  }, [memo]);

  useEffect(() => {
    setTab(hasAi ? 'ai' : 'raw');
  }, [memo?.id, hasAi]);

  if (!memo) return null;

  const aiSummary = (() => {
    const raw = memo.ai_summary;
    if (!raw) return null;
    if (typeof raw === 'string') {
      try { return JSON.parse(raw); } catch { return { title: '', summary: {} }; }
    }
    return raw;
  })();

  const copy = async () => {
    const text = tab === 'ai' && hasAi
      ? buildCopyText(memo, aiSummary)
      : memo.raw_memo || '';
    try {
      await navigator.clipboard.writeText(text);
      setCopyMsg('복사됨');
      setTimeout(() => setCopyMsg(null), 1500);
    } catch {
      setCopyMsg('복사 실패');
      setTimeout(() => setCopyMsg(null), 1500);
    }
  };

  const downloadPdf = async () => {
    try {
      const html2pdf = (await import('html2pdf.js')).default;
      const element = printRef.current;
      if (!element) return;
      const filename = `${memo.title || memo.doctor_name || 'memo'}_${formatDate(memo.visit_date)}.pdf`;
      await html2pdf()
        .from(element)
        .set({
          margin: 10,
          filename,
          image: { type: 'jpeg', quality: 0.95 },
          html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff' },
          jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
        })
        .save();
    } catch (e) {
      setErr('PDF 생성 실패: ' + e.message);
    }
  };

  const resummarize = async () => {
    setBusy(true);
    setErr(null);
    try {
      const updated = await memoApi.summarize(memo.id, memo.template_id || null);
      onChanged?.(updated);
      setTab('ai');
    } catch (e) {
      setErr(e.message || 'AI 재정리 실패');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm('이 메모를 삭제하시겠습니까? 복구할 수 없습니다.')) return;
    setBusy(true);
    try {
      await memoApi.remove(memo.id);
      onChanged?.(null);
      onBack?.();
    } catch (e) {
      setErr(e.message || '삭제 실패');
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 720, animation: 'slideR .25s ease' }}>
      {/* 상단 바 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <button onClick={onBack} style={{
          display: 'flex', alignItems: 'center', gap: 4, fontSize: 13,
          color: 'var(--t3)', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit',
        }}>
          <ArrowLeft size={16} /> 목록으로
        </button>
        <div style={{ display: 'flex', gap: 6 }}>
          <IconBtn onClick={copy} title={copyMsg || '복사'}>
            <Copy size={13} /> {copyMsg || '복사'}
          </IconBtn>
          <IconBtn onClick={downloadPdf} title="PDF 다운로드">
            <FileDown size={13} /> PDF
          </IconBtn>
          <IconBtn onClick={() => onEdit?.(memo)} title="편집">
            <Edit3 size={13} /> 편집
          </IconBtn>
          <IconBtn onClick={remove} title="삭제" danger>
            <Trash2 size={13} />
          </IconBtn>
        </div>
      </div>

      {err && (
        <div style={{
          padding: '8px 12px', borderRadius: 8, background: '#fee2e2',
          color: '#b91c1c', fontSize: 12, marginBottom: 10,
        }}>
          {err}
        </div>
      )}

      {/* 헤더 카드 */}
      <div ref={printRef} style={{
        padding: '18px 20px', borderRadius: 14,
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
        marginBottom: 12,
      }}>
        <div style={{ display: 'flex', gap: 7, marginBottom: 8, alignItems: 'center' }}>
          <span style={{
            padding: '3px 8px', borderRadius: 5,
            background: 'var(--ac-d)', color: 'var(--ac)',
            fontSize: 10, fontWeight: 800, fontFamily: 'Manrope', letterSpacing: '.05em',
          }}>
            {MEMO_TYPE_LABEL[memo.memo_type] || '메모'}
          </span>
          <span style={{ fontSize: 11, color: 'var(--t3)' }}>
            {formatDate(memo.visit_date || memo.created_at)}
          </span>
        </div>
        <div style={{ fontFamily: 'Manrope', fontSize: 19, fontWeight: 800, color: 'var(--t1)', lineHeight: 1.35 }}>
          {memo.title || (memo.doctor_name ? `${memo.doctor_name} 교수 메모` : '(제목 없음)')}
        </div>
        {(memo.doctor_name || memo.hospital_name) && (
          <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 5 }}>
            {memo.doctor_name && <>{memo.doctor_name} 교수</>}
            {memo.hospital_name && <> · {memo.hospital_name}</>}
            {memo.department && <> · {memo.department}</>}
          </div>
        )}

        {/* PDF 내 원본/AI 모두 포함 */}
        <div className="pdf-only" style={{ display: 'none', marginTop: 16 }}>
          <h3 style={{ fontSize: 13, margin: '14px 0 6px' }}>원본 메모</h3>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.5 }}>{memo.raw_memo}</pre>
          {hasAi && aiSummary?.summary && (
            <>
              <h3 style={{ fontSize: 13, margin: '14px 0 6px' }}>AI 정리</h3>
              {Object.entries(aiSummary.summary || {}).map(([k, v]) => (
                <div key={k} style={{ fontSize: 12, marginBottom: 4 }}>
                  <b>{k}:</b> {String(v)}
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      {/* 탭 */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
        <TabBtn active={tab === 'ai'} onClick={() => setTab('ai')}>
          <Sparkles size={12} /> AI 정리
          {!hasAi && <span style={{ fontSize: 9, color: 'var(--t3)', marginLeft: 3 }}>(없음)</span>}
        </TabBtn>
        <TabBtn active={tab === 'raw'} onClick={() => setTab('raw')}>
          <FileText size={12} /> 원본
        </TabBtn>
        <div style={{ flex: 1 }} />
        <button
          onClick={resummarize}
          disabled={busy || !memo.raw_memo}
          style={{
            padding: '7px 12px', borderRadius: 7,
            background: 'var(--bg-2)', color: 'var(--t2)',
            border: '1px solid var(--bd-s)', cursor: busy ? 'not-allowed' : 'pointer',
            fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', gap: 4,
            opacity: busy ? .6 : 1,
          }}
        >
          <RefreshCw size={12} /> {hasAi ? '다시 정리' : 'AI로 정리하기'}
        </button>
      </div>

      {/* 탭 본문 */}
      {tab === 'ai' ? (
        hasAi ? (
          <div style={{
            padding: '16px 18px', borderRadius: 12,
            background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
          }}>
            {aiSummary?.summary && typeof aiSummary.summary === 'object' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {Object.entries(aiSummary.summary)
                  .filter(([, v]) => v != null && String(v).trim() !== '')
                  .map(([k, v]) => (
                    <div key={k} style={{
                      display: 'flex', gap: 12, fontSize: 13,
                      paddingBottom: 10, borderBottom: '1px dashed var(--bd-s)',
                    }}>
                      <span style={{
                        minWidth: 100, color: 'var(--t3)', fontWeight: 700,
                        fontSize: 12,
                      }}>{k}</span>
                      <span style={{ color: 'var(--t1)', flex: 1, lineHeight: 1.55 }}>
                        {String(v)}
                      </span>
                    </div>
                  ))}
                {Object.values(aiSummary.summary || {}).every(v => !v || !String(v).trim()) && (
                  <div style={{ fontSize: 12, color: 'var(--t3)', fontStyle: 'italic' }}>
                    AI 정리 결과가 비어 있습니다. 다시 정리를 시도해보세요.
                  </div>
                )}
              </div>
            ) : (
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, color: 'var(--t2)', lineHeight: 1.5 }}>
                {typeof memo.ai_summary === 'string' ? memo.ai_summary : JSON.stringify(memo.ai_summary, null, 2)}
              </pre>
            )}
          </div>
        ) : (
          <div style={{
            padding: '40px 20px', textAlign: 'center',
            background: 'var(--bg-1)', border: '1px dashed var(--bd-s)',
            borderRadius: 12, color: 'var(--t3)', fontSize: 13,
          }}>
            아직 AI 정리 결과가 없습니다.
            <div style={{ fontSize: 11, marginTop: 6 }}>
              상단 "AI로 정리하기"를 눌러 생성하세요.
            </div>
          </div>
        )
      ) : (
        <div style={{
          padding: '16px 18px', borderRadius: 12,
          background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
        }}>
          <pre style={{
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            fontFamily: 'inherit', fontSize: 13, color: 'var(--t1)',
            lineHeight: 1.6, margin: 0,
          }}>
            {memo.raw_memo || '(원본 메모 없음)'}
          </pre>
        </div>
      )}

      <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 10, textAlign: 'right' }}>
        생성: {formatDate(memo.created_at)}
        {memo.updated_at && memo.updated_at !== memo.created_at && (
          <> · 수정: {formatDate(memo.updated_at)}</>
        )}
      </div>
    </div>
  );
}

function buildCopyText(memo, aiSummary) {
  const lines = [];
  if (memo.title) lines.push(memo.title);
  if (memo.doctor_name) lines.push(`${memo.doctor_name} 교수${memo.hospital_name ? ' · ' + memo.hospital_name : ''}`);
  if (memo.visit_date) lines.push(formatDate(memo.visit_date));
  lines.push('');
  if (aiSummary?.summary && typeof aiSummary.summary === 'object') {
    Object.entries(aiSummary.summary).forEach(([k, v]) => {
      if (v != null && String(v).trim() !== '') lines.push(`${k}: ${v}`);
    });
  }
  return lines.join('\n');
}

function IconBtn({ children, onClick, danger }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '7px 11px', borderRadius: 8,
        background: danger ? '#fee2e2' : 'var(--bg-2)',
        color: danger ? '#b91c1c' : 'var(--t2)',
        border: `1px solid ${danger ? '#fca5a5' : 'var(--bd-s)'}`,
        fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
      }}
    >
      {children}
    </button>
  );
}

function TabBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '8px 14px', borderRadius: 8,
        background: active ? 'var(--ac-d)' : 'var(--bg-2)',
        color: active ? 'var(--ac)' : 'var(--t3)',
        border: `1px solid ${active ? 'var(--ac)' : 'var(--bd-s)'}`,
        fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
        display: 'flex', alignItems: 'center', gap: 5,
      }}
    >
      {children}
    </button>
  );
}
