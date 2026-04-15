"use client";

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/i18n/context";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const SYMBOLS = [
  { value: "BTCUSD", label: "BTC/USD" },
  { value: "ETHUSD", label: "ETH/USD" },
  { value: "EURUSD", label: "EUR/USD" },
  { value: "GBPUSD", label: "GBP/USD" },
  { value: "XAUUSD", label: "XAU/USD" },
  { value: "SOLUSD", label: "SOL/USD" },
];

const PERIODS = [
  { value: "1m", label: "1m", span: 1, type: "minute" as const },
  { value: "5m", label: "5m", span: 5, type: "minute" as const },
  { value: "15m", label: "15m", span: 15, type: "minute" as const },
  { value: "1h", label: "1H", span: 1, type: "hour" as const },
  { value: "4h", label: "4H", span: 4, type: "hour" as const },
  { value: "1d", label: "1D", span: 1, type: "day" as const },
];

const INDICATORS = [
  { value: "MA", label: "MA", main: true },
  { value: "EMA", label: "EMA", main: true },
  { value: "BOLL", label: "BOLL", main: true },
  { value: "VOL", label: "VOL", main: false },
  { value: "MACD", label: "MACD", main: false },
  { value: "RSI", label: "RSI", main: false },
  { value: "KDJ", label: "KDJ", main: false },
];

export function KlineChart() {
  const { t } = useI18n();
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<import("klinecharts").Chart | null>(null);
  const [symbol, setSymbol] = useState("BTCUSD");
  const [periodKey, setPeriodKey] = useState("1h");
  const [activeIndicators, setActiveIndicators] = useState<string[]>(["VOL"]);
  const [loading, setLoading] = useState(false);
  const [dataSource, setDataSource] = useState("");

  // We need a ref to symbol/period so the dataLoader callback reads the latest values
  const symbolRef = useRef(symbol);
  const periodRef = useRef(periodKey);
  symbolRef.current = symbol;
  periodRef.current = periodKey;

  // Initialize chart once
  useEffect(() => {
    let mounted = true;

    async function setup() {
      const kc = await import("klinecharts");
      if (!mounted || !chartRef.current) return;

      // Use type assertion for styles — klinecharts types are strict
      // but accept these runtime values fine
      const darkStyles = {
        grid: {
          show: true,
          horizontal: { color: "rgba(255,255,255,0.04)" },
          vertical: { color: "rgba(255,255,255,0.04)" },
        },
        candle: {
          bar: {
            upColor: "#22c55e",
            downColor: "#ef4444",
            upBorderColor: "#22c55e",
            downBorderColor: "#ef4444",
            upWickColor: "#22c55e",
            downWickColor: "#ef4444",
          },
          tooltip: { text: { color: "#a1a1aa" } },
        },
        indicator: {
          tooltip: { text: { color: "#a1a1aa" } },
        },
        xAxis: {
          axisLine: { color: "#27272a" },
          tickLine: { color: "#27272a" },
          tickText: { color: "#71717a" },
        },
        yAxis: {
          axisLine: { color: "#27272a" },
          tickLine: { color: "#27272a" },
          tickText: { color: "#71717a" },
        },
        separator: { color: "#27272a" },
        crosshair: {
          horizontal: { line: { color: "#3b82f6" } },
          vertical: { line: { color: "#3b82f6" } },
        },
      };

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const chart = kc.init(chartRef.current, { styles: darkStyles } as any);

      if (!chart) return;
      chartInstance.current = chart;

      // Set up data loader
      chart.setDataLoader({
        getBars: async ({ callback }) => {
          setLoading(true);
          try {
            const res = await fetch(
              `${API_BASE}/api/kline/${symbolRef.current}?period=${periodRef.current}&count=300`
            );
            const data = await res.json();
            setDataSource(data.source || "");
            callback(data.bars || [], false);
          } catch {
            callback([], false);
          } finally {
            setLoading(false);
          }
        },
      });

      // Set initial symbol and period
      const p = PERIODS.find((p) => p.value === periodRef.current) || PERIODS[3];
      chart.setSymbol({ ticker: symbolRef.current });
      chart.setPeriod({ span: p.span, type: p.type });

      // Default indicator
      chart.createIndicator("VOL");
    }

    setup();

    // Auto-refresh every 60 seconds
    const refreshInterval = setInterval(() => {
      if (chartInstance.current) {
        const pp = PERIODS.find((p) => p.value === periodRef.current) || PERIODS[3];
        chartInstance.current.setPeriod({ span: pp.span, type: pp.type });
      }
    }, 60000);

    return () => {
      mounted = false;
      clearInterval(refreshInterval);
      if (chartRef.current) {
        import("klinecharts").then((kc) => {
          if (chartRef.current) kc.dispose(chartRef.current);
        });
      }
      chartInstance.current = null;
    };
  }, []);

  // Update symbol
  useEffect(() => {
    if (chartInstance.current) {
      chartInstance.current.setSymbol({ ticker: symbol });
    }
  }, [symbol]);

  // Update period
  useEffect(() => {
    const p = PERIODS.find((pp) => pp.value === periodKey) || PERIODS[3];
    if (chartInstance.current) {
      chartInstance.current.setPeriod({ span: p.span, type: p.type });
    }
  }, [periodKey]);

  const toggleIndicator = (name: string) => {
    if (!chartInstance.current) return;

    const ind = INDICATORS.find((i) => i.value === name);
    if (!ind) return;

    if (activeIndicators.includes(name)) {
      if (ind.main) {
        chartInstance.current.removeIndicator({ paneId: "candle_pane", name });
      } else {
        chartInstance.current.removeIndicator({ name });
      }
      setActiveIndicators((prev) => prev.filter((i) => i !== name));
    } else {
      if (ind.main) {
        chartInstance.current.createIndicator(name, false, { id: "candle_pane" });
      } else {
        chartInstance.current.createIndicator(name);
      }
      setActiveIndicators((prev) => [...prev, name]);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
          {t("chart.title")}
        </h2>
        {loading && (
          <span className="text-xs text-zinc-500 animate-pulse">{t("chart.loading")}</span>
        )}
      </div>

      <div className="bg-zinc-900 rounded-lg overflow-hidden">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-1 px-3 py-2 border-b border-zinc-800">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="bg-zinc-800 text-white text-xs rounded px-2 py-1 focus:outline-none mr-2"
          >
            {SYMBOLS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>

          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriodKey(p.value)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                periodKey === p.value
                  ? "bg-blue-600 text-white"
                  : "bg-zinc-800 text-zinc-400 hover:text-white"
              }`}
            >
              {p.label}
            </button>
          ))}

          <div className="w-px h-4 bg-zinc-700 mx-1" />

          {INDICATORS.map((ind) => (
            <button
              key={ind.value}
              onClick={() => toggleIndicator(ind.value)}
              className={`px-2 py-1 text-xs rounded transition-colors ${
                activeIndicators.includes(ind.value)
                  ? "bg-zinc-700 text-green-400"
                  : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {ind.label}
            </button>
          ))}
        </div>

        {/* Chart */}
        <div className="relative">
          <div
            ref={chartRef}
            style={{ width: "100%", height: 420 }}
            className="bg-zinc-950"
          />
          {dataSource && (
            <div className="absolute bottom-2 right-3 text-[10px] text-zinc-600">
              Data: {dataSource}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
