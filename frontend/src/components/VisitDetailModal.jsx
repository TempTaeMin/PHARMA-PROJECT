import { useEffect, useMemo, useState } from 'react';
import { X, Calendar, Clock, Trash2, Save, CheckCircle, Sparkles, FileText } from 'lucide-react';

const STATUS_LABEL = {
  성공: { label: 'COMPLETED', c: '#166534', bg: '#dcfce7' },
  부재: { label: 'MISSED',    c: '#6b7280', bg: '#f3f4f6' },
  거절: { label: 'DECLINED',  c: '#b91c1c', bg: '#fee2e2' },
  예정: { label: 'UPCOMING',  c: '#0369a1', bg: '#e0f2fe' },
};

/**
 * 등록된 일정(VisitLog)의 상세/수정 모달.
 * - 예정: 날짜·시간·사전 메모 수정 가능, 결과 기록/일정 취소 액션
 * - 완료(성공/부재/거절): 읽기 전용, 결과 메모 수정만 가능
 */
export default function VisitDetailModal({
  open, visit, onClose, onSave, onCancelPlanned, onComplete,
}) {
  const [dateStr, setDateStr] = useState('');
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [memoTab, setMemoTab] = useState('raw');

  const aiSummary = useMemo(() => {
    const raw = visit?.ai_summary;
    if (!raw) return null;
    if (typeof raw === 'string') {
      try { return JSON.parse(raw); } catch { return null; }
    }
    return raw;
  }, [visit]);

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
    setNotes(visit.notes || '');
    setMemoTab(hasAi && visit.status !== '예정' ? 'ai' : 'raw');
  }, [visit?.id, hasAi]);

  if (!open || !visit) return null;

  const isPlanned = visit.status === '예정';
  const theme = STATUS_LABEL[visit.status] || STATUS_LABEL.예정;
  const showAiTabs = !isPlanned && hasAi;

  const incH = () => setHour((hour + 1) % 24);
  const decH = () => setHour((hour + 23) % 24);
  const incM = () => setMinute((minute + 10) % 60);
  const decM = () => setMinute((minute - 10 + 60) % 60);

  const handleSave = async () => {
    setSaving(true);
    try {
      const time = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00`;
      const patch = {
        visit_date: `${dateStr}T${time}`,
        notes: notes.trim() || null,
      };
      await onSave(visit, patch);
      onClose();
    } catch (e) {
      alert('저장 실패: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleCancelPlanned = async () => {
    if (!confirm(`${visit.doctor_name} 일정을 취소하시겠습니까?`)) return;
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

  return (
    <div
      onClick={onClose}
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
          padding: '22px 22px 20px', width: 480, maxWidth: '100%',
          maxHeight: '92vh', overflowY: 'auto',
          animation: 'fadeUp .22s ease',
        }}
      >
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
          <div>
            <span style={{
              display: 'inline-block',
              padding: '3px 8px', borderRadius: 5,
              fontSize: 10, fontWeight: 800, letterSpacing: '.05em',
              background: theme.bg, color: theme.c, fontFamily: 'Manrope',
              marginBottom: 8,
            }}>
              {theme.label}
            </span>
            <div style={{ fontFamily: 'Manrope', fontSize: 20, fontWeight: 800, color: 'var(--t1)' }}>
              {visit.doctor_name} 교수
            </div>
            <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 3 }}>
              {visit.hospital_name} · {visit.department}
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
            disabled={!isPlanned}
            onChange={e => setDateStr(e.target.value)}
            style={{
              width: '100%', padding: '11px 13px', borderRadius: 10,
              border: '1px solid var(--bd-s)',
              background: isPlanned ? 'var(--bg-1)' : 'var(--bg-2)',
              fontSize: 14, fontFamily: 'inherit', color: 'var(--t1)',
              boxSizing: 'border-box',
              opacity: isPlanned ? 1 : .7,
            }}
          />
        </div>

        {/* 시간 (예정만 편집) */}
        <div style={{ marginTop: 14 }}>
          <SectionLabel icon={<Clock size={12} />}>방문 시간</SectionLabel>
          {isPlanned ? (
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

        {/* 메모 */}
        <div style={{ marginTop: 14 }}>
          <SectionLabel>{isPlanned ? '사전 메모' : '결과 메모'}</SectionLabel>
          {showAiTabs && (
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
          {showAiTabs && memoTab === 'ai' ? (
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
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={4}
              placeholder={isPlanned
                ? '방문 전 준비사항, 언급할 제품/포인트 등'
                : '방문 결과를 입력하세요'}
              style={{
                width: '100%', padding: '12px 14px', borderRadius: 10,
                border: '1px solid var(--bd-s)', background: 'var(--bg-1)',
                fontSize: 13, fontFamily: 'inherit', color: 'var(--t1)',
                outline: 'none', resize: 'vertical', boxSizing: 'border-box',
                lineHeight: 1.5,
              }}
            />
          )}
        </div>

        {/* 액션 버튼 */}
        <div style={{ display: 'flex', gap: 8, marginTop: 20, flexWrap: 'wrap' }}>
          {isPlanned && (
            <>
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
                <Trash2 size={13} /> 일정 취소
              </button>
            </>
          )}
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
        </div>
      </div>
    </div>
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
