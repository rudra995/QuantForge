"""Unit tests for the performance and risk calculation metrics in QuantForge."""

from datetime import date, datetime, timezone
import pytest
import numpy as np

from quantforge.backtester.engine import BacktestConfig, BacktestResult
from quantforge.data.models import EquityCurvePoint, Trade
from quantforge.metrics.performance import cagr, sharpe_ratio, sortino_ratio, total_return_pct
from quantforge.metrics.risk import calmar_ratio, max_drawdown, value_at_risk
from quantforge.metrics.report import BacktestReport, generate_report


def test_total_return_pct() -> None:
    """Verifies that total_return_pct correctly calculates positive, negative, and zero returns."""
    # Positive return
    assert total_return_pct(100.0, 150.0) == 50.0
    # Negative return
    assert total_return_pct(100.0, 75.0) == -25.0
    # Zero return
    assert total_return_pct(100.0, 100.0) == 0.0
    # Invalid initial capital returns 0.0
    assert total_return_pct(0.0, 150.0) == 0.0
    assert total_return_pct(-10.0, 150.0) == 0.0


def test_cagr_calculation() -> None:
    """Verifies CAGR calculation with known values and checking invalid inputs."""
    # Double in 1 year: (2/1)^(1/1) - 1 = 100.0%
    assert cagr(1000.0, 2000.0, 1.0) == pytest.approx(100.0)
    # Double in 2 years: (2/1)^(1/2) - 1 = 41.421356%
    assert cagr(1000.0, 2000.0, 2.0) == pytest.approx(41.421356237)
    # Flat: 0.0%
    assert cagr(1000.0, 1000.0, 5.0) == 0.0

    # Years <= 0 raises ValueError
    with pytest.raises(ValueError) as exc_info:
        cagr(1000.0, 2000.0, 0.0)
    assert "years must be strictly greater than 0" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        cagr(1000.0, 2000.0, -1.5)
    assert "years must be strictly greater than 0" in str(exc_info.value)


def test_sharpe_ratio() -> None:
    """Verifies that sharpe_ratio handles flat equity (std dev = 0), short equity curves, and standard returns."""
    now = datetime.now(timezone.utc)

    # 1. Short curve: < 2 points
    curve_short = [EquityCurvePoint(timestamp=now, equity=10000.0)]
    assert sharpe_ratio(curve_short) == 0.0

    # 2. Flat equity (std dev of returns = 0.0)
    curve_flat = [
        EquityCurvePoint(timestamp=now, equity=10000.0),
        EquityCurvePoint(timestamp=now, equity=10000.0),
        EquityCurvePoint(timestamp=now, equity=10000.0),
    ]
    assert sharpe_ratio(curve_flat) == 0.0

    # 3. Known returns: returns = [0.01, -0.01, 0.02]
    # equities: 10000 -> 10100 -> 9999 -> 10198.98
    curve_known = [
        EquityCurvePoint(timestamp=now, equity=10000.0),
        EquityCurvePoint(timestamp=now, equity=10100.0),  # +1%
        EquityCurvePoint(timestamp=now, equity=9999.0),   # -1%
        EquityCurvePoint(timestamp=now, equity=10198.98), # +2%
    ]
    # returns: np.array([0.01, -0.01, 0.02])
    # mean of returns: 0.006666666...
    # std of returns (ddof=1): sample std of [0.01, -0.01, 0.02] is 0.01527525...
    # excess return (with rf=0): 0.00666666...
    # Sharpe = 0.00666666 / 0.01527525 * sqrt(252) = 0.43643578 * 15.8745 = 6.9282
    expected_sharpe = (0.006666666666666667 / 0.015275252315989069) * np.sqrt(252)
    assert sharpe_ratio(curve_known, risk_free_rate=0.0) == pytest.approx(expected_sharpe)


def test_sortino_ratio() -> None:
    """Verifies sortino_ratio downside deviation logic and handling curves with all positive returns."""
    now = datetime.now(timezone.utc)

    # 1. No downside returns (all positive returns) -> downside deviation = 0.0 -> returns 0.0
    curve_positive = [
        EquityCurvePoint(timestamp=now, equity=10000.0),
        EquityCurvePoint(timestamp=now, equity=10100.0),  # +1%
        EquityCurvePoint(timestamp=now, equity=10201.0),  # +1%
    ]
    assert sortino_ratio(curve_positive, risk_free_rate=0.0) == 0.0

    # 2. Known returns: returns = [0.02, -0.01, -0.02]
    # excess returns (rf=0): [0.02, -0.01, -0.02]
    # downside diffs: np.minimum(excess, 0) = [0.0, -0.01, -0.02]
    # downside variance: np.mean([0, 0.0001, 0.0004]) = 0.0005 / 3 = 0.0001666666...
    # downside std = sqrt(0.000166666...) = 0.01290994...
    # mean of returns: (0.02 - 0.01 - 0.02) / 3 = -0.00333333...
    # Sortino = -0.00333333 / 0.01290994 * sqrt(252) = -0.2581988897 * 15.8745 = -4.09878
    curve_known = [
        EquityCurvePoint(timestamp=now, equity=10000.0),
        EquityCurvePoint(timestamp=now, equity=10200.0),  # +2%
        EquityCurvePoint(timestamp=now, equity=10098.0),  # -1%
        EquityCurvePoint(timestamp=now, equity=9896.04),  # -2%
    ]
    expected_sortino = (-0.0033333333333333335 / np.sqrt(0.0005 / 3.0)) * np.sqrt(252)
    assert sortino_ratio(curve_known, risk_free_rate=0.0) == pytest.approx(expected_sortino)


