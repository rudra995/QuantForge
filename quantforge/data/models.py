from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class OHLCVBar(BaseModel):
    """Represents a standard Open, High, Low, Close, Volume price bar for a specific ticker.

    Includes validation to ensure logical price constraints (e.g. High must be greatest).
    """

    ticker: str = Field(..., min_length=1, description="The financial instrument ticker symbol.")
    timestamp: datetime = Field(..., description="Timestamp of the bar period (timezone-aware recommended).")
    open: float = Field(..., gt=0, description="Opening price of the bar.")
    high: float = Field(..., gt=0, description="Highest price reached during the bar interval.")
    low: float = Field(..., gt=0, description="Lowest price reached during the bar interval.")
    close: float = Field(..., gt=0, description="Closing price of the bar.")
    volume: float = Field(..., ge=0, description="Volume of units traded during the bar interval.")

    @model_validator(mode="after")
    def validate_price_boundaries(self) -> "OHLCVBar":
        """Ensures that high is greater than or equal to open/close/low, and low is less than or equal to open/close/high.

        Returns:
            The validated OHLCVBar instance.

        Raises:
            ValueError: If price constraints are violated.
        """
        if self.high < self.open:
            raise ValueError(f"High price ({self.high}) cannot be less than open price ({self.open}).")
        if self.high < self.close:
            raise ValueError(f"High price ({self.high}) cannot be less than close price ({self.close}).")
        if self.low > self.open:
            raise ValueError(f"Low price ({self.low}) cannot be greater than open price ({self.open}).")
        if self.low > self.close:
            raise ValueError(f"Low price ({self.low}) cannot be greater than close price ({self.close}).")
        if self.low > self.high:
            raise ValueError(f"Low price ({self.low}) cannot be greater than high price ({self.high}).")
        return self


class Trade(BaseModel):
    """Represents an executed order or trade in the platform.

    Maintains rigorous validation constraints to ensure negative values cannot be input.
    """

    id: str = Field(..., min_length=1, description="Unique identifier for the trade record.")
    ticker: str = Field(..., min_length=1, description="Ticker symbol of the asset traded.")
    side: Literal["buy", "sell"] = Field(..., description="Execution direction of the trade ('buy' or 'sell').")
    quantity: float = Field(..., gt=0, description="Total volume/quantity of units exchanged.")
    price: float = Field(..., gt=0, description="Execution price per unit of the trade.")
    timestamp: datetime = Field(..., description="Date and time of execution.")
    fees: float = Field(default=0.0, ge=0, description="Transaction fee overheads charged for the trade execution.")


class Position(BaseModel):
    """Represents an active, held position in a single asset.

    Contains quantity and average entry price for tracking unrealized gains.
    """

    ticker: str = Field(..., min_length=1, description="Ticker symbol of the asset.")
    quantity: float = Field(..., description="The asset quantity held. Positive represents a long position, negative represents a short position.")
    average_entry_price: float = Field(..., gt=0, description="Weighted average cost basis per unit.")


class EquityCurvePoint(BaseModel):
    """Represents a snapshot value of the portfolio's total equity at a given time."""

    timestamp: datetime = Field(..., description="The time of the equity evaluation.")
    equity: float = Field(..., ge=0, description="Total equity valuation (cash + market value of open positions).")


class Portfolio(BaseModel):
    """Represents the real-time state of the trading account including cash, open positions, and history.

    Replaces loose dictionaries with structured objects.
    """

    cash: float = Field(default=0.0, ge=0, description="Total liquid cash balance available.")
    positions: dict[str, Position] = Field(
        default_factory=dict,
        description="Active open positions mapped from ticker symbol to Position model."
    )
    equity_curve: list[EquityCurvePoint] = Field(
        default_factory=list,
        description="Historical equity curve points representing portfolio valuation over time."
    )

    @property
    def total_positions_cost(self) -> float:
        """Calculates total capital invested in open positions at average entry price.

        Returns:
            Calculated total value.
        """
        return sum(pos.quantity * pos.average_entry_price for pos in self.positions.values())
