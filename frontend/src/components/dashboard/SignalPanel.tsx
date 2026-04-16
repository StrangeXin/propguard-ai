"use client";

import { useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/i18n/context";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface SignalScore {
  score: number;
  rationale: string;
  risk_level: string;
}

interface Signal {
  id: string;
  symbol: string;
  direction: string;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  source_name: string;
  received_at: string;
}

interface ScoredSignal {
  signal: Signal;
  score: SignalScore | null;
}

const scoreColor = (score: number) => {
  if (score >= 70) return "bg-green-900 text-green-300";
  if (score >= 40) return "bg-yellow-900 text-yellow-300";
  return "bg-red-900 text-red-300";
};

const riskBadge = (risk: string) => {
  const map: Record<string, string> = {
    low: "bg-green-900 text-green-300",
    med: "bg-yellow-900 text-yellow-300",
    high: "bg-red-900 text-red-300",
  };
  return map[risk] || "bg-zinc-800 text-zinc-400";
};

export function SignalPanel({ onTrade }: { onTrade?: (symbol: string, side: string) => void } = {}) {
  const { t, locale } = useI18n();
  const [input, setInput] = useState("");
  const [signals, setSignals] = useState<ScoredSignal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submitSignal = useCallback(async () => {
    if (!input.trim()) return;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/signals/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: input, source_name: "Manual" }),
      });
      const data = await res.json();

      if (data.parsed) {
        setSignals((prev) => [
          { signal: data.signal, score: data.score },
          ...prev.slice(0, 19),
        ]);
        setInput("");
      } else {
        setError(data.message || t("signals.error.parse"));
      }
    } catch {
      setError(t("signals.error.api"));
    } finally {
      setLoading(false);
    }
  }, [input]);

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
        {t("signals.title")}
      </h2>

      {/* Input area */}
      <div className="bg-zinc-900 rounded-lg p-4 space-y-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("signals.placeholder")}
          className="w-full bg-zinc-800 text-white rounded-lg p-3 text-sm resize-none h-20 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-600"
        />
        <div className="flex justify-between items-center">
          <p className="text-xs text-zinc-500">
            {t("signals.hint")}
          </p>
          <button
            onClick={submitSignal}
            disabled={loading || !input.trim()}
            className="px-4 py-1.5 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
          >
            {loading ? t("signals.scoring") : t("signals.score")}
          </button>
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>

      {/* Signal list */}
      {signals.length > 0 && (
        <div className="space-y-3">
          {signals.map((s) => (
            <Card key={s.signal.id} className="bg-zinc-900 border-0">
              <CardContent className="pt-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-white">
                      {s.signal.symbol}
                    </span>
                    <Badge
                      className={
                        s.signal.direction === "long"
                          ? "bg-green-900 text-green-300"
                          : "bg-red-900 text-red-300"
                      }
                    >
                      {s.signal.direction.toUpperCase()}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    {s.score && (
                      <>
                        <Badge className={scoreColor(s.score.score)}>
                          {s.score.score}/100
                        </Badge>
                        <Badge className={riskBadge(s.score.risk_level)}>
                          {s.score.risk_level.toUpperCase()}
                        </Badge>
                      </>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 text-xs text-zinc-400 mb-2">
                  <div>
                    <span className="text-zinc-600">Entry</span>
                    <p className="font-mono text-zinc-300">
                      {s.signal.entry_price
                        ? `$${s.signal.entry_price.toLocaleString()}`
                        : "—"}
                    </p>
                  </div>
                  <div>
                    <span className="text-zinc-600">SL</span>
                    <p className="font-mono text-red-400">
                      {s.signal.stop_loss
                        ? `$${s.signal.stop_loss.toLocaleString()}`
                        : "—"}
                    </p>
                  </div>
                  <div>
                    <span className="text-zinc-600">TP</span>
                    <p className="font-mono text-green-400">
                      {s.signal.take_profit
                        ? `$${s.signal.take_profit.toLocaleString()}`
                        : "—"}
                    </p>
                  </div>
                </div>

                {s.score && (
                  <p className="text-xs text-zinc-500">{s.score.rationale}</p>
                )}

                {onTrade && s.score && s.score.score >= 40 && (
                  <button
                    onClick={() => onTrade(s.signal.symbol, s.signal.direction === "long" ? "buy" : "sell")}
                    className="mt-2 w-full py-1.5 bg-blue-800 hover:bg-blue-700 text-white text-xs rounded transition-colors"
                  >
                    {locale === "zh" ? `一键交易 ${s.signal.symbol}` : `Trade ${s.signal.symbol}`}
                  </button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {signals.length === 0 && (
        <div className="text-center text-zinc-600 text-sm py-8">
          {t("signals.empty")}
        </div>
      )}
    </div>
  );
}
