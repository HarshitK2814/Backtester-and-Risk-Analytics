from __future__ import annotations
import logging
from typing import Any
import numpy as np
import pandas as pd
from engine.metrics import _candles_per_day, _trade_statistics

logger = logging.getLogger(__name__)
TRADING_DAYS_PER_YEAR = 252
REGIMES = ("bull", "bear", "sideways")


def classify_regimes(df: pd.DataFrame) -> list[str]:
    n = len(df)
    if n == 0:
        return []
    close = df["close"].astype(float).values
    cpd       = _candles_per_day(df["timestamp"].tolist()) if "timestamp" in df.columns else 1.0
    long_days  = float(np.clip(n / cpd / 5, 10, 60))
    short_days = max(2.0, long_days / 3)
    long_w     = max(2, round(long_days  * cpd))
    short_w    = max(2, round(short_days * cpd))

    close_s  = pd.Series(close)
    long_ma  = close_s.rolling(long_w,  min_periods=long_w).mean().values
    short_ma = close_s.rolling(short_w, min_periods=short_w).mean().values
    slope    = pd.Series(short_ma).pct_change(periods=short_w).values
    returns  = close_s.pct_change().values
    rv       = pd.Series(returns).rolling(short_w, min_periods=2).std().values
    med_rv   = float(np.nanmedian(rv)) if not np.all(np.isnan(rv)) else 1e-4
    eps      = max(0.3 * med_rv, 1e-5)

    labels = []
    for i in range(n):
        c, lm, sm, sl = close[i], long_ma[i], short_ma[i], slope[i]
        if np.isnan(lm) or np.isnan(sm) or np.isnan(sl):
            labels.append("sideways")
        elif c > lm and sm > lm and sl > eps:
            labels.append("bull")
        elif c < lm and sm < lm and sl < -eps:
            labels.append("bear")
        else:
            labels.append("sideways")
    return labels


def regime_breakdown(equity_curve, timestamps, trades, regimes, initial_capital=10_000.0) -> dict[str, Any]:
    regimes = list(regimes)
    eq_raw  = list(equity_curve)
    if len(eq_raw) == len(regimes) + 1:
        eq_raw = eq_raw[1:]
    elif len(regimes) > len(eq_raw):
        regimes = regimes[-len(eq_raw):]
    elif len(regimes) < len(eq_raw):
        regimes = ["sideways"] * (len(eq_raw) - len(regimes)) + regimes

    n = len(eq_raw)
    if n == 0 or not regimes:
        return {"method": "ma_trend_tf_aware", "regime_counts": {r: 0 for r in REGIMES},
                **{r: {"total_return_pct": 0.0, "sharpe_ratio": 0.0, "num_trades": 0, "win_rate": 0.0,
                       "max_drawdown_pct": 0.0, "num_candles": 0, "pct_of_period": 0.0,
                       "profit_factor": 0.0, "avg_trade_pnl": 0.0, "best_trade": 0.0,
                       "worst_trade": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
                       "avg_trade_duration": 0.0, "trades_per_day": 0.0, "sortino_ratio": 0.0,
                       "volatility_pct": 0.0} for r in REGIMES}}

    eq   = np.array(eq_raw, dtype=float)
    can_rets = np.diff(eq) / np.where(eq[:-1] != 0, eq[:-1], 1.0)
    cpd  = _candles_per_day(timestamps)
    ts_to_idx = {str(t): i for i, t in enumerate(timestamps)}

    result: dict[str, Any] = {"method": "ma_trend_tf_aware",
                               "regime_counts": {r: regimes.count(r) for r in REGIMES}}
    for regime in REGIMES:
        mask     = np.array([r == regime for r in regimes], dtype=bool)
        n_regime = int(mask.sum())
        if n_regime < 2:
            result[regime] = {"total_return_pct": 0.0, "sharpe_ratio": 0.0, "sortino_ratio": 0.0,
                              "volatility_pct": 0.0, "max_drawdown_pct": 0.0,
                              "num_candles": n_regime, "pct_of_period": round(100 * n_regime / n, 2),
                              **_trade_statistics([])}
            continue
        r_rets = can_rets[mask[:-1]]
        compound_ret = float(np.prod(1 + r_rets) - 1) if len(r_rets) else 0.0
        mean_r = float(np.mean(r_rets)) if len(r_rets) else 0.0
        std_r  = float(np.std(r_rets))  if len(r_rets) else 0.0
        sharpe = mean_r / std_r * np.sqrt(TRADING_DAYS_PER_YEAR * cpd) if std_r > 1e-10 else 0.0
        down   = r_rets[r_rets < 0]
        dstd   = float(np.std(down)) if len(down) > 1 else 1e-10
        sortino = mean_r / dstd * np.sqrt(TRADING_DAYS_PER_YEAR * cpd) if dstd > 1e-10 else 0.0
        volatility = float(std_r * np.sqrt(TRADING_DAYS_PER_YEAR * cpd))
        sub_eq = np.cumprod(np.concatenate([[1.0], 1 + r_rets])) * initial_capital
        run_mx = np.maximum.accumulate(sub_eq)
        dd_arr = (sub_eq - run_mx) / np.where(run_mx != 0, run_mx, 1.0)
        max_dd = float(np.min(dd_arr))
        regime_trades = [t for t in trades
                         if ts_to_idx.get(str(t.get("entry_time","")), None) is not None
                         and regimes[ts_to_idx[str(t["entry_time"])]] == regime]
        result[regime] = {
            "total_return_pct": round(compound_ret * 100, 4),
            "sharpe_ratio":     round(sharpe,    4),
            "sortino_ratio":    round(sortino,   4),
            "volatility_pct":   round(volatility * 100, 4),
            "max_drawdown_pct": round(max_dd * 100, 4),
            "num_candles":      n_regime,
            "pct_of_period":    round(100 * n_regime / n, 2),
            **_trade_statistics(regime_trades),
        }
    return result
