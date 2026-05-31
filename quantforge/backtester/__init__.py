"""Backtester module for QuantForge trading platform.

This package houses the components for the event-driven backtesting engine,
including the event queue, execution models, portfolio managers, and the main
BacktestEngine.
"""

from quantforge.backtester.engine import BacktestConfig, BacktestEngine, BacktestResult
from quantforge.backtester.events import (
    BacktestEvent,
    EventQueue,
    FillEvent,
    MarketEvent,
    OrderEvent,
    OrderType,
    SignalEvent,
)
from quantforge.backtester.portfolio import PortfolioManager
from quantforge.backtester.execution import (
    SlippageModel,
    FixedSlippageModel,
    PercentageSlippageModel,
    CommissionModel,
    FixedCommissionModel,
    PercentageCommissionModel,
    ExecutionHandler,
    create_default_execution_handler,
)

__all__ = [
    # Engine
    "BacktestConfig",
    "BacktestResult",
    "BacktestEngine",
    # Events
    "MarketEvent",
    "SignalEvent",
    "OrderEvent",
    "FillEvent",
    "OrderType",
    "BacktestEvent",
    "EventQueue",
    # Portfolio
    "PortfolioManager",
    # Execution
    "SlippageModel",
    "FixedSlippageModel",
    "PercentageSlippageModel",
    "CommissionModel",
    "FixedCommissionModel",
    "PercentageCommissionModel",
    "ExecutionHandler",
    "create_default_execution_handler",
]
