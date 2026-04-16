"""
AI Trading Engine — sends full trading context to Claude, gets trading actions,
and executes them automatically via MetaApi.

Flow:
1. Collect context: strategy, account, positions, market data, compliance
2. Build prompt with all context
3. Claude analyzes and returns JSON actions
4. Execute actions (open/close/modify orders)
5. Log results
"""

import json
import logging
import asyncio
from datetime import datetime, timezone

from app.config import get_settings
from app.services.live_trading import (
    mt5_place_order, mt5_close_position, mt5_modify_position,
    mt5_get_positions, mt5_get_symbol_price, mt5_get_account_info,
    resolve_symbol, get_metaapi_connection,
)
from app.services.kline_data import get_kline_data
from app.rules.engine import evaluate_compliance, load_firm_rules
from app.models.account import AccountState

logger = logging.getLogger(__name__)

# Active trading sessions
_sessions: dict[str, dict] = {}

SYSTEM_PROMPT = """You are an AI trading assistant executing a specific trading strategy on a live MT5 account.

CRITICAL RULES:
1. ONLY return valid JSON. No explanations, no markdown.
2. Every action must follow the user's strategy EXACTLY.
3. Consider risk management, compliance limits, and current positions.
4. If no action needed, return empty actions array.
5. Never exceed the strategy's risk limits.

Response format (JSON only):
{
  "analysis": "Brief analysis of current market state",
  "actions": [
    {
      "type": "buy" | "sell" | "close" | "modify",
      "symbol": "EURUSD",
      "volume": 0.01,
      "stop_loss": null,
      "take_profit": null,
      "position_id": null,
      "reason": "Why this action"
    }
  ],
  "next_review": "What to watch for next cycle"
}"""


async def collect_trading_context(
    strategy: dict,
    firm_name: str = "ftmo",
    account_size: int = 100000,
    evaluation_type: str | None = None,
) -> dict:
    """Collect all context needed for AI trading decision."""
    context = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "strategy": strategy,
    }

    # Account info
    try:
        info = await mt5_get_account_info()
        context["account"] = info
    except Exception as e:
        context["account"] = {"error": str(e)}

    # Current positions
    try:
        positions = await mt5_get_positions()
        context["positions"] = positions
        context["position_count"] = len(positions)
        context["total_profit"] = sum(p.get("profit", 0) for p in positions)

        # Separate by direction
        longs = [p for p in positions if p.get("side") == "long"]
        shorts = [p for p in positions if p.get("side") == "short"]
        context["long_count"] = len(longs)
        context["short_count"] = len(shorts)
        context["long_profit"] = sum(p.get("profit", 0) for p in longs)
        context["short_profit"] = sum(p.get("profit", 0) for p in shorts)
    except Exception as e:
        context["positions"] = []
        context["position_count"] = 0

    # Compliance
    try:
        firm_rules = load_firm_rules(firm_name)
        # Build minimal account state for compliance check
        acc_info = context.get("account", {})
        acc_state = AccountState(
            account_id="ai-trader",
            firm_name=firm_name,
            account_size=account_size,
            initial_balance=float(account_size),
            current_balance=float(acc_info.get("balance", account_size)),
            current_equity=float(acc_info.get("equity", account_size)),
            daily_pnl=0,
            total_pnl=float(acc_info.get("equity", account_size)) - float(account_size),
            equity_high_watermark=max(float(account_size), float(acc_info.get("equity", account_size))),
            open_positions=[],
            challenge_start_date=datetime.now(timezone.utc),
        )
        report = evaluate_compliance(acc_state, evaluation_type)
        context["compliance"] = {
            "status": report.overall_status.value,
            "checks": [
                {"rule": c.rule_type, "level": c.alert_level.value,
                 "remaining": c.remaining, "message": c.message}
                for c in report.checks
            ],
        }
    except Exception as e:
        context["compliance"] = {"error": str(e)}

    # Market data for strategy symbols
    symbols = strategy.get("symbols", ["EURUSD"])
    kline_period = strategy.get("kline_period", "1h")
    context["market_data"] = {}

    for symbol in symbols:
        try:
            # Current price
            price = await mt5_get_symbol_price(symbol)
            if price:
                context["market_data"][symbol] = {"price": price}

            # Recent K-line data (last 50 bars for indicator calculation)
            bars, source = await get_kline_data(symbol, kline_period, 50)
            if bars:
                context["market_data"][symbol]["bars"] = bars[-20:]  # Last 20 for context
                context["market_data"][symbol]["bar_count"] = len(bars)

                # Calculate simple indicators for AI context
                closes = [b["close"] for b in bars]
                if len(closes) >= 20:
                    sma10 = sum(closes[-10:]) / 10
                    sma20 = sum(closes[-20:]) / 20
                    context["market_data"][symbol]["sma10"] = round(sma10, 5)
                    context["market_data"][symbol]["sma20"] = round(sma20, 5)
                    context["market_data"][symbol]["sma_cross"] = "golden" if sma10 > sma20 else "death"

                # ATR(14)
                if len(bars) >= 15:
                    trs = []
                    for i in range(1, min(15, len(bars))):
                        h = bars[i]["high"]
                        l = bars[i]["low"]
                        pc = bars[i-1]["close"]
                        tr = max(h - l, abs(h - pc), abs(l - pc))
                        trs.append(tr)
                    if trs:
                        context["market_data"][symbol]["atr14"] = round(sum(trs) / len(trs), 5)

        except Exception as e:
            logger.warning(f"Market data error for {symbol}: {e}")

    return context


