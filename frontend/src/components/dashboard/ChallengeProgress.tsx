"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/i18n/context";
import { Progress } from "@/components/ui/progress";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface ProgressData {
  profit_target: number;
  profit_target_pct: number;
  current_profit: number;
  profit_progress_pct: number;
  drawdown_limit: number;
  drawdown_used: number;
  drawdown_used_pct: number;
  drawdown_remaining: number;
  trading_days: number;
  min_trading_days: number;
  days_elapsed: number;
  total_pnl: number;
  pnl_pct: number;
}

const texts: Record<string, Record<string, string>> = {
  en: {
    title: "Challenge Progress",
    profitTarget: "Profit Target",
    drawdownUsed: "Drawdown Used",
    tradingDays: "Trading Days",
    elapsed: "Days Elapsed",
    remaining: "remaining",
    reached: "Target reached!",
    of: "of",
  },
  zh: {
    title: "挑战进度",
    profitTarget: "盈利目标",
    drawdownUsed: "回撤已用",
    tradingDays: "交易天数",
    elapsed: "已过天数",
    remaining: "剩余",
    reached: "目标已达成!",
    of: "/",
  },
};

export function ChallengeProgress({
  accountId,
  firmName,
  accountSize,
}: {
  accountId: string;
  firmName: string;
  accountSize: number;
}) {
  const { locale } = useI18n();
  const t = texts[locale] || texts.en;
  const [data, setData] = useState<ProgressData | null>(null);

  const fetch_ = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/accounts/${accountId}/challenge-progress?firm_name=${firmName}&account_size=${accountSize}`
      );
      const d = await res.json();
      if (!d.status && !d.error) setData(d);
    } catch { /* silent */ }
  }, [accountId, firmName, accountSize]);

  useEffect(() => {
    fetch_();
    const interval = setInterval(fetch_, 5000);
    return () => clearInterval(interval);
  }, [fetch_]);

  if (!data) return null;

  const profitColor = data.profit_progress_pct >= 100 ? "text-green-400" : "text-zinc-300";
  const ddColor = data.drawdown_used_pct > 70 ? "text-red-400" : data.drawdown_used_pct > 40 ? "text-yellow-400" : "text-green-400";

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
        {t.title}
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Profit Target */}
        <div className="bg-zinc-900 rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">{t.profitTarget}</span>
            <span className={`text-xs font-mono ${profitColor}`}>
              {data.profit_progress_pct >= 100 ? t.reached : `${data.profit_progress_pct}%`}
            </span>
          </div>
          <Progress
            value={data.profit_progress_pct}
            className="h-2 bg-zinc-800 [&>div]:bg-green-500"
          />
          <div className="flex justify-between text-xs text-zinc-500">
            <span className="font-mono">${data.current_profit.toLocaleString()}</span>
            <span className="font-mono">${data.profit_target.toLocaleString()}</span>
          </div>
        </div>

        {/* Drawdown Used */}
        <div className="bg-zinc-900 rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">{t.drawdownUsed}</span>
            <span className={`text-xs font-mono ${ddColor}`}>
              {data.drawdown_used_pct}%
            </span>
          </div>
          <Progress
            value={data.drawdown_used_pct}
            className={`h-2 bg-zinc-800 ${
              data.drawdown_used_pct > 70 ? "[&>div]:bg-red-500" :
              data.drawdown_used_pct > 40 ? "[&>div]:bg-yellow-500" :
              "[&>div]:bg-green-500"
            }`}
          />
          <div className="flex justify-between text-xs text-zinc-500">
            <span className="font-mono">${data.drawdown_used.toLocaleString()}</span>
            <span className="font-mono">${data.drawdown_remaining.toLocaleString()} {t.remaining}</span>
          </div>
        </div>

        {/* Trading Days + Stats */}
        <div className="bg-zinc-900 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-zinc-500">{t.tradingDays}</span>
            <span className="text-xs font-mono text-zinc-300">
              {data.trading_days} {t.of} {data.min_trading_days || "∞"}
            </span>
          </div>
          {data.min_trading_days > 0 && (
            <Progress
              value={Math.min(data.trading_days / data.min_trading_days * 100, 100)}
              className="h-2 bg-zinc-800 [&>div]:bg-blue-500"
            />
          )}
          <div className="grid grid-cols-2 gap-2 pt-1">
            <div>
              <span className="text-[10px] text-zinc-600 block">P&L</span>
              <span className={`text-sm font-mono font-bold ${data.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                {data.total_pnl >= 0 ? "+" : ""}{data.pnl_pct}%
              </span>
            </div>
            <div>
              <span className="text-[10px] text-zinc-600 block">{t.elapsed}</span>
              <span className="text-sm font-mono text-zinc-300">
                {data.days_elapsed}d
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
