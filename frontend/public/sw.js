// MediSync Service Worker — 최소 PWA 자격 (설치 가능 + 홈 화면 추가).
// 베타 단계엔 적극 캐싱 안 함 — 배포 후 새 버전이 즉시 보이도록 네트워크 우선.

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // 네트워크 우선 — 캐시 미사용.
  // 추후 오프라인 지원 시 여기에 cache-first 또는 stale-while-revalidate 전략 추가.
});
