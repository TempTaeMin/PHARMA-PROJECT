import { useEffect, useState } from 'react';
import { X, Bell, RefreshCw, AlertTriangle, GraduationCap, ChevronRight, UserMinus, ArrowRightLeft, Check } from 'lucide-react';
import { notificationApi, academicApi, doctorApi } from '../api/client';

export default function NotificationPanel({ open, onClose, notifications, onRefresh, onNavigate }) {
  const [tab, setTab] = useState('work');
  const [lecturerEvents, setLecturerEvents] = useState([]);

  // 스케줄 변경 탭 열릴 때 내 교수 참여 학회 로드
  useEffect(() => {
    if (!open || tab !== 'schedule_change') return;
    let cancelled = false;
    academicApi.myLecturers(1)
      .then(list => { if (!cancelled) setLecturerEvents(Array.isArray(list) ? list : []); })
      .catch(() => { if (!cancelled) setLecturerEvents([]); });
    return () => { cancelled = true; };
  }, [open, tab]);

  // 스케줄 변경 탭 = schedule_change + doctor_auto_missing + doctor_transfer_candidate
  const isScheduleType = (t) =>
    t === 'schedule_change' ||
    t === 'doctor_auto_missing' ||
    t === 'doctor_transfer_candidate';
  const filtered = tab === 'schedule_change'
    ? notifications.filter(n => isScheduleType(n.type))
    : notifications.filter(n => !isScheduleType(n.type));

  const unreadAll = notifications.filter(n => !n.read).length;

  const markAllRead = async () => {
    try {
      await notificationApi.markAllRead();
      onRefresh?.();
    } catch (e) { console.error(e); }
  };

  const sendTest = async () => {
    try {
      await notificationApi.test('테스트 알림: 교수 일정 변경됨');
      onRefresh?.();
    } catch (e) { console.error(e); }
  };

  const goConferences = () => {
    onClose?.();
    onNavigate?.('conferences');
  };

  const typeIcon = (type) => {
    if (type === 'schedule_change') return <RefreshCw size={12} style={{ color: 'var(--am)' }} />;
    if (type === 'doctor_auto_missing') return <UserMinus size={12} style={{ color: 'var(--am)' }} />;
    if (type === 'doctor_transfer_candidate') return <ArrowRightLeft size={12} style={{ color: 'var(--ac)' }} />;
    if (type === 'visit_reminder') return <Bell size={12} style={{ color: 'var(--ac)' }} />;
    if (type === 'overdue_warning') return <AlertTriangle size={12} style={{ color: 'var(--rd)' }} />;
    return <Bell size={12} style={{ color: 'var(--t3)' }} />;
  };

  const typeLabel = (type) => {
    if (type === 'schedule_change') return { text: '스케줄 변경', color: 'var(--am)' };
    if (type === 'doctor_auto_missing') return { text: '교수 누락', color: 'var(--am)' };
    if (type === 'doctor_transfer_candidate') return { text: '이직 후보', color: 'var(--ac)' };
    if (type === 'visit_reminder') return { text: '리마인더', color: 'var(--ac)' };
    if (type === 'overdue_warning') return { text: '미방문 경고', color: 'var(--rd)' };
    return { text: '알림', color: 'var(--t3)' };
  };

  const goDoctor = (doctorId) => {
    onClose?.();
    onNavigate?.('my-doctors', { initialDoctorId: doctorId });
  };

  const linkTransfer = async (n) => {
    const { new_doctor_id, old_doctor_id } = n.data || {};
    if (!new_doctor_id || !old_doctor_id) return;
    try {
      await doctorApi.update(new_doctor_id, { linked_doctor_id: old_doctor_id });
      if (n.id) await notificationApi.markRead(n.id);
      onRefresh?.();
    } catch (e) {
      alert('연결 실패: ' + e.message);
    }
  };

  const dismissNotification = async (n) => {
    if (!n.id) return;
    try {
      await notificationApi.markRead(n.id);
      onRefresh?.();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <>
      {/* Overlay */}
      {open && <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 49, animation: 'fadeIn .15s' }} />}

      {/* Panel */}
      <div style={{
        position: 'fixed', right: 0, top: 0, bottom: 0, width: 380, maxWidth: '100vw',
        background: 'var(--bg-1)', borderLeft: '1px solid var(--bd-s)', zIndex: 50,
        transform: open ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform .25s cubic-bezier(.4,0,.2,1)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{ padding: '16px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontFamily: 'Outfit', fontSize: 16, fontWeight: 600 }}>
            알림 {unreadAll > 0 && <span style={{ fontSize: 12, color: 'var(--ac)', fontWeight: 400 }}>({unreadAll})</span>}
          </h3>
          <div style={{ display: 'flex', gap: 4 }}>
            {unreadAll > 0 && (
              <button onClick={markAllRead} style={{ padding: '5px 10px', borderRadius: 6, background: 'var(--bg-2)', border: '1px solid var(--bd-s)', color: 'var(--t3)', fontSize: 10, cursor: 'pointer', fontFamily: 'inherit' }}>모두 읽음</button>
            )}
            <button onClick={onClose} style={{ width: 30, height: 30, borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--t3)' }}>
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--bd-s)' }}>
          {[
            { id: 'work', label: '업무' },
            { id: 'schedule_change', label: '스케줄 변경' },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              flex: 1, padding: '11px 0', textAlign: 'center', fontSize: 12, fontWeight: 500,
              color: tab === t.id ? 'var(--t1)' : 'var(--t3)',
              cursor: 'pointer', border: 'none', background: 'none', fontFamily: 'inherit',
              borderBottom: tab === t.id ? '2px solid var(--ac)' : '2px solid transparent',
            }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
          {/* 스케줄 변경 탭 전용: 내 교수 참여 학회 요약 */}
          {tab === 'schedule_change' && lecturerEvents.length > 0 && (
            <div style={{
              marginBottom: 12, padding: 12, borderRadius: 10,
              background: 'var(--ac-d)', border: '1px solid var(--ac)',
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                gap: 6, marginBottom: 8,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--ac)', fontSize: 12, fontWeight: 800, fontFamily: 'Manrope' }}>
                  <GraduationCap size={14} />
                  내 교수 참여 학회
                  <span style={{ fontSize: 10, color: 'var(--t3)', fontWeight: 500, marginLeft: 2 }}>
                    (향후 1개월 · {lecturerEvents.length}건)
                  </span>
                </div>
              </div>
              {lecturerEvents.slice(0, 3).map(ev => (
                <div key={ev.id} style={{
                  fontSize: 11, color: 'var(--t1)', lineHeight: 1.55,
                  display: 'flex', gap: 6, alignItems: 'baseline', marginBottom: 3,
                }}>
                  <span style={{
                    fontFamily: "'JetBrains Mono'", color: 'var(--ac)',
                    flexShrink: 0, minWidth: 38,
                  }}>
                    {formatMD(ev.start_date)}
                  </span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {ev.name}
                  </span>
                  <span style={{ flexShrink: 0, fontSize: 10, color: 'var(--ac)', fontWeight: 700 }}>
                    {(ev.matched_doctor_names || []).slice(0, 2).join(', ')}
                    {ev.matched_doctor_count > 2 ? ` +${ev.matched_doctor_count - 2}` : ''}
                  </span>
                </div>
              ))}
              <button onClick={goConferences} style={{
                marginTop: 8, width: '100%',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
                padding: '7px 10px', borderRadius: 7,
                background: 'var(--bg-1)', border: '1px solid var(--ac)',
                color: 'var(--ac)', fontSize: 11, fontWeight: 700, cursor: 'pointer',
                fontFamily: 'inherit',
              }}>
                전체 학회 보기 <ChevronRight size={12} />
              </button>
            </div>
          )}

          {filtered.length === 0 && (tab !== 'schedule_change' || lecturerEvents.length === 0) ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Bell size={24} style={{ color: 'var(--t3)', marginBottom: 8, opacity: .3 }} />
              <div style={{ fontSize: 13, color: 'var(--t3)' }}>알림이 없습니다</div>
            </div>
          ) : filtered.map((n, i) => {
            const label = typeLabel(n.type);
            const docId = n.type === 'doctor_auto_missing' ? n.data?.doctor_id : null;
            const isTransfer = n.type === 'doctor_transfer_candidate';
            const sameGroup = isTransfer && !!n.data?.same_group;
            return (
              <div key={n.id || i} style={{
                padding: 14, borderRadius: 9, marginBottom: 6,
                background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
                borderLeft: !n.read ? `3px solid ${label.color}` : '1px solid var(--bd-s)',
                opacity: n.read ? .6 : 1,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  {typeIcon(n.type)}
                  <span style={{ fontSize: 10, fontWeight: 600, color: label.color, textTransform: 'uppercase', letterSpacing: '.04em' }}>{label.text}</span>
                  {isTransfer && (
                    <span style={{
                      padding: '1px 6px', borderRadius: 4, fontSize: 9, fontWeight: 700, fontFamily: "'JetBrains Mono'",
                      background: sameGroup ? 'var(--ac-d)' : 'var(--bg-3)',
                      color: sameGroup ? 'var(--ac)' : 'var(--t3)',
                      border: `1px solid ${sameGroup ? 'var(--ac)' : 'var(--bd-s)'}`,
                    }}>
                      {sameGroup ? '강함 (같은 재단)' : '보통'}
                    </span>
                  )}
                  <span style={{ fontSize: 10, color: 'var(--t3)', marginLeft: 'auto' }}>{n.created_at ? new Date(n.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : ''}</span>
                </div>
                <div style={{ fontSize: 13, color: 'var(--t1)', lineHeight: 1.4 }}>{n.data?.message || JSON.stringify(n.data)}</div>

                {/* 이직 후보 — 비교 카드 + 예/아니오 액션 */}
                {isTransfer && (
                  <>
                    <div style={{
                      marginTop: 8, padding: 10, borderRadius: 7,
                      background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
                      display: 'flex', alignItems: 'center', gap: 8, fontSize: 11,
                    }}>
                      <div style={{ flex: 1, color: 'var(--t3)' }}>
                        <div style={{ fontWeight: 600, color: 'var(--t1)' }}>{n.data?.old_doctor_name}</div>
                        <div>{n.data?.old_hospital_name} · {n.data?.old_department}</div>
                      </div>
                      <ArrowRightLeft size={14} style={{ color: 'var(--ac)', flexShrink: 0 }} />
                      <div style={{ flex: 1, color: 'var(--t3)' }}>
                        <div style={{ fontWeight: 600, color: 'var(--t1)' }}>{n.data?.new_doctor_name}</div>
                        <div>{n.data?.new_hospital_name} · {n.data?.new_department}</div>
                      </div>
                    </div>
                    {!sameGroup && (
                      <div style={{ fontSize: 10, color: 'var(--t3)', marginTop: 4, lineHeight: 1.5 }}>
                        ⓘ 다른 재단입니다. 동명이인 가능성을 확인 후 연결하세요.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                      <button onClick={() => linkTransfer(n)} style={{
                        flex: 1, padding: '6px 10px', borderRadius: 6,
                        background: 'var(--ac)', color: '#fff', border: 'none',
                        fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 4,
                      }}>
                        <Check size={11} /> 예, 같은 사람이에요
                      </button>
                      <button onClick={() => dismissNotification(n)} style={{
                        flex: 1, padding: '6px 10px', borderRadius: 6,
                        background: 'var(--bg-1)', color: 'var(--t2)', border: '1px solid var(--bd-s)',
                        fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                      }}>
                        아니오
                      </button>
                    </div>
                  </>
                )}

                {/* doctor_auto_missing — 의사 상세로 가기 */}
                {docId && (
                  <button onClick={() => goDoctor(docId)} style={{
                    marginTop: 8, padding: '5px 10px', borderRadius: 6,
                    background: 'var(--bg-1)', color: 'var(--am)',
                    border: '1px solid rgba(245,158,11,.4)',
                    fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                  }}>
                    이직/퇴직 처리하기 <ChevronRight size={11} />
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* Test button (dev) */}
        <div style={{ padding: '10px 14px', borderTop: '1px solid var(--bd-s)' }}>
          <button onClick={sendTest} style={{
            width: '100%', padding: '8px', borderRadius: 7, background: 'var(--bg-2)',
            border: '1px solid var(--bd-s)', color: 'var(--t3)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
          }}>
            🧪 테스트 알림 발송 (개발용)
          </button>
        </div>
      </div>
    </>
  );
}

function formatMD(dateStr) {
  if (!dateStr) return '';
  const s = String(dateStr).slice(0, 10);
  const parts = s.split('-');
  if (parts.length !== 3) return s;
  return `${Number(parts[1])}/${Number(parts[2])}`;
}
