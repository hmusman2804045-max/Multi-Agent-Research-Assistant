import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as api from '../api/client';
import { useAuth } from './AuthContext';

const QuotaContext = createContext(null);

/**
 * Holds the two separate caps reported by GET /quota.
 *
 * `personal` is this identity's own daily/burst allocation. `serviceWide` is the shared
 * pool every user draws from. They are kept apart deliberately: "you are out of searches"
 * and "the service is out of searches" are different situations for the reader.
 */
export function QuotaProvider({ children }) {
  const { token, guestId } = useAuth();
  const [quota, setQuota] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(
    async (signal) => {
      try {
        const data = await api.getQuota({ token, guestId, signal });
        setQuota({
          scope: data.scope,
          personal: data.personal,
          serviceWide: data.global,
        });
      } catch {
        // Quota display is ancillary; a failure here must never block research.
      } finally {
        setLoading(false);
      }
    },
    [token, guestId],
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const value = useMemo(() => ({ quota, loading, refresh }), [quota, loading, refresh]);
  return <QuotaContext.Provider value={value}>{children}</QuotaContext.Provider>;
}

export function useQuota() {
  const ctx = useContext(QuotaContext);
  if (!ctx) throw new Error('useQuota must be used inside <QuotaProvider>');
  return ctx;
}
