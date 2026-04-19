# PR 3b: Hardening + Polish (post-public-launch)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the security/cost gaps the earlier reviews flagged (MetaApi ownership proof, IP-level anonymous abuse backstop, `/pricing` page so `UpgradeModal` actually upgrades, cost-ledger retention) and ship the remaining §11 conversion hooks so anonymous users see the "register / upgrade" prompts at the moments they matter.

**Architecture:** Two-file changes per concern. Ownership proof: user pastes a MetaApi user-level API token; server uses it (not the admin token) to fetch the account; if the account is reachable, we know the user controls the token. IP backstop: hash client IP on every `POST /api/ai-trade/tick`, increment daily counter in a new `ip_quota_usage` table, 402 at a global limit. Pricing page: new `/pricing` route reading plans + Stripe price IDs, renders "Upgrade to Pro" button hitting existing `/api/payments/checkout`. Conversion hooks: four small modals driven by frontend state or backend flags.

**Tech Stack:** same as prior PRs. New: `cryptography` for token encryption at rest (users bring their own API token → we store it AES-GCM encrypted).

**Spec reference:** `docs/superpowers/specs/2026-04-19-anonymous-sandbox-design.md` §11 items 2–5; PR 2b review I1; PR 3 review I1.

**Dependencies:** PRs 1, 2a, 2b, 3 landed on `main`.

**Scope for this plan:** PR 3b. After this lands we can credibly announce the public beta.

---

## File Structure

**New files:**
- `supabase/migrations/20260423000000_ip_quota_and_retention.sql` — `ip_quota_usage` table + retention prune function
- `supabase/migrations/20260423000001_user_api_tokens.sql` — `users.metaapi_user_token_encrypted` column
- `backend/app/services/crypto.py` — AES-GCM encrypt/decrypt using a key from env
- `backend/app/services/ip_quota.py` — IP-hash counter helpers
- `frontend/src/app/pricing/page.tsx` — public pricing page
- `frontend/src/components/dashboard/ConversionToasts.tsx` — §11 hooks 2–4

**Modified files:**
- `backend/app/services/metaapi_admin.py` — new `verify_with_user_token(account_id, user_token)` using the user's token
- `backend/app/api/routes.py` — `POST /api/user/broker/connect` requires `metaapi_user_token`; `POST /api/ai-trade/tick` gains IP check; `POST /api/sandbox/reset` gains client-side subtext in frontend only
- `backend/app/services/quota.py` — `check_and_consume` also checks IP aggregate before per-owner consume
- `backend/app/services/ai_client.py` — read global cost ceiling from env, abort if exceeded
- `backend/app/services/database.py` — `db_save_ai_trade_log` accepts `owner_id`/`owner_kind` explicitly (M3 from PR 2b review)
- `frontend/src/app/settings/broker/page.tsx` — add second field: "MetaApi API token (for ownership proof)"
- `frontend/src/components/UpgradeModal.tsx` — link points to `/pricing` now that the page exists
- `frontend/src/components/dashboard/PlanBanner.tsx` — mount `ConversionToasts` below it

---

## Task 1: MetaApi ownership proof — user-supplied token

**Files:**
- Create: `backend/app/services/crypto.py`
- Modify: `backend/app/services/metaapi_admin.py`
- Create: `supabase/migrations/20260423000001_user_api_tokens.sql`
- Modify: `backend/app/api/routes.py` (the `user_broker_connect` endpoint)
- Modify: `frontend/src/app/settings/broker/page.tsx`

Current threat: server-token-only validation lets anyone bind anyone's MetaApi account ID. Fix: require the user to paste their MetaApi **user-level API token** (available at app.metaapi.cloud → API Access). We use that token to fetch the account; if it succeeds, the user demonstrably controls the token. We then encrypt-at-rest and store it so subsequent SDK calls can go through the user's own quota, not our admin budget.

### Step 1: Migration

`supabase/migrations/20260423000001_user_api_tokens.sql`:

```sql
-- Per-user MetaApi API tokens for ownership proof + user-scoped SDK calls.
-- Encrypted at rest with AES-GCM; backend holds the key via env
-- METAAPI_TOKEN_ENC_KEY (32 bytes base64). Rotating the key invalidates
-- every stored token (users re-bind).
alter table users
  add column if not exists metaapi_user_token_encrypted text;
```

