"""Execution handler and market friction models for the QuantForge backtesting system.

This module provides abstract and concrete models for transaction costs (slippage
and commission) and handles simulated execution of orders into filled transactions.
"""

from abc import ABC, abstractmethod

from quantforge.backtester.events import FillEvent, OrderEvent
from quantforge.core import logger
from quantforge.core.exceptions import BacktestError
from quantforge.data.models import OHLCVBar


class SlippageModel(ABC):
    """Abstract base class representing a model for calculating transaction slippage."""

    @abstractmethod
    def calculate(self, order: OrderEvent, bar: OHLCVBar) -> float:
        """Calculates slippage in price/cash units.

        Args:
            order: The order event being simulated.
            bar: The current market price bar (OHLCV) for the asset.

        Returns:
            The total slippage amount.
        """


class FixedSlippageModel(SlippageModel):
    """Slippage model with a fixed cost per unit traded."""

    def __init__(self, slippage_per_unit: float = 0.0) -> None:
        """Initialises the FixedSlippageModel.

        Args:
            slippage_per_unit: Flat cost per traded unit (must be >= 0).

        Raises:
            ValueError: If slippage_per_unit is negative.
        """
        if slippage_per_unit < 0:
            raise ValueError(
                f"slippage_per_unit must be non-negative, got {slippage_per_unit}."
            )
        self.slippage_per_unit = slippage_per_unit

    def calculate(self, order: OrderEvent, bar: OHLCVBar) -> float:
        """Calculates fixed slippage scaling with quantity.

        Args:
            order: The order event being simulated.
            bar: The current market price bar (OHLCV).

        Returns:
            Calculated total slippage.
        """
        return self.slippage_per_unit * order.quantity


class PercentageSlippageModel(SlippageModel):
    """Slippage model calculated as a percentage of the asset close price."""

    def __init__(self, percentage: float = 0.001) -> None:
        """Initialises the PercentageSlippageModel.

        Args:
            percentage: Slipped percentage (e.g. 0.001 = 0.1%, must be >= 0).

        Raises:
            ValueError: If percentage is negative.
        """
        if percentage < 0:
            raise ValueError(
                f"percentage must be non-negative, got {percentage}."
            )
        self.percentage = percentage

    def calculate(self, order: OrderEvent, bar: OHLCVBar) -> float:
        """Calculates percentage-based slippage scaling with quantity and close price.

        Args:
            order: The order event being simulated.
            bar: The current market price bar (OHLCV).

        Returns:
            Calculated total slippage.
        """
        return bar.close * self.percentage * order.quantity


class CommissionModel(ABC):
    """Abstract base class representing a model for calculating broker commissions."""

    @abstractmethod
    def calculate(self, order: OrderEvent, fill_price: float) -> float:
        """Calculates commission in cash units.

        Args:
            order: The order event being simulated.
            fill_price: The simulated per-share execution price.

        Returns:
            The total commission fee.
        """


class FixedCommissionModel(CommissionModel):
    """Commission model with a flat transaction fee per trade."""

    def __init__(self, commission_per_trade: float = 0.0) -> None:
        """Initialises the FixedCommissionModel.

        Args:
            commission_per_trade: Flat cost per transaction (must be >= 0).

        Raises:
            ValueError: If commission_per_trade is negative.
        """
        if commission_per_trade < 0:
            raise ValueError(
                f"commission_per_trade must be non-negative, got {commission_per_trade}."
            )
        self.commission_per_trade = commission_per_trade

    def calculate(self, order: OrderEvent, fill_price: float) -> float:
        """Calculates fixed flat commission per trade.

        Args:
            order: The order event being simulated.
            fill_price: The simulated per-share execution price.

        Returns:
            The flat commission amount.
        """
        return self.commission_per_trade


class PercentageCommissionModel(CommissionModel):
    """Commission model calculated as a percentage of the total transaction size."""

    def __init__(self, percentage: float = 0.001) -> None:
        """Initialises the PercentageCommissionModel.

        Args:
            percentage: Commission percentage (e.g. 0.001 = 0.1%, must be >= 0).

        Raises:
            ValueError: If percentage is negative.
        """
        if percentage < 0:
            raise ValueError(
                f"percentage must be non-negative, got {percentage}."
            )
        self.percentage = percentage

    def calculate(self, order: OrderEvent, fill_price: float) -> float:
        """Calculates commission based on trade volume and fill price.

        Args:
            order: The order event being simulated.
            fill_price: The simulated per-share execution price.

        Returns:
            The calculated percentage commission amount.
        """
        return fill_price * order.quantity * self.percentage


class ExecutionHandler:
    """Simulates market transaction execution by mapping orders into fills.

    Applies realistic friction (slippage and commissions) to ensure backtest integrity.
    """

    def __init__(
        self,
        slippage_model: SlippageModel,
        commission_model: CommissionModel,
    ) -> None:
        """Initialises the ExecutionHandler.

        Args:
            slippage_model: Model utilized to simulate execution slippage.
            commission_model: Model utilized to simulate transaction fees.
        """
        self.slippage_model = slippage_model
        self.commission_model = commission_model

    def execute(self, order: OrderEvent, bar: OHLCVBar) -> FillEvent:
        """Executes an OrderEvent against a given OHLCVBar to produce a FillEvent.

        Args:
            order: The order instruction to execute.
            bar: The current OHLCV price bar representing market liquidity.

        Returns:
            The completed FillEvent.

        Raises:
            BacktestError: If calculated fill price after slippage is non-positive.
        """
        # Calculate slippage amount
        slippage_amount = self.slippage_model.calculate(order, bar)

        # Determine execution fill price based on buy/sell direction (slippage moves against us)
        if order.side == "buy":
            fill_price = bar.close + slippage_amount
        elif order.side == "sell":
            fill_price = bar.close - slippage_amount
        else:
            raise ValueError(f"Unknown order side: {order.side}")

        # Ensure the resulting fill price is strictly positive
        if fill_price <= 0:
            raise BacktestError(
                message=(
                    f"Slippage amount {slippage_amount} pushed fill price to "
                    f"non-positive value: {fill_price} on ticker '{order.ticker}'."
                ),
                ticker=order.ticker,
            )

        # Calculate commission fee
        commission = self.commission_model.calculate(order, fill_price)

        logger.debug(
            "Order executed",
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage=slippage_amount,
        )

        return FillEvent(
            timestamp=bar.timestamp,
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage=slippage_amount,
        )


def create_default_execution_handler() -> ExecutionHandler:
    """Convenience factory creating a standard default ExecutionHandler.

    Returns:
        An ExecutionHandler utilizing 0.1% percentage slippage and commission models.
    """
    return ExecutionHandler(
        slippage_model=PercentageSlippageModel(0.001),
        commission_model=PercentageCommissionModel(0.001),
    )
