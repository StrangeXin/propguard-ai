# PropGuard AI — Development Guide

## Project Overview

PropGuard AI is an AI-powered risk management tool for Prop Firm traders. It monitors trading accounts against Prop Firm compliance rules in real-time, scores trading signals with Claude AI, and provides position sizing recommendations.

**Live URLs:**
- Frontend: https://propguard-ai.vercel.app
- Backend: https://propguard-ai-production.up.railway.app
- Telegram Bot: https://t.me/PropGuardAIBot
- GitHub: https://github.com/StrangeXin/propguard-ai

## Architecture

```
Frontend (Vercel)          Backend (Railway)           Database (Supabase)
Next.js 16 + TS            FastAPI + Uvicorn           PostgreSQL
shadcn/ui + KlineCharts    Docker container            REST API access
WebSocket + Polling        MetaApi SDK (MT5)
i18n (EN/ZH)               Claude API (AI)
                           OKX + TwelveData (行情)
                           Telegram Bot API
```

## Local Development

```bash
# Backend
cd backend
cp .env.example .env  # Fill in API keys
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8001

# Frontend
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8001" > .env.local
npx next dev --port 3001

# Tests
cd backend && python -m pytest tests/ -v
```

## Deployment

- **Frontend**: Vercel auto-deploys from `main` branch. Root directory: `frontend`
- **Backend**: Railway auto-deploys from `main` branch. Uses `Dockerfile` at project root
- **Database**: Supabase cloud, shared between local and production

All environment variables must be set in Railway Dashboard (Variables section).

## Database Migrations

```bash
# Create new migration
./scripts/db-migrate.sh new "description_here"

# Edit the generated SQL file in supabase/migrations/

# Push to Supabase
export SUPABASE_ACCESS_TOKEN=<token>
./scripts/db-migrate.sh push

# Check status
./scripts/db-migrate.sh status
```

Migration files are in `supabase/migrations/`, versioned with git.

## MetaApi Accounts

The broker module supports multiple MetaApi connections, one per Prop Firm:

| Firm | MetaApi Account ID | MT5 Server | Purpose |
|------|-------------------|------------|---------|
| FTMO | `462031a5-c503-49ec-9e9f-9383628ad736` | OANDA-Demo-1 | FTMO Free Trial (real FTMO rules) |
| Default | `96165adc-d3a4-4b73-b861-49fcd71d1377` | MetaQuotes-Demo | TopStep / CryptoFundTrader |

To add a new Prop Firm account:
1. Register the MT5 account with MetaApi REST API
2. Add `FIRMNAME_METAAPI_ACCOUNT_ID=xxx` to `.env`
3. Add the mapping in `broker.py` `__init__` → `self._account_map`
4. Add the config field in `config.py`

## Prop Firm Rules

Rules are JSON files in `data/prop_firm_rules/`. Each file contains:
- Firm metadata (name, markets, evaluation types)
- Account sizes and profit targets
- Compliance rules (daily loss, drawdown, trading days, etc.)
- Source URLs for verification

**CRITICAL: Rules must match official Prop Firm documentation exactly.**
- Always verify against the Prop Firm's official website
- Include source URLs in the JSON
- Note the verification date in `effective_date`
- If unsure, register a free trial to verify

Currently supported:
- `ftmo.json` — Verified from FTMO Free Trial page (2026-04-16)
- `topstep.json` — From TopStep Help Center
- `cryptofundtrader.json` — From CFT website

Rule engine checkers in `backend/app/rules/engine.py`:
- `daily_loss` — Equity-based, supports % and USD limits
- `max_drawdown` — Static and EOD trailing
- `min_trading_days` — Calendar days
- `time_limit` — Challenge deadline
- `news_restriction` — High-impact news window
- `trading_hours` — Session/weekend checks
- `leverage` — Per-asset leverage limits
- `position_size` — Contract/lot limits

## Key Design Decisions

1. **Read-only monitoring** — We never execute trades on behalf of users for compliance. Trading panel uses MetaApi but is separate from compliance monitoring.
2. **Conservative calculations** — When we can't match the exact official calculation (e.g., FTMO midnight CET snapshot), we use the more conservative approximation. Better to show less room than more.
3. **WebSocket + Polling fallback** — Try WebSocket first for real-time data. If WS fails (e.g., Railway proxy issues), auto-fallback to HTTP polling every 3 seconds.
4. **Placeholder on broker disconnect** — If MetaApi isn't connected yet, show rules with placeholder account data rather than showing nothing.

## API Endpoints (19 total)

### Compliance
- `GET /api/firms` — List supported Prop Firms
- `GET /api/firms/{name}/rules` — Get firm rules
- `GET /api/accounts/{id}/compliance` — Real-time compliance check
- `GET /api/accounts/{id}/challenge-progress` — Profit target + drawdown progress
- `WS /ws/compliance/{id}` — WebSocket real-time stream

### Trading (MetaApi MT5)
- `POST /api/trading/order` — Market order
- `POST /api/trading/pending-order` — Limit/stop order
- `POST /api/trading/position/{id}/close` — Close position
- `POST /api/trading/position/{id}/close-partial` — Partial close
- `POST /api/trading/position/{id}/modify` — Modify SL/TP
- `POST /api/trading/order/{id}/cancel` — Cancel pending order
- `GET /api/trading/account` — Account + positions
- `GET /api/trading/account-info` — Full account details
- `GET /api/trading/orders` — Pending orders
- `GET /api/trading/history` — Trade history + win rate
- `GET /api/trading/symbol/{symbol}` — Symbol spec + live bid/ask

### Signals
- `POST /api/signals/parse` — Parse + AI score a signal
- `GET /api/signals/recent` — Recent signals
- `GET /api/signals/top` — Top scored signals
- `POST /api/webhook/tradingview` — TradingView webhook

### Other
- `GET /api/accounts/{id}/briefing` — AI pre-market briefing
- `POST /api/position/calculate` — Position size calculator
- `GET /api/kline/{symbol}` — K-line data (OKX/TwelveData)
- `GET /api/alerts/history` — Alert history
- `POST /api/auth/register` / `POST /api/auth/login` / `GET /api/auth/me`
- `POST /api/payments/checkout` / `POST /api/payments/webhook`
- `GET /api/health` — Health check

## Frontend Pages

- `/` — Landing page (product intro, features, pricing)
- `/login` — Register / login
- `/dashboard` — Main dashboard (requires auth)
- `/docs` — Product documentation

## Testing

60 tests covering:
- Rule engine (all 3 firms, all rule types, edge cases)
- Signal parser (EN/CN formats, edge cases)
- Position calculator (1% rule, Kelly, constraints)
- Tier system (Free/Pro/Premium feature gates)
- TradingView webhook parser
- Auth (register, login, token verification)

Run: `cd backend && python -m pytest tests/ -v`

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
