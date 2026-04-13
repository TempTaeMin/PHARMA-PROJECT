import { useState, useMemo } from 'react';
import { X, Search, Plus } from 'lucide-react';

const GC = {
  A: { c: '#ba1a1a', bg: '#ffdad6' },
  B: { c: '#b45309', bg: '#fef3c7' },
  C: { c: '#0056d2', bg: '#dae2ff' },
};

const SLOTS = [
  { key: 'morning', label: '오전', time: '09:00' },
  { key: 'afternoon', label: '오후', time: '13:00' },
  { key: 'evening', label: '야간', time: '18:00' },
];

/**
 * "N월 N일에 방문 예정 추가" 모달.
 * 교수 검색 + 시간대 선택 → 저장.
 */
export default function AddVisitModal({ open, dateStr, doctors = [], onClose, onSubmit }) {
  const [search, setSearch] = useState('');
  const [selectedDoctorId, setSelectedDoctorId] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState('morning');
  const [saving, setSaving] = useState(false);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return doctors;
    return doctors.filter(d =>
      (d.name || '').toLowerCase().includes(q) ||
      (d.hospital_name || '').toLowerCase().includes(q) ||
      (d.department || '').toLowerCase().includes(q)
    );
  }, [search, doctors]);

  if (!open) return null;

  const dateObj = dateStr ? new Date(dateStr + 'T00:00:00') : null;
  const dateLabel = dateObj ? `${dateObj.getMonth() + 1}월 ${dateObj.getDate()}일` : '';

  const handleSubmit = async () => {
    if (!selectedDoctorId) return;
    setSaving(true);
    try {
      await onSubmit(selectedDoctorId, selectedSlot);
      setSearch('');
      setSelectedDoctorId(null);
      setSelectedSlot('morning');
      onClose();
    } catch (e) {
      alert('추가 실패: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)',
        zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center',
        animation: 'fadeIn .15s ease',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-1)', borderRadius: 16, padding: 22,
          width: 460, maxWidth: '92%', maxHeight: '85vh',
          display: 'flex', flexDirection: 'column',
          animation: 'fadeUp .2s ease',
        }}
      >
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <div>
            <div style={{ fontFamily: 'Manrope', fontSize: 17, fontWeight: 700 }}>방문 예정 추가</div>
            <div style={{ fontSize: 12, color: 'var(--t3)', marginTop: 2 }}>{dateLabel}</div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--t3)',
            width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}><X size={18} /></button>
        </div>

        {/* 시간대 선택 */}
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 600, marginBottom: 6 }}>시간대</div>
          <div style={{ display: 'flex', gap: 6 }}>
            {SLOTS.map(s => (
              <button
                key={s.key}
                onClick={() => setSelectedSlot(s.key)}
                style={{
                  flex: 1, padding: '10px 8px', borderRadius: 9, cursor: 'pointer',
                  fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  background: selectedSlot === s.key ? 'var(--ac-d)' : 'var(--bg-2)',
                  color: selectedSlot === s.key ? 'var(--ac)' : 'var(--t3)',
                  border: `1px solid ${selectedSlot === s.key ? 'var(--ac)' : 'var(--bd-s)'}`,
                }}
              >
                <div>{s.label}</div>
                <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono'", opacity: .75, marginTop: 2 }}>{s.time}</div>
              </button>
            ))}
          </div>
        </div>

        {/* 교수 검색 */}
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 600, marginBottom: 6 }}>교수 선택</div>
          <div style={{
            position: 'relative',
            display: 'flex', alignItems: 'center',
            background: 'var(--bg-2)', borderRadius: 9,
            border: '1px solid var(--bd-s)',
            padding: '0 10px',
          }}>
            <Search size={14} style={{ color: 'var(--t3)' }} />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="이름, 병원, 진료과 검색"
              style={{
                flex: 1, padding: '10px 8px', border: 'none', background: 'transparent',
                outline: 'none', fontSize: 13, fontFamily: 'inherit', color: 'var(--t1)',
              }}
            />
          </div>
        </div>

        {/* 교수 리스트 */}
        <div style={{
          marginTop: 10, flex: 1, overflowY: 'auto', minHeight: 200, maxHeight: 340,
          border: '1px solid var(--bd-s)', borderRadius: 10,
        }}>
          {filtered.length === 0 ? (
            <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--t3)', fontSize: 12 }}>
              {doctors.length === 0 ? '등록된 교수가 없습니다' : '검색 결과가 없습니다'}
            </div>
          ) : (
            <div>
              {filtered.map(d => {
                const isSelected = selectedDoctorId === d.id;
                const gc = GC[d.visit_grade] || GC.B;
                return (
                  <button
                    key={d.id}
                    onClick={() => setSelectedDoctorId(d.id)}
                    style={{
                      width: '100%', padding: '10px 12px', border: 'none',
                      background: isSelected ? 'var(--ac-d)' : 'transparent',
                      cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
                      borderBottom: '1px solid var(--bd-s)',
                      display: 'flex', alignItems: 'center', gap: 10,
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--t1)' }}>{d.name}</span>
                        {d.visit_grade && (
                          <span style={{
                            padding: '1px 5px', borderRadius: 4,
                            fontSize: 9, fontWeight: 700, fontFamily: "'JetBrains Mono'",
                            background: gc.bg, color: gc.c,
                          }}>{d.visit_grade}</span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--t3)' }}>
                        {d.hospital_name} · {d.department}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* 액션 */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
          <button onClick={onClose} style={{
            padding: '9px 18px', borderRadius: 8, background: 'var(--bg-2)',
            color: 'var(--t2)', border: '1px solid var(--bd-s)', cursor: 'pointer',
            fontSize: 12, fontFamily: 'inherit',
          }}>취소</button>
          <button
            onClick={handleSubmit}
            disabled={!selectedDoctorId || saving}
            style={{
              padding: '9px 18px', borderRadius: 8, background: 'var(--ac)',
              color: '#fff', border: 'none', cursor: selectedDoctorId ? 'pointer' : 'not-allowed',
              fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
              opacity: selectedDoctorId && !saving ? 1 : .5,
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            <Plus size={13} />
            {saving ? '추가 중…' : '예정 추가'}
          </button>
        </div>
      </div>
    </div>
  );
}
