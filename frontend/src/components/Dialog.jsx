import { useEffect, useState, useCallback, useRef } from 'react';
import { AlertCircle, CheckCircle2, AlertTriangle, X } from 'lucide-react';

/**
 * 디자인 일관 alert/confirm 다이얼로그.
 *
 * 사용법:
 *   import { showAlert, showConfirm } from '../utils/dialog';
 *   await showAlert('저장 실패: 메시지');
 *   const ok = await showConfirm('정말 삭제할까요?', { tone: 'danger' });
 *
 * App 최상위에 <DialogHost /> 한 번만 마운트하면 됨. 모듈 레벨 setter 로
 * Promise 기반 imperative API 노출.
 */

let _setQueue = null;
let _idSeq = 1;

const TONE_THEME = {
  info:    { color: '#0369a1', bg: '#e0f2fe', border: '#7dd3fc', icon: AlertCircle },
  success: { color: '#166534', bg: '#dcfce7', border: '#86efac', icon: CheckCircle2 },
  warning: { color: '#b45309', bg: '#fef3c7', border: '#fcd34d', icon: AlertTriangle },
  danger:  { color: '#b91c1c', bg: '#fee2e2', border: '#fca5a5', icon: AlertTriangle },
};

export function _enqueue(item) {
  if (!_setQueue) {
    // Provider 마운트 전 호출되면 native fallback (개발 단계 안전망)
    if (item.kind === 'confirm') return Promise.resolve(window.confirm(item.message));
    window.alert(item.message);
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    _setQueue((q) => [...q, { ...item, id: _idSeq++, resolve }]);
  });
}

export default function DialogHost() {
  const [queue, setQueue] = useState([]);
  const lastFocusRef = useRef(null);

  useEffect(() => {
    _setQueue = setQueue;
    return () => { _setQueue = null; };
  }, []);

  const close = useCallback((id, value) => {
    setQueue((q) => {
      const item = q.find((it) => it.id === id);
      if (item) item.resolve(value);
      return q.filter((it) => it.id !== id);
    });
  }, []);

  const top = queue[0];

  // ESC 닫기 + 첫 버튼 자동 포커스
  useEffect(() => {
    if (!top) return;
    lastFocusRef.current = document.activeElement;
    const onKey = (e) => {
      if (e.key === 'Escape') close(top.id, top.kind === 'confirm' ? false : undefined);
      if (e.key === 'Enter' && top.kind !== 'confirm') close(top.id, undefined);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      try { lastFocusRef.current?.focus?.(); } catch { /* ignore */ }
    };
  }, [top, close]);

  if (!top) return null;
  const theme = TONE_THEME[top.tone] || TONE_THEME.info;
  const Icon = theme.icon;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
        zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16, animation: 'fadeIn .15s ease', fontFamily: 'inherit',
      }}
      onClick={(e) => {
        // backdrop 클릭 — alert 만 닫기 (confirm 은 명시적 선택 필요)
        if (e.target === e.currentTarget && top.kind !== 'confirm') close(top.id, undefined);
      }}
    >
      <div style={{
        background: 'var(--bg-1)', borderRadius: 14,
        width: 380, maxWidth: '100%',
        boxShadow: '0 12px 40px rgba(0,0,0,.18)',
        animation: 'fadeUp .18s ease',
        overflow: 'hidden',
      }}>
        <div style={{
          display: 'flex', gap: 12, padding: '18px 18px 6px',
          alignItems: 'flex-start',
        }}>
          <div style={{
            flexShrink: 0, width: 36, height: 36, borderRadius: 10,
            background: theme.bg, color: theme.color,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon size={18} />
          </div>
          <div style={{ flex: 1, minWidth: 0, paddingTop: 4 }}>
            {top.title && (
              <div style={{
                fontSize: 14, fontWeight: 800, color: 'var(--t1)', marginBottom: 4,
              }}>
                {top.title}
              </div>
            )}
            <div style={{
              fontSize: 13, color: 'var(--t2)', lineHeight: 1.55,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>
              {top.message}
            </div>
          </div>
          {top.kind !== 'confirm' && (
            <button
              type="button"
              onClick={() => close(top.id, undefined)}
              aria-label="닫기"
              style={{
                background: 'transparent', border: 'none', cursor: 'pointer',
                color: 'var(--t3)', padding: 0, marginLeft: 4,
              }}
            >
              <X size={16} />
            </button>
          )}
        </div>
        <div style={{
          padding: '14px 18px 18px', display: 'flex',
          gap: 8, justifyContent: 'flex-end',
        }}>
          {top.kind === 'confirm' && (
            <button
              type="button"
              onClick={() => close(top.id, false)}
              style={{
                padding: '9px 16px', borderRadius: 9,
                background: 'var(--bg-2)', color: 'var(--t2)',
                border: '1px solid var(--bd-s)', cursor: 'pointer',
                fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
              }}
            >
              {top.cancelLabel || '취소'}
            </button>
          )}
          <button
            type="button"
            autoFocus
            onClick={() => close(top.id, top.kind === 'confirm' ? true : undefined)}
            style={{
              padding: '9px 18px', borderRadius: 9,
              background: top.tone === 'danger' ? '#b91c1c' : 'var(--ac)',
              color: '#fff', border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: 800, fontFamily: 'inherit',
              boxShadow: '0 2px 8px rgba(0,0,0,.12)',
            }}
          >
            {top.confirmLabel || '확인'}
          </button>
        </div>
      </div>
    </div>
  );
}
