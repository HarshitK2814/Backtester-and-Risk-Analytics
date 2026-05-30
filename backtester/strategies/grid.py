from __future__ import annotations
import logging
from typing import Any
import numpy as np
import pandas as pd
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

class GridStrategy(BaseStrategy):
    """Grid strategy: buy dips and sell rallies within a defined price range."""

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "upper_bound": 45_000.0, "lower_bound": 35_000.0,
            "num_levels": 5, "spacing": "linear",
            "invest_per_level_usd": 500.0, "quantity_per_level": 0.001,
        }

    def _validate_params(self, params):
        if params["lower_bound"] >= params["upper_bound"]:
            raise ValueError("lower_bound must be < upper_bound")
        if not (2 <= params["num_levels"] <= 50):
            raise ValueError("num_levels must be 2-50")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        levels = self._build_levels()
        logger.info("Grid levels (%s): %s", self.spacing, [round(l, 2) for l in levels])
        signals = ["HOLD"] * len(df); qtys = [0.0] * len(df); meta = [{}] * len(df)
        prev_price = None
        for i, row in df.iterrows():
            price = float(row["close"])
            if prev_price is None:
                prev_price = price; continue
            signal, qty, triggered = self._check_crossings(prev_price, price, levels, price)
            signals[i] = signal; qtys[i] = qty; meta[i] = {"triggered_levels": triggered}
            prev_price = price
        df["signal"] = signals; df["quantity"] = qtys; df["meta"] = meta
        return df

    def _build_levels(self):
        if self.spacing == "exponential":
            return list(np.exp(np.linspace(np.log(self.lower_bound), np.log(self.upper_bound), self.num_levels)))
        return list(np.linspace(self.lower_bound, self.upper_bound, self.num_levels))

    def _qty(self, price, count=1):
        invest = getattr(self, "invest_per_level_usd", 0)
        if invest > 0 and price > 0: return invest * count / price
        return self.quantity_per_level * count

    def _check_crossings(self, prev, curr, levels, price):
        buy_levels  = [l for l in levels if prev > l >= curr]
        sell_levels = [l for l in levels if prev < l <= curr]
        if sell_levels: return "SELL", self._qty(price, len(sell_levels)), sell_levels
        if buy_levels:  return "BUY",  self._qty(price, len(buy_levels)),  buy_levels
        return "HOLD", 0.0, []
