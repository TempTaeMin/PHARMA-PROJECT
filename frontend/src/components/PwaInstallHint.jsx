import { useEffect, useState, useRef } from 'react';
import { Download, Share, MoreVertical, X, Smartphone, ChevronRight } from 'lucide-react';

const STORAGE_KEY = 'medisync-pwa-hint-dismissed';
const SHOW_DELAY_MS = 1500;

function detectPlatform() {
  if (typeof navigator === 'undefined') return 'unknown';
  const ua = navigator.userAgent || '';
  if (/iPhone|iPad|iPod/i.test(ua)) return 'ios';
  if (/Android/i.test(ua)) return 'android';
  return 'unknown';
}

function isMobile() {
  if (typeof navigator === 'undefined') return false;
  return /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '');
}

function isStandalone() {
  if (typeof window === 'undefined') return false;
  if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) return true;
  if (window.navigator && window.navigator.standalone) return true;  // iOS Safari
  return false;
}

/**
 * 모바일 베타 테스터에게 PWA "홈 화면에 추가" 방법을 안내.
 * - 데스크톱 / 이미 설치 / dismissed 면 안 뜸
 * - iOS: 매뉴얼 안내 (공유 → 홈 화면에 추가)
 * - Android: beforeinstallprompt 캡처해서 직접 설치 트리거
 * - "다시 보지 않기" → localStorage 영구 저장
 */
export default function PwaInstallHint() {
  const [show, setShow] = useState(false);
  const [platform, setPlatform] = useState('unknown');
  const deferredRef = useRef(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    // 노출 조건 체크
    const path = window.location.pathname || '/';
    if (path.startsWith('/auth') || path.startsWith('/login')) return;
    if (!isMobile()) return;
    if (isStandalone()) return;
    if (localStorage.getItem(STORAGE_KEY) === '1') return;

    setPlatform(detectPlatform());

    // Android Chrome — beforeinstallprompt 캡처
    const onBIP = (e) => {
      e.preventDefault();
      deferredRef.current = e;
    };
    window.addEventListener('beforeinstallprompt', onBIP);

    // 1.5s 지연 후 표시 — 첫 진입 정신없는 와중 안 뜨게
    const t = setTimeout(() => setShow(true), SHOW_DELAY_MS);

    return () => {
      window.removeEventListener('beforeinstallprompt', onBIP);
      clearTimeout(t);
    };
  }, []);

  const dismiss = (permanent) => {
    if (permanent) localStorage.setItem(STORAGE_KEY, '1');
    setShow(false);
  };

  const triggerInstall = async () => {
    const dp = deferredRef.current;
    if (!dp) return;
    try {
      dp.prompt();
      const { outcome } = await dp.userChoice;
      if (outcome === 'accepted') {
        dismiss(true);
      }
    } catch { /* ignore */ }
    deferredRef.current = null;
  };

  if (!show) return null;

  const isAndroid = platform === 'android';
  const isIOS = platform === 'ios';
  const canInstallNow = isAndroid && !!deferredRef.current;

  return (
    <>
      <div
        onClick={() => dismiss(false)}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)',
          zIndex: 90, animation: 'fadeIn .15s', cursor: 'pointer',
        }}
      />
      <div style={{
        position: 'fixed', left: '50%', bottom: 16, transform: 'translateX(-50%)',
        width: 'min(420px, 92vw)',
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)', borderRadius: 14,
        zIndex: 91, boxShadow: '0 10px 40px rgba(0,0,0,.25)',
        animation: 'fadeUp .25s ease',
        overflow: 'hidden',
      }}>
        {/* 헤더 */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 16px',
          background: 'linear-gradient(135deg, var(--ac), #0056d2)',
          color: '#fff',
        }}>
          <Smartphone size={18} />
          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: 'Outfit', fontSize: 14, fontWeight: 700 }}>홈 화면에 추가</div>
            <div style={{ fontSize: 11, opacity: 0.9, marginTop: 1 }}>
              앱처럼 빠르게 열고 알림도 받으세요
            </div>
          </div>
          <button
            onClick={() => dismiss(false)}
            style={{
              width: 26, height: 26, borderRadius: 7,
              background: 'rgba(255,255,255,.18)', border: 'none', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
            }}
          >
            <X size={13} />
          </button>
        </div>

        {/* 본문 */}
        <div style={{ padding: 16 }}>
          {isIOS ? (
            <>
              <div style={{ fontSize: 12, color: 'var(--t2)', marginBottom: 10, lineHeight: 1.55 }}>
                Safari 에서 다음 두 단계로 추가할 수 있어요.
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Step n="1" Icon={Share} text="화면 아래 공유 버튼" />
                <Step n="2" Icon={ChevronRight} text='"홈 화면에 추가" 선택' />
              </div>
            </>
          ) : isAndroid ? (
            canInstallNow ? (
              <>
                <div style={{ fontSize: 12, color: 'var(--t2)', marginBottom: 12, lineHeight: 1.55 }}>
                  설치 버튼을 누르면 홈 화면에 바로 추가돼요.
                </div>
                <button
                  onClick={triggerInstall}
                  style={{
                    width: '100%', padding: '11px 14px', borderRadius: 9,
                    background: 'var(--ac)', color: '#fff', border: 'none',
                    fontSize: 13, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  }}
                >
                  <Download size={14} /> 지금 설치
                </button>
              </>
            ) : (
              <>
                <div style={{ fontSize: 12, color: 'var(--t2)', marginBottom: 10, lineHeight: 1.55 }}>
                  Chrome 메뉴에서 다음 항목을 선택해주세요.
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <Step n="1" Icon={MoreVertical} text="우측 상단 메뉴 열기" />
                  <Step n="2" Icon={ChevronRight} text='"홈 화면에 추가" 또는 "앱 설치"' />
                </div>
              </>
            )
          ) : (
            <div style={{ fontSize: 12, color: 'var(--t2)' }}>
              브라우저 메뉴에서 "홈 화면에 추가" 를 찾아주세요.
            </div>
          )}
        </div>

        {/* 푸터 */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', gap: 6,
          padding: '10px 16px', borderTop: '1px solid var(--bd-s)',
          background: 'var(--bg-2)',
        }}>
          <button
            onClick={() => dismiss(true)}
            style={{
              padding: '6px 10px', borderRadius: 6,
              background: 'transparent', border: 'none', color: 'var(--t3)',
              fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            다시 보지 않기
          </button>
          <button
            onClick={() => dismiss(false)}
            style={{
              padding: '6px 10px', borderRadius: 6,
              background: 'transparent', border: 'none', color: 'var(--t2)',
              fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            나중에
          </button>
        </div>
      </div>
    </>
  );
}

function Step({ n, Icon, text }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 10px', borderRadius: 8,
      background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
    }}>
      <span style={{
        width: 22, height: 22, borderRadius: '50%',
        background: 'var(--ac)', color: '#fff',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 700, fontFamily: 'Outfit', flexShrink: 0,
      }}>{n}</span>
      <Icon size={14} style={{ color: 'var(--ac)', flexShrink: 0 }} />
      <span style={{ fontSize: 12, color: 'var(--t1)' }}>{text}</span>
    </div>
  );
}
