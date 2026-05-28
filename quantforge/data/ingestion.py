import asyncio
from datetime import date, datetime
import pandas as pd
import yfinance as yf
from pydantic import ValidationError

from quantforge.core import logger
from quantforge.core.exceptions import DataIngestionError
from quantforge.data.models import OHLCVBar


class DataIngester:
    """Asynchronous data ingestion manager for fetching financial market data.

    Utilizes the `yfinance` package to request historical price bars, and
    performs asynchronous execution using a background worker threadpool.
    """

    async def fetch_historical(
        self, ticker: str, start: date, end: date, interval: str
    ) -> list[OHLCVBar]:
        """Fetches historical price bars (OHLCV) asynchronously for a ticker.

        Uses yfinance in a separate thread via `asyncio.to_thread` to prevent
        blocking the main event loop.

        Args:
            ticker: The ticker symbol of the financial instrument (e.g. 'AAPL').
            start: Start date for the historical range (inclusive).
            end: End date for the historical range (exclusive).
            interval: Bar frequency interval (e.g. '1d', '1h', '5m').

        Returns:
            A list of validated `OHLCVBar` Pydantic models.

        Raises:
            DataIngestionError: If the response is empty, a network failure occurs,
                                or the data fails parsing or validation.
        """
        # Convert standard date objects to string formats expected by yfinance
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        logger.info(
            "Starting historical data fetch",
            ticker=ticker,
            start=start_str,
            end=end_str,
            interval=interval,
        )

        try:
            # Execute yfinance blocking I/O operation inside thread pool
            df = await asyncio.to_thread(self._fetch_sync, ticker, start_str, end_str, interval)
        except Exception as e:
            logger.error(
                "Network or execution failure during historical data fetch",
                ticker=ticker,
                error=str(e),
            )
            raise DataIngestionError(
                message=f"yfinance request failed: {e}", ticker=ticker, source="yfinance"
            ) from e

        # Validate DataFrame existence and completeness
        if df is None or df.empty:
            logger.warning(
                "Empty historical data response received",
                ticker=ticker,
                start=start_str,
                end=end_str,
            )
            raise DataIngestionError(
                message=f"No historical data returned for ticker '{ticker}' in date range.",
                ticker=ticker,
                source="yfinance",
            )

        required_cols = ["Open", "High", "Low", "Close", "Volume"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(
                "Missing required OHLCV columns in DataFrame",
                ticker=ticker,
                missing_columns=missing_cols,
            )
            raise DataIngestionError(
                message=f"yfinance DataFrame is missing required columns: {missing_cols}",
                ticker=ticker,
                source="yfinance",
            )

        # Parse and construct OHLCVBar models
        bars: list[OHLCVBar] = []
        try:
            for timestamp, row in df.iterrows():
                # Safeguard against parsing non-datetime indexes
                if not isinstance(timestamp, (datetime, pd.Timestamp)):
                    raise ValueError(
                        f"Expected datetime index point, got type {type(timestamp)}"
                    )

                # Standardize pandas Timestamp to Python datetime
                dt_val = (
                    timestamp.to_pydatetime()
                    if hasattr(timestamp, "to_pydatetime")
                    else timestamp
                )

                # Pydantic validates boundaries (e.g. High >= Open, close > 0, etc.)
                bar = OHLCVBar(
                    ticker=ticker,
                    timestamp=dt_val,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
                bars.append(bar)
        except ValidationError as e:
            logger.error(
                "Pydantic validation failed during OHLCVBar mapping",
                ticker=ticker,
                validation_errors=e.errors(),
            )
            raise DataIngestionError(
                message=f"Failed to validate financial boundaries or types: {e}",
                ticker=ticker,
                source="yfinance",
            ) from e
        except Exception as e:
            logger.error(
                "Parsing failure during DataFrame rows mapping",
                ticker=ticker,
                error=str(e),
            )
            raise DataIngestionError(
                message=f"Failed to parse and map yfinance DataFrame rows: {e}",
                ticker=ticker,
                source="yfinance",
            ) from e

        logger.info(
            "Successfully fetched historical data",
            ticker=ticker,
            row_count=len(bars),
        )
        return bars

    @staticmethod
    def _fetch_sync(ticker: str, start_str: str, end_str: str, interval: str) -> pd.DataFrame:
        """Synchronous wrapper to execute yfinance API history fetch.

        Args:
            ticker: Ticker symbol.
            start_str: Formatted start date.
            end_str: Formatted end date.
            interval: Data frequency.

        Returns:
            The raw pandas DataFrame of historical metrics.
        """
        ticker_obj = yf.Ticker(ticker)
        return ticker_obj.history(start=start_str, end=end_str, interval=interval)


# Global singleton instance export
data_ingester = DataIngester()