Apply: `echo "y" | supabase db push --linked --include-all`.

### Step 2: Crypto helpers

`backend/app/services/crypto.py`:

```python
"""AES-GCM encryption for at-rest secrets (user MetaApi tokens).

Key is read from env METAAPI_TOKEN_ENC_KEY (base64-encoded 32 bytes).
If not set, encryption is a no-op — values stored in plaintext. Staging
OK; production must set the key or CI refuses to deploy (see main.py
startup check added in this PR).
"""

import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key() -> bytes | None:
    raw = os.getenv("METAAPI_TOKEN_ENC_KEY", "")
    if not raw:
        return None
    try:
        return base64.b64decode(raw)
    except Exception:
        return None


def encrypt(plaintext: str) -> str:
    """Returns base64(nonce || ciphertext). Returns plaintext prefixed `pt:` if no key."""
    key = _key()
    if key is None or len(key) != 32:
        return "pt:" + plaintext
    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aes.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(stored: str) -> str | None:
    if stored.startswith("pt:"):
        return stored[3:]
    key = _key()
    if key is None or len(key) != 32:
        return None
    try:
        raw = base64.b64decode(stored)
        nonce, ct = raw[:12], raw[12:]
        return AESGCM(key).decrypt(nonce, ct, None).decode()
    except Exception:
        return None
```

### Step 3: User-token verification in `metaapi_admin.py`

Append:

```python
async def verify_with_user_token(account_id: str, user_token: str) -> tuple[bool, str]:
    """Validate that `user_token` can reach `account_id`. If yes, the user
    demonstrably owns the token (and by extension the account).

    Returns (ok, message). Message is user-safe on every failure path.
    """
    if not user_token or len(user_token) < 20:
        return False, "Missing MetaApi API token. Paste it from app.metaapi.cloud → API Access."
    try:
        from metaapi_cloud_sdk import MetaApi
        api = MetaApi(user_token)  # <-- user's token, not server's
        account = await asyncio.wait_for(
            api.metatrader_account_api.get_account(account_id), timeout=10,
        )
        state = getattr(account, "state", "UNKNOWN")
        if state == "DRAFT":
            return False, "Account is in DRAFT state. Deploy it in the MetaApi dashboard first."
        return True, f"Ownership verified (account state: {state})"
    except asyncio.TimeoutError:
        return False, "MetaApi timed out. Check network and try again."
    except Exception as e:
        msg = str(e).lower()
        if "401" in msg or "unauthorized" in msg:
            return False, "Token rejected by MetaApi — double-check the API token (not the MT5 password)."
        if "not found" in msg or "404" in msg:
            return False, "This account ID doesn't exist under that token — make sure the token is from the same MetaApi workspace as the account."
        return False, f"Verification failed: {str(e)[:200]}"
```

### Step 4: Update endpoint

In `backend/app/api/routes.py` replace the body of `POST /api/user/broker/connect`:

```python
class BrokerConnectInput(BaseModel):
    metaapi_account_id: str
    metaapi_user_token: str  # NEW: ownership proof

@router.post("/api/user/broker/connect")
async def user_broker_connect(
    body: BrokerConnectInput, owner: Owner = Depends(require_user),
):
    acct_id = body.metaapi_account_id.strip()
    user_tok = body.metaapi_user_token.strip()
    if not acct_id or len(acct_id) < 20:
        raise HTTPException(400, "Invalid MetaApi account ID format.")

    from app.services.metaapi_admin import verify_with_user_token
    ok, message = await verify_with_user_token(acct_id, user_tok)
    if not ok:
        raise HTTPException(400, message)

    from app.services.crypto import encrypt
    from app.services.auth import update_user
    encrypted_tok = encrypt(user_tok)
    updated = update_user(owner.id, {
        "metaapi_account_id": acct_id,
        "metaapi_user_token_encrypted": encrypted_tok,
    })
    if not updated:
        raise HTTPException(500, "Failed to save account binding.")

    logger.info("metaapi_bind_verified user=%s account=%s", owner.id[:8], acct_id[:8])
    return {"success": True, "message": message, "user": {
        **updated, "metaapi_user_token_encrypted": None,  # never leak
    }}
```

