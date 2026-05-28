"""
Strategies module providing the abstract BaseStrategy, StrategyRegistry, and
concrete strategy implementations for QuantForge.
"""

from quantforge.strategies.base import BaseStrategy, Signal, SignalType
from quantforge.strategies.registry import StrategyRegistry, strategy_registry
from quantforge.strategies.sma_crossover import SMACrossoverStrategy

__all__ = [
    "BaseStrategy",
    "Signal",
    "SignalType",
    "StrategyRegistry",
    "strategy_registry",
    "SMACrossoverStrategy",
]
