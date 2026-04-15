import { useEffect, useState } from 'react';
import { X, Plus, Trash2, Edit3, Star, Save, Sparkles } from 'lucide-react';
import { memoTemplateApi } from '../api/client';

const DEFAULT_FIELD_PRESETS = [
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
    fields: ['방문일시', '교수명', '논의내용', '결과', '다음 액션'],
    prompt_addon: '',
    is_default: false,
  });

  const startEdit = (t) => setEditing({
    id: t.id,
    name: t.name,
    fields: [...(t.fields || [])],
    prompt_addon: t.prompt_addon || '',
    is_default: !!t.is_default,
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
      const payload = {
        name: editing.name.trim(),
        fields: editing.fields,
        prompt_addon: editing.prompt_addon.trim() || null,
        is_default: editing.is_default,
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
    <div onClick={onClose} style={{
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
                        display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4,
                      }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>
                          {t.name}
                        </span>
                        {t.is_default && (
                          <span style={{
                            padding: '2px 6px', borderRadius: 4, fontSize: 9, fontWeight: 800,
                            background: 'var(--ac-d)', color: 'var(--ac)',
                            display: 'flex', alignItems: 'center', gap: 2,
                          }}>
                            <Star size={8} /> 기본
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--t3)' }}>
                        필드 {(t.fields || []).length}개: {(t.fields || []).slice(0, 5).join(', ')}
                        {(t.fields || []).length > 5 && ' ...'}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 4 }}>
                      <button onClick={() => startEdit(t)} style={iconBtnStyle()}>
                        <Edit3 size={12} />
                      </button>
                      {!t.is_default && (
                        <button onClick={() => remove(t)} style={iconBtnStyle(true)}>
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

  const presetKeys = new Set(DEFAULT_FIELD_PRESETS.map(p => p.key));
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
        <Label>기본 필드 선택</Label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {['필수', '선택'].map(group => (
            <div key={group}>
              <div style={{ fontSize: 10, color: 'var(--t3)', fontWeight: 700, marginBottom: 4 }}>
                {group}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {DEFAULT_FIELD_PRESETS.filter(p => p.group === group).map(p => {
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
          ))}
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
          기본 템플릿으로 설정
        </label>
      </div>

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
