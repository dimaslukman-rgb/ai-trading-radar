"""Broker factory — create any supported exchange adapter.

Usage:
    from aitrader_bot.broker import create_broker

    # Paper (testing)
    broker = create_broker("paper", initial_cash=10000)

    # MT5 / Finex
    broker = create_broker("mt5", server="FinexAsia-Demo", login=12345, password="...")

    # Binance (crypto)
    broker = create_broker("binance", api_key="...", secret="...")

    # Alpaca (US stocks)
    broker = create_broker("alpaca", api_key="...", secret_key="...", paper=True)
"""

from __future__ import annotations

import inspect

from .base import AccountInfo, BaseBroker, Candle, ExchangeType, OrderResult, OrderSide, OrderStatus, PositionInfo, Quote
from .paper_broker import PaperBroker


def create_broker(backend: str, **kwargs) -> BaseBroker:
    """Factory: returns a broker instance by backend name.

    Supported backends:
      - "paper"    : in-memory simulation (default)
      - "mt5"      : MetaTrader 5 (Finex)
      - "binance"  : Binance via CCXT
      - "alpaca"   : Alpaca for US stocks
    """
    backend = backend.lower()

    if backend == "mt5":
        return _try_import("Mt5Broker", "mt5_broker", kwargs)

    elif backend == "binance":
        return _try_import("CcxtBroker", "ccxt_broker", kwargs)

    elif backend == "alpaca":
        return _try_import("AlpacaBroker", "alpaca_broker", kwargs)

    # Default: paper
    return PaperBroker(initial_cash=kwargs.get("initial_cash", 10000.0))


def _try_import(class_name: str, module_name: str, kwargs: dict) -> BaseBroker:
    """Lazy-import a broker class and instantiate it with only valid params."""
    import importlib

    try:
        module = importlib.import_module(f".{module_name}", package=__package__)
        cls = getattr(module, class_name)
        # Only pass kwargs that the class __init__ accepts
        sig = inspect.signature(cls.__init__)
        valid_keys = set(sig.parameters.keys()) - {"self"}
        filtered = {k: v for k, v in kwargs.items() if k in valid_keys}
        return cls(**filtered)
    except ImportError as e:
        raise ImportError(
            f"Broker {class_name} tidak tersedia. "
            f"Install dependensi yang diperlukan. Detail: {e}"
        )


__all__ = [
    "BaseBroker",
    "AccountInfo",
    "Candle",
    "ExchangeType",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "PaperBroker",
    "PositionInfo",
    "Quote",
    "create_broker",
]
