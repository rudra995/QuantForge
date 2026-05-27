from typing import Any


class AppException(Exception):
    """Base exception class for all domain-specific errors within QuantForge.

    Attributes:
        message: Human-readable error description.
        context: High-level context details relating to the error.
    """

    def __init__(self, message: str, context: str | None = None) -> None:
        """Initializes the base application exception with optional high-level context.

        Args:
            message: Explanation of the error occurrence.
            context: Additional contextual description.
        """
        super().__init__(message)
        self.message = message
        self.context = context

    def __str__(self) -> str:
        if self.context:
            return f"[{self.context}] {self.message}"
        return self.message


class DataIngestionError(AppException):
    """Raised when data retrieval, parsing, or storage processing fails.

    Attributes:
        ticker: The financial instrument ticker symbol related to the ingestion failure.
        source: The external provider or source from which data was requested.
    """

    def __init__(self, message: str, ticker: str, source: str | None = None) -> None:
        """Initializes DataIngestionError with ticker and source.

        Args:
            message: Explanation of why data ingestion failed.
            ticker: The symbol that failed ingestion.
            source: Source system identifier (e.g. 'yfinance').
        """
        super().__init__(message, context=f"DataIngestion:{ticker}")
        self.ticker = ticker
        self.source = source


class StrategyNotFoundError(AppException):
    """Raised when an attempt to load or execute a non-existent trading strategy is made.

    Attributes:
        strategy_name: Name of the strategy that was not found.
    """

    def __init__(self, message: str, strategy_name: str) -> None:
        """Initializes StrategyNotFoundError.

        Args:
            message: Failure reason details.
            strategy_name: Name of the missing strategy.
        """
        super().__init__(message, context=f"StrategyNotFound:{strategy_name}")
        self.strategy_name = strategy_name


class BacktestError(AppException):
    """Raised when errors occur during strategy execution or performance evaluation in backtesting.

    Attributes:
        ticker: Optional symbol being tested during the failure.
        metric: The calculation metric that encountered a failure, if applicable.
    """

    def __init__(self, message: str, ticker: str | None = None, metric: str | None = None) -> None:
        """Initializes BacktestError.

        Args:
            message: Detailed breakdown of the backtest execution failure.
            ticker: The asset ticker symbol being backtested, if any.
            metric: The specific performance metric calculation that failed, if any.
        """
        ctx_detail = f"Backtest:{ticker}" if ticker else "Backtest"
        super().__init__(message, context=ctx_detail)
        self.ticker = ticker
        self.metric = metric
