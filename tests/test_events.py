"""Unit tests for the event-driven backtesting system in QuantForge.

Validates the structure, Pydantic constraints, and properties of MarketEvent,
SignalEvent, OrderEvent, and FillEvent. Also verifies FIFO mechanics, type
preservation, and size tracking of the EventQueue.
"""

from datetime import datetime, timezone
import queue
import pytest
from pydantic import ValidationError

from quantforge.backtester.events import (
    EventQueue,
    FillEvent,
    MarketEvent,
    OrderEvent,
    OrderType,
    SignalEvent,
)
from quantforge.data.models import OHLCVBar
from quantforge.strategies.base import SignalType


@pytest.fixture
def sample_ohlcv_bar() -> OHLCVBar:
    """Fixture supplying a valid OHLCV price bar for testing."""
    return OHLCVBar(
        ticker="AAPL",
        timestamp=datetime.now(timezone.utc),
        open=150.0,
        high=155.0,
        low=149.0,
        close=152.5,
        volume=1000000.0,
    )


def test_market_event_construction(sample_ohlcv_bar: OHLCVBar) -> None:
    """Verifies that MarketEvent constructs correctly and is immutable."""
    now = datetime.now(timezone.utc)
    event = MarketEvent(timestamp=now, bar=sample_ohlcv_bar)

    assert event.event_type == "MARKET"
    assert event.timestamp == now
    assert event.bar == sample_ohlcv_bar

    # Immutability check
    with pytest.raises(ValidationError):
        # Pydantic v2 blocks assignment when frozen=True
        # For direct type checker or python behavior, modifying attributes raises ValidationError
        event.timestamp = datetime.now(timezone.utc)  # type: ignore


def test_signal_event_validation() -> None:
    """Verifies SignalEvent field constraints and validation."""
    now = datetime.now(timezone.utc)

    # Valid SignalEvent
    event = SignalEvent(
        timestamp=now,
        ticker="AAPL",
        signal_type=SignalType.BUY,
        strength=0.85,
        strategy_name="SMACrossover",
    )
    assert event.event_type == "SIGNAL"
    assert event.ticker == "AAPL"
    assert event.signal_type == SignalType.BUY
    assert event.strength == 0.85
    assert event.strategy_name == "SMACrossover"

    # Strength too high (> 1.0)
    with pytest.raises(ValidationError):
        SignalEvent(
            timestamp=now,
            ticker="AAPL",
            signal_type=SignalType.BUY,
            strength=1.1,
            strategy_name="SMACrossover",
        )

    # Strength too low (< 0.0)
    with pytest.raises(ValidationError):
        SignalEvent(
            timestamp=now,
            ticker="AAPL",
            signal_type=SignalType.BUY,
            strength=-0.1,
            strategy_name="SMACrossover",
        )

    # Missing ticker
    with pytest.raises(ValidationError):
        SignalEvent(
            timestamp=now,
            ticker="",
            signal_type=SignalType.BUY,
            strength=0.5,
            strategy_name="SMACrossover",
        )


def test_order_event_validation() -> None:
    """Verifies OrderEvent construction constraints for LIMIT and MARKET orders."""
    now = datetime.now(timezone.utc)

    # Valid MARKET order
    mkt_order = OrderEvent(
        timestamp=now,
        ticker="AAPL",
        order_type=OrderType.MARKET,
        side="buy",
        quantity=100.0,
    )
    assert mkt_order.event_type == "ORDER"
    assert mkt_order.order_type == OrderType.MARKET
    assert mkt_order.limit_price is None

    # Valid LIMIT order
    limit_order = OrderEvent(
        timestamp=now,
        ticker="AAPL",
        order_type=OrderType.LIMIT,
        side="sell",
        quantity=50.0,
        limit_price=155.0,
    )
    assert limit_order.order_type == OrderType.LIMIT
    assert limit_order.limit_price == 155.0

    # Invalid LIMIT order: None limit_price
    with pytest.raises(ValidationError) as exc_info:
        OrderEvent(
            timestamp=now,
            ticker="AAPL",
            order_type=OrderType.LIMIT,
            side="buy",
            quantity=100.0,
            limit_price=None,
        )
    assert "limit_price must not be None for LIMIT orders" in str(exc_info.value)

    # Invalid LIMIT order: non-positive limit_price
    with pytest.raises(ValidationError) as exc_info:
        OrderEvent(
            timestamp=now,
            ticker="AAPL",
            order_type=OrderType.LIMIT,
            side="buy",
            quantity=100.0,
            limit_price=-5.0,
        )
    assert "limit_price must be greater than 0" in str(exc_info.value)

    # Invalid LIMIT order: zero limit_price
    with pytest.raises(ValidationError) as exc_info:
        OrderEvent(
            timestamp=now,
            ticker="AAPL",
            order_type=OrderType.LIMIT,
            side="buy",
            quantity=100.0,
            limit_price=0.0,
        )
    assert "limit_price must be greater than 0" in str(exc_info.value)

    # Invalid Quantity <= 0
    with pytest.raises(ValidationError):
        OrderEvent(
            timestamp=now,
            ticker="AAPL",
            order_type=OrderType.MARKET,
            side="buy",
            quantity=0.0,
        )


