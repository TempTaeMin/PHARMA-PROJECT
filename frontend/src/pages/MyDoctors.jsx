import { useState, useEffect } from 'react';
import { Search, Plus, Clock, AlertTriangle, ChevronLeft, ChevronRight, FileText, Send, CheckCircle, XCircle, UserMinus, Calendar, RefreshCw, Sparkles, LogOut, X, RotateCcw, Archive } from 'lucide-react';
import { doctorApi, visitApi, crawlApi, memoApi } from '../api/client';
import { useCachedApi } from '../hooks/useCachedApi';
import { invalidate } from '../api/cache';
import ManualDoctorModal from '../components/ManualDoctorModal';
import ScheduleCalendar from '../components/ScheduleCalendar';

const REASON_LABELS = {
  transferred: { text: '이직', color: 'var(--am)' },
  retired: { text: '퇴직', color: 'var(--t3)' },
  mistake: { text: '오인 등록', color: 'var(--rd)' },
  manual: { text: '수동 비활성', color: 'var(--t3)' },
  'auto-missing': { text: '자동 누락', color: 'var(--am)' },
};

const G = { A: { bg: 'var(--rd-d)', c: 'var(--rd)' }, B: { bg: 'var(--am-d)', c: 'var(--am)' }, C: { bg: 'var(--bl-d)', c: 'var(--bl)' } };
const DAY_NAMES = ['월', '화', '수', '목', '금', '토'];
const SLOT_NAMES = { morning: '오전', afternoon: '오후', evening: '야간' };

/* MiniCalendar 는 ScheduleCalendar (frontend/src/components/ScheduleCalendar.jsx) 로 통합되어 제거됨. */

