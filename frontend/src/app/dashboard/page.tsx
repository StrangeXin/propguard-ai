"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { useAuth } from "../providers";
import { useCompliance } from "@/hooks/useCompliance";
import { AccountHeader } from "@/components/dashboard/AccountHeader";
import { RuleCard } from "@/components/dashboard/RuleCard";
import { ConnectionStatus } from "@/components/dashboard/ConnectionStatus";
import { SignalPanel } from "@/components/dashboard/SignalPanel";
import { BriefingPanel } from "@/components/dashboard/BriefingPanel";
import { PositionCalculator } from "@/components/dashboard/PositionCalculator";
import { KlineChart } from "@/components/dashboard/KlineChart";
import { AlertHistory } from "@/components/dashboard/AlertHistory";
import { AccountManager } from "@/components/dashboard/AccountManager";
import { ChallengeProgress } from "@/components/dashboard/ChallengeProgress";
import { TradingPanel } from "@/components/dashboard/TradingPanel";
import { LocaleSwitcher } from "@/components/dashboard/LocaleSwitcher";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";

const FIRMS = [
  { name: "ftmo", label: "FTMO", sizes: [10000, 25000, 50000, 100000, 200000] },
  { name: "topstep", label: "TopStep", sizes: [50000, 100000, 150000] },
  { name: "breakout", label: "Breakout", sizes: [5000, 10000, 25000, 50000, 100000] },
];

export default function Dashboard() {
  const { t } = useI18n();
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
    }
  }, [authLoading, user, router]);

  const [firmName, setFirmName] = useState("ftmo");
  const [accountSize, setAccountSize] = useState(100000);
  const [accountId, setAccountId] = useState("demo-001");
  const [selectedSymbol, setSelectedSymbol] = useState("BTCUSD");

  const firm = FIRMS.find((f) => f.name === firmName) || FIRMS[0];

  const { account, compliance, connected, error, reconnecting, brokerConnecting } = useCompliance({
    accountId,
    firmName,
    accountSize,
  });

  if (authLoading || !user) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" />
      </main>
    );
  }

  return (
    <main className="min-h-screen p-4 md:p-8 max-w-6xl mx-auto space-y-6">
      {/* Top bar */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <div className="flex gap-3">
          <Select value={firmName} onValueChange={(v) => { if (!v) return; setFirmName(v); const found = FIRMS.find(f => f.name === v); setAccountSize(found ? found.sizes[2] : 50000); }}>
            <SelectTrigger className="w-40 bg-zinc-900 border-zinc-800 text-white">
              <SelectValue placeholder="Select firm" />
            </SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-800">
              {FIRMS.map((f) => (
                <SelectItem key={f.name} value={f.name} className="text-white">{f.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={String(accountSize)} onValueChange={(v) => { if (v) setAccountSize(Number(v)); }}>
            <SelectTrigger className="w-36 bg-zinc-900 border-zinc-800 text-white">
              <SelectValue placeholder="Account size" />
            </SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-800">
              {firm.sizes.map((s) => (
                <SelectItem key={s} value={String(s)} className="text-white">${s.toLocaleString()}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-3">
          <LocaleSwitcher />
          <ConnectionStatus connected={connected} reconnecting={reconnecting} error={error} />
          {user && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-zinc-400">{user.name}</span>
              <button onClick={logout} className="text-zinc-600 hover:text-white transition-colors">
                Logout
              </button>
            </div>
          )}
        </div>
      </div>

      <Separator className="bg-zinc-800" />

      {/* Loading / Broker connecting */}
      {!account && !error && (
        <div className="flex items-center justify-center h-64 text-zinc-500">
          <div className="text-center space-y-3">
            <div className="w-8 h-8 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin mx-auto" />
            <p>{brokerConnecting ? t("status.brokerConnecting") : t("status.connecting")}</p>
          </div>
        </div>
      )}

      {/* Dashboard */}
      {account && compliance && (
        <>
          <AccountHeader account={account} overallStatus={compliance.overall_status} firmName={firmName} accountSize={accountSize} />

          <ChallengeProgress accountId={accountId} firmName={firmName} accountSize={accountSize} />

          <div className="space-y-3">
            <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
              {t("compliance.title")}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {compliance.checks.map((check, i) => (
                <RuleCard key={`${check.rule_type}-${i}`} check={check} />
              ))}
            </div>
          </div>

          <KlineChart symbol={selectedSymbol} onSymbolChange={setSelectedSymbol} />

          <div id="trading-panel">
            <TradingPanel symbol={selectedSymbol} onSymbolChange={setSelectedSymbol} />
          </div>

          <Separator className="bg-zinc-800" />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <BriefingPanel accountId={accountId} firmName={firmName} accountSize={accountSize} />
            <div className="space-y-6">
              <PositionCalculator equity={account.current_equity} />
              <AlertHistory accountId={accountId} />
            </div>
          </div>

          <Separator className="bg-zinc-800" />

          <SignalPanel onTrade={(sym, side) => {
            setSelectedSymbol(sym);
            // Scroll to trading panel
            document.getElementById("trading-panel")?.scrollIntoView({ behavior: "smooth" });
          }} />

          <Separator className="bg-zinc-800" />

          <AccountManager onSelectAccount={(f, s, id) => { setFirmName(f); setAccountSize(s); setAccountId(id); }} />

          {/* Footer */}
          <div className="text-xs text-zinc-600 text-center pt-4 space-y-1">
            <p>
              {t("footer.lastUpdated")}: {new Date(account.last_updated).toLocaleTimeString()} &middot;
              {t("footer.account")}: {account.account_id} &middot;
              {t("footer.highWatermark")}: ${account.equity_high_watermark.toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </p>
            <p>
              <a href="/docs" className="text-zinc-500 hover:text-white transition-colors underline underline-offset-2">
                {t("footer.docs")}
              </a>
            </p>
          </div>
        </>
      )}
    </main>
  );
}
