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
  size?: number;
  volume?: number;
  entry_price: number;
  current_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  unrealized_pnl?: number;
  profit?: number;
}

interface PaperAccount {
  balance: number;
  equity: number;
  pnl: number;
  pnl_pct: number;
  open_positions: number;
  total_trades: number;
  win_rate: number;
  positions: Position[];
  recent_trades: Array<{
    symbol: string;
    side: string;
    pnl: number;
    entry_price: number;
    exit_price: number;
    reason?: string;
  }>;
}

const texts: Record<string, Record<string, string>> = {
  en: {
    title: "Trading",
    balance: "Balance",
    equity: "Equity",
    pnl: "P&L",
    winRate: "Win Rate",
    trades: "Trades",
    placeOrder: "Place Order",
    symbol: "Symbol",
    side: "Side",
    size: "Size",
    sl: "Stop Loss",
    tp: "Take Profit",
    buy: "Buy / Long",
    sell: "Sell / Short",
    submit: "Place Order",
    close: "Close",
    modify: "SL/TP",
    positions: "Open Positions",
    history: "Trade History",
    reset: "Reset Account",
    noPositions: "No open positions",
    noTrades: "No trades yet",
  },
  zh: {
    title: "交易",
    balance: "余额",
    equity: "净值",
    pnl: "盈亏",
    winRate: "胜率",
    trades: "交易数",
    placeOrder: "下单",
    symbol: "品种",
    side: "方向",
    size: "手数",
    sl: "止损",
    tp: "止盈",
    buy: "买入 / 做多",
    sell: "卖出 / 做空",
    submit: "下单",
    close: "平仓",
    modify: "止损止盈",
    positions: "持仓",
    history: "交易记录",
    reset: "重置账户",
    noPositions: "暂无持仓",
    noTrades: "暂无交易",
  },
};