def test_fill_event_validation_and_total_cost() -> None:
    """Verifies FillEvent field constraints and proper total_cost calculations."""
    now = datetime.now(timezone.utc)

    # Valid FillEvent
    fill = FillEvent(
        timestamp=now,
        ticker="AAPL",
        side="buy",
        quantity=100.0,
        fill_price=150.0,
        commission=10.0,
        slippage=5.0,
    )
    assert fill.event_type == "FILL"
    assert fill.quantity == 100.0
    assert fill.commission == 10.0
    assert fill.slippage == 5.0

    # Invalid price <= 0
    with pytest.raises(ValidationError):
        FillEvent(
            timestamp=now,
            ticker="AAPL",
            side="buy",
            quantity=100.0,
            fill_price=0.0,
        )

    # Invalid commission < 0
    with pytest.raises(ValidationError):
        FillEvent(
            timestamp=now,
            ticker="AAPL",
            side="buy",
            quantity=100.0,
            fill_price=150.0,
            commission=-1.0,
        )

    # Invalid slippage < 0
    with pytest.raises(ValidationError):
        FillEvent(
            timestamp=now,
            ticker="AAPL",
            side="buy",
            quantity=100.0,
            fill_price=150.0,
            slippage=-0.5,
        )

    # total_cost test for BUY side: qty * price + commission + slippage
    # 100.0 * 150.0 + 10.0 + 5.0 = 15000.0 + 15.0 = 15015.0
    buy_fill = FillEvent(
        timestamp=now,
        ticker="AAPL",
        side="buy",
        quantity=100.0,
        fill_price=150.0,
        commission=10.0,
        slippage=5.0,
    )
    assert buy_fill.total_cost == 15015.0

    # total_cost test for SELL side: qty * price - commission - slippage
    # 100.0 * 150.0 - 10.0 - 5.0 = 15000.0 - 15.0 = 14985.0
    sell_fill = FillEvent(
        timestamp=now,
        ticker="AAPL",
        side="sell",
        quantity=100.0,
        fill_price=150.0,
        commission=10.0,
        slippage=5.0,
    )
    assert sell_fill.total_cost == 14985.0


def test_event_queue_fifo_and_operations(sample_ohlcv_bar: OHLCVBar) -> None:
    """Verifies that EventQueue behaves as a synchronous FIFO queue with correct tracking."""
    eq = EventQueue()

    # Initial state
    assert eq.empty() is True
    assert eq.size() == 0

    # Calling get on empty queue raises Empty
    with pytest.raises(queue.Empty):
        eq.get()

    now = datetime.now(timezone.utc)

    # Create several events
    e1 = MarketEvent(timestamp=now, bar=sample_ohlcv_bar)
    e2 = SignalEvent(
        timestamp=now,
        ticker="AAPL",
        signal_type=SignalType.BUY,
        strength=1.0,
        strategy_name="SMACrossover",
    )
    e3 = OrderEvent(
        timestamp=now,
        ticker="AAPL",
        order_type=OrderType.MARKET,
        side="buy",
        quantity=100.0,
    )
    e4 = FillEvent(
        timestamp=now,
        ticker="AAPL",
        side="buy",
        quantity=100.0,
        fill_price=150.0,
        commission=10.0,
        slippage=5.0,
    )

    # Put onto queue and verify size updates
    eq.put(e1)
    assert eq.empty() is False
    assert eq.size() == 1

    eq.put(e2)
    eq.put(e3)
    eq.put(e4)
    assert eq.size() == 4

    # Get events and verify FIFO ordering, value matching and type preservation
    r1 = eq.get()
    assert r1 == e1
    assert isinstance(r1, MarketEvent)
    assert eq.size() == 3

    r2 = eq.get()
    assert r2 == e2
    assert isinstance(r2, SignalEvent)
    assert eq.size() == 2

    r3 = eq.get()
    assert r3 == e3
    assert isinstance(r3, OrderEvent)
    assert eq.size() == 1

    r4 = eq.get()
    assert r4 == e4
    assert isinstance(r4, FillEvent)
    assert eq.empty() is True
    assert eq.size() == 0

    # Call get on now empty queue
    with pytest.raises(queue.Empty):
        eq.get()
