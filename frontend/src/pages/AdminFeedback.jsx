import { useEffect, useState, useCallback } from 'react';
import { Inbox, RefreshCw, Bug, Lightbulb, MessageCircle, CheckCircle2, Trash2, Circle, Globe } from 'lucide-react';
import { feedbackApi } from '../api/client';
import { showConfirm, showError } from '../utils/dialog';

const FILTERS = [
  { key: 'unread', label: '미처리', handled: false, category: null },
  { key: 'all', label: '전체', handled: null, category: null },
  { key: 'bug', label: '버그', handled: null, category: 'bug' },
  { key: 'suggestion', label: '제안', handled: null, category: 'suggestion' },
  { key: 'other', label: '기타', handled: null, category: 'other' },
];

const CATEGORY_META = {
  bug: { label: '버그', Icon: Bug, color: '#dc2626', bg: '#fee2e2' },
  suggestion: { label: '제안', Icon: Lightbulb, color: '#2563eb', bg: '#dbeafe' },
  other: { label: '기타', Icon: MessageCircle, color: '#6b7280', bg: '#f3f4f6' },
};

function formatRelative(iso) {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.floor((now - t) / 1000);
  if (diff < 60) return `${diff}초 전`;
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  if (diff < 2592000) return `${Math.floor(diff / 86400)}일 전`;
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * 베타 테스터들이 보낸 피드백을 모아 보는 admin 전용 페이지.
 * 사이드바 "피드백 관리" 메뉴에서 진입.
 */
export default function AdminFeedback({ onSummaryChange }) {
  const [filterKey, setFilterKey] = useState('unread');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState({ total: 0, unread_count: 0, by_category: {} });

  const filter = FILTERS.find(f => f.key === filterKey) || FILTERS[0];

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filter.handled !== null) params.handled = filter.handled;
      if (filter.category) params.category = filter.category;
      const [list, sum] = await Promise.all([
        feedbackApi.list({ ...params, limit: 100 }),
        feedbackApi.summary(),
      ]);
      setItems(Array.isArray(list) ? list : []);
      setSummary(sum);
      onSummaryChange?.(sum.unread_count || 0);
    } catch (e) {
      showError(e, { title: '불러오기 실패' });
    } finally {
      setLoading(false);
    }
  }, [filter.handled, filter.category, onSummaryChange]);

  useEffect(() => { refresh(); }, [refresh]);

  const toggleHandled = async (fb) => {
    try {
      await feedbackApi.setHandled(fb.id, !fb.handled);
      refresh();
    } catch (e) {
      showError(e, { title: '처리 상태 변경 실패' });
    }
  };

  const removeOne = async (fb) => {
    const ok = await showConfirm(
      `이 피드백을 삭제하시겠습니까?\n\n"${fb.message.slice(0, 50)}${fb.message.length > 50 ? '…' : ''}"`,
      { tone: 'danger', confirmLabel: '삭제', cancelLabel: '취소' }
    );
    if (!ok) return;
    try {
      await feedbackApi.remove(fb.id);
      refresh();
    } catch (e) {
      showError(e, { title: '삭제 실패' });
    }
  };

  return (
    <div style={{ maxWidth: 880 }}>
      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <Inbox size={20} style={{ color: 'var(--ac)' }} />
        <h2 style={{ fontFamily: 'Outfit', fontSize: 22, fontWeight: 700 }}>피드백 관리</h2>
      </div>
      <div style={{ fontSize: 12, color: 'var(--t3)', marginBottom: 16 }}>
        총 {summary.total}건 · 미처리 {summary.unread_count}건 (버그 {summary.by_category?.bug || 0} · 제안 {summary.by_category?.suggestion || 0} · 기타 {summary.by_category?.other || 0})
      </div>

      {/* 필터 + 새로고침 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
        marginBottom: 14, padding: 4, background: 'var(--bg-1)',
        border: '1px solid var(--bd-s)', borderRadius: 10,
      }}>
        {FILTERS.map(f => (
          <button
            key={f.key}
            onClick={() => setFilterKey(f.key)}
            style={{
              padding: '7px 13px', borderRadius: 7, border: 'none',
              background: filterKey === f.key ? 'var(--ac-d)' : 'transparent',
              color: filterKey === f.key ? 'var(--ac)' : 'var(--t3)',
              fontWeight: filterKey === f.key ? 700 : 500,
              fontSize: 12, fontFamily: 'inherit', cursor: 'pointer',
            }}
          >
            {f.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button
          onClick={refresh}
          disabled={loading}
          style={{
            padding: '6px 11px', borderRadius: 7,
            background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
            color: 'var(--t2)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
            display: 'inline-flex', alignItems: 'center', gap: 4,
            opacity: loading ? 0.6 : 1,
          }}
        >
          <RefreshCw size={12} style={loading ? { animation: 'spin .8s linear infinite' } : {}} />
          새로고침
        </button>
      </div>

      {/* 리스트 */}
      {loading && items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)' }}>로딩 중…</div>
      ) : items.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 60, color: 'var(--t3)', fontSize: 13,
          background: 'var(--bg-1)', border: '1px dashed var(--bd-s)', borderRadius: 12,
        }}>
          {filterKey === 'unread' ? '미처리 피드백이 없어요. 깔끔!' : '해당 항목 없음'}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(fb => {
            const meta = CATEGORY_META[fb.category] || CATEGORY_META.other;
            const Icon = meta.Icon;
            return (
              <article key={fb.id} style={{
                padding: 14, borderRadius: 11,
                background: 'var(--bg-1)',
                border: `1px solid ${fb.handled ? 'var(--bd-s)' : meta.color + '40'}`,
                opacity: fb.handled ? 0.65 : 1,
              }}>
                {/* 헤더 — 카테고리 + 작성자 + 시간 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    padding: '3px 8px', borderRadius: 6,
                    background: meta.bg, color: meta.color,
                    fontSize: 10, fontWeight: 700, letterSpacing: '.02em',
                  }}>
                    <Icon size={11} /> {meta.label}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--t1)' }}>
                    {fb.user_name || '익명'}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--t3)' }}>
                    {fb.user_email || ''}
                  </span>
                  <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>
                    {formatRelative(fb.created_at)}
                  </span>
                </div>

                {/* 메시지 */}
                <div style={{
                  fontSize: 13, color: 'var(--t1)', lineHeight: 1.55,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  padding: '8px 10px', borderRadius: 7,
                  background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
                  marginBottom: 8,
                }}>
                  {fb.message}
                </div>

                {/* 메타 — 페이지 + user-agent */}
                {(fb.page_path || fb.user_agent) && (
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
                    fontSize: 10, color: 'var(--t3)', marginBottom: 8,
                  }}>
                    {fb.page_path && (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                        <Globe size={10} /> {fb.page_path}
                      </span>
                    )}
                    {fb.user_agent && (
                      <span style={{
                        maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }} title={fb.user_agent}>
                        {fb.user_agent}
                      </span>
                    )}
                  </div>
                )}

                {/* 액션 */}
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={() => toggleHandled(fb)}
                    style={{
                      padding: '6px 11px', borderRadius: 7,
                      background: fb.handled ? 'var(--bg-2)' : 'var(--gn-d)',
                      color: fb.handled ? 'var(--t3)' : 'var(--gn)',
                      border: `1px solid ${fb.handled ? 'var(--bd-s)' : 'var(--gn)'}`,
                      fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                    }}
                  >
                    {fb.handled ? <Circle size={11} /> : <CheckCircle2 size={11} />}
                    {fb.handled ? '미처리로 되돌리기' : '처리 완료'}
                  </button>
                  <button
                    onClick={() => removeOne(fb)}
                    style={{
                      padding: '6px 11px', borderRadius: 7,
                      background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
                      color: 'var(--rd)',
                      fontSize: 11, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                    }}
                  >
                    <Trash2 size={11} /> 삭제
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
