/**
 * 디자인 일관 alert/confirm 헬퍼.
 * window.alert / window.confirm 대신 사용.
 *
 *   await showAlert('저장 실패: ' + err.message);
 *   const ok = await showConfirm('정말 삭제할까요?', { tone: 'danger', confirmLabel: '삭제' });
 *
 * 옵션:
 *   - tone: 'info' | 'success' | 'warning' | 'danger'
 *   - title: 짧은 제목 (생략 가능)
 *   - confirmLabel / cancelLabel
 */
import { _enqueue } from '../components/Dialog.jsx';

export function showAlert(message, opts = {}) {
  return _enqueue({
    kind: 'alert',
    message: String(message || ''),
    title: opts.title,
    tone: opts.tone || 'info',
    confirmLabel: opts.confirmLabel || '확인',
  });
}

export function showConfirm(message, opts = {}) {
  return _enqueue({
    kind: 'confirm',
    message: String(message || ''),
    title: opts.title,
    tone: opts.tone || 'info',
    confirmLabel: opts.confirmLabel || '확인',
    cancelLabel: opts.cancelLabel || '취소',
  });
}

// 편의: 에러 객체 받아서 alert (메시지 + danger tone)
export function showError(err, opts = {}) {
  const msg = (err && err.message) || String(err) || '오류가 발생했어요.';
  return showAlert(msg, { tone: 'danger', title: opts.title || '오류', ...opts });
}
