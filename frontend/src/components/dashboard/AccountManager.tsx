"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/i18n/context";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface RegisteredAccount {
  account_id: string;
  firm_name: string;
  account_size: number;
  broker_type: string;
  label: string;
  created_at: string;
}

const brokerLabels: Record<string, string> = {
  metaapi: "MT5 (MetaApi)",
  okx: "OKX",
  mock: "Demo",
};

export function AccountManager({
  onSelectAccount,
}: {
  onSelectAccount: (firmName: string, accountSize: number, accountId: string) => void;
}) {
  const { t } = useI18n();
  const [accounts, setAccounts] = useState<RegisteredAccount[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [newId, setNewId] = useState("");
  const [newFirm, setNewFirm] = useState("ftmo");
  const [newSize, setNewSize] = useState("100000");
  const [newBroker, setNewBroker] = useState("metaapi");
  const [newLabel, setNewLabel] = useState("");

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/accounts`);
      const data = await res.json();
      setAccounts(data.accounts || []);
    } catch {
      // silently fail
    }
  }, []);

  useEffect(() => { fetchAccounts(); }, [fetchAccounts]);

  const addAccount = async () => {
    if (!newId.trim()) return;
    await fetch(`${API_BASE}/api/accounts/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        account_id: newId,
        firm_name: newFirm,
        account_size: parseInt(newSize),
        broker_type: newBroker,
        label: newLabel || newId,
      }),
    });
    setShowAdd(false);
    setNewId("");
    setNewLabel("");
    fetchAccounts();
  };

  const removeAccount = async (id: string) => {
    await fetch(`${API_BASE}/api/accounts/${id}`, { method: "DELETE" });
    fetchAccounts();
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">
          {t("accounts.title")}
        </h2>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="text-xs text-zinc-500 hover:text-white transition-colors"
        >
          {showAdd ? t("accounts.cancel") : t("accounts.add")}
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <Card className="bg-zinc-900 border-0">
          <CardContent className="pt-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-zinc-500 block mb-1">{t("accounts.id")}</label>
                <input
                  value={newId}
                  onChange={(e) => setNewId(e.target.value)}
                  placeholder="my-ftmo-001"
                  className="w-full bg-zinc-800 text-white rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-600"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">{t("accounts.label")}</label>
                <input
                  value={newLabel}
                  onChange={(e) => setNewLabel(e.target.value)}
                  placeholder="FTMO Challenge #1"
                  className="w-full bg-zinc-800 text-white rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-600"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">{t("accounts.firm")}</label>
                <select
                  value={newFirm}
                  onChange={(e) => setNewFirm(e.target.value)}
                  className="w-full bg-zinc-800 text-white rounded px-3 py-1.5 text-sm focus:outline-none"
                >
                  <option value="ftmo">FTMO</option>
                  <option value="topstep">TopStep</option>
                  <option value="breakout">Breakout</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">{t("accounts.size")}</label>
                <input
                  type="number"
                  value={newSize}
                  onChange={(e) => setNewSize(e.target.value)}
                  className="w-full bg-zinc-800 text-white rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-zinc-600"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">{t("accounts.broker")}</label>
                <select
                  value={newBroker}
                  onChange={(e) => setNewBroker(e.target.value)}
                  className="w-full bg-zinc-800 text-white rounded px-3 py-1.5 text-sm focus:outline-none"
                >
                  <option value="metaapi">MT5 (MetaApi)</option>
                  <option value="okx">OKX</option>
                  <option value="mock">Demo (Mock)</option>
                </select>
              </div>
              <div className="flex items-end">
                <button
                  onClick={addAccount}
                  disabled={!newId.trim()}
                  className="w-full px-4 py-1.5 bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white text-sm rounded transition-colors"
                >
                  {t("accounts.addBtn")}
                </button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Account list */}
      {accounts.length > 0 && (
        <div className="space-y-2">
          {accounts.map((acc) => (
            <div
              key={acc.account_id}
              className="bg-zinc-900 rounded-lg px-4 py-2.5 flex items-center justify-between cursor-pointer hover:bg-zinc-800 transition-colors"
              onClick={() => onSelectAccount(acc.firm_name, acc.account_size, acc.account_id)}
            >
              <div className="flex items-center gap-3">
                <div>
                  <p className="text-sm text-white font-medium">{acc.label || acc.account_id}</p>
                  <p className="text-xs text-zinc-500">
                    {acc.firm_name.toUpperCase()} &middot; ${acc.account_size.toLocaleString()}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge className="bg-zinc-800 text-zinc-400 text-[10px]">
                  {brokerLabels[acc.broker_type] || acc.broker_type}
                </Badge>
                <button
                  onClick={(e) => { e.stopPropagation(); removeAccount(acc.account_id); }}
                  className="text-zinc-600 hover:text-red-400 text-xs transition-colors"
                >
                  x
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {accounts.length === 0 && !showAdd && (
        <div className="bg-zinc-900 rounded-lg p-4 text-center text-zinc-600 text-sm">
          {t("accounts.empty")}
        </div>
      )}
    </div>
  );
}
