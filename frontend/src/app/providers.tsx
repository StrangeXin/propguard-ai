"use client";

import { createContext, useContext, type ReactNode } from "react";
import { I18nProvider } from "@/i18n/context";
import { useAuthState } from "@/hooks/useAuth";
import { UpgradeModal } from "@/components/UpgradeModal";
import { LoginGateProvider } from "@/hooks/useLoginGate";
import { LoginModal } from "@/components/LoginModal";

type AuthContextType = ReturnType<typeof useAuthState>;

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside Providers");
  return ctx;
}

function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuthState();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <I18nProvider>
      <AuthProvider>
        <LoginGateProvider>
          {children}
          <UpgradeModal />
          <LoginModal />
        </LoginGateProvider>
      </AuthProvider>
    </I18nProvider>
  );
}
