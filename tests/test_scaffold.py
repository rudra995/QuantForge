from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from quantforge.core.config import Settings
from quantforge.core.exceptions import (
    AppException,
    BacktestError,
    DataIngestionError,
    StrategyNotFoundError,
)
from quantforge.core.logging import get_request_id, inject_request_id_processor, set_request_id
from quantforge.data.models import (
    EquityCurvePoint,
    OHLCVBar,
    Portfolio,
    Position,
    Trade,
)


def test_settings_parsing() -> None:
    """Verifies that the Settings Pydantic-settings class initializes and validates fields."""
    settings = Settings(
        ENV="prod",
        LOG_LEVEL="warning",
        DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db",
        REDIS_URL="redis://host:6379/1"
    )
    assert settings.ENV == "prod"
    assert settings.LOG_LEVEL == "warning"
    assert "postgresql+asyncpg" in settings.DATABASE_URL
    assert settings.REDIS_URL == "redis://host:6379/1"


def test_custom_exceptions() -> None:
    """Verifies exception instantiation, attributes, and custom formatting."""
    # Base Exception
    base_err = AppException("Generic system error", context="System")
    assert str(base_err) == "[System] Generic system error"
    assert base_err.message == "Generic system error"

    # DataIngestionError
    ingest_err = DataIngestionError("API timeout", ticker="AAPL", source="yfinance")
    assert ingest_err.ticker == "AAPL"
    assert ingest_err.source == "yfinance"
    assert "DataIngestion:AAPL" in str(ingest_err)

    # StrategyNotFoundError
    strat_err = StrategyNotFoundError("Strategy code missing", strategy_name="MomentumClassic")
    assert strat_err.strategy_name == "MomentumClassic"
    assert "StrategyNotFound:MomentumClassic" in str(strat_err)

    # BacktestError
    bt_err = BacktestError("Zero division in Sharpe calculation", ticker="MSFT", metric="Sharpe")
    assert bt_err.ticker == "MSFT"
    assert bt_err.metric == "Sharpe"
    assert "Backtest:MSFT" in str(bt_err)


def test_structlog_context_request_id() -> None:
    """Verifies request_id context variable getters, setters, and structlog injection processor."""
    # Test setting and getting
    set_request_id("test-req-1234")
    assert get_request_id() == "test-req-1234"

    # Test processor behavior
    event_dict = {"event": "successful operation"}
    processed_dict = inject_request_id_processor(None, "info", event_dict)
    assert processed_dict["request_id"] == "test-req-1234"

    # Test clearing
    set_request_id(None)
    assert get_request_id() is None

    event_dict_empty = {"event": "another operation"}
    processed_dict_empty = inject_request_id_processor(None, "info", event_dict_empty)
    assert "request_id" not in processed_dict_empty


def test_ohlcv_validation() -> None:
    """Verifies Pydantic validation rules and model validators for OHLCV bars."""
    now = datetime.now(timezone.utc)
    
    # Valid bar
    bar = OHLCVBar(
        ticker="BTC-USD",
        timestamp=now,
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=10000.0
    )
    assert bar.ticker == "BTC-USD"
    assert bar.high == 105.0

    # Invalid price check: high is less than open
    with pytest.raises(ValidationError) as exc_info:
        OHLCVBar(
            ticker="BTC-USD",
            timestamp=now,
            open=100.0,
            high=95.0,  # Invalid: high < open
            low=90.0,
            close=92.0,
            volume=500.0
        )
    assert "High price" in str(exc_info.value)

    # Invalid negative price check
    with pytest.raises(ValidationError) as exc_info:
        OHLCVBar(
            ticker="BTC-USD",
            timestamp=now,
            open=-5.0,  # Invalid: open must be > 0
            high=10.0,
            low=4.0,
            close=8.0,
            volume=100.0
        )
    assert "Input should be greater than 0" in str(exc_info.value)


def test_trade_validation() -> None:
    """Verifies that Trade model validations work under various scenarios."""
    now = datetime.now(timezone.utc)
    
    trade = Trade(
        id="t-1",
        ticker="AAPL",
        side="buy",
        quantity=50.0,
        price=150.0,
        timestamp=now,
        fees=1.5
    )
    assert trade.side == "buy"
    assert trade.fees == 1.5

    # Invalid side
    with pytest.raises(ValidationError):
        Trade(
            id="t-2",
            ticker="AAPL",
            side="hold",  # Invalid: side must be 'buy' or 'sell'
            quantity=50.0,
            price=150.0,
            timestamp=now,
            fees=1.5
        )


def test_portfolio_positions_and_equity_curve() -> None:
    """Verifies that Portfolio processes structured Position models and computes properties correctly without raw dicts."""
    now = datetime.now(timezone.utc)

    # Instantiate Position objects
    pos_a = Position(ticker="AAPL", quantity=10.0, average_entry_price=150.0)
    pos_b = Position(ticker="MSFT", quantity=5.0, average_entry_price=300.0)

    # Create portfolio
    portfolio = Portfolio(
        cash=5000.0,
        positions={
            "AAPL": pos_a,
            "MSFT": pos_b
        },
        equity_curve=[
            EquityCurvePoint(timestamp=now, equity=8000.0)
        ]
    )

    assert portfolio.cash == 5000.0
    assert len(portfolio.positions) == 2
    assert portfolio.positions["AAPL"].quantity == 10.0
    
    # Verify calculated total open positions cost cost basis
    # Apple: 10 * 150 = 1500; Microsoft: 5 * 300 = 1500; Total = 3000
    assert portfolio.total_positions_cost == 3000.0
    assert len(portfolio.equity_curve) == 1
    assert portfolio.equity_curve[0].equity == 8000.0
