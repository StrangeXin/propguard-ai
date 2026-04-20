"use client";

import { useState } from "react";
import { useAuth } from "@/app/providers";
import { useLoginGate } from "@/hooks/useLoginGate";
import { useI18n } from "@/i18n/context";

export function LoginModal() {
  const { open, reason, closeGate } = useLoginGate();
  const { login } = useAuth();
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    const result = await login(email, password);
    setSubmitting(false);
    if (result) {
      setErr(result);
    } else {
      closeGate();
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      role="dialog"
      aria-modal="true"
      onClick={closeGate}
    >
      <div
        className="bg-neutral-900 border border-neutral-700 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-semibold mb-1">{t("auth.login_required_title")}</h2>
        {reason && <p className="text-sm text-neutral-400 mb-4">{reason}</p>}
        <form onSubmit={onSubmit} className="space-y-3">
          <input
            type="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("auth.email")}
            className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-white"
          />
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("auth.password")}
            className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-white"
          />
          {err && <p className="text-sm text-red-400">{err}</p>}
          <div className="flex gap-2 justify-end pt-1">
            <button
              type="button"
              className="px-4 py-2 text-sm rounded bg-neutral-700 hover:bg-neutral-600"
              onClick={closeGate}
            >
              {t("auth.cancel")}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50"
            >
              {submitting ? t("auth.logging_in") : t("auth.login")}
            </button>
          </div>
          <p className="text-xs text-neutral-500 pt-2">
            {t("auth.no_account")}{" "}
            <a href="/login?mode=register" className="text-blue-400 hover:underline">
              {t("auth.register_cta")}
            </a>
          </p>
        </form>
      </div>
    </div>
  );
}
