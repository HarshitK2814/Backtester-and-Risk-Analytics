from __future__ import annotations
import logging
from typing import Any
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
TRADING_DAYS_PER_YEAR = 252


def calculate_metrics(trades, equity_curve, timestamps, initial_capital=10_000.0) -> dict[str, Any]:
    if not equity_curve:
        return _empty_metrics(initial_capital)

    eq = np.array(equity_curve, dtype=float)
    total_return_usd = float(eq[-1] - eq[0])
    total_return_pct = float((eq[-1] - eq[0]) / eq[0]) if eq[0] != 0 else 0.0

    candle_returns = np.diff(eq) / eq[:-1]
    candle_returns = candle_returns[np.isfinite(candle_returns)]

    cpd = _candles_per_day(timestamps)
    n_days = len(eq) / max(cpd, 1)
    ann_return = float((eq[-1] / eq[0]) ** (TRADING_DAYS_PER_YEAR / max(n_days, 1)) - 1) if eq[0] > 0 else 0.0

    mean_ret = float(np.mean(candle_returns)) if len(candle_returns) else 0.0
    std_ret  = float(np.std(candle_returns))  if len(candle_returns) else 0.0
    sharpe   = mean_ret / std_ret * np.sqrt(TRADING_DAYS_PER_YEAR * cpd) if std_ret > 1e-10 else 0.0

    downside = candle_returns[candle_returns < 0]
    down_std = float(np.std(downside)) if len(downside) > 1 else 1e-10
    sortino  = mean_ret / down_std * np.sqrt(TRADING_DAYS_PER_YEAR * cpd) if down_std > 1e-10 else 0.0

    running_max = np.maximum.accumulate(eq)
    drawdowns   = (eq - running_max) / running_max
    drawdowns   = np.where(running_max == 0, 0, drawdowns)
    max_dd      = float(np.min(drawdowns))
    dd_duration = _max_dd_duration(drawdowns)
    calmar      = ann_return / abs(max_dd) if abs(max_dd) > 1e-10 else 0.0
    volatility  = float(std_ret * np.sqrt(TRADING_DAYS_PER_YEAR * cpd)) if std_ret > 0 else 0.0

    trade_stats = _trade_statistics(trades)
    metrics = {
        "total_return_usd":       round(total_return_usd, 4),
        "total_return_pct":       round(total_return_pct * 100, 4),
        "annualised_return_pct":  round(ann_return * 100, 4),
        "final_equity":           round(float(eq[-1]), 4),
        "initial_capital":        round(initial_capital, 4),
        "sharpe_ratio":           round(sharpe,   4),
        "sortino_ratio":          round(sortino,  4),
        "calmar_ratio":           round(calmar,   4),
        "volatility_pct":         round(volatility * 100, 4),
        "max_drawdown_pct":       round(max_dd * 100, 4),
        "max_dd_duration_candles": int(dd_duration),
        **trade_stats,
        "equity_curve":  [round(float(v), 4) for v in eq],
        "drawdowns":     [round(float(v) * 100, 4) for v in drawdowns],
        "timestamps":    [str(t) for t in timestamps],
        "trades":        trades,
    }
    logger.info("Metrics — return: %.2f%% | sharpe: %.2f | max_dd: %.2f%% | trades: %d",
                metrics["total_return_pct"], metrics["sharpe_ratio"],
                metrics["max_drawdown_pct"], metrics["num_trades"])
    return metrics


def _trade_statistics(trades):
    if not trades:
        return {"num_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "avg_trade_pnl": 0.0,
                "best_trade": 0.0, "worst_trade": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
                "avg_trade_duration": 0.0, "trades_per_day": 0.0}
    pnls    = [t["pnl"] for t in trades]
    winners = [p for p in pnls if p > 0]
    losers  = [p for p in pnls if p <= 0]
    gross_profit = sum(winners)
    gross_loss   = abs(sum(losers))
    profit_factor = gross_profit / gross_loss if gross_loss > 1e-10 else float("inf")
    durations = []
    for t in trades:
        try:
            durations.append((pd.Timestamp(t["exit_time"]) - pd.Timestamp(t["entry_time"])).total_seconds() / 3600)
        except Exception:
            pass
    avg_duration = float(np.mean(durations)) if durations else 0.0
    try:
        days = max((pd.Timestamp(trades[-1]["exit_time"]) - pd.Timestamp(trades[0]["entry_time"])).days, 1)
        trades_per_day = len(trades) / days
    except Exception:
        trades_per_day = 0.0
    return {
        "num_trades": len(trades), "win_rate": round(len(winners) / len(trades) * 100, 2),
        "profit_factor": round(profit_factor, 4), "avg_trade_pnl": round(float(np.mean(pnls)), 4),
        "best_trade": round(max(pnls), 4), "worst_trade": round(min(pnls), 4),
        "gross_profit": round(gross_profit, 4), "gross_loss": round(gross_loss, 4),
        "avg_trade_duration": round(avg_duration, 2), "trades_per_day": round(trades_per_day, 4),
    }


def _candles_per_day(timestamps) -> float:
    if len(timestamps) < 2:
        return 1.0
    try:
        ts = [pd.Timestamp(t) for t in timestamps[:50]]
        diffs = [(ts[i+1] - ts[i]).total_seconds() for i in range(len(ts)-1)]
        median_sec = float(np.median(diffs))
        return max(1.0, 86_400 / median_sec)
    except Exception:
        return 1.0


def _max_dd_duration(drawdowns) -> int:
    max_dur = cur_dur = 0
    for dd in drawdowns:
        if dd < 0:
            cur_dur += 1
            max_dur = max(max_dur, cur_dur)
        else:
            cur_dur = 0
    return max_dur


def _empty_metrics(initial_capital):
    return {
        "total_return_usd": 0.0, "total_return_pct": 0.0, "annualised_return_pct": 0.0,
        "final_equity": initial_capital, "initial_capital": initial_capital,
        "sharpe_ratio": 0.0, "sortino_ratio": 0.0, "calmar_ratio": 0.0, "volatility_pct": 0.0,
        "max_drawdown_pct": 0.0, "max_dd_duration_candles": 0,
        "num_trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "avg_trade_pnl": 0.0,
        "best_trade": 0.0, "worst_trade": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
        "avg_trade_duration": 0.0, "trades_per_day": 0.0,
        "equity_curve": [initial_capital], "drawdowns": [0.0], "timestamps": [], "trades": [],
    }
