"use client";

import { useState, useCallback, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/app/providers";
import { useLoginGate } from "@/hooks/useLoginGate";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface BriefingData {
  generated_at: string;
  firm_name: string;
  overall_status: string;
  source: string;
  sections?: {
    risk_status: string;
    todays_focus: string;
    recommendation: string;
  };
  briefing?: string; // AI-generated free-form
  signals_count: number;
}

export function BriefingPanel({
  accountId,
  firmName,
  accountSize,
}: {
  accountId: string;
  firmName: string;
  accountSize: number;
}) {
  const { t } = useI18n();
  const { token } = useAuth();
  const { openGate } = useLoginGate();
  const [briefing, setBriefing] = useState<BriefingData | null>(null);
  const [loading, setLoading] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);

  // Skip fetch entirely when not logged in
  useEffect(() => {
    if (!token) {
      setAuthRequired(true);
    }
  }, [token]);

  const generateBriefing = useCallback(async () => {
    if (!token) {
      setAuthRequired(true);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/accounts/${accountId}/briefing?firm_name=${firmName}&account_size=${accountSize}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.status === 401) {
        setAuthRequired(true);
        return;
      }
      const data = await res.json();
      setBriefing(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [accountId, firmName, accountSize, token]);

  const statusColor: Record<string, string> = {
    safe: "text-green-400",
    warning: "text-yellow-400",
    critical: "text-orange-400",
    danger: "text-red-400",
    breached: "text-red-300",
  };

  if (authRequired) {
    return (
      <div className="bg-zinc-900 rounded-lg p-6 text-center">
        <p className="text-zinc-400 mb-3">{t("auth.login_to_view_briefing")}</p>
        <button
          className="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white"
          onClick={() => openGate(t("auth.login_to_view_briefing"))}
        >
          {t("auth.login")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
          {t("briefing.title")}
        </h2>
        <button
          onClick={generateBriefing}
          disabled={loading}
          className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 text-white text-xs rounded-lg transition-colors"
        >
          {loading ? t("briefing.generating") : briefing ? t("briefing.refresh") : t("briefing.generate")}
        </button>
      </div>

      {!briefing && !loading && (
        <div className="bg-zinc-900 rounded-lg p-6 text-center text-zinc-500 text-sm">
          {t("briefing.placeholder")}
        </div>
      )}

      {loading && (
        <div className="bg-zinc-900 rounded-lg p-6 text-center text-zinc-500">
          <div className="w-6 h-6 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin mx-auto mb-2" />
          <p className="text-sm">{t("briefing.analyzing")}</p>
        </div>
      )}

      {briefing && !loading && (
        <Card className="bg-zinc-900 border-0">
          <CardContent className="pt-4 space-y-4">
            <div className="flex items-center justify-between text-xs">
              <Badge className="bg-zinc-800 text-zinc-400">
                {briefing.source === "ai" ? "AI Generated" : "Template"}
              </Badge>
              <span className="text-zinc-600">
                {new Date(briefing.generated_at).toLocaleTimeString()}
              </span>
            </div>

            {briefing.sections ? (
              <>
                <Section
                  title={t("briefing.riskStatus")}
                  content={briefing.sections.risk_status}
                  color={statusColor[briefing.overall_status] || "text-zinc-300"}
                />
                <Section
                  title={t("briefing.todaysFocus")}
                  content={briefing.sections.todays_focus}
                />
                <Section
                  title={t("briefing.recommendation")}
                  content={briefing.sections.recommendation}
                  highlight
                />
              </>
            ) : briefing.briefing ? (
              <div className="text-sm text-zinc-300 whitespace-pre-wrap leading-relaxed">
                {briefing.briefing}
              </div>
            ) : null}

            <p className="text-xs text-zinc-600">
              {briefing.signals_count} signals analyzed
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Section({
  title,
  content,
  color = "text-zinc-300",
  highlight = false,
}: {
  title: string;
  content: string;
  color?: string;
  highlight?: boolean;
}) {
  return (
    <div className={highlight ? "bg-zinc-800/50 rounded-lg p-3" : ""}>
      <p className="text-xs text-zinc-500 uppercase tracking-wider mb-1">{title}</p>
      <p className={`text-sm leading-relaxed ${color}`}>{content}</p>
    </div>
  );
}
