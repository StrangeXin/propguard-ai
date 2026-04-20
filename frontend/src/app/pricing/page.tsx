"use client";

import Link from "next/link";
import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { useAuth } from "../providers";
import { api } from "@/lib/api";
import { PLANS, type Plan } from "@/lib/pricing";

export default function PricingPage() {
  const { locale } = useI18n();
  const { user } = useAuth();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  const startCheckout = async (plan: Plan) => {
    if (!user) {
      window.location.href = `/login?next=${encodeURIComponent("/pricing")}`;
      return;
    }
    setError("");
    setLoading(plan);
    try {
      const res = await api<{ url?: string; error?: string }>(
        "/api/payments/checkout",
        { method: "POST", body: JSON.stringify({ tier: plan }) },
      );
      if (res.url) {
        window.location.href = res.url;
      } else {
        setError(res.error || "Checkout unavailable.");
        setLoading(null);
      }
    } catch (e: unknown) {
      const err = e as { message?: string };
      setError(err.message || "Checkout failed.");
      setLoading(null);
    }
  };

  return (
    <main className="min-h-screen p-6 md:p-12 max-w-5xl mx-auto space-y-10">
      <header className="space-y-3 text-center">
        <h1 className="text-3xl md:text-4xl font-bold">Pricing</h1>
        <p className="text-neutral-400">
          Start on sandbox for free. Upgrade when you're ready to trade real funds.
        </p>
      </header>

      <section className="grid md:grid-cols-3 gap-4">
        {PLANS.map((p) => {
          const isCurrent = user?.tier === p.key;
          const features = p.features[locale] ?? p.features.en;
          const price = p.price[locale] ?? p.price.en;
          return (
            <div
              key={p.key}
              className={`rounded-lg border p-6 flex flex-col gap-4 ${
                p.highlight
                  ? "border-blue-500 bg-blue-950/20"
                  : "border-neutral-800 bg-neutral-900/50"
              }`}
            >
              <div>
                <h2 className="text-xl font-semibold capitalize">{p.key}</h2>
                <p className="text-3xl font-bold mt-1">{price}</p>
              </div>
              <ul className="text-sm space-y-1.5 text-neutral-300 flex-1">
                {features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span className="text-emerald-500">✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              {p.key === "free" ? (
                <Link
                  href="/dashboard"
                  className="block text-center py-2.5 rounded bg-neutral-700 hover:bg-neutral-600 text-sm font-medium transition"
                >
                  {user ? "Go to dashboard" : "Try for free"}
                </Link>
              ) : (
                <button
                  onClick={() => startCheckout(p.key)}
                  disabled={loading !== null || isCurrent}
                  className={`py-2.5 rounded text-sm font-medium transition ${
                    p.highlight
                      ? "bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50"
                      : "bg-neutral-700 hover:bg-neutral-600 disabled:opacity-50"
                  }`}
                >
                  {isCurrent
                    ? "Current plan"
                    : loading === p.key
                    ? "Redirecting…"
                    : `Upgrade to ${p.key}`}
                </button>
              )}
            </div>
          );
        })}
      </section>

      {error && (
        <div className="text-center text-sm text-red-400">{error}</div>
      )}

      <footer className="text-center text-xs text-neutral-500">
        <Link href="/dashboard" className="underline hover:text-white">
          ← Back to dashboard
        </Link>
      </footer>
    </main>
  );
}
