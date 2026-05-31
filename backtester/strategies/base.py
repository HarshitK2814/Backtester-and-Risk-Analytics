"""
Base strategy abstract class.

Every strategy must implement:
  - default_params()  → dict of param_name: default_value
  - generate_signals() → pd.DataFrame with column 'signal' (BUY / SELL / HOLD)
                         and optionally 'quantity'
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class SignalRow:
    index:    int
    signal:   str    # "BUY" | "SELL" | "HOLD"
    quantity: float  # units to trade
    price:    float
    metadata: dict   # any extra info (e.g., grid_level, ema_cross)


class BaseStrategy(ABC):
    """Abstract base for all trading strategies."""

    def __init__(self, **params):
        defaults = self.default_params()
        # Merge: defaults first, then override with any supplied params
        merged = {**defaults, **params}
        self._validate_params(merged)
        self.__dict__.update(merged)
        self.params = merged

    # ── Abstract interface ────────────────────────────────────────────────────

    @staticmethod
    @abstractmethod
    def default_params() -> dict[str, Any]:
        """Return the default parameter set for this strategy."""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals for every candle in df.

        Args:
            df: DataFrame with columns timestamp, open, high, low, close, volume

        Returns:
            df with additional columns:
              signal   : 'BUY' | 'SELL' | 'HOLD'
              quantity : units to trade (may be 0 for HOLD)
        """

    # ── Optional hooks ────────────────────────────────────────────────────────

    def _validate_params(self, params: dict):
        """Override to add parameter validation (raises ValueError on failure)."""

    @classmethod
    def name(cls) -> str:
        return cls.__name__.replace("Strategy", "").upper()

    @classmethod
    def description(cls) -> str:
        return (cls.__doc__ or "").strip().split("\n")[0]

    @classmethod
    def parameter_schema(cls) -> dict[str, Any]:
        """Return parameter descriptions for the API."""
        return cls.default_params()
