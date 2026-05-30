"""Unit tests for the PortfolioManager and portfolio state tracking in QuantForge."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from quantforge.backtester.events import FillEvent, OrderEvent, OrderType, SignalEvent
from quantforge.backtester.portfolio import PortfolioManager
from quantforge.core.exceptions import BacktestError
from quantforge.data.models import EquityCurvePoint, Position
from quantforge.strategies.base import SignalType


def test_init_invalid_capital() -> None:
    """Verifies that initialising with non-positive capital raises a ValueError."""
    with pytest.raises(ValueError) as exc_info:
        PortfolioManager(initial_capital=0.0)
    assert "initial_capital must be strictly greater than 0" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        PortfolioManager(initial_capital=-500.0)
    assert "initial_capital must be strictly greater than 0" in str(exc_info.value)


def test_init_valid_capital() -> None:
    """Verifies successful initialisation and default properties of PortfolioManager."""
    pm = PortfolioManager(initial_capital=10000.0)
    assert pm.cash == 10000.0
    assert len(pm.positions) == 0
    assert len(pm.equity_curve) == 0
    assert pm.portfolio.cash == 10000.0


def test_buy_fill_creates_position() -> None:
    """Verifies that a BUY fill event updates cash and correctly creates a new Position."""
    pm = PortfolioManager(initial_capital=10000.0)
    
    # 10 shares of AAPL filled at $150, commission $10, slippage $5.
    # total_cost = 10 * 150 + 10 + 5 = 1515.0
    fill = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="buy",
        quantity=10.0,
        fill_price=150.0,
        commission=10.0,
        slippage=5.0,
    )
    
    current_prices = {"AAPL": 150.0}
    pm.on_fill(fill, current_prices)
    
    assert pm.cash == 10000.0 - 1515.0  # 8485.0
    assert "AAPL" in pm.positions
    position = pm.positions["AAPL"]
    assert position.ticker == "AAPL"
    assert position.quantity == 10.0
    assert position.average_entry_price == 150.0


def test_buy_fill_updates_weighted_average() -> None:
    """Verifies that BUY fills into an existing position update the weighted average entry price."""
    pm = PortfolioManager(initial_capital=10000.0)
    current_prices = {"AAPL": 150.0}

    # First Buy: 10 shares at $150
    # total_cost = 1500.0
    fill1 = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="buy",
        quantity=10.0,
        fill_price=150.0,
    )
    pm.on_fill(fill1, current_prices)
    
    # Second Buy: 20 shares at $160
    # total_cost = 3200.0
    # Weighted average entry price: (10 * 150 + 20 * 160) / 30 = (1500 + 3200) / 30 = 4700 / 30 = 156.6666...
    fill2 = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="buy",
        quantity=20.0,
        fill_price=160.0,
    )
    current_prices = {"AAPL": 160.0}
    pm.on_fill(fill2, current_prices)
    
    assert pm.cash == 10000.0 - 1500.0 - 3200.0  # 5300.0
    assert pm.positions["AAPL"].quantity == 30.0
    assert pm.positions["AAPL"].average_entry_price == pytest.approx(156.66666666666666)


def test_sell_fill_reduces_position_and_adds_cash() -> None:
    """Verifies that a SELL fill reduces the position quantity and correctly adds cash."""
    pm = PortfolioManager(initial_capital=10000.0)
    current_prices = {"AAPL": 150.0}
    
    # Buy 10 shares of AAPL at 150
    fill_buy = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="buy",
        quantity=10.0,
        fill_price=150.0,
    )
    pm.on_fill(fill_buy, current_prices)
    
    # Sell 4 shares of AAPL at 155 with commission $5 and slippage $2
    # total_cost = 4 * 155 - 5 - 2 = 620 - 7 = 613.0
    fill_sell = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="sell",
        quantity=4.0,
        fill_price=155.0,
        commission=5.0,
        slippage=2.0,
    )
    current_prices = {"AAPL": 155.0}
    pm.on_fill(fill_sell, current_prices)
    
    assert pm.cash == (10000.0 - 1500.0) + 613.0  # 9113.0
    assert pm.positions["AAPL"].quantity == 6.0
    # Entry price should remain unchanged after selling
    assert pm.positions["AAPL"].average_entry_price == 150.0


def test_sell_fill_clears_position_entirely() -> None:
    """Verifies that selling the full quantity of a position removes it from positions dict."""
    pm = PortfolioManager(initial_capital=10000.0)
    current_prices = {"AAPL": 150.0}

    # Buy 10 shares
    fill_buy = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="buy",
        quantity=10.0,
        fill_price=150.0,
    )
    pm.on_fill(fill_buy, current_prices)
    
    # Sell 10 shares
    fill_sell = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="sell",
        quantity=10.0,
        fill_price=155.0,
    )
    current_prices = {"AAPL": 155.0}
    pm.on_fill(fill_sell, current_prices)
    
    assert pm.cash == (10000.0 - 1500.0) + 1550.0  # 10050.0
    assert "AAPL" not in pm.positions
    assert len(pm.positions) == 0


def test_sell_more_than_held_raises_backtest_error() -> None:
    """Verifies that selling more shares than held raises a BacktestError."""
    pm = PortfolioManager(initial_capital=10000.0)
    current_prices = {"AAPL": 150.0}

    # 1. Sell when not holding any
    fill_empty = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="sell",
        quantity=5.0,
        fill_price=150.0,
    )
    with pytest.raises(BacktestError) as exc_info:
        pm.on_fill(fill_empty, current_prices)
    assert "no position is held" in str(exc_info.value)
    assert exc_info.value.ticker == "AAPL"

    # 2. Buy 10 shares, then try to sell 12 shares
    fill_buy = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="buy",
        quantity=10.0,
        fill_price=150.0,
    )
    pm.on_fill(fill_buy, current_prices)

    fill_excess = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="sell",
        quantity=12.0,
        fill_price=150.0,
    )
    with pytest.raises(BacktestError) as exc_info:
        pm.on_fill(fill_excess, current_prices)
    assert "Cannot sell 12.0 units of AAPL when only 10.0 are held" in str(exc_info.value)
    assert exc_info.value.ticker == "AAPL"


def test_equity_curve_recording_and_missing_prices() -> None:
    """Verifies equity curve appends points and raises BacktestError on missing prices."""
    pm = PortfolioManager(initial_capital=10000.0)
    current_prices = {"AAPL": 150.0, "MSFT": 300.0}

    # Buy AAPL
    fill1 = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="buy",
        quantity=10.0,
        fill_price=150.0,
    )
    pm.on_fill(fill1, current_prices)
    assert len(pm.equity_curve) == 1
    # Cash = 8500. Portfolio Equity = 8500 + 10 * 150 = 10000
    assert pm.equity_curve[0].equity == 10000.0

    # Buy MSFT
    fill2 = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="MSFT",
        side="buy",
        quantity=5.0,
        fill_price=300.0,
    )
    # Market updates: AAPL goes up to 160, MSFT remains at 300
    # cash = 8500 - 1500 = 7000
    # Equity = 7000 + 10 * 160 + 5 * 300 = 7000 + 1600 + 1500 = 10100
    current_prices = {"AAPL": 160.0, "MSFT": 300.0}
    pm.on_fill(fill2, current_prices)
    assert len(pm.equity_curve) == 2
    assert pm.equity_curve[1].equity == 10100.0

    # Test missing ticker price during fill
    fill3 = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="buy",
        quantity=5.0,
        fill_price=160.0,
    )
    # Current prices missing MSFT price
    bad_prices = {"AAPL": 160.0}
    with pytest.raises(BacktestError) as exc_info:
        pm.on_fill(fill3, bad_prices)
    assert "Missing current price for ticker 'MSFT'" in str(exc_info.value)
    assert exc_info.value.ticker == "MSFT"


def test_on_signal_handling() -> None:
    """Verifies that signals are converted into correct OrderEvents or None based on sizing rules."""
    pm = PortfolioManager(initial_capital=10000.0)
    current_prices = {"AAPL": 150.0}

    # 1. HOLD Signal -> returns None
    sig_hold = SignalEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        signal_type=SignalType.HOLD,
        strength=1.0,
        strategy_name="SMACrossover",
    )
    order_hold = pm.on_signal(sig_hold, current_prices)
    assert order_hold is None

    # 2. BUY Signal: cash = 10000.0.
    # 95% of cash = 9500.0.
    # AAPL price = 150.0.
    # quantity = floor(9500.0 / 150.0) = floor(63.333) = 63.
    sig_buy = SignalEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        signal_type=SignalType.BUY,
        strength=0.9,
        strategy_name="SMACrossover",
    )
    order_buy = pm.on_signal(sig_buy, current_prices)
    assert order_buy is not None
    assert order_buy.order_type == OrderType.MARKET
    assert order_buy.side == "buy"
    assert order_buy.quantity == 63.0
    assert order_buy.ticker == "AAPL"

    # 3. BUY Signal with insufficient cash (e.g. price is huge, 95% of cash < price)
    huge_prices = {"AAPL": 20000.0}
    order_insufficient = pm.on_signal(sig_buy, huge_prices)
    assert order_insufficient is None

    # 4. SELL Signal when no position held -> returns None
    sig_sell = SignalEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        signal_type=SignalType.SELL,
        strength=1.0,
        strategy_name="SMACrossover",
    )
    order_sell_empty = pm.on_signal(sig_sell, current_prices)
    assert order_sell_empty is None

    # 5. SELL Signal with position -> returns OrderEvent with full quantity
    # Manually execute fill to create a position of 25 shares of AAPL
    fill = FillEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        side="buy",
        quantity=25.0,
        fill_price=150.0,
    )
    pm.on_fill(fill, current_prices)
    
    order_sell_held = pm.on_signal(sig_sell, current_prices)
    assert order_sell_held is not None
    assert order_sell_held.order_type == OrderType.MARKET
    assert order_sell_held.side == "sell"
    assert order_sell_held.quantity == 25.0
    assert order_sell_held.ticker == "AAPL"
