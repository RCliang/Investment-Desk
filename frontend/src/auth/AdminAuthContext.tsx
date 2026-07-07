import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

const STORAGE_KEY = 'adminToken';

interface AdminAuthContextValue {
  token: string | null;
  isAdmin: boolean;
  login: (token: string, remember: boolean) => void;
  logout: () => void;
}

const AdminAuthContext = createContext<AdminAuthContextValue>({
  token: null,
  isAdmin: false,
  login: () => {},
  logout: () => {},
});

function readToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(STORAGE_KEY) ?? sessionStorage.getItem(STORAGE_KEY);
}

function clearTokenEverywhere() {
  localStorage.removeItem(STORAGE_KEY);
  sessionStorage.removeItem(STORAGE_KEY);
}

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readToken());

  // Cross-tab sync: another tab changed the token.
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setToken(readToken());
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  // Axios response interceptor (Task 6) dispatches this on 401.
  useEffect(() => {
    const handler = () => {
      clearTokenEverywhere();
      setToken(null);
    };
    window.addEventListener('admin:unauthorized', handler);
    return () => window.removeEventListener('admin:unauthorized', handler);
  }, []);

  const login = (tok: string, remember: boolean) => {
    clearTokenEverywhere(); // defensive: never leave stale tokens in the other storage
    const storage = remember ? localStorage : sessionStorage;
    storage.setItem(STORAGE_KEY, tok);
    setToken(tok);
  };

  const logout = () => {
    clearTokenEverywhere();
    setToken(null);
  };

  return (
    <AdminAuthContext.Provider value={{ token, isAdmin: !!token, login, logout }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAdminAuth(): AdminAuthContextValue {
  return useContext(AdminAuthContext);
}
