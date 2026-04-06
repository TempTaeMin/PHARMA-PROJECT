import { useState, useEffect, useCallback, useRef } from 'react';
import { getCached, setCache, isStale, invalidate } from '../api/cache';

/**
 * SWR 캐싱이 적용된 API 호출 훅
 * 
 * 사용법:
 *   const { data, loading, refresh } = useCachedApi('doctors', doctorApi.list);
 * 
 * 동작:
 *   1. 캐시에 데이터 있으면 → loading=false, 즉시 표시
 *   2. 캐시가 오래됐으면 → 백그라운드에서 갱신
 *   3. 캐시 없으면 → loading=true, API 호출
 */
export function useCachedApi(cacheKey, apiFn, options = {}) {
  const { ttlKey = 'doctors', deps = [], immediate = true } = options;
  const cached = getCached(cacheKey);

  const [data, setData] = useState(cached);
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);

  const execute = useCallback(async (...args) => {
    // 캐시 없을 때만 로딩 표시
    if (!getCached(cacheKey)) {
      setLoading(true);
    }
    setError(null);

    try {
      const result = await apiFn(...args);
      if (mountedRef.current) {
        setData(result);
        setCache(cacheKey, result);
        setLoading(false);
      }
      return result;
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message);
        setLoading(false);
      }
      throw err;
    }
  }, [cacheKey, ...deps]);

  useEffect(() => {
    mountedRef.current = true;

    if (immediate) {
      if (cached && !isStale(cacheKey, ttlKey)) {
        // 신선한 캐시 → API 호출 안 함
        setData(cached);
        setLoading(false);
      } else if (cached) {
        // 오래된 캐시 → 보여주면서 백그라운드 갱신
        setData(cached);
        setLoading(false);
        execute().catch(() => {});
      } else {
        // 캐시 없음 → 로딩
        execute().catch(() => {});
      }
    }

    return () => { mountedRef.current = false; };
  }, [cacheKey, immediate, ...deps]);

  const refresh = useCallback(() => {
    invalidate(cacheKey);
    return execute();
  }, [cacheKey, execute]);

  return { data, loading, error, refresh, execute };
}
