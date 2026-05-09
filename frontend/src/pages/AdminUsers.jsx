import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Users, RefreshCw, Search, Building2, CalendarDays, Star, Mail, Clock, UserCircle2,
  Activity, Plus, Edit3,
} from 'lucide-react';
import { adminApi } from '../api/client';
import { showError } from '../utils/dialog';

// 베타 배포일 — 활동 모드 default 시작일.
const BETA_LAUNCH_DATE = '2026-05-06';

const KIND_LABEL = {
  visit: '일정',
  visit_note: '메모',
  memo: '회의록',
  report: '보고서',
  doctor_grade: '등급',
  doctor_memo: '의사 메모',
  academic_pin: '학회 핀',
  template: '템플릿',
  feedback: '피드백',
  team: '팀',
  invitation: '초대',
};
const KIND_COLOR = {
  visit: '#5b8def',
  visit_note: '#6aa6e6',
  memo: '#8b5cf6',
  report: '#d97706',
  doctor_grade: '#10b981',
  doctor_memo: '#0ea5e9',
  academic_pin: '#ec4899',
  template: '#64748b',
  feedback: '#ef4444',
  team: '#f59e0b',
  invitation: '#a855f7',
};

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}
function formatRelative(iso) {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  const diff = Math.floor((Date.now() - t) / 1000);
  if (diff < 60) return `${diff}초 전`;
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  if (diff < 2592000) return `${Math.floor(diff / 86400)}일 전`;
  return formatDate(iso);
}
function formatDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const Y = d.getFullYear();
  const M = String(d.getMonth() + 1).padStart(2, '0');
  const D = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  return `${Y}.${M}.${D} ${h}:${m}`;
}

const VISIT_CATEGORY_LABEL = {
  professor: '교수 방문',
  personal: '개인 일정',
  announcement: '업무 공지',
  etc: '기타',
};

