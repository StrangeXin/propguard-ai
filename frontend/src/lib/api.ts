// Single fetch wrapper. Attaches JWT when present, always sends cookies
// so the anon_session_id cookie flows with anonymous requests, and routes
// 402/403 through a global error handler (mounted by UpgradeModal).

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export type ApiError = {
  status: number;
  code?: string;
  message?: string;
  detail?: Record<string, unknown>;
};

type ApiErrorHandler = (error: ApiError) => void;

let _onError: ApiErrorHandler = () => {};

export function setApiErrorHandler(fn: ApiErrorHandler) {
  _onError = fn;
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = typeof window !== "undefined"
    ? localStorage.getItem("propguard-token")
    : null;

  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include", // send anon_session_id cookie
  });

  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    const detail = (data as { detail?: unknown })?.detail;
    const detailObj = detail && typeof detail === "object"
      ? (detail as Record<string, unknown>)
      : undefined;
    const code = detailObj && typeof detailObj.code === "string"
      ? (detailObj.code as string)
      : undefined;
    const message = typeof detail === "string"
      ? detail
      : (detailObj?.message as string | undefined);

    _onError({ status: res.status, code, message, detail: detailObj });

    const err = new Error(`API ${res.status}: ${message ?? "request failed"}`);
    Object.assign(err, { status: res.status, code, detail: detailObj });
    throw err;
  }

  return data as T;
}
