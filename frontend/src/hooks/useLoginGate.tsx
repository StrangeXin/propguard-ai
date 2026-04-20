"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

type GateState = {
  open: boolean;
  reason: string | null;
  openGate: (reason?: string) => void;
  closeGate: () => void;
};

const Ctx = createContext<GateState | null>(null);

export function LoginGateProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<string | null>(null);
  return (
    <Ctx.Provider
      value={{
        open,
        reason,
        openGate: (r?: string) => { setOpen(true); setReason(r ?? null); },
        closeGate: () => { setOpen(false); setReason(null); },
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
