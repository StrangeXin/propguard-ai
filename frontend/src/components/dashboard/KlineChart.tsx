"use client";

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/i18n/context";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

import { SymbolSelect } from "./SymbolSelect";

// klinecharts 10 beta only ships the MA indicator built-in; everything else
// (VOL, BOLL, MACD, RSI, …) must be registered per-app. We do that once on
// first chart mount so all instances share the same registry.
let indicatorsRegistered = false;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function registerBuiltInIndicators(kc: any) {
  if (indicatorsRegistered) return;
  indicatorsRegistered = true;

  // VOL — volume histogram colored by candle direction.
  kc.registerIndicator({
    name: "VOL",
    shortName: "VOL",
    series: "volume",
    calcParams: [5, 10, 20],
    figures: [
      { key: "ma5", title: "MA5: ", type: "line" },
      { key: "ma10", title: "MA10: ", type: "line" },
      { key: "ma20", title: "MA20: ", type: "line" },
      {
        key: "volume",
        title: "VOLUME: ",
        type: "bar",
        baseValue: 0,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        styles: (data: any) => {
          const k = data.current.kLineData;
          return {
            color: k && k.close >= k.open ? "#22c55e" : "#ef4444",
          };
        },
      },
    ],
    minValue: 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    calc: (dataList: any[], indicator: any) => {
      const [p5, p10, p20] = indicator.calcParams;
      const sums: Record<number, number> = { [p5]: 0, [p10]: 0, [p20]: 0 };
      return dataList.map((k, i) => {
        const vol = k.volume ?? 0;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const row: any = { volume: vol };
        [p5, p10, p20].forEach((p) => {
          sums[p] += vol;
          if (i >= p) sums[p] -= dataList[i - p].volume ?? 0;
          if (i >= p - 1) row[`ma${p}`] = sums[p] / p;
        });
        return row;
      });
    },
  });

  // MACD — fast EMA − slow EMA + signal EMA; histogram = diff − signal.
  kc.registerIndicator({
    name: "MACD",
    shortName: "MACD",
    calcParams: [12, 26, 9],
    figures: [
      { key: "dif", title: "DIF: ", type: "line" },
      { key: "dea", title: "DEA: ", type: "line" },
      {
        key: "macd", title: "MACD: ", type: "bar", baseValue: 0,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        styles: (data: any) => ({ color: (data.current.indicatorData?.macd ?? 0) >= 0 ? "#22c55e" : "#ef4444" }),
      },
    ],
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    calc: (dataList: any[], indicator: any) => {
      const [fast, slow, signal] = indicator.calcParams;
      const kFast = 2 / (fast + 1);
      const kSlow = 2 / (slow + 1);
      const kSig = 2 / (signal + 1);
      let emaFast = 0, emaSlow = 0, dea = 0;
      return dataList.map((k, i) => {
        const c = k.close;
        emaFast = i === 0 ? c : c * kFast + emaFast * (1 - kFast);
        emaSlow = i === 0 ? c : c * kSlow + emaSlow * (1 - kSlow);
        const dif = emaFast - emaSlow;
        dea = i === 0 ? dif : dif * kSig + dea * (1 - kSig);
        return { dif, dea, macd: (dif - dea) * 2 };
      });
    },
  });

  // RSI — standard Wilder (14).
  kc.registerIndicator({
    name: "RSI",
    shortName: "RSI",
    calcParams: [6, 12, 24],
    figures: [
      { key: "rsi1", title: "RSI6: ", type: "line" },
      { key: "rsi2", title: "RSI12: ", type: "line" },
      { key: "rsi3", title: "RSI24: ", type: "line" },
    ],
    minValue: 0, maxValue: 100,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    calc: (dataList: any[], indicator: any) => {
      const periods = indicator.calcParams as number[];
      const gains = periods.map(() => 0);
      const losses = periods.map(() => 0);
      const ready = periods.map(() => false);
      return dataList.map((k, i) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const row: any = {};
        if (i === 0) return row;
        const diff = k.close - dataList[i - 1].close;
        const gain = diff > 0 ? diff : 0;
        const loss = diff < 0 ? -diff : 0;
        periods.forEach((p, idx) => {
          if (i <= p) {
            gains[idx] += gain;
            losses[idx] += loss;
            if (i === p) {
              gains[idx] /= p; losses[idx] /= p; ready[idx] = true;
            }
          } else {
            gains[idx] = (gains[idx] * (p - 1) + gain) / p;
            losses[idx] = (losses[idx] * (p - 1) + loss) / p;
          }
          if (ready[idx]) {
            const rs = losses[idx] === 0 ? 100 : gains[idx] / losses[idx];
            row[`rsi${idx + 1}`] = losses[idx] === 0 ? 100 : 100 - 100 / (1 + rs);
          }
        });
        return row;
      });
    },
  });

  // BOLL — middle = SMA(20), bands = middle ± 2·stdev.
  kc.registerIndicator({
    name: "BOLL",
    shortName: "BOLL",
    calcParams: [20, 2],
    figures: [
      { key: "up", title: "UP: ", type: "line" },
      { key: "mid", title: "MID: ", type: "line" },
      { key: "dn", title: "DN: ", type: "line" },
    ],
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    calc: (dataList: any[], indicator: any) => {
      const [period, mult] = indicator.calcParams;
      return dataList.map((_, i) => {
        if (i < period - 1) return {};
        const slice = dataList.slice(i - period + 1, i + 1);
        const mid = slice.reduce((s, x) => s + x.close, 0) / period;
        const variance = slice.reduce((s, x) => s + (x.close - mid) ** 2, 0) / period;
        const sd = Math.sqrt(variance);
        return { up: mid + mult * sd, mid, dn: mid - mult * sd };
      });
    },
  });

  // EMA(5,10,20) overlay on the candle pane.
  kc.registerIndicator({
    name: "EMA",
    shortName: "EMA",
    calcParams: [5, 10, 20],
    figures: [
      { key: "ema1", title: "EMA5: ", type: "line" },
      { key: "ema2", title: "EMA10: ", type: "line" },
      { key: "ema3", title: "EMA20: ", type: "line" },
    ],
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    calc: (dataList: any[], indicator: any) => {
      const periods = indicator.calcParams as number[];
      const ks = periods.map((p) => 2 / (p + 1));
      const prev = periods.map(() => 0);
      return dataList.map((d, i) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const row: any = {};
        periods.forEach((_p, idx) => {
          prev[idx] = i === 0 ? d.close : d.close * ks[idx] + prev[idx] * (1 - ks[idx]);
          row[`ema${idx + 1}`] = prev[idx];
        });
        return row;
      });
    },
  });

  // KDJ — stochastic on 9-period range.
  kc.registerIndicator({
    name: "KDJ",
    shortName: "KDJ",
    calcParams: [9, 3, 3],
    figures: [
      { key: "k", title: "K: ", type: "line" },
      { key: "d", title: "D: ", type: "line" },
      { key: "j", title: "J: ", type: "line" },
    ],
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    calc: (dataList: any[], indicator: any) => {
      const [n, m1, m2] = indicator.calcParams;
      let K = 50, D = 50;
      return dataList.map((k, i) => {
        if (i < n - 1) return {};
        const slice = dataList.slice(i - n + 1, i + 1);
        const low = Math.min(...slice.map((x) => x.low));
        const high = Math.max(...slice.map((x) => x.high));
        const rsv = high === low ? 50 : ((k.close - low) / (high - low)) * 100;
        K = (K * (m1 - 1) + rsv) / m1;
        D = (D * (m2 - 1) + K) / m2;
        return { k: K, d: D, j: 3 * K - 2 * D };
      });
    },
  });
}

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

