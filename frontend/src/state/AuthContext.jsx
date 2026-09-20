import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as api from '../api/client';

const TOKEN_KEY = 'ra.token';
const USER_KEY = 'ra.user';
const GUEST_KEY = 'ra.guestId';

const AuthContext = createContext(null);

function readStored(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key, value) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* private browsing or blocked storage — the session simply does not persist */
  }
}

/**
 * Stable per-browser guest identifier.
 *
 * Guest research is still rate limited, under its own scoped bucket, so the same
 * browser keeps the same allocation across reloads instead of minting a fresh quota
 * on every page load.
 */
function loadGuestId() {
  const existing = readStored(GUEST_KEY);
  if (existing) return existing;
  const random = Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
  const id = `guest_web_${random}`;
  writeStored(GUEST_KEY, id);
  return id;
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => readStored(TOKEN_KEY));
  const [user, setUser] = useState(() => {
    const raw = readStored(USER_KEY);
    try {
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [guestId] = useState(loadGuestId);

  const applySession = useCallback((payload) => {
    const profile = { userId: payload.user_id, email: payload.email, expiresAt: payload.expires_at };
    setToken(payload.access_token);
    setUser(profile);
    writeStored(TOKEN_KEY, payload.access_token);
    writeStored(USER_KEY, JSON.stringify(profile));
    return profile;
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
    writeStored(TOKEN_KEY, null);
    writeStored(USER_KEY, null);
  }, []);

  const signIn = useCallback(
    async (username, password) => applySession(await api.login(username, password)),
    [applySession],
  );

  const signUp = useCallback(
    async (username, password, email) => applySession(await api.register(username, password, email)),
    [applySession],
  );

  // A stored token whose expiry has passed is cleared up front, so the UI never shows a
  // signed-in header that every request would then reject.
  useEffect(() => {
    if (!user?.expiresAt) return;
    const expiresAt = new Date(user.expiresAt).getTime();
    if (Number.isFinite(expiresAt) && expiresAt <= Date.now()) signOut();
  }, [user, signOut]);

  const value = useMemo(
    () => ({ token, user, guestId, isAuthenticated: Boolean(token), signIn, signUp, signOut }),
    [token, user, guestId, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
