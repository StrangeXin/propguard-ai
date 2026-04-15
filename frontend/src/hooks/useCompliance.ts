"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { ComplianceUpdate, AccountState, ComplianceReport } from "@/lib/types";

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
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null);
  // Track whether the close was intentional (param change) vs unexpected
  const intentionalClose = useRef(false);

  const connect = useCallback(() => {
    if (!enabled || !accountId) return;

    const wsUrl = API_BASE.replace("http", "ws");
    const url = `${wsUrl}/ws/compliance/${accountId}?firm_name=${firmName}&account_size=${accountSize}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setError(null);
      setReconnecting(false);
      reconnectAttempt.current = 0;
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
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;

      // If we closed intentionally (param change), don't show reconnecting
      // and don't trigger backoff — the new connect() is already queued
      if (intentionalClose.current) {
        intentionalClose.current = false;
        return;
      }

      // Unexpected close: exponential backoff reconnection
      if (enabled) {
        const delay = Math.min(
          1000 * Math.pow(2, reconnectAttempt.current),
          30000
        );
        setReconnecting(true);
        reconnectAttempt.current += 1;

        reconnectTimer.current = setTimeout(() => {
          connect();
        }, delay);
      }
    };

    ws.onerror = () => {
      setError("Connection error. Retrying...");
    };
  }, [accountId, firmName, accountSize, enabled]);

  useEffect(() => {
    // Close previous connection cleanly before opening new one
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      intentionalClose.current = true;
      wsRef.current.close();
      wsRef.current = null;
    }
    // Keep old data visible — don't clear account/compliance here
    // New data will replace it once the new WS connects

    connect();

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        intentionalClose.current = true;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

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