def test_max_drawdown() -> None:
    """Verifies max_drawdown calculations on known peak-to-trough series and flat series."""
    now = datetime.now(timezone.utc)

    # 1. Flat series
    curve_flat = [
        EquityCurvePoint(timestamp=now, equity=10000.0),
        EquityCurvePoint(timestamp=now, equity=10000.0),
    ]
    assert max_drawdown(curve_flat) == 0.0

    # 2. Known peak-to-trough series:
    # 10000 (peak=10000, dd=0%)
    # 9000  (peak=10000, dd=-10%)
    # 11000 (peak=11000, dd=0%)
    # 8800  (peak=11000, dd=-20%) -> max drawdown
    # 10500 (peak=11000, dd=-4.54%)
    curve_known = [
        EquityCurvePoint(timestamp=now, equity=10000.0),
        EquityCurvePoint(timestamp=now, equity=9000.0),
        EquityCurvePoint(timestamp=now, equity=11000.0),
        EquityCurvePoint(timestamp=now, equity=8800.0),
        EquityCurvePoint(timestamp=now, equity=10500.0),
    ]
    assert max_drawdown(curve_known) == -20.0


def test_value_at_risk() -> None:
    """Verifies historical Value at Risk returns correct percentile and validates confidence range."""
    now = datetime.now(timezone.utc)

    # 1. Validation limits
    curve = [EquityCurvePoint(timestamp=now, equity=1000.0), EquityCurvePoint(timestamp=now, equity=1100.0)]
    with pytest.raises(ValueError) as exc_info:
        value_at_risk(curve, confidence=0.0)
    assert "confidence must be strictly between 0 and 1" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        value_at_risk(curve, confidence=1.0)
    assert "confidence must be strictly between 0 and 1" in str(exc_info.value)

    # 2. Historical percentile estimation
    # We want 5 sorted returns to estimate historical VaR.
    # returns: [-0.10, -0.05, 0.00, 0.05, 0.10]
    # equities: 1000 -> 900 -> 855 -> 855 -> 897.75 -> 987.525
    curve_series = [
        EquityCurvePoint(timestamp=now, equity=1000.0),
        EquityCurvePoint(timestamp=now, equity=900.0),     # -10%
        EquityCurvePoint(timestamp=now, equity=855.0),     # -5%
        EquityCurvePoint(timestamp=now, equity=855.0),     # 0%
        EquityCurvePoint(timestamp=now, equity=897.75),    # +5%
        EquityCurvePoint(timestamp=now, equity=987.525),   # +10%
    ]
    # With confidence = 0.80 (20% cutoff) on 5 items:
    # returns: [-0.10, -0.05, 0.0, 0.05, 0.10]
    # 20th percentile is -0.06
    expected_var = np.percentile([-0.10, -0.05, 0.0, 0.05, 0.10], 20.0)
    assert value_at_risk(curve_series, confidence=0.80) == pytest.approx(expected_var)


def test_calmar_ratio() -> None:
    """Verifies Calmar ratio calculation and handling division-by-zero when drawdown is 0."""
    assert calmar_ratio(10.0, -2.0) == 5.0
    assert calmar_ratio(15.0, 0.0) == 0.0
    assert calmar_ratio(12.0, -4.0) == 3.0


def test_generate_report() -> None:
    """Verifies generate_report successfully builds a BacktestReport and maps all variables correctly."""
    config = BacktestConfig(
        ticker="AAPL",
        start=date(2025, 1, 1),
        end=date(2026, 1, 1),
        initial_capital=10000.0,
        strategy_name="BuyAndHold",
    )
    
    # 365 days / 365.25 = ~0.9993 years
    now = datetime.now(timezone.utc)
    # Simple equity curve: AAPL double
    equity_curve = [
        EquityCurvePoint(timestamp=now, equity=10000.0),
        EquityCurvePoint(timestamp=now, equity=20000.0),
    ]

    result = BacktestResult(
        config=config,
        trades=[],
        equity_curve=equity_curve,
        final_equity=20000.0,
        total_return_pct=100.0,
        total_bars=252,
        total_signals=1,
        total_trades=0,
    )

    report = generate_report(result)

    # Type & Value assertions
    assert isinstance(report, BacktestReport)
    assert report.ticker == "AAPL"
    assert report.strategy_name == "BuyAndHold"
    assert report.initial_capital == 10000.0
    assert report.final_equity == 20000.0
    assert report.total_return_pct == 100.0
    
    # CAGR double in ~1 year (365 days)
    # years = 365 / 365.25 = 0.9993155
    # cagr = ((2/1)**(1/0.9993155) - 1) * 100 = 100.095%
    assert report.cagr_pct == pytest.approx(100.095, abs=1e-2)
    assert report.max_drawdown_pct == 0.0
    assert report.calmar_ratio == 0.0
    assert report.total_bars == 252
    assert report.total_signals == 1
    assert report.total_trades == 0
    assert report.start == date(2025, 1, 1)
    assert report.end == date(2026, 1, 1)
