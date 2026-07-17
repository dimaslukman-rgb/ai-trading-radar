"""Isolated live-cycle processor for one trading symbol.

The engine owns a single broker connection and account refresh cadence.  Each
``SymbolProcessor`` owns every symbol-scoped service and state machine, so a
failure or open position in one market cannot overwrite another market's
strategy, risk, or dashboard state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from aitrader_bot.agents.gemini_sentiment import GeminiSentimentAgent
from aitrader_bot.agents.integration import build_context, create_chief_trader
from aitrader_bot.agents.performance_registry import PerformanceRegistry
from aitrader_bot.position_state import PositionSide
from aitrader_bot.services import (
    ExecutionKind,
    ExecutionService,
    MarketDataService,
    PositionStateService,
    RiskService,
    SignalService,
)
from aitrader_bot.services.risk import current_session_label, detect_sessions

from . import dashboard_data as dd
from .logger import setup_logging
from .news_filter import get_macro_sentiment, get_upcoming_event

log = setup_logging(__name__)


@dataclass(frozen=True)
class CycleResult:
    message: str
    had_market_data: bool = True


class SymbolProcessor:
    """Run signal, risk, execution, AI, and dashboard work for one symbol."""

    def __init__(
        self,
        *,
        broker: Any,
        symbol: str,
        scalping_config: Any,
        ai_config: Any,
        telegram: Any,
        strategy_factory: Callable[[Any], Any],
        performance_registry: PerformanceRegistry,
        emit: Callable[[str], None],
        notify_dashboard: Callable[[], None],
    ) -> None:
        self.broker = broker
        self.symbol = symbol
        self.mapped_symbol = broker.get_symbol_map(symbol)
        self.telegram = telegram
        self.emit = emit
        self.notify_dashboard = notify_dashboard
        self.ai_config = ai_config
        self.strategy = strategy_factory(scalping_config)
        self.position_state = PositionStateService.from_config(
            broker, self.mapped_symbol, scalping_config,
        )
        self.risk = RiskService(scalping_config, self.position_state.machine)
        self.market_data = MarketDataService(
            broker, self.mapped_symbol, scalping_config.candle_timeframe,
        )
        self.signal_service = SignalService(self.strategy, self.market_data)
        self.execution = ExecutionService(
            broker, self.mapped_symbol, symbol, self.position_state, self.risk,
        )
        self.performance_registry = performance_registry
        self.chief = (
            create_chief_trader(performance_registry)
            if ai_config.agents_enabled else None
        )
        self.gemini = (
            GeminiSentimentAgent(
                ai_config.gemini_api_key,
                ai_config.gemini_model,
                ai_config.gemini_timeout_seconds,
            )
            if ai_config.gemini_enabled else None
        )
        self._initialize_dashboard()

    def _initialize_dashboard(self) -> None:
        config = self.strategy.config
        dd.update(
            symbol=self.symbol,
            aggressive_mode=config.aggressive_mode,
            timeout_minutes=config.timeout_exit_minutes,
            processor_status="ready",
        )
        log.info(
            "Processor ready: %s (mapped: %s), %s/%ss",
            self.symbol, self.mapped_symbol, config.candle_timeframe,
            config.interval_seconds,
        )

    @staticmethod
    def _candle_dicts(snapshot: Any) -> list[dict[str, Any]]:
        return [
            {
                "timestamp": candle.timestamp.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            for candle in snapshot.candles
        ]

    @staticmethod
    def _reasoning(
        votes: dict[str, dict[str, Any]],
        weights: dict[str, float],
    ) -> list[dict[str, Any]]:
        """A compact, JSON-safe explanation list for the dashboard."""
        rows: list[dict[str, Any]] = []
        for agent_id, output in votes.items():
            summary = (
                output.get("reason") or output.get("summary") or
                output.get("overall") or output.get("market_structure") or
                output.get("liquidity") or output.get("flow") or
                output.get("volatility") or output.get("risk") or "No directional view"
            )
            rows.append({
                "agent": agent_id,
                "summary": str(summary)[:180],
                "confidence": round(float(output.get("confidence", 0) or 0), 1),
                "weight": round(float(weights.get(agent_id, 1.0)), 3),
            })
        return rows

    def _run_agents(self, snapshot: Any, macro: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str | None]:
        if self.chief is None:
            return {}, {}, None
        quote = snapshot.quote
        try:
            account = self.broker.get_account()
            balance, equity = account.balance, account.equity
        except Exception:
            balance = equity = 0.0
        context = build_context(
            symbol=self.symbol,
            price=quote.last,
            bid=quote.bid,
            ask=quote.ask,
            point_size=quote.point_size or 0.0,
            candles=self._candle_dicts(snapshot),
            balance=balance,
            equity=equity,
            positions=self.position_state.dashboard_rows(quote.point_size),
            trades_history=dd.snapshot().get("trades", [])[-20:],
            session_label=current_session_label(detect_sessions()),
            macro_events=macro.get("events", []),
            news_risk=str(macro.get("risk", "Low")).title(),
        )
        self.performance_registry.settle(self.symbol, quote.last)
        chief_output = self.chief.analyze(context).output
        votes = chief_output.get("agent_votes", {})
        weights = chief_output.get("agent_weights", {})
        self.performance_registry.record(self.symbol, quote.last, votes)

        gemini_summary: str | None = None
        if self.gemini is not None:
            gemini = self.gemini.run(context).output
            chief_output["gemini_sentiment"] = gemini
            gemini_summary = gemini.get("summary")
            macro = dict(macro)
            macro["llm"] = gemini
        dd.update(
            symbol=self.symbol,
            agent_reasoning=self._reasoning(votes, weights),
            agent_scores=self.performance_registry.snapshot(),
            chief_decision={
                key: chief_output.get(key)
                for key in ("decision", "confidence", "reason", "approved", "agents_used")
            },
        )
        return chief_output, macro, gemini_summary

    def process_cycle(self) -> CycleResult:
        """Execute exactly one safe live iteration for this symbol."""
        snapshot = self.market_data.snapshot()
        if snapshot is None:
            message = f"waiting - no quote for {self.symbol}"
            dd.update(symbol=self.symbol, processor_status="waiting", last_signal=message)
            return CycleResult(message, had_market_data=False)

        quote = snapshot.quote
        news_event = (
            get_upcoming_event(buffer_minutes=self.strategy.config.news_filter_minutes)
            if self.strategy.config.news_filter_enabled else None
        )
        entry_blocks = self.risk.entry_blocks(
            quote,
            supports_attached_protection=self.broker.supports_attached_protection,
            news_event=news_event,
        )
        evaluation = self.signal_service.evaluate(
            self.symbol, snapshot, entry_blocked=bool(entry_blocks),
        )
        signal = evaluation.signal
        position_snapshot = self.position_state.sync()

        for repair in self.execution.repair_missing_protection(
            position_snapshot.broker_positions, quote.point_size,
        ):
            if repair.success:
                dd.add_log(f"{self.symbol}: protection restored for {repair.ticket}")
            else:
                self.emit(f"error:{repair.message}")
                self.telegram.send_error(repair.message)

        macro = get_macro_sentiment()
        chief, macro, _ = self._run_agents(snapshot, macro)
        liquidity = chief.get("agent_votes", {}).get("liquidity", {})
        adaptive_risk = self.risk.set_market_atr(float(liquidity.get("atr", 0) or 0), quote.point_size)
        sessions = detect_sessions()
        session_label = current_session_label(sessions)
        action_for_execution = signal.action
        reason_for_execution = signal.reason
        if self.ai_config.agent_execution_enabled and chief.get("approved"):
            proposed = str(chief.get("decision", "HOLD")).lower()
            if proposed in {"buy", "sell", "hold"}:
                action_for_execution = proposed
                reason_for_execution = f"{signal.reason} | AI: {chief.get('reason', '')}"

        protection = self.risk.protective_prices(
            quote.last, action_for_execution, symbol=self.symbol, point_size=quote.point_size,
        )
        dd.update(
            symbol=self.symbol,
            processor_status="running",
            entry_time=(
                position_snapshot.earliest_entry_time.isoformat()
                if position_snapshot.earliest_entry_time else None
            ),
            open_positions=self.position_state.dashboard_rows(quote.point_size),
            confidence_pct=evaluation.confidence_pct,
            confidence_category=evaluation.confidence_category,
            signal_action=action_for_execution.upper(),
            entry=protection["entry"], sl=protection["sl"], tp=protection["tp"], rr=protection["rr"],
            signal_status=evaluation.confidence_category,
            current_session=session_label, sessions=sessions,
            sentiment=evaluation.sentiment, volatility=evaluation.volatility,
            news_events=macro.get("events", []), macro_sentiment=macro,
            analysis=evaluation.analysis, adaptive_risk=adaptive_risk,
        )

        decision_plan = self.risk.decide(
            action_for_execution, self.mapped_symbol, point_size=quote.point_size,
            now=datetime.now(timezone.utc), entry_block_reasons=entry_blocks,
            higher_timeframe_confirmed=evaluation.higher_timeframe_confirmed,
            higher_timeframe_reason=evaluation.higher_timeframe_reason,
        )
        batch = self.execution.execute(decision_plan.actions, quote, reason_for_execution)
        messages: list[str] = []
        for outcome in batch.outcomes:
            messages.append(outcome.message)
            if outcome.kind == ExecutionKind.CLOSED:
                self.risk.decisions.record_closed_trade(outcome.pnl)
                dd.add_trade(
                    f"CLOSE {outcome.side.name}", self.symbol, outcome.price,
                    outcome.quantity, outcome.action.reason, outcome.pnl,
                )
                close_action = "sell" if outcome.side == PositionSide.LONG else "buy"
                self.telegram.send_signal(
                    close_action, self.symbol, outcome.price, outcome.action.reason,
                    pnl=outcome.pnl,
                )
                self.telegram.send_trade_report(
                    self.symbol, outcome.pnl, outcome.action.reason,
                    equity=self._account_equity(),
                )
            elif outcome.kind == ExecutionKind.OPENED:
                dd.add_trade(
                    f"OPEN {outcome.side.name}", self.symbol, outcome.price,
                    outcome.quantity, reason_for_execution,
                )
                self.telegram.send_signal(outcome.side.value, self.symbol, outcome.price, reason_for_execution)
                dd.update(
                    symbol=self.symbol,
                    entry_time=outcome.result.timestamp.isoformat() if outcome.result else None,
                    timeout_minutes=self.strategy.config.timeout_exit_minutes,
                )
            elif outcome.kind == ExecutionKind.ENTRY_REJECTED:
                dd.add_log(f"{self.symbol}: REJECTED {outcome.message}")
            elif outcome.kind == ExecutionKind.CLOSE_UNCONFIRMED:
                self.emit(f"error:{outcome.message}")
                dd.add_log(f"{self.symbol}: BROKER ERROR (close unconfirmed) — {outcome.message}")
                self.telegram.send_error(outcome.message)
                # Tetap catat ke history dengan PnL yang ada (bisa negatif)
                if outcome.side is not None:
                    dd.add_trade(
                        f"CLOSE_ERR {outcome.side.name}", self.symbol, outcome.price,
                        outcome.quantity, outcome.action.reason, outcome.pnl or None,
                    )

        if batch.refresh_error:
            log.warning("%s position refresh failed: %s", self.symbol, batch.refresh_error)
        message = " || ".join(messages) or (
            f"HOLD {self.symbol} @ {quote.last:.5f} sc={signal.confidence:.3f}"
        )
        dd.update(
            symbol=self.symbol,
            open_positions=self.position_state.dashboard_rows(quote.point_size),
            last_signal=message, last_price=quote.last, last_confidence=signal.confidence,
        )
        self.notify_dashboard()
        return CycleResult(message)

    def _account_equity(self) -> float | None:
        try:
            return float(self.broker.get_account().equity)
        except Exception:
            return None
