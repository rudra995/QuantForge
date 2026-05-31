"""Tests for quantforge.backtester.engine.

Covers:
- BacktestConfig: valid construction, end <= start rejected, positive capital enforced.
- BacktestEngine: full run produces BacktestResult with correct types and counts.
- total_bars equals the bar count returned by the mock ingester.
- equity_curve is non-empty when at least one trade is executed.
- Flat prices produce zero trades (no crossover → no signals → no orders).
- Engine uses sma_crossover strategy against a known BUY/SELL crossover series.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantforge.backtester.engine import BacktestConfig, BacktestEngine, BacktestResult
from quantforge.backtester.execution import create_default_execution_handler
from quantforge.data.models import OHLCVBar


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_bar(ticker: str, close: float, day: int) -> OHLCVBar:
    """Construct a single OHLCVBar with all required price boundaries satisfied."""
    ts = datetime(2024, 1, day if day <= 28 else 28, tzinfo=timezone.utc)
    price = max(close, 0.01)  # guard against zero / negative
    return OHLCVBar(
        ticker=ticker,
        timestamp=ts,
        open=price,
        high=price * 1.005,
        low=price * 0.995,
        close=price,
        volume=1_000.0,
    )


def _make_crossover_bars(ticker: str = "TEST") -> list[OHLCVBar]:
    """
    Produce 22 bars that contain a clear SMA(fast=3, slow=7) BUY crossover.

    Price series:
      - Bars 0-6 : 10.0 (flat warm-up so slow SMA starts computing)
      - Bars 7-10: 10.0 (still flat, no crossover yet)
      - Bars 11-21: 50.0 (big jump forces fast SMA above slow SMA → BUY then plateau)

    With fast=3, slow=7:
      - Slow SMA needs bars 0-6 (indices 0..6) to settle.
      - After the price jump at bar 11, fast SMA reacts after ~3 bars, slow SMA
        after ~7 bars — a clear upward crossover is guaranteed.
    """
    closes = [10.0] * 11 + [50.0] * 11
    return [_make_bar(ticker, c, i + 1) for i, c in enumerate(closes)]


def _make_flat_bars(ticker: str = "FLAT", n: int = 22) -> list[OHLCVBar]:
    """Produce *n* bars of constant price — no crossover is possible."""
    return [_make_bar(ticker, 100.0, i + 1) for i in range(n)]


def _mock_ingester(bars: list[OHLCVBar]) -> MagicMock:
    """Return a mock DataIngester whose fetch_historical returns *bars*."""
    ingester = MagicMock()
    ingester.fetch_historical = AsyncMock(return_value=bars)
    return ingester


def _crossover_config(ticker: str = "TEST") -> BacktestConfig:
    return BacktestConfig(
        ticker=ticker,
        start=date(2024, 1, 1),
        end=date(2024, 2, 28),
        interval="1d",
        initial_capital=10_000.0,
        strategy_name="sma_crossover",
        strategy_parameters={"fast_period": 3, "slow_period": 7},
    )


def _flat_config(ticker: str = "FLAT") -> BacktestConfig:
    return BacktestConfig(
        ticker=ticker,
        start=date(2024, 1, 1),
        end=date(2024, 2, 28),
        interval="1d",
        initial_capital=10_000.0,
        strategy_name="sma_crossover",
        strategy_parameters={"fast_period": 3, "slow_period": 7},
    )


# ── BacktestConfig ─────────────────────────────────────────────────────────────


class TestBacktestConfig:
    """Validates BacktestConfig Pydantic model construction and constraints."""

    def test_valid_config_constructs(self) -> None:
        """A well-formed config constructs without errors."""
        cfg = BacktestConfig(
            ticker="AAPL",
            start=date(2023, 1, 1),
            end=date(2023, 12, 31),
            initial_capital=50_000.0,
            strategy_name="sma_crossover",
            strategy_parameters={"fast_period": 5, "slow_period": 20},
        )
        assert cfg.ticker == "AAPL"
        assert cfg.interval == "1d"  # default

    def test_default_interval_is_1d(self) -> None:
        cfg = _crossover_config()
        assert cfg.interval == "1d"

    def test_end_equals_start_raises(self) -> None:
        """end == start must be rejected."""
        with pytest.raises(ValueError, match="after"):
            BacktestConfig(
                ticker="X",
                start=date(2024, 6, 1),
                end=date(2024, 6, 1),
                initial_capital=1000.0,
                strategy_name="sma_crossover",
                strategy_parameters={},
            )

    def test_end_before_start_raises(self) -> None:
        """end < start must be rejected."""
        with pytest.raises(ValueError, match="after"):
            BacktestConfig(
                ticker="X",
                start=date(2024, 6, 15),
                end=date(2024, 6, 1),
                initial_capital=1000.0,
                strategy_name="sma_crossover",
                strategy_parameters={},
            )

    def test_zero_initial_capital_raises(self) -> None:
        """initial_capital must be > 0."""
        with pytest.raises(ValueError):
            BacktestConfig(
                ticker="X",
                start=date(2024, 1, 1),
                end=date(2024, 12, 31),
                initial_capital=0.0,
                strategy_name="sma_crossover",
                strategy_parameters={},
            )

    def test_negative_initial_capital_raises(self) -> None:
        with pytest.raises(ValueError):
            BacktestConfig(
                ticker="X",
                start=date(2024, 1, 1),
                end=date(2024, 12, 31),
                initial_capital=-500.0,
                strategy_name="sma_crossover",
                strategy_parameters={},
            )

    def test_empty_ticker_raises(self) -> None:
        with pytest.raises(ValueError):
            BacktestConfig(
                ticker="",
                start=date(2024, 1, 1),
                end=date(2024, 12, 31),
                initial_capital=1000.0,
                strategy_name="sma_crossover",
                strategy_parameters={},
            )

    def test_strategy_parameters_defaults_to_empty_dict(self) -> None:
        cfg = BacktestConfig(
            ticker="AAPL",
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
            initial_capital=1000.0,
            strategy_name="sma_crossover",
        )
        assert cfg.strategy_parameters == {}


# ── BacktestEngine — full run ──────────────────────────────────────────────────


class TestBacktestEngineFullRun:
    """Integration-style tests that wire up the engine against mock data."""

    @pytest.mark.asyncio
    async def test_run_returns_backtest_result_type(self) -> None:
        """Engine.run must return a BacktestResult instance."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        config = _crossover_config()
        result = await engine.run(config)
        assert isinstance(result, BacktestResult)

    @pytest.mark.asyncio
    async def test_total_bars_equals_bar_count(self) -> None:
        """result.total_bars must equal the number of bars returned by the ingester."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_crossover_config())
        assert result.total_bars == len(bars)

    @pytest.mark.asyncio
    async def test_total_signals_equals_bar_count(self) -> None:
        """SMACrossover generates exactly one signal per bar."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_crossover_config())
        assert result.total_signals == len(bars)

    @pytest.mark.asyncio
    async def test_equity_curve_non_empty_on_crossover_bars(self) -> None:
        """Crossover bars trigger at least one fill → equity_curve must be non-empty."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_crossover_config())
        assert len(result.equity_curve) > 0

    @pytest.mark.asyncio
    async def test_trades_list_correct_type(self) -> None:
        """result.trades must be a list (of Trade objects)."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_crossover_config())
        assert isinstance(result.trades, list)

    @pytest.mark.asyncio
    async def test_total_trades_matches_trades_list_length(self) -> None:
        """result.total_trades must equal len(result.trades)."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_crossover_config())
        assert result.total_trades == len(result.trades)

    @pytest.mark.asyncio
    async def test_result_config_preserved(self) -> None:
        """BacktestResult must embed the original config unchanged."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        cfg = _crossover_config()
        result = await engine.run(cfg)
        assert result.config.ticker == cfg.ticker
        assert result.config.initial_capital == cfg.initial_capital
        assert result.config.strategy_name == cfg.strategy_name

    @pytest.mark.asyncio
    async def test_final_equity_is_positive(self) -> None:
        """Final equity must be a positive float for any reasonable backtest."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_crossover_config())
        assert result.final_equity > 0.0

    @pytest.mark.asyncio
    async def test_total_return_pct_is_float(self) -> None:
        """total_return_pct must be a finite float."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_crossover_config())
        assert isinstance(result.total_return_pct, float)

    @pytest.mark.asyncio
    async def test_crossover_bars_produce_at_least_one_trade(self) -> None:
        """The known-crossover series must trigger at least one fill/trade."""
        bars = _make_crossover_bars()
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_crossover_config())
        assert result.total_trades >= 1, (
            f"Expected at least 1 trade but got {result.total_trades}. "
            "The crossover series should trigger a BUY."
        )


