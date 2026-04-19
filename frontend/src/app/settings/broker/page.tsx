"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "../../providers";
import { api } from "@/lib/api";

// Bind a MetaApi account ID so trading routes route through MetaApiBroker
// (real funds) instead of SandboxBroker (per-user simulation). Unbinding
// reverts to sandbox mode.
export default function BrokerSettingsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const currentBinding = user?.metaapi_account_id ?? "";
  const [accountId, setAccountId] = useState(currentBinding);
  const [status, setStatus] = useState<"idle" | "connecting" | "connected" | "error">("idle");
  const [message, setMessage] = useState("");

  if (!user) {
    return (
      <div className="max-w-xl mx-auto p-6 space-y-3">
        <h1 className="text-xl font-semibold">Broker settings</h1>
        <p className="text-sm text-neutral-400">
          Please <Link href="/login" className="underline hover:text-white">log in</Link> to bind a MetaApi account.
        </p>
      </div>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setStatus("connecting");
    setMessage("Validating account…");
    try {
      const result = await api<{ message: string; user: { metaapi_account_id: string } }>(
        "/api/user/broker/connect",
        {
          method: "POST",
          body: JSON.stringify({ metaapi_account_id: accountId.trim() }),
        },
      );
      setStatus("connected");
      setMessage(result.message || "Connected.");
      setTimeout(() => router.push("/dashboard"), 1500);
    } catch (e: unknown) {
      setStatus("error");
      const err = e as { detail?: string | { message?: string }; message?: string };
      const detailMsg =
        typeof err.detail === "string" ? err.detail :
        err.detail?.message ?? err.message ?? "Connection failed.";
      setMessage(detailMsg);
    }
  };

  const disconnect = async () => {
    try {
      await api("/api/user/broker", { method: "DELETE" });
      setAccountId("");
      setStatus("idle");
      setMessage("Disconnected — reverted to sandbox mode.");
    } catch {
      setMessage("Failed to disconnect.");
    }
  };

  return (
    <div className="max-w-xl mx-auto p-6 space-y-5">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Broker settings</h1>
        <p className="text-sm text-neutral-400">
          Bind your MetaApi account ID to trade with real funds. Get your account ID
          from{" "}
          <a
            className="underline hover:text-white"
            href="https://app.metaapi.cloud/"
            target="_blank"
            rel="noreferrer"
          >
            app.metaapi.cloud
          </a>.
        </p>
      </div>

      {currentBinding && (
        <div className="text-xs text-emerald-300 bg-emerald-950/40 border border-emerald-900 rounded px-3 py-2">
          Currently bound: <span className="font-mono">{currentBinding}</span>
        </div>
      )}

      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm font-medium">MetaApi account ID</label>
        <input
          type="text"
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
          placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          className="w-full px-3 py-2 rounded bg-neutral-800 border border-neutral-700 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
          required
        />
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={status === "connecting"}
            className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50 text-sm transition"
          >
            {status === "connecting" ? "Validating…" : "Connect"}
          </button>
          {currentBinding && (
            <button
              type="button"
              onClick={disconnect}
              className="px-4 py-2 rounded bg-neutral-700 hover:bg-neutral-600 text-sm transition"
            >
              Disconnect
            </button>
          )}
        </div>
        {message && (
          <div
            className={
              status === "error"
                ? "text-sm text-red-400"
                : status === "connected"
                ? "text-sm text-emerald-400"
                : "text-sm text-neutral-300"
            }
          >
            {message}
          </div>
        )}
      </form>

      <Link href="/dashboard" className="text-xs text-neutral-500 hover:text-white inline-block">
        ← Back to dashboard
      </Link>
    </div>
  );
}
