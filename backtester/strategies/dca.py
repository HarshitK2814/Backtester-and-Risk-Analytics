from __future__ import annotations
import logging
from typing import Any
import pandas as pd
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

class DCAStrategy(BaseStrategy):
    """DCA strategy: regular interval buys with time-based or profit-target exit."""

    @staticmethod
    def default_params() -> dict[str, Any]:
        return {
            "buy_interval_hours": 24, "invest_per_buy_usd": 200.0,
            "buy_quantity": 0.001, "hold_days": 30,
            "exit_type": "time", "profit_target_pct": 10.0,
        }

    def _validate_params(self, params):
        if params["buy_interval_hours"] <= 0: raise ValueError("buy_interval_hours must be > 0")
        if params["hold_days"] <= 0: raise ValueError("hold_days must be > 0")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        n = len(df)
        signals = ["HOLD"] * n; qtys = [0.0] * n; meta = [{}] * n
        if n > 1:
            diffs = df["timestamp"].diff().dropna()
            median_hours = diffs.median().total_seconds() / 3600
        else:
            median_hours = 24.0
        buy_every_n  = max(1, round(self.buy_interval_hours / median_hours))
        hold_candles = max(1, round(self.hold_days * 24 / median_hours))
        avg_entry_price = 0.0; accumulated_qty = 0.0; i = 0
        while i < n:
            phase_end = min(i + hold_candles, n)
            buy_count = 0
            for j in range(i, phase_end):
                if (j - i) % buy_every_n == 0:
                    price = float(df.iloc[j]["close"])
                    invest = getattr(self, "invest_per_buy_usd", 0)
                    qty = (invest / price) if (invest > 0 and price > 0) else self.buy_quantity
                    signals[j] = "BUY"; qtys[j] = qty
                    meta[j] = {"dca_buy_count": buy_count + 1}
                    total_cost = avg_entry_price * accumulated_qty + price * qty
                    accumulated_qty += qty
                    avg_entry_price = total_cost / accumulated_qty if accumulated_qty > 0 else price
                    buy_count += 1
            sell_idx = min(phase_end, n - 1)
            if accumulated_qty > 0:
                price = float(df.iloc[sell_idx]["close"])
                if self.exit_type == "profit":
                    for k in range(i, min(phase_end + 1, n)):
                        p = float(df.iloc[k]["close"])
                        if avg_entry_price > 0 and (p - avg_entry_price) / avg_entry_price * 100 >= self.profit_target_pct:
                            sell_idx = k; price = p; break
                signals[sell_idx] = "SELL"; qtys[sell_idx] = accumulated_qty
                meta[sell_idx] = {"dca_sell": True, "avg_entry": round(avg_entry_price, 4)}
                avg_entry_price = 0.0; accumulated_qty = 0.0
            i = sell_idx + 1
        df["signal"] = signals; df["quantity"] = qtys; df["meta"] = meta
        logger.info("DCA signals — buys: %d | sells: %d", signals.count("BUY"), signals.count("SELL"))
        return df