### Step 5: Frontend — add token field

Modify `frontend/src/app/settings/broker/page.tsx`:

- Add a second input labeled "MetaApi API token (for ownership proof)" of type `password`.
- Link to `https://app.metaapi.cloud/token` (or whatever the current MetaApi path is — check their docs).
- Remove the warning banner since ownership is now verified.
- Form state: `{ accountId, userToken }`, both required.

Post to `/api/user/broker/connect` with `metaapi_account_id` AND `metaapi_user_token`.

### Step 6: Tests

Add to `backend/tests/test_metaapi_admin.py`:

```python
class TestVerifyWithUserToken:
    @pytest.mark.asyncio
    async def test_missing_token_rejected(self):
        from app.services.metaapi_admin import verify_with_user_token
        ok, msg = await verify_with_user_token("acc-xxxxxxxxxxxxxxxxxxxxxxxx", "")
        assert not ok
        assert "token" in msg.lower()

    @pytest.mark.asyncio
    async def test_unauthorized_token(self):
        from app.services.metaapi_admin import verify_with_user_token
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(
            side_effect=Exception("401 unauthorized"))
        with _patch_sdk(fake_api):
            ok, msg = await verify_with_user_token(
                "acc-xxxxxxxxxxxxxxxxxxxxxxxx",
                "user-token-xxxxxxxxxxxxxxxxxx",
            )
            assert not ok
            assert "rejected" in msg.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        from app.services.metaapi_admin import verify_with_user_token
        fake_account = MagicMock(state="DEPLOYED")
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(return_value=fake_account)
        with _patch_sdk(fake_api):
            ok, msg = await verify_with_user_token(
                "acc-xxxxxxxxxxxxxxxxxxxxxxxx",
                "user-token-xxxxxxxxxxxxxxxxxx",
            )
            assert ok
            assert "DEPLOYED" in msg
```

Also add a test for `crypto.py`:

```python
# backend/tests/test_crypto.py
import os
import base64
from unittest.mock import patch

from app.services.crypto import encrypt, decrypt


class TestCrypto:
    def test_roundtrip_with_key(self):
        key = base64.b64encode(b"\x00" * 32).decode()
        with patch.dict(os.environ, {"METAAPI_TOKEN_ENC_KEY": key}):
            ct = encrypt("my-secret-token")
            assert not ct.startswith("pt:")
            assert decrypt(ct) == "my-secret-token"

    def test_no_key_falls_back_to_plaintext(self):
        with patch.dict(os.environ, {"METAAPI_TOKEN_ENC_KEY": ""}):
            ct = encrypt("secret")
            assert ct.startswith("pt:")
            assert decrypt(ct) == "secret"

    def test_malformed_ciphertext_returns_none(self):
        key = base64.b64encode(b"\x00" * 32).decode()
        with patch.dict(os.environ, {"METAAPI_TOKEN_ENC_KEY": key}):
            assert decrypt("garbage") is None
```

### Step 7: Commit

```bash
git add supabase/migrations/20260423000001_user_api_tokens.sql backend/app/services/crypto.py backend/app/services/metaapi_admin.py backend/app/api/routes.py frontend/src/app/settings/broker/page.tsx backend/tests/test_metaapi_admin.py backend/tests/test_crypto.py
git commit -m "feat(security): MetaApi ownership proof via user-supplied API token"
```

---

## Task 2: IP-level anonymous abuse backstop

**Files:**
- Create: `supabase/migrations/20260423000000_ip_quota_and_retention.sql`
- Create: `backend/app/services/ip_quota.py`
- Modify: `backend/app/services/quota.py` (`check_and_consume` calls IP helper before owner consume)
- Modify: `backend/app/services/owner_resolver.py` (expose IP hash on Owner — already stored in `anon_sessions.ip_hash`, need to pass to quota layer)

Current threat: an attacker clears cookies between each call, getting unlimited 50/day anon `ai_trade_tick` allowances. Burns our Claude budget. Fix: a per-IP daily counter, separate from per-owner. Counter applies only to anon owners (paid users trust their auth).

