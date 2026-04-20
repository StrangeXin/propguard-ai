"use client";

import type { AccountState, AlertLevel } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/i18n/context";
import Link from "next/link";
import { useAuth } from "@/app/providers";
import { useLoginGate } from "@/hooks/useLoginGate";

const statusColors: Record<AlertLevel, string> = {
  safe: "bg-green-900 text-green-300",
  warning: "bg-yellow-900 text-yellow-300",
  critical: "bg-orange-900 text-orange-300",
  danger: "bg-red-900 text-red-300 animate-pulse",
  breached: "bg-red-800 text-red-200 animate-pulse",
};

export function AccountHeader({
  account,
  overallStatus,
  firmName,
  accountSize,
}: {
  account: AccountState;
  overallStatus: AlertLevel;
  firmName?: string;
  accountSize?: number;
}) {
  const { t } = useI18n();
  const { user, token } = useAuth();
  const { openGate } = useLoginGate();
  const pnlColor = account.total_pnl >= 0 ? "text-green-400" : "text-red-400";
  const dailyColor = account.daily_pnl >= 0 ? "text-green-400" : "text-red-400";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{t("app.title")}</h1>
          <p className="text-zinc-400 text-sm">
            {firmName || account.firm_name} &middot; ${(accountSize || account.account_size).toLocaleString()} {t("app.challenge")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {token && !user?.metaapi_account_id && (
            <Link
              href="/settings/broker"
              className="px-3 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white"
            >
              {t("auth.connect_your_account")}
            </Link>
          )}
          {!token && (
            <button
              onClick={() => openGate(t("auth.connect_your_account_cta"))}
              className="px-3 py-1.5 text-sm rounded bg-neutral-700 hover:bg-neutral-600 text-white"
            >
              {t("auth.login_to_connect")}
            </button>
          )}
          <Badge className={`text-sm px-3 py-1 ${statusColors[overallStatus]}`}>
            {overallStatus.toUpperCase()}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label={t("account.equity")} value={`$${account.current_equity.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <StatCard label={t("account.balance")} value={`$${account.current_balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <StatCard
          label={t("account.dailyPnl")}
          value={`${account.daily_pnl >= 0 ? "+" : ""}$${account.daily_pnl.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          className={dailyColor}
        />
        <StatCard
          label={t("account.totalPnl")}
          value={`${account.total_pnl >= 0 ? "+" : ""}$${account.total_pnl.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          className={pnlColor}
        />
      </div>
    </div>
  );
}

function StatCard({ label, value, className = "text-white" }: { label: string; value: string; className?: string }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-3">
      <p className="text-xs text-zinc-500 uppercase tracking-wider">{label}</p>
      <p className={`text-lg font-mono font-bold ${className}`}>{value}</p>
    </div>
  );
}
