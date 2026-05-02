import { useRef, useState } from 'react';
import { X, Copy, FileDown, Trash2, RefreshCw, Sparkles, FileText, FileType } from 'lucide-react';
import { reportApi } from '../api/client';

/**
 * 보고서 상세 모달.
 * 탭: 종합(AI) / 원본(raw_combined)
 * 액션: 복사, PDF 다운로드, AI 재정리, 삭제
 */
export default function ReportDetail({ open, report, onClose, onChanged }) {
  const [tab, setTab] = useState('ai');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [copyMsg, setCopyMsg] = useState(null);
  const printRef = useRef(null);

  if (!open || !report) return null;

  const summary = (report.ai_summary && typeof report.ai_summary === 'object' && report.ai_summary.summary) || {};
  const periodLabel = report.period_start === report.period_end
    ? report.period_start
    : `${report.period_start} ~ ${report.period_end}`;
  const typeLabel = report.report_type === 'weekly' ? '주간' : '일일';

  const copy = async () => {
    try {
      const lines = [];
      if (report.title) lines.push(`# ${report.title}`);
      lines.push(`기간: ${periodLabel}`);
      lines.push('');
      Object.entries(summary).filter(([, v]) => v && String(v).trim()).forEach(([k, v]) => {
        lines.push(`## ${k}`);
        lines.push(String(v));
        lines.push('');
      });
      await navigator.clipboard.writeText(lines.join('\n'));
      setCopyMsg('복사됨');
      setTimeout(() => setCopyMsg(null), 1500);
    } catch {
      setCopyMsg('복사 실패');
      setTimeout(() => setCopyMsg(null), 1500);
    }
  };

  const downloadDocx = () => {
    // 백엔드가 Content-Disposition 헤더로 파일명 지정 → <a download> 만 트리거
    const a = document.createElement('a');
    a.href = reportApi.docxUrl(report.id);
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const downloadPdf = async () => {
    try {
      const html2pdf = (await import('html2pdf.js')).default;
      const element = printRef.current;
      if (!element) return;
      const filename = `${typeLabel}보고서_${report.period_start}${report.period_end !== report.period_start ? `_${report.period_end}` : ''}.pdf`;
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

  const regenerate = async () => {
    setBusy(true); setErr(null);
    try {
      const updated = await reportApi.regenerate(report.id);
      onChanged?.(updated);
      setTab('ai');
    } catch (e) {
      setErr(e.message || 'AI 재정리 실패');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm('이 보고서를 삭제하시겠습니까?')) return;
    setBusy(true);
    try {
      await reportApi.remove(report.id);
      onChanged?.(null);
      onClose?.();
    } catch (e) {
      setErr(e.message || '삭제 실패');
      setBusy(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 380,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16, animation: 'fadeIn .18s ease',
    }}>
      <div style={{
        background: 'var(--bg-1)', borderRadius: 14,
        width: 720, maxWidth: '100%', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
        animation: 'fadeUp .2s ease',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 16px', borderBottom: '1px solid var(--bd-s)', flexShrink: 0,
        }}>
          <FileText size={18} style={{ color: 'var(--ac)' }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: 'Manrope', fontSize: 15, fontWeight: 800, color: 'var(--t1)', lineHeight: 1.3 }}>
              {report.title || `${typeLabel} 보고서`}
            </div>
            <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>
              {typeLabel} · {periodLabel}
            </div>
          </div>
          <button onClick={onClose} aria-label="닫기" style={iconCloseBtn}>
            <X size={14} />
          </button>
        </div>

        {/* 액션바 */}
        <div style={{
          display: 'flex', gap: 6, padding: '10px 16px',
          borderBottom: '1px solid var(--bd-s)', flexShrink: 0, flexWrap: 'wrap',
        }}>
          <ActionBtn onClick={copy}><Copy size={12} /> {copyMsg || '복사'}</ActionBtn>
          <ActionBtn onClick={downloadDocx}><FileType size={12} /> DOCX</ActionBtn>
          <ActionBtn onClick={downloadPdf}><FileDown size={12} /> PDF</ActionBtn>
          <ActionBtn onClick={regenerate} disabled={busy}>
            {busy ? <RefreshCw size={12} style={{ animation: 'spin .8s linear infinite' }} /> : <Sparkles size={12} />} AI 재정리
          </ActionBtn>
          <div style={{ flex: 1 }} />
          <ActionBtn onClick={remove} disabled={busy} danger><Trash2 size={12} /> 삭제</ActionBtn>
        </div>

        {/* 탭 */}
        <div style={{
          display: 'flex', gap: 4, padding: '8px 16px 0', borderBottom: '1px solid var(--bd-s)', flexShrink: 0,
        }}>
          <TabBtn active={tab === 'ai'} onClick={() => setTab('ai')}>종합 정리</TabBtn>
          <TabBtn active={tab === 'raw'} onClick={() => setTab('raw')}>원본 (묶인 메모)</TabBtn>
        </div>

        {err && (
          <div style={{
            margin: '10px 16px 0', padding: '8px 12px', borderRadius: 8,
            background: '#fee2e2', color: '#b91c1c', fontSize: 12,
          }}>{err}</div>
        )}

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px' }}>
          {tab === 'ai' ? (
            <div ref={printRef} style={{ background: 'var(--bg-1)' }}>
              {report.title && (
                <div style={{
                  fontFamily: 'Manrope', fontSize: 18, fontWeight: 800,
                  color: 'var(--t1)', marginBottom: 10, lineHeight: 1.35,
                }}>{report.title}</div>
              )}
              <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 14 }}>
                {typeLabel} 보고서 · {periodLabel}
              </div>
              {Object.keys(summary).length === 0 ? (
                <div style={{ padding: 30, textAlign: 'center', color: 'var(--t3)', fontSize: 12 }}>
                  AI 정리 결과가 없습니다.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {Object.entries(summary).filter(([, v]) => v && String(v).trim()).map(([k, v]) => (
                    <div key={k} style={{
                      padding: '12px 14px', borderRadius: 10,
                      background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
                    }}>
                      <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--t3)', marginBottom: 6, letterSpacing: '.04em' }}>{k}</div>
                      <div style={{ fontSize: 13, color: 'var(--t1)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{String(v)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <pre style={{
              margin: 0, padding: '12px 14px', borderRadius: 10,
              background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11, color: 'var(--t2)', lineHeight: 1.6,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>{report.raw_combined || '(원본 데이터 없음)'}</pre>
          )}
        </div>
      </div>
    </div>
  );
}

function ActionBtn({ children, onClick, disabled, danger }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: '6px 11px', borderRadius: 7,
      background: danger ? '#fee2e2' : 'var(--bg-2)',
      color: danger ? '#b91c1c' : 'var(--t2)',
      border: `1px solid ${danger ? '#fca5a5' : 'var(--bd-s)'}`,
      fontSize: 11, fontWeight: 700, cursor: disabled ? 'not-allowed' : 'pointer',
      fontFamily: 'inherit',
      display: 'flex', alignItems: 'center', gap: 4,
      opacity: disabled ? .6 : 1,
    }}>{children}</button>
  );
}

function TabBtn({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: '7px 14px', borderRadius: '7px 7px 0 0',
      background: active ? 'var(--bg-1)' : 'transparent',
      color: active ? 'var(--ac)' : 'var(--t3)',
      border: 'none',
      borderBottom: active ? '2px solid var(--ac)' : '2px solid transparent',
      fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
      marginBottom: -1,
    }}>{children}</button>
  );
}

const iconCloseBtn = {
  width: 30, height: 30, border: '1px solid var(--bd-s)', borderRadius: 7,
  background: 'var(--bg-2)', color: 'var(--t3)', cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
};
