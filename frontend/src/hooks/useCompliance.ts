"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { AccountState, ComplianceReport } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const POLL_INTERVAL = 3000;
const WS_MAX_RETRIES = 5;

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
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const intentionalClose = useRef(false);
  const wsRetries = useRef(0);
  const modeRef = useRef<"ws" | "poll">("ws");

  // REST poll
  const fetchOnce = useCallback(async () => {
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
      // silent
    }
  }, [accountId, firmName, accountSize]);

  const startPoll = useCallback(() => {
    if (pollRef.current) return;
    modeRef.current = "poll";
    fetchOnce();
    pollRef.current = setInterval(fetchOnce, POLL_INTERVAL);
  }, [fetchOnce]);

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const cleanup = () => {
    stopPoll();
    if (wsRef.current) {
      intentionalClose.current = true;
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  // WebSocket
  const connectWs = useCallback(() => {
    if (!enabled || !accountId) return;

    if (wsRetries.current >= WS_MAX_RETRIES) {
      // Give up WS, use polling permanently
      startPoll();
      return;
    }

    const wsUrl = API_BASE.replace("http", "ws");
    const url = `${wsUrl}/ws/compliance/${accountId}?firm_name=${firmName}&account_size=${accountSize}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;
      modeRef.current = "ws";

      ws.onopen = () => {
        setConnected(true);
        setError(null);
        setReconnecting(false);
        wsRetries.current = 0;
        stopPoll();
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
        } catch { /* ignore */ }
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (intentionalClose.current) {
          intentionalClose.current = false;
          return;
        }
        setConnected(false);
        wsRetries.current += 1;

        if (wsRetries.current >= WS_MAX_RETRIES) {
          // Switch to polling
          startPoll();
        } else {
          // Retry WS with backoff
          setReconnecting(true);
          const delay = Math.min(1000 * Math.pow(2, wsRetries.current), 15000);
          setTimeout(connectWs, delay);
        }
      };

      ws.onerror = () => {
        // onclose will fire after this
      };
    } catch {
      wsRetries.current += 1;
      startPoll();
    }
  }, [accountId, firmName, accountSize, enabled, startPoll]);

  useEffect(() => {
    cleanup();
    // Clear stale data from previous firm/account
    setAccount(null);
    setCompliance(null);
    setBrokerConnecting(false);
    wsRetries.current = 0;
    modeRef.current = "ws";
    connectWs();

    return cleanup;
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
