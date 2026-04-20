"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/app/providers";
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
}

interface PendingOrder {
  id: string;
  symbol: string;
  type: string;
  volume: number;
  price: number;
  stop_loss: number | null;
  take_profit: number | null;
}

interface TradeRecord {
  symbol: string;
  side: string;
  volume: number;
  price: number;
  profit: number;
  time: string;
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
    partial: "Partial",
    modify: "Modify",
    cancel: "Cancel",
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
    partial: "部分",
    modify: "修改",
    cancel: "取消",
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
  const { locale } = useI18n();
  const { token } = useAuth();
  const t = texts[locale] || texts.en;

  const [tab, setTab] = useState<"order" | "positions" | "orders" | "history">("order");
  const [orderType, setOrderType] = useState<"market" | "limit" | "stop">("market");
  const [account, setAccount] = useState<AccountData | null>(null);
  const [accountInfo, setAccountInfo] = useState<{ free_margin: number; leverage: number } | null>(null);
  const [pendingOrders, setPendingOrders] = useState<PendingOrder[]>([]);
  const [tradeHistory, setTradeHistory] = useState<TradeRecord[]>([]);
  const [historyStats, setHistoryStats] = useState<{ total_trades: number; win_rate: number; total_pnl: number }>({ total_trades: 0, win_rate: 0, total_pnl: 0 });
  const [symbolPrice, setSymbolPrice] = useState<SymbolPrice | null>(null);

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
  const [msg, setMsg] = useState("");

