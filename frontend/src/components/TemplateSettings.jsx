import { useEffect, useState } from 'react';
import { X, Plus, Trash2, Edit3, Star, Save, Sparkles, FileText, MessageSquare } from 'lucide-react';
import { memoTemplateApi } from '../api/client';

const MEMO_FIELD_PRESETS = [
  { key: '방문일시', group: '필수' },
  { key: '교수명', group: '필수' },
  { key: '논의내용', group: '필수' },
  { key: '결과', group: '필수' },
  { key: '다음 액션', group: '필수' },
  { key: '병원명', group: '선택' },
  { key: '면담시간', group: '선택' },
  { key: '논의 제품', group: '선택' },
  { key: '동석자', group: '선택' },
  { key: '처방 요청 여부', group: '선택' },
  { key: '경쟁사 언급', group: '선택' },
  { key: '다음 방문 예정일', group: '선택' },
];

const REPORT_FIELD_PRESETS = [
  { key: '핵심 활동', group: '필수' },
  { key: '병원별 활동', group: '필수' },
  { key: '주요 논의/이슈', group: '필수' },
  { key: '다음 액션', group: '필수' },
  { key: '이번 주 지표', group: '주간' },
  { key: '다음 주 계획', group: '주간' },
  { key: '경쟁사 동향', group: '선택' },
  { key: '신규 처방 시도', group: '선택' },
  { key: '학회/세미나 참석', group: '선택' },
];

const SCOPE_OPTIONS = [
  { value: 'memo', label: '메모용', icon: MessageSquare, desc: '방문/회의록 정리' },
  { value: 'report', label: '보고서용', icon: FileText, desc: '일일/주간 종합' },
  { value: 'both', label: '공용', icon: Sparkles, desc: '메모/보고서 둘 다' },
];

const REPORT_TYPE_OPTIONS = [
  { value: '', label: '제한 없음' },
  { value: 'daily', label: '일일 추천' },
  { value: 'weekly', label: '주간 추천' },
];

function presetsForScope(scope) {
  return scope === 'report' ? REPORT_FIELD_PRESETS : MEMO_FIELD_PRESETS;
}

function defaultFieldsForScope(scope) {
  if (scope === 'report') {
    return ['핵심 활동', '병원별 활동', '주요 논의/이슈', '다음 액션'];
  }
  return ['방문일시', '교수명', '논의내용', '결과', '다음 액션'];
}

function ScopeBadge({ scope }) {
  if (!scope || scope === 'memo') {
    return (
      <span style={badgeStyle('#dbeafe', '#1d4ed8', '#93c5fd')}>
        <MessageSquare size={9} /> 메모
      </span>
    );
  }
  if (scope === 'report') {
    return (
      <span style={badgeStyle('#ede9fe', '#6d28d9', '#c4b5fd')}>
        <FileText size={9} /> 보고서
      </span>
    );
  }
  return (
    <span style={badgeStyle('#dcfce7', '#15803d', '#86efac')}>
      <Sparkles size={9} /> 공용
    </span>
  );
}

function badgeStyle(bg, color, border) {
  return {
    padding: '2px 6px', borderRadius: 4, fontSize: 9, fontWeight: 800,
    background: bg, color, border: `1px solid ${border}`,
    display: 'inline-flex', alignItems: 'center', gap: 3,
  };
}

