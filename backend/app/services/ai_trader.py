"""
AI Trading Engine — sends full trading context to Claude, gets trading actions,
and executes them automatically via MetaApi.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta

from app.config import get_settings
from app.services.live_trading import (
    mt5_place_order, mt5_close_position, mt5_modify_position,
    mt5_get_positions, mt5_get_symbol_price, mt5_get_account_info,
    mt5_get_trade_history,
)
from app.services.kline_data import get_kline_data
from app.rules.engine import evaluate_compliance, load_firm_rules
from app.models.account import AccountState

logger = logging.getLogger(__name__)

_sessions: dict[str, dict] = {}

SYSTEM_PROMPT = """你是一个专业的AI交易助手，在真实MT5账户上执行用户定义的交易策略。

## 核心原则
1. 严格按照用户策略执行，不要自作主张添加额外的谨慎判断
2. 如果策略条件满足，必须给出操作指令，不要因为"谨慎"而跳过
3. 仓位管理按策略规定执行，不超过策略的最大仓位限制
4. 只有在策略条件明确不满足时，才返回空操作
5. 交易时段、胜率等信息仅供参考，不作为拒绝执行策略的理由

## 输出格式
只返回JSON，不要其他内容：
{
  "analysis": "当前市场分析（中文）",
  "actions": [
    {
      "type": "buy" | "sell" | "close" | "modify",
      "symbol": "品种名",
      "volume": 0.01,
      "stop_loss": null,
      "take_profit": null,
      "position_id": "平仓或修改时填持仓ID",
      "reason": "操作原因（中文）"
    }
  ],
  "next_review": "下次需要关注什么（中文）"
}