export default function MyDoctors({ onNavigate, initialDoctorId }) {
  // 'active' (기본, 정상 활성 내 교수) | 'inactive' (이직/퇴직/오인 등록 처리된 의사 — 복원 가능)
  const [view, setView] = useState('active');
  const { data: doctors, loading, refresh } = useCachedApi(
    `my-doctors:${view}`,
    () => doctorApi.list({ my_only: true, status: view }),
    { ttlKey: 'doctors', deps: [view] },
  );
  const [searchQ, setSearchQ] = useState('');
  const [detail, setDetail] = useState(null);
  const [visits, setVisits] = useState([]);
  const [doctorMemos, setDoctorMemos] = useState([]);
  const [reportFor, setReportFor] = useState(null);
  const [reportStatus, setReportStatus] = useState('');
  const [reportProduct, setReportProduct] = useState('');
  const [reportNotes, setReportNotes] = useState('');
  const [reportDone, setReportDone] = useState(false);
  const [crawlLoading, setCrawlLoading] = useState(false);
  const [crawlResult, setCrawlResult] = useState(null);
  const [lastCrawlDate, setLastCrawlDate] = useState(() => localStorage.getItem('my-doctors-last-crawl'));
  const [showManual, setShowManual] = useState(false);
  // 이직/퇴직 처리 모달: { doctor, reason } | null
  const [deactivateFor, setDeactivateFor] = useState(null);

  const formatDate = (iso) => {
    if (!iso) return null;
    const d = new Date(iso);
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };

  const runScheduleUpdate = async () => {
    setCrawlLoading(true);
    setCrawlResult(null);
    try {
      const res = await crawlApi.runMyDoctors();
      setCrawlResult(res);
      const now = new Date().toISOString();
      setLastCrawlDate(now);
      localStorage.setItem('my-doctors-last-crawl', now);
      invalidate('my-doctors');
      invalidate('doctors');
      invalidate('academic');
      refresh();
    } catch (e) {
      setCrawlResult({ error: e.message });
    } finally {
      setCrawlLoading(false);
      setTimeout(() => setCrawlResult(null), 8000);
    }
  };

  const openDetail = async (doc) => {
    try {
      const [d, v, mm] = await Promise.all([
        doctorApi.get(doc.id),
        visitApi.list(doc.id),
        memoApi.listByDoctor(doc.id, 5).catch(() => []),
      ]);
      setDetail(d); setVisits(v); setDoctorMemos(mm || []);
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    if (initialDoctorId) openDetail({ id: initialDoctorId });
  }, [initialDoctorId]);

  const submitReport = async () => {
    try {
      await visitApi.create(reportFor.id, { doctor_id: reportFor.id, visit_date: new Date().toISOString(), status: reportStatus, product: reportProduct, notes: reportNotes });
      setReportDone(true);
      invalidate('doctors');
      invalidate('my-visits');
      invalidate('dashboard');
      setTimeout(() => { setReportFor(null); setReportDone(false); refresh(); }, 1200);
    } catch (e) { alert('저장 실패: ' + e.message); }
  };

  const docs = doctors || [];
  const filtered = docs.filter(d => !searchQ || d.name?.includes(searchQ) || d.department?.includes(searchQ));

  // 병원별 그룹핑
  const hospitalGroups = {};
  filtered.forEach(d => {
    const hname = d.hospital_name || '기타';
    if (!hospitalGroups[hname]) hospitalGroups[hname] = [];
    hospitalGroups[hname].push(d);
  });
  const hospitalEntries = Object.entries(hospitalGroups).sort(([a], [b]) => a.localeCompare(b));

  const reasonLabels = {
    transferred: { label: '이직', desc: '다른 병원으로 옮겼습니다' },
    retired: { label: '퇴직', desc: '의료계를 떠났거나 정년퇴직했습니다' },
    mistake: { label: '오인 등록', desc: '잘못 등록되었습니다' },
  };

  const submitDeactivate = async () => {
    if (!deactivateFor?.doctor) return;
    try {
      await doctorApi.update(deactivateFor.doctor.id, {
        is_active: false,
        deactivated_reason: deactivateFor.reason,
      });
      invalidate('my-doctors'); invalidate('doctors'); invalidate('academic');
      setDeactivateFor(null);
      setDetail(null);
      refresh();
    } catch (e) {
      alert('처리 실패: ' + e.message);
    }
  };

  const restoreDoctor = async (doc) => {
    if (!confirm(`${doc.name} 교수를 다시 활성 상태로 복원하시겠습니까?`)) return;
    try {
      await doctorApi.update(doc.id, { is_active: true });
      invalidate('my-doctors'); invalidate('doctors'); invalidate('academic');
      refresh();
    } catch (e) {
      alert('복원 실패: ' + e.message);
    }
  };

  const formatDeactivatedAt = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
  };

  /** 수동 등록 + 이직/퇴직 처리 모달 — 모든 view 에서 공유. */
  const sharedModals = (
    <>
      <ManualDoctorModal
        open={showManual}
        onClose={() => setShowManual(false)}
        onCreated={() => { invalidate('my-doctors'); refresh(); }}
      />
      {deactivateFor && (
        <>
          <div onClick={() => setDeactivateFor(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 60, animation: 'fadeIn .15s' }} />
          <div style={{
            position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
            width: 'min(440px, 92vw)', background: 'var(--bg-1)',
            border: '1px solid var(--bd-s)', borderRadius: 12, zIndex: 61,
            boxShadow: '0 14px 60px rgba(0,0,0,.5)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid var(--bd-s)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <LogOut size={16} style={{ color: 'var(--am)' }} />
                <h3 style={{ fontFamily: 'Outfit', fontSize: 15, fontWeight: 700 }}>이직/퇴직 처리</h3>
              </div>
              <button onClick={() => setDeactivateFor(null)} style={{ width: 28, height: 28, borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--t3)' }}>
                <X size={13} />
              </button>
            </div>
            <div style={{ padding: 18 }}>
              <div style={{ marginBottom: 14, padding: 12, borderRadius: 8, background: 'var(--bg-2)', border: '1px solid var(--bd-s)' }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{deactivateFor.doctor?.name}</div>
                <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>
                  {deactivateFor.doctor?.hospital_name} · {deactivateFor.doctor?.department}
                </div>
              </div>
              <div style={{ fontSize: 12, color: 'var(--t3)', marginBottom: 10 }}>사유를 선택하세요</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
                {Object.entries(reasonLabels).map(([k, v]) => (
                  <button key={k} onClick={() => setDeactivateFor(p => ({ ...p, reason: k }))} style={{
                    padding: '10px 12px', borderRadius: 7, textAlign: 'left',
                    background: deactivateFor.reason === k ? 'var(--ac-d)' : 'var(--bg-2)',
                    color: deactivateFor.reason === k ? 'var(--ac)' : 'var(--t1)',
                    border: deactivateFor.reason === k ? '1px solid var(--ac)' : '1px solid var(--bd-s)',
                    fontSize: 13, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
                  }}>
                    <div style={{ fontWeight: 600 }}>{v.label}</div>
                    <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>{v.desc}</div>
                  </button>
                ))}
              </div>
              <div style={{ fontSize: 11, color: 'var(--t3)', padding: '8px 10px', background: 'var(--bg-2)', borderRadius: 6, lineHeight: 1.5 }}>
                처리 후에도 과거 방문 기록과 메모는 그대로 보존됩니다.
                의사 데이터는 비활성화되어 목록에서 숨겨집니다.
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, padding: '12px 18px', borderTop: '1px solid var(--bd-s)' }}>
              <button onClick={() => setDeactivateFor(null)} style={{
                padding: '8px 14px', borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)',
                color: 'var(--t2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
              }}>취소</button>
              <button onClick={submitDeactivate} style={{
                padding: '8px 14px', borderRadius: 7, background: 'var(--am)', border: 'none',
                color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
              }}>처리</button>
            </div>
          </div>
        </>
      )}
    </>
  );

  // ── 보고서 ──
  if (reportFor) {
    return (<>
      <div style={{ maxWidth: 560, animation: 'slideR .25s ease' }}>
        <button onClick={() => setReportFor(null)} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: 'var(--t3)', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit', marginBottom: 16 }}><ChevronLeft size={16} /> 돌아가기</button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20, padding: 14, borderRadius: 10, background: 'var(--bg-1)', border: '1px solid var(--bd-s)' }}>
          <div style={{ width: 40, height: 40, borderRadius: 9, background: 'var(--ac-d)', color: 'var(--ac)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 700, fontFamily: 'Outfit' }}>{reportFor.name?.[0]}</div>
          <div><div style={{ fontSize: 14, fontWeight: 600 }}>{reportFor.name}</div><div style={{ fontSize: 12, color: 'var(--t3)' }}>{reportFor.department}</div></div>
        </div>
        {reportDone ? (
          <div style={{ textAlign: 'center', padding: 60 }}><CheckCircle size={48} style={{ color: 'var(--gn)', marginBottom: 16 }} /><div style={{ fontSize: 16, fontWeight: 600 }}>저장 완료</div></div>
        ) : (
          <>
            <div style={{ marginBottom: 16 }}><label style={{ fontSize: 12, color: 'var(--t3)', fontWeight: 500, marginBottom: 6, display: 'block' }}>방문 결과</label><div style={{ display: 'flex', gap: 6 }}>{['성공', '부재', '거절'].map(s => (<button key={s} onClick={() => setReportStatus(s)} style={{ flex: 1, padding: 10, borderRadius: 8, textAlign: 'center', cursor: 'pointer', fontSize: 12, fontWeight: 500, fontFamily: 'inherit', background: reportStatus === s ? 'var(--ac-d)' : 'var(--bg-2)', color: reportStatus === s ? 'var(--ac)' : 'var(--t3)', border: `1px solid ${reportStatus === s ? 'rgba(124,106,240,.3)' : 'var(--bd-s)'}` }}>{s}</button>))}</div></div>
            <div style={{ marginBottom: 16 }}><label style={{ fontSize: 12, color: 'var(--t3)', fontWeight: 500, marginBottom: 6, display: 'block' }}>디테일링 제품</label><input value={reportProduct} onChange={e => setReportProduct(e.target.value)} placeholder="예: 관절주사A" style={{ width: '100%', padding: '10px 12px', borderRadius: 8, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: 'var(--t1)', fontSize: 13, outline: 'none' }} /></div>
            <div style={{ marginBottom: 16 }}><label style={{ fontSize: 12, color: 'var(--t3)', fontWeight: 500, marginBottom: 6, display: 'block' }}>메모</label><textarea value={reportNotes} onChange={e => setReportNotes(e.target.value)} rows={3} placeholder="핵심 대화 내용" style={{ width: '100%', padding: '10px 12px', borderRadius: 8, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: 'var(--t1)', fontSize: 13, outline: 'none', resize: 'vertical' }} /></div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}><button onClick={() => setReportFor(null)} style={{ padding: '9px 18px', borderRadius: 8, background: 'var(--bg-2)', color: 'var(--t2)', border: '1px solid var(--bd)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>취소</button><button onClick={submitReport} disabled={!reportStatus} style={{ padding: '9px 18px', borderRadius: 8, background: 'var(--ac)', color: '#fff', border: 'none', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5, opacity: reportStatus ? 1 : .5 }}><Send size={14} /> 저장</button></div>
          </>
        )}
      </div>
      {sharedModals}
    </>);
  }

  // ── 상세 ──
  if (detail) {
    const g = G[detail.visit_grade] || G.B;
    return (<>
      <div style={{ maxWidth: 600, animation: 'slideR .25s ease' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <button onClick={() => setDetail(null)} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: 'var(--t3)', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit' }}><ChevronLeft size={16} /> 돌아가기</button>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => setDeactivateFor({ doctor: detail, reason: 'transferred' })} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--am)', cursor: 'pointer', background: 'none', border: '1px solid rgba(245,158,11,.3)', borderRadius: 6, padding: '5px 10px', fontFamily: 'inherit' }}><LogOut size={13} /> 이직/퇴직 처리</button>
            <button onClick={async () => { if (!confirm(`${detail.name} 교수를 내 의료진에서 해제하시겠습니까?`)) return; await doctorApi.update(detail.id, { visit_grade: null }); invalidate('my-doctors'); invalidate('doctors'); invalidate('academic'); refresh(); setDetail(null); }} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--rd)', cursor: 'pointer', background: 'none', border: '1px solid rgba(248,113,113,.3)', borderRadius: 6, padding: '5px 10px', fontFamily: 'inherit' }}><UserMinus size={13} /> 내 의료진 해제</button>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
          <div style={{ width: 56, height: 56, borderRadius: 12, background: 'var(--ac-d)', color: 'var(--ac)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, fontWeight: 700, fontFamily: 'Outfit', flexShrink: 0 }}>{detail.name?.[0]}</div>
          <div>
            <div style={{ fontFamily: 'Outfit', fontSize: 20, fontWeight: 700 }}>{detail.name} <span style={{ fontSize: 14, color: 'var(--t3)', fontWeight: 400 }}>{detail.position}</span></div>
            <div style={{ fontSize: 13, color: 'var(--t3)', marginBottom: 8 }}>{detail.hospital_name} · {detail.department}</div>
            <span style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500, background: g.bg, color: g.c }}>{detail.visit_grade}등급</span>
          </div>
        </div>

        {/* 이직 이력 — 이전 병원 record 와 연결됐을 때 */}
        {detail.linked_doctor_id && detail.linked_hospital_name && (
          <div style={{
            marginBottom: 20, padding: '12px 14px', borderRadius: 10,
            background: 'var(--ac-d)', border: '1px solid var(--ac)',
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: 'var(--bg-1)', color: 'var(--ac)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              ↩
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--ac)', letterSpacing: '.04em', marginBottom: 2 }}>
                이전 병원 이력
              </div>
              <div style={{ fontSize: 13, color: 'var(--t1)', fontWeight: 600 }}>
                {detail.linked_hospital_name} {detail.linked_doctor_department || ''} {detail.linked_doctor_name || ''} 에서 옮겨오심
              </div>
              <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>
                과거 방문 기록과 메모는 비활성 의료진 보기에서 확인할 수 있습니다.
              </div>
            </div>
          </div>
        )}
        {/* 전문 분야 */}
        {detail.specialty && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>전문 분야</div>
            <div style={{ fontSize: 13, color: 'var(--t2)', padding: '10px 14px', background: 'var(--bg-2)', borderRadius: 8, border: '1px solid var(--bd-s)' }}>
              {detail.specialty}
            </div>
          </div>
        )}
        {(detail.schedules?.length > 0 || detail.date_schedules?.length > 0) && (
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 600, marginBottom: 10 }}>진료 시간표</div>
            <ScheduleCalendar
              schedules={detail.schedules || []}
              dateSchedules={detail.date_schedules || []}
            />
            {detail.notes && (
              <div style={{ marginTop: 10, padding: '10px 12px', borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd-s)' }}>
                <div style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 500, marginBottom: 4 }}>특이사항</div>
                <div style={{ fontSize: 12, color: 'var(--t2)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{detail.notes}</div>
              </div>
            )}
          </div>
        )}
        {/* 메모 */}
        {detail.memo && <div style={{ marginBottom: 24 }}><div style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>메모</div><div style={{ padding: 14, borderRadius: 9, background: 'var(--bg-1)', border: '1px solid var(--bd-s)', fontSize: 13, color: 'var(--t2)', lineHeight: 1.6 }}>{detail.memo}</div></div>}

        {/* 방문 기록 — visit + memo 통합 */}
        {(() => {
          const memoByVisitId = new Map(
            doctorMemos.filter(m => m.visit_log_id).map(m => [m.visit_log_id, m])
          );
          const orphanMemos = doctorMemos.filter(m => !m.visit_log_id);
          const isEmpty = visits.length === 0 && orphanMemos.length === 0;

          const aiSummaryLine = (m) => {
            const aiOk = !!(m.ai_summary && (
              (typeof m.ai_summary === 'object' && m.ai_summary.summary) ||
              (typeof m.ai_summary === 'string' && m.ai_summary.trim())
            ));
            const oneLine = (() => {
              if (aiOk && typeof m.ai_summary === 'object' && m.ai_summary.summary) {
                const s = m.ai_summary.summary;
                const pref = s['결과'] || s['논의내용'] || s['요약'];
                if (pref && String(pref).trim()) return String(pref);
                const first = Object.values(s).find(v => v && String(v).trim());
                if (first) return String(first);
              }
              return (m.raw_memo || '').slice(0, 80);
            })();
            return { aiOk, oneLine };
          };

          const statusColor = (status) => {
            if (status === '성공') return { bg: 'var(--gn-d)', c: 'var(--gn)' };
            if (status === '예정') return { bg: '#e0f2fe', c: '#0369a1' };
            return { bg: 'var(--am-d)', c: 'var(--am)' };
          };

          return (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <span style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 600 }}>방문 기록</span>
                <div style={{ display: 'flex', gap: 6 }}>
                  {doctorMemos.length > 0 && (
                    <button
                      onClick={() => onNavigate?.('memos', { filters: { doctor_id: detail.id } })}
                      style={{
                        padding: '6px 11px', borderRadius: 7,
                        background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
                        color: 'var(--t2)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
                      }}
                    >
                      전체 보기
                    </button>
                  )}
                  <button onClick={() => { setReportFor(detail); setDetail(null); }} style={{ padding: '6px 14px', borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: 'var(--t2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 4 }}><Plus size={13} /> 방문 기록</button>
                </div>
              </div>

              {isEmpty ? (
                <div style={{
                  padding: '24px 16px', textAlign: 'center',
                  background: 'var(--bg-1)', border: '1px dashed var(--bd-s)',
                  borderRadius: 10, fontSize: 13, color: 'var(--t3)',
                }}>
                  방문 기록 없음
                  <div style={{ fontSize: 11, marginTop: 4 }}>
                    방문 후 "방문결과메모"를 작성하면 여기에 표시됩니다.
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {visits.map(v => {
                    const memo = memoByVisitId.get(v.id);
                    const sc = statusColor(v.status);
                    const { aiOk, oneLine } = memo ? aiSummaryLine(memo) : { aiOk: false, oneLine: '' };
                    const clickable = !!memo;
                    return (
                      <div
                        key={`v-${v.id}`}
                        onClick={clickable ? () => onNavigate?.('memos', { filters: { doctor_id: detail.id } }) : undefined}
                        style={{
                          padding: '12px 14px', borderRadius: 9,
                          background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
                          cursor: clickable ? 'pointer' : 'default',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
                          <span style={{ fontFamily: "'JetBrains Mono'", fontSize: 11, color: 'var(--t3)' }}>
                            {new Date(v.visit_date).toLocaleDateString('ko-KR')}
                          </span>
                          <span style={{
                            padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                            background: sc.bg, color: sc.c,
                          }}>{v.status}</span>
                          {v.product && (
                            <span style={{ fontSize: 11, color: 'var(--ac)', fontWeight: 600 }}>
                              🏷 {v.product}
                            </span>
                          )}
                          {aiOk && (
                            <span style={{
                              padding: '1px 6px', borderRadius: 4,
                              background: 'var(--ac-d)', color: 'var(--ac)',
                              fontSize: 9, fontWeight: 800, fontFamily: 'Manrope',
                              display: 'inline-flex', alignItems: 'center', gap: 2, marginLeft: 'auto',
                            }}>
                              <Sparkles size={8} /> AI
                            </span>
                          )}
                        </div>
                        {memo ? (
                          <>
                            {memo.title && (
                              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)', marginBottom: 3, lineHeight: 1.35 }}>
                                {memo.title}
                              </div>
                            )}
                            {oneLine && (
                              <div style={{
                                fontSize: 12, color: 'var(--t2)', lineHeight: 1.45,
                                overflow: 'hidden', textOverflow: 'ellipsis',
                                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                              }}>
                                {oneLine}
                              </div>
                            )}
                          </>
                        ) : (
                          (v.post_notes || v.notes) && (
                            <div style={{ fontSize: 12, color: 'var(--t2)', lineHeight: 1.5 }}>
                              {v.post_notes || v.notes}
                            </div>
                          )
                        )}
                      </div>
                    );
                  })}

                  {orphanMemos.map(m => {
                    const { aiOk, oneLine } = aiSummaryLine(m);
                    return (
                      <div
                        key={`m-${m.id}`}
                        onClick={() => onNavigate?.('memos', { filters: { doctor_id: detail.id } })}
                        style={{
                          padding: '12px 14px', borderRadius: 9,
                          background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                          <span style={{ fontFamily: "'JetBrains Mono'", fontSize: 11, color: 'var(--t3)' }}>
                            {m.visit_date ? new Date(m.visit_date).toLocaleDateString('ko-KR') : ''}
                          </span>
                          <span style={{
                            padding: '2px 7px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                            background: 'var(--bg-2)', color: 'var(--t3)',
                          }}>메모</span>
                          {aiOk && (
                            <span style={{
                              padding: '1px 6px', borderRadius: 4,
                              background: 'var(--ac-d)', color: 'var(--ac)',
                              fontSize: 9, fontWeight: 800, fontFamily: 'Manrope',
                              display: 'inline-flex', alignItems: 'center', gap: 2, marginLeft: 'auto',
                            }}>
                              <Sparkles size={8} /> AI
                            </span>
                          )}
                        </div>
                        {m.title && (
                          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)', marginBottom: 3, lineHeight: 1.35 }}>
                            {m.title}
                          </div>
                        )}
                        {oneLine && (
                          <div style={{
                            fontSize: 12, color: 'var(--t2)', lineHeight: 1.45,
                            overflow: 'hidden', textOverflow: 'ellipsis',
                            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                          }}>
                            {oneLine}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })()}
      </div>
      {sharedModals}
    </>);
  }

  // ── 목록 ──
  return (
    <>
      {/* 고정 헤더 영역 */}
      <div style={{ position: 'sticky', top: 49, zIndex: 5, background: 'var(--bg-0)', marginLeft: -24, marginRight: -24, paddingLeft: 24, paddingRight: 24, paddingTop: 4, paddingBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', borderRadius: 7, padding: '6px 10px', flex: 1, maxWidth: 280 }}><Search size={14} style={{ color: 'var(--t3)' }} /><input placeholder="교수명, 진료과 검색" value={searchQ} onChange={e => setSearchQ(e.target.value)} style={{ border: 'none', background: 'none', outline: 'none', color: 'var(--t1)', fontSize: 12.5, width: '100%' }} /></div>
          <span style={{ fontSize: 12, color: 'var(--t3)' }}>{filtered.length}명</span>
          {view === 'active' && (
            <button onClick={() => setShowManual(true)} style={{
              padding: '6px 11px', borderRadius: 7,
              background: 'var(--ac-d)', color: 'var(--ac)', border: '1px solid var(--ac)',
              fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <Plus size={13} /> 수동 등록
            </button>
          )}
          <button onClick={() => setView(v => v === 'active' ? 'inactive' : 'active')} style={{
            padding: '6px 11px', borderRadius: 7,
            background: view === 'inactive' ? 'var(--am-d)' : 'var(--bg-2)',
            color: view === 'inactive' ? 'var(--am)' : 'var(--t3)',
            border: `1px solid ${view === 'inactive' ? 'var(--am)' : 'var(--bd-s)'}`,
            fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', gap: 4,
          }}>
            <Archive size={13} />
            {view === 'inactive' ? '활성 의료진 보기' : '비활성/이직·퇴직 보기'}
          </button>
        </div>

        {view === 'inactive' && (
          <div style={{
            padding: '10px 14px', borderRadius: 9, marginBottom: 10,
            background: 'var(--am-d)', border: '1px solid rgba(245,158,11,.3)',
            fontSize: 12, color: 'var(--am)', lineHeight: 1.55,
          }}>
            이직·퇴직·오인 등록으로 비활성화된 의료진입니다.
            과거 방문 기록과 메모는 그대로 보존되어 있고, <b>복원</b> 버튼으로 다시 활성 목록으로 되돌릴 수 있습니다.
          </div>
        )}

        {/* 일정 업데이트 — 활성 view 에서만 */}
        {view === 'active' && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 14px', borderRadius: 9,
          background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
          marginBottom: 8,
        }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--t2)' }}>일정 업데이트</div>
          <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>
            {lastCrawlDate ? `마지막: ${formatDate(lastCrawlDate)}` : '아직 업데이트 안 됨'}
          </div>
        </div>
        <button
          onClick={runScheduleUpdate}
          disabled={crawlLoading}
          style={{
            padding: '7px 14px', borderRadius: 7,
            background: 'var(--ac)', color: '#fff', border: 'none',
            fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', gap: 5,
            opacity: crawlLoading ? .6 : 1,
          }}
        >
          <RefreshCw size={13} style={crawlLoading ? { animation: 'spin .8s linear infinite' } : {}} />
          {crawlLoading ? '업데이트 중…' : '일정 업데이트'}
        </button>
      </div>
      )}

      {/* 크롤링 결과 알림 */}
      {crawlResult && (
        <div style={{
          padding: '10px 14px', borderRadius: 8, marginBottom: 12, fontSize: 12,
          animation: 'fadeUp .2s ease',
          background: crawlResult.error ? 'var(--rd-d)' : 'var(--gn-d)',
          border: `1px solid ${crawlResult.error ? 'rgba(248,113,113,.2)' : 'rgba(52,211,153,.2)'}`,
          color: crawlResult.error ? 'var(--rd)' : 'var(--gn)',
        }}>
          {crawlResult.error ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <AlertTriangle size={13} />
              <span>업데이트 실패: {crawlResult.error}</span>
            </div>
          ) : (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <CheckCircle size={13} />
                <span>{crawlResult.crawled}명 업데이트, {crawlResult.changes}건 변경</span>
              </div>
              {crawlResult.errors?.length > 0 && (
                <div style={{ marginTop: 6, fontSize: 11, color: 'var(--am)' }}>
                  오류: {crawlResult.errors.join(', ')}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      </div>

      {loading && !docs.length ? <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)' }}>로딩 중…</div> : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)', fontSize: 13 }}>
          {searchQ ? '검색 결과 없음' : '등록된 의료진이 없습니다. 의료진 검색에서 등록해주세요.'}
        </div>
      ) : (
        <div>
          {hospitalEntries.map(([hname, group]) => (
            <div key={hname} style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)' }}>{hname}</span>
                <span style={{ fontSize: 11, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>{group.length}</span>
                <div style={{ flex: 1, height: 1, background: 'var(--bd-s)' }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8 }}>
                {group.map((d, i) => {
                  const g = G[d.visit_grade] || G.B;
                  const isManual = d.source === 'manual';
                  const isInactive = view === 'inactive';
                  const reason = REASON_LABELS[d.deactivated_reason] || null;
                  return (
                    <div
                      key={d.id}
                      onClick={isInactive ? undefined : () => openDetail(d)}
                      style={{
                        background: isInactive ? 'var(--bg-2)' : 'var(--bg-1)',
                        border: `1px solid ${isInactive ? 'var(--bd-s)' : 'var(--bd-s)'}`,
                        borderRadius: 10, padding: 16,
                        cursor: isInactive ? 'default' : 'pointer',
                        opacity: isInactive ? .85 : 1,
                        transition: 'all .12s',
                        animation: `fadeUp .3s ease ${i * .03}s both`,
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                        <div style={{ width: 38, height: 38, borderRadius: 9, background: isInactive ? 'var(--bg-3)' : 'var(--ac-d)', color: isInactive ? 'var(--t3)' : 'var(--ac)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 700, fontFamily: 'Outfit' }}>{d.name?.[0]}</div>
                        <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                          {isManual && (
                            <span title="수동 등록" style={{ padding: '3px 6px', borderRadius: 4, fontSize: 9, fontWeight: 700, fontFamily: "'JetBrains Mono'", background: 'var(--bg-3)', color: 'var(--t2)', border: '1px solid var(--bd-s)' }}>수동</span>
                          )}
                          {isInactive && reason ? (
                            <span style={{ padding: '3px 7px', borderRadius: 4, fontSize: 10, fontWeight: 700, fontFamily: "'JetBrains Mono'", background: 'var(--bg-3)', color: reason.color, border: `1px solid ${reason.color}` }}>
                              {reason.text}
                            </span>
                          ) : (
                            <span style={{ padding: '3px 7px', borderRadius: 4, fontSize: 10, fontWeight: 700, fontFamily: "'JetBrains Mono'", background: g.bg, color: g.c }}>{d.visit_grade}</span>
                          )}
                        </div>
                      </div>
                      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2, color: isInactive ? 'var(--t2)' : 'var(--t1)' }}>{d.name} <span style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 400 }}>{d.position}</span></div>
                      <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 6 }}>{d.department}</div>
                      {!isInactive && d.linked_doctor_id && d.linked_hospital_name && (
                        <div style={{
                          fontSize: 10, color: 'var(--ac)', marginBottom: 8,
                          display: 'flex', alignItems: 'center', gap: 3,
                          padding: '3px 7px', background: 'var(--ac-d)',
                          borderRadius: 4, border: '1px solid rgba(124,106,240,.2)',
                          alignSelf: 'flex-start', width: 'fit-content',
                        }}>
                          ← {d.linked_hospital_name} 에서 옮겨오심
                        </div>
                      )}
                      {isInactive && d.deactivated_at && (
                        <div style={{ fontSize: 10, color: 'var(--t3)', marginBottom: 8, fontFamily: "'JetBrains Mono'" }}>
                          처리일: {formatDeactivatedAt(d.deactivated_at)}
                        </div>
                      )}
                      <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid var(--bd-s)' }}>
                        <span style={{ fontSize: 10, color: 'var(--t3)' }}>ID: {d.id}</span>
                        {isInactive ? (
                          <button onClick={e => { e.stopPropagation(); restoreDoctor(d); }} style={{
                            padding: '4px 10px', borderRadius: 5,
                            background: 'var(--ac-d)', border: '1px solid var(--ac)',
                            color: 'var(--ac)', fontSize: 10, fontWeight: 600,
                            cursor: 'pointer', fontFamily: 'inherit',
                            display: 'flex', alignItems: 'center', gap: 3,
                          }}>
                            <RotateCcw size={10} /> 복원
                          </button>
                        ) : (
                          <button onClick={e => { e.stopPropagation(); setReportFor(d); }} style={{ padding: '4px 10px', borderRadius: 5, background: 'var(--bg-3)', border: '1px solid var(--bd-s)', color: 'var(--t2)', fontSize: 10, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 3 }}><FileText size={10} /> 보고서</button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
      {sharedModals}
    </>
  );
}
