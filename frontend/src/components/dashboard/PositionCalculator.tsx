"use client";

import { useState, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/i18n/context";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface CalcResult {
  recommended_size: number;
  stop_loss_price: number;
  risk_amount: number;
  risk_pct: number;
  max_allowed_size: number;
  kelly_size: number | null;
  kelly_note: string | null;
  warnings: string[];
}

export function PositionCalculator({ equity }: { equity: number }) {
  const { t } = useI18n();
  const [entry, setEntry] = useState("");
  const [sl, setSl] = useState("");
  const [contractSize, setContractSize] = useState("100000");
  const [result, setResult] = useState<CalcResult | null>(null);
  const [loading, setLoading] = useState(false);

  const calculate = useCallback(async () => {
    if (!entry || !sl) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/position/calculate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          equity,
          entry_price: parseFloat(entry),
          stop_loss: parseFloat(sl),
          contract_size: parseFloat(contractSize),
        }),
      });
      setResult(await res.json());
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [equity, entry, sl, contractSize]);

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
        {t("calc.title")}
      </h2>

      <div className="bg-zinc-900 rounded-lg p-4 space-y-3">
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-zinc-500 block mb-1">{t("calc.entryPrice")}</label>
            <input
              type="number"
              step="any"
              value={entry}
              onChange={(e) => setEntry(e.target.value)}
              placeholder="1.0850"
              className="w-full bg-zinc-800 text-white rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-600"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">{t("calc.stopLoss")}</label>
            <input
              type="number"
              step="any"
              value={sl}
              onChange={(e) => setSl(e.target.value)}
              placeholder="1.0800"
              className="w-full bg-zinc-800 text-white rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-600"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">{t("calc.contractSize")}</label>
            <select
              value={contractSize}
              onChange={(e) => setContractSize(e.target.value)}
              className="w-full bg-zinc-800 text-white rounded px-3 py-1.5 text-sm focus:outline-none"
            >
              <option value="100000">Forex (100K)</option>
              <option value="1">Crypto (1:1)</option>
              <option value="50">Futures (50x)</option>
            </select>
          </div>
        </div>

        <div className="flex justify-between items-center">
          <p className="text-xs text-zinc-500">
            Equity: ${equity.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
          <button
            onClick={calculate}
            disabled={loading || !entry || !sl}
            className="px-4 py-1.5 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
          >
            {loading ? "..." : t("calc.calculate")}
          </button>
        </div>
      </div>

      {result && (
        <Card className="bg-zinc-900 border-0">
          <CardContent className="pt-4 space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <ResultRow
                label={t("calc.recommended")}
                value={`${result.recommended_size} lots`}
                highlight
              />
              <ResultRow
                label={t("calc.riskAmount")}
                value={`$${result.risk_amount.toFixed(2)}`}
                color={result.risk_pct > 2 ? "text-red-400" : "text-zinc-300"}
              />
              <ResultRow
                label={t("calc.riskPct")}
                value={`${result.risk_pct}%`}
                color={result.risk_pct > 2 ? "text-red-400" : "text-green-400"}
              />
              <ResultRow
                label={t("calc.maxAllowed")}
                value={`${result.max_allowed_size} lots`}
              />
            </div>

            {result.kelly_size !== null && (
              <div className="bg-zinc-800/50 rounded p-2">
                <p className="text-xs text-zinc-500">
                  Kelly reference: {result.kelly_size} lots
                </p>
                {result.kelly_note && (
                  <p className="text-xs text-zinc-600 mt-1">{result.kelly_note}</p>
                )}
              </div>
            )}

            {result.warnings.length > 0 && (
              <div className="space-y-1">
                {result.warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs text-yellow-400">
                    <span>⚠</span>
                    <span>{w}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ResultRow({
  label,
  value,
  color = "text-zinc-300",
  highlight = false,
}: {
  label: string;
  value: string;
  color?: string;
  highlight?: boolean;
}) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className={`font-mono ${highlight ? "text-lg font-bold text-white" : `text-sm ${color}`}`}>
        {value}
      </p>
    </div>
  );
}
