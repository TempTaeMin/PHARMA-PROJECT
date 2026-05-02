import { useMemo, useState } from 'react';
import { Search, Check, X } from 'lucide-react';

const GRADE_AVATAR = {
  A: { bg: '#ffdad6', c: '#ba1a1a' },
  B: { bg: '#fef3c7', c: '#b45309' },
  C: { bg: '#dae2ff', c: '#0056d2' },
};

/**
 * 내 의료진 선택 풀스크린 오버레이.
 * 검색 + 병원 탭 + 병원별 그룹핑 교수 카드 리스트.
 * 교수 선택 시 onSelect(doctor)를 호출 → 상위에서 힌트 팝업 띄움.
 */
export default function SelectDoctorForMeeting({ open, doctors = [], onBack, onSelect }) {
  const [search, setSearch] = useState('');
  const [activeHospital, setActiveHospital] = useState('all');

  const hospitals = useMemo(() => {
    const set = new Map();
    doctors.forEach(d => {
      if (!d.hospital_name) return;
      set.set(d.hospital_name, (set.get(d.hospital_name) || 0) + 1);
    });
    return Array.from(set.entries()).map(([name, count]) => ({ name, count }));
  }, [doctors]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return doctors.filter(d => {
      if (activeHospital !== 'all' && d.hospital_name !== activeHospital) return false;
      if (!q) return true;
      return (
        (d.name || '').toLowerCase().includes(q) ||
        (d.hospital_name || '').toLowerCase().includes(q) ||
        (d.department || '').toLowerCase().includes(q)
      );
    });
  }, [doctors, search, activeHospital]);

  // 병원별 그룹핑
  const grouped = useMemo(() => {
    const map = new Map();
    filtered.forEach(d => {
      const key = d.hospital_name || '기타';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(d);
    });
    return Array.from(map.entries()).map(([name, list]) => ({ name, list }));
  }, [filtered]);

  if (!open) return null;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
      zIndex: 350, display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16, animation: 'fadeIn .18s ease',
    }}>
      <div style={{
        background: 'var(--bg-1)', borderRadius: 14,
        width: 560, maxWidth: '100%', maxHeight: '92vh',
        display: 'flex', flexDirection: 'column',
        animation: 'fadeUp .2s ease',
      }}>
      {/* ── Header ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '14px 16px',
        borderBottom: '1px solid var(--bd-s)',
        flexShrink: 0,
      }}>
        <div style={{
          flex: 1, fontFamily: 'Manrope', fontSize: 16, fontWeight: 800,
          color: 'var(--t1)',
        }}>
          내 의료진 관리
        </div>
        <button onClick={onBack} aria-label="닫기" style={{
          width: 30, height: 30, border: '1px solid var(--bd-s)', borderRadius: 7,
          background: 'var(--bg-2)', color: 'var(--t3)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
        }}>
          <X size={14} />
        </button>
      </div>

      {/* ── 검색창 ── */}
      <div style={{ padding: '12px 16px 6px', flexShrink: 0 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--bg-2)', borderRadius: 10,
          padding: '10px 12px',
          border: '1px solid var(--bd-s)',
        }}>
          <Search size={15} style={{ color: 'var(--t3)' }} />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="의료진 이름 또는 병원 검색"
            style={{
              flex: 1, border: 'none', background: 'transparent',
              outline: 'none', fontSize: 13, color: 'var(--t1)',
              fontFamily: 'inherit',
            }}
          />
        </div>
      </div>

      {/* ── 병원 탭 ── */}
      <div style={{
        display: 'flex', gap: 6, padding: '10px 16px 12px',
        overflowX: 'auto',
        borderBottom: '1px solid var(--bd-s)',
        flexShrink: 0,
      }}>
        <TabPill
          label="전체"
          active={activeHospital === 'all'}
          onClick={() => setActiveHospital('all')}
        />
        {hospitals.map(h => (
          <TabPill
            key={h.name}
            label={h.name}
            active={activeHospital === h.name}
            onClick={() => setActiveHospital(h.name)}
          />
        ))}
      </div>

      {/* ── 그룹핑 리스트 ── */}
      <div style={{
        flex: 1, overflowY: 'auto',
        padding: '14px 14px 20px',
      }}>
        {grouped.length === 0 ? (
          <div style={{
            padding: '80px 20px', textAlign: 'center',
            color: 'var(--t3)', fontSize: 13,
          }}>
            {doctors.length === 0 ? '등록된 교수가 없습니다' : '검색 결과가 없습니다'}
          </div>
        ) : grouped.map(group => (
          <div key={group.name} style={{ marginBottom: 18 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
              padding: '0 4px',
            }}>
              <div style={{
                width: 3, height: 14, borderRadius: 2,
                background: 'var(--ac)',
              }} />
              <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--t1)' }}>
                {group.name}
              </div>
              <div style={{ fontSize: 11, color: 'var(--t3)' }}>
                {group.list.length}명
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {group.list.map(doc => <DoctorCard key={doc.id} doctor={doc} onSelect={onSelect} />)}
            </div>
          </div>
        ))}
      </div>
      </div>
    </div>
  );
}

function DoctorCard({ doctor, onSelect }) {
  const avatar = { bg: 'var(--ac-d)', c: 'var(--ac)' };
  const initial = (doctor.name || '?').slice(0, 1);
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '12px 14px', borderRadius: 12,
      background: 'var(--bg-2)',
      border: '1px solid var(--bd-s)',
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 10,
        background: avatar.bg, color: avatar.c,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 17, fontWeight: 800, fontFamily: 'Manrope',
        flexShrink: 0,
      }}>{initial}</div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--t1)' }}>
          {doctor.name} <span style={{ fontSize: 11, color: 'var(--t3)', fontWeight: 500 }}>교수</span>
        </div>
        <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 2 }}>
          {doctor.department}
          {doctor.position ? ` · ${doctor.position}` : ''}
        </div>
      </div>

      <button
        onClick={() => onSelect?.(doctor)}
        style={{
          padding: '8px 16px', borderRadius: 9,
          background: 'var(--bg-1)', color: 'var(--ac)',
          border: '1px solid var(--ac)',
          fontSize: 12, fontWeight: 700, cursor: 'pointer',
          fontFamily: 'inherit',
          display: 'flex', alignItems: 'center', gap: 4,
        }}
      >
        <Check size={13} />
        선택
      </button>
    </div>
  );
}

function TabPill({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '7px 14px', borderRadius: 999,
        background: active ? 'var(--ac)' : 'var(--bg-2)',
        color: active ? '#fff' : 'var(--t2)',
        border: `1px solid ${active ? 'var(--ac)' : 'var(--bd-s)'}`,
        fontSize: 12, fontWeight: 700, cursor: 'pointer',
        fontFamily: 'inherit', whiteSpace: 'nowrap',
        flexShrink: 0,
      }}
    >
      {label}
    </button>
  );
}
