import { useState, useEffect } from 'react';
import { CheckCircle, AlertTriangle, RefreshCw, ChevronRight, ChevronDown, ChevronLeft, Star, Users, Activity, Loader } from 'lucide-react';
import { crawlApi, hospitalApi } from '../api/client';

export default function CrawlStatus() {
  const [hospitals, setHospitals] = useState([]);
  const [dbHospitals, setDbHospitals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('my'); // 'my' | 'hospital' | 'dept'

  // 내 교수 크롤링
  const [myLoading, setMyLoading] = useState(false);
  const [myResult, setMyResult] = useState(null);

  // 병원별 크롤링
  const [runningCode, setRunningCode] = useState(null);
  const [crawlResult, setCrawlResult] = useState(null);

  // 진료과 선택 크롤링
  const [selectedHospital, setSelectedHospital] = useState(null);
  const [departments, setDepartments] = useState([]);
  const [deptLoading, setDeptLoading] = useState(false);
  const [runningDept, setRunningDept] = useState(null);
  const [deptResult, setDeptResult] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const [crawl, db] = await Promise.all([crawlApi.hospitals(), hospitalApi.list()]);
        setHospitals(crawl.hospitals || []);
        setDbHospitals(db || []);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    }
    load();
  }, []);

  // ── 내 교수 크롤링 ──
  const runMyDoctors = async () => {
    setMyLoading(true);
    setMyResult(null);
    try {
      const res = await fetch('/api/crawl/my-doctors', { method: 'POST' });
      const data = await res.json();
      setMyResult(data);
    } catch (e) {
      setMyResult({ error: e.message });
    }
    finally { setMyLoading(false); }
  };

  // ── 병원 전체 크롤링 ──
  const runHospitalCrawl = async (code) => {
    setRunningCode(code);
    setCrawlResult(null);
    try {
      const res = await fetch(`/api/crawl/run/${code}`, { method: 'POST' });
      const data = await res.json();
      setCrawlResult({ code, ...data });
    } catch (e) {
      setCrawlResult({ code, error: e.message });
    }
    finally { setRunningCode(null); }
  };

  // ── 진료과 목록 로드 ──
  const openDeptSelect = async (hospital) => {
    setSelectedHospital(hospital);
    setDeptLoading(true);
    setDeptResult(null);
    try {
      const code = hospital.code || dbHospitals.find(h => h.name === hospital.name)?.code || hospital.code;
      const res = await crawlApi.departments(code);
      setDepartments(res.departments || []);
    } catch (e) {
      setDepartments([]);
    }
    finally { setDeptLoading(false); }
  };

  // ── 진료과 크롤링 ──
  const runDeptCrawl = async (deptCode, deptName) => {
    const hCode = selectedHospital.code || dbHospitals.find(h => h.name === selectedHospital.name)?.code;
    if (!hCode) return;
    setRunningDept(deptCode);
    setDeptResult(null);
    try {
      const res = await fetch(`/api/crawl/department/${hCode}/${deptCode}`, { method: 'POST' });
      const data = await res.json();
      setDeptResult({ dept: deptName, ...data });
    } catch (e) {
      setDeptResult({ dept: deptName, error: e.message });
    }
    finally { setRunningDept(null); }
  };

  if (loading) return <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)' }}>로딩 중…</div>;

  return (
    <>
      {/* 탭 */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {[
          { id: 'my', label: '내 의료진 크롤링', icon: Star },
          { id: 'hospital', label: '병원별 크롤링', icon: Activity },
          { id: 'dept', label: '진료과 선택 크롤링', icon: Users },
        ].map(t => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding: '9px 16px', borderRadius: 8, fontSize: 12, fontWeight: 500,
              cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 5,
              background: tab === t.id ? 'var(--ac-d)' : 'var(--bg-2)',
              color: tab === t.id ? 'var(--ac)' : 'var(--t3)',
              border: `1px solid ${tab === t.id ? 'rgba(124,106,240,.3)' : 'var(--bd-s)'}`,
            }}>
              <Icon size={13} /> {t.label}
            </button>
          );
        })}
      </div>

      {/* ═══ 내 의료진 크롤링 ═══ */}
      {tab === 'my' && (
        <div>
          <div style={{ padding: 20, borderRadius: 12, background: 'var(--bg-1)', border: '1px solid var(--bd-s)', marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div>
                <div style={{ fontFamily: 'Outfit', fontSize: 15, fontWeight: 600 }}>내 의료진 일정 크롤링</div>
                <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 2 }}>
                  등록된 담당 교수들의 진료일정만 빠르게 업데이트합니다
                </div>
              </div>
              <button onClick={runMyDoctors} disabled={myLoading} style={{
                padding: '10px 20px', borderRadius: 8, background: 'var(--ac)', color: '#fff',
                border: 'none', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', gap: 6, opacity: myLoading ? .6 : 1,
              }}>
                <RefreshCw size={14} style={{ animation: myLoading ? 'spin .8s linear infinite' : 'none' }} />
                {myLoading ? '크롤링 중…' : '내 의료진 크롤링'}
              </button>
            </div>

            <div style={{ fontSize: 11, color: 'var(--t3)', padding: '10px 14px', background: 'var(--bg-2)', borderRadius: 8, lineHeight: 1.6 }}>
              • 내 의료진으로 등록된 의료진만 크롤링합니다<br/>
              • 진료일정이 변경되면 자동으로 DB에 반영됩니다<br/>
              • 변경 사항은 알림으로 전달됩니다
            </div>
          </div>

          {/* 결과 */}
          {myResult && (
            <div style={{
              padding: 16, borderRadius: 10, animation: 'fadeUp .2s ease',
              background: myResult.error ? 'var(--rd-d)' : 'var(--gn-d)',
              border: `1px solid ${myResult.error ? 'rgba(248,113,113,.2)' : 'rgba(52,211,153,.2)'}`,
            }}>
              {myResult.error ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--rd)' }}>
                  <AlertTriangle size={16} />
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>크롤링 실패</div>
                    <div style={{ fontSize: 12, opacity: .8, marginTop: 2 }}>{myResult.error}</div>
                    <div style={{ fontSize: 11, marginTop: 4, color: 'var(--t3)' }}>
                      실제 병원 사이트에 접속할 수 있는 네트워크에서 실행해주세요
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ color: 'var(--gn)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <CheckCircle size={16} />
                    <span style={{ fontSize: 13, fontWeight: 600 }}>크롤링 완료</span>
                  </div>
                  <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
                    <span>크롤링: <strong>{myResult.crawled}</strong>/{myResult.total}명</span>
                    <span>일정 변경: <strong>{myResult.changes}</strong>건</span>
                  </div>
                  {myResult.errors?.length > 0 && (
                    <div style={{ marginTop: 8, fontSize: 11, color: 'var(--am)' }}>
                      오류: {myResult.errors.join(', ')}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ═══ 병원별 크롤링 ═══ */}
      {tab === 'hospital' && (
        <div>
          <div style={{ fontSize: 12, color: 'var(--t3)', marginBottom: 12 }}>
            병원 전체 교수를 크롤링합니다. 시간이 오래 걸릴 수 있습니다.
          </div>

          {crawlResult && (
            <div style={{
              padding: '12px 16px', borderRadius: 9, marginBottom: 12,
              background: crawlResult.error ? 'var(--rd-d)' : 'var(--gn-d)',
              border: `1px solid ${crawlResult.error ? 'rgba(248,113,113,.2)' : 'rgba(52,211,153,.2)'}`,
              fontSize: 12, animation: 'fadeUp .2s ease',
            }}>
              {crawlResult.error ? (
                <span style={{ color: 'var(--rd)' }}>
                  <AlertTriangle size={12} style={{ display: 'inline', verticalAlign: -2, marginRight: 4 }} />
                  {crawlResult.code} 실패: {crawlResult.error}
                </span>
              ) : (
                <span style={{ color: 'var(--gn)' }}>
                  <CheckCircle size={12} style={{ display: 'inline', verticalAlign: -2, marginRight: 4 }} />
                  {crawlResult.code} 크롤링 {crawlResult.crawl_status} — {crawlResult.doctors_found}명 발견
                  {crawlResult.db_save && ` → DB 저장 ${crawlResult.db_save.saved}명 신규, ${crawlResult.db_save.updated}명 업데이트`}
                </span>
              )}
            </div>
          )}

          {hospitals.map((h, i) => (
            <div key={h.code} style={{
              display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px', borderRadius: 10,
              background: 'var(--bg-1)', border: '1px solid var(--bd-s)', marginBottom: 6,
              animation: `fadeUp .3s ease ${i * .04}s both`,
            }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--gn-d)', color: 'var(--gn)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CheckCircle size={18} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 500 }}>
                  {h.name}
                  <span style={{ marginLeft: 6, fontFamily: "'JetBrains Mono'", fontSize: 11, color: 'var(--t3)' }}>{h.code}</span>
                </div>
              </div>
              <button onClick={() => runHospitalCrawl(h.code)} disabled={!!runningCode} style={{
                padding: '6px 14px', borderRadius: 6, background: 'var(--bg-3)', border: '1px solid var(--bd)',
                color: 'var(--t2)', fontSize: 11, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', gap: 4, opacity: runningCode ? .6 : 1,
              }}>
                <RefreshCw size={12} style={{ animation: runningCode === h.code ? 'spin .8s linear infinite' : 'none' }} />
                {runningCode === h.code ? '실행 중…' : '크롤링'}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ═══ 진료과 선택 크롤링 ═══ */}
      {tab === 'dept' && (
        <div>
          {!selectedHospital ? (
            <>
              <div style={{ fontSize: 12, color: 'var(--t3)', marginBottom: 12 }}>
                병원을 선택한 후, 원하는 진료과만 골라서 크롤링할 수 있습니다.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
                {hospitals.map((h, i) => (
                  <div key={h.code} onClick={() => openDeptSelect(h)} style={{
                    background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 10,
                    padding: 16, cursor: 'pointer', transition: 'all .12s',
                    display: 'flex', alignItems: 'center', gap: 12,
                    animation: `fadeUp .3s ease ${i * .04}s both`,
                  }}>
                    <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--ac-d)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>🏥</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 500 }}>{h.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--t3)' }}>{h.code}</div>
                    </div>
                    <ChevronRight size={14} style={{ color: 'var(--t3)' }} />
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div style={{ animation: 'slideR .25s ease' }}>
              {/* 브레드크럼 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16, fontSize: 13 }}>
                <span onClick={() => { setSelectedHospital(null); setDeptResult(null); }} style={{ color: 'var(--t3)', cursor: 'pointer' }}>병원 선택</span>
                <ChevronRight size={13} style={{ color: 'var(--t3)' }} />
                <span style={{ color: 'var(--t1)' }}>{selectedHospital.name} 진료과</span>
              </div>

              {/* 결과 */}
              {deptResult && (
                <div style={{
                  padding: '12px 16px', borderRadius: 9, marginBottom: 12,
                  background: deptResult.error ? 'var(--rd-d)' : 'var(--gn-d)',
                  border: `1px solid ${deptResult.error ? 'rgba(248,113,113,.2)' : 'rgba(52,211,153,.2)'}`,
                  fontSize: 12, animation: 'fadeUp .2s ease',
                }}>
                  {deptResult.error ? (
                    <span style={{ color: 'var(--rd)' }}>{deptResult.dept} 크롤링 실패: {deptResult.error}</span>
                  ) : (
                    <span style={{ color: 'var(--gn)' }}>
                      <CheckCircle size={12} style={{ display: 'inline', verticalAlign: -2, marginRight: 4 }} />
                      {deptResult.dept} 크롤링 완료 — {deptResult.saved || 0}명 신규, {deptResult.updated || 0}명 업데이트
                    </span>
                  )}
                </div>
              )}

              {deptLoading ? (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--t3)' }}>진료과 목록 로딩 중…</div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {departments.map((d, i) => (
                    <button key={d.code} onClick={() => runDeptCrawl(d.code, d.name)} disabled={!!runningDept} style={{
                      padding: '10px 16px', borderRadius: 8, fontSize: 12, fontWeight: 500,
                      cursor: 'pointer', fontFamily: 'inherit',
                      background: runningDept === d.code ? 'var(--ac-d)' : 'var(--bg-1)',
                      color: runningDept === d.code ? 'var(--ac)' : 'var(--t2)',
                      border: `1px solid ${runningDept === d.code ? 'rgba(124,106,240,.3)' : 'var(--bd-s)'}`,
                      display: 'flex', alignItems: 'center', gap: 5,
                      opacity: runningDept && runningDept !== d.code ? .5 : 1,
                      animation: `fadeUp .2s ease ${i * .02}s both`,
                    }}>
                      {runningDept === d.code && <RefreshCw size={11} style={{ animation: 'spin .8s linear infinite' }} />}
                      {d.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
