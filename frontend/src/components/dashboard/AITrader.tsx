"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/app/providers";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SymbolSelect } from "./SymbolSelect";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const INTERVALS = [
  { value: "1m", label: "1m" }, { value: "5m", label: "5m" },
  { value: "15m", label: "15m" }, { value: "1h", label: "1H" },
  { value: "4h", label: "4H" }, { value: "1d", label: "1D" },
];

const t_: Record<string, Record<string, string>> = {
  en: {
    title: "AI Auto Trading", strategy: "Strategy", newStrategy: "New",
    save: "Save", delete: "Delete", symbols: "Symbols", rules: "Rules",
    analyze: "AI Analyze", analyzing: "Analyzing...", startAuto: "Auto",
    stop: "Stop", running: "Running", cycles: "Cycles",
    confirm: "Confirm Execute", cancel: "Cancel", noAction: "No action needed",
    proposed: "AI Trading Decision", analysis: "Analysis", history: "History",
    context: "Full AI Context", systemPrompt: "System Prompt", userPrompt: "User Prompt",
    saved: "Saved", selectStrategy: "Select strategy...",
    placeholder: "Enter trading strategy, e.g.:\n• Buy on golden cross, sell on death cross\n• Buy when RSI < 30, sell when RSI > 70",
  },
  zh: {
    title: "AI 自动交易", strategy: "策略", newStrategy: "新建",
    save: "保存", delete: "删除", symbols: "品种", rules: "规则",
    analyze: "AI 分析", analyzing: "分析中...", startAuto: "自动",
    stop: "停止", running: "运行中", cycles: "次数",
    confirm: "确认执行", cancel: "取消", noAction: "当前无需操作",
    proposed: "AI 交易决策", analysis: "分析结论", history: "历史记录",
    context: "AI 完整上下文", systemPrompt: "系统提示词", userPrompt: "用户提示词",
    saved: "已保存", selectStrategy: "选择策略...",
    placeholder: "输入交易策略，例如：\n• 均线金叉做多，死叉做空\n• RSI低于30买入，高于70卖出",
  },
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;

export function AITrader({ firmName, accountSize, evaluationType, symbol }: {
  firmName: string; accountSize: number; evaluationType?: string; symbol?: string;
}) {
  const { locale } = useI18n();
  const { token } = useAuth();
  const t = t_[locale] || t_.en;

  // Strategy state
  const [strategies, setStrategies] = useState<Any[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [strategyName, setStrategyName] = useState("MA Crossover");
  const [symbols, setSymbols] = useState(symbol || "EURUSD");
  const [rules, setRules] = useState("SMA10和SMA20，金叉做多，死叉做空\n首单0.01手，1.1倍加仓\n单向最多5单");
  const [interval, setInterval_] = useState("1h");
  const [loading, setLoading] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  // Results
  const [pendingResult, setPendingResult] = useState<Any>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [sessions, setSessions] = useState<Any[]>([]);
  const [historyLogs, setHistoryLogs] = useState<Any[]>([]);
  const [showHistory, setShowHistory] = useState(true);

  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  // Sync symbol from parent
  useEffect(() => {
    if (symbol && symbol !== symbols) setSymbols(symbol);
  }, [symbol]);

  // Load strategies
  const fetchStrategies = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/strategies`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) { const d = await res.json(); setStrategies(d.strategies || []); }
    } catch { /* silent */ }
  }, [token]);

  const fetchSessions = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/sessions`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) { const d = await res.json(); setSessions(d.sessions || []); }
    } catch { /* silent */ }
  }, [token]);

  const fetchHistory = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/logs?limit=10`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) { const d = await res.json(); setHistoryLogs(d.logs || []); }
    } catch { /* silent */ }
  }, [token]);

  useEffect(() => {
    fetchStrategies();
    fetchSessions();
    fetchHistory();
    const i = setInterval(fetchSessions, 30000); // 30s
    return () => clearInterval(i);
  }, [fetchStrategies, fetchSessions, fetchHistory]);

  // Strategy CRUD
  const selectStrategy = (s: Any) => {
    setSelectedId(s.id);
    setStrategyName(s.name);
    setSymbols(s.symbols || "");
    setRules(s.rules || "");
    if (s.kline_period) setInterval_(s.kline_period);
  };

  const saveStrategy = async () => {
    const body = { name: strategyName, symbols, kline_period: interval, rules };
    const url = selectedId ? `${API_BASE}/api/strategies/${selectedId}` : `${API_BASE}/api/strategies`;
    const method = selectedId ? "PUT" : "POST";
    const res = await fetch(url, { method, headers, body: JSON.stringify(body) });
    if (res.ok) {
      setSaveMsg(t.saved);
      setTimeout(() => setSaveMsg(""), 2000);
      fetchStrategies();
      const d = await res.json();
      if (d.strategy?.id) setSelectedId(d.strategy.id);
    }
  };

  const deleteStrategy = async () => {
    if (!selectedId) return;
    await fetch(`${API_BASE}/api/strategies/${selectedId}`, { method: "DELETE", headers });
    setSelectedId(null);
    setStrategyName("");
    setRules("");
    fetchStrategies();
  };

  const newStrategy = () => {
    setSelectedId(null);
    setStrategyName("");
    setSymbols(symbol || "EURUSD");
    setRules("");
  };

  const buildStrategy = () => ({
    name: strategyName || "unnamed",
    symbols: symbols.split(",").map((s: string) => s.trim()).filter(Boolean),
    kline_period: interval,
    rules: rules.split("\n").filter((r: string) => r.trim()),
  });

  // AI Analyze
  const analyzeAndPropose = async () => {
    setLoading(true);
    setPendingResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/analyze`, {
        method: "POST", headers,
        body: JSON.stringify({
          strategy: buildStrategy(), firm_name: firmName,
          account_size: accountSize, evaluation_type: evaluationType, dry_run: true,
        }),
      });
      const data = await res.json();
      setPendingResult(data);
      if (!data.error) setShowConfirm(true);
      fetchHistory();
    } catch { setPendingResult({ error: "Network error" }); }
    finally { setLoading(false); }
  };

  const confirmExecute = async () => {
    if (!pendingResult?.executions?.length) return;
    setExecuting(true);
    try {
      // Extract actions from dry run result and execute directly
      const actions = pendingResult.executions.map((e: Any) => e.action).filter(Boolean);
      const res = await fetch(`${API_BASE}/api/ai-trade/execute`, {
        method: "POST", headers,
        body: JSON.stringify({ actions }),
      });
      const data = await res.json();
      setPendingResult({
        ...pendingResult,
        dry_run: false,
        actions_executed: data.actions_executed,
        executions: data.executions,
      });
      setShowConfirm(false);
      fetchHistory();
    } catch { setPendingResult({ error: "Execution failed" }); }
    finally { setExecuting(false); }
  };

  const startAuto = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/ai-trade/start`, {
        method: "POST", headers,
        body: JSON.stringify({
          strategy: buildStrategy(), interval, firm_name: firmName,
          account_size: accountSize, evaluation_type: evaluationType, dry_run: false,
        }),
      });
      if ((await res.json()).started) fetchSessions();
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  const stopSession = async (id: string) => {
    await fetch(`${API_BASE}/api/ai-trade/stop/${id}`, { method: "POST", headers });
    fetchSessions();
  };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">{t.title}</h2>

      {/* Strategy Editor */}
      <Card className="bg-zinc-900 border-0">
        <CardContent className="pt-4 space-y-3">
          {/* Strategy selector + actions */}
          <div className="flex items-center gap-2">
            <select
              value={selectedId || ""}
              onChange={(e) => {
                const s = strategies.find((s: Any) => s.id === e.target.value);
                if (s) selectStrategy(s);
              }}
              className="flex-1 bg-zinc-800 text-white text-sm rounded px-2 py-1.5 focus:outline-none"
            >
              <option value="">{t.selectStrategy}</option>
              {strategies.map((s: Any) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            <button onClick={newStrategy} className="px-2 py-1.5 bg-zinc-800 text-zinc-400 text-xs rounded hover:text-white transition-colors">{t.newStrategy}</button>
            <button onClick={saveStrategy} className="px-2 py-1.5 bg-blue-900 text-blue-300 text-xs rounded hover:bg-blue-800 transition-colors">{t.save}</button>
            {selectedId && (
              <button onClick={deleteStrategy} className="px-2 py-1.5 text-xs text-zinc-600 hover:text-red-400 transition-colors">{t.delete}</button>
            )}
            {saveMsg && <span className="text-xs text-green-400">{saveMsg}</span>}
          </div>

          {/* Name + Symbols */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">{t.strategy}</label>
              <input value={strategyName} onChange={(e) => setStrategyName(e.target.value)}
                className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none" />
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">{t.symbols}</label>
              <SymbolSelect
                value={symbols.split(",")[0]?.trim() || "EURUSD"}
                onChange={(s) => setSymbols(s)}
                firmName={firmName}
                className="w-full"
              />
            </div>
          </div>

          {/* Rules */}
          <div>
            <label className="text-[10px] text-zinc-500 block mb-1">{t.rules}</label>
            <textarea value={rules} onChange={(e) => setRules(e.target.value)} rows={4}
              placeholder={t.placeholder}
              className="w-full bg-zinc-800 text-white rounded px-3 py-2 text-xs font-mono resize-none focus:outline-none leading-relaxed placeholder-zinc-600" />
          </div>

          {/* Actions */}
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
                {INTERVALS.map((iv) => <option key={iv.value} value={iv.value}>{iv.label}</option>)}
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
          <div className="bg-zinc-900 rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6 space-y-4">
            <h3 className="text-lg font-bold text-white">{t.proposed}</h3>

            {/* AI Context */}
            {(pendingResult.prompt || pendingResult.system_prompt) && (
              <details className="group">
                <summary className="text-[10px] text-zinc-500 cursor-pointer hover:text-zinc-300">{t.context}</summary>
                <div className="mt-2 bg-zinc-950 rounded-lg p-3 max-h-48 overflow-y-auto border border-zinc-800 space-y-2">
                  {pendingResult.system_prompt && (
                    <div>
                      <span className="text-[10px] text-blue-400 font-bold block mb-1">{t.systemPrompt}:</span>
                      <pre className="text-[10px] text-zinc-500 whitespace-pre-wrap font-mono">{pendingResult.system_prompt}</pre>
                    </div>
                  )}
                  {pendingResult.prompt && (
                    <div>
                      <span className="text-[10px] text-green-400 font-bold block mb-1">{t.userPrompt}:</span>
                      <pre className="text-[10px] text-zinc-400 whitespace-pre-wrap font-mono">{pendingResult.prompt}</pre>
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Analysis */}
            {pendingResult.analysis && (
              <div className="bg-zinc-800 rounded-lg p-3">
                <span className="text-[10px] text-zinc-500 block mb-1">{t.analysis}</span>
                <p className="text-sm text-zinc-300">{pendingResult.analysis}</p>
              </div>
            )}

            {/* Actions */}
            {pendingResult.executions?.map((ex: Any, i: number) => (
              <div key={i} className="bg-zinc-800 rounded-lg p-3">
                <span className={`text-sm font-bold ${ex.action?.type === "buy" ? "text-green-400" : ex.action?.type === "sell" ? "text-red-400" : "text-blue-400"}`}>
                  {ex.action?.type?.toUpperCase()}
                </span>
                <span className="text-sm text-white ml-2">{ex.action?.symbol}</span>
                <span className="text-xs text-zinc-400 ml-2">{ex.action?.volume} lots</span>
                {ex.action?.reason && <p className="text-xs text-zinc-500 mt-1">{ex.action.reason}</p>}
              </div>
            ))}

            {pendingResult.actions_planned === 0 && <p className="text-sm text-zinc-400 text-center py-2">{t.noAction}</p>}

            <div className="flex gap-3">
              <button onClick={() => setShowConfirm(false)}
                className={`${pendingResult.actions_planned > 0 ? "flex-1" : "w-full"} py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm rounded-lg`}>
                {pendingResult.actions_planned > 0 ? t.cancel : "OK"}
              </button>
              {pendingResult.actions_planned > 0 && (
                <button onClick={confirmExecute} disabled={executing}
                  className="flex-1 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-sm rounded-lg font-bold">
                  {executing ? "..." : t.confirm}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Result card (after dialog closed) */}
      {pendingResult && !showConfirm && (
        <Card className="bg-zinc-900 border-0">
          <CardContent className="pt-3 space-y-2">
            {pendingResult.analysis && <p className="text-xs text-zinc-300">{pendingResult.analysis}</p>}
            {pendingResult.error && <p className="text-xs text-red-400">{pendingResult.error}</p>}
            {pendingResult.actions_planned === 0 && !pendingResult.error && <p className="text-xs text-zinc-500">{t.noAction}</p>}
            {pendingResult.executions?.filter((e: Any) => e.status !== "dry_run").map((ex: Any, i: number) => (
              <div key={i} className="text-xs bg-zinc-800 rounded px-2 py-1 flex justify-between">
                <span className="text-zinc-300">{ex.action?.type?.toUpperCase()} {ex.action?.symbol} {ex.action?.volume}</span>
                <span className={ex.result?.success ? "text-green-400" : "text-red-400"}>{ex.result?.success ? "executed" : "failed"}</span>
              </div>
            ))}
            {(pendingResult.prompt || pendingResult.system_prompt) && (
              <details>
                <summary className="text-[10px] text-zinc-600 cursor-pointer hover:text-zinc-400">{t.context}</summary>
                <div className="mt-2 bg-zinc-950 rounded-lg p-3 max-h-48 overflow-y-auto border border-zinc-800 space-y-2">
                  {pendingResult.system_prompt && <div><span className="text-[10px] text-blue-400 font-bold block mb-1">{t.systemPrompt}:</span><pre className="text-[10px] text-zinc-500 whitespace-pre-wrap font-mono">{pendingResult.system_prompt}</pre></div>}
                  {pendingResult.prompt && <div><span className="text-[10px] text-green-400 font-bold block mb-1">{t.userPrompt}:</span><pre className="text-[10px] text-zinc-400 whitespace-pre-wrap font-mono">{pendingResult.prompt}</pre></div>}
                </div>
              </details>
            )}
          </CardContent>
        </Card>
      )}

      {/* Active Sessions */}
      {sessions.length > 0 && sessions.map((s: Any) => (
        <div key={s.id} className="bg-zinc-900 rounded-lg px-4 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Badge className={s.status === "running" ? "bg-green-900 text-green-300 text-[10px]" : "bg-zinc-800 text-zinc-400 text-[10px]"}>
              {s.status === "running" ? t.running : t.stop}
            </Badge>
            <span className="text-sm text-white">{s.strategy_name}</span>
            <span className="text-xs text-zinc-600">{t.cycles}: {s.cycles}</span>
          </div>
          {s.status === "running" && (
            <button onClick={() => stopSession(s.id)} className="text-xs text-red-400 hover:text-red-300">{t.stop}</button>
          )}
        </div>
      ))}

      {/* History */}
      {historyLogs.length > 0 && (
        <details open={showHistory} onToggle={(e) => setShowHistory((e.target as HTMLDetailsElement).open)}>
          <summary className="text-xs text-zinc-500 cursor-pointer hover:text-zinc-300">{t.history} ({historyLogs.length})</summary>
          <div className="mt-2 space-y-2">
            {historyLogs.map((log: Any) => (
              <div key={log.id} className="bg-zinc-900/50 rounded-lg px-4 py-2 space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-white">{log.strategy_name}</span>
                    <span className="text-[10px] text-zinc-500">{log.symbols}</span>
                    {log.actions_executed > 0 && <Badge className="bg-green-900 text-green-300 text-[10px]">{log.actions_executed} executed</Badge>}
                    {log.actions_planned === 0 && <Badge className="bg-zinc-800 text-zinc-400 text-[10px]">no action</Badge>}
                  </div>
                  <span className="text-[10px] text-zinc-600">{new Date(log.created_at).toLocaleString()}</span>
                </div>
                <p className="text-xs text-zinc-400 line-clamp-2">{log.analysis}</p>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