## 持仓操作说明
- close 操作必须提供 position_id（从持仓列表中获取）
- modify 操作必须提供 position_id + stop_loss 和/或 take_profit
- buy/sell 操作会开新仓，volume 是手数
- 如果不需要任何操作，actions 返回空数组 []"""


async def collect_trading_context(
    strategy: dict,
    firm_name: str = "ftmo",
    account_size: int = 100000,
    evaluation_type: str | None = None,
) -> dict:
    """收集完整的交易上下文"""

    now = datetime.now(timezone.utc)
    context = {"current_time": now.strftime("%Y-%m-%d %H:%M:%S UTC")}

    # 交易时段判断
    hour = now.hour
    weekday = now.weekday()
    if weekday >= 5:
        context["session"] = "周末休市"
    elif 0 <= hour < 8:
        context["session"] = "亚洲盘"
    elif 8 <= hour < 13:
        context["session"] = "欧洲盘"
    elif 13 <= hour < 21:
        context["session"] = "美洲盘（最活跃）"
    else:
        context["session"] = "尾盘"

    # 账户信息
    try:
        info = await mt5_get_account_info()
        if info:
            context["account"] = {
                "broker": info.get("broker"),
                "balance": info.get("balance"),
                "equity": info.get("equity"),
                "margin_used": info.get("margin"),
                "free_margin": info.get("free_margin"),
                "leverage": f"1:{info.get('leverage')}",
                "account_type": info.get("type"),
            }
    except Exception as e:
        context["account"] = {"error": str(e)}

    # 当前持仓
    try:
        positions = await mt5_get_positions()
        longs = [p for p in positions if p.get("side") == "long"]
        shorts = [p for p in positions if p.get("side") == "short"]

        context["positions_summary"] = {
            "total": len(positions),
            "long_count": len(longs),
            "short_count": len(shorts),
            "long_total_pnl": round(sum(p.get("profit", 0) for p in longs), 2),
            "short_total_pnl": round(sum(p.get("profit", 0) for p in shorts), 2),
            "total_pnl": round(sum(p.get("profit", 0) for p in positions), 2),
        }

        # 详细持仓（AI 需要 position_id 来平仓）
        context["positions"] = [
            {
                "position_id": p.get("id"),
                "symbol": p.get("symbol"),
                "direction": p.get("side"),
                "volume": p.get("volume"),
                "entry_price": p.get("entry_price"),
                "current_price": p.get("current_price"),
                "stop_loss": p.get("stop_loss"),
                "take_profit": p.get("take_profit"),
                "profit_usd": p.get("profit"),
            }
            for p in positions
        ]
    except Exception as e:
        context["positions_summary"] = {"error": str(e)}
        context["positions"] = []

    # 最近平仓记录
    try:
        history = await mt5_get_trade_history(days=7)
        if history:
            recent = history[-5:]  # 最近5笔
            wins = sum(1 for t in history if t.get("profit", 0) > 0)
            context["recent_trades"] = {
                "total_7d": len(history),
                "wins": wins,
                "losses": len(history) - wins,
                "win_rate": f"{wins/len(history)*100:.0f}%" if history else "N/A",
                "last_5": [
                    {
                        "symbol": t.get("symbol"),
                        "side": t.get("side"),
                        "profit": t.get("profit"),
                    }
                    for t in recent
                ],
            }
    except Exception:
        context["recent_trades"] = {"total_7d": 0}

    # 合规检查
    try:
        firm_rules = load_firm_rules(firm_name)
        acc = context.get("account", {})
        acc_state = AccountState(
            account_id="ai-trader",
            firm_name=firm_name,
            account_size=account_size,
            initial_balance=float(account_size),
            current_balance=float(acc.get("balance", account_size)),
            current_equity=float(acc.get("equity", account_size)),
            daily_pnl=0,
            total_pnl=float(acc.get("equity", account_size)) - float(account_size),
            equity_high_watermark=max(float(account_size), float(acc.get("equity", account_size))),
            open_positions=[],
            challenge_start_date=now,
        )
        report = evaluate_compliance(acc_state, evaluation_type)

        # 过滤无意义的数据
        context["compliance"] = {
            "status": report.overall_status.value,
            "checks": [
                {
                    "rule": c.rule_type,
                    "status": c.alert_level.value,
                    "detail": c.message,
                }
                for c in report.checks
                if c.remaining < 900000  # 过滤 999999 的无意义数据
            ],
        }
    except Exception as e:
        context["compliance"] = {"error": str(e)}

    # 行情数据
    symbols = strategy.get("symbols", ["EURUSD"])
    kline_period = strategy.get("kline_period", "1h")
    context["market"] = {}

    for symbol in symbols:
        sym_data: dict = {}

        # 实时价格
        try:
            price = await mt5_get_symbol_price(symbol)
            if price:
                sym_data["bid"] = price.get("bid")
                sym_data["ask"] = price.get("ask")
                sym_data["spread_points"] = round(
                    (price.get("ask", 0) - price.get("bid", 0)) * 100000, 1
                ) if price.get("bid") and price.get("bid") < 10 else round(
                    (price.get("ask", 0) - price.get("bid", 0)) * 100, 1
                )
        except Exception:
            pass

        # K线数据 + 指标
        try:
            bars, _ = await get_kline_data(symbol, kline_period, 50)
            if bars:
                closes = [b["close"] for b in bars]

                # 转换 timestamp 为可读时间
                readable_bars = []
                for b in bars[-10:]:  # 只传最近10根
                    ts = datetime.fromtimestamp(b["timestamp"] / 1000, tz=timezone.utc)
                    bar = {
                        "time": ts.strftime("%m-%d %H:%M"),
                        "open": b["open"],
                        "high": b["high"],
                        "low": b["low"],
                        "close": b["close"],
                    }
                    if b.get("volume", 0) > 0:
                        bar["volume"] = b["volume"]
                    readable_bars.append(bar)
                sym_data["kline"] = readable_bars
                sym_data["kline_period"] = kline_period

                # SMA
                if len(closes) >= 20:
                    sma10_now = round(sum(closes[-10:]) / 10, 5)
                    sma20_now = round(sum(closes[-20:]) / 20, 5)
                    sma10_prev = round(sum(closes[-11:-1]) / 10, 5)
                    sma20_prev = round(sum(closes[-21:-1]) / 20, 5)

                    cross_now = "golden" if sma10_now > sma20_now else "death"
                    cross_prev = "golden" if sma10_prev > sma20_prev else "death"

                    sym_data["sma10"] = sma10_now
                    sym_data["sma20"] = sma20_now
                    sym_data["sma_cross"] = cross_now
                    sym_data["sma_just_crossed"] = cross_now != cross_prev
                    if cross_now != cross_prev:
                        sym_data["cross_signal"] = f"刚刚发生{'金叉' if cross_now == 'golden' else '死叉'}"

                # ATR(14)
                if len(bars) >= 15:
                    trs = []
                    for i in range(1, min(15, len(bars))):
                        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i-1]["close"]
                        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
                    sym_data["atr14"] = round(sum(trs) / len(trs), 5)
                    sym_data["atr14_points"] = round(sym_data["atr14"] * 100000 if sym_data["atr14"] < 1 else sym_data["atr14"] * 100, 1)

        except Exception as e:
            logger.warning(f"Market data error for {symbol}: {e}")

        if sym_data:
            context["market"][symbol] = sym_data

    return context


async def ai_analyze_and_trade(
    strategy: dict,
    firm_name: str = "ftmo",
    account_size: int = 100000,
    evaluation_type: str | None = None,
    dry_run: bool = False,
    owner=None,
    consume_quota: bool = True,
) -> dict:
    """执行一次AI交易分析.

    `owner` must be provided to call Claude (used for quota + cost ledger).
    `consume_quota=False` tells AIClient the route already charged via
    @require_quota, so we skip double-consuming.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {"error": "Anthropic API key not configured"}
    if owner is None:
        return {"error": "Owner context required for AI trading"}

    # 1. 收集上下文
    context = await collect_trading_context(strategy, firm_name, account_size, evaluation_type)

    # 2. 构建提示词
    user_prompt = f"""## 交易策略
名称: {strategy.get('name', '未命名')}
品种: {', '.join(strategy.get('symbols', []))}
规则:
{chr(10).join(f'  - {r}' for r in strategy.get('rules', []))}

## 当前时间与交易时段
{context.get('current_time', '')} | {context.get('session', '')}

## 账户状态
{json.dumps(context.get('account', {}), indent=2, ensure_ascii=False, default=str)}

## 持仓概况
{json.dumps(context.get('positions_summary', {}), indent=2, ensure_ascii=False, default=str)}

## 持仓明细（平仓时使用 position_id）
{json.dumps(context.get('positions', []), indent=2, ensure_ascii=False, default=str)}

## 最近交易记录
{json.dumps(context.get('recent_trades', {}), indent=2, ensure_ascii=False, default=str)}

## 合规状态（不可违反）
{json.dumps(context.get('compliance', {}), indent=2, ensure_ascii=False, default=str)}

## 行情数据
{json.dumps(context.get('market', {}), indent=2, ensure_ascii=False, default=str)}

请根据策略和当前状态，决定现在应该执行什么操作。只返回JSON。"""

    # 3. 调用 Claude via AIClient (handles quota + cost ledger)
    try:
        from app.services.ai_client import AIClient
        ai = AIClient(owner)
        resp = await ai.trade_tick(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=1000,
            consume_quota=consume_quota,
        )

        result_text = resp["text"].strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        ai_result = json.loads(result_text)

    except json.JSONDecodeError:
        return {"error": "AI 返回了无效的 JSON", "raw": result_text[:500],
                "system_prompt": SYSTEM_PROMPT, "prompt": user_prompt}
    except Exception as e:
        return {"error": f"AI 调用失败: {str(e)}",
                "system_prompt": SYSTEM_PROMPT, "prompt": user_prompt}

    # 4. 执行操作
    executed = []
    for action in ai_result.get("actions", []):
        action_type = action.get("type")
        symbol = action.get("symbol", "")
        volume = action.get("volume", 0.01)
        sl = action.get("stop_loss")
        tp = action.get("take_profit")
        position_id = action.get("position_id")

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
                executed.append({"action": action, "status": "skipped"})
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
    session_id: str, strategy: dict, interval_seconds: int,
    firm_name: str = "ftmo", account_size: int = 100000,
    evaluation_type: str | None = None, dry_run: bool = False,
    owner=None,
):
    _sessions[session_id] = {
        "status": "running", "strategy": strategy, "interval": interval_seconds,
        "firm_name": firm_name, "account_size": account_size,
        "evaluation_type": evaluation_type, "dry_run": dry_run,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cycles": 0, "last_result": None, "log": [],
    }

    while _sessions.get(session_id, {}).get("status") == "running":
        try:
            result = await ai_analyze_and_trade(
                strategy, firm_name, account_size, evaluation_type, dry_run,
                owner=owner,
            )
            _sessions[session_id]["cycles"] += 1
            _sessions[session_id]["last_result"] = result
            _sessions[session_id]["log"].append({
                "cycle": _sessions[session_id]["cycles"],
                "timestamp": result.get("timestamp"),
                "analysis": result.get("analysis", "")[:200],
                "actions": result.get("actions_executed", 0),
            })
            if len(_sessions[session_id]["log"]) > 50:
                _sessions[session_id]["log"] = _sessions[session_id]["log"][-50:]
        except Exception as e:
            _sessions[session_id]["last_error"] = str(e)

        if _sessions.get(session_id, {}).get("status") == "running":
            await asyncio.sleep(interval_seconds)

    _sessions[session_id]["status"] = "stopped"


def stop_trading_session(session_id: str) -> bool:
    if session_id in _sessions:
        _sessions[session_id]["status"] = "stopping"
        return True
    return False


def get_session_status(session_id: str) -> dict | None:
    return _sessions.get(session_id)


def list_sessions() -> list[dict]:
    return [
        {"id": sid, "status": s["status"], "strategy_name": s["strategy"].get("name", ""),
         "interval": s["interval"], "cycles": s["cycles"], "started_at": s["started_at"]}
        for sid, s in _sessions.items()
    ]