# ── Flat prices → zero trades ──────────────────────────────────────────────────


class TestBacktestEngineFlatPrices:
    """With constant prices the SMA crossover never fires — zero trades expected."""

    @pytest.mark.asyncio
    async def test_flat_prices_produce_zero_trades(self) -> None:
        """Constant price series → no crossover → no signals → no orders → 0 trades."""
        bars = _make_flat_bars(n=22)
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_flat_config())
        assert result.total_trades == 0

    @pytest.mark.asyncio
    async def test_flat_prices_equity_curve_empty(self) -> None:
        """No fills on flat prices → equity_curve remains empty (only filled on fills)."""
        bars = _make_flat_bars(n=22)
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_flat_config())
        assert result.equity_curve == []

    @pytest.mark.asyncio
    async def test_flat_prices_total_bars_correct(self) -> None:
        n = 22
        bars = _make_flat_bars(n=n)
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_flat_config())
        assert result.total_bars == n

    @pytest.mark.asyncio
    async def test_flat_prices_final_equity_equals_initial(self) -> None:
        """With zero trades, final equity equals the initial capital."""
        bars = _make_flat_bars(n=22)
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_flat_config())
        assert result.final_equity == pytest.approx(10_000.0)

    @pytest.mark.asyncio
    async def test_flat_prices_total_return_pct_is_zero(self) -> None:
        bars = _make_flat_bars(n=22)
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(
            execution_handler=create_default_execution_handler(),
            data_ingester=ingester,
        )
        result = await engine.run(_flat_config())
        assert result.total_return_pct == pytest.approx(0.0)


# ── Engine defaults ────────────────────────────────────────────────────────────


class TestBacktestEngineDefaults:
    """Verifies the engine uses sensible defaults when no arguments are provided."""

    def test_engine_constructs_with_no_args(self) -> None:
        """BacktestEngine() must construct without error using all defaults."""
        engine = BacktestEngine()
        assert engine is not None

    @pytest.mark.asyncio
    async def test_engine_uses_injected_ingester(self) -> None:
        """The engine must call fetch_historical on the injected ingester."""
        bars = _make_flat_bars(n=22)
        ingester = _mock_ingester(bars)
        engine = BacktestEngine(data_ingester=ingester)
        await engine.run(_flat_config())
        ingester.fetch_historical.assert_awaited_once()
