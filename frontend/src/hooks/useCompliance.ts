"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { AccountState, ComplianceReport } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface UseComplianceOptions {
  accountId: string;
  firmName: string;
  accountSize: number;
  enabled?: boolean;
}

interface UseComplianceReturn {
  account: AccountState | null;
  compliance: ComplianceReport | null;
  connected: boolean;
  error: string | null;
  reconnecting: boolean;
  brokerConnecting: boolean;
}

export function useCompliance({
  accountId,
  firmName,
  accountSize,
  enabled = true,
}: UseComplianceOptions): UseComplianceReturn {
  const [account, setAccount] = useState<AccountState | null>(null);
  const [compliance, setCompliance] = useState<ComplianceReport | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [brokerConnecting, setBrokerConnecting] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const pollTimer = useRef<NodeJS.Timeout | null>(null);
  const intentionalClose = useRef(false);
  const usingPolling = useRef(false);
  const wsFailCount = useRef(0);

  // HTTP polling fallback
  const poll = useCallback(async () => {
    if (!enabled || !accountId) return;
    try {
      const res = await fetch(
        `${API_BASE}/api/accounts/${accountId}/compliance?firm_name=${firmName}&account_size=${accountSize}`
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
      }
    } catch {
      // silently retry
    }
  }, [accountId, firmName, accountSize, enabled]);

  const startPolling = useCallback(() => {
    if (pollTimer.current) return;
    usingPolling.current = true;
    poll(); // immediate first fetch
    pollTimer.current = setInterval(poll, 3000);
  }, [poll]);

  const stopPolling = () => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
    usingPolling.current = false;
  };

  // WebSocket connection
  const connectWs = useCallback(() => {
    if (!enabled || !accountId) return;

    // If WS failed 3+ times, stay on polling
    if (wsFailCount.current >= 3) {
      startPolling();
      return;
    }

    const wsUrl = API_BASE.replace("http", "ws");
    const url = `${wsUrl}/ws/compliance/${accountId}?firm_name=${firmName}&account_size=${accountSize}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      const wsTimeout = setTimeout(() => {
        // If WS doesn't open within 5 seconds, fallback to polling
        if (ws.readyState !== WebSocket.OPEN) {
          ws.close();
          wsFailCount.current += 1;
          startPolling();
        }
      }, 5000);

      ws.onopen = () => {
        clearTimeout(wsTimeout);
        setConnected(true);
        setError(null);
        setReconnecting(false);
        wsFailCount.current = 0;
        stopPolling(); // stop polling if WS connects
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "compliance_update") {
            setBrokerConnecting(false);
            setAccount(data.account);
            setCompliance(data.compliance);
          } else if (data.type === "broker_connecting") {
            setBrokerConnecting(true);
          }
        } catch {
          // ignore
        }
      };

      ws.onclose = () => {
        clearTimeout(wsTimeout);
        setConnected(false);
        wsRef.current = null;

        if (intentionalClose.current) {
          intentionalClose.current = false;
          return;
        }

        wsFailCount.current += 1;
        // Fallback to polling after WS fails
        startPolling();
      };

      ws.onerror = () => {
        clearTimeout(wsTimeout);
        wsFailCount.current += 1;
      };
    } catch {
      // WebSocket constructor can throw in some environments
      wsFailCount.current += 1;
      startPolling();
    }
  }, [accountId, firmName, accountSize, enabled, startPolling]);

  useEffect(() => {
    // Cleanup previous
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
    if (wsRef.current) {
      intentionalClose.current = true;
      wsRef.current.close();
      wsRef.current = null;
    }

    // Reset WS fail count on param change
    wsFailCount.current = 0;
    usingPolling.current = false;

    // Try WebSocket first, auto-fallback to polling
    connectWs();

    return () => {
      stopPolling();
      if (wsRef.current) {
        intentionalClose.current = true;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connectWs]);

  return { account, compliance, connected, error, reconnecting, brokerConnecting };
}

export async function fetchFirms() {
  const res = await fetch(`${API_BASE}/api/firms`);
  if (!res.ok) throw new Error("Failed to fetch firms");
  return res.json();
}

export async function fetchCompliance(
  accountId: string,
  firmName: string,
  accountSize: number
) {
  const res = await fetch(
    `${API_BASE}/api/accounts/${accountId}/compliance?firm_name=${firmName}&account_size=${accountSize}`
  );
  if (!res.ok) throw new Error("Failed to fetch compliance");
  return res.json();
}
