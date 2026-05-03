import { useEffect, useState } from 'react';
import { Users, UserPlus, Trash2, Edit3, LogOut, Plus, Mail, Crown, X, Check, Clock } from 'lucide-react';
import { teamApi } from '../api/client';

/**
 * 팀 관리 페이지.
 * - 팀 미소속: 빈 상태 + "팀 만들기" 버튼
 * - 팀 소속: 멤버 목록 + (팀장) 초대/제거, (멤버) 탈퇴
 */
export default function Team({ currentUser, onTeamChanged }) {
  const [data, setData] = useState(null); // { team, role, members }
  const [sentInvites, setSentInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [info, setInfo] = useState(null);

  const [creating, setCreating] = useState(false);
  const [newTeamName, setNewTeamName] = useState('');

  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState('');

  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await teamApi.me();
      setData(r);
      setErr(null);
      // 팀장이면 보낸 초대도 가져오기
      if (r?.role === 'owner') {
        try {
          const sent = await teamApi.sentInvitations();
          setSentInvites(Array.isArray(sent) ? sent : []);
        } catch { setSentInvites([]); }
      } else {
        setSentInvites([]);
      }
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    const name = newTeamName.trim();
    if (!name) return;
    setCreating(true);
    setErr(null);
    try {
      await teamApi.create(name);
      setNewTeamName('');
      await load();
      onTeamChanged?.();
    } catch (e) {
      setErr(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleRename = async () => {
    const name = renameValue.trim();
    if (!name) return;
    try {
      await teamApi.rename(name);
      setRenaming(false);
      await load();
      onTeamChanged?.();
    } catch (e) {
      setErr(e.message);
    }
  };

  const handleInvite = async () => {
    const email = inviteEmail.trim();
    if (!email) return;
    setInviting(true);
    setErr(null);
    setInfo(null);
    try {
      const res = await teamApi.invite(email);
      setInviteEmail('');
      setInfo(res?.message || `${email} 에게 초대장을 보냈습니다.`);
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setInviting(false);
    }
  };

  const handleCancelInvite = async (inv) => {
    if (!confirm(`${inv.invitee_email} 에게 보낸 초대장을 취소할까요?`)) return;
    try {
      await teamApi.cancelInvite(inv.id);
      await load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const handleRemove = async (member) => {
    if (!confirm(`${member.name || member.email} 님을 팀에서 제거하시겠습니까?`)) return;
    try {
      await teamApi.removeMember(member.user_id);
      await load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const handleLeave = async () => {
    if (!confirm('팀에서 탈퇴하시겠습니까? 공유받던 팀 일정은 더 이상 보이지 않습니다.')) return;
    try {
      await teamApi.leave();
      await load();
      onTeamChanged?.();
    } catch (e) {
      setErr(e.message);
    }
  };

  if (loading) {
    return <div style={{ padding: 30, color: 'var(--t3)', fontSize: 13 }}>로딩 중…</div>;
  }

  // ── 팀 미소속: 빈 상태 ──
  if (!data?.team) {
    return (
      <div style={{ maxWidth: 600, margin: '40px auto', padding: 16 }}>
        <div style={{
          padding: 32, borderRadius: 14, background: 'var(--bg-1)',
          border: '1px solid var(--bd-s)', textAlign: 'center',
        }}>
          <div style={{
            width: 56, height: 56, borderRadius: '50%', margin: '0 auto 16px',
            background: 'var(--ac-d)', color: 'var(--ac)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Users size={26} />
          </div>
          <div style={{ fontSize: 16, fontWeight: 800, fontFamily: 'Manrope', color: 'var(--t1)', marginBottom: 8 }}>
            아직 팀에 속해있지 않습니다
          </div>
          <div style={{ fontSize: 13, color: 'var(--t3)', lineHeight: 1.6, marginBottom: 24 }}>
            혼자 사용하셔도 모든 기능을 그대로 쓸 수 있어요.<br />
            동료와 일정·공지·학회 핀을 공유하려면 팀을 만들거나 팀장에게 초대를 받으세요.
          </div>
          <div style={{ display: 'flex', gap: 8, maxWidth: 360, margin: '0 auto' }}>
            <input
              value={newTeamName}
              onChange={e => setNewTeamName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="팀 이름 (예: 영업3팀)"
              style={inputStyle}
            />
            <button
              onClick={handleCreate}
              disabled={creating || !newTeamName.trim()}
              style={{ ...btnPrimary, opacity: (creating || !newTeamName.trim()) ? .5 : 1 }}
            >
              <Plus size={14} /> 팀 만들기
            </button>
          </div>
          {err && <div style={errBox}>{err}</div>}
        </div>
      </div>
    );
  }

  // ── 팀 소속 ──
  const isOwner = data.role === 'owner';
  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      {/* 팀 헤더 */}
      <div style={{
        padding: '20px 22px', borderRadius: 14, background: 'var(--bg-1)',
        border: '1px solid var(--bd-s)', marginBottom: 14,
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 48, height: 48, borderRadius: 12, background: 'var(--ac-d)',
          color: 'var(--ac)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Users size={22} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          {renaming ? (
            <div style={{ display: 'flex', gap: 6 }}>
              <input
                value={renameValue}
                onChange={e => setRenameValue(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleRename()}
                autoFocus
                style={{ ...inputStyle, fontSize: 16, fontWeight: 700 }}
              />
              <button onClick={handleRename} style={iconBtn()}><Check size={14} /></button>
              <button onClick={() => setRenaming(false)} style={iconBtn()}><X size={14} /></button>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h2 style={{
                fontFamily: 'Manrope', fontSize: 18, fontWeight: 800, color: 'var(--t1)',
                margin: 0,
              }}>{data.team.name}</h2>
              {isOwner && (
                <button
                  onClick={() => { setRenameValue(data.team.name); setRenaming(true); }}
                  style={iconBtn()}
                  title="팀 이름 변경"
                >
                  <Edit3 size={12} />
                </button>
              )}
            </div>
          )}
          <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 4 }}>
            멤버 {data.members.length}명 · 본인 역할: {isOwner ? '팀장' : '팀원'}
          </div>
        </div>
        {!isOwner && (
          <button onClick={handleLeave} style={btnDanger}>
            <LogOut size={13} /> 탈퇴
          </button>
        )}
      </div>

      {/* 멤버 초대 (팀장 only) */}
      {isOwner && (
        <div style={{
          padding: '14px 16px', borderRadius: 12, background: 'var(--bg-1)',
          border: '1px solid var(--bd-s)', marginBottom: 14,
        }}>
          <div style={{
            fontSize: 11, fontWeight: 800, color: 'var(--t3)',
            letterSpacing: '.04em', marginBottom: 8,
          }}>
            <UserPlus size={11} style={{ marginRight: 4, verticalAlign: 'middle' }} />
            멤버 초대
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <Mail size={14} style={{ color: 'var(--t3)', alignSelf: 'center', flexShrink: 0 }} />
            <input
              type="email"
              value={inviteEmail}
              onChange={e => setInviteEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleInvite()}
              placeholder="초대할 동료의 Gmail"
              style={inputStyle}
            />
            <button
              onClick={handleInvite}
              disabled={inviting || !inviteEmail.trim()}
              style={{ ...btnPrimary, opacity: (inviting || !inviteEmail.trim()) ? .5 : 1 }}
            >
              {inviting ? '초대 중…' : '초대'}
            </button>
          </div>
          <div style={{ fontSize: 10, color: 'var(--t3)', marginTop: 6, lineHeight: 1.5 }}>
            상대방이 한 번이라도 MediSync 에 로그인해야 초대할 수 있어요.
            초대장을 보내면 상대 알림에서 수락하기 전까진 멤버로 등록되지 않습니다.
          </div>
          {info && (
            <div style={{
              marginTop: 8, padding: '8px 10px', borderRadius: 7,
              background: '#dcfce7', color: '#166534',
              fontSize: 11, fontWeight: 600,
            }}>
              ✓ {info}
            </div>
          )}
        </div>
      )}

      {/* 보낸 초대 (pending) — 팀장만 */}
      {isOwner && sentInvites.length > 0 && (
        <div style={{
          padding: '14px 16px', borderRadius: 12, background: 'var(--bg-1)',
          border: '1px solid var(--bd-s)', marginBottom: 14,
        }}>
          <div style={{
            fontSize: 11, fontWeight: 800, color: 'var(--t3)',
            letterSpacing: '.04em', marginBottom: 10,
            display: 'flex', alignItems: 'center', gap: 5,
          }}>
            <Clock size={11} /> 수락 대기 중 ({sentInvites.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {sentInvites.map(inv => (
              <div key={inv.id} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 12px', borderRadius: 8,
                background: 'var(--bg-2)', border: '1px dashed var(--bd-s)',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--t1)' }}>
                    {inv.invitee_name || '이름 없음'}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--t3)' }}>{inv.invitee_email}</div>
                </div>
                <button onClick={() => handleCancelInvite(inv)} style={iconBtn(true)} title="초대 취소">
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 멤버 목록 */}
      <div style={{
        padding: '14px 16px', borderRadius: 12, background: 'var(--bg-1)',
        border: '1px solid var(--bd-s)',
      }}>
        <div style={{
          fontSize: 11, fontWeight: 800, color: 'var(--t3)',
          letterSpacing: '.04em', marginBottom: 10,
        }}>
          멤버 ({data.members.length})
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {data.members.map(m => (
            <div key={m.user_id} style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '10px 12px', borderRadius: 10,
              background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
            }}>
              {m.picture ? (
                <img src={m.picture} alt="" referrerPolicy="no-referrer" style={{
                  width: 36, height: 36, borderRadius: '50%', objectFit: 'cover',
                }} />
              ) : (
                <div style={{
                  width: 36, height: 36, borderRadius: '50%', background: 'var(--ac-d)',
                  color: 'var(--ac)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 14, fontWeight: 700,
                }}>
                  {(m.name || m.email)[0].toUpperCase()}
                </div>
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>
                    {m.name || '이름 없음'}
                  </span>
                  {m.role === 'owner' && (
                    <span style={ownerBadge}><Crown size={9} /> 팀장</span>
                  )}
                  {m.user_id === currentUser?.id && (
                    <span style={{
                      fontSize: 9, fontWeight: 800, color: 'var(--t3)',
                      padding: '1px 5px', borderRadius: 3, background: 'var(--bg-1)',
                    }}>나</span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>{m.email}</div>
              </div>
              {isOwner && m.role !== 'owner' && (
                <button onClick={() => handleRemove(m)} style={iconBtn(true)} title="제거">
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {err && <div style={errBox}>{err}</div>}
    </div>
  );
}

const inputStyle = {
  flex: 1, padding: '9px 12px', borderRadius: 8,
  background: 'var(--bg-2)', border: '1px solid var(--bd)',
  fontSize: 13, color: 'var(--t1)', fontFamily: 'inherit', outline: 'none',
};
const btnPrimary = {
  padding: '9px 14px', borderRadius: 8, background: 'var(--ac)',
  color: '#fff', border: 'none', cursor: 'pointer',
  fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
  display: 'flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap',
};
const btnDanger = {
  padding: '8px 14px', borderRadius: 8, background: '#fee2e2',
  color: '#b91c1c', border: '1px solid #fca5a5', cursor: 'pointer',
  fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
  display: 'flex', alignItems: 'center', gap: 5,
};
const ownerBadge = {
  fontSize: 9, fontWeight: 800, color: '#92400e',
  padding: '2px 6px', borderRadius: 4, background: '#fef3c7',
  border: '1px solid #fcd34d',
  display: 'inline-flex', alignItems: 'center', gap: 2,
};
const errBox = {
  marginTop: 12, padding: '10px 12px', borderRadius: 8,
  background: '#fee2e2', color: '#b91c1c', fontSize: 12,
};

function iconBtn(danger) {
  return {
    width: 30, height: 30, borderRadius: 7,
    background: danger ? '#fee2e2' : 'var(--bg-2)',
    color: danger ? '#b91c1c' : 'var(--t2)',
    border: `1px solid ${danger ? '#fca5a5' : 'var(--bd-s)'}`,
    cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexShrink: 0,
  };
}
