"""
Abstract base class for all trading strategies in QuantForge.

Defines the plug-and-play strategy interface:  every concrete strategy must
inherit from BaseStrategy and implement ``generate_signals``.

The ``Signal`` dataclass and ``SignalType`` enum live here as a forward
declaration.  Once ``backtester/events.py`` is implemented the backtester
will consume these same objects via the full ``SignalEvent`` wrapper — no
breaking changes needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from quantforge.core import logger
from quantforge.data.models import OHLCVBar


class SignalType(str, Enum):
    """Enumeration of possible trading signal directions."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Signal:
    """Immutable value object representing a discrete trading signal.

    Attributes:
        ticker: The asset ticker symbol this signal applies to.
        signal_type: Direction of the signal (BUY / SELL / HOLD).
        timestamp: The bar timestamp at which the signal was generated.
        strength: Normalised signal confidence in the range [0.0, 1.0].
    """

    ticker: str
    signal_type: SignalType
    timestamp: datetime
    strength: float

    def __post_init__(self) -> None:
        """Validates that strength is within the allowed [0.0, 1.0] range."""
        if not (0.0 <= self.strength <= 1.0):
            raise ValueError(
                f"Signal strength must be in [0.0, 1.0], got {self.strength}."
            )


class BaseStrategy(ABC):
    """Abstract base class that every QuantForge trading strategy must inherit from.

    Subclasses register themselves via :data:`~quantforge.strategies.registry.strategy_registry`
    and are instantiated by the backtester engine with a ``parameters`` dict.

    Attributes:
        _name: Internal strategy identifier (set once at construction).
        _parameters: Immutable copy of runtime configuration parameters.
    """

    def __init__(self, name: str, parameters: dict[str, Any]) -> None:
        """Initialises the strategy with an identifier and configuration.

        Args:
            name: Human-readable, unique strategy name.
            parameters: Key-value configuration for this strategy instance.
        """
        self._name: str = name
        self._parameters: dict[str, Any] = dict(parameters)  # defensive copy
        logger.debug("Strategy initialised", strategy=name, parameters=parameters)
        self.validate_parameters()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        """Returns the strategy's registered name."""
        return self._name

    @property
    def parameters(self) -> dict[str, Any]:
        """Returns a copy of the strategy parameters to prevent external mutation."""
        return dict(self._parameters)

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_parameters(self) -> None:
        """Validates that all required parameters are present and correctly typed.

        Base implementation is a no-op; subclasses *must* override this to add
        strategy-specific validation and call ``super().validate_parameters()``
        first if chaining is desired.

        Raises:
            ValueError: When a required parameter is missing or malformed.
        """

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def generate_signals(self, bars: list[OHLCVBar]) -> list[Signal]:
        """Analyses a list of price bars and produces a signal per bar.

        Args:
            bars: Chronologically ordered list of OHLCV bars for a single ticker.

        Returns:
            A list of :class:`Signal` objects — one per evaluated bar position
            (strategies may return fewer if they require a warm-up period).

        Raises:
            ValueError: If ``bars`` is empty or contains inconsistent tickers.
        """
