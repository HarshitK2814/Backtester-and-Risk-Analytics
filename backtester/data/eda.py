from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class EDAEngine:
    def __init__(self, charts_dir: Path | None = None):
        if charts_dir is None:
            from config import CHARTS_DIR
            charts_dir = CHARTS_DIR
        self.charts_dir = Path(charts_dir)
        self.charts_dir.mkdir(exist_ok=True)

    def analyse(self, df: pd.DataFrame, symbol: str) -> dict[str, Any]:
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

        report: dict[str, Any] = {"symbol": symbol}
        report["statistics"]    = self._statistics(df)
        report["distributions"] = self._distributions(df)
        report["seasonality"]   = self._seasonality(df)
        report["trends"]        = self._trends(df)
        report["correlations"]  = self._correlations(df)
        report["volatility"]    = self._volatility(df)
        report["charts"]        = self._generate_charts(df, symbol)
        return report

    def _statistics(self, df: pd.DataFrame) -> dict:
        close = df["close"]
        volume = df["volume"]
        returns = close.pct_change().dropna()
        return {
            "total_candles": int(len(df)),
            "date_range": {
                "start": str(df["timestamp"].min().date()),
                "end":   str(df["timestamp"].max().date()),
                "days":  int((df["timestamp"].max() - df["timestamp"].min()).days),
            },
            "close": {
                "mean":    round(float(close.mean()), 4),
                "median":  round(float(close.median()), 4),
                "std":     round(float(close.std()), 4),
                "min":     round(float(close.min()), 4),
                "max":     round(float(close.max()), 4),
                "q25":     round(float(close.quantile(0.25)), 4),
                "q75":     round(float(close.quantile(0.75)), 4),
            },
            "volume": {
                "total":   round(float(volume.sum()), 2),
                "mean":    round(float(volume.mean()), 2),
                "max":     round(float(volume.max()), 2),
            },
            "returns": {
                "mean_pct":  round(float(returns.mean() * 100), 4),
                "std_pct":   round(float(returns.std() * 100), 4),
                "total_pct": round(float((close.iloc[-1] / close.iloc[0] - 1) * 100), 2),
            },
        }

    def _distributions(self, df: pd.DataFrame) -> dict:
        from scipy import stats as sp_stats
        returns = df["close"].pct_change().dropna()
        log_returns = np.log(df["close"] / df["close"].shift(1)).dropna()
        skewness  = float(sp_stats.skew(returns))
        kurtosis  = float(sp_stats.kurtosis(returns))
        _, p_norm = sp_stats.normaltest(returns)
        hist_counts, hist_edges = np.histogram(returns * 100, bins=20)
        hist_data = [
            {"bin": round(float((hist_edges[i] + hist_edges[i + 1]) / 2), 4),
             "count": int(hist_counts[i])}
            for i in range(len(hist_counts))
        ]
        return {
            "skewness":           round(skewness, 4),
            "kurtosis":           round(kurtosis, 4),
            "is_normal_dist":     bool(p_norm > 0.05),
            "normality_p_value":  round(float(p_norm), 6),
            "return_histogram":   hist_data,
            "log_return_std":     round(float(log_returns.std()), 6),
            "positive_days_pct":  round(float((returns > 0).mean() * 100), 2),
        }

    def _seasonality(self, df: pd.DataFrame) -> dict:
        df2 = df.copy()
        df2["month"]    = df2["timestamp"].dt.month
        df2["weekday"]  = df2["timestamp"].dt.dayofweek
        df2["returns"]  = df2["close"].pct_change()
        monthly = (
            df2.groupby("month")["returns"]
            .agg(["mean", "std", "count"])
            .round(6)
            .reset_index()
            .rename(columns={"mean": "avg_return", "std": "volatility", "count": "candles"})
        )
        monthly["month_name"] = monthly["month"].apply(
            lambda m: ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][m - 1]
        )
        weekly = (
            df2.groupby("weekday")["returns"]
            .agg(["mean", "std", "count"])
            .round(6)
            .reset_index()
            .rename(columns={"mean": "avg_return", "std": "volatility", "count": "candles"})
        )
        weekly["day_name"] = weekly["weekday"].apply(
            lambda d: ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d]
        )
        best_month  = monthly.loc[monthly["avg_return"].idxmax()]
        worst_month = monthly.loc[monthly["avg_return"].idxmin()]
        return {
            "monthly":     monthly.to_dict(orient="records"),
            "weekly":      weekly.to_dict(orient="records"),
            "best_month":  best_month["month_name"],
            "worst_month": worst_month["month_name"],
        }

    def _trends(self, df: pd.DataFrame) -> dict:
        close = df["close"]
        ma_20  = float(close.rolling(20).mean().iloc[-1]) if len(df) >= 20 else None
        ma_50  = float(close.rolling(50).mean().iloc[-1]) if len(df) >= 50 else None
        ma_200 = float(close.rolling(200).mean().iloc[-1]) if len(df) >= 200 else None
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = (100 - 100 / (1 + rs)).iloc[-1]
        ema12  = close.ewm(span=12, adjust=False).mean()
        ema26  = close.ewm(span=26, adjust=False).mean()
        macd   = (ema12 - ema26).iloc[-1]
        signal = (ema12 - ema26).ewm(span=9, adjust=False).mean().iloc[-1]
        ath = float(df["high"].max())
        atl = float(df["low"].min())
        pct_from_ath = float((close.iloc[-1] - ath) / ath * 100)
        return {
            "last_close":       round(float(close.iloc[-1]), 4),
            "ma_20":            round(ma_20,  4) if ma_20  else None,
            "ma_50":            round(ma_50,  4) if ma_50  else None,
            "ma_200":           round(ma_200, 4) if ma_200 else None,
            "rsi_14":           round(float(rsi), 2) if not np.isnan(rsi) else None,
            "macd":             round(float(macd), 4),
            "macd_signal":      round(float(signal), 4),
            "all_time_high":    round(ath, 4),
            "all_time_low":     round(atl, 4),
            "pct_from_ath":     round(pct_from_ath, 2),
        }

    def _correlations(self, df: pd.DataFrame) -> dict:
        cols = ["open", "high", "low", "close", "volume"]
        existing = [c for c in cols if c in df.columns]
        corr_matrix = df[existing].corr().round(4)
        return {
            "matrix": corr_matrix.to_dict(),
            "price_volume_corr": round(float(df["close"].corr(df["volume"])), 4),
        }

    def _volatility(self, df: pd.DataFrame) -> dict:
        returns = df["close"].pct_change().dropna()
        daily_vol = float(returns.std())
        annual_vol = daily_vol * np.sqrt(252)
        rolling_vol = returns.rolling(30).std() * np.sqrt(252)
        vol_series  = rolling_vol.dropna()
        return {
            "daily_volatility":         round(daily_vol * 100, 4),
            "annualised_volatility_pct": round(annual_vol * 100, 2),
            "max_rolling_30d_vol":       round(float(vol_series.max() * 100), 2) if len(vol_series) else None,
            "min_rolling_30d_vol":       round(float(vol_series.min() * 100), 2) if len(vol_series) else None,
            "current_rolling_30d_vol":   round(float(vol_series.iloc[-1] * 100), 2) if len(vol_series) else None,
        }

    def _generate_charts(self, df: pd.DataFrame, symbol: str) -> list[str]:
        try:
            import plotly.graph_objects as go
            import plotly.io as pio
        except ImportError:
            return []

        charts = []
        safe_sym = symbol.replace("/", "_")

        try:
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df["timestamp"], open=df["open"], high=df["high"],
                low=df["low"], close=df["close"], name="OHLC",
            ))
            fig.add_trace(go.Bar(
                x=df["timestamp"], y=df["volume"], name="Volume",
                yaxis="y2", opacity=0.3, marker_color="steelblue",
            ))
            fig.update_layout(
                title=f"{symbol} - Price & Volume",
                template="plotly_dark",
                yaxis2=dict(overlaying="y", side="right", showgrid=False),
                height=500,
            )
            p = self.charts_dir / f"{safe_sym}_price_volume.png"
            pio.write_image(fig, str(p))
            charts.append(str(p))
        except Exception as e:
            logger.warning("Price chart failed: %s", e)

        try:
            returns = df["close"].pct_change().dropna() * 100
            fig = go.Figure(go.Histogram(x=returns, nbinsx=50, name="Daily Returns", marker_color="#1E88E5"))
            fig.update_layout(
                title=f"{symbol} - Daily Return Distribution",
                xaxis_title="Return (%)", yaxis_title="Count",
                template="plotly_dark", height=400,
            )
            p = self.charts_dir / f"{safe_sym}_returns_dist.png"
            pio.write_image(fig, str(p))
            charts.append(str(p))
        except Exception as e:
            logger.warning("Returns chart failed: %s", e)

        return charts
