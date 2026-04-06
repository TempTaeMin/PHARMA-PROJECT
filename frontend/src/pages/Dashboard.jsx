import { TrendingUp, ChevronRight, AlertTriangle } from 'lucide-react';
import { doctorApi, hospitalApi } from '../api/client';
import { useCachedApi } from '../hooks/useCachedApi';

const G = { A: { bg: 'var(--rd-d)', c: 'var(--rd)' }, B: { bg: 'var(--am-d)', c: 'var(--am)' }, C: { bg: 'var(--bl-d)', c: 'var(--bl)' } };

export default function Dashboard({ onNavigate }) {
  const { data: doctors, loading: dLoad, error: dErr } = useCachedApi('doctors', doctorApi.list, { ttlKey: 'doctors' });
  const { data: hospitals, loading: hLoad } = useCachedApi('hospitals', hospitalApi.list, { ttlKey: 'hospitals' });

  if (dLoad && !doctors) return <Loader />;
  if (dErr && !doctors) return <ErrView msg={dErr} />;

  const docs = doctors || [];
  const hosps = hospitals || [];

  const kpis = [
    { l: '담당 교수', v: docs.length, s: `${hosps.length}개 병원`, c: 'var(--t1)' },
    { l: 'A등급', v: docs.filter(d => d.visit_grade === 'A').length, s: '주 1회', c: 'var(--rd)' },
    { l: 'B등급', v: docs.filter(d => d.visit_grade === 'B').length, s: '격주', c: 'var(--am)' },
    { l: 'C등급', v: docs.filter(d => d.visit_grade === 'C').length, s: '월 1회', c: 'var(--bl)' },
  ];

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 24 }}>
        {kpis.map((k, i) => (
          <div key={i} style={{ background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 10, padding: '16px 18px', animation: `fadeUp .3s ease ${i * .05}s both` }}>
            <div style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 500 }}>{k.l}</div>
            <div style={{ fontFamily: 'Outfit', fontSize: 28, fontWeight: 700, letterSpacing: '-.03em', color: k.c, margin: '4px 0' }}>{k.v}</div>
            <div style={{ fontSize: 11, color: 'var(--t3)' }}>{k.s}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 600 }}>내 교수</span>
            <button onClick={() => onNavigate('my-doctors')} style={{ fontSize: 11, color: 'var(--t3)', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 2 }}>전체 보기 <ChevronRight size={13} /></button>
          </div>
          {docs.slice(0, 5).map((d, i) => (
            <div key={d.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 9, background: 'var(--bg-1)', border: '1px solid var(--bd-s)', marginBottom: 5, animation: `fadeUp .3s ease ${i * .04}s both` }}>
              <div style={{ width: 34, height: 34, borderRadius: 8, background: 'var(--ac-d)', color: 'var(--ac)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 700, fontFamily: 'Outfit', flexShrink: 0 }}>{d.name?.[0]}</div>
              <div style={{ flex: 1 }}><div style={{ fontSize: 13, fontWeight: 500 }}>{d.name} <span style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 400 }}>{d.position}</span></div><div style={{ fontSize: 11, color: 'var(--t3)' }}>{d.department}</div></div>
              <span style={{ padding: '3px 7px', borderRadius: 4, fontSize: 10, fontWeight: 700, fontFamily: "'JetBrains Mono'", ...(G[d.visit_grade] || G.B) }}>{d.visit_grade}</span>
            </div>
          ))}
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 600 }}>병원 현황</span>
            <button onClick={() => onNavigate('browse')} style={{ fontSize: 11, color: 'var(--t3)', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 2 }}>전체 보기 <ChevronRight size={13} /></button>
          </div>
          {hosps.map((h, i) => (
            <div key={h.id} onClick={() => onNavigate('browse')} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 9, background: 'var(--bg-1)', border: '1px solid var(--bd-s)', marginBottom: 5, cursor: 'pointer', animation: `fadeUp .3s ease ${i * .04}s both` }}>
              <div style={{ width: 34, height: 34, borderRadius: 8, background: 'var(--ac-d)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>🏥</div>
              <div style={{ flex: 1 }}><div style={{ fontSize: 13, fontWeight: 500 }}>{h.name}</div><div style={{ fontSize: 11, color: 'var(--t3)' }}>{h.address}</div></div>
              <span style={{ fontSize: 11, color: 'var(--t2)', fontFamily: "'JetBrains Mono'" }}>{h.code}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function Loader() {
  return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300 }}><div style={{ width: 24, height: 24, border: '2px solid var(--bd)', borderTopColor: 'var(--ac)', borderRadius: '50%', animation: 'spin .8s linear infinite' }} /><span style={{ marginLeft: 10, color: 'var(--t3)', fontSize: 13 }}>로딩 중…</span></div>;
}
function ErrView({ msg }) {
  return <div style={{ textAlign: 'center', padding: 60 }}><AlertTriangle size={32} style={{ color: 'var(--rd)', marginBottom: 12 }} /><div style={{ fontSize: 14 }}>API 연결 실패</div><div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 4 }}>{msg}</div><div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 8 }}>백엔드: <code style={{ color: 'var(--ac)', fontFamily: "'JetBrains Mono'" }}>uvicorn app.main:app --reload</code></div></div>;
}