### Step 1: Migration

```sql
create table if not exists ip_quota_usage (
  ip_hash text not null,
  action text not null,
  date date not null,
  count integer not null default 0,
  primary key (ip_hash, action, date)
);

create index if not exists idx_ip_quota_usage_date on ip_quota_usage(date);

-- Retention: prune rows older than 30 days.
create or replace function prune_ip_quota_old() returns integer language plpgsql as $$
declare deleted int;
begin
  delete from ip_quota_usage where date < current_date - interval '30 days';
  get diagnostics deleted = row_count;
  return deleted;
end $$;

-- Retention for ai_cost_ledger: prune >90 days (M4 from PR 2b review, GDPR hygiene).
create or replace function prune_ai_cost_ledger_old() returns integer language plpgsql as $$
declare deleted int;
begin
  delete from ai_cost_ledger where date < current_date - interval '90 days';
  get diagnostics deleted = row_count;
  return deleted;
end $$;

-- Atomic IP-level consume, same pattern as quota_consume.
create or replace function ip_quota_consume(
  p_ip_hash text, p_action text, p_date date, p_limit integer
) returns integer language plpgsql as $$
declare result_count integer;
begin
  insert into ip_quota_usage (ip_hash, action, date, count)
    values (p_ip_hash, p_action, p_date, 1)
  on conflict (ip_hash, action, date) do update
    set count = ip_quota_usage.count + 1
    where ip_quota_usage.count < p_limit
  returning count into result_count;
  return result_count;
end $$;
```

### Step 2: IP limits config (env-driven, not DB-seeded — easier to tune)

`backend/app/config.py` — add:
```python
ip_quota_ai_trade_tick: int = 500  # per IP per day
ip_quota_ai_score: int = 100
```

### Step 3: Implement `ip_quota.py`

```python
"""Per-IP daily caps for anonymous AI actions.

Runs alongside per-owner quota. A determined attacker clearing cookies
after every call would otherwise get unlimited anon allowance, burning
our Claude budget. IP cap kicks in first; owner cap still applies.
"""

import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.services.database import get_db
from app.services.quota import QuotaExceeded

logger = logging.getLogger(__name__)


def _today_utc_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _ip_limit_for(action: str) -> int | None:
    settings = get_settings()
    mapping = {
        "ai_trade_tick": settings.ip_quota_ai_trade_tick,
        "ai_score": settings.ip_quota_ai_score,
    }
    return mapping.get(action)


def check_ip(ip_hash: str | None, action: str) -> None:
    """Raises QuotaExceeded if IP cap reached. No-op if ip_hash is None
    (paid users with no cookie) or action is uncapped.
    """
    if not ip_hash:
        return
    limit = _ip_limit_for(action)
    if limit is None:
        return
    db = get_db()
    if not db:
        return
    try:
        today = _today_utc_iso()
        result = db.rpc("ip_quota_consume", {
            "p_ip_hash": ip_hash,
            "p_action": action,
            "p_date": today,
            "p_limit": limit,
        }).execute()
        new_count = result.data
        if new_count is None:
            # Use a dedicated error code so the frontend modal can say "abuse"
            # instead of the upgrade CTA that normal quota shows.
            raise QuotaExceeded(
                action=f"ip:{action}",
                limit=limit, used=limit, plan="anon-ip",
            )
    except QuotaExceeded:
        raise
    except Exception as e:
        logger.error(f"ip_quota check: {e}")
        # Fail-open — consistent with per-owner quota.
```

### Step 4: Wire into `check_and_consume`

In `quota.py` modify signature:

```python
def check_and_consume(owner: Owner, action: str, ip_hash: str | None = None) -> bool:
    # Only apply IP cap to anonymous owners.
    if owner.kind == "anon" and ip_hash:
        from app.services.ip_quota import check_ip
        check_ip(ip_hash, action)
    # ... existing body ...
```

`require_quota` factory needs the IP. The `get_owner` dependency already has access to `request.client.host` — thread it through.

Modify `require_quota` in `quota.py`:

