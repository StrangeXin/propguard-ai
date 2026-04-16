"use client";

import type { RuleCheckResult, AlertLevel } from "@/lib/types";
import { useI18n } from "@/i18n/context";
import { Progress } from "@/components/ui/progress";

const alertColors: Record<AlertLevel, { bg: string; text: string; dot: string; progress: string }> = {
  safe: { bg: "bg-green-950/20", text: "text-green-400", dot: "bg-green-500", progress: "[&>div]:bg-green-500" },
  warning: { bg: "bg-yellow-950/20", text: "text-yellow-400", dot: "bg-yellow-500", progress: "[&>div]:bg-yellow-500" },
  critical: { bg: "bg-orange-950/20", text: "text-orange-400", dot: "bg-orange-500", progress: "[&>div]:bg-orange-500" },
  danger: { bg: "bg-red-950/20", text: "text-red-400", dot: "bg-red-500", progress: "[&>div]:bg-red-500" },
  breached: { bg: "bg-red-950/30", text: "text-red-300", dot: "bg-red-600 animate-pulse", progress: "[&>div]:bg-red-600" },
};

// Rules that show dollar amounts vs other units
const DOLLAR_RULES = new Set(["daily_loss", "max_drawdown"]);
const HIDE_PROGRESS = new Set(["news_restriction", "time_limit"]);

export function RuleCard({ check }: { check: RuleCheckResult }) {
  const { t, locale } = useI18n();
  const style = alertColors[check.alert_level];

  const ruleLabels: Record<string, string> = {
    daily_loss: t("compliance.dailyLoss"),
    max_drawdown: t("compliance.maxDrawdown"),
    position_size: locale === "zh" ? "仓位大小" : "Position Size",
    min_trading_days: locale === "zh" ? "交易天数" : "Trading Days",
    news_restriction: locale === "zh" ? "新闻限制" : "News",
    trading_hours: locale === "zh" ? "交易时段" : "Hours",
    leverage: locale === "zh" ? "杠杆" : "Leverage",
    time_limit: locale === "zh" ? "时间限制" : "Time Limit",
  };

  const isDollar = DOLLAR_RULES.has(check.rule_type);
  const showProgress = !HIDE_PROGRESS.has(check.rule_type) && check.limit_value > 0;
  const usedPct = showProgress ? Math.min((1 - check.remaining_pct / 100) * 100, 100) : 0;

  const formatValue = (v: number) => {
    if (isDollar) return `$${v.toLocaleString("en", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
    if (check.rule_type === "min_trading_days") return `${v.toFixed(0)}d`;
    if (check.rule_type === "time_limit") return `${v.toFixed(0)}d`;
    if (check.rule_type === "position_size") return `${v.toFixed(1)}`;
    return `${v}`;
  };

  // Short status text
  const statusText = () => {
    if (check.rule_type === "news_restriction") return check.alert_level === "safe" ? "OK" : "Check";
    if (check.rule_type === "trading_hours") return check.alert_level === "safe" ? "OK" : "Weekend";
    if (check.rule_type === "leverage") return check.alert_level === "safe" ? "OK" : "Over";
    if (check.rule_type === "time_limit") {
      const days = Math.max(check.remaining, 0);
      return `${days.toFixed(0)}d left`;
    }
    if (check.rule_type === "min_trading_days") {
      return `${check.current_value.toFixed(0)}/${check.limit_value.toFixed(0)}`;
    }
    if (isDollar) {
      return `$${check.remaining.toLocaleString("en", { maximumFractionDigits: 0 })}`;
    }
    return `${check.remaining_pct.toFixed(0)}%`;
  };

  return (
    <div className={`${style.bg} rounded-lg px-4 py-3 flex items-center gap-3`}>
      {/* Status dot */}
      <div className={`w-2 h-2 rounded-full shrink-0 ${style.dot}`} />

      {/* Label */}
      <div className="flex-1 min-w-0">
        <span className="text-sm text-zinc-300">{ruleLabels[check.rule_type] || check.rule_type}</span>
      </div>

      {/* Progress bar (only for dollar rules) */}
      {showProgress && (
        <div className="w-24 shrink-0">
          <Progress value={usedPct} className={`h-1.5 bg-zinc-800 ${style.progress}`} />
        </div>
      )}

      {/* Value */}
      <span className={`text-sm font-mono font-bold shrink-0 ${style.text}`}>
        {statusText()}
      </span>
    </div>
  );
}
