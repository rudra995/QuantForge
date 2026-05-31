"""Performance metrics for historical backtesting and portfolio evaluation.

All calculations use numpy for performance and type-safe computation.
"""

import numpy as np

from quantforge.data.models import EquityCurvePoint


def total_return_pct(initial_capital: float, final_equity: float) -> float:
    """Calculates the total percentage return of the portfolio.

    Args:
        initial_capital: Starting investment amount.
        final_equity: Final portfolio equity valuation.

    Returns:
        The total percentage return.
    """
    if initial_capital <= 0:
        return 0.0
    return ((final_equity - initial_capital) / initial_capital) * 100.0


def cagr(initial_capital: float, final_equity: float, years: float) -> float:
    """Calculates the Compound Annual Growth Rate (CAGR).

    Args:
        initial_capital: Starting investment amount.
        final_equity: Final portfolio equity valuation.
        years: The duration of the investment in years.

    Returns:
        The CAGR as a percentage.

    Raises:
        ValueError: If years is less than or equal to 0.
    """
    if years <= 0:
        raise ValueError(f"years must be strictly greater than 0, got {years}.")
    if initial_capital <= 0 or final_equity <= 0:
        return 0.0
    return ((final_equity / initial_capital) ** (1.0 / years) - 1.0) * 100.0


def sharpe_ratio(
    equity_curve: list[EquityCurvePoint],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Calculates the annualized Sharpe Ratio.

    Requires at least 2 points in the equity curve to compute returns.
    Returns 0.0 if standard deviation of returns is 0.0.

    Args:
        equity_curve: Chronological list of portfolio equity snapshots.
        risk_free_rate: Annualized risk-free rate of return.
        periods_per_year: Number of tracking periods in a year (e.g. 252 for daily).

    Returns:
        The annualized Sharpe Ratio.
    """
    if len(equity_curve) < 2:
        return 0.0

    equities = np.array([pt.equity for pt in equity_curve], dtype=np.float64)
    if np.any(equities[:-1] <= 0):
        # Prevent division by zero or negative equity issues
        return 0.0

    returns = (equities[1:] - equities[:-1]) / equities[:-1]
    
    # Standard deviation of returns (sample std dev using ddof=1)
    std_dev = np.std(returns, ddof=1) if len(returns) > 1 else 0.0
    if std_dev == 0.0 or np.isnan(std_dev):
        return 0.0

    # Calculate excess returns relative to periodic risk-free rate
    periodic_rf = risk_free_rate / periods_per_year
    excess_returns = returns - periodic_rf
    mean_excess = np.mean(excess_returns)

    return float((mean_excess / std_dev) * np.sqrt(periods_per_year))


def sortino_ratio(
    equity_curve: list[EquityCurvePoint],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Calculates the annualized Sortino Ratio.

    Similar to the Sharpe Ratio, but penalizes only downside volatility.
    Returns 0.0 if downside deviation is 0.0.

    Args:
        equity_curve: Chronological list of portfolio equity snapshots.
        risk_free_rate: Annualized risk-free rate of return.
        periods_per_year: Number of tracking periods in a year (e.g. 252 for daily).

    Returns:
        The annualized Sortino Ratio.
    """
    if len(equity_curve) < 2:
        return 0.0

    equities = np.array([pt.equity for pt in equity_curve], dtype=np.float64)
    if np.any(equities[:-1] <= 0):
        return 0.0

    returns = (equities[1:] - equities[:-1]) / equities[:-1]

    # Calculate excess returns relative to periodic risk-free rate
    periodic_rf = risk_free_rate / periods_per_year
    excess_returns = returns - periodic_rf

    # Downside deviation uses elements below risk-free rate
    downside_diffs = np.minimum(excess_returns, 0.0)
    downside_variance = np.mean(downside_diffs ** 2)
    downside_std = np.sqrt(downside_variance)

    if downside_std == 0.0 or np.isnan(downside_std):
        return 0.0

    mean_excess = np.mean(excess_returns)
    return float((mean_excess / downside_std) * np.sqrt(periods_per_year))