```python
from fastapi import Depends, HTTPException, Request


def require_quota(action: str):
    def _check(request: Request, owner: Owner = Depends(get_owner)) -> Owner:
        from app.services.owner_resolver import _hash_ip
        ip = request.client.host if request.client else None
        ip_hash = _hash_ip(ip)
        try:
            check_and_consume(owner, action, ip_hash=ip_hash)
        except QuotaExceeded as e:
            # ... same 402 body as before, but include action prefix so frontend
            # can distinguish 'ip:ai_trade_tick' (abuse) vs 'ai_trade_tick' (upgrade).
            ...
    return _check
```

### Step 5: Tests

`backend/tests/test_ip_quota.py`:

```python
"""IP-level anonymous quota: prevents cookie-clearing abuse."""

import os
import secrets

import pytest

from app.services.ip_quota import check_ip
from app.services.quota import QuotaExceeded

pytestmark = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"), reason="requires Supabase dev env"
)


class TestIPQuota:
    def test_first_call_allowed(self):
        ip_hash = secrets.token_hex(16)
        check_ip(ip_hash, "ai_score")  # no raise

    def test_limit_enforced(self):
        ip_hash = secrets.token_hex(16)
        # ai_score IP limit default 100
        for _ in range(100):
            check_ip(ip_hash, "ai_score")
        with pytest.raises(QuotaExceeded) as exc:
            check_ip(ip_hash, "ai_score")
        assert exc.value.action.startswith("ip:")

    def test_uncapped_action_is_noop(self):
        ip_hash = secrets.token_hex(16)
        check_ip(ip_hash, "briefing")  # not in mapping → no raise
```

Commit:
```bash
git add supabase/migrations/20260423000000_ip_quota_and_retention.sql backend/app/services/ip_quota.py backend/app/config.py backend/app/services/quota.py backend/tests/test_ip_quota.py
git commit -m "feat(quota): per-IP anonymous cap prevents cookie-clearing abuse"
```

---

## Task 3: Global cost ceiling

**Files:**
- Modify: `backend/app/services/ai_client.py`
- Modify: `backend/app/config.py`

Second layer of defense. If IP backstop is bypassed (attacker rotates IPs via proxies), a dollar-denominated daily cap on *total anon AI spend* caps the blast radius.

### Step 1: Config

```python
anon_daily_cost_ceiling_usd: float = 50.0  # hard-stop anon AI when total anon cost/day exceeds this
```

### Step 2: AIClient gate

In `ai_client.py._call`:

```python
    async def _call(self, *, action, system_prompt, user_prompt, max_tokens=1024, consume_quota=True):
        if consume_quota:
            check_and_consume(self._owner, action)

        # Defense-in-depth: global anon cost ceiling.
        if self._owner.kind == "anon":
            from app.services.ai_cost import get_anon_cost_today
            from app.config import get_settings
            settings = get_settings()
            today_anon_cost = get_anon_cost_today()
            if today_anon_cost >= settings.anon_daily_cost_ceiling_usd:
                raise QuotaExceeded(
                    action=f"anon-cost-ceiling:{action}",
                    limit=int(settings.anon_daily_cost_ceiling_usd),
                    used=int(today_anon_cost),
                    plan="anon",
                )
        # ... existing body ...
```

### Step 3: Aggregate query

Add to `ai_cost.py`:

```python
def get_anon_cost_today() -> float:
    db = get_db()
    if not db:
        return 0.0
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        result = db.table("ai_cost_ledger").select("cost_usd").eq(
            "owner_kind", "anon").eq("date", today).execute()
        return round(sum(float(r["cost_usd"]) for r in (result.data or [])), 6)
    except Exception as e:
        logger.error(f"get_anon_cost_today: {e}")
        return 0.0
```

Test + commit.

```bash
git add backend/app/services/ai_cost.py backend/app/services/ai_client.py backend/app/config.py
git commit -m "feat(ai): global anon daily cost ceiling as last-resort defense"
```

---

## Task 4: `/pricing` page

**Files:**
- Create: `frontend/src/app/pricing/page.tsx`

The `UpgradeModal` Upgrade button currently 404s because `/pricing` doesn't exist. The landing page's `PricingCard` already has the data; extract to a shared component and render on `/pricing`.

