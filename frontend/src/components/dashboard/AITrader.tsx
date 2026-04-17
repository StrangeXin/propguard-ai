"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/app/providers";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

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
    strategyName: "Strategy Name",
    symbols: "Symbols",
    rules: "Strategy Rules",
    interval: "Interval",
    analyze: "AI Analyze",
    analyzing: "Analyzing...",
    startAuto: "Start Auto",
    stop: "Stop",
    running: "Running",
    stopped: "Stopped",
    cycles: "Cycles",
    confirm: "Confirm & Execute",
    cancel: "Cancel",
    noAction: "No action needed",
    proposed: "Proposed Actions",
    analysis: "Analysis",
    reason: "Reason",
    log: "Sessions",
  },
  zh: {
    title: "AI 自动交易",
    strategyName: "策略名称",
    symbols: "交易品种",
    rules: "策略规则",
    interval: "执行间隔",
    analyze: "AI 分析",
    analyzing: "分析中...",
    startAuto: "自动执行",
    stop: "停止",
    running: "运行中",
    stopped: "已停止",
    cycles: "次数",
    confirm: "确认执行",
    cancel: "取消",
    noAction: "当前无需操作",
    proposed: "建议操作",
    analysis: "分析结论",
    reason: "原因",
    log: "会话",
  },
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyResult = any;

