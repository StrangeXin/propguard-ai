"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/app/providers";
import { useLoginGate } from "@/hooks/useLoginGate";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Position {
  id: string;
  symbol: string;
  side: string;
  volume: number;
  entry_price: number;
  current_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  profit: number;
  opened_at?: string | null;
  user_label?: string | null;
}

interface PendingOrder {
  id: string;
  symbol: string;
  type: string;
  volume: number;
  price: number;
  stop_loss: number | null;
  take_profit: number | null;
  created_at?: string | null;
  user_label?: string | null;
}

interface TradeRecord {
  id?: string;
  symbol: string;
  side: string;
  volume: number;
  price: number;
  profit: number;
  time?: string | null;
  user_label?: string | null;
}

interface AccountData {
  balance: number;
  equity: number;
  pnl: number;
  pnl_pct: number;
  open_positions: number;
  positions: Position[];
}

interface SymbolPrice {
  bid: number;
  ask: number;
  spread: number;
  digits?: number;
}

interface SymbolSpec {
  min_volume: number;
  max_volume: number;
  volume_step: number;
}

import { SymbolSelect } from "./SymbolSelect";

const texts: Record<string, Record<string, string>> = {
  en: {
    title: "Trading",
    market: "Market",
    pending: "Pending",
    balance: "Balance",
    equity: "Equity",
    margin: "Free Margin",
    pnl: "P&L",
    symbol: "Symbol",
    size: "Lots",
    sl: "Stop Loss",
    tp: "Take Profit",
    price: "Price",
    buy: "BUY",
    sell: "SELL",
    limit: "Limit",
    stop: "Stop",
    place: "Place Order",
    positions: "Open Positions",
    pendingOrders: "Pending Orders",
    history: "Trade History",
    close: "Close",
    closing: "Closing…",
    partial: "Partial",
    modify: "Modify",
    cancel: "Cancel",
    cancelling: "Cancelling…",
    processing: "processing",
    placing: "Placing…",
    symbolUnavailable: "This symbol is not available on the demo account.",
    noPositions: "No open positions",
    noOrders: "No pending orders",
    noHistory: "No trade history",
    bid: "Bid",
    ask: "Ask",
    spread: "Spread",
    trades: "Trades",
    winRate: "Win Rate",
    save: "Save",
  },
  zh: {
    title: "交易",
    market: "市价",
    pending: "挂单",
    balance: "余额",
    equity: "净值",
    margin: "可用保证金",
    pnl: "盈亏",
    symbol: "品种",
    size: "手数",
    sl: "止损",
    tp: "止盈",
    price: "价格",
    buy: "买入",
    sell: "卖出",
    limit: "限价",
    stop: "止损",
    place: "下单",
    positions: "持仓",
    pendingOrders: "挂单",
    history: "交易记录",
    close: "平仓",
    closing: "平仓中…",
    partial: "部分",
    modify: "修改",
    cancel: "取消",
    cancelling: "撤单中…",
    processing: "处理中",
    placing: "下单中…",
    symbolUnavailable: "当前账号不支持该品种",
    noPositions: "暂无持仓",
    noOrders: "暂无挂单",
    noHistory: "暂无交易记录",
    bid: "买价",
    ask: "卖价",
    spread: "点差",
    trades: "交易数",
    winRate: "胜率",
    save: "保存",
  },
};