### Step 1: Extract pricing data from `page.tsx`

Move the `texts.free/Features`, `proFeatures`, `premiumFeatures` strings into a new shared module `frontend/src/lib/pricing.ts`. Import from both landing and `/pricing`.

### Step 2: `frontend/src/app/pricing/page.tsx`

```tsx
"use client";

import Link from "next/link";
import { useI18n } from "@/i18n/context";
import { useAuth } from "../providers";
import { api } from "@/lib/api";
import { PLANS, type Plan } from "@/lib/pricing";
import { useState } from "react";

export default function PricingPage() {
  const { locale } = useI18n();
  const { user } = useAuth();
  const [loading, setLoading] = useState<string | null>(null);

  const startCheckout = async (plan: Plan) => {
    if (!user) {
      window.location.href = "/login?next=/pricing";
      return;
    }
    setLoading(plan);
    try {
      const res = await api<{ url: string }>("/api/payments/checkout", {
        method: "POST",
        body: JSON.stringify({ tier: plan }),
      });
      window.location.href = res.url;
    } catch {
      setLoading(null);
    }
  };

  return (
    <main className="min-h-screen p-6 max-w-5xl mx-auto space-y-8">
      <h1 className="text-3xl font-bold">Pricing</h1>
      <p className="text-neutral-400">Start on sandbox for free. Upgrade when you're ready to trade real funds.</p>
      <div className="grid md:grid-cols-3 gap-4">
        {PLANS.map((p) => (
          <div key={p.key} className={`rounded border p-5 space-y-3 ${p.highlight ? "border-blue-500 bg-blue-950/20" : "border-neutral-700 bg-neutral-900"}`}>
            <h2 className="text-xl font-semibold capitalize">{p.key}</h2>
            <p className="text-2xl font-bold">{p.price[locale] ?? p.price.en}</p>
            <ul className="text-sm space-y-1 text-neutral-300">
              {(p.features[locale] ?? p.features.en).map((f: string) => (
                <li key={f}>• {f}</li>
              ))}
            </ul>
            {p.key === "free" ? (
              <Link href="/dashboard" className="block text-center py-2 rounded bg-neutral-700 hover:bg-neutral-600">
                Use free
              </Link>
            ) : (
              <button
                onClick={() => startCheckout(p.key)}
                disabled={loading === p.key || user?.tier === p.key}
                className="w-full py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50"
              >
                {user?.tier === p.key ? "Current plan" :
                 loading === p.key ? "Redirecting…" : `Upgrade to ${p.key}`}
              </button>
            )}
          </div>
        ))}
      </div>
    </main>
  );
}
```

### Step 3: `frontend/src/lib/pricing.ts`

```typescript
export type Plan = "free" | "pro" | "premium";

export const PLANS: Array<{
  key: Plan;
  price: { en: string; zh?: string };
  features: { en: string[]; zh?: string[] };
  highlight?: boolean;
}> = [
  {
    key: "free",
    price: { en: "$0", zh: "¥0" },
    features: {
      en: ["Sandbox trading", "20 AI scores / day", "100 auto-trade ticks / day", "3 saved strategies"],
      zh: ["沙盒交易", "每日 20 次 AI 评分", "每日 100 次自动交易", "3 个策略保存"],
    },
  },
  {
    key: "pro",
    price: { en: "$29/mo", zh: "¥199/月" },
    features: {
      en: ["Bind real MetaApi account", "500 AI scores / day", "2000 auto-trade ticks / day", "50 strategies", "24/7 backend auto-trader"],
      zh: ["绑定真实 MetaApi 账户", "每日 500 次 AI 评分", "每日 2000 次自动交易", "50 个策略", "24/7 后端自动交易"],
    },
    highlight: true,
  },
  {
    key: "premium",
    price: { en: "$49/mo", zh: "¥349/月" },
    features: {
      en: ["Everything in Pro", "Unlimited AI", "Unlimited history", "Multiple accounts", "Priority support"],
      zh: ["Pro 的一切", "AI 无限额", "永久历史", "多账户管理", "优先支持"],
    },
  },
];
```

