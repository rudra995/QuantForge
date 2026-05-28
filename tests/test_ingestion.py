from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from quantforge.core.exceptions import DataIngestionError
from quantforge.data.ingestion import DataIngester, data_ingester

#helps reuse data in multiple test cases
@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    """Fixture returning a standard pandas DataFrame in yfinance history format."""
    timestamps = [
        pd.Timestamp("2026-05-20 09:30:00", tz="UTC"),
        pd.Timestamp("2026-05-21 09:30:00", tz="UTC"),
    ]
    data = {
        "Open": [100.0, 102.5],
        "High": [105.0, 104.0],
        "Low": [95.0, 101.0],
        "Close": [102.0, 103.0],
        "Volume": [10000.0, 15000.0],
    }
    return pd.DataFrame(data, index=timestamps)

#converts sync to asyn since api is asynch
@pytest.mark.asyncio
async def test_fetch_historical_success(sample_ohlcv_df: pd.DataFrame) -> None:
    """Tests a successful data ingestion flow, mapping dataframe rows to OHLCVBar models."""
    ingester = DataIngester()
    start_date = date(2026, 5, 20)
    end_date = date(2026, 5, 22)

    with patch("quantforge.data.ingestion.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = sample_ohlcv_df
        mock_ticker_cls.return_value = mock_ticker

        bars = await ingester.fetch_historical("AAPL", start_date, end_date, "1d")

        # Assert correct length and attributes
        assert len(bars) == 2
        assert bars[0].ticker == "AAPL"
        assert bars[0].open == 100.0
        assert bars[0].high == 105.0
        assert bars[0].low == 95.0
        assert bars[0].close == 102.0
        assert bars[0].volume == 10000.0
        assert isinstance(bars[0].timestamp, datetime)

        # Assert correct arguments passed to yfinance
        mock_ticker_cls.assert_called_once_with("AAPL")
        mock_ticker.history.assert_called_once_with(
            start="2026-05-20", end="2026-05-22", interval="1d"
        )


@pytest.mark.asyncio
async def test_fetch_historical_empty_response() -> None:
    """Tests that DataIngester raises DataIngestionError when yfinance returns empty data."""
    ingester = DataIngester()
    empty_df = pd.DataFrame()

    with patch("quantforge.data.ingestion.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = empty_df
        mock_ticker_cls.return_value = mock_ticker

        with pytest.raises(DataIngestionError) as exc_info:
            await ingester.fetch_historical("INVALID", date(2026, 5, 20), date(2026, 5, 22), "1d")

        assert exc_info.value.ticker == "INVALID"
        assert exc_info.value.source == "yfinance"
        assert "No historical data returned" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_historical_network_error() -> None:
    """Tests that DataIngester raises DataIngestionError when yfinance encounters network/IO failures."""
    ingester = DataIngester()

    with patch("quantforge.data.ingestion.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("Connection timed out or DNS failure")
        mock_ticker_cls.return_value = mock_ticker

        with pytest.raises(DataIngestionError) as exc_info:
            await ingester.fetch_historical("AAPL", date(2026, 5, 20), date(2026, 5, 22), "1d")

        assert exc_info.value.ticker == "AAPL"
        assert exc_info.value.source == "yfinance"
        assert "yfinance request failed" in str(exc_info.value) #yfin server down.


@pytest.mark.asyncio
async def test_fetch_historical_missing_columns(sample_ohlcv_df: pd.DataFrame) -> None:
    """Tests that DataIngester raises DataIngestionError when DataFrame is missing required columns."""
    ingester = DataIngester()
    malformed_df = sample_ohlcv_df.drop(columns=["Open"])

    with patch("quantforge.data.ingestion.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = malformed_df
        mock_ticker_cls.return_value = mock_ticker

        with pytest.raises(DataIngestionError) as exc_info:
            await ingester.fetch_historical("AAPL", date(2026, 5, 20), date(2026, 5, 22), "1d")

        assert exc_info.value.ticker == "AAPL"
        assert exc_info.value.source == "yfinance"
        assert "missing required columns" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_historical_validation_failure() -> None:
    """Tests that DataIngester raises DataIngestionError when OHLCV boundaries are violated."""
    ingester = DataIngester()

    # Create invalid price bar (High price is less than Open price)
    timestamps = [pd.Timestamp("2026-05-20 09:30:00")]
    invalid_data = {
        "Open": [100.0],
        "High": [90.0],  # Invalid: High < Open
        "Low": [85.0],
        "Close": [95.0],
        "Volume": [1000.0],
    }
    invalid_df = pd.DataFrame(invalid_data, index=timestamps)

    with patch("quantforge.data.ingestion.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = invalid_df
        mock_ticker_cls.return_value = mock_ticker

        with pytest.raises(DataIngestionError) as exc_info:
            await ingester.fetch_historical("AAPL", date(2026, 5, 20), date(2026, 5, 22), "1d")

        assert exc_info.value.ticker == "AAPL"
        assert exc_info.value.source == "yfinance"
        assert "Failed to validate financial boundaries" in str(exc_info.value)


def test_singleton_export() -> None:
    """Verifies that data_ingester singleton instance is exported correctly,for consistency instead of 
    calling the class we are calling the object."""
    assert isinstance(data_ingester, DataIngester)