export function TradingPanel() {
  const { locale } = useI18n();
  const { token } = useAuth();
  const t = texts[locale] || texts.en;

  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [symbol, setSymbol] = useState("BTCUSD");
  const [side, setSide] = useState("buy");
  const [size, setSize] = useState("0.01");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  const fetchAccount = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/trading/account`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setAccount(await res.json());
    } catch { /* silent */ }
  }, [token]);

  useEffect(() => {
    fetchAccount();
    const interval = setInterval(fetchAccount, 5000);
    return () => clearInterval(interval);
  }, [fetchAccount]);

  const submitOrder = async (orderSide: string) => {
    setLoading(true);
    setMsg("");
    try {
      const res = await fetch(`${API_BASE}/api/trading/order`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          symbol,
          side: orderSide,
          size: parseFloat(size),
          stop_loss: sl ? parseFloat(sl) : null,
          take_profit: tp ? parseFloat(tp) : null,
        }),
      });
      const data = await res.json();
      if (data.success) {
        const price = data.price || data.order?.filled_price || "";
        setMsg(`${orderSide.toUpperCase()} ${symbol} ${size} lots${price ? ` @ $${Number(price).toLocaleString()}` : ""} — Order #${data.order_id || ""}`);
        setSl("");
        setTp("");
        fetchAccount();
      } else {
        setMsg(data.error || "Order failed");
      }
    } catch {
      setMsg("Network error");
    } finally {
      setLoading(false);
    }
  };

  const closePos = async (posId: string) => {
    const res = await fetch(`${API_BASE}/api/trading/position/${posId}/close`, { method: "POST", headers });
    const data = await res.json();
    if (data.success) fetchAccount();
  };

  const resetAccount = async () => {
    await fetch(`${API_BASE}/api/trading/reset`, { method: "POST", headers });
    fetchAccount();
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
        <div className="grid grid-cols-5 gap-3">
          <Stat label={t.balance} value={`$${account.balance.toLocaleString("en", { minimumFractionDigits: 2 })}`} />
          <Stat label={t.equity} value={`$${account.equity.toLocaleString("en", { minimumFractionDigits: 2 })}`} />
          <Stat label={t.pnl} value={`${account.pnl >= 0 ? "+" : ""}$${account.pnl.toFixed(2)}`} color={pnlColor(account.pnl)} />
          <Stat label={t.winRate} value={`${account.win_rate}%`} />
          <Stat label={t.trades} value={`${account.total_trades}`} />
        </div>
      )}

      {/* Order form */}
      <Card className="bg-zinc-900 border-0">
        <CardContent className="pt-4 space-y-3">
          <div className="grid grid-cols-4 gap-3">
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">{t.symbol}</label>
              <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none">
                <option value="BTCUSD">BTC/USD</option>
                <option value="ETHUSD">ETH/USD</option>
                <option value="EURUSD">EUR/USD</option>
                <option value="XAUUSD">XAU/USD</option>
                <option value="GBPUSD">GBP/USD</option>
                <option value="SOLUSD">SOL/USD</option>
              </select>
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">{t.size}</label>
              <input type="number" step="0.01" value={size} onChange={(e) => setSize(e.target.value)} className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none" />
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">{t.sl}</label>
              <input type="number" step="any" value={sl} onChange={(e) => setSl(e.target.value)} placeholder="—" className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none placeholder-zinc-600" />
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 block mb-1">{t.tp}</label>
              <input type="number" step="any" value={tp} onChange={(e) => setTp(e.target.value)} placeholder="—" className="w-full bg-zinc-800 text-white rounded px-2 py-1.5 text-sm focus:outline-none placeholder-zinc-600" />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => submitOrder("buy")}
              disabled={loading}
              className="flex-1 py-2 bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white text-sm rounded-lg font-medium transition-colors"
            >
              {t.buy}
            </button>
            <button
              onClick={() => submitOrder("sell")}
              disabled={loading}
              className="flex-1 py-2 bg-red-800 hover:bg-red-700 disabled:opacity-40 text-white text-sm rounded-lg font-medium transition-colors"
            >
              {t.sell}
            </button>
          </div>
          {msg && <p className="text-xs text-zinc-400">{msg}</p>}
        </CardContent>
      </Card>

      {/* Positions */}
      {account && account.positions.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs text-zinc-500 uppercase">{t.positions}</h3>
          {account.positions.map((p) => (
            <div key={p.id} className="bg-zinc-900 rounded-lg px-4 py-2.5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Badge className={p.side === "long" ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}>
                  {p.side.toUpperCase()}
                </Badge>
                <span className="font-mono text-white text-sm">{p.symbol}</span>
                <span className="text-xs text-zinc-500">{p.volume || p.size} @ ${p.entry_price.toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`font-mono text-sm font-bold ${pnlColor(p.profit ?? p.unrealized_pnl ?? 0)}`}>
                  {(p.profit ?? p.unrealized_pnl ?? 0) >= 0 ? "+" : ""}${(p.profit ?? p.unrealized_pnl ?? 0).toFixed(2)}
                </span>
                <button onClick={() => closePos(p.id)} className="text-xs text-zinc-500 hover:text-red-400 transition-colors">
                  {t.close}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Trade history */}
      {account && account.recent_trades.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs text-zinc-500 uppercase">{t.history}</h3>
          {account.recent_trades.slice(-5).reverse().map((trade, i) => (
            <div key={i} className="bg-zinc-900/50 rounded px-4 py-2 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className={trade.side === "long" ? "text-green-500" : "text-red-500"}>{trade.side.toUpperCase()}</span>
                <span className="text-zinc-300">{trade.symbol}</span>
                <span className="text-zinc-600">{trade.entry_price} → {trade.exit_price}</span>
                {trade.reason && <span className="text-zinc-600">({trade.reason})</span>}
              </div>
              <span className={`font-mono font-bold ${pnlColor(trade.pnl)}`}>
                {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
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