export function AITrader({ firmName, accountSize, evaluationType }: {
  firmName: string;
  accountSize: number;
  evaluationType?: string;
}) {
  const { locale } = useI18n();
  const { token } = useAuth();
  const t = texts[locale] || texts.en;

  const [strategyName, setStrategyName] = useState("MA Crossover");
  const [symbols, setSymbols] = useState("EURUSD");
  const [rules, setRules] = useState("SMA10和SMA20，金叉做多，死叉做空\n首单0.01手，1.1倍加仓\n单向最多5单\n整体盈利300点全平");
  const [interval, setInterval_] = useState("1h");
  const [loading, setLoading] = useState(false);

  // Confirmation dialog state
  const [pendingResult, setPendingResult] = useState<AnyResult>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [executing, setExecuting] = useState(false);

  const [sessions, setSessions] = useState<AnyResult[]>([]);
  const [historyLogs, setHistoryLogs] = useState<AnyResult[]>([]);
  const [showHistory, setShowHistory] = useState(true);

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

  const fetchHistory = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/logs?limit=10`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setHistoryLogs(data.logs || []);
      }
    } catch { /* silent */ }
  }, [token]);

  useEffect(() => {
    fetchSessions();
    fetchHistory(); // Load history on mount
    const i = setInterval(fetchSessions, 10000);
    return () => clearInterval(i);
  }, [fetchSessions, fetchHistory]);

  // Step 1: AI Analyze (dry run) → show confirmation
  const analyzeAndPropose = async () => {
    setLoading(true);
    setPendingResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/analyze`, {
        method: "POST", headers,
        body: JSON.stringify({
          strategy: buildStrategy(),
          firm_name: firmName,
          account_size: accountSize,
          evaluation_type: evaluationType,
          dry_run: true,
        }),
      });
      const data = await res.json();
      setPendingResult(data);
      if (!data.error) {
        setShowConfirm(true);
        fetchHistory();
      }
    } catch {
      setPendingResult({ error: "Network error" });
    } finally {
      setLoading(false);
    }
  };

  // Step 2: User confirms → execute for real
  const confirmExecute = async () => {
    setExecuting(true);
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/analyze`, {
        method: "POST", headers,
        body: JSON.stringify({
          strategy: buildStrategy(),
          firm_name: firmName,
          account_size: accountSize,
          evaluation_type: evaluationType,
          dry_run: false,
        }),
      });
      const data = await res.json();
      setPendingResult(data);
      setShowConfirm(false);
    } catch {
      setPendingResult({ error: "Execution failed" });
    } finally {
      setExecuting(false);
    }
  };

  // Start auto session (auto-executes without confirmation)
  const startAuto = async () => {
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
          dry_run: false,
        }),
      });
      const data = await res.json();
      if (data.started) fetchSessions();
      setPendingResult(data);
    } catch {
      setPendingResult({ error: "Failed to start" });
    } finally {
      setLoading(false);
    }
  };

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
              <input value={symbols} onChange={(e) => setSymbols(e.target.value)} placeholder="EURUSD, GBPUSD"
                className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none" />
            </div>
          </div>

          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">{t.rules}</label>
            <textarea value={rules} onChange={(e) => setRules(e.target.value)} rows={4}
              placeholder={locale === "zh"
                ? "输入你的交易策略，例如：\n• 均线金叉做多，死叉做空\n• 价格突破布林带上轨做多\n• RSI低于30买入，高于70卖出"
                : "Enter your trading strategy, e.g.:\n• Buy on golden cross, sell on death cross\n• Buy when price breaks above Bollinger upper band\n• Buy when RSI < 30, sell when RSI > 70"}
              className="w-full bg-zinc-800 text-white rounded px-3 py-2 text-xs font-mono resize-none focus:outline-none leading-relaxed placeholder-zinc-600" />
          </div>

          <div className="flex gap-2">
            <button onClick={analyzeAndPropose} disabled={loading}
              className="flex-1 py-2 bg-blue-800 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-lg font-medium transition-colors">
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
                  {t.analyzing}
                </span>
              ) : t.analyze}
            </button>
            <div className="flex items-center gap-1">
              <select value={interval} onChange={(e) => setInterval_(e.target.value)}
                className="bg-zinc-800 text-zinc-400 text-xs rounded px-2 py-2 focus:outline-none">
                {INTERVALS.map((iv) => (
                  <option key={iv.value} value={iv.value}>{iv.label}</option>
                ))}
              </select>
              <button onClick={startAuto} disabled={loading}
                className="py-2 px-3 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-white text-xs rounded-lg transition-colors whitespace-nowrap">
                {t.startAuto}
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Confirmation Dialog */}
      {showConfirm && pendingResult && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 rounded-xl max-w-lg w-full p-6 space-y-4">
            <h3 className="text-lg font-bold text-white">{t.proposed}</h3>

            {/* Full AI context */}
            {(pendingResult.prompt || pendingResult.system_prompt) && (
              <details open className="group">
                <summary className="text-[10px] text-zinc-500 cursor-pointer hover:text-zinc-300 transition-colors mb-1">
                  {locale === "zh" ? "AI 完整上下文" : "Full AI Context"}
                </summary>
                <div className="bg-zinc-950 rounded-lg p-3 max-h-60 overflow-y-auto border border-zinc-800 space-y-3">
                  {pendingResult.system_prompt && (
                    <div>
                      <span className="text-[10px] text-blue-400 font-bold block mb-1">System Prompt:</span>
                      <pre className="text-[10px] text-zinc-500 whitespace-pre-wrap font-mono leading-relaxed">{pendingResult.system_prompt}</pre>
                    </div>
                  )}
                  {pendingResult.prompt && (
                    <div>
                      <span className="text-[10px] text-green-400 font-bold block mb-1">User Prompt:</span>
                      <pre className="text-[10px] text-zinc-400 whitespace-pre-wrap font-mono leading-relaxed">{pendingResult.prompt}</pre>
                    </div>
                  )}
                </div>
              </details>
            )}

            {pendingResult.analysis && (
              <div className="bg-zinc-800 rounded-lg p-3">
                <span className="text-[10px] text-zinc-500 block mb-1">{t.analysis}</span>
                <p className="text-sm text-zinc-300">{pendingResult.analysis}</p>
              </div>
            )}

            <div className="space-y-2">
              {pendingResult.executions?.map((ex: AnyResult, i: number) => (
                <div key={i} className="bg-zinc-800 rounded-lg p-3 flex items-center justify-between">
                  <div>
                    <span className={`text-sm font-bold ${ex.action?.type === "buy" ? "text-green-400" : ex.action?.type === "sell" ? "text-red-400" : "text-blue-400"}`}>
                      {ex.action?.type?.toUpperCase()}
                    </span>
                    <span className="text-sm text-white ml-2">{ex.action?.symbol}</span>
                    <span className="text-xs text-zinc-400 ml-2">{ex.action?.volume} lots</span>
                    {ex.action?.stop_loss && <span className="text-xs text-zinc-500 ml-2">SL: {ex.action.stop_loss}</span>}
                    {ex.action?.take_profit && <span className="text-xs text-zinc-500 ml-2">TP: {ex.action.take_profit}</span>}
                  </div>
                </div>
              ))}

              {pendingResult.executions?.length > 0 && pendingResult.executions[0]?.action?.reason && (
                <p className="text-xs text-zinc-500">{t.reason}: {pendingResult.executions[0].action.reason}</p>
              )}
            </div>

            {/* Prompt in confirmation dialog */}
            {pendingResult.prompt && (
              <details className="group">
                <summary className="text-[10px] text-zinc-600 cursor-pointer hover:text-zinc-400 transition-colors">
                  {locale === "zh" ? "查看 AI 提示词" : "View AI Prompt"}
                </summary>
                <pre className="mt-2 bg-zinc-950 rounded-lg p-3 text-[10px] text-zinc-500 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap font-mono leading-relaxed">
                  {pendingResult.prompt}
                </pre>
              </details>
            )}

            {pendingResult.actions_planned === 0 && (
              <p className="text-sm text-zinc-400 text-center py-2">{t.noAction}</p>
            )}

            <div className="flex gap-3">
              <button onClick={() => setShowConfirm(false)}
                className={`${pendingResult.actions_planned > 0 ? "flex-1" : "w-full"} py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm rounded-lg transition-colors`}>
                {pendingResult.actions_planned > 0 ? t.cancel : "OK"}
              </button>
              {pendingResult.actions_planned > 0 && (
                <button onClick={confirmExecute} disabled={executing}
                  className="flex-1 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-sm rounded-lg font-bold transition-colors">
                  {executing ? "..." : t.confirm}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Last Result (no confirmation needed) */}
      {pendingResult && !showConfirm && (
        <Card className="bg-zinc-900 border-0">
          <CardContent className="pt-3 space-y-3">
            {pendingResult.analysis && (
              <div>
                <span className="text-[10px] text-zinc-500 block mb-1">{t.analysis}</span>
                <p className="text-xs text-zinc-300">{pendingResult.analysis}</p>
              </div>
            )}
            {pendingResult.error && (
              <p className="text-xs text-red-400">{pendingResult.error}</p>
            )}
            {pendingResult.actions_planned === 0 && !pendingResult.error && (
              <p className="text-xs text-zinc-500">{t.noAction}</p>
            )}
            {pendingResult.executions?.filter((e: AnyResult) => e.status !== "dry_run").map((ex: AnyResult, i: number) => (
              <div key={i} className="text-xs bg-zinc-800 rounded px-2 py-1 flex justify-between">
                <span className="text-zinc-300">
                  {ex.action?.type?.toUpperCase()} {ex.action?.symbol} {ex.action?.volume}
                </span>
                <span className={ex.result?.success ? "text-green-400" : "text-red-400"}>
                  {ex.result?.success ? "executed" : "failed"}
                </span>
              </div>
            ))}
            {pendingResult.next_review && (
              <p className="text-[10px] text-zinc-600">Next: {pendingResult.next_review}</p>
            )}

            {(pendingResult.prompt || pendingResult.system_prompt) && (
              <details className="group">
                <summary className="text-[10px] text-zinc-600 cursor-pointer hover:text-zinc-400 transition-colors">
                  {locale === "zh" ? "查看 AI 完整上下文" : "View Full AI Context"}
                </summary>
                <div className="mt-2 bg-zinc-950 rounded-lg p-3 max-h-64 overflow-y-auto border border-zinc-800 space-y-3">
                  {pendingResult.system_prompt && (
                    <div>
                      <span className="text-[10px] text-blue-400 font-bold block mb-1">System Prompt:</span>
                      <pre className="text-[10px] text-zinc-500 whitespace-pre-wrap font-mono leading-relaxed">{pendingResult.system_prompt}</pre>
                    </div>
                  )}
                  {pendingResult.prompt && (
                    <div>
                      <span className="text-[10px] text-green-400 font-bold block mb-1">User Prompt:</span>
                      <pre className="text-[10px] text-zinc-400 whitespace-pre-wrap font-mono leading-relaxed">{pendingResult.prompt}</pre>
                    </div>
                  )}
                </div>
              </details>
            )}
          </CardContent>
        </Card>
      )}

      {/* Active Sessions */}
      {sessions.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs text-zinc-500 uppercase">{t.log}</h3>
          {sessions.map((s: AnyResult) => (
            <div key={s.id} className="bg-zinc-900 rounded-lg px-4 py-2.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge className={s.status === "running" ? "bg-green-900 text-green-300 text-[10px]" : "bg-zinc-800 text-zinc-400 text-[10px]"}>
                  {s.status === "running" ? t.running : t.stopped}
                </Badge>
                <span className="text-sm text-white">{s.strategy_name}</span>
                <span className="text-xs text-zinc-600">{t.cycles}: {s.cycles}</span>
              </div>
              {s.status === "running" && (
                <button onClick={() => stopSession(s.id)} className="text-xs text-red-400 hover:text-red-300">{t.stop}</button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* History Logs */}
      <div className="space-y-2">
        <button onClick={() => { setShowHistory(!showHistory); if (!showHistory) fetchHistory(); }}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
          {showHistory
            ? (locale === "zh" ? "收起分析记录" : "Hide History")
            : (locale === "zh" ? `查看分析记录 (${historyLogs.length})` : `View History (${historyLogs.length})`)}
        </button>

        {showHistory && historyLogs.length > 0 && (
          <div className="space-y-2">
            {historyLogs.map((log: AnyResult) => (
              <div key={log.id} className="bg-zinc-900/50 rounded-lg px-4 py-2.5 space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-white font-medium">{log.strategy_name}</span>
                    <span className="text-[10px] text-zinc-500">{log.symbols}</span>
                    {log.actions_executed > 0 && (
                      <Badge className="bg-green-900 text-green-300 text-[10px]">
                        {log.actions_executed} {locale === "zh" ? "已执行" : "executed"}
                      </Badge>
                    )}
                    {log.actions_planned === 0 && (
                      <Badge className="bg-zinc-800 text-zinc-400 text-[10px]">
                        {locale === "zh" ? "无操作" : "no action"}
                      </Badge>
                    )}
                    {log.dry_run && log.actions_planned > 0 && log.actions_executed === 0 && (
                      <Badge className="bg-yellow-900 text-yellow-300 text-[10px]">
                        {locale === "zh" ? "未确认" : "not confirmed"}
                      </Badge>
                    )}
                  </div>
                  <span className="text-[10px] text-zinc-600">
                    {new Date(log.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="text-xs text-zinc-400 line-clamp-2">{log.analysis}</p>
              </div>
            ))}
          </div>
        )}

        {showHistory && historyLogs.length === 0 && (
          <p className="text-xs text-zinc-600">{locale === "zh" ? "暂无分析记录" : "No analysis history yet"}</p>
        )}
      </div>
    </div>
  );
}
