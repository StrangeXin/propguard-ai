"use client";

import { useState, useEffect, useCallback, createContext, useContext } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface User {
  id: string;
  email: string;
  name: string;
  tier: string;
  telegram_chat_id: string | null;
}

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<string | null>;
  register: (email: string, password: string, name: string) => Promise<string | null>;
  logout: () => void;
}

export function useAuthState(): AuthState {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Load token from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem("propguard-token");
    if (saved) {
      setToken(saved);
      fetchMe(saved);
    } else {
      setLoading(false);
    }
  }, []);

  const fetchMe = async (t: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data.user);
        setToken(t);
      } else {
        localStorage.removeItem("propguard-token");
        setToken(null);
        setUser(null);
      }
    } catch {
      // offline
    } finally {
      setLoading(false);
    }
  };

  const login = useCallback(async (email: string, password: string): Promise<string | null> => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const err = await res.json();
        return err.detail || "Login failed";
      }
      const data = await res.json();
      localStorage.setItem("propguard-token", data.token);
      setToken(data.token);
      setUser(data.user);
      return null;
    } catch {
      return "Network error";
    }
  }, []);

  const register = useCallback(async (email: string, password: string, name: string): Promise<string | null> => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, name }),
      });
      if (!res.ok) {
        const err = await res.json();
        return err.detail || "Registration failed";
      }
      const data = await res.json();
      localStorage.setItem("propguard-token", data.token);
      setToken(data.token);
      setUser(data.user);
      return null;
    } catch {
      return "Network error";
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("propguard-token");
    setToken(null);
    setUser(null);
  }, []);

  return { user, token, loading, login, register, logout };
}
