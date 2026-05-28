"""Backtester module for QuantForge trading platform.

This package houses the components for the event-driven backtesting engine,
including the event queue, execution models, and portfolio managers.
"""

from quantforge.backtester.events import (
    BacktestEvent,
    EventQueue,
    FillEvent,
    MarketEvent,
    OrderEvent,
    OrderType,
    SignalEvent,
)

__all__ = [
    "MarketEvent",
    "SignalEvent",
    "OrderEvent",
    "FillEvent",
    "OrderType",
    "BacktestEvent",
    "EventQueue",
]
