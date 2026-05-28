"""
StrategyRegistry — a dict-backed registry for trading strategy classes.

Strategies self-register via the ``@strategy_registry.register("name")``
decorator.  The engine resolves concrete strategy classes at runtime by name,
keeping the backtester fully decoupled from strategy implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from quantforge.core import logger
from quantforge.core.exceptions import StrategyNotFoundError

if TYPE_CHECKING:
    from quantforge.strategies.base import BaseStrategy


class StrategyRegistry:
    """Central registry mapping strategy names to their implementation classes.

    Usage::

        @strategy_registry.register("my_strategy")
        class MyStrategy(BaseStrategy):
            ...

        cls = strategy_registry.get("my_strategy")
        instance = cls(name="my_strategy", parameters={...})
    """

    def __init__(self) -> None:
        """Initialises an empty registry."""
        self._registry: dict[str, type[BaseStrategy]] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, name: str):  # noqa: ANN201  — returns a decorator
        """Class decorator that registers a strategy implementation under *name*.

        Args:
            name: The unique identifier used to look up the strategy later.

        Returns:
            A decorator that registers the decorated class and returns it
            unchanged so normal class semantics are preserved.

        Raises:
            ValueError: If *name* is empty or already registered.
        """
        if not name or not name.strip():
            raise ValueError("Strategy registration name must be a non-empty string.")

        def decorator(cls: type[BaseStrategy]) -> type[BaseStrategy]:
            if name in self._registry:
                raise ValueError(
                    f"Strategy '{name}' is already registered. "
                    "Use a unique name per strategy class."
                )
            self._registry[name] = cls
            logger.debug("Strategy registered", strategy_name=name, cls=cls.__name__)
            return cls

        return decorator

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def get(self, name: str) -> type[BaseStrategy]:
        """Retrieves the strategy class associated with *name*.

        Args:
            name: The registered strategy identifier.

        Returns:
            The strategy class (not an instance).

        Raises:
            StrategyNotFoundError: When no strategy is registered under *name*.
        """
        if name not in self._registry:
            raise StrategyNotFoundError(
                message=(
                    f"Strategy '{name}' is not registered. "
                    f"Available strategies: {self.list_strategies()}"
                ),
                strategy_name=name,
            )
        return self._registry[name]

    def list_strategies(self) -> list[str]:
        """Returns a sorted list of all registered strategy names.

        Returns:
            Alphabetically sorted list of registered strategy identifiers.
        """
        return sorted(self._registry.keys())


# ── Module-level singleton ─────────────────────────────────────────────────────
strategy_registry: StrategyRegistry = StrategyRegistry()
"""Shared registry instance.  Import this singleton everywhere strategies are
registered or resolved."""
