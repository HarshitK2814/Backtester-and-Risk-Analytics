from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import pandas as pd

@dataclass
class SignalRow:
    index: int; signal: str; quantity: float; price: float; metadata: dict


class BaseStrategy(ABC):
    """Abstract base for all trading strategies."""
    def __init__(self, **params):
        defaults = self.default_params()
        merged = {**defaults, **params}
        self._validate_params(merged)
        self.__dict__.update(merged)
        self.params = merged

    @staticmethod
    @abstractmethod
    def default_params() -> dict[str, Any]: ...

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame: ...

    def _validate_params(self, params: dict): pass

    @classmethod
    def name(cls) -> str: return cls.__name__.replace("Strategy", "").upper()

    @classmethod
    def description(cls) -> str: return (cls.__doc__ or "").strip().split("\n")[0]

    @classmethod
    def parameter_schema(cls) -> dict[str, Any]: return cls.default_params()
