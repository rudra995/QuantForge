"""
SMA Crossover Strategy — first concrete strategy in QuantForge.

Generates BUY signals when the fast simple moving average (SMA) crosses *above*
the slow SMA, SELL signals when it crosses *below*, and HOLD otherwise.

Signal strength is the normalised percentage divergence between the two SMAs::

    strength = abs(fast_sma[-1] - slow_sma[-1]) / slow_sma[-1]

Clamped to [0.0, 1.0] to satisfy the Signal contract.

Only ``numpy`` is used for SMA computation — no pandas dependency.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from quantforge.core import logger
from quantforge.data.models import OHLCVBar
from quantforge.strategies.base import BaseStrategy, Signal, SignalType
from quantforge.strategies.registry import strategy_registry


@strategy_registry.register("sma_crossover")
class SMACrossoverStrategy(BaseStrategy):
    """Simple Moving Average (SMA) crossover strategy.

    Emits:
    - **BUY** when the fast SMA crosses *above* the slow SMA.
    - **SELL** when the fast SMA crosses *below* the slow SMA.
    - **HOLD** on all other bars (including warm-up bars without a full window).

    Required parameters:
        fast_period (int): Window length for the fast SMA.  Must be > 0 and
            strictly less than ``slow_period``.
        slow_period (int): Window length for the slow SMA.  Must be > 0 and
            strictly greater than ``fast_period``.
    """

    def __init__(self, name: str, parameters: dict[str, Any]) -> None:
        """Initialises the SMA crossover strategy and caches typed parameter values.

        Args:
            name: Strategy identifier (typically ``"sma_crossover"``).
            parameters: Must contain ``fast_period`` and ``slow_period`` as ints.
        """
        # validate_parameters is called inside super().__init__
        super().__init__(name, parameters)
        self._fast_period: int = int(self._parameters["fast_period"])
        self._slow_period: int = int(self._parameters["slow_period"])

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_parameters(self) -> None:
        """Validates fast_period and slow_period constraints.

        Raises:
            ValueError: If any constraint is violated.
        """
        required = ("fast_period", "slow_period")
        for key in required:
            if key not in self._parameters:
                raise ValueError(
                    f"SMACrossoverStrategy requires parameter '{key}'."
                )

        try:
            fast = int(self._parameters["fast_period"])
            slow = int(self._parameters["slow_period"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "fast_period and slow_period must be integer-compatible values."
            ) from exc

        if fast <= 0:
            raise ValueError(
                f"fast_period must be > 0, got {fast}."
            )
        if slow <= 0:
            raise ValueError(
                f"slow_period must be > 0, got {slow}."
            )
        if fast >= slow:
            raise ValueError(
                f"fast_period ({fast}) must be strictly less than "
                f"slow_period ({slow})."
            )

    # ── Signal generation ─────────────────────────────────────────────────────

    def generate_signals(self, bars: list[OHLCVBar]) -> list[Signal]:
        """Computes SMA crossover signals for the supplied bar series.

        The first ``slow_period - 1`` bars are emitted as HOLD with strength 0.0
        because there is insufficient history to compute both SMAs.

        Args:
            bars: Chronologically ordered OHLCV bars for a **single** ticker.
                Must not be empty.

        Returns:
            A list of :class:`~quantforge.strategies.base.Signal` objects,
            one per input bar.

        Raises:
            ValueError: If ``bars`` is empty or contains mixed tickers.
        """
        if not bars:
            raise ValueError("generate_signals requires at least one OHLCVBar.")

        tickers = {bar.ticker for bar in bars}
        if len(tickers) > 1:
            raise ValueError(
                f"generate_signals expects a single-ticker bar series, "
                f"got: {tickers}."
            )

        ticker = bars[0].ticker
        closes: np.ndarray = np.array([bar.close for bar in bars], dtype=np.float64)
        n = len(closes)

        logger.debug(
            "Generating SMA crossover signals",
            strategy=self._name,
            ticker=ticker,
            bar_count=n,
            fast_period=self._fast_period,
            slow_period=self._slow_period,
        )

        # Pre-compute rolling SMAs using cumulative-sum trick for O(n) time
        fast_sma: np.ndarray = self._rolling_mean(closes, self._fast_period)
        slow_sma: np.ndarray = self._rolling_mean(closes, self._slow_period)

        signals: list[Signal] = []

        for i, bar in enumerate(bars):
            # Not enough bars yet for the slow SMA window → HOLD
            if i < self._slow_period - 1:
                signals.append(
                    Signal(
                        ticker=ticker,
                        signal_type=SignalType.HOLD,
                        timestamp=bar.timestamp,
                        strength=0.0,
                    )
                )
                continue

            current_fast = fast_sma[i]
            current_slow = slow_sma[i]

            # Normalised divergence, clamped to [0.0, 1.0]
            strength = float(
                min(abs(current_fast - current_slow) / current_slow, 1.0)
            )

            # Determine crossover direction by inspecting previous bar's SMAs
            prev_idx = i - 1
            if prev_idx >= self._slow_period - 1:
                prev_fast = fast_sma[prev_idx]
                prev_slow = slow_sma[prev_idx]

                if prev_fast <= prev_slow and current_fast > current_slow:
                    signal_type = SignalType.BUY
                elif prev_fast >= prev_slow and current_fast < current_slow:
                    signal_type = SignalType.SELL
                else:
                    signal_type = SignalType.HOLD
            else:
                # First bar that has a valid slow SMA but no previous reference
                signal_type = SignalType.HOLD

            signals.append(
                Signal(
                    ticker=ticker,
                    signal_type=signal_type,
                    timestamp=bar.timestamp,
                    strength=strength,
                )
            )

        logger.info(
            "SMA crossover signal generation complete",
            strategy=self._name,
            ticker=ticker,
            total_signals=len(signals),
            buys=sum(1 for s in signals if s.signal_type == SignalType.BUY),
            sells=sum(1 for s in signals if s.signal_type == SignalType.SELL),
        )

        return signals

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
        """Computes a simple rolling mean using cumulative sums (O(n)).

        Positions with fewer than ``window`` prior values are filled with
        ``np.nan`` so callers can detect the warm-up period explicitly.

        Args:
            values: 1-D array of floating-point prices.
            window: Rolling window size (must be >= 1).

        Returns:
            Array of the same length as ``values`` with rolling means.
        """
        result = np.full_like(values, np.nan)
        cumsum = np.cumsum(values)
        # Indices where a full window is available
        result[window - 1:] = (
            cumsum[window - 1:]
            - np.concatenate(([0.0], cumsum[:-window]))
        ) / window
        return result
