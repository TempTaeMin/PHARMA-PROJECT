import { useState, useEffect, useCallback } from 'react';
import { Search, ChevronRight, ChevronLeft, Star, RefreshCw, Clock, UserPlus, X, AlertTriangle, CheckCircle } from 'lucide-react';
import { crawlApi } from '../api/client';
import { useCachedApi } from '../hooks/useCachedApi';
import { invalidate } from '../api/cache';

const DAY_NAMES = ['월', '화', '수', '목', '금', '토'];
const SLOT_NAMES = { morning: '오전', afternoon: '오후', evening: '야간' };

export default function BrowseDoctors({ onNavigate }) {
  const { data: crawlHospitals, loading } = useCachedApi('crawl-hospitals', crawlApi.hospitals, { ttlKey: 'hospitals' });

  // 병원 선택
  const [selectedHospital, setSelectedHospital] = useState(null);
  const [hospitalSearchQ, setHospitalSearchQ] = useState('');

  // 교수 목록 (DB에서)
  const [doctors, setDoctors] = useState([]);
  const [doctorsLoading, setDoctorsLoading] = useState(false);
  const [lastCrawled, setLastCrawled] = useState(null);
  const [searchQ, setSearchQ] = useState('');
  const [searchTimer, setSearchTimer] = useState(null);

  // 크롤링 상태
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);

  // 교수 미리보기
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [scheduleError, setScheduleError] = useState(null);
  const [registering, setRegistering] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [registeredSet, setRegisteredSet] = useState(new Set());

  // ── DB에서 교수 목록 조회 ──
  const loadDoctors = useCallback(async (code, search = '') => {
    setDoctorsLoading(true);
    try {
      const res = await crawlApi.browse(code, search);
      setDoctors(res.doctors || []);
      setLastCrawled(res.last_crawled);
      // DB에 데이터가 없으면 자동으로 크롤링 시작
      if (!res.doctors?.length && !search) {
        syncHospital(code);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setDoctorsLoading(false);
    }
  }, []);

  // ── 병원 클릭 ──
  const openHospital = (hospital) => {
    setSelectedHospital(hospital);
    closePreview();
    setSearchQ('');
    setSyncResult(null);
    loadDoctors(hospital.code);
  };

  // ── 검색 (디바운스) ──
  const handleSearch = (q) => {
    setSearchQ(q);
    if (searchTimer) clearTimeout(searchTimer);
    const timer = setTimeout(() => {
      if (selectedHospital) loadDoctors(selectedHospital.code, q);
    }, 300);
    setSearchTimer(timer);
  };

  // ── 새로 크롤링 ──
  const syncHospital = async (code) => {
    const hospitalCode = code || selectedHospital?.code;
    if (!hospitalCode) return;
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await crawlApi.sync(hospitalCode);
      setSyncResult(res);
      // 크롤링 후 DB에서 다시 로드
      await loadDoctors(hospitalCode, searchQ);
    } catch (e) {
      setSyncResult({ status: 'error', message: e.message });
    } finally {
      setSyncing(false);
    }
  };

  // ── 교수 미리보기 ──
  const openPreview = (doctor) => {
    setSelectedDoctor(doctor);
    setSchedule(null);
    setScheduleError(null);
    setScheduleLoading(false);
    setRegistered(doctor.visit_grade === 'A' || doctor.visit_grade === 'B' || registeredSet.has(doctor.external_id));
  };
  const closePreview = () => {
    setSelectedDoctor(null);
    setSchedule(null);
    setScheduleError(null);
    setRegistered(false);
  };

  // ── 진료시간 가져오기 ──
  const fetchSchedule = async () => {
    if (!selectedDoctor?.external_id || !selectedHospital?.code) return;
    setScheduleLoading(true);
    setScheduleError(null);
    try {
      const result = await crawlApi.doctor(selectedHospital.code, selectedDoctor.external_id);
      setSchedule(result);
    } catch (e) {
      setScheduleError(e.message);
    } finally {
      setScheduleLoading(false);
    }
  };

  // ── 내 교수로 등록 ──
  const registerDoctor = async () => {
    if (!selectedDoctor || !selectedHospital) return;
    setRegistering(true);
    try {
      await crawlApi.registerDoctor({
        hospital_code: selectedHospital.code,
        name: selectedDoctor.name,
        department: selectedDoctor.department,
        position: selectedDoctor.position || schedule?.position || '',
        specialty: schedule?.specialty || selectedDoctor.specialty || '',
        external_id: selectedDoctor.external_id || '',
        profile_url: selectedDoctor.profile_url || schedule?.profile_url || '',
        photo_url: selectedDoctor.photo_url || schedule?.photo_url || '',
        schedules: schedule?.schedules || [],
      });
      invalidate('doctors');
      invalidate('my-doctors');
      setRegistered(true);
      setRegisteredSet(prev => new Set([...prev, selectedDoctor.external_id]));
      setTimeout(() => onNavigate?.('my-doctors'), 1200);
    } catch (e) {
      alert('등록 실패: ' + e.message);
    } finally {
      setRegistering(false);
    }
  };

  const hospitals = (crawlHospitals?.hospitals || []);
  const filteredHospitals = hospitals.filter(h =>
    !hospitalSearchQ || h.name?.includes(hospitalSearchQ) || h.code?.toLowerCase().includes(hospitalSearchQ.toLowerCase())
  );

  // 마지막 크롤링 날짜 포맷
  const formatCrawledDate = (iso) => {
    if (!iso) return '아직 크롤링 안 됨';
    const d = new Date(iso);
    const now = new Date();
    const diff = Math.floor((now - d) / (1000 * 60 * 60 * 24));
    if (diff === 0) return '오늘';
    if (diff === 1) return '어제';
    if (diff < 30) return `${diff}일 전`;
    return d.toLocaleDateString('ko-KR');
  };

  // ═══ 병원 내 교수 목록 ═══
  if (selectedHospital) {
    return (
      <div style={{ display: 'flex', gap: 16, animation: 'slideR .25s ease' }}>
        {/* 왼쪽: 교수 목록 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* 브레드크럼 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16, fontSize: 13 }}>
            <span onClick={() => { setSelectedHospital(null); closePreview(); }} style={{ color: 'var(--t3)', cursor: 'pointer' }}>전체 병원</span>
            <ChevronRight size={13} style={{ color: 'var(--t3)' }} />
            <span style={{ color: 'var(--t1)' }}>{selectedHospital.name}</span>
          </div>

          {/* 병원 헤더 + 크롤링 정보 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, padding: 14, borderRadius: 10, background: 'var(--bg-1)', border: '1px solid var(--bd-s)' }}>
            <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--ac-d)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>🏥</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{selectedHospital.name}</div>
              <div style={{ fontSize: 11, color: 'var(--t3)' }}>
                {doctors.length}명 · 마지막 크롤링: {formatCrawledDate(lastCrawled)}
              </div>
            </div>
            <button
              onClick={() => syncHospital()}
              disabled={syncing}
              style={{ padding: '5px 12px', borderRadius: 6, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: syncing ? 'var(--t3)' : 'var(--ac)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 4 }}
            >
              <RefreshCw size={12} style={syncing ? { animation: 'spin .8s linear infinite' } : {}} />
              {syncing ? '크롤링 중…' : '새로 크롤링'}
            </button>
            <button onClick={() => { setSelectedHospital(null); closePreview(); }} style={{ padding: '5px 10px', borderRadius: 6, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: 'var(--t2)', fontSize: 10, cursor: 'pointer', fontFamily: 'inherit' }}>
              <ChevronLeft size={12} style={{ display: 'inline', verticalAlign: -2 }} /> 돌아가기
            </button>
          </div>

          {/* 크롤링 결과 알림 */}
          {syncResult && (
            <div style={{
              padding: '8px 12px', borderRadius: 7, marginBottom: 10, fontSize: 11, display: 'flex', alignItems: 'center', gap: 5,
              background: syncResult.status === 'success' ? 'var(--gn-d)' : 'var(--rd-d)',
              border: `1px solid ${syncResult.status === 'success' ? 'rgba(52,211,153,.2)' : 'rgba(248,113,113,.2)'}`,
              color: syncResult.status === 'success' ? 'var(--gn)' : 'var(--rd)',
            }}>
              {syncResult.status === 'success' ? (
                <><CheckCircle size={12} /> {syncResult.total_crawled}명 크롤링 완료 (신규 {syncResult.created}, 업데이트 {syncResult.updated})</>
              ) : (
                <><AlertTriangle size={12} /> {syncResult.message || '크롤링 실패'}</>
              )}
            </div>
          )}

          {/* 검색 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', borderRadius: 7, padding: '6px 10px', marginBottom: 12 }}>
            <Search size={14} style={{ color: 'var(--t3)' }} />
            <input
              placeholder="교수명, 진료과 검색"
              value={searchQ}
              onChange={e => handleSearch(e.target.value)}
              style={{ border: 'none', background: 'none', outline: 'none', color: 'var(--t1)', fontSize: 12.5, width: '100%' }}
            />
          </div>

          {/* 로딩 */}
          {(doctorsLoading || syncing) && !doctors.length ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <RefreshCw size={24} style={{ color: 'var(--ac)', animation: 'spin .8s linear infinite', marginBottom: 12 }} />
              <div style={{ fontSize: 13, color: 'var(--t2)' }}>{syncing ? '크롤링 중…' : '로딩 중…'}</div>
            </div>
          ) : doctors.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--t3)', fontSize: 13 }}>
              {searchQ ? '검색 결과 없음' : '교수 데이터가 없습니다. "새로 크롤링" 버튼을 눌러주세요.'}
            </div>
          ) : doctors.map((d, i) => {
            const isSelected = selectedDoctor?.external_id === d.external_id;
            const isMyDoctor = d.visit_grade === 'A' || d.visit_grade === 'B' || registeredSet.has(d.external_id);
            return (
              <div
                key={d.external_id || d.id || i}
                onClick={() => openPreview(d)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '12px 14px', borderRadius: 9,
                  background: isSelected ? 'var(--bg-2)' : 'var(--bg-1)',
                  border: `1px solid ${isSelected ? 'var(--ac)' : 'var(--bd-s)'}`,
                  marginBottom: 5, cursor: 'pointer', transition: 'all .12s',
                  animation: `fadeUp .25s ease ${i * .02}s both`,
                }}
              >
                <div style={{
                  width: 34, height: 34, borderRadius: 8, flexShrink: 0,
                  background: isMyDoctor ? 'var(--gn-d)' : isSelected ? 'var(--ac-d)' : 'var(--bg-3)',
                  color: isMyDoctor ? 'var(--gn)' : isSelected ? 'var(--ac)' : 'var(--t3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 13, fontWeight: 700, fontFamily: 'Outfit',
                }}>{d.name?.[0]}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>
                    {d.name}
                    {isMyDoctor && <Star size={11} style={{ color: 'var(--gn)', display: 'inline', verticalAlign: -1, marginLeft: 4 }} fill="var(--gn)" />}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {d.department}
                  </div>
                </div>
                {isMyDoctor ? (
                  <span style={{ padding: '3px 8px', borderRadius: 4, background: 'var(--gn-d)', color: 'var(--gn)', fontSize: 10, fontWeight: 600, flexShrink: 0 }}>내 교수</span>
                ) : (
                  <ChevronRight size={14} style={{ color: isSelected ? 'var(--ac)' : 'var(--t3)', flexShrink: 0 }} />
                )}
              </div>
            );
          })}
        </div>

        {/* 오른쪽: 미리보기 패널 */}
        {selectedDoctor && (
          <div style={{
            width: 360, minWidth: 360, position: 'sticky', top: 80, alignSelf: 'flex-start',
            background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 12,
            padding: 20, animation: 'fadeUp .25s ease',
          }}>
            <button onClick={closePreview} style={{
              position: 'absolute', top: 12, right: 12,
              width: 24, height: 24, borderRadius: 6, background: 'var(--bg-2)',
              border: '1px solid var(--bd-s)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', color: 'var(--t3)',
            }}><X size={12} /></button>

            {/* 프로필 */}
            <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
              <div style={{
                width: 48, height: 48, borderRadius: 10, flexShrink: 0,
                background: 'var(--ac-d)', color: 'var(--ac)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 20, fontWeight: 700, fontFamily: 'Outfit',
              }}>{selectedDoctor.name?.[0]}</div>
              <div>
                <div style={{ fontFamily: 'Outfit', fontSize: 17, fontWeight: 700 }}>{selectedDoctor.name}</div>
                <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 2 }}>{selectedDoctor.department}</div>
              </div>
            </div>

            {/* 진료시간 가져오기 버튼 */}
            {!schedule && !scheduleLoading && !scheduleError && (
              <button onClick={fetchSchedule} style={{
                width: '100%', padding: '12px 16px', borderRadius: 8, marginBottom: 12,
                background: 'var(--bg-2)', color: 'var(--ac)', border: '1px solid rgba(124,106,240,.3)',
                fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}>
                <Clock size={14} /> 진료시간 가져오기
              </button>
            )}

            {scheduleLoading && (
              <div style={{ textAlign: 'center', padding: '20px 0', marginBottom: 12 }}>
                <RefreshCw size={20} style={{ color: 'var(--ac)', animation: 'spin .8s linear infinite', marginBottom: 8 }} />
                <div style={{ fontSize: 12, color: 'var(--t2)' }}>진료시간 크롤링 중…</div>
              </div>
            )}

            {scheduleError && (
              <div style={{ padding: '10px 14px', borderRadius: 7, marginBottom: 12, background: 'var(--rd-d)', border: '1px solid rgba(248,113,113,.2)', fontSize: 11, color: 'var(--rd)', display: 'flex', alignItems: 'center', gap: 5 }}>
                <AlertTriangle size={12} /> {scheduleError}
              </div>
            )}

            {schedule && (
              <>
                <div style={{ padding: '8px 12px', borderRadius: 7, marginBottom: 12, background: 'var(--gn-d)', border: '1px solid rgba(52,211,153,.2)', fontSize: 11, color: 'var(--gn)', display: 'flex', alignItems: 'center', gap: 5 }}>
                  <CheckCircle size={12} /> 진료시간 크롤링 완료
                </div>
                {schedule.specialty && (
                  <div style={{ marginBottom: 14 }}>
                    <div style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 500, marginBottom: 4 }}>전문 분야</div>
                    <div style={{ fontSize: 12, color: 'var(--t2)', padding: '8px 10px', background: 'var(--bg-2)', borderRadius: 6 }}>{schedule.specialty}</div>
                  </div>
                )}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 500, marginBottom: 6 }}>진료 시간표</div>
                  {schedule.schedules?.length > 0 ? (
                    <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, border: '1px solid var(--bd-s)', borderRadius: 8, overflow: 'hidden' }}>
                      <thead><tr>
                        <th style={{ padding: '8px 6px', textAlign: 'center', fontSize: 10, background: 'var(--bg-2)', color: 'var(--t3)', fontWeight: 500, borderBottom: '1px solid var(--bd-s)' }}>구분</th>
                        {DAY_NAMES.map(d => <th key={d} style={{ padding: '8px 4px', textAlign: 'center', fontSize: 10, background: 'var(--bg-2)', color: 'var(--t3)', fontWeight: 500, borderBottom: '1px solid var(--bd-s)' }}>{d}</th>)}
                      </tr></thead>
                      <tbody>{['morning', 'afternoon'].map(slot => (
                        <tr key={slot}>
                          <td style={{ padding: '8px 6px', textAlign: 'center', fontSize: 10, color: 'var(--t3)', fontWeight: 500, background: 'var(--bg-1)', borderBottom: '1px solid var(--bd-s)' }}>{SLOT_NAMES[slot]}</td>
                          {[0,1,2,3,4,5].map(di => {
                            const has = schedule.schedules.some(s => (s.day_of_week === di || s.day === di) && (s.time_slot === slot || s.slot === slot));
                            return <td key={di} style={{ padding: '8px 4px', textAlign: 'center', background: 'var(--bg-1)', borderBottom: '1px solid var(--bd-s)' }}>{has ? <span style={{ display: 'inline-block', width: 16, height: 16, borderRadius: 4, background: 'var(--ac-d)', color: 'var(--ac)', lineHeight: '16px', fontWeight: 700, fontSize: 9 }}>●</span> : <span style={{ color: 'var(--t3)', fontSize: 10 }}>-</span>}</td>;
                          })}
                        </tr>
                      ))}</tbody>
                    </table>
                  ) : (
                    <div style={{ padding: '16px 0', textAlign: 'center', color: 'var(--t3)', fontSize: 12 }}>진료일정 정보 없음</div>
                  )}
                </div>
                {schedule.notes && (
                  <div style={{ marginBottom: 16, padding: '10px 12px', borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd-s)' }}>
                    <div style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 500, marginBottom: 4 }}>특이사항</div>
                    <div style={{ fontSize: 12, color: 'var(--t2)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{schedule.notes}</div>
                  </div>
                )}
              </>
            )}

            {/* 내 교수 등록 버튼 */}
            {registered ? (
              <div style={{ padding: '12px 16px', borderRadius: 8, textAlign: 'center', background: 'var(--gn-d)', border: '1px solid rgba(52,211,153,.2)', color: 'var(--gn)', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <CheckCircle size={16} /> 내 교수로 등록되었습니다
              </div>
            ) : (
              <button onClick={registerDoctor} disabled={registering} style={{
                width: '100%', padding: '12px 16px', borderRadius: 8,
                background: 'var(--ac)', color: '#fff', border: 'none',
                fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                opacity: registering ? .6 : 1, transition: 'opacity .12s',
              }}>
                {registering ? <><RefreshCw size={14} style={{ animation: 'spin .8s linear infinite' }} /> 등록 중…</> : <><UserPlus size={14} /> 내 교수로 등록</>}
              </button>
            )}
          </div>
        )}
      </div>
    );
  }

  // ═══ 병원 목록 ═══
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', borderRadius: 7, padding: '6px 10px', flex: 1, maxWidth: 280 }}>
          <Search size={14} style={{ color: 'var(--t3)' }} />
          <input placeholder="병원명 검색" value={hospitalSearchQ} onChange={e => setHospitalSearchQ(e.target.value)} style={{ border: 'none', background: 'none', outline: 'none', color: 'var(--t1)', fontSize: 12.5, width: '100%' }} />
        </div>
        <span style={{ fontSize: 12, color: 'var(--t3)' }}>병원 선택 → 교수 검색 → 진료시간 확인 → 내 교수 등록</span>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)' }}>로딩 중…</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
          {filteredHospitals.map((h, i) => (
            <div key={h.code} onClick={() => openHospital(h)} style={{
              background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 12,
              padding: 20, cursor: 'pointer', transition: 'all .15s',
              display: 'flex', flexDirection: 'column', gap: 10,
              animation: `fadeUp .3s ease ${i * .04}s both`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: 'var(--ac-d)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>🏥</div>
                <ChevronRight size={16} style={{ color: 'var(--t3)' }} />
              </div>
              <div>
                <div style={{ fontFamily: 'Outfit', fontSize: 15, fontWeight: 600 }}>{h.name}</div>
              </div>
              <div style={{ paddingTop: 10, borderTop: '1px solid var(--bd-s)', fontSize: 11, color: 'var(--t2)', fontFamily: "'JetBrains Mono'" }}>{h.code}</div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
