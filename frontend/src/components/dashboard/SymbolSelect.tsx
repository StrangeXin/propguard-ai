"use client";

import { getSymbolsForFirm, getAllSymbols, type SymbolDef } from "@/lib/symbols";

interface SymbolSelectProps {
  value: string;
  onChange: (symbol: string) => void;
  firmName?: string;
  className?: string;
}

export function SymbolSelect({ value, onChange, firmName, className = "" }: SymbolSelectProps) {
  const symbols = firmName ? getSymbolsForFirm(firmName) : getAllSymbols();

  // Group by category
  const groups: Record<string, SymbolDef[]> = {};
  for (const s of symbols) {
    if (!groups[s.category]) groups[s.category] = [];
    groups[s.category].push(s);
  }

  const categoryLabels: Record<string, string> = {
    forex: "Forex",
    metals: "Metals",
    crypto: "Crypto",
    indices: "Indices",
  };

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`bg-zinc-800 text-white text-sm rounded px-2 py-1.5 focus:outline-none ${className}`}
    >
      {Object.entries(groups).map(([cat, syms]) => (
        <optgroup key={cat} label={categoryLabels[cat] || cat}>
          {syms.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
