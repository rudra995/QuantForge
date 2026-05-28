"""
Tests for the quantforge.strategies module.

Covers:
- BaseStrategy cannot be instantiated directly (ABC enforcement).
- StrategyRegistry: register, get, unknown key raises StrategyNotFoundError, list.
- SMACrossoverStrategy: valid construction, invalid parameters, signal generation
  correctness on a controlled price series, and signal strength bounds.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from quantforge.core.exceptions import StrategyNotFoundError
from quantforge.data.models import OHLCVBar
from quantforge.strategies.base import BaseStrategy, Signal, SignalType
from quantforge.strategies.registry import StrategyRegistry
from quantforge.strategies.sma_crossover import SMACrossoverStrategy


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_bar(ticker: str, close: float, idx: int = 0) -> OHLCVBar:
    """Construct a minimal OHLCVBar with a synthetic timestamp."""
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc).replace(day=max(1, idx % 28 + 1))
    price = abs(close)
    return OHLCVBar(
        ticker=ticker,
        timestamp=ts,
        open=price,
        high=price * 1.01,
        low=price * 0.99,
        close=price,
        volume=1_000.0,
    )


def _make_bars(ticker: str, closes: list[float]) -> list[OHLCVBar]:
    """Construct a bar series from a list of close prices."""
    bars: list[OHLCVBar] = []
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i, close in enumerate(closes):
        ts = base.replace(day=i % 28 + 1)
        price = abs(close)
        bars.append(
            OHLCVBar(
                ticker=ticker,
                timestamp=ts,
                open=price,
                high=price * 1.005,
                low=price * 0.995,
                close=price,
                volume=500.0,
            )
        )
    return bars


# ── BaseStrategy ──────────────────────────────────────────────────────────────


class TestBaseStrategyAbstract:
    """Ensures BaseStrategy enforces abstract method contract."""

    def test_cannot_instantiate_directly(self) -> None:
        """BaseStrategy is abstract and cannot be instantiated without implementing generate_signals."""
        with pytest.raises(TypeError):
            BaseStrategy(name="abstract", parameters={})  # type: ignore[abstract]

    def test_concrete_subclass_without_generate_signals_raises(self) -> None:
        """A subclass that does not implement generate_signals is still abstract."""

        class Incomplete(BaseStrategy):  # type: ignore[abstract]
            pass

        with pytest.raises(TypeError):
            Incomplete(name="incomplete", parameters={})  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self) -> None:
        """A fully implemented subclass can be instantiated normally."""

        class Minimal(BaseStrategy):
            def generate_signals(self, bars: list[OHLCVBar]) -> list[Signal]:
                return []

        strat = Minimal(name="minimal", parameters={"k": 1})
        assert strat.name == "minimal"
        assert strat.parameters == {"k": 1}

    def test_parameters_property_returns_copy(self) -> None:
        """Mutating the returned dict must not affect internal state."""

        class Minimal(BaseStrategy):
            def generate_signals(self, bars: list[OHLCVBar]) -> list[Signal]:
                return []

        strat = Minimal(name="m", parameters={"a": 1})
        params = strat.parameters
        params["a"] = 999
        assert strat.parameters["a"] == 1  # internal copy unchanged


# ── Signal dataclass ──────────────────────────────────────────────────────────


class TestSignal:
    """Validates Signal immutability and strength constraints."""

    def test_valid_signal_creation(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        sig = Signal(ticker="AAPL", signal_type=SignalType.BUY, timestamp=ts, strength=0.75)
        assert sig.ticker == "AAPL"
        assert sig.signal_type == SignalType.BUY
        assert sig.strength == 0.75

    def test_strength_zero_allowed(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        sig = Signal(ticker="X", signal_type=SignalType.HOLD, timestamp=ts, strength=0.0)
        assert sig.strength == 0.0

    def test_strength_one_allowed(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        sig = Signal(ticker="X", signal_type=SignalType.SELL, timestamp=ts, strength=1.0)
        assert sig.strength == 1.0

    def test_strength_above_one_raises(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="strength"):
            Signal(ticker="X", signal_type=SignalType.BUY, timestamp=ts, strength=1.001)

    def test_strength_below_zero_raises(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="strength"):
            Signal(ticker="X", signal_type=SignalType.BUY, timestamp=ts, strength=-0.1)

    def test_signal_is_immutable(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        sig = Signal(ticker="X", signal_type=SignalType.BUY, timestamp=ts, strength=0.5)
        with pytest.raises((AttributeError, TypeError)):
            sig.ticker = "Y"  # type: ignore[misc]


# ── StrategyRegistry ──────────────────────────────────────────────────────────


class TestStrategyRegistry:
    """Tests StrategyRegistry registration, retrieval, and listing."""

    def _fresh_registry(self) -> StrategyRegistry:
        """Returns an isolated registry to avoid polluting the global singleton."""
        return StrategyRegistry()

    def test_register_and_get(self) -> None:
        reg = self._fresh_registry()

        @reg.register("test_strat")
        class TestStrat(BaseStrategy):
            def generate_signals(self, bars: list[OHLCVBar]) -> list[Signal]:
                return []

        cls = reg.get("test_strat")
        assert cls is TestStrat

    def test_get_unknown_raises_strategy_not_found(self) -> None:
        reg = self._fresh_registry()
        with pytest.raises(StrategyNotFoundError) as exc_info:
            reg.get("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_list_strategies_empty(self) -> None:
        reg = self._fresh_registry()
        assert reg.list_strategies() == []

    def test_list_strategies_sorted(self) -> None:
        reg = self._fresh_registry()

        for name in ("zebra", "alpha", "momentum"):
            @reg.register(name)
            class _Strat(BaseStrategy):
                def generate_signals(self, bars: list[OHLCVBar]) -> list[Signal]:
                    return []

        assert reg.list_strategies() == ["alpha", "momentum", "zebra"]

    def test_duplicate_registration_raises(self) -> None:
        reg = self._fresh_registry()

        @reg.register("dupe")
        class _First(BaseStrategy):
            def generate_signals(self, bars: list[OHLCVBar]) -> list[Signal]:
                return []

        with pytest.raises(ValueError, match="already registered"):
            @reg.register("dupe")
            class _Second(BaseStrategy):
                def generate_signals(self, bars: list[OHLCVBar]) -> list[Signal]:
                    return []

    def test_empty_name_raises(self) -> None:
        reg = self._fresh_registry()
        with pytest.raises(ValueError):
            reg.register("")


# ── SMACrossoverStrategy — parameter validation ───────────────────────────────


class TestSMACrossoverValidation:
    """Parameter validation tests for SMACrossoverStrategy."""

    def _make(self, fast: int, slow: int) -> SMACrossoverStrategy:
        return SMACrossoverStrategy(
            name="sma_crossover",
            parameters={"fast_period": fast, "slow_period": slow},
        )

    def test_valid_parameters(self) -> None:
        strat = self._make(fast=5, slow=20)
        assert strat.name == "sma_crossover"
        assert strat.parameters["fast_period"] == 5

    def test_fast_equals_slow_raises(self) -> None:
        with pytest.raises(ValueError, match="strictly less than"):
            self._make(fast=10, slow=10)

    def test_fast_greater_than_slow_raises(self) -> None:
        with pytest.raises(ValueError, match="strictly less than"):
            self._make(fast=20, slow=5)

    def test_fast_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="fast_period must be > 0"):
            self._make(fast=0, slow=10)

    def test_slow_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="slow_period must be > 0"):
            self._make(fast=5, slow=0)

    def test_negative_fast_raises(self) -> None:
        with pytest.raises(ValueError):
            self._make(fast=-3, slow=10)

    def test_missing_fast_period_raises(self) -> None:
        with pytest.raises(ValueError, match="fast_period"):
            SMACrossoverStrategy(
                name="sma_crossover", parameters={"slow_period": 20}
            )

    def test_missing_slow_period_raises(self) -> None:
        with pytest.raises(ValueError, match="slow_period"):
            SMACrossoverStrategy(
                name="sma_crossover", parameters={"fast_period": 5}
            )


# ── SMACrossoverStrategy — signal generation ──────────────────────────────────


class TestSMACrossoverSignals:
    """Signal generation tests for SMACrossoverStrategy using controlled price series."""

    def _strategy(self, fast: int = 3, slow: int = 5) -> SMACrossoverStrategy:
        return SMACrossoverStrategy(
            name="sma_crossover",
            parameters={"fast_period": fast, "slow_period": slow},
        )

    def test_empty_bars_raises(self) -> None:
        strat = self._strategy()
        with pytest.raises(ValueError, match="at least one"):
            strat.generate_signals([])

    def test_mixed_tickers_raises(self) -> None:
        strat = self._strategy()
        bars = [_make_bar("AAPL", 100, 0), _make_bar("GOOG", 200, 1)]
        with pytest.raises(ValueError, match="single-ticker"):
            strat.generate_signals(bars)

    def test_signal_count_equals_bar_count(self) -> None:
        strat = self._strategy(fast=3, slow=5)
        bars = _make_bars("AAPL", [100.0] * 20)
        signals = strat.generate_signals(bars)
        assert len(signals) == 20

    def test_warm_up_bars_are_hold(self) -> None:
        """The first (slow_period - 1) bars must be HOLD with strength 0.0."""
        strat = self._strategy(fast=3, slow=5)
        bars = _make_bars("AAPL", [100.0] * 20)
        signals = strat.generate_signals(bars)
        # Bars 0..3 (indices 0 to slow_period-2 = 3) are warm-up
        for sig in signals[:4]:
            assert sig.signal_type == SignalType.HOLD
            assert sig.strength == 0.0

    def test_buy_signal_on_upward_crossover(self) -> None:
        """
        Craft a price series where fast SMA crosses above slow SMA at a known index.

        Series (fast=2, slow=4):
          Prices: [10, 10, 10, 10,  5,  5,  20, 20, 20, 20]
                                            ^-- fast crosses above slow here

        - Bars 0-2: warm-up (slow needs 4 bars).
        - Bars 0-5: declining / flat prices keep fast ≤ slow.
        - Around bar 6/7 the big jump causes fast SMA to jump above slow SMA.
        """
        closes = [10.0, 10.0, 10.0, 10.0, 5.0, 5.0, 20.0, 20.0, 20.0, 20.0]
        strat = self._strategy(fast=2, slow=4)
        bars = _make_bars("TEST", closes)
        signals = strat.generate_signals(bars)

        signal_types = [s.signal_type for s in signals]
        assert SignalType.BUY in signal_types, (
            f"Expected at least one BUY signal. Got: {signal_types}"
        )

    def test_sell_signal_on_downward_crossover(self) -> None:
        """
        fast=2, slow=4.
        Start high, then prices crash → fast SMA should cross below slow SMA.
        """
        closes = [20.0, 20.0, 20.0, 20.0, 30.0, 30.0, 5.0, 5.0, 5.0, 5.0]
        strat = self._strategy(fast=2, slow=4)
        bars = _make_bars("TEST", closes)
        signals = strat.generate_signals(bars)

        signal_types = [s.signal_type for s in signals]
        assert SignalType.SELL in signal_types, (
            f"Expected at least one SELL signal. Got: {signal_types}"
        )

    def test_flat_prices_produce_only_hold(self) -> None:
        """Constant price series — fast and slow SMAs are identical, no crossover occurs."""
        closes = [50.0] * 20
        strat = self._strategy(fast=3, slow=5)
        bars = _make_bars("FLAT", closes)
        signals = strat.generate_signals(bars)

        for sig in signals:
            assert sig.signal_type == SignalType.HOLD

    def test_all_signal_strengths_in_bounds(self) -> None:
        """Signal strength must always be in [0.0, 1.0] on any price series."""
        # Use a volatile series to stress-test strength clamping
        rng = np.random.default_rng(seed=42)
        closes = list(rng.uniform(1.0, 500.0, 50))
        strat = self._strategy(fast=5, slow=15)
        bars = _make_bars("VOL", closes)
        signals = strat.generate_signals(bars)

        for sig in signals:
            assert 0.0 <= sig.strength <= 1.0, (
                f"Strength out of bounds: {sig.strength}"
            )

    def test_signal_tickers_match_input(self) -> None:
        """Every generated signal must carry the same ticker as the input bars."""
        closes = list(range(10, 30))
        strat = self._strategy(fast=3, slow=5)
        bars = _make_bars("MSFT", closes)
        signals = strat.generate_signals(bars)

        for sig in signals:
            assert sig.ticker == "MSFT"

    def test_buy_then_sell_sequence(self) -> None:
        """
        A rising-then-falling price series must yield at least one BUY
        followed eventually by at least one SELL.
        """
        # rise then fall
        closes = [10.0] * 4 + [i * 2.0 for i in range(10, 20)] + [15.0] * 4 + [i * -1.0 + 30.0 for i in range(10, 20)]
        # Ensure all closes positive
        closes = [max(0.5, c) for c in closes]
        strat = self._strategy(fast=3, slow=7)
        bars = _make_bars("WAVE", closes)
        signals = strat.generate_signals(bars)

        types = [s.signal_type for s in signals]
        assert SignalType.BUY in types
        assert SignalType.SELL in types

    def test_global_registry_contains_sma_crossover(self) -> None:
        """The module-level strategy_registry singleton should contain 'sma_crossover'."""
        from quantforge.strategies.registry import strategy_registry  # noqa: PLC0415

        assert "sma_crossover" in strategy_registry.list_strategies()

    def test_registry_get_returns_sma_crossover_class(self) -> None:
        """strategy_registry.get('sma_crossover') returns SMACrossoverStrategy."""
        from quantforge.strategies.registry import strategy_registry  # noqa: PLC0415

        cls = strategy_registry.get("sma_crossover")
        assert cls is SMACrossoverStrategy
