"""Integration layer — wires the multi-agent system into the existing engine."""

from __future__ import annotations

from queue import Queue
from typing import Any

from aitrader_bot.agents.base import AgentContext
from aitrader_bot.agents.chief_trader import ChiefTrader
from aitrader_bot.agents.correlation import CorrelationAgent
from aitrader_bot.agents.entry_strategy import EntryStrategyAgent
from aitrader_bot.agents.exit_strategy import ExitStrategyAgent
from aitrader_bot.agents.indicator_confirmation import IndicatorConfirmationAgent
from aitrader_bot.agents.journal import JournalAgent
from aitrader_bot.agents.liquidity import LiquidityAgent
from aitrader_bot.agents.market_structure import MarketStructureAgent
from aitrader_bot.agents.news_macro import NewsMacroAgent
from aitrader_bot.agents.order_flow import OrderFlowAgent
from aitrader_bot.agents.performance_analyst import PerformanceAnalystAgent
from aitrader_bot.agents.position_sizing import PositionSizingAgent
from aitrader_bot.agents.price_action import PriceActionAgent
from aitrader_bot.agents.risk_manager import RiskManagerAgent
from aitrader_bot.agents.session import SessionAgent
from aitrader_bot.agents.smart_money import SmartMoneyAgent
from aitrader_bot.agents.trade_execution import TradeExecutionAgent
from aitrader_bot.agents.trade_management import TradeManagementAgent
from aitrader_bot.agents.trend_analyst import TrendAnalystAgent
from aitrader_bot.agents.volatility import VolatilityAgent
from aitrader_bot.agents.volume_profile import VolumeProfileAgent
from aitrader_bot.agents.performance_registry import PerformanceRegistry


def create_chief_trader(performance_registry: PerformanceRegistry | None = None) -> ChiefTrader:
    chief = ChiefTrader(performance_registry=performance_registry)

    # Register all 20 agents
    chief.register(MarketStructureAgent())
    chief.register(TrendAnalystAgent())
    chief.register(SmartMoneyAgent())
    chief.register(LiquidityAgent())
    chief.register(OrderFlowAgent())
    chief.register(VolumeProfileAgent())
    chief.register(PriceActionAgent())
    chief.register(IndicatorConfirmationAgent())
    chief.register(VolatilityAgent())
    chief.register(SessionAgent())
    chief.register(NewsMacroAgent())
    chief.register(CorrelationAgent())
    chief.register(EntryStrategyAgent())
    chief.register(RiskManagerAgent())
    chief.register(PositionSizingAgent())
    chief.register(TradeExecutionAgent())
    chief.register(TradeManagementAgent())
    chief.register(ExitStrategyAgent())
    chief.register(PerformanceAnalystAgent())
    chief.register(JournalAgent())

    return chief


def build_context(
    symbol: str,
    price: float,
    bid: float,
    ask: float,
    point_size: float,
    candles: list[dict],
    daily_candles: list[dict] | None = None,
    weekly_candles: list[dict] | None = None,
    balance: float = 0,
    equity: float = 0,
    positions: list[dict] | None = None,
    trades_history: list[dict] | None = None,
    session_label: str = "",
    macro_events: list[dict] | None = None,
    news_risk: str = "Low",
) -> AgentContext:
    import datetime

    ctx = AgentContext(
        symbol=symbol,
        price=price,
        bid=bid,
        ask=ask,
        point_size=point_size,
        candles=candles,
        daily_candles=daily_candles or [],
        weekly_candles=weekly_candles or [],
        balance=balance,
        equity=equity,
        positions=positions or [],
        trades_history=trades_history or [],
        current_time=datetime.datetime.now().isoformat(),
        session_label=session_label,
        macro_events=macro_events or [],
        news_risk=news_risk,
    )
    return ctx


def format_agent_output(decision: dict[str, Any]) -> str:
    action = decision.get("decision", "HOLD")
    confidence = decision.get("confidence", 0)
    entry = decision.get("entry", 0)
    sl = decision.get("sl", 0)
    tp = decision.get("tp", 0)
    lot = decision.get("lot", 0)
    reason = decision.get("reason", "")
    approved = decision.get("approved", False)
    agents_used = decision.get("agents_used", 0)

    if not approved:
        rejected = ", ".join(decision.get("rejected_by", []))
        return f"REJECTED by {rejected} | {reason}"

    return (
        f"CHIEF: {action} lot={lot} entry={entry} sl={sl} tp={tp} "
        f"conf={confidence}% ({agents_used} agents) | {reason}"
    )
