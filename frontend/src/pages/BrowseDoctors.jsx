import { useState, useEffect, useCallback } from 'react';
import { Search, ChevronRight, ChevronLeft, Star, RefreshCw, Clock, UserPlus, X, AlertTriangle, CheckCircle, Calendar } from 'lucide-react';
import { crawlApi } from '../api/client';
import { useCachedApi } from '../hooks/useCachedApi';
import { invalidate } from '../api/cache';
import HospitalLogo from '../components/HospitalLogo';
import ScheduleCalendar from '../components/ScheduleCalendar';

const DAY_NAMES = ['월', '화', '수', '목', '금', '토'];
const SLOT_NAMES = { morning: '오전', afternoon: '오후', evening: '야간' };

/* MiniCalendar 는 ScheduleCalendar (frontend/src/components/ScheduleCalendar.jsx) 로 통합되어 제거됨. */

export default function BrowseDoctors({ onNavigate }) {
  const { data: crawlHospitals, loading } = useCachedApi('crawl-hospitals', crawlApi.hospitals, { ttlKey: 'hospitals' });

  // 병원 선택
  const [selectedHospital, setSelectedHospital] = useState(null);
  const [hospitalSearchQ, setHospitalSearchQ] = useState('');

  // 전체 교수 검색 (병원 목록 화면용)
  const [globalDoctorResults, setGlobalDoctorResults] = useState([]);
  const [globalDoctorLoading, setGlobalDoctorLoading] = useState(false);

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
  const loadDoctors = useCallback(async (code, search = '', autoSync = true) => {
    setDoctorsLoading(true);
    try {
      const res = await crawlApi.browse(code, search);
      setDoctors(res.doctors || []);
      setLastCrawled(res.last_crawled);
      // DB에 데이터가 없으면 자동으로 크롤링 시작 (재귀 방지: autoSync=false일 때 건너뜀)
      if (!res.doctors?.length && !search && autoSync) {
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

  // ── 전체 검색된 교수 클릭 → 해당 병원 선택 + 미리보기 자동 오픈 ──
  const openDoctorFromGlobal = (doctor) => {
    const hospital = (crawlHospitals?.hospitals || []).find(h => h.code === doctor.hospital_code)
      || { code: doctor.hospital_code, name: doctor.hospital_name };
    setSelectedHospital(hospital);
    setSearchQ('');
    setSyncResult(null);
    setSelectedDoctor(doctor);
    setSchedule(null);
    setScheduleError(null);
    setScheduleLoading(false);
    setRegistered(doctor.visit_grade === 'A' || doctor.visit_grade === 'B' || registeredSet.has(doctor.external_id));
    loadDoctors(hospital.code);
  };

  // ── 전체 교수 검색 (디바운스) ──
  useEffect(() => {
    const q = hospitalSearchQ.trim();
    if (!q) {
      setGlobalDoctorResults([]);
      setGlobalDoctorLoading(false);
      return;
    }
    setGlobalDoctorLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await crawlApi.searchDoctors(q);
        setGlobalDoctorResults(res.doctors || []);
      } catch (e) {
        console.error(e);
        setGlobalDoctorResults([]);
      } finally {
        setGlobalDoctorLoading(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [hospitalSearchQ]);

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
      // 크롤링 후 DB에서 다시 로드 (autoSync=false로 재귀 방지)
      await loadDoctors(hospitalCode, searchQ, false);
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

  // ── 내 교수로 등록 (스케줄 미조회 시 백엔드에서 자동 크롤링) ──
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
        date_schedules: schedule?.date_schedules || [],
      });
      invalidate('doctors');
      invalidate('my-doctors');
      invalidate('academic');
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

  // 지역별 그룹핑 — 광역시도 전체 (factory.py _HOSPITAL_REGION 의 모든 값 포함)
  const REGION_ORDER = [
    '서울', '경기', '인천',
    '강원', '충북', '충남', '대전', '세종',
    '전북', '전남', '광주',
    '경북', '경남', '대구', '울산', '부산',
    '제주',
  ];
  const groupedHospitals = {};
  REGION_ORDER.forEach(r => { groupedHospitals[r] = []; });
  filteredHospitals.forEach(h => {
    const region = h.region || '기타';
    if (!groupedHospitals[region]) groupedHospitals[region] = [];
    groupedHospitals[region].push(h);
  });
  Object.keys(groupedHospitals).forEach(r => {
    groupedHospitals[r].sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ko'));
  });
  const regionEntries = REGION_ORDER.map(r => [r, groupedHospitals[r] || []]).filter(([, list]) => list.length > 0);
  if (groupedHospitals['기타']?.length) regionEntries.push(['기타', groupedHospitals['기타']]);

  // 마지막 크롤링 날짜 포맷
  const formatCrawledDate = (iso) => {
    if (!iso) return '아직 크롤링 안 됨';
    const d = new Date(iso);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${yyyy}.${mm}.${dd} ${hh}:${min}`;
  };

  // ═══ 병원 내 교수 목록 ═══
  if (selectedHospital) {
    return (
      <div style={{ display: 'flex', gap: 16, animation: 'slideR .25s ease' }}>
        {/* 왼쪽: 교수 목록 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* 고정 헤더 영역 */}
          <div style={{ position: 'sticky', top: 49, zIndex: 5, background: 'var(--bg-0)', marginLeft: -24, marginRight: -24, paddingLeft: 24, paddingRight: 24, paddingTop: 4, paddingBottom: 4 }}>
            {/* 브레드크럼 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12, fontSize: 13 }}>
              <span onClick={() => { setSelectedHospital(null); closePreview(); }} style={{ color: 'var(--t3)', cursor: 'pointer' }}>전체 병원</span>
              <ChevronRight size={13} style={{ color: 'var(--t3)' }} />
              <span style={{ color: 'var(--t1)' }}>{selectedHospital.name}</span>
            </div>

            {/* 병원 헤더 + 크롤링 정보 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, padding: 14, borderRadius: 10, background: 'var(--bg-1)', border: '1px solid var(--bd-s)', flexWrap: 'wrap' }}>
              <HospitalLogo code={selectedHospital.code} size={36} radius={8} />
              <div style={{ flex: 1, minWidth: 120 }}>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{selectedHospital.name}</div>
                <div style={{ fontSize: 11, color: 'var(--t3)' }}>
                  {doctors.length}명 · 마지막 크롤링: {formatCrawledDate(lastCrawled)}
                </div>
              </div>
              <button
                onClick={() => syncHospital()}
                disabled={syncing}
                style={{ padding: '5px 12px', borderRadius: 6, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: syncing ? 'var(--t3)' : 'var(--ac)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap', flexShrink: 0 }}
              >
                <RefreshCw size={12} style={syncing ? { animation: 'spin .8s linear infinite' } : {}} />
                {syncing ? '크롤링 중…' : '새로 크롤링'}
              </button>
              <button onClick={() => { setSelectedHospital(null); closePreview(); }} style={{ padding: '5px 10px', borderRadius: 6, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: 'var(--t2)', fontSize: 10, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap', flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                <ChevronLeft size={12} /> 돌아가기
              </button>
            </div>

            {/* 크롤링 결과 알림 */}
            {syncResult && (
              <div style={{
                padding: '8px 12px', borderRadius: 7, marginBottom: 8, fontSize: 11, display: 'flex', alignItems: 'center', gap: 5,
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', borderRadius: 7, padding: '6px 10px', marginBottom: 8 }}>
              <Search size={14} style={{ color: 'var(--t3)' }} />
              <input
                placeholder="교수명, 진료과 검색"
                value={searchQ}
                onChange={e => handleSearch(e.target.value)}
                style={{ border: 'none', background: 'none', outline: 'none', color: 'var(--t1)', fontSize: 12.5, width: '100%' }}
              />
            </div>
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
          ) : (() => {
            // 진료과별 그룹핑
            const deptGroups = {};
            doctors.forEach(d => {
              const dept = d.department || '기타';
              if (!deptGroups[dept]) deptGroups[dept] = [];
              deptGroups[dept].push(d);
            });
            const deptEntries = Object.entries(deptGroups).sort(([a], [b]) => a.localeCompare(b));
            return (
              <div>
                {deptEntries.map(([dept, group]) => (
                  <div key={dept} style={{ marginBottom: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, padding: '0 2px' }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--t2)' }}>{dept}</span>
                      <span style={{ fontSize: 11, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>{group.length}</span>
                      <div style={{ flex: 1, height: 1, background: 'var(--bd-s)' }} />
                    </div>
                    {group.map((d, i) => {
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
                            <span style={{ padding: '3px 8px', borderRadius: 4, background: 'var(--gn-d)', color: 'var(--gn)', fontSize: 10, fontWeight: 600, flexShrink: 0 }}>내 의료진</span>
                          ) : (
                            <ChevronRight size={14} style={{ color: isSelected ? 'var(--ac)' : 'var(--t3)', flexShrink: 0 }} />
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            );
          })()}
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
                  {(schedule.date_schedules?.length > 0 || schedule.schedules?.length > 0) ? (
                    <ScheduleCalendar
                      compact
                      schedules={(schedule.schedules || []).map(s => ({
                        day_of_week: s.day_of_week ?? s.day,
                        time_slot: s.time_slot ?? s.slot,
                      }))}
                      dateSchedules={schedule.date_schedules || []}
                    />
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

            {/* 내 의료진 등록 버튼 */}
            {registered ? (
              <div style={{ padding: '12px 16px', borderRadius: 8, textAlign: 'center', background: 'var(--gn-d)', border: '1px solid rgba(52,211,153,.2)', color: 'var(--gn)', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <CheckCircle size={16} /> 내 의료진으로 등록되었습니다
              </div>
            ) : (
              <button onClick={registerDoctor} disabled={registering} style={{
                width: '100%', padding: '12px 16px', borderRadius: 8,
                background: 'var(--ac)', color: '#fff', border: 'none',
                fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                opacity: registering ? .6 : 1, transition: 'opacity .12s',
              }}>
                {registering ? <><RefreshCw size={14} style={{ animation: 'spin .8s linear infinite' }} /> 등록 중…</> : <><UserPlus size={14} /> 내 의료진으로 등록</>}
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', borderRadius: 7, padding: '6px 10px', flex: 1, maxWidth: 320 }}>
          <Search size={14} style={{ color: 'var(--t3)' }} />
          <input placeholder="병원명 또는 교수 이름 검색" value={hospitalSearchQ} onChange={e => setHospitalSearchQ(e.target.value)} style={{ border: 'none', background: 'none', outline: 'none', color: 'var(--t1)', fontSize: 12.5, width: '100%' }} />
        </div>
        <span style={{ fontSize: 12, color: 'var(--t3)' }}>병원 선택 → 의료진 검색 → 진료시간 확인 → 내 의료진으로 등록</span>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--t3)' }}>로딩 중…</div>
      ) : hospitalSearchQ ? (
        /* 검색 시 플랫 표시: 병원 + 교수 통합 결과 */
        <>
          {/* 병원 검색 결과 */}
          {filteredHospitals.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--t2)' }}>병원</span>
                <span style={{ fontSize: 11, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>{filteredHospitals.length}</span>
                <div style={{ flex: 1, height: 1, background: 'var(--bd-s)' }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
                {filteredHospitals.map((h, i) => (
            <div key={h.code} onClick={() => openHospital(h)} style={{
              background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 12,
              padding: 20, cursor: 'pointer', transition: 'all .15s',
              display: 'flex', flexDirection: 'column', gap: 10,
              animation: `fadeUp .3s ease ${i * .04}s both`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <HospitalLogo code={h.code} size={44} radius={10} />
                <ChevronRight size={16} style={{ color: 'var(--t3)' }} />
              </div>
              <div>
                <div style={{ fontFamily: 'Outfit', fontSize: 15, fontWeight: 600 }}>{h.name}</div>
              </div>
              <div style={{ paddingTop: 10, borderTop: '1px solid var(--bd-s)', fontSize: 11, color: 'var(--t2)', fontFamily: "'JetBrains Mono'" }}>{h.code}</div>
            </div>
          ))}
              </div>
            </div>
          )}

          {/* 교수 검색 결과 */}
          {(globalDoctorLoading || globalDoctorResults.length > 0) && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--t2)' }}>교수</span>
                <span style={{ fontSize: 11, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>
                  {globalDoctorLoading ? '…' : globalDoctorResults.length}
                </span>
                <div style={{ flex: 1, height: 1, background: 'var(--bd-s)' }} />
              </div>
              {globalDoctorLoading && globalDoctorResults.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 20, color: 'var(--t3)', fontSize: 12 }}>검색 중…</div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8 }}>
                  {globalDoctorResults.map((d, i) => {
                    const isMyDoctor = d.visit_grade === 'A' || d.visit_grade === 'B' || registeredSet.has(d.external_id);
                    return (
                      <div
                        key={`${d.hospital_code}-${d.external_id || d.id || i}`}
                        onClick={() => openDoctorFromGlobal(d)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 10,
                          padding: '10px 12px', borderRadius: 9,
                          background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
                          cursor: 'pointer', transition: 'all .12s',
                          animation: `fadeUp .25s ease ${i * .02}s both`,
                        }}
                      >
                        <HospitalLogo code={d.hospital_code} size={32} radius={7} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 4 }}>
                            {d.name}
                            {isMyDoctor && <Star size={11} style={{ color: 'var(--gn)' }} fill="var(--gn)" />}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {d.hospital_name} · {d.department}
                          </div>
                        </div>
                        <ChevronRight size={14} style={{ color: 'var(--t3)', flexShrink: 0 }} />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* 둘 다 결과 없음 */}
          {!globalDoctorLoading && filteredHospitals.length === 0 && globalDoctorResults.length === 0 && (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--t3)', fontSize: 13 }}>검색 결과 없음</div>
          )}
        </>
      ) : (
        /* 지역별 그룹 표시 */
        <div>
          {regionEntries.map(([region, list]) => (
            <div key={region} style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)' }}>{region}</span>
                <span style={{ fontSize: 11, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>{list.length}</span>
                <div style={{ flex: 1, height: 1, background: 'var(--bd-s)' }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
                {list.map((h, i) => (
                  <div key={h.code} onClick={() => openHospital(h)} style={{
                    background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 12,
                    padding: 20, cursor: 'pointer', transition: 'all .15s',
                    display: 'flex', flexDirection: 'column', gap: 10,
                    animation: `fadeUp .3s ease ${i * .04}s both`,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <HospitalLogo code={h.code} size={44} radius={10} />
                      <ChevronRight size={16} style={{ color: 'var(--t3)' }} />
                    </div>
                    <div>
                      <div style={{ fontFamily: 'Outfit', fontSize: 15, fontWeight: 600 }}>{h.name}</div>
                    </div>
                    <div style={{ paddingTop: 10, borderTop: '1px solid var(--bd-s)', fontSize: 11, color: 'var(--t2)', fontFamily: "'JetBrains Mono'" }}>{h.code}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
