"use client";

import type { RuleCheckResult, AlertLevel } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useI18n } from "@/i18n/context";

const alertStyles: Record<AlertLevel, { bg: string; text: string; badge: string; progress: string }> = {
  safe: { bg: "bg-green-950/30", text: "text-green-400", badge: "bg-green-900 text-green-300", progress: "[&>div]:bg-green-500" },
  warning: { bg: "bg-yellow-950/30", text: "text-yellow-400", badge: "bg-yellow-900 text-yellow-300", progress: "[&>div]:bg-yellow-500" },
  critical: { bg: "bg-orange-950/30", text: "text-orange-400", badge: "bg-orange-900 text-orange-300", progress: "[&>div]:bg-orange-500" },
  danger: { bg: "bg-red-950/30", text: "text-red-400", badge: "bg-red-900 text-red-300", progress: "[&>div]:bg-red-500" },
  breached: { bg: "bg-red-950/50", text: "text-red-300", badge: "bg-red-800 text-red-200", progress: "[&>div]:bg-red-600" },
};

export function RuleCard({ check }: { check: RuleCheckResult }) {
  const { t, locale } = useI18n();
  const style = alertStyles[check.alert_level];
  const usedPct = Math.min(100 - check.remaining_pct, 100);

  const ruleLabels: Record<string, string> = {
    daily_loss: t("compliance.dailyLoss"),
    max_drawdown: t("compliance.maxDrawdown"),
    position_size: t("compliance.positionSize"),
    min_trading_days: t("compliance.tradingDays"),
    news_restriction: locale === "zh" ? "新闻限制" : "News Restriction",
    trading_hours: locale === "zh" ? "交易时段" : "Trading Hours",
    leverage: locale === "zh" ? "杠杆限制" : "Leverage",
    time_limit: locale === "zh" ? "时间限制" : "Time Limit",
  };

  return (
    <Card className={`${style.bg} border-0`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-zinc-300">
            {ruleLabels[check.rule_type] || check.rule_type}
          </CardTitle>
          <Badge className={`${style.badge} text-xs font-mono`}>
            {check.alert_level.toUpperCase()}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">{t("compliance.used")}</span>
          <span className={`font-mono font-bold ${style.text}`}>
            ${check.current_value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>
        <Progress value={usedPct} className={`h-2 bg-zinc-800 ${style.progress}`} />
        <div className="flex justify-between text-xs text-zinc-500">
          <span>
            {t("compliance.remaining")}: ${check.remaining.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span>{t("compliance.limit")}: ${check.limit_value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        </div>
        <p className="text-xs text-zinc-400 leading-relaxed">{check.message}</p>
      </CardContent>
    </Card>
  );
}
