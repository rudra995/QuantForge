"""Unit tests for the simulated ExecutionHandler, SlippageModels, and CommissionModels in QuantForge."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from quantforge.backtester.events import FillEvent, OrderEvent, OrderType
from quantforge.backtester.execution import (
    ExecutionHandler,
    FixedCommissionModel,
    FixedSlippageModel,
    PercentageCommissionModel,
    PercentageSlippageModel,
    create_default_execution_handler,
)
from quantforge.core.exceptions import BacktestError
from quantforge.data.models import OHLCVBar


@pytest.fixture
def sample_bar() -> OHLCVBar:
    """Fixture supplying a valid OHLCV price bar for AAPL at $150."""
    return OHLCVBar(
        ticker="AAPL",
        timestamp=datetime.now(timezone.utc),
        open=148.0,
        high=152.0,
        low=147.0,
        close=150.0,
        volume=100000.0,
    )


@pytest.fixture
def sample_buy_order() -> OrderEvent:
    """Fixture supplying a valid buy OrderEvent for 100 shares of AAPL."""
    return OrderEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        order_type=OrderType.MARKET,
        side="buy",
        quantity=100.0,
    )


@pytest.fixture
def sample_sell_order() -> OrderEvent:
    """Fixture supplying a valid sell OrderEvent for 50 shares of AAPL."""
    return OrderEvent(
        timestamp=datetime.now(timezone.utc),
        ticker="AAPL",
        order_type=OrderType.MARKET,
        side="sell",
        quantity=50.0,
    )


def test_slippage_models_validation() -> None:
    """Verifies that negative values for constructor arguments raise a ValueError."""
    with pytest.raises(ValueError) as exc_info:
        FixedSlippageModel(slippage_per_unit=-0.1)
    assert "must be non-negative" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        PercentageSlippageModel(percentage=-0.005)
    assert "must be non-negative" in str(exc_info.value)


def test_commission_models_validation() -> None:
    """Verifies that negative values for constructor arguments raise a ValueError."""
    with pytest.raises(ValueError) as exc_info:
        FixedCommissionModel(commission_per_trade=-10.0)
    assert "must be non-negative" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        PercentageCommissionModel(percentage=-0.002)
    assert "must be non-negative" in str(exc_info.value)


def test_slippage_calculations(sample_bar: OHLCVBar, sample_buy_order: OrderEvent) -> None:
    """Verifies that FixedSlippageModel and PercentageSlippageModel calculate correct slippage values."""
    # Fixed Slippage: quantity = 100, cost per unit = 0.05. Slippage = 5.0
    fixed_model = FixedSlippageModel(slippage_per_unit=0.05)
    assert fixed_model.calculate(sample_buy_order, sample_bar) == 5.0

    # Percentage Slippage: close = 150, quantity = 100, percentage = 0.002 (0.2%).
    # Slippage = 150 * 0.002 * 100 = 30.0
    pct_model = PercentageSlippageModel(percentage=0.002)
    assert pct_model.calculate(sample_buy_order, sample_bar) == 30.0


def test_commission_calculations(sample_buy_order: OrderEvent) -> None:
    """Verifies that FixedCommissionModel and PercentageCommissionModel calculate correct commission values."""
    # Fixed Commission: flat $5.0
    fixed_model = FixedCommissionModel(commission_per_trade=5.0)
    assert fixed_model.calculate(sample_buy_order, fill_price=150.0) == 5.0

    # Percentage Commission: close = 150.0, quantity = 100, percentage = 0.001 (0.1%).
    # Commission = 150.0 * 100 * 0.001 = 15.0
    pct_model = PercentageCommissionModel(percentage=0.001)
    assert pct_model.calculate(sample_buy_order, fill_price=150.0) == 15.0


def test_execution_handler_buy(sample_bar: OHLCVBar, sample_buy_order: OrderEvent) -> None:
    """Verifies that ExecutionHandler.execute processes a BUY order with correct fill price, commission, and slippage."""
    # Set up models: slippage = $0.1 per unit (total $10), commission = 0.2% of total transaction
    slippage_model = FixedSlippageModel(slippage_per_unit=0.1)
    commission_model = PercentageCommissionModel(percentage=0.002)
    handler = ExecutionHandler(slippage_model, commission_model)

    fill_event = handler.execute(sample_buy_order, sample_bar)

    # Asserts
    assert isinstance(fill_event, FillEvent)
    assert fill_event.event_type == "FILL"
    assert fill_event.ticker == "AAPL"
    assert fill_event.side == "buy"
    assert fill_event.quantity == 100.0

    # Fill price: close + slippage = 150.0 + 10.0 = 160.0
    assert fill_event.fill_price == 160.0
    assert fill_event.slippage == 10.0

    # Commission: 160.0 * 100 * 0.002 = 32.0
    assert fill_event.commission == 32.0
    assert fill_event.timestamp == sample_bar.timestamp


def test_execution_handler_sell(sample_bar: OHLCVBar, sample_sell_order: OrderEvent) -> None:
    """Verifies that ExecutionHandler.execute processes a SELL order with correct fill price, commission, and slippage."""
    # Set up models: slippage = 0.5% (total = 150 * 0.005 * 50 = 37.5), commission = flat $8.0
    slippage_model = PercentageSlippageModel(percentage=0.005)
    commission_model = FixedCommissionModel(commission_per_trade=8.0)
    handler = ExecutionHandler(slippage_model, commission_model)

    fill_event = handler.execute(sample_sell_order, sample_bar)

    # Asserts
    assert isinstance(fill_event, FillEvent)
    assert fill_event.side == "sell"
    assert fill_event.quantity == 50.0

    # Fill price: close - slippage = 150.0 - 37.5 = 112.5
    assert fill_event.fill_price == 112.5
    assert fill_event.slippage == 37.5
    assert fill_event.commission == 8.0


def test_execution_extreme_slippage_raises_backtest_error(
    sample_bar: OHLCVBar, sample_sell_order: OrderEvent
) -> None:
    """Verifies that if slippage pushes the calculated fill price to <= 0, a BacktestError is raised."""
    # Slippage of 200% on SELL will calculate slippage as 150 * 2.0 * 50 = 15000.
    # Fill price: 150.0 - 15000.0 = -14850.0
    slippage_model = PercentageSlippageModel(percentage=2.0)
    commission_model = FixedCommissionModel(commission_per_trade=0.0)
    handler = ExecutionHandler(slippage_model, commission_model)

    with pytest.raises(BacktestError) as exc_info:
        handler.execute(sample_sell_order, sample_bar)

    assert "pushed fill price to non-positive value" in str(exc_info.value)
    assert exc_info.value.ticker == "AAPL"


def test_create_default_execution_handler() -> None:
    """Verifies that create_default_execution_handler returns correctly configured types."""
    handler = create_default_execution_handler()

    assert isinstance(handler, ExecutionHandler)
    assert isinstance(handler.slippage_model, PercentageSlippageModel)
    assert isinstance(handler.commission_model, PercentageCommissionModel)
    assert handler.slippage_model.percentage == 0.001
    assert handler.commission_model.percentage == 0.001
