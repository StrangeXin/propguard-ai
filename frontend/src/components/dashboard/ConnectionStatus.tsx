"use client";

import { useI18n } from "@/i18n/context";

export function ConnectionStatus({
  connected,
  reconnecting,
  error,
}: {
  connected: boolean;
  reconnecting: boolean;
  error: string | null;
}) {
  const { t } = useI18n();

  if (connected) {
    return (
      <div className="flex items-center gap-2 text-xs text-green-400">
        <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
        {t("status.live")}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-950/50 border border-red-800 rounded-lg px-4 py-2 text-sm text-red-300">
        {error}
      </div>
    );
  }

  if (reconnecting) {
    return (
      <div className="bg-yellow-950/50 border border-yellow-800 rounded-lg px-4 py-2 text-sm text-yellow-300">
        {t("status.reconnecting")}
      </div>
    );
  }

  // Brief disconnection during param switch — show subtle indicator, no banner
  return (
    <div className="flex items-center gap-2 text-xs text-yellow-500">
      <span className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
      {t("status.connecting")}
    </div>
  );
}
