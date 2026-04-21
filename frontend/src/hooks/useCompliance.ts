"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { AccountState, ComplianceReport, RuleFreshness } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const POLL_INTERVAL = 10000; // 10s, reduced from 3s

interface UseComplianceOptions {
  accountId: string;
  firmName: string;
  accountSize: number;
  evaluationType?: string;
  enabled?: boolean;
}

interface UseComplianceReturn {
  account: AccountState | null;
  compliance: ComplianceReport | null;
  ruleFreshness: RuleFreshness | null;
  connected: boolean;
  error: string | null;
  reconnecting: boolean;
  brokerConnecting: boolean;
}

export function useCompliance({
  accountId,
  firmName,
  accountSize,
  evaluationType,
  enabled = true,
}: UseComplianceOptions): UseComplianceReturn {
  const evalParam = evaluationType ? `&evaluation_type=${evaluationType}` : "";
  const [account, setAccount] = useState<AccountState | null>(null);
  const [compliance, setCompliance] = useState<ComplianceReport | null>(null);
  const [ruleFreshness, setRuleFreshness] = useState<RuleFreshness | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [brokerConnecting, setBrokerConnecting] = useState(false);

  // REST fetch — always works, used as primary + fallback
  const fetchRest = useCallback(async () => {
    if (!enabled || !accountId) return;
    try {
      const res = await fetch(
        `${API_BASE}/api/accounts/${accountId}/compliance?firm_name=${firmName}&account_size=${accountSize}${evalParam}`
      );
      const data = await res.json();
      if (data.status === "connecting") {
        setBrokerConnecting(true);
      } else if (data.account) {
        setBrokerConnecting(false);
        setConnected(true);
        setError(null);
        setReconnecting(false);
        setAccount(data.account);
        setCompliance(data.compliance);
        if (data.rule_freshness) setRuleFreshness(data.rule_freshness);
      }
    } catch {
      // silent
    }
  }, [accountId, firmName, accountSize, evaluationType, enabled]);

  useEffect(() => {
    // Clear old data immediately on param change
    setAccount(null);
    setCompliance(null);
    setConnected(false);
    setBrokerConnecting(false);

    if (!enabled || !accountId) return;

    // 1. Immediate REST fetch — get data on screen ASAP
    fetchRest();

    // 2. Start polling as reliable baseline
    const pollInterval = setInterval(fetchRest, POLL_INTERVAL);

    // 3. Try WebSocket for real-time upgrade
    let ws: WebSocket | null = null;
    let wsTimeout: NodeJS.Timeout | null = null;

    const tryWs = () => {
      const wsUrl = API_BASE.replace("http", "ws");
      const url = `${wsUrl}/ws/compliance/${accountId}?firm_name=${firmName}&account_size=${accountSize}${evalParam}`;

      try {
        ws = new WebSocket(url);

        // Give WS 5 seconds to connect, otherwise stay on polling
        wsTimeout = setTimeout(() => {
          if (ws && ws.readyState !== WebSocket.OPEN) {
            ws.close();
            ws = null;
          }
        }, 5000);

        ws.onopen = () => {
          if (wsTimeout) clearTimeout(wsTimeout);
          // WS connected — stop polling, use WS
          clearInterval(pollInterval);
          setConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === "compliance_update") {
              setBrokerConnecting(false);
              setAccount(data.account);
              setCompliance(data.compliance);
              if (data.rule_freshness) setRuleFreshness(data.rule_freshness);
            } else if (data.type === "broker_connecting") {
              setBrokerConnecting(true);
            }
          } catch { /* ignore */ }
        };

        ws.onclose = () => {
          if (wsTimeout) clearTimeout(wsTimeout);
          ws = null;
          // Don't restart polling here — the interval is already running
          // unless it was cleared when WS connected
          setConnected(false);
        };

        ws.onerror = () => {
          // onclose will fire
        };
      } catch {
        // WS not available, polling continues
      }
    };

    tryWs();

    // Cleanup
    return () => {
      clearInterval(pollInterval);
      if (wsTimeout) clearTimeout(wsTimeout);
      if (ws) {
        ws.close();
        ws = null;
      }
    };
  }, [accountId, firmName, accountSize, evaluationType, enabled, fetchRest]);

  return { account, compliance, ruleFreshness, connected, error, reconnecting, brokerConnecting };
}

export async function fetchFirms() {
  const res = await fetch(`${API_BASE}/api/firms`);
  if (!res.ok) throw new Error("Failed to fetch firms");
  return res.json();
}

export async function fetchCompliance(
  accountId: string,
  firmName: string,
  accountSize: number,
  evaluationType?: string
) {
  const ep = evaluationType ? `&evaluation_type=${evaluationType}` : "";
  const res = await fetch(
    `${API_BASE}/api/accounts/${accountId}/compliance?firm_name=${firmName}&account_size=${accountSize}${ep}`
  );
  if (!res.ok) throw new Error("Failed to fetch compliance");
  return res.json();
}