  // Modify SL/TP state
  const [editingPos, setEditingPos] = useState<string | null>(null);
  const [editSl, setEditSl] = useState("");
  const [editTp, setEditTp] = useState("");
  // Partial close state
  const [partialPos, setPartialPos] = useState<string | null>(null);
  const [partialVol, setPartialVol] = useState("");

  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  // Fetch account + positions
  const fetchAccount = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/trading/account`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setAccount(await res.json());
    } catch { /* silent */ }
  }, [token]);

  // Fetch account info (margin, leverage)
  const fetchAccountInfo = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/trading/account-info`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setAccountInfo(await res.json());
    } catch { /* silent */ }
  }, [token]);

  // Fetch symbol price
  const fetchPrice = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/trading/symbol/${symbol}`);
      if (res.ok) {
        const data = await res.json();
        if (data.price) setSymbolPrice(data.price);
      }
    } catch { /* silent */ }
  }, [symbol]);

  // Fetch pending orders
  const fetchOrders = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/trading/orders`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setPendingOrders(data.orders || []);
      }
    } catch { /* silent */ }
  }, [token]);

  // Fetch trade history
  const fetchHistory = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/trading/history?days=30`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setTradeHistory(data.trades || []);
        setHistoryStats(data.stats || { total_trades: 0, win_rate: 0, total_pnl: 0 });
      }
    } catch { /* silent */ }
  }, [token]);

  useEffect(() => {
    fetchAccount();
    fetchAccountInfo();
    const i1 = setInterval(fetchAccount, 15000); // 15s, not 5s
    return () => clearInterval(i1);
  }, [fetchAccount, fetchAccountInfo]);

  useEffect(() => {
    setSymbolPrice(null);
    fetchPrice();
    const i2 = setInterval(fetchPrice, 10000); // 10s, not 3s
    return () => clearInterval(i2);
  }, [fetchPrice]);

  useEffect(() => {
    if (tab === "orders") fetchOrders();
    if (tab === "history") fetchHistory();
  }, [tab, fetchOrders, fetchHistory]);

  // Place order
  const submitOrder = async (side: string) => {
    if (!token) {
      setMsg("Please sign in to place trades.");
      window.location.href = "/login?next=/dashboard";
      return;
    }
    setLoading(true);
    setMsg("");
    try {
      const url = orderType === "market" ? `${API_BASE}/api/trading/order` : `${API_BASE}/api/trading/pending-order`;
      const body: Record<string, unknown> = {
        symbol,
        side,
        size: parseFloat(size),
        stop_loss: sl ? parseFloat(sl) : null,
        take_profit: tp ? parseFloat(tp) : null,
      };
      if (orderType !== "market") {
        body.price = parseFloat(limitPrice);
        body.order_type = orderType;
      }

      const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
      const data = await res.json();
      if (data.success) {
        setMsg(`${side.toUpperCase()} ${symbol} ${size} lots — #${data.order_id || "OK"}`);
        setSl(""); setTp(""); setLimitPrice("");
        fetchAccount();
        fetchOrders();
      } else {
        setMsg(data.error || "Order failed");
      }
    } catch {
      setMsg("Network error");
    } finally {
      setLoading(false);
    }
  };

  // Close position
  const closePos = async (posId: string) => {
    await fetch(`${API_BASE}/api/trading/position/${posId}/close`, { method: "POST", headers });
    fetchAccount();
  };

  // Partial close
  const partialClose = async (posId: string) => {
    if (!partialVol) return;
    await fetch(`${API_BASE}/api/trading/position/${posId}/close-partial?volume=${parseFloat(partialVol)}`, { method: "POST", headers });
    setPartialPos(null);
    setPartialVol("");
    fetchAccount();
  };

  // Modify SL/TP
  const modifyPos = async (posId: string) => {
    await fetch(`${API_BASE}/api/trading/position/${posId}/modify`, {
      method: "POST", headers,
      body: JSON.stringify({
        stop_loss: editSl ? parseFloat(editSl) : null,
        take_profit: editTp ? parseFloat(editTp) : null,
      }),
    });
    setEditingPos(null);
    fetchAccount();
  };

  // Cancel pending order
  const cancelOrder = async (orderId: string) => {
    await fetch(`${API_BASE}/api/trading/order/${orderId}/cancel`, { method: "POST", headers });
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

            {/* Symbol + live price */}
            <div className="flex items-center gap-3">
              <SymbolSelect value={symbol} onChange={setSymbol} />
              {symbolPrice && (
                <div className="flex gap-3 text-xs">
                  <span className="text-green-400">{t.bid}: {symbolPrice.bid}</span>
                  <span className="text-red-400">{t.ask}: {symbolPrice.ask}</span>
                  <span className="text-zinc-600">{t.spread}: {(symbolPrice.spread * 100000).toFixed(1)}p</span>
                </div>
              )}
            </div>

            {/* Inputs */}
            <div className={`grid ${orderType === "market" ? "grid-cols-3" : "grid-cols-4"} gap-2`}>
              <div>
                <label className="text-[10px] text-zinc-500 block mb-1">{t.size}</label>
                <input type="number" step="0.01" value={size} onChange={(e) => setSize(e.target.value)} className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none" />
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

            {/* Buy / Sell buttons */}
            <div className="flex gap-2">
              <button onClick={() => submitOrder("buy")} disabled={loading}
                className="flex-1 py-2.5 bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-sm rounded-lg font-bold transition-colors">
                {t.buy} {symbolPrice ? symbolPrice.ask : ""}
              </button>
              <button onClick={() => submitOrder("sell")} disabled={loading}
                className="flex-1 py-2.5 bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white text-sm rounded-lg font-bold transition-colors">
                {t.sell} {symbolPrice ? symbolPrice.bid : ""}
              </button>
            </div>
            {msg && <p className="text-xs text-zinc-400">{msg}</p>}
          </CardContent>
        </Card>
      )}

      {/* Positions Tab */}
      {tab === "positions" && (
        <div className="space-y-2">
          {(!account || account.positions.length === 0) && (
            <div className="bg-zinc-900 rounded-lg p-6 text-center text-zinc-600 text-sm">{t.noPositions}</div>
          )}
          {account?.positions.map((p) => (
            <div key={p.id} className="bg-zinc-900 rounded-lg p-3 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Badge className={p.side === "long" ? "bg-green-900 text-green-300 text-[10px]" : "bg-red-900 text-red-300 text-[10px]"}>{p.side.toUpperCase()}</Badge>
                  <span className="font-mono text-white text-sm">{p.symbol}</span>
                  <span className="text-xs text-zinc-500">{p.volume} lots @ {p.entry_price}</span>
                </div>
                <span className={`font-mono text-sm font-bold ${pnlColor(p.profit)}`}>
                  {p.profit >= 0 ? "+" : ""}${p.profit.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <span>SL: {p.stop_loss || "—"}</span>
                <span>TP: {p.take_profit || "—"}</span>
                <span>Now: {p.current_price}</span>
              </div>
              <div className="flex gap-2">
                <button onClick={() => closePos(p.id)} className="px-3 py-1 bg-red-900/50 text-red-300 text-xs rounded hover:bg-red-900 transition-colors">{t.close}</button>
                <button onClick={() => { setPartialPos(p.id); setPartialVol(String(p.volume / 2)); }} className="px-3 py-1 bg-zinc-800 text-zinc-400 text-xs rounded hover:bg-zinc-700 transition-colors">{t.partial}</button>
                <button onClick={() => { setEditingPos(p.id); setEditSl(p.stop_loss ? String(p.stop_loss) : ""); setEditTp(p.take_profit ? String(p.take_profit) : ""); }} className="px-3 py-1 bg-zinc-800 text-zinc-400 text-xs rounded hover:bg-zinc-700 transition-colors">{t.modify}</button>
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
          ))}
        </div>
      )}

      {/* Pending Orders Tab */}
      {tab === "orders" && (
        <div className="space-y-2">
          {pendingOrders.length === 0 && (
            <div className="bg-zinc-900 rounded-lg p-6 text-center text-zinc-600 text-sm">{t.noOrders}</div>
          )}
          {pendingOrders.map((o) => (
            <div key={o.id} className="bg-zinc-900 rounded-lg px-4 py-2.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge className="bg-yellow-900 text-yellow-300 text-[10px]">{o.type}</Badge>
                <span className="font-mono text-white text-sm">{o.symbol}</span>
                <span className="text-xs text-zinc-500">{o.volume} @ {o.price}</span>
              </div>
              <button onClick={() => cancelOrder(o.id)} className="text-xs text-zinc-500 hover:text-red-400 transition-colors">{t.cancel}</button>
            </div>
          ))}
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
          {tradeHistory.slice(0, 20).map((trade, i) => (
            <div key={i} className="bg-zinc-900/50 rounded px-4 py-2 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className={trade.side === "buy" ? "text-green-500" : "text-red-500"}>{trade.side.toUpperCase()}</span>
                <span className="text-zinc-300">{trade.symbol}</span>
                <span className="text-zinc-600">{trade.volume} @ {trade.price}</span>
              </div>
              <span className={`font-mono font-bold ${pnlColor(trade.profit)}`}>
                {trade.profit >= 0 ? "+" : ""}${trade.profit.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color = "text-white" }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-3">
      <p className="text-[10px] text-zinc-500 uppercase">{label}</p>
      <p className={`text-sm font-mono font-bold ${color}`}>{value}</p>
    </div>
  );
}
