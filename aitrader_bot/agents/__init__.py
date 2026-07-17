"""Institutional multi-agent trading system.

Each agent has a narrow responsibility and returns structured JSON.
ChiefTrader aggregates all agent outputs into a final decision.
"""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent
from .chief_trader import ChiefTrader
from .market_structure import MarketStructureAgent
from .trend_analyst import TrendAnalystAgent
from .smart_money import SmartMoneyAgent
from .liquidity import LiquidityAgent
from .order_flow import OrderFlowAgent
from .volume_profile import VolumeProfileAgent
from .price_action import PriceActionAgent
from .indicator_confirmation import IndicatorConfirmationAgent
from .volatility import VolatilityAgent
from .session import SessionAgent
from .news_macro import NewsMacroAgent
from .correlation import CorrelationAgent
from .entry_strategy import EntryStrategyAgent
from .risk_manager import RiskManagerAgent
from .position_sizing import PositionSizingAgent
from .trade_execution import TradeExecutionAgent
from .trade_management import TradeManagementAgent
from .exit_strategy import ExitStrategyAgent
from .performance_analyst import PerformanceAnalystAgent
from .journal import JournalAgent
from .performance_registry import PerformanceRegistry
from .gemini_sentiment import GeminiSentimentAgent

__all__ = [
    "AgentContext", "AgentResult", "BaseAgent",
    "ChiefTrader",
    "MarketStructureAgent", "TrendAnalystAgent", "SmartMoneyAgent",
    "LiquidityAgent", "OrderFlowAgent", "VolumeProfileAgent",
    "PriceActionAgent", "IndicatorConfirmationAgent", "VolatilityAgent",
    "SessionAgent", "NewsMacroAgent", "CorrelationAgent",
    "EntryStrategyAgent", "RiskManagerAgent", "PositionSizingAgent",
    "TradeExecutionAgent", "TradeManagementAgent", "ExitStrategyAgent",
    "PerformanceAnalystAgent", "JournalAgent",
    "PerformanceRegistry", "GeminiSentimentAgent",
]
