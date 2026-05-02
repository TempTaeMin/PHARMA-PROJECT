import { useEffect, useMemo, useState } from 'react';
import { X, ChevronLeft, ChevronRight, Building2, User, Calendar, Plus } from 'lucide-react';
import { doctorApi, hospitalApi } from '../api/client';
import { invalidate } from '../api/cache';

const DAY_NAMES = ['월', '화', '수', '목', '금', '토'];
const SLOT_DEFAULT = { morning: ['09:00', '12:00'], afternoon: ['13:00', '17:00'] };

/**
 * 수동 등록 모달 — 3단계.
 *  1) 병원 선택 (기존 또는 신규 등록)
 *  2) 의사 정보 입력
 *  3) 주간 진료시간 체크박스
 * 저장 시 hospital → doctor → schedules 순차 호출.
 */
export default function ManualDoctorModal({ open, onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [hospitals, setHospitals] = useState([]);
  const [hospMode, setHospMode] = useState('existing'); // 'existing' | 'new'
  const [hospitalId, setHospitalId] = useState(null);
  const [hospSearch, setHospSearch] = useState('');
  const [newHosp, setNewHosp] = useState({ name: '', address: '', region: '', phone: '' });
  const [doctorForm, setDoctorForm] = useState({
    name: '', department: '', position: '', specialty: '', memo: '',
  });
  // 12개 슬롯 체크 — { 'morning-0': {checked, location}, ... }
  const [slots, setSlots] = useState({});
  const [slotTimes, setSlotTimes] = useState({
    morning: { start: SLOT_DEFAULT.morning[0], end: SLOT_DEFAULT.morning[1] },
    afternoon: { start: SLOT_DEFAULT.afternoon[0], end: SLOT_DEFAULT.afternoon[1] },
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    setStep(1); setHospMode('existing'); setHospitalId(null); setHospSearch('');
    setNewHosp({ name: '', address: '', region: '', phone: '' });
    setDoctorForm({ name: '', department: '', position: '', specialty: '', memo: '' });
    setSlots({}); setError(null); setSaving(false);
    setSlotTimes({
      morning: { start: SLOT_DEFAULT.morning[0], end: SLOT_DEFAULT.morning[1] },
      afternoon: { start: SLOT_DEFAULT.afternoon[0], end: SLOT_DEFAULT.afternoon[1] },
    });
    hospitalApi.list().then(setHospitals).catch(() => setHospitals([]));
  }, [open]);

  const filteredHosps = useMemo(() => {
    const q = hospSearch.trim().toLowerCase();
    if (!q) return hospitals;
    return hospitals.filter(h =>
      h.name?.toLowerCase().includes(q) || h.code?.toLowerCase().includes(q)
    );
  }, [hospitals, hospSearch]);

  const toggleSlot = (slot, dow) => {
    const key = `${slot}-${dow}`;
    setSlots(prev => {
      const next = { ...prev };
      if (next[key]) delete next[key];
      else next[key] = { location: '' };
      return next;
    });
  };

  const setSlotLocation = (slot, dow, location) => {
    const key = `${slot}-${dow}`;
    setSlots(prev => prev[key] ? { ...prev, [key]: { ...prev[key], location } } : prev);
  };

  const canNext1 = hospMode === 'existing'
    ? Boolean(hospitalId)
    : Boolean(newHosp.name.trim());
  const canNext2 = doctorForm.name.trim().length > 0;
  const canSave = Object.keys(slots).length > 0 || step === 3; // 진료시간 0개라도 저장 허용

  const save = async () => {
    setSaving(true); setError(null);
    try {
      // 1. 병원 등록 (필요 시)
      let hid = hospitalId;
      if (hospMode === 'new') {
        const created = await hospitalApi.create({
          name: newHosp.name.trim(),
          code: '',  // 서버가 MANUAL_xxx 자동 발급
          address: newHosp.address.trim() || null,
          region: newHosp.region.trim() || null,
          phone: newHosp.phone.trim() || null,
          source: 'manual',
        });
        hid = created.id;
      }
      // 2. 의사 등록
      const doc = await doctorApi.create({
        hospital_id: hid,
        name: doctorForm.name.trim(),
        department: doctorForm.department.trim() || null,
        position: doctorForm.position.trim() || null,
        specialty: doctorForm.specialty.trim() || null,
        memo: doctorForm.memo.trim() || null,
        visit_grade: 'B',
        source: 'manual',
      });
      // 3. 진료시간 저장
      const items = Object.entries(slots).map(([key, val]) => {
        const [slot, dowStr] = key.split('-');
        return {
          day_of_week: parseInt(dowStr, 10),
          time_slot: slot,
          start_time: slotTimes[slot]?.start || null,
          end_time: slotTimes[slot]?.end || null,
          location: val.location || null,
        };
      });
      if (items.length > 0) {
        await doctorApi.replaceManualSchedules(doc.id, items);
      }
      invalidate('my-doctors'); invalidate('doctors'); invalidate('hospitals'); invalidate('academic');
      onCreated?.(doc);
      onClose?.();
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <>
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', zIndex: 60, animation: 'fadeIn .15s' }} />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        width: 'min(560px, 92vw)', maxHeight: '92vh', overflowY: 'auto',
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
        borderRadius: 14, zIndex: 61, boxShadow: '0 14px 60px rgba(0,0,0,.5)',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid var(--bd-s)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Plus size={16} style={{ color: 'var(--ac)' }} />
            <h3 style={{ fontFamily: 'Outfit', fontSize: 15, fontWeight: 700 }}>수동 등록</h3>
            <span style={{ fontSize: 11, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>{step}/3</span>
          </div>
          <button onClick={onClose} style={{ width: 28, height: 28, borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--t3)' }}>
            <X size={13} />
          </button>
        </div>

        {/* Step indicator */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--bd-s)' }}>
          {[
            { n: 1, label: '병원', icon: Building2 },
            { n: 2, label: '의사', icon: User },
            { n: 3, label: '진료시간', icon: Calendar },
          ].map((s, i) => {
            const Icon = s.icon;
            const active = step === s.n;
            const done = step > s.n;
            return (
              <div key={s.n} style={{
                flex: 1, padding: '10px 0', textAlign: 'center', fontSize: 11,
                color: active ? 'var(--t1)' : done ? 'var(--ac)' : 'var(--t3)',
                background: active ? 'var(--bg-1)' : 'var(--bg-2)',
                borderBottom: active ? '2px solid var(--ac)' : '2px solid transparent',
                borderRight: i < 2 ? '1px solid var(--bd-s)' : 'none',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                fontWeight: active ? 600 : 400,
              }}>
                <Icon size={12} /> {s.label}
              </div>
            );
          })}
        </div>

        {/* Body */}
        <div style={{ padding: 18 }}>
          {step === 1 && (
            <>
              <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
                {[
                  { k: 'existing', label: '기존 병원' },
                  { k: 'new', label: '새 병원 등록' },
                ].map(o => (
                  <button key={o.k} onClick={() => setHospMode(o.k)} style={{
                    flex: 1, padding: '8px 10px', borderRadius: 7,
                    background: hospMode === o.k ? 'var(--ac-d)' : 'var(--bg-2)',
                    color: hospMode === o.k ? 'var(--ac)' : 'var(--t3)',
                    border: hospMode === o.k ? '1px solid var(--ac)' : '1px solid var(--bd-s)',
                    fontSize: 12, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
                  }}>{o.label}</button>
                ))}
              </div>

              {hospMode === 'existing' ? (
                <>
                  <input
                    placeholder="병원명/코드 검색"
                    value={hospSearch}
                    onChange={e => setHospSearch(e.target.value)}
                    style={{ width: '100%', padding: '9px 12px', borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: 'var(--t1)', fontSize: 13, outline: 'none', marginBottom: 10 }}
                  />
                  <div style={{ maxHeight: 280, overflowY: 'auto', border: '1px solid var(--bd-s)', borderRadius: 8 }}>
                    {filteredHosps.map(h => (
                      <div key={h.id} onClick={() => setHospitalId(h.id)} style={{
                        padding: '8px 12px', cursor: 'pointer', fontSize: 12,
                        background: hospitalId === h.id ? 'var(--ac-d)' : 'transparent',
                        color: hospitalId === h.id ? 'var(--ac)' : 'var(--t1)',
                        borderBottom: '1px solid var(--bd-s)',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      }}>
                        <span>{h.name}</span>
                        <span style={{ fontSize: 10, color: 'var(--t3)', fontFamily: "'JetBrains Mono'" }}>
                          {h.region || ''} · {h.code}
                        </span>
                      </div>
                    ))}
                    {filteredHosps.length === 0 && (
                      <div style={{ padding: 20, textAlign: 'center', color: 'var(--t3)', fontSize: 12 }}>
                        검색 결과 없음
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <Field label="병원명 *" v={newHosp.name} onChange={v => setNewHosp(p => ({ ...p, name: v }))} placeholder="OO의원" />
                  <Field label="지역" v={newHosp.region} onChange={v => setNewHosp(p => ({ ...p, region: v }))} placeholder="서울 / 경기 / 부산..." />
                  <Field label="주소" v={newHosp.address} onChange={v => setNewHosp(p => ({ ...p, address: v }))} placeholder="OO시 OO구..." />
                  <Field label="전화번호" v={newHosp.phone} onChange={v => setNewHosp(p => ({ ...p, phone: v }))} placeholder="02-..." />
                </div>
              )}
            </>
          )}

          {step === 2 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <Field label="이름 *" v={doctorForm.name} onChange={v => setDoctorForm(p => ({ ...p, name: v }))} placeholder="홍길동" />
              <Field label="진료과" v={doctorForm.department} onChange={v => setDoctorForm(p => ({ ...p, department: v }))} placeholder="내과 / 정형외과..." />
              <Field label="직위" v={doctorForm.position} onChange={v => setDoctorForm(p => ({ ...p, position: v }))} placeholder="원장 / 부원장..." />
              <Field label="전문분야" v={doctorForm.specialty} onChange={v => setDoctorForm(p => ({ ...p, specialty: v }))} placeholder="당뇨, 갑상선..." />
              <Field label="메모" v={doctorForm.memo} onChange={v => setDoctorForm(p => ({ ...p, memo: v }))} placeholder="MR 개인 메모" multiline />
            </div>
          )}

          {step === 3 && (
            <>
              <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--t3)' }}>
                요일 × 오전/오후 셀을 클릭해 진료시간을 표시하세요. 비워둬도 등록 가능합니다.
              </div>
              {/* 시간 입력 */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
                {['morning', 'afternoon'].map(slot => (
                  <div key={slot} style={{ flex: 1, padding: 10, borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd-s)' }}>
                    <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 4 }}>
                      {slot === 'morning' ? '오전' : '오후'} 시간
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <input
                        type="time"
                        value={slotTimes[slot].start}
                        onChange={e => setSlotTimes(p => ({ ...p, [slot]: { ...p[slot], start: e.target.value } }))}
                        style={{ flex: 1, padding: 5, borderRadius: 5, background: 'var(--bg-1)', border: '1px solid var(--bd)', color: 'var(--t1)', fontSize: 12, fontFamily: "'JetBrains Mono'" }}
                      />
                      <span style={{ fontSize: 11, color: 'var(--t3)' }}>~</span>
                      <input
                        type="time"
                        value={slotTimes[slot].end}
                        onChange={e => setSlotTimes(p => ({ ...p, [slot]: { ...p[slot], end: e.target.value } }))}
                        style={{ flex: 1, padding: 5, borderRadius: 5, background: 'var(--bg-1)', border: '1px solid var(--bd)', color: 'var(--t1)', fontSize: 12, fontFamily: "'JetBrains Mono'" }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, border: '1px solid var(--bd-s)', borderRadius: 8, overflow: 'hidden' }}>
                <thead>
                  <tr>
                    <th style={{ padding: '8px 6px', background: 'var(--bg-2)', fontSize: 11, color: 'var(--t3)', fontWeight: 500 }}>구분</th>
                    {DAY_NAMES.map(d => (
                      <th key={d} style={{ padding: '8px 6px', background: 'var(--bg-2)', fontSize: 11, color: 'var(--t3)', fontWeight: 500 }}>{d}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {['morning', 'afternoon'].map(slot => (
                    <tr key={slot}>
                      <td style={{ padding: '8px 6px', textAlign: 'center', fontSize: 11, color: 'var(--t3)', fontWeight: 500, background: 'var(--bg-1)', borderTop: '1px solid var(--bd-s)' }}>
                        {slot === 'morning' ? '오전' : '오후'}
                      </td>
                      {[0, 1, 2, 3, 4, 5].map(dow => {
                        const key = `${slot}-${dow}`;
                        const checked = !!slots[key];
                        return (
                          <td key={dow} onClick={() => toggleSlot(slot, dow)} style={{
                            padding: 8, textAlign: 'center', cursor: 'pointer',
                            background: checked ? 'var(--ac-d)' : 'var(--bg-1)',
                            color: checked ? 'var(--ac)' : 'var(--t3)',
                            borderTop: '1px solid var(--bd-s)',
                            fontWeight: checked ? 700 : 400,
                          }}>
                            {checked ? '●' : '–'}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              {Object.keys(slots).length > 0 && (
                <div style={{ marginTop: 14, padding: 10, background: 'var(--bg-2)', borderRadius: 7, border: '1px solid var(--bd-s)' }}>
                  <div style={{ fontSize: 11, color: 'var(--t3)', marginBottom: 6 }}>장소 (선택, 셀별 입력)</div>
                  {Object.entries(slots).map(([key, val]) => {
                    const [slot, dowStr] = key.split('-');
                    const label = `${DAY_NAMES[parseInt(dowStr, 10)]} ${slot === 'morning' ? '오전' : '오후'}`;
                    return (
                      <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <span style={{ fontSize: 11, color: 'var(--t2)', minWidth: 56 }}>{label}</span>
                        <input
                          value={val.location || ''}
                          onChange={e => setSlotLocation(slot, parseInt(dowStr, 10), e.target.value)}
                          placeholder="진료실/호실 등"
                          style={{ flex: 1, padding: '5px 9px', fontSize: 11, borderRadius: 5, background: 'var(--bg-1)', border: '1px solid var(--bd)', color: 'var(--t1)', outline: 'none' }}
                        />
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {error && (
            <div style={{ marginTop: 14, padding: '8px 10px', borderRadius: 6, background: 'var(--rd-d)', color: 'var(--rd)', fontSize: 12 }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 18px', borderTop: '1px solid var(--bd-s)' }}>
          <button onClick={() => step > 1 ? setStep(s => s - 1) : onClose()} style={{
            padding: '8px 14px', borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)',
            color: 'var(--t2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', gap: 4,
          }}>
            <ChevronLeft size={13} /> {step > 1 ? '이전' : '취소'}
          </button>
          {step < 3 ? (
            <button onClick={() => setStep(s => s + 1)} disabled={(step === 1 && !canNext1) || (step === 2 && !canNext2)} style={{
              padding: '8px 14px', borderRadius: 7, background: 'var(--ac)', border: 'none',
              color: '#fff', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
              cursor: ((step === 1 && !canNext1) || (step === 2 && !canNext2)) ? 'not-allowed' : 'pointer',
              opacity: ((step === 1 && !canNext1) || (step === 2 && !canNext2)) ? .5 : 1,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              다음 <ChevronRight size={13} />
            </button>
          ) : (
            <button onClick={save} disabled={saving} style={{
              padding: '8px 14px', borderRadius: 7, background: 'var(--ac)', border: 'none',
              color: '#fff', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
              cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? .6 : 1,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              {saving ? '저장 중…' : '저장'}
            </button>
          )}
        </div>
      </div>
    </>
  );
}

function Field({ label, v, onChange, placeholder = '', multiline = false }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 11, color: 'var(--t3)', fontWeight: 500, marginBottom: 4 }}>{label}</label>
      {multiline ? (
        <textarea value={v} onChange={e => onChange(e.target.value)} rows={3} placeholder={placeholder}
          style={{ width: '100%', padding: '8px 11px', borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: 'var(--t1)', fontSize: 13, outline: 'none', resize: 'vertical', fontFamily: 'inherit' }} />
      ) : (
        <input value={v} onChange={e => onChange(e.target.value)} placeholder={placeholder}
          style={{ width: '100%', padding: '8px 11px', borderRadius: 7, background: 'var(--bg-2)', border: '1px solid var(--bd)', color: 'var(--t1)', fontSize: 13, outline: 'none' }} />
      )}
    </div>
  );
}
