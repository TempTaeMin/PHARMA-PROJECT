import { useState, useEffect, useMemo } from 'react';
import { Plus, X, Sparkles, RefreshCw } from 'lucide-react';
import DailySchedule from '../components/DailySchedule';
import AddEventBottomSheet from '../components/AddEventBottomSheet';
import SelectDoctorForMeeting from '../components/SelectDoctorForMeeting';
import SelectVisitDate from '../components/SelectVisitDate';
import DoctorScheduleHintPopup from '../components/DoctorScheduleHintPopup';
import SelectMeetingTime from '../components/SelectMeetingTime';
import VisitDetailModal from '../components/VisitDetailModal';
import PersonalEventEditor from '../components/PersonalEventEditor';
import AcademicEventCreateModal from '../components/AcademicEventCreateModal';
import AcademicEventModal from '../components/AcademicEventModal';
import WorkTypeChooser from '../components/WorkTypeChooser';
import WorkAnnouncementEditor from '../components/WorkAnnouncementEditor';
import ShareVisitModal from '../components/ShareVisitModal';
import { useMonthCalendar } from '../hooks/useMonthCalendar';
import { useCachedApi } from '../hooks/useCachedApi';
import { invalidate } from '../api/cache';
import { memoApi, visitApi, academicApi, memoTemplateApi } from '../api/client';

