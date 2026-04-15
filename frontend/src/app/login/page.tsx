"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../providers";
import { useI18n } from "@/i18n/context";

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    let err: string | null;
    if (mode === "register") {
      err = await register(email, password, name);
    } else {
      err = await login(email, password);
    }

    if (err) {
      setError(err);
      setLoading(false);
    } else {
      router.push("/");
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white">PropGuard AI</h1>
          <p className="text-zinc-400 text-sm mt-2">
            {mode === "login" ? "Sign in to your account" : "Create a new account"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-zinc-900 rounded-lg p-6 space-y-4">
          {mode === "register" && (
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full bg-zinc-800 text-white rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-600"
              />
            </div>
          )}

          <div>
            <label className="text-xs text-zinc-500 block mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="w-full bg-zinc-800 text-white rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-600"
            />
          </div>

          <div>
            <label className="text-xs text-zinc-500 block mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••"
              required
              minLength={6}
              className="w-full bg-zinc-800 text-white rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-600"
            />
          </div>

          {error && (
            <p className="text-sm text-red-400 bg-red-950/30 px-3 py-2 rounded">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-white text-black font-medium rounded-lg hover:bg-zinc-200 disabled:opacity-50 transition-colors text-sm"
          >
            {loading ? "..." : mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        <p className="text-center text-sm text-zinc-500">
          {mode === "login" ? (
            <>
              No account?{" "}
              <button onClick={() => { setMode("register"); setError(null); }} className="text-white hover:underline">
                Register
              </button>
            </>
          ) : (
            <>
              Have an account?{" "}
              <button onClick={() => { setMode("login"); setError(null); }} className="text-white hover:underline">
                Sign in
              </button>
            </>
          )}
        </p>
      </div>
    </main>
  );
}
