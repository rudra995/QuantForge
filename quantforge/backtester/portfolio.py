"""Portfolio management components for the event-driven backtesting system in QuantForge.

This module contains the PortfolioManager class which handles updating portfolio holdings,
cash balances, and equity tracking upon execution fills and signal occurrences.
"""

import math
from datetime import datetime, timezone
from typing import Any

from quantforge.backtester.events import FillEvent, OrderEvent, OrderType, SignalEvent
from quantforge.core import logger
from quantforge.core.exceptions import BacktestError
from quantforge.data.models import EquityCurvePoint, Portfolio, Position
from quantforge.strategies.base import SignalType

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc


class PortfolioManager:
    """Stateful, mutable manager that owns the Portfolio model and processes events.

    Updates cash, positions, and equity curve points consistently and handles sizing
    for buy and sell signals.
    """

    def __init__(self, initial_capital: float) -> None:
        """Initialises the PortfolioManager with a starting capital.

        Args:
            initial_capital: The starting cash amount for the backtest. Must be greater than 0.

        Raises:
            ValueError: If initial_capital is less than or equal to 0.
        """
        if initial_capital <= 0:
            raise ValueError(
                f"initial_capital must be strictly greater than 0, got {initial_capital}."
            )

        self._initial_capital: float = initial_capital
        self._portfolio: Portfolio = Portfolio(
            cash=initial_capital,
            positions={},
            equity_curve=[],
        )
        logger.info(
            "PortfolioManager initialised",
            initial_capital=initial_capital,
            cash=self._portfolio.cash,
        )

    @property
    def portfolio(self) -> Portfolio:
        """Returns the underlying Portfolio model."""
        return self._portfolio

    @property
    def cash(self) -> float:
        """Returns the current cash balance."""
        return self._portfolio.cash

    @property
    def equity_curve(self) -> list[EquityCurvePoint]:
        """Returns the historical equity curve points."""
        return self._portfolio.equity_curve

    @property
    def positions(self) -> dict[str, Position]:
        """Returns the active open positions."""
        return self._portfolio.positions

    def on_fill(self, fill: FillEvent, current_prices: dict[str, float]) -> None:
        """Processes a FillEvent and updates cash + positions.

        Args:
            fill: The completed trade execution event.
            current_prices: Real-time price mapping for all active tickers.

        Raises:
            BacktestError: If trying to sell more than held.
        """
        logger.debug(
            "Processing fill event",
            ticker=fill.ticker,
            side=fill.side,
            quantity=fill.quantity,
            price=fill.fill_price,
            total_cost=fill.total_cost,
        )

        if fill.side == "buy":
            # Deduct cost from cash
            self._portfolio.cash -= fill.total_cost

            # Update or add position
            if fill.ticker in self._portfolio.positions:
                pos = self._portfolio.positions[fill.ticker]
                new_quantity = pos.quantity + fill.quantity
                # Weighted average entry price
                new_average_entry_price = (
                    (pos.quantity * pos.average_entry_price)
                    + (fill.quantity * fill.fill_price)
                ) / new_quantity

                self._portfolio.positions[fill.ticker] = Position(
                    ticker=fill.ticker,
                    quantity=new_quantity,
                    average_entry_price=new_average_entry_price,
                )
            else:
                self._portfolio.positions[fill.ticker] = Position(
                    ticker=fill.ticker,
                    quantity=fill.quantity,
                    average_entry_price=fill.fill_price,
                )
        elif fill.side == "sell":
            if fill.ticker not in self._portfolio.positions:
                raise BacktestError(
                    message=f"Attempted to sell {fill.quantity} units of {fill.ticker} but no position is held.",
                    ticker=fill.ticker,
                )

            pos = self._portfolio.positions[fill.ticker]
            if fill.quantity > pos.quantity:
                raise BacktestError(
                    message=(
                        f"Cannot sell {fill.quantity} units of {fill.ticker} "
                        f"when only {pos.quantity} are held."
                    ),
                    ticker=fill.ticker,
                )

            # Add cost to cash
            self._portfolio.cash += fill.total_cost

            # Reduce position quantity
            new_quantity = pos.quantity - fill.quantity
            if new_quantity == 0:
                del self._portfolio.positions[fill.ticker]
            else:
                self._portfolio.positions[fill.ticker] = Position(
                    ticker=fill.ticker,
                    quantity=new_quantity,
                    average_entry_price=pos.average_entry_price,
                )
        else:
            raise ValueError(f"Unknown fill side: {fill.side}")

        # Update equity curve
        self._record_equity(current_prices)

    def _record_equity(self, current_prices: dict[str, float]) -> None:
        """Computes and appends the total equity curve point.

        Args:
            current_prices: Real-time price mapping for all active tickers.

        Raises:
            BacktestError: If a position's ticker is missing from current_prices.
        """
        total_equity = self._portfolio.cash
        for ticker, pos in self._portfolio.positions.items():
            if ticker not in current_prices:
                raise BacktestError(
                    message=f"Missing current price for ticker '{ticker}' while recording equity.",
                    ticker=ticker,
                )
            total_equity += pos.quantity * current_prices[ticker]

        self._portfolio.equity_curve.append(
            EquityCurvePoint(timestamp=datetime.now(UTC), equity=total_equity)
        )
        logger.debug(
            "Recorded equity curve point",
            equity=total_equity,
            positions_count=len(self._portfolio.positions),
        )

    def on_signal(
        self, signal: SignalEvent, current_prices: dict[str, float]
    ) -> OrderEvent | None:
        """Converts a SignalEvent into an OrderEvent using simple position sizing.

        Args:
            signal: The strategy signal event.
            current_prices: Real-time price mapping for sizing calculation.

        Returns:
            An OrderEvent representing the trade instruction, or None if no action.

        Raises:
            BacktestError: If the signal ticker is missing from current_prices for a BUY signal.
        """
        if signal.signal_type == SignalType.HOLD:
            return None

        elif signal.signal_type == SignalType.BUY:
            if signal.ticker not in current_prices:
                raise BacktestError(
                    message=f"Missing current price for ticker '{signal.ticker}' to size BUY signal.",
                    ticker=signal.ticker,
                )

            current_price = current_prices[signal.ticker]
            if current_price <= 0:
                raise BacktestError(
                    message=f"Invalid price {current_price} for sizing BUY signal on '{signal.ticker}'.",
                    ticker=signal.ticker,
                )

            # Use 95% of available cash, floor to whole units
            size = math.floor((self._portfolio.cash * 0.95) / current_price)
            if size < 1:
                logger.debug(
                    "Insufficient cash to place BUY order",
                    cash=self._portfolio.cash,
                    required=current_price * 0.95,
                )
                return None

            return OrderEvent(
                timestamp=datetime.now(UTC),
                ticker=signal.ticker,
                order_type=OrderType.MARKET,
                side="buy",
                quantity=float(size),
            )

        elif signal.signal_type == SignalType.SELL:
            position = self._portfolio.positions.get(signal.ticker)
            if position is None or position.quantity <= 0:
                logger.debug(
                    "No position held to size SELL signal", ticker=signal.ticker
                )
                return None

            # Size is the full current position quantity
            size = position.quantity
            return OrderEvent(
                timestamp=datetime.now(UTC),
                ticker=signal.ticker,
                order_type=OrderType.MARKET,
                side="sell",
                quantity=float(size),
            )

        else:
            raise ValueError(f"Unknown signal type: {signal.signal_type}")