function StatCard({ label, value, sub }) {
  return (
    <div style={{
      flex: 1, minWidth: 130,
      padding: '12px 14px', borderRadius: 11,
      background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
    }}>
      <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--t1)', fontFamily: 'Outfit' }}>
        {value ?? '—'}
      </div>
      {sub && <div style={{ fontSize: 10, color: 'var(--t3)', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

export default function AdminUsers() {
  const [mode, setMode] = useState('users'); // 'users' | 'teams' | 'activity'
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailTab, setDetailTab] = useState('activity'); // 'activity' | 'visits' | 'doctors' | 'teams'
  const [detailVisits, setDetailVisits] = useState([]);
  const [detailDoctors, setDetailDoctors] = useState([]);
  const [detailActivity, setDetailActivity] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

  // 활동 모드 — 기간 시작일 (default = 베타 배포일). 종료일은 항상 '현재' (백엔드 cutoff 단순화).
  const [activitySince, setActivitySince] = useState(BETA_LAUNCH_DATE);
  const [activeUsers, setActiveUsers] = useState([]);
  const [activitySinceServer, setActivitySinceServer] = useState(null);
  const [activityLoading, setActivityLoading] = useState(false);

  const sinceISO = useMemo(() => {
    if (!activitySince) return null;
    return new Date(`${activitySince}T00:00:00`).toISOString();
  }, [activitySince]);

  const refreshList = useCallback(async () => {
    setLoading(true);
    try {
      const [s, u, t] = await Promise.all([
        adminApi.stats(),
        adminApi.users(),
        adminApi.teams(),
      ]);
      setStats(s);
      setUsers(Array.isArray(u) ? u : []);
      setTeams(Array.isArray(t) ? t : []);
    } catch (e) {
      showError(e, { title: '불러오기 실패' });
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshActivity = useCallback(async () => {
    setActivityLoading(true);
    try {
      const r = await adminApi.activeUsers(sinceISO);
      setActiveUsers(Array.isArray(r?.users) ? r.users : []);
      setActivitySinceServer(r?.since || null);
    } catch (e) {
      showError(e, { title: '활동 사용자 로딩 실패' });
    } finally {
      setActivityLoading(false);
    }
  }, [sinceISO]);

  useEffect(() => { refreshList(); }, [refreshList]);
  useEffect(() => {
    if (mode === 'activity') refreshActivity();
  }, [mode, refreshActivity]);

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter(u =>
      (u.email || '').toLowerCase().includes(q) ||
      (u.name || '').toLowerCase().includes(q)
    );
  }, [users, search]);

  const filteredActiveUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return activeUsers;
    return activeUsers.filter(u =>
      (u.email || '').toLowerCase().includes(q) ||
      (u.name || '').toLowerCase().includes(q)
    );
  }, [activeUsers, search]);

  const loadDetail = useCallback(async (userId) => {
    setSelectedId(userId);
    setDetailLoading(true);
    setDetail(null);
    setDetailVisits([]);
    setDetailDoctors([]);
    setDetailActivity([]);
    try {
      const [d, vs, ds, act] = await Promise.all([
        adminApi.user(userId),
        adminApi.userVisits(userId, 100),
        adminApi.userDoctors(userId, 300),
        adminApi.userActivity(userId, sinceISO, 300),
      ]);
      setDetail(d);
      setDetailVisits(Array.isArray(vs) ? vs : []);
      setDetailDoctors(Array.isArray(ds) ? ds : []);
      setDetailActivity(Array.isArray(act?.events) ? act.events : []);
    } catch (e) {
      showError(e, { title: '사용자 상세 로딩 실패' });
    } finally {
      setDetailLoading(false);
    }
  }, [sinceISO]);

  return (
    <div style={{ maxWidth: 1280 }}>
      {/* 헤더 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <Users size={20} style={{ color: 'var(--ac)' }} />
        <h2 style={{ fontFamily: 'Outfit', fontSize: 22, fontWeight: 700 }}>사용자 관리</h2>
      </div>
      <div style={{ fontSize: 12, color: 'var(--t3)', marginBottom: 14 }}>
        가입자 활동·데이터 inspect — 운영자 전용
      </div>

      {/* stats */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <StatCard label="총 사용자" value={stats?.users_total} sub={`팀 ${stats?.teams_total ?? 0}개`} />
        <StatCard label="7일 신규" value={stats?.signups_7d} />
        <StatCard label="24h 활성" value={stats?.active_24h} sub="last_login 기준" />
        <StatCard label="7일 활성" value={stats?.active_7d} />
        <StatCard label="30일 활성" value={stats?.active_30d} />
        <StatCard label="총 일정" value={stats?.visits_total} />
      </div>

      {/* 모드 토글 + 검색 + 새로고침 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
        marginBottom: 12, padding: 4, background: 'var(--bg-1)',
        border: '1px solid var(--bd-s)', borderRadius: 10,
      }}>
        <button
          onClick={() => setMode('users')}
          style={{
            padding: '7px 13px', borderRadius: 7, border: 'none',
            background: mode === 'users' ? 'var(--ac-d)' : 'transparent',
            color: mode === 'users' ? 'var(--ac)' : 'var(--t3)',
            fontWeight: mode === 'users' ? 700 : 500,
            fontSize: 12, fontFamily: 'inherit', cursor: 'pointer',
          }}
        >사용자 ({users.length})</button>
        <button
          onClick={() => setMode('teams')}
          style={{
            padding: '7px 13px', borderRadius: 7, border: 'none',
            background: mode === 'teams' ? 'var(--ac-d)' : 'transparent',
            color: mode === 'teams' ? 'var(--ac)' : 'var(--t3)',
            fontWeight: mode === 'teams' ? 700 : 500,
            fontSize: 12, fontFamily: 'inherit', cursor: 'pointer',
          }}
        >팀 ({teams.length})</button>
        <button
          onClick={() => setMode('activity')}
          style={{
            padding: '7px 13px', borderRadius: 7, border: 'none',
            background: mode === 'activity' ? 'var(--ac-d)' : 'transparent',
            color: mode === 'activity' ? 'var(--ac)' : 'var(--t3)',
            fontWeight: mode === 'activity' ? 700 : 500,
            fontSize: 12, fontFamily: 'inherit', cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}
        ><Activity size={11} /> 활동{mode === 'activity' && activeUsers.length ? ` (${activeUsers.length})` : ''}</button>

        {mode === 'activity' && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 8px', borderRadius: 7,
            background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
            fontSize: 11, color: 'var(--t3)',
          }}>
            <Clock size={11} />
            <span>시작</span>
            <input
              type="date"
              value={activitySince}
              onChange={e => setActivitySince(e.target.value)}
              style={{
                border: 'none', outline: 'none', background: 'transparent',
                color: 'var(--t1)', fontSize: 11, fontFamily: 'inherit',
              }}
            />
          </div>
        )}

        {(mode === 'users' || mode === 'activity') && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 200,
            padding: '4px 8px', borderRadius: 7,
            background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
          }}>
            <Search size={13} style={{ color: 'var(--t3)' }} />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="이메일 / 이름 검색"
              style={{
                flex: 1, border: 'none', outline: 'none',
                background: 'transparent', color: 'var(--t1)',
                fontSize: 12, fontFamily: 'inherit',
              }}
            />
          </div>
        )}
        <div style={{ flex: (mode === 'users' || mode === 'activity') ? 0 : 1 }} />
        <button
          onClick={mode === 'activity' ? refreshActivity : refreshList}
          disabled={mode === 'activity' ? activityLoading : loading}
          style={{
            padding: '6px 11px', borderRadius: 7,
            background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
            color: 'var(--t2)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
            display: 'inline-flex', alignItems: 'center', gap: 4,
            opacity: (mode === 'activity' ? activityLoading : loading) ? 0.6 : 1,
          }}
        >
          <RefreshCw size={12} style={(mode === 'activity' ? activityLoading : loading) ? { animation: 'spin .8s linear infinite' } : {}} />
          새로고침
        </button>
      </div>

      {mode === 'teams' ? (
        <TeamsTable teams={teams} loading={loading} />
      ) : mode === 'activity' ? (
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 460px', minWidth: 0 }}>
            <ActiveUsersTable
              users={filteredActiveUsers}
              loading={activityLoading}
              selectedId={selectedId}
              onSelect={loadDetail}
              sinceLabel={activitySinceServer}
            />
          </div>
          <div style={{ flex: '1 1 440px', minWidth: 0 }}>
            {selectedId ? (
              <div style={{
                background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 12,
                overflow: 'hidden',
              }}>
                <div style={{
                  padding: '10px 14px', borderBottom: '1px solid var(--bd-s)',
                  background: 'var(--bg-2)', fontSize: 12, fontWeight: 600, color: 'var(--t1)',
                  display: 'flex', alignItems: 'center', gap: 6,
                }}>
                  <Activity size={13} style={{ color: 'var(--ac)' }} />
                  활동 타임라인
                  <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>
                    {detail?.email || ''}
                  </span>
                </div>
                <div style={{ maxHeight: 600, overflowY: 'auto' }}>
                  {detailLoading ? (
                    <div style={{ padding: 40, textAlign: 'center', color: 'var(--t3)', fontSize: 12 }}>로딩 중…</div>
                  ) : (
                    <ActivityTimeline events={detailActivity} />
                  )}
                </div>
              </div>
            ) : (
              <div style={{
                padding: 36, textAlign: 'center', color: 'var(--t3)', fontSize: 12,
                background: 'var(--bg-1)', border: '1px dashed var(--bd-s)', borderRadius: 12,
              }}>
                좌측에서 사용자 선택 → 시간순 활동 로그
              </div>
            )}
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          {/* 사용자 리스트 */}
          <div style={{ flex: '1 1 460px', minWidth: 0 }}>
            <UsersTable
              users={filteredUsers}
              loading={loading}
              selectedId={selectedId}
              onSelect={loadDetail}
            />
          </div>

          {/* 상세 패널 */}
          <div style={{ flex: '1 1 440px', minWidth: 0 }}>
            {selectedId ? (
              <DetailPanel
                detail={detail}
                visits={detailVisits}
                doctors={detailDoctors}
                activity={detailActivity}
                tab={detailTab}
                onTabChange={setDetailTab}
                loading={detailLoading}
              />
            ) : (
              <div style={{
                padding: 36, textAlign: 'center', color: 'var(--t3)', fontSize: 12,
                background: 'var(--bg-1)', border: '1px dashed var(--bd-s)', borderRadius: 12,
              }}>
                좌측 사용자를 클릭하면 raw 데이터가 보여요.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function UsersTable({ users, loading, selectedId, onSelect }) {
  if (loading && users.length === 0) {
    return <div style={{ padding: 60, textAlign: 'center', color: 'var(--t3)' }}>로딩 중…</div>;
  }
  if (users.length === 0) {
    return (
      <div style={{
        padding: 40, textAlign: 'center', color: 'var(--t3)', fontSize: 12,
        background: 'var(--bg-1)', border: '1px dashed var(--bd-s)', borderRadius: 12,
      }}>일치하는 사용자가 없어요.</div>
    );
  }
  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 11,
      overflow: 'hidden',
    }}>
      <div style={{
        display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr .6fr .6fr .6fr',
        padding: '8px 12px', fontSize: 10, fontWeight: 700,
        color: 'var(--t3)', textTransform: 'uppercase', letterSpacing: '.04em',
        background: 'var(--bg-2)', borderBottom: '1px solid var(--bd-s)',
      }}>
        <div>사용자</div>
        <div>가입일</div>
        <div>마지막 로그인</div>
        <div style={{ textAlign: 'right' }}>팀</div>
        <div style={{ textAlign: 'right' }}>의사</div>
        <div style={{ textAlign: 'right' }}>일정</div>
      </div>
      <div style={{ maxHeight: 560, overflowY: 'auto' }}>
        {users.map(u => {
          const isSelected = u.id === selectedId;
          return (
            <button
              key={u.id}
              onClick={() => onSelect(u.id)}
              style={{
                display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr .6fr .6fr .6fr',
                width: '100%', padding: '10px 12px',
                border: 'none', borderBottom: '1px solid var(--bd-s)',
                background: isSelected ? 'var(--ac-d)' : 'transparent',
                color: isSelected ? 'var(--ac)' : 'var(--t1)',
                cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
                alignItems: 'center', gap: 4,
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{
                  fontSize: 13, fontWeight: 600, overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>{u.name || '(이름 없음)'}</div>
                <div style={{
                  fontSize: 10, color: isSelected ? 'var(--ac)' : 'var(--t3)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>{u.email}</div>
              </div>
              <div style={{ fontSize: 11, color: 'var(--t2)', fontFamily: "'JetBrains Mono'" }}>
                {formatDate(u.created_at)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--t2)', fontFamily: "'JetBrains Mono'" }}>
                {formatRelative(u.last_login_at)}
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, textAlign: 'right' }}>{u.team_count}</div>
              <div style={{ fontSize: 12, fontWeight: 600, textAlign: 'right' }}>{u.doctor_count}</div>
              <div style={{ fontSize: 12, fontWeight: 600, textAlign: 'right' }}>{u.visit_count}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function TeamsTable({ teams, loading }) {
  if (loading && teams.length === 0) {
    return <div style={{ padding: 60, textAlign: 'center', color: 'var(--t3)' }}>로딩 중…</div>;
  }
  if (teams.length === 0) {
    return (
      <div style={{
        padding: 40, textAlign: 'center', color: 'var(--t3)', fontSize: 12,
        background: 'var(--bg-1)', border: '1px dashed var(--bd-s)', borderRadius: 12,
      }}>등록된 팀이 없어요.</div>
    );
  }
  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 11,
      overflow: 'hidden',
    }}>
      <div style={{
        display: 'grid', gridTemplateColumns: '2fr 2fr .8fr 1fr',
        padding: '8px 12px', fontSize: 10, fontWeight: 700,
        color: 'var(--t3)', textTransform: 'uppercase', letterSpacing: '.04em',
        background: 'var(--bg-2)', borderBottom: '1px solid var(--bd-s)',
      }}>
        <div>팀명</div>
        <div>리더</div>
        <div style={{ textAlign: 'right' }}>멤버 수</div>
        <div style={{ textAlign: 'right' }}>생성일</div>
      </div>
      {teams.map(t => (
        <div
          key={t.id}
          style={{
            display: 'grid', gridTemplateColumns: '2fr 2fr .8fr 1fr',
            padding: '10px 12px', borderBottom: '1px solid var(--bd-s)',
            alignItems: 'center', gap: 4,
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--t1)' }}>{t.name}</div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--t1)' }}>{t.owner_name || '—'}</div>
            <div style={{ fontSize: 10, color: 'var(--t3)' }}>{t.owner_email || '—'}</div>
          </div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--t1)', textAlign: 'right' }}>
            {t.member_count}
          </div>
          <div style={{ fontSize: 11, color: 'var(--t2)', fontFamily: "'JetBrains Mono'", textAlign: 'right' }}>
            {formatDate(t.created_at)}
          </div>
        </div>
      ))}
    </div>
  );
}

function DetailPanel({ detail, visits, doctors, activity, tab, onTabChange, loading }) {
  if (loading || !detail) {
    return (
      <div style={{
        padding: 60, textAlign: 'center', color: 'var(--t3)',
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 12,
      }}>로딩 중…</div>
    );
  }
  const TABS = [
    { key: 'activity', label: `활동 (${activity?.length || 0})`, Icon: Activity },
    { key: 'visits', label: `일정 (${visits.length})`, Icon: CalendarDays },
    { key: 'doctors', label: `의사 (${doctors.length})`, Icon: Star },
    { key: 'teams', label: `팀 (${detail.teams?.length || 0})`, Icon: Building2 },
  ];

  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 12,
      overflow: 'hidden',
    }}>
      {/* 프로필 헤더 */}
      <div style={{
        padding: 14, borderBottom: '1px solid var(--bd-s)', background: 'var(--bg-2)',
        display: 'flex', gap: 12, alignItems: 'center',
      }}>
        {detail.picture ? (
          <img src={detail.picture} alt="" style={{ width: 44, height: 44, borderRadius: 22, objectFit: 'cover' }} />
        ) : (
          <UserCircle2 size={44} style={{ color: 'var(--t3)' }} />
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--t1)' }}>
            {detail.name || '(이름 없음)'}
          </div>
          <div style={{
            fontSize: 11, color: 'var(--t3)', display: 'flex', gap: 8, flexWrap: 'wrap',
            marginTop: 2,
          }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
              <Mail size={10} /> {detail.email}
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
              <Clock size={10} /> 가입 {formatDate(detail.created_at)}
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
              마지막 로그인 {formatRelative(detail.last_login_at)}
            </span>
          </div>
        </div>
      </div>

      {/* 탭 */}
      <div style={{
        display: 'flex', gap: 2, padding: 4, background: 'var(--bg-2)',
        borderBottom: '1px solid var(--bd-s)',
      }}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => onTabChange(t.key)}
            style={{
              flex: 1, padding: '7px 10px', borderRadius: 6, border: 'none',
              background: tab === t.key ? 'var(--ac-d)' : 'transparent',
              color: tab === t.key ? 'var(--ac)' : 'var(--t3)',
              fontWeight: tab === t.key ? 700 : 500,
              fontSize: 11, fontFamily: 'inherit', cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 4,
            }}
          >
            <t.Icon size={11} /> {t.label}
          </button>
        ))}
      </div>

      {/* 탭 본문 */}
      <div style={{ maxHeight: 520, overflowY: 'auto' }}>
        {tab === 'activity' && <ActivityTimeline events={activity || []} />}
        {tab === 'visits' && <VisitList items={visits} />}
        {tab === 'doctors' && <DoctorList items={doctors} />}
        {tab === 'teams' && <TeamList items={detail.teams || []} />}
      </div>
    </div>
  );
}

function VisitList({ items }) {
  if (items.length === 0) return <Empty msg="일정 없음" />;
  return (
    <div>
      {items.map(v => (
        <div key={v.id} style={{
          padding: '10px 12px', borderBottom: '1px solid var(--bd-s)', fontSize: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 3 }}>
            <span style={{
              fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 5,
              background: 'var(--bg-2)', color: 'var(--t2)',
            }}>{VISIT_CATEGORY_LABEL[v.category] || v.category}</span>
            {v.status && (
              <span style={{ fontSize: 10, color: 'var(--t2)' }}>· {v.status}</span>
            )}
            {v.visibility === 'team' && (
              <span style={{ fontSize: 10, color: 'var(--ac)' }}>· 팀 공유</span>
            )}
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>
              {formatDateTime(v.visit_date)}
            </span>
          </div>
          <div style={{ color: 'var(--t1)', fontWeight: 500 }}>
            {v.title || v.doctor_name || '(제목 없음)'}
          </div>
          {(v.doctor_name || v.doctor_dept || v.hospital_name) && v.title && (
            <div style={{ fontSize: 10, color: 'var(--t3)', marginTop: 2 }}>
              {v.doctor_name}{v.doctor_dept ? ` · ${v.doctor_dept}` : ''}{v.hospital_name ? ` · ${v.hospital_name}` : ''}
            </div>
          )}
          {v.notes_preview && (
            <div style={{
              fontSize: 11, color: 'var(--t2)', marginTop: 4, padding: '4px 7px',
              borderRadius: 5, background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>
              {v.notes_preview}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function DoctorList({ items }) {
  if (items.length === 0) return <Empty msg="등록된 의사 없음" />;
  return (
    <div>
      {items.map(d => (
        <div key={d.doctor_id} style={{
          padding: '8px 12px', borderBottom: '1px solid var(--bd-s)',
          display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
        }}>
          <span style={{
            fontSize: 10, fontWeight: 700, width: 18, height: 18, borderRadius: 9,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--ac-d)', color: 'var(--ac)',
          }}>{d.grade}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: 'var(--t1)', fontWeight: 500 }}>{d.name}</div>
            <div style={{ fontSize: 10, color: 'var(--t3)' }}>
              {d.department || '—'}{d.hospital_name ? ` · ${d.hospital_name}` : ''}
            </div>
          </div>
          {!d.is_active && (
            <span style={{ fontSize: 9, color: 'var(--rd)', fontWeight: 700 }}>비활성</span>
          )}
        </div>
      ))}
    </div>
  );
}

function TeamList({ items }) {
  if (items.length === 0) return <Empty msg="소속 팀 없음" />;
  return (
    <div>
      {items.map(t => (
        <div key={t.id} style={{
          padding: '10px 12px', borderBottom: '1px solid var(--bd-s)',
          display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
        }}>
          <Building2 size={14} style={{ color: 'var(--t3)' }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: 'var(--t1)', fontWeight: 600 }}>{t.name}</div>
            <div style={{ fontSize: 10, color: 'var(--t3)' }}>
              {t.role === 'owner' ? '리더' : '멤버'} · 생성 {formatDate(t.created_at)}
            </div>
          </div>
          {t.is_active && (
            <span style={{
              fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 5,
              background: 'var(--ac-d)', color: 'var(--ac)',
            }}>활성</span>
          )}
        </div>
      ))}
    </div>
  );
}

function ActiveUsersTable({ users, loading, selectedId, onSelect, sinceLabel }) {
  if (loading && users.length === 0) {
    return <div style={{ padding: 60, textAlign: 'center', color: 'var(--t3)' }}>로딩 중…</div>;
  }
  if (users.length === 0) {
    return (
      <div style={{
        padding: 40, textAlign: 'center', color: 'var(--t3)', fontSize: 12,
        background: 'var(--bg-1)', border: '1px dashed var(--bd-s)', borderRadius: 12,
      }}>해당 기간에 활동한 사용자가 없어요.</div>
    );
  }
  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 11,
      overflow: 'hidden',
    }}>
      <div style={{
        padding: '8px 12px', fontSize: 10, color: 'var(--t3)',
        background: 'var(--bg-2)', borderBottom: '1px solid var(--bd-s)',
        display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <Activity size={11} style={{ color: 'var(--ac)' }} />
        <span>활동 1건 이상 사용자 ({users.length}명)</span>
        {sinceLabel && (
          <span style={{ marginLeft: 'auto', fontFamily: "'JetBrains Mono'", fontSize: 10 }}>
            since {sinceLabel.slice(0, 10)}
          </span>
        )}
      </div>
      <div style={{ maxHeight: 600, overflowY: 'auto' }}>
        {users.map(u => {
          const isSelected = u.id === selectedId;
          const kinds = Object.entries(u.by_kind || {})
            .sort((a, b) => b[1] - a[1]);
          return (
            <button
              key={u.id}
              onClick={() => onSelect(u.id)}
              style={{
                display: 'block', width: '100%', padding: '10px 12px',
                border: 'none', borderBottom: '1px solid var(--bd-s)',
                background: isSelected ? 'var(--ac-d)' : 'transparent',
                color: isSelected ? 'var(--ac)' : 'var(--t1)',
                cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 13, fontWeight: 600, overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>{u.name || '(이름 없음)'}</div>
                  <div style={{
                    fontSize: 10, color: isSelected ? 'var(--ac)' : 'var(--t3)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>{u.email}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: isSelected ? 'var(--ac)' : 'var(--t1)' }}>
                    {u.total_activity_count}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>
                    {formatRelative(u.last_activity_at)}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {kinds.map(([k, c]) => (
                  <span key={k} style={{
                    fontSize: 9, fontWeight: 600, padding: '2px 6px', borderRadius: 5,
                    background: 'var(--bg-2)', color: KIND_COLOR[k] || 'var(--t2)',
                    border: `1px solid ${KIND_COLOR[k] || 'var(--bd-s)'}33`,
                  }}>
                    {KIND_LABEL[k] || k} {c}
                  </span>
                ))}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ActivityTimeline({ events }) {
  if (!events || events.length === 0) return <Empty msg="활동 없음" />;
  return (
    <div>
      {events.map((e, i) => {
        const color = KIND_COLOR[e.kind] || 'var(--t2)';
        const ActionIcon = e.action === 'create' ? Plus : Edit3;
        return (
          <div key={i} style={{
            padding: '10px 12px', borderBottom: '1px solid var(--bd-s)',
            display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 12,
          }}>
            <div style={{
              width: 22, height: 22, borderRadius: 11, flexShrink: 0,
              background: `${color}22`, color,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              marginTop: 1,
            }}>
              <ActionIcon size={11} strokeWidth={2.5} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 2 }}>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 5,
                  background: `${color}22`, color,
                }}>{KIND_LABEL[e.kind] || e.kind}</span>
                <span style={{ fontSize: 9, color: 'var(--t3)', textTransform: 'uppercase' }}>
                  {e.action}
                </span>
                <span style={{
                  marginLeft: 'auto', fontSize: 10, color: 'var(--t3)',
                  fontFamily: "'JetBrains Mono'",
                }}>
                  {formatDateTime(e.ts)}
                </span>
              </div>
              <div style={{
                color: 'var(--t1)', fontSize: 12,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {e.title}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Empty({ msg }) {
  return (
    <div style={{ padding: 30, textAlign: 'center', color: 'var(--t3)', fontSize: 12 }}>
      {msg}
    </div>
  );
}
