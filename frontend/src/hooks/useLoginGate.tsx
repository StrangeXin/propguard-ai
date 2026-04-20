"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

export type GateMode = "login" | "register";

type GateState = {
  open: boolean;
  reason: string | null;
  initialMode: GateMode;
  openGate: (reason?: string, mode?: GateMode) => void;
  closeGate: () => void;
};

const Ctx = createContext<GateState | null>(null);

export function LoginGateProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<string | null>(null);
  const [initialMode, setInitialMode] = useState<GateMode>("login");
  return (
    <Ctx.Provider
      value={{
        open,
        reason,
        initialMode,
        openGate: (r, mode) => {
          setOpen(true);
          setReason(r ?? null);
          setInitialMode(mode ?? "login");
        },
        closeGate: () => {
          setOpen(false);
          setReason(null);
          setInitialMode("login");
        },
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useLoginGate(): GateState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLoginGate must be used within LoginGateProvider");
  return v;
}
