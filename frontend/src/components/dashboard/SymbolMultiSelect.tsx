"use client";

import { useState, useRef, useEffect } from "react";
import { getSymbolsForFirm, getAllSymbols, type SymbolDef } from "@/lib/symbols";

interface SymbolMultiSelectProps {
  value: string[];
  onChange: (symbols: string[]) => void;
  firmName?: string;
}

export function SymbolMultiSelect({ value, onChange, firmName }: SymbolMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const symbols = firmName ? getSymbolsForFirm(firmName) : getAllSymbols();
  const groups: Record<string, SymbolDef[]> = {};
  for (const s of symbols) {
    if (!groups[s.category]) groups[s.category] = [];
    groups[s.category].push(s);
  }

  const categoryLabels: Record<string, string> = {
    forex: "Forex", metals: "Metals", crypto: "Crypto", indices: "Indices",
  };

  const toggle = (sym: string) => {
    onChange(value.includes(sym) ? value.filter((v) => v !== sym) : [...value, sym]);
  };

  const selectAll = () => onChange(symbols.map((s) => s.value));
  const clearAll = () => onChange([]);

  // Close on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="w-full bg-zinc-800 text-left text-sm text-white rounded px-2 py-1.5 focus:outline-none flex items-center justify-between"
      >
        <span className="truncate">
          {value.length === 0
            ? "Select symbols..."
            : value.length <= 3
              ? value.join(", ")
              : `${value.slice(0, 2).join(", ")} +${value.length - 2}`}
        </span>
        <span className="text-zinc-500 text-xs ml-1">{value.length}</span>
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-64 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl max-h-64 overflow-y-auto">
          <div className="flex gap-2 p-2 border-b border-zinc-700">
            <button onClick={selectAll} className="text-[10px] text-blue-400 hover:text-blue-300">All</button>
            <button onClick={clearAll} className="text-[10px] text-zinc-500 hover:text-zinc-300">Clear</button>
          </div>
          {Object.entries(groups).map(([cat, syms]) => (
            <div key={cat}>
              <div className="px-2 py-1 text-[10px] text-zinc-500 uppercase bg-zinc-850">{categoryLabels[cat]}</div>
              {syms.map((s) => (
                <label key={s.value} className="flex items-center gap-2 px-2 py-1 hover:bg-zinc-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={value.includes(s.value)}
                    onChange={() => toggle(s.value)}
                    className="rounded border-zinc-600 bg-zinc-700 text-blue-500 focus:ring-0 w-3 h-3"
                  />
                  <span className="text-xs text-zinc-300">{s.label}</span>
                </label>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