async def ai_analyze_and_trade(
    strategy: dict,
    firm_name: str = "ftmo",
    account_size: int = 100000,
    evaluation_type: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Run one AI trading cycle: analyze → decide → execute."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {"error": "Anthropic API key not configured"}

    # 1. Collect context
    context = await collect_trading_context(strategy, firm_name, account_size, evaluation_type)

    # 2. Build prompt
    user_prompt = f"""## Trading Strategy
{json.dumps(strategy, indent=2, ensure_ascii=False)}

## Current Account State
{json.dumps(context.get('account', {}), indent=2, default=str)}

## Open Positions ({context.get('position_count', 0)} total, {context.get('long_count', 0)} long, {context.get('short_count', 0)} short)
Long P&L: ${context.get('long_profit', 0):.2f} | Short P&L: ${context.get('short_profit', 0):.2f}
{json.dumps(context.get('positions', []), indent=2, default=str)}

## Compliance Status
{json.dumps(context.get('compliance', {}), indent=2, default=str)}

## Market Data
{json.dumps(context.get('market_data', {}), indent=2, default=str)}

Based on the strategy and current state, what actions should be taken NOW?
Return ONLY valid JSON with your analysis and actions."""

    # 3. Call Claude
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        response = await client.messages.create(
            model=settings.ai_model,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        result_text = response.content[0].text.strip()
        # Handle markdown-wrapped JSON
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        ai_result = json.loads(result_text)

    except json.JSONDecodeError:
        return {"error": "AI returned invalid JSON", "raw": result_text[:500], "prompt": user_prompt}
    except Exception as e:
        return {"error": f"AI call failed: {str(e)}", "prompt": user_prompt}

    # 4. Execute actions (or dry run)
    executed = []
    for action in ai_result.get("actions", []):
        action_type = action.get("type")
        symbol = action.get("symbol", "")
        volume = action.get("volume", 0.01)
        sl = action.get("stop_loss")
        tp = action.get("take_profit")
        position_id = action.get("position_id")
        reason = action.get("reason", "")

        if dry_run:
            executed.append({"action": action, "status": "dry_run"})
            continue

        try:
            if action_type in ("buy", "sell"):
                result = await mt5_place_order(symbol, action_type, volume, sl, tp)
                executed.append({"action": action, "result": result})

            elif action_type == "close" and position_id:
                result = await mt5_close_position(position_id)
                executed.append({"action": action, "result": result})

            elif action_type == "modify" and position_id:
                result = await mt5_modify_position(position_id, sl, tp)
                executed.append({"action": action, "result": result})

            else:
                executed.append({"action": action, "status": "skipped", "reason": "invalid action"})

        except Exception as e:
            executed.append({"action": action, "status": "error", "error": str(e)})

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system_prompt": SYSTEM_PROMPT,
        "prompt": user_prompt,
        "analysis": ai_result.get("analysis", ""),
        "actions_planned": len(ai_result.get("actions", [])),
        "actions_executed": len(executed),
        "executions": executed,
        "next_review": ai_result.get("next_review", ""),
        "dry_run": dry_run,
    }


# === Session Management ===

async def start_trading_session(
    session_id: str,
    strategy: dict,
    interval_seconds: int,
    firm_name: str = "ftmo",
    account_size: int = 100000,
    evaluation_type: str | None = None,
    dry_run: bool = False,
):
    """Start an automated trading session that runs on interval."""
    _sessions[session_id] = {
        "status": "running",
        "strategy": strategy,
        "interval": interval_seconds,
        "firm_name": firm_name,
        "account_size": account_size,
        "evaluation_type": evaluation_type,
        "dry_run": dry_run,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cycles": 0,
        "last_result": None,
        "log": [],
    }

    logger.info(f"AI trading session {session_id} started: {interval_seconds}s interval")

    while _sessions.get(session_id, {}).get("status") == "running":
        try:
            result = await ai_analyze_and_trade(
                strategy, firm_name, account_size, evaluation_type, dry_run
            )
            _sessions[session_id]["cycles"] += 1
            _sessions[session_id]["last_result"] = result

            # Keep last 50 log entries
            _sessions[session_id]["log"].append({
                "cycle": _sessions[session_id]["cycles"],
                "timestamp": result.get("timestamp"),
                "analysis": result.get("analysis", "")[:200],
                "actions": result.get("actions_executed", 0),
            })
            if len(_sessions[session_id]["log"]) > 50:
                _sessions[session_id]["log"] = _sessions[session_id]["log"][-50:]

            logger.info(f"Session {session_id} cycle {_sessions[session_id]['cycles']}: {result.get('actions_executed', 0)} actions")

        except Exception as e:
            logger.error(f"Session {session_id} error: {e}")
            _sessions[session_id]["last_error"] = str(e)

        # Wait for next cycle
        if _sessions.get(session_id, {}).get("status") == "running":
            await asyncio.sleep(interval_seconds)

    _sessions[session_id]["status"] = "stopped"
    logger.info(f"AI trading session {session_id} stopped")


def stop_trading_session(session_id: str) -> bool:
    if session_id in _sessions:
        _sessions[session_id]["status"] = "stopping"
        return True
    return False


def get_session_status(session_id: str) -> dict | None:
    return _sessions.get(session_id)


def list_sessions() -> list[dict]:
    return [
        {
            "id": sid,
            "status": s["status"],
            "strategy_name": s["strategy"].get("name", "unnamed"),
            "interval": s["interval"],
            "cycles": s["cycles"],
            "started_at": s["started_at"],
        }
        for sid, s in _sessions.items()
    ]
