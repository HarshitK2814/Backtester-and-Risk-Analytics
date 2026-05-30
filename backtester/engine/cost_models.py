from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Literal

MarketType     = Literal["equity_delivery", "equity_intraday", "futures", "options"]
BrokerageModel = Literal["flat", "percentage", "zero"]

@dataclass
class CostBreakdown:
    brokerage:        float = 0.0
    stt:              float = 0.0
    exchange_charges: float = 0.0
    sebi_charges:     float = 0.0
    gst:              float = 0.0
    stamp_duty:       float = 0.0
    total:            float = 0.0

    def as_dict(self) -> dict:
        return {k: round(v, 4) for k, v in asdict(self).items()}


class SimpleCostModel:
    def __init__(self, fee_pct: float = 0.001):
        self.fee_pct = fee_pct
    def calculate(self, turnover: float, side: str) -> float:
        return round(turnover * self.fee_pct, 4)


class IndianCostModel:
    _STT_RATES = {
        "equity_delivery_buy":  0.001,
        "equity_delivery_sell": 0.001,
        "equity_intraday_sell": 0.00025,
        "futures_sell":         0.0002,
        "options_sell":         0.001,
    }
    _ETC = {"equity": 0.0000297, "futures": 0.0000173, "options": 0.0003503}
    _SEBI  = 0.000001
    _GST   = 0.18
    _STAMP = {"equity_delivery": 0.00015, "equity_intraday": 0.00003,
              "futures": 0.00003, "options": 0.00003}

    def calculate(self, turnover, side, market_type="equity_delivery",
                  brokerage_model="flat", brokerage_flat=20.0, brokerage_pct=0.005) -> CostBreakdown:
        cb = CostBreakdown()
        if turnover <= 0:
            return cb
        if brokerage_model == "flat":
            cb.brokerage = min(brokerage_flat, turnover * (0.001 if market_type == "equity_delivery" else 0.025))
        elif brokerage_model == "percentage":
            cb.brokerage = turnover * brokerage_pct
        key = f"{market_type}_{side.lower()}"
        cb.stt = turnover * self._STT_RATES.get(key, 0.0)
        if market_type in ("equity_delivery", "equity_intraday"):
            cb.exchange_charges = turnover * self._ETC["equity"]
        elif market_type == "futures":
            cb.exchange_charges = turnover * self._ETC["futures"]
        else:
            cb.exchange_charges = turnover * self._ETC["options"]
        cb.sebi_charges = turnover * self._SEBI
        cb.gst = (cb.brokerage + cb.exchange_charges + cb.sebi_charges) * self._GST
        if side.upper() == "BUY":
            cb.stamp_duty = turnover * self._STAMP.get(market_type, 0.0)
        cb.total = cb.brokerage + cb.stt + cb.exchange_charges + cb.sebi_charges + cb.gst + cb.stamp_duty
        return cb

    def effective_pct(self, market_type="equity_delivery", brokerage_model="flat",
                      brokerage_flat=20.0, sample_turnover=100_000.0) -> float:
        buy  = self.calculate(sample_turnover, "BUY",  market_type, brokerage_model, brokerage_flat)
        sell = self.calculate(sample_turnover, "SELL", market_type, brokerage_model, brokerage_flat)
        return round((buy.total + sell.total) / sample_turnover * 100, 3)


def aggregate_cost_breakdown(breakdowns: list[CostBreakdown]) -> dict:
    totals = CostBreakdown()
    for cb in breakdowns:
        totals.brokerage        += cb.brokerage
        totals.stt              += cb.stt
        totals.exchange_charges += cb.exchange_charges
        totals.sebi_charges     += cb.sebi_charges
        totals.gst              += cb.gst
        totals.stamp_duty       += cb.stamp_duty
        totals.total            += cb.total
    return totals.as_dict()
