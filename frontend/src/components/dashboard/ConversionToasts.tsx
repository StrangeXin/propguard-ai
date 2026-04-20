"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/app/providers";

type Toast = {
  id: "strategy-cap" | "ai-while-away" | "sandbox-bust";
  message: string;
  cta: { label: string; href: string };
};

const SESSION_KEY = "pg-toasts-dismissed";

function readDismissed(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    return new Set(JSON.parse(sessionStorage.getItem(SESSION_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

// Three §11 conversion toasts, each fires once per session:
// 1. Anon saves 3 strategies → "register for 50"
// 2. AI auto-trader running 15+ min (anon/free) → "upgrade to keep it running"
// 3. Anon equity < 10% of initial → "sandbox about to reset"
export function ConversionToasts({
  strategyCount,
  aiTradeStartedAt,
  equity,
  initialBalance,
}: {
  strategyCount: number;
  aiTradeStartedAt: number | null;
  equity: number | null;
  initialBalance: number | null;
}) {
  const { user } = useAuth();
  const [visible, setVisible] = useState<Toast | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(readDismissed);

  const dismiss = (id: Toast["id"]) => {
    setDismissed((prev) => {
      const next = new Set(prev);
      next.add(id);
      sessionStorage.setItem(SESSION_KEY, JSON.stringify([...next]));
      return next;
    });
    setVisible(null);
  };

  // Rule 1: strategy cap for anon
  useEffect(() => {
    if (!user && strategyCount >= 3 && !dismissed.has("strategy-cap")) {
      setVisible({
        id: "strategy-cap",
        message: "You've saved 3 strategies — the anonymous limit. Register to keep up to 50.",
        cta: { label: "Register", href: "/login" },
      });
    }
  }, [user, strategyCount, dismissed]);

  // Rule 2: AI auto-trade running > 15 min (anon/free only, Pro/Premium run in backend)
  useEffect(() => {
    if (!aiTradeStartedAt) return;
    if (user?.tier === "pro" || user?.tier === "premium") return;
    const check = () => {
      const elapsed = Date.now() - aiTradeStartedAt;
      if (elapsed > 15 * 60 * 1000 && !dismissed.has("ai-while-away")) {
        setVisible({
          id: "ai-while-away",
          message: "AI has been trading for 15+ minutes. Upgrade to Pro to keep it running when you close the tab.",
          cta: { label: "Upgrade", href: "/pricing" },
        });
      }
    };
    check();
    const t = setInterval(check, 60_000);
    return () => clearInterval(t);
  }, [aiTradeStartedAt, user, dismissed]);

  // Rule 3: sandbox bust (anon only)
  useEffect(() => {
    if (user) return;
    if (equity == null || initialBalance == null || initialBalance === 0) return;
    if (equity < initialBalance * 0.1 && !dismissed.has("sandbox-bust")) {
      setVisible({
        id: "sandbox-bust",
        message: "Sandbox almost wiped. Try real-account risk controls instead?",
        cta: { label: "Register", href: "/login" },
      });
    }
  }, [equity, initialBalance, user, dismissed]);

  if (!visible) return null;

  return (
    <div className="fixed bottom-4 right-4 max-w-sm rounded-lg bg-neutral-900 border border-neutral-700 shadow-xl p-4 space-y-3 z-40">
      <p className="text-sm text-neutral-200">{visible.message}</p>
      <div className="flex gap-2 justify-end">
        <button
          onClick={() => dismiss(visible.id)}
          className="text-xs text-neutral-500 hover:text-white transition"
        >
          Dismiss
        </button>
        <Link
          href={visible.cta.href}
          className="text-xs px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white transition"
        >
          {visible.cta.label}
        </Link>
      </div>
    </div>
  );
}
