"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/app/providers";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const DEFAULT_STRATEGY = {
  name: "MA Crossover",
  description: "SMA10/SMA20 crossover with martingale position sizing",
  symbols: ["EURUSD"],
  kline_period: "1h",
  rules: [
    "SMA10 and SMA20 crossover: golden cross = buy, death cross = sell",
    "Initial lot: 0.01, scale factor: 1.1x, spacing by ATR(14)",
    "Max 30 orders per direction, max lot per order: 0.1",
    "Close all when avg profit reaches 300 points",
    "Force close all if one-direction floating loss exceeds $50,000",
    "Trailing stop: per order start 200 points / retrace 50 points; overall start 100 points / retrace 20 points",
    "Hedging: if floating loss > $600 start hedging, stop at $500, ensure min $10 profit per close",
    "Bi-directional trading enabled"
  ],
};

const INTERVALS = [
  { value: "1m", label: "1m" },
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "1h", label: "1H" },
  { value: "4h", label: "4H" },
  { value: "1d", label: "1D" },
];

const texts: Record<string, Record<string, string>> = {
  en: {
    title: "AI Auto Trading",
    strategy: "Strategy",
    strategyName: "Strategy Name",
    symbols: "Symbols",
    rules: "Rules (one per line)",
    interval: "Interval",
    dryRun: "Dry Run (no real orders)",
    live: "Live Trading",
    analyze: "Analyze Once",
    start: "Start Auto Trading",
    stop: "Stop",
    running: "Running",
    stopped: "Stopped",
    cycles: "Cycles",
    lastAnalysis: "Last Analysis",
    actions: "Actions",
    log: "Execution Log",
    noSessions: "No active sessions",
    warning: "Warning: Live trading uses real money. Start with Dry Run first.",
  },
  zh: {
    title: "AI 自动交易",
    strategy: "交易策略",
    strategyName: "策略名称",
    symbols: "交易品种",
    rules: "策略规则（每行一条）",
    interval: "执行间隔",
    dryRun: "模拟运行（不下真单）",
    live: "实盘交易",
    analyze: "分析一次",
    start: "启动自动交易",
    stop: "停止",
    running: "运行中",
    stopped: "已停止",
    cycles: "执行次数",
    lastAnalysis: "最近分析",
    actions: "操作",
    log: "执行日志",
    noSessions: "无活跃会话",
    warning: "警告：实盘交易使用真实资金。请先用模拟运行测试。",
  },
};

