// Login state for the whole dashboard: who is logged in, login/logout, and an `api` helper that sends the token.
import { createContext, useCallback, useContext, useEffect, useState } from "react";

const STORAGE_KEY = "hub_auth";
const AuthContext = createContext(null);

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(loadSaved); // { token, user } or null
  const [ready, setReady] = useState(false); // false until a saved token has been checked

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setAuth(null);
  }, []);

  // On first load, ask the hub if the saved token still works (it expires after 8 hours).
  useEffect(() => {
    if (!auth) {
      setReady(true);
      return;
    }
    fetch("/api/auth/me", { headers: { Authorization: "Bearer " + auth.token } })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((user) => setAuth((a) => ({ ...a, user })))
      .catch(logout)
      .finally(() => setReady(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(username, password) {
    const r = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || "Login failed");
    localStorage.setItem(STORAGE_KEY, JSON.stringify(body));
    setAuth(body);
  }

  // fetch() that adds the token and logs out if the hub says the session is no longer valid.
  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (auth) headers.Authorization = "Bearer " + auth.token;
    const r = await fetch(path, { ...options, headers });
    if (r.status === 401) logout();
    return r;
  }

  return (
    <AuthContext.Provider value={{ user: auth ? auth.user : null, ready, login, logout, api }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
