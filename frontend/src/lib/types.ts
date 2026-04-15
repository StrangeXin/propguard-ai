export type AlertLevel = "safe" | "warning" | "critical" | "danger" | "breached";

export interface Position {
  symbol: string;
  side: string;
  size: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  opened_at: string;
}

export interface AccountState {
  account_id: string;
  firm_name: string;
  account_size: number;
  initial_balance: number;
  current_balance: number;
  current_equity: number;
  daily_pnl: number;
  total_pnl: number;
  equity_high_watermark: number;
  open_positions: Position[];
  trading_days_count: number;
  challenge_start_date: string | null;
  last_updated: string;
}

export interface RuleCheckResult {
  rule_type: string;
  rule_description: string;
  current_value: number;
  limit_value: number;
  remaining: number;
  remaining_pct: number;
  alert_level: AlertLevel;
  message: string;
}

export interface ComplianceReport {
  account_id: string;
  firm_name: string;
  timestamp: string;
  overall_status: AlertLevel;
  checks: RuleCheckResult[];
  next_reset: string | null;
}

export interface ComplianceUpdate {
  type: "compliance_update";
  account: AccountState;
  compliance: ComplianceReport;
}

export interface FirmInfo {
  firm_name: string;
  markets: string[];
  evaluation_type: string;
  version: number;
  effective_date: string;
  account_sizes: number[];
}
