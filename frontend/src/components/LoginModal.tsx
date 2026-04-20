"use client";

import { useState } from "react";
import { useAuth } from "@/app/providers";
import { useLoginGate } from "@/hooks/useLoginGate";
import { useI18n } from "@/i18n/context";

type Mode = "login" | "register";

export function LoginModal() {
  const { open, reason, closeGate } = useLoginGate();
  const { login, register } = useAuth();
  const { t } = useI18n();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    const result = mode === "login"
      ? await login(email, password)
      : await register(email, password, name);
    setSubmitting(false);
    if (result) {
      setErr(result);
    } else {
      closeGate();
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setErr(null);
  }

  const title = mode === "login" ? t("auth.login_required_title") : t("auth.register_required_title");
  const submitLabel = mode === "login"
    ? (submitting ? t("auth.logging_in") : t("auth.login"))
    : (submitting ? t("auth.registering") : t("auth.register_cta"));

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
        <div className="flex gap-1 mb-4 bg-neutral-800 rounded p-1">
          <button
            type="button"
            onClick={() => switchMode("login")}
            className={`flex-1 py-1.5 text-sm rounded transition ${
              mode === "login" ? "bg-neutral-700 text-white" : "text-neutral-400 hover:text-white"
            }`}
          >
            {t("auth.login")}
          </button>
          <button
            type="button"
            onClick={() => switchMode("register")}
            className={`flex-1 py-1.5 text-sm rounded transition ${
              mode === "register" ? "bg-neutral-700 text-white" : "text-neutral-400 hover:text-white"
            }`}
          >
            {t("auth.register_cta")}
          </button>
        </div>
        <h2 className="text-xl font-semibold mb-1">{title}</h2>
        {reason && <p className="text-sm text-neutral-400 mb-4">{reason}</p>}
        <form onSubmit={onSubmit} className="space-y-3">
          {mode === "register" && (
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("auth.name_optional")}
              className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-white"
            />
          )}
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
            minLength={mode === "register" ? 6 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === "register" ? t("auth.password_register_hint") : t("auth.password")}
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
              {submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
