import React, { createContext, useContext, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { authStore } from '@/lib/auth-store';
import { refreshPushToken } from '@/lib/push-notifications';

interface Profile {
  name: string;
  mobile: string;
  vault_url: string;
  employer_count: number;
  active_since: string;
  has_totp: boolean;
}

interface AuthContextValue {
  isAuthenticated: boolean;
  hasDeviceCredential: boolean;
  profile: Profile | null;
  signIn: (token: string) => void;
  signOut: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasDeviceCredential, setHasDeviceCredential] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);

  // Restore session on mount. If there's no active session, check whether
  // this device was previously registered (SecureStore-persisted device id)
  // so splash.tsx can route to biometric-unlock instead of sign-in.
  useEffect(() => {
    (async () => {
      const token = await authStore.loadFromStorage();
      if (token) {
        setIsAuthenticated(true);
        loadProfile();
        refreshPushToken();  // fire-and-forget — never blocks app startup
      } else {
        const deviceId = await authStore.getDeviceId();
        setHasDeviceCredential(!!deviceId);
      }
    })();

    authStore.onSignOut = () => {
      setIsAuthenticated(false);
      setProfile(null);
    };
  }, []);

  async function loadProfile() {
    try {
      const data = await api.get<Profile>('/v1/vault/profile');
      setProfile(data);
    } catch {
      // Profile load failure is non-fatal; vault still usable
    }
  }

  function signIn(token: string) {
    authStore.setToken(token);
    authStore.clearStepToken();
    setIsAuthenticated(true);
    loadProfile();
  }

  function signOut() {
    authStore.clearToken();
    setIsAuthenticated(false);
    setProfile(null);
    // Best-effort server-side revocation
    api.post('/auth/employee/logout').catch(() => {});
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        hasDeviceCredential,
        profile,
        signIn,
        signOut,
        refreshProfile: loadProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
