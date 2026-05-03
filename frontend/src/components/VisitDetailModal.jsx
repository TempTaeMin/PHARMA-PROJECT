import { useEffect, useMemo, useState } from 'react';
import {
  X, Calendar, Clock, Trash2, Save, CheckCircle,
  Sparkles, FileText, RefreshCw, Users,
} from 'lucide-react';
import { visitApi } from '../api/client';
import { invalidate } from '../api/cache';

const STATUS_LABEL = {
  성공: { label: 'COMPLETED', c: '#166534', bg: '#dcfce7' },
  부재: { label: 'MISSED',    c: '#6b7280', bg: '#f3f4f6' },
  거절: { label: 'DECLINED',  c: '#b91c1c', bg: '#fee2e2' },
  예정: { label: 'UPCOMING',  c: '#0369a1', bg: '#e0f2fe' },
};

/**
 * 등록된 일정(VisitLog)의 상세/수정 모달.
 * - 예정(교수): 날짜·시간·사전 메모 수정
 * - 완료(교수): 사전 메모 읽기 전용 + 결과 메모 편집 + AI 정리
 * - 개인 일정 / 업무공지: 단일 메모 편집 + AI 정리
 */
export default function VisitDetailModal({
  open, visit, onClose, onSave, onCancelPlanned, onComplete,
  onShare, hasTeam = false,
}) {
  const [dateStr, setDateStr] = useState('');
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);
  const [preNotes, setPreNotes] = useState('');
  const [postNotes, setPostNotes] = useState('');
  const [singleNotes, setSingleNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [memoTab, setMemoTab] = useState('raw');
  const [aiSummaryState, setAiSummaryState] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState(null);

  const initialAiSummary = useMemo(() => {
    const raw = visit?.ai_summary;
    if (!raw) return null;
    if (typeof raw === 'string') {
      try { return JSON.parse(raw); } catch { return null; }
    }
    return raw;
  }, [visit]);

  const aiSummary = aiSummaryState || initialAiSummary;
  const hasAi = !!(aiSummary && (aiSummary.title || (aiSummary.summary && Object.values(aiSummary.summary).some(v => v && String(v).trim()))));

  useEffect(() => {
    if (!visit) return;
    const d = visit.visit_date ? new Date(visit.visit_date) : new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    setDateStr(`${y}-${m}-${day}`);
    setHour(d.getHours());
    setMinute(Math.round(d.getMinutes() / 10) * 10 % 60);
    setPreNotes(visit.notes || '');
    setPostNotes(visit.post_notes || '');
    setSingleNotes(visit.notes || '');
    setAiSummaryState(null);
    setAiError(null);
    const initialHasAi = !!(initialAiSummary && (initialAiSummary.title ||
      (initialAiSummary.summary && Object.values(initialAiSummary.summary).some(v => v && String(v).trim()))));
    setMemoTab(initialHasAi ? 'ai' : 'raw');
  }, [visit?.id]);

  if (!open || !visit) return null;

  const isPlanned = visit.status === '예정';
  const isAnnouncement = visit.category === 'announcement';
  const isPersonal = !isAnnouncement && (visit.category === 'personal' || !visit.doctor_name);
  const isProfessor = !isPersonal && !isAnnouncement && !!visit.doctor_id;
  const theme = STATUS_LABEL[visit.status] || STATUS_LABEL.예정;

  // AI 버튼 노출 조건:
  // - 교수 완료 방문: post_notes 원본이 있을 때
  // - 개인/공지: notes 원본이 있을 때 (예정이든 완료든)
  const aiSource = isProfessor
    ? postNotes
    : singleNotes;
  const canAiSummarize = isProfessor
    ? (!isPlanned && aiSource.trim().length > 0)
    : (aiSource.trim().length > 0);

  const incH = () => setHour((hour + 1) % 24);
  const decH = () => setHour((hour + 23) % 24);
  const incM = () => setMinute((minute + 10) % 60);
  const decM = () => setMinute((minute - 10 + 60) % 60);

  const handleSave = async () => {
    setSaving(true);
    try {
      const isMineLocal = visit.is_mine !== false;
      let patch;
      if (!isMineLocal) {
        // recipient — 결과 메모만 저장 가능 (완료된 교수 visit 한정)
        patch = { post_notes: postNotes.trim() || null };
      } else {
        const time = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00`;
        patch = { visit_date: `${dateStr}T${time}` };
        if (isProfessor) {
          if (isPlanned) {
            patch.notes = preNotes.trim() || null;
          } else {
            patch.post_notes = postNotes.trim() || null;
          }
        } else {
          patch.notes = singleNotes.trim() || null;
        }
      }
      await onSave(visit, patch);
      onClose();
    } catch (e) {
      alert('저장 실패: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleCancelPlanned = async () => {
    const label = isAnnouncement
      ? (visit.title || '업무공지')
      : (isPersonal ? (visit.title || '업무 일정') : `${visit.doctor_name} 방문`);
    const verb = (isPersonal || isAnnouncement) ? '삭제' : '취소';
    if (!confirm(`${label} 을(를) ${verb}하시겠습니까?`)) return;
    setSaving(true);
    try {
      await onCancelPlanned(visit);
      onClose();
    } catch (e) {
      alert('취소 실패: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleAiSummarize = async () => {
    if (!canAiSummarize) return;
    setAiLoading(true);
    setAiError(null);
    try {
      const rawMemo = (isProfessor ? postNotes : singleNotes).trim();
      const res = await visitApi.aiSummarize(visit.id, { raw_memo: rawMemo });
      setAiSummaryState(res.ai_summary || null);
      setMemoTab('ai');
      invalidate('my-visits');
      invalidate('dashboard');
    } catch (e) {
      setAiError(e.message || 'AI 정리 실패');
    } finally {
      setAiLoading(false);
    }
  };

  const memoLabel = isAnnouncement
    ? '공지 내용'
    : (isPersonal ? '메모' : (isPlanned ? '사전 메모' : '결과 메모'));

  const isMine = visit.is_mine !== false;
  const isShared = (visit.visibility || 'private') === 'team';
  const recipientCount = Array.isArray(visit.recipient_user_ids) ? visit.recipient_user_ids.length : 0;
  const shareLabel = isAnnouncement ? '팀공지로 공유' : '팀에 공유';
  // recipient 는 완료된 교수 visit 의 post_notes 만 수정 가능
  const canSave = isMine || (isProfessor && !isPlanned);

  return (
    <div
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
          padding: '22px 22px 20px', width: 520, maxWidth: '100%',
          maxHeight: '92vh', overflowY: 'auto',
          animation: 'fadeUp .22s ease',
        }}
      >
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
          <div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
              <span style={{
                display: 'inline-block',
                padding: '3px 8px', borderRadius: 5,
                fontSize: 10, fontWeight: 800, letterSpacing: '.05em',
                background: isAnnouncement ? '#fef3c7' : (isPersonal ? 'var(--ac-d)' : theme.bg),
                color: isAnnouncement ? '#b45309' : (isPersonal ? 'var(--ac)' : theme.c),
                fontFamily: 'Manrope',
              }}>
                {isAnnouncement ? '공지' : (isPersonal ? '업무' : theme.label)}
              </span>
              {!isMine && visit.owner_name && (
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '3px 8px', borderRadius: 5,
                  fontSize: 10, fontWeight: 800, letterSpacing: '.02em',
                  background: '#ede9fe', color: '#6d28d9',
                  border: '1px solid #c4b5fd', fontFamily: 'Manrope',
                }}>
                  <Users size={11} /> {visit.owner_name} 님이 공유
                </span>
              )}
            </div>
            <div style={{ fontFamily: 'Manrope', fontSize: 20, fontWeight: 800, color: 'var(--t1)' }}>
              {isAnnouncement
                ? (visit.title || '업무공지')
                : (isPersonal ? (visit.title || '업무 일정') : `${visit.doctor_name} 교수`)}
            </div>
            <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 3 }}>
              {isAnnouncement
                ? '업무공지'
                : (isPersonal
                    ? '업무 일정'
                    : `${visit.hospital_name}${visit.department ? ` · ${visit.department}` : ''}`)}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--t3)',
          }}><X size={20} /></button>
        </div>

        {/* 날짜 */}
        <div style={{ marginTop: 18 }}>
          <SectionLabel icon={<Calendar size={12} />}>방문 날짜</SectionLabel>
          <input
            type="date"
            value={dateStr}
            disabled={!isPlanned || !isMine}
            onChange={e => setDateStr(e.target.value)}
            style={{
              width: '100%', padding: '11px 13px', borderRadius: 10,
              border: '1px solid var(--bd-s)',
              background: (isPlanned && isMine) ? 'var(--bg-1)' : 'var(--bg-2)',
              fontSize: 14, fontFamily: 'inherit', color: 'var(--t1)',
              boxSizing: 'border-box',
              opacity: (isPlanned && isMine) ? 1 : .7,
            }}
          />
        </div>

        {/* 시간 (공지는 없음) */}
        {!isAnnouncement && (
        <div style={{ marginTop: 14 }}>
          <SectionLabel icon={<Clock size={12} />}>방문 시간</SectionLabel>
          {isPlanned && isMine ? (
            <div style={{
              padding: '14px 16px', borderRadius: 10,
              background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
              display: 'flex', alignItems: 'center', gap: 12,
              justifyContent: 'center',
            }}>
              <SpinnerCol value={hour} onInc={incH} onDec={decH} />
              <div style={{
                fontFamily: 'Manrope', fontSize: 28, fontWeight: 800,
                color: 'var(--t2)', lineHeight: 1, paddingBottom: 2,
              }}>:</div>
              <SpinnerCol value={minute} onInc={incM} onDec={decM} />
              <span style={{
                marginLeft: 6, padding: '3px 7px', borderRadius: 5,
                background: 'var(--ac-d)', color: 'var(--ac)',
                fontSize: 9, fontWeight: 800, fontFamily: 'Manrope',
              }}>24H</span>
            </div>
          ) : (
            <div style={{
              padding: '12px 14px', borderRadius: 10,
              background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
              fontSize: 15, fontWeight: 800, color: 'var(--t2)',
              fontFamily: "'JetBrains Mono'",
            }}>
              {String(hour).padStart(2, '0')}:{String(minute).padStart(2, '0')}
            </div>
          )}
        </div>
        )}

        {/* 교수 방문 완료: 사전 메모 (읽기 전용) */}
        {isProfessor && !isPlanned && (preNotes || '').trim() && (
          <div style={{ marginTop: 14 }}>
            <SectionLabel>사전 메모 <span style={{ fontWeight: 500, opacity: .7 }}>· 방문 전 작성</span></SectionLabel>
            <div style={{
              padding: '11px 13px', borderRadius: 10,
              background: 'var(--bg-2)', border: '1px dashed var(--bd-s)',
              fontSize: 13, color: 'var(--t2)', lineHeight: 1.5,
              whiteSpace: 'pre-wrap',
            }}>
              {preNotes}
            </div>
          </div>
        )}

        {/* 메모 본문 */}
        <div style={{ marginTop: 14 }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            marginBottom: 6, gap: 8,
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 5,
              fontSize: 11, fontWeight: 800, color: 'var(--t3)',
              letterSpacing: '.04em',
            }}>
              {memoLabel}
            </div>
            {canAiSummarize && (
              <button
                onClick={handleAiSummarize}
                disabled={aiLoading}
                style={{
                  padding: '5px 10px', borderRadius: 7,
                  background: 'var(--ac-d)', color: 'var(--ac)',
                  border: '1px solid var(--ac)',
                  fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
                  cursor: aiLoading ? 'not-allowed' : 'pointer',
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  opacity: aiLoading ? .6 : 1,
                }}
                title="Claude Haiku 로 구조화된 정리"
              >
                {aiLoading ? <RefreshCw size={12} /> : <Sparkles size={12} />}
                {aiLoading ? '정리 중…' : (hasAi ? '다시 정리' : 'MR AI로 정리')}
              </button>
            )}
          </div>

          {hasAi && (
            <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
              <TabButton
                active={memoTab === 'ai'}
                onClick={() => setMemoTab('ai')}
                icon={<Sparkles size={11} />}
              >AI 정리</TabButton>
              <TabButton
                active={memoTab === 'raw'}
                onClick={() => setMemoTab('raw')}
                icon={<FileText size={11} />}
              >원본</TabButton>
            </div>
          )}

          {hasAi && memoTab === 'ai' ? (
            <div style={{
              padding: '12px 14px', borderRadius: 10,
              background: 'var(--ac-d)', border: '1px solid var(--ac)',
            }}>
              {aiSummary.title && (
                <div style={{
                  fontSize: 14, fontWeight: 700, color: 'var(--t1)', marginBottom: 8,
                }}>
                  {aiSummary.title}
                </div>
              )}
              {aiSummary.summary && typeof aiSummary.summary === 'object' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {Object.entries(aiSummary.summary)
                    .filter(([, v]) => v != null && String(v).trim() !== '')
                    .map(([k, v]) => (
                      <div key={k} style={{
                        display: 'flex', gap: 8, fontSize: 12,
                        paddingBottom: 6, borderBottom: '1px dashed var(--bd-s)',
                      }}>
                        <span style={{
                          minWidth: 76, color: 'var(--t3)', fontWeight: 700,
                        }}>{k}</span>
                        <span style={{ color: 'var(--t1)', flex: 1, lineHeight: 1.5 }}>
                          {String(v)}
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ) : (
            <MemoTextarea
              visit={visit}
              isProfessor={isProfessor}
              isPlanned={isPlanned}
              isAnnouncement={isAnnouncement}
              isMine={isMine}
              preNotes={preNotes}
              setPreNotes={setPreNotes}
              postNotes={postNotes}
              setPostNotes={setPostNotes}
              singleNotes={singleNotes}
              setSingleNotes={setSingleNotes}
            />
          )}

          {aiError && (
            <div style={{
              marginTop: 8, fontSize: 11, color: '#b91c1c',
              background: '#fee2e2', padding: '7px 10px', borderRadius: 6,
            }}>
              {aiError}
            </div>
          )}
        </div>

        {/* 팀 공유 행 — 본인 일정 + 팀 있을 때만 */}
        {isMine && hasTeam && onShare && (
          <button
            onClick={() => onShare(visit)}
            style={{
              marginTop: 18, width: '100%', padding: '11px 14px', borderRadius: 10,
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
              background: isShared ? '#dcfce7' : 'var(--bg-2)',
              color: isShared ? '#15803d' : 'var(--t2)',
              border: `1px solid ${isShared ? '#86efac' : 'var(--bd-s)'}`,
              cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Users size={14} />
              <span style={{ fontSize: 13, fontWeight: 700 }}>
                {isShared
                  ? `공유 중 · ${recipientCount}명`
                  : shareLabel}
              </span>
            </span>
            <span style={{ fontSize: 11, color: 'inherit', opacity: .7 }}>
              {isShared ? '수신자 변경 →' : '수신자 선택 →'}
            </span>
          </button>
        )}

        {/* 액션 버튼 */}
        <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
          {isPlanned && !isPersonal && !isAnnouncement && (
            <button
              onClick={() => { onClose(); onComplete?.(visit); }}
              disabled={saving}
              style={{
                flex: '1 1 100%', padding: '12px 16px', borderRadius: 10,
                background: '#166534', color: '#fff', border: 'none',
                cursor: 'pointer', fontSize: 13, fontWeight: 800, fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}
            >
              <CheckCircle size={14} /> 방문 결과 기록
            </button>
          )}
          {isPlanned && isMine && (
            <button
              onClick={handleCancelPlanned}
              disabled={saving}
              style={{
                flex: '0 0 auto', padding: '12px 14px', borderRadius: 10,
                background: 'var(--bg-2)', color: '#b91c1c',
                border: '1px solid var(--bd-s)', cursor: 'pointer',
                fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', gap: 5,
              }}
            >
              <Trash2 size={13} /> {(isPersonal || isAnnouncement) ? '삭제' : '일정 취소'}
            </button>
          )}
          {canSave && (
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                flex: 1, padding: '12px 16px', borderRadius: 10,
                background: 'var(--ac)', color: '#fff', border: 'none',
                cursor: saving ? 'not-allowed' : 'pointer',
                fontSize: 13, fontWeight: 800, fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                opacity: saving ? .7 : 1,
              }}
            >
              <Save size={14} /> {saving ? '저장 중…' : '저장'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function MemoTextarea({
  visit, isProfessor, isPlanned, isAnnouncement, isMine = true,
  preNotes, setPreNotes, postNotes, setPostNotes,
  singleNotes, setSingleNotes,
}) {
  let value = '';
  let setter = () => {};
  let placeholder = '';
  // recipient(비-owner)는 사전 메모 / 개인메모 / 공지 본문 편집 불가. 결과 메모만 허용.
  let readOnly = false;
  if (isProfessor) {
    if (isPlanned) {
      value = preNotes; setter = setPreNotes;
      placeholder = '방문 전 준비사항, 언급할 제품/포인트 등';
      if (!isMine) readOnly = true;
    } else {
      value = postNotes; setter = setPostNotes;
      placeholder = '방문 결과를 입력하세요 (사전 메모는 보존됩니다)';
    }
  } else {
    value = singleNotes; setter = setSingleNotes;
    placeholder = isAnnouncement
      ? '공지 상세 내용 (일시, 장소, 준비물, 참고사항 등)'
      : '업무 내용 / 회의 내용 / 참고 메모';
    if (!isMine) readOnly = true;
  }
  return (
    <textarea
      value={value}
      onChange={e => setter(e.target.value)}
      rows={5}
      placeholder={placeholder}
      readOnly={readOnly}
      style={{
        width: '100%', padding: '12px 14px', borderRadius: 10,
        border: '1px solid var(--bd-s)',
        background: readOnly ? 'var(--bg-2)' : 'var(--bg-1)',
        fontSize: 13, fontFamily: 'inherit', color: 'var(--t1)',
        outline: 'none', resize: 'vertical', boxSizing: 'border-box',
        lineHeight: 1.5,
        opacity: readOnly ? .8 : 1,
      }}
    />
  );
}

function TabButton({ active, onClick, icon, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 4,
        padding: '6px 12px', borderRadius: 8,
        fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
        background: active ? 'var(--ac-d)' : 'var(--bg-2)',
        color: active ? 'var(--ac)' : 'var(--t3)',
        border: `1px solid ${active ? 'var(--ac)' : 'var(--bd-s)'}`,
        cursor: 'pointer',
      }}
    >
      {icon}{children}
    </button>
  );
}

function SectionLabel({ children, icon }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 5,
      fontSize: 11, fontWeight: 800, color: 'var(--t3)',
      letterSpacing: '.04em', marginBottom: 6,
    }}>
      {icon}{children}
    </div>
  );
}

function SpinnerCol({ value, onInc, onDec }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
    }}>
      <button onClick={onInc} style={spinBtn} aria-label="증가">▲</button>
      <div style={{
        fontFamily: 'Manrope', fontSize: 34, fontWeight: 800,
        color: 'var(--t1)', minWidth: 58, textAlign: 'center',
        lineHeight: 1.15,
        fontVariantNumeric: 'tabular-nums',
      }}>
        {String(value).padStart(2, '0')}
      </div>
      <button onClick={onDec} style={spinBtn} aria-label="감소">▼</button>
    </div>
  );
}

const spinBtn = {
  width: 40, height: 24, borderRadius: 6,
  background: 'transparent', border: 'none',
  cursor: 'pointer', color: 'var(--t3)',
  fontSize: 11,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};
