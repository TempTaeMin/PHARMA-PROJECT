import { useState } from 'react';
import { Search, Plus, Clock, AlertTriangle, ChevronLeft, FileText, Send, CheckCircle, XCircle, UserMinus } from 'lucide-react';
import { doctorApi, visitApi } from '../api/client';
import { useCachedApi } from '../hooks/useCachedApi';
import { invalidate } from '../api/cache';

const G = { A: { bg: 'var(--rd-d)', c: 'var(--rd)' }, B: { bg: 'var(--am-d)', c: 'var(--am)' }, C: { bg: 'var(--bl-d)', c: 'var(--bl)' } };
const DAY_NAMES = ['월', '화', '수', '목', '금', '토'];
const SLOT_NAMES = { morning: '오전', afternoon: '오후', evening: '야간' };

export default function MyDoctors() {
  const { data: doctors, loading, refresh } = useCachedApi('my-doctors', () => doctorApi.list({ my_only: true }), { ttlKey: 'doctors' });
  const [searchQ, setSearchQ] = useState('');
  const [detail, setDetail] = useState(null);
  const [visits, setVisits] = useState([]);
  const [reportFor, setReportFor] = useState(null);
  const [reportStatus, setReportStatus] = useState('');
  const [reportProduct, setReportProduct] = useState('');
  const [reportNotes, setReportNotes] = useState('');
  const [reportDone, setReportDone] = useState(false);

  const openDetail = async (doc) => {
    try {
      const [d, v] = await Promise.all([doctorApi.get(doc.id), visitApi.list(doc.id)]);
      setDetail(d); setVisits(v);
    } catch (e) { console.error(e); }
  };

  const submitReport = async () => {
    try {
      await visitApi.create(reportFor.id, { doctor_id: reportFor.id, visit_date: new Date().toISOString(), status: reportStatus, product: reportProduct, notes: reportNotes });
      setReportDone(true);
      invalidate('doctors');
      setTimeout(() => { setReportFor(null); setReportDone(false); refresh(); }, 1200);
    } catch (e) { alert('저장 실패: ' + e.message); }
  };

  const docs = doctors || [];
  const filtered = docs.filter(d => !searchQ || d.name?.includes(searchQ) || d.department?.includes(searchQ));

  // ── 보고서 ──
  if (reportFor) {
    return (
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
    );
  }

  // ── 상세 ──
  if (detail) {
    const g = G[detail.visit_grade] || G.B;
    return (
      <div style={{ maxWidth: 600, animation: 'slideR .25s ease' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <button onClick={() => setDetail(null)} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, color: 'var(--t3)', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit' }}><ChevronLeft size={16} /> 돌아가기</button>
          <button onClick={async () => { if (!confirm(`${detail.name} 교수를 내 교수에서 해제하시겠습니까?`)) return; await doctorApi.update(detail.id, { visit_grade: null }); invalidate('my-doctors'); invalidate('doctors'); refresh(); setDetail(null); }} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--rd)', cursor: 'pointer', background: 'none', border: '1px solid rgba(248,113,113,.3)', borderRadius: 6, padding: '5px 10px', fontFamily: 'inherit' }}><UserMinus size={13} /> 내 교수 해제</button>
        </div>
        <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
          <div style={{ width: 56, height: 56, borderRadius: 12, background: 'var(--ac-d)', color: 'var(--ac)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, fontWeight: 700, fontFamily: 'Outfit', flexShrink: 0 }}>{detail.name?.[0]}</div>
          <div>
            <div style={{ fontFamily: 'Outfit', fontSize: 20, fontWeight: 700 }}>{detail.name} <span style={{ fontSize: 14, color: 'var(--t3)', fontWeight: 400 }}>{detail.position}</span></div>
            <div style={{ fontSize: 13, color: 'var(--t3)', marginBottom: 8 }}>{detail.hospital_name} · {detail.department} · {detail.specialty}</div>
            <span style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500, background: g.bg, color: g.c }}>{detail.visit_grade}등급</span>
          </div>
        </div>
        {/* 전문 분야 */}
        {detail.specialty && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>전문 분야</div>
            <div style={{ fontSize: 13, color: 'var(--t2)', padding: '10px 14px', background: 'var(--bg-2)', borderRadius: 8, border: '1px solid var(--bd-s)' }}>
              {detail.specialty}
            </div>
          </div>
        )}
        {detail.schedules?.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 600, marginBottom: 10 }}>진료 시간표</div>
            <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, border: '1px solid var(--bd-s)', borderRadius: 10, overflow: 'hidden' }}>
              <thead><tr>{['구분', ...DAY_NAMES].map(h => <th key={h} style={{ padding: '10px 12px', textAlign: 'center', fontSize: 12, background: 'var(--bg-2)', color: 'var(--t3)', fontWeight: 500, borderBottom: '1px solid var(--bd-s)' }}>{h}</th>)}</tr></thead>
              <tbody>{['morning', 'afternoon'].map(slot => (<tr key={slot}><td style={{ padding: '10px', textAlign: 'center', fontSize: 12, color: 'var(--t3)', fontWeight: 500, background: 'var(--bg-1)', borderBottom: '1px solid var(--bd-s)' }}>{slot === 'morning' ? '오전' : '오후'}</td>{[0,1,2,3,4,5].map(di => { const has = detail.schedules.some(s => s.day_of_week === di && s.time_slot === slot); return <td key={di} style={{ padding: '10px', textAlign: 'center', background: 'var(--bg-1)', borderBottom: '1px solid var(--bd-s)' }}>{has ? <span style={{ color: 'var(--ac)', fontWeight: 700 }}>●</span> : <span style={{ color: 'var(--t3)' }}>-</span>}</td>; })}</tr>))}</tbody>
            </table>
            {/* 진료일 태그 */}
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 10 }}>
              {detail.schedules.map((s, i) => (
                <span key={i} style={{ padding: '4px 10px', borderRadius: 5, fontSize: 11, fontWeight: 500, background: 'var(--ac-d)', color: 'var(--ac)', border: '1px solid rgba(124,106,240,.2)' }}>
                  {DAY_NAMES[s.day_of_week] || '?'} {SLOT_NAMES[s.time_slot] || ''}
                </span>
              ))}
            </div>
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
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 600 }}>방문 이력</span>
            <button onClick={() => { setReportFor(detail); setDetail(null); }} style={{ padding: '6px 14px', borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: 'var(--t2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 4 }}><Plus size={13} /> 방문 기록</button>
          </div>
          {visits.length === 0 && <div style={{ padding: 30, textAlign: 'center', color: 'var(--t3)', fontSize: 13 }}>방문 기록 없음</div>}
          {visits.map((v, i) => (
            <div key={v.id} style={{ padding: '12px 14px', borderRadius: 9, background: 'var(--bg-1)', border: '1px solid var(--bd-s)', marginBottom: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}><span style={{ fontFamily: "'JetBrains Mono'", fontSize: 11, color: 'var(--t3)' }}>{new Date(v.visit_date).toLocaleDateString('ko-KR')}</span><span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600, background: v.status === '성공' ? 'var(--gn-d)' : 'var(--am-d)', color: v.status === '성공' ? 'var(--gn)' : 'var(--am)' }}>{v.status}</span></div>
              {v.product && <div style={{ fontSize: 12, color: 'var(--ac)', marginBottom: 4 }}>{v.product}</div>}
              {v.notes && <div style={{ fontSize: 12, color: 'var(--t2)', lineHeight: 1.5 }}>{v.notes}</div>}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── 목록 ──
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', borderRadius: 7, padding: '6px 10px', flex: 1, maxWidth: 280 }}><Search size={14} style={{ color: 'var(--t3)' }} /><input placeholder="교수명, 진료과 검색" value={searchQ} onChange={e => setSearchQ(e.target.value)} style={{ border: 'none', background: 'none', outline: 'none', color: 'var(--t1)', fontSize: 12.5, width: '100%' }} /></div>
        <span style={{ fontSize: 12, color: 'var(--t3)' }}>{filtered.length}명</span>
      </div>
      {loading && !docs.length ? <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)' }}>로딩 중…</div> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8 }}>
          {filtered.map((d, i) => {
            const g = G[d.visit_grade] || G.B;
            return (
              <div key={d.id} onClick={() => openDetail(d)} style={{ background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 10, padding: 16, cursor: 'pointer', transition: 'all .12s', animation: `fadeUp .3s ease ${i * .03}s both` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div style={{ width: 38, height: 38, borderRadius: 9, background: 'var(--ac-d)', color: 'var(--ac)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, fontWeight: 700, fontFamily: 'Outfit' }}>{d.name?.[0]}</div>
                  <span style={{ padding: '3px 7px', borderRadius: 4, fontSize: 10, fontWeight: 700, fontFamily: "'JetBrains Mono'", background: g.bg, color: g.c }}>{d.visit_grade}</span>
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>{d.name} <span style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 400 }}>{d.position}</span></div>
                <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 10 }}>{d.department} · {d.specialty}</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid var(--bd-s)' }}>
                  <span style={{ fontSize: 10, color: 'var(--t3)' }}>ID: {d.id}</span>
                  <button onClick={e => { e.stopPropagation(); setReportFor(d); }} style={{ padding: '4px 10px', borderRadius: 5, background: 'var(--bg-3)', border: '1px solid var(--bd-s)', color: 'var(--t2)', fontSize: 10, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 3 }}><FileText size={10} /> 보고서</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