function ymd(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

export default function Dashboard({ onNavigate, currentUser, teamMembers = [] }) {
  const hasTeam = !!currentUser?.team_id;
  const now = new Date();
  const todayStr = ymd(now.getFullYear(), now.getMonth(), now.getDate());

  const [selected, setSelected] = useState(todayStr);
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() });

  // ─ 일정 추가 플로우 state ─
  // null | 'category' | 'select-doctor' | 'select-date' | 'hint-popup' | 'select-time'
  const [flowStep, setFlowStep] = useState(null);
  const [flowDoctor, setFlowDoctor] = useState(null);
  // 일정 추가 흐름에서 사용할 방문 날짜. 기본값은 일정확인에서 선택한 날짜이지만
  // SelectVisitDate 모달에서 사용자가 변경 가능.
  const [flowDate, setFlowDate] = useState(null);

  // ─ 방문 완료 처리 state ─
  const [completing, setCompleting] = useState(null);
  const [completeStatus, setCompleteStatus] = useState('');
  const [rawMemo, setRawMemo] = useState('');
  const [memoId, setMemoId] = useState(null);      // visits_memo.id
  const [aiResult, setAiResult] = useState(null);  // { title, summary }
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState(null);

  // ─ 일정 상세/수정 모달 state ─
  const [detailVisit, setDetailVisit] = useState(null);
  // ─ 공유 모달 state (카드 우상단 공유 버튼) ─
  const [shareVisit, setShareVisit] = useState(null);

  const { year, month } = view;
  const {
    doctors, visitsByDate, loading, actions, refresh,
  } = useMonthCalendar(year, month);

  // ─ 학회 일정 (이번 월) ─
  const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const { data: monthEvents, refresh: refreshAcademic } = useCachedApi(
    `academic-my-schedule:${monthKey}`,
    () => academicApi.mySchedule({
      start_date: ymd(year, month, 1),
      end_date: ymd(year, month, daysInMonth),
    }),
    { ttlKey: 'academic', deps: [monthKey] },
  );
  const events = monthEvents || [];

  // 기본 템플릿 — AI 정리 버튼 라벨에 표시
  const { data: tplList } = useCachedApi(
    'memo-templates',
    () => memoTemplateApi.list().then(r => r.templates || r || []),
    { ttlKey: 'memo-templates' },
  );
  const defaultTpl = useMemo(
    () => (tplList || []).find(t => t.is_default),
    [tplList],
  );

  const eventsByDate = useMemo(() => {
    const map = {};
    events.forEach(e => {
      if (!e.start_date) return;
      const start = e.start_date;
      const end = e.end_date || start;
      let cur = start;
      while (cur <= end) {
        (map[cur] ||= []).push(e);
        const d = new Date(cur + 'T00:00:00');
        d.setDate(d.getDate() + 1);
        cur = ymd(d.getFullYear(), d.getMonth(), d.getDate());
      }
    });
    return map;
  }, [events]);

  // ─ 학회 상세 모달 state ─
  const [academicModalEvent, setAcademicModalEvent] = useState(null);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 주간 스트립에서 다른 월의 날짜를 선택하면 view도 따라가야 함
  const handleSelectDate = (dateStr) => {
    setSelected(dateStr);
    const d = new Date(dateStr + 'T00:00:00');
    if (d.getFullYear() !== year || d.getMonth() !== month) {
      setView({ year: d.getFullYear(), month: d.getMonth() });
    }
  };

  const selectedVisits = (visitsByDate[selected] || []).slice().sort((a, b) =>
    (a.visit_date || '').localeCompare(b.visit_date || '')
  );

  const selectedEvents = eventsByDate[selected] || [];

  // ─ 일정 추가 플로우 액션 ─
  const handleSelectCategory = (key) => {
    if (key === 'professor') {
      setFlowStep('select-doctor');
    } else if (key === 'personal') {
      setFlowStep('personal-type');
    } else if (key === 'etc') {
      setFlowStep('academic-event');
    }
  };

  const handleSelectPersonalType = (type) => {
    if (type === 'event') setFlowStep('personal-event');
    else if (type === 'announcement') setFlowStep('work-announcement');
  };

  const handleSubmitPersonal = async ({ dateStr, timeHHMM, title, notes, visibility, recipient_user_ids }) => {
    const dt = `${dateStr}T${timeHHMM}:00`;
    await visitApi.createPersonal({
      visit_date: dt, title, notes, status: '예정', visibility,
      recipient_user_ids: recipient_user_ids ?? null,
    });
    refresh();
    handleSelectDate(dateStr);
    closeFlow();
  };

  const handleSubmitAnnouncement = async ({ dateStr, title, content, visibility, recipient_user_ids }) => {
    const dt = `${dateStr}T00:00:00`;
    await visitApi.createAnnouncement({
      visit_date: dt, title, notes: content, visibility,
      recipient_user_ids: recipient_user_ids ?? null,
    });
    refresh();
    handleSelectDate(dateStr);
    closeFlow();
  };

  const handlePickDoctor = (doctor) => {
    setFlowDoctor(doctor);
    setFlowDate(selected); // 일정확인에서 선택한 날짜를 기본값으로
    setFlowStep('select-date');
  };

  const handleConfirmDate = (dateStr) => {
    setFlowDate(dateStr);
    setFlowStep('hint-popup');
  };

  const handleConfirmHint = () => {
    setFlowStep('select-time');
  };

  const handleConfirmTime = async ({ doctor, dateStr, timeHHMM, notes, visibility, recipient_user_ids }) => {
    await actions.addPlanned(doctor.id, dateStr, 'morning', {
      timeHHMM, notes, visibility, recipient_user_ids,
    });
    // 선택 날짜를 예정 추가한 날짜로 맞춰 바로 보이도록
    handleSelectDate(dateStr);
    closeFlow();
  };

  const closeFlow = () => {
    setFlowStep(null);
    setFlowDoctor(null);
    setFlowDate(null);
  };

  // ─ 완료/취소 액션 ─
  const openComplete = (visit) => {
    setCompleting(visit);
    setCompleteStatus('');
    setRawMemo(visit.post_notes || '');
    setMemoId(visit.memo_id || null);
    setAiResult(visit.ai_summary || null);
    setAiError(null);
  };

  const closeComplete = () => {
    setCompleting(null);
    setCompleteStatus('');
    setRawMemo('');
    setMemoId(null);
    setAiResult(null);
    setAiError(null);
  };

  const submitComplete = async () => {
    if (!completing) return;
    if (!completeStatus) {
      alert('방문 결과를 선택해주세요.');
      return;
    }
    try {
      // 1) visit_logs 상태/사후 메모 업데이트. 사전 메모(notes)는 보존.
      await actions.updateVisit(completing, {
        status: completeStatus,
        post_notes: rawMemo || null,
      });
      // 2) 메모가 아직 저장 전이면 원본만이라도 저장 (AI 정리는 선택)
      if (!memoId && rawMemo.trim()) {
        try {
          await memoApi.create({
            doctor_id: completing.doctor_id,
            visit_log_id: completing.id,
            visit_date: completing.visit_date,
            memo_type: 'visit',
            raw_memo: rawMemo,
          });
        } catch (e) {
          console.warn('메모 저장 실패(무시):', e);
        }
      } else if (memoId) {
        // 이미 생성된 메모에 visit_log_id 링크 보강
        try {
          await memoApi.update(memoId, {
            visit_log_id: completing.id,
            doctor_id: completing.doctor_id,
          });
        } catch (e) {
          console.warn('메모 링크 업데이트 실패(무시):', e);
        }
      }
      closeComplete();
    } catch (e) {
      alert('저장 실패: ' + e.message);
    }
  };

  // MR AI 정리: 메모가 없으면 먼저 생성 → /summarize 호출
  const handleAiOrganize = async () => {
    if (!rawMemo.trim()) {
      alert('정리할 메모를 먼저 작성해주세요.');
      return;
    }
    setAiLoading(true);
    setAiError(null);
    try {
      let id = memoId;
      if (!id) {
        const created = await memoApi.create({
          doctor_id: completing.doctor_id,
          visit_log_id: completing.id,
          visit_date: completing.visit_date,
          memo_type: 'visit',
          raw_memo: rawMemo,
        });
        id = created.id;
        setMemoId(id);
      } else {
        // 원본 메모 최신화
        await memoApi.update(id, { raw_memo: rawMemo });
      }
      const result = await memoApi.summarize(id, null);
      setAiResult(result.ai_summary || null);
    } catch (e) {
      setAiError(e.message || 'AI 정리 실패');
    } finally {
      setAiLoading(false);
    }
  };

  const cancelPlanned = async (visit) => {
    if (!confirm(`${visit.doctor_name} 예정을 취소하시겠습니까?`)) return;
    try {
      await actions.cancelPlanned(visit);
    } catch (e) {
      alert('취소 실패: ' + e.message);
    }
  };

  return (
    <div style={{
      maxWidth: 520, margin: '0 auto', padding: '0 6px 110px',
      display: 'flex', flexDirection: 'column', minHeight: '100%',
    }}>
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--t3)', fontSize: 13 }}>
          로딩 중…
        </div>
      ) : (
        <DailySchedule
          dateStr={selected}
          todayStr={todayStr}
          visits={selectedVisits}
          events={selectedEvents}
          visitsByDate={visitsByDate}
          eventsByDate={eventsByDate}
          onSelectDate={handleSelectDate}
          onComplete={openComplete}
          onCancel={cancelPlanned}
          onOpenDetail={setDetailVisit}
          onOpenAcademic={setAcademicModalEvent}
          onOpenMonth={() => onNavigate?.('schedule')}
          onShare={setShareVisit}
          hasTeam={hasTeam}
        />
      )}

      {/* ── Quick Add Bar (fixed bottom) ── */}
      <div style={{
        position: 'fixed',
        bottom: 18,
        left: '50%',
        transform: 'translateX(-50%)',
        width: 'min(780px, calc(100% - 32px))',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: 10,
        zIndex: 50,
        pointerEvents: 'none',
      }}>
        <button
          onClick={() => setFlowStep('category')}
          style={{
            width: 58, height: 58, borderRadius: '50%',
            background: 'var(--ac)', color: '#fff',
            border: 'none',
            boxShadow: '0 8px 24px rgba(0,64,161,.35)',
            cursor: 'pointer', pointerEvents: 'auto',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          title="일정 추가"
        >
          <Plus size={26} strokeWidth={2.4} />
        </button>
      </div>

      {/* ── Add Event Flow ── */}
      <AddEventBottomSheet
        open={flowStep === 'category'}
        onClose={closeFlow}
        onSelectCategory={handleSelectCategory}
        onPickFromAcademicList={() => {
          closeFlow();
          onNavigate?.('conferences', { mode: 'pick-for-add' });
        }}
      />
      <SelectDoctorForMeeting
        open={flowStep === 'select-doctor'}
        doctors={doctors}
        onBack={closeFlow}
        onSelect={handlePickDoctor}
      />
      <SelectVisitDate
        open={flowStep === 'select-date'}
        doctor={flowDoctor}
        initialDate={flowDate || selected}
        onBack={() => setFlowStep('select-doctor')}
        onConfirm={handleConfirmDate}
      />
      <DoctorScheduleHintPopup
        open={flowStep === 'hint-popup'}
        doctor={flowDoctor}
        selectedDate={flowDate || selected}
        onClose={() => setFlowStep('select-date')}
        onConfirm={handleConfirmHint}
      />
      <SelectMeetingTime
        open={flowStep === 'select-time'}
        doctor={flowDoctor}
        initialDate={flowDate || selected}
        todayStr={todayStr}
        onBack={() => setFlowStep('hint-popup')}
        onConfirm={handleConfirmTime}
        hasTeam={hasTeam}
        teamMembers={teamMembers}
        currentUserId={currentUser?.id}
      />
      <WorkTypeChooser
        open={flowStep === 'personal-type'}
        onClose={closeFlow}
        onSelect={handleSelectPersonalType}
      />
      <PersonalEventEditor
        open={flowStep === 'personal-event'}
        initialDate={selected}
        onClose={closeFlow}
        onSubmit={handleSubmitPersonal}
        hasTeam={hasTeam}
        teamMembers={teamMembers}
        currentUserId={currentUser?.id}
      />
      <WorkAnnouncementEditor
        open={flowStep === 'work-announcement'}
        initialDate={selected}
        onClose={closeFlow}
        onSubmit={handleSubmitAnnouncement}
        hasTeam={hasTeam}
        teamMembers={teamMembers}
        currentUserId={currentUser?.id}
      />
      <AcademicEventCreateModal
        open={flowStep === 'academic-event'}
        initialDate={selected}
        onClose={closeFlow}
        onCreated={() => { refresh(); refreshAcademic(); }}
      />

      {/* ── 학회 상세 (Dashboard 학회 카드 클릭 시) ── */}
      <AcademicEventModal
        open={!!academicModalEvent}
        event={academicModalEvent}
        onClose={() => setAcademicModalEvent(null)}
        hasTeam={hasTeam}
        currentUserId={currentUser?.id}
        onUpdated={() => {
          invalidate('academic');
          refreshAcademic();
        }}
      />

      {/* ── Visit Detail / Edit Modal ── */}
      <VisitDetailModal
        open={!!detailVisit}
        visit={detailVisit}
        onClose={() => setDetailVisit(null)}
        onSave={async (visit, patch) => {
          await actions.updateVisit(visit, patch);
        }}
        onCancelPlanned={async (visit) => {
          await actions.cancelPlanned(visit);
        }}
        onComplete={openComplete}
        onShare={setShareVisit}
        hasTeam={hasTeam}
      />

      {/* ── 공유 설정 Modal (카드 우상단 / 상세 모달 내부 공유 버튼) ── */}
      <ShareVisitModal
        open={!!shareVisit}
        visit={shareVisit}
        teamMembers={teamMembers}
        currentUserId={currentUser?.id}
        onClose={() => setShareVisit(null)}
        onSaved={(updated) => {
          setShareVisit(null);
          // 상세 모달이 같은 visit 을 보고 있으면 즉시 visibility/recipients 반영
          if (updated && detailVisit && detailVisit.id === updated.id) {
            setDetailVisit({
              ...detailVisit,
              visibility: updated.visibility,
              recipient_user_ids: updated.recipient_user_ids ?? [],
            });
          }
          refresh();
        }}
      />

      {/* ── Complete Modal (raw + AI 2영역) ── */}
      {completing && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 200,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 16, animation: 'fadeIn .15s ease',
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--bg-1)', borderRadius: 16, padding: 22,
              width: 560, maxWidth: '100%', maxHeight: '92vh', overflowY: 'auto',
              animation: 'fadeUp .2s ease',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <div style={{ fontFamily: 'Manrope', fontSize: 17, fontWeight: 700 }}>방문 결과 기록</div>
              <button onClick={closeComplete} style={{
                background: 'none', border: 'none', cursor: 'pointer', color: 'var(--t3)',
              }}><X size={18} /></button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 2, marginBottom: 16 }}>
              {completing.doctor_name} · {completing.department}
            </div>

            <label style={{ display: 'block', fontSize: 11, color: 'var(--t3)', fontWeight: 600, marginBottom: 6 }}>결과</label>
            <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
              {['성공', '부재', '거절'].map(s => (
                <button key={s} onClick={() => setCompleteStatus(s)} style={{
                  flex: 1, padding: 10, borderRadius: 8, cursor: 'pointer',
                  fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  background: completeStatus === s ? 'var(--ac-d)' : 'var(--bg-2)',
                  color: completeStatus === s ? 'var(--ac)' : 'var(--t3)',
                  border: `1px solid ${completeStatus === s ? 'var(--ac)' : 'var(--bd-s)'}`,
                }}>{s}</button>
              ))}
            </div>

            {completing.notes && (
              <div style={{
                marginBottom: 12,
                padding: '10px 12px', borderRadius: 8,
                background: 'var(--bg-2)', border: '1px dashed var(--bd-s)',
              }}>
                <div style={{
                  fontSize: 10, fontWeight: 800, letterSpacing: '.06em',
                  color: 'var(--t3)', marginBottom: 4, fontFamily: 'Manrope',
                }}>
                  사전 메모 (방문 전 작성)
                </div>
                <div style={{ fontSize: 12, color: 'var(--t2)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                  {completing.notes}
                </div>
              </div>
            )}

            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 6,
            }}>
              <label style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 600 }}>
                결과 메모 <span style={{ color: 'var(--t4, #9ca3af)', fontWeight: 500 }}>· 자유 입력</span>
              </label>
              <button
                onClick={handleAiOrganize}
                disabled={aiLoading || !rawMemo.trim()}
                style={{
                  padding: '5px 10px', borderRadius: 7,
                  background: 'var(--ac-d)', color: 'var(--ac)',
                  border: '1px solid var(--ac)',
                  fontSize: 11, fontWeight: 700, fontFamily: 'inherit',
                  cursor: (aiLoading || !rawMemo.trim()) ? 'not-allowed' : 'pointer',
                  display: 'flex', alignItems: 'center', gap: 4,
                  opacity: (aiLoading || !rawMemo.trim()) ? .5 : 1,
                }}
                title="Claude Haiku로 구조화된 방문일지로 정리"
              >
                {aiLoading ? <RefreshCw size={12} /> : <Sparkles size={12} />}
                {aiLoading ? '정리 중…' : (aiResult ? '다시 정리' : `MR AI로 정리${defaultTpl ? ` · ${defaultTpl.name}` : ''}`)}
              </button>
            </div>
            <textarea
              value={rawMemo}
              onChange={e => setRawMemo(e.target.value)}
              rows={5}
              placeholder="방문 결과·핵심 대화 내용을 자유롭게 입력하세요. 원본은 그대로 보존됩니다."
              style={{ ...modalInput, resize: 'vertical', marginBottom: 8 }}
            />

            {aiError && (
              <div style={{
                fontSize: 11, color: '#b91c1c', background: '#fee2e2',
                padding: '7px 10px', borderRadius: 6, marginBottom: 10,
              }}>
                {aiError}
              </div>
            )}

            {aiResult && (
              <div style={{
                marginTop: 4, marginBottom: 12,
                padding: '12px 14px', borderRadius: 10,
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
                  <div style={{
                    fontSize: 14, fontWeight: 700, color: 'var(--t1)', marginBottom: 8,
                  }}>
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
                <div style={{
                  fontSize: 10, color: 'var(--t3)', marginTop: 8, fontStyle: 'italic',
                }}>
                  원본 메모는 그대로 보존됩니다. 필요 시 "다시 정리"로 재실행할 수 있어요.
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14 }}>
              <button onClick={closeComplete} style={btnGhost}>취소</button>
              <button onClick={submitComplete} style={btnPrimary}>저장</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Styles ───
const modalInput = {
  width: '100%', padding: '9px 11px', borderRadius: 7,
  background: 'var(--bg-2)', border: '1px solid var(--bd)',
  color: 'var(--t1)', fontSize: 12, outline: 'none',
  fontFamily: 'inherit', marginBottom: 12, boxSizing: 'border-box',
};
const btnGhost = {
  padding: '8px 16px', borderRadius: 7, background: 'var(--bg-2)',
  color: 'var(--t2)', border: '1px solid var(--bd)',
  fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
};
const btnPrimary = {
  padding: '8px 16px', borderRadius: 7, background: 'var(--ac)',
  color: '#fff', border: 'none',
  fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
};
