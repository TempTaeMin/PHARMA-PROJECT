import { useEffect, useState } from 'react';
import { Sparkles, X, Check } from 'lucide-react';

const STORAGE_KEY = 'medisync-changelog-last-version';

/**
 * 새 배포 직후 베타 테스터에게 변경사항을 보여주는 모달.
 * - 마운트 시 /changelog.json (cache-bust) 를 fetch
 * - localStorage 의 last-version 과 latest 비교
 *   · 일치 → 안 뜸
 *   · last-version 이 null/undefined (첫 방문) → silent stamp, 안 뜸
 *   · 다름 → last-version 이후 entry 만 모아 모달 표시
 * - "확인" 시 latest 를 last-version 에 저장
 */
export default function ChangelogModal() {
  const [show, setShow] = useState(false);
  const [latest, setLatest] = useState(null);
  const [newEntries, setNewEntries] = useState([]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch('/changelog.json?v=' + Date.now(), { cache: 'no-store' });
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        const newest = data.latest;
        const entries = Array.isArray(data.entries) ? data.entries : [];
        if (!newest) return;

        const last = localStorage.getItem(STORAGE_KEY);
        if (last === newest) return;  // 변경 없음

        if (!last) {
          // 첫 방문자 — 변경사항 모달 의미 없음, silent stamp 만
          localStorage.setItem(STORAGE_KEY, newest);
          return;
        }

        // last 이후 entry 만 추출 (entries 가 최신순으로 정렬되어 있다고 가정)
        const since = entries.filter(e => e.version > last);
        if (since.length === 0) {
          // entries 갱신 없이 latest 만 바뀐 경우 — 그냥 stamp
          localStorage.setItem(STORAGE_KEY, newest);
          return;
        }

        setLatest(newest);
        setNewEntries(since);
        setShow(true);
      } catch { /* offline / 404 — 무시 */ }
    })();

    return () => { cancelled = true; };
  }, []);

  const close = () => {
    if (latest) localStorage.setItem(STORAGE_KEY, latest);
    setShow(false);
  };

  if (!show) return null;

  return (
    <>
      <div
        onClick={close}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
          zIndex: 70, animation: 'fadeIn .15s', cursor: 'pointer',
        }}
      />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        width: 'min(520px, 92vw)', maxHeight: '85vh',
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 14,
        zIndex: 71, boxShadow: '0 14px 60px rgba(0,0,0,.5)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          padding: '18px 20px',
          background: 'linear-gradient(135deg, var(--ac), #6d28d9)',
          color: '#fff',
          borderTopLeftRadius: 14, borderTopRightRadius: 14,
          position: 'relative',
        }}>
          <button
            onClick={close}
            style={{
              position: 'absolute', top: 14, right: 14,
              width: 28, height: 28, borderRadius: 7,
              background: 'rgba(255,255,255,.18)', border: 'none', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
            }}
          >
            <X size={13} />
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Sparkles size={18} />
            <div style={{ fontFamily: 'Outfit', fontSize: 16, fontWeight: 700 }}>
              새로운 업데이트
            </div>
          </div>
          <div style={{ fontSize: 11, opacity: 0.9 }}>
            그동안 보고된 문제들을 반영했어요
          </div>
        </div>

        {/* Body */}
        <div style={{
          padding: 20, overflowY: 'auto', flex: 1,
        }}>
          {newEntries.map(entry => (
            <div key={entry.version} style={{ marginBottom: 16 }}>
              <div style={{
                display: 'flex', alignItems: 'baseline', gap: 8,
                marginBottom: 10, paddingBottom: 6,
                borderBottom: '1px solid var(--bd-s)',
              }}>
                <div style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 700, color: 'var(--t1)' }}>
                  {entry.title || entry.version}
                </div>
                <div style={{
                  fontSize: 10, color: 'var(--t3)',
                  fontFamily: "'JetBrains Mono'",
                }}>
                  {entry.date}
                </div>
              </div>
              <ul style={{
                listStyle: 'none', padding: 0, margin: 0,
                display: 'flex', flexDirection: 'column', gap: 6,
              }}>
                {(entry.items || []).map((item, i) => (
                  <li key={i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 8,
                    fontSize: 13, color: 'var(--t2)', lineHeight: 1.5,
                  }}>
                    <Check size={14} style={{ color: 'var(--gn)', flexShrink: 0, marginTop: 3 }} />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end',
          padding: '12px 20px', borderTop: '1px solid var(--bd-s)',
        }}>
          <button
            onClick={close}
            style={{
              padding: '9px 18px', borderRadius: 8,
              background: 'var(--ac)', color: '#fff', border: 'none',
              fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            확인
          </button>
        </div>
      </div>
    </>
  );
}
