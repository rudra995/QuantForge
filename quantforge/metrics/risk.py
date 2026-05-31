"""Risk metrics for portfolio evaluation and historical drawdown analysis.

All calculations use numpy for performance and type-safe computation.
"""

import numpy as np

from quantforge.data.models import EquityCurvePoint


def max_drawdown(equity_curve: list[EquityCurvePoint]) -> float:
    """Calculates the maximum peak-to-trough drawdown as a negative percentage.

    Requires at least 1 point. Returns 0.0 if there is no drawdown.

    Args:
        equity_curve: Chronological list of portfolio equity snapshots.

    Returns:
        The maximum drawdown as a negative percentage (e.g. -15.3).
    """
    if len(equity_curve) < 1:
        return 0.0

    equities = np.array([pt.equity for pt in equity_curve], dtype=np.float64)
    if len(equities) == 0:
        return 0.0

    # Calculate cumulative running peak
    peaks = np.maximum.accumulate(equities)
    
    # Avoid division by zero if all peaks are <= 0
    drawdowns = np.where(peaks > 0.0, (equities - peaks) / peaks * 100.0, 0.0)
    
    max_dd = np.min(drawdowns)
    
    # Ensure -0.0 is cleaned to 0.0 if there is no drawdown
    if max_dd >= 0.0:
        return 0.0
    return float(max_dd)


def value_at_risk(equity_curve: list[EquityCurvePoint], confidence: float = 0.95) -> float:
    """Calculates the historical Value at Risk (VaR) at a given confidence level.

    Calculates VaR on the periodic returns of the equity curve.
    Returns the loss at the confidence percentile as a negative fractional number.

    Args:
        equity_curve: Chronological list of portfolio equity snapshots.
        confidence: Confidence level in the interval (0, 1) (default 0.95).

    Returns:
        The historical VaR return value (typically negative).

    Raises:
        ValueError: If confidence is not in the interval (0, 1).
    """
    if not (0.0 < confidence < 1.0):
        raise ValueError(
            f"confidence must be strictly between 0 and 1, got {confidence}."
        )

    if len(equity_curve) < 2:
        return 0.0

    equities = np.array([pt.equity for pt in equity_curve], dtype=np.float64)
    if np.any(equities[:-1] <= 0):
        return 0.0

    returns = (equities[1:] - equities[:-1]) / equities[:-1]
    
    # 1 - confidence represents the cutoff alpha percentile (e.g. 0.05 for 0.95)
    alpha = 1.0 - confidence
    var_value = np.percentile(returns, alpha * 100.0)
    
    return float(var_value)


def calmar_ratio(cagr_pct: float, max_drawdown_pct: float) -> float:
    """Calculates the Calmar Ratio.

    Formula: cagr_pct / abs(max_drawdown_pct)
    Returns 0.0 if max_drawdown_pct is 0.0.

    Args:
        cagr_pct: The Compound Annual Growth Rate as a percentage.
        max_drawdown_pct: The maximum drawdown as a negative percentage.

    Returns:
        The Calmar Ratio value.
    """
    if max_drawdown_pct == 0.0:
        return 0.0
    return float(cagr_pct / abs(max_drawdown_pct))
