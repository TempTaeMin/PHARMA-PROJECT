import { useState, useEffect } from 'react';
import { Plus, X, Sparkles, RefreshCw } from 'lucide-react';
import DailySchedule from '../components/DailySchedule';
import AddEventBottomSheet from '../components/AddEventBottomSheet';
import SelectDoctorForMeeting from '../components/SelectDoctorForMeeting';
import DoctorScheduleHintPopup from '../components/DoctorScheduleHintPopup';
import SelectMeetingTime from '../components/SelectMeetingTime';
import VisitDetailModal from '../components/VisitDetailModal';
import PersonalEventEditor from '../components/PersonalEventEditor';
import { useMonthCalendar } from '../hooks/useMonthCalendar';
import { memoApi, visitApi } from '../api/client';

function ymd(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

export default function Dashboard({ onNavigate }) {
  const now = new Date();
  const todayStr = ymd(now.getFullYear(), now.getMonth(), now.getDate());

  const [selected, setSelected] = useState(todayStr);
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() });

  // ─ 일정 추가 플로우 state ─
  // null | 'category' | 'select-doctor' | 'hint-popup' | 'select-time'
  const [flowStep, setFlowStep] = useState(null);
  const [flowDoctor, setFlowDoctor] = useState(null);

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

  const { year, month } = view;
  const {
    doctors, visitsByDate, loading, actions, refresh,
  } = useMonthCalendar(year, month);

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

  // ─ 일정 추가 플로우 액션 ─
  const handleSelectCategory = (key) => {
    if (key === 'professor') {
      setFlowStep('select-doctor');
    } else if (key === 'personal') {
      setFlowStep('personal-event');
    }
  };

  const handleSubmitPersonal = async ({ dateStr, timeHHMM, title, notes }) => {
    const dt = `${dateStr}T${timeHHMM}:00`;
    await visitApi.createPersonal({ visit_date: dt, title, notes, status: '예정' });
    refresh();
    handleSelectDate(dateStr);
    closeFlow();
  };

  const handlePickDoctor = (doctor) => {
    setFlowDoctor(doctor);
    setFlowStep('hint-popup');
  };

  const handleConfirmHint = () => {
    setFlowStep('select-time');
  };

  const handleConfirmTime = async ({ doctor, dateStr, timeHHMM, notes }) => {
    await actions.addPlanned(doctor.id, dateStr, 'morning', { timeHHMM, notes });
    // 선택 날짜를 예정 추가한 날짜로 맞춰 바로 보이도록
    handleSelectDate(dateStr);
    closeFlow();
  };

  const closeFlow = () => {
    setFlowStep(null);
    setFlowDoctor(null);
  };

  // ─ 완료/취소 액션 ─
  const openComplete = (visit) => {
    setCompleting(visit);
    setCompleteStatus('');
    setRawMemo(visit.notes || '');
    setMemoId(null);
    setAiResult(null);
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
    if (!completeStatus || !completing) return;
    try {
      // 1) visit_logs 상태/메모 업데이트 (raw_memo를 notes에도 미러링)
      await actions.updateVisit(completing, {
        status: completeStatus,
        notes: rawMemo || null,
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
          onSelectDate={handleSelectDate}
          onComplete={openComplete}
          onCancel={cancelPlanned}
          onOpenDetail={setDetailVisit}
          onOpenMonth={() => onNavigate?.('schedule')}
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
      />
      <SelectDoctorForMeeting
        open={flowStep === 'select-doctor'}
        doctors={doctors}
        onBack={closeFlow}
        onSelect={handlePickDoctor}
      />
      <DoctorScheduleHintPopup
        open={flowStep === 'hint-popup'}
        doctor={flowDoctor}
        selectedDate={selected}
        onClose={() => setFlowStep('select-doctor')}
        onConfirm={handleConfirmHint}
      />
      <SelectMeetingTime
        open={flowStep === 'select-time'}
        doctor={flowDoctor}
        initialDate={selected}
        todayStr={todayStr}
        onBack={() => setFlowStep('hint-popup')}
        onConfirm={handleConfirmTime}
      />
      <PersonalEventEditor
        open={flowStep === 'personal-event'}
        initialDate={selected}
        onClose={closeFlow}
        onSubmit={handleSubmitPersonal}
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
      />

      {/* ── Complete Modal (raw + AI 2영역) ── */}
      {completing && (
        <div
          onClick={closeComplete}
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

            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 6,
            }}>
              <label style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 600 }}>
                원본 메모 <span style={{ color: 'var(--t4, #9ca3af)', fontWeight: 500 }}>· 자유 입력</span>
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
                {aiLoading ? '정리 중…' : (aiResult ? '다시 정리' : 'MR AI로 정리')}
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
              <button
                onClick={submitComplete}
                disabled={!completeStatus}
                style={{ ...btnPrimary, opacity: completeStatus ? 1 : .5 }}
              >저장</button>
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
