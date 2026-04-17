/**
 * Unified symbol definitions — single source of truth for all components.
 * Different firms support different symbols.
 */

export interface SymbolDef {
  value: string;
  label: string;
  category: "forex" | "metals" | "crypto" | "indices";
}

const ALL_SYMBOLS: SymbolDef[] = [
  // Forex
  { value: "EURUSD", label: "EUR/USD", category: "forex" },
  { value: "GBPUSD", label: "GBP/USD", category: "forex" },
  { value: "USDJPY", label: "USD/JPY", category: "forex" },
  { value: "AUDUSD", label: "AUD/USD", category: "forex" },
  { value: "USDCAD", label: "USD/CAD", category: "forex" },
  { value: "NZDUSD", label: "NZD/USD", category: "forex" },
  { value: "USDCHF", label: "USD/CHF", category: "forex" },
  { value: "EURJPY", label: "EUR/JPY", category: "forex" },
  { value: "GBPJPY", label: "GBP/JPY", category: "forex" },
  { value: "EURGBP", label: "EUR/GBP", category: "forex" },
  { value: "AUDCAD", label: "AUD/CAD", category: "forex" },
  // Metals
  { value: "XAUUSD", label: "XAU/USD", category: "metals" },
  { value: "XAGUSD", label: "XAG/USD", category: "metals" },
  // Crypto
  { value: "BTCUSD", label: "BTC/USD", category: "crypto" },
  { value: "ETHUSD", label: "ETH/USD", category: "crypto" },
  { value: "SOLUSD", label: "SOL/USD", category: "crypto" },
  // Indices
  { value: "US30", label: "US30", category: "indices" },
  { value: "NAS100", label: "NAS100", category: "indices" },
  { value: "SPX500", label: "SPX500", category: "indices" },
];

// Per-firm symbol availability
const FIRM_SYMBOLS: Record<string, string[]> = {
  ftmo: [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF",
    "EURJPY", "GBPJPY", "EURGBP", "AUDCAD",
    "XAUUSD", "XAGUSD",
    "BTCUSD", "ETHUSD",
    "US30", "NAS100", "SPX500",
  ],
  topstep: [
    "US30", "NAS100", "SPX500",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "XAUUSD",
  ],
  cryptofundtrader: [
    "BTCUSD", "ETHUSD", "SOLUSD",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "XAUUSD",
    "US30", "NAS100",
  ],
};

/**
 * Get symbols available for a specific firm.
 * Falls back to all symbols if firm not found.
 */
export function getSymbolsForFirm(firmName: string): SymbolDef[] {
  const allowed = FIRM_SYMBOLS[firmName.toLowerCase()];
  if (!allowed) return ALL_SYMBOLS;
  return ALL_SYMBOLS.filter((s) => allowed.includes(s.value));
}

/**
 * Get all symbols (for chart/general use).
 */
export function getAllSymbols(): SymbolDef[] {
  return ALL_SYMBOLS;
}

/**
 * Get just the value strings for a firm.
 */
export function getSymbolValuesForFirm(firmName: string): string[] {
  return getSymbolsForFirm(firmName).map((s) => s.value);
}
