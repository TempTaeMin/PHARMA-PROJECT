import { useEffect, useMemo, useState } from 'react';
import { X, Sparkles, Save, Search, Calendar, RefreshCw } from 'lucide-react';
import { memoApi } from '../api/client';

const MEMO_TYPES = [
  { key: 'visit', label: '방문' },
  { key: 'meeting', label: '회의록' },
  { key: 'note', label: '노트' },
];

function ymdLocal(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/**
 * 메모 작성/편집 풀스크린 모달.
 * - 신규: memo=null → create
 * - 편집: memo={...} → PUT
 *
 * onSaved(memo) → 저장 완료 시 부모에서 목록 리프레시/상세 전환 등
 */
export default function MemoEditor({
  open,
  memo,
  doctors = [],
  templates = [],
  defaultDoctorId = null,
  onClose,
  onSaved,
}) {
  const [doctorId, setDoctorId] = useState(null);
  const [visitDate, setVisitDate] = useState(() => ymdLocal(new Date()));
  const [memoType, setMemoType] = useState('visit');
  const [templateId, setTemplateId] = useState(null);
  const [rawMemo, setRawMemo] = useState('');
  const [title, setTitle] = useState('');
  const [doctorQuery, setDoctorQuery] = useState('');
  const [saving, setSaving] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState(null);
  const [aiError, setAiError] = useState(null);
  const [currentId, setCurrentId] = useState(null);

  const isEdit = !!memo;

  useEffect(() => {
    if (!open) return;
    if (memo) {
      setDoctorId(memo.doctor_id || null);
      setVisitDate(
        memo.visit_date
          ? ymdLocal(new Date(memo.visit_date))
          : ymdLocal(new Date())
      );
      setMemoType(memo.memo_type || 'visit');
      setTemplateId(memo.template_id || null);
      setRawMemo(memo.raw_memo || '');
      setTitle(memo.title || '');
      setAiResult(memo.ai_summary || null);
      setCurrentId(memo.id);
    } else {
      setDoctorId(defaultDoctorId || null);
      setVisitDate(ymdLocal(new Date()));
      setMemoType('visit');
      const def = templates.find(t => t.is_default) || templates[0];
      setTemplateId(def?.id || null);
      setRawMemo('');
      setTitle('');
      setAiResult(null);
      setCurrentId(null);
    }
    setAiError(null);
    setDoctorQuery('');
  }, [open, memo?.id, defaultDoctorId, templates.length]);

  const filteredDoctors = useMemo(() => {
    const q = doctorQuery.trim();
    if (!q) return doctors.slice(0, 30);
    return doctors
      .filter(d =>
        (d.name || '').includes(q) ||
        (d.department || '').includes(q) ||
        (d.hospital_name || '').includes(q)
      )
      .slice(0, 30);
  }, [doctors, doctorQuery]);

  const selectedDoctor = doctors.find(d => d.id === doctorId) || null;

  if (!open) return null;

  const buildPayload = () => ({
    doctor_id: doctorId,
    visit_log_id: memo?.visit_log_id ?? null,
    template_id: templateId,
    visit_date: visitDate ? `${visitDate}T09:00:00` : null,
    memo_type: memoType,
    title: title || null,
    raw_memo: rawMemo,
  });

  const save = async () => {
    if (!rawMemo.trim()) {
      alert('원본 메모를 입력해주세요.');
      return;
    }
    setSaving(true);
    try {
      let saved;
      if (isEdit || currentId) {
        const id = currentId || memo.id;
        const payload = buildPayload();
        delete payload.visit_log_id;
        saved = await memoApi.update(id, payload);
      } else {
        saved = await memoApi.create(buildPayload());
      }
      setCurrentId(saved.id);
      onSaved?.(saved);
      onClose?.();
    } catch (e) {
      alert('저장 실패: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const aiOrganize = async () => {
    if (!rawMemo.trim()) {
      alert('정리할 원본 메모를 입력해주세요.');
      return;
    }
    setAiLoading(true);
    setAiError(null);
    try {
      let id = currentId;
      if (!id) {
        const created = await memoApi.create(buildPayload());
        id = created.id;
        setCurrentId(id);
      } else {
        await memoApi.update(id, {
          raw_memo: rawMemo,
          template_id: templateId,
          doctor_id: doctorId,
          visit_date: visitDate ? `${visitDate}T09:00:00` : null,
          memo_type: memoType,
        });
      }
      const result = await memoApi.summarize(id, templateId);
      setAiResult(result.ai_summary || null);
      if (result.title) setTitle(result.title);
      onSaved?.(result);
    } catch (e) {
      setAiError(e.message || 'AI 정리 실패');
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 400,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16, animation: 'fadeIn .18s ease',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-1)', borderRadius: 18, padding: '22px 22px 20px',
          width: 640, maxWidth: '100%', maxHeight: '92vh', overflowY: 'auto',
          animation: 'fadeUp .2s ease',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
          <div>
            <div style={{ fontFamily: 'Manrope', fontSize: 18, fontWeight: 800, color: 'var(--t1)' }}>
              {isEdit ? '메모 편집' : '새 메모 작성'}
            </div>
            <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 3 }}>
              원본 메모는 그대로 보존되며, AI 정리는 별도로 저장됩니다.
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--t3)',
          }}><X size={20} /></button>
        </div>

        {/* 교수 선택 */}
        <Section label="교수 선택">
          {selectedDoctor ? (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 12px', borderRadius: 10,
              background: 'var(--ac-d)', border: '1px solid var(--ac)',
            }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>
                  {selectedDoctor.name} <span style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 500 }}>{selectedDoctor.position || ''}</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>
                  {selectedDoctor.hospital_name} · {selectedDoctor.department}
                </div>
              </div>
              <button onClick={() => setDoctorId(null)} style={{
                background: 'none', border: 'none', color: 'var(--t3)', cursor: 'pointer', fontSize: 11,
              }}>변경</button>
            </div>
          ) : (
            <div>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 7,
                background: 'var(--bg-2)', border: '1px solid var(--bd)', borderRadius: 8,
                padding: '8px 10px', marginBottom: 8,
              }}>
                <Search size={14} style={{ color: 'var(--t3)' }} />
                <input
                  placeholder="교수명·진료과·병원 검색 (선택 안 하면 미지정)"
                  value={doctorQuery}
                  onChange={e => setDoctorQuery(e.target.value)}
                  style={{ border: 'none', background: 'none', outline: 'none', color: 'var(--t1)', fontSize: 12.5, width: '100%' }}
                />
              </div>
              {doctorQuery && (
                <div style={{
                  maxHeight: 170, overflowY: 'auto',
                  border: '1px solid var(--bd-s)', borderRadius: 8,
                  background: 'var(--bg-1)',
                }}>
                  {filteredDoctors.length === 0 ? (
                    <div style={{ padding: 14, textAlign: 'center', fontSize: 12, color: 'var(--t3)' }}>검색 결과 없음</div>
                  ) : (
                    filteredDoctors.map(d => (
                      <button
                        key={d.id}
                        onClick={() => { setDoctorId(d.id); setDoctorQuery(''); }}
                        style={{
                          display: 'block', width: '100%', textAlign: 'left',
                          padding: '9px 12px', background: 'none', border: 'none',
                          borderBottom: '1px solid var(--bd-s)',
                          cursor: 'pointer', fontFamily: 'inherit', color: 'var(--t1)',
                        }}
                      >
                        <div style={{ fontSize: 13, fontWeight: 600 }}>
                          {d.name} <span style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 400 }}>{d.position || ''}</span>
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 1 }}>
                          {d.hospital_name} · {d.department}
                        </div>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
        </Section>

        {/* 날짜 / 유형 */}
        <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
          <div style={{ flex: 1 }}>
            <Section label="방문/작성 날짜" icon={<Calendar size={11} />}>
              <input
                type="date"
                value={visitDate}
                onChange={e => setVisitDate(e.target.value)}
                style={inputStyle}
              />
            </Section>
          </div>
          <div style={{ flex: 1 }}>
            <Section label="유형">
              <div style={{ display: 'flex', gap: 5 }}>
                {MEMO_TYPES.map(t => (
                  <button
                    key={t.key}
                    onClick={() => setMemoType(t.key)}
                    style={{
                      flex: 1, padding: '9px 8px', borderRadius: 7, cursor: 'pointer',
                      fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                      background: memoType === t.key ? 'var(--ac-d)' : 'var(--bg-2)',
                      color: memoType === t.key ? 'var(--ac)' : 'var(--t3)',
                      border: `1px solid ${memoType === t.key ? 'var(--ac)' : 'var(--bd-s)'}`,
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </Section>
          </div>
        </div>

        {/* 템플릿 */}
        {templates.length > 0 && (
          <Section label="템플릿 (AI 정리 규칙)">
            <select
              value={templateId || ''}
              onChange={e => setTemplateId(e.target.value ? parseInt(e.target.value) : null)}
              style={inputStyle}
            >
              <option value="">(기본)</option>
              {templates.map(t => (
                <option key={t.id} value={t.id}>
                  {t.name}{t.is_default ? ' · 기본' : ''}
                </option>
              ))}
            </select>
          </Section>
        )}

        {/* 제목 (AI가 생성하거나 수동) */}
        <Section label="제목 (선택 — 비워두면 AI가 생성)">
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="예: 김정형 교수 – 관절주사A 전환 논의"
            style={inputStyle}
          />
        </Section>

        {/* 원본 메모 */}
        <div style={{ marginTop: 14 }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            fontSize: 11, fontWeight: 800, color: 'var(--t3)',
            letterSpacing: '.04em', marginBottom: 6,
          }}>
            <span>원본 메모 (자유 입력)</span>
            <button
              onClick={aiOrganize}
              disabled={aiLoading || !rawMemo.trim()}
              style={{
                padding: '5px 10px', borderRadius: 7,
                background: 'var(--ac-d)', color: 'var(--ac)',
                border: '1px solid var(--ac)',
                fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
                cursor: (aiLoading || !rawMemo.trim()) ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: 4,
                opacity: (aiLoading || !rawMemo.trim()) ? .5 : 1,
                letterSpacing: 0,
              }}
            >
              {aiLoading ? <RefreshCw size={12} /> : <Sparkles size={12} />}
              {aiLoading ? '정리 중…' : (aiResult ? '다시 정리' : 'AI로 정리하기')}
            </button>
          </div>
          <textarea
            value={rawMemo}
            onChange={e => setRawMemo(e.target.value)}
            rows={7}
            placeholder="방문 직후 기억나는 대로 자유롭게 작성하세요. AI가 구조화된 방문일지로 정리해줍니다."
            style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5, fontSize: 13 }}
          />
        </div>

        {aiError && (
          <div style={{
            marginTop: 8, fontSize: 11, color: '#b91c1c', background: '#fee2e2',
            padding: '7px 10px', borderRadius: 6,
          }}>
            {aiError}
          </div>
        )}

        {aiResult && (
          <div style={{
            marginTop: 12, padding: '12px 14px', borderRadius: 10,
            background: 'var(--ac-d)', border: '1px solid var(--ac)',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 5,
              fontSize: 10, fontWeight: 800, letterSpacing: '.06em',
              color: 'var(--ac)', marginBottom: 8, fontFamily: 'Manrope',
            }}>
              <Sparkles size={11} /> AI 정리 결과
            </div>
            {aiResult.title && (
              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)', marginBottom: 8 }}>
                {aiResult.title}
              </div>
            )}
            {aiResult.summary && typeof aiResult.summary === 'object' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {Object.entries(aiResult.summary)
                  .filter(([, v]) => v != null && String(v).trim() !== '')
                  .map(([k, v]) => (
                    <div key={k} style={{
                      display: 'flex', gap: 8, fontSize: 12,
                      paddingBottom: 6, borderBottom: '1px dashed var(--bd-s)',
                    }}>
                      <span style={{ minWidth: 80, color: 'var(--t3)', fontWeight: 700 }}>{k}</span>
                      <span style={{ color: 'var(--t1)', flex: 1, lineHeight: 1.5 }}>{String(v)}</span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        )}

        {/* 액션 */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 18 }}>
          <button onClick={onClose} style={btnGhost}>취소</button>
          <button
            onClick={save}
            disabled={saving || !rawMemo.trim()}
            style={{
              ...btnPrimary,
              opacity: (saving || !rawMemo.trim()) ? .6 : 1,
              cursor: (saving || !rawMemo.trim()) ? 'not-allowed' : 'pointer',
            }}
          >
            <Save size={13} /> {saving ? '저장 중…' : '저장'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ label, icon, children }) {
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 5,
        fontSize: 11, fontWeight: 800, color: 'var(--t3)',
        letterSpacing: '.04em', marginBottom: 6,
      }}>
        {icon}{label}
      </div>
      {children}
    </div>
  );
}

const inputStyle = {
  width: '100%', padding: '10px 12px', borderRadius: 8,
  background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
  color: 'var(--t1)', fontSize: 13, outline: 'none',
  fontFamily: 'inherit', boxSizing: 'border-box',
};
const btnGhost = {
  padding: '9px 18px', borderRadius: 8, background: 'var(--bg-2)',
  color: 'var(--t2)', border: '1px solid var(--bd)',
  fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
};
const btnPrimary = {
  padding: '9px 18px', borderRadius: 8, background: 'var(--ac)',
  color: '#fff', border: 'none',
  fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
  display: 'flex', alignItems: 'center', gap: 6,
};
