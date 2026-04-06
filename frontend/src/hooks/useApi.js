import { useState, useEffect, useCallback } from 'react';

export function useApi(apiFn, deps = [], immediate = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState(null);

  const execute = useCallback(async (...args) => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFn(...args);
      setData(result);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, deps);

  useEffect(() => {
    if (immediate) execute();
  }, [immediate, ...deps]);

  return { data, loading, error, execute, setData };
}

export function useWebSocket(userId = 'default') {
  const [messages, setMessages] = useState([]);
  const [connected, setConnected] = useState(false);
  const [ws, setWs] = useState(null);

  useEffect(() => {
    let socket = null;
    try {
      const { connectWebSocket } = require('../api/client');
      socket = connectWebSocket(
        userId,
        (msg) => setMessages(prev => [msg, ...prev].slice(0, 50)),
        () => setConnected(false),
      );
      setWs(socket);
      setConnected(true);
    } catch (e) {
      console.warn('[WS] Connection failed:', e.message);
    }

    return () => socket?.close();
  }, [userId]);

  return { messages, connected, ws };
}
