"use client";

import Link from "next/link";
import { useLoginGate } from "@/hooks/useLoginGate";

type Props = {
  userKind: "anon" | "user";
  plan: string;
  metaapiAccountId: string | null;
};

// Persistent banner at the top of the dashboard communicating what "mode"
// the current visitor is in. Drives conversion: anon sees a prominent
// register CTA; Free sees upgrade CTA; Pro+ sees managed-account status.
export function PlanBanner({ userKind, plan, metaapiAccountId }: Props) {
  const { openGate } = useLoginGate();

  if (userKind === "anon") {
    return (
      <div className="flex items-center justify-between gap-4 rounded border border-amber-600/50 bg-amber-950/40 px-4 py-2 text-sm">
        <div className="text-amber-200">
          👀 Preview mode · Viewing shared MetaApi demo · Sign in to place trades
        </div>
        <button
          onClick={() => openGate("Sign in to place trades")}
          className="px-3 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium transition"
        >
          Sign in →
        </button>
      </div>
    );
  }

  if (!metaapiAccountId) {
    return (
      <div className="flex items-center justify-between gap-4 rounded border border-blue-600/50 bg-blue-950/40 px-4 py-2 text-sm">
        <div className="text-blue-200">
          ✅ Logged in · <span className="capitalize">{plan}</span> plan · Sandbox only
        </div>
        <Link
          href="/settings/broker"
          className="px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition"
        >
          Bind real MetaApi account →
        </Link>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between gap-4 rounded border border-emerald-600/50 bg-emerald-950/40 px-4 py-2 text-sm">
      <div className="text-emerald-200">
        ✅ <span className="capitalize">{plan}</span> · Real account:{" "}
        <span className="font-mono">{metaapiAccountId.slice(0, 8)}…</span>
      </div>
      <Link
        href="/settings/broker"
        className="text-emerald-200 hover:underline text-xs"
      >
        Manage →
      </Link>
    </div>
  );
}
