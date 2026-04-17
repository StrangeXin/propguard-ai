"use client";

import { useState, useEffect, useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/i18n/context";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface AlertRecord {
  timestamp: string;
  account_id: string;
  firm_name: string;
  rule_type: string;
  alert_level: string;
  message: string;
  remaining: number;
  remaining_pct: number;
}

const levelColors: Record<string, string> = {
  warning: "bg-yellow-900 text-yellow-300",
  critical: "bg-orange-900 text-orange-300",
  danger: "bg-red-900 text-red-300",
  breached: "bg-red-800 text-red-200",
};

const levelIcons: Record<string, string> = {
  warning: "⚠",
  critical: "🔴",
  danger: "🚨",
  breached: "💀",
};

export function AlertHistory({ accountId }: { accountId: string }) {
  const { t } = useI18n();
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [expanded, setExpanded] = useState(false);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/alerts/history?account_id=${accountId}&limit=20`);
      const data = await res.json();
      setAlerts(data.alerts || []);
    } catch {
      // silently fail
    }
  }, [accountId]);

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 30000); // 30s
    return () => clearInterval(interval);
  }, [fetchAlerts]);

  if (alerts.length === 0) {
    return (
      <div className="space-y-3">
        <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
          {t("alerts.title")}
        </h2>
        <div className="bg-zinc-900 rounded-lg p-4 text-center text-zinc-600 text-sm">
          {t("alerts.empty")}
        </div>
      </div>
    );
  }

  const displayed = expanded ? alerts : alerts.slice(0, 5);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
          {t("alerts.title")}
          <span className="ml-2 text-xs text-zinc-600">({alerts.length})</span>
        </h2>
        {alerts.length > 5 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-zinc-500 hover:text-white transition-colors"
          >
            {expanded ? t("alerts.showLess") : t("alerts.showAll")}
          </button>
        )}
      </div>

      <div className="space-y-2">
        {displayed.map((alert, i) => (
          <div key={`${alert.timestamp}-${i}`} className="bg-zinc-900 rounded-lg px-4 py-2.5 flex items-start gap-3">
            <span className="text-sm mt-0.5">{levelIcons[alert.alert_level] || "ℹ"}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <Badge className={`text-[10px] px-1.5 ${levelColors[alert.alert_level] || "bg-zinc-800 text-zinc-400"}`}>
                  {alert.alert_level.toUpperCase()}
                </Badge>
                <span className="text-[10px] text-zinc-600 font-mono">
                  {alert.rule_type.replace("_", " ")}
                </span>
                <span className="text-[10px] text-zinc-700 ml-auto">
                  {new Date(alert.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <p className="text-xs text-zinc-400 truncate">{alert.message}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