### Step 4: Import into landing page to de-duplicate

Update `frontend/src/app/page.tsx` to read features from `@/lib/pricing` instead of the inline arrays.

### Step 5: Commit

```bash
git add frontend/src/lib/pricing.ts frontend/src/app/pricing/page.tsx frontend/src/app/page.tsx
git commit -m "feat(frontend): /pricing page (unblocks UpgradeModal's Upgrade link)"
```

---

## Task 5: Conversion hooks (spec §11 items 2–5)

**Files:**
- Create: `frontend/src/components/dashboard/ConversionToasts.tsx`
- Modify: `frontend/src/components/dashboard/AITrader.tsx` (emit events)
- Modify: `frontend/src/app/dashboard/page.tsx` (mount component)

Four small UX hooks:
1. Strategy save count reaches 3 → "Max 3 saved — register for 50"
2. AI auto-trader running 15+ min → "AI is working. Upgrade to Pro to keep it running when you close the tab"
3. Sandbox account bust (equity < 10% of initial) → "Sandbox reset. Try real accounts to stay in play?"
4. Reset Sandbox button subtext → "Register for unlimited resets + permanent history"

Implementation: a single `<ConversionToasts>` component that reads from `localStorage`/state + the owner kind. For item 1, intercept the strategy-save click at the form level. For item 2, a `setInterval` watcher on the auto-trade session. For item 3, watch `account.equity` from useCompliance and compare to initial. For item 4, inline text under the reset button.

Keep it small (~150 lines total). Each toast dismisses once per session.

### Step 1: Implement

`frontend/src/components/dashboard/ConversionToasts.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/app/providers";

type Toast = {
  id: string;
  message: string;
  cta: { label: string; href: string };
};

const SESSION_KEY = "pg-toasts-dismissed";

export function ConversionToasts({
  strategyCount,
  aiTradeStartedAt,
  equity,
  initialBalance,
}: {
  strategyCount: number;
  aiTradeStartedAt: number | null;  // ms epoch
  equity: number | null;
  initialBalance: number | null;
}) {
  const { user } = useAuth();
  const [visible, setVisible] = useState<Toast | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(() => {
    if (typeof window === "undefined") return new Set();
    try {
      return new Set(JSON.parse(sessionStorage.getItem(SESSION_KEY) || "[]"));
    } catch {
      return new Set();
    }
  });

  const dismiss = (id: string) => {
    setDismissed((prev) => {
      const next = new Set(prev);
      next.add(id);
      sessionStorage.setItem(SESSION_KEY, JSON.stringify([...next]));
      return next;
    });
    setVisible(null);
  };

  // Rule 1: strategy cap for anon
  useEffect(() => {
    if (!user && strategyCount >= 3 && !dismissed.has("strategy-cap")) {
      setVisible({
        id: "strategy-cap",
        message: "You've saved 3 strategies — the anon limit. Register for up to 50.",
        cta: { label: "Register", href: "/login" },
      });
    }
  }, [user, strategyCount, dismissed]);

  // Rule 2: AI auto-trade running > 15 min (anon/free only)
  useEffect(() => {
    if (!aiTradeStartedAt) return;
    if (user?.tier === "pro" || user?.tier === "premium") return;
    const check = () => {
      const elapsed = Date.now() - aiTradeStartedAt;
      if (elapsed > 15 * 60 * 1000 && !dismissed.has("ai-while-away")) {
        setVisible({
          id: "ai-while-away",
          message: "AI is working for you. Upgrade to Pro to keep it running when you close the tab.",
          cta: { label: "Upgrade", href: "/pricing" },
        });
      }
    };
    check();
    const t = setInterval(check, 60_000);
    return () => clearInterval(t);
  }, [aiTradeStartedAt, user, dismissed]);

  // Rule 3: sandbox bust (anon only)
  useEffect(() => {
    if (user) return;
    if (equity == null || initialBalance == null) return;
    if (equity < initialBalance * 0.1 && !dismissed.has("sandbox-bust")) {
      setVisible({
        id: "sandbox-bust",
        message: "Sandbox almost wiped. Reset and try with real-account risk controls?",
        cta: { label: "Register", href: "/login" },
      });
    }
  }, [equity, initialBalance, user, dismissed]);

  if (!visible) return null;

  return (
    <div className="fixed bottom-4 right-4 max-w-sm rounded bg-neutral-900 border border-neutral-700 shadow-xl p-4 space-y-3">
      <p className="text-sm">{visible.message}</p>
      <div className="flex gap-2 justify-end">
        <button
          onClick={() => dismiss(visible.id)}
          className="text-xs text-neutral-500 hover:text-white"
        >
          Dismiss
        </button>
        <Link
          href={visible.cta.href}
          className="text-xs px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white"
        >
          {visible.cta.label}
        </Link>
      </div>
    </div>
  );
}
```

