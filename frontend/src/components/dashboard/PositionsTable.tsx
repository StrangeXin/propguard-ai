"use client";

import type { Position } from "@/lib/types";
import { useI18n } from "@/i18n/context";

export function PositionsTable({ positions }: { positions: Position[] }) {
  const { t } = useI18n();

  if (positions.length === 0) {
    return (
      <div className="bg-zinc-900 rounded-lg p-6 text-center text-zinc-500">
        {t("positions.empty")}
      </div>
    );
  }

  return (
    <div className="bg-zinc-900 rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-800">
        <h3 className="text-sm font-medium text-zinc-300">{t("positions.title")}</h3>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-zinc-500 uppercase tracking-wider">
            <th className="px-4 py-2 text-left">{t("positions.symbol")}</th>
            <th className="px-4 py-2 text-left">{t("positions.side")}</th>
            <th className="px-4 py-2 text-right">{t("positions.size")}</th>
            <th className="px-4 py-2 text-right">{t("positions.entry")}</th>
            <th className="px-4 py-2 text-right">{t("positions.current")}</th>
            <th className="px-4 py-2 text-right">{t("positions.pnl")}</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos, i) => (
            <tr key={i} className="border-t border-zinc-800">
              <td className="px-4 py-2 font-mono text-white">{pos.symbol}</td>
              <td className="px-4 py-2">
                <span className={pos.side === "long" ? "text-green-400" : "text-red-400"}>
                  {pos.side.toUpperCase()}
                </span>
              </td>
              <td className="px-4 py-2 text-right font-mono text-zinc-300">{pos.size}</td>
              <td className="px-4 py-2 text-right font-mono text-zinc-300">
                {pos.entry_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </td>
              <td className="px-4 py-2 text-right font-mono text-zinc-300">
                {pos.current_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </td>
              <td className={`px-4 py-2 text-right font-mono font-bold ${pos.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                {pos.unrealized_pnl >= 0 ? "+" : ""}${pos.unrealized_pnl.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
