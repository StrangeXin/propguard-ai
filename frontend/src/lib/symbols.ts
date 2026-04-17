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
  // Forex Major
  { value: "EURUSD", label: "EUR/USD", category: "forex" },
  { value: "GBPUSD", label: "GBP/USD", category: "forex" },
  { value: "USDJPY", label: "USD/JPY", category: "forex" },
  { value: "AUDUSD", label: "AUD/USD", category: "forex" },
  { value: "USDCAD", label: "USD/CAD", category: "forex" },
  { value: "NZDUSD", label: "NZD/USD", category: "forex" },
  { value: "USDCHF", label: "USD/CHF", category: "forex" },
  // Forex Cross
  { value: "EURJPY", label: "EUR/JPY", category: "forex" },
  { value: "GBPJPY", label: "GBP/JPY", category: "forex" },
  { value: "EURGBP", label: "EUR/GBP", category: "forex" },
  { value: "AUDCAD", label: "AUD/CAD", category: "forex" },
  { value: "AUDCHF", label: "AUD/CHF", category: "forex" },
  { value: "AUDJPY", label: "AUD/JPY", category: "forex" },
  { value: "AUDNZD", label: "AUD/NZD", category: "forex" },
  { value: "EURAUD", label: "EUR/AUD", category: "forex" },
  { value: "EURCAD", label: "EUR/CAD", category: "forex" },
  { value: "EURCHF", label: "EUR/CHF", category: "forex" },
  { value: "EURNZD", label: "EUR/NZD", category: "forex" },
  { value: "GBPAUD", label: "GBP/AUD", category: "forex" },
  { value: "GBPCAD", label: "GBP/CAD", category: "forex" },
  { value: "GBPCHF", label: "GBP/CHF", category: "forex" },
  { value: "GBPNZD", label: "GBP/NZD", category: "forex" },
  { value: "NZDCAD", label: "NZD/CAD", category: "forex" },
  { value: "NZDCHF", label: "NZD/CHF", category: "forex" },
  { value: "NZDJPY", label: "NZD/JPY", category: "forex" },
  { value: "CADCHF", label: "CAD/CHF", category: "forex" },
  { value: "CADJPY", label: "CAD/JPY", category: "forex" },
  { value: "CHFJPY", label: "CHF/JPY", category: "forex" },
  // Metals
  { value: "XAUUSD", label: "XAU/USD (Gold)", category: "metals" },
  { value: "XAGUSD", label: "XAG/USD (Silver)", category: "metals" },
  // Energy
  { value: "USOIL", label: "US Oil", category: "metals" },
  // Crypto
  { value: "BTCUSD", label: "BTC/USD", category: "crypto" },
  { value: "ETHUSD", label: "ETH/USD", category: "crypto" },
  { value: "SOLUSD", label: "SOL/USD", category: "crypto" },
  // Indices
  { value: "US30", label: "US30 (Dow)", category: "indices" },
  { value: "US100", label: "US100 (Nasdaq)", category: "indices" },
  { value: "US500", label: "US500 (S&P)", category: "indices" },
  { value: "NAS100", label: "NAS100", category: "indices" },
  { value: "SPX500", label: "SPX500", category: "indices" },
];

// Per-firm symbol availability (verified from MT5 account)
const FIRM_SYMBOLS: Record<string, string[]> = {
  ftmo: [
    // Verified: 49 symbols from FTMO Free Trial MT5 (OANDA-Demo-1)
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF",
    "EURJPY", "GBPJPY", "EURGBP", "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD",
    "EURAUD", "EURCAD", "EURCHF", "EURNZD",
    "GBPAUD", "GBPCAD", "GBPCHF", "GBPNZD",
    "NZDCAD", "NZDCHF", "NZDJPY", "CADCHF", "CADJPY", "CHFJPY",
    "XAUUSD", "XAGUSD", "USOIL",
    "BTCUSD",
    "US30", "US100", "US500",
  ],
  topstep: [
    "US30", "US100", "US500",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "XAUUSD",
  ],
  cryptofundtrader: [
    "BTCUSD", "ETHUSD", "SOLUSD",
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "XAUUSD",
    "US30", "US100",
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