### Step 2: Mount in dashboard

Dashboard already knows `account.current_equity` and `account.initial_balance` via `useCompliance`. It needs to expose the strategy count and AI trade start time. Surface via state + pass into `<ConversionToasts>`. Plus subtext under the Reset Sandbox button.

### Step 3: Commit

```bash
git add frontend/src/components/dashboard/ConversionToasts.tsx frontend/src/app/dashboard/page.tsx
git commit -m "feat(conversion): §11 hooks — strategy cap, AI-while-away, sandbox bust"
```

---

## Task 6: `db_save_ai_trade_log` accepts anon owners (M3 from PR 2b review)

**Files:**
- Modify: `backend/app/services/database.py`
- Modify: `backend/app/api/routes.py` (`/api/ai-trade/tick` endpoint)

Currently only persists when `user_id` is provided, so anon AI ticks disappear from the audit log. Make the helper accept explicit `owner_id`/`owner_kind` (keep `user_id` for backwards compat).

```python
def db_save_ai_trade_log(
    user_id: str | None = None, *,
    owner_id: str | None = None,
    owner_kind: str | None = None,
    strategy_name: str = "", ...
) -> dict | None:
    # Derive owner from user_id if caller didn't pass explicit.
    if owner_id is None and user_id is not None:
        owner_id = user_id
        owner_kind = "user"
    if owner_id is None:
        return None  # nothing to log against
    # ... rest sets owner_id, owner_kind, user_id (if user) ...
```

Update `/api/ai-trade/tick` to pass `owner_id=owner.id, owner_kind=owner.kind` so anon ticks land in `ai_trade_logs` too.

Commit:
```bash
git commit -m "feat(logs): ai_trade_logs accepts anon owners (M3 from PR 2b review)"
```

---

## Task 7: Test + smoke + PR

- [ ] Run full pytest: expect ~155 pass (144 + ~11 new)
- [ ] End-to-end smoke:
  - Browser: `/pricing` loads, Upgrade button from UpgradeModal lands there
  - curl: bind MetaApi with valid token → success, with invalid token → 400 "token rejected"
  - curl: hit `/api/ai-trade/tick` 101 times from same IP → the 101st returns 402 `ip:ai_trade_tick`
  - Manual check: conversion toast appears after saving 3 strategies
- [ ] Open PR.

```bash
gh pr create --title "PR 3b: Security + cost hardening, /pricing, conversion hooks" \
  --body "See docs/superpowers/plans/2026-04-19-hardening-and-polish.md"
```

---

## Self-review

- [ ] **Security I1 addressed** — ownership verified via user-supplied token, stored AES-GCM encrypted.
- [ ] **Cost I1 addressed** — two layers: per-IP daily cap + global anon cost ceiling.
- [ ] **UpgradeModal's /pricing link** no longer 404s.
- [ ] **§11 conversion hooks 2–5** live.
- [ ] **Retention (M4 from PR 2b review)** — ai_cost_ledger 90-day prune function defined; schedule in Supabase dashboard.
- [ ] **M3 (anon ai_trade_logs)** addressed.
- [ ] **Out of scope:** full Stripe webhook wiring (already exists from earlier), circuit breaker on DB fail-open (M1 — defer; quota-table downtime is rare enough that we'll add when we see a real incident).
- [ ] **Env var added:** `METAAPI_TOKEN_ENC_KEY` required for production deploys; staging falls back to plaintext. Document in CLAUDE.md deployment section.
