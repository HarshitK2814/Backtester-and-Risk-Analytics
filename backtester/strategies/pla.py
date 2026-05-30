from __future__ import annotations
import logging
from typing import Any
import pandas as pd
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

def _ema(series, period): return series.ewm(span=period, adjust=False).mean()

class PLAStrategy(BaseStrategy):
    """PLA strategy: EMA crossover entries with cascading position averaging."""

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "fast_ema": 12, "slow_ema": 26,
            "entry_levels": [0.0, -1.0, -2.5, -4.0],
            "invest_per_level_usd": [300.0, 300.0, 600.0, 900.0],
            "entry_quantities": [0.001, 0.001, 0.002, 0.003],
            "exit_type": "crossover",
            "take_profit_pct": 5.0, "stop_loss_pct": 3.0,
        }

    def _validate_params(self, params):
        if params["fast_ema"] >= params["slow_ema"]:
            raise ValueError("fast_ema must be < slow_ema")

    def _qty(self, price, level_idx):
        invest_list = getattr(self, "invest_per_level_usd", [])
        if invest_list and level_idx < len(invest_list) and invest_list[level_idx] > 0 and price > 0:
            return invest_list[level_idx] / price
        qty_list = getattr(self, "entry_quantities", [0.001])
        return qty_list[level_idx] if level_idx < len(qty_list) else qty_list[-1]

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = _ema(df["close"], self.fast_ema)
        df["ema_slow"] = _ema(df["close"], self.slow_ema)
        df["ema_diff"] = df["ema_fast"] - df["ema_slow"]
        n = len(df)
        signals = ["HOLD"] * n; qtys = [0.0] * n; meta = [{}] * n
        in_position = False; entry_price = 0.0; avg_entry = 0.0
        total_qty = 0.0; levels_filled: set = set()
        for i in range(1, n):
            prev_diff = df.iloc[i-1]["ema_diff"]
            curr_diff = df.iloc[i]["ema_diff"]
            price     = float(df.iloc[i]["close"])
            if not in_position and prev_diff <= 0 and curr_diff > 0:
                qty0 = self._qty(price, 0)
                signals[i] = "BUY"; qtys[i] = qty0; meta[i] = {"pla_level": 0, "ema_cross": "golden"}
                in_position = True; entry_price = price; avg_entry = price
                total_qty = qty0; levels_filled = {0}; continue
            if in_position:
                for lvl_idx in range(1, len(self.entry_levels)):
                    if lvl_idx in levels_filled: continue
                    qty   = self._qty(price, lvl_idx)
                    target = entry_price * (1 + self.entry_levels[lvl_idx] / 100)
                    if price <= target:
                        new_cost = avg_entry * total_qty + price * qty
                        total_qty += qty; avg_entry = new_cost / total_qty
                        if signals[i] != "BUY":
                            signals[i] = "BUY"; qtys[i] = qty; meta[i] = {"pla_level": lvl_idx}
                        else:
                            qtys[i] += qty
                        levels_filled.add(lvl_idx)
            if in_position:
                exit_triggered = False
                if self.exit_type == "crossover" and prev_diff >= 0 and curr_diff < 0:
                    exit_triggered = True
                elif self.exit_type == "take_profit" and avg_entry > 0:
                    if (price - avg_entry) / avg_entry * 100 >= self.take_profit_pct:
                        exit_triggered = True
                elif self.exit_type == "stop_loss" and avg_entry > 0:
                    if (avg_entry - price) / avg_entry * 100 >= self.stop_loss_pct:
                        exit_triggered = True
                if exit_triggered:
                    signals[i] = "SELL"; qtys[i] = total_qty
                    meta[i] = {"pla_exit": self.exit_type, "avg_entry": round(avg_entry, 4)}
                    in_position = False; entry_price = 0.0; avg_entry = 0.0
                    total_qty = 0.0; levels_filled = set()
        df["signal"] = signals; df["quantity"] = qtys; df["meta"] = meta
        logger.info("PLA signals — buys: %d | sells: %d", signals.count("BUY"), signals.count("SELL"))
        return df
