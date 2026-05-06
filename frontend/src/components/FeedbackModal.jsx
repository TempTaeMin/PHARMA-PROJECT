import { useState, useEffect } from 'react';
import { X, MessageSquarePlus, Bug, Lightbulb, MessageCircle, Send, CheckCircle } from 'lucide-react';
import { feedbackApi } from '../api/client';
import { showError } from '../utils/dialog';

const CATEGORIES = [
  { key: 'bug', label: '버그 / 오류 제보', desc: '잘못 동작하거나 깨진 부분', Icon: Bug, color: '#dc2626' },
  { key: 'suggestion', label: '기능 제안 / 개선', desc: '있으면 좋겠다 / 이렇게 바꿔주세요', Icon: Lightbulb, color: '#2563eb' },
  { key: 'other', label: '기타 의견', desc: '사용 후기, 칭찬, 질문 등', Icon: MessageCircle, color: '#6b7280' },
];

/**
 * 베타 테스터가 앱 안에서 개발자에게 의견 보내는 모달.
 * 헤더 프로필 dropdown 의 "피드백 보내기" 항목에서 호출.
 */
export default function FeedbackModal({ open, onClose }) {
  const [category, setCategory] = useState('bug');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCategory('bug');
    setMessage('');
    setSaving(false);
    setDone(false);
  }, [open]);

  const submit = async () => {
    if (!message.trim()) return;
    setSaving(true);
    try {
      await feedbackApi.create({
        category,
        message: message.trim(),
        page_path: window.location.pathname || null,
      });
      setDone(true);
      setTimeout(() => onClose?.(), 1500);
    } catch (e) {
      showError(e, { title: '전송 실패' });
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
          zIndex: 80, animation: 'fadeIn .15s', cursor: 'pointer',
        }}
      />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        width: 'min(520px, 92vw)', maxHeight: '92vh', overflowY: 'auto',
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
        borderRadius: 14, zIndex: 81, boxShadow: '0 14px 60px rgba(0,0,0,.5)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '14px 18px', borderBottom: '1px solid var(--bd-s)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <MessageSquarePlus size={16} style={{ color: 'var(--ac)' }} />
            <h3 style={{ fontFamily: 'Outfit', fontSize: 15, fontWeight: 700 }}>피드백 보내기</h3>
          </div>
          <button onClick={onClose} style={{
            width: 28, height: 28, borderRadius: 7, background: 'var(--bg-2)',
            border: '1px solid var(--bd)', display: 'flex', alignItems: 'center',
            justifyContent: 'center', cursor: 'pointer', color: 'var(--t3)',
          }}>
            <X size={13} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: 18 }}>
          {done ? (
            <div style={{ textAlign: 'center', padding: '32px 16px' }}>
              <CheckCircle size={40} style={{ color: 'var(--gn)', marginBottom: 12 }} />
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>전송 완료</div>
              <div style={{ fontSize: 12, color: 'var(--t3)' }}>의견 감사합니다. 빠른 시일 내에 검토할게요.</div>
            </div>
          ) : (
            <>
              <div style={{ fontSize: 12, color: 'var(--t3)', lineHeight: 1.55, marginBottom: 12 }}>
                베타 테스터로 사용하시면서 발견한 버그, 개선 아이디어, 사용 후기를 자유롭게 남겨주세요.
                현재 페이지 정보가 함께 전송됩니다.
              </div>

              {/* 카테고리 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
                {CATEGORIES.map(({ key, label, desc, Icon, color }) => {
                  const active = category === key;
                  return (
                    <button
                      key={key}
                      onClick={() => setCategory(key)}
                      style={{
                        padding: '10px 12px', borderRadius: 8, textAlign: 'left',
                        background: active ? 'var(--ac-d)' : 'var(--bg-2)',
                        color: active ? 'var(--ac)' : 'var(--t1)',
                        border: active ? '1px solid var(--ac)' : '1px solid var(--bd-s)',
                        fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
                        display: 'flex', alignItems: 'flex-start', gap: 10,
                      }}
                    >
                      <Icon size={16} style={{ color, flexShrink: 0, marginTop: 2 }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600 }}>{label}</div>
                        <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>{desc}</div>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* 메시지 */}
              <label style={{
                display: 'block', fontSize: 11, color: 'var(--t3)',
                fontWeight: 500, marginBottom: 4,
              }}>
                내용 <span style={{ color: 'var(--rd)' }}>*</span>
              </label>
              <textarea
                value={message}
                onChange={e => setMessage(e.target.value)}
                rows={6}
                maxLength={2000}
                placeholder={
                  category === 'bug' ? '어떤 화면에서 어떤 동작을 했을 때 무엇이 잘못됐는지 적어주세요.\n예) 메모 페이지에서 삭제 버튼 누르면 빈 화면이 됨'
                  : category === 'suggestion' ? '어떤 기능이 있으면 좋을지, 어떻게 바뀌면 더 편할지 적어주세요.'
                  : '자유롭게 의견을 남겨주세요.'
                }
                style={{
                  width: '100%', padding: '10px 12px', borderRadius: 8,
                  background: 'var(--bg-2)', border: '1px solid var(--bd)',
                  color: 'var(--t1)', fontSize: 13, outline: 'none',
                  resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.5,
                }}
              />
              <div style={{ fontSize: 10, color: 'var(--t3)', marginTop: 4, textAlign: 'right' }}>
                {message.length} / 2000
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        {!done && (
          <div style={{
            display: 'flex', justifyContent: 'flex-end', gap: 6,
            padding: '12px 18px', borderTop: '1px solid var(--bd-s)',
          }}>
            <button
              onClick={onClose}
              style={{
                padding: '8px 14px', borderRadius: 7, background: 'var(--bg-2)',
                border: '1px solid var(--bd)', color: 'var(--t2)',
                fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              취소
            </button>
            <button
              onClick={submit}
              disabled={saving || !message.trim()}
              style={{
                padding: '8px 14px', borderRadius: 7,
                background: 'var(--ac)', border: 'none', color: '#fff',
                fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                cursor: (saving || !message.trim()) ? 'not-allowed' : 'pointer',
                opacity: (saving || !message.trim()) ? 0.5 : 1,
                display: 'inline-flex', alignItems: 'center', gap: 5,
              }}
            >
              <Send size={13} /> {saving ? '전송 중…' : '보내기'}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
