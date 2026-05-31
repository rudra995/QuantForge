"""Comprehensive backtest report generation and aggregation models.

Ties performance and risk metrics together into a structured, validated report.
"""

from datetime import date
from pydantic import BaseModel, Field

from quantforge.backtester.engine import BacktestResult
from quantforge.metrics.performance import cagr, sharpe_ratio, sortino_ratio, total_return_pct
from quantforge.metrics.risk import calmar_ratio, max_drawdown, value_at_risk


class BacktestReport(BaseModel):
    """Aggregated, validated performance and risk report for a completed backtest.

    Replaces loose dictionaries with standard validated data structures.
    """

    ticker: str = Field(..., min_length=1, description="Asset ticker symbol.")
    strategy_name: str = Field(..., min_length=1, description="Trading strategy registered identifier.")
    initial_capital: float = Field(..., gt=0, description="Starting cash amount.")
    final_equity: float = Field(..., ge=0, description="Ending equity valuation (cash + positions value).")
    total_return_pct: float = Field(..., description="Total return percentage relative to initial capital.")
    cagr_pct: float = Field(..., description="Compound Annual Growth Rate percentage.")
    sharpe_ratio: float = Field(..., description="Annualized Sharpe Ratio.")
    sortino_ratio: float = Field(..., description="Annualized Sortino Ratio (downside volatility adjusted).")
    max_drawdown_pct: float = Field(..., le=0.0, description="Maximum peak-to-trough drawdown as negative percentage.")
    var_95: float = Field(..., description="Value at Risk (VaR) at 95% confidence level.")
    calmar_ratio: float = Field(..., description="Calmar Ratio (cagr_pct / abs(max_drawdown_pct)).")
    total_bars: int = Field(..., ge=0, description="Total number of price bars processed.")
    total_trades: int = Field(..., ge=0, description="Total number of executed transactions (fills).")
    total_signals: int = Field(..., ge=0, description="Total number of strategy-emitted signals.")
    start: date = Field(..., description="Backtest start date.")
    end: date = Field(..., description="Backtest end date.")


def generate_report(result: BacktestResult) -> BacktestReport:
    """Generates a complete BacktestReport aggregating performance and risk metrics.

    Args:
        result: The result model returned by a completed BacktestEngine run.

    Returns:
        The fully computed and validated BacktestReport.
    """
    # Calculate duration of the backtest in years
    days_duration = (result.config.end - result.config.start).days
    years = days_duration / 365.25

    # Compute performance metrics
    tot_ret = total_return_pct(result.config.initial_capital, result.final_equity)
    cagr_val = cagr(result.config.initial_capital, result.final_equity, years)
    sharpe = sharpe_ratio(result.equity_curve)
    sortino = sortino_ratio(result.equity_curve)

    # Compute risk metrics
    max_dd = max_drawdown(result.equity_curve)
    var_value = value_at_risk(result.equity_curve, confidence=0.95)
    calmar = calmar_ratio(cagr_val, max_dd)

    return BacktestReport(
        ticker=result.config.ticker,
        strategy_name=result.config.strategy_name,
        initial_capital=result.config.initial_capital,
        final_equity=result.final_equity,
        total_return_pct=tot_ret,
        cagr_pct=cagr_val,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown_pct=max_dd,
        var_95=var_value,
        calmar_ratio=calmar,
        total_bars=result.total_bars,
        total_trades=result.total_trades,
        total_signals=result.total_signals,
        start=result.config.start,
        end=result.config.end,
    )
