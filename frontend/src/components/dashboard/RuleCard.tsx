"use client";

import type { RuleCheckResult, AlertLevel } from "@/lib/types";
import { useI18n } from "@/i18n/context";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";

const alertStyles: Record<AlertLevel, { bg: string; text: string; badge: string; progress: string }> = {
  safe: { bg: "bg-green-950/20 border-green-900/30", text: "text-green-400", badge: "bg-green-900 text-green-300", progress: "[&>div]:bg-green-500" },
  warning: { bg: "bg-yellow-950/20 border-yellow-900/30", text: "text-yellow-400", badge: "bg-yellow-900 text-yellow-300", progress: "[&>div]:bg-yellow-500" },
  critical: { bg: "bg-orange-950/20 border-orange-900/30", text: "text-orange-400", badge: "bg-orange-900 text-orange-300", progress: "[&>div]:bg-orange-500" },
  danger: { bg: "bg-red-950/20 border-red-900/30", text: "text-red-400", badge: "bg-red-900 text-red-300", progress: "[&>div]:bg-red-500" },
  breached: { bg: "bg-red-950/30 border-red-800/50", text: "text-red-300", badge: "bg-red-800 text-red-200", progress: "[&>div]:bg-red-600" },
};

const DOLLAR_RULES = new Set(["daily_loss", "max_drawdown", "profit_target"]);
const INFO_RULES = new Set(["news_restriction", "best_day_rule"]);

export function RuleCard({ check }: { check: RuleCheckResult }) {
  const { locale } = useI18n();
  const style = alertStyles[check.alert_level];

  const labels: Record<string, string> = {
    daily_loss: locale === "zh" ? "每日亏损限额" : "Daily Loss Limit",
    max_drawdown: locale === "zh" ? "最大回撤" : "Max Drawdown",
    position_size: locale === "zh" ? "仓位限制" : "Position Size",
    min_trading_days: locale === "zh" ? "最低交易天数" : "Min Trading Days",
    news_restriction: locale === "zh" ? "新闻交易限制" : "News Restriction",
    trading_hours: locale === "zh" ? "交易时段" : "Trading Hours",
    leverage: locale === "zh" ? "杠杆限制" : "Leverage Limit",
    time_limit: locale === "zh" ? "交易期限" : "Trading Period",
    profit_target: locale === "zh" ? "盈利目标" : "Profit Target",
    best_day_rule: locale === "zh" ? "最佳日规则" : "Best Day Rule",
  };

  const isDollar = DOLLAR_RULES.has(check.rule_type);
  const isInfo = INFO_RULES.has(check.rule_type);
  const isProfit = check.rule_type === "profit_target";

  // Calculate progress bar percentage
  let progressPct = 0;
  if (isDollar && check.limit_value > 0) {
    if (isProfit) {
      progressPct = Math.min(check.remaining_pct, 100); // progress towards target
    } else {
      progressPct = Math.min((check.current_value / check.limit_value) * 100, 100); // used
    }
  } else if (check.rule_type === "min_trading_days" && check.limit_value > 0) {
    progressPct = Math.min((check.current_value / check.limit_value) * 100, 100);
  }

  // Format display values
  const formatVal = (v: number) => {
    if (isDollar) return `$${v.toLocaleString("en", { maximumFractionDigits: 0 })}`;
    return v.toFixed(0);
  };

  return (
    <div className={`${style.bg} border rounded-lg p-3 space-y-2`}>
      {/* Header: label + badge */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-200">
          {labels[check.rule_type] || check.rule_type}
        </span>
        <Badge className={`${style.badge} text-[10px] px-1.5 py-0`}>
          {check.alert_level.toUpperCase()}
        </Badge>
      </div>

      {/* Info-only rules (news, best day) */}
      {isInfo && (
        <p className="text-xs text-zinc-400">{check.message}</p>
      )}

      {/* Progress rules (daily loss, drawdown, profit target) */}
      {isDollar && check.limit_value > 0 && (
        <>
          <Progress
            value={progressPct}
            className={`h-1.5 bg-zinc-800 ${isProfit ? "[&>div]:bg-blue-500" : style.progress}`}
          />
          <div className="flex justify-between text-xs">
            <span className={`font-mono ${style.text}`}>
              {isProfit ? formatVal(check.current_value) : formatVal(check.current_value)}
            </span>
            <span className="text-zinc-500 font-mono">
              {isProfit
                ? `${locale === "zh" ? "目标" : "target"} ${formatVal(check.limit_value)}`
                : `${locale === "zh" ? "剩余" : "remaining"} ${formatVal(check.remaining)}`
              }
            </span>
          </div>
        </>
      )}

      {/* Day-count rules (min trading days, time limit) */}
      {check.rule_type === "min_trading_days" && (
        <>
          <Progress
            value={progressPct}
            className="h-1.5 bg-zinc-800 [&>div]:bg-blue-500"
          />
          <div className="flex justify-between text-xs">
            <span className="font-mono text-zinc-300">
              {check.current_value.toFixed(0)} {locale === "zh" ? "天" : "days"}
            </span>
            <span className="text-zinc-500 font-mono">
              {locale === "zh" ? "需要" : "need"} {check.limit_value.toFixed(0)}
            </span>
          </div>
        </>
      )}

      {check.rule_type === "time_limit" && check.limit_value > 0 && (
        <div className="flex justify-between text-xs">
          <span className="font-mono text-zinc-300">
            {locale === "zh" ? "第" : "Day"} {Math.max(check.current_value, 0).toFixed(0)}
          </span>
          <span className="text-zinc-500 font-mono">
            {check.remaining.toFixed(0)} {locale === "zh" ? "天剩余" : "days left"}
          </span>
        </div>
      )}

      {check.rule_type === "time_limit" && check.limit_value === 0 && (
        <p className="text-xs text-zinc-500">{check.message}</p>
      )}

      {/* Trading hours / leverage */}
      {(check.rule_type === "trading_hours" || check.rule_type === "leverage") && (
        <p className="text-xs text-zinc-400">{check.message}</p>
      )}

      {/* Position size */}
      {check.rule_type === "position_size" && (
        <>
          <Progress
            value={progressPct}
            className={`h-1.5 bg-zinc-800 ${style.progress}`}
          />
          <div className="flex justify-between text-xs">
            <span className={`font-mono ${style.text}`}>
              {check.current_value.toFixed(1)} {locale === "zh" ? "合约" : "contracts"}
            </span>
            <span className="text-zinc-500 font-mono">
              {locale === "zh" ? "最大" : "max"} {check.limit_value.toFixed(0)}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