export default function TemplateSettings({ open, onClose, onChanged }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);
  const [err, setErr] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await memoTemplateApi.list();
      setTemplates(r.templates || r || []);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      load();
      setEditing(null);
      setErr(null);
    }
  }, [open]);

  if (!open) return null;

  const startNew = () => setEditing({
    id: null,
    name: '',
    fields: defaultFieldsForScope('memo'),
    prompt_addon: '',
    is_default: false,
    scope: 'memo',
    default_report_type: '',
  });

  const startEdit = (t) => setEditing({
    id: t.id,
    name: t.name,
    fields: [...(t.fields || [])],
    prompt_addon: t.prompt_addon || '',
    is_default: !!t.is_default,
    scope: t.scope || 'memo',
    default_report_type: t.default_report_type || '',
  });

  const remove = async (t) => {
    if (!confirm(`"${t.name}" 템플릿을 삭제하시겠습니까?`)) return;
    try {
      await memoTemplateApi.remove(t.id);
      await load();
      onChanged?.();
    } catch (e) {
      setErr(e.message);
    }
  };

  const setAsDefault = async (t) => {
    try {
      await memoTemplateApi.update(t.id, { is_default: true });
      await load();
      onChanged?.();
    } catch (e) {
      setErr(e.message);
    }
  };

  const save = async () => {
    if (!editing.name.trim()) {
      setErr('템플릿 이름을 입력해주세요.');
      return;
    }
    if (editing.fields.length === 0) {
      setErr('최소 1개 이상의 필드를 선택해주세요.');
      return;
    }
    setErr(null);
    try {
      const scope = editing.scope || 'memo';
      const payload = {
        name: editing.name.trim(),
        fields: editing.fields,
        prompt_addon: editing.prompt_addon.trim() || null,
        is_default: scope === 'report' ? false : editing.is_default,
        scope,
        default_report_type: editing.default_report_type || null,
      };
      if (editing.id) {
        await memoTemplateApi.update(editing.id, payload);
      } else {
        await memoTemplateApi.create(payload);
      }
      setEditing(null);
      await load();
      onChanged?.();
    } catch (e) {
      setErr(e.message);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 50, padding: 20,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: 'var(--bg-0)', borderRadius: 14, width: '100%',
        maxWidth: 720, maxHeight: '90vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(0,0,0,.3)',
      }}>
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--bd-s)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div style={{ fontFamily: 'Manrope', fontSize: 16, fontWeight: 800 }}>
            메모 템플릿 관리
          </div>
          <button onClick={onClose} style={{
            width: 30, height: 30, borderRadius: 8, background: 'var(--bg-2)',
            border: '1px solid var(--bd-s)', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--t2)',
          }}>
            <X size={14} />
          </button>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
          {err && (
            <div style={{
              padding: '8px 12px', borderRadius: 8, background: '#fee2e2',
              color: '#b91c1c', fontSize: 12, marginBottom: 12,
            }}>{err}</div>
          )}

          {editing ? (
            <TemplateForm
              value={editing}
              onChange={setEditing}
              onSave={save}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <>
              <div style={{
                padding: '10px 12px', borderRadius: 8, marginBottom: 12,
                background: 'var(--ac-d)', border: '1px solid var(--ac)',
                fontSize: 11, color: 'var(--ac)', lineHeight: 1.5,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <Sparkles size={12} style={{ flexShrink: 0 }} />
                <span>
                  기본 템플릿을 지정하면, <b>내 일정 / 메모 페이지 / 의료진 상세</b> 의 모든 AI 메모 정리가 이 템플릿 구조로 적용됩니다.
                </span>
              </div>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                marginBottom: 12,
              }}>
                <div style={{ fontSize: 12, color: 'var(--t3)' }}>
                  {loading ? '로드 중...' : `${templates.length}개 템플릿`}
                </div>
                <button onClick={startNew} style={{
                  padding: '8px 14px', borderRadius: 8,
                  background: 'var(--ac)', color: '#fff', border: 'none',
                  fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
                  display: 'flex', alignItems: 'center', gap: 5,
                }}>
                  <Plus size={13} /> 새 템플릿
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {templates.map(t => (
                  <div key={t.id} style={{
                    padding: '12px 14px', borderRadius: 10,
                    background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
                  }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'wrap',
                      }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>
                          {t.name}
                        </span>
                        <ScopeBadge scope={t.scope} />
                        {t.default_report_type && (
                          <span style={badgeStyle('#fef3c7', '#92400e', '#fcd34d')}>
                            {t.default_report_type === 'weekly' ? '주간' : '일일'} 추천
                          </span>
                        )}
                        {t.is_default && (
                          <span style={{
                            padding: '2px 6px', borderRadius: 4, fontSize: 9, fontWeight: 800,
                            background: 'var(--ac-d)', color: 'var(--ac)',
                            display: 'flex', alignItems: 'center', gap: 2,
                          }}>
                            <Star size={8} /> 메모 기본
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--t3)' }}>
                        필드 {(t.fields || []).length}개: {(t.fields || []).slice(0, 5).join(', ')}
                        {(t.fields || []).length > 5 && ' ...'}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 4 }}>
                      {!t.is_default && t.scope !== 'report' && (
                        <button onClick={() => setAsDefault(t)} style={iconBtnStyle()} title="메모 기본으로 지정">
                          <Star size={12} />
                        </button>
                      )}
                      <button onClick={() => startEdit(t)} style={iconBtnStyle()} title="편집">
                        <Edit3 size={12} />
                      </button>
                      {!t.is_default && (
                        <button onClick={() => remove(t)} style={iconBtnStyle(true)} title="삭제">
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {!loading && templates.length === 0 && (
                  <div style={{
                    padding: 40, textAlign: 'center', color: 'var(--t3)', fontSize: 13,
                    background: 'var(--bg-1)', borderRadius: 10, border: '1px dashed var(--bd-s)',
                  }}>
                    템플릿이 없습니다. "새 템플릿"을 눌러 추가하세요.
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function TemplateForm({ value, onChange, onSave, onCancel }) {
  const [customField, setCustomField] = useState('');
  const scope = value.scope || 'memo';
  const presets = presetsForScope(scope);
  const groupOrder = scope === 'report' ? ['필수', '주간', '선택'] : ['필수', '선택'];

  const toggleField = (key) => {
    const has = value.fields.includes(key);
    onChange({
      ...value,
      fields: has ? value.fields.filter(f => f !== key) : [...value.fields, key],
    });
  };

  const addCustom = () => {
    const k = customField.trim();
    if (!k || value.fields.includes(k)) return;
    onChange({ ...value, fields: [...value.fields, k] });
    setCustomField('');
  };

  const removeField = (key) => {
    onChange({ ...value, fields: value.fields.filter(f => f !== key) });
  };

  const setScope = (next) => {
    if (next === scope) return;
    // scope 가 바뀌면 현재 필드가 보존하되, 비어있거나 신규 작성 중이면 프리셋으로 교체 제안
    const isFreshDefault =
      value.fields.length > 0 &&
      value.fields.every(f => defaultFieldsForScope(scope).includes(f)) &&
      defaultFieldsForScope(scope).every(f => value.fields.includes(f));
    onChange({
      ...value,
      scope: next,
      fields: isFreshDefault ? defaultFieldsForScope(next) : value.fields,
      // 메모로 돌아가면 default_report_type 비움
      default_report_type: next === 'memo' ? '' : value.default_report_type,
      // 보고서 전용은 메모 기본 플래그 무의미
      is_default: next === 'report' ? false : value.is_default,
    });
  };

  const presetKeys = new Set(presets.map(p => p.key));
  const customFields = value.fields.filter(f => !presetKeys.has(f));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <Label>템플릿 이름</Label>
        <input
          type="text"
          value={value.name}
          onChange={(e) => onChange({ ...value, name: e.target.value })}
          placeholder="예: 학회 미팅 템플릿"
          style={inputStyle()}
        />
      </div>

      <div>
        <Label>용도</Label>
        <div style={{ display: 'flex', gap: 6 }}>
          {SCOPE_OPTIONS.map(opt => {
            const on = scope === opt.value;
            const Icon = opt.icon;
            return (
              <button
                key={opt.value}
                onClick={() => setScope(opt.value)}
                style={{
                  flex: 1, padding: '10px 12px', borderRadius: 9,
                  background: on ? 'var(--ac-d)' : 'var(--bg-2)',
                  color: on ? 'var(--ac)' : 'var(--t2)',
                  border: `1px solid ${on ? 'var(--ac)' : 'var(--bd-s)'}`,
                  cursor: 'pointer', fontFamily: 'inherit',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                }}
              >
                <Icon size={14} />
                <span style={{ fontSize: 12, fontWeight: 700 }}>{opt.label}</span>
                <span style={{ fontSize: 10, opacity: .8 }}>{opt.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      {scope !== 'memo' && (
        <div>
          <Label>보고서 타입 추천 (선택)</Label>
          <div style={{ display: 'flex', gap: 6 }}>
            {REPORT_TYPE_OPTIONS.map(opt => {
              const on = (value.default_report_type || '') === opt.value;
              return (
                <button
                  key={opt.value || 'none'}
                  onClick={() => onChange({ ...value, default_report_type: opt.value })}
                  style={{
                    flex: 1, padding: '7px 10px', borderRadius: 7,
                    background: on ? 'var(--ac-d)' : 'var(--bg-2)',
                    color: on ? 'var(--ac)' : 'var(--t3)',
                    border: `1px solid ${on ? 'var(--ac)' : 'var(--bd-s)'}`,
                    fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          <div style={{ fontSize: 10, color: 'var(--t3)', marginTop: 5 }}>
            보고서 만들기 화면에서 일치하는 타입일 때 자동으로 추천됩니다.
          </div>
        </div>
      )}

      <div>
        <Label>{scope === 'report' ? '보고서 섹션' : '기본 필드 선택'}</Label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {groupOrder.map(group => {
            const items = presets.filter(p => p.group === group);
            if (items.length === 0) return null;
            return (
              <div key={group}>
                <div style={{ fontSize: 10, color: 'var(--t3)', fontWeight: 700, marginBottom: 4 }}>
                  {group}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {items.map(p => {
                    const on = value.fields.includes(p.key);
                    return (
                      <button
                        key={p.key}
                        onClick={() => toggleField(p.key)}
                        style={{
                          padding: '6px 11px', borderRadius: 16,
                          background: on ? 'var(--ac-d)' : 'var(--bg-2)',
                          color: on ? 'var(--ac)' : 'var(--t3)',
                          border: `1px solid ${on ? 'var(--ac)' : 'var(--bd-s)'}`,
                          fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                        }}
                      >
                        {on ? '✓ ' : ''}{p.key}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <Label>커스텀 필드</Label>
        <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
          <input
            type="text"
            value={customField}
            onChange={(e) => setCustomField(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustom())}
            placeholder="커스텀 필드명 입력 후 Enter"
            style={{ ...inputStyle(), flex: 1 }}
          />
          <button onClick={addCustom} style={{
            padding: '8px 14px', borderRadius: 8,
            background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
            fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
            color: 'var(--t2)',
          }}>
            추가
          </button>
        </div>
        {customFields.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {customFields.map(f => (
              <span key={f} style={{
                padding: '5px 10px', borderRadius: 14,
                background: '#fef3c7', color: '#92400e',
                border: '1px solid #fcd34d',
                fontSize: 11, fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 4,
              }}>
                {f}
                <button onClick={() => removeField(f)} style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                  color: '#92400e', display: 'flex', alignItems: 'center',
                }}>
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <Label>프롬프트 추가 지시 (선택)</Label>
        <textarea
          value={value.prompt_addon}
          onChange={(e) => onChange({ ...value, prompt_addon: e.target.value })}
          placeholder="예: 결과는 반드시 긍정/보류/부정 중 하나로 분류하세요."
          style={{ ...inputStyle(), minHeight: 80, resize: 'vertical', fontFamily: 'inherit' }}
        />
      </div>

      {scope !== 'report' && (
        <div>
          <label style={{
            display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
            color: 'var(--t2)', cursor: 'pointer',
          }}>
            <input
              type="checkbox"
              checked={value.is_default}
              onChange={(e) => onChange({ ...value, is_default: e.target.checked })}
            />
            메모 정리 시 기본 템플릿으로 사용
          </label>
        </div>
      )}

      <div style={{
        padding: 12, borderRadius: 10,
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
      }}>
        <div style={{
          fontSize: 11, color: 'var(--t3)', fontWeight: 700, marginBottom: 6,
          display: 'flex', alignItems: 'center', gap: 4,
        }}>
          <Sparkles size={11} /> AI 응답 JSON 미리보기
        </div>
        <pre style={{
          margin: 0, fontSize: 11, color: 'var(--t2)',
          fontFamily: "'JetBrains Mono', monospace", lineHeight: 1.5,
          whiteSpace: 'pre-wrap',
        }}>
{`{
  "title": "...",
  "summary": {
${value.fields.map(f => `    "${f}": "..."`).join(',\n')}
  }
}`}
        </pre>
      </div>

      <div style={{
        display: 'flex', gap: 8, justifyContent: 'flex-end',
        paddingTop: 12, borderTop: '1px solid var(--bd-s)',
      }}>
        <button onClick={onCancel} style={{
          padding: '10px 18px', borderRadius: 8,
          background: 'var(--bg-2)', color: 'var(--t2)',
          border: '1px solid var(--bd-s)', cursor: 'pointer',
          fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
        }}>
          취소
        </button>
        <button onClick={onSave} style={{
          padding: '10px 18px', borderRadius: 8,
          background: 'var(--ac)', color: '#fff',
          border: 'none', cursor: 'pointer',
          fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
          display: 'flex', alignItems: 'center', gap: 5,
        }}>
          <Save size={13} /> 저장
        </button>
      </div>
    </div>
  );
}

function Label({ children }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 700, color: 'var(--t2)',
      marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.04em',
    }}>{children}</div>
  );
}

function inputStyle() {
  return {
    width: '100%', padding: '9px 12px', borderRadius: 8,
    border: '1px solid var(--bd-s)', background: 'var(--bg-1)',
    fontSize: 13, color: 'var(--t1)', fontFamily: 'inherit',
    outline: 'none',
  };
}

function iconBtnStyle(danger) {
  return {
    width: 28, height: 28, borderRadius: 7,
    background: danger ? '#fee2e2' : 'var(--bg-2)',
    color: danger ? '#b91c1c' : 'var(--t2)',
    border: `1px solid ${danger ? '#fca5a5' : 'var(--bd-s)'}`,
    cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
  };
}
