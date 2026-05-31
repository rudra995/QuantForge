"""Metrics and performance evaluation module for QuantForge.

Provides quantitative computation tools for returns, risk factors, and
aggregate backtest report generation.
"""

from quantforge.metrics.performance import (
    cagr,
    sharpe_ratio,
    sortino_ratio,
    total_return_pct,
)
from quantforge.metrics.report import BacktestReport, generate_report
from quantforge.metrics.risk import calmar_ratio, max_drawdown, value_at_risk

__all__ = [
    "total_return_pct",
    "cagr",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "value_at_risk",
    "calmar_ratio",
    "BacktestReport",
    "generate_report",
]
