from __future__ import annotations
import logging, math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd
from config import DEFAULT_FEE_PERCENT, DEFAULT_SLIPPAGE_PERCENT
from engine.cost_models import IndianCostModel, SimpleCostModel, CostBreakdown, aggregate_cost_breakdown

logger = logging.getLogger(__name__)

@dataclass
class Position:
    symbol: str; quantity: float; avg_price: float; entry_time: datetime; entry_price: float
    @property
    def total_cost(self): return self.quantity * self.avg_price

@dataclass
class TradeRecord:
    entry_time: datetime; entry_price: float; exit_time: datetime; exit_price: float
    quantity: float; pnl: float; pnl_pct: float; fees: float; side: str = "LONG"
    def to_dict(self):
        return {
            "entry_time":  str(self.entry_time) if not hasattr(self.entry_time, "isoformat") else self.entry_time.isoformat(),
            "entry_price": round(self.entry_price, 6), "exit_time": str(self.exit_time) if not hasattr(self.exit_time, "isoformat") else self.exit_time.isoformat(),
            "exit_price": round(self.exit_price, 6), "quantity": round(self.quantity, 6),
            "pnl": round(self.pnl, 4), "pnl_pct": round(self.pnl_pct, 4),
            "fees": round(self.fees, 4), "side": self.side,
        }


class TradeSimulator:
    def __init__(self, symbol="BTC/USDT", capital=10_000.0, fee_percent=DEFAULT_FEE_PERCENT,
                 slippage_percent=DEFAULT_SLIPPAGE_PERCENT, use_indian_costs=False,
                 market_type="equity_delivery", brokerage_model="flat", brokerage_flat=20.0,
                 brokerage_pct=0.005, lot_size=1):
        self.symbol = symbol; self.initial_capital = capital; self.fee_percent = fee_percent
        self.slippage_percent = slippage_percent; self.use_indian_costs = use_indian_costs
        self.market_type = market_type; self.brokerage_model = brokerage_model
        self.brokerage_flat = brokerage_flat; self.brokerage_pct = brokerage_pct
        self.lot_size = max(1, int(lot_size))
        self._indian_calc = IndianCostModel() if use_indian_costs else None
        self._simple_calc = SimpleCostModel(fee_percent)
        self._reset()

    def run(self, df: pd.DataFrame) -> dict:
        self._reset()
        for _, row in df.iterrows():
            ts = row["timestamp"]; price = float(row["close"])
            sig = row.get("signal", "HOLD"); qty = float(row.get("quantity", 0))
            if self.lot_size > 1 and qty > 0:
                qty = math.floor(qty / self.lot_size) * self.lot_size
                if qty <= 0:
                    if sig == "BUY": self._lot_size_skips += 1
                    self._equity_curve.append(self._mark_equity(price))
                    self._timestamps.append(ts); continue
            if sig == "BUY" and qty > 0: self._execute_buy(price, qty, ts)
            elif sig == "SELL" and qty > 0: self._execute_sell(price, qty, ts)
            self._equity_curve.append(self._mark_equity(price)); self._timestamps.append(ts)
        if self._position and len(df):
            last = df.iloc[-1]
            self._execute_sell(float(last["close"]), self._position.quantity, last["timestamp"])
        return {
            "equity_curve": self._equity_curve, "timestamps": [str(t) for t in self._timestamps],
            "trades": [t.to_dict() for t in self._trades],
            "final_equity": self._equity_curve[-1] if self._equity_curve else self.initial_capital,
            "total_fees_paid": round(self._total_fees, 4), "position": self._position,
            "lot_size_skips": self._lot_size_skips,
            "cost_breakdown": (aggregate_cost_breakdown(self._cost_breakdowns)
                               if self.use_indian_costs and self._cost_breakdowns else {}),
        }

    def _calculate_cost(self, turnover, side, track=True):
        if self._indian_calc is not None:
            cb = self._indian_calc.calculate(turnover, side, self.market_type,
                                             self.brokerage_model, self.brokerage_flat, self.brokerage_pct)
            if track: self._cost_breakdowns.append(cb)
            return cb.total
        return self._simple_calc.calculate(turnover, side)

    def _execute_buy(self, price, quantity, timestamp):
        actual_price = price * (1 + self.slippage_percent)
        cost = quantity * actual_price
        fee  = self._calculate_cost(cost, "BUY", track=False)
        total_cost = cost + fee
        if total_cost > self._cash:
            if self._cash <= 0: return 0.0
            if self.use_indian_costs:
                affordable = self._cash * 0.97 / actual_price
                if self.lot_size > 1: affordable = math.floor(affordable / self.lot_size) * self.lot_size
                if affordable <= 0: return 0.0
                quantity = affordable; cost = quantity * actual_price
                fee = self._calculate_cost(cost, "BUY", track=True); total_cost = cost + fee
            else:
                quantity = self._cash / (actual_price * (1 + self.fee_percent))
                cost = quantity * actual_price
                fee = self._calculate_cost(cost, "BUY", track=True); total_cost = cost + fee
        else:
            self._calculate_cost(cost, "BUY", track=True)
        self._cash -= total_cost; self._total_fees += fee
        if self._position is None:
            self._position = Position(self.symbol, quantity, actual_price, timestamp, actual_price)
        else:
            old_qty = self._position.quantity; old_avg = self._position.avg_price
            new_qty = old_qty + quantity
            self._position.quantity  = new_qty
            self._position.avg_price = (old_qty * old_avg + quantity * actual_price) / new_qty
        return quantity

    def _execute_sell(self, price, quantity, timestamp):
        if self._position is None or self._position.quantity <= 0: return 0.0
        quantity     = min(quantity, self._position.quantity)
        actual_price = price * (1 - self.slippage_percent)
        proceeds     = quantity * actual_price
        fee          = self._calculate_cost(proceeds, "SELL")
        pnl          = (actual_price - self._position.avg_price) * quantity - fee
        pnl_pct      = pnl / (self._position.avg_price * quantity) if self._position.avg_price > 0 else 0.0
        self._trades.append(TradeRecord(self._position.entry_time, self._position.avg_price,
                                        timestamp, actual_price, quantity, pnl, pnl_pct, fee))
        self._cash += proceeds - fee; self._total_fees += fee
        self._position.quantity -= quantity
        if self._position.quantity <= 1e-10: self._position = None
        return quantity

    def _mark_equity(self, current_price):
        mtm = self._position.quantity * current_price if self._position else 0.0
        return round(self._cash + mtm, 4)

    def _reset(self):
        self._cash = self.initial_capital; self._position = None; self._trades = []
        self._equity_curve = [self.initial_capital]; self._timestamps = []
        self._total_fees = 0.0; self._cost_breakdowns = []; self._lot_size_skips = 0