export function AITrader({ firmName, accountSize, evaluationType }: {
  firmName: string;
  accountSize: number;
  evaluationType?: string;
}) {
  const { locale } = useI18n();
  const { token } = useAuth();
  const t = texts[locale] || texts.en;

  const [strategyName, setStrategyName] = useState(DEFAULT_STRATEGY.name);
  const [symbols, setSymbols] = useState(DEFAULT_STRATEGY.symbols.join(", "));
  const [rules, setRules] = useState(DEFAULT_STRATEGY.rules.join("\n"));
  const [interval, setInterval_] = useState("1h");
  const [dryRun, setDryRun] = useState(true);
  const [loading, setLoading] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [lastResult, setLastResult] = useState<any | null>(null);
  const [sessions, setSessions] = useState<Array<Record<string, unknown>>>([]);

  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  const buildStrategy = () => ({
    name: strategyName,
    symbols: symbols.split(",").map((s: string) => s.trim()).filter(Boolean),
    kline_period: interval,
    rules: rules.split("\n").filter((r: string) => r.trim()),
  });

  // Fetch sessions
  const fetchSessions = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/sessions`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch { /* silent */ }
  }, [token]);

  useEffect(() => {
    fetchSessions();
    const i = setInterval(fetchSessions, 5000);
    return () => clearInterval(i);
  }, [fetchSessions]);

  // Analyze once
  const analyzeOnce = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/analyze`, {
        method: "POST", headers,
        body: JSON.stringify({
          strategy: buildStrategy(),
          firm_name: firmName,
          account_size: accountSize,
          evaluation_type: evaluationType,
          dry_run: dryRun,
        }),
      });
      const data = await res.json();
      setLastResult(data);
    } catch (e) {
      setLastResult({ error: "Network error" });
    } finally {
      setLoading(false);
    }
  };

  // Start session
  const startSession = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/start`, {
        method: "POST", headers,
        body: JSON.stringify({
          strategy: buildStrategy(),
          interval,
          firm_name: firmName,
          account_size: accountSize,
          evaluation_type: evaluationType,
          dry_run: dryRun,
        }),
      });
      const data = await res.json();
      if (data.started) fetchSessions();
      setLastResult(data);
    } catch {
      setLastResult({ error: "Failed to start" });
    } finally {
      setLoading(false);
    }
  };

  // Stop session
  const stopSession = async (sessionId: string) => {
    await fetch(`${API_BASE}/api/ai-trade/stop/${sessionId}`, { method: "POST", headers });
    fetchSessions();
  };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">{t.title}</h2>

      {/* Strategy Editor */}
      <Card className="bg-zinc-900 border-0">
        <CardContent className="pt-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">{t.strategyName}</label>
              <input value={strategyName} onChange={(e) => setStrategyName(e.target.value)}
                className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none" />
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">{t.symbols}</label>
              <input value={symbols} onChange={(e) => setSymbols(e.target.value)}
                placeholder="EURUSD, GBPUSD"
                className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none" />
            </div>
          </div>

          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">{t.rules}</label>
            <textarea value={rules} onChange={(e) => setRules(e.target.value)} rows={6}
              className="w-full bg-zinc-800 text-white rounded px-3 py-2 text-xs font-mono resize-none focus:outline-none leading-relaxed" />
          </div>

          <div className="flex items-center gap-3">
            {/* Interval */}
            <div className="flex bg-zinc-800 rounded overflow-hidden">
              {INTERVALS.map((iv) => (
                <button key={iv.value} onClick={() => setInterval_(iv.value)}
                  className={`px-2 py-1 text-xs transition-colors ${interval === iv.value ? "bg-zinc-600 text-white" : "text-zinc-500"}`}>
                  {iv.label}
                </button>
              ))}
            </div>

            {/* Dry run toggle */}
            <button onClick={() => setDryRun(!dryRun)}
              className={`px-3 py-1 text-xs rounded transition-colors ${dryRun ? "bg-yellow-900 text-yellow-300" : "bg-red-900 text-red-300"}`}>
              {dryRun ? t.dryRun : t.live}
            </button>
          </div>

          {!dryRun && (
            <p className="text-xs text-red-400">{t.warning}</p>
          )}

          <div className="flex gap-2">
            <button onClick={analyzeOnce} disabled={loading}
              className="flex-1 py-2 bg-blue-800 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
              {loading ? "..." : t.analyze}
            </button>
            <button onClick={startSession} disabled={loading}
              className="flex-1 py-2 bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
              {t.start}
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Active Sessions */}
      {sessions.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs text-zinc-500 uppercase">{t.log}</h3>
          {sessions.map((s) => (
            <div key={String(s.id)} className="bg-zinc-900 rounded-lg px-4 py-2.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge className={s.status === "running" ? "bg-green-900 text-green-300 text-[10px]" : "bg-zinc-800 text-zinc-400 text-[10px]"}>
                  {s.status === "running" ? t.running : t.stopped}
                </Badge>
                <span className="text-sm text-white">{String(s.strategy_name)}</span>
                <span className="text-xs text-zinc-500">{String(s.interval)}s</span>
                <span className="text-xs text-zinc-600">{t.cycles}: {String(s.cycles)}</span>
              </div>
              {s.status === "running" && (
                <button onClick={() => stopSession(String(s.id))}
                  className="text-xs text-red-400 hover:text-red-300">{t.stop}</button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Last Result */}
      {lastResult && (
        <Card className="bg-zinc-900 border-0">
          <CardContent className="pt-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500">{t.lastAnalysis}</span>
              {lastResult.dry_run && <Badge className="bg-yellow-900 text-yellow-300 text-[10px]">DRY RUN</Badge>}
            </div>
            {lastResult.analysis && (
              <p className="text-xs text-zinc-300">{String(lastResult.analysis)}</p>
            )}
            {lastResult.error && (
              <p className="text-xs text-red-400">{String(lastResult.error)}</p>
            )}
            {lastResult.executions && Array.isArray(lastResult.executions) && lastResult.executions.length > 0 && (
              <div className="space-y-1">
                <span className="text-[10px] text-zinc-500">{t.actions}:</span>
                {(lastResult.executions as Array<Record<string, unknown>>).map((ex, i) => {
                  const action = ex.action as Record<string, unknown> | undefined;
                  return (
                    <div key={i} className="text-xs bg-zinc-800 rounded px-2 py-1 flex justify-between">
                      <span className="text-zinc-300">
                        {action ? `${String(action.type).toUpperCase()} ${String(action.symbol)} ${String(action.volume)}` : "unknown"}
                      </span>
                      <span className={ex.status === "dry_run" ? "text-yellow-400" : (ex.result as Record<string, unknown>)?.success ? "text-green-400" : "text-red-400"}>
                        {ex.status === "dry_run" ? "simulated" : (ex.result as Record<string, unknown>)?.success ? "executed" : "failed"}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
            {lastResult.next_review && (
              <p className="text-[10px] text-zinc-600">Next: {String(lastResult.next_review)}</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
