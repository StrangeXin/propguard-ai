"use client";

import { useEffect, useState } from "react";
import { setApiErrorHandler } from "@/lib/api";

type UpgradePayload = {
  code?: string;
  action?: string;
  message?: string;
  limit?: number;
  used?: number;
  plan?: string;
  upgrade_url?: string;
  resets_at?: string;
};

// Global modal that surfaces quota-exceeded (402) responses as an upgrade
// CTA. Mounted once at the Providers root.
export function UpgradeModal() {
  const [payload, setPayload] = useState<UpgradePayload | null>(null);

  useEffect(() => {
    setApiErrorHandler((err) => {
      if (err.status === 402 && err.detail) {
        setPayload(err.detail as UpgradePayload);
      }
    });
  }, []);

  if (!payload) return null;

  const resetAt = payload.resets_at ? new Date(payload.resets_at) : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      role="dialog"
      aria-modal="true"
      onClick={() => setPayload(null)}
    >
      <div
        className="bg-neutral-900 border border-neutral-700 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-semibold mb-2">Daily limit reached</h2>
        <p className="text-neutral-300 mb-4">
          {payload.message ?? `You've used your daily ${payload.action ?? "API"} allowance.`}
        </p>
        <dl className="text-sm text-neutral-400 space-y-1 mb-5">
          {payload.used != null && payload.limit != null && (
            <div className="flex justify-between">
              <dt>Used</dt>
              <dd>{payload.used} / {payload.limit}</dd>
            </div>
          )}
          {payload.plan && (
            <div className="flex justify-between">
              <dt>Plan</dt>
              <dd className="capitalize">{payload.plan}</dd>
            </div>
          )}
          {resetAt && (
            <div className="flex justify-between">
              <dt>Resets</dt>
              <dd>{resetAt.toLocaleString()}</dd>
            </div>
          )}
        </dl>
        <div className="flex gap-2 justify-end">
          <button
            className="px-4 py-2 text-sm rounded bg-neutral-700 hover:bg-neutral-600 transition"
            onClick={() => setPayload(null)}
          >
            Close
          </button>
          <a
            className="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white transition"
            href={payload.upgrade_url || "/pricing"}
          >
            Upgrade
          </a>
        </div>
      </div>
    </div>
  );
}