export function TradingPanel({ symbol: externalSymbol, onSymbolChange }: { symbol?: string; onSymbolChange?: (s: string) => void } = {}) {
  const { locale, t: ti18n } = useI18n();
  const { token, logout } = useAuth();
  const { openGate } = useLoginGate();
  const t = texts[locale] || texts.en;

  const [tab, setTab] = useState<"order" | "positions" | "orders" | "history">("order");
  const [orderType, setOrderType] = useState<"market" | "limit" | "stop">("market");
  const [account, setAccount] = useState<AccountData | null>(null);
  const [accountInfo, setAccountInfo] = useState<{ free_margin: number; leverage: number } | null>(null);
  const [pendingOrders, setPendingOrders] = useState<PendingOrder[]>([]);
  const [tradeHistory, setTradeHistory] = useState<TradeRecord[]>([]);
  const [historyStats, setHistoryStats] = useState<{ total_trades: number; win_rate: number; total_pnl: number }>({ total_trades: 0, win_rate: 0, total_pnl: 0 });
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(20);
  const [historyTotalPages, setHistoryTotalPages] = useState(1);
  const [symbolPrice, setSymbolPrice] = useState<SymbolPrice | null>(null);
  const [symbolSpec, setSymbolSpec] = useState<SymbolSpec | null>(null);

  // Called when a mutating request comes back 401 — token either expired or
  // the server rotated secrets. Clear the stored token, drop user state, and
  // re-open the login modal so the user can re-auth without seeing the dead
  // "Authentication required" toast.
  const handleAuthExpired = () => {
    logout();
    openGate(ti18n("auth.session_expired"));
  };

  const [symbol, setSymbolLocal] = useState(externalSymbol || "EURUSD");

  useEffect(() => {
    if (externalSymbol && externalSymbol !== symbol) {
      setSymbolLocal(externalSymbol);
    }
  }, [externalSymbol]);

  const setSymbol = (s: string) => {
    setSymbolLocal(s);
    onSymbolChange?.(s);
  };
  const [size, setSize] = useState("0.01");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [loading, setLoading] = useState(false);
  type Toast = { kind: "success" | "error"; text: string } | null;
  const [msg, setMsgRaw] = useState<Toast>(null);
  // Keep the "setMsg" name for backwards compat with existing call sites.
  const setMsg = (v: string | Toast) => {
    if (v === null || v === "") { setMsgRaw(null); return; }
    if (typeof v === "string") {
      // Heuristic: strings that contain 'fail', 'error', '网络' are errors.
      const lower = v.toLowerCase();
      const isErr = /fail|error|invalid|\u7f51\u7edc|\u5931\u8d25/i.test(lower + v);
      setMsgRaw({ kind: isErr ? "error" : "success", text: v });
    } else {
      setMsgRaw(v);
    }
    // Auto-clear success toasts after 4s; keep errors until the next action.
    if (typeof v !== "string" ? v?.kind === "success" : !/fail|error|invalid|\u7f51\u7edc|\u5931\u8d25/i.test(v)) {
      setTimeout(() => setMsgRaw((cur) => (cur && cur.kind === "success" && cur.text === (typeof v === "string" ? v : v.text) ? null : cur)), 4000);
    }
  };

  // Modify SL/TP state
  const [editingPos, setEditingPos] = useState<string | null>(null);
  const [editSl, setEditSl] = useState("");
  const [editTp, setEditTp] = useState("");
  // Partial close state
  const [partialPos, setPartialPos] = useState<string | null>(null);
  const [partialVol, setPartialVol] = useState("");

  const authHeaders: Record<string, string> = { "Content-Type": "application/json" };
  if (token) authHeaders.Authorization = `Bearer ${token}`;
  const headers = authHeaders;

  const readHeaders: Record<string, string> = {};
  if (token) readHeaders.Authorization = `Bearer ${token}`;

  // Fetch account + positions (anon allowed — routes to shared public account)
  const fetchAccount = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/trading/account`, {
        headers: readHeaders,
        credentials: "include",
      });
      if (res.ok) setAccount(await res.json());
    } catch { /* silent */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Fetch account info (margin, leverage) — anon allowed
  const fetchAccountInfo = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/trading/account-info`, {
        headers: readHeaders,
        credentials: "include",
      });
      if (res.ok) setAccountInfo(await res.json());
    } catch { /* silent */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const [symbolUnavailable, setSymbolUnavailable] = useState(false);

  // Fetch symbol price + spec. Sets unavailable=true when MetaApi returns
  // {price: null} so we can disable the order buttons instead of silently
  // letting the user submit with a stale price from a previous symbol.
  const fetchPrice = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/trading/symbol/${symbol}`);
      if (res.ok) {
        const data = await res.json();
        if (data.price) {
          setSymbolPrice({ ...data.price, digits: data.spec?.digits });
          if (data.spec) {
            const spec: SymbolSpec = {
              min_volume: Number(data.spec.min_volume) || 0.01,
              max_volume: Number(data.spec.max_volume) || 100,
              volume_step: Number(data.spec.volume_step) || 0.01,
            };
            setSymbolSpec((prev) => {
              // First load for this symbol, or volume_step changed → snap
              // the size input to a valid value so the user can't submit an
              // off-step volume (e.g. US500 needs step 0.1, not default 0.01).
              if (!prev || prev.volume_step !== spec.volume_step || prev.min_volume !== spec.min_volume) {
                setSize(String(spec.min_volume));
              }
              return spec;
            });
          }
          setSymbolUnavailable(false);
        } else {
          setSymbolPrice(null);
          setSymbolSpec(null);
          setSymbolUnavailable(true);
        }
      } else {
        setSymbolPrice(null);
        setSymbolSpec(null);
        setSymbolUnavailable(true);
      }
    } catch {
      setSymbolPrice(null);
    }
  }, [symbol]);

  // Fetch pending orders (anon allowed)
  const fetchOrders = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/trading/orders`, {
        headers: readHeaders,
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setPendingOrders(data.orders || []);
      }
    } catch { /* silent */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Fetch trade history (anon allowed)
  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/trading/history?days=30&page=${historyPage}&page_size=${historyPageSize}`,
        { headers: readHeaders, credentials: "include" },
      );
      if (res.ok) {
        const data = await res.json();
        setTradeHistory(data.trades || []);
        setHistoryStats(data.stats || { total_trades: 0, win_rate: 0, total_pnl: 0 });
        setHistoryTotalPages(data.pagination?.total_pages ?? 1);
      }
    } catch { /* silent */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, historyPage, historyPageSize]);

  useEffect(() => {
    fetchAccount();
    fetchAccountInfo();
    // Account polling at 30s — the compliance hook (useCompliance) polls
    // every 10s AND keeps a WebSocket for live updates, so account/positions
    // data is kept fresh by that channel. This interval exists as a belt-
    // and-suspenders refresh in case WS drops; making it too aggressive just
    // spams /api/trading/account (which goes to MetaApi and can be slow).
    const i1 = setInterval(fetchAccount, 30000);
    return () => clearInterval(i1);
  }, [fetchAccount, fetchAccountInfo]);

  useEffect(() => {
    // Symbol changed — clear price + per-symbol inputs. Stale SL/TP/limit
    // from a different-magnitude symbol (BTC vs EURUSD) would otherwise
    // produce garbage orders on submit.
    setSymbolPrice(null);
    setSymbolUnavailable(false);
    setSl("");
    setTp("");
    setLimitPrice("");
    setMsg(null);
    fetchPrice();
    // Price poll at 5s — fast enough to keep the BUY/SELL ladder fresh, slow
    // enough that MetaApi / TwelveData rate-limits don't push back.
    const i2 = setInterval(fetchPrice, 5000);
    return () => clearInterval(i2);
  }, [fetchPrice]);

  useEffect(() => {
    if (tab === "orders") fetchOrders();
    if (tab === "history") fetchHistory();
  }, [tab, fetchOrders, fetchHistory]);

  // Place order
  const submitOrder = async (side: string) => {
    if (!token) {
      openGate(ti18n("auth.login_to_place_order"));
      return;
    }
    // Pre-submit volume validation — catch off-step / out-of-range before
    // wasting a broker round-trip ("Invalid volume in the request").
    const vol = parseFloat(size);
    if (symbolSpec) {
      const { min_volume, max_volume, volume_step } = symbolSpec;
      if (isNaN(vol) || vol < min_volume || vol > max_volume) {
        setMsg({ kind: "error", text: `Size must be between ${min_volume} and ${max_volume}` });
        return;
      }
      // Check multiples of volume_step with an epsilon for float imprecision.
      const ratio = (vol - min_volume) / volume_step;
      if (Math.abs(ratio - Math.round(ratio)) > 1e-6) {
        setMsg({ kind: "error", text: `Size must be a multiple of ${volume_step}` });
        return;
      }
    }
    setLoading(true);
    setMsg(null);
    try {
      const url = orderType === "market" ? `${API_BASE}/api/trading/order` : `${API_BASE}/api/trading/pending-order`;
      const body: Record<string, unknown> = {
        symbol,
        side,
        size: vol,
        stop_loss: sl ? parseFloat(sl) : null,
        take_profit: tp ? parseFloat(tp) : null,
      };
      if (orderType !== "market") {
        body.price = parseFloat(limitPrice);
        body.order_type = orderType;
      }

      const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
      if (res.status === 401) {
        handleAuthExpired();
        return;
      }
      const data = await res.json();
      if (res.ok && data.success) {
        setMsg({
          kind: "success",
          text: `${side.toUpperCase()} ${symbol} ${size} — #${data.order_id || "OK"}`,
        });
        setSl(""); setTp(""); setLimitPrice("");
        fetchAccount();
        fetchOrders();
      } else {
        const raw = String(data.error || data.detail || "Order failed");
        setMsg({ kind: "error", text: humanizeBrokerError(raw, vol) });
      }
    } catch {
      setMsg({ kind: "error", text: "Network error" });
    } finally {
      setLoading(false);
    }
  };

  // Track in-flight position/order mutations so the UI can disable buttons
  // and fade out the row during the MetaApi round-trip (0.5–2s typical).
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const markBusy = (id: string, busy: boolean) => {
    setBusyIds((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id); else next.delete(id);
      return next;
    });
  };

  // Close position — row shows a "closing" state during the MetaApi
  // round-trip. On confirmed success we remove it from local state
  // immediately (no flash where the busy state clears before refetch
  // catches up), then refetch in the background to reconcile.
  const closePos = async (posId: string) => {
    if (!token) { openGate(ti18n("auth.login_to_place_order")); return; }
    markBusy(posId, true);
    let ok = false;
    try {
      const res = await fetch(`${API_BASE}/api/trading/position/${posId}/close`, { method: "POST", headers });
      if (res.status === 401) { handleAuthExpired(); markBusy(posId, false); return; }
      ok = res.ok;
      if (!ok) setMsg("Close failed");
    } catch {
      setMsg("Network error");
    }
    if (ok && account) {
      setAccount({ ...account, positions: account.positions.filter((p) => p.id !== posId) });
    }
    markBusy(posId, false);
    fetchAccount();
  };

  const partialClose = async (posId: string) => {
    if (!token) { openGate(ti18n("auth.login_to_place_order")); return; }
    if (!partialVol) return;
    markBusy(posId, true);
    try {
      const res = await fetch(`${API_BASE}/api/trading/position/${posId}/close-partial?volume=${parseFloat(partialVol)}`, { method: "POST", headers });
      if (res.status === 401) { handleAuthExpired(); return; }
    } finally {
      markBusy(posId, false);
      setPartialPos(null);
      setPartialVol("");
      fetchAccount();
    }
  };

  const modifyPos = async (posId: string) => {
    if (!token) { openGate(ti18n("auth.login_to_place_order")); return; }
    markBusy(posId, true);
    try {
      const res = await fetch(`${API_BASE}/api/trading/position/${posId}/modify`, {
        method: "POST", headers,
        body: JSON.stringify({
          stop_loss: editSl ? parseFloat(editSl) : null,
          take_profit: editTp ? parseFloat(editTp) : null,
        }),
      });
      if (res.status === 401) { handleAuthExpired(); return; }
    } finally {
      markBusy(posId, false);
      setEditingPos(null);
      fetchAccount();
    }
  };

  const cancelOrder = async (orderId: string) => {
    if (!token) { openGate(ti18n("auth.login_to_place_order")); return; }
    markBusy(orderId, true);
    let ok = false;
    try {
      const res = await fetch(`${API_BASE}/api/trading/order/${orderId}/cancel`, { method: "POST", headers });
      if (res.status === 401) { handleAuthExpired(); markBusy(orderId, false); return; }
      ok = res.ok;
      if (!ok) setMsg("Cancel failed");
    } catch {
      setMsg("Network error");
    }
    if (ok) {
      setPendingOrders((prev) => prev.filter((o) => o.id !== orderId));
    }
    markBusy(orderId, false);
    fetchOrders();
  };

  const pnlColor = (v: number) => v >= 0 ? "text-green-400" : "text-red-400";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">{t.title}</h2>
        <Badge className="bg-zinc-800 text-zinc-500 text-[10px]">MT5 Demo</Badge>
      </div>

      {/* Account stats */}
      {account && (
        <div className="grid grid-cols-4 gap-3">
          <Stat label={t.balance} value={`$${account.balance.toLocaleString("en", { minimumFractionDigits: 2 })}`} />
          <Stat label={t.equity} value={`$${account.equity.toLocaleString("en", { minimumFractionDigits: 2 })}`} />
          <Stat label={t.margin} value={accountInfo ? `$${accountInfo.free_margin.toLocaleString("en", { minimumFractionDigits: 2 })}` : "—"} />
          <Stat label={t.pnl} value={`${account.pnl >= 0 ? "+" : ""}$${account.pnl.toFixed(2)}`} color={pnlColor(account.pnl)} />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-zinc-900 rounded-lg p-1">
        {(["order", "positions", "orders", "history"] as const).map((key) => {
          const labels = { order: t.place, positions: t.positions, orders: t.pendingOrders, history: t.history };
          const counts = { order: "", positions: account ? `(${account.open_positions})` : "", orders: `(${pendingOrders.length})`, history: "" };
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex-1 py-1.5 text-xs rounded-md transition-colors ${tab === key ? "bg-zinc-700 text-white" : "text-zinc-500 hover:text-zinc-300"}`}
            >
              {labels[key]} {counts[key]}
            </button>
          );
        })}
      </div>

      {/* Order Form */}
      {tab === "order" && (
        <Card className="bg-zinc-900 border-0">
          <CardContent className="pt-4 space-y-3">
            {/* Order type toggle */}
            <div className="flex gap-1 bg-zinc-800 rounded p-0.5">
              {(["market", "limit", "stop"] as const).map((ot) => (
                <button key={ot} onClick={() => setOrderType(ot)}
                  className={`flex-1 py-1 text-xs rounded transition-colors ${orderType === ot ? "bg-zinc-600 text-white" : "text-zinc-500"}`}>
                  {ot === "market" ? t.market : ot === "limit" ? t.limit : t.stop}
                </button>
              ))}
            </div>

            {/* Symbol */}
            <div className="flex items-center gap-3">
              <SymbolSelect value={symbol} onChange={setSymbol} />
            </div>

            {/* Inputs */}
            <div className={`grid ${orderType === "market" ? "grid-cols-3" : "grid-cols-4"} gap-2`}>
              <div>
                <label className="text-[10px] text-zinc-500 block mb-1">
                  {t.size}
                  {symbolSpec && (
                    <span className="text-zinc-600 ml-1">
                      ({symbolSpec.min_volume}–{symbolSpec.max_volume}, step {symbolSpec.volume_step})
                    </span>
                  )}
                </label>
                <input
                  type="number"
                  step={symbolSpec?.volume_step ?? 0.01}
                  min={symbolSpec?.min_volume ?? 0.01}
                  max={symbolSpec?.max_volume ?? 100}
                  value={size}
                  onChange={(e) => setSize(e.target.value)}
                  className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none"
                />
              </div>
              {orderType !== "market" && (
                <div>
                  <label className="text-[10px] text-zinc-500 block mb-1">{t.price}</label>
                  <input type="number" step="any" value={limitPrice} onChange={(e) => setLimitPrice(e.target.value)} placeholder={symbolPrice ? String(symbolPrice.bid) : ""} className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none placeholder-zinc-700" />
                </div>
              )}
              <div>
                <label className="text-[10px] text-zinc-500 block mb-1">{t.sl}</label>
                <input type="number" step="any" value={sl} onChange={(e) => setSl(e.target.value)} placeholder="—" className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none placeholder-zinc-700" />
              </div>
              <div>
                <label className="text-[10px] text-zinc-500 block mb-1">{t.tp}</label>
                <input type="number" step="any" value={tp} onChange={(e) => setTp(e.target.value)} placeholder="—" className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none placeholder-zinc-700" />
              </div>
            </div>

            {/* Sell (bid) | spread | Buy (ask) — MT5-style quote ladder */}
            {symbolUnavailable && (
              <div className="text-xs px-3 py-2 rounded bg-amber-900/30 border border-amber-800/50 text-amber-300">
                {t.symbolUnavailable}
              </div>
            )}
            <div className="flex items-stretch gap-0 rounded-lg overflow-hidden">
              <button onClick={() => submitOrder("sell")} disabled={loading || !symbolPrice}
                className="flex-1 py-3 bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white transition-colors flex flex-col items-center justify-center gap-0.5">
                {loading ? (
                  <span className="flex items-center gap-2 py-2">
                    <span className="inline-block w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                    <span className="text-sm font-bold">{t.placing}</span>
                  </span>
                ) : (
                  <>
                    <span className="text-[10px] uppercase tracking-wider opacity-80">{t.sell} · {t.bid}</span>
                    <span className="text-lg font-mono font-bold tabular-nums">{symbolPrice ? symbolPrice.bid : "—"}</span>
                  </>
                )}
              </button>
              <div className="flex flex-col items-center justify-center px-3 bg-zinc-800 text-zinc-400 min-w-[56px]">
                <span className="text-[9px] uppercase tracking-wider text-zinc-500">{t.spread}</span>
                <span className="text-xs font-mono tabular-nums">
                  {symbolPrice ? formatSpread(symbolPrice.spread, symbolPrice.digits) : "—"}
                </span>
              </div>
              <button onClick={() => submitOrder("buy")} disabled={loading || !symbolPrice}
                className="flex-1 py-3 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white transition-colors flex flex-col items-center justify-center gap-0.5">
                {loading ? (
                  <span className="flex items-center gap-2 py-2">
                    <span className="inline-block w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                    <span className="text-sm font-bold">{t.placing}</span>
                  </span>
                ) : (
                  <>
                    <span className="text-[10px] uppercase tracking-wider opacity-80">{t.buy} · {t.ask}</span>
                    <span className="text-lg font-mono font-bold tabular-nums">{symbolPrice ? symbolPrice.ask : "—"}</span>
                  </>
                )}
              </button>
            </div>
            {msg && (
              <div
                className={`text-xs px-3 py-2 rounded flex items-center gap-2 ${
                  msg.kind === "success"
                    ? "bg-green-900/30 border border-green-800/50 text-green-300"
                    : "bg-red-900/30 border border-red-800/50 text-red-300"
                }`}
              >
                <span>{msg.kind === "success" ? "✓" : "✗"}</span>
                <span className="flex-1">{msg.text}</span>
                <button onClick={() => setMsg(null)} className="text-[10px] opacity-60 hover:opacity-100">✕</button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Positions Tab */}
      {tab === "positions" && (
        <div className="space-y-2">
          {(!account || account.positions.length === 0) && (
            <div className="bg-zinc-900 rounded-lg p-6 text-center text-zinc-600 text-sm">{t.noPositions}</div>
          )}
          {account?.positions.map((p) => {
            const busy = busyIds.has(p.id);
            return (
            <div key={p.id} className={`bg-zinc-900 rounded-lg p-3 space-y-2 transition-opacity ${busy ? "opacity-60" : ""}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Badge className={p.side === "long" ? "bg-green-900 text-green-300 text-[10px]" : "bg-red-900 text-red-300 text-[10px]"}>{p.side.toUpperCase()}</Badge>
                  <span className="font-mono text-white text-sm">{p.symbol}</span>
                  <span className="text-xs text-zinc-500">{p.volume} lots @ {p.entry_price}</span>
                  {p.user_label && (
                    <span className="text-[10px] text-zinc-500 bg-zinc-800 rounded px-1.5 py-0.5 truncate max-w-[120px]">
                      {ti18n("positions.by")}: {p.user_label}
                    </span>
                  )}
                </div>
                <span className={`font-mono text-sm font-bold ${pnlColor(p.profit)}`}>
                  {p.profit >= 0 ? "+" : ""}${p.profit.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <span>SL: {p.stop_loss || "—"}</span>
                <span>TP: {p.take_profit || "—"}</span>
                <span>Now: {p.current_price}</span>
                {p.opened_at && (
                  <span className="ml-auto tabular-nums">{fmtShortTime(p.opened_at)}</span>
                )}
              </div>
              <div className="flex gap-2 items-center">
                <button onClick={() => closePos(p.id)} disabled={busy} className="px-3 py-1 bg-red-900/50 text-red-300 text-xs rounded hover:bg-red-900 disabled:opacity-50 transition-colors flex items-center gap-1.5">
                  {busy && <span className="inline-block w-3 h-3 border-2 border-red-300/40 border-t-red-300 rounded-full animate-spin" />}
                  {busy ? t.closing : t.close}
                </button>
                <button onClick={() => { setPartialPos(p.id); setPartialVol(String(p.volume / 2)); }} disabled={busy} className="px-3 py-1 bg-zinc-800 text-zinc-400 text-xs rounded hover:bg-zinc-700 disabled:opacity-50 transition-colors">{t.partial}</button>
                <button onClick={() => { setEditingPos(p.id); setEditSl(p.stop_loss ? String(p.stop_loss) : ""); setEditTp(p.take_profit ? String(p.take_profit) : ""); }} disabled={busy} className="px-3 py-1 bg-zinc-800 text-zinc-400 text-xs rounded hover:bg-zinc-700 disabled:opacity-50 transition-colors">{t.modify}</button>
                {busy && <span className="text-[10px] text-zinc-500 ml-1">{t.processing}</span>}
              </div>

              {/* Partial close form */}
              {partialPos === p.id && (
                <div className="flex gap-2 items-center bg-zinc-800 rounded p-2">
                  <input type="number" step="0.01" value={partialVol} onChange={(e) => setPartialVol(e.target.value)} className="w-20 bg-zinc-700 text-white rounded px-2 py-1 text-xs focus:outline-none" />
                  <span className="text-xs text-zinc-500">lots</span>
                  <button onClick={() => partialClose(p.id)} className="px-2 py-1 bg-red-800 text-white text-xs rounded">{t.close}</button>
                  <button onClick={() => setPartialPos(null)} className="text-xs text-zinc-500">{t.cancel}</button>
                </div>
              )}

              {/* Modify SL/TP form */}
              {editingPos === p.id && (
                <div className="flex gap-2 items-center bg-zinc-800 rounded p-2">
                  <input type="number" step="any" value={editSl} onChange={(e) => setEditSl(e.target.value)} placeholder="SL" className="w-24 bg-zinc-700 text-white rounded px-2 py-1 text-xs focus:outline-none placeholder-zinc-600" />
                  <input type="number" step="any" value={editTp} onChange={(e) => setEditTp(e.target.value)} placeholder="TP" className="w-24 bg-zinc-700 text-white rounded px-2 py-1 text-xs focus:outline-none placeholder-zinc-600" />
                  <button onClick={() => modifyPos(p.id)} className="px-2 py-1 bg-blue-800 text-white text-xs rounded">{t.save}</button>
                  <button onClick={() => setEditingPos(null)} className="text-xs text-zinc-500">{t.cancel}</button>
                </div>
              )}
            </div>
            );
          })}
        </div>
      )}

      {/* Pending Orders Tab */}
      {tab === "orders" && (
        <div className="space-y-2">
          {pendingOrders.length === 0 && (
            <div className="bg-zinc-900 rounded-lg p-6 text-center text-zinc-600 text-sm">{t.noOrders}</div>
          )}
          {pendingOrders.map((o) => {
            const busy = busyIds.has(o.id);
            return (
            <div key={o.id} className={`bg-zinc-900 rounded-lg px-4 py-2.5 flex items-center justify-between transition-opacity ${busy ? "opacity-50" : ""}`}>
              <div className="flex items-center gap-2 min-w-0">
                <Badge className="bg-yellow-900 text-yellow-300 text-[10px]">{o.type}</Badge>
                <span className="font-mono text-white text-sm">{o.symbol}</span>
                <span className="text-xs text-zinc-500">{o.volume} @ {o.price}</span>
                {o.user_label && (
                  <span className="text-[10px] text-zinc-500 bg-zinc-800 rounded px-1.5 py-0.5 truncate max-w-[120px]">
                    {ti18n("positions.by")}: {o.user_label}
                  </span>
                )}
                {o.created_at && (
                  <span className="text-[10px] text-zinc-600 tabular-nums ml-1">{fmtShortTime(o.created_at)}</span>
                )}
              </div>
              <button onClick={() => cancelOrder(o.id)} disabled={busy} className="text-xs text-zinc-500 hover:text-red-400 disabled:opacity-50 transition-colors flex items-center gap-1.5">
                {busy && <span className="inline-block w-3 h-3 border-2 border-zinc-500/40 border-t-zinc-300 rounded-full animate-spin" />}
                {busy ? t.cancelling : t.cancel}
              </button>
            </div>
            );
          })}
        </div>
      )}

      {/* History Tab */}
      {tab === "history" && (
        <div className="space-y-3">
          {/* Stats */}
          <div className="grid grid-cols-3 gap-3">
            <Stat label={t.trades} value={String(historyStats.total_trades)} />
            <Stat label={t.winRate} value={`${historyStats.win_rate}%`} />
            <Stat label={t.pnl} value={`$${historyStats.total_pnl.toFixed(2)}`} color={pnlColor(historyStats.total_pnl)} />
          </div>
          {tradeHistory.length === 0 && (
            <div className="bg-zinc-900 rounded-lg p-6 text-center text-zinc-600 text-sm">{t.noHistory}</div>
          )}
          {(() => {
            const showByColumn = tradeHistory.some((d) => d.user_label != null);
            const fmtTime = (iso?: string | null) => fmtShortTime(iso) || "—";
            return (
              <>
                {tradeHistory.map((trade, i) => (
                  <div key={`${trade.id ?? i}-${i}`} className="bg-zinc-900/50 rounded px-4 py-2 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-zinc-600 tabular-nums shrink-0">{fmtTime(trade.time)}</span>
                      <span className={trade.side === "buy" ? "text-green-500 shrink-0" : "text-red-500 shrink-0"}>{trade.side.toUpperCase()}</span>
                      <span className="text-zinc-300 shrink-0">{trade.symbol}</span>
                      <span className="text-zinc-600 shrink-0">{trade.volume} @ {trade.price}</span>
                      {showByColumn && (
                        <span className="text-zinc-500 truncate">{trade.user_label ?? "—"}</span>
                      )}
                    </div>
                    <span className={`font-mono font-bold shrink-0 ${pnlColor(trade.profit)}`}>
                      {trade.profit >= 0 ? "+" : ""}${trade.profit.toFixed(2)}
                    </span>
                  </div>
                ))}
                {historyStats.total_trades > 0 && (
                  <div className="pt-2 flex items-center justify-between text-xs text-zinc-500">
                    <div className="flex items-center gap-2">
                      <span>{locale === "zh" ? "每页" : "Per page"}</span>
                      <select
                        value={historyPageSize}
                        onChange={(e) => { setHistoryPageSize(Number(e.target.value)); setHistoryPage(1); }}
                        className="bg-zinc-800 text-zinc-300 rounded px-2 py-1 text-xs focus:outline-none"
                      >
                        {[10, 20, 50, 100].map((n) => (
                          <option key={n} value={n}>{n}</option>
                        ))}
                      </select>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
                        disabled={historyPage <= 1}
                        className="px-2 py-1 rounded bg-zinc-800 disabled:opacity-40 hover:bg-zinc-700 transition-colors"
                      >‹</button>
                      <span className="tabular-nums">
                        {historyPage} / {historyTotalPages}
                      </span>
                      <button
                        onClick={() => setHistoryPage((p) => Math.min(historyTotalPages, p + 1))}
                        disabled={historyPage >= historyTotalPages}
                        className="px-2 py-1 rounded bg-zinc-800 disabled:opacity-40 hover:bg-zinc-700 transition-colors"
                      >›</button>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}

function formatSpread(spread: number, digits?: number): string {
  // Convert to MT5-style "points" using the symbol's digit precision.
  //   EURUSD (5 digits): spread 0.00004 → 4.0 pts
  //   USDJPY (3 digits): spread 0.020   → 20.0 pts
  //   BTCUSD (2 digits): spread 3.00    → 300 pts (displayed as raw price diff,
  //                                       since "points" means nothing for crypto)
  if (digits == null) return spread.toFixed(5);
  if (digits >= 3) {
    const pts = spread * Math.pow(10, digits);
    return pts.toFixed(1);
  }
  // Low-digit instruments (crypto, indices): show raw price diff; "3" is more
  // meaningful than "300 pts" for BTC.
  return spread.toFixed(digits);
}

function humanizeBrokerError(raw: string, size: number): string {
  const s = raw.toLowerCase();
  if (s.includes("invalid volume")) {
    return `Broker rejected size ${size}. The account's per-order cap is usually lower than the spec's max_volume; try a smaller size.`;
  }
  if (s.includes("not enough money") || s.includes("no money")) {
    return "Insufficient free margin. Close some positions or reduce the size.";
  }
  if (s.includes("market is closed") || s.includes("off quotes")) {
    return "Market closed for this symbol right now. Try again during session hours.";
  }
  if (s.includes("invalid stops")) {
    return "Stop-loss / take-profit is too close to the current price or on the wrong side.";
  }
  if (s.includes("no price")) {
    return "No price feed for this symbol. Try a different one or refresh.";
  }
  return raw;
}

function fmtShortTime(iso?: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString([], {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function Stat({ label, value, color = "text-white" }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-3">
      <p className="text-[10px] text-zinc-500 uppercase">{label}</p>
      <p className={`text-sm font-mono font-bold ${color}`}>{value}</p>
    </div>
  );
}