export function KlineChart({ symbol: externalSymbol, onSymbolChange }: { symbol?: string; onSymbolChange?: (s: string) => void } = {}) {
  const { t } = useI18n();
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<import("klinecharts").Chart | null>(null);
  const [symbol, setSymbolLocal] = useState(externalSymbol || "BTCUSD");

  // Sync with external symbol
  useEffect(() => {
    if (externalSymbol && externalSymbol !== symbol) {
      setSymbolLocal(externalSymbol);
    }
  }, [externalSymbol]);

  const setSymbol = (s: string) => {
    setSymbolLocal(s);
    onSymbolChange?.(s);
  };
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
      await registerBuiltInIndicators(kc);
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
          <SymbolSelect value={symbol} onChange={setSymbol} className="text-xs mr-2" />

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
            <div
              className={`absolute bottom-2 right-3 text-[10px] px-1.5 py-0.5 rounded ${
                dataSource === "mock"
                  ? "bg-red-900/60 text-red-200"
                  : dataSource === "estimated"
                  ? "bg-amber-900/60 text-amber-200"
                  : "text-zinc-600"
              }`}
              title={
                dataSource === "mock"
                  ? "Synthetic data — real market feed unavailable"
                  : dataSource === "estimated"
                  ? "Estimated data — external API unreachable, seeded from realistic base price"
                  : ""
              }
            >
              {dataSource === "mock" ? "⚠ SIM DATA" : dataSource === "estimated" ? "⚠ EST DATA" : `Data: ${dataSource}`}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
