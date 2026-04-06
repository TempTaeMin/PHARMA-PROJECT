/**
 * 심플 인메모리 캐시 스토어
 * 
 * 페이지 전환 시 API를 매번 호출하지 않고,
 * 캐시된 데이터를 즉시 보여준 후 백그라운드에서 갱신합니다.
 * 
 * 전략: Stale-While-Revalidate (SWR)
 * 1. 캐시에 데이터가 있으면 → 즉시 반환 (화면 바로 표시)
 * 2. 캐시가 오래됐으면 → 백그라운드에서 API 호출 → 자동 갱신
 * 3. 캐시가 없으면 → API 호출 → 로딩 표시
 */

const cache = new Map();
const TTL = {
  hospitals: 5 * 60 * 1000,   // 5분 (거의 안 바뀜)
  doctors: 2 * 60 * 1000,     // 2분
  departments: 5 * 60 * 1000, // 5분
  crawl: 10 * 60 * 1000,      // 10분
  notifications: 30 * 1000,   // 30초
};

export function getCached(key) {
  const entry = cache.get(key);
  if (!entry) return null;
  return entry.data;
}

export function isStale(key, ttlKey = 'doctors') {
  const entry = cache.get(key);
  if (!entry) return true;
  const ttl = TTL[ttlKey] || 60000;
  return Date.now() - entry.timestamp > ttl;
}

export function setCache(key, data) {
  cache.set(key, { data, timestamp: Date.now() });
}

export function invalidate(key) {
  if (key) {
    // 특정 키 또는 prefix로 시작하는 모든 키 삭제
    for (const k of cache.keys()) {
      if (k === key || k.startsWith(key + ':')) {
        cache.delete(k);
      }
    }
  } else {
    cache.clear();
  }
}

/**
 * SWR 패턴으로 데이터 로드
 * - 캐시 있으면 즉시 반환 + 백그라운드 갱신
 * - 캐시 없으면 로딩 후 반환
 */
export async function fetchWithCache(key, apiFn, ttlKey = 'doctors') {
  const cached = getCached(key);

  if (cached && !isStale(key, ttlKey)) {
    // 신선한 캐시 → 그대로 반환
    return { data: cached, fromCache: true };
  }

  if (cached) {
    // 오래된 캐시 → 일단 반환하고 백그라운드 갱신
    apiFn().then(fresh => setCache(key, fresh)).catch(() => {});
    return { data: cached, fromCache: true, stale: true };
  }

  // 캐시 없음 → API 호출
  const data = await apiFn();
  setCache(key, data);
  return { data, fromCache: false };
}
