/**
 * 방문 결과 form 입력 — 템플릿 fields 를 textarea 로 순차 렌더.
 *
 * - 각 필드에 ✨ "AI 다듬기" 버튼 (props.onRefineField 가 있을 때만 표시)
 * - 다듬기 결과는 "원본 / 다듬은 결과 / 적용 / 취소" 패널로 노출, 사용자가 확인 후 적용
 * - hiddenKeys 로 지정된 필드는 form 에서 숨김 (헤더에서 prefill 표시되는 자동 라벨용)
 */
import { useState } from 'react';
import { Sparkles, Check, X as XIcon, RefreshCw } from 'lucide-react';

export default function TemplateFormFields({
  fields = [],
  values = {},
  onChange,
  hiddenKeys = [],
  onRefineField,
}) {
  const visible = fields.filter(k => !hiddenKeys.includes(k));
  if (visible.length === 0) {
    return (
      <div style={{
        padding: '12px 14px', borderRadius: 8,
        background: 'var(--bg-2)', border: '1px dashed var(--bd-s)',
        fontSize: 12, color: 'var(--t3)',
      }}>
        선택된 템플릿에 입력 가능한 필드가 없습니다.
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {visible.map(key => (
        <FieldRow
          key={key}
          fieldKey={key}
          value={values[key] || ''}
          onChange={v => onChange({ ...values, [key]: v })}
          onRefineField={onRefineField}
        />
      ))}
    </div>
  );
}


function FieldRow({ fieldKey, value, onChange, onRefineField }) {
  const [refining, setRefining] = useState(false);
  const [refined, setRefined] = useState(null); // { original, suggestion }
  const [error, setError] = useState(null);

  const canRefine = !!onRefineField && (value || '').trim().length > 0 && !refining;

  const handleRefine = async () => {
    if (!canRefine) return;
    setRefining(true);
    setError(null);
    try {
      const original = value;
      const suggestion = await onRefineField(fieldKey, original);
      if (suggestion && typeof suggestion === 'string') {
        setRefined({ original, suggestion });
      } else {
        setError('AI 응답이 비어있습니다.');
      }
    } catch (e) {
      setError(e?.message || 'AI 다듬기 실패');
    } finally {
      setRefining(false);
    }
  };

  const accept = () => {
    if (refined) onChange(refined.suggestion);
    setRefined(null);
  };
  const cancel = () => setRefined(null);

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 6, gap: 8,
      }}>
        <span style={{
          fontSize: 11, fontWeight: 700, color: 'var(--t3)',
          letterSpacing: '.04em', textTransform: 'uppercase',
        }}>{fieldKey}</span>
        {onRefineField && (
          <button
            type="button"
            onClick={handleRefine}
            disabled={!canRefine}
            title={canRefine ? 'AI 가 이 필드 텍스트를 다듬어 제안' : '필드에 내용을 먼저 입력하세요'}
            style={{
              padding: '3px 8px', borderRadius: 6,
              background: canRefine ? 'var(--ac-d)' : 'var(--bg-2)',
              color: canRefine ? 'var(--ac)' : 'var(--t3)',
              border: '1px solid ' + (canRefine ? 'var(--ac)' : 'var(--bd-s)'),
              fontSize: 10, fontWeight: 700, fontFamily: 'inherit',
              cursor: canRefine ? 'pointer' : 'not-allowed',
              display: 'inline-flex', alignItems: 'center', gap: 3,
              opacity: refining ? .6 : 1,
            }}
          >
            {refining ? <RefreshCw size={11} /> : <Sparkles size={11} />}
            {refining ? '다듬는 중…' : 'AI 다듬기'}
          </button>
        )}
      </div>
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        rows={2}
        placeholder={`${fieldKey} 입력`}
        style={{
          width: '100%', padding: '9px 11px', borderRadius: 8,
          border: '1px solid var(--bd-s)',
          background: 'var(--bg-1)', color: 'var(--t1)',
          fontSize: 13, fontFamily: 'inherit',
          resize: 'vertical', minHeight: 56, boxSizing: 'border-box',
          lineHeight: 1.5,
        }}
      />
      {error && (
        <div style={{
          marginTop: 6, fontSize: 11, color: '#b91c1c',
          background: '#fee2e2', padding: '5px 8px', borderRadius: 6,
        }}>
          {error}
        </div>
      )}
      {refined && (
        <div style={{
          marginTop: 8, padding: '10px 12px', borderRadius: 8,
          background: 'var(--ac-d)', border: '1px solid var(--ac)',
        }}>
          <div style={{
            fontSize: 11, fontWeight: 700, color: 'var(--ac)',
            marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4,
          }}>
            <Sparkles size={11} /> AI 다듬은 결과 (적용 전 검토)
          </div>
          <div style={{
            fontSize: 13, lineHeight: 1.55, color: 'var(--t1)',
            whiteSpace: 'pre-wrap', marginBottom: 8,
          }}>{refined.suggestion}</div>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={cancel}
              style={{
                padding: '5px 10px', borderRadius: 6,
                background: 'var(--bg-1)', color: 'var(--t2)',
                border: '1px solid var(--bd-s)',
                fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
                cursor: 'pointer',
                display: 'inline-flex', alignItems: 'center', gap: 3,
              }}
            ><XIcon size={11} /> 취소</button>
            <button
              type="button"
              onClick={accept}
              style={{
                padding: '5px 10px', borderRadius: 6,
                background: 'var(--ac)', color: '#fff',
                border: '1px solid var(--ac)',
                fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
                cursor: 'pointer',
                display: 'inline-flex', alignItems: 'center', gap: 3,
              }}
            ><Check size={11} /> 적용</button>
          </div>
        </div>
      )}
    </div>
  );
}
