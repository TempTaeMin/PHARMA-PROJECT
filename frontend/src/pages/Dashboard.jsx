import { useState } from 'react';
import { Plus, X } from 'lucide-react';
import DailySchedule from '../components/DailySchedule';
import AddEventBottomSheet from '../components/AddEventBottomSheet';
import SelectDoctorForMeeting from '../components/SelectDoctorForMeeting';
import DoctorScheduleHintPopup from '../components/DoctorScheduleHintPopup';
import SelectMeetingTime from '../components/SelectMeetingTime';
import { useMonthCalendar } from '../hooks/useMonthCalendar';

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

  // ─ 방문 완료 처리 state (기존 기능 유지) ─
  const [completing, setCompleting] = useState(null);
  const [completeStatus, setCompleteStatus] = useState('');
  const [completeProduct, setCompleteProduct] = useState('');
  const [completeNotes, setCompleteNotes] = useState('');

  const { year, month } = view;
  const {
    doctors, visitsByDate, doctorsByDate, loading, actions,
  } = useMonthCalendar(year, month);

  // 주간 스트립에서 다른 월의 날짜를 선택하면 view도 따라가야 함
  const handleSelectDate = (dateStr) => {
    setSelected(dateStr);
    const d = new Date(dateStr + 'T00:00:00');
    if (d.getFullYear() !== year || d.getMonth() !== month) {
      setView({ year: d.getFullYear(), month: d.getMonth() });
    }
  };

  const selectedDoctors = doctorsByDate[selected] || [];
  const selectedVisits = (visitsByDate[selected] || []).slice().sort((a, b) =>
    (a.visit_date || '').localeCompare(b.visit_date || '')
  );

  // ─ 일정 추가 플로우 액션 ─
  const handleSelectCategory = (key) => {
    if (key === 'professor') {
      setFlowStep('select-doctor');
    }
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

  // ─ 기존 완료/취소 액션 ─
  const openComplete = (visit) => {
    setCompleting(visit);
    setCompleteStatus('');
    setCompleteProduct(visit.product || '');
    setCompleteNotes(visit.notes || '');
  };

  const submitComplete = async () => {
    if (!completeStatus || !completing) return;
    try {
      await actions.updateVisit(completing, {
        status: completeStatus,
        product: completeProduct || null,
        notes: completeNotes || null,
      });
      setCompleting(null);
    } catch (e) {
      alert('저장 실패: ' + e.message);
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
          doctors={selectedDoctors}
          visits={selectedVisits}
          onSelectDate={handleSelectDate}
          onComplete={openComplete}
          onCancel={cancelPlanned}
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

      {/* ── Complete Modal (기존 유지) ── */}
      {completing && (
        <div
          onClick={() => setCompleting(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 200,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            animation: 'fadeIn .15s ease',
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--bg-1)', borderRadius: 16, padding: 22,
              width: 420, maxWidth: '92%', animation: 'fadeUp .2s ease',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <div style={{ fontFamily: 'Manrope', fontSize: 17, fontWeight: 700 }}>방문 완료 처리</div>
              <button onClick={() => setCompleting(null)} style={{
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

            <label style={{ display: 'block', fontSize: 11, color: 'var(--t3)', fontWeight: 600, marginBottom: 6 }}>디테일링 제품</label>
            <input
              value={completeProduct}
              onChange={e => setCompleteProduct(e.target.value)}
              placeholder="예: 관절주사A"
              style={modalInput}
            />

            <label style={{ display: 'block', fontSize: 11, color: 'var(--t3)', fontWeight: 600, marginBottom: 6 }}>메모</label>
            <textarea
              value={completeNotes}
              onChange={e => setCompleteNotes(e.target.value)}
              rows={3}
              placeholder="핵심 대화 내용"
              style={{ ...modalInput, resize: 'vertical' }}
            />

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14 }}>
              <button onClick={() => setCompleting(null)} style={btnGhost}>취소</button>
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
